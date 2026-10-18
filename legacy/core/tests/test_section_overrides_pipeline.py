"""Abschnitts-Overrides wirken in der Kern-Tür — Gradierungs-Drift geschlossen (#188).

Vor #188 slicte ``slice_and_simulate_section`` (damals ``actions._slice_and_simulate_section``,
seit #189 in ``fgc.pipeline.sectionsim``) mit den **globalen** Werten
(``job_slice_overrides``/``job_orientation``), obwohl die Pro-Abschnitts-Overrides
(``process_params.sections``, #82/#83) persistiert wurden und den Abschnitt
veralteten — exakt die Drift-Klasse, die #51 mit der einen ``nozzle_quat``-Quelle
geschlossen hat. Jetzt beziehen ``section_sim_context``/``slice_and_simulate_section``
beide Gruppen abschnitts-effektiv (``section_slice_overrides``/``section_orientation``
über ``effective_section_params``); alle vier Aufrufer (Simulation, Kollisions-Advisor,
Clearance-Check, Prüf-Tür) erben die Gradierung über die unveränderte Signatur.

Akzeptanzkriterien end-to-end über ``simulate_section`` (der persistierte Lauf,
aus dem auch der Export liest):

- Abschnitts-Override ``layer_height_mm`` ändert ``n_layers`` des Abschnitts-Laufs
  (vor dem Fix rot: der Override wurde persistiert, aber nie gerechnet).
- Abschnitts-Override Kipp ändert nachweisbar die Bahnorientierung **nur** dieses
  Abschnitts (Muster #61: ``frame.quat`` weicht von ``NOZZLE_DOWN_QUAT`` ab).
- Abschnitt ohne Override rechnet byte-gleich wie bisher (Regressionsanker):
  ein Override am Nachbar-Abschnitt lässt Targets + Parameter-Echo unverändert.

Fixtures folgen dem Prior-Art-Muster aus test_section_simulation (Stub-Wände,
horizontale Zerlegung in zwei Abschnitte — kein IFC/ifcopenshell nötig).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fgc.domain.orientation import NOZZLE_DOWN_QUAT
from fgc.pipeline.actions import (
    create_project_from_ifc,
    propose_decomposition,
    reassess_walls_for_robot,
    set_print_job,
    set_process_params,
    simulate_section,
)

ROBOT = "doosan_m1013"
WALL_ID = "WALLAAAAAAAAAAAAAAAAAA"


@pytest.fixture
def stub_walls(install_walls, make_wall):
    # Überhohe Quaderwand (2600 mm) im Weltsystem (x/y zentriert, z ab 0).
    return install_walls([make_wall(WALL_ID, length=800.0, height=2600.0)])


def _project_with_decomposition(tmp_path):
    """Projekt + Druckjob + horizontale Zerlegung (zwei Abschnitte übereinander)."""
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, WALL_ID, str(creation.overview_run_dir), projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src",
                             projects_dir=projects_dir, runs_dir=runs_dir)
    decomp = propose_decomposition(
        slug, "src", cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    return slug, projects_dir, runs_dir, decomp


def _toolpath(run_dir: Path) -> dict:
    return json.loads((run_dir / "toolpath.json").read_text(encoding="utf-8"))


def test_section_layer_height_override_changes_n_layers(tmp_path, stub_walls):
    """Akzeptanz #188: Abschnitts-Override ``layer_height_mm`` ändert ``n_layers``
    des Abschnitts-Laufs — und nur diesen; der Nachbar rechnet mit der Karte."""
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    sid, sid_other = (s["section_id"] for s in decomp.sections[:2])

    baseline = simulate_section(slug, sid, "src",
                                projects_dir=projects_dir, runs_dir=runs_dir)
    tp_base = _toolpath(baseline.run_dir)
    default_lh = tp_base["params"]["layer_height_mm"]
    n_base = tp_base["summary"]["n_layers"]

    set_process_params(
        slug, {},
        sections={sid: {"slice": {"layer_height_mm": default_lh * 2.0}}},
        projects_dir=projects_dir,
    )
    result = simulate_section(slug, sid, "src",
                              projects_dir=projects_dir, runs_dir=runs_dir)
    tp = _toolpath(result.run_dir)
    # Der Override wirkt im gerechneten Lauf (vor #188: params blieben global).
    assert tp["params"]["layer_height_mm"] == default_lh * 2.0
    assert tp["summary"]["n_layers"] < n_base
    assert tp["summary"]["n_layers"] == pytest.approx(n_base / 2.0, abs=1.0)

    # Gradierung, keine Globalität: der Nachbar-Abschnitt bleibt bei der Karte.
    other = simulate_section(slug, sid_other, "src",
                             projects_dir=projects_dir, runs_dir=runs_dir)
    assert _toolpath(other.run_dir)["params"]["layer_height_mm"] == default_lh


def test_section_kipp_override_orients_only_that_section(tmp_path, stub_walls):
    """Akzeptanz #188 (Muster #61): Kipp-Override eines Abschnitts kippt dessen
    Bahnorientierung (``frame.quat`` ≠ senkrecht), der Nachbar bleibt senkrecht."""
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    sid, sid_other = (s["section_id"] for s in decomp.sections[:2])

    set_process_params(
        slug, {},
        sections={sid: {"orientation": {"kipp_deg": 25.0}}},
        projects_dir=projects_dir,
    )

    kipped = simulate_section(slug, sid, "src",
                              projects_dir=projects_dir, runs_dir=runs_dir)
    prints = [t for t in _toolpath(kipped.run_dir)["targets"] if t["kind"] == "print"]
    assert prints
    down = list(NOZZLE_DOWN_QUAT)
    assert any(t["frame"]["quat"] != down for t in prints), (
        "Kipp-Override des Abschnitts hat die Bahnorientierung nicht erreicht"
    )

    upright = simulate_section(slug, sid_other, "src",
                               projects_dir=projects_dir, runs_dir=runs_dir)
    assert all(
        t["frame"]["quat"] == down for t in _toolpath(upright.run_dir)["targets"]
    ), "Nachbar-Abschnitt ohne Override muss senkrecht von oben bleiben"


def test_section_without_override_is_byte_identical(tmp_path, stub_walls):
    """Regressionsanker #188: ein Abschnitt ohne eigenen Override rechnet byte-gleich
    wie bisher — auch wenn global Werte gesetzt sind und der Nachbar übersteuert."""
    slug, projects_dir, runs_dir, decomp = _project_with_decomposition(tmp_path)
    sid, sid_other = (s["section_id"] for s in decomp.sections[:2])

    # Globale Overrides gesetzt (der interessante Fall: Erben statt Karte).
    set_process_params(
        slug, {"layer_height_mm": 12.0, "n_shells": 3},
        orientation={"lead_deg": 5.0},
        projects_dir=projects_dir,
    )
    before = simulate_section(slug, sid, "src",
                              projects_dir=projects_dir, runs_dir=runs_dir)
    tp_before = _toolpath(before.run_dir)

    # Override NUR am Nachbarn — dieser Abschnitt erbt weiter global. Die globalen
    # Gruppen werden unverändert mitgesendet (so echot sie auch der Viewer beim
    # Abschnitts-Speichern; ein leeres slice_params würde sie löschen).
    set_process_params(
        slug, {"layer_height_mm": 12.0, "n_shells": 3},
        orientation={"lead_deg": 5.0},
        sections={sid_other: {
            "slice": {"layer_height_mm": 20.0},
            "orientation": {"kipp_deg": 25.0},
        }},
        projects_dir=projects_dir,
    )
    after = simulate_section(slug, sid, "src",
                             projects_dir=projects_dir, runs_dir=runs_dir)
    tp_after = _toolpath(after.run_dir)

    # Byte-gleiche Rechnung: identisches Parameter-Echo + identische Targets.
    assert tp_after["params"] == tp_before["params"]
    assert json.dumps(tp_after["targets"], sort_keys=True) == json.dumps(
        tp_before["targets"], sort_keys=True
    )
    assert tp_after["summary"] == tp_before["summary"]
