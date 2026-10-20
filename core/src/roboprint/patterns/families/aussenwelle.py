"""Outfill-Familie „Außenwelle“ (O1): gewellte Außenschale innerhalb der IFC-Wanddicke.

Idee (AUFTRAG, Abschnitt Outfill, O1; recherche.md §6): Die Außenschale (Schale 0) läuft auf den
langen Außenseiten nicht gerade, sondern als Welle. Längsschwinden baut sich dann durch Verformung
der Welle ab (Bogenlängenzuwachs), statt eine lange gerade Raupe zu reißen. Kennzahl ist die
längste gerade, ungestützte Außenstrecke (metrics: `longest_straight_outer_mm`).

Geometrie
---------
Ausgangspunkt ist der gerundete Schalenring 0 des Kerns (`ctx.lanes`, Offset w/2, Eckradius
`corner_radius`). Gewellt werden nur seine **geraden Stücke, die an einer y-Fläche des Teils
liegen** (y = y_min/y_max der Teil-Bounding-Box ± w/2: die langen Außenseiten). Stoßflächen
(x-Flächen), Laibungen und die gerundeten Ecken bleiben, wie der Kern sie baut.

Die Auslenkung d(s) zeigt immer **nach innen** (Normale in die Insel) und liegt in [0, D] mit
D = 2·A (Spitze-Spitze). So bleibt die Raupe bündig mit der IFC-Fläche (Außenkante genau auf der
Fläche, M5 ohne die 1-mm-Toleranz zu nutzen) und die Welle steht nie über die Wand hinaus.
- `sinus`: d(s) = A·(1 − cos(2π·s/λ)). Anfang und Ende jeder Wellenzone haben d = 0 und d' = 0,
  der Übergang in Ecke bzw. Gerade ist tangentenstetig. Kleinster Radius R = λ²/(4π²·A).
- `zickzack`: Dreieck 0 → D → 0 mit gerundeten Scheiteln (Radius `outer_round_radius_mm`); die
  Fußpunkte an den Zonenenden werden mit demselben Radius in die Gerade übergeführt. Die geraden
  Flanken sind die längsten geraden Außenstrecken (≈ λ/2).
Gewellt wird in **Wellenzonen**, die aus dem ganzen Teil bestimmt werden (`wave_zones`, M3): nur
dort, wo jede Schicht an dieser Fläche ein gerades Stück von Schale 0 hat. Ändert sich der
Querschnitt (Brüstung, Sturz, Pfeiler neben einer Öffnung), bleiben die Stücke über bzw. unter der
Öffnung in allen Schichten gerade, und die Wellen liegen deckungsgleich übereinander. Je Zone wird
eine ganze Zahl von Wellen eingepasst (`fit_to_length`, Rest gleichmäßig verteilt); die
tatsächliche Wellenlänge steht in `meta.runs`. Das Ergebnis hängt damit von `ctx.sections` ab,
aber nur über Größen, die innerhalb eines `plan_pattern`-Aufrufs für alle Schichten gleich sind;
gleiche Inselgeometrie gibt deshalb gleiches Ergebnis, und `layer_invariant` bleibt True (der
Cache in plan.py lebt nur einen Aufruf).

Amplitude und Nachbarbahn (Kern der Begründung)
-----------------------------------------------
Die Outfill-Rolle ersetzt nur den Ring der Schale 0; die innere Nachbarbahn (Schale 1 bzw. das
Infill, das Schale 0 berührt) bleibt an ihrem Sollort. Damit gilt für die Auslenkung D nach innen:
- **zwei oder mehr Schalen**: Schale 1 liegt w neben der Soll-Lage von Schale 0. Die Welle darf
  sie nur mit gewolltem Kontakt berühren (Mittellinienabstand ≥ (1 − ε)·w, M2/M7):
  D ≤ ε·w − 0,5 mm = 4,0 mm (w = 30, ε = 0,15), also A ≤ 2,0 mm. Die Wellentäler berühren Schale 1
  mit 26 mm Mittellinienabstand (Kontaktzonen je λ).
- **eine Schale mit Infill**: Das Infill berührt Schale 0 selbst schon mit seiner eigenen
  Überlappung (Wellen: 5 % = 1,5 mm). Für die Welle bleibt die Hälfte des Kontaktbudgets:
  D ≤ ε·w/2 − 0,25 mm = 2,0 mm, A ≤ 1,0 mm.
- **eine Schale ohne Infill**: Innen ist Hohlraum. D ≤ (t − 2·w)/2 − 1 mm mit t = örtliche
  Dicke hinter der Wellenzone über alle Schichten (`local_thickness`; 200 mm: 69 mm); die
  Startwerte A = 8 mm, λ = 150 mm passen unverändert (D = 16 mm, R_min = 71 mm, Bogenzuwachs
  (πA/λ)² ≈ 2,8 %, gemessen mit eingepasstem λ 2,2–2,7 %).
- **je Zone M6** (`_profile`): Sinus A ≤ λ²/(4π²·w) (Ziel R ≥ w), Zickzack mit ungekürztem
  Scheitelradius max(r, w/2) und ohne Überlappung von Fuß- und Scheitelbogen; sonst wird D
  kleiner.
Die angeforderte Amplitude wird auf diese Grenzen gekappt; `meta` nennt beide Werte und den Grund
(`amplitude_limited_by`). Eine volle 8-mm-Welle bei zwei Schalen bräuchte eine mitwellende bzw.
um D nach innen gerückte Schale 1; das kann die Outfill-Schnittstelle (`shell_chain(ring0=…)`)
nicht ausdrücken (Kerneinwand, docs/muster/aussenwelle.md).

Naht: `choose_seam` des Kerns. Bei kleiner Auslenkung (D < 8,8 mm) bleibt sie in der Mitte des
Eckbogens; bei einer Schale ohne Infill (D = 16 mm) wandert sie in das erste Wellental der Fläche
y_min, die Raupenkante liegt dort D hinter der Außenfläche (recherche.md §7: „Naht im Wellental“).
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import numpy as np
import shapely.wkb
from shapely.geometry import box

from roboprint.patterns import IslandContext, IslandPlan, ParamSpec, Segment, pattern
from roboprint.patterns.geometry import dedupe, fillet_polyline, offset_ring, resample_curve, tangent_arc
from roboprint.patterns.layout import fit_to_length

#: Feine Abtastung vor dem Neu-Abtasten (wie der Kern, Sehnenfehler gesamt ≤ chord_tol + 0,05)
FINE_TOL_MM = 0.05
#: Ein Ringstück gilt als „an der y-Fläche“, wenn beide Enden ≤ LINE_TOL_MM von y_face ± w/2 liegen
LINE_TOL_MM = 0.05
#: Sicherheitsabstand zur M2-Grenze (1 − ε)·w bei Kontakt mit der Nachbarbahn
CONTACT_MARGIN_MM = 0.5
#: Kleinste Wellenzone in Wellenlängen; kürzere gerade Stücke bleiben gerade
MIN_WAVES = 1

SHAPES = ("sinus", "zickzack")
FACES = ("beide", "y_min", "y_max")

PARAMS = (
    ParamSpec(
        "outer_wavelength_mm",
        "Wellenlänge außen",
        150.0,
        "mm",
        60.0,
        600.0,
        5.0,
        help="Sollwert; je gerader Außenstrecke wird eine ganze Zahl von Wellen eingepasst",
    ),
    ParamSpec(
        "outer_amplitude_mm",
        "Amplitude außen",
        8.0,
        "mm",
        0.5,
        30.0,
        0.5,
        help="Halbe Spitze-Spitze-Auslenkung nach innen; wird auf die Grenze der Nachbarbahn gekappt",
    ),
    ParamSpec(
        "outer_shape",
        "Wellenform außen",
        "sinus",
        "",
        kind="choice",
        choices=SHAPES,
        help="Sinus oder Zickzack mit gerundeten Scheiteln",
    ),
    ParamSpec(
        "outer_round_radius_mm",
        "Scheitelradius (Zickzack)",
        60.0,
        "mm",
        15.0,
        500.0,
        1.0,
        help="Radius der Zickzack-Scheitel (M6: hart ≥ w/2, Ziel ≥ w)",
    ),
    ParamSpec(
        "outer_faces",
        "Gewellte Seiten",
        "beide",
        "",
        kind="choice",
        choices=FACES,
        help="Welche lange Außenseite gewellt wird; die Stoßflächen bleiben immer gerade",
    ),
)


def amplitude_limit(ctx: IslandContext) -> tuple[float, str]:
    """Größte Spitze-Spitze-Auslenkung D nach innen und der Grund (siehe Modul-Docstring)."""
    p = ctx.params
    if p.shells >= 2:
        return p.eps * p.w - CONTACT_MARGIN_MM, "Schale 1 (Kontakt ≥ (1 − ε)·w)"
    if p.infill != "none":
        return p.eps * p.w / 2.0 - CONTACT_MARGIN_MM / 2.0, "Infill an Schale 0 (halbes Kontaktbudget)"
    t = ctx.part_bounds[3] - ctx.part_bounds[1]
    return max((t - 2.0 * p.w) / 2.0 - 1.0, 0.0), "Gegenseite (Hohlraum)"


def local_thickness(ctx: IslandContext, y_line: float, lo: float, hi: float) -> float:
    """Örtliche Wanddicke hinter einer Wellenzone [lo, hi] auf der Fläche y_line, über alle Schichten.

    Die Grenze „Gegenseite“ in `amplitude_limit` rechnet mit der Dicke der Teil-Bounding-Box. Bei
    einem L- oder T-förmigen Teil ist der Arm mit der Welle dünner (gemessen: Arm 100 mm in einem
    600 mm tiefen L-Teil, A = 30 mm, λ = 600 mm → Welle 10 mm Mittellinienabstand zur Gegenseite,
    M2-Fehler). Gemessen wird deshalb je Schicht in der Spalte [lo − w, hi + w] der Abstand von der
    Fläche bis zum ersten Rand der Insel nach innen (Teile des Komplements, die die Fläche selbst
    berühren, liegen seitlich neben der Zone und zählen nicht)."""
    w = ctx.params.w
    _, y0, _, y1 = ctx.part_bounds
    lower = y_line < 0.5 * (y0 + y1)
    face = y0 if lower else y1
    best = y1 - y0
    seen: set[bytes] = set()
    for geom in ctx.sections.values():
        if geom is None or geom.is_empty or geom.wkb in seen:
            continue
        seen.add(geom.wkb)
        best = min(best, _column_depth(geom.wkb, round(lo - w, 6), round(hi + w, 6), face, lower, y1 - y0))
    return best


@lru_cache(maxsize=256)
def _column_depth(wkb: bytes, x0: float, x1: float, face: float, lower: bool, t: float) -> float:
    geom = shapely.wkb.loads(wkb)
    y_lo, y_hi = (face, face + t) if lower else (face - t, face)
    rest = box(x0, y_lo, x1, y_hi).difference(geom)
    depth = t
    for part in getattr(rest, "geoms", [rest]):
        if part.is_empty or part.area < 1e-6:
            continue
        b = part.bounds
        gap = (b[1] - face) if lower else (face - b[3])
        if gap > LINE_TOL_MM:  # berührt die Fläche nicht: liegt innen gegenüber
            depth = min(depth, gap)
    return depth


def _face_runs(ring: np.ndarray, ctx: IslandContext, faces: str) -> list[tuple[int, int, float]]:
    """Gerade Ringstücke an den y-Flächen: (i0, i1, Flächen-y) mit Ringindizes i0 < i1, ohne
    Umlauf über den Ringanfang (der Ring beginnt bei offset_ring an einer Ecke)."""
    w = ctx.params.w
    _, y0, _, y1 = ctx.part_bounds
    lines = []
    if faces in ("beide", "y_min"):
        lines.append(y0 + w / 2.0)
    if faces in ("beide", "y_max"):
        lines.append(y1 - w / 2.0)
    runs: list[tuple[int, int, float]] = []
    for yl in lines:
        on = np.abs(ring[:, 1] - yl) <= LINE_TOL_MM
        seg_on = on[:-1] & on[1:]
        i = 0
        n = len(seg_on)
        while i < n:
            if not seg_on[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and seg_on[j + 1]:
                j += 1
            runs.append((i, j + 1, yl))
            i = j + 1
    return runs


def _profile(
    shape: str,
    length: float,
    D: float,
    lam_target: float,
    radius: float,
    base_radius: float = 0.0,
    min_radius: float = 0.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Wellenprofil wie `_profile_once`, mit Auslenkung so weit verkleinert, dass M6 hält.

    `min_radius` ist der Zielradius des Sinus (w). Zickzack: Die Scheitel behalten den Radius
    max(`radius`, w/2) ungekürzt, und Fußbogen (`base_radius`) und Scheitelbogen dürfen sich auf
    einer Flanke nicht überlappen. Sonst entstünde bei kurzen Zonen bzw. steiler Welle ein Knick
    (gemessen: R = 3,5 mm bei λ = 86 mm, D = 34 mm, w = 25). Hält eine Bedingung nicht, wird D in
    Schritten von 15 % verkleinert (Zickzack: auch, wenn die Fußbögen keine Zone übrig lassen);
    unter 0,2 mm bleibt die Strecke gerade."""
    d = D
    while d > 0.2:
        prof, info = _profile_once(shape, length, d, lam_target, radius, base_radius)
        if not len(prof):
            if shape == "sinus":  # Zone < λ/2 hängt beim Sinus nicht an D
                break
            d *= 0.85
            continue
        if not info.pop("_ok", True):
            d *= 0.85
            continue
        if shape == "sinus" and info["min_radius_mm"] < min_radius - 1e-6:
            # R = λ²/(4π²·A): A direkt aus der eingepassten Wellenlänge (hängt nicht an D)
            lam = info["wavelength_mm"]
            d = min(0.999 * d, 0.999 * 2.0 * lam * lam / (4.0 * math.pi**2 * min_radius))
            continue
        info["amplitude_mm"] = round(d / 2.0, 3)
        if d < D - 1e-9:
            info["amplitude_limited_by"] = "Krümmungsradius (M6)"
        return prof, info
    return np.empty((0, 2)), {}


