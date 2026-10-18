"""Szenario ausfuehren, Laufordner schreiben, Fortschritt melden."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

# Fortschritts-Callback: progress(stage, fraction 0..1, message), siehe `roboprint.api_jobs`.
ProgressCallback = Callable[[str, float, str], None]


def run_scenario(
    path: Path, out: Path, jobs: int = 1, progress: ProgressCallback | None = None
) -> int:
    """Fuehrt ein Szenario aus und schreibt die Artefakte (SPEC §6) nach `out`."""
    raise NotImplementedError
