"""Familie „Mehrfach“: Doppelwelle (Kettenglied), Waben und Fermat-Spirale (AUFTRAG M2 „I-Mehrfach“).

Doppelwelle und Waben (Rolle `infill`)
=====================================

Zwei gegenphasige Wellen im Infill-Band, die sich in der Bandmitte **berühren** (Kontakt `node`,
Mittellinienabstand w − Überlappung ∈ [(1 − ε)·w, w]) und sich nie kreuzen. Gedruckt als **ein**
Strang: hin als Welle 1 in der einen Bandhälfte, am Bandende eine halbkreisförmige Wende, zurück
als Welle 2 in der anderen Hälfte. Welle 2 ist das Spiegelbild von Welle 1 an der Bandachse
(v → −v); Täler von Welle 1 treffen so genau die Berge von Welle 2, es entstehen Kettenglieder
(Sinus) bzw. Sechseckzellen (Trapez, „Waben“).

Bandkoordinaten (u entlang, v quer, wie `wellen.band_frame`), halbe Bandbreite b, Überlappung o:
- Scheitel an der Schale: v_t = b + o (die Raupe berührt die Innenschale wie bei den Wellen).
- Kontakt in der Mitte: v_b = (w − o)/2, also Abstand der beiden Wellen 2·v_b = w − o.
- Hub jeder Welle 2A = v_t − v_b = (B − w)/2 + 1,5·o (B = 2b Bandbreite). Das ist der ganze
  Spielraum: Er ist kleiner als der Hub einer einfachen Welle (2A = B + 2o) um mehr als die Hälfte.
- Wende am Bandende: Halbkreis mit Radius v_t um (u_e, 0), u_e = u₁ − b; der Scheitel der Wende
  berührt die Stirnschale. Welle 1 endet deshalb in einem Scheitel an der Schale, zwischen
  Wellenanfang u_s und u_e liegt eine ganze Zahl k von Wellenlängen.
- Sinus: v = σ·(c + A·cos(2π(u − u_s)/λ)), c = (v_t + v_b)/2, kleinster Radius λ²/(4π²A).
- Waben: Trapezwelle mit Flankenwinkel θ (Standard 60°) und Plateaus an der Schale und in der Mitte;
  Plateau P = λ/2 − 2A/tan θ. Wellenlänge 0 = automatisch regelmäßiges Sechseck (Seite
  s = 2A/sin θ = P, λ = 2s + 2·2A/tan θ). Ecken mit Radius r gerundet; zwei Ecken einer Flanke
  brauchen den Hub 2·r·(1 − cos θ) ≤ 2A.

**Grenze (Belege).** Unter dem Mindesthub `min_stroke_mm` (Standard w/2 = 15 mm) entfällt das
Muster mit Begründung (meta `skipped`), der Schalenpfad bleibt gültig. Für S1 (200 mm Wand,
2 Schalen, Hohlraum 80 mm, Band B = 50 mm, o = 1,5 mm) ist 2A = 12,25 mm: Die beiden „Wellen“
wären fast gerade Raupen (A = 6,1 mm), die Zellen zwischen Welle und Schale nur ≈ 10,8 mm breit
(< w/2, laufen beim Quetschen zu), die Wende hätte Radius 26,5 mm < w. Waben gehen dort gar nicht:
Bei θ = 60° brauchen zwei Eckbögen mit r ≥ w/2 = 15 mm einen Hub ≥ 2·15·(1 − cos 60°) = 15 mm
> 12,25 mm (M6 hart). Kleinster Hohlraum für die Doppelwelle: 2A ≥ w/2 ⇔ B ≥ 2w − 3o = 55,5 mm,
also Hohlraum ≥ 85,5 mm; geeignet sind Wände ≥ 300 mm mit 2 Schalen (B = 150) oder eine Schale je
Seite (200 mm: B = 110).

Einlauf: wie bei den Wellen (`wellen.py`) ein tangentenstetiger Biarc von `ctx.entry` auf den ersten
Scheitel von Welle 1; gesucht werden Wellenanfang u_s (1-mm-Schritte) und Seite σ, gewählt der
größte Einlaufradius (bis w). Welle 2 endet als Spiegelbild des Einstiegs neben dem Einlauf im
Hohlraum: Dort liegt mit `alternate` der senkrechte Schichtwechsel (M4), fern der Außen- und
Stoßflächen.

Fermat-Spirale (Rolle `full`): siehe `_mehrfach_fermat.py`.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from roboprint.patterns.families import _mehrfach_fermat as fermat
from roboprint.patterns.families import wellen
from roboprint.patterns.geometry import arc_points, biarc, densify
from roboprint.patterns.metrics import RADIUS_TOL
from roboprint.patterns.registry import pattern
from roboprint.patterns.types import Contact, IslandContext, IslandPlan, ParamSpec, Segment

#: Abtastung für Abstandsprüfungen (mm)
CHECK_MM = wellen.CHECK_MM
#: Reserve über (1 − ε)·w bei der Einlaufsuche
CLEAR_MARGIN_MM = wellen.CLEAR_MARGIN_MM
#: Suchbereich des Wellenanfangs hinter dem Bandanfang (in w)
SEARCH_W = 3.0

OVERLAP_PARAM = ParamSpec(
    "contact_overlap_pct",
    "Kontaktüberlappung",
    5.0,
    "% von w",
    0.0,
    15.0,
    1.0,
    help="Überlappung an Schale und Mittelkontakt (M7: 0 … ε·w); wirksam höchstens ε·w − 0,6 mm",
)
STROKE_PARAM = ParamSpec(
    "min_stroke_mm",
    "Mindesthub je Welle",
    15.0,
    "mm",
    0.0,
    200.0,
    1.0,
    help="Unter diesem Hub 2A (Schale ↔ Mittelkontakt) entfällt das Muster: Die Zellen wären < w/2",
)
DOUBLE_PARAMS = (
    ParamSpec(
        "wavelength_mm",
        "Wellenlänge",
        250.0,
        "mm",
        80.0,
        2000.0,
        5.0,
        help="Sollwert; angepasst auf eine ganze Zahl Wellenlängen bis zur Wende",
    ),
    OVERLAP_PARAM,
    STROKE_PARAM,
)
HONEYCOMB_PARAMS = (
    ParamSpec(
        "wavelength_mm",
        "Wellenlänge",
        0.0,
        "mm",
        0.0,
        2000.0,
        5.0,
        help="0 = regelmäßiges Sechseck aus Hub und Flankenwinkel; sonst Sollwert",
    ),
    ParamSpec(
        "flank_angle_deg",
        "Flankenwinkel",
        60.0,
        "°",
        20.0,
        80.0,
        1.0,
        help="Winkel der Wabenflanke gegen die Wandachse (60° = regelmäßiges Sechseck)",
    ),
    ParamSpec(
        "round_radius_mm",
        "Eckradius",
        30.0,
        "mm",
        15.0,
        200.0,
        1.0,
        help="Radius der Wabenecken (M6: hart ≥ w/2, Ziel ≥ w)",
    ),
    OVERLAP_PARAM,
    STROKE_PARAM,
)


# --------------------------------------------------------------------------- Wellenprofil


def _profile(
    shape: str, u_s: float, u_e: float, k: int, amp: float, opts: dict[str, Any]
) -> tuple[np.ndarray, float]:
    """Welle 1 (σ = +1, um v = 0 zentriert) von u_s bis u_e mit k Wellenlängen, Scheitel (+A) an
    beiden Enden. Rückgabe (uv, kleinster Radius der Sollkurve); leer, wenn die Form nicht passt."""
    lam = (u_e - u_s) / k
    if shape == "sinus":
        uv = wellen.sine_uv(u_s, u_e, lam, amp, 0.0, 1.0)
        return uv, lam * lam / (4 * math.pi**2 * amp) if amp > 1e-9 else math.inf
    th = math.radians(float(opts["flank_angle_deg"]))
    plateau = lam / 2.0 - 2.0 * amp / math.tan(th)
    if plateau < 0.0:
        return np.zeros((0, 2)), 0.0
    uv, rmin, peak = wellen.trapezoid_uv(u_s, u_e, lam, amp, 0.0, 1.0, plateau, opts["round_radius_mm"])
    if len(uv) < 2 or peak < amp - 0.5:
        return np.zeros((0, 2)), 0.0
    return uv, rmin


def _target_wavelength(shape: str, amp: float, opts: dict[str, Any]) -> float:
    lam = float(opts["wavelength_mm"])
    if shape == "waben" and lam <= 0.0:
        th = math.radians(float(opts["flank_angle_deg"]))
        side = 2.0 * amp / math.sin(th)
        lam = 2.0 * side + 2.0 * 2.0 * amp / math.tan(th)
    return lam


def _fit_profile(
    shape: str, u_s: float, u_e: float, amp: float, opts: dict[str, Any], w: float
) -> tuple[np.ndarray, int, float] | None:
    """Ganze Zahl k Wellenlängen nahe der Sollwellenlänge; k verringern, bis der Radius das Ziel
    (min(w, r) bzw. w) erreicht. Rückgabe (uv, k, Radius) oder None."""
    total = u_e - u_s
    if total <= 0:
        return None
    lam_t = _target_wavelength(shape, amp, opts)
    k0 = max(1, round(total / lam_t))
    target = w if shape == "sinus" else min(w, float(opts["round_radius_mm"]))
    best = None
    for k in range(k0, 0, -1):
        uv, r = _profile(shape, u_s, u_e, k, amp, opts)
        if len(uv) < 2:
            continue
        if best is None or r > best[2] + 0.05:
            best = (uv, k, r)
        if r >= target - 1e-6:
            break
    return best


# --------------------------------------------------------------------------- Aufbau


def _stroke(ctx: IslandContext, half: float, overlap: float) -> tuple[float, float]:
    """(v_t, v_b): Scheitel an der Schale und Kontaktlinie in der Mitte."""
    return half + overlap, (ctx.w - overlap) / 2.0


def build_double(ctx: IslandContext, shape: str) -> IslandPlan:
    p = ctx.params
    w = p.w
    fr = wellen.band_frame(ctx)
    if fr is None or ctx.entry is None:
        return IslandPlan([], meta={"skipped": "kein rechteckiges Infill-Band"})
    opts: dict[str, Any] = {s.name: ctx.param(s.name) for s in ctx.spec}
    if "round_radius_mm" in opts:
        opts["round_radius_mm"] = max(float(opts["round_radius_mm"]), w / 2.0 + wellen.R_HARD_MARGIN_MM)
    overlap_req = float(opts["contact_overlap_pct"]) / 100.0 * w
    if overlap_req > p.eps * w + 1e-9:
        raise ValueError(f"Kontaktüberlappung {overlap_req:.2f} mm > ε·w = {p.eps * w:.2f} mm (M7)")
    overlap = min(overlap_req, max(p.eps * w - 2.0 * CLEAR_MARGIN_MM, 0.0))
    half = fr["half"]
    v_t, v_b = _stroke(ctx, half, overlap)
    stroke = v_t - v_b
    amp, c = stroke / 2.0, (v_t + v_b) / 2.0
    base = {
        "shape": shape,
        "band_mm": [round(fr["length"], 2), round(2 * half, 2)],
        "stroke_mm": round(stroke, 2),
        "overlap_mm": round(overlap, 2),
        "turn_radius_mm": round(v_t, 2),
    }
    min_stroke = float(opts["min_stroke_mm"])
    if stroke < min_stroke - 1e-9:
        return IslandPlan(
            [],
            meta={
                **base,
                "skipped": f"Band {2 * half:.1f} mm zu schmal für zwei Wellen: Hub 2A = {stroke:.2f} mm "
                f"< {min_stroke:.1f} mm (braucht Band ≥ {w + 2 * min_stroke - 3 * overlap:.1f} mm)",
            },
        )
    u0, u1 = -fr["length"] / 2.0, fr["length"] / 2.0
    u_e = u1 - half  # Wendescheitel u_e + v_t = u₁ + o berührt die Stirnschale
    entry, t_in = np.asarray(ctx.entry, float), np.asarray(ctx.entry_tangent, float)
    loc = entry - fr["center"]
    u_entry = float(loc @ fr["eu"])
    sv = float(t_in @ fr["ev"])
    sigma0 = -1.0 if sv < 0 else 1.0
    if abs(sv) < 1e-6:
        sigma0 = -1.0 if float(loc @ fr["ev"]) < 0 else 1.0
    printed = wellen.Printed(ctx.printed)
    thresh = min((1.0 - p.eps) * w + CLEAR_MARGIN_MM, w - overlap - 0.05)
    exempt = 2.0 * w

    def pieces(u_s: float, sigma: float):
        fit = _fit_profile(shape, u_s, u_e, amp, opts, w)
        if fit is None:
            return None
        uv, k, r_wave = fit
        w1 = uv.copy()
        w1[:, 1] = sigma * (c + w1[:, 1])
        arc = arc_points(np.array([u_e, 0.0]), v_t, sigma * math.pi / 2, -sigma * math.pi, 0.05, 1.0)
        arc[0], arc[-1] = w1[-1], [u_e, -w1[-1, 1]]
        w2 = w1[::-1].copy()
        w2[:, 1] = -w2[:, 1]
        return (
            wellen.to_xy(fr, w1),
            wellen.to_xy(fr, arc),
            wellen.to_xy(fr, w2),
            k,
            r_wave,
        )

    def feasible(curve: np.ndarray) -> bool:
        dense = densify(curve, CHECK_MM)
        s = wellen.arc_of(dense)
        if printed.violates(dense, s, thresh, exempt) or wellen.self_violates(dense, s, thresh, exempt):
            return False
        return LineString(np.vstack([printed.pts[-3:], dense[1:]])).is_simple

    # 1. Einlauf: Welle 1 beginnt immer in einem Scheitel (u_s, σ·v_t) mit Richtung +u. Der Biarc
    #    hängt also nur von (σ, u_s) ab; Kandidaten nach (Einlaufradius bis w, frühester Einstieg).
    cands = []
    lo = max(u0 - w, u_entry)
    for sigma in (sigma0, -sigma0):
        full_radius = False
        for u_s in np.arange(lo, lo + SEARCH_W * w + 1e-9, 1.0):
            if u_e - u_s < w:
                break
            q = wellen.to_xy(fr, np.array([[u_s, sigma * v_t]]))[0]
            res = biarc(entry, t_in, q, fr["eu"], 0.05, 1.0)
            if res is None:
                continue
            lead, r_lead = res
            r_lead = min(r_lead, w)
            if r_lead < (1.0 - RADIUS_TOL) * w / 2.0:
                continue
            # Vorprüfung nur des Einlaufs (plus 2·w geradeaus am Scheitel)
            probe = np.vstack([lead, q + 2.0 * w * fr["eu"]])
            cands.append(((round(r_lead, 1), -float(u_s)), sigma, float(u_s), lead, r_lead, probe))
            # frühester Einstieg mit vollem Radius w: besser wird es auf dieser Seite nicht
            if r_lead >= w - 1e-6 and feasible(probe):
                full_radius = True
                break
        if full_radius:
            break
    cands.sort(key=lambda c: c[0], reverse=True)
    # 2. Wellen bauen und den ganzen Strang prüfen, bis ein Kandidat passt
    best = None
    for _, sigma, u_s, lead, r_lead, probe in cands:
        if not feasible(probe):
            continue
        pc = pieces(u_s, sigma)
        if pc is None:
            continue
        w1, arc, w2, k, r_wave = pc
        if min(r_wave, v_t) < (1.0 - RADIUS_TOL) * w / 2.0:
            continue
        if feasible(np.vstack([lead, w1[1:], arc[1:], w2[1:]])):
            best = (
                None,
                {"lead": lead, "w1": w1, "arc": arc, "w2": w2, "k": k, "r_wave": r_wave,
                 "r_lead": r_lead, "u_s": u_s, "sigma": sigma},
            )  # fmt: skip
            break
    if best is None:
        return IslandPlan(
            [], meta={**base, "skipped": "kein kreuzungsfreier Einlauf bzw. Wellen passen nicht ins Band"}
        )
    b = best[1]
    rs = lambda a: wellen.resample_pieces(a, p.step_mm, p.chord_tol_mm)  # noqa: E731
    s1 = rs(np.vstack([b["lead"], b["w1"][1:]]))
    s2 = rs(b["arc"])
    s3 = rs(b["w2"])
    s2[0], s3[0] = s1[-1], s2[-1]
    label = LABELS[shape]
    segs = [
        Segment("infill", p.shells, s1, label=f"{label}: Welle 1 (hin)"),
        Segment("infill", p.shells, s2, label=f"{label}: Wende"),
        Segment("infill", p.shells, s3, label=f"{label}: Welle 2 (zurück)"),
    ]
    contacts = _shell_contacts(segs, printed, w, p.contact_tol_mm) + _node_contacts(segs, w, p.contact_tol_mm)
    lam = (u_e - b["u_s"]) / b["k"]
    meta = {
        **base,
        "wavelength_mm": round(lam, 2),
        "wavelength_target_mm": round(_target_wavelength(shape, amp, opts), 2),
        "wavelengths": b["k"],
        "amplitude_mm": round(amp, 2),
        "crest_v_mm": round(v_t, 2),
        "contact_v_mm": round(v_b, 2),
        "lead_in_radius_mm": round(b["r_lead"], 2),
        "wave_min_radius_mm": round(b["r_wave"], 2) if math.isfinite(b["r_wave"]) else None,
        "u_start_mm": round(b["u_s"] - u0, 2),
        "node_contacts": sum(1 for c in contacts if c.kind == "node"),
        "shell_contacts": sum(1 for c in contacts if c.kind == "shell"),
        **({"overlap_clamped": True} if overlap < overlap_req - 1e-9 else {}),
    }
    if shape == "waben":
        th = math.radians(float(opts["flank_angle_deg"]))
        meta["plateau_mm"] = round(lam / 2.0 - stroke / math.tan(th), 2)
        meta["flank_angle_deg"] = float(opts["flank_angle_deg"])
        meta["round_radius_mm"] = round(float(opts["round_radius_mm"]), 2)
    return IslandPlan(segs, contacts, meta)


def _runs(idx: np.ndarray) -> list[np.ndarray]:
    return np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []


def _shell_contacts(segs: list[Segment], printed: wellen.Printed, w: float, tol: float) -> list[Contact]:
    """Kontaktzonen Infill ↔ Schalen je eigenem Segment (Bogenlängenabstand > 2·w)."""
    out: list[Contact] = []
    s0 = 0.0
    for k, seg in enumerate(segs):
        dense = densify(seg.points, CHECK_MM)
        s = s0 + wellen.arc_of(dense)
        s0 = float(s[-1])
        d, j = printed.tree.query(dense)
        jj = np.minimum(j, len(printed.t) - 1)
        hit = (d <= w + tol) & (printed.t[jj] + s > 2.0 * w)
        for run in _runs(np.flatnonzero(hit)):
            mid = run[len(run) // 2]
            at = (dense[mid] + printed.pts[jj[mid]]) / 2.0
            length = float(s[run[-1]] - s[run[0]]) + CHECK_MM
            out.append(Contact("shell", tuple(at), length, (-1, k), float(d[run].min())))
    return out


def _node_contacts(segs: list[Segment], w: float, tol: float) -> list[Contact]:
    """Mittelkontakte Welle 1 ↔ Welle 2 (Abstand ≤ w + tol)."""
    a = densify(segs[0].points, CHECK_MM)
    b = densify(segs[-1].points, CHECK_MM)
    d, j = cKDTree(b).query(a)
    out: list[Contact] = []
    s = wellen.arc_of(a)
    for run in _runs(np.flatnonzero(d <= w + tol)):
        if s[run[-1]] - s[run[0]] < 1e-9 and len(run) == 1 and run[0] in (0, len(a) - 1):
            continue
        mid = run[len(run) // 2]
        at = (a[mid] + b[j[mid]]) / 2.0
        length = float(s[run[-1]] - s[run[0]]) + CHECK_MM
        out.append(Contact("node", tuple(at), length, (0, len(segs) - 1), float(d[run].min())))
    return out


LABELS = {"sinus": "Doppelwelle", "waben": "Waben"}

_DESC = (
    "Zwei gegenphasige Wellen berühren sich in der Bandmitte (Kontakt, keine Kreuzung); ein Strang: "
    "hin als Welle 1, Wende am Bandende, zurück als Welle 2. Für Wände ≥ 300 mm mit 2 Schalen oder "
    "eine Schale je Seite; im 50-mm-Band von S1 zu schmal (Hub 12,25 mm < w/2)."
)


@pattern(
    "doppelwelle",
    "infill",
    "Doppelwelle (Kettenglied)",
    params=DOUBLE_PARAMS,
    description="Doppelwelle aus zwei Sinuswellen, Kettenglieder. " + _DESC,
)
def build_double_wave(ctx: IslandContext) -> IslandPlan:
    return build_double(ctx, "sinus")


@pattern(
    "waben",
    "infill",
    "Waben",
    params=HONEYCOMB_PARAMS,
    description="Waben aus zwei gegenphasigen Trapezwellen, Sechseckzellen. " + _DESC,
)
def build_honeycomb(ctx: IslandContext) -> IslandPlan:
    return build_double(ctx, "waben")


@pattern(
    "fermat",
    "full",
    "Fermat-Spirale (kleine Inseln)",
    params=fermat.PARAMS,
    description=(
        "Connected Fermat Spiral (Zhao et al. 2016) für kleine Inseln wie Pfeiler: Ringe im Abstand w, "
        "einwärts auf jedem zweiten Ring, Kehre innen, auswärts dazwischen. Start und Ende am Rand "
        "nebeneinander; mit alternate senkrechter Schichtwechsel. Breite Inseln: Grundmuster."
    ),
)
def build_fermat(ctx: IslandContext) -> IslandPlan:
    return fermat.build(ctx)
