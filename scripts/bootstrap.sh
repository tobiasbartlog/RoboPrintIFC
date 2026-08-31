#!/usr/bin/env bash
# Idempotente Provisionierung (POSIX-Spiegel von scripts/bootstrap.ps1):
# .venv (Python-Deps) + viewer/node_modules (Node-Deps). Nach jedem `git pull`
# erneut ausfuehrbar; schneller No-Op, wenn nichts driftete.
#
#   ./scripts/bootstrap.sh            normaler Lauf
#   ./scripts/bootstrap.sh --force    Marker ignorieren, alles neu
#   QUIET=1 ./scripts/bootstrap.sh    nur bei Arbeit/Fehlern ausgeben
set -euo pipefail

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1
QUIET="${QUIET:-0}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"
PYPROJECT="$ROOT/core/pyproject.toml"
VIEWER="$ROOT/viewer"
LOCKFILE="$VIEWER/package-lock.json"

info() { [[ "$QUIET" == "1" ]] || echo "[setup] $*"; }
step() { echo "[setup] $*"; }
warn() { echo "[setup] $*" >&2; }
fail() { echo "[setup] FEHLER: $*" >&2; exit 1; }

hash_of() { [[ -f "$1" ]] && (sha256sum "$1" 2>/dev/null || shasum -a 256 "$1") | awk '{print $1}' || echo ""; }

# --- Python >=3.12 finden (keine bestimmte Minor erzwingen) ---
find_python() {
    for c in python3.12 python3.13 python3.14 python3 python; do
        if command -v "$c" >/dev/null 2>&1; then
            if "$c" -c "import sys; assert sys.version_info[:2] >= (3,12)" >/dev/null 2>&1; then
                echo "$c"; return 0
            fi
        fi
    done
    return 1
}

# --- 1) Python-venv + Deps ---
PY_HASH_FILE="$VENV/.deps-hash"
WANT_PY_HASH="$(hash_of "$PYPROJECT")"
HAVE_PY_HASH="$([[ -f "$PY_HASH_FILE" ]] && cat "$PY_HASH_FILE" || echo "")"

if [[ -x "$VENV_PY" && "$FORCE" == "0" && -n "$WANT_PY_HASH" && "$WANT_PY_HASH" == "$HAVE_PY_HASH" ]]; then
    info ".venv aktuell (pyproject unveraendert)."
else
    if [[ ! -x "$VENV_PY" ]]; then
        PY="$(find_python)" || fail "Kein Python >=3.12 gefunden. Bitte Python 3.12+ installieren."
        step "Lege .venv an ($("$PY" --version)) ..."
        "$PY" -m venv "$VENV"
    fi
    step "Synchronisiere Python-Abhaengigkeiten (pip install -e core[dev,geo]) ..."
    "$VENV_PY" -m pip install --upgrade pip --quiet
    "$VENV_PY" -m pip install -e "$ROOT/core[dev,geo]"
    echo "$WANT_PY_HASH" > "$PY_HASH_FILE"
    step ".venv bereit."
fi

# --- 2) Node/Viewer-Deps ---
if ! command -v npm >/dev/null 2>&1; then
    warn "npm/Node.js nicht gefunden — der Viewer braucht Node.js (nodejs.org)."
    warn "Python-Seite ist bereit; Viewer erst nach Node-Installation + erneutem setup."
else
    NODE_MODULES="$VIEWER/node_modules"
    NPM_HASH_FILE="$NODE_MODULES/.deps-hash"
    WANT_NPM_HASH="$(hash_of "$LOCKFILE")"
    HAVE_NPM_HASH="$([[ -f "$NPM_HASH_FILE" ]] && cat "$NPM_HASH_FILE" || echo "")"

    if [[ -d "$NODE_MODULES" && "$FORCE" == "0" && -n "$WANT_NPM_HASH" && "$WANT_NPM_HASH" == "$HAVE_NPM_HASH" ]]; then
        info "viewer/node_modules aktuell (package-lock unveraendert)."
    else
        (
            cd "$VIEWER"
            if [[ -f "$LOCKFILE" ]]; then
                step "Synchronisiere Node-Abhaengigkeiten (npm ci) ..."
                npm ci || { warn "npm ci fehlgeschlagen — versuche npm install ..."; npm install; }
            else
                step "Synchronisiere Node-Abhaengigkeiten (npm install) ..."
                npm install
            fi
        )
        echo "$WANT_NPM_HASH" > "$NODE_MODULES/.deps-hash"
        step "viewer/node_modules bereit."
    fi
fi

[[ "$QUIET" == "1" ]] || step "Fertig. Start mit: python -m fgc.pipeline.viewer_launch  oder  fgc start"
