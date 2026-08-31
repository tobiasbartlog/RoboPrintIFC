"""Der Druckjob-Mutations-Seam (Issue #119): Lock/Lookup/Bump/Write an einem Ort.

Vor #119 buchstabierte jeder reine Druckjob-Setter dieselbe Choreografie aus
(``project_lock`` → ``load_project`` → Job suchen → identischer ``ValueError`` →
Job ersetzen → ``write_project``) und die Veraltungs-Entscheidung lag als
Copy-Paste-Kommentar je Setter vor. ``fgc.project.mutate_print_job`` besitzt diese
Choreografie jetzt **einmal**; die Aktionen deklarieren nur noch ihre Fachlogik +
Bump-Semantik. Genau das prüft diese Datei **direkt am Seam** — die 13 impliziten
Wiederholungen in den Setter-Tests entfallen dadurch:

- Job-Lookup-Fehler (einheitlicher Text) und der Upsert-Zweig (kein Lookup)
- die **deklarierte** Bump-Semantik (Issue #199, Diff-dann-bump): ``bump_always``
  (Rebuild-Setter), ``bump_if_changed`` (beobachtete Pfade, echo-fest) und
  ``bump_sections_if_changed`` (section-gekeyter Pfad, beide Formen) vs. die
  sichtbare „BEWUSST kein Bump"-Deklaration (nichts deklariert)
- der Befund-Rückkanal des Mutators
- ``missing_ok``/``artifact_updates`` (Issue #199 — ``reassess_walls_for_robot``
  läuft durch den Seam, pflegt aber zusätzlich ``overview_run``)
- Lock-Verhalten (kein Lost Update) und Reentranz unter gehaltenem ``project_lock``
  (ADR-018, RLock — ``suggest_placement`` → ``evaluate_placements``)
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from fgc.project import (
    JobMutation,
    load_project,
    mutate_print_job,
    project_dir_for,
    project_lock,
    write_project,
)

PROVENANCE = {
    "source": "test",
    "created": "2026-07-09T12:00:00Z",
    "git_commit": "0000000",
}


def _base_project(
    projects_dir: Path, slug: str, *, print_jobs: list[dict] | None = None
) -> Path:
    """Schreibt ein minimales, schema-valides project.json und gibt den Ordner zurück."""
    project_dir = projects_dir / slug
    artifact = {
        "schema_version": "0.1",
        "provenance": PROVENANCE,
        "name": "Seam-Test",
        "model_path": "/tmp/model.ifc",
        "overview_run": "/tmp/runs/overview",
        "print_jobs": print_jobs if print_jobs is not None else [],
    }
    write_project(project_dir, artifact)
    return project_dir


def _job(job_id: str, **extra: object) -> dict:
    """Minimaler, schema-valider Druckjob (job_id + wall_global_id)."""
    return {"job_id": job_id, "wall_global_id": "W", **extra}


# ---------------------------------------------------------------------------
# Job-Lookup + Upsert
# ---------------------------------------------------------------------------


def test_missing_job_raises_unified_error(tmp_path: Path) -> None:
    """Fehlender Druckjob (upsert=False) → der eine, einheitliche ValueError-Text."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    called = False

    def _mutate(job: dict) -> JobMutation:  # pragma: no cover - darf nicht laufen
        nonlocal called
        called = True
        return JobMutation(job=job)

    with pytest.raises(ValueError, match="existiert nicht im Projekt"):
        mutate_print_job("proj", "fehlt", _mutate, projects_dir=projects_dir)
    # Der Mutator wird bei fehlendem Job gar nicht erst aufgerufen (Lookup zuerst).
    assert called is False


def test_missing_project_raises_file_not_found(tmp_path: Path) -> None:
    """Fehlt das Projekt selbst, meldet load_project zuerst (FileNotFoundError)."""
    projects_dir = tmp_path / "projects"
    with pytest.raises(FileNotFoundError):
        mutate_print_job(
            "gibtsnicht", "default", lambda j: JobMutation(job=j), projects_dir=projects_dir
        )


