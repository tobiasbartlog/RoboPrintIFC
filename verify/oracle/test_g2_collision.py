"""G2 (SPEC §11): roboprint.collision gegen das Coal-Orakel auf Roh-Meshes.

Szene S1: Quader 600 x 200 x 400 mm (Laenge x Dicke x Hoehe) als Teil, feste Platzierung auf der
Arbeitsflaeche bei S = (0, -50) mm, Gier 0 (Teil y_S in [-150, 50]; die Roboterbasis beginnt bei
y_S ~ 136, Abstand ~ 86 mm). Halb gedruckt: k = 20 von 40 Schichten (Druckstand bis z_P = 200 mm).

500 Posen mit festem Seed: 250 gleichverteilt in den Gelenkgrenzen, 250 nahe am Teil (numerische IK
auf Zufallsziele um den Druckstand, Duese grob nach unten), damit Nah- und Durchdringungsfaelle vorkommen.

Kriterien: d_rp <= d_coal + 1 mm (bei d_coal < 0: d_rp <= 1 mm, die Tiefe nichtkonvexer Koerper ist
nicht eindeutig, s. README); wo |d_coal| > 12 mm gleiches Vorzeichen; wo beide >= 0: |d_rp - d_coal| <= 12.
"""

from __future__ import annotations

import numpy as np
from roboprint.collision import World  # System unter Test, bewusst ohne Skip

from verify.oracle.collision_oracle import CollisionOracle, box_part_mesh, checked_pairs
from verify.oracle.robot_oracle import ROOT, Rz, default_robot, inv_T, workstation_frames, wrap_pi

SEED = 20261018
N_UNIFORM = 250
N_NEAR = 250
K = 20
PLACEMENT_S = (0.0, -50.0, 0.0)  # x, y in S (mm), Gier (deg)
SIZE = (600.0, 200.0, 400.0)


def scene():
    _, T_WS, _ = workstation_frames()
    T_SP = np.eye(4)
    T_SP[:3, :3] = Rz(np.deg2rad(PLACEMENT_S[2]))
    T_SP[:3, 3] = [PLACEMENT_S[0], PLACEMENT_S[1], 0.0]
    return box_part_mesh(SIZE), T_WS @ T_SP


def poses() -> np.ndarray:
    r = default_robot()
    T_WB, _, _ = workstation_frames()
    _, T_WP = scene()
    rng = np.random.default_rng(SEED)
    out = list(rng.uniform(r.limits[:, 0], r.limits[:, 1], size=(N_UNIFORM, 6)))
    seed0 = np.deg2rad([-90.0, 0.0, 90.0, 0.0, 90.0, 0.0])
    for _ in range(N_NEAR):
        pP = np.array([rng.uniform(-360, 360), rng.uniform(-160, 160),
                       rng.uniform(K * 10 - 60, K * 10 + 160)])
        tilt = np.deg2rad(rng.uniform(0, 30))
        az = rng.uniform(0, 2 * np.pi)
        axis = np.array([np.sin(tilt) * np.cos(az), np.sin(tilt) * np.sin(az), -np.cos(tilt)])
        x = np.cross([0.0, 1.0, 0.0], axis)
        x /= np.linalg.norm(x)
        R = np.column_stack([x, np.cross(axis, x), axis]) @ Rz(rng.uniform(0, 2 * np.pi))
        T_WT = np.eye(4)
        T_WT[:3, :3] = T_WP[:3, :3] @ R
        T_WT[:3, 3] = T_WP[:3, :3] @ pP + T_WP[:3, 3]
        T_BF = inv_T(T_WB) @ T_WT @ inv_T(r.T_FT)
        q0 = seed0 + rng.normal(0, 0.4, 6)
        q, _ = r.ik_numeric(T_BF, q0, iters=150)
        q = wrap_pi(q)
        q[2] = np.clip(q[2], r.limits[2, 0], r.limits[2, 1])
        out.append(q)
    return np.array(out)


def test_g2_collision_against_coal():
    mesh, T_WP = scene()
    world = World(part_mesh_P=mesh, T_WP=T_WP, layer_height_mm=10.0, root=ROOT)
    oracle = CollisionOracle(mesh, T_WP, 10.0, 40.0)
    names = {n for p in checked_pairs() for n in p}
    bad, n_neg, n_near = [], 0, 0
    for i, q in enumerate(poses()):
        c_rp = world.distance(np.asarray(q, dtype=float), K)
        c_or = oracle.status_contact(q, K, 10.0, depth=True)  # d_status, SPEC §2
        d_rp, d_or = float(c_rp.d_mm), float(c_or.d_mm)
        n_neg += d_or < 0
        n_near += 0 <= d_or < 50
        why = []
        if tuple(c_rp.pair)[0] not in names or len(c_rp.pair) != 2 or len(c_rp.witness_W) != 2:
            why.append(f"Schnittstelle: pair={c_rp.pair}")
        if d_or >= 0 and d_rp > d_or + 1.0:
            why.append("nicht konservativ (d_rp > d_coal + 1)")
        if d_or < 0 and d_rp > 1.0:
            why.append("Durchdringung nicht erkannt (d_rp > 1 bei d_coal < 0)")
        if abs(d_or) > 12.0 and (d_rp < 0) != (d_or < 0):
            why.append("Vorzeichen verschieden bei |d_coal| > 12")
        if d_or >= 0 and d_rp >= 0 and abs(d_rp - d_or) > 12.0:
            why.append("|d_rp - d_coal| > 12")
        if why:
            bad.append(f"Pose {i} q={np.round(q, 4).tolist()}: d_rp={d_rp:.2f} {tuple(c_rp.pair)}, "
                       f"d_coal={d_or:.2f} {c_or.pair}: " + "; ".join(why))
    assert n_neg >= 20 and n_near >= 20, f"Posenmix ungeeignet: {n_neg} Durchdringungen, {n_near} nah"
    assert not bad, f"{len(bad)} von {N_UNIFORM + N_NEAR} Posen verletzen G2:\n" + "\n".join(bad[:20])