def _profile_once(
    shape: str, length: float, D: float, lam_target: float, radius: float, base_radius: float = 0.0
) -> tuple[np.ndarray, dict[str, Any]]:
    """Wellenprofil (s, d) einer geraden Strecke der Länge `length`, d ∈ [0, D], d(0) = d(L) = 0.

    Rückgabe (Punkte (n, 2) fein, Info) oder ein leeres Array, wenn keine Welle hineinpasst.
    `longest_straight_mm` ist der geometrische Wert (Sinus: 0, Zickzack: gerade Flanke); gemessen
    wird zusätzlich am abgetasteten Ring (`longest_straight_on_faces`)."""
    if shape == "sinus":
        margin = 0.0
    else:
        # Fußpunkt an den Zonenenden: Knick α, Übergangsbogen mit r_b = max(r, base_radius) braucht
        # r_b·tan(α/2) Gerade vor der Zone. α für die kürzeste Wellenlänge, die fit_to_length
        # liefern kann (≥ λ/2 bei Zonen ≥ λ/2), damit der Bogen sicher vor der Zone beginnt
        alpha = math.atan2(4.0 * D, lam_target)
        base_radius = max(radius, base_radius)
        margin = base_radius * math.tan(alpha / 2.0) + 1.0
    zone = length - 2.0 * margin
    if zone < MIN_WAVES * lam_target * 0.5 or D <= 1e-6:
        return np.empty((0, 2)), {}
    fit = fit_to_length(zone, lam_target, min_count=MIN_WAVES)
    lam = fit.length_mm
    info: dict[str, Any] = {"waves": fit.count, "wavelength_mm": round(lam, 3), "zone_mm": round(zone, 3)}
    if shape == "sinus":
        A = D / 2.0
        s = np.linspace(0.0, zone, max(int(math.ceil(zone / 0.5)), 8) + 1)
        prof = np.column_stack([s, A * (1.0 - np.cos(2.0 * math.pi * s / lam))])
        info["min_radius_mm"] = round(lam * lam / (4.0 * math.pi**2 * A), 2)
        info["longest_straight_mm"] = 0.0
        return prof, info
    k = np.arange(2 * fit.count + 1)
    verts = np.column_stack([margin + k * lam / 2.0, np.where(k % 2 == 1, D, 0.0)])
    # Scheitel und Täler innerhalb der Zone (Zonenenden bleiben Ecken), dann die Fußpunkte mit dem
    # größeren Radius r_b: Ein kurzer Bogen r neben der Geraden ergäbe nach dem Neu-Abtasten
    # (step 20 mm) eine Sehne über Bogen und Gerade, die metrics als Sehnenfehler > 0,5 mm schätzt
    zz, r_used = fillet_polyline(verts, radius, chord_tol_mm=FINE_TOL_MM, step_mm=2.0)
    theta = math.atan2(2.0 * D, lam)  # halber Knick an Scheitel und Tal
    tb = base_radius * math.tan(theta / 2.0)
    leg = np.array([math.cos(theta), math.sin(theta)])
    head = tangent_arc(
        np.array([margin - tb, 0.0]), np.array([1.0, 0.0]), verts[0] + tb * leg, FINE_TOL_MM, 2.0
    )[0]
    back = np.array([math.cos(theta), -math.sin(theta)])
    tail = tangent_arc(verts[-1] - tb * back, back, np.array([verts[-1][0] + tb, 0.0]), FINE_TOL_MM, 2.0)[0]
    prof = np.vstack([[0.0, 0.0], head, zz[1:-1], tail, [length, 0.0]])
    # M6: Scheitelradius ungekürzt, Fußbogen und erster/letzter Scheitelbogen ohne Überlappung
    leg_len = math.hypot(lam / 2.0, D)
    info["_ok"] = bool(r_used >= radius - 1e-6 and tb + r_used * math.tan(theta) <= leg_len + 1e-9)
    r_used = min(r_used, base_radius)
    info["min_radius_mm"] = round(r_used, 2)
    info["longest_straight_mm"] = round(
        max(math.hypot(lam / 2.0, D) - 2.0 * r_used * math.tan(theta), 0.0), 2
    )
    return dedupe(prof), info


