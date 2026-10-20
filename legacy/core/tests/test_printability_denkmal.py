"""Druckbarkeit als Lauf-Eigenschaft — Akzeptanz auf dem realen Denkmal (Issue #164).

Zwei Beweise am echten Denkmal (Karte #139, Entscheidung #141, Scheibe 3);
die Modulzahl haengt an den lebenden Projektdaten und wird darum aus dem Plan
abgeleitet, nicht gepinnt (urspruenglich 16, Drift dokumentiert im Stufe-1-Test):

- **Stufe 1 (gratis, das luegende „n/n ✓" faellt):** ein frischer
  ``propose_decomposition``-Lauf traegt fuer **alle Module** rot + Ursache
  („Wand zu dick", Ueberschuss), **ohne vorherige Simulation** — die Wand ist nach
  dem Freigang-Kriterium (#163) zu dick, die teure Pruef-Tuer entfaellt. Schnell.
- **Stufe 2 (teuer, `slow`):** wird die Stufe-1-Abkuerzung umgangen (Freigang=None),
  prueft die repraesentative Pruef-Tuer je Hoehenreihe nur die unguenstigste Zelle
  und die uebrigen erben das Urteil als ``presumed`` — alle rot mit Verursacher-
  Glied + Eindringtiefe, je Reihe eine geprueft, der Rest vermutlich. Das beweist
  die Reihen-Vererbung + den ``SectionSimContext``-Reuse auf echter Geometrie.

Wird uebersprungen, wenn das reale Projekt „denkmal" fehlt.
"""

from __future__ import annotations

import json

import pytest

from fgc import domain
from fgc.paths import PROJECTS_DIR

DENKMAL = PROJECTS_DIR / "denkmal" / "project.json"


def _denkmal_context():
    from fgc.decompose import evaluate
    from fgc.domain.process_params import job_orientation
    from fgc.pipeline import actions as A
    from fgc.project import load_project, project_dir_for

    artifact = load_project(project_dir_for("denkmal"))
    job = artifact["print_jobs"][0]
    pc = A.placement_context_for_job(job)
    robot, tool = pc.robot, pc.tool
    plan = A.plan_for_job(job, pc.wall, robot, tool, strict_overrides=False).plan
    ori = job_orientation(job)
    statuses = evaluate(plan, robot, tool, lead_rad=ori.lead_rad, kipp_rad=ori.kipp_rad)
    return A, artifact, job, robot, tool, plan, statuses


def test_denkmal_decompose_marks_all_modules_red_too_thick(tmp_path):
    """Akzeptanz Stufe 1: der frische Zerlegungslauf traegt fuer ALLE Module rot
    (``too_thick``) + Ursache (Ueberschuss) — ohne Simulation, schema-valide.

    Die Modulzahl wird bewusst NICHT gepinnt (frueher 16): sie haengt an den
    lebenden Projektdaten (``module_limits``, Platzierung) und driftete bereits
    vor der Abstand-Semantik-Umstellung (Issue #160) auf 18. Das Orakel dieses
    Tests ist das Urteil (alle rot, Ursache Dicke), nicht die Teilungszahl."""
    if not DENKMAL.exists():
        pytest.skip("Reales Projekt 'denkmal' nicht vorhanden")

    from fgc.pipeline import actions as A

    result = A.propose_decomposition(
        "denkmal", "test-164-stufe1", kind="modul", runs_dir=tmp_path / "runs",
    )
    assert result.decomposition_kind == "modul"
    assert len(result.sections) >= 16  # 510-mm-Denkmalwand: viele kleine Module

    artifact = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")
    assert artifact["freigang"]["too_thick"] is True

    for s in artifact["sections"]:
        pr = s["printability"]
        assert pr["verdict"] == "too_thick"       # rot
        assert pr["presumed"] is True             # #177: vermutlich (höhenblind, #167)
        assert pr["excess_mm"] > 0                # Ursache: Dicken-Ueberschuss
        # 30gut traegt einen realen TCP ⇒ nicht provisorisch (Feld fehlt).
        assert "tcp_provisional" not in pr
    # Und in der API-Antwort ebenso (der Viewer sieht es ohne Nachladen).
    assert all(s["printability"]["verdict"] == "too_thick" for s in result.sections)


@pytest.mark.slow
def test_denkmal_representative_pruef_tuer_inherits_row_verdict(tmp_path):
    """Stufe 2 (`slow`): Freigang umgangen ⇒ repraesentative Pruef-Tuer je Reihe.
    Alle Module rot (``collides``) mit Verursacher-Glied + Eindringtiefe; je
    Hoehenreihe genau eine geprueft, die uebrigen ``presumed`` (,vermutlich').
    Zahlen werden aus dem lebenden Plan abgeleitet (siehe Stufe-1-Test)."""
    if not DENKMAL.exists():
        pytest.skip("Reales Projekt 'denkmal' nicht vorhanden")

    from fgc.decompose.pruefung import PruefCache, assess_plan
    from fgc.pipeline.sectionsim import clearance_verdict

    A, artifact, job, _robot, _tool, plan, statuses = _denkmal_context()

    # freigang=None: erzwingt die teure Stufe 2 (sonst kuerzt „zu dick" sie ab).
    # Produktiv-Orakel (Closure ueber sectionsim, Issue #190) + frischer Cache je
    # Aufruf (Signatur damit beliebig) — jede Hoehenreihe wird wirklich gerechnet.
    printability, _stats, _samples = assess_plan(
        plan, statuses, None, frozenset(),
        lambda sid: clearance_verdict(artifact, job, plan, sid),
        signature=("denkmal",), cache=PruefCache(),
    )

    n_parts = len(plan.sections)
    n_rows = len({sp.section.z0_mm for sp in plan.sections})
    assert len(printability) == n_parts
    assert all(p.verdict == "collides" for p in printability.values())
    checked = [p for p in printability.values() if not p.presumed]
    presumed = [p for p in printability.values() if p.presumed]
    # Je Hoehenreihe genau ein geprueftes Modul, der Rest erbt.
    assert len(checked) == n_rows and len(presumed) == n_parts - n_rows
    # Die geprueften tragen die Ursache aus der Pruef-Tuer (Verursacher + Tiefe).
    for p in checked:
        assert p.causer_link is not None
        assert p.penetration_mm is not None and p.penetration_mm > 0
        assert p.representative_id == p.section_id
    # Die erbenden zeigen auf ihren geprueften Repraesentanten (,vermutlich').
    for p in presumed:
        assert p.representative_id in {c.section_id for c in checked}
