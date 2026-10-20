#!/usr/bin/env bash
# Entwicklung: startet API (127.0.0.1:8765) und Web-Dev-Server (Vite, Proxy /api -> API).
# Ctrl-C beendet beide.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${FGC_VENV:-/opt/fgc-venv}/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

pids=()
cleanup() {
    trap - INT TERM EXIT
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

cd "$ROOT" || exit 1
PYTHONPATH="$ROOT/core/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" -m roboprint serve --runs "$ROOT/runs" &
pids+=($!)
npm --prefix web run dev &
pids+=($!)

wait -n
