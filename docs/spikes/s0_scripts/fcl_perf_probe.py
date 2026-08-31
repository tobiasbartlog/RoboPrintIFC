"""Spike S0 (PRD #124) — python-fcl auf Windows: Distanz-Performance mit echter trajectory.json.

Misst, was ADR-024 vorsieht: je Bahn-Sample der minimale Abstand aller
Armglieder (exakte URDF-Kollisionsmeshes, python-fcl via trimesh) gegen den
wachsenden Druckstand (echte Wandgeometrie aus wallspec.json, je Schicht bei
z gekappt) + Boden. Kein Produktionscode — reine Messsonde.

Aufruf (Repo-Root, venv):

    .venv/Scripts/python.exe docs/spikes/s0_scripts/fcl_perf_probe.py runs/<lauf>

Gemessen wird:
  1. Mesh-Laden + BVH-Aufbau (Kollisionsmeshes je Glied, DH-Frame-Offsets
     exakt wie convert_robot_meshes.py — dieselbe Offset-Formel, importiert).
  2. FK (link_frames) über alle Samples; TCP je Sample aus dem Tool-TCP
     (tools/30gut.json — derselbe Wert, den die Simulation als setup["tcp"]
     verwendet hat). Die Schichtzuordnung läuft über die TCP-Höhe:
     Druckstand-Oberkante = floor(tcp_z / schichthöhe) · schichthöhe.
  3. Distanz je Sample, zwei Geometrie-Varianten auf einer Teilmenge
     (A exakte Meshes, B konvexe Hüllen je Glied), danach Volllauf mit A.
     Glied 0 (Basis) ist ausgenommen — Basis↔Boden ist erlaubter Dauerkontakt
     (montiert) und stünde sonst als ewige Pseudo-Kollision im Minimum.
  4. Selbstkollision: nicht-benachbarte Gliedpaare (|i−j| ≥ 2) paarweise,
     auf Teilmenge — benachbarte Glieder teilen sich das Gelenk und berühren
     sich konstruktiv.
  5. Determinismus (gleiche Pose zweimal + Manager-Neuaufbau → bitgleich?).
  6. Tunneling-Kennzahl: max. TCP-Schrittweite zwischen Nachbar-Samples.
"""

from __future__ import annotations

import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh
from trimesh.collision import CollisionManager

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "core" / "scripts"))

import convert_robot_meshes as crm  # noqa: E402  (Offset-Formel wiederverwenden)
from fgc.kinematics.opw import OpwKinematics, _quat_to_rot  # noqa: E402

MM = 1000.0
TOOL_JSON = REPO / "tools" / "30gut.json"


def parse_collision_entries(urdf_path: Path):
    """Wie crm._parse_urdf, aber für die <collision>-Elemente je Glied."""
    root = ET.parse(urdf_path).getroot()
    links = {ln.get("name"): ln for ln in root.findall("link")}
    out: dict[str, list[tuple[Path, np.ndarray, float]]] = {}
    for name in crm.LINK_ORDER:
        entries = []
        for coll in links[name].findall("collision"):
            origin_mm = crm._origin_matrix_mm(coll.find("origin"))
            mesh_el = coll.find("geometry/mesh")
            if mesh_el is None:
                continue
            filename = mesh_el.get("filename", "")
            assert filename.startswith(crm.MESH_PACKAGE_PREFIX), filename
            rel = filename[len(crm.MESH_PACKAGE_PREFIX) :]
            scale = 1.0
            if mesh_el.get("scale"):
                sx, sy, sz = (float(v) for v in mesh_el.get("scale").split())
                assert sx == sy == sz
                scale = sx
            entries.append((crm.MESH_ROOT / rel, origin_mm, scale))
        out[name] = entries
    return out


def load_link_collision_meshes() -> list[trimesh.Trimesh]:
    """Kollisionsmesh je Glied, Vertices im DH-Gliedframe (worldV = frames[i]·v)."""
    joint_origin_mm, _ = crm._parse_urdf(crm.URDF_PATH)
    offsets = crm._link_offsets_mm(joint_origin_mm)
    coll_entries = parse_collision_entries(crm.URDF_PATH)
    meshes = []
    for i, name in enumerate(crm.LINK_ORDER):
        parts = []
        for mesh_path, origin_mm, scale in coll_entries[name]:
            m = trimesh.load(mesh_path, force="mesh", process=False)
            m.apply_scale(scale * MM)
            m.apply_transform(origin_mm)
            parts.append(m)
        merged = trimesh.util.concatenate(parts)
        merged.apply_transform(offsets[i])
        meshes.append(merged)
    return meshes


