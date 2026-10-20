"""Tests fuer Roboter-Schema-Validierung + Defektmeldung in GET /robots (Issue #73).

Robuster Katalog (rein additiv, read-only im #69-Scope):
- robot.schema.json ist registriert und deckt die realen robots/*.json ab
- RobotDef.load validiert; der bestehende M1013 laedt unveraendert
- GET /robots meldet eine defekte Definition sichtbar (Log-Warnung + errors-Feld),
  statt sie still zu verschlucken
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from fgc import domain
from fgc.domain.robot import RobotDef
from fgc.pipeline.api import app

# ---------------------------------------------------------------------------
# Schema-Validierung
# ---------------------------------------------------------------------------


def test_robot_schema_registered() -> None:
    """Das Roboter-Schema ist in VALIDATABLE_KINDS registriert und ladbar."""
    assert "robot" in domain.VALIDATABLE_KINDS
    schema = domain.load_schema("robot")
    assert schema["$id"].endswith("robot.schema.json")


def test_reference_robots_validate_and_load() -> None:
    """Die Referenz-JSONs in robots/ sind schema-valide und laden korrekt."""
    from fgc.paths import ROBOTS_DIR

    files = list(ROBOTS_DIR.glob("*.json"))
    assert files, "robots/ sollte mindestens eine Definition enthalten"
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        domain.validate(raw, "robot")  # darf nicht werfen
        RobotDef.load(path.stem)  # laedt unveraendert


def test_m1013_loads_unchanged() -> None:
    """Der bestehende M1013 laedt mit unveraenderten Kennwerten (Regression)."""
    rd = RobotDef.load("doosan_m1013")
    assert rd.name == "doosan_m1013"
    assert rd.reach_mm == 1300
    assert rd.payload_kg == 10
    assert rd.max_print_height_mm == 1000
    assert rd.max_print_length_mm == 2000
    assert rd.kinematics is not None
    assert rd.kinematics.solver == "opw"
    assert rd.kinematics.n_joints == 6


def test_schema_allows_underscore_comment_fields() -> None:
    """Unterstrich-praefixierte Kommentarfelder (_note/_source/…) sind erlaubt."""
    from fgc.paths import ROBOTS_DIR

    raw = json.loads((ROBOTS_DIR / "doosan_m1013.json").read_text(encoding="utf-8"))
    # Der M1013 traegt _note/_source/_units/_limits_source — muss valide bleiben.
    assert "_note" in raw["workspace"]
    assert "_source" in raw["kinematics"]
    domain.validate(raw, "robot")


def test_schema_rejects_additional_properties() -> None:
    """Ein unbekanntes (nicht-Unterstrich-)Feld schlaegt die Validierung fehl."""
    from fgc.paths import ROBOTS_DIR

    raw = json.loads((ROBOTS_DIR / "doosan_m1013.json").read_text(encoding="utf-8"))
    raw["unexpected"] = 1
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(raw, "robot")


def test_schema_requires_workspace() -> None:
    """Fehlendes workspace schlaegt die Validierung fehl."""
    bad = {"schema_version": "0.2", "name": "x", "reach_mm": 1000}
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(bad, "robot")


def test_load_raises_on_broken_definition(tmp_path: Path) -> None:
    """RobotDef.load wirft bei schema-widriger Definition (statt still zu laden)."""
    bad = {"schema_version": "0.2", "name": "broken", "reach_mm": -5, "workspace": {}}
    (tmp_path / "broken.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(jsonschema.ValidationError):
        RobotDef.load("broken", robots_dir=tmp_path)


# ---------------------------------------------------------------------------
# GET /robots meldet Defekte sichtbar (Log + errors-Feld)
# ---------------------------------------------------------------------------


def test_get_robots_reports_defect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Eine kaputte Definition wird in errors gemeldet UND als Warnung geloggt.

    Der gueltige M1013 wird weiterhin geliefert — report-and-continue, kein Crash.
    """
    from fgc.paths import ROBOTS_DIR

    # Echten M1013 kopieren (gueltig) + eine bewusst kaputte Definition daneben.
    good = json.loads((ROBOTS_DIR / "doosan_m1013.json").read_text(encoding="utf-8"))
    (tmp_path / "doosan_m1013.json").write_text(json.dumps(good), encoding="utf-8")
    broken = {"schema_version": "0.2", "name": "broken", "reach_mm": 1000}  # ohne workspace
    (tmp_path / "broken.json").write_text(json.dumps(broken), encoding="utf-8")

    # GET /robots liest ROBOTS_DIR per lokalem Import → auf tmp_path umbiegen.
    monkeypatch.setattr("fgc.paths.ROBOTS_DIR", tmp_path)

    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="fgc.pipeline.api"):
        resp = client.get("/robots")
    assert resp.status_code == 200
    body = resp.json()

    names = {r["name"] for r in body["robots"]}
    assert "doosan_m1013" in names  # gueltiger laedt weiter

    errors = body["errors"]
    assert any(e["name"] == "broken" for e in errors)  # kaputter sichtbar gemeldet
    assert any("broken.json" in rec.message for rec in caplog.records)  # und geloggt
