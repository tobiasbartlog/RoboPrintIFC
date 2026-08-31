"""Beam-Suche end-to-end DURCH die Aktion (Issue #217, PRD #183 Stufe 3).

Ergaenzt ``test_beam_suche.py`` (Strategie-Einheit) um die **produktive Naht** in
``fgc.pipeline.actions.propose_decomposition``: der Scorer wird aus der geladenen
Reichweitenkarte (#210) gebaut, die Pruef-Tuer (#165) urteilt, der Sieger wird ueber
``_persist_decompose_run``/``DecomposeBundle`` (#198) persistiert — Metriken-Katalog +
Verworfen-Gruende + Relaxationsausweis landen im ``refinement``-Block des Laufs.

Die teure Kollisions-Pruef-Tuer wird am **oeffentlichen** Aktions-Seam
``actions.collision_pruef_tuer`` durch ein schnelles, deterministisches Fake ersetzt
(Muster wie ``test_pruef_check`` fuer ``clearance_verdict``); die Reichweitenkarte ist
eine echte, grob gebaute :class:`ReachabilityMap` (dieselbe Build-Logik wie offline).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from test_decompose import _project_with_job

from fgc.pipeline import actions, checkjobs

ROBOT = "doosan_m1013"


@pytest.fixture
def stub_walls(install_walls, make_wall):
    # Moderate Wand: vom Boden erreichbar (auch als 1x1) — so kollidiert der grobe
    # Schnitt per Fake echt (Reject-Grund „kollision"), feinere Schnitte sind frei.
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", height=1000.0, length=1000.0)])


@pytest.fixture(scope="module")
def coarse_map():
    from fgc.kinematics.opw import OpwKinematics
    from fgc.kinematics.reachability import ReachabilityMap

    return ReachabilityMap.build(OpwKinematics.from_robot(ROBOT), cell_mm=150.0, n_alpha=13)


@dataclass
class FakeVerdict:
    collides: bool
    causer_position_mm: tuple | None = None


def _install_fake_pruef_tuer(monkeypatch, *, collide_if):
    """Ersetzt das produktive Orakel durch ein schnelles Fake: ``collide_if(n_len, n_hoehe)``."""

    def _factory(_artifact, _job, **_k):
        def _tuer(kandidat, _row_index, _option):
            if collide_if(kandidat.n_length, kandidat.n_height):
                return FakeVerdict(collides=True, causer_position_mm=(0.0, 0.0, 0.0))
            return FakeVerdict(collides=False)

        return _tuer

    monkeypatch.setattr(actions, "collision_pruef_tuer", _factory)


def _read_refinement(result):
    doc = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    return doc.get("refinement"), doc


# --------------------------------------------------------------------------- #
# Scorer-Fabrik (produktiv, fail-soft)
# --------------------------------------------------------------------------- #


def test_beam_search_setup_baut_scorer_aus_der_karte(monkeypatch, coarse_map, tmp_path, stub_walls):
    """`_beam_search_setup` baut BeamSuche + BilligerScorer + Objective aus der Karte."""
    from fgc.decompose import BeamSuche, BilligerScorer, ObjectiveConfig

    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *_a, **_k: coarse_map)
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    from fgc.project import load_project, project_dir_for

    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    pc = actions.placement_context_for_job(job)

    strat, scorer, obj = actions._beam_search_setup(pc, job, None, "floor")
    assert isinstance(strat, BeamSuche)
    assert isinstance(scorer, BilligerScorer)
    assert isinstance(obj, ObjectiveConfig)


def test_beam_search_setup_fail_soft_ohne_karte(monkeypatch, tmp_path, stub_walls):
    """Ohne Reichweitenkarte (None) liefert die Fabrik (None, None, None) — Greedy-Fallback."""
    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *_a, **_k: None)
    slug, projects_dir, _runs = _project_with_job(tmp_path)
    from fgc.project import load_project, project_dir_for

    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    pc = actions.placement_context_for_job(job)
    assert actions._beam_search_setup(pc, job, None, "floor") == (None, None, None)


# --------------------------------------------------------------------------- #
# End-to-end durch propose_decomposition
# --------------------------------------------------------------------------- #


def test_propose_decomposition_beam_end_to_end(monkeypatch, coarse_map, tmp_path, stub_walls):
    """Kollidierender Fall durch die Aktion: kollisionsfreier Sieger + Metriken + Verworfen."""
    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *_a, **_k: coarse_map)
    # Grobe (wenig geteilte) Raster kollidieren; die Suche muss feiner schneiden.
    _install_fake_pruef_tuer(monkeypatch, collide_if=lambda nl, nh: nh <= 1)

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    result = actions.propose_decomposition(
        slug, "src", beam_search=True,
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    refinement, doc = _read_refinement(result)

    assert refinement is not None
    assert refinement["strategy"] == "beam-suche"
    assert refinement["geprueft"] is True
    # Kollidierendes 1x1 wird NICHT vorgeschlagen — die Suche fand einen feineren Schnitt.
    assert doc["grid"]["n_height"] >= 2
    # Metriken-Katalog vollstaendig (US 20).
    assert set(refinement["metriken"]) == {
        "teilanzahl", "volumen_cv", "fugenflaeche_mm2", "erreichbarer_anteil",
        "geprueft_frei_anteil", "standplaetze", "rechenzeit_s",
    }
    # Verworfen-Gruende nachvollziehbar (US 10) — mindestens ein Kollisions-Reject.
    gruende = {v["grund"] for v in refinement["verworfen"]}
    assert "kollision" in gruende
    # Schema-valide (das refinement ist additiv, decompose.json bleibt gueltig).
    from fgc import domain

    domain.validate(doc, "decompose")


def test_propose_decomposition_default_byte_gleich(tmp_path, stub_walls):
    """Ohne beam_search bleibt der Vorschlag byte-gleich (kein refinement, Regressionsanker)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    result = actions.propose_decomposition(
        slug, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    _refinement, doc = _read_refinement(result)
    assert "refinement" not in doc


def test_propose_decomposition_beam_fail_soft_ohne_karte(monkeypatch, tmp_path, stub_walls):
    """beam_search=True ohne Karte ⇒ Greedy (byte-gleich), kein refinement, kein Beam."""
    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *_a, **_k: None)
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    result = actions.propose_decomposition(
        slug, "src", beam_search=True,
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    _refinement, doc = _read_refinement(result)
    assert "refinement" not in doc


# --------------------------------------------------------------------------- #
# Beam-Suche fuer Modul-Jobs (Issue #237)
# --------------------------------------------------------------------------- #


def _project_with_module_job(tmp_path):
    """Projekt mit Druckjob, Workstation UND gespeicherter Zerlegungsart „modul"."""
    from test_decompose import _project_with_module_workstation

    from fgc.project import load_project, project_dir_for, write_project

    slug, projects_dir, runs_dir, ws_dir = _project_with_module_workstation(tmp_path)
    pdir = project_dir_for(slug, projects_dir=projects_dir)
    art = load_project(pdir)
    art["print_jobs"][0]["decomposition_kind"] = "modul"
    write_project(pdir, art)
    return slug, projects_dir, runs_dir, ws_dir


def test_collision_pruef_tuer_reicht_die_zerlegungsart_durch(monkeypatch):
    """#237: die Pruef-Tuer erzwingt nicht mehr „abschnitt" — ein Modul-Kandidaten-Job
    wird am Druckort simuliert (die Job-Kopie behaelt seine Zerlegungsart)."""
    from fgc.decompose.kandidaten import band_raster_kandidat
    from fgc.decompose.strategie import ZellenOption
    from fgc.pipeline import sectionsim
    from fgc.placement import WallSurface

    captured = {}

    def fake_ctx(_artifact, temp_job, _section_id, **_k):
        captured["kind"] = temp_job["decomposition_kind"]
        raise RuntimeError("stop")  # fail-soft-Pfad: die Tuer liefert None

    monkeypatch.setattr(sectionsim, "section_sim_context", fake_ctx)
    tuer = sectionsim.collision_pruef_tuer({}, {"decomposition_kind": "modul"})
    k = band_raster_kandidat(WallSurface(800.0, 1000.0, 200.0), 1, 2)
    assert tuer(k, 0, ZellenOption()) is None  # Befund, kein Gate (fail-soft)
    assert captured["kind"] == "modul"


def test_propose_decomposition_beam_uebernimmt_job_zerlegungsart(
    monkeypatch, coarse_map, tmp_path, stub_walls
):
    """#237 end-to-end: ohne ``kind``-Argument uebernimmt der Beam-Lauf die im Job
    gespeicherte Art „modul" (vorher erzwang der Default „abschnitt" eine In-situ-
    Suche der ganzen Wand — 256/256 „reichweite", 0 Pruef-Tuer-Aufrufe)."""
    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *_a, **_k: coarse_map)
    seen = {}

    def _factory(_artifact, job, **_k):
        seen["kind"] = job["decomposition_kind"]

        def _tuer(kandidat, _row_index, _option):
            if kandidat.n_height <= 1:
                return FakeVerdict(collides=True, causer_position_mm=(0.0, 0.0, 0.0))
            return FakeVerdict(collides=False)

        return _tuer

    monkeypatch.setattr(actions, "collision_pruef_tuer", _factory)

    slug, projects_dir, runs_dir, ws_dir = _project_with_module_job(tmp_path)
    result = actions.propose_decomposition(
        slug, "src", beam_search=True,
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    assert result.decomposition_kind == "modul"
    assert seen["kind"] == "modul"  # die Pruef-Tuer urteilt am Druckort, nicht in-place

    refinement, doc = _read_refinement(result)
    assert refinement is not None
    assert refinement["strategy"] == "beam-suche"
    assert refinement["geprueft"] is True  # vorher: leer=True, calls_used=0 (#237)
    assert doc["grid"]["n_height"] >= 2  # kollidierendes 1x1 wird nicht vorgeschlagen
    # Die Job-Art bleibt „modul" — der Hintergrundlauf stellt sie nie um.
    assert result.artifact["print_jobs"][0]["decomposition_kind"] == "modul"
    from fgc import domain

    domain.validate(doc, "decompose")


# --------------------------------------------------------------------------- #
# Hintergrundlauf mit Fortschritt + Abbruch (checkjobs-Muster #145/#175)
# --------------------------------------------------------------------------- #


def test_start_beam_propose_hintergrundlauf(monkeypatch, coarse_map, tmp_path, stub_walls):
    """Der Beam-Lauf laeuft als Hintergrund-Job mit Fortschritt bis zum Ergebnis."""
    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *_a, **_k: coarse_map)
    _install_fake_pruef_tuer(monkeypatch, collide_if=lambda nl, nh: nh <= 1)

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    checkjobs.reset()
    job = checkjobs.start_beam_propose(
        slug, "default", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    # Auf Abschluss warten (Daemon-Thread) — deterministisch ueber den Job-Zustand.
    import time
    from pathlib import Path

    for _ in range(200):
        handle = checkjobs.get_beam_propose(job.id)
        if handle.finished_at is not None:
            break
        time.sleep(0.05)
    handle = checkjobs.get_beam_propose(job.id)
    assert handle.state == checkjobs.STATE_DONE
    assert handle.n_total > 0  # Kontingent gemeldet
    assert handle.n_done >= 1  # Fortschritt in Pruef-Tuer-Aufrufen
    assert handle.run_dir is not None
    doc = json.loads((Path(handle.run_dir) / "decompose.json").read_text(encoding="utf-8"))
    assert doc["refinement"]["strategy"] == "beam-suche"
    checkjobs.reset()
