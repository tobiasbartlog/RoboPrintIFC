"""Provenienzblock für Artefakte (P2, ADR-004) — ab dem allerersten Lauf."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import Any

from fgc.paths import REPO_ROOT


def make_provenance(source: str) -> dict[str, Any]:
    """source = reproduzierbarer Aufruf, z. B. 'fgc slice model.ifc --wall <id>'."""
    return {
        "source": source,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
    }


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"
