"""Kleine Coal-Referenz auf Roh-Meshes fuer test_collision (unabhaengig von der Naeherung).

Abstand je Paar aus SPEC §5.1 als Coal-BVH-Abstand der Original-Dreiecke; Boden exakt ueber die
Ecken. Bei Dreiecksschnitt oder Enthaltensein (Ecke im geschlossenen Solid) gilt d = -1e-3 mm,
die Tiefe wird nicht bestimmt. Kriterien wie G2: d_rp <= d_ref + 1 (bei d_ref < 0: d_rp <= 1),
beide >= 0: |d_rp - d_ref| <= 12.
"""

from __future__ import annotations

import json
from functools import lru_cache

import coal
import numpy as np
import trimesh

from roboprint import collision_assets as ca
from roboprint.collision import LINKS, checked_pairs


def _bvh(mesh: trimesh.Trimesh) -> coal.BVHModelOBBRSS:
    b = coal.BVHModelOBBRSS()
    b.beginModel(len(mesh.faces), len(mesh.vertices))
    b.addVertices(np.ascontiguousarray(mesh.vertices, dtype=float))
    b.addTriangles(np.ascontiguousarray(mesh.faces, dtype=np.int64))
    b.endModel()
    return b


class _Raw:
    def __init__(self, mesh: trimesh.Trimesh):
        self.mesh = mesh
        self.bvh = _bvh(mesh)
        self.solids = [c for c in mesh.split(only_watertight=False) if c.is_watertight]
        self.probe = np.asarray(mesh.vertices)[:: max(1, len(mesh.vertices) // 50)]


@lru_cache(maxsize=2)
def _raw_bodies(root, r_free: float = 40.0):
    from roboprint.urdf_chain import load_chain

    chain = load_chain(root)
    bodies = {n: _Raw(ca.link_mesh(chain.collision[n])) for n in LINKS}
    tj = json.loads((root / "tools" / "30gut.json").read_text())
    tool = trimesh.load(str(root / "tools" / "30gut.stl"), force="mesh")
    tool.apply_transform(ca.pose_matrix(tj["mesh_transform"]["pos_mm"], tj["mesh_transform"]["quat"]))
    tcp = np.asarray(tj["tcp_frame"]["pos_mm"], dtype=float)
    cen = np.linalg.norm(tool.triangles_center - tcp, axis=1)
    bodies["tool_body"] = _Raw(trimesh.Trimesh(tool.vertices, tool.faces[cen > r_free]))
    bodies["nozzle_tip"] = _Raw(trimesh.Trimesh(tool.vertices, tool.faces[cen <= r_free]))
    bodies["table"] = _Raw(trimesh.load(str(root / "workstations" / "doosantisch.stl"), force="mesh"))
    return bodies


def _tf(T):  # noqa: N803
    return coal.Transform3s(np.ascontiguousarray(T[:3, :3]), np.ascontiguousarray(T[:3, 3]))


def _inside(a: _Raw, Ta, b: _Raw, Tb) -> bool:  # noqa: N803
    """Liegt eine Probe von a in einem geschlossenen Solid von b?"""
    if not b.solids:
        return False
    p = a.probe @ Ta[:3, :3].T + Ta[:3, 3]
    p = (p - Tb[:3, 3]) @ Tb[:3, :3]
    for s in b.solids:
        lo, hi = s.bounds
        m = np.all((p >= lo) & (p <= hi), axis=1)
        if m.any() and s.contains(p[m]).any():
            return True
    return False


def reference_distance(world, q, k: int) -> tuple[float, tuple[str, str]]:
    bodies = dict(_raw_bodies(world.root))
    if k > 0:
        clipped = ca.clip_below(world.part_mesh_P, k * world.h)
        if clipped is not None:
            bodies["printed"] = _Raw(clipped)
    frames = world.frames_W(q)
    T = {n: frames[i] for i, n in enumerate(LINKS)}  # noqa: N806
    T["tool_body"] = T["nozzle_tip"] = T["link_6"]
    T["table"] = np.eye(4)
    T["printed"] = world.T_WP
    best, pair = np.inf, ("", "")
    req, creq = coal.DistanceRequest(), coal.CollisionRequest()
    for a, b in checked_pairs():
        if a not in bodies or (b != "floor" and b not in bodies):
            continue
        if b == "floor":
            v = bodies[a].mesh.vertices
            d = float((v @ T[a][2, :3]).min() + T[a][2, 3])
        else:
            A, B = bodies[a], bodies[b]  # noqa: N806
            ta, tb = _tf(T[a]), _tf(T[b])
            if coal.collide(A.bvh, ta, B.bvh, tb, creq, coal.CollisionResult()):
                d = -1e-3
            else:
                d = coal.distance(A.bvh, ta, B.bvh, tb, req, coal.DistanceResult())
                if d < 200 and (_inside(A, T[a], B, T[b]) or _inside(B, T[b], A, T[a])):
                    d = -1e-3
        if d < best:
            best, pair = d, (a, b)
    return float(best), pair


def sample_poses(world, n_uniform: int, n_near: int, seed: int, k: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    lim = np.array([[-2 * np.pi, 2 * np.pi]] * 6)
    lim[2] = [-np.deg2rad(160), np.deg2rad(160)]
    out = list(rng.uniform(lim[:, 0], lim[:, 1], size=(n_uniform, 6)))
    top = world.T_WP @ np.array([0.0, 0.0, k * world.h, 1.0])
    seed0 = np.deg2rad([-90.0, 0.0, 90.0, 0.0, 90.0, 0.0])
    while len(out) < n_uniform + n_near:
        q = seed0 + rng.normal(0, 0.6, 6)
        tcp = world.tcp_W(q)[:3, 3]
        if np.linalg.norm(tcp - top[:3]) < 350.0:
            out.append(q)
    return np.array(out)


def compare(world, scene, n_uniform: int, n_near: int, seed: int, k: int = 20):
    bad, n_neg, n_near_cnt = [], 0, 0
    for i, q in enumerate(sample_poses(world, n_uniform, n_near, seed, k)):
        c = world.distance(q, k)
        d_ref, p_ref = reference_distance(world, q, k)
        n_neg += d_ref < 0
        n_near_cnt += 0 <= d_ref < 50
        why = []
        if d_ref >= 0 and c.d_mm > d_ref + 1.0:
            why.append("nicht konservativ")
        if d_ref < 0 and c.d_mm > 1.0:
            why.append("Durchdringung nicht erkannt")
        if d_ref >= 0 and c.d_mm >= 0 and abs(c.d_mm - d_ref) > 12.0:
            why.append("|d_rp - d_ref| > 12")
        if d_ref > 12.0 and c.d_mm < 0:
            why.append("Vorzeichen")
        if why:
            bad.append(f"Pose {i}: d_rp={c.d_mm:.2f} {c.pair} d_ref={d_ref:.2f} {p_ref}: {why}")
    return bad, {"n_neg": n_neg, "n_near": n_near_cnt}
