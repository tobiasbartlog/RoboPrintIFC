"""Selbsttests des Kinematik-Orakels (ohne roboprint)."""

from __future__ import annotations

import numpy as np
import pytest

from verify.oracle.robot_oracle import (
    HOME_RAD,
    R_to_quat,
    R_to_zyz,
    RobotOracle,
    Ry,
    Rz,
    quat_to_R,
    resolve_package_uri,
    rot_angle,
    urdf_collision_meshes,
    zyz_to_R,
)

R = RobotOracle()


def test_zero_pose_flange_nominal():
    # Nullstellung: Arm senkrecht, Flansch bei z = 152,5 + 620 + 559 + 121, Seitenversatz 34,5 mm.
    # Die URDF rundet pi/2 auf 1,571; daraus folgen Abweichungen < 0,5 mm gegen die Nennmasse.
    T = R.fk(np.zeros(6))
    assert np.allclose(T[:3, 3], [0.0, 34.5, 1452.5], atol=0.5)
    assert np.allclose(T[:3, :3], np.eye(3), atol=1e-3)


def test_home_pose_flange_nominal():
    T = R.fk(HOME_RAD)
    assert np.allclose(T[:3, 3], [559.0, 34.5, 651.5], atol=0.5)
    assert np.allclose(T[:3, 2], [0.0, 0.0, -1.0], atol=1e-3)  # Flansch-Z zeigt nach unten
    assert R.in_limits(HOME_RAD)


def test_urdf_units_and_paths():
    meshes = urdf_collision_meshes()
    assert set(meshes) >= {"base_link", "link_6"}
    for items in meshes.values():
        for path, _T, scale in items:
            assert path.is_file(), path
            assert np.allclose(scale, 1.0)  # URDF-Skala 0,001 (mm -> m) mal 1000 (m -> mm)
    assert resolve_package_uri("package://dsr_description2/meshes/m1013_collision/MF1013_0_0.dae").is_file()


def test_limits_from_robot_json():
    assert np.allclose(R.limits[2], np.deg2rad([-160, 160]), atol=1e-6)
    assert np.allclose(R.limits[0], np.deg2rad([-360, 360]), atol=1e-6)
    assert np.allclose(np.rad2deg(R.vel_limits), [120, 120, 180, 225, 225, 225], atol=1e-4)


def test_tcp_frame():
    T = R.fk_tcp(HOME_RAD)
    assert np.allclose(T, R.fk(HOME_RAD) @ R.T_FT)
    assert np.allclose(R.T_FT[:3, 3], [134.0, 0.0, 73.0])
    assert np.allclose(R.T_FT[:3, 2], [1.0, 0.0, 0.0], atol=1e-9)  # Duesenachse = Flansch-X


@pytest.mark.parametrize("b_deg", [0.0, 1e-9, 90.0, 179.999999, 180.0])
def test_zyz_roundtrip(b_deg):
    rng = np.random.default_rng(int(b_deg * 1000) % 2**31)
    for _ in range(50):
        a, c = rng.uniform(-180, 180, 2)
        Rm = Rz(np.deg2rad(a)) @ Ry(np.deg2rad(b_deg)) @ Rz(np.deg2rad(c))
        abc = R_to_zyz(Rm)
        assert 0.0 <= abc[1] <= 180.0
        assert rot_angle(zyz_to_R(*abc), Rm) < 1e-9


def test_zyz_gimbal_nozzle_down():
    # Duese senkrecht nach unten: b = 180; die v1-Formel (atan2(r21, r11)) verdreht um 180 deg
    Rm = Rz(0.3) @ np.diag([1.0, -1.0, -1.0])
    a, b, c = R_to_zyz(Rm)
    assert abs(b - 180.0) < 1e-9
    assert rot_angle(zyz_to_R(a, b, c), Rm) < 1e-12
    a_v1 = np.rad2deg(np.arctan2(Rm[1, 0], Rm[0, 0]))
    assert rot_angle(zyz_to_R(a_v1, 180.0, 0.0), Rm) > np.deg2rad(90)


def test_quat_roundtrip():
    rng = np.random.default_rng(1)
    for _ in range(100):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        Rm = quat_to_R(q)
        assert np.allclose(quat_to_R(R_to_quat(Rm)), Rm, atol=1e-12)


def test_numeric_ik_and_wrist_flip_branch():
    rng = np.random.default_rng(2)
    q = np.deg2rad([-80.0, 20.0, 100.0, 30.0, 70.0, 10.0])
    T = R.fk(q)
    q2, ok = R.ik_numeric(T, q + rng.normal(0, 0.05, 6))
    assert ok and np.linalg.norm(R.fk(q2)[:3, 3] - T[:3, 3]) < 1e-5
    seed = q + np.array([0.0, 0.0, 0.0, np.pi, 0.0, np.pi])
    seed[4] = -q[4]
    # Die URDF (1,571 statt pi/2) ist nicht exakt sphaerisch: Flip-Seed liegt ~0,02 mm daneben
    assert np.linalg.norm(R.fk(seed)[:3, 3] - T[:3, 3]) < 0.1
    flip, ok = R.ik_numeric(T, seed)
    assert ok and np.linalg.norm(R.fk(flip)[:3, 3] - T[:3, 3]) < 1e-5
    s1, s2 = R.branch_signs(q), R.branch_signs(flip)
    assert s1[:2] == s2[:2] and s1[2] == -s2[2] != 0
