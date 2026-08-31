"""Platzierung: Bewertungsmodus (Issue #22) + Optimalvorschlag (Issue #23).

Geprüft wird das externe Verhalten der Modul-Schnittstelle mit synthetischen
Wand-Fixtures (klein/hoch), keine Implementationsdetails: Was liefert
``fgc.placement.evaluate`` für eine kleine Wand nahe der Basis (100 %
erreichbar) und eine überhohe Wand (< 100 %), deterministisch reproduzierbar.
Warnungen sind Daten (kein Abbruch). ``suggest`` findet für eine überhohe Wand
eine erhöhte Basis mit besserem Score als Bodenniveau — deterministisch.
Aktion und API-Endpoints folgen dem Prior-Art-Muster aus test_project
(Stub-Wände + Verzeichnis-Seams).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fgc import domain
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.domain.workstation import WorkstationDef
from fgc.pipeline import runfolder
from fgc.pipeline.actions import (
    advise_singularity,
    create_project_from_ifc,
    evaluate_placements,
    reassess_walls_for_robot,
    select_placement,
    set_print_job,
    suggest_placement,
)
from fgc.pipeline.api import app
from fgc.placement import (
    DEFAULT_STANDOFF_MM,
    PlacementOption,
    WallSurface,
    evaluate,
    placement_artifact,
    suggest,
)
from fgc.project import store as project_store

ROBOT = "doosan_m1013"

PROVENANCE = {
    "source": "test",
    "created": "2026-07-05T12:00:00Z",
    "git_commit": "0000000",
}

#: Kleine Testwand nahe der Basis: vollständig im Arbeitsraum des M1013.
SMALL_WALL = WallSurface(length_mm=600.0, height_mm=400.0, thickness_mm=200.0)

#: Überhohe Testwand: oberer Bereich jenseits der Reichweite (1300 mm).
TALL_WALL = WallSurface(length_mm=600.0, height_mm=4000.0, thickness_mm=200.0)

#: Basis 700 mm vor der Wandfront, mittig, ebenerdig.
OPTION = PlacementOption(
    option_id="boden-mitte", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=0.0
)


@pytest.fixture(scope="module")
def robot() -> RobotDef:
    return RobotDef.load(ROBOT)


@pytest.fixture(scope="module")
def tool() -> ToolDef:
    """Null-TCP-Werkzeug (Düse am Flansch) — hält die Fixtures synthetisch."""
    return ToolDef(
        name="testduese",
        tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )


# --- evaluate: Metrik + Determinismus ----------------------------------------


def test_small_wall_near_base_is_fully_reachable(robot, tool):
    score = evaluate(SMALL_WALL, robot, tool, OPTION)
    assert score.reachable_fraction == 1.0
    assert score.n_reachable == score.n_samples > 0
    assert score.warnings == []


def test_tall_wall_is_partially_reachable(robot, tool):
    score = evaluate(TALL_WALL, robot, tool, OPTION)
    assert 0.0 < score.reachable_fraction < 1.0
    # Nicht erreichte Punkte kommen als Warn-Daten zurück — kein Abbruch.
    kinds = {w["kind"] for w in score.warnings}
    assert "unreachable" in kinds or "joint_limits" in kinds


def test_evaluate_is_deterministic(robot, tool):
    """Gleiche Eingaben → identischer Score (festes Sampling-Raster, ADR-004-Geist)."""
    a = evaluate(TALL_WALL, robot, tool, OPTION)
    b = evaluate(TALL_WALL, robot, tool, OPTION)
    assert a == b


def test_score_carries_margin_and_sampling(robot, tool):
    score = evaluate(SMALL_WALL, robot, tool, OPTION)
    assert score.kinematic_margin is not None
    assert 0.0 < score.kinematic_margin <= 1.0
    assert score.mean_margin is not None
    assert score.kinematic_margin <= score.mean_margin
    assert score.sampling["spacing_mm"] > 0
    assert score.sampling["n_length"] >= 2
    assert score.sampling["n_height"] >= 2


def test_stand_height_raises_reachability_of_tall_wall(robot, tool):
    """Podest (Aufstellhöhe) erhöht den erreichbaren Anteil der hohen Wand."""
    ground = evaluate(TALL_WALL, robot, tool, OPTION)
    podest = evaluate(
        TALL_WALL,
        robot,
        tool,
        PlacementOption("podest", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=1500.0),
    )
    assert podest.reachable_fraction > ground.reachable_fraction


def test_warnings_are_data_not_exceptions(robot, tool):
    """Eine komplett unerreichbare Wand liefert Score 0 + Warnungen — keine Exception."""
    far = PlacementOption("weit-weg", lateral_mm=0.0, standoff_mm=10_000.0, stand_height_mm=0.0)
    score = evaluate(SMALL_WALL, robot, tool, far)
    assert score.reachable_fraction == 0.0
    assert score.kinematic_margin is None
    assert score.mean_margin is None
    assert all(w["kind"] == "unreachable" for w in score.warnings)
    assert len(score.warnings) == score.n_samples


def test_kipp_changes_reachability_evaluation(robot, tool):
    """Der bahn-relative Kipp-Winkel (Issue #61) beeinflusst nachweisbar die
    Erreichbarkeits-Bewertung (Ampel): die angestellte Düse ändert die Flansch-
    Ziel-Orientierung und damit die IK-Erreichbarkeit — über dieselbe geteilte
    ``nozzle_quat`` wie der Slicer (kein Drift, Regressionsschutz #51)."""
    straight = evaluate(TALL_WALL, robot, tool, OPTION)
    tilted = evaluate(TALL_WALL, robot, tool, OPTION, kipp_rad=math.radians(45))
    assert tilted.reachable_fraction != straight.reachable_fraction
    # 0/0 bleibt das heutige Verhalten (senkrecht von oben).
    assert evaluate(TALL_WALL, robot, tool, OPTION, kipp_rad=0.0) == straight


def test_robot_without_kinematics_raises(tool):
    stub = RobotDef(
        name="ohne-kinematik", reach_mm=1000.0,
        max_print_height_mm=1000.0, max_print_length_mm=1000.0,
    )
    with pytest.raises(ValueError, match="Kinematik"):
        evaluate(SMALL_WALL, stub, tool, OPTION)


# --- z_offset_mm: echte Hoehenlage der Flaeche (Issue #132) --------------------


def test_zero_z_offset_is_bitidentical_to_legacy_surface(robot, tool):
    """Regressionsanker (#132): z_offset 0 (Default) ist die alte Konvention —
    Score bit-identisch zur Flaeche ohne explizites Offset-Feld."""
    explicit = WallSurface(600.0, 400.0, 200.0, z_offset_mm=0.0)
    assert evaluate(explicit, robot, tool, OPTION) == evaluate(SMALL_WALL, robot, tool, OPTION)


def test_row_at_1646_from_floor_is_not_fully_reachable(robot, tool):
    """Spezifikations-Anker (#132): eine Flaeche auf z 1646..2470 ist mit
    Reichweite 1300 mm von einer Basis am Boden (stand_height 0) nicht voll
    erreichbar — kein Phantom-Podest mehr."""
    high_row = WallSurface(600.0, 823.2, 200.0, z_offset_mm=1646.4)
    score = evaluate(high_row, robot, tool, OPTION)
    assert score.reachable_fraction < 1.0


def test_absolute_stand_height_compensates_z_offset(robot, tool):
    """Translations-Invarianz (#132): Flaeche + Basis gemeinsam um dz verschoben
    ergibt denselben Score — stand_height und z_offset teilen dasselbe absolute
    Hoehensystem (Boden = Wandfuss)."""
    dz = 1646.4
    lifted_row = WallSurface(600.0, 400.0, 200.0, z_offset_mm=dz)
    lifted_base = PlacementOption(
        "podest-abs", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=dz
    )
    assert (
        evaluate(lifted_row, robot, tool, lifted_base).reachable_fraction
        == evaluate(SMALL_WALL, robot, tool, OPTION).reachable_fraction
    )


# --- placement_artifact: Schema-Vertrag ---------------------------------------


def test_placement_artifact_validates_against_schema(robot, tool):
    score = evaluate(SMALL_WALL, robot, tool, OPTION)
    artifact = placement_artifact(
        ROBOT, tool.name, SMALL_WALL, [(OPTION, score)], PROVENANCE,
        wall_global_id="WALLAAAAAAAAAAAAAAAAAA", selected=OPTION.option_id,
    )
    domain.validate(artifact, "placement")
    assert artifact["options"][0]["score"]["reachable_fraction"] == 1.0
    assert artifact["selected"] == OPTION.option_id


# --- Aktion evaluate_placements / select_placement -----------------------------


@pytest.fixture
def stub_walls(install_walls, make_wall):
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA")])


def _project_with_job(tmp_path, *, with_robot: bool = True):
    """Testprojekt mit Druckjob (+ optional Roboter via Neubewertung) anlegen."""
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  projects_dir=projects_dir)
    if with_robot:
        reassess_walls_for_robot(slug, ROBOT, "src",
                                 projects_dir=projects_dir, runs_dir=runs_dir)
    return slug, projects_dir, runs_dir


OPTIONS = [
    {"option_id": "boden", "lateral_mm": 0.0, "standoff_mm": 700.0, "stand_height_mm": 0.0},
    {"option_id": "podest", "lateral_mm": 0.0, "standoff_mm": 700.0, "stand_height_mm": 1000.0},
]

#: So landen die Optionen im Druckjob: yaw_rad wird mit Default 0.0 vervollständigt.
STORED_OPTIONS = [{**o, "yaw_rad": 0.0} for o in OPTIONS]


def test_evaluate_placements_writes_run_and_updates_job(tmp_path, stub_walls):
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    result = evaluate_placements(
        slug, OPTIONS, "src", selected="boden",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )

    # Bewertungslauf: placement.json vorhanden und schema-valide (ADR-004).
    placement_path = result.run_dir / "placement.json"
    assert placement_path.exists()
    artifact = json.loads(placement_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "placement")
    assert artifact["robot"] == ROBOT
    assert artifact["wall_global_id"] == "WALLAAAAAAAAAAAAAAAAAA"
    assert len(artifact["options"]) == 2

    # Druckjob: nur Plan-Eingaben + Wahl + Lauf-Verweis, keine Scores (ADR-016).
    job = result.artifact["print_jobs"][0]
    assert job["placements"] == STORED_OPTIONS
    assert job["selected_placement"] == "boden"
    assert Path(job["placement_run"]) == result.run_dir.resolve()
    assert str(result.run_dir.resolve()) in job["runs"]
    assert "score" not in job["placements"][0]
    domain.validate(result.artifact, "project")

    # API-Antwortdaten: je Option ein Score.
    assert [s["option_id"] for s in result.scored] == ["boden", "podest"]
    for s in result.scored:
        assert 0.0 <= s["score"]["reachable_fraction"] <= 1.0


def test_evaluate_placements_artifact_carries_labelled_reach_estimate(tmp_path, stub_walls):
    """AC2 (#214): mit vorhandener Reichweitenkarte traegt jede Option im placement.json
    die als Schaetzung gekennzeichnete Karten-Vorwegnahme — das IK-Urteil bleibt daneben."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    result = evaluate_placements(slug, OPTIONS, "src", selected="boden",
                                 projects_dir=projects_dir, runs_dir=runs_dir)
    artifact = json.loads((result.run_dir / "placement.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "placement")
    for opt in artifact["options"]:
        est = opt["score"]["reach_estimate"]
        assert est is not None
        assert est["is_estimate"] is True
        assert est["source"] == "reachability_map"
        assert 0.0 <= est["reachable_fraction"] <= 1.0
        # Ampel-Basis unveraendert (US 11): das IK-Urteil steht getrennt daneben.
        assert 0.0 <= opt["score"]["reachable_fraction"] <= 1.0
    # Auch in der API-Antwort sichtbar (scored ist die dict-Nutzlast der Route).
    assert all(s["score"]["reach_estimate"]["is_estimate"] is True for s in result.scored)


def test_evaluate_placements_without_map_is_byte_identical(tmp_path, stub_walls, monkeypatch):
    """Ohne Karte fail-soft byte-gleich (US 12): kein reach_estimate-Schluessel im Artefakt."""
    from fgc.pipeline import actions

    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *a, **k: None)
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    result = evaluate_placements(slug, OPTIONS, "src",
                                 projects_dir=projects_dir, runs_dir=runs_dir)
    artifact = json.loads((result.run_dir / "placement.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "placement")
    for opt in artifact["options"]:
        assert "reach_estimate" not in opt["score"]


def test_evaluate_placements_without_robot_raises(tmp_path, stub_walls):
    slug, projects_dir, runs_dir = _project_with_job(tmp_path, with_robot=False)
    with pytest.raises(ValueError, match="Roboter"):
        evaluate_placements(slug, OPTIONS, "src",
                            projects_dir=projects_dir, runs_dir=runs_dir)


def test_evaluate_placements_unknown_selected_stores_none(tmp_path, stub_walls):
    """Eine unbekannte selected-Angabe wird nicht übernommen (keine Phantom-Wahl)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    result = evaluate_placements(slug, OPTIONS, "src", selected="gibt-es-nicht",
                                 projects_dir=projects_dir, runs_dir=runs_dir)
    assert result.selected is None
    assert result.artifact["print_jobs"][0]["selected_placement"] is None


def test_select_placement_persists_choice(tmp_path, stub_walls):
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    evaluate_placements(slug, OPTIONS, "src",
                        projects_dir=projects_dir, runs_dir=runs_dir)

    result = select_placement(slug, "podest", projects_dir=projects_dir)

    # Persistiert und nach erneutem Laden wiederhergestellt.
    reloaded = json.loads(result.project_path.read_text(encoding="utf-8"))
    domain.validate(reloaded, "project")
    assert reloaded["print_jobs"][0]["selected_placement"] == "podest"

    # Wahl aufheben (None) ist erlaubt.
    cleared = select_placement(slug, None, projects_dir=projects_dir)
    assert cleared.artifact["print_jobs"][0]["selected_placement"] is None


def test_select_placement_unknown_option_raises(tmp_path, stub_walls):
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    evaluate_placements(slug, OPTIONS, "src",
                        projects_dir=projects_dir, runs_dir=runs_dir)
    with pytest.raises(ValueError, match="nicht"):
        select_placement(slug, "gibt-es-nicht", projects_dir=projects_dir)


# --- IK-Konfiguration: Vorschlag → Uebernahme → Simulation (Issue #233) ----------

_BAA = {"shoulder": "b", "elbow": "a", "wrist": "a"}


def test_ik_config_from_suggestion_flows_into_simulation(tmp_path, install_walls, make_wall):
    """Integration (Issue #233, ADR-026 Punkt 5): der prior-gefuehrt gewaehlte IK-Zweig
    des Optimalvorschlags steht **im Vorschlag** und **im Projekt-Artefakt**, und beim
    Uebernehmen (`select_placement`) faehrt die Simulation nachweislich **dieselbe**
    Konfiguration wie die Bewertung — ueber genau die `IkConfigFilter.from_block`-Tuer,
    die `sectionsim` fuettert. Denkmal-nahe Wand (800x250, Prior-Zelle 800_250 ⇒ `baa`)."""
    from fgc.domain.process_params import effective_section_params
    from fgc.kinematics import IkConfigFilter
    from fgc.pipeline.actions import (
        set_stand_mode_for_job,
        set_tool_for_job,
        set_workstation_for_job,
    )

    install_walls(
        [make_wall("WALLAAAAAAAAAAAAAAAAAA", length=800.0, thickness=250.0, height=700.0)]
    )
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    # Referenz-Tool (30gut) ⇒ der eingecheckte Prior greift; mobile_hub als Workstation.
    set_tool_for_job(slug, "30gut", projects_dir=projects_dir)
    set_workstation_for_job(slug, "mobile_hub", projects_dir=projects_dir)
    set_stand_mode_for_job(slug, "elevated", projects_dir=projects_dir)

    result = suggest_placement(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)

    # (1) Im Vorschlag (API-Nutzlast `scored`): der Sieger traegt den Zweig `baa`.
    winner = result.scored[0]
    assert winner["score"]["ik_config"] == _BAA, winner["score"].get("ik_config")

    # (2) Im Projekt-Artefakt: die Aufstellmoeglichkeit persistiert den Zweig.
    job = result.artifact["print_jobs"][0]
    win_pl = next(p for p in job["placements"] if p["option_id"] == winner["option_id"])
    assert win_pl["ik_config"] == _BAA
    domain.validate(result.artifact, "project")

    # (3) Uebernehmen: select_placement traegt den Zweig in process_params.ik_config.
    sel = select_placement(slug, winner["option_id"], projects_dir=projects_dir)
    job2 = sel.artifact["print_jobs"][0]
    assert job2["process_params"]["ik_config"] == _BAA
    domain.validate(sel.artifact, "project")

    # (4) Die eine Sim-Tuer: sectionsim baut `IkConfigFilter.from_block(effective_
    #     section_params(...)["ik_config"])` — genau der `baa`-Zweig der Bewertung.
    block = effective_section_params(job2, "beliebiger-abschnitt").get("ik_config")
    assert IkConfigFilter.from_block(block) == IkConfigFilter.from_block(_BAA)
    assert not IkConfigFilter.from_block(block).is_auto  # nicht hartkodiert-auto


# --- API: dünne Wrapper ---------------------------------------------------------


@pytest.fixture
def api_dirs(tmp_path, monkeypatch):
    """Projekt- und Laufverzeichnis der Default-Pfade auf tmp umbiegen."""
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


def _api_project_with_job(client, tmp_path) -> str:
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
    return slug


def test_api_post_placements_scores_options(client, api_dirs, stub_walls, tmp_path):
    slug = _api_project_with_job(client, tmp_path)

    resp = client.post(f"/projects/{slug}/placements",
                       json={"options": OPTIONS, "selected": "boden"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["selected"] == "boden"
    assert Path(data["run_dir"]).exists()
    assert [s["option_id"] for s in data["scored"]] == ["boden", "podest"]
    score = data["scored"][0]["score"]
    assert {"reachable_fraction", "n_samples", "n_reachable",
            "kinematic_margin", "warnings"} <= set(score)
    # Druckjob trägt Plan-Eingaben + Verweis (keine Scores).
    job = data["print_jobs"][0]
    assert job["placements"] == STORED_OPTIONS
    assert job["placement_run"] == data["run_dir"]


def test_api_put_placement_selection_roundtrip(client, api_dirs, stub_walls, tmp_path):
    slug = _api_project_with_job(client, tmp_path)
    client.post(f"/projects/{slug}/placements", json={"options": OPTIONS})

    resp = client.put(f"/projects/{slug}/placement-selection",
                      json={"option_id": "podest"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["selected"] == "podest"

    # Nach Neuladen wiederhergestellt.
    job = client.get(f"/projects/{slug}").json()["print_jobs"][0]
    assert job["selected_placement"] == "podest"


def test_api_post_placements_unknown_slug_returns_404(client, api_dirs):
    resp = client.post("/projects/gibt-es-nicht/placements", json={"options": OPTIONS})
    assert resp.status_code == 404


def test_api_post_placements_without_robot_returns_422(client, api_dirs, stub_walls, tmp_path):
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post(
        "/projects", json={"name": "H", "model_path": str(model)}
    ).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA",
                     "assessment_run": overview_run})

    resp = client.post(f"/projects/{slug}/placements", json={"options": OPTIONS})
    assert resp.status_code == 422


# --- suggest: Optimalvorschlag (Issue #23) -------------------------------------


def test_suggest_returns_n_best_sorted_by_reachability(robot, tool):
    """suggest gibt n_best Kandidaten zurueck, beste (hoechste Erreichbarkeit) zuerst."""
    results = suggest(SMALL_WALL, robot, tool, n_best=3)
    assert 1 <= len(results) <= 3
    fractions = [s.reachable_fraction for _, s in results]
    assert fractions == sorted(fractions, reverse=True)


def test_suggest_tall_wall_finds_raised_base_with_better_score(robot, tool):
    """Fuer eine ueberhohe Wand findet suggest eine erhobene Basis mit besserem Score
    als Bodenniveau — deterministisch (Acceptance Criterion Issue #23)."""
    results = suggest(TALL_WALL, robot, tool, n_best=5)
    assert len(results) >= 1
    best_opt, best_score = results[0]
    # Boden-Score (Hoehe 0, Mitte) als Vergleich
    ground_score = evaluate(
        TALL_WALL,
        robot,
        tool,
        PlacementOption(
            "boden",
            lateral_mm=0.0,
            standoff_mm=DEFAULT_STANDOFF_MM,
            stand_height_mm=0.0,
        ),
    )
    # Bester Vorschlag muss mindestens so gut sein wie der Boden-Score.
    assert best_score.reachable_fraction >= ground_score.reachable_fraction
    # Fuer eine ueberhohe Wand (4000 mm) muss der beste Vorschlag eine Hoehe > 0 haben.
    assert best_opt.stand_height_mm > 0.0


def test_suggest_is_deterministic(robot, tool):
    """Gleiche Eingaben → identische Vorschlaege (ADR-004-Geist)."""
    a = suggest(TALL_WALL, robot, tool)
    b = suggest(TALL_WALL, robot, tool)
    assert len(a) == len(b)
    for (opt_a, score_a), (opt_b, score_b) in zip(a, b, strict=True):
        assert opt_a == opt_b
        assert score_a == score_b


def test_suggest_respects_n_best_limit(robot, tool):
    results_1 = suggest(SMALL_WALL, robot, tool, n_best=1)
    results_5 = suggest(SMALL_WALL, robot, tool, n_best=5)
    assert len(results_1) == 1
    assert 1 <= len(results_5) <= 5
    # Das beste Ergebnis ist bei beiden identisch.
    assert results_1[0][0].option_id == results_5[0][0].option_id


def test_suggest_option_ids_start_with_vorschlag(robot, tool):
    """Alle Vorschlaege haben deterministisch kodierte option_ids."""
    results = suggest(SMALL_WALL, robot, tool, n_best=3)
    for opt, _ in results:
        assert opt.option_id.startswith("vorschlag-"), opt.option_id


# --- suggest mit Workstation: zentral + Podesthoehe + optimierter Abstand (#80) --


def _stationary_ws(
    base_heights: tuple[float, ...], *, safety: float = 50.0
) -> WorkstationDef:
    """Nicht-hoehenverstellbare Workstation mit diskretem Podesthoehen-Satz."""
    return WorkstationDef(
        name="teststation",
        mobility="stationary",
        height_adjustable=False,
        base_heights_mm=base_heights,
        safety_min_distance_mm=safety,
    )


def test_suggest_lateral_is_section_center(robot, tool):
    """Golden (#80): mit Workstation steht der Roboter fest zentral — jede
    vorgeschlagene Lage hat seitlich exakt die Abschnittsmitte (lateral 0)."""
    ws = _stationary_ws((0.0, 500.0, 1000.0))
    results = suggest(SMALL_WALL, robot, tool, workstation=ws, n_best=50)
    assert results
    for opt, _ in results:
        assert opt.lateral_mm == 0.0, opt


def test_suggest_picks_best_height_from_pedestal_set(robot, tool):
    """Aus dem Podesthoehen-Satz wird die beste Hoehe gewaehlt (#80): Boden-only
    (nur 0) und Podeststapel liefern nachvollziehbar unterschiedliche Wahl."""
    floor_only = _stationary_ws((0.0,))
    pedestal = _stationary_ws((0.0, 500.0, 1000.0, 1500.0))

    floor_best, _ = suggest(TALL_WALL, robot, tool, workstation=floor_only, n_best=1)[0]
    stack_best, _ = suggest(TALL_WALL, robot, tool, workstation=pedestal, n_best=1)[0]

    # Boden-only kann nur die Bodenhoehe waehlen; der Podeststapel erhoeht die Basis,
    # weil die ueberhohe Wand so mehr Flaeche erreichbar macht.
    assert floor_best.stand_height_mm == 0.0
    assert stack_best.stand_height_mm > 0.0


def test_suggest_distance_optimizes_margin_and_respects_safety(robot, tool):
    """Der gewaehlte Abstand maximiert die Marge (Min-Marge vor Mean-Marge, #98)
    bei voller Erreichbarkeit und liegt nie < `safety_min_distance_mm` (#80)."""
    ws = _stationary_ws((0.0, 500.0, 1000.0), safety=50.0)
    results = suggest(SMALL_WALL, robot, tool, workstation=ws, n_best=50)
    best_opt, best_score = results[0]

    # Sicherheits-Mindestabstand wird nie unterschritten.
    assert best_opt.standoff_mm >= ws.safety_min_distance_mm
    # Voller erreichbarer Anteil erreichbar und gewaehlt.
    assert best_score.reachable_fraction == 1.0
    # Unter allen voll erreichbaren Vorschlaegen ist es das Marge-Maximum —
    # Worst-Case (kinematic_margin) entscheidet vor dem Durchschnitt (#98).
    full = [s for _, s in results if s.reachable_fraction == 1.0]
    assert (best_score.kinematic_margin, best_score.mean_margin) == max(
        (s.kinematic_margin or 0.0, s.mean_margin or 0.0) for s in full
    )
    # Aktiv wegoptimiert: der Minimal-Abstand (Sicherheitsgrenze) ist nicht besser.
    close = evaluate(
        SMALL_WALL, robot, tool,
        PlacementOption("close", 0.0, ws.safety_min_distance_mm, best_opt.stand_height_mm),
    )
    assert (
        best_score.reachable_fraction,
        best_score.kinematic_margin or 0.0,
        best_score.mean_margin or 0.0,
    ) >= (
        close.reachable_fraction,
        close.kinematic_margin or 0.0,
        close.mean_margin or 0.0,
    )


def test_suggest_tiebreak_prefers_worst_case_margin_then_center(robot, tool):
    """Sortierkriterium (#98): unter voll erreichbaren Kandidaten gewinnt die
    beste Min-Marge (Worst-Case), nicht die beste Mean-Marge — und bei exakt
    gleichen Margen die zentrale Lage (kleinstes |lateral|)."""
    results = suggest(SMALL_WALL, robot, tool, n_best=50)
    full = [(o, s) for o, s in results if s.reachable_fraction == 1.0]
    assert full, "SMALL_WALL muss voll erreichbare Kandidaten haben"
    best_opt, best_score = full[0]
    # Kein voll erreichbarer Kandidat hat eine strikt bessere Min-Marge.
    assert (best_score.kinematic_margin or 0.0) == max(
        s.kinematic_margin or 0.0 for _, s in full
    )
    # Unter allen Kandidaten mit identischem Score-Tupel ist die Wahl die
    # zentralste (Zentrums-Praeferenz als letzter Tiebreak).
    key = (
        best_score.reachable_fraction,
        best_score.kinematic_margin or 0.0,
        best_score.mean_margin or 0.0,
    )
    ties = [
        o for o, s in full
        if (s.reachable_fraction, s.kinematic_margin or 0.0, s.mean_margin or 0.0) == key
    ]
    assert abs(best_opt.lateral_mm) == min(abs(o.lateral_mm) for o in ties)


def test_suggest_fallback_floor_mode_clamps_height(robot, tool):
    """Aufstell-Toggle im Fallback (#100): ohne Workstation und mit
    stand_mode='floor' bleiben alle Kandidaten auf Bodenhoehe 0."""
    results = suggest(TALL_WALL, robot, tool, stand_mode="floor", n_best=50)
    assert results
    for opt, _ in results:
        assert opt.stand_height_mm == 0.0, opt


def test_suggest_fallback_elevated_mode_keeps_height_grid(robot, tool):
    """Gegenprobe (#100): stand_mode='elevated' laesst dem Fallback das volle
    Hoehenraster — die ueberhohe Wand bekommt weiterhin eine erhoehte Basis."""
    best_opt, _ = suggest(TALL_WALL, robot, tool, stand_mode="elevated", n_best=1)[0]
    assert best_opt.stand_height_mm > 0.0


def test_suggest_workstation_is_deterministic(robot, tool):
    """Determinismus (#80): gleiche Wand/Roboter/Workstation → gleiche Wahl."""
    ws = _stationary_ws((0.0, 500.0, 1000.0))
    a = suggest(TALL_WALL, robot, tool, workstation=ws)
    b = suggest(TALL_WALL, robot, tool, workstation=ws)
    assert len(a) == len(b)
    for (opt_a, score_a), (opt_b, score_b) in zip(a, b, strict=True):
        assert opt_a == opt_b
        assert score_a == score_b


def test_suggest_adjustable_workstation_rasters_height_range(robot, tool):
    """Hoehenverstellbare (mobile) Workstation: die beste Hoehe kommt aus dem
    `height_range_mm`-Intervall, zentral, Abstand >= Sicherheitsabstand (#80)."""
    ws = WorkstationDef(
        name="mobil",
        mobility="mobile",
        height_adjustable=True,
        height_range_mm=(0.0, 1500.0),
    )
    best_opt, _ = suggest(TALL_WALL, robot, tool, workstation=ws, n_best=1)[0]
    assert 0.0 <= best_opt.stand_height_mm <= 1500.0
    assert best_opt.lateral_mm == 0.0
    assert best_opt.standoff_mm >= ws.safety_min_distance_mm


# --- suggest_placement action (Issue #23) --------------------------------------


def test_suggest_placement_adds_vorschlag_options(tmp_path, stub_walls):
    """suggest_placement fuegt Vorschlaege mit 'vorschlag-'-IDs in den Druckjob ein."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    result = suggest_placement(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)

    option_ids = [s["option_id"] for s in result.scored]
    assert any(oid.startswith("vorschlag-") for oid in option_ids)
    # Placement-Lauf ist gueltig.
    placement_path = result.run_dir / "placement.json"
    assert placement_path.exists()
    domain.validate(json.loads(placement_path.read_text(encoding="utf-8")), "placement")


def test_suggest_placement_preserves_manual_options(tmp_path, stub_walls):
    """Manuelle Optionen bleiben erhalten; nur alte Vorschlaege werden ersetzt."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    # Erst manuelle Optionen bewerten
    evaluate_placements(slug, OPTIONS, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    result = suggest_placement(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)

    option_ids = [s["option_id"] for s in result.scored]
    # Manuelle Optionen bleiben
    assert "boden" in option_ids
    assert "podest" in option_ids
    # Vorschlaege dazu
    assert any(oid.startswith("vorschlag-") for oid in option_ids)


def test_suggest_placement_replaces_old_suggestions(tmp_path, stub_walls):
    """Mehrfacher Aufruf erzeugt keine Vorschlags-Duplikate."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    suggest_placement(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    result = suggest_placement(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)

    option_ids = [s["option_id"] for s in result.scored]
    vorschlag_ids = [oid for oid in option_ids if oid.startswith("vorschlag-")]
    assert len(vorschlag_ids) == len(set(vorschlag_ids))


def test_suggest_placement_without_robot_raises(tmp_path, stub_walls):
    slug, projects_dir, runs_dir = _project_with_job(tmp_path, with_robot=False)
    with pytest.raises(ValueError, match="Roboter"):
        suggest_placement(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)


def test_suggest_placement_preserves_existing_selection(tmp_path, stub_walls):
    """Ein Optimalvorschlag ergänzt die Vergleichsliste — er hebt keine bereits
    getroffene Wahl auf (nur `select_placement`/erneutes Wählen darf das)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    evaluate_placements(slug, OPTIONS, "src", selected="boden",
                        projects_dir=projects_dir, runs_dir=runs_dir)

    result = suggest_placement(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)

    assert result.selected == "boden"
    assert result.artifact["print_jobs"][0]["selected_placement"] == "boden"


# --- API: placement-suggestion endpoint (Issue #23) ----------------------------


def test_api_post_placement_suggestion_returns_scored_options(
    client, api_dirs, stub_walls, tmp_path
):
    """POST /placement-suggestion gibt Vorschlaege in der scored-Liste zurueck."""
    slug = _api_project_with_job(client, tmp_path)

    resp = client.post(f"/projects/{slug}/placement-suggestion", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    scored = data["scored"]
    assert len(scored) > 0
    assert any(s["option_id"].startswith("vorschlag-") for s in scored)
    assert Path(data["run_dir"]).exists()
    # Score-Felder vorhanden
    score = scored[0]["score"]
    required = {"reachable_fraction", "n_samples", "n_reachable", "kinematic_margin", "warnings"}
    assert required <= set(score)


def test_api_placement_suggestion_unknown_slug_returns_404(client, api_dirs):
    resp = client.post("/projects/gibt-es-nicht/placement-suggestion", json={})
    assert resp.status_code == 404


def test_api_placement_suggestion_merges_with_manual_options(
    client, api_dirs, stub_walls, tmp_path
):
    """Vorschlaege werden zu bestehenden manuellen Optionen hinzugefuegt."""
    slug = _api_project_with_job(client, tmp_path)
    # Manuelle Optionen anlegen
    client.post(f"/projects/{slug}/placements", json={"options": OPTIONS})
    # Optimalvorschlag dazu
    resp = client.post(f"/projects/{slug}/placement-suggestion", json={"n_best": 2})
    assert resp.status_code == 200, resp.text
    option_ids = [s["option_id"] for s in resp.json()["scored"]]
    assert "boden" in option_ids
    assert "podest" in option_ids
    assert any(oid.startswith("vorschlag-") for oid in option_ids)


# --- Singularitaets-Advisor: Aktion + API (Issue #65, AC 3; Fokus-Abschnitt #134) ---


def test_advise_singularity_classifies_focused_section(tmp_path, stub_walls):
    """Der Advisor bewertet die Platzierung des Fokus-Abschnitts (Issue #134):
    ``section_id`` waehlt den Abschnitt des Zerlegungsplans, dessen persistierte
    Platzierung (``plan_for_job``, Muster Kollisions-Advisor #130) beurteilt wird."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    result = advise_singularity(
        slug, section_id="abschnitt-1", projects_dir=projects_dir
    )

    # Read-only Urteil: ein Typ der schlechtesten erreichten Pose liegt vor.
    assert result.section_id == "abschnitt-1"
    assert result.type in ("wrist", "elbow", "shoulder")
    assert result.measure is not None
    # Wenn beraten wird, traegt der Vorschlag Hebel + Vorher/Nachher-Marge.
    if result.advice is not None:
        assert result.advice["lever"] in ("kipp", "placement", "config_flip")
        assert "margin_before" in result.advice and "margin_after" in result.advice


def test_advise_singularity_without_section_is_empty(tmp_path, stub_walls):
    """Ohne Fokus-Abschnitt (``section_id=None``) ist die Antwort leer — kein
    Fehler (Issue #134): der Viewer zeigt den freundlichen Fokus-Hinweis."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    result = advise_singularity(slug, projects_dir=projects_dir)
    assert result.section_id is None
    assert result.type is None
    assert result.advice is None


def test_advise_singularity_stale_section_is_empty(tmp_path, stub_walls):
    """Ein Abschnitt, den der Plan nicht (mehr) kennt, ergibt ebenfalls das
    leere Ergebnis (stale Fokus, kein Fehler — Issue #134)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    result = advise_singularity(
        slug, section_id="gibt-es-nicht", projects_dir=projects_dir
    )
    assert result.section_id is None
    assert result.type is None
    assert result.advice is None


def test_api_singularity_advice_returns_judgment(client, api_dirs, stub_walls, tmp_path):
    slug = _api_project_with_job(client, tmp_path)

    resp = client.post(f"/projects/{slug}/singularity-advice",
                       json={"section_id": "abschnitt-1"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["section_id"] == "abschnitt-1"
    assert data["type"] in ("wrist", "elbow", "shoulder")
    assert set(data) >= {"slug", "job_id", "section_id", "type", "near", "measure", "advice"}


def test_api_singularity_advice_without_section_is_empty(
    client, api_dirs, stub_walls, tmp_path
):
    """Ohne ``section_id`` antwortet die Route freundlich leer (Issue #134)."""
    slug = _api_project_with_job(client, tmp_path)
    resp = client.post(f"/projects/{slug}/singularity-advice", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] is None
    assert data["advice"] is None


def test_api_singularity_advice_unknown_slug_returns_404(client, api_dirs):
    resp = client.post("/projects/gibt-es-nicht/singularity-advice", json={})
    assert resp.status_code == 404


# --- Altprojekte: Gesamtwand-Felder bleiben lesbar (Issue #134) -----------------


def test_legacy_placement_fields_survive_reload_byte_identical(tmp_path, stub_walls):
    """Altprojekt mit gesetzten ``placements``/``selected_placement``: die Felder
    bleiben schema-valide lesbar und ein Neuladen laesst project.json byte-gleich
    (Issue #134 — der Gesamtwand-Satz wird nur nicht mehr befuellt/angezeigt)."""
    from fgc.project import load_project, project_dir_for, write_project

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    evaluate_placements(slug, OPTIONS, "src", selected="boden",
                        projects_dir=projects_dir, runs_dir=runs_dir)
    select_placement(slug, "podest", projects_dir=projects_dir)

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    before = (project_dir / "project.json").read_bytes()

    artifact = load_project(project_dir)
    domain.validate(artifact, "project")
    job = artifact["print_jobs"][0]
    assert job["placements"] == STORED_OPTIONS
    assert job["selected_placement"] == "podest"

    # Unverändertes Zurückschreiben (Lese-Pfad) ändert kein Byte.
    write_project(project_dir, artifact)
    assert (project_dir / "project.json").read_bytes() == before


# --- Abstand-Semantik: standoff misst ab der Wandflaeche (Issue #160) -----------


def test_base_position_in_wall_adds_half_thickness():
    """Die eine Naht: y = Dicke/2 + standoff — der Abstand ist der FREIE Abstand
    vor der Wandflaeche (Zollstock-Mass), nicht die Mittelebenen-Koordinate.
    Regression Denkmal 2026-07-12: 510-mm-Wand, Abstand 535 ⇒ Basis bei y=790,
    nicht 535 (dort stuende sie nur 280 mm vor der Flaeche und kollidierte)."""
    from fgc.placement import base_position_in_wall

    option = PlacementOption("p", lateral_mm=12.0, standoff_mm=535.0, stand_height_mm=40.0)
    assert base_position_in_wall(option, 510.0) == (12.0, 790.0, 40.0)


def test_base_position_roundtrip_and_degenerate_thickness():
    from fgc.placement import base_position_in_wall, standoff_from_base_y

    option = PlacementOption("p", 0.0, standoff_mm=700.0, stand_height_mm=0.0)
    _, y, _ = base_position_in_wall(option, 300.0)
    assert standoff_from_base_y(y, 300.0) == pytest.approx(700.0)
    # Unbekannte Dicke (<= 0) degeneriert ehrlich zu y = standoff — kein Raten.
    assert base_position_in_wall(option, 0.0)[1] == 700.0
    assert base_position_in_wall(option, -5.0)[1] == 700.0


def test_thicker_wall_moves_base_back_in_evaluation(robot, tool):
    """Gleicher Abstand, dickere Wand ⇒ die Basis steht weiter von der
    Mittelebene (den Stichproben-Zielen) — der erreichbare Anteil darf nicht
    steigen. Vorher (Mittelebenen-Semantik) war die Bewertung dickenblind."""
    option = PlacementOption("p", 0.0, standoff_mm=700.0, stand_height_mm=0.0)
    thin = WallSurface(length_mm=2600.0, height_mm=2200.0, thickness_mm=100.0)
    thick = WallSurface(length_mm=2600.0, height_mm=2200.0, thickness_mm=800.0)
    frac_thin = evaluate(thin, robot, tool, option).reachable_fraction
    frac_thick = evaluate(thick, robot, tool, option).reachable_fraction
    assert frac_thick < frac_thin