def _face_lines(ctx: IslandContext, faces: str) -> list[float]:
    """y der Mittellinie von Schale 0 an den gewählten langen Außenseiten."""
    w = ctx.params.w
    _, y0, _, y1 = ctx.part_bounds
    return ([y0 + w / 2.0] if faces in ("beide", "y_min") else []) + (
        [y1 - w / 2.0] if faces in ("beide", "y_max") else []
    )


@lru_cache(maxsize=256)
def _section_intervals(
    wkb: bytes, w: float, corner_radius: float, y_line: float
) -> tuple[tuple[float, float], ...]:
    """x-Intervalle der geraden Stücke von Schale 0 aller Inseln eines Querschnitts auf y = y_line."""
    geom = shapely.wkb.loads(wkb)
    out: list[tuple[float, float]] = []
    for kind, ring in offset_ring(geom, w / 2.0, corner_radius):
        if kind != "exterior":
            continue
        on = np.abs(ring[:, 1] - y_line) <= LINE_TOL_MM
        for k in np.flatnonzero(on[:-1] & on[1:]):
            lo, hi = sorted((float(ring[k, 0]), float(ring[k + 1, 0])))
            out.append((lo, hi))
    return tuple(_merge(out))


def _merge(iv: list[tuple[float, float]]) -> list[tuple[float, float]]:
    res: list[tuple[float, float]] = []
    for lo, hi in sorted(iv):
        if res and lo <= res[-1][1] + LINE_TOL_MM:
            res[-1] = (res[-1][0], max(res[-1][1], hi))
        else:
            res.append((lo, hi))
    return res


