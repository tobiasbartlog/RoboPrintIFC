"""Kinematik `roboprint.robot` gegen Pinocchio auf der URDF (gleichwertig zu Gate G1) plus Unit-Tests."""

from __future__ import annotations

import time

import numpy as np
import pytest

from roboprint import frames, robot
from roboprint.assets import REPO_ROOT, URDF_PATH, load_tool
from roboprint.robot import JOINT_LIMITS, branch_of, fk, fk_batch, ik, ik_batch

pin = pytest.importorskip("pinocchio")

N = 2000
POS_TOL_MM = 0.01
ROT_TOL_RAD = 1e-6


@pytest.fixture(scope="module")
def pin_fk():
    model = pin.buildModelFromUrdf(str(REPO_ROOT / URDF_PATH))
    data = model.createData()
    fid = model.getFrameId("link_6")

    def _fk(q: np.ndarray) -> np.ndarray:
        pin.framesForwardKinematics(model, data, np.asarray(q, dtype=float))
        M = data.oMf[fid]
        T = np.eye(4)
        T[:3, :3] = M.rotation
        T[:3, 3] = M.translation * 1000.0
        return T

    return _fk


def _rot_angle(Ra: np.ndarray, Rb: np.ndarray) -> float:
    E = Ra.T @ Rb
    v = np.array([E[2, 1] - E[1, 2], E[0, 2] - E[2, 0], E[1, 0] - E[0, 1]])
    return float(np.arctan2(0.5 * np.linalg.norm(v), 0.5 * (np.trace(E) - 1.0)))


def _random_q(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(JOINT_LIMITS[:, 0], JOINT_LIMITS[:, 1], size=(n, 6))


def _wrapped_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.max(np.abs(robot.wrap(a - b))))


# --- G1: FK -------------------------------------------------------------------------------


def test_fk_matches_pinocchio(pin_fk):
    Q = _random_q(N, 1)
    Tb = fk_batch(Q)
    for q, T in zip(Q, Tb, strict=True):
        Tp = pin_fk(q)
        assert np.linalg.norm(T[:3, 3] - Tp[:3, 3]) < POS_TOL_MM
        assert _rot_angle(T[:3, :3], Tp[:3, :3]) < ROT_TOL_RAD
        np.testing.assert_allclose(fk(q), T, atol=1e-9)


# --- G1: IK -------------------------------------------------------------------------------


def test_ik_roundtrip_against_pinocchio(pin_fk):
    Q = _random_q(N, 2)
    n_sol = []
    for q in Q:
        T = pin_fk(q)
        sols = ik(T)
        n_sol.append(len(sols))
        assert sols, f"keine Loesung fuer q={np.degrees(q)}"
        found = False
        for b, qs in sols:
            Ts = pin_fk(qs)
            assert np.linalg.norm(Ts[:3, 3] - T[:3, 3]) < POS_TOL_MM
            assert _rot_angle(Ts[:3, :3], T[:3, :3]) < ROT_TOL_RAD
            assert robot.in_limits(qs)
            assert branch_of(qs) == b
            found |= _wrapped_dist(qs, q) < 1e-6
        assert found, f"erzeugendes q={np.degrees(q)} (Zweig {branch_of(q)}) fehlt"
        assert len({b for b, _ in sols}) == len(sols)
    assert np.mean(np.array(n_sol) == 8) > 0.95


def test_home_pose_valid(pin_fk):
    home = np.radians([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])
    np.testing.assert_allclose(robot.HOME_Q, home)
    assert robot.in_limits(home)
    assert branch_of(home) == robot.ELBOW_ABOVE  # Lefty/Above/NoFlip = 2
    sols = ik(pin_fk(home))
    assert any(b == 2 and _wrapped_dist(q, home) < 1e-9 for b, q in sols)
    # Flansch zeigt senkrecht nach unten, Handgelenkzentrum 559 mm vor J1
    T = fk(home)
    np.testing.assert_allclose(T[:3, 2], [0.0, 0.0, -1.0], atol=1e-3)


# --- Zweige -------------------------------------------------------------------------------


def test_branch_bits_match_geometric_definition():
    """Abseits der Singularitaeten: Bits nach den Ideal-Formeln des Docstrings."""
    Q = _random_q(N, 3)
    r = 620.0 * np.sin(Q[:, 1]) + 559.0 * np.sin(Q[:, 1] + Q[:, 2])
    far = (np.abs(r) > 5.0) & (np.abs(np.sin(Q[:, 2])) > 1e-2) & (np.abs(np.sin(Q[:, 4])) > 1e-2)
    Q, r = Q[far], r[far]
    expect = (
        np.where(r < 0, robot.SHOULDER_RIGHTY, 0)
        + np.where(np.sin(Q[:, 2]) * np.sign(r) > 0, robot.ELBOW_ABOVE, 0)
        + np.where(robot.wrap(Q[:, 4]) < 0, robot.WRIST_FLIP, 0)
    )
    np.testing.assert_array_equal(branch_of(Q), expect)
    assert set(expect) == set(range(8))


def test_ik_returns_all_eight_branches_generic_pose():
    q = np.radians([20.0, -30.0, 70.0, 40.0, 60.0, -15.0])
    sols = ik(fk(q))
    assert [b for b, _ in sols] == list(range(8))
    qs = np.array([s for _, s in sols])
    for i in range(8):
        for j in range(i + 1, 8):
            assert _wrapped_dist(qs[i], qs[j]) > 1e-3


