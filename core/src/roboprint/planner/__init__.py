"""Ladder-Graph ueber (Zweig x psi x tau) je Wegpunkt, Travel-Planung, dichte Gelenktrajektorie.

Schnittstelle::

    plan_part(part_mesh_P, part_id, params, mode=..., placement=None, root=...) -> PartPlan
    find_placement(part_mesh_P, params) -> [Candidate]             # Platzierungssuche (5.4/3)

Module: `graph` (Knoten, Kanten, Viterbi), `plan` (Ringe, Travel, Pruefung), `densify`
(movel/movej-Abtastung), `placement` (Suche), `backend` (Kollisions-Naht, Kugel-Double),
`kin` (Posen mit psi), `params` (SPEC §10).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from roboprint import frames
from roboprint.assets import REPO_ROOT, load_tool, load_workstation
from roboprint.slicer import SlicedPart, SliceParams, slice_part

from .backend import CollisionBackend, SphereWorld, make_world
from .kin import Kin
from .params import PlannerParams, from_overrides
from .placement import Candidate, distinct, find_placement, rank_placements
from .plan import PartPlanner, PlannedPath, RingTask

Progress = Callable[[float, str], None]


@dataclass
class PartPlan:
    part_id: str
    placement: frames.Placement
    T_WP: np.ndarray  # noqa: N815
    sliced: SlicedPart
    path: PlannedPath
    candidates: list[Candidate] = field(default_factory=list)
    tried: list[dict[str, Any]] = field(default_factory=list)
    timings_s: dict[str, float] = field(default_factory=dict)


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


def plan_part(
    part_mesh_P: Any,  # noqa: N803
    part_id: str,
    params: PlannerParams,
    mode: str = "collision_aware",
    placement: frames.Placement | None = None,
    root: Path = REPO_ROOT,
    world_factory: Callable[..., Any] = make_world,
    max_candidates: int = 3,
    progress: Progress | None = None,
    procs: int = 1,
) -> PartPlan:
    """Schneidet, sucht (ohne `placement`) die Platzierung und plant das Teil.

    Ohne feste Platzierung werden die besten `max_candidates` verschiedenen Kandidaten der
    Suche in zwei Durchgaengen geplant: zuerst jeder mit dem schnellen Double (Abschlusspruefung
    mit der echten Welt), bis einer machbar ist; erst wenn keiner so machbar ist, plant die
    teure Nachplanung mit der echten Welt die Kandidaten in derselben Reihenfolge nach. Ein
    Kandidat, an dem schon das Double klar scheitert (z. B. S2-Modul 600 x 200 x 370 an
    (475, 450): d_min -34 mm), kostet so nur den schnellen Durchgang (A6.3: 436 s -> ~90 s).
    Sonst gilt der Plan mit dem groessten d_min.
    """
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    sliced = slice_part(
        part_mesh_P,
        SliceParams(
            params.layer_height_mm, params.bead_width_mm, params.shells, params.step_mm, params.approach_mm
        ),
    )
    timings["slice"] = time.perf_counter() - t0
    aware = mode == "collision_aware"
    cands: list[Candidate] = []
    if placement is None:
        t = time.perf_counter()
        kin = Kin(load_workstation(root), load_tool(root))
        cands = rank_placements(part_mesh_P, kin, params, root, procs=procs)
        timings["placement"] = time.perf_counter() - t
        todo = [c.placement for c in distinct(cands, max_candidates)]
        if not todo:
            raise ValueError(f"Teil {part_id}: keine zulaessige Platzierung auf der Arbeitsflaeche")
    else:
        todo = [placement]
    best: tuple[frames.Placement, np.ndarray, PlannedPath] | None = None
    tried: list[dict[str, Any]] = []
    first: list[tuple[frames.Placement, np.ndarray, PlannedPath]] = []

    def consider(pl: frames.Placement, T_WP: np.ndarray, path: PlannedPath) -> None:  # noqa: N803
        nonlocal best
        tried.append(
            {
                "x_mm": pl.x_mm,
                "y_mm": pl.y_mm,
                "yaw_deg": float(np.degrees(pl.yaw_rad)),
                "feasible": path.feasible,
                "d_min_mm": path.d_min_mm,
            }
        )
        better = (
            best is None
            or (path.feasible and not best[2].feasible)
            or (path.feasible == best[2].feasible and (path.d_min_mm or -1e9) > (best[2].d_min_mm or -1e9))
        )
        if better:
            best = (pl, T_WP, path)

    t = time.perf_counter()
    for i, pl in enumerate(todo):  # Durchgang 1: Double-Planung
        if progress:
            progress(i / (2 * len(todo)), f"Platzierung {i + 1}/{len(todo)}")
        T_WP, path = plan_at(  # noqa: N806
            part_mesh_P, sliced, pl, params, aware, root, world_factory, procs, replan=False
        )
        consider(pl, T_WP, path)
        first.append((pl, T_WP, path))
        if path.feasible:
            break
    if aware and not (best and best[2].feasible):  # Durchgang 2: Nachplanung mit der echten Welt
        for i, (pl, T_WP, path) in enumerate(first):  # noqa: N806
            if progress:
                progress(0.5 + i / (2 * len(first)), f"Nachplanung {i + 1}/{len(first)}")
            path2 = replan_at(part_mesh_P, sliced, pl, params, path, root, world_factory, procs)
            if path2 is path:
                continue
            consider(pl, T_WP, path2)
            if path2.feasible:
                break
    timings["plan"] = time.perf_counter() - t
    assert best is not None
    pl, T_WP, path = best  # noqa: N806
    for k, v in path.timings_s.items():
        timings[f"plan_{k}"] = v
    return PartPlan(part_id, pl, T_WP, sliced, path, cands, tried, timings)


__all__ = [
    "Candidate",
    "CollisionBackend",
    "PartPlan",
    "PlannedPath",
    "PlannerParams",
    "SphereWorld",
    "find_placement",
    "from_overrides",
    "make_world",
    "plan_at",
    "plan_part",
    "replan_at",
    "rank_placements",
]