def _intersect(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> list[tuple[float, float]]:
    res = []
    for lo1, hi1 in a:
        for lo2, hi2 in b:
            lo, hi = max(lo1, lo2), min(hi1, hi2)
            if hi - lo > LINE_TOL_MM:
                res.append((lo, hi))
    return _merge(res)


def wave_zones(ctx: IslandContext, y_line: float) -> list[tuple[float, float]]:
    """x-Intervalle, in denen die Welle auf der Fläche y_line liegen darf (M3, ganzes Teil).

    Gewellt wird nur, wo **jede** nicht leere Schicht des Teils dort ein gerades Stück von
    Schale 0 hat: Schnitt über alle Schichten. Jede Zone wird in jeder Schicht gleich eingeteilt
    (Wellenlänge und Phase hängen nur an der Zone), die Welle liegt also deckungsgleich
    übereinander. Ohne diese Regel säße z. B. über einer Brüstung ein Pfeiler mit eigener
    Einteilung auf der Welle darunter, versetzt um bis zu D, also Überhang. Über einer Öffnung
    bzw. neben neuen Laibungen bleibt die Außenschale deshalb in allen Schichten gerade."""
    p = ctx.params
    zones: list[tuple[float, float]] | None = None
    seen: set[bytes] = set()
    for geom in ctx.sections.values():
        if geom is None or geom.is_empty:
            continue
        wkb = geom.wkb
        if wkb in seen:
            continue
        seen.add(wkb)
        iv = list(_section_intervals(wkb, p.w, p.corner_radius, round(y_line, 6)))
        zones = iv if zones is None else _intersect(zones, iv)
        if not zones:
            return []
    return zones or []


def wave_ring(ctx: IslandContext) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Gewellter Ring der Schale 0 (geschlossen, gegen den Uhrzeigersinn) und meta."""
    lam = float(ctx.param("outer_wavelength_mm"))
    A_req = float(ctx.param("outer_amplitude_mm"))
    shape = str(ctx.param("outer_shape"))
    radius = float(ctx.param("outer_round_radius_mm"))
    faces = str(ctx.param("outer_faces"))
    rings = [ln.ring for ln in ctx.lanes if ln.shell == 0 and ln.kind == "exterior"]
    if not rings:
        return None, {"empty": True}
    ring = _start_off_faces(max(rings, key=lambda r: abs(_area(r))), ctx)
    D_max, reason = amplitude_limit(ctx)
    p = ctx.params
    base_r = p.step_mm**2 / (8.0 * p.chord_tol_mm)  # Sehne step über Bogen r_b: Pfeilhöhe ≤ chord_tol
    D = min(2.0 * A_req, D_max)
    meta: dict[str, Any] = {
        "shape": shape,
        "amplitude_requested_mm": A_req,
        "amplitude_mm": round(D / 2.0, 3),
        "peak_to_peak_mm": round(D, 3),
        "amplitude_limited_by": reason if 2.0 * A_req > D_max + 1e-9 else None,
        "runs": [],
    }
    zones = {round(y, 6): wave_zones(ctx, y) for y in _face_lines(ctx, faces)}
    runs = sorted(_face_runs(ring, ctx, faces))
    out: list[np.ndarray] = []
    pos = 0
    gain_len = straight_len = 0.0
    for i0, i1, y_line in runs:
        a, b = ring[i0], ring[i1]
        length = float(np.linalg.norm(b - a))
        u = (b - a) / length
        n_in = np.array([-u[1], u[0]])  # links der Laufrichtung = innen (Ring gegen Uhrzeigersinn)
        lo_run, hi_run = sorted((float(a[0]), float(b[0])))
        pieces: list[tuple[float, np.ndarray]] = []
        for lo, hi in _intersect([(lo_run, hi_run)], zones.get(round(y_line, 6), [])):
            s0, s1 = sorted((abs(lo - float(a[0])), abs(hi - float(a[0]))))
            D_z, local = D, None
            if p.shells == 1 and p.infill == "none":
                t_loc = local_thickness(ctx, y_line, lo, hi)
                D_loc = max((t_loc - 2.0 * p.w) / 2.0 - 1.0, 0.0)
                if D_loc < D - 1e-9:
                    D_z, local = D_loc, f"Gegenseite (örtliche Dicke {t_loc:.0f} mm)"
            prof, info = _profile(shape, s1 - s0, D_z, lam, max(radius, p.w / 2.0), base_r, p.w)
            if local and len(prof) and "amplitude_limited_by" not in info:
                info["amplitude_limited_by"] = local
            if not len(prof):
                continue
            pts = a + (prof[:, :1] + s0) * u + prof[:, 1:] * n_in
            arc = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
            gain_len += arc
            straight_len += s1 - s0
            pieces.append((s0, pts))
            meta["runs"].append(
                {
                    "from": [round(float(pts[0][0]), 2), round(float(pts[0][1]), 2)],
                    "to": [round(float(pts[-1][0]), 2), round(float(pts[-1][1]), 2)],
                    "length_mm": round(s1 - s0, 2),
                    "arc_gain_pct": round(100.0 * (arc / (s1 - s0) - 1.0), 3),
                    **info,
                }
            )
        if not pieces:
            continue
        waved = [a[None, :]] + [q for _, q in sorted(pieces, key=lambda t: t[0])] + [b[None, :]]
        out.append(ring[pos:i0])
        out.append(np.vstack(waved))
        pos = i1 + 1
    out.append(ring[pos:])
    res = dedupe(np.vstack(out))
    if np.linalg.norm(res[0] - res[-1]) > 1e-9:
        res = np.vstack([res, res[:1]])
    meta["arc_gain_pct"] = round(100.0 * (gain_len / straight_len - 1.0), 3) if straight_len else 0.0
    meta["longest_straight_face_mm"] = round(longest_straight_on_faces(res, ctx, D), 2)
    if meta["runs"]:
        meta["min_radius_mm"] = min(r["min_radius_mm"] for r in meta["runs"])
        a_min = min(r["amplitude_mm"] for r in meta["runs"])
        if a_min < meta["amplitude_mm"] - 1e-9:
            # mindestens eine Zone wegen M6 flacher: ehrlich die kleinste gebaute Amplitude nennen
            meta["amplitude_mm"] = a_min
            meta["peak_to_peak_mm"] = round(2.0 * a_min, 3)
            meta["amplitude_limited_by"] = next(
                r.get("amplitude_limited_by") for r in meta["runs"] if r["amplitude_mm"] == a_min
            )
    return res, meta


def longest_straight_on_faces(ring: np.ndarray, ctx: IslandContext, D: float) -> float:
    """Längste gerade Strecke des Rings an den langen Außenseiten (y-Flächen), gemessen wie
    metrics (Knick > 1° beendet eine Gerade) am mit step/chord_tol abgetasteten Ring. Anders als
    `longest_straight_outer_mm` zählen die Stoßflächen nicht mit: Sie bleiben gewollt gerade und
    liegen quer zur Schwindrichtung der Wand."""
    p = ctx.params
    pts = resample_curve(ring, p.step_mm, p.chord_tol_mm, closed=True)
    _, y0, _, y1 = ctx.part_bounds
    band = D + LINE_TOL_MM + 0.5
    near = (np.abs(pts[:, 1] - (y0 + p.w / 2.0)) <= band) | (np.abs(pts[:, 1] - (y1 - p.w / 2.0)) <= band)
    v = np.diff(pts, axis=0)
    ang = np.arctan2(v[:, 1], v[:, 0])
    turn = np.degrees(np.abs((np.diff(ang) + np.pi) % (2 * np.pi) - np.pi))
    best = run = 0.0
    for k in range(len(v)):
        if k > 0 and turn[k - 1] > 1.0:
            run = 0.0
        if near[k] and near[k + 1]:
            run += float(np.linalg.norm(v[k]))
            best = max(best, run)
        else:
            run = 0.0
    return best


def _start_off_faces(ring: np.ndarray, ctx: IslandContext) -> np.ndarray:
    """Ring so drehen, dass er an einem Punkt abseits der y-Flächen beginnt (kein Lauf über den
    Ringanfang); unverändert, wenn es keinen solchen Punkt gibt."""
    w = ctx.params.w
    _, y0, _, y1 = ctx.part_bounds
    r = ring[:-1] if np.linalg.norm(ring[0] - ring[-1]) < 1e-9 else ring
    off = (np.abs(r[:, 1] - (y0 + w / 2.0)) > LINE_TOL_MM) & (np.abs(r[:, 1] - (y1 - w / 2.0)) > LINE_TOL_MM)
    if not np.any(off):
        return ring
    k = int(np.flatnonzero(off)[0])
    r = np.roll(r, -k, axis=0)
    return np.vstack([r, r[:1]])


def _area(r: np.ndarray) -> float:
    x, y = r[:, 0], r[:, 1]
    return 0.5 * float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


@pattern(
    "aussenwelle",
    "outfill",
    "Gewellte Außenschale (O1)",
    params=PARAMS,
    description="Schale 0 läuft auf den langen Außenseiten als Welle (Sinus oder gerundetes Zickzack) "
    "nach innen, bündig mit der IFC-Fläche; Stoßflächen und Ecken bleiben gerade bzw. gerundet. Die "
    "Amplitude wird so gekappt, dass Schale 1 bzw. das Infill nur mit gewolltem Kontakt berührt wird.",
)
def build(ctx: IslandContext) -> IslandPlan:
    ring, meta = wave_ring(ctx)
    if ring is None:
        return IslandPlan([], meta=meta)
    p = ctx.params
    # fein abtasten (Sehnenfehler 0,05 mm): Der Kern schneidet den Ring an der Naht und tastet ihn
    # mit chord_tol neu ab. Ein schon grob abgetasteter Eckbogen ergäbe dabei Knicke (R ≈ 21 mm
    # statt w = 30 mm am Eckbogen der Naht, M6-Warnung).
    pts = resample_curve(ring, p.step_mm, FINE_TOL_MM, closed=True)
    if np.linalg.norm(pts[0] - pts[-1]) > 1e-9:
        pts = np.vstack([pts, pts[:1]])
    return IslandPlan([Segment("outfill", 0, pts, closed=True, label="Außenwelle")], meta=meta)


__all__ = ["FACES", "PARAMS", "SHAPES", "amplitude_limit", "build", "longest_straight_on_faces", "wave_ring"]
