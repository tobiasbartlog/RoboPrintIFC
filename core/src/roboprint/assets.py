"""Roboter (URDF), Werkzeug, Workstation und Prozessparameter laden (SPEC §4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_robot(root: Path | None = None) -> Any:
    """Laedt den Roboter aus `third_party/doosan_m1013/urdf/m1013.white.urdf`."""
    raise NotImplementedError


def load_tool(root: Path | None = None) -> Any:
    """Laedt das Werkzeug aus `tools/30gut.json`."""
    raise NotImplementedError


def load_workstation(root: Path | None = None) -> Any:
    """Laedt die Workstation aus `workstations/doosantisch.json`."""
    raise NotImplementedError
