"""Unit-Tests für das Run-Objekt (pipeline.runfolder).

Erstmals lassen sich Läufe über die Schnittstelle prüfen — Ordner entsteht,
Provenienz wird gestempelt, Artefakt wird validiert und geschrieben — ohne
per Disk-Globbing durch runs/ zu suchen.
"""

import json

import jsonschema
import pytest

from fgc.domain.models import candidates_artifact
from fgc.pipeline import runfolder
from fgc.pipeline.runfolder import Run


def test_create_makes_dir_and_stamps_provenance(tmp_path):
    run = Run.create("slice", "haus", source="fgc slice haus.ifc --wall X", runs_dir=tmp_path)

    assert run.dir.is_dir()
    assert run.dir.parent == tmp_path
    assert run.dir.name.endswith("_slice_haus")
    assert run.provenance["source"] == "fgc slice haus.ifc --wall X"
    assert run.provenance["created"]  # ISO-Zeitstempel gesetzt
    assert run.provenance["git_commit"]  # Kurzhash oder "unknown"


def test_write_validates_and_persists_artifact(tmp_path):
    run = Run.create("walls-list", "haus", source="fgc walls list haus.ifc", runs_dir=tmp_path)
    artifact = candidates_artifact("haus.ifc", [], run.provenance)

    path = run.write("candidates", artifact)

    assert path == run.dir / "candidates.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["model"] == "haus.ifc"
    assert written["provenance"] == run.provenance  # eingebetteter Provenienzblock


def test_write_rejects_invalid_artifact(tmp_path):
    run = Run.create("walls-list", "haus", source="fgc walls list haus.ifc", runs_dir=tmp_path)

    with pytest.raises(jsonschema.ValidationError):
        run.write("candidates", {"schema_version": "0.1"})  # Pflichtfelder fehlen

    assert not (run.dir / "candidates.json").exists()  # ungültig -> nichts geschrieben


def test_runs_dir_defaults_to_module_global(tmp_path, monkeypatch):
    """Ohne runs_dir gilt das monkeypatchbare Modul-Global RUNS_DIR (Test-Seam)."""
    monkeypatch.setattr(runfolder, "RUNS_DIR", tmp_path)

    run = Run.create("slice", "haus", source="fgc slice haus.ifc")

    assert run.dir.parent == tmp_path
