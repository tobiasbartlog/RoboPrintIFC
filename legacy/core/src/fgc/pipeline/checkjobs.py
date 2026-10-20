"""In-Process-Hintergrundlauf der Stufe-2-Prüf-Tür (Issue #175).

Die entkoppelte Druckbarkeitsprüfung (:func:`fgc.pipeline.actions.check_decomposition`)
läuft hier **asynchron mit Fortschritt und Abbruch** — nach dem Muster des bestehenden,
synchronen Aktions-Ausführungsmodells (ADR-014/018), aber in einem Hintergrund-Thread,
damit der Editor nicht blockiert und ein laufender Prüflauf abbrechbar ist.

**Warum ein eigener Registry-Thread statt FastAPI-``BackgroundTasks``:** letztere laufen
*nach* der Antwort und haben **keinen** Fortschritts-/Abbruch-Griff. Der Viewer braucht
beides (Fortschrittsanzeige + „Abbrechen") — also ein kleiner In-Process-Registry:
``start`` spawnt einen Thread und gibt sofort eine ``check_id`` zurück; ``get`` liefert
den Fortschritt; ``cancel`` setzt das Abbruch-Signal. Single-Process wie der Projekt-Lock
(ADR-018): ein Core-Prozess je GUI, ein prozessweiter Registry genügt.

**Sperre nicht durchgehend gehalten** (Akzeptanzkriterium): die eigentliche Rechnung in
``check_decomposition`` hält die Projekt-Sperre nur an den kurzen Lade-/Schreib-Rändern —
der Hintergrund-Thread ändert daran nichts, er verlagert sie nur aus dem Request-Pfad.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

#: Zustände eines Hintergrund-Prüflaufs (Spiegel von ``CheckDecompositionResult.state``
#: plus ``"running"``/``"error"``). Der Viewer poll't ``get`` und zeigt sie an.
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_CANCELLED = "cancelled"
STATE_SUPERSEDED = "superseded"
STATE_EMPTY = "empty"
STATE_ERROR = "error"


@dataclass
class CheckJob:
    """Ein laufender/abgeschlossener Hintergrund-Prüflauf (Issue #175)."""

    id: str
    slug: str
    job_id: str
    scope: str
    section_id: str | None
    n_total: int = 0
    n_done: int = 0
    state: str = STATE_RUNNING
    error: str | None = None
    #: Bei ``done``: die Sektionen (mit frischer ``printability``) + ``print_jobs``
    #: für den Viewer, damit er ohne Nachladen aktualisiert.
    sections: list[dict] | None = None
    print_jobs: list[dict] | None = None
    n_computed: int = 0
    n_cached: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.id,
            "slug": self.slug,
            "job_id": self.job_id,
            "scope": self.scope,
            "section_id": self.section_id,
            "state": self.state,
            "n_total": self.n_total,
            "n_done": self.n_done,
            "n_computed": self.n_computed,
            "n_cached": self.n_cached,
            "error": self.error,
            "sections": self.sections,
            "print_jobs": self.print_jobs,
        }


_JOBS: dict[str, CheckJob] = {}
_LATEST: dict[tuple[str, str], str] = {}
_REGISTRY_LOCK = threading.Lock()


def _register(job: CheckJob) -> None:
    with _REGISTRY_LOCK:
        _JOBS[job.id] = job
        # Ältere Läufe desselben (Projekt, Druckjob) automatisch abbrechen — ein neuer
        # Anstoß (z. B. Fokus → global) löst den vorigen ab (kein Doppel-Schreiben).
        prev_id = _LATEST.get((job.slug, job.job_id))
        if prev_id and prev_id in _JOBS:
            _JOBS[prev_id]._cancel.set()
        _LATEST[(job.slug, job.job_id)] = job.id
        # Registry gegen unbegrenztes Wachsen deckeln: abgeschlossene Altläufe verwerfen.
        _evict_finished_locked()


def _evict_finished_locked(keep: int = 32) -> None:
    finished = [j for j in _JOBS.values() if j.finished_at is not None]
    if len(finished) <= keep:
        return
    finished.sort(key=lambda j: j.finished_at or 0.0)
    for old in finished[: len(finished) - keep]:
        _JOBS.pop(old.id, None)