def test_upsert_creates_missing_job_at_end(tmp_path: Path) -> None:
    """upsert=True: fehlender Job → Mutator bekommt None, neuer Job kommt ans Ende."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("a"), _job("b")])

    seen: list[object] = []

    def _mutate(job: dict | None) -> JobMutation:
        seen.append(job)
        return JobMutation(job=_job("c", tool="t1"))

    outcome = mutate_print_job("proj", "c", _mutate, upsert=True, projects_dir=projects_dir)

    assert seen == [None]  # kein bestehender Job → None an den Mutator
    ids = [j["job_id"] for j in outcome.artifact["print_jobs"]]
    assert ids == ["a", "b", "c"]  # ans Ende gehängt


def test_upsert_replaces_existing_and_moves_to_end(tmp_path: Path) -> None:
    """upsert=True: gleichnamiger Alt-Job entfällt, der neue steht am Ende (wie set_print_job)."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("a"), _job("b"), _job("c")])

    def _mutate(job: dict | None) -> JobMutation:
        assert job is not None and job["job_id"] == "a"
        return JobMutation(job=_job("a", tool="neu"))

    outcome = mutate_print_job("proj", "a", _mutate, upsert=True, projects_dir=projects_dir)

    jobs = outcome.artifact["print_jobs"]
    assert [j["job_id"] for j in jobs] == ["b", "c", "a"]  # 'a' ans Ende gewandert
    assert jobs[-1]["tool"] == "neu"


def test_non_upsert_replaces_in_place(tmp_path: Path) -> None:
    """Ohne Upsert bleibt die Position des Jobs in der Liste erhalten."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("a"), _job("b"), _job("c")])

    def _mutate(job: dict) -> JobMutation:
        return JobMutation(job={**job, "tool": "x"})

    outcome = mutate_print_job("proj", "b", _mutate, projects_dir=projects_dir)

    jobs = outcome.artifact["print_jobs"]
    assert [j["job_id"] for j in jobs] == ["a", "b", "c"]  # Reihenfolge unverändert
    assert jobs[1]["tool"] == "x"


# ---------------------------------------------------------------------------
# Bump-Deklaration (Veraltungs-Semantik als Daten, ADR-017 / Issue #199)
# ---------------------------------------------------------------------------


def test_bump_always_increments_counter_unconditionally(tmp_path: Path) -> None:
    """bump_always=("wall",) erhöht den Zähler auch ohne Feldänderung (Rebuild-Modus)."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    def _mutate(job: dict) -> JobMutation:
        return JobMutation(job=dict(job), bump_always=("wall",))  # Job unverändert

    outcome = mutate_print_job("proj", "default", _mutate, projects_dir=projects_dir)

    inputs = outcome.artifact["print_jobs"][0]["revisions"]["inputs"]
    assert inputs["wall"] == 1  # bedingungslos, obwohl nichts anders ist
    assert inputs["tool"] == 0  # nur der deklarierte Zähler steigt


