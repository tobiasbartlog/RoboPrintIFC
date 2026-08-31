"""Die eine Persistier-Tür der Zerlegungs-Bewertung: ``_persist_decompose_run`` (#198).

Testet die Tür **selbst** (nicht nur indirekt über ihre zwei Aufrufer
``propose_decomposition``/``check_decomposition``): ein fertig berechnetes
:class:`DecomposeBundle` rein → decompose.json-Lauf (ADR-004) + Druckjob-Update
(ADR-016) raus, ohne dass die Tür irgendetwas neu rechnet. Dazu die beiden
Vertragskanten, die den früheren Seitenkanal ablösen: ``last_pruef=None`` (der
interaktive Stufe-1-Aufrufer) lässt den Prüfstand unberührt, ``last_pruef``
gesetzt (Stufe-2-Aufrufer) schreibt den Marker samt Eingabe-Schnappschuss —
kein Paar-Kontrakt mehr. Und die ADR-018-Kante: die Tür nimmt den reentranten
``project_lock`` selbst, auch wenn der Aufrufer ihn bereits hält (Phase 3 von
``check_decomposition``) — kein Selbst-Deadlock.

Das Bündel wird aus reinen Plan-/Status-Objekten gebaut (kein IK-Sampling, keine
Platzierungssuche) — genau die Zusicherung der Tür: sie persistiert nur.
"""

from __future__ import annotations

import json

import pytest

# Voller Projekt-Aufbau aus der Zerlegungs-Suite (eine Wand, ein Druckjob).
from test_decompose import _project_with_job

from fgc import domain
from fgc.decompose import DecompositionPlan, ModuleLimits, Section, SectionPlan
from fgc.decompose.evaluate import SectionStatus
from fgc.decompose.printability import REASON_UNCHECKED, VERDICT_UNKNOWN
from fgc.decompose.pruefung import assess_plan
from fgc.pipeline import actions
from fgc.placement import PlacementOption, WallSurface
from fgc.project import load_project, project_dir_for, project_lock

ROBOT = "doosan_m1013"


@pytest.fixture
def stub_walls(install_walls, make_wall):
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", height=2600.0)])


def _two_part_plan() -> DecompositionPlan:
    wall = WallSurface(length_mm=800.0, height_mm=1600.0, thickness_mm=200.0)
    low = SectionPlan(
        Section("abschnitt-1", 1, -400.0, 400.0, 0.0, 800.0),
        PlacementOption("platz-1", 0.0, 700.0, 0.0),
    )
    high = SectionPlan(
        Section("abschnitt-2", 2, -400.0, 400.0, 800.0, 1600.0),
        PlacementOption("platz-2", 0.0, 700.0, 0.0),
    )
    return DecompositionPlan("abschnitt", wall, (), (low, high), 1, 2)


def _status(sid: str, order: int) -> SectionStatus:
    return SectionStatus(
        section_id=sid, order=order, reachable=True, reachable_fraction=1.0,
        n_samples=100, n_reachable=100, kinematic_margin=0.3, mean_margin=0.3,
    )


def _bundle(plan: DecompositionPlan) -> actions.DecomposeBundle:
    """Fertig berechnetes Bewertungs-Bündel aus **reinen** Objekten (kein Rechnen)."""
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    printability, _stats, _samples = assess_plan(plan, statuses, None, frozenset(), None)
    return actions.DecomposeBundle(
        robot_name=ROBOT,
        tool_name="(kein)",  # Default aus placement_context_for_job ohne Endeffektor
        wall_global_id="WALLAAAAAAAAAAAAAAAAAA",
        plan=plan,
        statuses=statuses,
        module_limits=ModuleLimits.from_dict(None),
        module_checks=None,
        placement_checks=None,
        module_poses=None,
        freigang=None,
        printability=printability,
        pruef_scope={"n_representatives": 2, "n_parts": 2, "est_seconds": 20.0},
    )


