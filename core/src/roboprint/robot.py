"""Kinematik des Doosan M1013: FK aus der URDF-Kette, analytische IK (OPW), Gelenkgrenzen.

Konvention (SPEC §2): q in rad, **Doosan-Steuerungskonvention = URDF-Nullstellung**,
Translationen in mm. `fk(q)` liefert T_BF (Basis `base_link` -> Flansch `link_6`).
Die FK rechnet exakt die URDF-Kette (Origins rpy/xyz, Achsen), auch deren gerundete
Winkel (rpy = 1.571 statt pi/2, Abweichung 2e-4 rad, bis ~0,4 mm am Flansch).

IK: analytische OPW-Loesung je Zweig auf der idealisierten Kette (rpy auf Vielfache von
pi/2 gerundet, sphaerisches Handgelenk), dann Fixpunkt-Korrektur der Zielpose und
Newton-Schritte auf der exakten Kette. Jede gelieferte Loesung erfuellt fk(q) == T auf
< 1e-4 mm / 1e-8 rad (typisch 1e-12). Nahe Singularitaeten, wo zwei Ideal-Zweige auf
dieselbe exakte Loesung fallen, wird der fehlende Zweig aus der gespiegelten Loesung
neu gestartet.

Geometrie (aus der URDF, q = 0 ist die gestreckte Senkrechte):
d1 = 152,5 (Schulterhoehe), b = 34,5 (Seitenversatz entlang y von Glied 1),
L2 = 620 (Oberarm), L3 = 559 (Unterarm bis Handgelenkzentrum C), d6 = 121 (C -> Flansch).
C = p_F - d6 * z_F. Ideal gilt im um q1 gedrehten Glied-1-Frame
r = L2 sin q2 + L3 sin(q2 + q3) (horizontale Reichweite von C vor der J1-Achse).

Zweig-Bits (spec/ARTEFAKTE.md, Annahme A; Bitlage wie die `sol_space`-Tabelle des Doosan-
`ikin`, Manual 3.4). Ausgewertet auf der exakten Kette mit S = Ursprung J2 (Schulter),
E = Ursprung J3 (Ellbogen), C = Ursprung J5 (Handgelenkzentrum), n = Achse J2,
z4/z5/z6 = Achsen J4/J5/J6, alles in B. So liegen die Grenzen genau auf den
Singularitaeten der URDF-Kette.

- **Bit 2 (Wert 4) Schulter Righty**: r = (n x e_z) . C < 0, d. h. das Handgelenkzentrum
  liegt hinter der J1-Achse (Oberarm ueber Kopf nach hinten). Lefty: r >= 0; der Oberarm
  sitzt dann, von oben in Reichrichtung gesehen, links der J1-Achse. Ideal: r wie oben.
- **Bit 1 (Wert 2) Ellbogen Above**: E liegt in der Armebene oberhalb der Geraden S -> C:
  sign(r) * n . ((E - S) x (C - S)) > 0 (sign(0) = +1). Ideal: sin(q3) * sign(r) > 0,
  also in Lefty Above <=> q3 > 0, in Righty Above <=> q3 < 0.
- **Bit 0 (Wert 1) Handgelenk Flip**: (z4 x z6) . z5 < 0. Ideal: q5 auf (-pi, pi]
  gewickelt < 0. NoFlip: q5 in [0, pi].

Home (0, 0, 90, 0, 90, 0) Grad ist Lefty/Above/NoFlip = Zweig 2.
Singularitaeten: Handgelenk (sin q5 = 0, J4 und J6 fluchten), Schulter (r = 0, C auf der
J1-Achse), Ellbogen gestreckt (q3 = -0,0117 Grad in der URDF-Kette, Rand der Reichweite).
Genau an der Handgelenk-Singularitaet waehlt `ik` q4 = 0 und liefert nur eine Loesung
(beide Handgelenkzweige fallen zusammen); `ik_nearest` uebernimmt dort q4 aus der Referenz.

`ik` liefert je Zweig hoechstens eine kanonische Loesung (alle Gelenke auf (-pi, pi]) und
nur Loesungen in `JOINT_LIMITS`; `ik_batch` ist die vektorisierte Fassung fuer den Planer.
Die um +-2pi verschobenen Varianten der +-360-Grad-Gelenke liefern `turn_variants(q)`,
`nearest_turn(q, q_ref)` und `ik_nearest(T, q_ref, branch)`.
"""