def test_bump_if_changed_bumps_on_change(tmp_path: Path) -> None:
    """bump_if_changed: eine tatsächliche Änderung am beobachteten Pfad bumpt."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    def _mutate(job: dict) -> JobMutation:
        return JobMutation(
            job={**job, "tool": "t1"}, bump_if_changed={"tool": ("tool",)}
        )

    outcome = mutate_print_job("proj", "default", _mutate, projects_dir=projects_dir)

    inputs = outcome.artifact["print_jobs"][0]["revisions"]["inputs"]
    assert inputs["tool"] == 1
    assert inputs["wall"] == 0


def test_bump_if_changed_is_echo_fest(tmp_path: Path) -> None:
    """Echo-Schreiben (gleicher Wert) bumpt nicht — das Diff rechnet der Seam (#199)."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default", tool="t1")])

    def _mutate(job: dict) -> JobMutation:
        return JobMutation(
            job={**job, "tool": "t1"}, bump_if_changed={"tool": ("tool",)}
        )

    outcome = mutate_print_job("proj", "default", _mutate, projects_dir=projects_dir)

    job = outcome.artifact["print_jobs"][0]
    assert job["tool"] == "t1"
    assert "revisions" not in job  # kein Bump → keine Revisionsstände angelegt


def test_bump_if_changed_walks_dotted_paths(tmp_path: Path) -> None:
    """Gepunktete Pfade beobachten verschachtelte Gruppen; leer == nicht gesetzt."""
    projects_dir = tmp_path / "projects"
    _base_project(
        projects_dir, "proj",
        print_jobs=[_job("default", process_params={"slice": {"layer_height_mm": 8.0}})],
    )
    paths = ("process_params.slice", "process_params.orientation")

    # Echo: identische Gruppe + fehlende Orientierung (None wie {}) → kein Bump.
    outcome = mutate_print_job(
        "proj", "default",
        lambda j: JobMutation(job=dict(j), bump_if_changed={"process": paths}),
        projects_dir=projects_dir,
    )
    assert "revisions" not in outcome.artifact["print_jobs"][0]

    # Änderung in der beobachteten Untergruppe → Bump.
    outcome = mutate_print_job(
        "proj", "default",
        lambda j: JobMutation(
            job={**j, "process_params": {"slice": {"layer_height_mm": 9.0}}},
            bump_if_changed={"process": paths},
        ),
        projects_dir=projects_dir,
    )
    assert outcome.artifact["print_jobs"][0]["revisions"]["inputs"]["process"] == 1


def test_no_bump_leaves_revisions_absent(tmp_path: Path) -> None:
    """Leere Bump-Deklaration = „BEWUSST kein Bump": kein revisions-Feld entsteht."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    def _mutate(job: dict) -> JobMutation:
        return JobMutation(job={**job, "stand_mode": "floor"})

    outcome = mutate_print_job("proj", "default", _mutate, projects_dir=projects_dir)

    job = outcome.artifact["print_jobs"][0]
    assert job["stand_mode"] == "floor"
    assert "revisions" not in job  # nichts veraltet → keine Revisionsstände angelegt


def test_unknown_declared_input_raises_even_without_change(tmp_path: Path) -> None:
    """Ein Tippfehler in der Deklaration fällt sofort auf — nicht erst beim Wechsel."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    with pytest.raises(ValueError, match="Unbekannte Eingabe-Stufe"):
        mutate_print_job(
            "proj", "default",
            lambda j: JobMutation(job=dict(j), bump_if_changed={"tippfehler": ("tool",)}),
            projects_dir=projects_dir,
        )


def test_section_diff_dict_keyed_bumps_only_changed(tmp_path: Path) -> None:
    """Dict-Form (process_params.sections): nur geänderte section_ids bumpen (Issue #83)."""
    projects_dir = tmp_path / "projects"
    sections = {"s1": {"slice": {"layer_height_mm": 6.0}}, "s2": {"slice": {"n_shells": 3}}}
    _base_project(
        projects_dir, "proj",
        print_jobs=[_job("default", process_params={"sections": sections})],
    )

    new_sections = {"s1": {"slice": {"layer_height_mm": 7.0}}, "s2": {"slice": {"n_shells": 3}}}
    outcome = mutate_print_job(
        "proj", "default",
        lambda j: JobMutation(
            job={**j, "process_params": {"sections": new_sections}},
            bump_sections_if_changed="process_params.sections",
        ),
        projects_dir=projects_dir,
    )
    section_inputs = outcome.artifact["print_jobs"][0]["revisions"]["section_inputs"]
    assert section_inputs == {"s1": 1}  # s2 unverändert → kein Zähler


def test_section_diff_list_keyed_ignores_order_and_detects_removal(tmp_path: Path) -> None:
    """Listen-Form (section_overrides): Reihenfolge egal; Entfernen eines Eintrags bumpt."""
    projects_dir = tmp_path / "projects"
    overrides = [
        {"section_id": "s1", "standoff_mm": 800.0},
        {"section_id": "s2", "lateral_mm": 100.0},
    ]
    _base_project(
        projects_dir, "proj",
        print_jobs=[_job("default", section_overrides=overrides)],
    )

    # Nur umsortiert (Inhalt identisch) → kein Bump.
    outcome = mutate_print_job(
        "proj", "default",
        lambda j: JobMutation(
            job={**j, "section_overrides": list(reversed(j["section_overrides"]))},
            bump_sections_if_changed="section_overrides",
        ),
        projects_dir=projects_dir,
    )
    assert "revisions" not in outcome.artifact["print_jobs"][0]

    # Eintrag s1 entfernt → nur s1 bumpt.
    outcome = mutate_print_job(
        "proj", "default",
        lambda j: JobMutation(
            job={**j, "section_overrides": [{"section_id": "s2", "lateral_mm": 100.0}]},
            bump_sections_if_changed="section_overrides",
        ),
        projects_dir=projects_dir,
    )
    section_inputs = outcome.artifact["print_jobs"][0]["revisions"]["section_inputs"]
    assert section_inputs == {"s1": 1}


# ---------------------------------------------------------------------------
# missing_ok + artifact_updates (Issue #199: set_robot durch den Seam)
# ---------------------------------------------------------------------------


def test_missing_ok_writes_artifact_updates_without_job(tmp_path: Path) -> None:
    """missing_ok: fehlender Druckjob ist kein Fehler — artifact_updates landen trotzdem."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("andere")])

    called = False

    def _mutate(job: dict) -> JobMutation:  # pragma: no cover - darf nicht laufen
        nonlocal called
        called = True
        return JobMutation(job=job)

    outcome = mutate_print_job(
        "proj", "fehlt", _mutate,
        missing_ok=True,
        artifact_updates={"overview_run": "/tmp/runs/neu"},
        projects_dir=projects_dir,
    )
    assert called is False  # Mutator läuft ohne Job nicht
    assert outcome.befund is None
    assert outcome.artifact["overview_run"] == "/tmp/runs/neu"
    # Druckjob-Liste unangetastet und persistiert.
    reloaded = load_project(project_dir_for("proj", projects_dir=projects_dir))
    assert [j["job_id"] for j in reloaded["print_jobs"]] == ["andere"]
    assert reloaded["overview_run"] == "/tmp/runs/neu"


def test_artifact_updates_merge_alongside_job_mutation(tmp_path: Path) -> None:
    """artifact_updates + Job-Mutation in einem Schreiben (reassess-Muster, #199)."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    outcome = mutate_print_job(
        "proj", "default",
        lambda j: JobMutation(job={**j, "robot": "m1013"}, bump_always=("robot",)),
        artifact_updates={"overview_run": "/tmp/runs/neu"},
        projects_dir=projects_dir,
    )
    assert outcome.artifact["overview_run"] == "/tmp/runs/neu"
    job = outcome.artifact["print_jobs"][0]
    assert job["robot"] == "m1013"
    assert job["revisions"]["inputs"]["robot"] == 1


# ---------------------------------------------------------------------------
# Befund-Rückkanal
# ---------------------------------------------------------------------------


def test_befund_channel_passes_through(tmp_path: Path) -> None:
    """Der Mutator-Befund reist unverändert im MutationOutcome heraus (kein Gate)."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    def _mutate(job: dict) -> JobMutation:
        return JobMutation(job=job, befund=(True, 3.5))

    outcome = mutate_print_job("proj", "default", _mutate, projects_dir=projects_dir)
    assert outcome.befund == (True, 3.5)


def test_befund_defaults_to_none(tmp_path: Path) -> None:
    """Ohne Befund ist outcome.befund None (Setter ohne Befund wie select_placement)."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    outcome = mutate_print_job(
        "proj", "default", lambda j: JobMutation(job=j), projects_dir=projects_dir
    )
    assert outcome.befund is None


