"""DRL-Emitter fuer die Dialekte v2 und v3 (Doosan). Grad gibt es nur hier."""

from __future__ import annotations

from typing import Any


def emit(planned_part: Any, dialect: str) -> str:
    """Erzeugt den DRL-Programmtext fuer `dialect` in {"v2", "v3"}."""
    raise NotImplementedError
