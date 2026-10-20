"""Zentrale Repo-Pfade — die eine Stelle, die das Monorepo-Layout kennt.

Im installierten Zustand (Wheel statt editable) müssen diese Pfade später als
Paketdaten bzw. Konfiguration kommen; bis dahin gilt das Layout aus §10 der
Architektur.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

SCHEMA_DIR = REPO_ROOT / "schemas"
ROBOTS_DIR = REPO_ROOT / "robots"
TOOLS_DIR = REPO_ROOT / "tools"
WORKSTATIONS_DIR = REPO_ROOT / "workstations"
MATERIALCARDS_DIR = REPO_ROOT / "materialcards"
#: Versionierte Prior-Tabellen (Platzierungs-Messwissen, ADR-026 Punkt 3, #230),
#: geschluesselt auf Roboter+Tool: ``placement_prior.<robot>.<tool>.json``.
PRIORS_DIR = REPO_ROOT / "priors"
RUNS_DIR = REPO_ROOT / "runs"
PROJECTS_DIR = REPO_ROOT / "projects"
EXAMPLES_DIR = REPO_ROOT / "examples"
VIEWER_DIR = REPO_ROOT / "viewer"

PROCESS_WINDOW_CARD = MATERIALCARDS_DIR / "process_window.provisional.json"
