"""Nebenläufigkeit der Projekt-Schreibstelle (ADR-018, Issue #45).

FastAPI führt die synchronen Aktions-Endpunkte im Threadpool aus → echte
Nebenläufigkeit auf ``project.json``. Ohne Serialisierung verlieren zwei
parallele ``load_project → mutieren → write_project``-Sektionen Updates (der
zweite Write überschreibt den ersten). Geprüft wird externes Verhalten: dass der
``project_lock`` diese Read-Modify-Write-Sektion serialisiert (kein Lost Update)
und dass ``write_project`` atomar schreibt (kein zerrissenes File).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fgc.pipeline.actions import set_print_job
from fgc.project import load_project, project_lock, write_project

PROVENANCE = {
    "source": "test",
    "created": "2026-07-05T12:00:00Z",
    "git_commit": "0000000",
}


def _counter_job() -> dict:
    """Ein Druckjob mit dem ``wall``-Revisionszähler als serialisierbarem Zählerfeld."""
    return {"job_id": "default", "wall_global_id": "W", "revisions": {"inputs": {"wall": 0}}}


def _base_project(project_dir: Path, *, print_jobs: list[dict] | None = None) -> None:
    """Schreibt ein minimales, schema-valides project.json in ``project_dir``."""
    artifact = {
        "schema_version": "0.1",
        "provenance": PROVENANCE,
        "name": "Nebenläufigkeit",
        "model_path": "/tmp/model.ifc",
        "overview_run": "/tmp/runs/overview",
        "print_jobs": print_jobs if print_jobs is not None else [],
    }
    write_project(project_dir, artifact)


def _increment_wall_revision(project_dir: Path, *, use_lock: bool, delay: float) -> None:
    """Read-Modify-Write auf den ``wall``-Zähler des ersten Druckjobs.

    ``delay`` weitet das Fenster zwischen Lesen und Schreiben auf, damit die
    Nebenläufigkeit sichtbar wird. ``use_lock`` schaltet die Serialisierung.
    """

    def body() -> None:
        artifact = load_project(project_dir)
        job = artifact["print_jobs"][0]
        current = job["revisions"]["inputs"]["wall"]
        time.sleep(delay)  # Fenster für die Verschränkung öffnen
        job = {**job, "revisions": {"inputs": {"wall": current + 1}}}
        updated = {**artifact, "print_jobs": [job]}
        write_project(project_dir, updated)

    if use_lock:
        with project_lock(project_dir):
            body()
    else:
        body()


def test_project_lock_serializes_read_modify_write(tmp_path: Path) -> None:
    """Der Fix: N Threads × M Inkremente unter ``project_lock`` → exakt N×M.

    Trotz des künstlichen Fensters (delay) zwischen Lesen und Schreiben geht kein
    Update verloren, weil der Lock die Sektion je Projekt serialisiert.
    """
    project_dir = tmp_path / "proj"
    _base_project(
        project_dir,
        print_jobs=[_counter_job()],
    )

    n_threads, per_thread = 8, 5

    def worker() -> None:
        for _ in range(per_thread):
            _increment_wall_revision(project_dir, use_lock=True, delay=0.001)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = load_project(project_dir)["print_jobs"][0]["revisions"]["inputs"]["wall"]
    assert final == n_threads * per_thread


def test_without_lock_loses_updates(tmp_path: Path) -> None:
    """Bug-Reproduktion: ohne Lock gehen Updates verloren (was der Lock verhindert).

    Alle Threads lesen an einer Barriere denselben Stand und schreiben danach —
    deterministisch ein Lost Update: der Endstand ist kleiner als die Zahl der
    Schreiber. Dieselbe Sektion *mit* Lock liefert den vollen Zählerstand
    (Test oben) — das isoliert die Wirkung des Locks.
    """
    project_dir = tmp_path / "proj"
    _base_project(
        project_dir,
        print_jobs=[_counter_job()],
    )

    n_threads = 8
    barrier = threading.Barrier(n_threads)
    # Nur das *Schreiben* serialisieren (nicht die Read-Modify-Write-Sektion) —
    # so bleibt das Lost Update aus dem veralteten Read isoliert sichtbar, ohne
    # dass zwei os.replace auf dieselbe Datei rennen (Windows-Sharing).
    write_guard = threading.Lock()

    def worker() -> None:
        artifact = load_project(project_dir)
        job = artifact["print_jobs"][0]
        current = job["revisions"]["inputs"]["wall"]
        barrier.wait()  # alle lesen v0, bevor irgendwer schreibt
        job = {**job, "revisions": {"inputs": {"wall": current + 1}}}
        with write_guard:
            write_project(project_dir, {**artifact, "print_jobs": [job]})

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = load_project(project_dir)["print_jobs"][0]["revisions"]["inputs"]["wall"]
    assert final < n_threads  # Updates gingen verloren


def test_set_print_job_concurrent_keeps_all_jobs(tmp_path: Path) -> None:
    """End-to-End: N parallele ``set_print_job`` auf dasselbe Projekt (Issue #45).

    Jeder Aufruf liest das Projekt, hängt seinen Druckjob an und schreibt zurück.
    Ohne Serialisierung überschrieben sich die Writes → nur ein Bruchteil der Jobs
    bliebe. Mit dem ``project_lock`` in ``set_print_job`` überleben **alle** N Jobs.
    """
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "proj"
    _base_project(project_dir)

    n_jobs = 10

    def worker(i: int) -> None:
        set_print_job(
            "proj",
            wall_global_id=f"WALL{i:02d}",
            assessment_run=str(tmp_path / "runs" / "overview"),
            job_id=f"job-{i}",
            projects_dir=projects_dir,
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    jobs = load_project(project_dir)["print_jobs"]
    assert {j["job_id"] for j in jobs} == {f"job-{i}" for i in range(n_jobs)}


def test_write_project_is_atomic(tmp_path: Path) -> None:
    """``write_project`` schreibt atomar: kein zurückgelassenes Temp-File, valides JSON."""
    project_dir = tmp_path / "proj"
    _base_project(project_dir)

    path = project_dir / "project.json"
    # Datei ist vollständig und valide (nicht halb geschrieben).
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["name"] == "Nebenläufigkeit"
    # Keine .tmp-Reste im Projektverzeichnis (Temp + os.replace, kein Leak).
    assert [p.name for p in project_dir.glob("*.tmp")] == []
    assert [p.name for p in project_dir.iterdir()] == ["project.json"]
