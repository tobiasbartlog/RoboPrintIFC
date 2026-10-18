"""Tests für den Endeffektor-Konfigurator (Issue #28): Upload → Ablage → Katalog.

Prüft die Speicher-Aktion (`create_tool_from_upload`) und die API (`POST /tools`):
- Upload-Validierung: gültiges Mesh, unbekanntes Format, kaputte/leere/zu große Datei
- Schema-Validität der abgelegten Definition + Mesh-Datei auf der Platte
- Namens-Normalisierung (datei-sicher, überschreibt gleichnamigen Endeffektor)
- TCP-Konsistenz: der im Konfigurator gesetzte TCP kommt bei placement/simulation
  identisch an (stichprobenhafte Konsistenzprüfung, Akzeptanzkriterium 3)
- API: POST /tools → 200, erscheint sofort in GET /tools mit mesh_path; Fehlerfälle → 422
"""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient

from fgc import domain
from fgc.domain.tool import (
    MAX_MESH_BYTES,
    ToolDef,
    build_tool_artifact,
    compute_tool_envelope,
    mesh_suffix,
    safe_tool_name,
    validate_mesh_bytes,
)
from fgc.pipeline.actions import (
    create_tool_from_upload,
    delete_tool,
    update_tool_from_upload,
)
from fgc.pipeline.api import app

TCP = {"pos_mm": [0.0, 0.0, 180.0], "quat": [1.0, 0.0, 0.0, 0.0]}
MESH_XF = {"pos_mm": [0.0, 0.0, 10.0], "quat": [1.0, 0.0, 0.0, 0.0]}
CHANNELS = {"pump_a": {"kind": "analog", "description": "Pumpe A", "default_value": 0.0}}


# ---------------------------------------------------------------------------
# Mesh-Fixtures
# ---------------------------------------------------------------------------


def _box_stl_bytes() -> bytes:
    """Ein winziges gültiges STL-Mesh (Quader) als Bytes."""
    box = trimesh.creation.box(extents=[100.0, 100.0, 200.0])
    return box.export(file_type="stl")


def _box_glb_bytes() -> bytes:
    box = trimesh.creation.box(extents=[50.0, 50.0, 120.0])
    return box.export(file_type="glb")


# ---------------------------------------------------------------------------
# Reine Helfer (Namensnormalisierung, Format, Mesh-Validierung)
# ---------------------------------------------------------------------------


def test_safe_tool_name_normalizes() -> None:
    assert safe_tool_name("Zwei-Komponenten Düse!") == "zwei_komponenten_duse"
    assert safe_tool_name("  Foam Head 2  ") == "foam_head_2"


def test_safe_tool_name_rejects_empty() -> None:
    with pytest.raises(ValueError, match="gueltigen Dateinamen"):
        safe_tool_name("!!!")


def test_mesh_suffix_accepts_known_formats() -> None:
    assert mesh_suffix("nozzle.STL") == ".stl"
    assert mesh_suffix("nozzle.obj") == ".obj"
    assert mesh_suffix("nozzle.glb") == ".glb"


def test_mesh_suffix_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="nicht unterstuetzt"):
        mesh_suffix("nozzle.step")


def test_validate_mesh_bytes_accepts_valid_stl() -> None:
    validate_mesh_bytes(_box_stl_bytes(), ".stl")  # darf nicht werfen


def test_validate_mesh_bytes_rejects_empty() -> None:
    with pytest.raises(ValueError, match="leer"):
        validate_mesh_bytes(b"", ".stl")


def test_validate_mesh_bytes_rejects_corrupt() -> None:
    with pytest.raises(ValueError, match="nicht lesbar|keine Geometrie"):
        validate_mesh_bytes(b"this is not a mesh", ".stl")


def test_validate_mesh_bytes_rejects_oversize() -> None:
    with pytest.raises(ValueError, match="zu gross"):
        validate_mesh_bytes(b"x" * (MAX_MESH_BYTES + 1), ".stl")


# ---------------------------------------------------------------------------
# build_tool_artifact — Schema-Vertrag
# ---------------------------------------------------------------------------


def test_build_tool_artifact_is_schema_valid() -> None:
    artifact = build_tool_artifact(
        "test_nozzle", TCP, 3.0, CHANNELS, mesh="test_nozzle.stl", mesh_transform=MESH_XF
    )
    domain.validate(artifact, "tool")  # darf nicht werfen
    assert artifact["mesh_transform"] == MESH_XF


