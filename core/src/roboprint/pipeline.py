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

from roboprint import frames, selfcheck
from roboprint.assets import REPO_ROOT, load_tool, load_workstation
from roboprint.contracts import (
    BBox,
    Cause,
    PartArtifact,
    PartEntry,
    Placement,
    Provenance,
    Scenario,
    Scene,
    SceneParams,
    SceneRobot,
    SceneTool,
    SceneWorkstation,
    Summary,
    Trajectory,
    TrajectorySummary,
    WallEntry,
    dump_json,
    load_json,
)
from roboprint.planner import PartPlan, PlannerParams, from_overrides, plan_part
from roboprint.planner.kin import Kin, psi_of, rot_down
from roboprint.slicer import to_toolpath
from roboprint.timing import TimingParams, time_parametrize

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


def _ifc_jobs(scn: Scenario, params: PlannerParams) -> tuple[list[WallEntry], list[PartJob]]:
    """IFC-Quelle: Zerlegung in Module (A2.2, `roboprint.decompose`)."""
    from roboprint import decompose

    fn = getattr(decompose, "scenario_parts", None)
    if fn is None:
        raise NotImplementedError(
            "IFC-Szenarien brauchen roboprint.decompose.scenario_parts(scenario, params) "
            "-> (walls, parts) (Aufgabe A2.2)"
        )
    return fn(scn, params)


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


def _trajectory(pp: PartPlan, kin: Kin, params: PlannerParams) -> Trajectory:
    path = pp.path
    n = len(path.q)
    T = kin.tcp_W(path.q)  # noqa: N806
    ok = path.reachable
    pos = np.where(ok[:, None], T[:, :3, 3], path.p_W)
    R = np.where(ok[:, None, None], T[:, :3, :3], rot_down(path.psi))  # noqa: N806
    quat = np.array([frames.matrix_to_quat(r) for r in R])
    psi = np.where(ok, psi_of(T[:, :3, :3]), path.psi)
    t_s = time_parametrize(
        path.q,
        pos,
        path.kind,
        path.ring,
        TimingParams(
            v_print_mm_s=params.v_print_mm_s,
            v_travel_mm_s=params.v_travel_mm_s,
            joint_speed_fraction=params.joint_speed_fraction,
            t_tot_s=params.t_tot_s,
        ),
    )
    d_mm, pair, wit = [], [], []
    for c, o in zip(path.contacts, ok, strict=True):
        if not o or c is None:
            d_mm.append(None)
            pair.append(None)
            wit.append(None)
        else:
            d_mm.append(float(c.d_mm))
            pair.append([str(c.pair[0]), str(c.pair[1])])
            wit.append([[float(v) for v in c.witness_W[0]], [float(v) for v in c.witness_W[1]]])
    status = path.status
    cnt = {k: status.count(k) for k in ("ok", "warn", "collision", "unreachable")}
    return Trajectory(
        part_id=pp.part_id,
        t_s=[float(v) for v in t_s],
        q=path.q.tolist(),
        tcp=np.hstack([pos, quat]).tolist(),
        layer=[int(v) for v in path.layer],
        ring=[int(v) for v in path.ring],
        kind=list(path.kind),
        branch=[int(v) for v in path.branch],
        status=list(status),
        d_mm=d_mm,
        pair=pair,
        witness=wit,
        psi_rad=[float(v) for v in psi],
        summary=TrajectorySummary(
            n=n,
            n_ok=cnt["ok"],
            n_warn=cnt["warn"],
            n_collision=cnt["collision"],
            n_unreachable=cnt["unreachable"],
            d_min_mm=path.d_min_mm,
            dauer_s=float(t_s[-1]) if n else 0.0,
            zweig_wechsel_in_ringen=path.branch_switches_in_rings,
        ),
    )


