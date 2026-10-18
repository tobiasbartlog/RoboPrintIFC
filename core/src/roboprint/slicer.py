"""Schichten, Schalenringe, Ringstart, An- und Abfahrt eines Teils."""

from __future__ import annotations

from typing import Any


def slice_part(part: Any, params: Any) -> Any:
    """Zerlegt ein Teil in Schichten und Ringe und liefert den `Toolpath`."""
    raise NotImplementedError
