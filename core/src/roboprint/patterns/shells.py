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

Löcher in einer Insel (Schacht im Querschnitt) und zerfallende Schalen (Hals schmaler als w)
werden hier nur angehängt (gerader Verbinder zum nächsten Punkt); M1/M2/M5 melden das. Die
richtige Behandlung ist Aufgabe der Familie „Topologie“.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from roboprint.patterns.geometry import (
    Loop,
    biarc,
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


def shell_chain(ctx: IslandContext, ring0: np.ndarray | None = None, ring0_kind: str = "outer") -> IslandPlan:
    """Alle Schalen der Insel als ein Strang (Richtung außen → innen).

    `ring0` ersetzt den Außenring der Schale 0 (Outfill-Rolle), `ring0_kind` ist dann `outfill`.
    Rückgabe: IslandPlan mit `meta = {seam, clearance_mm, fallback, transitions_mm, shells}`."""
    p = ctx.params
    mains: list[np.ndarray] = []
    extras: list[tuple[int, str, np.ndarray]] = []
    for s in range(p.shells):
        m, rest = _main_exterior(ctx.lanes, s)
        if s == 0 and ring0 is not None:
            m = np.asarray(ring0, float)
        if m is None:
            break
        mains.append(m)
        extras.extend((s, "inner" if s else "outer", r) for r in rest)
    if not mains:
        return IslandPlan([], meta={"empty": True})
    loops = [Loop(m) for m in mains]
    start, meta = choose_seam(loops[0], ctx.region, ctx.part_bounds, p)
    meta = {**meta, "shells": len(loops), "transitions_mm": []}
    segs: list[Segment] = []
    if len(loops) == 1:
        pts = loops[0].sub(start, start)
        pts = _fine(pts, p, closed=True)
        segs.append(Segment(ring0_kind, 0, pts, closed=True, label="Schale 0"))
    head: np.ndarray | None = None
    for k, lp in enumerate(loops if len(loops) > 1 else []):
        kind = ring0_kind if k == 0 else "inner"
        # Ende dieses Rings: frei von der ankommenden S-Kurve (head)
        t_end = start + lp.length if head is None else clear_end(lp, start, head, p.w)
        if k < len(loops) - 1:
            ell, trans, tb = lane_change(
                lp, loops[k + 1], start, p, min_ell=start + lp.length - t_end, avoid=head
            )
            body = lp.sub(start, start - ell)
            meta["transitions_mm"].append(round(ell, 2))
        else:
            body = lp.sub(start, t_end)
            trans, tb = None, start
        pts = body if head is None else np.vstack([head, body[1:]])
        segs.append(Segment(kind, k, _fine(pts, p), label=f"Schale {k}"))
        head, start = trans, tb
    # Ausweichfall: weitere Teile und Löcher anhängen (siehe Modul-Docstring)
    holes = [(ln.shell, "hole", ln.ring) for ln in ctx.lanes if ln.kind == "hole"]
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
