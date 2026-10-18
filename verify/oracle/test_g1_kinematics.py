"""G1 (SPEC §11): roboprint.robot gegen das Pinocchio-Orakel auf der URDF.

Kriterien: 2000 Zufalls-q in den Grenzen: Positionsfehler < 0,01 mm, Rotationsfehler < 1e-6 rad.
2000 Zufallsposen (FK zufaelliger q): jede IK-Loesung erfuellt die FK auf 0,01 mm und liegt in den
Grenzen, die erzeugende Loesung ist (modulo 2 pi) enthalten. Home-Pose gueltig. Zweig-Bits plausibel.
"""

from __future__ import annotations

import numpy as np
from roboprint.robot import JOINT_LIMITS, fk, ik  # System unter Test, bewusst ohne Skip

from verify.oracle.robot_oracle import HOME_RAD, RobotOracle, rot_angle, wrap_pi

SEED = 20261018
N = 2000
POS_TOL = 0.01  # mm
ROT_TOL = 1e-6  # rad (FK)
IK_ROT_TOL = 1e-5  # rad (IK: "erfuellt die FK"; Lage zusaetzlich, ~0,01 mm auf 1 m Hebel)
Q_TOL = 1e-4  # rad, erzeugende Loesung in der Loesungsmenge
ORACLE = RobotOracle()


def _random_q(rng: np.random.Generator, n: int) -> np.ndarray:
    lim = ORACLE.limits
    return rng.uniform(lim[:, 0], lim[:, 1], size=(n, 6))


def _report(bad: list[str], what: str) -> str:
    return f"{len(bad)} Verstoesse gegen {what}:\n" + "\n".join(bad[:15])


def _same_config(qa: np.ndarray, qb: np.ndarray, tol: float = Q_TOL) -> bool:
    d = np.abs(wrap_pi(np.asarray(qa) - np.asarray(qb)))
    if d.max() <= tol:
        return True
    # Handgelenk-Singularitaet: nur q4 + q6 (q5 ~ 0) bzw. q4 - q6 (q5 ~ pi) ist bestimmt
    if abs(np.sin(qa[4])) < 1e-3 and max(d[0], d[1], d[2], d[4]) <= tol:
        s = 1.0 if np.cos(qa[4]) > 0 else -1.0
        return abs(wrap_pi((qa[3] + s * qa[5]) - (qb[3] + s * qb[5]))) <= tol
    return False


def test_joint_limits_interface():
    lim = np.asarray(JOINT_LIMITS, dtype=float)
    assert lim.shape == (6, 2)
    assert np.allclose(lim, ORACLE.limits, atol=1e-6), f"JOINT_LIMITS {lim} != {ORACLE.limits}"


def test_fk_random_q():
    rng = np.random.default_rng(SEED)
    bad = []
    worst = (0.0, 0.0)
    for q in _random_q(rng, N):
        T_rp = np.asarray(fk(q), dtype=float)
        T_or = ORACLE.fk(q)
        e = float(np.linalg.norm(T_rp[:3, 3] - T_or[:3, 3]))
        a = rot_angle(T_rp[:3, :3], T_or[:3, :3])
        worst = (max(worst[0], e), max(worst[1], a))
        if e >= POS_TOL or a >= ROT_TOL:
            bad.append(f"q={np.round(q, 6).tolist()}: dp={e:.5f} mm, dR={a:.2e} rad")
    assert not bad, _report(bad, f"FK (worst dp={worst[0]:.5f} mm, dR={worst[1]:.2e})")


def test_ik_random_poses():
    rng = np.random.default_rng(SEED + 1)
    bad, missing, branch_bad = [], [], []
    mapping: dict[tuple, int] = {}
    inverse: dict[int, tuple] = {}
    for q in _random_q(rng, N):
        T = ORACLE.fk(q)
        sols = list(ik(T))
        found = False
        for b, qs in sols:
            qs = np.asarray(qs, dtype=float)
            if not (0 <= int(b) <= 7):
                branch_bad.append(f"Zweig {b} ausserhalb 0..7")
            if not ORACLE.in_limits(qs, tol=1e-9):
                bad.append(f"Loesung ausserhalb der Grenzen: {np.round(qs, 6).tolist()}")
            Ts = ORACLE.fk(qs)
            e = float(np.linalg.norm(Ts[:3, 3] - T[:3, 3]))
            a = rot_angle(Ts[:3, :3], T[:3, :3])
            if e > POS_TOL or a > IK_ROT_TOL:
                bad.append(f"q={np.round(q, 6).tolist()} Zweig {b}: FK(Loesung) dp={e:.5f} mm dR={a:.2e}")
            found |= _same_config(q, qs)
            s = ORACLE.branch_signs(qs, eps=0.05)
            if 0 not in s:
                if mapping.setdefault(s, int(b)) != int(b) or inverse.setdefault(int(b), s) != s:
                    branch_bad.append(f"Zweig {b} bei Konfiguration {s}, "
                                      f"vorher {mapping[s]}/{inverse[int(b)]}")
        # je Zweig eine Konfiguration (2-pi-Varianten erlaubt), verschiedene Zweige verschieden
        reps: dict[int, np.ndarray] = {}
        for b, qs in sols:
            qs = np.asarray(qs, dtype=float)
            if int(b) in reps:
                if not _same_config(reps[int(b)], qs, tol=1e-3):
                    branch_bad.append(f"Zweig {b} liefert zwei verschiedene Konfigurationen")
            else:
                for bo, qo in reps.items():
                    if _same_config(qo, qs):
                        branch_bad.append(f"Zweige {bo} und {b} liefern dieselbe Konfiguration")
                reps[int(b)] = qs
        if not found:
            missing.append(f"q={np.round(q, 6).tolist()}: {len(sols)} Loesungen, erzeugende fehlt")
    assert not bad, _report(bad, "IK-Loesungen")
    assert not missing, _report(missing, "Vollstaendigkeit (erzeugende Loesung modulo 2 pi)")
    assert not branch_bad, _report(branch_bad, "Zweig-Bits")
    assert len(mapping) == 8, f"nur {len(mapping)} der 8 Zweige beobachtet: {mapping}"


def test_home_pose_valid():
    lim = np.asarray(JOINT_LIMITS, dtype=float)
    assert np.all(HOME_RAD >= lim[:, 0]) and np.all(HOME_RAD <= lim[:, 1])
    T_rp = np.asarray(fk(HOME_RAD), dtype=float)
    T_or = ORACLE.fk(HOME_RAD)
    assert np.linalg.norm(T_rp[:3, 3] - T_or[:3, 3]) < POS_TOL
    assert rot_angle(T_rp[:3, :3], T_or[:3, :3]) < ROT_TOL
    assert any(_same_config(HOME_RAD, np.asarray(qs)) for _, qs in ik(T_or)), "ik(fk(home)) ohne home"
