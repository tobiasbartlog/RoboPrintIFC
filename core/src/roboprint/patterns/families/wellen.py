"""Infill-Familie „Wellen“: Sinus, Zickzack mit Rundung, Trapez und Mäander im Hohlraum zwischen
den inneren Schalen (Rolle `infill`, AUFTRAG M2 „I-Wellen“).

Aufbau je Insel
===============

1. **Band.** `ctx.band` ist die Fläche der Infill-Mittellinien, deren Raupe die innerste Schale
   gerade berührt (S1 600 × 200, 2 Schalen: 450 × 50 mm; eine Schale je Seite: 510 × 110 mm).
   Die Welle läuft entlang der Längsachse des Bands (kleinstes umschreibendes Rechteck). Ihre
   Amplitude kommt aus dem Band: A = halbe Bandbreite + Kontaktüberlappung (Parameter, Standard
   5 % von w = 1,5 mm nach recherche.md §7). Jeder Wellenberg berührt so die eine Innenschale,
   jedes Tal die andere, mit Mittellinienabstand w − Überlappung ∈ [(1 − ε)·w, w] (M7).
   Nicht rechteckige Bänder (Öffnung, L-Querschnitt) sind Aufgabe der Familie „Topologie“; hier
   entfällt das Infill dann (meta `skipped`), der Pfad bleibt gültig.
2. **Wellenform** in Bandkoordinaten (u entlang, v quer):
   - `sinus`: v = σ·A·cos(2π(u − u_s)/λ + φ). Kleinster Radius λ²/(4π²·A).
   - `zickzack`: gerade Flanken, Scheitel mit Radius r gerundet; die Scheitelpunkte liegen so weit
     außerhalb, dass der Bogenscheitel genau A erreicht.
   - `trapez`: Plateaus der Länge P an beiden Schalen (lange Kontaktzonen), Ecken mit Radius r.
   - `maeander`: Trapez mit senkrechten Flanken (P = λ/2).
   Die Wellenlänge wird auf eine ganze Zahl Halbwellen zwischen Einlauf und Bandende angepasst
   (`fit_to_length`), mit höchstens so vielen Halbwellen, dass der Radius das Ziel erreicht
   (Sinus: ≥ w; sonst ≥ min(w, r)). Zickzack braucht λ > 4·r (sonst erreicht der Bogenscheitel A
   nie), Mäander r ≤ A (50-mm-Band: r ≤ 26,5 mm < w, M6-Warnung). Ein zu langes Trapez-Plateau
   wird halbiert bzw. entfällt.
3. **Einlauf ohne Kreuzung und ohne Doppelmaterial.** Der Kern beendet die innerste Schale bei
   folgendem Infill früher (`shell_chain(open_end=True)`): eine Schale je Seite mit der S-Kurve
   auf den Bandrand, mehrere Schalen ℓ vor dem Ringstart. Das Infill beginnt genau bei
   `ctx.entry` (Verbinder Länge 0) mit einem tangentenstetigen Biarc auf die Welle. Gesucht wird
   (a) der Wellenanfang u_s (1-mm-Schritte, Welle bis zum Bandende neu angepasst), (b) falls das
   nicht reicht, ein späterer Einstieg in die festgehaltene Welle (bis eine Wellenlänge, alle
   2 mm), jeweils für beide Seiten σ des ersten Scheitels. Gewählt wird der größte Einlaufradius
   (bis w), bei Gleichstand der früheste Einstieg; alle Punkte mit Bogenlängenabstand > 2·w zu
   Schalen und Welle bleiben ≥ (1 − ε)·w + 0,3 mm entfernt, der Radius ≥ w/2. Passt die gewählte
   Phase gar nicht, gilt Phase 0 (meta `phase_deg`); passt gar nichts, entfällt das Infill (meta
   `skipped`), der Schalenpfad bleibt gültig.
   Laufzeit (Vorschau < 100 ms): Je Wellenanfang werden nur Eckradius und die ersten zwei Punkte
   der Welle gerechnet (`_wellen_form`), der Einlaufradius ohne Bogenpunkte (`biarc_radius`); die
   Prüfung auf Kreuzung und Doppelmaterial (Anfang 2·λ + 2·w der Welle) läuft erst, wenn ein
   Kandidat über Abbruch oder Auswahl entscheidet, die ganze Welle nur für den gewählten. Das
   Ergebnis gleicht der früheren vollständigen Suche (test_patterns_wellen_perf.py).
4. **Ende und Schichtwechsel.** Die Welle endet am Bandende in einem Scheitel (Phase 0) und
   berührt dort die Stirnschale. Mit `alternate` druckt Schicht L + 1 dieselbe Bahn rückwärts:
   Ende L = Anfang L + 1, der Schichtwechsel ist ein reiner Z-Hub (M4). Die Naht liegt im Hohlraum,
   weit weg von Außen- und Stoßfläche.

Kontakte (Art `shell`) werden gemessen und deklariert: Zonen, in denen die Infill-Mittellinie einer
Schale (Bogenlängenabstand > 2·w) bis w + contact_tol nahekommt; Segmente (−1, 0) = (Schale,
Infill-Segment), der Kern verschiebt den Infill-Index.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from roboprint.patterns.families._wellen_form import (  # noqa: F401 (Teil der Schnittstelle)
    FINE_MM,
    RADIUS_TIE_MM,
    _trapezoid_verts,
    clip_u,
    sine_uv,
    trapezoid_radius,
    trapezoid_uv,
    wave_uv,
    zigzag_height,
)
from roboprint.patterns.geometry import (
    biarc,
    biarc_radius,
    dedupe,
    densify,
    polygons,
    resample_curve,
)
from roboprint.patterns.metrics import RADIUS_TOL
from roboprint.patterns.registry import pattern
from roboprint.patterns.types import Contact, IslandContext, IslandPlan, ParamSpec, Segment

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

COMMON_PARAMS = (
    ParamSpec(
        "wavelength_mm",
        "Wellenlänge",
        250.0,
        "mm",
        80.0,
        2000.0,
        5.0,
        help="Sollwert; angepasst auf eine ganze Zahl Halbwellen im Band",
    ),
    ParamSpec(
        "phase_deg",
        "Phase",
        0.0,
        "°",
        0.0,
        360.0,
        15.0,
        help="0° = Scheitel am Einlauf und am Bandende (Kontakt an beiden Enden)",
    ),
    ParamSpec(
        "contact_overlap_pct",
        "Kontaktüberlappung",
        5.0,
        "% von w",
        0.0,
        15.0,
        1.0,
        help="Überlappung der Raupe mit der Innenschale an Berg und Tal (M7: 0 … ε·w)",
    ),
)
RADIUS_PARAM = ParamSpec(
    "round_radius_mm",
    "Rundungsradius",
    30.0,
    "mm",
    15.0,
    300.0,
    1.0,
    help="Radius der Scheitel bzw. Ecken (M6: hart ≥ w/2, Ziel ≥ w)",
)
PLATEAU_PARAM = ParamSpec(
    "plateau_mm",
    "Trapez-Plateaulänge",
    60.0,
    "mm",
    0.0,
    1000.0,
    5.0,
    help="Länge der geraden Kontaktstrecke an der Schale (höchstens λ/2 = Mäander)",
)


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
        if not len(idx):
            return False
        # alle Paare im Abstand ≤ thresh auf einmal (wie query_ball_point je Punkt)
        pairs = cKDTree(pts[idx]).sparse_distance_matrix(self.tree, thresh, output_type="ndarray")
        return bool(len(pairs) and np.any(self.t[pairs["j"]] + s[idx[pairs["i"]]] > exempt))


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


class Join:
    """Einlauf-Kandidat: Rangschlüssel (Einlaufradius auf 0,1 mm, −u), Kennwerte, Prüfung
    (einmal gerechnet, bei Bedarf) und die ganze Kurve (bei Bedarf)."""

    def __init__(
        self,
        key: tuple[float, float],
        info: dict[str, Any],
        check: Callable[[], bool],
        curve: Callable[[], np.ndarray],
    ):
        self.key, self.info, self._check, self.curve = key, info, check, curve
        self._ok: bool | None = None

    def ok(self) -> bool:
        if self._ok is None:
            self._ok = bool(self._check())
        return self._ok


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

    def try_join(
        wave: np.ndarray,
        k: int,
        lam: float,
        n: int,
        r_wave: float,
        at: np.ndarray | None = None,
        prefix: Callable[[], np.ndarray] | None = None,
        full: Callable[[], tuple[np.ndarray, float]] | None = None,
    ) -> Join | None:
        """Einlauf-Biarc auf den Wellenpunkt `at` im Stück k → k + 1 (Standard: Punkt k), Rest der
        Welle ab k + 1. Rückgabe: Kandidat (Prüfung auf Kreuzung und Doppelmaterial erst bei
        Bedarf, `Join.ok`) oder None, wenn es keinen Biarc mit Radius ≥ w/2 gibt.

        `wave` darf nur der Anfang der Welle sein (bitgleich, bis hinter Punkt k + 1); `prefix`
        liefert dann den Anfang für die Prüfung (mindestens λ + 2·w + längstes Stück hinter k),
        `full` die ganze Welle für den gewählten Kandidaten."""
        q = wave[k] if at is None else at
        tq = wave[k + 1] - wave[k]
        tq = tq / np.linalg.norm(tq)
        r_lead = biarc_radius(entry, t_in, q, tq)  # Punkte erst bei Bedarf (`lead`)
        if r_lead is None:
            return None
        r_lead = min(r_lead, w)
        if min(r_lead, r_wave) < (1.0 - RADIUS_TOL) * w / 2.0:  # M6 hart
            return None
        u_join = float((q - fr["center"]) @ fr["eu"])
        info = {"lam": lam, "n": n, "r_wave": r_wave, "r_lead": r_lead, "u_s": u_join}

        def lead() -> np.ndarray:
            return biarc(entry, t_in, q, tq, 0.05, FINE_MM)[0]

        def full_wave() -> np.ndarray:
            xy, info["r_wave"] = full()  # Radius der ganzen Welle (Bericht)
            return xy

        return Join(
            (round(r_lead, 1), -u_join),
            info,
            lambda: _check(lead(), (wave if prefix is None else prefix())[k + 1 :], lam),
            lambda: np.vstack([lead(), (wave if full is None else full_wave())[k + 1 :]]),
        )

    def _check(lead: np.ndarray, tail: np.ndarray, lam: float) -> bool:
        """Kreuzung und Doppelmaterial bis λ + 2·w hinter dem Einlauf. Die Welle wird dafür hinter
        dem Stück, das diese Stelle enthält, abgeschnitten (gleiches Ergebnis, weniger Punkte)."""
        if len(tail) > 2:
            seg = np.linalg.norm(np.diff(tail, axis=0), axis=1)
            arc = np.concatenate([[0.0], np.cumsum(seg)])
            tail = tail[: int(np.searchsorted(arc, lam + exempt + float(seg.max()) + 1.0, side="right")) + 1]
        return feasible(np.vstack([lead, tail]), float(arc_of(lead)[-1]) + lam + exempt)

    def search(o: dict[str, Any], sigma: float) -> dict[str, Any] | None:
        # Kandidaten in Suchreihenfolge; gültig ist ein Kandidat erst mit `ok()` (Prüfung bei
        # Bedarf: Für Abbruch und Auswahl zählen nur wenige, die übrigen werden nie geprüft)
        cands: list[Join] = []

        def good(c: Join | None) -> bool:
            return c is not None and c.info["r_lead"] >= w - 1e-6 and c.ok()

        # 1. Wellenanfang u_s verschieben (Phasenpunkt am Einlauf), Welle bis zum Bandende angepasst
        lo = max(u0 - w, u_entry)
        n_fixed = None
        for u_s in np.arange(lo, lo + SEARCH_W * w + 1e-9, 1.0):
            if u1 - u_s < w:
                break
            u_s = float(u_s)
            # für den Einlauf genügen die ersten zwei Punkte, für die Prüfung 2·λ + 2·w + 10 mm, die
            # ganze Welle erst für den gewählten Kandidaten (alle Stücke wie in der ganzen Welle)
            uv, lam, n, r_wave = wave_uv(shape, u_s, u1, amp, o, sigma, n_fixed, start_only=True)

            def part(
                cut: tuple[float, float] | None, u_s: float = u_s, n: int = n
            ) -> tuple[np.ndarray, float]:
                uv, _, _, r = wave_uv(shape, u_s, u1, amp, o, sigma, n, cut)
                return to_xy(fr, uv), r

            n_fixed = n
            if len(uv) < 2:
                continue
            c = try_join(
                to_xy(fr, uv),
                0,
                lam,
                n,
                r_wave,
                prefix=lambda part=part: part((2.0, exempt + 10.0))[0],
                full=lambda part=part: part(None),
            )
            if c is not None:
                cands.append(c)
            if good(c):
                break
        # 2. Reicht das nicht (z. B. Phase 180°: Scheitel auf der Gegenseite), Welle ab Bandanfang
        #    festhalten und später einsteigen (bis eine Wellenlänge weit, alle CHECK_MM)
        thr = (1.0 - RADIUS_TOL) * w
        if not any(c.key[0] >= thr and c.ok() for c in cands):
            uv, lam, n, r_wave = wave_uv(shape, max(u0, lo), u1, amp, o, sigma)
            fine = to_xy(fr, uv) if len(uv) >= 2 else np.zeros((0, 2))
            s_f = arc_of(fine)
            for s_k in np.arange(0.0, min(lam, s_f[-1] - w) if len(fine) else 0.0, CHECK_MM):
                k = min(int(np.searchsorted(s_f, s_k, side="right")) - 1, len(fine) - 2)
                t = (s_k - s_f[k]) / max(s_f[k + 1] - s_f[k], 1e-12)
                c = try_join(fine, k, lam, n, r_wave, fine[k] + t * (fine[k + 1] - fine[k]))
                if c is not None:
                    cands.append(c)
                if good(c):
                    break
        # stabil wie zuvor: gleiche Schlüssel in Suchreihenfolge
        for c in sorted(cands, key=lambda c: c.key, reverse=True):
            if c.ok():
                curve = c.curve()
                if feasible(curve, None):
                    return {**c.info, "curve": curve}
        return None

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

_DESC = (
    "Infill im Hohlraum zwischen den inneren Schalen, Berge und Täler berühren beide Innenschalen. "
    "Ein Strang mit den Schalen, Einlauf ohne Kreuzung; mit alternate senkrechter Schichtwechsel."
)


@pattern("sinus", "infill", "Sinuswelle", params=COMMON_PARAMS, description="Sinuswelle. " + _DESC)
def build_sine(ctx: IslandContext) -> IslandPlan:
    return build_wave(ctx, "sinus")


@pattern(
    "zickzack",
    "infill",
    "Zickzack gerundet",
    params=(*COMMON_PARAMS, RADIUS_PARAM),
    description="Zickzack mit gerundeten Scheiteln (r ≥ w). " + _DESC,
)
def build_zigzag(ctx: IslandContext) -> IslandPlan:
    return build_wave(ctx, "zickzack")


@pattern(
    "trapez",
    "infill",
    "Trapezwelle",
    params=(*COMMON_PARAMS, RADIUS_PARAM, PLATEAU_PARAM),
    description="Trapezwelle mit Plateaus an den Schalen (lange Kontaktzonen). " + _DESC,
)
def build_trapezoid(ctx: IslandContext) -> IslandPlan:
    return build_wave(ctx, "trapez")


@pattern(
    "maeander",
    "infill",
    "Mäander",
    params=(*COMMON_PARAMS, RADIUS_PARAM),
    description="Mäander: Trapez mit senkrechten Flanken (Plateau = λ/2). " + _DESC,
)
def build_meander(ctx: IslandContext) -> IslandPlan:
    return build_wave(ctx, "maeander")
