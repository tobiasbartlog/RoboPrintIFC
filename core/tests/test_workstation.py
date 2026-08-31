"""Tests fuer die Workstation-Domaene, -Bibliothek und CRUD-API (Issue #72, PRD #69).

Prueft:
- Schema-Registrierung + Validierung (gueltig/ungueltig, additionalProperties)
- WorkstationDef.load / build_workstation_artifact / safe_workstation_name
- Hoehen-Branch-Regel (fest ⇒ geordnetes base_heights_mm inkl. 0; verstellbar ⇒
  height_range_mm mit min<max)
- Roundtrip stationaer + mobil + hoehenverstellbar
- CRUD-API GET/POST/PUT/DELETE /workstations (atomar geschrieben; 404 bei Unbekannt)
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import jsonschema
import pytest
import trimesh
from fastapi.testclient import TestClient

from fgc import domain
from fgc.domain.workstation import (
    WorkstationDef,
    build_workstation_artifact,
    safe_workstation_name,
    write_workstation_artifact,
)
from fgc.pipeline.actions import (
    create_workstation,
    delete_workstation,
    list_workstations,
    update_workstation,
)
from fgc.pipeline.api import app

# ---------------------------------------------------------------------------
# Schema-Validierung
# ---------------------------------------------------------------------------


def test_workstation_schema_registered() -> None:
    """Das Workstation-Schema ist im VALIDATABLE_KINDS registriert."""
    assert "workstation" in domain.VALIDATABLE_KINDS


def test_reference_workstations_validate() -> None:
    """Die Referenz-JSONs in workstations/ sind schema-valide und laden korrekt."""
    from fgc.paths import WORKSTATIONS_DIR

    for path in WORKSTATIONS_DIR.glob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        domain.validate(raw, "workstation")  # darf nicht werfen
        WorkstationDef.load(path.stem)  # Branch-Regel greift auch hier


def test_schema_rejects_additional_properties() -> None:
    """Ein unbekanntes Feld schlaegt die Validierung fehl (additionalProperties: false)."""
    bad = {
        "schema_version": "0.1",
        "name": "bad",
        "mobility": "stationary",
        "height_adjustable": False,
        "base_heights_mm": [0],
        "unexpected": 1,
    }
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(bad, "workstation")


def test_schema_rejects_unknown_mobility() -> None:
    """Ein unbekannter mobility-Wert schlaegt die Validierung fehl."""
    bad = {
        "schema_version": "0.1",
        "name": "bad",
        "mobility": "flying",
        "height_adjustable": False,
        "base_heights_mm": [0],
    }
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(bad, "workstation")


def test_safety_default_is_50() -> None:
    """build_workstation_artifact setzt safety_min_distance_mm-Default auf 50."""
    artifact = build_workstation_artifact(
        "s", "stationary", False, base_heights_mm=[0.0, 100.0]
    )
    assert artifact["safety_min_distance_mm"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Hoehen-Branch-Regel (ueber das rohe Schema hinaus)
# ---------------------------------------------------------------------------


def test_fixed_requires_base_heights() -> None:
    """Nicht-verstellbar ohne base_heights_mm → klarer ValueError."""
    with pytest.raises(ValueError, match="base_heights_mm"):
        build_workstation_artifact("s", "stationary", False)


def test_fixed_base_heights_must_contain_zero() -> None:
    """base_heights_mm ohne 0 → ValueError (Bodenhoehe fehlt)."""
    with pytest.raises(ValueError, match="0"):
        build_workstation_artifact("s", "stationary", False, base_heights_mm=[100.0, 200.0])


def test_fixed_base_heights_must_be_ordered() -> None:
    """Unsortierte base_heights_mm → ValueError."""
    with pytest.raises(ValueError, match="aufsteigend"):
        build_workstation_artifact(
            "s", "stationary", False, base_heights_mm=[0.0, 200.0, 100.0]
        )


def test_adjustable_requires_range() -> None:
    """Verstellbar ohne height_range_mm → ValueError."""
    with pytest.raises(ValueError, match="height_range_mm"):
        build_workstation_artifact("s", "mobile", True)


def test_adjustable_range_min_lt_max() -> None:
    """height_range_mm mit min >= max → ValueError."""
    with pytest.raises(ValueError, match="min < max"):
        build_workstation_artifact(
            "s", "mobile", True, height_range_mm={"min": 500.0, "max": 500.0}
        )


# ---------------------------------------------------------------------------
# Roundtrip: build → write → load
# ---------------------------------------------------------------------------


def test_roundtrip_stationary_fixed(tmp_path: Path) -> None:
    """Stationaere, nicht-verstellbare Zelle round-trippt inkl. base_heights_mm."""
    artifact = build_workstation_artifact(
        "zelle", "stationary", False, base_heights_mm=[0.0, 150.0, 300.0], vendor="ACME"
    )
    path = tmp_path / "zelle.json"
    write_workstation_artifact(path, artifact)
    ws = WorkstationDef.load("zelle", workstations_dir=tmp_path)
    assert ws.mobility == "stationary"
    assert ws.height_adjustable is False
    assert ws.base_heights_mm == (0.0, 150.0, 300.0)
    assert ws.height_range_mm is None
    assert ws.vendor == "ACME"
    assert ws.safety_min_distance_mm == pytest.approx(50.0)


def test_roundtrip_mobile_adjustable(tmp_path: Path) -> None:
    """Mobile, hoehenverstellbare Workstation round-trippt inkl. height_range_mm."""
    artifact = build_workstation_artifact(
        "hub",
        "mobile",
        True,
        height_range_mm={"min": 0.0, "max": 600.0},
        safety_min_distance_mm=80.0,
        compatible_robots=["doosan_m1013"],
    )
    path = tmp_path / "hub.json"
    write_workstation_artifact(path, artifact)
    ws = WorkstationDef.load("hub", workstations_dir=tmp_path)
    assert ws.mobility == "mobile"
    assert ws.height_adjustable is True
    assert ws.height_range_mm == (0.0, 600.0)
    assert ws.base_heights_mm == ()
    assert ws.safety_min_distance_mm == pytest.approx(80.0)
    assert ws.compatible_robots == ("doosan_m1013",)


def test_load_missing_raises(tmp_path: Path) -> None:
    """WorkstationDef.load wirft FileNotFoundError bei fehlender Definition."""
    with pytest.raises(FileNotFoundError, match="workstations/"):
        WorkstationDef.load("nonexistent", workstations_dir=tmp_path)


def test_safe_workstation_name_rejects_empty() -> None:
    """safe_workstation_name wirft ValueError bei degenerierter Eingabe."""
    with pytest.raises(ValueError):
        safe_workstation_name("   ")


# ---------------------------------------------------------------------------
# Aktionen: create / update / delete / list
# ---------------------------------------------------------------------------


def test_create_update_delete_action(tmp_path: Path) -> None:
    """create → update → delete auf dem Aktions-Layer (atomar geschrieben)."""
    res = create_workstation(
        "Meine Zelle", "stationary", False, base_heights_mm=[0.0, 200.0],
        workstations_dir=tmp_path,
    )
    assert res.name == "meine_zelle"
    assert res.path.exists()
    assert [w.name for w in list_workstations(workstations_dir=tmp_path)] == ["meine_zelle"]

    upd = update_workstation(
        "meine_zelle", "mobile", True, height_range_mm={"min": 0.0, "max": 500.0},
        workstations_dir=tmp_path,
    )
    assert upd.workstation.mobility == "mobile"  # type: ignore[attr-defined]
    assert upd.workstation.height_range_mm == (0.0, 500.0)  # type: ignore[attr-defined]

    deleted = delete_workstation("meine_zelle", workstations_dir=tmp_path)
    assert not deleted.exists()
    assert list_workstations(workstations_dir=tmp_path) == []


def test_update_unknown_raises(tmp_path: Path) -> None:
    """update_workstation → FileNotFoundError bei unbekannter Workstation."""
    with pytest.raises(FileNotFoundError):
        update_workstation(
            "ghost", "stationary", False, base_heights_mm=[0.0], workstations_dir=tmp_path
        )


def test_delete_unknown_raises(tmp_path: Path) -> None:
    """delete_workstation → FileNotFoundError bei unbekannter Workstation."""
    with pytest.raises(FileNotFoundError):
        delete_workstation("ghost", workstations_dir=tmp_path)


# ---------------------------------------------------------------------------
# API: GET/POST/PUT/DELETE /workstations
# ---------------------------------------------------------------------------


def test_api_crud_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """Voller CRUD-Zyklus ueber die API gegen ein Temp-Verzeichnis."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    client = TestClient(app)

    # POST stationaer/fest
    resp = client.post(
        "/workstations",
        json={
            "name": "Testzelle",
            "mobility": "stationary",
            "height_adjustable": False,
            "base_heights_mm": [0, 200, 400],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "testzelle"
    assert body["base_heights_mm"] == [0, 200, 400]
    assert body["safety_min_distance_mm"] == 50

    # GET listet die neue Workstation
    resp = client.get("/workstations")
    assert resp.status_code == 200
    assert "testzelle" in [w["name"] for w in resp.json()["workstations"]]

    # PUT → mobil/verstellbar
    resp = client.put(
        "/workstations/testzelle",
        json={
            "name": "testzelle",
            "mobility": "mobile",
            "height_adjustable": True,
            "height_range_mm": {"min": 0, "max": 600},
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["mobility"] == "mobile"
    assert resp.json()["height_range_mm"] == {"min": 0, "max": 600}

    # Datei wirklich auf Platte + atomar (keine .tmp-Reste)
    assert (tmp_path / "testzelle.json").exists()
    assert list(tmp_path.glob("*.tmp")) == []

    # DELETE entfernt die Datei
    resp = client.delete("/workstations/testzelle")
    assert resp.status_code == 200
    assert not (tmp_path / "testzelle.json").exists()


def test_api_post_invalid_height_model_422(tmp_path: Path, monkeypatch) -> None:
    """POST mit verletzter Hoehen-Branch-Regel → 422 (verstellbar ohne range)."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/workstations",
        json={"name": "kaputt", "mobility": "mobile", "height_adjustable": True},
    )
    assert resp.status_code == 422


def test_api_put_unknown_404(tmp_path: Path, monkeypatch) -> None:
    """PUT auf unbekannte Workstation → 404."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    client = TestClient(app)
    resp = client.put(
        "/workstations/ghost",
        json={
            "name": "ghost",
            "mobility": "stationary",
            "height_adjustable": False,
            "base_heights_mm": [0],
        },
    )
    assert resp.status_code == 404


def test_api_delete_unknown_404(tmp_path: Path, monkeypatch) -> None:
    """DELETE auf unbekannte Workstation → 404."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    client = TestClient(app)
    resp = client.delete("/workstations/ghost")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Mesh-Upload + Platzierungs-Frames (Issue #78, ADR-021)
# ---------------------------------------------------------------------------


def _box_mesh_bytes(file_type: str = "stl", extents=(200.0, 200.0, 40.0)) -> bytes:
    """Kleines, gueltiges Dreiecksnetz (Quader) fuer die Mesh-Upload-Tests."""
    mesh = trimesh.creation.box(extents=list(extents))
    data = mesh.export(file_type=file_type)
    return data if isinstance(data, bytes) else data.encode("utf-8")


_RBF = {"pos_mm": [10.0, 20.0, 40.0], "quat": [1.0, 0.0, 0.0, 0.0]}
_WSF = {"pos_mm": [0.0, 0.0, 40.0], "quat": [1.0, 0.0, 0.0, 0.0]}


def test_create_with_mesh_and_frames_roundtrip(tmp_path: Path) -> None:
    """create_workstation mit Mesh + Frames legt Mesh-Datei ab und round-trippt."""
    res = create_workstation(
        "Zelle Halle A",
        "stationary",
        False,
        base_heights_mm=[0.0, 300.0],
        mesh_bytes=_box_mesh_bytes("stl"),
        mesh_filename="upload.stl",
        robot_base_frame=_RBF,
        work_surface_frame=_WSF,
        workstations_dir=tmp_path,
    )
    assert res.name == "zelle_halle_a"
    assert (tmp_path / "zelle_halle_a.stl").exists()  # Mesh neben <name>.json
    ws = WorkstationDef.load("zelle_halle_a", workstations_dir=tmp_path)
    assert ws.mesh == "zelle_halle_a.stl"
    assert ws.robot_base_frame == _RBF
    assert ws.work_surface_frame == _WSF


def test_mesh_optional_backcompat(tmp_path: Path) -> None:
    """Ohne Mesh/Frames bleibt die Workstation reine Zahlenfelder (kein mesh-Feld)."""
    res = create_workstation(
        "nur zahlen", "stationary", False, base_heights_mm=[0.0], workstations_dir=tmp_path
    )
    raw = json.loads(res.path.read_text(encoding="utf-8"))
    assert "mesh" not in raw
    assert "robot_base_frame" not in raw
    assert list(tmp_path.glob("*.stl")) == []


def test_update_preserves_mesh_without_reupload(tmp_path: Path) -> None:
    """Update ohne neue Mesh-Bytes erhaelt die bestehende Mesh-Datei + den Dateinamen."""
    create_workstation(
        "zelle", "stationary", False, base_heights_mm=[0.0],
        mesh_bytes=_box_mesh_bytes("stl"), mesh_filename="a.stl",
        robot_base_frame=_RBF, workstations_dir=tmp_path,
    )
    upd = update_workstation(
        "zelle", "stationary", False, base_heights_mm=[0.0, 100.0],
        robot_base_frame=_RBF, work_surface_frame=_WSF, workstations_dir=tmp_path,
    )
    assert (tmp_path / "zelle.stl").exists()
    assert upd.workstation.mesh == "zelle.stl"  # type: ignore[attr-defined]
    assert upd.workstation.work_surface_frame == _WSF  # type: ignore[attr-defined]


def test_update_replaces_mesh_removes_orphan(tmp_path: Path) -> None:
    """Ein neu hochgeladenes Mesh anderen Formats ersetzt das alte ohne Waise."""
    create_workstation(
        "zelle", "stationary", False, base_heights_mm=[0.0],
        mesh_bytes=_box_mesh_bytes("stl"), mesh_filename="a.stl",
        workstations_dir=tmp_path,
    )
    update_workstation(
        "zelle", "stationary", False, base_heights_mm=[0.0],
        mesh_bytes=_box_mesh_bytes("glb"), mesh_filename="b.glb",
        workstations_dir=tmp_path,
    )
    assert not (tmp_path / "zelle.stl").exists()  # Waise entfernt
    assert (tmp_path / "zelle.glb").exists()
    ws = WorkstationDef.load("zelle", workstations_dir=tmp_path)
    assert ws.mesh == "zelle.glb"


def test_delete_removes_mesh_sibling(tmp_path: Path) -> None:
    """delete_workstation entfernt auch die Mesh-Datei (keine Waise)."""
    create_workstation(
        "zelle", "stationary", False, base_heights_mm=[0.0],
        mesh_bytes=_box_mesh_bytes("stl"), mesh_filename="a.stl",
        workstations_dir=tmp_path,
    )
    assert (tmp_path / "zelle.stl").exists()
    delete_workstation("zelle", workstations_dir=tmp_path)
    assert not (tmp_path / "zelle.json").exists()
    assert not (tmp_path / "zelle.stl").exists()


def test_invalid_mesh_bytes_rejected(tmp_path: Path) -> None:
    """Kaputte Mesh-Bytes → ValueError (kein halb angelegter Eintrag)."""
    with pytest.raises(ValueError):
        create_workstation(
            "zelle", "stationary", False, base_heights_mm=[0.0],
            mesh_bytes=b"not a mesh", mesh_filename="a.stl", workstations_dir=tmp_path,
        )


def test_api_create_with_mesh_base64(tmp_path: Path, monkeypatch) -> None:
    """POST /workstations mit base64-Mesh + Frames → 200, Antwort traegt mesh_path + Frame."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/workstations",
        json={
            "name": "API Zelle",
            "mobility": "stationary",
            "height_adjustable": False,
            "base_heights_mm": [0, 200],
            "mesh_filename": "up.stl",
            "mesh_base64": base64.b64encode(_box_mesh_bytes("stl")).decode("ascii"),
            "robot_base_frame": _RBF,
            "work_surface_frame": _WSF,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mesh"] == "api_zelle.stl"
    assert body["mesh_path"] is not None and body["mesh_path"].endswith("api_zelle.stl")
    assert body["robot_base_frame"]["pos_mm"] == [10.0, 20.0, 40.0]
    assert body["work_surface_frame"]["quat"] == [1.0, 0.0, 0.0, 0.0]
    assert (tmp_path / "api_zelle.stl").exists()

    # GET liefert dieselben Felder zurueck.
    got = client.get("/workstations").json()["workstations"]
    entry = next(w for w in got if w["name"] == "api_zelle")
    assert entry["mesh"] == "api_zelle.stl"
    assert entry["robot_base_frame"]["pos_mm"] == [10.0, 20.0, 40.0]


def test_api_create_with_bad_base64_422(tmp_path: Path, monkeypatch) -> None:
    """POST mit kaputtem base64-Mesh → 422 (nicht dekodierbar)."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/workstations",
        json={
            "name": "kaputt",
            "mobility": "stationary",
            "height_adjustable": False,
            "base_heights_mm": [0],
            "mesh_filename": "up.stl",
            "mesh_base64": "@@@not-base64@@@",
        },
    )
    assert resp.status_code == 422
