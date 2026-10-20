"""Abschnitts-Slicing + Simulation aus der Platzierung (Issue #26).

Deckt die Akzeptanzkriterien ab:
- **Abschnitts-Slice**: das Teil-Mesh eines Abschnitts (aus `fgc.decompose.apply`)
  fließt in den bestehenden Slicer (`slice_wall`, erweiterter Eingang) → Targets
  liegen nur im Abschnittsbereich (nicht über die ganze Wand).
- **Simulation aus Platzierung**: `simulate_section` erzeugt je Abschnitt **einen**
  regulären Lauf mit toolpath.json + trajectory.json; die Trajektorie vermerkt die
  Lagequelle „geplant" (`meta.pose_source == "planned"`); der Druckjob verweist je
  Abschnitt darauf (`section_runs`).

Aktion + Fixtures folgen dem Prior-Art-Muster aus test_decompose (Stub-Wände +
Verzeichnis-Seams), damit kein IFC/ifcopenshell nötig ist.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from fgc import domain
from fgc.decompose import Cut, apply, from_cuts
from fgc.domain.process_params import ProcessWindow, SliceParams
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.pipeline import runfolder
from fgc.pipeline.actions import (
    create_project_from_ifc,
    plan_for_job,
    propose_decomposition,
    reassess_walls_for_robot,
    set_print_job,
    set_workstation_for_job,
    simulate_section,
)
from fgc.pipeline.api import app
from fgc.placement import WallSurface
from fgc.project import store as project_store
from fgc.slicer import slice_wall

ROBOT = "doosan_m1013"

#: Überhohe Quaderwand (2600 mm) — erzwingt eine Zerlegung mit Höhenstufen.
TALL_WALL = WallSurface(length_mm=800.0, height_mm=2600.0, thickness_mm=200.0)


@pytest.fixture(scope="module")
def robot() -> RobotDef:
    return RobotDef.load(ROBOT)


@pytest.fixture(scope="module")
def tool() -> ToolDef:
    return ToolDef(
        name="testduese",
        tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )


def _wall_box(length: float, height: float, thickness: float) -> trimesh.Trimesh:
    """Quader im Wand-System: x zentriert, z ab 0 (wie WallSurface)."""
    box = trimesh.creation.box(extents=[length, thickness, height])
    box.apply_translation([0.0, 0.0, height / 2.0])
    return box


# --- Abschnitts-Slice: Teil-Mesh → Targets nur im Abschnittsbereich ------------


def test_section_slice_targets_confined_to_section(robot, tool):
    """Das Teil-Mesh eines oberen Abschnitts ergibt Targets nur in dessen Höhe."""
    mesh = _wall_box(800.0, 2600.0, 200.0)
    plan = from_cuts(TALL_WALL, robot, tool, [Cut("horizontal", 1300.0)])
    parts = apply(mesh, plan)
    assert len(parts) == 2

    # Oberer Abschnitt (z 1300..2600): ins abschnitts-lokale System (z ab 0).
    upper_idx = next(
        i for i, sp in enumerate(plan.sections) if sp.section.z0_mm == 1300.0
    )
    section = plan.sections[upper_idx].section
    part = parts[upper_idx]
    verts = np.asarray(part.vertices, dtype=float).copy()
    verts[:, 0] -= section.center_x_mm
    verts[:, 2] -= section.z0_mm

    params = SliceParams.from_window(ProcessWindow.load())
    toolpath = slice_wall(verts, np.asarray(part.faces), "WALLAAAAAAAAAAAAAAAAAA", params)
    assert toolpath.targets

    zs = [t.frame.pos_mm[2] for t in toolpath.targets]
    section_height = section.z1_mm - section.z0_mm  # ~1300 mm
    # Alle Targets im Abschnittsbereich (z in [0, Höhe]) — nicht über die ganze
    # Wand (2600 mm): max z bleibt deutlich unter der vollen Wandhöhe.
    assert min(zs) >= -1e-6
    assert max(zs) <= section_height + 1e-6
    assert max(zs) < 1400.0  # weit unter der vollen Wandhöhe von 2600 mm


# --- Aktion simulate_section: ein Lauf je Abschnitt, pose_source=planned -------


@pytest.fixture
def stub_walls(install_walls, make_wall):
    # Überhohe Quaderwand (2600 mm) im Weltsystem (x/y zentriert, z ab 0).
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", length=800.0, height=2600.0)])


def _project_with_decomposition(tmp_path):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src",
                             projects_dir=projects_dir, runs_dir=runs_dir)
    decomp = propose_decomposition(
        slug, "src", cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    return slug, projects_dir, runs_dir, decomp


def test_planned_setup_converts_absolute_height_to_section_local(tool):
    """Naht-Anker (Issue #132): stand_height 400 mm absolut bei Abschnittsfuss
    z0 = 819.6 ⇒ Basis im abschnitts-lokalen Sim-Frame bei −419.6 mm (negativ
    erlaubt: die Basis steht unterhalb des Abschnittsfusses); ``wall_to_base``
    traegt die Inverse (+419.6). Default ``z_offset_mm=0`` bleibt byte-gleich
    zum alten Verhalten (unterste Reihe / ganze Wand / Art „modul")."""
    from fgc.pipeline.sectionsim import planned_setup
    from fgc.placement import PlacementOption

    placement = PlacementOption(
        "p", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=400.0
    )
    setup = planned_setup(ROBOT, placement, tool, thickness_mm=300.0, z_offset_mm=819.6)
    # wall_to_base = invert(base_in_wall): z = -(400 - 819.6) = +419.6.
    assert setup["wall_to_base"]["pos_mm"][2] == pytest.approx(419.6)
    # Abstand ab Wandflaeche (Issue #160): y = Dicke/2 + 700 = 850; Inverse −850.
    assert setup["wall_to_base"]["pos_mm"][1] == pytest.approx(-850.0)

    legacy = planned_setup(ROBOT, placement, tool, thickness_mm=300.0)
    assert legacy["wall_to_base"]["pos_mm"][2] == pytest.approx(-400.0)


def test_simulate_upper_section_anchors_base_at_absolute_height(tmp_path, stub_walls):
    """End-to-end (Issue #132): der obere Abschnitt (z0 = 1300) mit
    Boden-Platzierung (stand_height 0 **absolut**) verankert die Basis im
    abschnitts-lokalen Frame bei z = −1300 — die Basis steht am Boden, nicht
    mehr auf einem Phantom-Podest am Abschnittsfuss. Die Simulation laeuft
    trotz (ehrlich) begrenzter Erreichbarkeit durch — Befund, kein Gate."""
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    upper = next(s for s in decomp.sections if s["z0_mm"] == 1300.0)
    assert upper["placement"]["stand_height_mm"] == 0.0  # floor ⇒ absolut 0

    result = simulate_section(
        slug, upper["section_id"], "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    trajectory = json.loads(
        (result.run_dir / "trajectory.json").read_text(encoding="utf-8")
    )
    assert trajectory["meta"]["base_frame"]["pos_mm"][2] == pytest.approx(-1300.0)


def test_simulate_section_persists_section_z0(tmp_path, stub_walls):
    """Issue #135: die Trajektorie nennt die echte Höhenlage des Abschnitts
    (``meta.section_z0_mm``) — der Viewer hebt das Replay (Bahn/Arm/Druckstand)
    damit auf die echte Bandlage. Unterste Reihe = 0, obere Reihe = ihr z0;
    das Artefakt bleibt schema-gültig (additive Erweiterung)."""
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    by_z0 = {s["z0_mm"]: s for s in decomp.sections}

    for z0 in (0.0, 1300.0):
        result = simulate_section(
            slug, by_z0[z0]["section_id"], "src",
            projects_dir=projects_dir, runs_dir=runs_dir,
        )
        trajectory = json.loads(
            (result.run_dir / "trajectory.json").read_text(encoding="utf-8")
        )
        domain.validate(trajectory, "trajectory")
        assert trajectory["meta"]["section_z0_mm"] == pytest.approx(z0)


def test_simulate_upper_section_collision_has_no_ground_alarm(tmp_path, stub_walls):
    """Issue #135 end-to-end: der obere Abschnitt (z0 = 1300) mit erreichbarer
    Podest-Platzierung (Aufstellhöhe 1300 absolut — das Nutzer-Szenario „obere
    Reihe, erhöht") bekommt seinen Kollisions-Boden bei lokal −1300 — kein
    „unter Boden"-Fehlalarm am Abschnittsfuß (kein rotes/gelbes Intervall gegen
    'ground'). (Vom Boden aus wäre die Bahn unerreichbar und der ehrlich
    eingefrorene Arm hinge in der DH-Null-Pose unter dem realen Boden — eine
    ehrliche Kollision, kein Fehlalarm; hier zählt die echte Bahn.)"""
    from fgc.pipeline.actions import set_placement_override_for_job

    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    upper = next(s for s in decomp.sections if s["z0_mm"] == 1300.0)
    set_placement_override_for_job(
        slug, upper["section_id"], stand_height_mm=1300.0, projects_dir=projects_dir,
    )

    result = simulate_section(
        slug, upper["section_id"], "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    trajectory = json.loads(
        (result.run_dir / "trajectory.json").read_text(encoding="utf-8")
    )
    # Basis auf dem Podest: abschnitts-lokal z = 1300 − 1300 = 0 (Naht #132).
    assert trajectory["meta"]["base_frame"]["pos_mm"][2] == pytest.approx(0.0)
    coll = trajectory["meta"].get("collision")
    if coll is None:
        pytest.skip("keine Kollisionsgeometrie installiert — Befund fehlt fail-soft")
    assert not any(
        iv["against"] == "ground" and iv["status"] != "green"
        for iv in coll["intervals"]
    )


def test_simulate_section_writes_run_with_planned_trajectory(tmp_path, stub_walls):
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    result = simulate_section(
        slug, section_id, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )

    # Ein regulärer Lauf mit toolpath.json + trajectory.json + Provenienz (ADR-004).
    toolpath_path = result.run_dir / "toolpath.json"
    traj_path = result.run_dir / "trajectory.json"
    assert toolpath_path.exists() and traj_path.exists()
    toolpath = json.loads(toolpath_path.read_text(encoding="utf-8"))
    trajectory = json.loads(traj_path.read_text(encoding="utf-8"))
    domain.validate(toolpath, "toolpath")
    domain.validate(trajectory, "trajectory")

    # Lagequelle „geplant" in den Trajektorien-Metadaten (Akzeptanzkriterium).
    assert trajectory["meta"]["pose_source"] == "planned"
    assert result.pose_source == "planned"
    assert result.duration_s > 0.0

    # Feste Roboterbasis im Wandsystem als Replay-Anker (Issue #66): vorhanden
    # und wohlgeformt; der Viewer verankert den Arm damit fix an der Platzierung.
    base_frame = trajectory["meta"]["base_frame"]
    assert len(base_frame["pos_mm"]) == 3
    assert len(base_frame["quat"]) == 4

    # Druckjob verweist je Abschnitt auf den Lauf (section_runs, ADR-016).
    job = result.artifact["print_jobs"][0]
    section_runs = {sr["section_id"]: sr["run"] for sr in job["section_runs"]}
    assert section_runs[section_id] == str(result.run_dir.resolve())
    assert str(result.run_dir.resolve()) in job["runs"]
    domain.validate(result.artifact, "project")


def test_simulate_section_writes_collision_finding(tmp_path, stub_walls):
    """simulate_section schreibt den additiven Kollisions-Befund automatisch (Issue #127).

    Der Roboter trägt ein ``collision_geometry``-Artefakt → ``meta.collision``
    entsteht mit Konfig-Echo (provisional), Abstandskurve parallel zu den Samples
    und verdichteten Intervallen. Befund, kein Gate: die Trajektorie validiert und
    bleibt vollständig, egal wie der Befund ausfällt.
    """
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    result = simulate_section(
        slug, section_id, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    trajectory = json.loads((result.run_dir / "trajectory.json").read_text(encoding="utf-8"))
    domain.validate(trajectory, "trajectory")

    coll = trajectory["meta"]["collision"]
    assert coll["config"]["provisional"] is True
    assert coll["config"]["mode"] == "abschnitt"
    # Abstandskurve/Verursacher liegen parallel zu den Samples (samples selbst
    # bleiben unangetastet — additiv in meta).
    assert len(coll["distances_mm"]) == len(trajectory["samples"])
    assert len(coll["causer_link"]) == len(trajectory["samples"])
    assert coll["n_red"] + coll["n_yellow"] + coll["n_green"] == len(trajectory["samples"])
    assert isinstance(coll["intervals"], list)


def test_simulate_section_uses_job_slice_params(tmp_path, stub_walls):
    """simulate_section liest die Slice-Basisparameter aus dem Druckjob (Issue #59).

    Ohne process_params.slice gelten die Karten-/Code-Defaults; ist der Block
    gesetzt, tragen die geschriebenen Toolpath-Parameter die Job-Werte.
    """
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    # Referenz: ohne Block = Karten-/Code-Default.
    default_lh = SliceParams.from_window(ProcessWindow.load()).layer_height_mm
    override_lh = default_lh + 3.0  # deutlich abweichend von der Karte

    set_process_params(
        slug, {"layer_height_mm": override_lh, "n_shells": 4}, projects_dir=projects_dir,
    )
    result = simulate_section(
        slug, section_id, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )

    toolpath = json.loads((result.run_dir / "toolpath.json").read_text(encoding="utf-8"))
    assert toolpath["params"]["layer_height_mm"] == override_lh
    assert toolpath["params"]["n_shells"] == 4


def test_simulate_section_uses_job_speeds_and_io(tmp_path, stub_walls):
    """v_print/v_travel/io_print/io_travel fließen über process_params bis in die Targets.

    Scheibe 2b (Issue #60): die „Fortgeschritten"-Felder sind editierbar und über
    den process_params.slice-Block beim Slicen wirksam. Die Geschwindigkeit landet
    je Ziel als ``v_mm_s``, der io-Skalar gleichförmig über alle io-Kanäle.
    """
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    set_process_params(
        slug,
        {
            "v_print_mm_s": 42.0,
            "v_travel_mm_s": 333.0,
            "io_print": 0.7,
            "io_travel": 0.0,
        },
        projects_dir=projects_dir,
    )
    result = simulate_section(
        slug, section_id, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )

    toolpath = json.loads((result.run_dir / "toolpath.json").read_text(encoding="utf-8"))
    prints = [t for t in toolpath["targets"] if t["kind"] == "print"]
    travels = [t for t in toolpath["targets"] if t["kind"] == "travel"]
    assert prints and travels
    assert all(t["v_mm_s"] == 42.0 for t in prints)
    assert all(t["v_mm_s"] == 333.0 for t in travels)
    # io-Skalar gleichförmig über alle Kanäle (v0: pump_a/pump_b).
    assert all(all(v == 0.7 for v in t["io"].values()) for t in prints)
    assert all(all(v == 0.0 for v in t["io"].values()) for t in travels)


def test_simulate_section_without_process_params_uses_card_default(tmp_path, stub_walls):
    """Ohne process_params.slice bleibt es beim Karten-/Code-Default (rückwärtskompatibel)."""
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    section_id = decomp.sections[0]["section_id"]
    default_lh = SliceParams.from_window(ProcessWindow.load()).layer_height_mm

    result = simulate_section(
        slug, section_id, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    toolpath = json.loads((result.run_dir / "toolpath.json").read_text(encoding="utf-8"))
    assert toolpath["params"]["layer_height_mm"] == default_lh


def test_simulate_section_replaces_previous_run_for_same_section(tmp_path, stub_walls):
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    first = simulate_section(slug, section_id, "src",
                             projects_dir=projects_dir, runs_dir=runs_dir)
    second = simulate_section(slug, section_id, "src",
                              projects_dir=projects_dir, runs_dir=runs_dir)

    assert first.run_dir != second.run_dir  # eigener Lauf je Aufruf (ADR-004)
    job = second.artifact["print_jobs"][0]
    entries = [sr for sr in job["section_runs"] if sr["section_id"] == section_id]
    assert len(entries) == 1  # nur der neueste Verweis je Abschnitt
    assert entries[0]["run"] == str(second.run_dir.resolve())


def test_simulate_section_unknown_section_raises(tmp_path, stub_walls):
    slug, projects_dir, runs_dir, _decomp = _project_with_decomposition(tmp_path)
    with pytest.raises(ValueError, match="Abschnitt"):
        simulate_section(slug, "abschnitt-gibt-es-nicht", "src",
                         projects_dir=projects_dir, runs_dir=runs_dir)


def test_simulate_section_without_robot_raises(tmp_path, stub_walls):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  projects_dir=projects_dir)
    # kein reassess → kein Roboter im Job
    with pytest.raises(ValueError, match="Roboter"):
        simulate_section(slug, "abschnitt-1", "src",
                         projects_dir=projects_dir, runs_dir=runs_dir)


# --- Zerlegungsplan: eine Tür für Druckplan + Simulation (Issue #112) -----------

WORKSTATION = "mobile_hub"  # workstations/mobile_hub.json (mobil, Höhen 0..600)


def _project_with_workstation(tmp_path, *, kind: str, stand_mode: str = "floor"):
    """Projekt + Druckjob mit gesetzter Workstation und Zerlegung der Art ``kind``.

    Spiegelt ``_project_with_decomposition``, setzt aber vorher die Workstation
    (Pflicht für ``kind="modul"``, Plan-Eingabe für ``stand_mode`` bei
    ``"abschnitt"``). Gibt Slug + Verzeichnisse + Decompose-Ergebnis zurück.
    """
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src",
                             projects_dir=projects_dir, runs_dir=runs_dir)
    set_workstation_for_job(slug, WORKSTATION, "default", projects_dir=projects_dir)
    if stand_mode != "floor":
        # Aufstell-Toggle direkt in den Job schreiben (#81) — kein eigener Setter
        # nötig; Plan-Eingabe, die die Tür lesen muss.
        from fgc.project import load_project, project_dir_for, write_project
        pd = project_dir_for(slug, projects_dir=projects_dir)
        art = load_project(pd)
        jobs = [{**j, "stand_mode": stand_mode} if j["job_id"] == "default" else j
                for j in art["print_jobs"]]
        write_project(pd, {**art, "print_jobs": jobs})
    decomp = propose_decomposition(
        slug, "src", kind=kind,
        cuts=([{"orientation": "horizontal", "position_mm": 1300.0}]
              if kind == "abschnitt" else None),
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    return slug, projects_dir, runs_dir, decomp


def test_simulate_section_modul_job_reconstructs_plan(tmp_path, stub_walls):
    """Regression #112/#97: die Simulation eines *Modul*-Druckjobs rekonstruiert
    den Plan, statt in ``ValueError`` „modul braucht eine Workstation" zu laufen.

    Vor #112 ließ der Lesepfad (`_plan_for_job`) die Workstation weg → `propose`
    warf, obwohl der Job eine Workstation trägt (im Viewer ein 422). Jetzt liest
    `plan_for_job` sie aus dem Job — die Modul-Simulation (#97) läuft durch.
    """
    slug, projects_dir, runs_dir, decomp = _project_with_workstation(
        tmp_path, kind="modul"
    )
    assert decomp.decomposition_kind == "modul"
    section_id = decomp.sections[0]["section_id"]

    result = simulate_section(
        slug, section_id, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )

    assert result.pose_source == "planned"
    assert (result.run_dir / "trajectory.json").exists()
    job = result.artifact["print_jobs"][0]
    section_runs = {sr["section_id"]: sr["run"] for sr in job["section_runs"]}
    assert section_runs[section_id] == str(result.run_dir.resolve())


def test_plan_for_job_read_path_matches_decomposition_placements(tmp_path, stub_walls):
    """Regression #112: der rekonstruierte Zerlegungsplan (Lesepfad) trägt
    dieselben Platzierungen wie der Decompose-Lauf (Schreibpfad) — auch mit
    gesetzter Workstation und erhöhtem Aufstell-Modus.

    Vor #112 ignorierte der Lesepfad Workstation/`stand_mode` und fiel auf das
    Fallback-Raster zurück → die simulierte Platzierung wich still vom Druckplan
    ab. Die eine Tür macht die Gleichheit zur erzwungenen Eigenschaft.
    """
    slug, projects_dir, runs_dir, decomp = _project_with_workstation(
        tmp_path, kind="abschnitt", stand_mode="elevated"
    )
    from fgc.pipeline.sectionsim import placement_context_for_job
    from fgc.project import load_project, project_dir_for

    art = load_project(project_dir_for(slug, projects_dir=projects_dir))
    job = art["print_jobs"][0]
    pc = placement_context_for_job(job)
    robot, tool, wall = pc.robot, pc.tool, pc.wall

    reconstructed = plan_for_job(job, wall, robot, tool, strict_overrides=False)

    # Platzierung je Teil: Lesepfad == im Decompose-Lauf gemeldete Platzierung.
    by_id = {sp.section.section_id: sp.placement for sp in reconstructed.plan.sections}
    assert by_id, "Rekonstruktion lieferte keine Teile"
    for sec in decomp.sections:
        p = by_id[sec["section_id"]]
        assert p.lateral_mm == pytest.approx(sec["placement"]["lateral_mm"])
        assert p.standoff_mm == pytest.approx(sec["placement"]["standoff_mm"])
        assert p.stand_height_mm == pytest.approx(sec["placement"]["stand_height_mm"])
    # Die Tür hat die Workstation tatsächlich aus dem Job aufgelöst.
    assert reconstructed.workstation is not None


# --- API: dünner Wrapper --------------------------------------------------------


@pytest.fixture
def api_dirs(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    projects_dir.mkdir()
    runs_dir.mkdir()
    monkeypatch.setattr(project_store, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(runfolder, "RUNS_DIR", runs_dir)
    return projects_dir, runs_dir


@pytest.fixture
def client():
    return TestClient(app)


def test_api_simulate_section_returns_run_and_planned_source(
    client, api_dirs, stub_walls, tmp_path
):
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post(
        "/projects", json={"name": "Testhaus", "model_path": str(model)}
    ).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA",
                     "assessment_run": overview_run})
    client.put(f"/projects/{slug}/robot", json={"robot": ROBOT})
    decomp = client.post(
        f"/projects/{slug}/decomposition",
        json={"cuts": [{"orientation": "horizontal", "position_mm": 1300.0}]},
    ).json()
    section_id = decomp["sections"][0]["section_id"]

    resp = client.post(f"/projects/{slug}/sections/{section_id}/simulate", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["pose_source"] == "planned"
    assert data["duration_s"] > 0.0
    assert Path(data["run_dir"]).exists()
    job = data["print_jobs"][0]
    assert any(sr["section_id"] == section_id for sr in job["section_runs"])


def test_api_simulate_unknown_slug_returns_404(client, api_dirs):
    resp = client.post("/projects/gibt-es-nicht/sections/abschnitt-1/simulate", json={})
    assert resp.status_code == 404


def test_api_simulate_unknown_section_returns_422(client, api_dirs, stub_walls, tmp_path):
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post(
        "/projects", json={"name": "H", "model_path": str(model)}
    ).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA",
                     "assessment_run": overview_run})
    client.put(f"/projects/{slug}/robot", json={"robot": ROBOT})
    resp = client.post(f"/projects/{slug}/sections/nope/simulate", json={})
    assert resp.status_code == 422
