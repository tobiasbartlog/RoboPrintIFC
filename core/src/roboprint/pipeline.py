"""Szenario ausfuehren, Laufordner schreiben (SPEC §6, spec/ARTEFAKTE.md), Fortschritt melden."""

from __future__ import annotations

import datetime as _dt
import multiprocessing as mp
import os
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from roboprint import export, frames
from roboprint.assets import REPO_ROOT, load_tool, load_workstation
from roboprint.contracts import (
    PartEntry,
    Provenance,
    Scenario,
    Scene,
    SceneParams,
    SceneRobot,
    SceneTool,
    SceneWorkstation,
    Summary,
    WallEntry,
    dump_json,
    load_json,
)
from roboprint.planner import PartPlan, PlannerParams, from_overrides, plan_part
from roboprint.planner.kin import Kin

# Fortschritts-Callback: progress(stage, fraction 0..1, message), siehe `roboprint.api_jobs`.
ProgressCallback = Callable[[str, float, str], None]

ASSUMPTIONS = [
    "Schichthoehe h = 10 mm (A)",
    "Strangbreite w = 30 mm, Duese 30gut (A)",
    "v_print = 100 mm/s (A)",
    "v_travel = 250 mm/s, Gelenke <= 30 % der Grenzen (A)",
    "z_lift = 30 mm ueber Druckstand-Oberkante (A)",
    "An- und Abfahrt senkrecht 20 mm (A)",
    "V_pump = 5,0 V konstant auf AO 1 (A)",
    "t_tot = 3,0 s Verweilzeit am Ringstart (A, provisorisch)",
    "r_blend = min(2 mm, halbe Segmentlaenge) (A)",
    "d_hard = 10 mm (A)",
    "tau_max = 0 Grad (A)",
    "tcp_name FGC_30GUT muss am Teach Pendant angelegt sein (A)",
    "Duese rotationssymmetrisch, Gierwinkel psi frei (SPEC §13/3)",
]


@dataclass
class PartJob:
    part_id: str
    wall_id: str
    mesh_P: Any  # trimesh.Trimesh  # noqa: N815
    T_LP: np.ndarray  # noqa: N815
    placement: frames.Placement | None
    plan: PartPlan | None = None  # schon in der Zerlegung voll geplant (A2.2), nicht wiederholen
    expected_size_mm: tuple[float, float, float] | None = None  # Zellmasse (Selbstpruefung f)
    expected_volume_mm3: float | None = None


def _git_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
        )
        return out.stdout.strip() or None
    except OSError:
        return None


def _resolve(path: Path) -> Path:
    p = Path(path)
    if p.exists():
        return p
    alt = REPO_ROOT / p
    return alt if alt.exists() else p


def _box_job(scn: Scenario) -> tuple[WallEntry, list[PartJob]]:
    from roboprint.geometry import make_box

    L, T, H = (float(v) for v in scn.source.size_mm)  # noqa: N806
    mesh = make_box([L, T, H], origin=[-L / 2, -T / 2, 0.0])
    T_LP = frames.T_LP([0.0, 0.0, 0.0], [L, T, H])  # noqa: N806
    pl = None
    if scn.placement_override is not None:
        po = scn.placement_override
        pl = frames.Placement(po.x_mm, po.y_mm, float(np.radians(po.yaw_deg)))
    pid = "box_01"
    wall = WallEntry(
        wall_id="box",
        name="Quader",
        eligible=True,
        reason=None,
        length_mm=L,
        thickness_mm=T,
        height_mm=H,
        volume_mm3=L * T * H,
        part_ids=[pid],
    )
    return wall, [PartJob(pid, "box", mesh, T_LP, pl)]


def _ifc_jobs(
    scn: Scenario, params: PlannerParams, jobs: int = 1, progress: ProgressCallback | None = None
) -> tuple[list[WallEntry], list[PartJob]]:
    """IFC-Quelle: Zerlegung in Module (A2.2, `roboprint.decompose`)."""
    from roboprint import decompose

    fn = getattr(decompose, "scenario_parts", None)
    if fn is None:
        raise NotImplementedError(
            "IFC-Szenarien brauchen roboprint.decompose.scenario_parts(scenario, params) "
            "-> (walls, parts) (Aufgabe A2.2)"
        )
    return fn(scn, params, jobs=jobs, progress=progress)


def _plan_job(job: PartJob, params: PlannerParams, mode: str, procs: int = 1) -> PartPlan:
    return plan_part(job.mesh_P, job.part_id, params, mode=mode, placement=job.placement, procs=procs)


def _check_procs() -> int:
    """Prozesse fuer die Pools innerhalb eines Teils (Graphen, Platzierung, Abschlusspruefung;
    4 vCPU: 3, der Hauptprozess plant derweil weiter)."""
    return max(1, min(3, (os.cpu_count() or 1) - 1))


def _warm_caches(params: PlannerParams, root: Path) -> None:
    """Statische Kollisionsgeometrie (echte Welt, Kugel-Double) und Arbeitsflaeche einmal im
    Elternprozess aufbauen, damit Kindprozesse (fork) sie erben statt neu zu bauen."""
    from roboprint.collision import World
    from roboprint.planner import SphereWorld
    from roboprint.planner.placement import base_footprint_S, work_surface_S

    World(None, np.eye(4), params.layer_height_mm, root, params.r_free_mm)
    SphereWorld(None, np.eye(4), params.layer_height_mm, root, params.r_free_mm)
    base_footprint_S(root)
    work_surface_S(root)


# --------------------------------------------------------------------------- Artefakte


