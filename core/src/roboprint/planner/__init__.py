"""Ladder-Graph ueber (Zweig x psi x tau) je Wegpunkt, Travel-Planung, dichte Gelenktrajektorie.

Schnittstelle::

    plan_part(part_mesh_P, part_id, params, mode=..., placement=None, root=...) -> PartPlan
    scan_height(part_mesh_P, part_id, params) -> PartPlan          # Hoehensuche, `path.layers_ok`
    truncate_plan(plan, n_layers, params) -> PartPlan              # Plan der unteren Schichten

Module: `graph` (Knoten, Kanten, Viterbi), `plan` (Ringe, Travel, Pruefung), `result` (Status,
Ursache, Praefix), `densify` (movel/movej-Abtastung), `placement` (Druckplatz), `backend`
(Kollisions-Naht, Kugel-Double), `kin` (Posen mit psi), `params` (SPEC §10).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from roboprint import frames
from roboprint.assets import REPO_ROOT, load_tool, load_workstation
from roboprint.slicer import SlicedPart, SliceParams, slice_part

from .backend import CollisionBackend, SphereWorld, make_world
from .kin import Kin
from .params import PlannerParams, from_overrides
from .placement import footprint_ok, placement_score, spot_placement
from .plan import PartPlanner, PlannedPath, RingTask, truncate

Progress = Callable[[float, str], None]


@dataclass
class PartPlan:
    part_id: str
    placement: frames.Placement
    T_WP: np.ndarray  # noqa: N815
    sliced: SlicedPart
    path: PlannedPath
    tried: list[dict[str, Any]] = field(default_factory=list)
    timings_s: dict[str, float] = field(default_factory=dict)


def slice_params(params: PlannerParams) -> SliceParams:
    return SliceParams(
        params.layer_height_mm, params.bead_width_mm, params.shells, params.step_mm, params.approach_mm
    )


def ring_tasks(sliced: SlicedPart, T_WP: np.ndarray) -> list[RingTask]:  # noqa: N803
    return [RingTask(i, r.layer, frames.transform_points(T_WP, r.points)) for i, r in enumerate(sliced.rings)]


def _setup(part_mesh_P, sliced, placement, params, root, world_factory):  # noqa: N803
    ws, tool = load_workstation(root), load_tool(root)
    T_WP = frames.T_WP(ws, placement)  # noqa: N806
    final = world_factory(part_mesh_P, T_WP, params.layer_height_mm, root, params.r_free_mm)
    screen = (
        final
        if isinstance(final, SphereWorld)
        else SphereWorld(part_mesh_P, T_WP, params.layer_height_mm, root, params.r_free_mm)
    )
    height = float(np.asarray(part_mesh_P.bounds)[1][2])
    return T_WP, final, screen, height, Kin(ws, tool), ring_tasks(sliced, T_WP)


def _needs_replan(path: PlannedPath, collision_aware: bool, final: Any, screen: Any) -> bool:
    return collision_aware and not path.feasible and final is not screen


def plan_at(
    part_mesh_P: Any,  # noqa: N803
    sliced: SlicedPart,
    placement: frames.Placement,
    params: PlannerParams,
    collision_aware: bool = True,
    root: Path = REPO_ROOT,
    world_factory: Callable[..., Any] = make_world,
    procs: int = 1,
    replan: bool = True,
) -> tuple[np.ndarray, PlannedPath]:
    """Plant ein Teil an fester Platzierung; liefert T_WP und den geprueften Pfad.

    Geplant wird mit dem schnellen Kugel-Double, die Abschlusspruefung jedes Samples nimmt die
    echte Welt. Scheitert das, plant `replan` mit der echten Welt nach (`replan_at`)."""
    T_WP, final, screen, height, kin, tasks = _setup(  # noqa: N806
        part_mesh_P, sliced, placement, params, root, world_factory
    )
    path = PartPlanner(kin, tasks, T_WP, params, screen, screen, collision_aware, height, final, procs).run()
    if replan and _needs_replan(path, collision_aware, final, screen):
        path = replan_at(part_mesh_P, sliced, placement, params, path, root, world_factory, procs)
    return T_WP, path


def replan_at(
    part_mesh_P: Any,  # noqa: N803
    sliced: SlicedPart,
    placement: frames.Placement,
    params: PlannerParams,
    first: PlannedPath,
    root: Path = REPO_ROOT,
    world_factory: Callable[..., Any] = make_world,
    procs: int = 1,
) -> PlannedPath:
    """Nachplanung: die echte Welt entscheidet auch waehrend der Planung (langsam, selten).
    `first` ist der gescheiterte Double-Plan derselben Platzierung (Zeiten werden addiert)."""
    T_WP, final, screen, height, kin, tasks = _setup(  # noqa: N806
        part_mesh_P, sliced, placement, params, root, world_factory
    )
    if final is screen:
        return first
    path = PartPlanner(kin, tasks, T_WP, params, final, screen, True, height, final, procs).run()
    t = first.timings_s
    path.timings_s = {k: path.timings_s.get(k, 0.0) + t.get(k, 0.0) for k in set(t) | set(path.timings_s)}
    path.timings_s["replan"] = 1.0
    return path


def _spot(part_mesh_P: Any, part_id: str, params: PlannerParams, root: Path) -> frames.Placement:  # noqa: N803
    """Druckplatz aus den Parametern; ValueError, wenn das Teil dort nicht auf die Arbeitsflaeche
    passt oder die Roboterbasis schneidet."""
    from shapely.geometry import MultiPoint

    pl = spot_placement(params)
    if not footprint_ok(MultiPoint(np.asarray(part_mesh_P.vertices)[:, :2]).convex_hull, pl, root):
        raise ValueError(
            f"Teil {part_id} passt am Druckplatz ({pl.x_mm:g}, {pl.y_mm:g}) mm nicht auf die Arbeitsflaeche"
        )
    return pl


def _tried(pl: frames.Placement, path: PlannedPath, **extra: Any) -> dict[str, Any]:
    return {"x_mm": pl.x_mm, "y_mm": pl.y_mm, "yaw_deg": float(np.degrees(pl.yaw_rad)),
            "feasible": path.feasible, "d_min_mm": path.d_min_mm, **extra}  # fmt: skip


def plan_part(
    part_mesh_P: Any,  # noqa: N803
    part_id: str,
    params: PlannerParams,
    mode: str = "collision_aware",
    placement: frames.Placement | None = None,
    root: Path = REPO_ROOT,
    world_factory: Callable[..., Any] = make_world,
    progress: Progress | None = None,
    procs: int = 1,
) -> PartPlan:
    """Schneidet und plant das Teil an `placement`, ohne Angabe am Druckplatz der Parameter.

    Zuerst mit dem schnellen Double (Abschlusspruefung mit der echten Welt). Ist das nicht machbar,
    plant die teure Nachplanung mit der echten Welt nach; es gilt der machbare Plan, sonst der mit
    dem groesseren d_min.
    """
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    sliced = slice_part(part_mesh_P, slice_params(params))
    timings["slice"] = time.perf_counter() - t0
    aware = mode == "collision_aware"
    pl = placement if placement is not None else _spot(part_mesh_P, part_id, params, root)
    t = time.perf_counter()
    if progress:
        progress(0.0, "Planung")
    T_WP, path = plan_at(  # noqa: N806
        part_mesh_P, sliced, pl, params, aware, root, world_factory, procs, replan=False
    )
    tried = [_tried(pl, path)]
    if aware and not path.feasible:
        if progress:
            progress(0.5, "Nachplanung")
        path2 = replan_at(part_mesh_P, sliced, pl, params, path, root, world_factory, procs)
        if path2 is not path:
            tried.append(_tried(pl, path2))
            if path2.feasible or (path2.d_min_mm or -1e9) > (path.d_min_mm or -1e9):
                path = path2
    timings["plan"] = time.perf_counter() - t
    for k, v in path.timings_s.items():
        timings[f"plan_{k}"] = v
    return PartPlan(part_id, pl, T_WP, sliced, path, tried, timings)


def scan_height(
    part_mesh_P: Any,  # noqa: N803
    part_id: str,
    params: PlannerParams,
    placement: frames.Placement | None = None,
    root: Path = REPO_ROOT,
    world_factory: Callable[..., Any] = make_world,
    procs: int = 1,
) -> PartPlan:
    """Hoehensuche: Wie viele Schichten des Teils gehen von unten gezaehlt?

    Ob Schicht k geht, haengt nur von den Schichten darunter ab, und ein niedrigeres Prisma besteht
    aus den unteren Schichten des hoeheren (gleiche Ringe, gleicher Druckstand). Deshalb wird das Teil
    am Druckplatz (oder an `placement`) einmal von unten geplant, jeder Ring sofort mit der echten Welt
    geprueft, und die Planung stoppt an der ersten Schicht, die nicht geht (`path.layers_ok`).
    `truncate_plan` liefert daraus exakt den Plan jedes niedrigeren Teils.
    """
    t0 = time.perf_counter()
    sliced = slice_part(part_mesh_P, slice_params(params))
    pl = placement if placement is not None else _spot(part_mesh_P, part_id, params, root)
    T_WP, final, screen, height, kin, tasks = _setup(  # noqa: N806
        part_mesh_P, sliced, pl, params, root, world_factory
    )
    path = PartPlanner(
        kin, tasks, T_WP, params, screen, screen, True, height, final, procs, stop_at_bad=True
    ).run()
    n = int(path.layers_ok or 0)
    cut = truncate(path, _prefix_len(path, sliced, n), params) if n else None
    tried = [_tried(pl, path, layers_ok=n, d_min_mm=None if cut is None else cut.d_min_mm)]
    return PartPlan(part_id, pl, T_WP, sliced, path, tried, {"scan": time.perf_counter() - t0})


def _prefix_len(path: PlannedPath, sliced: SlicedPart, n_layers: int) -> int:
    """Anzahl Samples bis einschliesslich des Abhebens nach Schicht `n_layers` - 1."""
    r_cut = sum(1 for r in sliced.rings if r.layer < n_layers)
    if any(r.layer >= n_layers for r in sliced.rings[:r_cut]):
        raise ValueError("Ringe sind nicht nach Schichten geordnet")
    return int(np.searchsorted(np.asarray(path.ring), r_cut))


def truncate_plan(pp: PartPlan, n_layers: int, params: PlannerParams) -> PartPlan:
    """Plan der unteren `n_layers` Schichten eines Plans aus `scan_height` (gleiche Platzierung)."""
    r_cut = sum(1 for r in pp.sliced.rings if r.layer < n_layers)
    sliced = SlicedPart(pp.sliced.layer_height_mm, pp.sliced.bead_width_mm, n_layers, pp.sliced.rings[:r_cut])
    path = truncate(pp.path, _prefix_len(pp.path, pp.sliced, n_layers), params)
    return replace(pp, sliced=sliced, path=path)


__all__ = [
    "CollisionBackend",
    "PartPlan",
    "PlannedPath",
    "PlannerParams",
    "SphereWorld",
    "from_overrides",
    "make_world",
    "plan_at",
    "plan_part",
    "replan_at",
    "placement_score",
    "scan_height",
    "slice_params",
    "spot_placement",
    "truncate_plan",
]
