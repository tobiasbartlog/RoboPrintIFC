"""Geometrische Wandanalyse auf dem tessellierten Mesh — reines numpy.

Bewusst ohne ifcopenshell-Abhängigkeit, damit die Heuristiken mit synthetischen
Meshes testbar sind und einzeln austauschbar bleiben.

Annahmen v0 (dokumentiert, revidierbar):
- Wände stehen aufrecht: Höhenachse = Welt-Z.
- Wandnormale = Richtung kleinster Ausdehnung im Grundriss (2D-PCA).
- Planar heißt: jeder Vertex liegt (in Normalenrichtung) nahe einer der beiden
  Wandflächen. Gekrümmte und mehrschenklige (L-)Wände fallen damit durch —
  genau der v1-Scope aus ADR-005.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Toleranz der Planaritätsprüfung: absolute Untergrenze bzw. Anteil der Dicke.
PLANARITY_TOL_MM = 2.0
PLANARITY_TOL_REL = 0.02


@dataclass(frozen=True)
class WallGeometry:
    """Eckdaten einer Wand aus dem Mesh (alles in mm)."""

    length_mm: float
    height_mm: float
    thickness_mm: float
    is_planar: bool
    planarity_deviation_mm: float
    #: Einheitsvektor der Wandnormalen im Grundriss (Welt-XY, z=0)
    normal_xy: tuple[float, float]


def analyze_wall_mesh(vertices_mm: np.ndarray) -> WallGeometry:
    """Bestimmt Länge/Höhe/Dicke und Planarität aus den Mesh-Vertices."""
    v = np.asarray(vertices_mm, dtype=float)
    if v.ndim != 2 or v.shape[1] != 3 or len(v) < 3:
        raise ValueError(f"Erwarte (n,3)-Vertices, bekam Shape {v.shape}")

    height = float(v[:, 2].max() - v[:, 2].min())

    # 2D-PCA im Grundriss: Eigenvektor zur kleinsten Varianz = Wandnormale
    xy = v[:, :2] - v[:, :2].mean(axis=0)
    cov = np.cov(xy.T)
    eigval, eigvec = np.linalg.eigh(cov)  # aufsteigend sortiert
    normal = eigvec[:, 0]
    along = eigvec[:, 1]

    d_normal = xy @ normal
    d_along = xy @ along
    thickness = float(d_normal.max() - d_normal.min())
    length = float(d_along.max() - d_along.min())

    # Planarität: Abstand jedes Vertex zur näheren der beiden Wandflächen
    half = thickness / 2.0
    center = (d_normal.max() + d_normal.min()) / 2.0
    deviation = float(np.abs(np.abs(d_normal - center) - half).max())
    tol = max(PLANARITY_TOL_MM, PLANARITY_TOL_REL * thickness)

    return WallGeometry(
        length_mm=length,
        height_mm=height,
        thickness_mm=thickness,
        is_planar=deviation <= tol,
        planarity_deviation_mm=deviation,
        normal_xy=(float(normal[0]), float(normal[1])),
    )
