"""Persistenz des Projekts (ADR-016): project.json bauen, validieren, lesen, listen.

Die eine Stelle, die ``project.json`` schreibt (``write_project``): sie
validiert jedes Projekt beim Schreiben **und** beim Lesen gegen
``project.schema.json`` — ungültige Projekte verlassen die Pipeline nie
(analog zum Laufordner, ADR-004). Alle Pfade (model_path, overview_run) werden
absolut aufgelöst abgelegt, damit der Viewer sie direkt als ``/@fs/``-URL
weiterreichen kann (wie candidates.model, Issue #10).
"""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fgc import domain
from fgc.atomic_io import replace_with_retry
from fgc.paths import PROJECTS_DIR

PROJECT_FILE = "project.json"
SCHEMA_VERSION = "0.1"

#: Prozessweite Registry von Projekt-Locks (ADR-018): je aufgelöstem Projektpfad
#: genau ein ``RLock``. ``_registry_guard`` serialisiert nur das *Anlegen* eines
#: Eintrags (klein, nie über eine Read-Modify-Write-Sektion gehalten), damit zwei
#: Threads, die dasselbe Projekt zum ersten Mal anfassen, nicht zwei Locks bauen.
_project_locks: dict[str, threading.RLock] = {}
_registry_guard = threading.Lock()


@contextmanager
def project_lock(project_dir: Path) -> Iterator[None]:
    """Serialisiert die Read-Modify-Write-Sektion je Projekt (ADR-018, Issue #45).

    FastAPI führt die synchronen Aktions-Endpunkte im Threadpool aus → echte
    Nebenläufigkeit. Ohne Serialisierung lesen zwei parallele mutierende Requests
    denselben Stand, mutieren je ihre Kopie und schreiben nacheinander → **Lost
    Update** (der zweite ``write_project`` überschreibt den ersten). Jede mutierende
    Aktion umschließt darum ihre ``load_project(...) → … → write_project(...)``-
    Sektion mit ``with project_lock(project_dir):``.

    Der Lock ist ein **``RLock``** (reentrant je Thread): ``suggest_placement``
    hält den Lock und delegiert an ``evaluate_placements``, das denselben
    Projekt-Lock erneut nimmt — mit einem einfachen ``Lock`` wäre das ein
    Selbst-Deadlock. Der Schlüssel ist der ``.resolve()``-te Pfad, damit
    verschiedene Schreibweisen desselben Ordners denselben Lock treffen.

    In-Process reicht (kein Cross-Process-Filelock): der Launcher hält genau
    einen Core-Prozess auf Port 8765 (ADR-018 / ``viewer_launch``).
    """
    key = str(project_dir.resolve())
    with _registry_guard:
        lock = _project_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _project_locks[key] = lock
    with lock:
        yield


@dataclass(frozen=True)
class ProjectSummary:
    """Kurzinfo eines Projekts für die Projektliste beim GUI-Start (ADR-016).

    Trägt genug für die Liste (Ordner-Slug, Anzeigename, Modell, Zahl der
    Druckjobs) ohne den ganzen Arbeitsstand zu laden. ``slug`` ist der
    Ordnername unter ``projects/`` und zugleich die API-Kennung.
    """

    slug: str
    name: str
    model_path: str
    n_print_jobs: int
    dir: Path


def project_slug(name: str) -> str:
    """Leitet einen datei-sicheren Ordnernamen aus dem Projektnamen ab.

    Kleingeschrieben, auf ASCII normalisiert, Nicht-alphanumerisches zu ``-``.
    Leerer/degenerierter Name → ``"projekt"`` (nie ein leerer Ordnername).
    """
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    return slug or "projekt"


def project_dir_for(slug: str, *, projects_dir: Path | None = None) -> Path:
    """Projektordner zu einem Slug (Standard: ``projects/<slug>/``)."""
    base = projects_dir or PROJECTS_DIR
    return base / slug


def unique_project_dir(name: str, *, projects_dir: Path | None = None) -> Path:
    """Freier Projektordner für ``name`` — hängt ``-1``, ``-2``, … an bei Kollision."""
    base = projects_dir or PROJECTS_DIR
    slug = project_slug(name)
    project_dir = base / slug
    suffix = 1
    while project_dir.exists():
        project_dir = base / f"{slug}-{suffix}"
        suffix += 1
    return project_dir


def project_artifact(
    name: str,
    model_path: Path | str,
    overview_run: Path | str,
    provenance: dict[str, Any],
    *,
    print_jobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Baut das project.json-Artefakt (Schema-Vertrag) aus reinen Projektdaten.

    Besitzt — analog ``candidates_artifact`` — ``schema_version``, das absolute
    Auflösen der Pfade und den Feldaufbau. ``print_jobs`` ist in diesem Slice
    leer; das Datenmodell trägt die Struktur von Anfang an (ADR-016).
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": provenance,
        "name": name,
        "model_path": str(Path(model_path).resolve()),
        "overview_run": str(Path(overview_run).resolve()),
        "print_jobs": print_jobs if print_jobs is not None else [],
    }


def write_project(project_dir: Path, artifact: dict[str, Any]) -> Path:
    """Validiert gegen project.schema.json und schreibt project.json — die eine Schreibstelle.

    Der Schreibvorgang ist **atomar** (ADR-018, Issue #45): erst in eine Temp-Datei
    im selben Verzeichnis, dann per ``replace_with_retry`` einschwenken (atomarer
    Rename auf Windows/POSIX, mit kurzem Retry gegen den transienten WinError 5/32,
    Issue #158). So sieht ``load_project`` nie ein halb geschriebenes File.
    Die Schema-Validierung *vor* dem Schreiben bleibt unverändert (ADR-016).
    """
    domain.validate(artifact, "project")
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / PROJECT_FILE
    text = json.dumps(artifact, indent=2, ensure_ascii=False)
    tmp = project_dir / f".{PROJECT_FILE}.{os.getpid()}.{threading.get_ident()}.tmp"
    tmp.write_text(text, encoding="utf-8")
    replace_with_retry(tmp, path)
    return path


def load_project(project_dir: Path) -> dict[str, Any]:
    """Lädt project.json aus ``project_dir`` und validiert es gegen das Schema.

    Wirft ``FileNotFoundError``, wenn kein project.json vorliegt, und
    ``jsonschema.ValidationError`` bei einem vertragswidrigen Projekt.
    """
    path = project_dir / PROJECT_FILE
    if not path.exists():
        raise FileNotFoundError(f"Kein Projekt in {project_dir}: {PROJECT_FILE} fehlt")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    domain.validate(artifact, "project")
    return artifact


def list_projects(projects_dir: Path | None = None) -> list[ProjectSummary]:
    """Listet alle Projekte unter ``projects/`` (Standard) als ``ProjectSummary``.

    Überspringt Ordner ohne project.json und unlesbares JSON stillschweigend —
    die Liste beim GUI-Start soll robust gegen halbfertige Ordner sein. Ergebnis
    ist alphabetisch nach Slug sortiert (stabile Reihenfolge).
    """
    base = projects_dir or PROJECTS_DIR
    if not base.exists():
        return []
    summaries: list[ProjectSummary] = []
    for child in sorted(base.iterdir()):
        pf = child / PROJECT_FILE
        if not pf.is_file():
            continue
        try:
            artifact = json.loads(pf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        summaries.append(
            ProjectSummary(
                slug=child.name,
                name=str(artifact.get("name", child.name)),
                model_path=str(artifact.get("model_path", "")),
                n_print_jobs=len(artifact.get("print_jobs", [])),
                dir=child,
            )
        )
    return summaries