def _scene(params: PlannerParams, root: Path) -> Scene:
    ws, tool = load_workstation(root), load_tool(root)
    return Scene(
        robot=SceneRobot(urdf="third_party/doosan_m1013/urdf/m1013.white.urdf"),
        workstation=SceneWorkstation(
            mesh=f"workstations/{ws.mesh}", T_WB=frames.T_WB(ws).tolist(), T_WS=frames.T_WS(ws).tolist()
        ),
        tool=SceneTool(
            mesh=f"tools/{tool.mesh}",
            T_FT=frames.T_FT(tool).tolist(),
            mesh_transform=frames.T_F_mesh(tool).tolist(),
        ),
        params=SceneParams(
            d_hard_mm=params.d_hard_mm,
            d_target_mm=params.d_target_mm,
            d_target_printed_mm=params.d_target_printed_mm,
            r_free_mm=params.r_free_mm,
            layer_height_mm=params.layer_height_mm,
        ),
    )


def run_scenario(path: Path, out: Path, jobs: int = 1, progress: ProgressCallback | None = None) -> int:
    """Fuehrt ein Szenario aus und schreibt die Artefakte (SPEC §6) nach `out`. Exit-Code 0
    auch bei nicht machbaren Teilen (Ergebnis in summary.json). `jobs`: Teile parallel in so
    vielen Prozessen, <= 0 = Anzahl vCPU (hoechstens Anzahl Teile)."""
    t_start = time.perf_counter()
    report = progress or (lambda stage, frac, msg: None)
    root = REPO_ROOT
    path, out = _resolve(Path(path)), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}
    scn = load_json(path, Scenario)
    ws = load_workstation(root)
    params = from_overrides(scn.params, ws.safety_min_distance_mm)
    report("load", 0.02, "Szenario geladen")

    t = time.perf_counter()
    if scn.source.kind == "box":
        wall, part_jobs = _box_job(scn)
        walls = [wall]
    else:
        walls, part_jobs = _ifc_jobs(
            scn, params, jobs, lambda s, f, m: report("decompose", 0.02 + 0.88 * min(max(f, 0.0), 1.0), m)
        )
    timings["decompose"] = time.perf_counter() - t
    report("decompose", 0.05, f"{len(part_jobs)} Teil(e)")

    t = time.perf_counter()
    jobs_arg = jobs
    todo = [j for j in part_jobs if j.plan is None]  # Teile aus der Zerlegung sind schon geplant
    done: dict[str, PartPlan] = {}
    n_cpu = os.cpu_count() or 1
    jobs = min(n_cpu if jobs <= 0 else jobs, max(len(todo), 1))
    if mp.current_process().daemon:  # z. B. API-Job: keine Kindprozesse erlaubt
        jobs = 1
    if jobs > 1:
        # Teile parallel; die Prozesse erben die aufgebaute Geometrie (fork) und teilen den
        # Plattencache, uebrige Kerne gehen an die Pools innerhalb eines Teils.
        procs = max(1, n_cpu // jobs)
        _warm_caches(params, root)
        ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else None
        with ProcessPoolExecutor(max_workers=jobs, mp_context=ctx) as ex:
            futs = [ex.submit(_plan_job, j, params, scn.planner_mode, procs) for j in todo]
            for i, (j, f) in enumerate(zip(todo, futs, strict=True)):
                done[j.part_id] = f.result()
                report("plan", 0.05 + 0.85 * (i + 1) / len(futs), f"Teil {i + 1}/{len(futs)}")
    else:
        for i, j in enumerate(todo):
            report("plan", 0.05 + 0.85 * i / max(len(todo), 1), f"Teil {i + 1}/{len(todo)}")
            done[j.part_id] = _plan_job(j, params, scn.planner_mode, _check_procs())
    plans: list[PartPlan] = [j.plan if j.plan is not None else done[j.part_id] for j in part_jobs]
    timings["plan"] = time.perf_counter() - t
    seen: set[int] = set()
    for pp in plans:
        # Kopien aus dem Geometrie-Cache teilen den Plan: Zeiten nur einmal (beim ersten Teil)
        if id(pp.path) in seen:
            continue
        seen.add(id(pp.path))
        for k, v in pp.timings_s.items():
            timings[f"{pp.part_id}.{k}"] = timings.get(f"{pp.part_id}.{k}", 0.0) + v

    t = time.perf_counter()
    scene = _scene(params, root)
    dump_json(scene, out / "scene.json")
    provenance = Provenance(
        git_commit=_git_commit(root),
        created=_dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        command=" ".join(sys.argv),
    )

    def summary(entries: list[PartEntry]) -> Summary:
        return Summary(
            scenario_id=scn.id,
            scenario_path=str(path),
            params=params.as_summary(),
            assumptions=ASSUMPTIONS,
            walls=walls,
            parts=entries,
            timings_s={k: round(v, 3) for k, v in timings.items()},
            provenance=provenance,
        )

    ctx = export.ExportContext(
        out=out,
        part_jobs=part_jobs,
        plans=plans,
        kin=Kin(ws, load_tool(root)),
        params=params,
        scn=scn,
        scene=scene,
        provenance=provenance,
        run_params=dict(summary([]).params),
    )
    report("export", 0.9, "Artefakte und DRL")
    entries = export.export_parts(
        ctx,
        min(n_cpu if jobs_arg <= 0 else jobs_arg, n_cpu),
        lambda i, n: report("export", 0.9 + 0.09 * i / max(n, 1), f"Export {i}/{n}"),
    )
    timings["export"] = time.perf_counter() - t
    timings["total"] = time.perf_counter() - t_start
    dump_json(summary(entries), out / "summary.json", indent=1)
    report("done", 1.0, "fertig")
    return 0
