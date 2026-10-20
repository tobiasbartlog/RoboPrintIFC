"""Pipeline-Aktionen über ihre Schnittstelle (ohne IFC-Laden, ohne runs/-Globbing).

Die Aktionen in `pipeline.actions` sind die eine Tür, die CLI, Wizard und (später)
die HTTP-API teilen (ADR-014). Hier prüfen wir sie direkt: Wandquelle-Umschaltung
(übergebene Teilmenge vs. Modell laden), Lauf-Schreiben mit injiziertem
`runs_dir` und die Warntext-Präsentation aus `report`.
"""

import json
from pathlib import Path

import numpy as np

from fgc import domain
from fgc.domain.process_params import ProcessWindow
from fgc.domain.robot import RobotDef
from fgc.eligibility import evaluate_wall
from fgc.pipeline.actions import evaluate_walls, walls_to_run
from fgc.pipeline.report import candidate_reasons

ROBOT = "doosan_m1013"  # reale Roboterdefinition aus robots/


def test_evaluate_walls_uses_passed_subset_without_touching_disk(make_wall):
    """Der Wizard-Fall: eine bereits geladene Wandliste wird evaluiert, ohne
    dass die Aktion das (hier nicht existierende) Modell von der Platte liest."""
    walls = [make_wall("WALLAAAAAAAAAAAAAAAAAA"), make_wall("WALLBBBBBBBBBBBBBBBBBB")]

    candidates = evaluate_walls(Path("existiert-nicht.ifc"), ROBOT, walls=walls)

    assert [c.global_id for c in candidates] == [w.global_id for w in walls]


def test_walls_to_run_writes_valid_candidates_to_injected_runs_dir(
    tmp_path, install_walls, make_wall
):
    """Der CLI-Fall: Modell laden, evaluieren, candidates.json schreiben. Wir
    stubben nur die Wandquelle und lesen das Artefakt über den zurückgegebenen
    Pfad — kein Globbing durch runs/, keine echte IFC-Datei."""
    walls = install_walls([make_wall(load_bearing=False)])

    result = walls_to_run(Path("modell.ifc"), ROBOT, "fgc walls list modell.ifc", runs_dir=tmp_path)

    assert result.run_dir.parent == tmp_path
    assert result.candidates_path == result.run_dir / "candidates.json"
    assert [c.global_id for c in result.candidates] == [w.global_id for w in walls]

    artifact = json.loads(result.candidates_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "candidates")  # gültig gegen das Schema geschrieben
    # model_path wird aufgelöst (absoluter Pfad), damit der Viewer ihn direkt
    # an POST /slice weiterleiten kann (Issue #10, ADR-014).
    assert Path(artifact["model"]).name == "modell.ifc"
    assert Path(artifact["model"]).is_absolute()
    assert {w["global_id"] for w in artifact["walls"]} == {w.global_id for w in walls}


def test_walls_to_run_writes_valid_model_glb_and_map(tmp_path, install_walls, make_wall):
    """walls_to_run schreibt neben candidates.json die binäre model.glb (ein
    Szenenknoten je Wand, ladbar via trimesh) und ein schema-/provenienz-konformes
    model_map.json (Knotenname ↔ GlobalId), Issue #6."""
    import trimesh

    walls = install_walls([
        make_wall("WALLAAAAAAAAAAAAAAAAAA"),
        make_wall("WALLBBBBBBBBBBBBBBBBBB"),
    ])

    result = walls_to_run(Path("modell.ifc"), ROBOT, "fgc walls list modell.ifc", runs_dir=tmp_path)

    # Binäre glTF existiert und lädt via trimesh; Knotennamen tragen die GlobalIds.
    assert result.model_glb_path == result.run_dir / "model.glb"
    assert result.model_glb_path.exists()
    scene = trimesh.load(str(result.model_glb_path), file_type="glb")
    assert set(scene.geometry.keys()) == {f"wall_{w.global_id}" for w in walls}

    # Mapping-Artefakt schema-valide und verweist auf die GLB.
    assert result.model_map_path == result.run_dir / "model_map.json"
    artifact = json.loads(result.model_map_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "model_map")
    # model_path wird aufgelöst — absoluter Pfad für den Viewer (Issue #10).
    assert Path(artifact["model"]).name == "modell.ifc"
    assert Path(artifact["model"]).is_absolute()
    assert artifact["mesh_file"] == "model.glb"
    assert len(artifact["walls"]) == 2


