"""Tests für Endeffektor-Domäne, -Katalog und Payload-Check (Issue #21).

Prüft:
- Schema-Validierung (gültige und ungültige Definitionen)
- ToolDef.load aus der Referenz-JSON
- Kanal-Deklaration abfragbar
- Payload-Check: unter / gleich / über Traglast
- API GET /tools und PUT /projects/{slug}/tool
- set_tool_for_job-Aktion (Persistenz im Druckjob)
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from fgc import domain
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.pipeline.actions import create_project_from_ifc, set_print_job, set_tool_for_job
from fgc.pipeline.api import app

ROBOT = "doosan_m1013"
TOOL = "30gut"


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _make_project_with_job(tmp_path: Path, install_walls, make_wall) -> tuple[str, dict]:
    """Legt ein minimales Projekt mit einem Druckjob an und gibt Slug + Artefakt zurück."""
    install_walls([make_wall("TESTWALL00000000000000")])

    model_path = tmp_path / "model.ifc"
    model_path.touch()

    creation = create_project_from_ifc(
        "Testprojekt",
        model_path,
        ROBOT,
        "test",
        projects_dir=tmp_path / "projects",
        runs_dir=tmp_path / "runs",
    )
    slug = creation.project_dir.name

    # Druckjob hinzufügen
    result = set_print_job(
        slug,
        "TESTWALL00000000000000",
        str(creation.overview_run_dir),
        "default",
        projects_dir=tmp_path / "projects",
    )
    return slug, result.artifact


# ---------------------------------------------------------------------------
# Schema-Validierung
# ---------------------------------------------------------------------------


def test_tool_schema_exists() -> None:
    """Das Endeffektor-Schema ist im VALIDATABLE_KINDS registriert."""
    assert "tool" in domain.VALIDATABLE_KINDS


def test_reference_tool_validates() -> None:
    """Die Referenz-JSON 30gut.json ist schema-valide."""
    from fgc.paths import TOOLS_DIR

    raw = json.loads((TOOLS_DIR / "30gut.json").read_text(encoding="utf-8"))
    domain.validate(raw, "tool")  # darf nicht werfen


def test_tool_schema_rejects_missing_channels() -> None:
    """Eine Tool-Definition ohne channels schlägt die Validierung fehl."""
    bad = {
        "schema_version": "0.1",
        "name": "bad_tool",
        "tcp_frame": {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "weight_kg": 1.0,
        # channels fehlt absichtlich
    }
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(bad, "tool")


def test_tool_schema_rejects_negative_weight() -> None:
    """weight_kg < 0 schlägt die Validierung fehl."""
    bad = {
        "schema_version": "0.1",
        "name": "bad_tool",
        "tcp_frame": {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "weight_kg": -1.0,
        "channels": {"pump_a": {"kind": "analog"}},
    }
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(bad, "tool")


def test_tool_schema_rejects_unknown_channel_kind() -> None:
    """Ein unbekanntes channel kind schlägt die Validierung fehl."""
    bad = {
        "schema_version": "0.1",
        "name": "bad_tool",
        "tcp_frame": {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "weight_kg": 1.0,
        "channels": {"pump_a": {"kind": "hydraulic"}},
    }
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(bad, "tool")


# ---------------------------------------------------------------------------
# ToolDef.load
# ---------------------------------------------------------------------------


def test_tooldef_load_reference() -> None:
    """ToolDef.load lädt die Referenz-JSON korrekt."""
    tool = ToolDef.load(TOOL)
    assert tool.name == "30gut"
    assert tool.weight_kg == pytest.approx(2.0)
    assert set(tool.channel_names) == {"pump_a"}
    assert tool.tcp_frame["pos_mm"][2] == pytest.approx(73.0)


def test_tooldef_channel_kinds() -> None:
    """Alle Kanäle der Referenz-Düse sind analog."""
    tool = ToolDef.load(TOOL)
    for ch in tool.channels.values():
        assert ch.kind == "analog"


def test_tooldef_load_missing_raises() -> None:
    """ToolDef.load wirft FileNotFoundError bei fehlender Definition."""
    with pytest.raises(FileNotFoundError, match="tools/"):
        ToolDef.load("nonexistent_tool")


def test_tooldef_channel_names_property() -> None:
    """channel_names gibt die Kanalnamen als Tupel zurück."""
    tool = ToolDef.load(TOOL)
    names = tool.channel_names
    assert isinstance(names, tuple)
    assert "pump_a" in names


# ---------------------------------------------------------------------------
# Payload-Check (Grenzfälle: unter / gleich / über Traglast)
# ---------------------------------------------------------------------------


def test_payload_ok_under_limit() -> None:
    """Werkzeug unter der Traglast → payload_ok=True."""
    tool = ToolDef.load(TOOL)  # 2.0 kg
    assert tool.payload_ok(10.0) is True
    assert tool.payload_margin_kg(10.0) == pytest.approx(8.0)


def test_payload_ok_at_limit() -> None:
    """Werkzeug exakt auf der Traglast → payload_ok=True."""
    tool = ToolDef.load(TOOL)  # 2.0 kg
    assert tool.payload_ok(2.0) is True
    assert tool.payload_margin_kg(2.0) == pytest.approx(0.0)


def test_payload_ok_over_limit() -> None:
    """Werkzeug über der Traglast → payload_ok=False, margin negativ."""
    tool = ToolDef.load(TOOL)  # 2.0 kg
    assert tool.payload_ok(1.0) is False
    assert tool.payload_margin_kg(1.0) == pytest.approx(-1.0)


def test_payload_check_from_robot() -> None:
    """Payload-Check gegen echte RobotDef (M1013 = 10 kg)."""
    robot = RobotDef.load(ROBOT)
    assert robot.payload_kg == pytest.approx(10.0)
    tool = ToolDef.load(TOOL)  # 2.0 kg
    assert tool.payload_ok(robot.payload_kg) is True


# ---------------------------------------------------------------------------
# API: GET /tools
# ---------------------------------------------------------------------------


def test_get_tools_lists_reference_tool() -> None:
    """GET /tools enthält die Referenz-Düse."""
    client = TestClient(app)
    resp = client.get("/tools")
    assert resp.status_code == 200
    body = resp.json()
    names = [t["name"] for t in body["tools"]]
    assert "30gut" in names


def test_get_tools_channels_present() -> None:
    """GET /tools enthält Kanal-Deklarationen der Referenz-Düse."""
    client = TestClient(app)
    resp = client.get("/tools")
    assert resp.status_code == 200
    tool = next(t for t in resp.json()["tools"] if t["name"] == "30gut")
    assert "pump_a" in tool["channels"]
    assert tool["channels"]["pump_a"]["kind"] == "analog"


def test_get_robots_includes_payload_kg() -> None:
    """GET /robots enthält jetzt payload_kg (Issue #21)."""
    client = TestClient(app)
    resp = client.get("/robots")
    assert resp.status_code == 200
    robots = resp.json()["robots"]
    doosan = next(r for r in robots if r["name"] == ROBOT)
    assert doosan["payload_kg"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# API: PUT /projects/{slug}/tool + set_tool_for_job
# ---------------------------------------------------------------------------


def test_set_tool_persists_in_print_job(tmp_path: Path, install_walls, make_wall) -> None:
    """set_tool_for_job schreibt das tool-Feld in den Druckjob."""

    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)

    # RobotDef.load muss robots/doosan_m1013.json finden
    result = set_tool_for_job(
        slug, TOOL, "default", projects_dir=tmp_path / "projects"
    )
    assert result.tool_name == TOOL
    jobs = result.artifact["print_jobs"]
    job = next(j for j in jobs if j["job_id"] == "default")
    assert job["tool"] == TOOL


def test_set_tool_echo_does_not_bump(tmp_path: Path, install_walls, make_wall) -> None:
    """Echo-fest (Issue #199): derselbe Endeffektor erneut gesetzt bumpt 'tool' nicht.

    Der Seam ``mutate_print_job`` difft den deklarierten Pfad — nur ein
    tatsaechlicher Wechsel veraltet Druckplan/Simulation/Export (ADR-017).
    """
    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)

    first = set_tool_for_job(slug, TOOL, "default", projects_dir=tmp_path / "projects")
    job = next(j for j in first.artifact["print_jobs"] if j["job_id"] == "default")
    assert job["revisions"]["inputs"]["tool"] == 1  # echter Wechsel (vorher kein tool)

    again = set_tool_for_job(slug, TOOL, "default", projects_dir=tmp_path / "projects")
    job = next(j for j in again.artifact["print_jobs"] if j["job_id"] == "default")
    assert job["tool"] == TOOL  # gespeichert bleibt er
    assert job["revisions"]["inputs"]["tool"] == 1  # aber kein Fake-Veralten


