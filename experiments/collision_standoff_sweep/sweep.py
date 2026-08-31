"""Abstand-Sweep → kollisionsfreies Höhenfenster + Verursacher-Glied (ein Wandmodul).

Forschungsmessung (paper-tauglich, reproduzierbar): Für EIN reales Wandmodul wird
der Abstand Roboterbasis↔Wandfront (``standoff_mm``) von nah bis fern durchgefahren.
Pro Abstand simuliert der **Produktivpfad** (dieselben Türen wie ``simulate_section``)
den kompletten Modul-Druck bottom→top; der Kollisionsbefund liefert je Bahn-Sample die
signierte Mindestdistanz, das verursachende Glied (0..6, 7=Werkzeug) und — über die
Toolpath-Schicht — die Druckhöhe. Aggregiert ergibt das ein (Abstand × Höhe)-Gitter:
pro Zelle die worst-case Mindestdistanz und das limitierende Glied.

Klassifikation (fgc.collision.check._classify, Sicherheitsabstand 50 mm):
  distance_mm < 0      → rot   (echte Durchdringung / Kollision)
  0 <= distance_mm <50 → gelb  (Sicherheitszone; weicher Lehm ⇒ auch Schaden)
  distance_mm >= 50    → grün  (frei)

Wir speichern die *signierte* Mindestdistanz je Zelle — beide Grenzen (harte
Kollision rot, Sicherheitsabstand grün) sind damit im Nachhinein zeichenbar.

Ausgaben (in --out-dir):
  grid.csv     — je (standoff, layer): height_mm, min_dist_mm, worst_link,
                 worst_against, status
  summary.csv  — je standoff: n_red/yellow/green, min_dist, onset-Höhen,
                 limitierende Glieder unten/oben, Reichweite-Warnungen
  meta.json    — Projekt, Modulmaße, Config, Sweep-Parameter, git-Commit

Aufruf (venv-Python, PYTHONPATH=core/src):
  python experiments/collision_standoff_sweep/sweep.py \
      --standoff-min 150 --standoff-max 1200 --standoff-step 50 --module-index 0
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

# Link-Index (URDF/Manifest doosan_m1013) → Klartext. 0 wird nie geprüft.
LINK_NAMES = {
    0: "base_link",
    1: "link_1",
    2: "link_2",
    3: "link_3",
    4: "link_4",
    5: "link_5",
    6: "link_6",
    7: "tool",
}
SAFETY_MM = 50.0


def _classify(dist_mm: float | None) -> str:
    if dist_mm is None:
        return "green"  # kein Nahpaar ⇒ frei
    if dist_mm < 0.0:
        return "red"
    if dist_mm < SAFETY_MM:
        return "yellow"
    return "green"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]
        ).decode().strip()
    except Exception:
        return "unknown"


def load_module(project: str, module_index: int):
    from fgc.pipeline import actions as A
    from fgc.pipeline import sectionsim as S
    from fgc.project import load_project, project_dir_for

    artifact = load_project(project_dir_for(project))
    job = artifact["print_jobs"][0]
    pc = S.placement_context_for_job(job)
    plan = A.plan_for_job(job, pc.wall, pc.robot, pc.tool, strict_overrides=False).plan
    sp = plan.sections[module_index]
    return S, artifact, job, plan, sp, sp.section.section_id


def aggregate_per_layer(coll: dict, layers: list[int]) -> dict[int, dict]:
    """Je Schicht: worst-case (kleinste) Mindestdistanz + deren Verursacher."""
    per: dict[int, dict] = {}
    dists = coll["distances_mm"]
    links = coll["causer_link"]
    against = coll["causer_against"]
    for i, d in enumerate(dists):
        lyr = layers[i]
        cell = per.get(lyr)
        if cell is None:
            cell = per[lyr] = {"min": None, "link": None, "against": None}
        if d is None:
            continue
        if cell["min"] is None or d < cell["min"]:
            cell["min"] = d
            cell["link"] = links[i]
            cell["against"] = against[i]
    return per


def main() -> int:
    try:  # Windows-Konsole (cp1252) verträgt keine Nicht-ASCII-Ausgabe
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="denkmal")
    ap.add_argument("--module-index", type=int, default=0)
    ap.add_argument("--standoff-min", type=float, default=150.0)
    ap.add_argument("--standoff-max", type=float, default=1200.0)
    ap.add_argument("--standoff-step", type=float, default=50.0)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "data"))
    args = ap.parse_args()

    from fgc.collision.advisor import Override

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    S, artifact, job, plan, sp, sid = load_module(args.project, args.module_index)
    sec = sp.section
    ctx = S.section_sim_context(artifact, job, sid, plan=plan)
    lh = ctx.base_params.layer_height_mm
    planned = ctx.placement

    print(f"[setup] project={args.project} module={args.module_index} section={sid}", flush=True)
    print(f"[setup] len={sec.length_mm:.1f}mm h={sec.height_mm:.1f}mm "
          f"thickness={plan.wall.thickness_mm:.1f}mm layer_height={lh}mm "
          f"planned_standoff={planned.standoff_mm}mm", flush=True)

    standoffs = []
    d = args.standoff_min
    while d <= args.standoff_max + 1e-6:
        standoffs.append(round(d, 3))
        d += args.standoff_step

    grid_rows: list[dict] = []
    summary_rows: list[dict] = []

    for d in standoffs:
        t0 = time.perf_counter()
        comp = S.slice_and_simulate_section(
            artifact, job, sid,
            override=Override(placement={"standoff_mm": float(d)}),
            ctx=ctx,
        )
        traj = comp.trajectory
        from fgc.collision.druckstand import layer_per_sample
        sample_times = [s["t_s"] for s in traj.samples]
        target_times = traj.target_times or []
        target_layers = [int(t.get("layer", 0)) for t in comp.target_dicts]
        layers = layer_per_sample(sample_times, target_times, target_layers)

        coll = S.section_collision_finding(comp, config=None)
        dt = time.perf_counter() - t0
        if coll is None:
            print(f"[d={d:.0f}] coll=None (Geo fehlt?) — übersprungen", flush=True)
            continue

        # Erreichbarkeit je Höhe: jede „reach"-Warnung trägt t_s → über dieselbe
        # Bisektion wie die Samples auf ihre Schicht abbilden (verortete IK-Fehler).
        warn = traj.meta.get("warnings", []) or []
        reach_ts = [w["t_s"] for w in warn
                    if isinstance(w, dict) and w.get("kind") == "reach"]
        reach_layers = (layer_per_sample(reach_ts, target_times, target_layers)
                        if reach_ts else [])
        reach_per_layer = Counter(reach_layers)
        samples_per_layer = Counter(layers)

        per = aggregate_per_layer(coll, layers)
        for lyr in sorted(per):
            cell = per[lyr]
            n_s = samples_per_layer.get(lyr, 0)
            n_r = reach_per_layer.get(lyr, 0)
            grid_rows.append({
                "standoff_mm": d,
                "layer": lyr,
                "height_mm": round(lyr * lh, 2),
                "min_dist_mm": None if cell["min"] is None else round(cell["min"], 3),
                "worst_link": cell["link"],
                "worst_link_name": LINK_NAMES.get(cell["link"], ""),
                "worst_against": cell["against"],
                "status": _classify(cell["min"]),
                "n_samples": n_s,
                "n_reach_warn": n_r,
                "reach_frac": round(1.0 - min(n_r, n_s) / n_s, 3) if n_s else None,
            })

        # onset-Höhen (von unten): niedrigste rote / niedrigste nicht-grüne Schicht
        red_layers = [ly for ly, c in per.items() if _classify(c["min"]) == "red"]
        nong_layers = [ly for ly, c in per.items() if _classify(c["min"]) != "green"]
        green_layers = [ly for ly, c in per.items() if _classify(c["min"]) == "green"]
        # limitierendes Glied unten (unterste rote/gelbe Schicht) und oben (oberste)
        def _limiter(layer_list):
            if not layer_list:
                return None, None
            lyr = layer_list[0]
            return per[lyr]["link"], per[lyr]["against"]
        nong_sorted = sorted(nong_layers)
        low_link, low_against = _limiter(nong_sorted)
        high_link, high_against = (None, None)
        if nong_sorted:
            hl = nong_sorted[-1]
            high_link, high_against = per[hl]["link"], per[hl]["against"]

        warn_kinds = Counter(w.get("kind", "?") for w in warn if isinstance(w, dict))

        summary_rows.append({
            "standoff_mm": d,
            "n_red": coll["n_red"],
            "n_yellow": coll["n_yellow"],
            "n_green": coll["n_green"],
            "min_dist_mm": round(coll["min_distance_mm"], 3),
            "lowest_red_layer": min(red_layers) if red_layers else None,
            "lowest_red_height_mm": round(min(red_layers) * lh, 1) if red_layers else None,
            "lowest_nongreen_layer": min(nong_layers) if nong_layers else None,
            "lowest_nongreen_height_mm": round(min(nong_layers) * lh, 1) if nong_layers else None,
            "highest_green_layer": max(green_layers) if green_layers else None,
            "n_layers": len(per),
            "low_limiter_link": low_link,
            "low_limiter_name": LINK_NAMES.get(low_link, ""),
            "low_limiter_against": low_against,
            "high_limiter_link": high_link,
            "high_limiter_name": LINK_NAMES.get(high_link, ""),
            "high_limiter_against": high_against,
            "warn_reach": warn_kinds.get("reach", 0),
            "warn_joint_limit": warn_kinds.get("joint_limit", 0),
            "warn_singularity": warn_kinds.get("singularity", 0),
            "sim_s": round(dt, 2),
        })
        print(f"[d={d:.0f}mm] red={coll['n_red']} yel={coll['n_yellow']} grn={coll['n_green']} "
              f"min={coll['min_distance_mm']:.1f}mm  low_lim={LINK_NAMES.get(low_link,'-')}"
              f"@{(min(nong_layers)*lh) if nong_layers else 0:.0f}mm  "
              f"warn(reach={warn_kinds.get('reach',0)},sing={warn_kinds.get('singularity',0)})  "
              f"[{dt:.1f}s]", flush=True)

    # --- schreiben ---
    grid_path = out / "grid.csv"
    with grid_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(grid_rows[0].keys()))
        w.writeheader()
        w.writerows(grid_rows)
    sum_path = out / "summary.csv"
    with sum_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    meta = {
        "project": args.project,
        "module_index": args.module_index,
        "section_id": sid,
        "module_length_mm": sec.length_mm,
        "module_height_mm": sec.height_mm,
        "wall_thickness_mm": plan.wall.thickness_mm,
        "layer_height_mm": lh,
        "planned_placement": {
            "standoff_mm": planned.standoff_mm,
            "lateral_mm": planned.lateral_mm,
            "stand_height_mm": planned.stand_height_mm,
            "yaw_rad": planned.yaw_rad,
        },
        "collision_config": {"safety_distance_mm": SAFETY_MM, "freizone_radius_mm": 40.0},
        "scene_mode": "modul",
        "sweep": {"min": args.standoff_min, "max": args.standoff_max, "step": args.standoff_step},
        "n_standoffs": len(summary_rows),
        "link_names": LINK_NAMES,
        "git_commit": _git_commit(),
        "generated_by": "experiments/collision_standoff_sweep/sweep.py",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[done] {len(grid_rows)} grid rows, {len(summary_rows)} standoffs → {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