def test_build_tool_artifact_carries_compatible_robots() -> None:
    """compatible_robots wird ins Artefakt geschrieben und bleibt schema-valide (#71)."""
    artifact = build_tool_artifact(
        "tagged", TCP, 3.0, CHANNELS, compatible_robots=["doosan_m1013", "kuka_kr16"]
    )
    domain.validate(artifact, "tool")  # darf nicht werfen
    assert artifact["compatible_robots"] == ["doosan_m1013", "kuka_kr16"]


def test_build_tool_artifact_omits_empty_compatible_robots() -> None:
    """Leere/fehlende Tags = 'unbekannt': das Feld wird nicht geschrieben (Altbestand, #71)."""
    without = build_tool_artifact("untagged", TCP, 3.0, CHANNELS)
    assert "compatible_robots" not in without
    empty = build_tool_artifact("untagged", TCP, 3.0, CHANNELS, compatible_robots=[])
    assert "compatible_robots" not in empty


def test_tooldef_load_without_compatible_robots_defaults_empty(tmp_path: Path) -> None:
    """Altbestand ohne compatible_robots laedt mit leerem Tupel (Migrationsschutz, #71)."""
    create_tool_from_upload(
        "legacy", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    raw = json.loads((tmp_path / "legacy.json").read_text(encoding="utf-8"))
    assert "compatible_robots" not in raw  # nichts erzwungen
    td = ToolDef.load("legacy", tools_dir=tmp_path)
    assert td.compatible_robots == ()


def test_create_and_update_roundtrip_compatible_robots(tmp_path: Path) -> None:
    """compatible_robots trippt durch Anlegen und Bearbeiten und bleibt erhalten (#71)."""
    create_tool_from_upload(
        "rt", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP,
        compatible_robots=["doosan_m1013"], tools_dir=tmp_path,
    )
    assert ToolDef.load("rt", tools_dir=tmp_path).compatible_robots == ("doosan_m1013",)

    # Update behaelt/ersetzt die Tags gemaess Eingabe.
    update_tool_from_upload(
        "rt", 3.0, CHANNELS, TCP,
        compatible_robots=["doosan_m1013", "extra"], tools_dir=tmp_path,
    )
    assert ToolDef.load("rt", tools_dir=tmp_path).compatible_robots == (
        "doosan_m1013",
        "extra",
    )


def test_build_tool_artifact_rejects_negative_weight() -> None:
    with pytest.raises(ValueError, match="schema-widrig"):
        build_tool_artifact("bad", TCP, -1.0, CHANNELS)


def test_build_tool_artifact_rejects_empty_channels() -> None:
    with pytest.raises(ValueError, match="schema-widrig"):
        build_tool_artifact("bad", TCP, 1.0, {})


# ---------------------------------------------------------------------------
# create_tool_from_upload — Ablage end-to-end
# ---------------------------------------------------------------------------


def test_create_tool_writes_mesh_and_definition(tmp_path: Path) -> None:
    """Upload → Mesh-Datei + schema-valide <name>.json liegen im Tools-Verzeichnis."""
    result = create_tool_from_upload(
        "Foam Nozzle",
        _box_stl_bytes(),
        "upload.stl",
        4.2,
        CHANNELS,
        TCP,
        vendor="FGC-Lab",
        cog_mm=[0.0, 0.0, 90.0],
        mesh_transform=MESH_XF,
        tools_dir=tmp_path,
    )
    assert result.tool_name == "foam_nozzle"
    assert result.mesh_path == tmp_path / "foam_nozzle.stl"
    assert result.mesh_path.exists()
    assert result.tool_path == tmp_path / "foam_nozzle.json"

    raw = json.loads(result.tool_path.read_text(encoding="utf-8"))
    domain.validate(raw, "tool")
    assert raw["mesh"] == "foam_nozzle.stl"
    assert raw["mesh_transform"] == MESH_XF
    assert raw["tcp_frame"] == TCP


def test_create_tool_glb(tmp_path: Path) -> None:
    """GLB-Upload wird ebenfalls akzeptiert und abgelegt."""
    result = create_tool_from_upload(
        "glb_tool", _box_glb_bytes(), "x.glb", 2.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    assert result.mesh_path.suffix == ".glb"
    assert result.mesh_path.exists()


def test_create_tool_rejects_bad_format(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="nicht unterstuetzt"):
        create_tool_from_upload(
            "x", _box_stl_bytes(), "x.step", 1.0, CHANNELS, TCP, tools_dir=tmp_path
        )
    assert not any(tmp_path.iterdir())  # nichts geschrieben bei Fehler


def test_create_tool_rejects_corrupt_mesh(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_tool_from_upload(
            "x", b"garbage", "x.stl", 1.0, CHANNELS, TCP, tools_dir=tmp_path
        )


def test_create_tool_overwrites_same_name(tmp_path: Path) -> None:
    """Gleicher Name → Stammdaten werden überschrieben (kein Duplikat)."""
    stl = _box_stl_bytes()
    create_tool_from_upload("dup", stl, "a.stl", 1.0, CHANNELS, TCP, tools_dir=tmp_path)
    create_tool_from_upload("dup", stl, "a.stl", 9.9, CHANNELS, TCP, tools_dir=tmp_path)
    td = ToolDef.load("dup", tools_dir=tmp_path)
    assert td.weight_kg == pytest.approx(9.9)


def test_created_tool_loads_as_tooldef(tmp_path: Path) -> None:
    """Der abgelegte Endeffektor ist über ToolDef.load ladbar (wie GET /tools)."""
    create_tool_from_upload(
        "loadme", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP,
        mesh_transform=MESH_XF, tools_dir=tmp_path,
    )
    td = ToolDef.load("loadme", tools_dir=tmp_path)
    assert td.name == "loadme"
    assert td.mesh == "loadme.stl"
    assert td.mesh_transform == MESH_XF
    assert td.channel_names == ("pump_a",)


# ---------------------------------------------------------------------------
# TCP-Konsistenz: Konfigurator → placement/simulation (Akzeptanzkriterium 3)
# ---------------------------------------------------------------------------


def test_configured_tcp_flows_into_planned_setup(tmp_path: Path) -> None:
    """Der im Konfigurator gesetzte TCP kommt in der Simulation identisch an.

    `sectionsim.planned_setup` baut das Setup, das die Abschnitts-Simulation (#26) an
    `build_trajectory` reicht (dieselbe TCP-Konvention wie `fgc.placement`).
    Der TCP dort muss exakt der gespeicherte Endeffektor-TCP sein.
    """
    from fgc.pipeline.sectionsim import planned_setup
    from fgc.placement import PlacementOption

    create_tool_from_upload(
        "tcp_tool", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    tool = ToolDef.load("tcp_tool", tools_dir=tmp_path)
    assert tool.tcp_frame == TCP  # 1) Persistenz identisch

    placement = PlacementOption(
        option_id="p1", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=0.0
    )
    setup = planned_setup("doosan_m1013", placement, tool, thickness_mm=200.0)
    # 2) Simulation liest exakt denselben TCP (Flansch → Düse).
    assert setup["tcp"]["pos_mm"] == pytest.approx(TCP["pos_mm"])
    assert setup["tcp"]["quat"] == pytest.approx(TCP["quat"])


# ---------------------------------------------------------------------------
# API: POST /tools + Sofort-Sichtbarkeit im Katalog
# ---------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_post_tools_creates_and_appears_in_catalog(tmp_path: Path, monkeypatch) -> None:
    """POST /tools legt ab; GET /tools zeigt den Endeffektor sofort mit mesh_path."""
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)

    client = TestClient(app)
    resp = client.post(
        "/tools",
        json={
            "name": "API Nozzle",
            "vendor": "Lab",
            "weight_kg": 3.3,
            "cog_mm": [0.0, 0.0, 80.0],
            "channels": {"pump_a": {"kind": "analog"}},
            "tcp_frame": TCP,
            "mesh_transform": MESH_XF,
            "mesh_filename": "up.stl",
            "mesh_base64": _b64(_box_stl_bytes()),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "api_nozzle"
    assert body["mesh"] == "api_nozzle.stl"
    assert body["mesh_path"] is not None
    assert Path(body["mesh_path"]).exists()
    assert body["mesh_transform"] == MESH_XF

    listing = client.get("/tools").json()["tools"]
    assert "api_nozzle" in [t["name"] for t in listing]


def test_post_and_put_tools_roundtrip_compatible_robots(tmp_path: Path, monkeypatch) -> None:
    """POST/GET/PUT tragen compatible_robots end-to-end (#71)."""
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)

    client = TestClient(app)
    resp = client.post(
        "/tools",
        json={
            "name": "tagged",
            "weight_kg": 3.0,
            "channels": {"pump_a": {"kind": "analog"}},
            "tcp_frame": TCP,
            "compatible_robots": ["doosan_m1013"],
            "mesh_filename": "up.stl",
            "mesh_base64": _b64(_box_stl_bytes()),
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["compatible_robots"] == ["doosan_m1013"]

    entry = next(t for t in client.get("/tools").json()["tools"] if t["name"] == "tagged")
    assert entry["compatible_robots"] == ["doosan_m1013"]

    # PUT ohne Feld → leert die Tags (Missing = 'unbekannt', kein erzwungenes Feld).
    resp = client.put(
        "/tools/tagged",
        json={
            "weight_kg": 3.0,
            "channels": {"pump_a": {"kind": "analog"}},
            "tcp_frame": TCP,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["compatible_robots"] == []


def test_get_tools_default_compatible_robots_empty(tmp_path: Path, monkeypatch) -> None:
    """Ein Endeffektor ohne Tags liefert compatible_robots=[] (Altbestand, #71)."""
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)
    create_tool_from_upload(
        "plain", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    entry = next(t for t in TestClient(app).get("/tools").json()["tools"] if t["name"] == "plain")
    assert entry["compatible_robots"] == []


def test_post_tools_bad_format_returns_422(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)

    client = TestClient(app)
    resp = client.post(
        "/tools",
        json={
            "name": "bad",
            "weight_kg": 1.0,
            "channels": {"pump_a": {"kind": "analog"}},
            "tcp_frame": TCP,
            "mesh_filename": "up.step",
            "mesh_base64": _b64(_box_stl_bytes()),
        },
    )
    assert resp.status_code == 422


def test_post_tools_corrupt_base64_returns_422(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)

    client = TestClient(app)
    resp = client.post(
        "/tools",
        json={
            "name": "bad",
            "weight_kg": 1.0,
            "channels": {"pump_a": {"kind": "analog"}},
            "tcp_frame": TCP,
            "mesh_filename": "up.stl",
            "mesh_base64": "!!!not-base64!!!",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# update_tool_from_upload — Bearbeiten (Issue #56)
# ---------------------------------------------------------------------------


NEW_TCP = {"pos_mm": [1.0, 2.0, 200.0], "quat": [1.0, 0.0, 0.0, 0.0]}
NEW_XF = {"pos_mm": [0.0, 0.0, 30.0], "quat": [1.0, 0.0, 0.0, 0.0]}


def test_update_tool_without_mesh_keeps_mesh_and_changes_metadata(tmp_path: Path) -> None:
    """Update OHNE Mesh: die alte Mesh-Datei bleibt, nur Stammdaten/TCP/Kanäle/XF ändern sich."""
    create_tool_from_upload(
        "edit_me", _box_stl_bytes(), "orig.stl", 3.0, CHANNELS, TCP,
        vendor="Alt", mesh_transform=MESH_XF, tools_dir=tmp_path,
    )
    mesh_file = tmp_path / "edit_me.stl"
    mesh_before = mesh_file.read_bytes()

    result = update_tool_from_upload(
        "edit_me", 7.5,
        {"foam": {"kind": "digital", "description": "Schaum", "default_value": 0.0}},
        NEW_TCP,
        vendor="Neu", cog_mm=[1.0, 2.0, 3.0], mesh_transform=NEW_XF, tools_dir=tmp_path,
    )
    assert result.tool_name == "edit_me"
    # Mesh-Datei unverändert erhalten.
    assert mesh_file.exists()
    assert mesh_file.read_bytes() == mesh_before

    td = ToolDef.load("edit_me", tools_dir=tmp_path)
    assert td.name == "edit_me"  # kein Rename
    assert td.mesh == "edit_me.stl"  # Mesh-Dateiname unverändert
    assert td.weight_kg == pytest.approx(7.5)
    assert td.vendor == "Neu"
    assert td.tcp_frame == NEW_TCP
    assert td.mesh_transform == NEW_XF
    assert td.channel_names == ("foam",)


def test_update_tool_with_new_mesh_replaces_mesh(tmp_path: Path) -> None:
    """Update MIT neuem Mesh: das Mesh wird ersetzt, die Definition bleibt schema-valide."""
    create_tool_from_upload(
        "swap", _box_stl_bytes(), "orig.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    new_bytes = trimesh.creation.box(extents=[10.0, 10.0, 10.0]).export(file_type="stl")
    update_tool_from_upload(
        "swap", 3.0, CHANNELS, TCP,
        mesh_bytes=new_bytes, mesh_filename="new.stl", tools_dir=tmp_path,
    )
    td = ToolDef.load("swap", tools_dir=tmp_path)
    assert td.mesh == "swap.stl"
    assert (tmp_path / "swap.stl").read_bytes() == new_bytes
    domain.validate(json.loads((tmp_path / "swap.json").read_text(encoding="utf-8")), "tool")


def test_update_tool_format_change_removes_old_mesh(tmp_path: Path) -> None:
    """Formatwechsel (.stl → .glb): das alte Mesh mit abweichendem Dateinamen wird entfernt."""
    create_tool_from_upload(
        "fmt", _box_stl_bytes(), "orig.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    assert (tmp_path / "fmt.stl").exists()
    update_tool_from_upload(
        "fmt", 3.0, CHANNELS, TCP,
        mesh_bytes=_box_glb_bytes(), mesh_filename="new.glb", tools_dir=tmp_path,
    )
    assert not (tmp_path / "fmt.stl").exists()  # Waise entfernt
    assert (tmp_path / "fmt.glb").exists()
    assert ToolDef.load("fmt", tools_dir=tmp_path).mesh == "fmt.glb"


def test_update_tool_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        update_tool_from_upload("ghost", 1.0, CHANNELS, TCP, tools_dir=tmp_path)


def test_update_tool_validates_new_mesh(tmp_path: Path) -> None:
    """Mesh-Validierung greift beim Update nur, wenn ein Mesh geliefert wird (hier kaputt)."""
    create_tool_from_upload(
        "valid", _box_stl_bytes(), "orig.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    with pytest.raises(ValueError):
        update_tool_from_upload(
            "valid", 3.0, CHANNELS, TCP,
            mesh_bytes=b"garbage", mesh_filename="x.stl", tools_dir=tmp_path,
        )


# ---------------------------------------------------------------------------
# Huellkennzahl (envelope_mm, ADR-026 Punkt 4, PRD #225, Issue #229)
# ---------------------------------------------------------------------------


def test_compute_tool_envelope_identity() -> None:
    """Achsparalleler Quader ohne Transform: radius/laenge direkt aus den Extents."""
    box = trimesh.creation.box(extents=[100.0, 100.0, 200.0])  # zentriert am Ursprung
    envelope = compute_tool_envelope(box.export(file_type="stl"), ".stl", None)
    assert envelope["length_mm"] == pytest.approx(200.0)
    assert envelope["radius_mm"] == pytest.approx(math.hypot(50.0, 50.0))


def test_compute_tool_envelope_translation_shifts_nothing_but_position() -> None:
    """Reine Translation entlang der Flanschachse aendert weder Radius noch Laenge."""
    box = trimesh.creation.box(extents=[100.0, 100.0, 200.0])
    xf = {"pos_mm": [0.0, 0.0, 10.0], "quat": [1.0, 0.0, 0.0, 0.0]}
    envelope = compute_tool_envelope(box.export(file_type="stl"), ".stl", xf)
    assert envelope["length_mm"] == pytest.approx(200.0)
    assert envelope["radius_mm"] == pytest.approx(math.hypot(50.0, 50.0))


def test_compute_tool_envelope_rotation_changes_axis_extent() -> None:
    """Eine 90-Grad-Drehung um die Flansch-y-Achse tauscht x- und z-Ausdehnung.

    Quader-Halbmasse (x, y, z) = (20, 30, 100); nach der Drehung liegt die lange
    Achse (200 mm) radial, die kurze (40 mm) axial — deterministisch aus der
    Mesh-Geometrie berechenbar (keine Toleranz-Raterei).
    """
    box = trimesh.creation.box(extents=[40.0, 60.0, 200.0])
    c, s = math.cos(math.pi / 4), math.sin(math.pi / 4)
    xf = {"pos_mm": [0.0, 0.0, 0.0], "quat": [c, 0.0, s, 0.0]}  # 90 Grad um y
    envelope = compute_tool_envelope(box.export(file_type="stl"), ".stl", xf)
    assert envelope["length_mm"] == pytest.approx(40.0)
    assert envelope["radius_mm"] == pytest.approx(math.hypot(100.0, 30.0))


def test_compute_tool_envelope_is_deterministic() -> None:
    """Gleiche Eingabe -> gleiches Ergebnis (keine Reihenfolge-/Zufallsabhaengigkeit)."""
    box = trimesh.creation.box(extents=[50.0, 30.0, 90.0])
    data = box.export(file_type="stl")
    first = compute_tool_envelope(data, ".stl", None)
    second = compute_tool_envelope(data, ".stl", None)
    assert first == second


def test_build_tool_artifact_writes_envelope_when_given() -> None:
    artifact = build_tool_artifact(
        "with_env", TCP, 3.0, CHANNELS, envelope_mm={"radius_mm": 70.71, "length_mm": 200.0}
    )
    domain.validate(artifact, "tool")  # darf nicht werfen
    assert artifact["envelope_mm"] == {"radius_mm": 70.71, "length_mm": 200.0}


def test_build_tool_artifact_omits_envelope_when_not_given() -> None:
    """Ohne berechneten Wert wird nichts geschrieben — kein Raten (#229)."""
    artifact = build_tool_artifact("no_env", TCP, 3.0, CHANNELS)
    assert "envelope_mm" not in artifact


def test_create_tool_computes_and_persists_envelope(tmp_path: Path) -> None:
    """Upload eines Tools mit Mesh berechnet und speichert die Huellkennzahl deterministisch."""
    result = create_tool_from_upload(
        "hull", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    raw = json.loads(result.tool_path.read_text(encoding="utf-8"))
    domain.validate(raw, "tool")
    assert raw["envelope_mm"]["length_mm"] == pytest.approx(200.0)
    assert raw["envelope_mm"]["radius_mm"] == pytest.approx(math.hypot(50.0, 50.0))

    td = ToolDef.load("hull", tools_dir=tmp_path)
    assert td.envelope_mm is not None
    assert td.envelope_mm["length_mm"] == pytest.approx(200.0)


def test_tooldef_load_without_envelope_defaults_none(tmp_path: Path) -> None:
    """Tool ohne Mesh (kein envelope_mm im Artefakt) laedt fehlerfrei mit ``None``."""
    artifact = build_tool_artifact("no_mesh", TCP, 3.0, CHANNELS)
    (tmp_path / "no_mesh.json").write_text(json.dumps(artifact), encoding="utf-8")
    td = ToolDef.load("no_mesh", tools_dir=tmp_path)
    assert td.envelope_mm is None


def test_legacy_tool_json_without_envelope_loads_and_rewrites_byte_identical(
    tmp_path: Path,
) -> None:
    """Altbestand ohne envelope_mm laedt unveraendert; ein Wieder-Schreiben ohne den
    berechneten Wert bleibt byte-gleich (Migrationslogik wie compatible_robots, #71)."""
    legacy = build_tool_artifact(
        "legacy_hull", TCP, 3.0, CHANNELS, mesh="legacy_hull.stl", mesh_transform=MESH_XF
    )
    assert "envelope_mm" not in legacy
    path = tmp_path / "legacy_hull.json"
    raw_bytes = json.dumps(legacy, indent=2, ensure_ascii=False).encode("utf-8")
    path.write_bytes(raw_bytes)

    td = ToolDef.load("legacy_hull", tools_dir=tmp_path)
    assert td.envelope_mm is None

    # Wieder-Schreiben ohne envelope_mm (kein Upload, kein neues Mesh) -> byte-gleich.
    rewritten = build_tool_artifact(
        "legacy_hull", td.tcp_frame, td.weight_kg, CHANNELS,
        mesh=td.mesh, mesh_transform=td.mesh_transform,
    )
    rewritten_bytes = json.dumps(rewritten, indent=2, ensure_ascii=False).encode("utf-8")
    assert rewritten_bytes == raw_bytes


def test_update_tool_without_new_mesh_keeps_existing_envelope(tmp_path: Path) -> None:
    """Update OHNE neues Mesh: envelope_mm bleibt unangetastet (kein Neuberechnen)."""
    create_tool_from_upload(
        "keep_env", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    before = ToolDef.load("keep_env", tools_dir=tmp_path).envelope_mm

    update_tool_from_upload(
        "keep_env", 5.0, CHANNELS, TCP, vendor="Neu", tools_dir=tmp_path,
    )
    after = ToolDef.load("keep_env", tools_dir=tmp_path).envelope_mm
    assert after == before


def test_update_tool_with_new_mesh_recomputes_envelope(tmp_path: Path) -> None:
    """Update MIT neuem Mesh: envelope_mm wird aus dem neuen Mesh neu berechnet."""
    create_tool_from_upload(
        "swap_env", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    new_bytes = trimesh.creation.box(extents=[10.0, 10.0, 10.0]).export(file_type="stl")
    update_tool_from_upload(
        "swap_env", 3.0, CHANNELS, TCP,
        mesh_bytes=new_bytes, mesh_filename="new.stl", tools_dir=tmp_path,
    )
    td = ToolDef.load("swap_env", tools_dir=tmp_path)
    assert td.envelope_mm["length_mm"] == pytest.approx(10.0)
    assert td.envelope_mm["radius_mm"] == pytest.approx(math.hypot(5.0, 5.0))


def test_get_tools_exposes_envelope_mm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)
    create_tool_from_upload(
        "env_api", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    client = TestClient(app)
    entry = next(t for t in client.get("/tools").json()["tools"] if t["name"] == "env_api")
    assert entry["envelope_mm"]["length_mm"] == pytest.approx(200.0)


def test_post_tools_response_includes_envelope_mm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/tools",
        json={
            "name": "post_env",
            "weight_kg": 2.0,
            "channels": {"pump_a": {"kind": "analog"}},
            "tcp_frame": TCP,
            "mesh_filename": "up.stl",
            "mesh_base64": _b64(_box_stl_bytes()),
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["envelope_mm"]["length_mm"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# delete_tool (Issue #56)
# ---------------------------------------------------------------------------


def test_delete_tool_removes_json_and_mesh(tmp_path: Path) -> None:
    create_tool_from_upload(
        "trash", _box_stl_bytes(), "orig.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    assert (tmp_path / "trash.json").exists()
    assert (tmp_path / "trash.stl").exists()
    delete_tool("trash", tools_dir=tmp_path)
    assert not (tmp_path / "trash.json").exists()
    assert not (tmp_path / "trash.stl").exists()


def test_delete_tool_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        delete_tool("ghost", tools_dir=tmp_path)


# ---------------------------------------------------------------------------
# API: PUT /tools/{name} + DELETE /tools/{name} (Issue #56)
# ---------------------------------------------------------------------------


def test_get_tools_exposes_tcp_frame(tmp_path: Path, monkeypatch) -> None:
    """GET /tools liefert tcp_frame — der Editor stellt ihn beim Bearbeiten wieder her."""
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)
    create_tool_from_upload(
        "cat", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    client = TestClient(app)
    listing = client.get("/tools").json()["tools"]
    entry = next(t for t in listing if t["name"] == "cat")
    assert entry["tcp_frame"] == TCP


def test_put_tools_updates_without_mesh(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)
    create_tool_from_upload(
        "api_edit", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP,
        mesh_transform=MESH_XF, tools_dir=tmp_path,
    )
    client = TestClient(app)
    resp = client.put(
        "/tools/api_edit",
        json={
            "vendor": "Neu",
            "weight_kg": 8.0,
            "channels": {"pump_a": {"kind": "analog"}},
            "tcp_frame": NEW_TCP,
            "mesh_transform": NEW_XF,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "api_edit"
    assert body["weight_kg"] == 8.0
    assert body["tcp_frame"] == NEW_TCP
    assert body["mesh"] == "api_edit.stl"  # Mesh erhalten
    assert Path(body["mesh_path"]).exists()


def test_put_tools_missing_returns_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)
    client = TestClient(app)
    resp = client.put(
        "/tools/ghost",
        json={
            "weight_kg": 1.0,
            "channels": {"pump_a": {"kind": "analog"}},
            "tcp_frame": TCP,
        },
    )
    assert resp.status_code == 404


def test_delete_tools_removes_and_404_on_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tmp_path)
    create_tool_from_upload(
        "api_del", _box_stl_bytes(), "a.stl", 3.0, CHANNELS, TCP, tools_dir=tmp_path
    )
    client = TestClient(app)
    resp = client.delete("/tools/api_del")
    assert resp.status_code == 200, resp.text
    assert not (tmp_path / "api_del.json").exists()
    assert not (tmp_path / "api_del.stl").exists()
    # Zweites Löschen → 404.
    assert client.delete("/tools/api_del").status_code == 404