def test_set_tool_payload_check_ok(tmp_path: Path, install_walls, make_wall) -> None:
    """Payload-Check berichtet ok, wenn Gewicht unter Traglast."""
    # Roboter im Job setzen (sonst kann der Check nicht laufen)

    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)

    result = set_tool_for_job(slug, TOOL, "default", projects_dir=tmp_path / "projects")
    # Kein Roboter im Job → payload_ok=None (kann nicht prüfen)
    assert result.payload_ok is None


def test_set_tool_payload_check_with_robot(tmp_path: Path, install_walls, make_wall) -> None:
    """Payload-Check gibt ok=True zurück wenn Roboter im Job gesetzt."""
    from fgc.project import project_dir_for
    from fgc.project import write_project as wp

    slug, artifact = _make_project_with_job(tmp_path, install_walls, make_wall)

    # Robot manuell in den Job eintragen
    project_dir = project_dir_for(slug, projects_dir=tmp_path / "projects")
    jobs = artifact["print_jobs"]
    updated_jobs = [{**j, "robot": ROBOT} if j["job_id"] == "default" else j for j in jobs]
    updated_artifact = {**artifact, "print_jobs": updated_jobs}
    wp(project_dir, updated_artifact)

    result = set_tool_for_job(slug, TOOL, "default", projects_dir=tmp_path / "projects")
    assert result.payload_ok is True
    assert result.payload_margin_kg == pytest.approx(8.0)


