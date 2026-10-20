"""Planer-Anbindung der Zerlegung (SPEC §5.4/3, §5.4/5) und Naht zur Pipeline.

- Alle Teile stehen am selben Platz: dem Druckplatz der Parameter (`spot_x_mm`, `spot_y_mm`) oder
  der festen Platzierung des Szenarios (`placement_override`). Die Zerlegung gilt genau dort.
- Vorpruefung fuer die H*-Bisektion: `planner.placement_score` am Platz (Kugel-Double, wenige
  Probewegpunkte). Machbar heisst: Vorauswahl-Abstand >= d_hard + `prefeasible_margin_mm`.
- Hoehensuche (`scan_fn`): Die Vorpruefung ist optimistisch. `planner.scan_height` plant den
  Quader b x T x H*_vor einmal von unten und stoppt an der ersten Schicht, die nicht geht; H* ist
  die Oberkante der Schicht darunter. Quader-Zellen bis zu dieser Hoehe bekommen den Plan als
  exakten Ausschnitt (`_from_scan`, gleiche Ringe und Platzierung) statt einer neuen Planung.
- Volle Pruefung je Teil: `planner.plan_part` (Ladder-Graph, Travel, dichte
  Abschlusspruefung). Der Plan wird an die Pipeline durchgereicht und dort nicht wiederholt.
  Gleiche Geometrie wird nur einmal geplant (Cache in `decompose`); unterschiedliche Teile einer
  Runde laufen mit `jobs > 1` parallel.
"""

from __future__ import annotations

import dataclasses
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from roboprint import geometry as geo
from roboprint.assets import REPO_ROOT, load_tool, load_workstation
from roboprint.decompose import (
    DecomposeParams,
    DecomposeStats,
    Feasibility,
    FeasibleFn,
    ProgressCallback,
    ScanFn,
    box_mesh_P,
    decompose_walls,
    wall_entry,
)
from roboprint.frames import Placement
from roboprint.ifc import Wall, read_walls

PREFEASIBLE_MARGIN_MM = 0.0

# Annahmen (A) fuer Laufzeit und Planbarkeit:
# - Die Vorpruefung (`placement_score`) ist zu optimistisch: Sie stuft Quader bis ~1000 mm Hoehe
#   als machbar ein. Deshalb bestaetigt die Hoehensuche der vollen Planung H* (schichtgenau).
#   Sie plant mit dem Kugel-Double und prueft jeden Ring mit der echten Welt; die langsame
#   Nachplanung (`replan_at`) laeuft dabei nicht, H* ist also eher etwas zu niedrig.
# - Die obere Schranke der H*-Bisektion ist die Nutzergrenze `module_height_max_mm` (Standard
#   400 mm, Lehm unter Eigengewicht).
# - b_max = 600 mm (SPEC §5.4/4) haelt S2 im Budget von 1800 s. Overrides: `DECOMPOSE_DEFAULTS`.
DECOMPOSE_DEFAULTS: dict[str, float | bool] = {"b_max_mm": 600.0}


def prefeasible_fn(
    params: Any,
    root: Path = REPO_ROOT,
    margin_mm: float = PREFEASIBLE_MARGIN_MM,
    placement: Placement | None = None,
) -> FeasibleFn:
    """Schnelle Vorpruefung am Platz (Kugel-Double); ohne `placement` am Druckplatz der Parameter."""
    from roboprint.planner import placement_score, spot_placement
    from roboprint.planner.kin import Kin

    kin = Kin(load_workstation(root), load_tool(root))
    need = params.d_hard_mm + margin_mm
    pl = placement if placement is not None else spot_placement(params)

    def check(mesh_P: trimesh.Trimesh) -> Feasibility:  # noqa: N803
        score = placement_score(mesh_P, kin, params, pl, root)
        if score is None:
            why = f"passt am Druckplatz ({pl.x_mm:g}, {pl.y_mm:g}) mm nicht auf die Arbeitsflaeche"
            return Feasibility(False, None, None, why)
        ok = score >= need
        why = None if ok else f"Vorauswahl-Abstand {score:.1f} mm < {need:.1f} mm"
        return Feasibility(ok, score, pl, why)

    return check


