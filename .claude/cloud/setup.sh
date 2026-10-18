#!/usr/bin/env bash
# Setup-Skript der Claude-Code-Cloud-Umgebung fuer RoboPrintIFC.
#
# Wird in claude.ai/code unter "Environment -> Setup script" eingefuegt und laeuft
# dort als root auf Ubuntu 24.04, bevor eine Session startet. Das Ergebnis landet im
# Umgebungs-Cache, solange das Skript in ~5 Minuten fertig wird.
#
# Hier stehen nur System- und Toolchain-Teile. Das Projekt selbst (pip install -e core,
# npm ci) installiert der SessionStart-Hook .claude/hooks/session-start.sh, weil erst
# dort der Arbeitsbaum der Session feststeht.
#
# Erwartete Umgebungsvariablen der Cloud-Umgebung (Environment -> Variables):
#   FGC_VENV=/opt/fgc-venv
#   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
#
# Optionale Teile schlagen nur mit WARNUNG fehl, damit die Umgebung trotzdem startet.
set -uo pipefail

log()  { echo "[setup] $*"; }
warn() { echo "[setup] WARNUNG: $*" >&2; }

export DEBIAN_FRONTEND=noninteractive
VENV="${FGC_VENV:-/opt/fgc-venv}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"

# --- 1) Systempakete --------------------------------------------------------------
# libspatialindex: rtree (trimesh). libgl/glu/xrender: Headless-Rendering von Meshes.
# xvfb: Fallback fuer Browser-Screenshots ohne Headless-Modus.
log "Systempakete ..."
apt-get update -qq || warn "apt-get update fehlgeschlagen"
apt-get install -y -qq --no-install-recommends \
    python3.12-venv python3.12-dev build-essential \
    libspatialindex-dev libgl1 libglu1-mesa libxrender1 libxi6 libxkbcommon0 \
    xvfb fonts-dejavu-core \
    || warn "Systempakete unvollstaendig"

# --- 2) Gemeinsame Python-venv ausserhalb des Repos -------------------------------
# Python 3.12 wie in der CI (.github/workflows/ci.yml) und passend zum abi3-Wheel von
# tesseract-robotics-nanobind. Die venv liegt ausserhalb des Arbeitsbaums, damit sie
# im Umgebungs-Cache bleibt und alle Worktrees einer Session sie teilen.
if [ ! -x "$VENV/bin/python" ]; then
    log "Lege venv $VENV an ..."
    if command -v uv >/dev/null 2>&1; then
        uv venv --seed --python 3.12 "$VENV" || python3.12 -m venv "$VENV"
    else
        python3.12 -m venv "$VENV"
    fi
fi

pip_install() {
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "$VENV/bin/python" "$@"
    else
        "$VENV/bin/python" -m pip install --quiet "$@"
    fi
}

# 2a) Bestehender Kern-Stack, Spiegel von core/pyproject.toml [dev,geo]. Vorab im Cache,
#     damit der Hook pro Session nur noch das Paket selbst editierbar nachzieht.
log "Kern-Stack ..."
pip_install \
    "jsonschema>=4.21" "fastapi>=0.110" "uvicorn[standard]>=0.29" \
    "pytest>=8" "pytest-xdist>=3.6" "ruff>=0.6" "httpx>=0.27" \
    ifcopenshell trimesh shapely numpy scipy networkx rtree pycollada \
    python-fcl mapbox-earcut vhacdx \
    || warn "Kern-Stack unvollstaendig"

# 2b) Kandidaten aus der Recherche (2026-10-18), einzeln und optional:
#     tesseract-robotics-nanobind  Descartes/TrajOpt/OMPL + Kontaktabstaende (Bahnplanung)
#     pin, coal                    Pinocchio + Coal als unabhaengiges Kollisions-/FK-Orakel
#     py-opw-kinematics            unabhaengiges OPW-IK-Orakel (CEAD)
#     manifold3d                   robuste Booleans fuer Schnitte und Druckstand
for pkg in tesseract-robotics-nanobind pin coal py-opw-kinematics manifold3d; do
    log "optional: $pkg ..."
    pip_install "$pkg" || warn "$pkg nicht installierbar"
done

# Die Session laeuft eventuell nicht als root: venv fuer alle beschreibbar machen,
# damit Agenten Pakete nachinstallieren koennen.
chmod -R a+rwX "$VENV" || true

# --- 3) Browser fuer UI-Screenshots (Playwright) ----------------------------------
# Braucht Netzwerkzugriff "Full" (oder cdn.playwright.dev + playwright.azureedge.net
# in der Custom-Liste). Weicht die im Repo gepinnte Playwright-Version spaeter ab, laedt
# der SessionStart-Hook den passenden Browser nach.
log "Playwright-Chromium samt Systemabhaengigkeiten ..."
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
npx -y playwright install --with-deps chromium \
    || warn "Playwright-Chromium nicht installiert (Netzwerkstufe pruefen)"
chmod -R a+rwX "$PLAYWRIGHT_BROWSERS_PATH" || true

# --- 4) Kurzbericht ---------------------------------------------------------------
log "Fertig. Python: $("$VENV/bin/python" --version 2>&1)"
"$VENV/bin/python" - <<'PY' || true
import importlib
for mod in ["ifcopenshell", "trimesh", "fcl", "tesseract_robotics", "pinocchio", "coal",
            "py_opw_kinematics", "manifold3d"]:
    try:
        importlib.import_module(mod)
        print(f"[setup]   ok      {mod}")
    except Exception as exc:  # noqa: BLE001 - Bericht, kein Abbruch
        print(f"[setup]   FEHLT   {mod}: {type(exc).__name__}")
PY
exit 0
