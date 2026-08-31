"""W×T-Prädikat-Gitter: druckbar(W,H,T) über synthetische Quader-Module.

Zielgröße H_max(W,T) = max. von unten zusammenhängend machbare Höhe (streng:
reach ≈ 100 % & grün), je (Breite W, Dicke T) optimiert über die drei Hebel
Abstand × Basishöhe × IK-Konfiguration (alle 8, an jeder Basishöhe neu — der
Gewinner verschiebt sich). Modul = EIN synthetischer Quader (kein Weiter-Zerlegen),
über den Produktionspfad (plan_for_job mit leeren Schnitten → eine Section);
geometrie-äquivalent zu realen Wänden (flache Quader).

Modi:
  --validate            : denkmal-nahen Quader (785×900×510) messen, H_max gegen die
                          reale Studie vergleichen (Mechanismus-Check).
  --wt-w W --wt-t T      : Worker — ein (W,T) messen, wall_W_T.json schreiben.
  (ohne)                 : Orchestrator — Gitter über alle (W,T), --jobs parallele Worker.

Aufruf:  PYTHONPATH=core/src python experiments/collision_standoff_sweep/sweep_grid.py --validate
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

WIDTHS = [500.0, 800.0, 1100.0]
THICKS = [100.0, 250.0, 400.0, 550.0]
STANDOFFS = [200.0, 350.0, 500.0, 650.0]
BASE_HEIGHTS = [0.0, 300.0]
BOX_HEIGHT = 900.0
CONFIGS = [(f"{s}{e}{w}", {"shoulder": s, "elbow": e, "wrist": w})
           for s in "ab" for e in "ab" for w in "ab"]  # 8
SAFETY_MM = 50.0
STRICT_REACH = 0.99
LINK_NAMES = {0: "base_link", 1: "link_1", 2: "link_2", 3: "link_3",
              4: "link_4", 5: "link_5", 6: "link_6", 7: "tool"}


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]
        ).decode().strip()
    except Exception:
        return "unknown"


def _env(project="denkmal"):
    from fgc.domain.robot import RobotDef
    from fgc.pipeline.sectionsim import placement_context_for_job
    from fgc.project import load_project, project_dir_for
    artifact = load_project(project_dir_for(project))
    template_job = artifact["print_jobs"][0]
    robot_name = template_job.get("robot") or "doosan_m1013"
    robot = RobotDef.load(robot_name)
    tool = placement_context_for_job(template_job).tool
    return artifact, template_job, robot, robot_name, tool


def build_box_ctx(template_job, robot, tool, robot_name, W, H, T):
    """SectionSimContext eines synthetischen Quaders (W×H×T) als EIN Modul."""
    from dataclasses import replace

    import numpy as np
    import trimesh

    from fgc.decompose import apply
    from fgc.domain.process_params import ProcessWindow, SliceParams, section_slice_overrides
    from fgc.kinematics.opw import OpwKinematics
    from fgc.pipeline import sectionsim as S
    from fgc.pipeline.actions import plan_for_job
    from fgc.placement.evaluate import WallSurface

    box = trimesh.creation.box(extents=[W, T, H])
    box.apply_translation([0.0, 0.0, H / 2.0])  # x zentriert, y zentriert, z ab 0
    verts_w = np.asarray(box.vertices, dtype=float)
    faces = np.asarray(box.faces)

    wall = WallSurface(length_mm=W, height_mm=H, thickness_mm=T, z_offset_mm=0.0)
    job = dict(template_job)
    job["wall_global_id"] = "synthetic"
    job["decomposition_kind"] = "modul"
    job["cuts"] = []          # leere Schnitte -> from_cuts -> genau eine Section
    job.pop("section_overrides", None)

    plan = plan_for_job(job, wall, robot, tool, strict_overrides=False).plan
    if len(plan.sections) != 1:
        raise ValueError(f"Erwartete 1 Section, bekam {len(plan.sections)} (W={W},H={H},T={T})")
    section = plan.sections[0].section
    placement = replace(plan.sections[0].placement, lateral_mm=0.0)  # zentral erzwingen

    mesh = trimesh.Trimesh(vertices=verts_w, faces=faces, process=False)
    parts = apply(mesh, plan)
    part = parts[0]
    v = np.asarray(part.vertices, dtype=float).copy()
    v[:, 0] -= section.center_x_mm
    v[:, 2] -= section.z0_mm

    window = ProcessWindow.load()
    base_params = SliceParams.from_window(window, **section_slice_overrides(job, section.section_id))
    ctx = S.SectionSimContext(
        robot_name=robot_name, tool=tool, plan=plan, section=section, placement=placement,
        verts=v, part_faces=part.faces, earlier_parts=[],
        section_z0_mm=plan.sim_z0_mm(section), base_params=base_params,
        kin=OpwKinematics.from_robot(robot_name),
    )
    return ctx, job, section


def measure(artifact, template_job, robot, robot_name, tool, W, T, standoffs, base_heights):
    from fgc.collision.advisor import Override
    from fgc.collision.druckstand import layer_per_sample
    from fgc.pipeline import sectionsim as S

    ctx, job, section = build_box_ctx(template_job, robot, tool, robot_name, W, BOX_HEIGHT, T)
    sid = section.section_id
    lh = ctx.base_params.layer_height_mm
    rows = []
    for bh in base_heights:
        for cfg_label, cfg_block in CONFIGS:
            for d in standoffs:
                ov = Override(placement={"standoff_mm": float(d), "stand_height_mm": float(bh)},
                              ik_config=cfg_block)
                try:
                    comp = S.slice_and_simulate_section(artifact, job, sid, override=ov, ctx=ctx)
                except Exception:  # noqa: BLE001
                    continue
                traj = comp.trajectory
                st = [s["t_s"] for s in traj.samples]
                tt = traj.target_times or []
                tl = [int(t.get("layer", 0)) for t in comp.target_dicts]
                layers = layer_per_sample(st, tt, tl)
                coll = S.section_collision_finding(comp, config=None)
                if coll is None:
                    continue
                warn = traj.meta.get("warnings", []) or []
                rts = [w["t_s"] for w in warn if isinstance(w, dict) and w.get("kind") == "reach"]
                rpl = Counter(layer_per_sample(rts, tt, tl) if rts else [])
                spl = Counter(layers)
                per = {}
                for i, dd in enumerate(coll["distances_mm"]):
                    ly = layers[i]
                    c = per.setdefault(ly, [None])
                    if dd is not None and (c[0] is None or dd < c[0]):
                        c[0] = dd
                for ly in sorted(per):
                    n_s = spl.get(ly, 0)
                    n_r = rpl.get(ly, 0)
                    rows.append({
                        "W": W, "T": T, "base_height_mm": bh, "config": cfg_label,
                        "standoff_mm": d, "layer": ly, "height_mm": round(ly * lh, 1),
                        "min_dist_mm": None if per[ly][0] is None else round(per[ly][0], 3),
                        "reach_frac": round(1.0 - min(n_r, n_s) / n_s, 3) if n_s else None,
                    })
    return rows, {"W": W, "T": T, "box_height_mm": BOX_HEIGHT, "layer_height_mm": lh,
                  "module_length_mm": section.length_mm, "module_height_mm": section.height_mm}


def hmax_from_rows(rows, lh):
    """best-EINZEL-Konfig H_max (streng) + Gewinner, aus den Zeilen EINER (W,T)."""
    import numpy as np
    bases = sorted({r["base_height_mm"] for r in rows})
    standoffs = sorted({r["standoff_mm"] for r in rows})
    layers = sorted({r["layer"] for r in rows})
    heights = [ly * lh for ly in layers]
    full = max(heights) + lh
    si = {d: i for i, d in enumerate(standoffs)}
    li = {ly: j for j, ly in enumerate(layers)}
    best = (0.0, None, None, None)  # h, base, config, standoff
    for bh in bases:
        for cfg_label, _ in CONFIGS:
            d = np.full((len(layers), len(standoffs)), np.nan)
            rf = np.full((len(layers), len(standoffs)), np.nan)
            for r in rows:
                if r["base_height_mm"] != bh or r["config"] != cfg_label:
                    continue
                i, j = li[r["layer"]], si[r["standoff_mm"]]
                d[i, j] = np.nan if r["min_dist_mm"] is None else r["min_dist_mm"]
                rf[i, j] = np.nan if r["reach_frac"] is None else r["reach_frac"]
            feas = ((d >= 50.0) | np.isnan(d)) & (rf >= STRICT_REACH)
            for jx in range(len(standoffs)):
                h = full
                for iy in range(len(heights)):
                    if not feas[iy, jx]:
                        h = heights[iy]
                        break
                if h > best[0]:
                    best = (h, bh, cfg_label, standoffs[jx])
    return best


def run_validate(args):
    artifact, template_job, robot, robot_name, tool = _env(args.project)
    rows, info = measure(artifact, template_job, robot, robot_name, tool,
                         785.0, 510.0, [150.0, 300.0, 450.0, 600.0, 750.0], [0.0])
    h, bh, cfg, d = hmax_from_rows(rows, info["layer_height_mm"])
    print(f"[validate] synth 785×900×510 @ base0: H_max={h:.0f}mm (cfg {cfg}, standoff {d:.0f})")
    print(f"[validate] Real (Studie IK-Pilot, base0): H_max≈450-490mm (cfg baa). "
          f"{'OK — reproduziert' if 380 <= h <= 560 else 'ABWEICHUNG prüfen'}")
    return 0


def run_worker(args):
    artifact, template_job, robot, robot_name, tool = _env(args.project)
    rows, info = measure(artifact, template_job, robot, robot_name, tool,
                         args.wt_w, args.wt_t, STANDOFFS, BASE_HEIGHTS)
    info["hmax"] = hmax_from_rows(rows, info["layer_height_mm"])
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"wall_{int(args.wt_w)}_{int(args.wt_t)}.json").write_text(
        json.dumps({"info": info, "grid": rows}, indent=2), encoding="utf-8")
    print(f"[worker] W={args.wt_w:.0f} T={args.wt_t:.0f} H_max={info['hmax'][0]:.0f}mm "
          f"(cfg {info['hmax'][2]}, base {info['hmax'][1]}, {len(rows)} rows)", flush=True)
    return 0


def run_orchestrator(args):
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    combos = [(w, t) for t in THICKS for w in WIDTHS]
    running = []
    done = 0

    def launch(w, t):
        cmd = [sys.executable, str(Path(__file__).resolve()), "--wt-w", str(w), "--wt-t", str(t),
               "--project", args.project, "--out-dir", str(out)]
        return subprocess.Popen(cmd)

    queue = list(combos)
    while queue or running:
        while queue and len(running) < args.jobs:
            w, t = queue.pop(0)
            print(f"=== launch W={w:.0f} T={t:.0f} ({len(combos)-len(queue)}/{len(combos)}) ===",
                  flush=True)
            running.append(((w, t), launch(w, t)))
        still = []
        for (w, t), p in running:
            rc = p.poll()
            if rc is None:
                still.append(((w, t), p))
            else:
                done += 1
                if rc != 0:
                    print(f"[orch] W={w:.0f} T={t:.0f} Exit {rc}", flush=True)
        running = still
        if running:
            running[0][1].wait(timeout=None)  # auf mind. einen warten (Busy-Loop vermeiden)

    all_rows, infos = [], []
    for w, t in combos:
        p = out / f"wall_{int(w)}_{int(t)}.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        infos.append(data["info"])
        all_rows.extend(data["grid"])
    if not all_rows:
        print("[done] keine Ergebnisse")
        return 1
    with (out / "grid_wt.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    meta = {"project": args.project, "widths": WIDTHS, "thicks": THICKS,
            "standoffs": STANDOFFS, "base_heights": BASE_HEIGHTS, "box_height_mm": BOX_HEIGHT,
            "configs": [c[0] for c in CONFIGS], "strict_reach": STRICT_REACH,
            "safety_mm": SAFETY_MM, "link_names": LINK_NAMES,
            "hmax_by_wt": {f"{int(i['W'])}_{int(i['T'])}": i["hmax"] for i in infos},
            "git_commit": _git_commit(),
            "generated_by": "experiments/collision_standoff_sweep/sweep_grid.py"}
    (out / "meta_wt.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[done] {len(all_rows)} rows, {len(infos)}/{len(combos)} (W,T) → {out}", flush=True)
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="denkmal")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--wt-w", type=float, default=None)
    ap.add_argument("--wt-t", type=float, default=None)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "data_grid"))
    args = ap.parse_args()
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    if args.validate:
        return run_validate(args)
    if args.wt_w is not None and args.wt_t is not None:
        return run_worker(args)
    return run_orchestrator(args)


if __name__ == "__main__":
    sys.exit(main())