from __future__ import annotations

import itertools

import numpy as np

from roboprint import frames
from roboprint.assets import load_robot, load_tool

_ROBOT = load_robot()

JOINT_LIMITS: np.ndarray = _ROBOT.joint_limits.copy()  # 6x2 rad
JOINT_VEL_LIMITS: np.ndarray = _ROBOT.vel_limits.copy()  # rad/s, 120/120/180/225/225/225 Grad/s
HOME_Q: np.ndarray = np.radians([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])

SHOULDER_RIGHTY = 4
ELBOW_ABOVE = 2
WRIST_FLIP = 1

_TWO_PI = 2.0 * np.pi
_LIMIT_TOL = 1e-9
_WRIST_SING = 1e-9  # |sin q5| darunter: analytisch singulaer behandelt
_REACH_TOL_MM2 = 1.0  # rho^2-Toleranz (ideal vs. exakt) an der Schulter-Singularitaet
_REACH_TOL_C3 = 5e-3  # cos q3-Toleranz am Rand der Reichweite; Endpruefung entscheidet
_FIXPOINT_ITERS = 2
_NEWTON_ITERS = 40
_ACCEPT_MM = 1e-4
_ACCEPT_RAD = 1e-8

# --- exakte URDF-Kette -------------------------------------------------------------------
_ORIG = np.stack([j.origin for j in _ROBOT.joints])  # 6x4x4
_AXES = np.stack([j.axis for j in _ROBOT.joints])  # 6x3
_Z_AXES = bool(np.allclose(_AXES, [0.0, 0.0, 1.0]))

# --- idealisierte Kette fuer die analytische Loesung ------------------------------------
_IDEAL_R = np.round(_ORIG[:, :3, :3])
_D1 = _ORIG[0, 2, 3]
_B = _ORIG[1, 1, 3]
_L2 = _ORIG[2, 0, 3]
_L3 = -_ORIG[3, 1, 3]
_D6 = -_ORIG[5, 1, 3]
_RX_MINUS_HALF_PI = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])


def _check_geometry() -> None:
    expect = np.array([[0, 0, 1], [0, 1, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0], [0, 1, 0]], dtype=bool)
    nonzero = np.abs(_ORIG[:, :3, 3]) > 1e-9
    rz90 = _rz_batch(np.array(np.pi / 2))
    ideal_ok = np.allclose(_IDEAL_R[0], np.eye(3)) and np.allclose(_IDEAL_R[2], rz90)
    near_ideal = np.abs(_ORIG[:, :3, :3] - _IDEAL_R).max() < 1e-3
    if not (ideal_ok and near_ideal and _Z_AXES and np.array_equal(nonzero, expect)):
        raise ValueError("URDF-Kette passt nicht zur OPW-Geometrie des M1013")


def _mm(A: np.ndarray, M: np.ndarray) -> np.ndarray:
    """(N,3,3) @ (3,3), schneller als Broadcasting-matmul."""
    return (A.reshape(-1, 3) @ M).reshape(A.shape)


def _mv(A: np.ndarray, v: np.ndarray) -> np.ndarray:
    """(N,3,3) @ (3,) -> (N,3)."""
    return (A.reshape(-1, 3) @ v).reshape(A.shape[0], 3)


def _joint_rot(q: np.ndarray, i: int) -> np.ndarray:
    """Drehung um eine allgemeine Gelenkachse (Rodrigues), batch: q (N,) -> (N,3,3)."""
    c, s = np.cos(q), np.sin(q)
    k = _AXES[i]
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s[:, None, None] * K + (1 - c)[:, None, None] * (K @ K)


