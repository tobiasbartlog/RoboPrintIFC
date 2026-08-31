"""Viewer und Core-API aus dem Core heraus öffnen/starten (ADR-014).

Verwaltet zwei lokale Server, die `fgc start` zusammen hochfährt:
- Vite-Dev-Server (Viewer, Port 5173)
- uvicorn-Core-API (Port 8765)

Der Viewer bleibt zustandsloser Abspieler; die Core-API ist ein dünner
Wrapper um pipeline.actions (keine eigene Fachlogik, kein eigener Zustand).
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path

from fgc.paths import REPO_ROOT, ROBOTS_DIR, RUNS_DIR, SCHEMA_DIR, VIEWER_DIR

VIEWER_URL = "http://localhost:5173"

# Lokale Core-API (ADR-014)
API_PORT = 8765
API_URL = f"http://localhost:{API_PORT}"


def run_url(run_dir: Path) -> str:
    """?run=-URL für einen Laufordner (Vite /@fs/-Pfad, ADR-004-Artefakte)."""
    return f"{VIEWER_URL}/?run=/@fs/{run_dir.resolve().as_posix()}"


def is_server_running(timeout_s: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(VIEWER_URL, timeout=timeout_s):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _npm() -> str | None:
    return shutil.which("npm")


def ensure_server(wait_s: float = 60.0) -> bool:
    """Startet den Vite-Dev-Server, falls er nicht läuft. True = erreichbar."""
    if is_server_running():
        return True

    npm = _npm()
    if npm is None:
        print("npm nicht gefunden — Node.js installieren, dann: cd viewer && npm run dev")
        return False

    if not (VIEWER_DIR / "node_modules").exists():
        print("Erststart: npm install im viewer/ (einmalig, kann etwas dauern) …")
        result = subprocess.run([npm, "install"], cwd=VIEWER_DIR)
        if result.returncode != 0:
            print("npm install fehlgeschlagen — Ausgabe oben prüfen.")
            return False

    print(f"Starte Viewer-Dev-Server ({VIEWER_URL}) …")
    if sys.platform == "win32":
        # Eigenes Konsolenfenster: Server-Logs sichtbar, läuft nach dem Wizard weiter.
        subprocess.Popen(
            [npm, "run", "dev"],
            cwd=VIEWER_DIR,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        subprocess.Popen(
            [npm, "run", "dev"],
            cwd=VIEWER_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if is_server_running():
            return True
        time.sleep(0.5)
    print(f"Viewer-Server antwortet nach {wait_s:.0f}s nicht — cd viewer && npm run dev")
    return False


def open_run(run_dir: Path) -> bool:
    """Öffnet einen Laufordner im Viewer; startet den Dev-Server bei Bedarf."""
    if not ensure_server():
        return False
    url = run_url(run_dir)
    print(f"Öffne {url}")
    webbrowser.open(url)
    return True


# --- Core-API (ADR-014) -----------------------------------------------------


def _probe_api(timeout_s: float = 1.0) -> str:
    """Klassifiziert, was auf dem API-Port antwortet (Issue #39).

    - ``"current"``: `/openapi.json` antwortet und kennt die Projekt-Routen
      (ADR-016) — die aktuelle API.
    - ``"stale"``: antwortet, kennt `/projects` aber nicht — eine veraltete
      fgc-Version, die ersetzt werden darf.
    - ``"timeout"``: keine Antwort im Zeitfenster. Das ist KEIN Beleg für
      veraltet — auch die aktuelle API kann den GIL sekundenlang an eine
      C-Extension verlieren (ifcopenshell/trimesh) und trotzdem gesund sein.
    - ``"down"``: Verbindung abgelehnt/kaputt — dort läuft keine (unsere) API.
    """
    try:
        with urllib.request.urlopen(f"{API_URL}/openapi.json", timeout=timeout_s) as resp:
            spec = json.load(resp)
    except TimeoutError:
        return "timeout"
    except urllib.error.URLError as err:
        return "timeout" if isinstance(err.reason, TimeoutError) else "down"
    except (OSError, ValueError, http.client.HTTPException):
        # HTTPException (z. B. BadStatusLine eines Nicht-HTTP-Diensts) ist weder
        # URLError noch OSError — ohne sie crasht der Start (Issue #47).
        return "down"
    return "current" if "/projects" in spec.get("paths", {}) else "stale"


def _startup_decision(status: str, port_busy: bool) -> str:
    """Was tun nach der Start-Probe (Issue #47)?

    - ``"ok"``: aktuelle API läuft.
    - ``"keep"``: Timeout = vermutlich beschäftigter, gesunder Server — nicht anfassen.
    - ``"replace"``: nachweislich veraltete fgc-API (antwortet, kennt /projects nicht).
    - ``"blocked"``: Port belegt, aber KEIN Beleg für eine fgc-API (fremder
      HTTP-/Nicht-HTTP-Dienst) — niemals taskkill auf Unbekanntes.
    - ``"start"``: Port frei — Server starten.
    """
    if status == "current":
        return "ok"
    if status == "timeout":
        return "keep"
    if not port_busy:
        return "start"
    return "replace" if status == "stale" else "blocked"


def _startup_probe(probe: Callable[[float], str] = _probe_api) -> str:
    """Probe für den GUI-Start: erst knapp (1 s), bei Timeout geduldig (5 s).

    Ein beschäftigter Server bekommt so eine zweite Chance, bevor irgendjemand
    über sein Schicksal entscheidet — er wird nie wegen eines einzelnen
    Timeouts als veraltet eingestuft (Issue #39).
    """
    status = probe(1.0)
    if status == "timeout":
        status = probe(5.0)
    return status


def is_api_running(timeout_s: float = 1.0) -> bool:
    """True, wenn die *aktuelle* Core-API erreichbar ist (s. `_probe_api`)."""
    return _probe_api(timeout_s) == "current"


def _listening_pids(port: int) -> list[int]:
    """PIDs, die auf `port` lauschen (Windows: netstat, sonst: lsof)."""
    pids: set[int] = set()
    try:
        if sys.platform == "win32":
            # Kein "-p TCP": das listet nur IPv4; IPv6-Sockets ([::1]:port)
            # tragen dieselbe Proto-Spalte "TCP" und sollen mit erfasst werden.
            out = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True,
            ).stdout
            # Der Status-Text ist lokalisiert ("LISTENING"/"ABHÖREN") — nicht
            # danach filtern. Ein lauschender Socket ist stattdessen daran
            # erkennbar, dass die Gegenstelle die Wildcard 0.0.0.0:0 / [::]:0
            # ist und eine echte PID (> 0) trägt (WARTEND-Zeilen haben PID 0).
            for line in out.splitlines():
                parts = line.split()
                if len(parts) < 4 or parts[0] != "TCP":
                    continue
                local, remote, pid = parts[1], parts[2], parts[-1]
                if local.rsplit(":", 1)[-1] != str(port):
                    continue
                if remote not in ("0.0.0.0:0", "[::]:0", "*:*"):
                    continue
                try:
                    value = int(pid)
                except ValueError:
                    continue
                if value > 0:
                    pids.add(value)
        else:
            out = subprocess.run(
                ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True, text=True,
            ).stdout
            pids.update(int(p) for p in out.split())
    except (OSError, ValueError):
        pass
    return sorted(pids)


def _free_port(port: int) -> None:
    """Beendet die Prozesse, die `port` belegen — den fest zugeteilten
    API-Port (ADR-014) für einen sauberen Neustart freimachen."""
    for pid in _listening_pids(port):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            else:
                os.kill(pid, __import__("signal").SIGTERM)
        except OSError:
            pass


def ensure_api_server(wait_s: float = 30.0) -> bool:
    """Startet den Core-API-Server (uvicorn), falls er nicht (aktuell) läuft.

    True = Server ist erreichbar. Start/Stop-Komfortweg nach ADR-014:
    derselbe Weg wie beim Viewer-Dev-Server; CLI und Wizard funktionieren
    weiterhin ohne laufende API. Hängt eine *veraltete* API auf dem Port
    (kennt `/projects` nicht), wird sie ersetzt — sonst würde uvicorn den Port
    nicht binden können und der Viewer bliebe an der alten API kleben.
    Antwortet der Port nur *langsam* (Timeout), wird NICHT gekillt: ein
    beschäftigter, gesunder Server ist kein veralteter (Issue #39).
    """
    status = _startup_probe()
    decision = _startup_decision(status, bool(_listening_pids(API_PORT)))
    if decision == "ok":
        return True
    if decision == "keep":
        print(
            f"API auf Port {API_PORT} antwortet langsam (beschäftigt?) — "
            "laufender Server wird nicht ersetzt."
        )
        return True
    if decision == "blocked":
        # "down"+belegt beweist NICHT, dass dort eine veraltete fgc-API läuft —
        # fremde Dienste werden nicht gekillt (Issue #47).
        print(
            f"Port {API_PORT} ist von einem fremden Prozess belegt (Probe: {status}) — "
            "wird NICHT beendet. Bitte Port freigeben und fgc start erneut ausführen."
        )
        return False
    if decision == "replace":
        print(f"Veralteter Server auf Port {API_PORT} — wird ersetzt …")
        _free_port(API_PORT)
        for _ in range(20):  # kurz warten, bis der Port frei ist
            if not _listening_pids(API_PORT):
                break
            time.sleep(0.1)

    print(f"Starte Core-API ({API_URL}) …")
    # --reload: der gestartete Server folgt dem Arbeitsbaum, statt Code UND
    # @cache-Schemas (fgc.domain.load_schema, Draft-Validator) aus der Startzeit
    # einzufrieren. Ohne das blieb nach einem `git pull` eine laufende API auf
    # altem Stand kleben (der Probe-Weg stuft sie als "current" ein, weil sie
    # /projects kennt, und startet sie nie neu) — genau die Falle, an der ein
    # nach #125 hinzugekommenes robots/*.json-Feld gegen das alte, gecachte
    # Schema durchfiel und die Roboterliste leer war.
    # Reload-Umfang bewusst eng: Core-Quellen + die validierten JSON-Stammdaten
    # (schemas/, robots/); NICHT runs/ oder projects/ (ändern sich laufend →
    # Reload-Sturm). Schema-/Datei-Edits ohne .py-Änderung greifen über
    # --reload-include=*.json.
    cmd = [
        sys.executable, "-m", "uvicorn", "fgc.pipeline.api:app", "--port", str(API_PORT),
        "--reload",
        "--reload-dir", str(REPO_ROOT / "core" / "src"),
        "--reload-dir", str(SCHEMA_DIR),
        "--reload-dir", str(ROBOTS_DIR),
        "--reload-include", "*.json",
    ]
    if sys.platform == "win32":
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if is_api_running():
            return True
        time.sleep(0.5)
    print(
        f"Core-API antwortet nach {wait_s:.0f}s nicht — manuell starten: "
        f"python -m uvicorn fgc.pipeline.api:app --port {API_PORT}"
    )
    return False


# --- GUI-Direkteinstieg (ohne Wizard) ----------------------------------------


def newest_model_run() -> Path | None:
    """Neuester Lauf mit Modellübersicht (model_map.json) unter runs/."""
    if not RUNS_DIR.exists():
        return None
    candidates = [p for p in RUNS_DIR.iterdir() if (p / "model_map.json").exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def start_gui() -> int:
    """API + Viewer starten und die Projektliste im Browser öffnen (ADR-016).

    Kanonischer GUI-Einstieg: Der Viewer landet auf der Projektliste — dort ein
    Projekt öffnen oder neu aus einer IFC-Datei anlegen. Das Projekt ist die
    langlebige Persistenz-Einheit (ADR-016); alle weiteren Schritte (Wand
    wählen, Roboter, Platzierung, Simulation, Export) laufen im Reiter-Fluss
    darüber. (Der `?run=`-Deeplink in einen rohen Laufordner bleibt als
    Dev/Automation-Fallback in main.ts, ist aber nicht mehr der Doppelklick-Start.)
    """
    ensure_api_server()
    if not ensure_server():
        return 1
    print(f"Öffne {VIEWER_URL}")
    webbrowser.open(VIEWER_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(start_gui())
