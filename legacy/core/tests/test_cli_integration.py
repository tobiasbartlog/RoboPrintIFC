"""Integration: CLI end-to-end gegen das Beispielmodell (braucht ifcopenshell)."""

import json

import pytest

from fgc import domain
from fgc.ifc_io.walls import load_walls
from fgc.paths import REPO_ROOT
from fgc.pipeline import cli, runfolder, wizard


def _scripted(*answers):
    it = iter(answers)
    return lambda _prompt="": next(it)

EXAMPLE_IFC = REPO_ROOT / "examples" / "Building-Architecture.ifc"
KNOWN_WALL = "1AQAupaRP1txwK1AGiN61V"  # house right front (S2-Protokoll)

pytestmark = pytest.mark.skipif(not EXAMPLE_IFC.exists(), reason="Beispielmodell fehlt")


@pytest.fixture
def tmp_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(runfolder, "RUNS_DIR", tmp_path)
    return tmp_path


def test_walls_list_writes_valid_candidates(tmp_runs, capsys):
    assert cli.main(["walls", "list", str(EXAMPLE_IFC)]) == 0
    artifact_path = next(tmp_runs.glob("*/candidates.json"))
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "candidates")
    assert len(artifact["walls"]) == 4
    assert KNOWN_WALL in {w["global_id"] for w in artifact["walls"]}


def test_slice_writes_valid_wallspec_and_toolpath(tmp_runs):
    code = cli.main(
        ["slice", str(EXAMPLE_IFC), "--wall", KNOWN_WALL, "--layer-height", "500"]
    )
    assert code == 0
    run_dir = next(tmp_runs.glob("*_slice_*"))
    toolpath = json.loads((run_dir / "toolpath.json").read_text(encoding="utf-8"))
    wallspec = json.loads((run_dir / "wallspec.json").read_text(encoding="utf-8"))
    domain.validate(toolpath, "toolpath")
    domain.validate(wallspec, "wallspec")
    assert toolpath["wall_global_id"] == KNOWN_WALL
    assert wallspec["global_id"] == KNOWN_WALL
    assert any(t["kind"] == "print" for t in toolpath["targets"])


def test_walls_list_writes_valid_context_for_overview(tmp_runs, capsys):
    """walls-list-Lauf exportiert Nicht-Wand-Elemente als schema-validiertes
    context.json (Issue #17). Wände selbst fehlen im Kontext (sie sind in model.glb);
    räumlich störende Elemente (Räume, Öffnungskörper) fehlen ebenfalls."""
    assert cli.main(["walls", "list", str(EXAMPLE_IFC)]) == 0
    run_dir = next(tmp_runs.glob("*_walls-list_*"))
    context_path = run_dir / "context.json"
    assert context_path.exists(), "context.json fehlt im Übersichts-Lauf"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    domain.validate(context, "context")
    # Kein wall_global_id im Übersichts-Kontext (Issue #17: kein ausgewähltes Wandelement)
    assert "wall_global_id" not in context
    wall_ids = {w["global_id"] for w in json.loads(
        (run_dir / "candidates.json").read_text())["walls"]}
    context_ids = {e["global_id"] for e in context["elements"]}
    # Wände dürfen nicht im Kontext auftauchen
    assert wall_ids.isdisjoint(context_ids), (
        f"Wand-IDs im Kontext gefunden: {wall_ids & context_ids}"
    )
    # Räume und Öffnungen sind ausgeblendet
    assert all(e["ifc_type"] not in ("IfcSpace", "IfcOpeningElement")
               for e in context["elements"])
    assert len(context["elements"]) > 0, "Kein Nicht-Wand-Element im Kontext"


def test_slice_writes_valid_context(tmp_runs):
    code = cli.main(
        ["slice", str(EXAMPLE_IFC), "--wall", KNOWN_WALL, "--layer-height", "500"]
    )
    assert code == 0
    run_dir = next(tmp_runs.glob("*_slice_*"))
    context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    domain.validate(context, "context")
    assert context["wall_global_id"] == KNOWN_WALL
    ids = {e["global_id"] for e in context["elements"]}
    assert KNOWN_WALL not in ids  # die ausgewählte Wand gehört nicht zum Kontext
    assert len(ids) > 0
    # keine Räume/Öffnungskörper im Kontext
    assert all(e["ifc_type"] not in ("IfcSpace", "IfcOpeningElement")
               for e in context["elements"])


def test_slice_no_context_skips_artifact(tmp_runs):
    code = cli.main(
        ["slice", str(EXAMPLE_IFC), "--wall", KNOWN_WALL,
         "--layer-height", "500", "--no-context"]
    )
    assert code == 0
    run_dir = next(tmp_runs.glob("*_slice_*"))
    assert not (run_dir / "context.json").exists()


def test_slice_unknown_wall_fails_cleanly(tmp_runs, capsys):
    assert cli.main(["slice", str(EXAMPLE_IFC), "--wall", "GIBTESNICHT0000000000"]) == 1


def test_wizard_slice_matches_cli_slice_for_same_wall(tmp_runs, monkeypatch, capsys):
    """Wizard und CLI slicen dieselbe Wand über dieselbe Aktion (slice_to_run)
    mit denselben Default-Parametern -> geometrisch identische Toolpaths.

    Deckt den bisher ungetesteten Wizard-Slice-Pfad end-to-end ab.
    """
    walls = load_walls(EXAMPLE_IFC)  # Reihenfolge = Wizard-Gruppe "alle"
    wall_idx = next(i for i, w in enumerate(walls) if w.global_id == KNOWN_WALL)
    monkeypatch.setattr(wizard, "discover_ifc_files", lambda: [EXAMPLE_IFC])

    answers = _scripted(
        "1",                 # Modell 1
        "1",                 # Filter: alle
        str(wall_idx + 1),   # Wand KNOWN_WALL
        "n",                 # Viewer nicht öffnen
    )
    assert wizard.run_wizard(input_fn=answers) == 0

    wiz_run = next(tmp_runs.glob("*_slice_*"))
    wiz_wallspec = json.loads((wiz_run / "wallspec.json").read_text(encoding="utf-8"))
    assert wiz_wallspec["global_id"] == KNOWN_WALL  # richtige Wand gewählt
    wiz_targets = json.loads((wiz_run / "toolpath.json").read_text(encoding="utf-8"))["targets"]

    # Dieselbe Wand über die CLI, ohne --layer-height -> gleiche Default-Params.
    before = set(tmp_runs.glob("*_slice_*"))
    assert cli.main(["slice", str(EXAMPLE_IFC), "--wall", KNOWN_WALL]) == 0
    cli_run = next(d for d in tmp_runs.glob("*_slice_*") if d not in before)
    cli_targets = json.loads((cli_run / "toolpath.json").read_text(encoding="utf-8"))["targets"]

    assert wiz_targets == cli_targets
