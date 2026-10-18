"""PreToolUse-Hook fuer den Nachtlauf (nur in der Cloud-Session aktiv).

1. Sperre: Sobald spec/LOCKED existiert, sind Aenderungen an spec/ und verify/ blockiert.
   Einwaende gegen ein Gate gehoeren nach PROGRESS.md (siehe spec/NACHTLAUF.md).
2. Git-Schutz: kein Push auf main, kein Force-Push, kein PR-Merge.

Exit-Code 2 blockiert den Aufruf, stderr geht als Begruendung an Claude zurueck.
"""

import json
import os
import re
import sys
from pathlib import Path

if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
    sys.exit(0)

try:
    event = json.load(sys.stdin)
except Exception:  # noqa: BLE001 - ohne lesbare Eingabe nichts blockieren
    sys.exit(0)

root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
tool = event.get("tool_name", "")
inp = event.get("tool_input", {}) or {}


def block(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(2)


def locked_path(path: str) -> bool:
    try:
        rel = Path(path).resolve().relative_to(root)
    except ValueError:
        return False
    parts = rel.parts
    return bool(parts) and parts[0] in ("spec", "verify")


if (root / "spec" / "LOCKED").exists():
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if path and locked_path(path):
            block("spec/ und verify/ sind seit Ende P0 gesperrt (spec/LOCKED). "
                  "Trage den Einwand mit Belegen unter 'Gate-Einwaende' in PROGRESS.md ein "
                  "und arbeite an anderem weiter.")
    if tool == "Bash":
        cmd = inp.get("command", "")
        target = r"(\.\/)?(spec|verify)/"
        writes = (
            rf">>?\s*{target}",
            rf"\bsed\s+-i\b.*(^|\s){target}",
            rf"\btee\b.*(^|\s){target}",
            rf"\b(rm|mv|cp)\b.*(^|\s){target}",
            rf"\bgit\s+(checkout|restore)\b.*(^|\s){target}",
        )
        if any(re.search(p, cmd) for p in writes):
            block("Schreibender Shell-Zugriff auf spec/ oder verify/ ist seit Ende P0 gesperrt.")

if tool == "Bash":
    cmd = inp.get("command", "")
    if re.search(r"\bgit\s+push\b", cmd):
        if re.search(r"(\s--force\b|\s-f\b|\s--force-with-lease\b|\s\+\S)", cmd):
            block("Force-Push ist im Nachtlauf verboten.")
        if re.search(r"\bmain\b|\bmaster\b", cmd):
            block("Push auf main ist im Nachtlauf verboten. Ziel ist v2-nachtlauf oder v2/*.")
    if re.search(r"\bgh\s+pr\s+merge\b", cmd):
        block("PRs merged der Nutzer selbst.")

sys.exit(0)
