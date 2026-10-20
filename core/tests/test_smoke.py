import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

MODULES = [
    "roboprint", "roboprint.contracts", "roboprint.assets", "roboprint.frames", "roboprint.robot",
    "roboprint.ifc", "roboprint.geometry", "roboprint.slicer", "roboprint.collision",
    "roboprint.planner", "roboprint.decompose", "roboprint.timing", "roboprint.drl",
    "roboprint.pipeline", "roboprint.api", "roboprint.cli",
]  # fmt: skip


@pytest.mark.parametrize("name", MODULES)
def test_import(name):
    importlib.import_module(name)


def test_cli_help():
    env = {**os.environ, "PYTHONPATH": str(SRC)}  # dieser Worktree, nicht ein installiertes Paket
    res = subprocess.run(
        [sys.executable, "-m", "roboprint", "--help"], capture_output=True, text=True, env=env
    )
    assert res.returncode == 0
    for cmd in ("run-scenario", "serve", "export-contracts"):
        assert cmd in res.stdout
