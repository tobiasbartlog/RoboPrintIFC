"""Platzierungssuche (SPEC §5.4/3): theta in {0, 90, 180, 270} Grad, (x, y) auf einem 25-mm-Raster
innerhalb der Arbeitsflaeche, ohne Ueberschneidung mit der Roboterbasis, Ziel maximales d_min.

Schnell in zwei Stufen ueber wenige Probewegpunkte (Ecken des Aussenrings in unterster,
mittlerer und oberster Schicht): Je Probe zaehlt der beste Knoten (max. Vorauswahl-Abstand
ueber psi und Zweige), je Kandidat die schlechteste Probe. Erst ein 100-mm-Raster, dann das
25-mm-Raster um die besten Kandidaten. Die volle Planung (und damit das echte d_min) laeuft
danach fuer die besten Kandidaten in `plan_part`; `decompose` nutzt `rank_placements` ebenso.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import MultiPoint, Polygon, box

from roboprint import frames
from roboprint.assets import REPO_ROOT, load_workstation

from .backend import SphereWorld, can_fork_pool, table_box
from .kin import Kin
from .params import PlannerParams

UNREACHABLE_SCORE = -1.0e3
_DEBUG = False


@dataclass(frozen=True)
class Candidate:
    placement: frames.Placement
    score: float  # min ueber Proben des besten Vorauswahl-Abstands (mm); < -999: unerreichbar


@lru_cache(maxsize=2)
def base_footprint_S(root: Path = REPO_ROOT) -> Polygon:  # noqa: N802
    """Grundriss der Roboterbasis (konvexe Huelle von base_link) in S."""
    import trimesh

    from .backend import _urdf_collision_meshes

    ws = load_workstation(root)
    pts = np.vstack(
        [trimesh.load(p, force="mesh").vertices for p in _urdf_collision_meshes(root)["base_link"]]
    )
    pts_S = frames.transform_points(frames.invert(frames.T_BS(ws)), pts)  # noqa: N806
    return MultiPoint(pts_S[:, :2]).convex_hull


@lru_cache(maxsize=2)
def work_surface_S(root: Path = REPO_ROOT) -> Polygon:  # noqa: N802
    """Tischplatte als Rechteck in S."""
    ws = load_workstation(root)
    lo, hi = table_box(root)
    T_SW = frames.T_SW(ws)  # noqa: N806
    c = frames.transform_points(T_SW, np.array([[lo[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]]]))
    return box(min(c[:, 0]), min(c[:, 1]), max(c[:, 0]), max(c[:, 1]))


def footprint_ok(foot_P: Polygon, pl: frames.Placement, root: Path = REPO_ROOT) -> bool:  # noqa: N803
    T = frames.T_SP(pl)  # noqa: N806
    pts = np.asarray(foot_P.exterior.coords)
    q = (T[:2, :2] @ pts.T).T + T[:2, 3]
    poly = Polygon(q)
    return work_surface_S(root).contains(poly) and not poly.intersects(base_footprint_S(root))


def probe_points(part_mesh_P: Any, layer_height_mm: float, full: bool = True) -> list[tuple[np.ndarray, int]]:  # noqa: N803
    """Probewegpunkte in P mit Schicht: Ecken (und mit `full` Kantenmitten in x) der Bounding-Box
    auf TCP-Hoehe (L+1)*h der untersten, (mittleren) und obersten Schicht, um 15 mm eingerueckt."""
    lo, hi = np.asarray(part_mesh_P.bounds, float)
    n = max(1, int(round(hi[2] / layer_height_mm)))
    inset = 15.0
    xs = [lo[0] + inset, hi[0] - inset] + ([0.5 * (lo[0] + hi[0])] if full else [])
    ys = (lo[1] + inset, hi[1] - inset)
    layers = sorted({0, n // 2, n - 1}) if full else sorted({0, n - 1})
    # TCP auf Travel-Hoehe (+30 mm): sonst bestimmt der feste Abstand Duesenspitze <-> Tisch in
    # Schicht 0 (~11 mm) den Score jeder Platzierung.
    return [(np.array([x, y, (L + 1) * layer_height_mm + 30.0]), L) for L in layers for x in xs for y in ys]


def _scores(
    kin: Kin,
    world: SphereWorld,
    T_WPs: list[np.ndarray],
    probes,
    psi: np.ndarray,
    self_collision: bool,  # noqa: N803
) -> np.ndarray:
    """Score je Platzierung: min ueber Proben des max. Vorauswahl-Abstands ueber (psi, Zweig)."""
    c, n, m = len(T_WPs), len(probes), len(psi)
    if c == 0:
        return np.zeros(0)
    Pp = np.array([p for p, _ in probes])  # noqa: N806
    layers = np.array([L for _, L in probes])
    P = np.concatenate([frames.transform_points(T, Pp) for T in T_WPs])  # (c*n,3)  # noqa: N806
    Q, ok = kin.ik(np.repeat(P, m, 0), np.tile(psi, c * n))  # noqa: N806
    ok = ok.reshape(c, n, m * 8)
    Q = Q.reshape(c, n, m * 8, 6)  # noqa: N806
    reach = ok.any(axis=2).all(axis=1)
    sel = ok & reach[:, None, None]
    d = np.full(ok.shape, -np.inf)
    if sel.any():
        k = np.broadcast_to(layers[None, :, None], ok.shape)[sel]
        T = np.broadcast_to(np.asarray(T_WPs)[:, None, None], (*ok.shape, 4, 4))[sel]  # noqa: N806
        d[sel] = world.d_batch_placed(Q[sel], k, T, self_collision=self_collision)
    sc = d.max(axis=2).min(axis=1)
    return np.where(reach, sc, UNREACHABLE_SCORE)


_POOL_ARGS: Any = None


def _scores_worker(T_WPs: list[np.ndarray]) -> np.ndarray:  # noqa: N803
    kin, world, probes, psi, self_collision = _POOL_ARGS
    return _scores(kin, world, T_WPs, probes, psi, self_collision)


def _scores_parallel(kin, world, T_WPs, probes, psi, self_collision, procs: int) -> np.ndarray:  # noqa: N803
    """`_scores` auf `procs` Prozesse verteilt (fork); jede Platzierung wird fuer sich bewertet,
    das Ergebnis ist dasselbe wie seriell."""
    import multiprocessing as mp

    global _POOL_ARGS
    if procs <= 1 or len(T_WPs) < 4 * procs or not can_fork_pool():
        return _scores(kin, world, T_WPs, probes, psi, self_collision)
    parts = [[T_WPs[i] for i in ix] for ix in np.array_split(np.arange(len(T_WPs)), 2 * procs)]
    _POOL_ARGS = (kin, world, probes, psi, self_collision)
    try:
        with mp.get_context("fork").Pool(procs) as pool:
            res = pool.map(_scores_worker, parts)
    finally:
        _POOL_ARGS = None
    return np.concatenate(res)


def rank_placements(
    part_mesh_P: Any,  # noqa: N803
    kin: Kin,
    params: PlannerParams,
    root: Path = REPO_ROOT,
    top: int = 4,
    yaws_deg: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0),
    procs: int = 1,
) -> list[Candidate]:
    """Kandidaten-Platzierungen, bestes zuerst (Score absteigend); `procs` > 1 bewertet die
    Kandidaten in mehreren Prozessen (gleiches Ergebnis). Ergebnisse werden je Prozess fuer
    gleiche Geometrie und Parameter gemerkt (Zerlegung: viele gleich grosse Module)."""
    import hashlib

    h = hashlib.sha1(np.ascontiguousarray(part_mesh_P.vertices, dtype=float).tobytes())
    h.update(np.ascontiguousarray(part_mesh_P.faces, dtype=np.int64).tobytes())
    key = (h.hexdigest(), params, str(root), top, tuple(yaws_deg))
    hit = _RANK_CACHE.get(key)
    if hit is None:
        hit = _rank_placements(part_mesh_P, kin, params, root, top, yaws_deg, procs)
        if len(_RANK_CACHE) >= 64:
            _RANK_CACHE.pop(next(iter(_RANK_CACHE)))
        _RANK_CACHE[key] = hit
    return list(hit)


_RANK_CACHE: dict[tuple, list[Candidate]] = {}


def _rank_placements(part_mesh_P, kin, params, root, top, yaws_deg, procs) -> list[Candidate]:  # noqa: N803
    ws = load_workstation(root)
    foot = MultiPoint(np.asarray(part_mesh_P.vertices)[:, :2]).convex_hull
    world = SphereWorld(part_mesh_P, np.eye(4), params.layer_height_mm, root, params.r_free_mm)
    world.skip_tip = True
    surf = work_surface_S(root).bounds

    def evaluate(cands: list[frames.Placement], probes, psi, self_collision) -> list[Candidate]:
        pls, seen = [], set()
        Pp = np.array([p for p, _ in probes])  # noqa: N806
        for pl in cands:
            if not footprint_ok(foot, pl, root):
                continue
            # symmetrische Teile: gleiche Probenmenge in W nur einmal bewerten
            key = tuple(sorted(map(tuple, np.round(frames.transform_points(frames.T_SP(pl), Pp), 1))))
            if key in seen:
                continue
            seen.add(key)
            pls.append(pl)
        T_WPs = [frames.T_WP(ws, pl) for pl in pls]  # noqa: N806
        sc = _scores_parallel(kin, world, T_WPs, probes, psi, self_collision, procs)
        return [Candidate(pl, float(v)) for pl, v in zip(pls, sc, strict=True)]

    def grid(step: float) -> list[frames.Placement]:
        xs = np.arange(np.ceil(surf[0] / step) * step, surf[2] + 1e-9, step)
        ys = np.arange(np.ceil(surf[1] / step) * step, surf[3] + 1e-9, step)
        return [
            frames.Placement(float(x), float(y), float(np.radians(t)))
            for t in yaws_deg
            for x in xs
            for y in ys
        ]

    import time

    t0 = time.perf_counter()
    coarse = evaluate(
        grid(100.0), probe_points(part_mesh_P, params.layer_height_mm, False), params.psi_grid[::6], False
    )
    coarse.sort(key=lambda c: -c.score)
    seeds = distinct([c for c in coarse if c.score > UNREACHABLE_SCORE], top, 150.0)
    pls: dict[tuple[float, float, float], frames.Placement] = {}
    for c in seeds:
        for dx in (-50.0, -25.0, 0.0, 25.0, 50.0):
            for dy in (-50.0, -25.0, 0.0, 25.0, 50.0):
                key = (c.placement.x_mm + dx, c.placement.y_mm + dy, c.placement.yaw_rad)
                pls.setdefault(key, frames.Placement(*key))
    t1 = time.perf_counter()
    fine = evaluate(
        list(pls.values()),
        probe_points(part_mesh_P, params.layer_height_mm, True),
        params.psi_grid[::3],
        False,
    )
    res = sorted(fine, key=lambda c: -c.score)
    if _DEBUG:
        t2 = time.perf_counter()
        print(f"placement: coarse {len(coarse)} {t1 - t0:.1f}s, fine {len(fine)} {t2 - t1:.1f}s")
    return res or coarse


def find_placement(
    part_mesh_P: Any,  # noqa: N803
    params: PlannerParams | None = None,
    root: Path = REPO_ROOT,
    top: int = 4,
) -> list[Candidate]:
    """Platzierungssuche fuer ein Teil (Frame P), bestes zuerst; fuer `decompose` (A2.2) und
    `plan_part`. Die volle Planung der besten Kandidaten macht `plan_part` (echtes d_min)."""
    from roboprint.assets import load_tool

    kin = Kin(load_workstation(root), load_tool(root))
    return rank_placements(part_mesh_P, kin, params or PlannerParams(), root, top)


def distinct(cands: list[Candidate], n: int, min_dist_mm: float = 100.0) -> list[Candidate]:
    """Die besten n Kandidaten, untereinander verschieden (anderes theta oder >= min_dist_mm)."""
    out: list[Candidate] = []
    for c in cands:
        p = c.placement
        if all(
            abs(p.yaw_rad - o.placement.yaw_rad) > 1e-6
            or np.hypot(p.x_mm - o.placement.x_mm, p.y_mm - o.placement.y_mm) >= min_dist_mm
            for o in out
        ):
            out.append(c)
        if len(out) >= n:
            break
    return out
