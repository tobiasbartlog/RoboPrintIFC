"""IK-Pilot: Abstand-Sweep über alle 8 IK-Konfigurationen (ein Modul).

Beantwortet die Gültigkeitsfrage: Sind die in `sweep.py` gemessenen Kollisionen
Artefakte der Konfigurationswahl? Für EIN Modul (Default: denkmal Modul 0,
785×822 @ 510 mm) wird der Abstand-Sweep für jede der 8 IK-Konfigurationen
(shoulder×elbow×wrist ∈ {a,b}³) plus die auto-Baseline gefahren; base=0,
lateral=0 (nur IK variiert, sauberer A/B gegen die Standard-Konfig `fig4`).

`best-over-8` je (Abstand, Höhe): gibt es IRGENDEINE Konfig, die dort erreichbar
UND kollisionsfrei ist? Die Differenz zur auto-Baseline = der IK-Gewinn.

Ausgabe: data_ik/grid_ik.csv (config, standoff, layer, height, min_dist, reach_frac),
data_ik/meta_ik.json. Auswertung/Plots in ik_plots.py.

Aufruf:  PYTHONPATH=core/src python experiments/collision_standoff_sweep/sweep_ik.py \
             --standoff-min 150 --standoff-max 1150 --standoff-step 100
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

LINK_NAMES = {0: "base_link", 1: "link_1", 2: "link_2", 3: "link_3",
              4: "link_4", 5: "link_5", 6: "link_6", 7: "tool"}
SAFETY_MM = 50.0

# auto-Baseline (kein ik_config-Override) + alle 8 diskreten Konfigurationen.
CONFIGS = [("auto", None)] + [
    (f"{s}{e}{w}", {"shoulder": s, "elbow": e, "wrist": w})
    for s in ("a", "b") for e in ("a", "b") for w in ("a", "b")
]


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
            cell = per[lyr] = {"min": None, "link": None}
        if d is None:
            continue
        if cell["min"] is None or d < cell["min"]:
            cell["min"] = d
            cell["link"] = coll["causer_link"][i]
    return per


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="denkmal")
    ap.add_argument("--module-index", type=int, default=0)
    ap.add_argument("--standoff-min", type=float, default=150.0)
    ap.add_argument("--standoff-max", type=float, default=1150.0)
    ap.add_argument("--standoff-step", type=float, default=100.0)
    ap.add_argument("--base-heights", nargs="*", type=float, default=[0.0],
                    help="Basishöhen (Aufstellhöhe der Roboterbasis, mm); je Höhe über alle 8 Konfigs")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "data_ik"))
    args = ap.parse_args()
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)  # früh: Tee-Log braucht das Verzeichnis

    from fgc.collision.advisor import Override
    from fgc.collision.druckstand import layer_per_sample
    from fgc.pipeline import actions as A
    from fgc.pipeline import sectionsim as S
    from fgc.project import load_project, project_dir_for

    artifact = load_project(project_dir_for(args.project))
    job = artifact["print_jobs"][0]
    pc = S.placement_context_for_job(job)
    plan = A.plan_for_job(job, pc.wall, pc.robot, pc.tool, strict_overrides=False).plan
    sp = plan.sections[args.module_index]
    sec = sp.section
    sid = sec.section_id
    ctx = S.section_sim_context(artifact, job, sid, plan=plan)
    lh = ctx.base_params.layer_height_mm
    print(f"[setup] module={sid} {sec.length_mm:.0f}x{sec.height_mm:.0f}mm "
          f"thickness={plan.wall.thickness_mm:.0f}mm base={ctx.placement.stand_height_mm}mm "
          f"lateral={ctx.placement.lateral_mm}mm layer_h={lh}mm", flush=True)

    standoffs = []
    d = args.standoff_min
    while d <= args.standoff_max + 1e-6:
        standoffs.append(round(d, 3))
        d += args.standoff_step

    grid_rows = []
    for bh, (cfg_label, cfg_block), d in (
        (bh, cfg, d)
        for bh in args.base_heights
        for cfg in CONFIGS
        for d in standoffs
    ):
        pl = {"standoff_mm": float(d), "stand_height_mm": float(bh)}
        ov = Override(placement=pl, ik_config=cfg_block) if cfg_block else Override(placement=pl)
        try:
            comp = S.slice_and_simulate_section(artifact, job, sid, override=ov, ctx=ctx)
        except Exception as e:  # noqa: BLE001 — unfahrbare Konfig: Zelle als leer überspringen
            print(f"   base={bh:.0f} cfg={cfg_label} d={d:.0f} build-Fehler {e!r}", flush=True)
            continue
        traj = comp.trajectory
        sample_times = [s["t_s"] for s in traj.samples]
        target_times = traj.target_times or []
        target_layers = [int(t.get("layer", 0)) for t in comp.target_dicts]
        layers = layer_per_sample(sample_times, target_times, target_layers)
        coll = S.section_collision_finding(comp, config=None)
        if coll is None:
            continue
        warn = traj.meta.get("warnings", []) or []
        reach_ts = [w["t_s"] for w in warn
                    if isinstance(w, dict) and w.get("kind") == "reach"]
        reach_pl = Counter(layer_per_sample(reach_ts, target_times, target_layers)
                           if reach_ts else [])
        spl = Counter(layers)
        per = aggregate_per_layer(coll, layers)
        for lyr in sorted(per):
            cell = per[lyr]
            n_s = spl.get(lyr, 0)
            n_r = reach_pl.get(lyr, 0)
            grid_rows.append({
                "base_height_mm": bh, "config": cfg_label, "standoff_mm": d, "layer": lyr,
                "height_mm": round(lyr * lh, 2),
                "min_dist_mm": None if cell["min"] is None else round(cell["min"], 3),
                "worst_link": cell["link"], "worst_link_name": LINK_NAMES.get(cell["link"], ""),
                "status": _classify(cell["min"]),
                "reach_frac": round(1.0 - min(n_r, n_s) / n_s, 3) if n_s else None,
            })
        print(f"   base={bh:.0f}mm cfg={cfg_label} d={d:.0f}mm red={coll['n_red']} "
              f"min={coll['min_distance_mm']:.0f}mm", flush=True)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "grid_ik.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(grid_rows[0].keys()))
        w.writeheader()
        w.writerows(grid_rows)
    meta = {
        "project": args.project, "module_index": args.module_index, "section_id": sid,
        "module_length_mm": sec.length_mm, "module_height_mm": sec.height_mm,
        "wall_thickness_mm": plan.wall.thickness_mm, "layer_height_mm": lh,
        "lateral_mm": ctx.placement.lateral_mm, "base_heights_mm": list(args.base_heights),
        "configs": [c[0] for c in CONFIGS],
        "collision_config": {"safety_distance_mm": SAFETY_MM, "freizone_radius_mm": 40.0},
        "sweep": {"min": args.standoff_min, "max": args.standoff_max, "step": args.standoff_step},
        "link_names": LINK_NAMES, "git_commit": _git_commit(),
        "generated_by": "experiments/collision_standoff_sweep/sweep_ik.py",
    }
    (out / "meta_ik.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[done] {len(grid_rows)} rows, {len(CONFIGS)} configs × {len(standoffs)} standoffs "
          f"-> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