def scan_fn(
    params: Any, scans: list[Any], root: Path = REPO_ROOT, procs: int = 1, placement: Placement | None = None
) -> ScanFn:
    """Hoehensuche fuer Quader b x t x h am Platz; jeder Plan landet in `scans` (fuer `_from_scan`)."""
    from roboprint.planner import scan_height

    def scan(b: float, t: float, h: float) -> float:
        try:
            pp = scan_height(box_mesh_P(b, t, h), "scan", params, placement, root=root, procs=procs)
        except ValueError:  # passt am Druckplatz nicht auf die Arbeitsflaeche
            return 0.0
        scans.append(pp)
        return float(pp.path.layers_ok or 0) * params.layer_height_mm

    return scan


def _same_rings(low: list[Any], high: list[Any], n_layers: int) -> bool:
    """Sind die Ringe `low` exakt die Ringe von `high` unter Schicht `n_layers`?"""
    if len(low) > len(high) or (len(high) > len(low) and high[len(low)].layer < n_layers):
        return False
    return all(
        a.layer == b.layer and a.shell == b.shell and a.kind == b.kind and a.points.shape == b.points.shape
        and np.allclose(a.points, b.points, atol=1e-6)
        for a, b in zip(low, high, strict=False)
    )  # fmt: skip


def _from_scan(mesh_P: trimesh.Trimesh, scans: list[Any], params: Any) -> Feasibility | None:  # noqa: N803
    """Plan eines Vollquaders als Ausschnitt einer Hoehensuche gleicher Grundflaeche.

    Exakt, wenn die Ringe uebereinstimmen: Die Planung haengt dann nur noch vom Druckstand ab, und
    der Druckstand des Teils liegt in dem des hoeheren Quaders."""
    from roboprint.planner import slice_params, truncate_plan
    from roboprint.slicer import slice_part

    ext = np.asarray(mesh_P.extents, float)
    if abs(geo.volume(mesh_P) - float(np.prod(ext))) > 1e-6 * float(np.prod(ext)):
        return None  # kein Vollquader (Oeffnung, schraege Oberkante)
    n = int(round(ext[2] / params.layer_height_mm))
    sliced = None
    for pp in scans:
        if n < 1 or n > (pp.path.layers_ok or 0):
            continue
        if sliced is None:
            sliced = slice_part(mesh_P, slice_params(params))
        if not _same_rings(sliced.rings, pp.sliced.rings, n):
            continue
        cut = truncate_plan(pp, n, params)
        if cut.path.feasible:
            return Feasibility(True, cut.path.d_min_mm, cut.placement, None, cut)
    return None


def _cause_text(path: Any) -> str | None:
    c = getattr(path, "cause", None)
    if not c:
        return None
    where = f"Sample {c.get('sample')}, {c.get('link')} / {c.get('obstacle')}"
    return f"{c.get('message', 'nicht machbar')} ({where})"


def _plan_one(args: tuple[trimesh.Trimesh, Any, str, int, Path, Placement | None]) -> Feasibility:
    from roboprint.planner import plan_part

    mesh_P, params, mode, procs, root, placement = args  # noqa: N806
    try:
        pp = plan_part(mesh_P, "decompose", params, mode=mode, placement=placement, root=root, procs=procs)
    except ValueError as exc:  # z. B. passt am Druckplatz nicht auf die Arbeitsflaeche
        return Feasibility(False, None, None, str(exc))
    except Exception as exc:  # noqa: BLE001 - Planerfehler: Teil gilt als nicht machbar, Zelle wird geteilt
        return Feasibility(False, None, None, f"Planerfehler {type(exc).__name__}: {exc}")
    path = pp.path
    return Feasibility(bool(path.feasible), path.d_min_mm, pp.placement, _cause_text(path), pp)


def effective_jobs(jobs: int) -> int:
    """jobs <= 0: alle vCPU; in Daemon-Prozessen (API-Job) keine Kindprozesse."""
    import multiprocessing as mp

    n = os.cpu_count() or 1
    j = n if jobs <= 0 else jobs
    return 1 if mp.current_process().daemon else max(1, j)


