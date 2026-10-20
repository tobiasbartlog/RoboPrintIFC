"""Das Projekt-Modul (ADR-016): Schema, anlegen/laden/listen, Lauf-Verweise.

Geprüft wird externes Verhalten, nicht die interne Umsetzung: Was liefern
`create_project_from_ifc`, `load_project`, `list_projects` für eine bekannte
Modell-/Roboter-Kombination, und was validiert das Schema. Die IFC-Wandquelle
wird gestubbt (wie in test_actions), damit kein Beispielmodell nötig ist; die
Projekt- und Laufverzeichnisse werden als Test-Seams injiziert.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from fgc import domain
from fgc.pipeline import runfolder
from fgc.pipeline.actions import create_project_from_ifc, reassess_walls_for_robot, set_print_job
from fgc.pipeline.api import app
from fgc.project import (
    list_projects,
    load_project,
    project_artifact,
    project_slug,
    write_project,
)
from fgc.project import store as project_store

ROBOT = "doosan_m1013"

PROVENANCE = {
    "source": "test",
    "created": "2026-07-04T12:00:00Z",
    "git_commit": "0000000",
}


@pytest.fixture
def stub_walls(install_walls, make_wall):
    # Zwei Wände, damit walls_to_run mehrere Kandidaten schreibt; leerer
    # Gebäudekontext, damit die Aktion kein IFC öffnet (Issue #17).
    return install_walls(
        [make_wall("WALLAAAAAAAAAAAAAAAAAA"), make_wall("WALLBBBBBBBBBBBBBBBBBB")]
    )


# --- Schema-Validierung ------------------------------------------------------


def _valid_project() -> dict:
    return project_artifact(
        "Testhaus", Path("modell.ifc"), Path("runs/some-run"), PROVENANCE
    )


def test_valid_project_passes_schema():
    domain.validate(_valid_project(), "project")


def test_project_requires_overview_run():
    project = _valid_project()
    del project["overview_run"]
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(project, "project")


def test_project_rejects_unknown_field():
    project = _valid_project()
    project["results"] = {"toolpath": "..."}  # eingebettete Ergebnisse verboten (ADR-016)
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(project, "project")


def test_print_job_minimal_structure_validates():
    project = _valid_project()
    project["print_jobs"] = [{"job_id": "j1", "wall_global_id": "WALLAAAAAAAAAAAAAAAAAA"}]
    domain.validate(project, "project")


def test_write_project_rejects_invalid_artifact(tmp_path):
    """Die eine Schreibstelle validiert: ein vertragswidriges Projekt wird nie geschrieben."""
    bad = _valid_project()
    del bad["name"]
    with pytest.raises(jsonschema.ValidationError):
        write_project(tmp_path / "x", bad)
    assert not (tmp_path / "x" / "project.json").exists()


def test_project_slug_is_file_safe():
    assert project_slug("Wohnhaus Süd 2!") == "wohnhaus-sud-2"
    assert project_slug("   ") == "projekt"


# --- anlegen / laden / listen + Lauf-Verweise --------------------------------


def test_create_project_from_ifc_writes_project_and_overview_run(tmp_path, stub_walls):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"

    creation = create_project_from_ifc(
        "Testhaus",
        Path("modell.ifc"),
        ROBOT,
        "POST /projects name='Testhaus'",
        projects_dir=projects_dir,
        runs_dir=runs_dir,
    )

    # Projektordner + project.json entstanden, schema-valide.
    assert creation.project_dir.parent == projects_dir
    assert creation.project_path == creation.project_dir / "project.json"
    artifact = json.loads(creation.project_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "project")
    assert artifact["name"] == "Testhaus"
    assert artifact["print_jobs"] == []  # leere Struktur in diesem Slice

    # Übersichts-Lauf entstanden und *verwiesen*, nicht eingebettet.
    assert creation.overview_run_dir.parent == runs_dir
    assert Path(artifact["overview_run"]) == creation.overview_run_dir.resolve()
    assert (creation.overview_run_dir / "candidates.json").exists()
    assert (creation.overview_run_dir / "model.glb").exists()
    assert (creation.overview_run_dir / "model_map.json").exists()
    # model_path absolut aufgelöst (für /@fs im Viewer).
    assert Path(artifact["model_path"]).name == "modell.ifc"
    assert Path(artifact["model_path"]).is_absolute()


def test_load_project_round_trips(tmp_path, stub_walls):
    projects_dir = tmp_path / "projects"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=tmp_path / "runs",
    )

    loaded = load_project(creation.project_dir)
    assert loaded == creation.artifact


def test_load_project_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / "gibt-es-nicht")


def test_list_projects_finds_created(tmp_path, stub_walls):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    create_project_from_ifc("Haus A", Path("a.ifc"), ROBOT, "src",
                            projects_dir=projects_dir, runs_dir=runs_dir)
    create_project_from_ifc("Haus B", Path("b.ifc"), ROBOT, "src",
                            projects_dir=projects_dir, runs_dir=runs_dir)

    summaries = list_projects(projects_dir)
    names = {s.name for s in summaries}
    assert names == {"Haus A", "Haus B"}
    assert all(s.n_print_jobs == 0 for s in summaries)


def test_list_projects_empty_when_no_dir(tmp_path):
    assert list_projects(tmp_path / "nope") == []


def test_create_project_unique_dir_on_name_collision(tmp_path, stub_walls):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    first = create_project_from_ifc("Haus", Path("a.ifc"), ROBOT, "src",
                                    projects_dir=projects_dir, runs_dir=runs_dir)
    second = create_project_from_ifc("Haus", Path("a.ifc"), ROBOT, "src",
                                     projects_dir=projects_dir, runs_dir=runs_dir)
    assert first.project_dir != second.project_dir
    assert {first.project_dir.name, second.project_dir.name} == {"haus", "haus-1"}


# --- API: anlegen/laden/listen erreichbar (dünne Wrapper) --------------------


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


def test_api_list_create_get_roundtrip(client, api_dirs, stub_walls, tmp_path):
    # Modellpfad muss existieren (POST /projects prüft das) — leere Datei genügt,
    # weil load_walls gestubbt ist.
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")

    # Anfangs leer.
    assert client.get("/projects").json()["projects"] == []

    # Anlegen.
    resp = client.post("/projects", json={"name": "Testhaus", "model_path": str(model)})
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["name"] == "Testhaus"
    assert created["print_jobs"] == []
    assert Path(created["overview_run"]).name  # Verweis vorhanden
    slug = created["slug"]

    # Listen zeigt das neue Projekt.
    listed = client.get("/projects").json()["projects"]
    assert [p["slug"] for p in listed] == [slug]
    assert listed[0]["n_print_jobs"] == 0

    # Laden liefert denselben Stand.
    got = client.get(f"/projects/{slug}").json()
    assert got == created


def test_api_create_unknown_model_returns_404(client, api_dirs):
    resp = client.post("/projects", json={"name": "X", "model_path": "gibt-es-nicht.ifc"})
    assert resp.status_code == 404


def test_api_get_unknown_project_returns_404(client, api_dirs):
    assert client.get("/projects/gibt-es-nicht").status_code == 404


# --- Druckjob setzen (Issue #19) -----------------------------------------------


def _create(tmp_path, stub_walls):
    """Hilfsfunktion: Testprojekt anlegen und slug + overview_run zurückgeben."""
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    return creation, projects_dir


def test_set_print_job_creates_job(tmp_path, stub_walls):
    """set_print_job schreibt einen schema-validen Druckjob mit Lauf-Verweis."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    overview_run = str(creation.overview_run_dir)

    result = set_print_job(
        slug, "WALLAAAAAAAAAAAAAAAAAA", overview_run, projects_dir=projects_dir
    )

    artifact = json.loads(result.project_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "project")
    assert len(artifact["print_jobs"]) == 1
    job = artifact["print_jobs"][0]
    assert job["job_id"] == "default"
    assert job["wall_global_id"] == "WALLAAAAAAAAAAAAAAAAAA"
    # assessment_run verweist auf den Übersichts-Lauf (absoluter Pfad).
    assert Path(job["assessment_run"]).is_absolute()
    assert Path(job["assessment_run"]) == Path(overview_run).resolve()


