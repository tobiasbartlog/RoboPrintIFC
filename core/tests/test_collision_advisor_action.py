"""Kollisions-Advisor End-to-End über die *echte* Simulation (Issue #130, ``slow``).

Beweist mit der realen Slice+Trajektorien+Befund-Maschinerie (doosan_m1013 trägt
Kollisionsgeometrie), dass ``advise_collision``:

- den Basis-Befund der Simulation liest (Vorher-Metrik, keine Parallel-Metrik),
- jeden Hebel-Kandidaten durch **Neu-Simulation** bewertet und nur Verbesserer
  (Vorher<Nachher) mit Schreibstellen-Nutzlast anbietet,
- deterministisch dieselbe Liste liefert.

Teuer (mehrere Neu-Simulationen) ⇒ ``slow``, per Default deselektiert. Das
Kandidatenmenü wird für den Test klein gehalten (Modul-Konstanten gepatcht), damit
er einige wenige Simulationen fährt statt der vollen Sweep-Matrix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fgc.collision import advisor as adv
from fgc.pipeline.actions import (
    advise_collision,
    check_section_clearance,
    create_project_from_ifc,
    propose_decomposition,
    reassess_walls_for_robot,
    set_print_job,
)

ROBOT = "doosan_m1013"


@pytest.fixture
def stub_walls(install_walls, make_wall):
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", length=800.0, height=2600.0)])


@pytest.fixture
def small_menu(monkeypatch):
    """Kleines Kandidatenmenü: wenige Neu-Simulationen statt der vollen Sweep-Matrix."""
    monkeypatch.setattr(adv, "IK_AXES", ("wrist",))
    monkeypatch.setattr(adv, "KIPP_DELTAS_DEG", (20.0,))
    monkeypatch.setattr(adv, "LEAD_DELTAS_DEG", ())
    monkeypatch.setattr(adv, "STANDOFF_DELTAS_MM", (200.0,))
    monkeypatch.setattr(adv, "STAND_HEIGHT_DELTAS_MM", ())


def _project(tmp_path):
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
    return slug, projects_dir, decomp


@pytest.mark.slow
def test_advise_collision_real_resimulation(tmp_path, stub_walls, small_menu):
    slug, projects_dir, decomp = _project(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    result = advise_collision(slug, section_id=section_id, projects_dir=projects_dir)

    # Basis-Befund aus der echten Simulation vorhanden (Vorher-Metrik).
    assert result.section_id == section_id
    assert result.baseline is not None
    assert "min_distance_mm" in result.baseline

    # Jede angebotene Option ist über die Neu-Simulation ein Verbesserer und trägt
    # eine anwendbare Schreibstellen-Nutzlast (bestehende Setter).
    for opt in result.options:
        better = (opt["min_distance_after_mm"] is not None
                  and opt["min_distance_before_mm"] is not None
                  and opt["min_distance_after_mm"] > opt["min_distance_before_mm"])
        removed = (not opt["collision_free_before"]) and opt["collision_free_after"]
        assert better or removed
        assert opt["write"]["setter"] in ("process-params", "placement-override")

    # Deterministisch: derselbe Aufruf liefert dieselbe Liste.
    again = advise_collision(slug, section_id=section_id, projects_dir=projects_dir)
    assert again.options == result.options


@pytest.mark.slow
def test_advise_collision_baseline_only_single_simulation(
    tmp_path, stub_walls, small_menu, monkeypatch,
):
    """``include_options=False`` (Prüf-UX #139/#145): nur der Basis-Befund entsteht —
    genau EINE Neu-Simulation, keine Kandidaten, leere Optionsliste."""
    from fgc.pipeline import actions as act

    slug, projects_dir, decomp = _project(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    calls = {"n": 0}
    orig = act.slice_and_simulate_section

    def counted(*args, **kwargs):
        calls["n"] += 1
        return orig(*args, **kwargs)

    monkeypatch.setattr(act, "slice_and_simulate_section", counted)

    result = advise_collision(
        slug, section_id=section_id, projects_dir=projects_dir, include_options=False,
    )
    assert result.section_id == section_id
    assert result.baseline is not None
    assert "min_distance_mm" in result.baseline
    assert result.options == []
    assert calls["n"] == 1


@pytest.mark.slow
def test_check_section_clearance_real_verdict(tmp_path, stub_walls):
    """Die Pruef-Tuer (#162) liefert über die echte Simulation ein kompaktes
    frei/kollidiert-Urteil je Teil (Verursacher/Eindringtiefe), deterministisch,
    ohne Lauf-Artefakt."""
    slug, projects_dir, decomp = _project(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    res = check_section_clearance(slug, section_id=section_id, projects_dir=projects_dir)
    assert res.section_id == section_id
    assert res.verdict is not None
    v = res.verdict
    assert {
        "collides", "min_distance_mm", "penetration_mm", "causer_link",
        "n_red", "n_checked", "n_samples", "travel_thinned",
    } <= set(v)
    assert isinstance(v["collides"], bool)
    assert v["n_checked"] <= v["n_samples"]
    assert v["penetration_mm"] >= 0.0
    # Kein Lauf geschrieben (read-only): keine section_runs am Job.
    from fgc.project import load_project, project_dir_for

    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    assert job.get("section_runs", []) == []
    # Deterministisch: gleicher Aufruf ⇒ gleiches Urteil.
    again = check_section_clearance(slug, section_id=section_id, projects_dir=projects_dir)
    assert again.verdict == v


@pytest.mark.slow
def test_check_section_clearance_reports_collision_location(tmp_path, stub_walls):
    """Pipeline-Aktions-Naht (Issue #181, Akzeptanzkriterium): ``check_section_clearance``
    liefert für eine konstruierte, real kollidierende Wand (dieselbe Testwand wie
    ``test_check_section_clearance_real_verdict``, kollidiert real für beide
    Abschnitte) den **Kollisions-ORT** additiv im Urteils-Dict — Original-Index,
    Schicht, Verursacher-Position und rote Intervalle, plausibel gegen die übrigen
    Urteils-Felder (n_samples/n_red/causer_link/causer_against/min_distance_mm)."""
    slug, projects_dir, decomp = _project(tmp_path)

    for section in decomp.sections:
        section_id = section["section_id"]
        res = check_section_clearance(slug, section_id=section_id, projects_dir=projects_dir)
        v = res.verdict
        assert v is not None and v["collides"] is True, (
            f"Testaufbau: Abschnitt {section_id} muss real kollidieren"
        )
        location_fields = {
            "worst_original_index", "worst_layer", "causer_position_mm", "red_intervals",
        }
        assert location_fields <= set(v)

        # Original-Index: innerhalb der ungedünnten Bahn, nicht der ausgedünnten.
        assert v["worst_original_index"] is not None
        assert 0 <= v["worst_original_index"] < v["n_samples"]
        assert v["worst_layer"] is not None and v["worst_layer"] >= 0

        # Verursacher-Position: drei endliche Koordinaten (mm) im Teilsystem.
        pos = v["causer_position_mm"]
        assert isinstance(pos, list) and len(pos) == 3
        assert all(isinstance(c, (int, float)) for c in pos)

        # Rote Intervalle: mindestens eines (die Wand kollidiert), jedes trägt
        # Original-indizierte Grenzen innerhalb der Bahn sowie Glied/Gegner, und das
        # schlimmste Intervall stimmt mit dem kompakten Verursacher-Urteil überein.
        assert v["red_intervals"], "collides=True muss mind. ein rotes Intervall ergeben"
        for iv in v["red_intervals"]:
            assert 0 <= iv["start_index"] <= iv["worst_index"] <= iv["end_index"] < v["n_samples"]
        worst_original_index = v["worst_original_index"]
        worst_intervals = [
            iv for iv in v["red_intervals"] if iv["worst_index"] == worst_original_index
        ]
        assert worst_intervals, "das schlimmste Sample muss in einem der roten Intervalle liegen"
        assert worst_intervals[0]["link"] == v["causer_link"]
        assert worst_intervals[0]["against"] == v["causer_against"]

        # Deterministisch wie das restliche Urteil.
        again = check_section_clearance(slug, section_id=section_id, projects_dir=projects_dir)
        assert again.verdict == v


@pytest.mark.slow
def test_check_section_clearance_reuses_prebuilt_ctx(tmp_path, stub_walls, monkeypatch):
    """Ein vorgebauter ``SectionSimContext`` (Verfeinerungs-Loop #165) wird
    wiederverwendet — der loop-invariante Unterbau (IFC/Zerlegung) läuft **nicht**
    erneut, und ein Platzierungs-Override wird ausgewertet."""
    from fgc.collision.advisor import Override
    from fgc.pipeline import actions as act
    from fgc.project import load_project, project_dir_for

    slug, projects_dir, decomp = _project(tmp_path)
    section_id = decomp.sections[0]["section_id"]

    artifact = load_project(project_dir_for(slug, projects_dir=projects_dir))
    job = artifact["print_jobs"][0]
    ctx = act.section_sim_context(artifact, job, section_id)

    calls = {"n": 0}
    orig = act.section_sim_context

    def counted(*args, **kwargs):
        calls["n"] += 1
        return orig(*args, **kwargs)

    monkeypatch.setattr(act, "section_sim_context", counted)

    res = check_section_clearance(
        slug, section_id=section_id, ctx=ctx, projects_dir=projects_dir,
        override=Override(placement={"standoff_mm": 300.0}),
    )
    # ctx wiederverwendet ⇒ kein erneuter Unterbau-Aufbau.
    assert calls["n"] == 0
    assert res.verdict is not None
    assert isinstance(res.verdict["collides"], bool)


@pytest.mark.slow
def test_check_section_clearance_section_id_strictness(tmp_path, stub_walls):
    """Abschnitts-ID-Strenge (Issue #169, Zwischenkritik B4): dieselbe Strenge wie
    beim Job-ID-Aufruf oben — kein stiller Rückfall auf den ersten Abschnitt, kein
    still aufgelöster Kontext-vs-ID-Konflikt.

    - Bekannte ``section_id`` ⇒ unverändertes Urteil (Verhalten vor #169 unverändert,
      dieselbe Simulation wie ``test_check_section_clearance_real_verdict``).
    - Unbekannte ``section_id`` ⇒ ``ValueError``, der die unbekannte ID **benennt**
      (kein stiller Fallback auf ``sids[0]``, der tendenziell freieste Abschnitt).
    - Ein vorgereichter ``ctx`` eines **anderen** Abschnitts als der explizit
      übergebenen ``section_id`` ⇒ Zurückweisung statt stille Auflösung zugunsten
      des ``ctx``.
    """
    from fgc.pipeline import actions as act
    from fgc.project import load_project, project_dir_for

    slug, projects_dir, decomp = _project(tmp_path)
    section_id = decomp.sections[0]["section_id"]
    other_section_id = decomp.sections[1]["section_id"]
    assert section_id != other_section_id

    # Bekannte ID: Urteil entsteht wie gehabt, keine Verhaltensänderung.
    res = check_section_clearance(slug, section_id=section_id, projects_dir=projects_dir)
    assert res.section_id == section_id
    assert res.verdict is not None
    assert isinstance(res.verdict["collides"], bool)

    # Unbekannte ID: benannter Fehler statt stiller Substitution durch sids[0].
    with pytest.raises(ValueError, match="unbekannte-abschnitts-id"):
        check_section_clearance(
            slug, section_id="unbekannte-abschnitts-id", projects_dir=projects_dir,
        )

    # Kontext-vs-ID-Konflikt: ein vorgereichter ctx eines anderen Abschnitts wird
    # zurückgewiesen statt still (zugunsten des ctx) aufgelöst.
    artifact = load_project(project_dir_for(slug, projects_dir=projects_dir))
    job = artifact["print_jobs"][0]
    ctx = act.section_sim_context(artifact, job, other_section_id)
    with pytest.raises(ValueError, match="widerspricht"):
        check_section_clearance(
            slug, section_id=section_id, ctx=ctx, projects_dir=projects_dir,
        )


def test_api_collision_advice_unknown_slug_returns_404():
    """Dünne Route: unbekanntes Projekt ⇒ 404 (schnell, ohne Simulation)."""
    from fastapi.testclient import TestClient

    from fgc.pipeline.api import app

    client = TestClient(app)
    resp = client.post("/projects/gibt-es-nicht/collision-advice", json={})
    assert resp.status_code == 404