def _chain(Q: np.ndarray, with_axes: bool = False):
    """Exakte URDF-Kette. Liefert T (N,4,4) und optional Gelenkachsen z und -ursprunge p (N,6,3)."""
    n = Q.shape[0]
    R = np.empty((n, 3, 3))
    R[:] = np.eye(3)
    p = np.zeros((n, 3))
    if with_axes:
        zs = np.empty((n, 6, 3))
        ps = np.empty((n, 6, 3))
    C, S = np.cos(Q), np.sin(Q)
    for i in range(6):
        p += _mv(R, _ORIG[i, :3, 3])
        R = _mm(R, _ORIG[i, :3, :3])
        if with_axes:
            zs[:, i] = _mv(R, _AXES[i])
            ps[:, i] = p
        if _Z_AXES:
            c, s = C[:, i, None], S[:, i, None]
            r0 = R[:, :, 0].copy()
            r1 = R[:, :, 1]
            R[:, :, 0] = c * r0 + s * r1
            R[:, :, 1] = c * r1 - s * r0
        else:
            R = R @ _joint_rot(Q[:, i], i)
    T = np.zeros((n, 4, 4))
    T[:, :3, :3] = R
    T[:, :3, 3] = p
    T[:, 3, 3] = 1.0
    if with_axes:
        return T, zs, ps
    return T


def fk_batch(Q: np.ndarray) -> np.ndarray:
    """Vektorisierte FK: Q (N,6) rad -> T_BF (N,4,4) in mm."""
    Q = np.asarray(Q, dtype=float).reshape(-1, 6)
    return _chain(Q)


def fk(q: np.ndarray) -> np.ndarray:
    """Vorwaertskinematik: 4x4 T_BF in mm, q in rad, Doosan-Konvention."""
    return _chain(np.asarray(q, dtype=float).reshape(1, 6))[0]


def jacobian(q: np.ndarray) -> np.ndarray:
    """Geometrische 6x6-Jacobi-Matrix des Flansches in B: Zeilen (v mm/rad, omega)."""
    return _jacobian_batch(np.asarray(q, dtype=float).reshape(1, 6))[1][0]


def _jacobian_batch(Q: np.ndarray):
    T, z, p = _chain(Q, with_axes=True)
    J = np.empty((Q.shape[0], 6, 6))
    J[:, :3, :] = np.cross(z, T[:, None, :3, 3] - p).transpose(0, 2, 1)
    J[:, 3:, :] = z.transpose(0, 2, 1)
    return T, J


def wrap(q: np.ndarray) -> np.ndarray:
    """Winkel auf (-pi, pi]."""
    q = np.asarray(q, dtype=float)
    return np.pi - np.mod(np.pi - q, _TWO_PI)


def branch_of(q: np.ndarray):
    """Zweig 0-7 einer Gelenkstellung (Definition im Moduldocstring). (6,) -> int, (N,6) -> (N,).

    Ausgewertet auf der exakten URDF-Kette, damit die Zweiggrenzen genau auf deren
    Singularitaeten liegen.
    """
    Q = np.asarray(q, dtype=float)
    _, z, p = _chain(Q.reshape(-1, 6), with_axes=True)
    return int(_branch_from_frames(z, p)[0]) if Q.ndim == 1 else _branch_from_frames(z, p)


def _branch_from_frames(z: np.ndarray, p: np.ndarray) -> np.ndarray:
    n2, s_, e_, c_ = z[:, 1], p[:, 1], p[:, 2], p[:, 4]  # J2-Achse, Schulter, Ellbogen, Handgelenk
    r = np.einsum("ij,ij->i", np.cross(n2, [0.0, 0.0, 1.0]), c_)
    elbow = np.einsum("ij,ij->i", n2, np.cross(e_ - s_, c_ - s_)) * np.where(r >= 0.0, 1.0, -1.0)
    wrist = np.einsum("ij,ij->i", np.cross(z[:, 3], z[:, 5]), z[:, 4])
    b = np.where(r < 0.0, SHOULDER_RIGHTY, 0) + np.where(elbow > 0.0, ELBOW_ABOVE, 0)
    return (b + np.where(wrist < 0.0, WRIST_FLIP, 0)).astype(int)


def in_limits(q: np.ndarray) -> np.ndarray | bool:
    """True, wenn q (6,) bzw. jede Zeile von (N,6) in `JOINT_LIMITS` liegt."""
    Q = np.asarray(q, dtype=float)
    ok = np.all((Q >= JOINT_LIMITS[:, 0] - _LIMIT_TOL) & (Q <= JOINT_LIMITS[:, 1] + _LIMIT_TOL), axis=-1)
    return bool(ok) if Q.ndim == 1 else ok