def test_set_print_job_stores_wall_name(tmp_path, stub_walls):
    """wall_name wird optional mitgespeichert (für UI-Anzeige, keine Norm-Daten)."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name

    result = set_print_job(
        slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
        wall_name="Testwand",
        projects_dir=projects_dir,
    )

    job = result.artifact["print_jobs"][0]
    assert job.get("wall_name") == "Testwand"
    domain.validate(result.artifact, "project")


def test_set_print_job_overwrites_same_job_id(tmp_path, stub_walls):
    """Derselbe job_id ersetzt den vorherigen Druckjob — nur ein Job bleibt."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    overview_run = str(creation.overview_run_dir)

    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", overview_run, projects_dir=projects_dir)
    result = set_print_job(slug, "WALLBBBBBBBBBBBBBBBBBB", overview_run, projects_dir=projects_dir)

    artifact = result.artifact
    domain.validate(artifact, "project")
    assert len(artifact["print_jobs"]) == 1
    assert artifact["print_jobs"][0]["wall_global_id"] == "WALLBBBBBBBBBBBBBBBBBB"


def test_set_print_job_multiple_jobs_coexist(tmp_path, stub_walls):
    """Verschiedene job_ids erzeugen separate Druckjobs im selben Projekt."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    overview_run = str(creation.overview_run_dir)

    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", overview_run, "job-a",
                  projects_dir=projects_dir)
    result = set_print_job(slug, "WALLBBBBBBBBBBBBBBBBBB", overview_run, "job-b",
                           projects_dir=projects_dir)

    artifact = result.artifact
    domain.validate(artifact, "project")
    assert len(artifact["print_jobs"]) == 2
    job_ids = {j["job_id"] for j in artifact["print_jobs"]}
    assert job_ids == {"job-a", "job-b"}


def test_set_print_job_preserves_runs_on_overwrite(tmp_path, stub_walls):
    """Überschreiben eines Druckjobs bewahrt bestehende runs-Verweise."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    overview_run = str(creation.overview_run_dir)

    # Ersten Job setzen und künstliche runs-Verweise eintragen.
    result = set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", overview_run,
                           projects_dir=projects_dir)
    artifact = {**result.artifact}
    artifact["print_jobs"][0] = {**artifact["print_jobs"][0], "runs": ["/fake/run"]}
    from fgc.project import write_project
    write_project(result.project_dir, artifact)

    # Jetzt mit neuer Wand überschreiben — runs sollen erhalten bleiben.
    result2 = set_print_job(slug, "WALLBBBBBBBBBBBBBBBBBB", overview_run,
                            projects_dir=projects_dir)
    assert result2.artifact["print_jobs"][0]["runs"] == ["/fake/run"]


