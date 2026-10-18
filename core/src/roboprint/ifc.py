"""IFC -> `Wall` in L (m -> mm, global -> lokal), Oeffnungen (SPEC §4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_walls(path: Path) -> list[Any]:
    """Liest alle Waende einer IFC-Datei als `Wall` im Wand-Frame L."""
    raise NotImplementedError