def test_put_tool_api(tmp_path: Path, monkeypatch, install_walls, make_wall) -> None:
    """PUT /projects/{slug}/tool gibt payload_ok in der Antwort zurück."""
    install_walls([make_wall("TESTWALL00000000000000")])

    model_path = tmp_path / "model.ifc"
    model_path.touch()

    creation = create_project_from_ifc(
        "API-Testprojekt",
        model_path,
        ROBOT,
        "test",
        projects_dir=tmp_path / "projects",
        runs_dir=tmp_path / "runs",
    )
    slug = creation.project_dir.name
    set_print_job(
        slug,
        "TESTWALL00000000000000",
        str(creation.overview_run_dir),
        "default",
        projects_dir=tmp_path / "projects",
    )

    # API-Test: monkeypatche project_dir_for so dass es in tmp_path schaut
    from fgc import project as proj_mod

    monkeypatch.setattr(
        proj_mod.store,
        "PROJECTS_DIR",
        tmp_path / "projects",
    )

    client = TestClient(app)
    resp = client.put(
        f"/projects/{slug}/tool",
        json={"tool": TOOL, "job_id": "default"},
    )
    assert resp.status_code == 200
    body = resp.json()
    jobs = body["print_jobs"]
    job = next(j for j in jobs if j["job_id"] == "default")
    assert job["tool"] == TOOL


def test_put_tool_api_unknown_tool(tmp_path: Path, monkeypatch, install_walls, make_wall) -> None:
    """PUT /projects/{slug}/tool → 404 bei unbekanntem Endeffektor."""
    install_walls([make_wall("TESTWALL00000000000000")])

    model_path = tmp_path / "model.ifc"
    model_path.touch()

    creation = create_project_from_ifc(
        "API-Testprojekt2",
        model_path,
        ROBOT,
        "test",
        projects_dir=tmp_path / "projects",
        runs_dir=tmp_path / "runs",
    )
    slug = creation.project_dir.name
    set_print_job(
        slug,
        "TESTWALL00000000000000",
        str(creation.overview_run_dir),
        "default",
        projects_dir=tmp_path / "projects",
    )

    from fgc import project as proj_mod

    monkeypatch.setattr(
        proj_mod.store,
        "PROJECTS_DIR",
        tmp_path / "projects",
    )

    client = TestClient(app)
    resp = client.put(
        f"/projects/{slug}/tool",
        json={"tool": "nonexistent_tool", "job_id": "default"},
    )
    assert resp.status_code == 404
