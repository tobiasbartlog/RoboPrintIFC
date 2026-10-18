"""Planer-Anbindung der Zerlegung (SPEC §5.4/3, §5.4/5) und Naht zur Pipeline.

- Vorpruefung fuer die H*-Bisektion: Platzierungssuche `planner.rank_placements` (Kugel-Double,
  wenige Probewegpunkte, ~10 s je Quader, unerreichbare Quader in < 1 s). Machbar heisst: die
  beste Platzierung hat einen Vorauswahl-Abstand >= d_hard + `prefeasible_margin_mm`.
- Volle Pruefung je Teil: `planner.plan_part` (Platzierungssuche, Ladder-Graph, Travel, dichte
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

from roboprint.assets import REPO_ROOT, load_tool, load_workstation
from roboprint.decompose import (
    DecomposeParams,
    DecomposeStats,
    Feasibility,
    FeasibleFn,
    ProgressCallback,
    decompose_walls,
    wall_entry,
)
from roboprint.ifc import Wall, read_walls

PREFEASIBLE_MARGIN_MM = 0.0

# Annahmen (A) fuer Laufzeit und Planbarkeit, gemessen am 2026-10-19 auf der Cloud-VM:
# - Die Vorpruefung (Platzierungssuche) ist zu optimistisch: Sie stuft Quader bis ~1000 mm Hoehe
#   als machbar ein (Score ~50 mm), die volle Planung schafft 600 x 200 x 460 nicht mehr
#   (d = 8,7 mm < d_hard, link_2 / printed) und braucht fuer hohe Teile > 30 min.
# - 600 x 200 x 400 (S1) ist geprueft machbar (d_min 10,8 mm, ~100 s).
# Deshalb begrenzt die Zerlegung im Szenariolauf b_max = 600 mm (SPEC §5.4/4) und die obere
# Schranke der H*-Bisektion auf 400 mm. Ohne diese Grenzen sprengt S2 das Budget von 1800 s um
# ein Vielfaches. Overrides: `DECOMPOSE_DEFAULTS` anpassen.
DECOMPOSE_DEFAULTS: dict[str, float] = {"b_max_mm": 600.0, "h_upper_mm": 400.0}


def prefeasible_fn(
    params: Any, root: Path = REPO_ROOT, margin_mm: float = PREFEASIBLE_MARGIN_MM, procs: int = 1
) -> FeasibleFn:
    """Schnelle Vorpruefung ueber die Platzierungssuche (Kugel-Double)."""
    from roboprint.planner import rank_placements
    from roboprint.planner.kin import Kin

    kin = Kin(load_workstation(root), load_tool(root))
    need = params.d_hard_mm + margin_mm

    def check(mesh_P: trimesh.Trimesh) -> Feasibility:  # noqa: N803
        cands = rank_placements(mesh_P, kin, params, root, procs=procs)
        if not cands:
            return Feasibility(False, None, None, "keine zulaessige Platzierung auf der Arbeitsflaeche")
        c = cands[0]
        ok = c.score >= need
        why = None if ok else f"Vorauswahl-Abstand {c.score:.1f} mm < {need:.1f} mm"
        return Feasibility(ok, float(c.score), c.placement, why)

    return check


def _cause_text(path: Any) -> str | None:
    c = getattr(path, "cause", None)
    if not c:
        return None
    where = f"Sample {c.get('sample')}, {c.get('link')} / {c.get('obstacle')}"
    return f"{c.get('message', 'nicht machbar')} ({where})"


def _plan_one(args: tuple[trimesh.Trimesh, Any, str, int, Path]) -> Feasibility:
    from roboprint.planner import plan_part

    mesh_P, params, mode, procs, root = args  # noqa: N806
    try:
        pp = plan_part(mesh_P, "decompose", params, mode=mode, root=root, procs=procs)
    except ValueError as exc:  # z. B. keine zulaessige Platzierung
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


def plan_many_fn(params: Any, mode: str, jobs: int = 1, root: Path = REPO_ROOT):
    """Volle Planung einer Liste von Teilen, mit `jobs > 1` parallel (fork, Geometrie einmal im
    Elternprozess); die uebrigen Kerne gehen als `procs` an die Pools innerhalb eines Teils."""
    import multiprocessing as mp

    cpus = os.cpu_count() or 1
    jobs = effective_jobs(jobs)

    def many(meshes: list[trimesh.Trimesh]) -> list[Feasibility]:
        workers = min(jobs, len(meshes))
        if workers > 1:
            from roboprint.pipeline import _warm_caches

            _warm_caches(params, root)
            procs = max(1, cpus // workers)
            ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else None
            with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
                return list(ex.map(_plan_one, [(m, params, mode, procs, root) for m in meshes]))
        return [_plan_one((m, params, mode, cpus, root)) for m in meshes]

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
    dp = DecomposeParams.from_any(
        {
            **DECOMPOSE_DEFAULTS,
            "bead_width_mm": params.bead_width_mm,
            "layer_height_mm": params.layer_height_mm,
        }
    )
    parts = decompose_walls(
        walls,
        dp,
        progress=progress,
        prefeasible=prefeasible_fn(params, root, procs=os.cpu_count() or 1),
        feasible_many=plan_many_fn(params, scenario.planner_mode, jobs, root),
        stats=stats,
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
