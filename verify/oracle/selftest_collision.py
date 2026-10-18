"""Selbsttests des Kollisions-Orakels und des Intervall-Pruefers (ohne roboprint)."""

from __future__ import annotations

import numpy as np
import trimesh

from verify.oracle.collision_oracle import (
    CollisionOracle,
    box_part_mesh,
    checked_pairs,
    clip_below,
    static_geometry,
)
from verify.oracle.interval_checker import IntervalChecker
from verify.oracle.robot_oracle import HOME_RAD, LINK_NAMES, Rz, default_robot, inv_T, workstation_frames

T_WB, T_WS, _ = workstation_frames()
Q_PRINT = np.deg2rad([-85.0, 21.0, 113.0, 94.0, 86.0, -134.0])  # Duese unten, vor dem Roboter


def _part_at(center_W: np.ndarray, size) -> tuple[trimesh.Trimesh, np.ndarray]:
    """Quader mit Bodenmitte bei center_W (Frame P achsparallel zu W)."""
    T = np.eye(4)
    T[:3, 3] = center_W
    return box_part_mesh(size), T


def test_pairs_exactly_spec():
    pairs = set(checked_pairs())
    assert ("base_link", "floor") not in pairs and ("link_1", "table") not in pairs
    assert ("nozzle_tip", "printed") not in pairs and ("nozzle_tip", "floor") in pairs
    assert ("tool_body", "printed") in pairs and ("base_link", "printed") in pairs
    assert ("link_2", "base_link") in pairs and ("link_1", "base_link") not in pairs
    assert ("tool_body", "link_4") in pairs and ("tool_body", "link_5") not in pairs
    self_pairs = [p for p in pairs if p[1] in LINK_NAMES]
    assert len(self_pairs) == 15 + 5
    assert len(pairs) == 7 + 7 + 8 + 15 + 5


def test_nozzle_split_at_r_free():
    g = static_geometry(40.0, 80.0)
    tcp = default_robot().T_FT[:3, 3]
    tip_c = np.linalg.norm(g.nozzle_tip.vertices - tcp, axis=1)
    assert tip_c.max() <= 40.0 + 1.5  # Dreiecke an der Kugel sind auf 1 mm unterteilt
    body_tris = np.array([c.bvh.num_tris for c in g.tool_body.chunks]).sum()
    assert body_tris > 0 and len(g.nozzle_tip.vertices) > 0


def test_cube_inside_link_is_negative():
    """Ein Wuerfel ganz im Glied link_3 (ohne Dreiecksschnitt) ergibt d < 0 mit Paar (link_3, printed)."""
    o0 = CollisionOracle()
    T3 = o0.body_poses(HOME_RAD)["link_3"]
    solid = max(o0.links["link_3"].solids, key=lambda s: s.volume)
    c_local = solid.centroid
    assert solid.contains([c_local])[0]
    part, T_WP = _part_at(T3[:3, :3] @ c_local + T3[:3, 3] - [0, 0, 5.0], (10.0, 10.0, 10.0))
    o = CollisionOracle(part, T_WP, 10.0, 40.0)
    c = o.distance(HOME_RAD, 1)
    assert c.d_mm < 0 and c.pair == ("link_3", "printed"), c
    iv = IntervalChecker(o, [0, 10, 12, 49, 50, 62]).evaluate(HOME_RAD, 1)
    assert iv.collision


def test_deep_penetration_depth_lower_bound():
    """Grosser Block quer durch den Unterarm: Tiefe > 12 mm erkannt, aber nie tiefer als der Block."""
    o0 = CollisionOracle()
    T4 = o0.body_poses(HOME_RAD)["link_4"]
    p = T4[:3, 3] + T4[:3, :3] @ np.array([0.0, 0.0, -250.0])
    part, T_WP = _part_at(p - [0, 0, 150.0], (300.0, 300.0, 300.0))
    o = CollisionOracle(part, T_WP, 10.0, 40.0)
    c = o.distance(HOME_RAD, 40)
    assert -150.0 <= c.d_mm < -12.0, c


