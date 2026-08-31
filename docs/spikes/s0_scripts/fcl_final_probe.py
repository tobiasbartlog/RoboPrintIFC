"""Spike S0 — Abschlussmessung: Volllauf mit dem S1-Kandidaten.

Strategie (aus den Vorsonden abgeleitet):
  1. Breitphase: konvexe Hülle je Glied, min-Distanz (untere Schranke der
     echten Distanz). hull_d > Sicherheitsabstand → Sample grün, fertig.
  2. Nahphase: VHACD-Konvexzerlegung je Glied (formtreu ±5 mm, konvex-schnell)
     liefert die berichtete Distanz inkl. Vorzeichen.

Volllauf über alle Samples der echten trajectory.json; Ergebnis: Gesamtzeit,
Distanzkurve, Intervalle unter den Schwellen (0 mm / 50 mm).

Aufruf: .venv/Scripts/python.exe docs/spikes/s0_scripts/fcl_final_probe.py runs/<lauf>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
from trimesh.collision import CollisionManager

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fcl_perf_probe import (  # noqa: E402
    REPO,
    TOOL_JSON,
    build_druckstand,
    frame_matrix,
    load_link_collision_meshes,
)

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

    report: dict = {"run": run_dir.name, "n_samples": len(samples)}

    # Geometrie vorbereiten (offline-Anteil, in S1 gecacht im robot_geometry-Artefakt)
    t0 = time.perf_counter()
    link_meshes = load_link_collision_meshes()
    hull_meshes = [m.convex_hull for m in link_meshes]
    vhacd_pieces: list[list[trimesh.Trimesh]] = []
    for m in link_meshes:
        pieces = m.convex_decomposition()
        if isinstance(pieces, trimesh.Trimesh):
            pieces = [pieces]
        vhacd_pieces.append(pieces)
    report["t_geometry_prep_s"] = round(time.perf_counter() - t0, 1)

    wall = trimesh.Trimesh(
        vertices=np.array(wallspec["geometry"]["vertices_mm"], dtype=float),
        faces=np.array(wallspec["geometry"]["faces"], dtype=int),
        process=True,
    )
    floor = trimesh.creation.box(extents=[6000, 6000, 200])
    floor.apply_translation([0, 0, -100])

    # FK über alle Samples
    kin = OpwKinematics.from_robot("doosan_m1013")
    t0 = time.perf_counter()
    all_frames = np.empty((len(samples), 7, 4, 4))
    for k in range(len(samples)):
        fs = kin.link_frames(joints[k])
        for i, f in enumerate(fs):
            all_frames[k, i] = base_mat @ frame_matrix(f.pos_mm, f.quat)
    report["t_fk_s"] = round(time.perf_counter() - t0, 1)

    tcp_z = np.einsum("kij,j->ki", all_frames[:, 6], tcp_mat[:, 3])[:, 2]
    ds_top = np.clip(np.floor(tcp_z / layer_h) * layer_h, 0.0, None)

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

    hull_cm = CollisionManager()
    for i in ARM_LINKS:
        hull_cm.add_object(f"link{i}", hull_meshes[i])
    vhacd_cm = CollisionManager()
    vhacd_names: list[tuple[str, int]] = []
    for i in ARM_LINKS:
        for p_idx, piece in enumerate(vhacd_pieces[i]):
            name = f"link{i}_p{p_idx}"
            vhacd_cm.add_object(name, piece)
            vhacd_names.append((name, i))

    # Volllauf
    t0 = time.perf_counter()
    dists = np.empty(len(samples))
    n_near = 0
    for k in range(len(samples)):
        obst = obstacles_for(float(ds_top[k]))
        for i in ARM_LINKS:
            hull_cm.set_transform(f"link{i}", all_frames[k, i])
        hull_d = hull_cm.min_distance_other(obst)
        if hull_d > SAFETY_MM:
            dists[k] = hull_d
            continue
        n_near += 1
        for name, i in vhacd_names:
            vhacd_cm.set_transform(name, all_frames[k, i])
        dists[k] = vhacd_cm.min_distance_other(obst)
    t_full = time.perf_counter() - t0

    below0 = dists <= 0
    below50 = dists < SAFETY_MM
    # verdichtete Intervalle (rot) wie im künftigen Artefakt
    edges = np.flatnonzero(np.diff(below0.astype(int)))
    n_intervals_red = int((len(edges) + (1 if below0[0] else 0) + (1 if below0[-1] else 0)) // 2)

    report["full_run"] = {
        "t_total_s": round(t_full, 1),
        "per_sample_ms": round(t_full / len(samples) * 1000, 3),
        "near_share": round(n_near / len(samples), 3),
        "min_dist_mm": round(float(dists.min()), 2),
        "n_below_0": int(below0.sum()),
        "n_below_50": int(below50.sum()),
        "n_red_intervals": n_intervals_red,
    }
    out = Path(__file__).parent / "last_final_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
