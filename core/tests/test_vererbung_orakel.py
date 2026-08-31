"""Reihen-Vererbung gegen den vollen Befund — Orakel an einer nicht-zu-dicken Wand.

Akzeptanz von Issue #174 (Repräsentanten-Wahl kollisionsehrlich, Befunde B10/B13/
B26/B36): das **geerbte** Reihen-Urteil (``presumed``) wird gegen den **vollen
Kollisionsbefund** je Zelle validiert — nicht nur die Prüf-Tür je Teil (das war das
16/16-Orakel von #162), sondern die Vererbung selbst.

Aufbau (Muster des 16/16-Orakels, aber **selbst-enthalten** statt Denkmal): eine
synthetische, **nicht-zu-dicke** Quaderwand (150 mm < D ≈ 181 mm ⇒ Freigang schweigt,
die teure Stufe 2 läuft wirklich) wird in **eine Höhenreihe mit drei Zellen** zerlegt.
Der Repräsentant ist die Zelle mit **maximaler Hindernislast** (zuletzt gedruckt =
meiste frühere Nachbarbänder als Hindernis), die übrigen erben ``presumed``. Dann wird
je Zelle der **volle Befund** gerechnet (``sectionsim.section_collision_finding``,
dieselbe Hindernis-Wahrheit ``earlier_parts``) und mit dem geerbten Urteil verglichen.

Das validiert den Kern von #174: die **hindernislastigste** Zelle als Repräsentant deckt
die Reihe in der **sicheren** Richtung. Die alte Wahl (hindernisärmste erste Zelle) hätte
hier die **freie** Zelle (ohne frühere Teile) gekürt und die zwei real kollidierenden
Zellen der Reihe fälschlich grün erben lassen (die S6-/B10-Falle auf Reihenebene).

**Ehrlich dokumentiert, nicht weggedefiniert:** jede Abweichung geerbt↔voll wird als
Testbefund ausgedruckt. Hart geprüft werden nur die **ehrlichen** Verträge — der
Repräsentant stimmt mit seinem eigenen vollen Befund überein, und **kein** geerbtes
Urteil ist grün, wo der volle Befund kollidiert (die gefährliche Richtung falsch-grün).
Abweichungen in die **sichere** Richtung (geerbt kollidiert, real frei) sind erwartet
und gewollt.

Langsam (echte VHACD-Distanzen je Zelle) ⇒ ``slow``: läuft nur mit ``-m slow``. Wird
übersprungen, wenn die Kollisions-Geometrie des Roboters fehlt.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

ROBOT = "doosan_m1013"
WALL_ID = "WALLAAAAAAAAAAAAAAAAAA"


def _build_project(tmp_path, install_walls, make_wall):
    """Projekt + Druckjob + 1-Reihe-3-Zellen-Zerlegung einer 150-mm-Wand (Produktivpfad)."""
    from fgc.pipeline import actions as A
    from fgc.project import load_project, project_dir_for

    # Nicht-zu-dicke Quaderwand (150 mm ⇒ Freigang schweigt, Stufe 2 läuft).
    install_walls(
        [make_wall(WALL_ID, length=1600.0, thickness=150.0, height=800.0, name="Vererbungswand")]
    )

    projects_dir, runs_dir = tmp_path / "projects", tmp_path / "runs"
    creation = A.create_project_from_ifc(
        "Vererbung", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    A.set_print_job(slug, WALL_ID, str(creation.overview_run_dir), projects_dir=projects_dir)
    A.reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    # Zwei vertikale Schnitte ⇒ genau eine Höhenreihe mit drei Zellen (unten, alle
    # erreichbar): die Vererbung ist damit real exerziert (zwei presumed je Reihe).
    A.propose_decomposition(
        slug, "src",
        cuts=[
            {"orientation": "vertical", "position_mm": -267.0},
            {"orientation": "vertical", "position_mm": 267.0},
        ],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    artifact = load_project(project_dir_for(slug, projects_dir=projects_dir))
    return A, artifact, artifact["print_jobs"][0]


def test_vererbung_matches_full_finding_on_nonthick_wall(
    tmp_path, install_walls, make_wall, capsys
):
    """Orakel: geerbtes Reihen-Urteil vs. voller Befund je Zelle (Issue #174)."""
    from fgc.decompose import evaluate
    from fgc.domain.process_params import job_orientation
    from fgc.pipeline import sectionsim as S

    A, artifact, job = _build_project(tmp_path, install_walls, make_wall)
    pc = S.placement_context_for_job(job)
    robot, tool, wall = pc.robot, pc.tool, pc.wall
    plan = A.plan_for_job(job, wall, robot, tool, strict_overrides=False).plan
    ori = job_orientation(job)
    statuses = evaluate(plan, robot, tool, lead_rad=ori.lead_rad, kipp_rad=ori.kipp_rad)

    freigang = A._freigang_finding(robot, tool, wall.thickness_mm)
    # Vorbedingung des Orakels: die Wand ist NICHT zu dick (sonst kürzt Stufe 1 ab und
    # es gäbe keine Vererbung zu prüfen).
    assert freigang is not None and freigang.too_thick is False

    sids = [sp.section.section_id for sp in plan.sections]
    assert len(sids) == 3  # eine Höhenreihe, drei Zellen

    # 1) Geerbtes Urteil je Zelle (die repräsentative Prüf-Tür + Vererbung): die
    # Politik-Tür ``assess_plan`` mit dem Produktiv-Orakel (Closure über sectionsim,
    # Issue #190) und frischem Cache (Signatur damit beliebig).
    from fgc.decompose.pruefung import PruefCache, assess_plan

    inherited, _stats, _samples = assess_plan(
        plan, statuses, freigang, frozenset(),
        lambda sid: S.clearance_verdict(artifact, job, plan, sid),
        signature=("vererbung",), cache=PruefCache(),
    )

    # 2) Voller Befund je Zelle (dieselbe Hindernis-Wahrheit earlier_parts).
    full_by_sid: dict[str, dict] = {}
    for sid in sids:
        ctx = S.section_sim_context(artifact, job, sid, plan=plan)
        comp = S.slice_and_simulate_section(artifact, job, sid, ctx=ctx)
        t0 = time.perf_counter()
        full = S.section_collision_finding(comp, config=None)
        if full is None:
            pytest.skip("Kollisions-Geometrie fehlt (kein voller Befund) — Orakel nicht anwendbar")
        full_by_sid[sid] = {
            "collides": full["n_red"] > 0, "n_red": full["n_red"],
            "n_earlier": len(comp.earlier_parts), "s": time.perf_counter() - t0,
        }

    # Repräsentant der (einen) Reihe: die Zelle mit maximaler Hindernislast in
    # Druckreihenfolge = die zuletzt gedruckte (abschnitt-3). Regel 1 auf echter Geometrie.
    rep = next(p for p in inherited.values() if not p.presumed)
    assert rep.section_id == sids[-1], "Repräsentant ist nicht die zuletzt gedruckte Zelle"

    # Abweichungen sammeln (Testbefund) + harte Ehrlichkeits-Verträge prüfen.
    deviations: list[str] = []
    false_green: list[str] = []
    for sid in sids:
        pr, full = inherited[sid], full_by_sid[sid]
        inherited_collides = pr.verdict == "collides"
        if inherited_collides != full["collides"]:
            deviations.append(
                f"{sid}: geerbt={'kollidiert' if inherited_collides else 'frei'} "
                f"(presumed={pr.presumed}) vs. voll={'kollidiert' if full['collides'] else 'frei'} "
                f"(n_red={full['n_red']}, n_earlier={full['n_earlier']})"
            )
        # Die GEFÄHRLICHE Richtung: ein grünes/druckbares Urteil, wo der volle Befund
        # kollidiert — genau das darf die kollisionsehrliche Wahl NICHT erzeugen.
        if pr.printable and full["collides"]:
            false_green.append(sid)

    with capsys.disabled():
        print("\n=== Vererbung vs. voller Befund (150-mm-Wand, 1 Reihe / 3 Zellen) ===")
        for sid in sids:
            pr, full = inherited[sid], full_by_sid[sid]
            print(
                f"{sid:<12} geerbt={pr.verdict:<9}presumed={str(pr.presumed):<6}"
                f"rep={pr.representative_id:<12}voll={'kollid.' if full['collides'] else 'frei':<8}"
                f"n_red={full['n_red']:<6}n_earlier={full['n_earlier']}  ({full['s']:.1f} s)"
            )
        print(f"Repräsentant der Reihe: {rep.section_id} (max Hindernislast, zuletzt gedruckt)")
        if deviations:
            print("Abweichungen geerbt↔voll (Testbefund, sichere Richtung erwartet):")
            for d in deviations:
                print(f"  - {d}")
        else:
            print("Keine Abweichung geerbt↔voll.")

    # Harter Vertrag 1: der Repräsentant stimmt mit seinem EIGENEN vollen Befund überein
    # (das per-Zelle-Orakel — er wurde ehrlich geprüft, nicht geerbt).
    assert (rep.verdict == "collides") == full_by_sid[rep.section_id]["collides"], (
        f"Repräsentant {rep.section_id}: geerbtes/geprüftes Urteil weicht vom vollen Befund ab"
    )
    # Harter Vertrag 2 (Kern von #174/B10/S6): KEIN geerbtes Grün, wo der volle Befund
    # kollidiert. Die alte Wahl (hindernisärmste Zelle) hätte hier genau das erzeugt.
    assert not false_green, (
        f"Falsch-grün trotz Kollision im vollen Befund: {false_green} — die "
        "Repräsentanten-Wahl deckt die Reihe NICHT in der sicheren Richtung"
    )