def start(
    slug: str,
    job_id: str,
    *,
    focus_section_id: str | None = None,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    workstations_dir: Path | None = None,
) -> CheckJob:
    """Startet einen Hintergrund-Prüflauf und gibt **sofort** den Griff zurück (Issue #175).

    Der eigentliche :func:`fgc.pipeline.actions.check_decomposition` läuft in einem
    Daemon-Thread; ``on_scope``/``on_progress``/``should_cancel`` verdrahten den
    Fortschritt und das Abbruch-Signal auf den ``CheckJob``.
    """
    from fgc.pipeline.actions import check_decomposition

    scope = "focus" if focus_section_id else "global"
    job = CheckJob(
        id=uuid.uuid4().hex, slug=slug, job_id=job_id,
        scope=scope, section_id=focus_section_id,
    )
    _register(job)

    source = (
        f"background decomposition-check slug={slug} job_id={job_id} scope={scope}"
    )

    def _run() -> None:
        try:
            result = check_decomposition(
                slug, source, job_id,
                focus_section_id=focus_section_id,
                on_scope=lambda n: setattr(job, "n_total", int(n)),
                on_progress=lambda d, t: (
                    setattr(job, "n_done", int(d)), setattr(job, "n_total", int(t))
                ),
                should_cancel=job.cancelled,
                projects_dir=projects_dir,
                runs_dir=runs_dir,
                workstations_dir=workstations_dir,
            )
            job.n_computed = result.stats.n_computed
            job.n_cached = result.stats.n_cached
            if result.state == "done" and result.result is not None:
                job.sections = result.result.sections
                job.print_jobs = result.result.artifact["print_jobs"]
                job.state = STATE_DONE
            elif result.state == "cancelled":
                job.state = STATE_CANCELLED
            elif result.state == "superseded":
                job.state = STATE_SUPERSEDED
            else:  # "empty"
                job.state = STATE_EMPTY
        except Exception as exc:  # noqa: BLE001 — Fehler sichtbar melden, nie den Thread verschlucken
            _LOG.warning("Hintergrund-Prüflauf %s fehlgeschlagen", job.id, exc_info=True)
            job.state = STATE_ERROR
            job.error = str(exc)
        finally:
            job.finished_at = time.time()

    threading.Thread(target=_run, name=f"pruef-check-{job.id[:8]}", daemon=True).start()
    return job


def get(check_id: str) -> CheckJob | None:
    """Liefert den Griff eines Prüflaufs (Fortschritt/Zustand) oder ``None``."""
    with _REGISTRY_LOCK:
        return _JOBS.get(check_id)


def cancel(check_id: str) -> bool:
    """Setzt das Abbruch-Signal eines Prüflaufs; ``True``, wenn er existiert."""
    with _REGISTRY_LOCK:
        job = _JOBS.get(check_id)
    if job is None:
        return False
    job._cancel.set()
    return True


def reset() -> None:
    """Leert den Registry (Testhilfe)."""
    with _REGISTRY_LOCK:
        for j in _JOBS.values():
            j._cancel.set()
        _JOBS.clear()
        _LATEST.clear()
        for bj in _BEAM_JOBS.values():
            bj._cancel.set()
        _BEAM_JOBS.clear()


# --------------------------------------------------------------------------- #
# Beam-Suche als Hintergrundlauf (Issue #217, PRD #183 Stufe 3)
# --------------------------------------------------------------------------- #


@dataclass
class BeamProposeJob:
    """Ein laufender/abgeschlossener Beam-Zerlegungslauf (Issue #217).

    ``n_done``/``n_total`` = verbrauchte / erlaubte Pruef-Tuer-Aufrufe (das
    Aufruf-Kontingent #215 — Fortschritt in **Aufrufen**, nicht in Sekunden). Bei
    ``done`` liegen die Sektionen + ``print_jobs`` + ``run_dir`` fuer den Viewer bereit.
    """

    id: str
    slug: str
    job_id: str
    n_total: int = 0
    n_done: int = 0
    state: str = STATE_RUNNING
    error: str | None = None
    sections: list[dict] | None = None
    print_jobs: list[dict] | None = None
    run_dir: str | None = None
    #: Bei ``done``: der ``refinement``-Block des Sieger-Laufs (verbatim aus
    #: decompose.json) — Strategie/Kontingent, **Verworfen-Gründe** (US 10),
    #: **Relaxationsausweis** (US 22) und der **Metriken-Katalog** (US 20). So
    #: kann der Viewer den Such-Ausweis direkt aus der Poll-Antwort speisen
    #: (`refinement-state.ts`), ohne den Lauf getrennt nachzuladen. ``None``,
    #: solange die Suche läuft oder wenn der Beam fail-soft auf den Greedy fiel.
    refinement: dict | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "beam_id": self.id,
            "slug": self.slug,
            "job_id": self.job_id,
            "state": self.state,
            "n_total": self.n_total,
            "n_done": self.n_done,
            "error": self.error,
            "run_dir": self.run_dir,
            "sections": self.sections,
            "print_jobs": self.print_jobs,
            "refinement": self.refinement,
        }