def test_set_print_job_unknown_slug_raises(tmp_path):
    """Unbekannter Slug wirft FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        set_print_job("gibt-es-nicht", "ID", "/fake/run",
                      projects_dir=tmp_path / "projects")


# --- API: Druckjob-Endpoint ---------------------------------------------------


def test_api_put_print_job_creates_job(client, api_dirs, stub_walls, tmp_path):
    """PUT /projects/{slug}/print-job setzt den Druckjob und antwortet schema-valide."""
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")

    create_resp = client.post("/projects", json={"name": "Testhaus", "model_path": str(model)})
    assert create_resp.status_code == 200
    slug = create_resp.json()["slug"]
    overview_run = create_resp.json()["overview_run"]

    resp = client.put(
        f"/projects/{slug}/print-job",
        json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA", "assessment_run": overview_run},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["print_jobs"]) == 1
    job = data["print_jobs"][0]
    assert job["wall_global_id"] == "WALLAAAAAAAAAAAAAAAAAA"
    assert "assessment_run" in job


def test_api_put_print_job_unknown_slug_returns_404(client, api_dirs):
    """Unbekannter Slug liefert 404."""
    resp = client.put(
        "/projects/gibt-es-nicht/print-job",
        json={"wall_global_id": "ID", "assessment_run": "/fake/run"},
    )
    assert resp.status_code == 404


def test_api_put_print_job_overwrites(client, api_dirs, stub_walls, tmp_path):
    """PUT zweimal mit demselben job_id → nur ein Druckjob."""
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post("/projects", json={"name": "H", "model_path": str(model)}).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]

    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": "AAA", "assessment_run": overview_run})
    resp = client.put(f"/projects/{slug}/print-job",
                      json={"wall_global_id": "BBB", "assessment_run": overview_run})

    assert resp.status_code == 200
    assert len(resp.json()["print_jobs"]) == 1
    assert resp.json()["print_jobs"][0]["wall_global_id"] == "BBB"


# --- Roboter-Neubewertung (Issue #20) -----------------------------------------


def test_reassess_creates_new_run_and_updates_overview(tmp_path, stub_walls):
    """reassess_walls_for_robot erzeugt neuen Lauf und aktualisiert overview_run."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    runs_dir = tmp_path / "runs"

    result = reassess_walls_for_robot(
        slug, ROBOT, "PUT /robot test",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )

    artifact = json.loads(result.project_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "project")
    # Neuer Lauf vorhanden und von overview_run referenziert.
    assert result.new_run_dir.exists()
    assert Path(artifact["overview_run"]) == result.new_run_dir.resolve()
    # Neuer Lauf ist verschieden vom ursprünglichen.
    assert result.new_run_dir != creation.overview_run_dir