def test_known_gap_to_box():
    """Flacher Quader 15 mm unter dem tiefsten Punkt von Glied/Werkzeugkoerper: d = 15 mm exakt."""
    o0 = CollisionOracle()
    poses = o0.body_poses(Q_PRINT)
    low = None
    for n in (*LINK_NAMES, "tool_body"):
        B = o0._body(n, 0)
        T = poses[n]
        v = B.vertices @ T[:3, :3].T + T[:3, 3]
        i = int(np.argmin(v[:, 2]))
        if low is None or v[i, 2] < low[2]:
            low = v[i]
    part, T_WP = _part_at(np.array([low[0], low[1], low[2] - 15.0 - 20.0]), (60.0, 60.0, 20.0))
    o = CollisionOracle(part, T_WP, 10.0, 40.0)
    c = o.distance(Q_PRINT, 2)
    assert abs(c.d_mm - 15.0) < 1e-3 and c.pair[1] == "printed", c
    assert abs(c.witness_W[0][2] - c.witness_W[1][2] - 15.0) < 1e-3


def test_floor_half_space():
    """Duesenspitze 20 mm unter dem Boden (neben dem Tisch): Bodenabstand exakt = tiefste Ecke (< 0).
    Nur die Bodenpaare werden ausgewertet (der Unterarm streift in dieser Pose die Tischkante)."""
    r = default_robot()
    T_WT = np.eye(4)
    T_WT[:3, :3] = Rz(np.pi / 2) @ np.diag([1.0, -1.0, -1.0])
    T_WT[:3, 3] = [780.0, 1550.0, -20.0]
    q, ok = r.ik_numeric(inv_T(T_WB) @ T_WT @ inv_T(r.T_FT), np.deg2rad([90, 30, 90, 0, 60, 0]))
    assert ok
    o = CollisionOracle()
    o.pairs = [p for p in o.pairs if p[1] == "floor"]
    c = o.distance(q, 0)
    poses = o.body_poses(q)
    zmin = min(float((o._body(n, 0).vertices @ poses[n][:3, :3].T + poses[n][:3, 3])[:, 2].min())
               for n in ("link_2", "link_3", "link_4", "link_5", "link_6", "tool_body", "nozzle_tip"))
    assert c.pair == ("nozzle_tip", "floor") and abs(c.d_mm - zmin) < 1e-9, (c, zmin)
    assert -25.0 < c.d_mm < -15.0
    assert abs(c.witness_W[1][2]) < 1e-12


def test_printed_volume_clip():
    part = box_part_mesh((600, 200, 400))
    half = clip_below(part, 200.0)
    assert half.is_watertight and abs(half.volume - 600 * 200 * 200) < 1.0
    assert clip_below(part, 0.0) is None
    o = CollisionOracle(part, T_WS, 10.0, 40.0)
    assert o.printed(0) is None and o.printed(20) is not None


def test_interval_checker_matches_exact_distance():
    """Intervall [lb, ub] enthaelt den exakten Abstand und entscheidet alle Schwellen (Zufallspfade)."""
    part = box_part_mesh((600, 200, 400))
    T_SP = np.eye(4)
    T_SP[:3, 3] = [0.0, -50.0, 0.0]
    o = CollisionOracle(part, T_WS @ T_SP, 10.0, 40.0)
    T = [0.0, 10.0, 12.0, 49.0, 50.0, 62.0]
    rng = np.random.default_rng(7)
    for start, k in ((Q_PRINT, 20), (rng.uniform(-2.5, 2.5, 6), 30)):
        ic = IntervalChecker(o, T)
        q = np.array(start, dtype=float)
        for i in range(40):
            q = q + rng.normal(0, 0.004, 6)
            iv = ic.evaluate(q, k)
            if i % 4:
                continue
            d = o.distance(q, k, depth=False).d_mm
            if d < 0:
                assert iv.collision
            else:
                assert iv.lb - 1e-6 <= d <= iv.ub + 1e-6
                assert all(iv.lb >= t or iv.ub < t for t in T)
