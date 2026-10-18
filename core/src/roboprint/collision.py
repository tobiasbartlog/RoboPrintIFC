"""Kollisionswelt: Glieder, Werkzeugkoerper, Duesenspitze, Boden, Tisch, Druckstand, Selbstkollision.

Schnittstelle nach spec/ARTEFAKTE.md. `layer` ist die Anzahl k fertiger Schichten;
Hindernis = Teil-Solid mit z_P <= k*h.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class Contact:
    d_mm: float  # vorzeichenbehaftet, < 0 bei Durchdringung
    pair: tuple[str, str]  # (Glied, Hindernis)
    witness_W: tuple[np.ndarray, np.ndarray]  # Zeugenpunkte in W, mm  # noqa: N815


class World:
    """Kollisionswelt aus Default-Assets plus Teilmesh und Druckstand."""

    def __init__(
        self,
        part_mesh_P,  # noqa: N803 - trimesh.Trimesh
        T_WP: np.ndarray,  # noqa: N803
        layer_height_mm: float = 10.0,
        root: Path = REPO_ROOT,
    ) -> None:
        raise NotImplementedError

    def distance(self, q: np.ndarray, layer: int) -> Contact:
        """Kleinster vorzeichenbehafteter Abstand der Pose q bei k = `layer` fertigen Schichten."""
        raise NotImplementedError
