"""Kinematische Hilfen des Planers: TCP-Posen mit Gierwinkel psi, IK-Batches, Gelenkdistanzen."""

from __future__ import annotations

import numpy as np

from roboprint import frames
from roboprint.robot import JOINT_LIMITS, JOINT_VEL_LIMITS, fk_batch, ik_batch

#: Duese senkrecht nach unten, psi = 0: X_T = X_W, Y_T = -Y_W, Z_T = -Z_W (slicer.NOZZLE_DOWN_QUAT).
R_DOWN = np.diag([1.0, -1.0, -1.0])
#: Gelenke mit +-360-Grad-Grenze werden modulo 2pi verglichen (J3 hat +-160 Grad).
WRAPS = np.abs(JOINT_LIMITS[:, 1]) > np.pi + 1e-6
#: Gewichte der Gelenkdistanz: zeitartig, 1/v_max normiert auf J1.
JOINT_WEIGHTS = JOINT_VEL_LIMITS[0] / JOINT_VEL_LIMITS

_TWO_PI = 2.0 * np.pi


def wrap_pi(a: np.ndarray) -> np.ndarray:
    return np.pi - np.mod(np.pi - np.asarray(a, float), _TWO_PI)


def joint_diff(qb: np.ndarray, qa: np.ndarray) -> np.ndarray:
    """qb - qa, fuer die +-360-Grad-Gelenke kuerzester Weg modulo 2pi."""
    d = np.asarray(qb, float) - np.asarray(qa, float)
    return np.where(WRAPS, wrap_pi(d), d)


def rot_down(psi: np.ndarray) -> np.ndarray:
    """R_WT fuer Duese nach unten mit Gierwinkel psi um +Z_T: (n,) -> (n,3,3)."""
    psi = np.atleast_1d(np.asarray(psi, float))
    c, s = np.cos(psi), np.sin(psi)
    Rz = np.zeros((len(psi), 3, 3))
    Rz[:, 0, 0], Rz[:, 0, 1], Rz[:, 1, 0], Rz[:, 1, 1], Rz[:, 2, 2] = c, -s, s, c, 1.0
    return R_DOWN @ Rz


def psi_of(R_WT: np.ndarray) -> np.ndarray:  # noqa: N803
    """Gierwinkel aus R_WT (n,3,3) bei (nahezu) senkrechter Duese."""
    M = np.swapaxes(R_DOWN, -1, -2) @ R_WT
    return np.arctan2(M[..., 1, 0], M[..., 0, 0])


class Kin:
    """Bindet Workstation und Werkzeug: W-Posen <-> Flanschposen in B, FK in W."""

    def __init__(self, ws, tool) -> None:
        self.T_WB = frames.T_WB(ws)
        self.T_BW = frames.invert(self.T_WB)
        self.T_FT = frames.T_FT(tool)
        self.T_TF = frames.invert(self.T_FT)

    def T_BF(self, p_W: np.ndarray, psi: np.ndarray) -> np.ndarray:  # noqa: N802, N803
        """Flanschposen (n,4,4) in B fuer TCP-Positionen p_W (n,3) und psi (n,)."""
        p_W = np.atleast_2d(np.asarray(p_W, float))
        n = len(p_W)
        T = np.zeros((n, 4, 4))
        T[:, :3, :3] = rot_down(np.broadcast_to(psi, (n,)))
        T[:, :3, 3] = p_W
        T[:, 3, 3] = 1.0
        return self.T_BW @ T @ self.T_TF

    def ik(self, p_W: np.ndarray, psi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:  # noqa: N803
        """IK fuer alle 8 Zweige: (n,8,6), gueltig (n,8)."""
        if len(np.atleast_2d(p_W)) == 0:
            return np.zeros((0, 8, 6)), np.zeros((0, 8), dtype=bool)
        return ik_batch(self.T_BF(p_W, psi))

    def tcp_W(self, Q: np.ndarray) -> np.ndarray:  # noqa: N802
        """TCP-Posen in W (n,4,4)."""
        return self.T_WB @ fk_batch(Q) @ self.T_FT


def unwrap_sequence(Q: np.ndarray, q0: np.ndarray) -> np.ndarray:
    """Folge kanonischer Loesungen stetig machen: q_k = q_{k-1} + joint_diff(Q_k, q_{k-1}).

    Startet bei der 2pi-Variante von Q[0], die q0 am naechsten liegt. Verlaesst ein Gelenk die
    Grenzen, wird dort auf die naechste zulaessige Variante gesprungen (der Sprung faellt dann
    in der Dichtepruefung auf).
    """
    Q = np.asarray(Q, float)
    out = np.empty_like(Q)
    prev = np.asarray(q0, float)
    for k in range(len(Q)):
        q = prev + joint_diff(Q[k], prev)
        bad = (q < JOINT_LIMITS[:, 0] - 1e-9) | (q > JOINT_LIMITS[:, 1] + 1e-9)
        if bad.any():
            q = np.where(bad, q - np.sign(q) * _TWO_PI, q)
        out[k] = q
        prev = q
    return out


def nearest_variant(q: np.ndarray, q_ref: np.ndarray) -> np.ndarray:
    """2pi-Variante von q, die q_ref am naechsten liegt (in den Grenzen)."""
    q = np.asarray(q_ref, float) + joint_diff(q, q_ref)
    bad = (q < JOINT_LIMITS[:, 0] - 1e-9) | (q > JOINT_LIMITS[:, 1] + 1e-9)
    return np.where(bad, q - np.sign(q) * _TWO_PI, q)
