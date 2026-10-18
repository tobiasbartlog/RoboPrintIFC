"""Export-Reiter (DRL je Abschnitt) + veraltet-Markierung (Issue #29).

Deckt die Akzeptanzkriterien ab:
- **DRL je Abschnitt als Lauf-Artefakt** (`export_section_drl`): mit gemessenem
  Setup im Lauf → vollständiges DRL (movej + Provenienz); ohne Setup → sichtbar
  gekennzeichneter Antasten-Hinweis statt eines unmarkiert unvollständigen
  Programms (kein Gate, ADR-006).
- **veraltet-Markierung** (Revisionsstände in `fgc.project`): Roboterwechsel
  bumpt die Eingabe-Revision → Druckplan/Simulation/Export veralten; die
  Neuerzeugung der jeweiligen Stufe hebt die Markierung stufenweise auf;
  Altprojekte ohne Revisionsfeld gelten als nicht veraltet.

Fixtures folgen dem Muster aus test_section_simulation (Stub-Wände, Verzeichnis-
Seams) — kein IFC/ifcopenshell nötig.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fgc.pipeline import runfolder
from fgc.pipeline.actions import (
    create_project_from_ifc,
    export_section_drl,
    propose_decomposition,
    reassess_walls_for_robot,
    set_print_job,
    simulate_section,
)
from fgc.pipeline.api import app
from fgc.pipeline.provenance import make_provenance
from fgc.project import (
    bump_input,
    bump_section_input,
    default_revisions,
    output_status,
    refresh_output,
    refresh_section_output,
    section_output_status,
)
from fgc.project import store as project_store

ROBOT = "doosan_m1013"
WALL_ID = "WALLAAAAAAAAAAAAAAAAAA"


# --- veraltet-Markierung: reine Revisionsstände (fgc.project.revisions) --------


def test_default_revisions_all_inputs_zero_no_outputs():
    rev = default_revisions()
    assert rev["inputs"] == {
        "wall": 0, "robot": 0, "tool": 0, "cutplan": 0, "process": 0, "workstation": 0,
    }
    assert rev["outputs"] == {}
    # Die Pro-Abschnitts-Ebene (Issue #83) entsteht erst lazy — hier noch nicht da.
    assert "section_inputs" not in rev and "section_outputs" not in rev


def test_project_without_revisions_is_not_stale():
    """Altprojekt ohne Revisionsfeld: nichts gilt als veraltet (rückwärtskompatibel)."""
    job: dict = {"job_id": "default", "wall_global_id": WALL_ID}
    assert output_status(job) == {
        "druckplan": "current",
        "simulation": "current",
        "export": "current",
    }


def test_output_missing_until_generated_then_current():
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    # Noch kein Output erzeugt → „missing" (nicht „stale").
    assert output_status(job)["druckplan"] == "missing"
    job = refresh_output(job, "druckplan")
    assert output_status(job)["druckplan"] == "current"


def test_robot_bump_marks_all_downstream_stale_and_stagewise_clearing():
    """Roboterwechsel → alle Stufen veraltet; Neuerzeugung hebt stufenweise auf."""
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    # Alle drei Stufen einmal erzeugt → aktuell.
    for out in ("druckplan", "simulation", "export"):
        job = refresh_output(job, out)
    assert set(output_status(job).values()) == {"current"}

    # Roboterwechsel: bump robot → alle drei veraltet (nichts gelöscht).
    job = bump_input(job, "robot")
    assert output_status(job) == {
        "druckplan": "stale",
        "simulation": "stale",
        "export": "stale",
    }

    # Stufenweise aufheben: Druckplan zuerst.
    job = refresh_output(job, "druckplan")
    st = output_status(job)
    assert st["druckplan"] == "current"
    assert st["simulation"] == "stale" and st["export"] == "stale"

    # Dann Simulation.
    job = refresh_output(job, "simulation")
    st = output_status(job)
    assert st["simulation"] == "current" and st["export"] == "stale"

    # Zuletzt Export.
    job = refresh_output(job, "export")
    assert set(output_status(job).values()) == {"current"}


def test_cutplan_bump_leaves_druckplan_but_stales_sim_and_export():
    """Schnittplan-Änderung veraltet Simulation/Export, nicht den Druckplan."""
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    for out in ("druckplan", "simulation", "export"):
        job = refresh_output(job, out)
    job = bump_input(job, "cutplan")
    st = output_status(job)
    assert st["druckplan"] == "current"  # Druckplan hängt nicht am cutplan
    assert st["simulation"] == "stale" and st["export"] == "stale"


def test_process_bump_stales_all_downstream():
    """Prozessparameter-Änderung veraltet Zerlegung/Simulation/Export (Issue #59).

    Parität zur TS-Ableitung (`ui/staleness.ts`): `process` ist Dependency aller
    drei Outputs (Slice-Parameter fließen überall ein).
    """
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    for out in ("druckplan", "simulation", "export"):
        job = refresh_output(job, out)
    assert set(output_status(job).values()) == {"current"}

    job = bump_input(job, "process")
    assert output_status(job) == {
        "druckplan": "stale", "simulation": "stale", "export": "stale",
    }
    # Stufenweises Auffrischen hebt die Markierung auf.
    job = refresh_output(job, "druckplan")
    assert output_status(job)["druckplan"] == "current"
    assert output_status(job)["simulation"] == "stale"


def test_default_revisions_includes_process_input():
    """Die process-Eingabe ist Teil der frischen Revisionsstände (Issue #59)."""
    assert default_revisions()["inputs"]["process"] == 0


def test_bump_unknown_input_raises():
    with pytest.raises(ValueError, match="Eingabe-Stufe"):
        bump_input({"job_id": "x", "wall_global_id": WALL_ID}, "nope")


def test_workstation_now_a_valid_input_key():
    """Issue #83: 'workstation' ist jetzt eine gültige Eingabe-Stufe (Ablösung #77-Seam)."""
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    for out in ("druckplan", "simulation", "export"):
        job = refresh_output(job, out)
    job = bump_input(job, "workstation")
    assert output_status(job) == {
        "druckplan": "stale", "simulation": "stale", "export": "stale",
    }


# --- Pro-Abschnitts-Veraltung: feingranulare Revisionen (Issue #83) ------------


def _job_with_section_layer(section_ids=("abschnitt-1", "abschnitt-2")):
    """Ein Job, dessen Abschnitte alle einmal simuliert+exportiert wurden (alle current)."""
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    for sid in section_ids:
        job = refresh_section_output(job, sid, "simulation")
        job = refresh_section_output(job, sid, "export")
    return job


def test_section_override_stales_only_that_section():
    """Ein Abschnitts-Override veraltet NUR diesen Abschnitt; Nachbarn bleiben aktuell."""
    job = _job_with_section_layer()
    assert section_output_status(job, "abschnitt-1") == {
        "simulation": "current", "export": "current",
    }

    # Override von abschnitt-1 → nur dessen Zähler bumpt.
    job = bump_section_input(job, "abschnitt-1")
    assert section_output_status(job, "abschnitt-1") == {
        "simulation": "stale", "export": "stale",
    }
    assert section_output_status(job, "abschnitt-2") == {
        "simulation": "current", "export": "current",
    }

    # abschnitt-1 neu simuliert+exportiert → wieder aktuell, Nachbar unberührt.
    job = refresh_section_output(job, "abschnitt-1", "simulation")
    job = refresh_section_output(job, "abschnitt-1", "export")
    assert section_output_status(job, "abschnitt-1") == {
        "simulation": "current", "export": "current",
    }


def test_section_override_stales_druckplan_at_source():
    """Issue #172 (Wurzel-Fix #161, Befunde B16/B32): ein Abschnitts-/Platzierungs-
    Override veraltet den GANZEN Druckplan-Output — an der Quelle (Revisionsmechanik),
    nicht pro Leser. Ein erneuter Zerlegungslauf (refresh_output) hebt es wieder auf."""
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    job = refresh_output(job, "druckplan")
    assert output_status(job)["druckplan"] == "current"

    # Platzierungs-/Abschnitts-Override → Abschnitts-Zähler steigt → Druckplan veraltet.
    job = bump_section_input(job, "abschnitt-1")
    assert output_status(job)["druckplan"] == "stale"

    # Ein zweiter Override eines ANDEREN Teils hält den Druckplan veraltet (Summe steigt).
    job = bump_section_input(job, "abschnitt-2")
    assert output_status(job)["druckplan"] == "stale"

    # Neuer Zerlegungslauf schnappt die aktuelle Abschnitts-Summe → wieder aktuell.
    job = refresh_output(job, "druckplan")
    assert output_status(job)["druckplan"] == "current"

    # Und der nächste Override veraltet erneut (Schnappschuss ist frisch, nicht taub).
    job = bump_section_input(job, "abschnitt-1")
    assert output_status(job)["druckplan"] == "stale"


def test_druckplan_snapshot_byte_equal_without_section_overrides():
    """Byte-Gleichheit (Issue #172): ohne je gesetzten Abschnitts-Override trägt der
    Druckplan-Schnappschuss KEIN section_total — Altprojekte bleiben unverändert."""
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    job = refresh_output(job, "druckplan")
    snap = job["revisions"]["outputs"]["druckplan"]
    assert "section_total" not in snap
    assert output_status(job)["druckplan"] == "current"


def test_global_and_structural_change_stales_all_sections():
    """Strukturell/global (cutplan, process, robot, workstation) veraltet ALLE Abschnitte."""
    for job_input in ("cutplan", "process", "robot", "workstation"):
        job = _job_with_section_layer()
        job = bump_input(job, job_input)
        for sid in ("abschnitt-1", "abschnitt-2"):
            assert section_output_status(job, sid) == {
                "simulation": "stale", "export": "stale",
            }, f"{job_input} muss {sid} veralten"


def test_old_job_without_section_layer_behaves_like_before():
    """Altprojekt ohne Pro-Abschnitts-Ebene: Ganzjob-Veraltung wie bisher."""
    # revisions vorhanden, aber KEIN section_outputs (Legacy): folgt output_status.
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    for out in ("druckplan", "simulation", "export"):
        job = refresh_output(job, out)
    assert "section_outputs" not in job["revisions"]
    whole = output_status(job)
    for sid in ("abschnitt-1", "abschnitt-2"):
        st = section_output_status(job, sid)
        assert st == {"simulation": whole["simulation"], "export": whole["export"]}

    # Roboterwechsel veraltet (Ganzjob) → jeder Abschnitt gilt als veraltet.
    job = bump_input(job, "robot")
    for sid in ("abschnitt-1", "abschnitt-2"):
        assert section_output_status(job, sid) == {
            "simulation": "stale", "export": "stale",
        }


def test_project_without_revisions_section_status_current():
    """Sehr altes Projekt ohne revisions-Feld: nichts veraltet (rückwärtskompatibel)."""
    job = {"job_id": "default", "wall_global_id": WALL_ID}
    assert section_output_status(job, "abschnitt-1") == {
        "simulation": "current", "export": "current",
    }


def test_section_status_missing_until_generated():
    """Ein Abschnitt ohne eigenen Schnappschuss ist 'missing', nach Erzeugung 'current'."""
    job = {"job_id": "default", "wall_global_id": WALL_ID, "revisions": default_revisions()}
    # Nachbar simuliert → Pro-Abschnitts-Ebene existiert, aber abschnitt-2 noch nicht.
    job = refresh_section_output(job, "abschnitt-1", "simulation")
    assert section_output_status(job, "abschnitt-2")["simulation"] == "missing"
    assert section_output_status(job, "abschnitt-1")["simulation"] == "current"


# Die Py↔TS-Parität (geteilte Golden-Fälle ``staleness-section.golden.json``)
# prüft das Paritäts-Manifest: ``test_parity.py::test_golden[staleness-section]``.


# --- Integration: Aktionen setzen die Revisionen (fgc.project einzige Stelle) --


@pytest.fixture
def stub_walls(install_walls, make_wall):
    return install_walls([make_wall(WALL_ID, length=800.0, height=2600.0)])


def _project_with_section_run(tmp_path):
    """Projekt mit Wand, Roboter, Zerlegung und einem simulierten Abschnitt."""
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, WALL_ID, str(creation.overview_run_dir), projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    decomp = propose_decomposition(
        slug, "src", cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    section_id = decomp.sections[0]["section_id"]
    sim = simulate_section(slug, section_id, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    return slug, projects_dir, runs_dir, section_id, sim


def test_actions_set_revisions_robot_change_stales_downstream(tmp_path, stub_walls):
    """Nach set_print_job/reassess/decompose/simulate sind die Stufen aktuell;
    ein Roboterwechsel veraltet Druckplan/Simulation/Export (Issue #29)."""
    slug, projects_dir, runs_dir, section_id, sim = _project_with_section_run(tmp_path)
    export_section_drl(slug, section_id, "src", projects_dir=projects_dir)

    from fgc.project import load_project, project_dir_for

    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    assert output_status(job) == {
        "druckplan": "current",
        "simulation": "current",
        "export": "current",
    }

    # Roboterwechsel (auf denselben Roboter genügt fürs bump) → alles veraltet.
    reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    assert output_status(job) == {
        "druckplan": "stale",
        "simulation": "stale",
        "export": "stale",
    }


def test_set_process_params_section_override_stales_only_that_section(tmp_path, stub_walls):
    """Integration (Issue #83): ein Abschnitts-Override über set_process_params veraltet
    nur diesen Abschnitt; eine globale Änderung veraltet alle."""
    from fgc.pipeline.actions import set_process_params
    from fgc.project import load_project, project_dir_for

    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, WALL_ID, str(creation.overview_run_dir), projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    decomp = propose_decomposition(
        slug, "src", cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    sid_a = decomp.sections[0]["section_id"]
    sid_b = decomp.sections[1]["section_id"]
    for sid in (sid_a, sid_b):
        simulate_section(slug, sid, "src", projects_dir=projects_dir, runs_dir=runs_dir)

    def job_now():
        return load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]

    # Beide Abschnitte aktuell.
    assert section_output_status(job_now(), sid_a)["simulation"] == "current"
    assert section_output_status(job_now(), sid_b)["simulation"] == "current"

    # Abschnitts-Override für A → nur A veraltet, B bleibt aktuell.
    set_process_params(
        slug, {}, projects_dir=projects_dir,
        sections={sid_a: {"slice": {"layer_height_mm": 7.0}}},
    )
    assert section_output_status(job_now(), sid_a)["simulation"] == "stale"
    assert section_output_status(job_now(), sid_b)["simulation"] == "current"
    # Die PER-ABSCHNITT-Stufen veralten nur für A (Nachbar B aktuell). Der DRUCKPLAN
    # ist hingegen der ganze Plan und veraltet bei JEDEM Abschnitts-Override (Issue
    # #172, Wurzel-Fix #161/B16/B32) — der Zerlegungslauf trägt danach einen
    # überholten Abschnitts-Parameter.
    assert output_status(job_now())["druckplan"] == "stale"

    # Globale Änderung → beide Abschnitte veralten.
    set_process_params(slug, {"layer_height_mm": 9.0}, projects_dir=projects_dir)
    assert section_output_status(job_now(), sid_a)["simulation"] == "stale"
    assert section_output_status(job_now(), sid_b)["simulation"] == "stale"


def test_set_process_params_ik_config_section_override_stales_only_that_section(
    tmp_path, stub_walls
):
    """Wählbare IK-Konfiguration (Issue #129): ein ik_config-Abschnitts-Override
    veraltet nur diesen Abschnitt (#83); eine globale ik_config-Änderung alle."""
    from fgc.pipeline.actions import set_process_params
    from fgc.project import load_project, project_dir_for

    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, WALL_ID, str(creation.overview_run_dir), projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    decomp = propose_decomposition(
        slug, "src", cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    sid_a = decomp.sections[0]["section_id"]
    sid_b = decomp.sections[1]["section_id"]
    for sid in (sid_a, sid_b):
        simulate_section(slug, sid, "src", projects_dir=projects_dir, runs_dir=runs_dir)

    def job_now():
        return load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]

    assert section_output_status(job_now(), sid_a)["simulation"] == "current"
    assert section_output_status(job_now(), sid_b)["simulation"] == "current"

    # IK-Konfig-Override nur für A (Ellbogen Zustand B) → nur A veraltet.
    set_process_params(
        slug, {}, projects_dir=projects_dir,
        sections={sid_a: {"ik_config": {"elbow": "b"}}},
    )
    job = job_now()
    assert job["process_params"]["sections"][sid_a] == {"ik_config": {"elbow": "b"}}
    assert section_output_status(job, sid_a)["simulation"] == "stale"
    assert section_output_status(job, sid_b)["simulation"] == "current"
    # Druckplan (ganzer Plan) veraltet bei jedem Abschnitts-Override (Issue #172).
    assert output_status(job)["druckplan"] == "stale"

    # Globale ik_config-Änderung → process bumpt → beide veralten.
    set_process_params(slug, {}, ik_config={"shoulder": "a"}, projects_dir=projects_dir)
    job = job_now()
    assert job["process_params"]["ik_config"] == {"shoulder": "a"}
    assert section_output_status(job, sid_a)["simulation"] == "stale"
    assert section_output_status(job, sid_b)["simulation"] == "stale"


def test_placement_override_stales_only_that_section_including_recheck(
    tmp_path, stub_walls
):
    """End-to-end (Issue #94, #83-Mechanik): ein freier Platzierungs-Override
    veraltet nur das betroffene Teil — auch nach der Neubewertung des
    unveränderten Schnittplans (die der Viewer nach dem Setzen anstößt)."""
    from fgc.pipeline.actions import set_placement_override_for_job

    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, WALL_ID, str(creation.overview_run_dir), projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    cuts = [{"orientation": "horizontal", "position_mm": 1300.0}]
    decomp = propose_decomposition(
        slug, "src", cuts=cuts, projects_dir=projects_dir, runs_dir=runs_dir,
    )
    sid_a = decomp.sections[0]["section_id"]
    sid_b = decomp.sections[1]["section_id"]
    for sid in (sid_a, sid_b):
        simulate_section(slug, sid, "src", projects_dir=projects_dir, runs_dir=runs_dir)

    from fgc.project import load_project, project_dir_for

    def job_now():
        return load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]

    assert section_output_status(job_now(), sid_a)["simulation"] == "current"
    assert section_output_status(job_now(), sid_b)["simulation"] == "current"

    # Freier Platzierungs-Override für A → nur A veraltet (Setter, #83-Mechanik).
    set_placement_override_for_job(slug, sid_a, standoff_mm=950.0, projects_dir=projects_dir)
    assert section_output_status(job_now(), sid_a)["simulation"] == "stale"
    assert section_output_status(job_now(), sid_b)["simulation"] == "current"

    # Neubewertung des UNVERÄNDERTEN Schnittplans (wie der Viewer sie nach dem
    # Setzen anstößt): kein cutplan-Bump — der Nachbar bleibt aktuell.
    job = job_now()
    propose_decomposition(
        slug, "src", cuts=job["cuts"], section_overrides=job["section_overrides"],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert section_output_status(job_now(), sid_a)["simulation"] == "stale"
    assert section_output_status(job_now(), sid_b)["simulation"] == "current"

    # A neu simuliert → wieder aktuell; eine STRUKTURELLE Änderung (Schnitt
    # verschoben) veraltet danach beide (cutplan-Bump wie bisher).
    simulate_section(slug, sid_a, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    assert section_output_status(job_now(), sid_a)["simulation"] == "current"
    propose_decomposition(
        slug, "src", cuts=[{"orientation": "horizontal", "position_mm": 900.0}],
        section_overrides=job["section_overrides"],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert section_output_status(job_now(), sid_a)["simulation"] == "stale"
    assert section_output_status(job_now(), sid_b)["simulation"] == "stale"


# --- Export-Aktion: DRL je Abschnitt, mit/ohne Setup ---------------------------


def test_export_without_setup_writes_marked_antasten_hint(tmp_path, stub_walls):
    slug, projects_dir, runs_dir, section_id, sim = _project_with_section_run(tmp_path)

    result = export_section_drl(slug, section_id, "src", projects_dir=projects_dir)

    assert result.complete is False
    assert result.setup_source == "none"
    assert "Antasten" in result.note
    # program.drl liegt im Abschnitts-Lauf und ist sichtbar gekennzeichnet.
    assert result.drl_path.exists()
    text = result.drl_path.read_text(encoding="utf-8")
    assert "UNVOLLSTÄNDIG" in text and "ANTASTEN FEHLT" in text
    assert "movej" not in text and "movel" not in text  # kein lauffähiges Programm
    # Export-Revision aufgefrischt (veraltet-Markierung, Issue #29).
    job = result.artifact["print_jobs"][0]
    assert output_status(job)["export"] == "current"


def _write_measured_setup(run_dir: Path) -> None:
    """Schreibt ein gemessenes Setup (Kanal-Mapping, ADR-011) in den Abschnitts-Lauf.

    Die io_channels werden aus den tatsächlich in der trajectory.json vorkommenden
    logischen Kanälen gebaut (mit passendem logical_range), damit `emit_drl` jeden
    Kanal mappen kann. Kommen keine Kanäle vor, genügt ein Dummy (minProperties 1).
    """
    from fgc import domain

    trajectory = json.loads((run_dir / "trajectory.json").read_text(encoding="utf-8"))
    values: dict[str, list[float]] = {}
    for s in trajectory["samples"]:
        for ch, v in s.get("io", {}).items():
            values.setdefault(ch, []).append(float(v))

    io_channels: dict[str, dict] = {}
    for idx, (ch, vals) in enumerate(values.items()):
        lo = min([*vals, 0.0])
        hi = max([*vals, 1.0])
        io_channels[ch] = {
            "kind": "analog_voltage",
            "index": idx,
            "physical_range": [0.0, 10.0],
            "logical_range": [lo, hi],
        }
    if not io_channels:
        io_channels["dummy"] = {
            "kind": "digital",
            "index": 0,
            "physical_range": [0.0, 1.0],
        }

    setup = {
        "schema_version": "0.1",
        "provenance": make_provenance("test measured setup"),
        "robot": ROBOT,
        "wall_to_base": {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "tcp": {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "io_channels": io_channels,
        "deadtime": {"t_tot_s": 0.0, "compensation": "none"},
    }
    domain.validate(setup, "setup")
    (run_dir / "setup.json").write_text(json.dumps(setup), encoding="utf-8")


def test_export_with_measured_setup_writes_full_drl(tmp_path, stub_walls):
    slug, projects_dir, runs_dir, section_id, sim = _project_with_section_run(tmp_path)
    _write_measured_setup(sim.run_dir)

    result = export_section_drl(slug, section_id, "src", projects_dir=projects_dir)

    assert result.complete is True
    assert result.setup_source == "measured"
    assert result.note == ""
    text = result.drl_path.read_text(encoding="utf-8")
    # Vollständiges Bewegungsprogramm: per Target movel (Druck) / movej (Travel).
    assert "movel(" in text or "movej(" in text
    assert "UNVOLLSTÄNDIG" not in text
    assert output_status(result.artifact["print_jobs"][0])["export"] == "current"


def test_export_without_section_run_raises(tmp_path, stub_walls):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, WALL_ID, str(creation.overview_run_dir), projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    with pytest.raises(ValueError, match="Abschnitts-Lauf"):
        export_section_drl(slug, "abschnitt-1", "src", projects_dir=projects_dir)


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


def _api_project_with_section(client, tmp_path):
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post("/projects", json={"name": "H", "model_path": str(model)}).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": WALL_ID, "assessment_run": overview_run})
    client.put(f"/projects/{slug}/robot", json={"robot": ROBOT})
    decomp = client.post(
        f"/projects/{slug}/decomposition",
        json={"cuts": [{"orientation": "horizontal", "position_mm": 1300.0}]},
    ).json()
    section_id = decomp["sections"][0]["section_id"]
    client.post(f"/projects/{slug}/sections/{section_id}/simulate", json={})
    return slug, section_id


def test_api_export_returns_incomplete_with_hint(client, api_dirs, stub_walls, tmp_path):
    slug, section_id = _api_project_with_section(client, tmp_path)
    resp = client.post(f"/projects/{slug}/sections/{section_id}/export", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["complete"] is False
    assert data["setup_source"] == "none"
    assert "Antasten" in data["note"]
    assert Path(data["run_dir"]).exists()


def test_api_export_unknown_slug_returns_404(client, api_dirs):
    resp = client.post("/projects/gibt-es-nicht/sections/abschnitt-1/export", json={})
    assert resp.status_code == 404


def test_api_export_unknown_section_returns_422(client, api_dirs, stub_walls, tmp_path):
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post("/projects", json={"name": "H", "model_path": str(model)}).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": WALL_ID, "assessment_run": overview_run})
    client.put(f"/projects/{slug}/robot", json={"robot": ROBOT})
    resp = client.post(f"/projects/{slug}/sections/nope/export", json={})
    assert resp.status_code == 422
