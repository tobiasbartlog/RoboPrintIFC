"""Alle Frame-Uebergaenge aus SPEC §2 (W, B, S, P, L); sonst nirgends."""

from __future__ import annotations

from typing import Any

import numpy as np


def wall_frame_from_ifc(wall: Any) -> np.ndarray:
    """Wand-Frame L (4x4, mm) aus der IFC-Wand in globalen Koordinaten."""
    raise NotImplementedError


def T_WP(placement: Any) -> np.ndarray:  # noqa: N802 - Name nach SPEC
    """Teil-Frame P in der Workstation W (4x4, mm) aus der Platzierung (x, y, yaw)."""
    raise NotImplementedError