def frame_matrix(pos_mm, quat) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = _quat_to_rot(tuple(quat))
    t[:3, 3] = np.asarray(pos_mm, dtype=float)
    return t


def build_druckstand(wall_mesh: trimesh.Trimesh, z_mm: float) -> trimesh.Trimesh | None:
    """Wandgeometrie bei z gekappt (wachsender Druckstand); None wenn leer."""
    if z_mm <= 0:
        return None
    if z_mm >= wall_mesh.bounds[1][2]:
        return wall_mesh
    sliced = trimesh.intersections.slice_mesh_plane(
        wall_mesh, plane_normal=[0, 0, -1], plane_origin=[0, 0, z_mm], cap=True
    )
    return sliced if len(sliced.faces) else None


def main() -> None:
    run_dir = REPO / (sys.argv[1] if len(sys.argv) > 1 else "runs/20260708-161603_slice_Denkmal")
    report: dict = {"run": run_dir.name}

    traj = json.loads((run_dir / "trajectory.json").read_text(encoding="utf-8"))
    wallspec = json.loads((run_dir / "wallspec.json").read_text(encoding="utf-8"))
    toolpath = json.loads((run_dir / "toolpath.json").read_text(encoding="utf-8"))
    layer_h = float(toolpath["params"]["layer_height_mm"])

    samples = traj["samples"]
    joints = np.array([s["joints_rad"] for s in samples])
    base_mat = frame_matrix(traj["meta"]["base_frame"]["pos_mm"], traj["meta"]["base_frame"]["quat"])
    tool = json.loads(TOOL_JSON.read_text(encoding="utf-8"))
    tcp_mat = frame_matrix(tool["tcp_frame"]["pos_mm"], tool["tcp_frame"]["quat"])
    report["n_samples"] = len(samples)

    # --- 1. Meshes laden -----------------------------------------------------
    t0 = time.perf_counter()
    link_meshes = load_link_collision_meshes()
    report["t_load_link_meshes_s"] = round(time.perf_counter() - t0, 3)
    report["link_mesh_faces"] = [int(len(m.faces)) for m in link_meshes]

    hull_meshes = [m.convex_hull for m in link_meshes]
    report["hull_mesh_faces"] = [int(len(m.faces)) for m in hull_meshes]

    wall = trimesh.Trimesh(
        vertices=np.array(wallspec["geometry"]["vertices_mm"], dtype=float),
        faces=np.array(wallspec["geometry"]["faces"], dtype=int),
        process=True,
    )
    report["wall_watertight"] = bool(wall.is_watertight)

    floor = trimesh.creation.box(extents=[6000, 6000, 200])
    floor.apply_translation([0, 0, -100])

    # --- 2. FK über alle Samples ---------------------------------------------
    kin = OpwKinematics.from_robot("doosan_m1013")
    t0 = time.perf_counter()
    all_frames = np.empty((len(samples), 7, 4, 4))
    for k in range(len(samples)):
        frames = kin.link_frames(joints[k])
        for i, f in enumerate(frames):
            all_frames[k, i] = base_mat @ frame_matrix(f.pos_mm, f.quat)
    t_fk = time.perf_counter() - t0
    report["t_fk_total_s"] = round(t_fk, 2)
    report["t_fk_per_sample_ms"] = round(t_fk / len(samples) * 1000, 3)

    # TCP je Sample (Flansch ∘ tcp) — Schichtzuordnung + Tunneling-Kennzahl
    tcp_pos = np.einsum("kij,j->ki", all_frames[:, 6], tcp_mat[:, 3])[:, :3]
    steps = np.linalg.norm(np.diff(tcp_pos, axis=0), axis=1)
    report["tcp_step_mm"] = {
        "max": round(float(steps.max()), 1),
        "p99": round(float(np.percentile(steps, 99)), 1),
        "median": round(float(np.median(steps)), 2),
    }

    # Druckstand-Oberkante = fertige Schichten unterhalb der aktuellen TCP-Höhe.
    ds_top = np.clip(np.floor(tcp_pos[:, 2] / layer_h) * layer_h, 0.0, None)
    report["ds_top_mm"] = {"min": float(ds_top.min()), "max": float(ds_top.max())}

    # --- 3. Hindernis-Manager je Druckstand-Oberkante (lazy Cache) -------------
    obst_cache: dict[float, CollisionManager] = {}
    t_druckstand_total = [0.0]

    def obstacles_for(top: float) -> CollisionManager:
        if top not in obst_cache:
            t0 = time.perf_counter()
            cm = CollisionManager()
            cm.add_object("floor", floor)
            ds = build_druckstand(wall, top)
            if ds is not None:
                cm.add_object("druckstand", ds)
            t_druckstand_total[0] += time.perf_counter() - t0
            obst_cache[top] = cm
        return obst_cache[top]

    # Glied 0 (Basis) ausgenommen: Basis↔Boden ist erlaubter Dauerkontakt.
    ARM_LINKS = list(range(1, 7))

    def make_arm_cm(meshes: list[trimesh.Trimesh]) -> CollisionManager:
        cm = CollisionManager()
        for i in ARM_LINKS:
            cm.add_object(f"link{i}", meshes[i])
        return cm

    def query(arm_cm: CollisionManager, k: int, obst: CollisionManager):
        for i in ARM_LINKS:
            arm_cm.set_transform(f"link{i}", all_frames[k, i])
        return arm_cm.min_distance_other(obst, return_names=True)

    # --- 4. Varianten auf Teilmenge --------------------------------------------
    stride = max(1, len(samples) // 1000)
    subset = list(range(0, len(samples), stride))
    report["subset"] = {"n": len(subset), "stride": stride}

    variants = {}
    for label, meshes in (("A_exakt", link_meshes), ("B_huellen", hull_meshes)):
        arm_cm = make_arm_cm(meshes)
        t0 = time.perf_counter()
        dists = []
        for k in subset:
            d, names = query(arm_cm, k, obstacles_for(float(ds_top[k])))
            dists.append(d)
        dt = time.perf_counter() - t0
        variants[label] = {
            "per_sample_ms": round(dt / len(subset) * 1000, 3),
            "min_dist_mm": round(float(min(dists)), 2),
            "n_below_0": int(sum(1 for d in dists if d <= 0)),
            "n_below_50": int(sum(1 for d in dists if d < 50)),
        }
    report["variants"] = variants

    # --- 5. Selbstkollision: nicht-benachbarte Paare (Teilmenge) ----------------
    single = {i: CollisionManager() for i in range(7)}
    for i, cm in single.items():
        cm.add_object(f"link{i}", link_meshes[i])
    pairs = [(i, j) for i in range(7) for j in range(i + 2, 7)]
    t0 = time.perf_counter()
    self_min = np.inf
    for k in subset[:200]:
        for i in range(7):
            single[i].set_transform(f"link{i}", all_frames[k, i])
        for i, j in pairs:
            d = single[i].min_distance_other(single[j])
            self_min = min(self_min, d)
    report["self_collision"] = {
        "per_sample_ms": round((time.perf_counter() - t0) / 200 * 1000, 3),
        "n_pairs": len(pairs),
        "min_dist_mm": round(float(self_min), 2),
    }

    # --- 6. Determinismus -------------------------------------------------------
    arm_cm = make_arm_cm(link_meshes)
    k = subset[len(subset) // 2]
    obst = obstacles_for(float(ds_top[k]))
    d1, _ = query(arm_cm, k, obst)
    d2, _ = query(arm_cm, k, obst)
    arm_cm2 = make_arm_cm(link_meshes)
    d3, _ = query(arm_cm2, k, obst)
    report["determinism"] = {"repeat_equal": d1 == d2, "rebuild_equal": d1 == d3}

    # --- 7. Volllauf (exakte Meshes, alle Samples) -------------------------------
    arm_cm = make_arm_cm(link_meshes)
    t0 = time.perf_counter()
    dists = np.empty(len(samples))
    causer: dict[str, int] = {}
    worst = (np.inf, -1, "")
    for k in range(len(samples)):
        d, names = query(arm_cm, k, obstacles_for(float(ds_top[k])))
        dists[k] = d
        pair = "|".join(sorted(names))
        if d < worst[0]:
            worst = (d, k, pair)
        if d < 50.0:
            causer[pair] = causer.get(pair, 0) + 1
    t_full = time.perf_counter() - t0
    report["full_run"] = {
        "t_total_s": round(t_full, 1),
        "per_sample_ms": round(t_full / len(samples) * 1000, 3),
        "t_druckstand_rebuilds_s": round(t_druckstand_total[0], 2),
        "n_obstacle_managers": len(obst_cache),
        "min_dist_mm": round(float(dists.min()), 2),
        "worst": {"dist_mm": round(worst[0], 2), "sample": worst[1], "t_s": samples[worst[1]]["t_s"], "pair": worst[2]},
        "n_below_0": int((dists <= 0).sum()),
        "n_below_50": int((dists < 50).sum()),
        "causer_pairs_below_50": sorted(causer.items(), key=lambda kv: -kv[1])[:8],
    }

    out = Path(__file__).parent / "last_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
