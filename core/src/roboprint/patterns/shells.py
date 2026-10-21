"""Grundmuster „Schalen ohne Infill“: alle Schalen einer Insel als ein Strang, Schalenwechsel ohne
Doppelmaterial, Naht nach `layout.choose_seam`.

Schalenringe. Schale s ist der Rand von Insel ⊖ (s + 0,5)·w, mit runder Fuge (konkave Ecken werden
Bögen) und konvexen Ecken mit Radius `params.corner_radius` (Standard w, Ziel M6). Jede Schale wird
für sich gerundet; die Ringe sind deshalb an konvexen Ecken nicht konzentrisch. Bei r = w liegen
die Mittellinien von Schale 0 und 1 auf der Eckdiagonale √2·w statt w auseinander (Spalt 0,41·w
im Inneren, außen unsichtbar). Konzentrische Ringe hätten außen r₀ = r₁ + w ≥ 1,5·w gebraucht
(Eckverlust 2,8-fach), deshalb diese Wahl.

Schalenwechsel (Begründung). Ein Strang muss von Ring k auf Ring k + 1 wechseln. Drei Wege:
1. Ring k ganz schließen, dann ein Querverbinder der Länge w zu Ring k + 1: Der Verbinder liegt auf
   ganzer Länge über den Raupen beider Ringe → Doppelmaterial, verworfen.
2. Spirale über den ganzen Umfang (Versatz wächst linear): Die Außenhaut wäre nicht mehr eben und
   läge nicht mehr bündig an der Außenfläche (M5, Abdeckung), verworfen.
3. **Gewählt: S-Kurve am Ringende.** Ring k läuft von seinem Start t₀ bis t₀ − ℓ, dann führt eine
   S-Kurve aus zwei tangentenstetigen Bögen mit Radius R = `transition_radius` (Standard w) auf
   Ring k + 1 an die Stelle neben t₀; Ring k + 1 läuft von dort einmal herum und endet neben dem
   Beginn der S-Kurve. Zwischen geraden parallelen Ringen gilt ℓ = 2·sqrt(R² − (R − w/2)²)
   (R = w: ℓ = √3·w ≈ 52 mm). Bei R = w liegt der Mittelpunkt des ersten Bogens genau auf dem Ende
   von Ring k + 1 und der des zweiten genau auf dem Start von Ring k: Die S-Kurve hält zu beiden
   überall genau den Abstand w, berührt also (Kontakt, keine Überlappung). Doppelmaterial entsteht
   nirgends; es bleibt je Wechsel ein Zwickel von etwa w·ℓ/2 in jeder der beiden Bahnen, außen
   direkt vor der Naht, innen hinter dem Ende von Ring k + 1. Beim Rechteck (Naht in der Mitte des
   Eckbogens bei (x_min, y_min), Umlauf gegen den Uhrzeigersinn) liegt der äußere Zwickel auf dem
   halben Eckbogen und dem anschließenden Stück der Stoßfläche x_min (S1: ℓ ≈ 77 mm), also nicht
   auf der Außenfläche. Kürzer ginge es nur mit R < w (M6-Ziel verfehlt, `transition_radius_mm`
   bis w/2 einstellbar); ein voll geschlossener Ring 0 ließe gar keinen Wechsel ohne Überfahren
   des Ringanfangs zu (M2).
   Liegt die Naht in einem Eckbogen oder sind die Ringe kurz (Pfeiler), sucht der Kern das kleinste
   ℓ ≥ ℓ₀, bei dem beide Bögen des Biarcs mindestens R haben und die S-Kurve den Ringanfang nur
   berührt; das Ende von Ring k + 1 wird so gewählt, dass es die S-Kurve nur berührt (`clear_end`).

Schichtwechsel: Gerade Schichten beginnen an der Naht auf Schale 0 und enden innen; ungerade sind
die exakte Umkehrung (plan.py). Ende L = Anfang L + 1, der Wechsel ist ein reiner Z-Hub.

Zu schmale oder an Kerben zerfallende innere Schalen: `shell_chain` misst den Strang (M1, M2,
M5, M6) und fällt auf die größte fehlerfreie Schalenzahl zurück (`meta.shells_dropped`).
Löcher in einer Insel (Schacht im Querschnitt) und zerfallende Schalen (Hals schmaler als w)
werden hier sonst nur angehängt (gerader Verbinder zum nächsten Punkt); M1/M2/M5 melden das. Die
richtige Behandlung ist Aufgabe der Familie „Topologie“.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from roboprint.patterns.geometry import (
    Loop,
    biarc,
    biarc_radius,
    centerline_band,
    densify,
    offset_region,
    offset_ring,
    resample_curve,
)
from roboprint.patterns.layout import choose_seam
from roboprint.patterns.registry import Pattern, register
from roboprint.patterns.types import IslandContext, IslandPlan, Lane, PatternParams, Segment

#: Feine Abtastung der Bögen vor dem Neu-Abtasten (Sehnenfehler gesamt ≤ chord_tol + 0,05 mm)
FINE_TOL_MM = 0.05
#: Abstand S-Kurve ↔ Ringanfang bzw. Ringende ≥ w − CLEAR_TOL_MM (Kontakt ohne Doppelmaterial)
CLEAR_TOL_MM = 0.1
#: Kürzester druckbarer Innenring in w: Ein kürzerer Ring hat weniger als w Durchmesser, seine
#: Raupe überdeckt sich selbst (M2) und lässt keinen Schalenwechsel zu (`clear_end`: Länge > 2·w)
MIN_RING_W = math.pi


def shell_lanes(region: Any, params: PatternParams) -> tuple[Lane, ...]:
    """Schalenringe der Insel, Schale 0 zuerst; je Schale Außenkonturen vor Löchern."""
    out: list[Lane] = []
    for s in range(params.shells):
        rings = offset_ring(region, (s + 0.5) * params.w, params.corner_radius)
        if not rings:
            break
        out.extend(Lane(s, kind, r) for kind, r in rings)
    return tuple(out)


def island_cavity(region: Any, params: PatternParams) -> Any:
    """Hohlraum innerhalb der innersten Schale (Raupenkante)."""
    return offset_region(region, params.shells * params.w, params.corner_radius)


def island_band(region: Any, params: PatternParams) -> Any:
    """Fläche für Infill-Mittellinien, deren Raupe die innerste Schale gerade berührt."""
    return centerline_band(region, params.shells, params.w)


def _main_exterior(lanes: tuple[Lane, ...], shell: int) -> tuple[np.ndarray | None, list[np.ndarray]]:
    """Größte Außenkontur einer Schale und die übrigen Außenkonturen."""
    ext = [ln.ring for ln in lanes if ln.shell == shell and ln.kind == "exterior"]
    if not ext:
        return None, []
    area = [abs(_area(r)) for r in ext]
    i = int(np.argmax(area))
    return ext[i], [r for k, r in enumerate(ext) if k != i]


def _area(r: np.ndarray) -> float:
    x, y = r[:, 0], r[:, 1]
    return 0.5 * float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def _fine(points: np.ndarray, params: PatternParams, closed: bool = False) -> np.ndarray:
    return resample_curve(points, params.step_mm, params.chord_tol_mm, closed=closed)


def _min_dist(a: np.ndarray, b: np.ndarray) -> float:
    """Kleinster Abstand zwischen zwei (dicht abgetasteten) Punktmengen."""
    if len(a) == 0 or len(b) == 0:
        return math.inf
    return float(cKDTree(b).query(a)[0].min())


def _dropped_note(shell: int, params: PatternParams, length: float | None) -> dict[str, Any]:
    """meta-Hinweis, wenn Schalen ab `shell` entfallen: als Restring (`length` = Ringlänge) oder
    weil der Offset-Ring leer ist (`length` None: die Schale passt gar nicht in die Insel)."""
    if length is None:
        return {
            "from_shell": shell,
            "count": params.shells - shell,
            "reason": "kein_ring",
            "hint": f"Schale {shell} passt nicht in die Insel (Offset {(shell + 0.5) * params.w:.1f} mm "
            f"bei w = {params.w:g} mm ergibt keinen Ring) und entfällt mit allen inneren Schalen",
        }
    return {
        "from_shell": shell,
        "count": params.shells - shell,
        "reason": "restring",
        "ring_length_mm": round(length, 2),
        "hint": f"Schale {shell} ist nur ein Restring ({length:.1f} mm < π·w = "
        f"{MIN_RING_W * params.w:.1f} mm) und entfällt mit allen inneren Schalen",
    }


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
    head_tree = cKDTree(head) if len(head) else None  # einmal statt je ℓ (wie `_min_dist`)
    ells = max(ell0, min_ell) + np.arange(0.0, 8.0 * w, 1.0)

    def clear_of(pts: np.ndarray) -> bool:
        probe = densify(pts, 1.0)[:-1]
        gap = math.inf if head_tree is None or not len(probe) else float(head_tree.query(probe)[0].min())
        return gap >= w - CLEAR_TOL_MM

    # Schneller Durchlauf: Gewählt wird das erste ℓ mit r ≥ R und freier S-Kurve; die Bestwerte
    # davor zählen dann nicht (Wertung < 2·R). Punkte und Abstand also nur für ℓ mit r ≥ R. Bricht
    # die Suche ohne Treffer ab, entscheidet der vollständige Durchlauf (Bestwert) wie bisher.
    for ell in ells:
        if ell >= 0.6 * ring.length:
            break
        A = ring.point(start - ell)
        tA = ring.tangent(start - ell, incoming=True)
        r = biarc_radius(A, tA, B, tB)
        if r is None or r < R - 1e-6:
            continue
        pts = biarc(A, tA, B, tB, FINE_TOL_MM, params.step_mm)[0]
        if clear_of(pts):
            return float(ell), pts, tb
    best: tuple[float, np.ndarray, float] | None = None
    for ell in ells:
        if ell >= 0.6 * ring.length:
            break
        A = ring.point(start - ell)
        tA = ring.tangent(start - ell, incoming=True)
        res = biarc(A, tA, B, tB, FINE_TOL_MM, params.step_mm)
        if res is None:
            continue
        pts, r = res
        clear = clear_of(pts)
        score = min(r, R) + (R if clear else 0.0)
        if best is None or score > best[2]:
            best = (float(ell), pts, score)
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
    if not len(ts):
        # Ring kürzer als 2·w: kein Ende frei von der S-Kurve (shell_chain lässt solche Ringe weg;
        # die Familie Topologie fängt den Fehler und versucht weniger Schalen)
        raise ValueError(f"Ring zu kurz für einen Schalenwechsel: {L:.1f} mm ≤ 2·w = {2.0 * w:.1f} mm")
    pts = loop.points(ts)
    dist = cKDTree(densify(trans, 1.0)).query(pts)[0]
    bad = np.flatnonzero(dist < w - CLEAR_TOL_MM)
    if len(bad) == 0:
        return float(ts[-1])
    return float(ts[max(int(bad[0]) - 1, 0)])


def _outside_area(ctx: IslandContext, trans: np.ndarray) -> float:
    """Fläche der Raupe der Kurve `trans` außerhalb der Insel ⊕ 1 mm (M5)."""
    return float(LineString(trans).buffer(ctx.params.w / 2.0).difference(ctx.region.buffer(1.0)).area)


def _transition_gap(ctx: IslandContext, ring: Loop, start: float, trans: np.ndarray) -> float | None:
    """Kleinster Abstand der S-Kurve am Ende eines Einzelrings zum Ringanfang, oder None, wenn die
    Raupe aus der Insel ⊕ 1 mm ragt (M5) oder näher als (1 − ε)·w − CLEAR_TOL_MM kommt (M2; die
    Feinkurve liegt bis 0,1 mm innerhalb der späteren Abtastung, deren Sehnen nach innen schneiden)."""
    w = ctx.params.w
    if _outside_area(ctx, trans) > 1.0:
        return None
    gap = _min_dist(densify(trans, 1.0), densify(ring.sub(start, start + 4.0 * w), 1.0))
    return gap if gap >= (1.0 - ctx.params.eps) * w - CLEAR_TOL_MM else None


def close_single(
    ctx: IslandContext, ring: Loop, start: float, virtuals: list[Loop]
) -> tuple[float, np.ndarray, float, bool] | None:
    """Ende eines Einzelrings mit S-Kurve auf die gedachte Bahn, die die Wand am Ringanfang schließt.

    Die S-Kurve zielt auf den Punkt der gedachten Bahn neben ring(start + δ). δ = 0 trifft bei der
    Eck-Naht die Ecke unter 45° (das Infill bräuchte dann eine Kehre R ≤ 15,9 mm bis zur Raupe der
    Außenschale), δ = 1,5·w die anschließende Gerade: ein Viertelbogen R = 1,5·w = 45 mm, der den
    Ringstart in 30,4 mm berührt (S1). Gewählt wird das erste (Bahn, δ), dessen S-Kurve in der Insel
    liegt, nicht überlappt und den Ringanfang berührt (≤ w + contact_tol); sonst die erste gültige.
    Rückgabe (Ende auf `ring` als Bogenlänge, S-Kurve, ℓ, geschlossen), oder None, wenn keine S-Kurve
    in der Insel liegt und den Ringanfang freilässt (kurze, schmale Module: Die S-Kurve liefe bis an
    die Außenfläche, M5). Der Aufrufer schließt den Ring dann ohne Abgang (`open_end_failed`)."""
    p = ctx.params
    first = None
    for v in virtuals:
        for delta in (1.5 * p.w, p.w, 2.0 * p.w, 0.5 * p.w, 0.0):
            ell, trans, _ = lane_change(ring, v, start + delta, p, min_ell=delta + p.w)
            gap = _transition_gap(ctx, ring, start, trans)
            if gap is None:
                continue
            cand = (start + delta - ell, trans, ell - delta, gap <= p.w + p.contact_tol_mm)
            if cand[3]:
                return cand
            first = first or cand
    if first is not None:
        return first
    # Letzter Versuch ohne Versatz; er muss wenigstens in der Insel liegen (M5), sonst kein Abgang
    ell, trans, _ = lane_change(ring, virtuals[-1], start, p)
    if _outside_area(ctx, trans) > 1.0:
        return None
    return start - ell, trans, ell, False


def shell_chain(
    ctx: IslandContext, ring0: np.ndarray | None = None, ring0_kind: str = "outer", open_end: bool = False
) -> IslandPlan:
    """Alle Schalen der Insel als ein Strang (Richtung außen → innen), mit Rückfall auf weniger
    Schalen.

    Gebaut wird zuerst mit allen Schalen (`_chain`). Hat der Strang dann harte Fehler (M1, M2, M5,
    M6 nach `metrics.measure_path`), weil eine innere Schale zu schmal ist (z. B. 600 × 120 bei
    w = 30: der Innenring ist ein Stadion von w Breite mit Radius < w/2) oder an einer Kerbe
    zerfällt, wird die Schalenzahl schrittweise verringert. Gewählt wird die größte fehlerfreie
    Schalenzahl; ist keine fehlerfrei (z. B. scharfe Ecken mit `corner_radius_mm = 0`, die jede
    Schalenzahl hat), bleibt es bei allen Schalen, und die Prüfung meldet die Fehler. Entfallen
    Schalen, steht das in `meta.shells_dropped` (Grund `regelfehler`, wie Restring und leerer
    Ring). Ein Strang mit nur einer Schale wird nicht gemessen (kein Rückfall möglich)."""
    plan = _chain(ctx, ring0, ring0_kind, open_end, ctx.params.shells)
    n = int(plan.meta.get("shells", 0))
    if n <= 1:
        return plan
    errors = _chain_errors(ctx, plan)
    if not errors:
        return plan
    for k in range(n - 1, 0, -1):
        cand = _chain(ctx, ring0, ring0_kind, open_end, k)
        if not cand.segments or _chain_errors(ctx, cand):
            continue
        cand.meta["shells_dropped"] = {
            "from_shell": k,
            "count": ctx.params.shells - k,
            "reason": "regelfehler",
            "errors_before": errors,
            "hint": f"Mit {n} Schalen hat der Strang {errors} Regelfehler (M2/M5/M6, Schale zu schmal "
            f"oder zerfallend); gedruckt werden {k} Schale(n)",
        }
        return cand
    return plan


#: Regeln, deren Fehler einen Rückfall auf weniger Schalen auslösen
_FALLBACK_RULES = frozenset({"M1", "M2", "M5", "M6"})


def _chain_errors(ctx: IslandContext, plan: IslandPlan) -> int:
    """Anzahl harter Fehler (M1, M2, M5, M6) des Strangs, gemessen wie in `metrics.measure`."""
    from roboprint.patterns.metrics import measure_path  # metrics importiert plan → shells
    from roboprint.patterns.types import LayerPath

    if not plan.segments:
        return 0
    _, viol = measure_path(LayerPath(ctx.layer, 0, plan.segments), ctx.region, ctx.params, ctx.part_bounds)
    return sum(v.severity == "error" and v.rule in _FALLBACK_RULES for v in viol)


def _chain(
    ctx: IslandContext, ring0: np.ndarray | None, ring0_kind: str, open_end: bool, shells: int
) -> IslandPlan:
    """Schalenkette mit höchstens `shells` Schalen (Richtung außen → innen).

    `ring0` ersetzt den Außenring der Schale 0 (Outfill-Rolle), `ring0_kind` ist dann `outfill`.
    `open_end` (ein Infill folgt): Die innerste Schale endet vor ihrem Start, wie vor einem
    Schalenwechsel auf die gedachte nächste Bahn (offset (Schalen + 0,5)·w = Rand des Infill-
    Bands). Bei einer Schale folgt die S-Kurve auf diese Bahn (`close_single`); sie schließt die
    Wand am Ringanfang (S1: Viertelbogen R = 45 mm, 30,4 mm vom Ringstart; mit dem Ziel direkt
    neben der Eck-Naht wären es 38,8 mm, also 8,8 mm Durchgang, oder 25,4 mm an der M2-Grenze).
    Bei mehreren Schalen endet der Strang ℓ vor dem Start der innersten, ohne S-Kurve, und das
    Infill legt seinen Einlauf selbst (`ctx.entry`). Gründe: Ein geschlossener Einzelring lässt
    keinen Abgang ohne Überfahren des Ringanfangs zu (M2). Bei mehreren Schalen endete die
    innerste sonst mit der Spitze gegen die ankommende S-Kurve; jede Kehre mit Radius ≥ w/2 ins
    Band käme ihr auf < (1 − ε)·w nahe (S1: 24,4 mm bei R = 15 mm). Ohne Infill ändert sich nichts.
    Rückgabe: IslandPlan mit `meta = {seam, clearance_mm, fallback, transitions_mm, shells}`."""
    p = ctx.params
    mains: list[np.ndarray] = []
    extras: list[tuple[int, str, np.ndarray]] = []
    dropped: dict[str, Any] | None = None
    for s in range(shells):
        m, rest = _main_exterior(ctx.lanes, s)
        if s == 0 and ring0 is not None:
            m = np.asarray(ring0, float)
        if m is None:
            if s > 0:  # Offset-Ring leer: Schale passt nicht (Hinweis wie beim Restring)
                dropped = _dropped_note(s, p, None)
            break
        if s > 0 and Loop(m).length < MIN_RING_W * p.w:
            # Rückfall: Restring (z. B. in der Innenecke eines L-Querschnitts, wo der Offset nur
            # noch einen Punkt übrig lässt) ist nicht druckbar und ließe keinen Schalenwechsel zu
            dropped = _dropped_note(s, p, Loop(m).length)
            break
        mains.append(m)
        extras.extend((s, "inner" if s else "outer", r) for r in rest)
    if not mains:
        return IslandPlan([], meta={"empty": True})
    loops = [Loop(m) for m in mains]
    start, meta = choose_seam(loops[0], ctx.region, ctx.part_bounds, p)
    meta = {**meta, "shells": len(loops), "transitions_mm": []}
    if dropped is not None:
        meta["shells_dropped"] = dropped
    segs: list[Segment] = []
    # gedachte nächste Bahn: konzentrisch (Eckradius r − w; + 0,5 mm, damit die Tangente in der
    # Ecke bestimmt ist), sonst wie eine echte Schale gerundet (r)
    virtuals: list[Loop] = []
    for rad in dict.fromkeys((max(p.corner_radius - p.w, 0.0) + 0.5, p.corner_radius)) if open_end else ():
        ext = [r for kd, r in offset_ring(ctx.region, (len(loops) + 0.5) * p.w, rad) if kd == "exterior"]
        if ext:
            # auch eine kurze gedachte Bahn bleibt: Sie wird nie gedruckt und nie mit `clear_end`
            # gekürzt, sie gibt nur die Richtung der S-Kurve ins Infill vor (Infill passt oft noch)
            virtuals.append(Loop(max(ext, key=lambda r: abs(_area(r)))))
    virtual = virtuals[0] if virtuals else None
    single = None
    if len(loops) == 1 and virtual is not None:
        single = close_single(ctx, loops[0], start, virtuals)
        if single is None:
            # keine S-Kurve ins Infill-Band liegt in der Insel: Ring schließen, kein Abgang
            # (build_island lässt das Infill dann mit Hinweis entfallen)
            virtual = None
            meta["open_end_failed"] = (
                "Einzelring: keine S-Kurve ins Infill-Band liegt in der Insel (Insel zu kurz bzw. zu "
                "schmal für w); Ring geschlossen, Infill entfällt"
            )
    if len(loops) == 1 and virtual is None:
        pts = loops[0].sub(start, start)
        pts = _fine(pts, p, closed=True)
        segs.append(Segment(ring0_kind, 0, pts, closed=True, label="Schale 0"))
    head: np.ndarray | None = None
    for k, lp in enumerate(loops if len(loops) > 1 or virtual is not None else []):
        kind = ring0_kind if k == 0 else "inner"
        # Ende dieses Rings: frei von der ankommenden S-Kurve (head)
        t_end = start + lp.length if head is None else clear_end(lp, start, head, p.w)
        nxt = loops[k + 1] if k < len(loops) - 1 else virtual
        if nxt is not None:
            if nxt is virtual and len(loops) == 1:  # Einzelring: S-Kurve schließt die Wand
                assert single is not None
                t_cut, trans, ell, closed = single
                tb = start
                if not closed:
                    meta["open_wall"] = True  # Spalt zwischen S-Kurve und Ringanfang
            else:
                ell, trans, tb = lane_change(lp, nxt, start, p, min_ell=start + lp.length - t_end, avoid=head)
                t_cut = start - ell
            body = lp.sub(start, t_cut)
            meta["transitions_mm"].append(round(ell, 2))
        else:
            body = lp.sub(start, t_end)
            trans, tb = None, start
        pts = body if head is None else np.vstack([head, body[1:]])
        if nxt is not None and nxt is virtual and len(loops) == 1:  # Einzelring: Wand schließen
            pts = np.vstack([pts, trans[1:]])
        segs.append(Segment(kind, k, _fine(pts, p), label=f"Schale {k}"))
        head, start = trans, tb
    # Ausweichfall: weitere Teile und Löcher anhängen (siehe Modul-Docstring)
    holes = [(ln.shell, "hole", ln.ring) for ln in ctx.lanes if ln.kind == "hole" and ln.shell < len(loops)]
    for s, kind, r in extras + holes:
        lp = Loop(r)
        t = lp.project(segs[-1].end)
        segs.append(Segment(kind, s, _fine(lp.sub(t, t), p, closed=True), closed=True, label=f"Schale {s}"))
        meta.setdefault("appended", 0)
        meta["appended"] += 1
    return IslandPlan(segs, meta=meta)


def _build(ctx: IslandContext) -> IslandPlan:
    return shell_chain(ctx)


SHELLS = register(
    Pattern(
        name="schalen",
        role="full",
        label="Schalen ohne Infill",
        build=_build,
        description="Alle Schalen als ein Strang, Schalenwechsel als S-Kurve ohne Doppelmaterial, "
        "Naht im Eckbogen. Mit Schichtfolge alternate senkrechter Schichtwechsel.",
        family="schalen",
    )
)

__all__ = ["SHELLS", "island_band", "island_cavity", "lane_change", "shell_chain", "shell_lanes"]