_BEAM_JOBS: dict[str, BeamProposeJob] = {}
_BEAM_LATEST: dict[tuple[str, str], str] = {}


def _read_refinement(run_dir: Path) -> dict | None:
    """Liest den ``refinement``-Block aus ``<run_dir>/decompose.json`` (fail-soft).

    Der Sieger-Lauf der Beam-Suche persistiert Strategie/Kontingent, Verworfen-Gründe
    (US 10), Relaxationsausweis (US 22) und Metriken (US 20) im ``refinement``-Block
    (siehe :mod:`fgc.decompose.artifact`). Wir reichen ihn verbatim in die Poll-Antwort
    durch, damit der Viewer den Ausweis ohne getrenntes Nachladen zeigt. Fehlt die
    Datei/der Block oder ist er unlesbar, ``None`` — ein Befund, kein Gate.
    """
    import json

    try:
        doc = json.loads((run_dir / "decompose.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ref = doc.get("refinement")
    return ref if isinstance(ref, dict) else None


def start_beam_propose(
    slug: str,
    job_id: str = "default",
    *,
    call_budget: int | None = None,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    workstations_dir: Path | None = None,
    robots_dir: Path | None = None,
) -> BeamProposeJob:
    """Startet die **Beam-Suche** als Hintergrundlauf und gibt sofort den Griff zurück.

    Fährt :func:`fgc.pipeline.actions.propose_decomposition` mit ``beam_search=True``
    in einem Daemon-Thread; ``on_progress``/``should_cancel`` verdrahten Fortschritt
    (verbrauchte Aufrufe) und Abbruch auf den :class:`BeamProposeJob` — dasselbe
    Muster wie :func:`start` (#175). Ein neuer Anstoß desselben (Projekt, Druckjob)
    bricht den vorigen ab. **Kein neuer HTTP-Stack** — der Aufrufer (künftige Route/
    Viewer-Trigger) poll't :func:`get_beam_propose` und ruft :func:`cancel_beam_propose`.
    """
    from fgc.pipeline.actions import propose_decomposition

    job = BeamProposeJob(id=uuid.uuid4().hex, slug=slug, job_id=job_id)
    with _REGISTRY_LOCK:
        _BEAM_JOBS[job.id] = job
        prev = _BEAM_LATEST.get((slug, job_id))
        if prev and prev in _BEAM_JOBS:
            _BEAM_JOBS[prev]._cancel.set()
        _BEAM_LATEST[(slug, job_id)] = job.id

    source = f"background beam-propose slug={slug} job_id={job_id}"

    def _run() -> None:
        try:
            result = propose_decomposition(
                slug, source, job_id,
                beam_search=True,
                call_budget=call_budget,
                on_progress=lambda d, t: (
                    setattr(job, "n_done", int(d)), setattr(job, "n_total", int(t))
                ),
                should_cancel=job.cancelled,
                projects_dir=projects_dir,
                runs_dir=runs_dir,
                workstations_dir=workstations_dir,
                robots_dir=robots_dir,
            )
            job.sections = result.sections
            job.print_jobs = result.artifact["print_jobs"]
            job.run_dir = str(result.run_dir)
            # Such-Ausweis (Verworfen-Gründe/Metriken/Relaxation) verbatim aus dem
            # Sieger-Lauf (decompose.json) nachladen — fail-soft: fehlt der Block
            # (Beam fiel auf den Greedy) oder ist er unlesbar, bleibt es bei ``None``
            # (Befund, kein Gate). Kein zweiter Rechenschritt, nur ein Datei-Lesen.
            job.refinement = _read_refinement(result.run_dir)
            job.state = STATE_CANCELLED if job.cancelled() else STATE_DONE
        except Exception as exc:  # noqa: BLE001 — Fehler sichtbar melden, nie den Thread verschlucken
            _LOG.warning("Hintergrund-Beam-Lauf %s fehlgeschlagen", job.id, exc_info=True)
            job.state = STATE_ERROR
            job.error = str(exc)
        finally:
            job.finished_at = time.time()

    threading.Thread(target=_run, name=f"beam-propose-{job.id[:8]}", daemon=True).start()
    return job


def get_beam_propose(beam_id: str) -> BeamProposeJob | None:
    """Liefert den Griff eines Beam-Laufs (Fortschritt/Zustand) oder ``None``."""
    with _REGISTRY_LOCK:
        return _BEAM_JOBS.get(beam_id)


def cancel_beam_propose(beam_id: str) -> bool:
    """Setzt das Abbruch-Signal eines Beam-Laufs; ``True``, wenn er existiert."""
    with _REGISTRY_LOCK:
        job = _BEAM_JOBS.get(beam_id)
    if job is None:
        return False
    job._cancel.set()
    return True
