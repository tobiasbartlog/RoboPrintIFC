"""Druckplatz (SPEC §5.4/3, Nutzerentscheidung 20.10.2026): Jedes Modul steht am Druckplatz aus den
Parametern (`spot_x_mm`, `spot_y_mm`, Rastpunkte aus `params.spot_grid()`), Gier 0, also mit der langen
Seite zum Roboter. Es gibt keine Suche mehr: Die fruehere Suche ueber den ganzen Tisch bewertete fast
jede Lage gleich (Abstaende ueber `_CULL_MM` = 50 mm sind nur geschaetzt) und landete zufaellig am Rand.

`placement_score` ist die schnelle Vorpruefung fuer die H*-Bisektion: wenige Probewegpunkte (Ecken des
Aussenrings in unterster, mittlerer und oberster Schicht), je Probe der beste Knoten (max.
Vorauswahl-Abstand ueber psi und Zweige), Ergebnis die schlechteste Probe.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import MultiPoint, Polygon, box

from roboprint import frames
from roboprint.assets import REPO_ROOT, load_workstation

from .backend import SphereWorld, table_box
from .kin import Kin
from .params import PlannerParams

UNREACHABLE_SCORE = -1.0e3


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


def spot_placement(params: PlannerParams) -> frames.Placement:
    """Druckplatz aus den Parametern: (x, y) in S, Gier 0."""
    return frames.Placement(float(params.spot_x_mm), float(params.spot_y_mm), 0.0)


def placement_score(
    part_mesh_P: Any,  # noqa: N803
    kin: Kin,
    params: PlannerParams,
    placement: frames.Placement,
    root: Path = REPO_ROOT,
) -> float | None:
    """Vorauswahl-Abstand des Teils an `placement` (mm), `UNREACHABLE_SCORE`, wenn eine Probe
    unerreichbar ist, None, wenn der Grundriss nicht auf die Arbeitsflaeche passt oder die
    Roboterbasis schneidet."""
    foot = MultiPoint(np.asarray(part_mesh_P.vertices)[:, :2]).convex_hull
    if not footprint_ok(foot, placement, root):
        return None
    world = SphereWorld(part_mesh_P, np.eye(4), params.layer_height_mm, root, params.r_free_mm)
    world.skip_tip = True
    probes = probe_points(part_mesh_P, params.layer_height_mm, True)
    T_WP = frames.T_WP(load_workstation(root), placement)  # noqa: N806
    return float(_scores(kin, world, [T_WP], probes, params.psi_grid[::3], False)[0])
