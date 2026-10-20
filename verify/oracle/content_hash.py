"""Inhalts-Schluessel fuer Teile mit identischen Pruefeingaben (check_run, fake_drcf).

Zwei Teile liefern identische Pruefergebnisse, wenn alle Eingaben der Pruefung je Teil gleich sind.
Ausgenommen sind nur Werte, die die Pruefung je Teil nicht liest (nur ihr Vorhandensein):
- `part_id` in `trajectory.json`/`toolpath.json` (der Wert wird ersetzt, der Schluessel bleibt Teil des
  Hashes),
- `part_id`, `wall_id`, `T_LP` in `part.json` (gehen nur in die Wandpruefung ein, die mit den Daten
  jedes einzelnen Teils laeuft),
- reine Kommentarzeilen im DRL-Text (sie werden durch Leerzeilen ersetzt, Zeilennummern bleiben).
Jede andere Abweichung, auch ein einzelnes Byte, ergibt einen anderen Schluessel. Hardlinks werden
ueber (Geraet, Inode, Groesse, mtime) nur einmal gelesen.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

_PART_ID = re.compile(rb'"part_id"\s*:\s*"(?:[^"\\]|\\.)*"')
_PART_IGNORED = ("part_id", "wall_id", "T_LP")
_FILE_CACHE: dict[tuple, str] = {}


def _cached(path: Path, kind: str, fn) -> str:
    st = os.stat(path)
    key = (kind, st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    if key not in _FILE_CACHE:
        _FILE_CACHE[key] = fn(path)
    return _FILE_CACHE[key]


def _raw(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    return h.hexdigest()


def _without_part_id(path: Path) -> str:
    return hashlib.sha256(_PART_ID.sub(b'"part_id":"*"', Path(path).read_bytes())).hexdigest()


def _part_json(path: Path) -> str:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(obj, dict):
        obj = {k: ("*" if k in _PART_IGNORED else v) for k, v in obj.items()}
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _drl(path: Path) -> str:
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    text = "\n".join("" if ln.lstrip().startswith("#") else ln for ln in lines)
    return hashlib.sha256(text.encode()).hexdigest()


def trajectory_key(path: Path) -> str:
    return _cached(path, "traj", _without_part_id)


def toolpath_key(path: Path) -> str:
    return _cached(path, "tp", _without_part_id)


def drl_key(path: Path) -> str:
    return _cached(path, "drl", _drl)


def part_key(pdir: Path) -> str | None:
    """Schluessel der Pruefeingaben je Teil; None, wenn eine Datei fehlt oder unlesbar ist (dann wird
    das Teil einzeln geprueft)."""
    pdir = Path(pdir)
    try:
        parts = [_cached(pdir / "part.json", "part", _part_json),
                 _cached(pdir / "part.stl", "raw", _raw),
                 toolpath_key(pdir / "toolpath.json"),
                 trajectory_key(pdir / "trajectory.json")]
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def retag(messages: list[str], src: str, dst: str) -> list[str]:
    """Fehlertexte des Repraesentanten auf das Duplikat umschreiben."""
    return [m.replace(src, dst) for m in messages]
