"""Spike S0 — Zusatzmessung: Urteilsgeometrie-Varianten (exakt / dezimiert / VHACD).

Der Hybrid-Vorfilter allein reicht nicht (32 ms je exakter Nahdistanz bei
3k–47k Dreiecken je Glied). Kandidaten für die Urteilsgeometrie:

  A  exakte URDF-Kollisionsmeshes      (Referenz — langsam)
  D  quadric-dezimiert auf ~1500 Faces (fast-simplification; nicht einhüllend,
                                        Fehler in beide Richtungen möglich)
  E  VHACD-Konvexzerlegung je Glied    (vhacdx; nahezu formtreu, viele kleine
                                        konvexe Stücke → schnelle Queries)

Je Variante: min-Distanz je Sample auf der Teilmenge (gleiche Posen wie die
Hauptsonde), Timing + Abweichung gegen Referenz A (nur getrennte Samples) +
Fehlklassifikationen an den Schwellen 0 mm / 50 mm.

Aufruf: .venv/Scripts/python.exe docs/spikes/s0_scripts/fcl_geometry_probe.py runs/<lauf>
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

ARM_LINKS = list(range(1, 7))
DECIMATE_FACES = 1500


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

    report: dict = {}

    # Variante D: dezimiert
    t0 = time.perf_counter()
    deci_meshes = []
    for m in link_meshes:
        if len(m.faces) > DECIMATE_FACES:
            deci_meshes.append(m.simplify_quadric_decimation(face_count=DECIMATE_FACES))
        else:
            deci_meshes.append(m)
    report["t_decimate_s"] = round(time.perf_counter() - t0, 2)
    report["deci_faces"] = [int(len(m.faces)) for m in deci_meshes]

    # Variante E: VHACD-Konvexzerlegung (Stücke je Glied)
    t0 = time.perf_counter()
    vhacd_pieces: list[list[trimesh.Trimesh]] = []
    for m in link_meshes:
        pieces = m.convex_decomposition()
        if isinstance(pieces, trimesh.Trimesh):
            pieces = [pieces]
        vhacd_pieces.append(pieces)
    report["t_vhacd_s"] = round(time.perf_counter() - t0, 2)
    report["vhacd_pieces"] = [len(p) for p in vhacd_pieces]
    report["vhacd_faces_total"] = [int(sum(len(x.faces) for x in p)) for p in vhacd_pieces]

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

    def run_variant(label: str, add_objects) -> np.ndarray:
        """add_objects(cm, set_pose_fns) baut den Arm-Manager; misst die Teilmenge."""
        cm = CollisionManager()
        setters = add_objects(cm)
        t0 = time.perf_counter()
        dists = np.empty(len(subset))
        for idx, k in enumerate(subset):
            for setter in setters:
                setter(cm, frames[k])
            d = cm.min_distance_other(obstacles_for(ds_top[k]))
            dists[idx] = d
        dt = time.perf_counter() - t0
        report[label] = {"per_sample_ms": round(dt / len(subset) * 1000, 3)}
        return dists

    def whole_mesh_objects(meshes):
        def add(cm):
            setters = []
            for i in ARM_LINKS:
                cm.add_object(f"link{i}", meshes[i])
                setters.append(lambda cm, fr, i=i: cm.set_transform(f"link{i}", fr[i]))
            return setters

        return add

    def vhacd_objects(pieces_per_link):
        def add(cm):
            setters = []
            for i in ARM_LINKS:
                for p_idx, piece in enumerate(pieces_per_link[i]):
                    name = f"link{i}_p{p_idx}"
                    cm.add_object(name, piece)
                    setters.append(
                        lambda cm, fr, i=i, name=name: cm.set_transform(name, fr[i])
                    )
            return setters

        return add

    d_exact = run_variant("A_exakt", whole_mesh_objects(link_meshes))
    d_deci = run_variant("D_dezimiert", whole_mesh_objects(deci_meshes))
    d_vhacd = run_variant("E_vhacd", vhacd_objects(vhacd_pieces))

    def compare(label: str, d_var: np.ndarray) -> None:
        sep = d_exact > 0
        err = d_var[sep] - d_exact[sep]
        report[label]["vs_exakt_sep"] = {
            "max_overestimate_mm": round(float(err.max()), 2),
            "max_underestimate_mm": round(float(err.min()), 2),
            "mean_abs_mm": round(float(np.abs(err).mean()), 2),
        }
        report[label]["n_below_0"] = int((d_var <= 0).sum())
        report[label]["n_below_50"] = int((d_var < 50).sum())
        report[label]["missed_collisions"] = int(((d_var > 0) & (d_exact <= 0)).sum())
        report[label]["false_collisions"] = int(((d_var <= 0) & (d_exact > 0)).sum())

    report["A_exakt"]["n_below_0"] = int((d_exact <= 0).sum())
    report["A_exakt"]["n_below_50"] = int((d_exact < 50).sum())
    compare("D_dezimiert", d_deci)
    compare("E_vhacd", d_vhacd)

    out = Path(__file__).parent / "last_geometry_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
