"""Fake-Pipeline fuer API-Tests (wird im Spawn-Kindprozess importiert)."""

import json
import time
from pathlib import Path


def fast(path: Path, out: Path, jobs: int = 1, progress=None) -> int:
    scen = json.loads(Path(path).read_text(encoding="utf-8"))
    progress("decompose", 0.25, "zerlege")
    progress("plan", 0.75, "Teil 1/1")
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps({"scenario": scen["id"]}), encoding="utf-8")
    (out / "hello.txt").write_text("hi", encoding="utf-8")
    return 0


def slow(path: Path, out: Path, jobs: int = 1, progress=None) -> int:
    progress("plan", 0.3, "rechne")
    time.sleep(60)
    return 0


def broken(path: Path, out: Path, jobs: int = 1, progress=None) -> int:
    raise ValueError("kaputt")
