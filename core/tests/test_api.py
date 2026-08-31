"""Integration: Core-API (ADR-014) end-to-end gegen das Beispielmodell.

Prüft, dass:
- POST /slice einen gültigen Laufordner mit schema-validierten Artefakten
  erzeugt (AC: kein In-Memory-Sonderweg).
- Der API-Aufruf geometrisch identische Toolpath-Targets liefert wie der
  äquivalente CLI-Aufruf (AC: dieselbe Aktion, kein Duplikat-Codepfad).

TestClient (starlette/httpx) ruft die FastAPI-App im selben Prozess —
kein laufender Server nötig. RUNS_DIR wird per monkeypatch injiziert
(gleicher Test-Seam wie test_cli_integration.py).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fgc import domain
from fgc.paths import REPO_ROOT
from fgc.pipeline import cli, runfolder
from fgc.pipeline.api import app

EXAMPLE_IFC = REPO_ROOT / "examples" / "Building-Architecture.ifc"
KNOWN_WALL = "1AQAupaRP1txwK1AGiN61V"  # house right front (S2-Protokoll)

pytestmark = pytest.mark.skipif(not EXAMPLE_IFC.exists(), reason="Beispielmodell fehlt")


@pytest.fixture
def tmp_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(runfolder, "RUNS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def client():
    return TestClient(app)


def test_slice_preflight_allows_viewer_origin(client):
    """CORS: Der Viewer (Port 5173) ruft die API (Port 8765) cross-origin.

    Ohne CORS-Header blockt der Browser jede Antwort — isApiAvailable() und
    postSlice() schlagen fehl, obwohl die API läuft (TestClient/curl merken
    davon nichts). Preflight OPTIONS /slice muss den Viewer-Origin erlauben.
    """
    resp = client.options(
        "/slice",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_post_slice_creates_valid_run(client, tmp_runs):
    """API-Aufruf erzeugt regulären Laufordner mit schema-validierten Artefakten."""
    resp = client.post(
        "/slice",
        json={
            "model_path": str(EXAMPLE_IFC),
            "global_id": KNOWN_WALL,
            "layer_height_mm": 500.0,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Antwort referenziert den Laufordner
    run_dir = REPO_ROOT.__class__(body["run_dir"])
    assert run_dir.is_dir()
    assert run_dir.parent == tmp_runs

    # Artefakte vorhanden und schema-validiert
    toolpath = json.loads((run_dir / "toolpath.json").read_text(encoding="utf-8"))
    wallspec = json.loads((run_dir / "wallspec.json").read_text(encoding="utf-8"))
    context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))

    domain.validate(toolpath, "toolpath")
    domain.validate(wallspec, "wallspec")
    domain.validate(context, "context")

    # Inhaltliche Korrektheit
    assert toolpath["wall_global_id"] == KNOWN_WALL
    assert wallspec["global_id"] == KNOWN_WALL
    assert any(t["kind"] == "print" for t in toolpath["targets"])

    # Kennzahlen in der Antwort stimmen mit dem Artefakt überein
    assert body["n_layers"] == toolpath["summary"]["n_layers"]
    assert body["n_targets"] == toolpath["summary"]["n_targets"]
    assert body["n_print"] == toolpath["summary"]["n_print"]


def test_post_slice_matches_cli_toolpath(client, tmp_runs):
    """API und CLI slicen dieselbe Wand über dieselbe Aktion → identische Targets.

    Entspricht dem Muster aus test_wizard_slice_matches_cli_slice_for_same_wall
    und belegt, dass POST /slice kein eigener Codepfad ist.
    """
    # API-Lauf
    resp = client.post(
        "/slice",
        json={
            "model_path": str(EXAMPLE_IFC),
            "global_id": KNOWN_WALL,
            "layer_height_mm": 500.0,
            "with_context": False,
        },
    )
    assert resp.status_code == 200
    api_run_dir = REPO_ROOT.__class__(resp.json()["run_dir"])
    api_targets = json.loads((api_run_dir / "toolpath.json").read_text(encoding="utf-8"))["targets"]

    # CLI-Lauf (gleiche Parameter)
    before = set(tmp_runs.glob("*_slice_*"))
    assert cli.main(
        ["slice", str(EXAMPLE_IFC), "--wall", KNOWN_WALL, "--layer-height", "500", "--no-context"]
    ) == 0
    cli_run_dir = next(d for d in tmp_runs.glob("*_slice_*") if d not in before)
    cli_targets = json.loads((cli_run_dir / "toolpath.json").read_text(encoding="utf-8"))["targets"]

    assert api_targets == cli_targets


def test_post_slice_unknown_wall_returns_404(client, tmp_runs):
    """Unbekannte GlobalId → HTTP 404 mit verständlicher Fehlermeldung."""
    resp = client.post(
        "/slice",
        json={"model_path": str(EXAMPLE_IFC), "global_id": "GIBTESNICHT0000000000"},
    )
    assert resp.status_code == 404
    assert "GIBTESNICHT" in resp.json()["detail"]


def test_post_slice_no_context_skips_context_artifact(client, tmp_runs):
    """with_context=False → kein context.json im Laufordner."""
    resp = client.post(
        "/slice",
        json={
            "model_path": str(EXAMPLE_IFC),
            "global_id": KNOWN_WALL,
            "layer_height_mm": 500.0,
            "with_context": False,
        },
    )
    assert resp.status_code == 200
    run_dir = REPO_ROOT.__class__(resp.json()["run_dir"])
    assert not (run_dir / "context.json").exists()


def test_post_slice_toolpath_has_params_block(client, tmp_runs):
    """Neuer Toolpath (0.3) enthält params-Block für das Viewer-Parameter-Panel (Issue #9).

    Der params-Block trägt model_path (absolut), layer_height_mm, strand_width_mm
    und n_shells — alle vier Felder, die das Panel zum erneuten Slicen braucht.
    """
    resp = client.post(
        "/slice",
        json={
            "model_path": str(EXAMPLE_IFC),
            "global_id": KNOWN_WALL,
            "layer_height_mm": 500.0,
            "strand_width_mm": 30.0,
            "n_shells": 2,
        },
    )
    assert resp.status_code == 200
    run_dir = REPO_ROOT.__class__(resp.json()["run_dir"])
    toolpath = json.loads((run_dir / "toolpath.json").read_text(encoding="utf-8"))

    assert toolpath["schema_version"] == "0.3"
    params = toolpath["params"]
    assert params["layer_height_mm"] == 500.0
    assert params["strand_width_mm"] == 30.0
    assert params["n_shells"] == 2
    # model_path muss absolut und aufgelöst sein, damit der Viewer ihn direkt nutzen kann
    assert str(EXAMPLE_IFC.resolve()) == params["model_path"]

    # Schema muss sauber validieren
    domain.validate(toolpath, "toolpath")


def test_post_slice_partial_override_fills_remaining_from_card(client, tmp_runs):
    """Nur layer_height_mm explizit gesetzt → strand_width_mm und n_shells aus Karte.

    Stichprobe für den Panel-Weg: ein Feld gesetzt, Rest leer (= Karten-Default).
    Die Karte ist Quelle, explizite Overrides gewinnen (ADR-013/014).
    """
    resp = client.post(
        "/slice",
        json={
            "model_path": str(EXAMPLE_IFC),
            "global_id": KNOWN_WALL,
            "layer_height_mm": 500.0,
            # strand_width_mm und n_shells nicht gesetzt → Karten-/Provisorisch-Default
        },
    )
    assert resp.status_code == 200
    run_dir = REPO_ROOT.__class__(resp.json()["run_dir"])
    toolpath = json.loads((run_dir / "toolpath.json").read_text(encoding="utf-8"))

    params = toolpath["params"]
    assert params["layer_height_mm"] == 500.0
    # strand_width_mm und n_shells stammen aus der Prozessfenster-Karte
    assert isinstance(params["strand_width_mm"], (int, float)) and params["strand_width_mm"] > 0
    assert isinstance(params["n_shells"], int) and params["n_shells"] >= 1

    domain.validate(toolpath, "toolpath")


def test_post_slice_no_overrides_uses_card_defaults(client, tmp_runs):
    """Kein Override → alle Parameter aus der Karte; params-Block vollständig befüllt."""
    resp = client.post(
        "/slice",
        json={
            "model_path": str(EXAMPLE_IFC),
            "global_id": KNOWN_WALL,
            # Alle Slice-Parameter null/weggelassen → Karten-Default
        },
    )
    assert resp.status_code == 200
    run_dir = REPO_ROOT.__class__(resp.json()["run_dir"])
    toolpath = json.loads((run_dir / "toolpath.json").read_text(encoding="utf-8"))

    params = toolpath["params"]
    # Alle vier Felder müssen vorhanden und sinnvoll sein
    required_keys = ("model_path", "layer_height_mm", "strand_width_mm", "n_shells")
    assert all(k in params for k in required_keys)
    assert params["model_path"]  # nicht leer
    assert params["layer_height_mm"] > 0
    assert params["strand_width_mm"] > 0
    assert params["n_shells"] >= 1

    domain.validate(toolpath, "toolpath")
