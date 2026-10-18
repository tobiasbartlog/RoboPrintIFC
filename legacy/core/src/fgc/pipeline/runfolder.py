"""Laufordner unter runs/ (ADR-004): ein Ordner je Pipeline-Lauf.

Ein Lauf ist mehr als eine Konvention: das `Run`-Objekt besitzt Laufordner
UND den einmal gestempelten Provenienzblock zusammen. Es kapselt die früher
offen ausgecodete Sequenz create_run_dir -> make_provenance -> write_artifact,
sodass Aufrufer (CLI, Wizard, später die lokale API aus ADR-014) nur noch
`Run.create(...)` und `run.write(...)` sehen.

Jedes Artefakt wird beim Schreiben gegen sein Schema validiert — ungültige
Artefakte verlassen die Pipeline nie.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fgc import domain
from fgc.paths import RUNS_DIR
from fgc.pipeline.provenance import make_provenance


@dataclass
class Run:
    """Ein Pipeline-Lauf: Laufordner + einmal gestempelte Provenienz (ADR-004).

    Bündelt, was bisher als lose Locals (run_dir, provenance) durch die
    Aufrufer gereicht wurde. Artefakt-Konstruktoren (candidates_artifact,
    Toolpath.to_artifact, context_artifact) betten den Provenienzblock weiter
    selbst ein — sie bekommen `run.provenance` als Parameter.
    """

    dir: Path
    provenance: dict[str, Any]

    @classmethod
    def create(
        cls,
        command: str,
        label: str = "",
        *,
        source: str,
        runs_dir: Path | None = None,
    ) -> Run:
        """Legt den Laufordner an und stempelt die Provenienz genau einmal.

        `source` = reproduzierbarer Aufruf für den Provenienzblock. `runs_dir`
        überschreibt das Standard-`runs/`-Verzeichnis (Test-Seam); ohne Angabe
        gilt das Modul-Global RUNS_DIR (monkeypatchbar).
        """
        run_dir = create_run_dir(command, label, runs_dir=runs_dir)
        return cls(dir=run_dir, provenance=make_provenance(source))

    def write(self, kind: str, artifact: dict[str, Any]) -> Path:
        """Validiert gegen schemas/<kind>.schema.json und schreibt <kind>.json."""
        return write_artifact(self.dir, kind, artifact)


def create_run_dir(command: str, label: str = "", runs_dir: Path | None = None) -> Path:
    base = runs_dir or RUNS_DIR
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}_{command}" + (f"_{label}" if label else "")
    run_dir = base / name
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{name}-{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True)
    return run_dir


def write_artifact(run_dir: Path, kind: str, artifact: dict[str, Any]) -> Path:
    """Validiert gegen schemas/<kind>.schema.json und schreibt <kind>.json.

    ``allow_nan=False``: NaN/Infinity sind **kein gültiges JSON** (RFC 8259) — der
    Python-Default würde sie als Literale ``NaN``/``Infinity`` schreiben, an denen
    jeder strenge Parser (u. a. der Browser-``JSON.parse`` des Viewers) scheitert.
    Wir lassen das Schreiben stattdessen laut mit ``ValueError`` fehlschlagen, damit
    ein numerischer Bug am Entstehungsort auffällt statt still eine unladbare Datei
    auszuliefern (Lehre aus dem #62-NaN in trajectory.json).
    """
    domain.validate(artifact, kind)
    path = run_dir / f"{kind}.json"
    path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    return path