def _write_part(
    out: Path, job: PartJob, pp: PartPlan, kin: Kin, params: PlannerParams, scn: Scenario | None = None
) -> tuple[PartEntry, Trajectory]:
    pdir = out / "parts" / job.part_id
    pdir.mkdir(parents=True, exist_ok=True)
    job.mesh_P.export(pdir / "part.stl")
    tp = to_toolpath(pp.sliced, pp.T_WP, job.part_id)
    dump_json(tp, pdir / "toolpath.json")
    tr = _trajectory(pp, kin, params)
    selfcheck.apply(pp, job, tr, tp, params, scn)
    dump_json(tr, pdir / "trajectory.json")
    path = pp.path
    status = "machbar" if path.feasible else "nicht machbar"
    cause = None
    if path.cause is not None:
        c = path.cause
        cause = Cause(
            sample=int(c["sample"]),
            t_s=float(tr.t_s[c["sample"]]),
            link=str(c["link"]),
            obstacle=str(c["obstacle"]),
            message=str(c["message"]),
        )
    lo, hi = np.asarray(job.mesh_P.bounds, float)
    pl = pp.placement
    part = PartArtifact(
        part_id=job.part_id,
        wall_id=job.wall_id,
        T_LP=np.asarray(job.T_LP).tolist(),
        T_SP=frames.T_SP(pl).tolist(),
        T_WP=pp.T_WP.tolist(),
        placement=Placement(x_mm=pl.x_mm, y_mm=pl.y_mm, yaw_deg=float(np.degrees(pl.yaw_rad))),
        bbox_P=BBox(min=lo.tolist(), max=hi.tolist()),
        volume_mm3=float(job.mesh_P.volume),
        n_layers=int(pp.sliced.n_layers),
        status=status,
        cause=cause,
    )
    dump_json(part, pdir / "part.json")
    entry = PartEntry(
        part_id=job.part_id,
        wall_id=job.wall_id,
        status=status,
        d_min_mm=path.d_min_mm,
        n_collision=tr.summary.n_collision,
        n_unreachable=tr.summary.n_unreachable,
    )
    return entry, tr


def _write_programs(pdir: Path, feasible: bool) -> None:
    from roboprint import drl

    try:
        if feasible:
            drl.write_programs(pdir)
            return
        pp = drl.load_planned_part(pdir)
        for d in drl.DIALECTS:
            (pdir / f"program.{d}.drl").write_text(
                drl.emit(pp, d, allow_infeasible=True), encoding="ascii", newline="\n"
            )
    except ValueError as exc:
        for d in ("v2", "v3"):
            (pdir / f"program.{d}.drl").write_text(
                f"# Kein Programm: Teil nicht machbar ({exc}).\n",
                encoding="ascii",
                errors="replace",
                newline="\n",
            )


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
        walls, part_jobs = _ifc_jobs(scn, params)
    timings["decompose"] = time.perf_counter() - t
    report("decompose", 0.05, f"{len(part_jobs)} Teil(e)")

    t = time.perf_counter()
    plans: list[PartPlan] = []
    n_cpu = os.cpu_count() or 1
    jobs = min(n_cpu if jobs <= 0 else jobs, len(part_jobs))
    if mp.current_process().daemon:  # z. B. API-Job: keine Kindprozesse erlaubt
        jobs = 1
    if jobs > 1:
        # Teile parallel; die Prozesse erben die aufgebaute Geometrie (fork) und teilen den
        # Plattencache, uebrige Kerne gehen an die Pools innerhalb eines Teils.
        procs = max(1, n_cpu // jobs)
        _warm_caches(params, root)
        ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else None
        with ProcessPoolExecutor(max_workers=jobs, mp_context=ctx) as ex:
            futs = [ex.submit(_plan_job, j, params, scn.planner_mode, procs) for j in part_jobs]
            for i, f in enumerate(futs):
                plans.append(f.result())
                report("plan", 0.05 + 0.85 * (i + 1) / len(futs), f"Teil {i + 1}/{len(futs)}")
    else:
        for i, j in enumerate(part_jobs):
            report("plan", 0.05 + 0.85 * i / max(len(part_jobs), 1), f"Teil {i + 1}/{len(part_jobs)}")
            plans.append(_plan_job(j, params, scn.planner_mode, _check_procs()))
    timings["plan"] = time.perf_counter() - t
    for pp in plans:
        for k, v in pp.timings_s.items():
            timings[f"{pp.part_id}.{k}"] = timings.get(f"{pp.part_id}.{k}", 0.0) + v

    t = time.perf_counter()
    kin = Kin(ws, load_tool(root))
    dump_json(_scene(params, root), out / "scene.json")
    entries = []
    for job, pp in zip(part_jobs, plans, strict=True):
        entry, _ = _write_part(out, job, pp, kin, params, scn)
        entries.append(entry)

    def summary() -> Summary:
        return Summary(
            scenario_id=scn.id,
            scenario_path=str(path),
            params=params.as_summary(),
            assumptions=ASSUMPTIONS,
            walls=walls,
            parts=entries,
            timings_s={k: round(v, 3) for k, v in timings.items()},
            provenance=Provenance(
                git_commit=_git_commit(root),
                created=_dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
                command=" ".join(sys.argv),
            ),
        )

    dump_json(summary(), out / "summary.json", indent=1)
    report("export", 0.95, "DRL")
    for job, pp in zip(part_jobs, plans, strict=True):
        _write_programs(out / "parts" / job.part_id, pp.path.feasible)
    timings["export"] = time.perf_counter() - t
    timings["total"] = time.perf_counter() - t_start
    dump_json(summary(), out / "summary.json", indent=1)
    report("done", 1.0, "fertig")
    return 0
