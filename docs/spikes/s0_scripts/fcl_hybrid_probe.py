"""Spike S0 — Zusatzmessung: Hybrid-Strategie Hülle-Vorfilter + exakte Nahdistanz.

Idee (Kandidat für S1): die konvexe Hülle je Glied *enthält* das exakte Mesh,
ihre Distanz zum Hindernis ist also eine **untere Schranke** der echten
Distanz. Damit:

  1. Hüllen-Distanz je Sample (billig, ~0,06 ms).
  2. hull_d > Sicherheitsabstand  → Sample sicher grün, echte Distanz ≥ hull_d.
  3. sonst exakt:
     a) binäre Kollisionsabfrage (exakte Meshes, ohne Eindringtiefe) — rot?
     b) wenn getrennt: exakte min-Distanz (nur getrennte Paare sind billig).
     c) wenn kollidierend: Eindringtiefe aus der Hülle (konservativ) statt
        teurer exakter signierter Distanz.

Misst je Klasse Häufigkeit + Kosten und projiziert den Volllauf.

Aufruf: .venv/Scripts/python.exe docs/spikes/s0_scripts/fcl_hybrid_probe.py runs/<lauf>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from trimesh.collision import CollisionManager

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fcl_perf_probe import (  # noqa: E402
    REPO,
    TOOL_JSON,
    build_druckstand,
    frame_matrix,
    load_link_collision_meshes,
)

import trimesh  # noqa: E402

from fgc.kinematics.opw import OpwKinematics  # noqa: E402

SAFETY_MM = 50.0
ARM_LINKS = list(range(1, 7))


def main() -> None:
    run_dir = REPO / (sys.argv[1] if len(sys.argv) > 1 else "runs/20260708-161603_slice_Denkmal")
    traj = json.loads((run_dir / "trajectory.json").read_text(encoding="utf-8"))
    wallspec = json.loads((run_dir / "wallspec.json").read_text(encoding="utf-8"))
    toolpath = json.loads((run_dir / "toolpath.json").read_text(encoding="utf-8"))
    layer_h = float(toolpath["params"]["layer_height_mm"])

    samples = traj["samples"]
    joints = np.array([s["joints_rad"] for s in samples])
    base_mat = frame_matrix(traj["meta"]["base_frame"]["pos_mm"], traj["meta"]["base_frame"]["quat"])
    tool = json.loads(TOOL_JSON.read_text(encoding="utf-8"))
    tcp_mat = frame_matrix(tool["tcp_frame"]["pos_mm"], tool["tcp_frame"]["quat"])

    link_meshes = load_link_collision_meshes()
    hull_meshes = [m.convex_hull for m in link_meshes]
    wall = trimesh.Trimesh(
        vertices=np.array(wallspec["geometry"]["vertices_mm"], dtype=float),
        faces=np.array(wallspec["geometry"]["faces"], dtype=int),
        process=True,
    )
    floor = trimesh.creation.box(extents=[6000, 6000, 200])
    floor.apply_translation([0, 0, -100])

    kin = OpwKinematics.from_robot("doosan_m1013")
    stride = max(1, len(samples) // 1000)
    subset = list(range(0, len(samples), stride))

    frames = {}
    for k in subset:
        fs = kin.link_frames(joints[k])
        frames[k] = [base_mat @ frame_matrix(f.pos_mm, f.quat) for f in fs]

    tcp_z = {k: float((frames[k][6] @ tcp_mat)[2, 3]) for k in subset}
    ds_top = {k: max(0.0, np.floor(tcp_z[k] / layer_h) * layer_h) for k in subset}

    obst_cache: dict[float, CollisionManager] = {}

    def obstacles_for(top: float) -> CollisionManager:
        if top not in obst_cache:
            cm = CollisionManager()
            cm.add_object("floor", floor)
            ds = build_druckstand(wall, top)
            if ds is not None:
                cm.add_object("druckstand", ds)
            obst_cache[top] = cm
        return obst_cache[top]

    def make_cm(meshes):
        cm = CollisionManager()
        for i in ARM_LINKS:
            cm.add_object(f"link{i}", meshes[i])
        return cm

    hull_cm = make_cm(hull_meshes)
    exact_cm = make_cm(link_meshes)

    def set_pose(cm, k):
        for i in ARM_LINKS:
            cm.set_transform(f"link{i}", frames[k][i])

    stats = {
        "far": {"n": 0, "t": 0.0},          # hull_d > SAFETY -> fertig
        "near_sep": {"n": 0, "t": 0.0},     # exakt getrennt -> exakte Distanz
        "colliding": {"n": 0, "t": 0.0},    # exakt kollidierend -> binär + Hüllen-Tiefe
    }
    t_hull_total = 0.0
    results = []

    for k in subset:
        obst = obstacles_for(ds_top[k])
        t0 = time.perf_counter()
        set_pose(hull_cm, k)
        hull_d, hull_names = hull_cm.min_distance_other(obst, return_names=True)
        t_hull_total += time.perf_counter() - t0

        if hull_d > SAFETY_MM:
            stats["far"]["n"] += 1
            results.append(hull_d)
            continue

        t0 = time.perf_counter()
        set_pose(exact_cm, k)
        hit = exact_cm.in_collision_other(obst)
        if hit:
            dt = time.perf_counter() - t0
            stats["colliding"]["n"] += 1
            stats["colliding"]["t"] += dt
            results.append(min(hull_d, 0.0))  # Hüllen-Tiefe als konservative Zahl
        else:
            d, names = exact_cm.min_distance_other(obst, return_names=True)
            dt = time.perf_counter() - t0
            stats["near_sep"]["n"] += 1
            stats["near_sep"]["t"] += dt
            results.append(d)

    n = len(subset)
    hull_ms = t_hull_total / n * 1000
    per_class = {
        label: {
            "n": s["n"],
            "share": round(s["n"] / n, 3),
            "ms_each": round(s["t"] / s["n"] * 1000, 3) if s["n"] else None,
        }
        for label, s in stats.items()
    }
    total_ms_per_sample = hull_ms + sum(s["t"] for s in stats.values()) / n * 1000
    report = {
        "subset_n": n,
        "hull_ms_per_sample": round(hull_ms, 3),
        "classes": per_class,
        "hybrid_ms_per_sample": round(total_ms_per_sample, 3),
        "projected_full_run_s": round(total_ms_per_sample * len(samples) / 1000, 1),
        "min_reported_mm": round(float(min(results)), 2),
        "n_below_0": int(sum(1 for d in results if d <= 0)),
        "n_below_50": int(sum(1 for d in results if d < SAFETY_MM)),
    }
    out = Path(__file__).parent / "last_hybrid_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
