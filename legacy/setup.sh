#!/usr/bin/env bash
# Einmalige (und nach jedem git pull wiederholbare) Einrichtung unter Linux/macOS:
# .venv + Viewer-Deps. Idempotent - schneller No-Op, wenn nichts driftete.
#   ./setup.sh            normaler Lauf
#   ./setup.sh --force    alles neu
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/scripts/bootstrap.sh" "$@"