def test_model_map_covers_all_candidates(tmp_path, install_walls, make_wall):
    """Die GlobalIds in model_map.json decken exakt die Kandidaten aus
    candidates.json ab, und jeder Eintrag bindet den GLB-Knoten an seine
    GlobalId (Issue #6)."""
    install_walls([
        make_wall("WALLAAAAAAAAAAAAAAAAAA"),
        make_wall("WALLBBBBBBBBBBBBBBBBBB"),
        make_wall("WALLCCCCCCCCCCCCCCCCCC"),
    ])

    result = walls_to_run(Path("modell.ifc"), ROBOT, "fgc walls list modell.ifc", runs_dir=tmp_path)

    entries = json.loads(result.model_map_path.read_text())["walls"]
    map_ids = {w["global_id"] for w in entries}
    candidate_ids = {c.global_id for c in result.candidates}
    assert map_ids == candidate_ids
    assert all(e["node"] == f"wall_{e['global_id']}" for e in entries)


def test_walls_to_run_writes_context_json_with_nonwall_elements(tmp_path, install_walls, make_wall):
    """walls_to_run schreibt context.json mit Nicht-Wand-Elementen, wenn vorhanden.

    Der Übersichts-Lauf (Issue #17) soll Decken, Dächer, Stützen usw. als
    Kontextgeometrie exportieren. Wände sind bereits in model.glb — sie werden
    über exclude_ifc_types ausgeblendet. Das Artefakt wird schema-validiert
    geschrieben und der Rückgabewert enthält `context_path`.
    """
    from fgc.ifc_io.context import ContextElement

    # Stub: ein Nicht-Wand-Element (z.B. Decke)
    slab = ContextElement(
        global_id="SLABAAAAAAAAAAAAAAAAAAAA",
        ifc_type="IfcSlab",
        name="Decke OG",
        vertices_mm=np.array([[0, 0, 0], [1000, 0, 0], [1000, 1000, 0], [0, 1000, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
    )
    install_walls([make_wall(load_bearing=False)], context=[slab])

    result = walls_to_run(Path("modell.ifc"), ROBOT, "fgc walls list modell.ifc", runs_dir=tmp_path)

    assert result.context_path is not None
    assert result.context_path == result.run_dir / "context.json"
    artifact = json.loads(result.context_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "context")
    # Kein wall_global_id im Übersichts-Lauf (Issue #17: optionales Feld)
    assert "wall_global_id" not in artifact
    assert len(artifact["elements"]) == 1
    assert artifact["elements"][0]["ifc_type"] == "IfcSlab"


def test_walls_to_run_context_path_is_none_when_no_nonwall_elements(
    tmp_path, install_walls, make_wall
):
    """Wenn ein Modell nur Wände enthält (keine Nicht-Wand-Elemente), bleibt
    context_path None und kein context.json wird geschrieben. So bleiben
    Bestandsläufe ohne Kontext unberührt (Issue #17 Kriterium 4)."""
    install_walls([make_wall(load_bearing=False)])

    result = walls_to_run(Path("modell.ifc"), ROBOT, "fgc walls list modell.ifc", runs_dir=tmp_path)

    assert result.context_path is None
    assert not (result.run_dir / "context.json").exists()


def test_candidate_reasons_lists_each_failed_check(make_wall):
    """Die aus CLI und Wizard extrahierte Warntext-Präsentation: ein Grund je
    nicht bestandener Prüfung, '; '-getrennt."""
    # tragende + zu hohe Wand -> load_bearing und workspace fallen durch
    candidate = evaluate_wall(
        make_wall(load_bearing=True, height=1500.0), ProcessWindow(), RobotDef.load(ROBOT)
    )
    assert not candidate.eligible

    reasons = candidate_reasons(candidate)

    for check in candidate.failed_checks:
        assert check.check in reasons
    assert reasons.count(";") == len(candidate.failed_checks) - 1