def plan_many_fn(
    params: Any,
    mode: str,
    jobs: int = 1,
    root: Path = REPO_ROOT,
    scans: list[Any] | None = None,
    placement: Placement | None = None,
):
    """Volle Planung einer Liste von Teilen, mit `jobs > 1` parallel (fork, Geometrie einmal im
    Elternprozess); die uebrigen Kerne gehen als `procs` an die Pools innerhalb eines Teils.
    Vollquader, die eine Hoehensuche in `scans` schon abdeckt, werden nicht neu geplant."""
    import multiprocessing as mp

    cpus = os.cpu_count() or 1
    jobs = effective_jobs(jobs)

    def many(meshes: list[trimesh.Trimesh]) -> list[Feasibility]:
        out = [_from_scan(m, scans, params) if scans else None for m in meshes]
        todo = [i for i, r in enumerate(out) if r is None]
        planned = plan_list([meshes[i] for i in todo]) if todo else []
        for i, r in zip(todo, planned, strict=True):
            out[i] = r
        return [r for r in out if r is not None]

    def plan_list(meshes: list[trimesh.Trimesh]) -> list[Feasibility]:
        workers = min(jobs, len(meshes))
        if workers > 1:
            from roboprint.pipeline import _warm_caches

            _warm_caches(params, root)
            procs = max(1, cpus // workers)
            ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else None
            with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
                return list(ex.map(_plan_one, [(m, params, mode, procs, root, placement) for m in meshes]))
        return [_plan_one((m, params, mode, cpus, root, placement)) for m in meshes]

    return many


def _select(walls: list[Wall], spec: Any) -> list[Wall]:
    if spec == "all":
        return walls
    want = set(spec)
    return [w for w in walls if w.wall_id in want or (w.name or "") in want]


def _resolve(path: str | Path, root: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() or p.exists() else root / p


def scenario_parts(
    scenario: Any,
    params: Any,
    jobs: int = 1,
    progress: ProgressCallback | None = None,
    root: Path = REPO_ROOT,
    stats: DecomposeStats | None = None,
):
    """IFC-Szenario -> (list[WallEntry], list[PartJob]); jeder PartJob traegt seinen fertigen Plan."""
    from roboprint.contracts import WallEntry
    from roboprint.pipeline import PartJob

    walls = _select(read_walls(_resolve(scenario.source.path, root)), scenario.source.walls)
    scans: list[Any] = []
    aware = scenario.planner_mode == "collision_aware"
    po = scenario.placement_override
    pl = None if po is None else Placement(po.x_mm, po.y_mm, float(np.radians(po.yaw_deg)))
    dp = DecomposeParams.from_any(
        {
            **DECOMPOSE_DEFAULTS,
            "bead_width_mm": params.bead_width_mm,
            "layer_height_mm": params.layer_height_mm,
            "h_upper_mm": params.module_height_max_mm,
        }
    )
    parts = decompose_walls(
        walls,
        dp,
        progress=progress,
        prefeasible=prefeasible_fn(params, root, placement=pl),
        feasible_many=plan_many_fn(params, scenario.planner_mode, jobs, root, scans, pl),
        stats=stats,
        scan=scan_fn(params, scans, root, os.cpu_count() or 1, pl) if aware else None,
    )
    entries = []
    for w in walls:
        e = wall_entry(w, parts, dp)
        e["name"] = e["name"] or w.wall_id
        entries.append(WallEntry(**e))
    jobs_out = []
    for p in parts:
        pp = p.feasibility.planned
        plan = dataclasses.replace(pp, part_id=p.part_id) if pp is not None else None
        w = next(x for x in walls if x.wall_id == p.wall_id)
        size = p.cell_max_L - p.cell_min_L
        if any(o.x0 < p.cell_max_L[0] and o.x1 > p.cell_min_L[0] for o in w.openings):
            size = np.asarray(p.mesh_P.extents, float)  # Oeffnung kann die Bounding-Box verkleinern
        jobs_out.append(
            PartJob(
                p.part_id, p.wall_id, p.mesh_P, p.T_LP, p.placement, plan,
                expected_size_mm=tuple(float(v) for v in size),
                expected_volume_mm3=p.volume_mm3,
            )
        )
    return entries, jobs_out
