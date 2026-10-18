"""Kinematik des Doosan M1013: FK aus der URDF-Kette, analytische IK (OPW), Gelenkgrenzen.

Gelenkwinkel stehen in Doosan-Steuerungskonvention (= URDF-Nullstellung), Einheit rad,
Translationen in mm. Zweig-Bits der IK (Annahme A nach der `sol_space`-Tabelle des
Doosan-Manuals): Bit 2 (Wert 4) = Schulter Righty, Bit 1 (Wert 2) = Ellbogen Above,
Bit 0 (Wert 1) = Handgelenk Flip. 0 = Lefty/Below/NoFlip, 7 = Righty/Above/Flip.
Die geometrische Definition wird bei der Implementierung hier ergaenzt.
"""

from __future__ import annotations

import numpy as np

JOINT_LIMITS: np.ndarray = np.zeros((6, 2))  # 6x2 in rad; wird aus der URDF befuellt


def fk(q: np.ndarray) -> np.ndarray:
    """Vorwaertskinematik: 4x4 T_BF in mm, q in rad, Doosan-Konvention."""
    raise NotImplementedError


def ik(T_BF: np.ndarray) -> list[tuple[int, np.ndarray]]:  # noqa: N803 - Name nach Vertrag
    """Inverse Kinematik: Liste (Zweig 0-7, q); nur Loesungen innerhalb der Grenzen."""
    raise NotImplementedError
