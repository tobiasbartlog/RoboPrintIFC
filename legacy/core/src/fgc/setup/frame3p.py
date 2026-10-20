"""3-Punkt-Antast-Verfahren: drei Roboterposen → wall_to_base-Frame (ADR-006).

Konvention (rechtshändig, Einheiten mm, Quaternion [w, x, y, z] nach ADR-006):

- **P0** — Wandnullpunkt (Ursprung des Wandkoordinatensystems), vom
  Teach-Pendant ablesen, wenn der Roboter dort positioniert ist.
- **P1** — Punkt auf der positiven X-Achse (Wandlängsrichtung), mindestens
  50 mm von P0 entfernt antasten.
- **P2** — Punkt in der XY-Ebene, aber **nicht** auf der X-Achse (z. B.
  50..200 mm in Wandhöhenrichtung von P0 entfernt).

Das Ergebnis ist der Frame ``wall_to_base``:
- ``pos_mm`` = P0 in Roboterbasis-Koordinaten
- ``quat`` = Quaternion, der die Wandorientierung in der Roboterbasis
  beschreibt (X → Wandlänge, Y ≈ Wandhöhe, Z = Wandnormale, rechtshändig)

Dieses Verfahren ist der Industriestandard-Dreipunkt-Frame-Aufbau aus der
Roboter-Teach-Pendant-Praxis (vgl. Fanuc FRAME SET / KUKA ToolBase).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def three_point_frame(
    p0: Sequence[float],
    p1: Sequence[float],
    p2: Sequence[float],
) -> tuple[list[float], list[float]]:
    """Berechnet Frame (pos_mm, quat [w, x, y, z]) aus drei Roboterposen.

    Parameters
    ----------
    p0:
        Wandursprung in mm (Teach-Pendant-Ablesung an Position „Nullpunkt").
    p1:
        Punkt auf der positiven X-Achse in mm (Wandlängsrichtung).
    p2:
        Punkt in der XY-Ebene in mm, **nicht** auf der X-Achse
        (Wandhöhenrichtung, definiert die Wandebene).

    Returns
    -------
    pos_mm:
        Liste [x, y, z] — Wandursprung P0 in Roboterbasis-Koordinaten.
    quat:
        Liste [w, x, y, z] — Einheitsquaternion der Wandorientierung.

    Raises
    ------
    ValueError
        Bei degenerierten Eingaben: identische Punkte (|P1−P0| oder
        |P2−P0| < 1e-6 mm) oder kollineare Punkte (P2 auf der X-Achse).
    """
    a = np.asarray(p0, dtype=float)
    b = np.asarray(p1, dtype=float)
    c = np.asarray(p2, dtype=float)

    d_x = b - a
    d_y = c - a

    norm_x = float(np.linalg.norm(d_x))
    norm_y_raw = float(np.linalg.norm(d_y))

    if norm_x < 1e-6:
        raise ValueError(
            f"P0 und P1 sind identisch oder zu nah beieinander "
            f"(Abstand {norm_x:.3g} mm, Mindestabstand 1e-6 mm). "
            "Bitte P1 mindestens 50 mm von P0 entfernt antasten."
        )
    if norm_y_raw < 1e-6:
        raise ValueError(
            f"P0 und P2 sind identisch oder zu nah beieinander "
            f"(Abstand {norm_y_raw:.3g} mm, Mindestabstand 1e-6 mm). "
            "Bitte P2 mindestens 50 mm von P0 entfernt antasten."
        )

    x_hat = d_x / norm_x

    # Gram-Schmidt: Y-Komponente senkrecht zur X-Achse
    y_proj = d_y - np.dot(d_y, x_hat) * x_hat
    norm_y = float(np.linalg.norm(y_proj))

    if norm_y < 1e-6:
        raise ValueError(
            f"P2 liegt auf der X-Achse — P0, P1 und P2 sind kollinear "
            f"(Restlänge senkrecht zur X-Achse: {norm_y:.3g} mm < 1e-6 mm). "
            "Bitte P2 abseits der P0-P1-Linie antasten "
            "(z. B. in Wandhöhenrichtung)."
        )

    y_hat = y_proj / norm_y
    z_hat = np.cross(x_hat, y_hat)  # rechtshändig → Wandnormale

    # Rotationsmatrix: Spalten = Basisvektoren des Wandrahmens in Basiskoordinaten
    rot = np.column_stack([x_hat, y_hat, z_hat])
    quat = _rot_to_quat(rot)

    return list(a), quat


def _rot_to_quat(r: np.ndarray) -> list[float]:
    """Konvertiert 3×3-Rotationsmatrix in Einheitsquaternion [w, x, y, z].

    Shepperd-Methode (numerisch stabil über alle Rotationen).
    Einheitenkonvention nach ADR-006: w-zuerst.
    """
    trace = r[0, 0] + r[1, 1] + r[2, 2]
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (r[2, 1] - r[1, 2]) * s
        y = (r[0, 2] - r[2, 0]) * s
        z = (r[1, 0] - r[0, 1]) * s
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = 2.0 * math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2])
        w = (r[2, 1] - r[1, 2]) / s
        x = 0.25 * s
        y = (r[0, 1] + r[1, 0]) / s
        z = (r[0, 2] + r[2, 0]) / s
    elif r[1, 1] > r[2, 2]:
        s = 2.0 * math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2])
        w = (r[0, 2] - r[2, 0]) / s
        x = (r[0, 1] + r[1, 0]) / s
        y = 0.25 * s
        z = (r[1, 2] + r[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1])
        w = (r[1, 0] - r[0, 1]) / s
        x = (r[0, 2] + r[2, 0]) / s
        y = (r[1, 2] + r[2, 1]) / s
        z = 0.25 * s
    return [w, x, y, z]
