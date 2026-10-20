"""Betriebsart „allgemein“ der Familie Topologie (Hilfsmodul): Schalenkette mit geprüfter Naht.

Gleicher Ablauf wie das Grundmuster (`shells.shell_chain`: Schalen als ein Strang, Wechsel als
S-Kurve), aber
- die Schalenringe werden mit schrittweise kleinerem Eckradius gerundet (`island_lanes`), statt bei
  einem Topologiewechsel scharfkantig zu bleiben;
- die Naht wird aus mehreren Kandidaten mit dem größten Freiabstand zu Außen- und Stoßflächen
  gewählt, und jeder Kandidat wird gebaut und mit `metrics.measure_path` geprüft (M2, M5, M6);
- gelingt es mit allen Schalen nicht fehlerfrei (Hals schmaler als 2·Schalen·w), wird die
  Schalenzahl der Insel verringert.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from shapely.geometry.polygon import orient

from roboprint.patterns.geometry import QUAD_SEGS, Loop, densify, polygons, resample_curve
from roboprint.patterns.layout import face_clearance
from roboprint.patterns.metrics import measure_path
from roboprint.patterns.shells import clear_end, lane_change
from roboprint.patterns.types import IslandContext, IslandPlan, Lane, LayerPath, PatternParams, Segment

#: höchstens so viele Nahtkandidaten werden gebaut und geprüft
MAX_SEAM_CANDIDATES = 12


def _chain_from(ctx: IslandContext, start: float, loops: list[Loop], extras: list) -> IslandPlan:
    """Wie `shells.shell_chain`, aber mit vorgegebener Naht (Bogenlänge auf Spur 0)."""
    p = ctx.params
    segs: list[Segment] = []
    trans_l: list[float] = []
    if len(loops) == 1:
        pts = resample_curve(loops[0].sub(start, start), p.step_mm, p.chord_tol_mm, closed=True)
        segs.append(Segment("outer", 0, pts, closed=True, label="Schale 0"))
    head: np.ndarray | None = None
    for k, lp in enumerate(loops if len(loops) > 1 else []):
        kind = "outer" if k == 0 else "inner"
        t_end = start + lp.length if head is None else clear_end(lp, start, head, p.w)
        if k < len(loops) - 1:
            ell, trans, tb = lane_change(lp, loops[k + 1], start, p, min_ell=start + lp.length - t_end)
            body = lp.sub(start, start - ell)
            trans_l.append(round(ell, 2))
        else:
            body = lp.sub(start, t_end)
            trans, tb = None, start
        pts = body if head is None else np.vstack([head, body[1:]])
        segs.append(Segment(kind, k, resample_curve(pts, p.step_mm, p.chord_tol_mm), label=f"Schale {k}"))
        head, start = trans, tb
    for s, kind, r in extras:
        lp = Loop(r)
        t = lp.project(segs[-1].end)
        pts = resample_curve(lp.sub(t, t), p.step_mm, p.chord_tol_mm, closed=True)
        segs.append(Segment(kind, s, pts, closed=True, label=f"Schale {s}"))
    return IslandPlan(segs, meta={"transitions_mm": trans_l, "appended": len(extras)})


def _seam_candidates(loop: Loop, ctx: IslandContext) -> list[float]:
    """Bogenlängen der Nahtkandidaten: größter Freiabstand zuerst, Gleichstand nächst der Ecke
    `seam_corner`, Kandidaten mindestens 2·w auseinander."""
    p = ctx.params
    cand = densify(loop.pts, 4.0)[:-1]
    clr = face_clearance(cand, ctx.region, ctx.part_bounds, p.w)
    clr = np.where(np.isfinite(clr), clr, 1e9)
    x0, y0, x1, y1 = ctx.part_bounds
    corner = np.array([x0 if p.seam_corner[0] < 0 else x1, y0 if p.seam_corner[1] < 0 else y1])
    d = np.linalg.norm(cand - corner, axis=1)
    order = np.lexsort((d, -np.round(clr / 0.5)))
    chosen: list[np.ndarray] = []
    out: list[float] = []
    for i in order:
        q = cand[i]
        if any(np.linalg.norm(q - c) < 2.0 * p.w for c in chosen):
            continue
        chosen.append(q)
        out.append(loop.project(q))
        if len(out) >= MAX_SEAM_CANDIDATES:
            break
    return out


def _signature(geom: Any) -> list[int]:
    return [len(q.interiors) for q in polygons(geom)]


def island_lanes(region: Any, params: PatternParams, shells: int) -> tuple[Lane, ...]:
    """Schalenringe wie `shells.shell_lanes`, aber mit schrittweiser Eckenrundung: Ändert die
    Rundung mit `corner_radius` die Topologie (z. B. hinter einer tiefen Kerbe), versucht der Kern
    die ungerundete Fläche (scharfe Ecken, M6-Fehler); hier gilt der größte Radius aus
    (r, ¾·r, w/2), der die Topologie erhält. Ecken mit w/2 sind druckbar (M6 hart), nur das Ziel
    r ≥ w wird verfehlt."""
    w, rc = params.w, params.corner_radius
    out: list[Lane] = []
    for s in range(shells):
        o = (s + 0.5) * w
        base = region.buffer(-o, join_style="round", quad_segs=QUAD_SEGS)
        g = base
        for r in (rc, 0.75 * rc, w / 2.0):
            if r <= 0:
                break
            cand = region.buffer(-(o + r), join_style="round", quad_segs=QUAD_SEGS).buffer(
                r, join_style="round", quad_segs=QUAD_SEGS
            )
            if _signature(cand) == _signature(base):
                g = cand
                break
        if g.is_empty:
            break
        for sub in polygons(g):
            sub = orient(sub, sign=1.0)
            out.append(Lane(s, "exterior", np.asarray(sub.exterior.coords, float)))
            out.extend(Lane(s, "hole", np.asarray(h.coords, float)) for h in sub.interiors)
    return tuple(out)


def _chain_candidates(
    ctx: IslandContext, shells: int
) -> tuple[int, int, IslandPlan, float, list[float], Loop] | None:
    from roboprint.patterns.shells import _main_exterior  # Hilfsfunktion des Kerns

    p = ctx.params
    lanes = island_lanes(ctx.region, p, shells)
    mains, extras = [], []
    for s in range(shells):
        m, rest = _main_exterior(lanes, s)
        if m is None:
            break
        mains.append(m)
        extras.extend((s, "inner" if s else "outer", r) for r in rest)
    extras.extend((ln.shell, "hole", ln.ring) for ln in lanes if ln.kind == "hole")
    if not mains:
        return None
    loops = [Loop(m) for m in mains]
    cands = _seam_candidates(loops[0], ctx)
    if not ctx.param("seam_check"):
        cands = cands[:1]
    best: tuple[int, int, IslandPlan, float] | None = None
    for k, s in enumerate(cands):
        plan = _chain_from(ctx, s, loops, extras)
        if not plan.segments:
            continue
        lp = LayerPath(ctx.layer, ctx.island, plan.segments)
        _, viol = measure_path(lp, ctx.region, p, ctx.part_bounds)
        n_err = sum(v.severity == "error" for v in viol)
        n_warn = len(viol) - n_err
        if best is None or (n_err, n_warn) < (best[0], best[1]):
            best = (n_err, n_warn, plan, s)
        # fehlerfrei und ohne Warnung, oder fehlerfrei nach drei Kandidaten: genug gesucht;
        # nach vier Kandidaten mit Fehlern liegt es nicht an der Naht (z. B. Hals, weniger Schalen)
        if best[0] == 0 and (best[1] == 0 or k >= 2):
            break
        if best[0] > 0 and k >= 3:
            break
    if best is None:
        return None
    return (*best, cands, loops[0])


def best_chain(ctx: IslandContext) -> IslandPlan:
    """Schalen der Insel als ein Strang mit geprüfter Naht (Betriebsart „allgemein“).

    Hat die Insel einen Hals, der schmaler ist als die Schalen (z. B. hinter einer tiefen Kerbe:
    Restdicke < 2·Schalen·w), entsteht mit allen Schalen Doppelmaterial (M2). Dann wird die
    Schalenzahl für diese Insel so weit verringert, bis der Strang fehlerfrei ist (`shells_used`)."""
    p = ctx.params
    res = None
    for shells in range(p.shells, 0, -1):
        r = _chain_candidates(ctx, shells)
        if r is None:
            continue
        if res is None or r[0] < res[0][0]:
            res = (r, shells)
        if r[0] == 0:
            break
    if res is None:
        return IslandPlan([], meta={"topology": {"mode": "allgemein", "empty": True}})
    (n_err, _, plan, s, cands, loop0), shells = res
    seam = loop0.point(s)
    clr = float(face_clearance(seam[None, :], ctx.region, ctx.part_bounds, p.w)[0])
    plan.meta = {
        "topology": {
            "mode": "allgemein",
            "seam": [round(float(seam[0]), 3), round(float(seam[1]), 3)],
            "seam_clearance_mm": None if not math.isfinite(clr) else round(clr, 3),
            "seam_candidate": cands.index(s),
            "shells_used": shells,
            "errors": n_err,
            **plan.meta,
        }
    }
    return plan