def test_ik_batch_matches_single():
    Q = _random_q(50, 4)
    Qb, ok = ik_batch(fk_batch(Q))
    for i, q in enumerate(Q):
        single = dict(ik(fk(q)))
        assert set(single) == set(np.nonzero(ok[i])[0])
        for b, qs in single.items():
            np.testing.assert_allclose(Qb[i, b], qs, atol=1e-12)


# --- Singularitaeten ----------------------------------------------------------------------


def _check_solutions(T, sols):
    assert sols
    for b, qs in sols:
        Ts = fk(qs)
        assert np.linalg.norm(Ts[:3, 3] - T[:3, 3]) < 1e-4
        assert _rot_angle(Ts[:3, :3], T[:3, :3]) < 1e-8
        assert branch_of(qs) == b


@pytest.mark.parametrize("q5_deg", [0.0, 1e-9, -1e-7, 180.0, 1e-3])
def test_wrist_singularity(q5_deg):
    q = np.radians([10.0, 20.0, 80.0, 30.0, q5_deg, -40.0])
    T = fk(q)
    sols = ik(T)
    _check_solutions(T, sols)
    best = robot.ik_nearest(T, q)
    assert best is not None
    Ts = fk(best[1])
    assert np.linalg.norm(Ts[:3, 3] - T[:3, 3]) < 1e-4
    assert _wrapped_dist(best[1], q) < 1e-3  # q4 aus der Referenz, nicht 0


def test_elbow_singularity_stretched():
    for d in (0.0, 1e-6, 1e-4, 2e-3):
        q = np.array([0.3, 0.4, robot._DELTA3 + d, 0.2, 0.7, 0.1])
        T = fk(q)
        sols = ik(T)
        _check_solutions(T, sols)
        assert any(_wrapped_dist(s, q) < 1e-6 for _, s in sols) or d < 1e-4


def test_shoulder_singularity():
    # Handgelenkzentrum nahe der J1-Achse: r = 620 sin q2 + 559 sin(q2 + q3) ~ 0
    q2 = 0.5
    q3 = -q2 - np.arcsin(620.0 * np.sin(q2) / 559.0)
    for dq in (0.0, 1e-5, 1e-3):
        q = np.array([0.2, q2, q3 + dq, 0.4, 1.0, 0.3])
        T = fk(q)
        sols = ik(T)
        _check_solutions(T, sols)


# --- Grenzen ------------------------------------------------------------------------------


def test_joint_limits_and_velocity_constants():
    np.testing.assert_allclose(JOINT_LIMITS[2], np.radians([-160.0, 160.0]))
    for i in (0, 1, 3, 4, 5):
        np.testing.assert_allclose(JOINT_LIMITS[i], np.radians([-360.0, 360.0]))
    np.testing.assert_allclose(robot.JOINT_VEL_LIMITS, np.radians([120, 120, 180, 225, 225, 225]))


def test_j3_limit_excludes_solutions():
    q = np.radians([0.0, 10.0, 170.0, 0.0, 30.0, 0.0])
    sols = ik(fk(q))
    assert all(abs(s[2]) <= JOINT_LIMITS[2, 1] + 1e-9 for _, s in sols)
    assert not any(_wrapped_dist(s, q) < 1e-6 for _, s in sols)


def test_unreachable_pose_is_empty():
    T = np.eye(4)
    T[:3, 3] = [3000.0, 0.0, 500.0]
    assert ik(T) == []
    Q, ok = ik_batch(T[None])
    assert not ok.any()


def test_turn_variants_and_nearest():
    q = np.radians([-10.0, -20.0, 30.0, 40.0, 50.0, 60.0])
    variants = robot.turn_variants(q)
    assert len(variants) == 2**5  # J3 hat nur eine Variante
    for v in variants:
        assert robot.in_limits(v)
        np.testing.assert_allclose(fk(v), fk(q), atol=1e-9)
    shift = np.array([2 * np.pi, 0, 0, -2 * np.pi, 0, -2 * np.pi])
    best = robot.ik_nearest(fk(q), q + shift + 0.01)
    assert best is not None
    np.testing.assert_allclose(best[1], q + shift, atol=1e-9)
    assert best[0] == branch_of(q)
    other = robot.ik_nearest(fk(q), q + shift, branch=branch_of(q) ^ robot.WRIST_FLIP)
    assert other is not None and other[0] == branch_of(q) ^ robot.WRIST_FLIP


# --- Werkzeug -----------------------------------------------------------------------------


def test_tool_tcp():
    T_FT = frames.T_FT(load_tool())
    np.testing.assert_allclose(T_FT[:3, 3], [134.0, 0.0, 73.0])
    # Duesenachse +Z_T ist Flansch-X (CLAUDE.md, Fallstricke)
    np.testing.assert_allclose(T_FT[:3, 2], [1.0, 0.0, 0.0], atol=1e-9)
    q = np.radians([15.0, 10.0, 80.0, -20.0, 70.0, 30.0])
    T_BT = robot.tcp_pose(q)
    np.testing.assert_allclose(T_BT, fk(q) @ T_FT, atol=1e-9)
    sols = robot.ik_tcp(T_BT)
    assert any(_wrapped_dist(s, q) < 1e-6 for _, s in sols)


# --- Performance --------------------------------------------------------------------------


def test_performance():
    Q = _random_q(1000, 5)
    T = fk_batch(Q)
    ik_batch(T[:5])
    t0 = time.perf_counter()
    _, ok = ik_batch(T)
    per_pose = (time.perf_counter() - t0) / len(Q)
    assert ok.any(axis=1).all()
    assert per_pose < 1e-3, f"ik_batch {per_pose * 1e6:.0f} us/Pose"
    t0 = time.perf_counter()
    fk_batch(_random_q(10000, 6))
    assert (time.perf_counter() - t0) / 10000 < 50e-6
