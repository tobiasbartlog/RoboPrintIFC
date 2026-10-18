"""Modul-Export: Setup aus Stammdaten generieren, Gate „nichts Provisorisches" (Issue #136).

Deckt die Akzeptanzkriterien des #116-Grills (Design-Log 2026-07-09) ab:

- **Setup generiert (Art „modul", ADR-022):** der Export baut das Setup selbst aus
  Workstation-Frames (feste Platzierung) + Werkzeug-TCP + Workstation-``io_channels``/
  ``deadtime`` — kein manuelles ``setup.json``. ``setup_source == "generated"``.
- **Ketten-Orakel:** das generierte Setup trägt dieselbe ``wall_to_base`` wie die
  Simulation (`sectionsim.planned_setup`, z_offset=0) — generiertes Setup ∘ Slicer-Target ==
  geplante TCP-Pose in Basis (die eine Transformationsstelle, ADR-006).
- **Gate:** je fehlendem/provisorischem Baustein (Frames, io_channels, Totzeit, TCP,
  Endeffektor) ein Kommentar-Stub mit **benanntem** Fehlbestand (``complete=False``,
  ``setup_source="generated_incomplete"``); alles bestätigt → ``complete=True``.
- **Altbestand:** Workstation ohne die neuen Felder lädt mit ``None`` (unverändert).

Fixtures folgen test_export/test_section_simulation (Stub-Wände, Verzeichnis-Seams) —
kein IFC/ifcopenshell nötig. Die Workstation liegt in einem Temp-Verzeichnis, das
über ``fgc.paths.WORKSTATIONS_DIR`` gepatcht wird, damit auch
``set_workstation_for_job`` (Default-Verzeichnis) sie findet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fgc.pipeline.actions import (
    _generate_module_setup,
    create_project_from_ifc,
    export_section_drl,
    plan_for_job,
    propose_decomposition,
    reassess_walls_for_robot,
    set_print_job,
    set_tool_for_job,
    set_workstation_for_job,
    simulate_section,
)
from fgc.pipeline.sectionsim import placement_context_for_job, planned_setup
from fgc.project import load_project, project_dir_for

ROBOT = "doosan_m1013"
TOOL = "30gut"  # tools/30gut.json — realer TCP, kein tcp_provisional (= bestätigt)
WALL_ID = "WALLAAAAAAAAAAAAAAAAAA"


@pytest.fixture
def stub_walls(install_walls, make_wall):
    return install_walls([make_wall(WALL_ID, length=800.0, height=2600.0)])


# --- Workstation-Stammdaten (S1) ------------------------------------------------

#: Voll bestätigte Workstation: Frames + Kanal-Mapping (pump_a/pump_b, die
#: Default-Slicer-Kanäle) + gemessene (nicht-provisorische) Totzeit.
FULL_WS: dict = {
    "schema_version": "0.1",
    "name": "s1_zelle",
    "mobility": "stationary",
    "height_adjustable": False,
    "base_heights_mm": [0.0, 200.0, 400.0],
    "safety_min_distance_mm": 50.0,
    "robot_base_frame": {"pos_mm": [0.0, 0.0, 300.0], "quat": [1.0, 0.0, 0.0, 0.0]},
    "work_surface_frame": {"pos_mm": [800.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
    "io_channels": {
        "pump_a": {"kind": "analog_voltage", "index": 0, "physical_range": [0.0, 10.0]},
        "pump_b": {"kind": "analog_voltage", "index": 1, "physical_range": [0.0, 10.0]},
    },
    "deadtime": {"t_tot_s": 2.4, "compensation": "simulation_shift", "provisional": False},
}


def _write_ws(ws_dir: Path, ws: dict) -> None:
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / f"{ws['name']}.json").write_text(
        json.dumps(ws, ensure_ascii=False), encoding="utf-8"
    )


def _module_project(tmp_path, monkeypatch, ws: dict, *, set_tool: bool = True):
    """Baut ein Modul-Projekt (Wand, Roboter, [Tool], Workstation, Zerlegung „modul",
    simulierter erster Abschnitt) und gibt die Handles + Export-Ergebnis-Bausteine zurück."""
    ws_dir = tmp_path / "workstations"
    _write_ws(ws_dir, ws)
    # set_workstation_for_job lädt über das Default-Verzeichnis → patchen.
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", ws_dir)

    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, WALL_ID, str(creation.overview_run_dir), projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    if set_tool:
        set_tool_for_job(slug, TOOL, projects_dir=projects_dir)
    set_workstation_for_job(slug, ws["name"], projects_dir=projects_dir)
    decomp = propose_decomposition(
        slug, "src", kind="modul",
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    assert decomp.decomposition_kind == "modul"
    section_id = decomp.sections[0]["section_id"]
    sim = simulate_section(
        slug, section_id, "src",
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    return slug, projects_dir, runs_dir, ws_dir, section_id, sim


# --- Vollständiger, generierter Modul-Export ------------------------------------


def test_module_export_generates_full_drl(tmp_path, stub_walls, monkeypatch):
    """Alles bestätigt → das Setup wird generiert, das DRL ist vollständig."""
    slug, projects_dir, runs_dir, ws_dir, section_id, _sim = _module_project(
        tmp_path, monkeypatch, FULL_WS
    )
    result = export_section_drl(
        slug, section_id, "src", projects_dir=projects_dir, workstations_dir=ws_dir
    )
    assert result.complete is True
    assert result.setup_source == "generated"  # ehrlich, nicht „measured"
    assert result.note == ""
    text = result.drl_path.read_text(encoding="utf-8")
    assert "movel(" in text or "movej(" in text
    assert "UNVOLLSTAENDIG" not in text and "UNVOLLSTÄNDIG" not in text


def test_module_export_chain_oracle(tmp_path, stub_walls, monkeypatch):
    """Ketten-Orakel: das generierte Setup trägt dieselbe ``wall_to_base`` wie die
    Simulation (`sectionsim.planned_setup`, z_offset=0) und den Werkzeug-TCP + Workstation-io.

    Damit gilt: generiertes Setup ∘ Slicer-Target == geplante TCP-Pose in Basis —
    das Setup bleibt die eine Transformationsstelle (ADR-006), nur je Zerlegungsart
    anders befüllt."""
    slug, projects_dir, runs_dir, ws_dir, section_id, _sim = _module_project(
        tmp_path, monkeypatch, FULL_WS
    )
    art = load_project(project_dir_for(slug, projects_dir=projects_dir))
    job = art["print_jobs"][0]

    setup, missing = _generate_module_setup(
        art, job, section_id, "src", workstations_dir=ws_dir
    )
    assert missing == []
    assert setup is not None

    # Erwartete Lage: dieselbe Tür wie die Simulation.
    pc = placement_context_for_job(job)
    robot_name, tool = pc.robot_name, pc.tool
    plan = plan_for_job(job, pc.wall, pc.robot, tool, workstations_dir=ws_dir).plan
    sp = next(s for s in plan.sections if s.section.section_id == section_id)
    expected = planned_setup(
        robot_name, sp.placement, tool,
        thickness_mm=plan.wall.thickness_mm, z_offset_mm=0.0,
    )

    assert setup["wall_to_base"] == expected["wall_to_base"]
    assert setup["robot"] == robot_name
    assert setup["tcp"]["pos_mm"] == [float(x) for x in tool.tcp_frame["pos_mm"]]
    # io_channels + Totzeit stammen aus der Workstation (S1-Stammdaten).
    assert setup["io_channels"] == FULL_WS["io_channels"]
    assert setup["deadtime"] == FULL_WS["deadtime"]


# --- Gate „nichts Provisorisches": benannter Fehlbestand ------------------------


def _export_incomplete(tmp_path, stub_walls, monkeypatch, ws, *, set_tool=True):
    slug, projects_dir, runs_dir, ws_dir, section_id, _sim = _module_project(
        tmp_path, monkeypatch, ws, set_tool=set_tool
    )
    return export_section_drl(
        slug, section_id, "src", projects_dir=projects_dir, workstations_dir=ws_dir
    )


def test_gate_missing_io_channels_names_it(tmp_path, stub_walls, monkeypatch):
    ws = {k: v for k, v in FULL_WS.items() if k != "io_channels"}
    result = _export_incomplete(tmp_path, stub_walls, monkeypatch, ws)
    assert result.complete is False
    assert result.setup_source == "generated_incomplete"
    assert "Kanal-Mapping" in result.note
    text = result.drl_path.read_text(encoding="utf-8")
    assert "MODUL-EXPORT UNVOLLSTAENDIG" in text
    assert "Kanal-Mapping" in text
    assert "movel(" not in text  # kein lauffähiges Programm


def test_gate_provisional_deadtime_names_it(tmp_path, stub_walls, monkeypatch):
    ws = {**FULL_WS, "deadtime": {**FULL_WS["deadtime"], "provisional": True}}
    result = _export_incomplete(tmp_path, stub_walls, monkeypatch, ws)
    assert result.complete is False
    assert "Totzeit" in result.note and "provisorisch" in result.note


def test_gate_missing_deadtime_names_it(tmp_path, stub_walls, monkeypatch):
    ws = {k: v for k, v in FULL_WS.items() if k != "deadtime"}
    result = _export_incomplete(tmp_path, stub_walls, monkeypatch, ws)
    assert result.complete is False
    assert "Totzeit" in result.note


def test_gate_missing_frames_names_them(tmp_path, stub_walls, monkeypatch):
    ws = {k: v for k, v in FULL_WS.items()
          if k not in ("robot_base_frame", "work_surface_frame")}
    result = _export_incomplete(tmp_path, stub_walls, monkeypatch, ws)
    assert result.complete is False
    assert "robot_base_frame" in result.note
    assert "Arbeitsflaeche" in result.note or "work_surface_frame" in result.note


def test_gate_missing_tool_names_it(tmp_path, stub_walls, monkeypatch):
    result = _export_incomplete(tmp_path, stub_walls, monkeypatch, FULL_WS, set_tool=False)
    assert result.complete is False
    assert "Endeffektor" in result.note


# --- TCP provisorisch: ehrliche Kennzeichnung am Werkzeug -----------------------


def test_gate_provisional_tcp_names_it(tmp_path, stub_walls, monkeypatch):
    """Ein als provisorisch markierter Werkzeug-TCP hält das Gate an (ADR-013-Geist)."""
    from fgc.domain.tool import build_tool_artifact

    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    artifact = build_tool_artifact(
        "prov_tcp",
        {"pos_mm": [0.0, 0.0, 200.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        1.0,
        {"pump_a": {"kind": "analog"}, "pump_b": {"kind": "analog"}},
        tcp_provisional=True,
    )
    (tools_dir / "prov_tcp.json").write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr("fgc.paths.TOOLS_DIR", tools_dir)

    slug, projects_dir, runs_dir, ws_dir, section_id, _sim = _module_project(
        tmp_path, monkeypatch, FULL_WS, set_tool=False
    )
    set_tool_for_job(slug, "prov_tcp", projects_dir=projects_dir)
    result = export_section_drl(
        slug, section_id, "src", projects_dir=projects_dir, workstations_dir=ws_dir
    )
    assert result.complete is False
    assert "provisorisch" in result.note and "TCP" in result.note


# --- Altbestand + Round-Trip der Stammdaten -------------------------------------


def test_workstation_without_s1_fields_loads_as_none(tmp_path):
    """Altbestand ohne die neuen Felder lädt mit ``None`` (rückwärtskompatibel)."""
    from fgc.domain.workstation import WorkstationDef

    ws_dir = tmp_path / "workstations"
    old = {k: v for k, v in FULL_WS.items()
           if k not in ("io_channels", "deadtime", "robot_base_frame", "work_surface_frame")}
    old["name"] = "alt"
    _write_ws(ws_dir, old)
    loaded = WorkstationDef.load("alt", workstations_dir=ws_dir)
    assert loaded.io_channels is None
    assert loaded.deadtime is None


def test_workstation_s1_fields_roundtrip(tmp_path):
    """build_workstation_artifact + load: io_channels/deadtime round-trippen additiv."""
    from fgc.domain.workstation import WorkstationDef, build_workstation_artifact

    artifact = build_workstation_artifact(
        "s1", "stationary", False,
        base_heights_mm=[0.0, 200.0],
        io_channels=FULL_WS["io_channels"],
        deadtime=FULL_WS["deadtime"],
    )
    assert artifact["io_channels"] == FULL_WS["io_channels"]
    assert artifact["deadtime"] == FULL_WS["deadtime"]
    ws_dir = tmp_path / "workstations"
    ws_dir.mkdir()
    (ws_dir / "s1.json").write_text(json.dumps(artifact), encoding="utf-8")
    loaded = WorkstationDef.load("s1", workstations_dir=ws_dir)
    assert loaded.io_channels == FULL_WS["io_channels"]
    assert loaded.deadtime == FULL_WS["deadtime"]


def test_tool_tcp_provisional_roundtrip(tmp_path):
    """build_tool_artifact schreibt tcp_provisional nur, wenn True; ToolDef liest es."""
    from fgc.domain.tool import ToolDef, build_tool_artifact

    channels = {"pump_a": {"kind": "analog"}}
    confirmed = build_tool_artifact(
        "conf", {"pos_mm": [0.0, 0.0, 1.0], "quat": [1.0, 0.0, 0.0, 0.0]}, 1.0, channels
    )
    assert "tcp_provisional" not in confirmed  # Altbestand-Byte-Gleichheit
    prov = build_tool_artifact(
        "prov", {"pos_mm": [0.0, 0.0, 1.0], "quat": [1.0, 0.0, 0.0, 0.0]}, 1.0, channels,
        tcp_provisional=True,
    )
    assert prov["tcp_provisional"] is True
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "prov.json").write_text(json.dumps(prov), encoding="utf-8")
    assert ToolDef.load("prov", tools_dir=tools_dir).tcp_provisional is True
    (tools_dir / "conf.json").write_text(json.dumps(confirmed), encoding="utf-8")
    assert ToolDef.load("conf", tools_dir=tools_dir).tcp_provisional is False
