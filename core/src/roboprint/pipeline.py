"""Szenario ausfuehren, Laufordner schreiben, Fortschritt melden."""

from __future__ import annotations

from pathlib import Path


def run_scenario(path: Path, out: Path, jobs: int = 1) -> int:
    """Fuehrt ein Szenario aus und schreibt die Artefakte (SPEC §6) nach `out`."""
    raise NotImplementedError
