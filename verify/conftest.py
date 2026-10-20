"""pytest-Konfiguration fuer verify/.

- Sammelt die Orakel-Selbsttests `oracle/selftest_*.py` (laufen ohne roboprint).
- Die Vergleichstests `test_g1_*`/`test_g2_*` importieren roboprint ohne Skip. Fehlt roboprint, werden sie
  bei einer Sammlung ueber das Verzeichnis (`pytest verify`) ausgelassen; ruft der Gate-Runner die Datei
  direkt auf, schlaegt der Import fehl und das Gate ist rot.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

COMPARISON = {"test_g1_kinematics.py", "test_g2_collision.py"}


def pytest_collect_file(file_path: Path, parent):
    if file_path.suffix == ".py" and file_path.name.startswith("selftest_"):
        if parent.session.isinitpath(file_path):
            return None  # explizit angegeben: pytest sammelt die Datei selbst
        return pytest.Module.from_parent(parent, path=file_path)
    return None


def _explicit(path: Path, config) -> bool:
    for a in config.args:
        p = Path(str(a).split("::", 1)[0])
        if not p.is_absolute():
            p = Path(config.invocation_params.dir) / p
        if p.resolve() == path.resolve():
            return True
    return False


def pytest_ignore_collect(collection_path: Path, config):
    if collection_path.name in COMPARISON and not _explicit(collection_path, config):
        if importlib.util.find_spec("roboprint") is None:
            return True
    return None


@pytest.fixture(scope="session")
def minirun_dir(tmp_path_factory) -> Path:
    """Konstruierter Mini-Laufordner (einmal je Worker gebaut, nicht veraendern: kopieren)."""
    from verify.oracle.minirun import build

    out = tmp_path_factory.mktemp("minirun")
    build(out)
    return out


@pytest.fixture
def minirun_copy(minirun_dir, tmp_path) -> Path:
    import shutil

    dst = tmp_path / "run"
    shutil.copytree(minirun_dir, dst)
    return dst


@pytest.fixture(scope="session")
def minirun_strand_dir(tmp_path_factory) -> Path:
    """Mini-Laufordner mit Straengen (Verbinder 0 -> 1 -> 2, Travel zu 3; SPEC §5.3). Nicht veraendern."""
    from verify.oracle.minirun import build

    out = tmp_path_factory.mktemp("minirun_strand")
    build(out, strand=True)
    return out


@pytest.fixture
def minirun_strand_copy(minirun_strand_dir, tmp_path) -> Path:
    import shutil

    dst = tmp_path / "run_strand"
    shutil.copytree(minirun_strand_dir, dst)
    return dst
