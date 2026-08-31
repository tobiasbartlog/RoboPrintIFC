"""Dicken-Studie: Abstand-Sweep über mehrere reale, öffnungsfreie Wände.

Erweitert die Einzel-Modul-Studie (`sweep.py`) auf mehrere reale Wände
unterschiedlicher **Dicke** aus dem denkmal-IFC-Modell. Ziel: zeigen, wie die
Wandstärke die machbare Region (kollisionsfrei UND erreichbar) und die maximale
machbare Bandhöhe verschiebt.

Vorgehen je Wand:
  1. Reale Wand aus der IFC laden (`load_wall`) — echtes Mesh + Maße + Öffnungszahl.
  2. `pc.wall` (WallSurface) direkt aus der IFC-Geometrie bauen (kein Assessment
     nötig — der Assessment-Pfad `placement_context_for_job` wird umgangen).
  3. Frische Modul-Zerlegung (`plan_for_job`, decomposition_kind=modul, keine
     gespeicherten Schnitte) — jede Wand wird eigenständig zerlegt.
  4. `SectionSimContext` von Modul 0 nachbilden (Mesh-Logik aus `section_sim_context`).
  5. Abstand-Sweep über `slice_and_simulate_section` + `section_collision_finding`
     — identische Türen wie `sweep.py`.

Nur öffnungsfreie Wände (opening_count == 0). Auswahl per --gids oder Default-Liste
(kuratiert: Höhe ≈ 3060 mm, Dicken 80–620 mm — Höhe fast konstant, Dicke variiert).

Aufruf:  PYTHONPATH=core/src python experiments/collision_standoff_sweep/sweep_thickness.py \
             --standoff-min 150 --standoff-max 1100 --standoff-step 100
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Kuratierte öffnungsfreie Wände: Höhe ≈ 3060 mm (fast konstant), Dicke 80–620 mm.
DEFAULT_GIDS = [
    "2mu0jgf9H6dQhlc8067eHh",  # 80.1 mm,  936×3060
    "2mu0jgf9H6dQhlc8067eeK",  # 130 mm,  1240×3060
    "2mu0jgf9H6dQhlc8067eok",  # 180 mm,   825×3060
    "2mu0jgf9H6dQhlc8067e39",  # 225 mm,   902×3060
    "2d9LuxY1D3owMKr995JnN$",  # 300 mm,  1124×3060
    "2d9LuxY1D3owMKr995JmcO",  # 489 mm,   844×3060 (Ersatz für 505-mm-Crash)
    "2d9LuxY1D3owMKr995JmXw",  # 505 mm,   990×3060 (nativer fcl/VHACD-Crash, wird übersprungen)
    "2mu0jgf9H6dQhlc8067e6b",  # 620 mm,  1106×3060
]

LINK_NAMES = {0: "base_link", 1: "link_1", 2: "link_2", 3: "link_3",
              4: "link_4", 5: "link_5", 6: "link_6", 7: "tool"}
SAFETY_MM = 50.0


def _classify(dist_mm):
    if dist_mm is None:
        return "green"
    if dist_mm < 0.0:
        return "red"
    if dist_mm < SAFETY_MM:
        return "yellow"
    return "green"


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]
        ).decode().strip()
    except Exception:
        return "unknown"


def aggregate_per_layer(coll, layers):
    per = {}
    for i, d in enumerate(coll["distances_mm"]):
        lyr = layers[i]
        cell = per.get(lyr)
        if cell is None:
            cell = per[lyr] = {"min": None, "link": None, "against": None}
        if d is None:
            continue
        if cell["min"] is None or d < cell["min"]:
            cell["min"] = d
            cell["link"] = coll["causer_link"][i]
            cell["against"] = coll["causer_against"][i]
    return per


def build_module0_ctx(artifact, template_job, gid, robot, tool, robot_name):
    """Baut SectionSimContext von Modul 0 einer beliebigen IFC-Wand (Assessment-frei).

    Spiegelt fgc.pipeline.sectionsim.section_sim_context, aber `pc.wall` kommt aus
    der IFC-Geometrie statt aus dem Befund-Lauf.
    """
    import numpy as np

    from fgc.decompose import apply
    from fgc.domain.process_params import ProcessWindow, SliceParams, section_slice_overrides
    from fgc.ifc_io import walls as ifc_walls
    from fgc.kinematics.opw import OpwKinematics
    from fgc.pipeline import sectionsim as S
    from fgc.pipeline.actions import plan_for_job
    from fgc.placement.evaluate import WallSurface

    model_path = Path(artifact["model_path"])
    wall_data = ifc_walls.load_wall(model_path, gid)
    if wall_data.opening_count != 0:
        raise ValueError(f"Wand {gid} hat {wall_data.opening_count} Öffnungen — übersprungen")
    g = wall_data.geometry
    wall_surface = WallSurface(
        length_mm=g.length_mm, height_mm=g.height_mm,
        thickness_mm=g.thickness_mm, z_offset_mm=0.0,
    )

    # Minimaler Job: frische Modul-Zerlegung (keine gespeicherten Schnitte).
    job = dict(template_job)
    job["wall_global_id"] = gid
    job["decomposition_kind"] = "modul"
    job.pop("cuts", None)
    job.pop("section_overrides", None)

    plan = plan_for_job(job, wall_surface, robot, tool, strict_overrides=False).plan
    if not plan.sections:
        raise ValueError(f"Wand {gid}: leerer Zerlegungsplan")
    idx = 0
    section = plan.sections[idx].section
    placement = plan.sections[idx].placement

    mesh = S._wall_local_mesh(wall_data.vertices_mm, wall_data.faces)
    parts = apply(mesh, plan)
    part = parts[idx]
    if len(part.vertices) == 0:
        raise ValueError(f"Wand {gid}: Modul-0-Mesh leer")
    verts = np.asarray(part.vertices, dtype=float).copy()
    verts[:, 0] -= section.center_x_mm
    verts[:, 2] -= section.z0_mm

    earlier_parts = []  # modul-Modus: prints_in_place False → leer

    window = ProcessWindow.load()
    base_params = SliceParams.from_window(window, **section_slice_overrides(job, section.section_id))

    ctx = S.SectionSimContext(
        robot_name=robot_name,
        tool=tool,
        plan=plan,
        section=section,
        placement=placement,
        verts=verts,
        part_faces=part.faces,
        earlier_parts=earlier_parts,
        section_z0_mm=plan.sim_z0_mm(section),
        base_params=base_params,
        kin=OpwKinematics.from_robot(robot_name),
    )
    return ctx, job, wall_surface, section, wall_data


def measure_wall(artifact, template_job, gid, robot, tool, robot_name, standoffs):
    from fgc.collision.advisor import Override
    from fgc.collision.druckstand import layer_per_sample
    from fgc.pipeline import sectionsim as S

    ctx, job, wall_surface, section, wall_data = build_module0_ctx(
        artifact, template_job, gid, robot, tool, robot_name
    )
    lh = ctx.base_params.layer_height_mm
    sid = section.section_id
    info = {
        "gid": gid,
        "name": wall_data.name,
        "thickness_mm": round(wall_surface.thickness_mm, 1),
        "wall_length_mm": round(wall_surface.length_mm, 1),
        "wall_height_mm": round(wall_surface.height_mm, 1),
        "module_length_mm": round(section.length_mm, 1),
        "module_height_mm": round(section.height_mm, 1),
        "layer_height_mm": lh,
        "n_modules": len(ctx.plan.sections),
    }
    print(f"[wall {gid}] thick={info['thickness_mm']}mm  modul0={info['module_length_mm']}×"
          f"{info['module_height_mm']}mm  ({info['n_modules']} Module)", flush=True)

    grid_rows = []
    for d in standoffs:
        comp = S.slice_and_simulate_section(
            artifact, job, sid,
            override=Override(placement={"standoff_mm": float(d)}), ctx=ctx,
        )
        traj = comp.trajectory
        sample_times = [s["t_s"] for s in traj.samples]
        target_times = traj.target_times or []
        target_layers = [int(t.get("layer", 0)) for t in comp.target_dicts]
        layers = layer_per_sample(sample_times, target_times, target_layers)
        coll = S.section_collision_finding(comp, config=None)
        if coll is None:
            print(f"   d={d:.0f} coll=None übersprungen", flush=True)
            continue
        warn = traj.meta.get("warnings", []) or []
        reach_ts = [w["t_s"] for w in warn if isinstance(w, dict) and w.get("kind") == "reach"]
        reach_pl = Counter(layer_per_sample(reach_ts, target_times, target_layers) if reach_ts else [])
        spl = Counter(layers)
        per = aggregate_per_layer(coll, layers)
        for lyr in sorted(per):
            cell = per[lyr]
            n_s = spl.get(lyr, 0)
            n_r = reach_pl.get(lyr, 0)
            grid_rows.append({
                "gid": gid, "thickness_mm": info["thickness_mm"], "standoff_mm": d,
                "layer": lyr, "height_mm": round(lyr * lh, 2),
                "min_dist_mm": None if cell["min"] is None else round(cell["min"], 3),
                "worst_link": cell["link"], "worst_link_name": LINK_NAMES.get(cell["link"], ""),
                "status": _classify(cell["min"]),
                "reach_frac": round(1.0 - min(n_r, n_s) / n_s, 3) if n_s else None,
            })
        red = coll["n_red"]
        print(f"   d={d:.0f}mm red={red} min={coll['min_distance_mm']:.0f}mm", flush=True)
    return info, grid_rows


def _standoffs(args):
    out = []
    d = args.standoff_min
    while d <= args.standoff_max + 1e-6:
        out.append(round(d, 3))
        d += args.standoff_step
    return out


def _load_env(project):
    from fgc.domain.robot import RobotDef
    from fgc.pipeline.sectionsim import placement_context_for_job
    from fgc.project import load_project, project_dir_for

    artifact = load_project(project_dir_for(project))
    template_job = artifact["print_jobs"][0]
    robot_name = template_job.get("robot") or "doosan_m1013"
    robot = RobotDef.load(robot_name)
    tool = placement_context_for_job(template_job).tool
    return artifact, template_job, robot, robot_name, tool


def run_worker(args) -> int:
    """Ein Wand-Messlauf in eigenem Prozess (isoliert native Crashes)."""
    artifact, template_job, robot, robot_name, tool = _load_env(args.project)
    info, rows = measure_wall(
        artifact, template_job, args.worker_gid, robot, tool, robot_name, _standoffs(args)
    )
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.out_dir) / f"wall_{args.worker_gid}.json").write_text(
        json.dumps({"info": info, "grid": rows}, indent=2), encoding="utf-8"
    )
    return 0


def run_orchestrator(args) -> int:
    """Startet je Wand einen Worker-Subprozess; ein Segfault verliert nur diese Wand."""
    gids = args.gids or DEFAULT_GIDS
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    status = {}
    for gid in gids:
        cmd = [sys.executable, str(Path(__file__).resolve()),
               "--worker-gid", gid, "--project", args.project, "--out-dir", str(out),
               "--standoff-min", str(args.standoff_min), "--standoff-max", str(args.standoff_max),
               "--standoff-step", str(args.standoff_step)]
        print(f"=== Wand {gid} (Subprozess) ===", flush=True)
        rc = subprocess.run(cmd).returncode
        status[gid] = rc
        if rc != 0:
            print(f"[wall {gid}] Subprozess Exit {rc} (nativer Crash?) — übersprungen", flush=True)

    all_grid, infos = [], []
    for gid in gids:
        p = out / f"wall_{gid}.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        infos.append(data["info"])
        all_grid.extend(data["grid"])

    if not all_grid:
        print("[done] keine Ergebnisse — alle Wände fehlgeschlagen", flush=True)
        return 1
    grid_path = out / "grid_thickness.csv"
    with grid_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_grid[0].keys()))
        w.writeheader()
        w.writerows(all_grid)
    meta = {
        "project": args.project, "robot": "doosan_m1013",
        "sweep": {"min": args.standoff_min, "max": args.standoff_max, "step": args.standoff_step},
        "collision_config": {"safety_distance_mm": SAFETY_MM, "freizone_radius_mm": 40.0},
        "scene_mode": "modul", "link_names": LINK_NAMES,
        "walls": infos, "worker_exit_codes": status, "git_commit": _git_commit(),
        "generated_by": "experiments/collision_standoff_sweep/sweep_thickness.py",
    }
    (out / "meta_thickness.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[done] {len(all_grid)} grid rows, {len(infos)}/{len(gids)} Wände ok → {out}", flush=True)
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="denkmal")
    ap.add_argument("--gids", nargs="*", default=None)
    ap.add_argument("--worker-gid", default=None, help="intern: ein Wand-Messlauf im Subprozess")
    ap.add_argument("--standoff-min", type=float, default=150.0)
    ap.add_argument("--standoff-max", type=float, default=1100.0)
    ap.add_argument("--standoff-step", type=float, default=100.0)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "data_thickness"))
    args = ap.parse_args()
    if args.worker_gid:
        return run_worker(args)
    return run_orchestrator(args)


if __name__ == "__main__":
    sys.exit(main())