def test_reassess_updates_print_job_robot_and_assessment_run(tmp_path, stub_walls):
    """reassess setzt robot + assessment_run im Druckjob."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    runs_dir = tmp_path / "runs"

    # Erst einen Druckjob anlegen.
    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  projects_dir=projects_dir)

    result = reassess_walls_for_robot(
        slug, ROBOT, "PUT /robot test",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )

    artifact = result.artifact
    domain.validate(artifact, "project")
    job = artifact["print_jobs"][0]
    assert job["robot"] == ROBOT
    assert Path(job["assessment_run"]) == result.new_run_dir.resolve()


def test_reassess_without_job_only_updates_overview(tmp_path, stub_walls):
    """reassess ohne Druckjob aktualisiert nur overview_run (kein Fehler)."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    runs_dir = tmp_path / "runs"

    result = reassess_walls_for_robot(
        slug, ROBOT, "PUT /robot test",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )

    artifact = result.artifact
    domain.validate(artifact, "project")
    assert artifact["print_jobs"] == []  # kein Job angelegt
    assert Path(artifact["overview_run"]) == result.new_run_dir.resolve()


def test_reassess_preserves_other_jobs(tmp_path, stub_walls):
    """reassess lässt Jobs mit anderem job_id unangetastet."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    runs_dir = tmp_path / "runs"

    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  "job-a", projects_dir=projects_dir)
    set_print_job(slug, "WALLBBBBBBBBBBBBBBBBBB", str(creation.overview_run_dir),
                  "job-b", projects_dir=projects_dir)

    result = reassess_walls_for_robot(
        slug, ROBOT, "PUT /robot test", "job-a",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )

    artifact = result.artifact
    domain.validate(artifact, "project")
    job_a = next(j for j in artifact["print_jobs"] if j["job_id"] == "job-a")
    job_b = next(j for j in artifact["print_jobs"] if j["job_id"] == "job-b")
    assert job_a["robot"] == ROBOT
    assert "robot" not in job_b  # job-b bleibt unangetastet


# --- API: Roboterkatalog + Neubewertungs-Endpoint (Issue #20) -----------------


def test_api_get_robots_returns_doosan(client):
    """GET /robots enthält mindestens den Doosan M1013."""
    resp = client.get("/robots")
    assert resp.status_code == 200
    robots = resp.json()["robots"]
    assert len(robots) >= 1
    names = {r["name"] for r in robots}
    assert "doosan_m1013" in names
    doosan = next(r for r in robots if r["name"] == "doosan_m1013")
    assert doosan["reach_mm"] == 1300
    assert "max_print_height_mm" in doosan
    assert "workspace_provisional" in doosan


def test_api_put_robot_creates_new_run(client, api_dirs, stub_walls, tmp_path):
    """PUT /projects/{slug}/robot erzeugt neuen Befund-Lauf und färbt neu ein."""
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")

    create_resp = client.post("/projects", json={"name": "Testhaus", "model_path": str(model)})
    assert create_resp.status_code == 200
    slug = create_resp.json()["slug"]
    original_run = create_resp.json()["overview_run"]

    resp = client.put(f"/projects/{slug}/robot", json={"robot": ROBOT})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # overview_run wurde aktualisiert (neuer Lauf).
    assert data["overview_run"] != original_run
    assert Path(data["overview_run"]).exists()


def test_api_put_robot_updates_job_robot_field(client, api_dirs, stub_walls, tmp_path):
    """PUT /robot setzt robot-Feld im Druckjob, wenn einer existiert."""
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post("/projects", json={"name": "H", "model_path": str(model)}).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]

    # Druckjob anlegen.
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA",
                     "assessment_run": overview_run})

    resp = client.put(f"/projects/{slug}/robot", json={"robot": ROBOT})
    assert resp.status_code == 200
    job = resp.json()["print_jobs"][0]
    assert job["robot"] == ROBOT
    assert "assessment_run" in job


def test_api_put_robot_unknown_slug_returns_404(client, api_dirs):
    """Unbekannter Slug liefert 404."""
    resp = client.put("/projects/gibt-es-nicht/robot", json={"robot": ROBOT})
    assert resp.status_code == 404


# --- Prozessparameter-Rail (Scheibe 2, Issue #59) -----------------------------


def _valid_project_with_job() -> dict:
    p = _valid_project()
    p["print_jobs"] = [{"job_id": "default", "wall_global_id": "WALLAAAAAAAAAAAAAAAAAA"}]
    return p


def test_process_params_slice_block_validates():
    """Ein Druckjob mit process_params.slice ist schema-valide (additiv)."""
    p = _valid_project_with_job()
    p["print_jobs"][0]["process_params"] = {
        "slice": {"layer_height_mm": 8.0, "strand_width_mm": 25.0, "n_shells": 3}
    }
    domain.validate(p, "project")


def test_process_params_partial_slice_validates():
    """Teil-Overrides (nur ein Feld) sind erlaubt — der Rest fällt auf Defaults."""
    p = _valid_project_with_job()
    p["print_jobs"][0]["process_params"] = {"slice": {"layer_height_mm": 7.5}}
    domain.validate(p, "project")


def test_old_project_without_process_params_still_validates():
    """Altprojekte ohne den Block laden unverändert (rückwärtskompatibel)."""
    domain.validate(_valid_project_with_job(), "project")


def test_process_params_rejects_unknown_slice_field():
    p = _valid_project_with_job()
    p["print_jobs"][0]["process_params"] = {"slice": {"nozzle_mm": 6.0}}
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(p, "project")


def test_process_params_rejects_nonpositive_layer_height():
    p = _valid_project_with_job()
    p["print_jobs"][0]["process_params"] = {"slice": {"layer_height_mm": 0}}
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(p, "project")


def _job_with_robot(tmp_path, stub_walls):
    """Testprojekt mit einem Druckjob (Wand gesetzt) + slug/projects_dir."""
    creation, projects_dir = _create(tmp_path, stub_walls)
    slug = creation.project_dir.name
    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  projects_dir=projects_dir)
    return slug, projects_dir


def test_set_process_params_writes_slice_block(tmp_path, stub_walls):
    """set_process_params schreibt den Slice-Block schema-valide (einzige Schreibstelle)."""
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    result = set_process_params(
        slug, {"layer_height_mm": 8.0, "strand_width_mm": 25.0, "n_shells": 3},
        projects_dir=projects_dir,
    )
    domain.validate(result.artifact, "project")
    job = result.artifact["print_jobs"][0]
    assert job["process_params"]["slice"] == {
        "layer_height_mm": 8.0, "strand_width_mm": 25.0, "n_shells": 3,
    }
    # Auf der Platte persistiert (nach Neuladen wiederhergestellt).
    reloaded = load_project(result.project_dir)
    assert reloaded["print_jobs"][0]["process_params"]["slice"]["layer_height_mm"] == 8.0


def test_set_process_params_only_stores_set_fields(tmp_path, stub_walls):
    """Nur gesetzte Felder landen im Block; None-Felder werden weggelassen."""
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    result = set_process_params(
        slug, {"layer_height_mm": 7.5, "strand_width_mm": None, "n_shells": None},
        projects_dir=projects_dir,
    )
    assert result.artifact["print_jobs"][0]["process_params"]["slice"] == {"layer_height_mm": 7.5}


def test_set_process_params_empty_removes_block(tmp_path, stub_walls):
    """Alle Felder leer → der Block wird entfernt (zurück auf Karten-/Code-Defaults)."""
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    set_process_params(slug, {"layer_height_mm": 8.0}, projects_dir=projects_dir)
    result = set_process_params(slug, {}, projects_dir=projects_dir)
    assert "process_params" not in result.artifact["print_jobs"][0]
    domain.validate(result.artifact, "project")


def test_set_process_params_writes_advanced_speed_and_io(tmp_path, stub_walls):
    """v_print/v_travel/io_print/io_travel werden schema-valide gespeichert (Issue #60).

    Die io-Werte liegen im Job als Skalar (nicht dict); nach dem Neuladen exakt
    wiederhergestellt.
    """
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    result = set_process_params(
        slug,
        {
            "layer_height_mm": 8.0,
            "v_print_mm_s": 42.0,
            "v_travel_mm_s": 333.0,
            "io_print": 0.7,
            "io_travel": 0.0,
        },
        projects_dir=projects_dir,
    )
    domain.validate(result.artifact, "project")
    stored = result.artifact["print_jobs"][0]["process_params"]["slice"]
    assert stored == {
        "layer_height_mm": 8.0,
        "v_print_mm_s": 42.0,
        "v_travel_mm_s": 333.0,
        "io_print": 0.7,
        "io_travel": 0.0,
    }
    # Auf der Platte persistiert (nach Neuladen wiederhergestellt).
    reloaded = load_project(result.project_dir)
    assert reloaded["print_jobs"][0]["process_params"]["slice"]["v_print_mm_s"] == 42.0
    assert reloaded["print_jobs"][0]["process_params"]["slice"]["io_travel"] == 0.0


# --- Gradierungs-Ebene: Pro-Abschnitts-Overrides (Issue #82) ---------------------


def test_process_params_sections_block_validates():
    """process_params.sections (section_id → sparse Override) ist schema-valide (additiv)."""
    p = _valid_project_with_job()
    p["print_jobs"][0]["process_params"] = {
        "slice": {"layer_height_mm": 8.0},
        "sections": {
            "abschnitt-1": {"slice": {"layer_height_mm": 6.0}, "orientation": {"kipp_deg": 5.0}},
            "abschnitt-2": {"slice": {"n_shells": 4}},
        },
    }
    domain.validate(p, "project")


def test_process_params_sections_rejects_unknown_field():
    p = _valid_project_with_job()
    p["print_jobs"][0]["process_params"] = {
        "sections": {"abschnitt-1": {"slice": {"nozzle_mm": 6.0}}}
    }
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(p, "project")


def test_process_params_ik_config_block_validates():
    """process_params.ik_config (global + je Abschnitt) ist schema-valide (Issue #129)."""
    p = _valid_project_with_job()
    p["print_jobs"][0]["process_params"] = {
        "ik_config": {"shoulder": "a", "elbow": "b"},
        "sections": {"abschnitt-1": {"ik_config": {"wrist": "b"}}},
    }
    domain.validate(p, "project")


def test_process_params_ik_config_rejects_invalid_state():
    """Nur 'a'/'b' erlaubt — ein anderer Wert ist schema-widrig."""
    p = _valid_project_with_job()
    p["print_jobs"][0]["process_params"] = {"ik_config": {"elbow": "auto"}}
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(p, "project")


def test_set_process_params_writes_sections_block(tmp_path, stub_walls):
    """set_process_params(sections=…) schreibt den Block schema-valide + persistent (Issue #82)."""
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    result = set_process_params(
        slug,
        {},
        sections={
            "abschnitt-1": {"slice": {"layer_height_mm": 6.0}, "orientation": {"kipp_deg": 5.0}},
            "abschnitt-2": {"slice": {"n_shells": 4, "strand_width_mm": None}},
        },
        projects_dir=projects_dir,
    )
    domain.validate(result.artifact, "project")
    sections = result.artifact["print_jobs"][0]["process_params"]["sections"]
    assert sections == {
        "abschnitt-1": {"slice": {"layer_height_mm": 6.0}, "orientation": {"kipp_deg": 5.0}},
        "abschnitt-2": {"slice": {"n_shells": 4}},  # None-Feld weggelassen
    }
    reloaded = load_project(result.project_dir)
    assert reloaded["print_jobs"][0]["process_params"]["sections"]["abschnitt-1"]["slice"][
        "layer_height_mm"
    ] == 6.0


def test_set_process_params_empty_section_dropped(tmp_path, stub_walls):
    """Ein Abschnitt ohne gesetzte Felder fällt weg; alle leer → kein sections-Block."""
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    result = set_process_params(
        slug,
        {},
        sections={"abschnitt-1": {"slice": {}, "orientation": {}}},
        projects_dir=projects_dir,
    )
    assert "process_params" not in result.artifact["print_jobs"][0]


def test_set_process_params_sections_none_leaves_existing(tmp_path, stub_walls):
    """sections=None lässt bestehende Abschnitts-Overrides unberührt (getrennt vom Global)."""
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    set_process_params(
        slug,
        {},
        sections={"abschnitt-1": {"slice": {"layer_height_mm": 6.0}}},
        projects_dir=projects_dir,
    )
    result = set_process_params(slug, {"layer_height_mm": 9.0}, projects_dir=projects_dir)
    pp = result.artifact["print_jobs"][0]["process_params"]
    assert pp["slice"] == {"layer_height_mm": 9.0}
    assert pp["sections"] == {"abschnitt-1": {"slice": {"layer_height_mm": 6.0}}}


def test_job_slice_overrides_expands_io_scalar_to_channels():
    """job_slice_overrides dehnt den io-Skalar gleichförmig auf die Kanäle aus (Issue #60)."""
    from fgc.domain.process_params import SliceParams, job_slice_overrides

    job = {
        "process_params": {
            "slice": {"v_print_mm_s": 90.0, "io_print": 0.6, "io_travel": 0.0},
        }
    }
    overrides = job_slice_overrides(job)
    assert overrides["v_print_mm_s"] == 90.0
    # io-Kanäle entsprechen den Basis-SliceParams (v0: pump_a/pump_b).
    base = SliceParams()
    assert overrides["io_print"] == {ch: 0.6 for ch in base.io_print}
    assert overrides["io_travel"] == {ch: 0.0 for ch in base.io_travel}
    # from_window akzeptiert die ausgedehnten Overrides.
    params = SliceParams.from_window(_process_window_zero(), **overrides)
    assert params.v_print_mm_s == 90.0
    assert params.io_print == {ch: 0.6 for ch in base.io_print}


def _process_window_zero():
    from fgc.domain.process_params import ProcessWindow

    return ProcessWindow()


def test_set_process_params_bumps_revision_marks_downstream_stale(tmp_path, stub_walls):
    """Änderung an process_params → Zerlegung/Simulation/Export veralten (ADR-017)."""
    from fgc.pipeline.actions import set_process_params
    from fgc.project import output_status, refresh_output

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    # Alle drei Stufen einmal als „erzeugt" markieren → aktuell.
    artifact = load_project(project_dir_for_slug := (tmp_path / "projects" / slug))
    job = artifact["print_jobs"][0]
    for out in ("druckplan", "simulation", "export"):
        job = refresh_output(job, out)
    artifact["print_jobs"][0] = job
    write_project(project_dir_for_slug, artifact)
    assert set(output_status(job).values()) == {"current"}

    # Prozessparameter setzen → process bumpt → alle drei veraltet.
    result = set_process_params(slug, {"layer_height_mm": 8.0}, projects_dir=projects_dir)
    assert output_status(result.artifact["print_jobs"][0]) == {
        "druckplan": "stale", "simulation": "stale", "export": "stale",
    }


def test_set_process_params_echo_does_not_bump(tmp_path, stub_walls):
    """Echo-fest (Issue #199): identisches Wieder-Senden von Globals UND Abschnitts-
    Overrides (so echot der Viewer beim Abschnitts-Speichern) bumpt weder die
    'process'-Revision noch einen Pro-Abschnitts-Zähler."""
    from fgc.pipeline.actions import set_process_params

    slug, projects_dir = _job_with_robot(tmp_path, stub_walls)
    payload = dict(
        slice_params={"layer_height_mm": 8.0},
        orientation={"lead_deg": 5.0},
        sections={"abschnitt-1": {"slice": {"n_shells": 3}}},
    )
    first = set_process_params(
        slug, payload["slice_params"], orientation=payload["orientation"],
        sections=payload["sections"], projects_dir=projects_dir,
    )
    rev = first.artifact["print_jobs"][0]["revisions"]
    assert rev["inputs"]["process"] == 1
    assert rev["section_inputs"] == {"abschnitt-1": 1}

    # Identisches Wieder-Senden: kein weiterer Bump (kein Fake-Veralten).
    again = set_process_params(
        slug, payload["slice_params"], orientation=payload["orientation"],
        sections=payload["sections"], projects_dir=projects_dir,
    )
    rev = again.artifact["print_jobs"][0]["revisions"]
    assert rev["inputs"]["process"] == 1
    assert rev["section_inputs"] == {"abschnitt-1": 1}


def test_set_process_params_unknown_job_raises(tmp_path, stub_walls):
    from fgc.pipeline.actions import set_process_params

    creation, projects_dir = _create(tmp_path, stub_walls)  # kein Druckjob
    with pytest.raises(ValueError, match="Druckjob"):
        set_process_params(creation.project_dir.name, {"layer_height_mm": 8.0},
                           projects_dir=projects_dir)


def test_api_put_process_params_roundtrip(client, api_dirs, stub_walls, tmp_path):
    """PUT /projects/{slug}/process-params setzt den Block, GET liest ihn zurück."""
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post("/projects", json={"name": "H", "model_path": str(model)}).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA", "assessment_run": overview_run})

    resp = client.put(f"/projects/{slug}/process-params",
                      json={"slice": {"layer_height_mm": 9.0, "n_shells": 4}})
    assert resp.status_code == 200, resp.text
    job = resp.json()["print_jobs"][0]
    assert job["process_params"]["slice"] == {"layer_height_mm": 9.0, "n_shells": 4}

    # Nach Neuladen wiederhergestellt (persistiert im project.json).
    got = client.get(f"/projects/{slug}").json()
    assert got["print_jobs"][0]["process_params"]["slice"]["layer_height_mm"] == 9.0


def test_api_put_process_params_unknown_slug_returns_404(client, api_dirs):
    resp = client.put("/projects/gibt-es-nicht/process-params",
                      json={"slice": {"layer_height_mm": 9.0}})
    assert resp.status_code == 404


# --- Fehlerkontrakt des Seams actions↔api (Issue #118) ------------------------
#
# Der 404/422-Kontrakt lebt seit #118 einmal im ``action_errors``-Kontextmanager
# (api.py) statt ~20-fach je Endpoint kopiert. Diese drei Tests prüfen ihn direkt.


def test_api_action_errors_missing_project_maps_to_404(client, api_dirs):
    """FileNotFoundError einer Aktion (Projekt fehlt) → 404 (ein Ort, Issue #118)."""
    resp = client.put("/projects/gibt-es-nicht/tool",
                      json={"tool": "irgendwas", "job_id": "default"})
    assert resp.status_code == 404


def test_api_action_errors_value_error_maps_to_422(client, api_dirs, stub_walls, tmp_path):
    """ValueError einer Aktion (Druckjob fehlt) → 422 (ein Ort, Issue #118).

    Ein frisch angelegtes Projekt hat keine Druckjobs; ``set_tool_for_job`` wirft
    über ``mutate_print_job`` den einheitlichen „Druckjob … existiert nicht"-
    ValueError — der Seam bildet ihn auf 422 ab.
    """
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post("/projects", json={"name": "H", "model_path": str(model)}).json()["slug"]

    resp = client.put(f"/projects/{slug}/tool", json={"tool": "irgendwas", "job_id": "default"})
    assert resp.status_code == 422


def test_api_put_print_job_missing_project_404_via_seam(client, api_dirs):
    """Regression (Issue #118): put_print_job hat keinen Vorab-``load_project`` mehr.

    Dessen Vorab-Load trug bis #118 die 404-Semantik (die Aktion fängt kein
    FileNotFoundError). Jetzt muss der ``action_errors``-Seam sie tragen — sonst
    würde aus dem fehlenden Projekt ein 500 statt eines 404. (Ergänzt den
    bestehenden ``…_unknown_slug_returns_404``-Test um den #118-Bezug.)
    """
    resp = client.put("/projects/gibt-es-nicht/print-job",
                      json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA",
                            "assessment_run": "runs/x"})
    assert resp.status_code == 404
