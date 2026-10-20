"""EINGEFRORENE REFERENZ (nicht ändern): Wellenplanung aus `roboprint/patterns/families/wellen.py`
und Schalenwechsel (`lane_change`, `clear_end`) aus `roboprint/patterns/shells.py` vor der
Wellen-Laufzeitoptimierung (Commit 5dd66ee), ohne Registrierung. Die Abtastung nutzt die
eingefrorene `resample_curve` (patterns_resample_reference.py). Der Gleichheitstest in
test_patterns_wellen_perf.py setzt diese Funktionen per monkeypatch ein und vergleicht die Pfade."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from patterns_resample_reference import resample_curve
from roboprint.patterns.geometry import Loop, biarc, dedupe, densify, fillet_polyline, polygons
from roboprint.patterns.layout import fit_to_length
from roboprint.patterns.metrics import RADIUS_TOL
from roboprint.patterns.shells import CLEAR_TOL_MM, FINE_TOL_MM
from roboprint.patterns.types import Contact, IslandContext, IslandPlan, PatternParams, Segment

#: Abtastung der Sollkurve vor dem Neu-Abtasten (mm)
FINE_MM = 1.0
#: Abtastung für Abstandsprüfungen (mm)
CHECK_MM = 2.0
#: Reserve über (1 − ε)·w bei der Einlaufsuche (Sehnenfehler der späteren Abtastung)
CLEAR_MARGIN_MM = 0.3
#: Reserve über w/2 für Eckbögen (M6 hart nach dem Neu-Abtasten)
R_HARD_MARGIN_MM = 0.5
#: Mindestanteil Bandfläche / umschreibendes Rechteck, damit das Band als Rechteck gilt
RECT_FILL = 0.97
#: Länge der Endstücke einer Geraden zwischen zwei Bögen (Wegpunkte, M6-Schätzung)
STRAIGHT_END_MM = 4.0
#: Suchbereich des Wellenanfangs hinter der Projektion des Eintritts (in w)
SEARCH_W = 3.0

# --------------------------------------------------------------------------- Band


def band_frame(ctx: IslandContext) -> dict[str, Any] | None:
    """Bandachse: Mitte, e_u (vom Eintritt weg), e_v, Länge, halbe Breite. None, wenn das Band
    fehlt oder kein Rechteck ist."""
    parts = polygons(ctx.band)
    if not parts:
        return None
    band = max(parts, key=lambda g: g.area)
    mrr = band.minimum_rotated_rectangle
    if mrr.area <= 0 or band.area / mrr.area < RECT_FILL:
        return None
    c = np.asarray(mrr.exterior.coords)[:4]
    e1, e2 = c[1] - c[0], c[2] - c[1]
    eu, ev = (e1, e2) if np.linalg.norm(e1) >= np.linalg.norm(e2) else (e2, e1)
    length, width = float(np.linalg.norm(eu)), float(np.linalg.norm(ev))
    eu = eu / length
    center = c.mean(axis=0)
    entry = ctx.entry if ctx.entry is not None else center - eu
    if float((entry - center) @ eu) > 0:
        eu = -eu
    ev = np.array([-eu[1], eu[0]])
    return {
        "center": center,
        "eu": eu,
        "ev": ev,
        "length": length,
        "half": width / 2.0,
        "n_parts": len(parts),
    }


def to_xy(fr: dict[str, Any], uv: np.ndarray) -> np.ndarray:
    return fr["center"] + uv[:, :1] * fr["eu"] + uv[:, 1:2] * fr["ev"]


# --------------------------------------------------------------------------- Wellenformen


def sine_uv(u_s: float, u_e: float, lam: float, amp: float, phase: float, sigma: float) -> np.ndarray:
    # Stücke ≤ FINE_MM auch an steilen Flanken (resample_pieces hält längere Stücke für Geraden)
    du = FINE_MM / math.sqrt(1.0 + (2 * math.pi * amp / lam) ** 2)
    n = max(2, math.ceil((u_e - u_s) / du) + 1)
    u = np.linspace(u_s, u_e, n)
    return np.column_stack([u, sigma * amp * np.cos(2 * math.pi * (u - u_s) / lam + phase)])


def zigzag_height(lam: float, amp: float, radius: float) -> float:
    """Höhe H der Zickzack-Scheitelpunkte, bei der der Bogenscheitel (Radius r) genau A erreicht:
    H − r·(√(1 + (4H/λ)²) − 1) = A. Lösbar nur für λ > 4·r (sonst wächst der Abzug schneller als
    H: zwei Bögen mit r füllen die Halbwelle allein); dann inf."""
    if lam <= 4.0 * radius:
        return math.inf
    f = lambda h: h - radius * (math.sqrt(1.0 + (4.0 * h / lam) ** 2) - 1.0) - amp  # noqa: E731
    lo, hi = amp, amp + 1.0
    while f(hi) < 0:
        hi *= 2.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return hi


def trapezoid_uv(
    u_s: float, u_e: float, lam: float, amp: float, phase: float, sigma: float, plateau: float, radius: float
) -> tuple[np.ndarray, float, float]:
    """Gerundete Trapezwelle (plateau = 0: Zickzack, plateau = λ/2: Mäander), Plateaumitte des
    ersten Scheitels bei u_s − phase/(2π)·λ. Rückgabe (uv, kleinster Eckradius, erreichte
    Amplitude); uv ist leer, wenn die Form mit diesem r nicht in die Halbwelle passt."""
    half = lam / 2.0
    P = min(max(plateau, 0.0), half)
    shift = phase / (2 * math.pi) * lam
    height = amp if P > 1e-9 else zigzag_height(lam, amp, radius)
    if not math.isfinite(height):
        return np.zeros((0, 2)), 0.0, 0.0
    verts = []
    for j in range(math.floor(shift / half) - 2, math.ceil((u_e - u_s + shift) / half) + 3):
        cu = u_s - shift + j * half
        sv = sigma * (1 if j % 2 == 0 else -1) * height
        verts += [(cu - P / 2, sv), (cu + P / 2, sv)] if P > 1e-9 else [(cu, sv)]
    # Mäander: senkrechte Flanken, Nachbarecken mit gleichem u (gewollt)
    uv, rmin = fillet_polyline(np.array(verts), radius, chord_tol_mm=0.05, step_mm=FINE_MM)
    uv = clip_u(uv, u_s, u_e)
    peak = float(np.max(np.abs(uv[:, 1]))) if len(uv) else 0.0
    return uv, rmin, peak


def clip_u(uv: np.ndarray, u_s: float, u_e: float) -> np.ndarray:
    """Polylinie (u nicht fallend, deckt [u_s, u_e] ab) auf [u_s, u_e] schneiden, mit exakten
    Endpunkten."""
    u = uv[:, 0]
    i0 = int(np.searchsorted(u, u_s, side="right"))
    i1 = int(np.searchsorted(u, u_e, side="left"))
    if i0 == 0 or i1 >= len(u) or i0 > i1:
        raise ValueError("Welle deckt den Bereich nicht ab")
    a, b = uv[i0 - 1], uv[i0]
    c, d = uv[i1 - 1], uv[i1]
    p = a + (b - a) * (u_s - a[0]) / (b[0] - a[0])
    q = c + (d - c) * (u_e - c[0]) / (d[0] - c[0]) if d[0] > c[0] else d
    return dedupe(np.vstack([p, uv[i0:i1], q]))


def wave_uv(
    shape: str,
    u_s: float,
    u_e: float,
    amp: float,
    opts: dict[str, Any],
    sigma: float,
    n_fixed: int | None = None,
):
    """Welle von u_s bis u_e: (uv, Wellenlänge, Halbwellen, kleinster Radius der Sollkurve).
    `n_fixed`: Zahl der Halbwellen vorgeben (Einlaufsuche, spart das erneute Anpassen)."""
    total = u_e - u_s
    lam_t = float(opts["wavelength_mm"])
    w = float(opts["w"])
    phase = math.radians(float(opts["phase_deg"]))
    n0 = fit_to_length(total, lam_t / 2.0).count
    target = w if shape == "sinus" else min(w, float(opts["round_radius_mm"]))
    best = None
    # Halbwellen verringern, bis der Radius das Ziel erreicht; begrenzt das Band den Radius
    # (Mäander im 50-mm-Band: r ≤ A), bleibt die angepasste Zahl mit dem größten Radius.
    for n in range(n_fixed or n0, 0, -1):
        lam = 2.0 * total / n
        if shape == "sinus":
            r = lam * lam / (4 * math.pi**2 * amp) if amp > 1e-9 else math.inf
            uv = None
        else:
            plateau = (
                lam / 2.0 if shape == "maeander" else (0.0 if shape == "zickzack" else opts["plateau_mm"])
            )
            # Trapez: zu langes Plateau lässt keinen Platz für die Eckbögen → Plateau kürzen
            for pl in dict.fromkeys([plateau, plateau / 2.0, 0.0] if shape == "trapez" else [plateau]):
                uv, r, peak = trapezoid_uv(u_s, u_e, lam, amp, phase, sigma, pl, opts["round_radius_mm"])
                if peak < amp - 0.5 and total >= lam / 2.0:  # Scheitel erreichen die Schale nicht
                    r = 0.0
                if r >= target - 1e-6:
                    break
        if best is None or r > best[3] + 0.05:
            best = (uv, lam, n, r)
        if r >= target - 1e-6:
            break
    uv, lam, n, r = best
    if uv is None:
        uv = sine_uv(u_s, u_e, lam, amp, phase, sigma)
    return uv, lam, n, r


# --------------------------------------------------------------------------- Abstände


class Printed:
    """Bereits gedruckte Schalen mit Bogenlänge t rückwärts ab dem Eintritt."""

    def __init__(self, segments: tuple[Segment, ...]):
        if segments:
            pts = densify(np.vstack([s.points for s in segments]), CHECK_MM)
        else:
            pts = np.zeros((1, 2)) + 1e12
        arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        self.pts, self.t = pts, arc[-1] - arc
        self.tree = cKDTree(pts)

    def violates(self, pts: np.ndarray, s: np.ndarray, thresh: float, exempt: float) -> bool:
        """Liegt ein Punkt (Bogenlänge s ab Eintritt) näher als `thresh` an einem gedruckten
        Punkt, dessen Bogenlängenabstand s + t > `exempt` ist?"""
        d, _ = self.tree.query(pts, distance_upper_bound=thresh)
        idx = np.flatnonzero(np.isfinite(d))
        for i, near in zip(idx, self.tree.query_ball_point(pts[idx], thresh), strict=True):
            if near and np.any(self.t[near] + s[i] > exempt):
                return True
        return False


def self_violates(pts: np.ndarray, s: np.ndarray, thresh: float, exempt: float) -> bool:
    pairs = cKDTree(pts).query_pairs(thresh, output_type="ndarray")
    return bool(len(pairs) and np.any(np.abs(s[pairs[:, 0]] - s[pairs[:, 1]]) > exempt))


def arc_of(pts: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])


def resample_pieces(curve: np.ndarray, step_mm: float, chord_tol_mm: float) -> np.ndarray:
    """Wie `resample_curve`, aber Übergänge Gerade ↔ Bogen und Wendepunkte bleiben Wegpunkte. Sonst überspannt
    eine Sehne den Übergang, und die Sehnenfehler-Schätzung (Radius der Nachbarpunkte) meldet
    bei kurzen Plateaus bis 0,9 mm, obwohl die Polylinie die Sollkurve auf 0,5 mm einhält."""
    p = np.asarray(curve, float)
    if len(p) < 4:
        return resample_curve(p, step_mm, chord_tol_mm)
    # Bögen sind fein abgetastet (≤ FINE_MM), Geraden sind einzelne lange Stücke
    v = np.diff(p, axis=0)
    long = np.flatnonzero(np.linalg.norm(v, axis=1) > 1.5 * FINE_MM)
    # Wendepunkte (Krümmung wechselt das Vorzeichen, z. B. Biarc-Mitte, Sinusflanke)
    # (nur deutliche Drehungen > 1e-4 rad, sonst flackert das Vorzeichen auf fast geraden Stücken)
    ln = np.linalg.norm(v, axis=1)
    turn = (v[:-1, 0] * v[1:, 1] - v[:-1, 1] * v[1:, 0]) / np.maximum(ln[:-1] * ln[1:], 1e-12)
    nz = np.flatnonzero(np.abs(turn) > 1e-4)
    flip = np.flatnonzero(np.sign(turn[nz[1:]]) != np.sign(turn[nz[:-1]]))
    infl = (nz[flip] + nz[flip + 1]) // 2 + 1
    cuts = sorted({int(c) for c in np.concatenate([long, long + 1, infl]) if 0 < c < len(p) - 1})
    idx = [0, *cuts, len(p) - 1]
    out = [p[:1]]
    for a, b in zip(idx[:-1], idx[1:], strict=True):
        if b == a + 1:
            # Gerade: kurze Endstücke, damit die Schätzung an den Bogenenden nicht über die
            # ganze Gerade greift (Umkreis dreier Punkte über Bogen und Gerade)
            P, Q = p[a], p[b]
            L = float(np.linalg.norm(Q - P))
            e = min(STRAIGHT_END_MM, L / 4.0)
            d = (Q - P) / L
            out.append(densify(np.vstack([P, P + e * d, Q - e * d, Q]), step_mm)[1:])
        elif b > a:
            out.append(resample_curve(p[a : b + 1], step_mm, chord_tol_mm)[1:])
    return dedupe(np.vstack(out))


# --------------------------------------------------------------------------- Aufbau


def build_wave(ctx: IslandContext, shape: str) -> IslandPlan:
    p = ctx.params
    w = p.w
    fr = band_frame(ctx)
    if fr is None or ctx.entry is None:
        return IslandPlan([], meta={"skipped": "kein rechteckiges Infill-Band"})
    opts: dict[str, Any] = {"w": w}
    for spec in ctx.spec:
        opts[spec.name] = ctx.param(spec.name)
    overlap = float(opts["contact_overlap_pct"]) / 100.0 * w
    if overlap > p.eps * w + 1e-9:
        raise ValueError(f"Kontaktüberlappung {overlap:.2f} mm > ε·w = {p.eps * w:.2f} mm (M7)")
    # Bei ε·w läge der Kontakt genau auf der M2-Grenze (1 − ε)·w; jede Sehne der Abtastung
    # schneidet darunter, und die Einlaufsuche fände nie etwas (15 %: Infill entfiel immer).
    # Höchstens ε·w − 2·CLEAR_MARGIN_MM (w = 30: 3,9 mm = 13 %), meta `overlap_clamped`.
    overlap_req = overlap
    overlap = min(overlap, max(p.eps * w - 2.0 * CLEAR_MARGIN_MM, 0.0))
    # M6 hart: Eckbögen mit r = w/2 liegen nach dem Neu-Abtasten bis 0,3 mm darunter (Sehnen über
    # den fein abgetasteten Bogen), daher r ≥ w/2 + R_HARD_MARGIN_MM (meta `round_radius_mm`)
    if "round_radius_mm" in opts:
        opts["round_radius_mm"] = max(float(opts["round_radius_mm"]), w / 2.0 + R_HARD_MARGIN_MM)
    amp = fr["half"] + overlap
    entry, t_in = np.asarray(ctx.entry, float), np.asarray(ctx.entry_tangent, float)
    loc = entry - fr["center"]
    u_entry, u0, u1 = float(loc @ fr["eu"]), -fr["length"] / 2.0, fr["length"] / 2.0
    sv = float(t_in @ fr["ev"])
    sigma0 = -1.0 if sv < 0 else 1.0
    if abs(sv) < 1e-6:
        sigma0 = -1.0 if float(loc @ fr["ev"]) < 0 else 1.0
    printed = Printed(ctx.printed)
    # Reserve gegen den Sehnenfehler, aber nie strenger als der gewollte Kontakt der Welle selbst
    thresh = min((1.0 - p.eps) * w + CLEAR_MARGIN_MM, w - overlap - 0.05)
    exempt = 2.0 * w

    def feasible(curve: np.ndarray, upto: float | None) -> bool:
        dense = densify(curve, CHECK_MM)
        s = arc_of(dense)
        if upto is not None:
            dense, s = dense[s <= upto], s[s <= upto]
        if printed.violates(dense, s, thresh, exempt) or self_violates(dense, s, thresh, exempt):
            return False
        return LineString(np.vstack([printed.pts[-3:], dense[1:]])).is_simple

    cands: list[tuple[tuple[float, float], dict[str, Any]]] = []

    def try_join(
        wave: np.ndarray, k: int, lam: float, n: int, r_wave: float, at: np.ndarray | None = None
    ) -> float:
        """Einlauf-Biarc auf den Wellenpunkt `at` im Stück k → k + 1 (Standard: Punkt k), Rest der
        Welle ab k + 1; Kandidat merken. Rückgabe: Einlaufradius (0 = nicht machbar)."""
        q = wave[k] if at is None else at
        tq = wave[k + 1] - wave[k]
        res = biarc(entry, t_in, q, tq / np.linalg.norm(tq), 0.05, FINE_MM)
        if res is None:
            return 0.0
        lead, r_lead = res
        r_lead = min(r_lead, w)
        if min(r_lead, r_wave) < (1.0 - RADIUS_TOL) * w / 2.0:  # M6 hart
            return 0.0
        curve = np.vstack([lead, wave[k + 1 :]])
        if not feasible(curve, float(arc_of(lead)[-1]) + lam + exempt):
            return 0.0
        u_join = float((q - fr["center"]) @ fr["eu"])
        info = {"curve": curve, "lam": lam, "n": n, "r_wave": r_wave, "r_lead": r_lead, "u_s": u_join}
        cands.append(((round(r_lead, 1), -u_join), info))
        return r_lead

    def search(o: dict[str, Any], sigma: float) -> dict[str, Any] | None:
        cands.clear()
        # 1. Wellenanfang u_s verschieben (Phasenpunkt am Einlauf), Welle bis zum Bandende angepasst
        lo = max(u0 - w, u_entry)
        n_fixed = None
        for u_s in np.arange(lo, lo + SEARCH_W * w + 1e-9, 1.0):
            if u1 - u_s < w:
                break
            uv, lam, n, r_wave = wave_uv(shape, float(u_s), u1, amp, o, sigma, n_fixed)
            n_fixed = n
            if len(uv) >= 2 and try_join(to_xy(fr, uv), 0, lam, n, r_wave) >= w - 1e-6:
                break
        # 2. Reicht das nicht (z. B. Phase 180°: Scheitel auf der Gegenseite), Welle ab Bandanfang
        #    festhalten und später einsteigen (bis eine Wellenlänge weit, alle CHECK_MM)
        if not cands or max(c[0][0] for c in cands) < (1.0 - RADIUS_TOL) * w:
            uv, lam, n, r_wave = wave_uv(shape, max(u0, lo), u1, amp, o, sigma)
            fine = to_xy(fr, uv) if len(uv) >= 2 else np.zeros((0, 2))
            s_f = arc_of(fine)
            for s_k in np.arange(0.0, min(lam, s_f[-1] - w) if len(fine) else 0.0, CHECK_MM):
                k = min(int(np.searchsorted(s_f, s_k, side="right")) - 1, len(fine) - 2)
                t = (s_k - s_f[k]) / max(s_f[k + 1] - s_f[k], 1e-12)
                if try_join(fine, k, lam, n, r_wave, fine[k] + t * (fine[k + 1] - fine[k])) >= w - 1e-6:
                    break
        cands.sort(key=lambda c: c[0], reverse=True)
        return next((c[1] for c in cands if feasible(c[1]["curve"], None)), None)

    # Erst der Scheitel auf der Seite, zu der der Eintritt zeigt; reicht der Einlaufradius nicht
    # (z. B. Eintritt parallel zum Band in Gegenrichtung: Kehre über die ganze Bandbreite), die
    # Gegenseite; dann Phase 0, falls die gewählte Phase gar nicht anschließt (meta phase_deg).
    b, phase_used = None, float(opts["phase_deg"])
    for ph in dict.fromkeys([phase_used, 0.0]):
        for sg in (sigma0, -sigma0):
            c = search({**opts, "phase_deg": ph}, sg)
            if c is not None and (b is None or c["r_lead"] > b["r_lead"] + 0.05):
                b, phase_used = c, ph
            if b is not None and b["r_lead"] >= (1.0 - RADIUS_TOL) * w:
                break
        if b is not None:
            break
    if b is None:
        return IslandPlan(
            [],
            meta={"skipped": "kein kreuzungsfreier Einlauf mit Radius ≥ w/2 bzw. Welle passt nicht ins Band"},
        )
    pts = resample_pieces(b["curve"], p.step_mm, p.chord_tol_mm)
    seg = Segment("infill", p.shells, pts, label=LABELS[shape])
    contacts = shell_contacts(pts, printed, w, p.contact_tol_mm)
    meta = {
        "shape": shape,
        "wavelength_mm": round(b["lam"], 2),
        "wavelength_target_mm": float(opts["wavelength_mm"]),
        "half_waves": b["n"],
        "amplitude_mm": round(amp, 2),
        "band_mm": [round(fr["length"], 2), round(2 * fr["half"], 2)],
        "overlap_mm": round(overlap, 2),
        **({"overlap_clamped": True} if overlap < overlap_req - 1e-9 else {}),
        **({"round_radius_mm": round(opts["round_radius_mm"], 2)} if "round_radius_mm" in opts else {}),
        "lead_in_radius_mm": round(b["r_lead"], 2),
        "wave_min_radius_mm": round(b["r_wave"], 2) if math.isfinite(b["r_wave"]) else None,
        "u_start_mm": round(b["u_s"] - u0, 2),
        "phase_deg": phase_used,
        "contacts": len(contacts),
    }
    if fr["n_parts"] > 1:
        meta["band_parts_ignored"] = fr["n_parts"] - 1
    return IslandPlan([seg], contacts, meta)


def shell_contacts(pts: np.ndarray, printed: Printed, w: float, tol: float) -> list[Contact]:
    """Kontaktzonen Infill ↔ Schalen (Bogenlängenabstand > 2·w, Abstand ≤ w + tol)."""
    dense = densify(pts, CHECK_MM)
    s = arc_of(dense)
    d, j = printed.tree.query(dense)
    hit = (d <= w + tol) & (printed.t[np.minimum(j, len(printed.t) - 1)] + s > 2.0 * w)
    out: list[Contact] = []
    idx = np.flatnonzero(hit)
    if not len(idx):
        return out
    for run in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
        k = run[int(np.argmin(d[run]))]
        mid = run[len(run) // 2]
        at = (dense[mid] + printed.pts[j[mid]]) / 2.0
        out.append(
            Contact("shell", tuple(at), float(s[run[-1]] - s[run[0]]) + CHECK_MM, (-1, 0), float(d[k]))
        )
    return out


LABELS = {"sinus": "Sinuswelle", "zickzack": "Zickzack", "trapez": "Trapezwelle", "maeander": "Mäander"}


# --------------------------------------------------------------------------- Schalenwechsel


def _min_dist(a: np.ndarray, b: np.ndarray) -> float:
    """Kleinster Abstand zwischen zwei (dicht abgetasteten) Punktmengen."""
    if len(a) == 0 or len(b) == 0:
        return math.inf
    return float(cKDTree(b).query(a)[0].min())


def lane_change(
    ring: Loop,
    nxt: Loop,
    start: float,
    params: PatternParams,
    min_ell: float = 0.0,
    avoid: np.ndarray | None = None,
) -> tuple[float, np.ndarray, float]:
    """S-Kurve vom Ende von `ring` (Start bei Bogenlänge `start`) auf `nxt`.

    Gesucht wird das kleinste ℓ ≥ max(ℓ₀, min_ell) (1-mm-Schritte), bei dem beide Biarc-Bögen
    mindestens R haben und die S-Kurve vom Anfang des Rings (start … start + 3·w) mindestens
    w − CLEAR_TOL_MM entfernt bleibt (kein Doppelmaterial), ebenso von `avoid` (die ankommende
    S-Kurve des vorigen Wechsels: Ab drei Schalen liegen zwei Wechsel nebeneinander; eine um w
    verschobene Kopie der S-Kurve hätte an der steilsten Stelle (60° bei R = w) nur w·cos 60° =
    w/2 Abstand, also Doppelmaterial, M2). Rückgabe (ℓ, Punkte der S-Kurve von
    A = ring(start − ℓ) nach B = nxt neben ring(start), Bogenlänge von B auf `nxt`)."""
    R, w = params.transition_radius, params.w
    P = ring.point(start)
    tb = nxt.project(P)
    B = nxt.point(tb)
    tB = nxt.tangent(tb)
    d = float(np.linalg.norm(B - P))
    ell0 = 2.0 * math.sqrt(max(R * R - (R - d / 2.0) ** 2, 0.0)) if d < 2 * R else d
    head = densify(ring.sub(start, start + min(3.0 * w, 0.3 * ring.length)), 1.0)[1:]
    if avoid is not None and len(avoid) > 1:
        head = np.vstack([head, densify(avoid, 1.0)])
    best: tuple[float, np.ndarray, float] | None = None
    for ell in max(ell0, min_ell) + np.arange(0.0, 8.0 * w, 1.0):
        if ell >= 0.6 * ring.length:
            break
        A = ring.point(start - ell)
        tA = ring.tangent(start - ell, incoming=True)
        res = biarc(A, tA, B, tB, FINE_TOL_MM, params.step_mm)
        if res is None:
            continue
        pts, r = res
        clear = _min_dist(densify(pts, 1.0)[:-1], head) >= w - CLEAR_TOL_MM
        score = min(r, R) + (R if clear else 0.0)
        if best is None or score > best[2]:
            best = (float(ell), pts, score)
        if r >= R - 1e-6 and clear:
            break
    if best is None:  # kein Biarc: gerade Linie (M6/M2 melden das)
        ell = min(ell0, 0.25 * ring.length)
        return ell, np.vstack([ring.point(start - ell), B]), tb
    return best[0], best[1], tb


def clear_end(loop: Loop, t_from: float, trans: np.ndarray, w: float) -> float:
    """Spätestes Ende (Bogenlänge in (t_from, t_from + L)) eines Rings, der bei t_from beginnt und
    einmal herumläuft, sodass seine letzten Stücke von der Kurve `trans` (die bei t_from auf den
    Ring traf) mindestens w − CLEAR_TOL_MM Abstand halten: Kontakt, kein Doppelmaterial."""
    L = loop.length
    lo = t_from + max(2.0 * w, L - 8.0 * w)
    ts = np.arange(lo, t_from + L, 1.0)
    pts = np.array([loop.point(t) for t in ts])
    dist = cKDTree(densify(trans, 1.0)).query(pts)[0]
    bad = np.flatnonzero(dist < w - CLEAR_TOL_MM)
    if len(bad) == 0:
        return float(ts[-1])
    return float(ts[max(int(bad[0]) - 1, 0)])