def _rot_err(R_target: np.ndarray, R: np.ndarray) -> np.ndarray:
    """Drehvektor (in B) von R nach R_target, batch (N,3,3) -> (N,3)."""
    E = R_target @ R.transpose(0, 2, 1)
    v = 0.5 * np.stack([E[:, 2, 1] - E[:, 1, 2], E[:, 0, 2] - E[:, 2, 0], E[:, 1, 0] - E[:, 0, 1]], axis=1)
    sn = np.linalg.norm(v, axis=1)
    cs = 0.5 * (np.trace(E, axis1=1, axis2=2) - 1.0)
    ang = np.arctan2(sn, cs)
    scale = np.where(sn > 1e-12, ang / np.maximum(sn, 1e-300), 1.0)
    return v * scale[:, None]


def _rz_batch(a: np.ndarray) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    R = np.zeros(a.shape + (3, 3))
    R[..., 0, 0] = c
    R[..., 0, 1] = -s
    R[..., 1, 0] = s
    R[..., 1, 1] = c
    R[..., 2, 2] = 1.0
    return R


def _ideal_ik(T: np.ndarray, branch: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Analytische OPW-Loesung der idealisierten Kette fuer Zweig `branch` je Pose.

    T (M,4,4), branch (M,) -> q (M,6), gueltig (M,). Die Zweig-Bits erfuellen
    branch_of(q) == branch ausser an Singularitaeten (dort faellt Flip auf NoFlip).
    """
    R = T[:, :3, :3]
    c = T[:, :3, 3] - _D6 * R[:, :, 2]
    rho2 = c[:, 0] ** 2 + c[:, 1] ** 2 - _B**2
    rho = np.sqrt(np.maximum(rho2, 0.0))
    h = c[:, 2] - _D1
    s = np.where(branch & SHOULDER_RIGHTY, -1.0, 1.0)
    r = s * rho
    q1 = np.arctan2(c[:, 1], c[:, 0]) - np.arctan2(_B, r)
    c3 = (r * r + h * h - _L2**2 - _L3**2) / (2.0 * _L2 * _L3)
    valid = (rho2 > -_REACH_TOL_MM2) & (np.abs(c3) <= 1.0 + _REACH_TOL_C3)
    a3 = np.arccos(np.clip(c3, -1.0, 1.0))
    q3 = np.where(branch & ELBOW_ABOVE, s * a3, -s * a3)
    q2 = np.arctan2(r, h) - np.arctan2(_L3 * np.sin(q3), _L2 + _L3 * np.cos(q3))
    R03 = _mm(_mm(_rz_batch(q1), _IDEAL_R[1]) @ _rz_batch(q2 + q3), _IDEAL_R[2])
    # R36 = Rx(pi/2) Rz(q4) Rx(-pi/2) Rz(q5) Rx(pi/2) Rz(q6) = Ry(-q4) Rz(q5) Ry(-q6) Rx(pi/2)
    M = _mm(R03.transpose(0, 2, 1) @ R, _RX_MINUS_HALF_PI)
    sb = np.hypot(M[:, 0, 1], M[:, 2, 1])
    sg = np.where(branch & WRIST_FLIP, -1.0, 1.0)
    q5 = np.arctan2(sg * sb, M[:, 1, 1])
    q4 = -np.arctan2(sg * M[:, 2, 1], -sg * M[:, 0, 1])
    q6 = -np.arctan2(sg * M[:, 1, 2], sg * M[:, 1, 0])
    sing = sb < _WRIST_SING
    if sing.any():
        up = M[:, 1, 1] > 0.0  # q5 = 0: M = Ry(-(q4 + q6)); q5 = pi: M Rz(pi)^T = Ry(q6 - q4)
        q4 = np.where(sing, 0.0, q4)
        q5 = np.where(sing, np.where(up, 0.0, np.pi), q5)
        q6_s = np.where(up, -np.arctan2(M[:, 0, 2], M[:, 0, 0]), np.arctan2(-M[:, 0, 2], -M[:, 0, 0]))
        q6 = np.where(sing, q6_s, q6)
        valid &= ~(sing & (branch & WRIST_FLIP).astype(bool))
    return np.stack([q1, q2, q3, q4, q5, q6], axis=1), valid


def _inv(T: np.ndarray) -> np.ndarray:
    Ti = np.zeros_like(T)
    Rt = T[..., :3, :3].swapaxes(-1, -2)
    Ti[..., :3, :3] = Rt
    Ti[..., :3, 3] = -(Rt @ T[..., :3, 3, None])[..., 0]
    Ti[..., 3, 3] = 1.0
    return Ti


def _pose_err(Ta: np.ndarray, Tb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Positionsfehler (mm) und Drehwinkel (rad) zwischen Posen, batch."""
    ep = np.linalg.norm(Ta[:, :3, 3] - Tb[:, :3, 3], axis=1)
    er = np.linalg.norm(_rot_err(Ta[:, :3, :3], Tb[:, :3, :3]), axis=1)
    return ep, er


def ik_batch(T_BF: np.ndarray):  # noqa: N803
    """Vektorisierte IK: T (N,4,4) -> q (N,8,6) je Zweig-Index, gueltig (N,8).

    q[:, b] ist kanonisch (alle Gelenke auf (-pi, pi]). gueltig heisst: erreichbar, in den
    Grenzen, fk(q) == T auf 1e-4 mm / 1e-8 rad und branch_of(q) == b.
    Ablauf: analytische Loesung der idealisierten Kette je Zweig, Fixpunkt-Korrektur der
    Zielpose auf die exakte URDF-Kette (T_ideal <- T_ideal * fk(q)^-1 * T), danach
    Newton-Schritte auf der exakten Kette und Einordnung nach dem exakten Zweig. Nahe der
    Ellbogen- bzw. Handgelenk-Singularitaet koennen zwei Ideal-Zweige auf dieselbe exakte
    Loesung fallen; fehlende Zweige werden dann aus der an der exakten Singularitaet
    gespiegelten Nachbarloesung neu gestartet.
    """
    T = np.asarray(T_BF, dtype=float).reshape(-1, 4, 4)
    n = T.shape[0]
    Tt = np.repeat(T, 8, axis=0)
    br = np.tile(np.arange(8), n)
    Ta = Tt
    for it in range(_FIXPOINT_ITERS):
        Q, valid = _ideal_ik(Ta, br)
        if it < _FIXPOINT_ITERS - 1:
            Ta = _ideal_fk(Q) @ _inv(_chain(Q)) @ Tt
    s_sh = np.where(br & SHOULDER_RIGHTY, -1.0, 1.0)
    side = np.stack([np.where(br & ELBOW_ABOVE, s_sh, -s_sh), np.where(br & WRIST_FLIP, -1.0, 1.0)], axis=1)
    Q, ok, label = _refine(Tt, Q, valid, side)
    out_q = np.full((n, 8, 6), np.nan)
    out_ok = np.zeros((n, 8), dtype=bool)
    _scatter(out_q, out_ok, np.nonzero(ok)[0] // 8, Q[ok], label[ok], prefer=label[ok] == br[ok])
    missing = np.nonzero(~out_ok.all(axis=1) & out_ok.any(axis=1))[0]
    if missing.size:
        _fill_mirrored(T, out_q, out_ok, missing)
    return out_q, out_ok


def _scatter(out_q, out_ok, pose, Q, label, prefer=None) -> None:
    """Loesungen nach (Pose, Zweig) einsortieren; belegte Plaetze bleiben, `prefer` zuerst."""
    order = np.argsort(~prefer, kind="stable") if prefer is not None else np.arange(len(pose))
    key = pose[order] * 8 + label[order]
    _, first = np.unique(key, return_index=True)
    sel = order[first]
    free = ~out_ok[pose[sel], label[sel]]
    sel = sel[free]
    out_q[pose[sel], label[sel]] = Q[sel]
    out_ok[pose[sel], label[sel]] = True


def _fill_mirrored(T, out_q, out_ok, poses) -> None:
    """Fehlende Zweige aus Nachbarloesungen spiegeln (Ellbogen bzw. Handgelenk) und neu loesen."""
    seeds, idx = [], []
    for i in poses:
        for b in np.nonzero(~out_ok[i])[0]:
            for bit, mirror in ((ELBOW_ABOVE, _mirror_elbow), (WRIST_FLIP, _mirror_wrist)):
                if out_ok[i, b ^ bit]:
                    seeds.append(mirror(out_q[i, b ^ bit]))
                    idx.append(i)
    if not seeds:
        return
    idx_a = np.array(idx)
    Q, ok, label = _refine(T[idx_a], np.array(seeds), np.ones(len(seeds), dtype=bool))
    _scatter(out_q, out_ok, idx_a[ok], Q[ok], label[ok])


def _mirror_elbow(q: np.ndarray) -> np.ndarray:
    """Spiegelung an der exakten Ellbogen-Singularitaet (q3 -> 2 d3 - q3, gleicher Abstand S-C)."""
    q = q.copy()
    d = q[..., 2] - _DELTA3
    q[..., 1] += 2.0 * _L3 / (_L2 + _L3) * d
    q[..., 2] = _DELTA3 - d
    return q


def _mirror_wrist(q: np.ndarray) -> np.ndarray:
    """Handgelenk-Gegenloesung (q4 + pi, 2 d5 - q5, q6 + pi)."""
    q = q.copy()
    q[..., 3] += np.pi
    q[..., 4] = 2.0 * _DELTA5 - q[..., 4]
    q[..., 5] += np.pi
    return q


def _sides(Q: np.ndarray) -> np.ndarray:
    """Seite relativ zur exakten Ellbogen- und Handgelenk-Singularitaet (je +-1)."""
    return np.stack([np.sign(np.sin(Q[:, 2] - _DELTA3)), np.sign(np.sin(Q[:, 4] - _DELTA5))], axis=1)


def _refine(
    T: np.ndarray, Q: np.ndarray, valid: np.ndarray, side: np.ndarray | None = None, lam: float = 1e-12
):
    """Newton auf der exakten Kette, Grenzen und Fehler pruefen, exakten Zweig bestimmen."""
    Q, ep, er = _newton(T, Q, valid, _sides(Q) if side is None else side, lam=lam)
    Q = wrap(Q)
    ok = valid & (ep < _ACCEPT_MM) & (er < _ACCEPT_RAD) & in_limits(Q)
    label = np.full(Q.shape[0], -1)
    if ok.any():
        _, z, p = _chain(Q[ok], with_axes=True)
        label[ok] = _branch_from_frames(z, p)
    return Q, ok, label


def _newton(T, Q, active, side, iters: int = _NEWTON_ITERS, lam: float = 1e-12):  # noqa: N803
    """Newton-Verfahren (minimal gedaempft) auf der exakten Kette fuer die aktiven Zeilen.

    `side` (M,2) haelt jede Zeile auf ihrer Seite der Ellbogen- und Handgelenk-Singularitaet
    (0 = frei): Ein Schritt ueber die Grenze wird gespiegelt. So landen zwei Zweige nahe
    einer fast doppelten Wurzel nicht auf derselben Loesung.
    """
    Q = Q.copy()
    ep = np.full(Q.shape[0], np.inf)
    er = np.full(Q.shape[0], np.inf)
    W = np.array([1e-3, 1e-3, 1e-3, 1.0, 1.0, 1.0])  # mm -> m, damit J gut skaliert ist
    act = np.nonzero(active)[0]
    prev = np.full(act.size, np.inf)
    for it in range(iters + 1):
        if act.size == 0:
            break
        Tc, z, p = _chain(Q[act], with_axes=True)
        Ts = T[act]
        dp = Ts[:, :3, 3] - Tc[:, :3, 3]
        dr = _rot_err(Ts[:, :3, :3], Tc[:, :3, :3])
        ep[act] = np.linalg.norm(dp, axis=1)
        er[act] = np.linalg.norm(dr, axis=1)
        # Stopp: konvergiert, divergiert (> 50 mm) oder kein Fortschritt mehr (Rundungsgrenze).
        # Nahe Singularitaeten (fast doppelte Wurzel) konvergiert Newton nur linear (~0,5).
        e_now = ep[act] + 1e3 * er[act]
        todo = ((ep[act] > 1e-11) | (er[act] > 1e-14)) & (ep[act] < 50.0) & ((e_now < 0.9 * prev) | (it < 4))
        if it == iters or not todo.any():
            break
        act, Tc, z, p, prev = act[todo], Tc[todo], z[todo], p[todo], e_now[todo]
        e = np.concatenate([dp[todo], dr[todo]], axis=1) * W
        J = np.empty((act.size, 6, 6))
        J[:, :3, :] = np.cross(z, Tc[:, None, :3, 3] - p).transpose(0, 2, 1) * 1e-3
        J[:, 3:, :] = z.transpose(0, 2, 1)
        Qa = Q[act] + _newton_step(J, e, lam)
        crossed = _sides(Qa) * side[act] < 0
        Qa[crossed[:, 0]] = _mirror_elbow(Qa[crossed[:, 0]])
        Qa[crossed[:, 1]] = _mirror_wrist(Qa[crossed[:, 1]])
        Q[act] = Qa
    return Q, ep, er


def _newton_step(J: np.ndarray, e: np.ndarray, lam: float) -> np.ndarray:
    """Newton-Schritt J dq = e. LU fuer gut gestellte Zeilen; nahe singulaere Zeilen (oder
    jede Zeile bei lam > 1e-12) ueber die gedaempfte Pseudoinverse per SVD."""
    dq = np.full(e.shape, np.nan)
    if lam <= 1e-12:
        try:
            dq = np.linalg.solve(J, e[..., None])[..., 0]
        except np.linalg.LinAlgError:
            pass
    bad = ~np.all(np.isfinite(dq), axis=1) | (np.abs(dq).max(axis=1) > 0.5)
    if bad.any():
        U, sv, Vt = np.linalg.svd(J[bad])
        coef = np.einsum("nji,nj->ni", U, e[bad]) * (sv / (sv * sv + lam * lam))
        dq[bad] = np.einsum("nji,nj->ni", Vt, coef)
    return dq


def _ideal_fk(Q: np.ndarray) -> np.ndarray:
    """FK der idealisierten Kette (nur fuer die Fixpunkt-Korrektur)."""
    R = _mm(_mm(_rz_batch(Q[:, 0]), _IDEAL_R[1]) @ _rz_batch(Q[:, 1] + Q[:, 2]), _IDEAL_R[2] @ _IDEAL_R[3])
    R = _mm(_mm(R @ _rz_batch(Q[:, 3]), _IDEAL_R[4]) @ _rz_batch(Q[:, 4]), _IDEAL_R[5]) @ _rz_batch(Q[:, 5])
    r = _L2 * np.sin(Q[:, 1]) + _L3 * np.sin(Q[:, 1] + Q[:, 2])
    h = _L2 * np.cos(Q[:, 1]) + _L3 * np.cos(Q[:, 1] + Q[:, 2])
    c1, s1 = np.cos(Q[:, 0]), np.sin(Q[:, 0])
    C = np.stack([c1 * r - s1 * _B, s1 * r + c1 * _B, _D1 + h], axis=1)
    T = np.zeros((Q.shape[0], 4, 4))
    T[:, :3, :3] = R
    T[:, :3, 3] = C + _D6 * R[:, :, 2]
    T[:, 3, 3] = 1.0
    return T


def ik(T_BF: np.ndarray) -> list[tuple[int, np.ndarray]]:  # noqa: N803
    """Inverse Kinematik: Liste (Zweig 0-7, q); nur Loesungen innerhalb der Grenzen.

    Je Zweig hoechstens eine kanonische Loesung (alle Gelenke auf (-pi, pi]), sortiert nach
    Zweig; es gilt branch_of(q) == Zweig. Leere Liste: Pose unerreichbar.
    """
    Q, ok = ik_batch(np.asarray(T_BF, dtype=float)[None])
    return [(b, Q[0, b].copy()) for b in range(8) if ok[0, b]]


def turn_variants(q: np.ndarray) -> list[np.ndarray]:
    """Alle um Vielfache von 2pi verschobenen Varianten von q innerhalb der Grenzen."""
    q = np.asarray(q, dtype=float)
    options = []
    for i in range(6):
        lo, hi = JOINT_LIMITS[i]
        k0 = int(np.ceil((lo - _LIMIT_TOL - q[i]) / _TWO_PI))
        k1 = int(np.floor((hi + _LIMIT_TOL - q[i]) / _TWO_PI))
        options.append([q[i] + k * _TWO_PI for k in range(k0, k1 + 1)])
    return [np.array(v) for v in itertools.product(*options)]


def nearest_turn(q: np.ndarray, q_ref: np.ndarray) -> np.ndarray:
    """Je Gelenk die 2pi-Variante von q, die q_ref am naechsten liegt und in den Grenzen ist."""
    q = np.asarray(q, dtype=float).copy()
    q_ref = np.asarray(q_ref, dtype=float)
    for i in range(6):
        lo, hi = JOINT_LIMITS[i]
        k = np.round((q_ref[i] - q[i]) / _TWO_PI)
        cands = q[i] + _TWO_PI * np.array([k - 1, k, k + 1])
        cands = cands[(cands >= lo - _LIMIT_TOL) & (cands <= hi + _LIMIT_TOL)]
        if cands.size:
            q[i] = cands[np.argmin(np.abs(cands - q_ref[i]))]
    return q


def ik_nearest(T_BF: np.ndarray, q_ref: np.ndarray, branch: int | None = None):  # noqa: N803
    """Loesung (Zweig, q) nahe q_ref: je Gelenk die naechste 2pi-Variante, dann die Loesung
    mit kleinster max. Gelenkdistanz. `branch` beschraenkt auf einen Zweig. None, wenn keine.

    Nahe der Handgelenk-Singularitaet (|sin q5| < 1e-4) wird q4 = q4_ref gesetzt, q6 angepasst
    und auf der exakten Kette neu eingepasst.
    """
    q_ref = np.asarray(q_ref, dtype=float)
    T = np.asarray(T_BF, dtype=float)
    best, best_d = None, np.inf
    for b, q in ik(T):
        if branch is not None and b != branch:
            continue
        if abs(np.sin(q[4])) < 1e-4:
            # J4/J6 fluchten nur in der Idealkette exakt: nach dem Umverteilen neu einpassen
            qw = _wrist_to_ref(q, q_ref)[None]
            Qr, ok, _ = _refine(T[None], qw, np.ones(1, dtype=bool), np.zeros((1, 2)), lam=1e-5)
            if ok[0]:
                q = Qr[0]
        qn = nearest_turn(q, q_ref)
        d = float(np.max(np.abs(qn - q_ref)))
        if d < best_d:
            best, best_d = (branch_of(qn), qn), d
    return best


def _wrist_to_ref(q: np.ndarray, q_ref: np.ndarray) -> np.ndarray:
    q = q.copy()
    sign = 1.0 if np.cos(q[4]) > 0.0 else -1.0  # q5 = 0: q4 + q6 fest, q5 = pi: q6 - q4 fest
    total = q[5] + sign * q[3]
    q[3] = q_ref[3]
    q[5] = total - sign * q[3]
    return q


def tcp_pose(q: np.ndarray, T_FT: np.ndarray | None = None) -> np.ndarray:  # noqa: N803
    """T_BT = fk(q) @ T_FT; Default-Werkzeug `tools/30gut.json`."""
    return fk(q) @ (default_T_FT() if T_FT is None else T_FT)


def ik_tcp(T_BT: np.ndarray, T_FT: np.ndarray | None = None) -> list[tuple[int, np.ndarray]]:  # noqa: N803
    """IK fuer eine TCP-Pose T_BT: ik(T_BT @ inv(T_FT))."""
    T_FT = default_T_FT() if T_FT is None else T_FT
    return ik(np.asarray(T_BT, dtype=float) @ np.linalg.inv(T_FT))


def default_T_FT() -> np.ndarray:
    """T_FT des Default-Werkzeugs (`tools/30gut.json`, `tcp_frame`)."""
    return frames.T_FT(load_tool())


_check_geometry()


def _singular_offsets() -> tuple[float, float]:
    """Exakte Ellbogen- und Handgelenk-Singularitaet als Gelenkwinkel (q3 = d3, q5 = d5)."""
    Q = np.array([[0.0, 0.3, 0.0, 0.0, 0.0, 0.0], [0.0, 0.3, np.pi / 2, 0.0, np.pi / 2, 0.0]])
    _, z, p = _chain(Q, with_axes=True)
    f = np.einsum("ij,ij->i", z[:, 1], np.cross(p[:, 2] - p[:, 1], p[:, 4] - p[:, 1]))
    g = np.einsum("ij,ij->i", np.cross(z[:, 3], z[:, 5]), z[:, 4])
    d3 = float(np.arctan2(-f[0], f[1]))
    d5 = float(np.arctan2(-g[0], g[1]))
    if max(abs(d3), abs(d5)) > 1e-2:
        raise ValueError("Singularitaets-Offsets der URDF unplausibel")
    return d3, d5


_DELTA3, _DELTA5 = _singular_offsets()
