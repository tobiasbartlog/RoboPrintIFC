"""Hintergrundjobs der API (SPEC §8): Prozess pro Job, Fortschritt in einer Statusdatei.

Fortschritts-Callback der Pipeline (festgelegt hier, genutzt von `pipeline.run_scenario`):

    progress(stage: str, fraction: float, message: str) -> None

`stage` ist der Name der Stufe (z. B. "ifc", "decompose", "plan", "export"), `fraction` der
Gesamtfortschritt 0..1 (monoton), `message` ein kurzer deutscher Klartext (z. B. "Teil 2/5").
Der Callback darf aus jedem Thread des Jobprozesses aufgerufen werden.

Jeder Job hat einen Ordner `<jobs_dir>/<job_id>/` mit `status.json` (atomar geschrieben) und
dem Laufordner `run/`. Der Prozess wird per `spawn` gestartet und beim Abbruch terminiert.
"""

from __future__ import annotations

import importlib
import json
import multiprocessing as mp
import os
import threading
import traceback
from pathlib import Path
from typing import Any

DEFAULT_PIPELINE = "roboprint.pipeline:run_scenario"


def write_status(job_dir: Path, status: dict[str, Any]) -> None:
    tmp = job_dir / "status.json.tmp"
    tmp.write_text(json.dumps(status), encoding="utf-8")
    os.replace(tmp, job_dir / "status.json")


def read_status(job_dir: Path) -> dict[str, Any] | None:
    try:
        return json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _resolve(target: str) -> Any:
    module, _, func = target.partition(":")
    return getattr(importlib.import_module(module), func)


def _job_main(job_dir_s: str, scenario_s: str, root_s: str, target: str, run_id: str) -> None:
    """Einstieg im Kindprozess."""
    job_dir = Path(job_dir_s)
    lock = threading.Lock()
    state: dict[str, Any] = {
        "state": "running",
        "progress": 0.0,
        "stage": None,
        "message": None,
        "run_id": None,
    }

    def progress(stage: str, fraction: float, message: str = "") -> None:
        with lock:
            state.update(
                progress=min(1.0, max(float(fraction), float(state["progress"]))),
                stage=stage,
                message=message,
            )
            write_status(job_dir, state)

    write_status(job_dir, state)
    try:
        os.chdir(root_s)
        result = _resolve(target)(Path(scenario_s), job_dir / "run", progress=progress)
        if int(result or 0) != 0:
            raise RuntimeError(f"Pipeline endete mit Exit-Code {result}")
        with lock:
            state.update(state="done", progress=1.0, run_id=run_id)
            write_status(job_dir, state)
    except BaseException as exc:  # noqa: BLE001 - jeder Fehler wird gemeldet
        with lock:
            state.update(state="failed", message=f"{type(exc).__name__}: {exc}")
            write_status(job_dir, state)
        traceback.print_exc()
        os._exit(1)


class JobManager:
    def __init__(self, jobs_dir: Path, root: Path, pipeline: str = DEFAULT_PIPELINE) -> None:
        self.jobs_dir = jobs_dir
        self.root = root
        self.pipeline = pipeline
        self._procs: dict[str, Any] = {}
        self._ctx = mp.get_context("spawn")

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def exists(self, job_id: str) -> bool:
        return self.job_dir(job_id).is_dir()

    def run_id(self, job_id: str) -> str:
        return f"{self.jobs_dir.name}/{job_id}/run"

    def start(self, job_id: str, scenario: dict[str, Any]) -> None:
        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        scenario_path = job_dir / "scenario.json"
        scenario_path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
        write_status(
            job_dir, {"state": "queued", "progress": 0.0, "stage": None, "message": None, "run_id": None}
        )
        proc = self._ctx.Process(
            target=_job_main,
            args=(str(job_dir), str(scenario_path), str(self.root), self.pipeline, self.run_id(job_id)),
            daemon=True,
        )
        proc.start()
        self._procs[job_id] = proc

    def state(self, job_id: str) -> dict[str, Any]:
        status = read_status(self.job_dir(job_id)) or {
            "state": "queued",
            "progress": 0.0,
            "stage": None,
            "message": None,
            "run_id": None,
        }
        proc = self._procs.get(job_id)
        if status["state"] in ("queued", "running") and proc is not None and not proc.is_alive():
            proc.join(timeout=0)
            # Endstand noch einmal lesen (Race zwischen letztem Schreiben und Prozessende).
            status = read_status(self.job_dir(job_id)) or status
            if status["state"] in ("queued", "running"):
                status = {
                    **status,
                    "state": "failed",
                    "message": f"Jobprozess beendet (Exit-Code {proc.exitcode})",
                }
                write_status(self.job_dir(job_id), status)
        return status

    def cancel(self, job_id: str) -> dict[str, Any]:
        status = self.state(job_id)
        if status["state"] in ("queued", "running"):
            proc = self._procs.get(job_id)
            if proc is not None and proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.kill()
                    proc.join(timeout=5)
            status = {**status, "state": "cancelled", "message": "Abgebrochen"}
            write_status(self.job_dir(job_id), status)
        return status

    def shutdown(self) -> None:
        for proc in self._procs.values():
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