def test_persist_writes_run_and_job_without_last_pruef(tmp_path, stub_walls):
    """Stufe-1-Kante (Aufrufer ``propose_decomposition``): das Bündel landet als
    schema-valider Lauf + Druckjob-Update; ``last_pruef=None`` lässt den Prüfstand
    unberührt (kein Marker). Die Tür rechnet nichts — alles kommt aus dem Bündle."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    plan = _two_part_plan()

    result = actions._persist_decompose_run(
        slug, project_dir, "src", "default", _bundle(plan), None,
        runs_dir=runs_dir, last_pruef=None,
    )

    # Lauf: decompose.json vorhanden, schema-valide, trägt das Bündel verbatim.
    artifact = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")
    assert artifact["robot"] == ROBOT
    assert artifact["wall_global_id"] == "WALLAAAAAAAAAAAAAAAAAA"
    assert [s["section_id"] for s in artifact["sections"]] == ["abschnitt-1", "abschnitt-2"]

    # Druckjob: Plan-Eingaben + Lauf-Verweis (ADR-016), kein last_pruef-Marker.
    job = result.artifact["print_jobs"][0]
    assert job["decomposition_kind"] == "abschnitt"
    assert job["decompose_run"] == str(result.run_dir.resolve())
    assert str(result.run_dir.resolve()) in job["runs"]
    assert "last_pruef" not in job
    domain.validate(result.artifact, "project")

    # Ergebnis: Sektionen + Durchreichungen (printability Stufe 1, pruef_scope).
    assert result.decomposition_kind == "abschnitt"
    assert result.pruef_scope == {"n_representatives": 2, "n_parts": 2, "est_seconds": 20.0}
    for s in result.sections:
        assert s["printability"]["verdict"] == VERDICT_UNKNOWN
        assert s["printability"]["reason"] == REASON_UNCHECKED

    # Persistiert: der neu geladene Stand entspricht dem zurückgegebenen Artefakt.
    assert load_project(project_dir)["print_jobs"][0] == job


def test_persist_last_pruef_sets_marker_with_snapshot(tmp_path, stub_walls):
    """Stufe-2-Kante (Aufrufer ``check_decomposition`` Phase 3): ``last_pruef``
    schreibt den Marker (scope/section_id) samt Eingabe-Schnappschuss — ohne den
    früheren Paar-Kontrakt (kein zweiter Parameter nötig, #198)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    project_dir = project_dir_for(slug, projects_dir=projects_dir)

    result = actions._persist_decompose_run(
        slug, project_dir, "src", "default", _bundle(_two_part_plan()), None,
        runs_dir=runs_dir, last_pruef={"scope": "focus", "section_id": "abschnitt-1"},
    )

    job = result.artifact["print_jobs"][0]
    assert job["last_pruef"]["scope"] == "focus"
    assert job["last_pruef"]["section_id"] == "abschnitt-1"
    assert job["last_pruef"]["input_snapshot"]  # Schnappschuss für die Veraltung
    domain.validate(result.artifact, "project")


def test_persist_missing_job_raises(tmp_path, stub_walls):
    """Verschwindet der Druckjob zwischen Rechnung und Persistierung, wirft die Tür
    (freundlicher ValueError) statt still einen Waisen-Lauf zu verdrahten."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    project_dir = project_dir_for(slug, projects_dir=projects_dir)

    with pytest.raises(ValueError, match="existiert nicht"):
        actions._persist_decompose_run(
            slug, project_dir, "src", "gibts-nicht", _bundle(_two_part_plan()), None,
            runs_dir=runs_dir,
        )


def test_persist_is_reentrant_under_held_lock(tmp_path, stub_walls):
    """ADR-018-Kante: der Stufe-2-Aufrufer hält den Projekt-Lock über seine
    Supersede-Sektion — die Tür (re-)nimmt denselben reentranten Lock ohne
    Selbst-Deadlock und schreibt atomar."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    project_dir = project_dir_for(slug, projects_dir=projects_dir)

    with project_lock(project_dir):  # wie check_decomposition Phase 3
        result = actions._persist_decompose_run(
            slug, project_dir, "src", "default", _bundle(_two_part_plan()), None,
            runs_dir=runs_dir, last_pruef={"scope": "global", "section_id": None},
        )

    job = load_project(project_dir)["print_jobs"][0]
    assert job["last_pruef"]["scope"] == "global"
    assert job["decompose_run"] == str(result.run_dir.resolve())