# ---------------------------------------------------------------------------
# Persistenz: der geschriebene Stand liegt validiert auf Platte
# ---------------------------------------------------------------------------


def test_write_is_persisted_and_valid(tmp_path: Path) -> None:
    """Der zurückgegebene artifact-Stand ist auch von Platte ladbar (schema-valide)."""
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    outcome = mutate_print_job(
        "proj", "default",
        lambda j: JobMutation(job={**j, "tool": "t1"}, bump_if_changed={"tool": ("tool",)}),
        projects_dir=projects_dir,
    )
    reloaded = load_project(project_dir_for("proj", projects_dir=projects_dir))
    assert reloaded == outcome.artifact
    assert reloaded["print_jobs"][0]["tool"] == "t1"


# ---------------------------------------------------------------------------
# Lock-Verhalten (ADR-018): Serialisierung + Reentranz
# ---------------------------------------------------------------------------


def test_lock_serializes_concurrent_mutations(tmp_path: Path) -> None:
    """N×M nebenläufige Bumps unter dem Seam → exakt N×M (kein Lost Update).

    Jeder Aufruf liest → bumpt den 'wall'-Zähler → schreibt. Ohne die
    Serialisierung im Seam überschrieben sich die Writes; mit dem (einen)
    ``project_lock`` überlebt jeder Bump.
    """
    projects_dir = tmp_path / "projects"
    _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    n_threads, per_thread = 8, 5

    def worker() -> None:
        for _ in range(per_thread):
            mutate_print_job(
                "proj", "default",
                lambda j: JobMutation(job=j, bump_always=("wall",)),
                projects_dir=projects_dir,
            )

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = load_project(project_dir_for("proj", projects_dir=projects_dir))
    assert final["print_jobs"][0]["revisions"]["inputs"]["wall"] == n_threads * per_thread


def test_reentrant_under_held_project_lock(tmp_path: Path) -> None:
    """Reentranz (RLock): der Seam funktioniert, während der Aufrufer den Lock hält.

    Spiegelt die Delegation ``suggest_placement`` → ``evaluate_placements``
    (ADR-018): der äußere Kontext hält ``project_lock``, der Seam nimmt ihn erneut —
    mit einem einfachen ``Lock`` wäre das ein Selbst-Deadlock.
    """
    projects_dir = tmp_path / "projects"
    project_dir = _base_project(projects_dir, "proj", print_jobs=[_job("default")])

    with project_lock(project_dir):
        outcome = mutate_print_job(
            "proj", "default",
            lambda j: JobMutation(job={**j, "tool": "t1"}, bump_if_changed={"tool": ("tool",)}),
            projects_dir=projects_dir,
        )

    assert outcome.artifact["print_jobs"][0]["tool"] == "t1"
