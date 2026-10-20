"""Tests für die Workstation-Wahl am Druckjob (Issue #77, PRD #69 — Seam zu #70).

Prüft:
- Schema: ``print_job.workstation`` ist additiv; Altprojekte ohne Feld laden unverändert
- Setter-Aktion persistiert die Wahl über ``fgc.project`` (einzige Schreibstelle)
- Kompatibilitäts-Befund (domain/compat) gegen den Roboter des Jobs — kein Gate
- API PUT /projects/{slug}/workstation (Persistenz + 404 bei unbekannter Workstation)
- Veralten (Issue #83, Ablösung des #77-Seams): ein Workstation-Wechsel bumpt die
  Eingabe-Revision 'workstation' → Druckplan/Simulation/Export (und alle Abschnitte)
  veralten, weil der Druckplan-Automatismus (#80–82) die Workstation-Werte konsumiert
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fgc import domain
from fgc.pipeline.actions import (
    create_project_from_ifc,
    set_print_job,
    set_workstation_for_job,
)
from fgc.pipeline.api import app
from fgc.project import bump_input, output_status, refresh_output

ROBOT = "doosan_m1013"
WORKSTATION = "mobile_hub"  # Referenz-Workstation (workstations/mobile_hub.json), ungetaggt


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _make_project_with_job(tmp_path: Path, install_walls, make_wall) -> tuple[str, dict]:
    """Legt ein minimales Projekt mit einem Druckjob an; gibt Slug + Artefakt zurück."""
    install_walls([make_wall("TESTWALL00000000000000")])

    model_path = tmp_path / "model.ifc"
    model_path.touch()

    creation = create_project_from_ifc(
        "Testprojekt",
        model_path,
        ROBOT,
        "test",
        projects_dir=tmp_path / "projects",
        runs_dir=tmp_path / "runs",
    )
    slug = creation.project_dir.name

    result = set_print_job(
        slug,
        "TESTWALL00000000000000",
        str(creation.overview_run_dir),
        "default",
        projects_dir=tmp_path / "projects",
    )
    return slug, result.artifact


def _set_job_robot(tmp_path: Path, slug: str, artifact: dict, robot: str) -> None:
    """Trägt einen Roboter direkt in den Druckjob ein (für den Kompat-Befund)."""
    from fgc.project import project_dir_for
    from fgc.project import write_project as wp

    project_dir = project_dir_for(slug, projects_dir=tmp_path / "projects")
    jobs = artifact["print_jobs"]
    updated = [{**j, "robot": robot} if j["job_id"] == "default" else j for j in jobs]
    wp(project_dir, {**artifact, "print_jobs": updated})


# ---------------------------------------------------------------------------
# Schema: additiv + rückwärtskompatibel
# ---------------------------------------------------------------------------


def test_schema_accepts_workstation_field() -> None:
    """Ein Druckjob mit ``workstation`` ist schema-valide (additiv)."""
    project = {
        "schema_version": "0.1",
        "provenance": {"source": "test", "created": "2026-07-07T00:00:00Z", "git_commit": "x"},
        "name": "P",
        "model_path": "/x/model.ifc",
        "overview_run": "/x/runs/walls-list",
        "print_jobs": [
            {
                "job_id": "default",
                "wall_global_id": "W1",
                "workstation": "mobile_hub",
            }
        ],
    }
    domain.validate(project, "project")  # darf nicht werfen


def test_schema_old_project_without_workstation_loads(
    tmp_path: Path, install_walls, make_wall
) -> None:
    """Ein Altprojekt-Job ohne ``workstation`` bleibt schema-valide (rückwärtskompatibel)."""
    slug, artifact = _make_project_with_job(tmp_path, install_walls, make_wall)
    job = next(j for j in artifact["print_jobs"] if j["job_id"] == "default")
    assert "workstation" not in job  # frisch angelegt: Feld fehlt
    domain.validate(artifact, "project")  # lädt/validiert unverändert


# ---------------------------------------------------------------------------
# Setter-Aktion: Persistenz + Kompat-Befund
# ---------------------------------------------------------------------------


def test_set_workstation_persists_in_print_job(tmp_path: Path, install_walls, make_wall) -> None:
    """set_workstation_for_job schreibt das workstation-Feld in den Druckjob."""
    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)

    result = set_workstation_for_job(
        slug, WORKSTATION, "default", projects_dir=tmp_path / "projects"
    )
    assert result.workstation_name == WORKSTATION
    job = next(j for j in result.artifact["print_jobs"] if j["job_id"] == "default")
    assert job["workstation"] == WORKSTATION


def test_set_workstation_restored_after_reload(tmp_path: Path, install_walls, make_wall) -> None:
    """Die Wahl liegt nach dem Neuladen des Projekts im Druckjob (Persistenz)."""
    from fgc.project import load_project, project_dir_for

    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)
    set_workstation_for_job(slug, WORKSTATION, "default", projects_dir=tmp_path / "projects")

    reloaded = load_project(project_dir_for(slug, projects_dir=tmp_path / "projects"))
    job = next(j for j in reloaded["print_jobs"] if j["job_id"] == "default")
    assert job["workstation"] == WORKSTATION


def test_set_workstation_compat_none_without_robot(
    tmp_path: Path, install_walls, make_wall
) -> None:
    """Ohne Roboter im Job ist der Kompat-Befund None (nicht prüfbar)."""
    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)
    result = set_workstation_for_job(
        slug, WORKSTATION, "default", projects_dir=tmp_path / "projects"
    )
    assert result.compatible is None


def test_set_workstation_compat_true_untagged(tmp_path: Path, install_walls, make_wall) -> None:
    """Ungetaggte Workstation gilt für jeden Roboter als kompatibel (Migrationsschutz)."""
    slug, artifact = _make_project_with_job(tmp_path, install_walls, make_wall)
    _set_job_robot(tmp_path, slug, artifact, ROBOT)

    result = set_workstation_for_job(
        slug, WORKSTATION, "default", projects_dir=tmp_path / "projects"
    )
    # mobile_hub trägt keine compatible_robots → unbekannt = kompatibel.
    assert result.compatible is True


def test_set_workstation_unknown_raises(tmp_path: Path, install_walls, make_wall) -> None:
    """Unbekannte Workstation → FileNotFoundError (API übersetzt in 404)."""
    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)
    with pytest.raises(FileNotFoundError, match="workstations/"):
        set_workstation_for_job(
            slug, "nonexistent_ws", "default", projects_dir=tmp_path / "projects"
        )


# ---------------------------------------------------------------------------
# Veralten (Issue #83): Workstation-Wechsel bumpt 'workstation' (Ablösung #77-Seam)
# ---------------------------------------------------------------------------


def test_workstation_change_stales_outputs(tmp_path: Path, install_walls, make_wall) -> None:
    """Ein Workstation-Wechsel veraltet Druckplan/Simulation/Export (Issue #83).

    Ablösung des #77-Seams: seit #80–82 treiben die Workstation-Werte den
    Druckplan-Automatismus, daher bumpt der Setter jetzt die Eingabe-Revision
    'workstation'. Ausgangslage alle Outputs frisch → 'current'; nach dem Setzen
    müssen sie 'stale' werden (Design-Log 2026-07-07, ADR-017-Nachtrag).
    """
    from fgc.project import load_project, project_dir_for
    from fgc.project import write_project as wp

    slug, artifact = _make_project_with_job(tmp_path, install_walls, make_wall)
    project_dir = project_dir_for(slug, projects_dir=tmp_path / "projects")

    # Alle Output-Stufen als 'erzeugt' markieren (Schnappschuss auf aktuelle Inputs).
    jobs = artifact["print_jobs"]
    job = next(j for j in jobs if j["job_id"] == "default")
    for output in ("druckplan", "simulation", "export"):
        job = refresh_output(job, output)
    updated = [job if j["job_id"] == "default" else j for j in jobs]
    wp(project_dir, {**artifact, "print_jobs": updated})

    before = output_status(job)
    assert before == {"druckplan": "current", "simulation": "current", "export": "current"}

    # Workstation setzen — bumpt jetzt die Eingabe-Revision 'workstation'.
    result = set_workstation_for_job(
        slug, WORKSTATION, "default", projects_dir=tmp_path / "projects"
    )
    reloaded_job = next(j for j in result.artifact["print_jobs"] if j["job_id"] == "default")

    after = output_status(reloaded_job)
    assert after == {"druckplan": "stale", "simulation": "stale", "export": "stale"}, (
        "Workstation-Wechsel veraltet jetzt alle Outputs (Issue #83)."
    )
    # Der Zähler 'workstation' wurde erhöht (neuer INPUT_KEY seit #83).
    reloaded = load_project(project_dir)
    reloaded_job2 = next(j for j in reloaded["print_jobs"] if j["job_id"] == "default")
    assert reloaded_job2["revisions"]["inputs"]["workstation"] == 1


def test_set_workstation_echo_does_not_bump(tmp_path: Path, install_walls, make_wall) -> None:
    """Echo-fest (Issue #199): dieselbe Workstation erneut gesetzt bumpt nicht.

    Der Seam ``mutate_print_job`` difft den deklarierten Pfad 'workstation' —
    nur ein tatsaechlicher Wechsel veraltet die Outputs (ADR-017/#83).
    """
    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)

    first = set_workstation_for_job(
        slug, WORKSTATION, "default", projects_dir=tmp_path / "projects"
    )
    job = next(j for j in first.artifact["print_jobs"] if j["job_id"] == "default")
    assert job["revisions"]["inputs"]["workstation"] == 1

    again = set_workstation_for_job(
        slug, WORKSTATION, "default", projects_dir=tmp_path / "projects"
    )
    job = next(j for j in again.artifact["print_jobs"] if j["job_id"] == "default")
    assert job["workstation"] == WORKSTATION  # gespeichert bleibt sie
    assert job["revisions"]["inputs"]["workstation"] == 1  # kein Fake-Veralten


def test_bump_input_accepts_workstation() -> None:
    """'workstation' ist seit Issue #83 ein gültiger INPUT_KEY (Ablösung #77-Seam)."""
    job = bump_input({"job_id": "default", "wall_global_id": "W1"}, "workstation")
    assert job["revisions"]["inputs"]["workstation"] == 1


# ---------------------------------------------------------------------------
# API: PUT /projects/{slug}/workstation
# ---------------------------------------------------------------------------


def _patch_projects_dir(monkeypatch, tmp_path: Path) -> None:
    from fgc import project as proj_mod

    monkeypatch.setattr(proj_mod.store, "PROJECTS_DIR", tmp_path / "projects")


def test_put_workstation_api(tmp_path: Path, monkeypatch, install_walls, make_wall) -> None:
    """PUT /projects/{slug}/workstation persistiert die Wahl + liefert Kompat-Befund."""
    slug, artifact = _make_project_with_job(tmp_path, install_walls, make_wall)
    _set_job_robot(tmp_path, slug, artifact, ROBOT)
    _patch_projects_dir(monkeypatch, tmp_path)

    client = TestClient(app)
    resp = client.put(
        f"/projects/{slug}/workstation",
        json={"workstation": WORKSTATION, "job_id": "default"},
    )
    assert resp.status_code == 200
    body = resp.json()
    job = next(j for j in body["print_jobs"] if j["job_id"] == "default")
    assert job["workstation"] == WORKSTATION
    assert body["compatible"] is True  # ungetaggt = kompatibel


def test_put_workstation_api_unknown(tmp_path: Path, monkeypatch, install_walls, make_wall) -> None:
    """PUT /projects/{slug}/workstation → 404 bei unbekannter Workstation."""
    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)
    _patch_projects_dir(monkeypatch, tmp_path)

    client = TestClient(app)
    resp = client.put(
        f"/projects/{slug}/workstation",
        json={"workstation": "nonexistent_ws", "job_id": "default"},
    )
    assert resp.status_code == 404


def test_put_workstation_api_roundtrip_persists(
    tmp_path: Path, monkeypatch, install_walls, make_wall
) -> None:
    """Nach PUT liegt die Wahl in der geschriebenen project.json (Persistenz auf Platte)."""
    slug, _ = _make_project_with_job(tmp_path, install_walls, make_wall)
    _patch_projects_dir(monkeypatch, tmp_path)

    client = TestClient(app)
    client.put(
        f"/projects/{slug}/workstation",
        json={"workstation": WORKSTATION, "job_id": "default"},
    )
    project_json = tmp_path / "projects" / slug / "project.json"
    raw = json.loads(project_json.read_text(encoding="utf-8"))
    job = next(j for j in raw["print_jobs"] if j["job_id"] == "default")
    assert job["workstation"] == WORKSTATION
