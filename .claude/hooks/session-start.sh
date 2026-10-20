#!/usr/bin/env bash
# SessionStart-Hook: macht eine Cloud-Session arbeitsfaehig. Lokal (Windows) tut er nichts.
#
# Normalfall: Die venv kommt aus dem Setup-Skript der Umgebung (.claude/cloud/setup.sh).
# Fehlt sie (z. B. Session in der Default-Umgebung ohne Setup-Skript), baut der Hook sie
# selbst unter $HOME/.fgc-venv, ohne root (apt- und Browser-Teile werden dann uebersprungen).
# Danach: venv auf den PATH (CLAUDE_ENV_FILE), core editierbar, web per npm ci.
# Ausfuehrliche Ausgaben gehen nach $LOG; stdout landet im Kontext und bleibt kurz.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
VENV="${FGC_VENV:-/opt/fgc-venv}"
LOG="${TMPDIR:-/tmp}/fgc-session-start.log"
status=()

cd "$ROOT" || exit 0

if [ ! -x "$VENV/bin/python" ]; then
    VENV="$HOME/.fgc-venv"
    if [ ! -x "$VENV/bin/python" ]; then
        FGC_VENV="$VENV" bash .claude/cloud/setup.sh >>"$LOG" 2>&1
        status+=("venv selbst gebaut unter $VENV (Setup-Skript der Umgebung fehlte)")
    fi
fi

if [ -x "$VENV/bin/python" ]; then
    if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
        {
            echo "export VIRTUAL_ENV=\"$VENV\""
            echo "export PATH=\"$VENV/bin:\$PATH\""
            echo "export PLAYWRIGHT_BROWSERS_PATH=\"${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}\""
        } >> "$CLAUDE_ENV_FILE"
    fi
    if [ -f core/pyproject.toml ]; then
        if command -v uv >/dev/null 2>&1; then
            uv pip install --python "$VENV/bin/python" -e "core[dev]" >>"$LOG" 2>&1 \
                || uv pip install --python "$VENV/bin/python" -e core >>"$LOG" 2>&1
        else
            "$VENV/bin/python" -m pip install -e "core[dev]" >>"$LOG" 2>&1 \
                || "$VENV/bin/python" -m pip install -e core >>"$LOG" 2>&1
        fi && status+=("core installiert") || status+=("core-Install FEHLGESCHLAGEN (siehe $LOG)")
    else
        status+=("core/ noch nicht angelegt (P0)")
    fi
else
    status+=("keine venv - Setup pruefen (siehe $LOG)")
fi

for app in web; do
    if [ -f "$app/package-lock.json" ]; then
        npm --prefix "$app" ci --no-audit --no-fund >>"$LOG" 2>&1 \
            && status+=("$app installiert") || status+=("npm ci in $app FEHLGESCHLAGEN (siehe $LOG)")
        if grep -q '"@playwright/test"' "$app/package.json" 2>/dev/null; then
            (cd "$app" && npx playwright install chromium) >>"$LOG" 2>&1 \
                && status+=("Playwright-Browser bereit") || status+=("Playwright-Browser fehlt")
        fi
    fi
done

echo "Cloud-Umgebung: $(printf '%s; ' "${status[@]}")Python: $VENV/bin/python. Log: $LOG"
exit 0
