# ADR-018 — Nebenläufigkeit der Projekt-Schreibstelle / Write-Lock

Status: angenommen · 2026-07-05 (Issue #45, Tiefenprüfung 2)

## Kontext

`fgc.project` ist die *eine Schreibstelle* für `project.json` (ADR-016). Jede
mutierende **Aktion** in `pipeline/actions.py` (`set_print_job`,
`set_tool_for_job`, `reassess_walls_for_robot`, `evaluate_placements`,
`suggest_placement`, `select_placement`, `propose_decomposition`,
`simulate_section`, `export_section_drl`) folgt demselben Muster:
`load_project(project_dir) → Artefakt mutieren → write_project(project_dir, …)`.

Die lokale Core-API (ADR-014) ist ein FastAPI-Wrapper, der die synchronen
Aktions-Endpunkte im **Threadpool** ausführt → echte Nebenläufigkeit. Zwei
parallele mutierende Requests auf *dasselbe* Projekt lesen beide denselben
Stand, mutieren je ihre Kopie und schreiben nacheinander → **Lost Update**: der
zweite `write_project` überschreibt die Änderung des ersten (z. B. Roboter
setzen + Endeffektor setzen gleichzeitig → einer geht verloren). Zusätzlich war
`write_project` nicht atomar (`path.write_text(...)`) → ein gleichzeitig lesender
`load_project` konnte theoretisch ein halb geschriebenes File sehen.

Das ist keine fachliche, sondern eine **Korrektheits-Invariante der einen
Schreibstelle** — daher Architekturrang.

## Entscheidung

Zwei Maßnahmen in `fgc.project.store`:

1. **Serialisierung je Projekt.** Ein Kontextmanager `project_lock(project_dir)`,
   gestützt auf eine prozessweite Registry von `threading.RLock` je aufgelöstem
   (`.resolve()`) Projektpfad (thread-safe angelegt hinter einem kleinen
   Registry-Guard). Jede mutierende Aktion umschließt ihre
   `load_project → … → write_project`-Sektion mit `with project_lock(project_dir):`.
   Der Schlüssel ist der `.resolve()`-te Pfad, damit verschiedene Schreibweisen
   desselben Ordners denselben Lock treffen; verschiedene Projekte serialisieren
   *nicht* gegeneinander (eigener Lock je Pfad).

   **`RLock` statt `Lock`**, weil `suggest_placement` den Lock hält und an
   `evaluate_placements` delegiert, das denselben Projekt-Lock erneut nimmt — mit
   einem einfachen `Lock` wäre das ein Selbst-Deadlock. Reentranz je Thread löst
   das ohne die verschachtelte Aktion aufzubrechen.

2. **Atomares `write_project`.** Erst in eine Temp-Datei im selben Verzeichnis
   schreiben, dann per `os.replace(...)` einschwenken (atomarer Rename auf
   Windows/POSIX). So sieht `load_project` nie ein halb geschriebenes File. Die
   Schema-Validierung *vor* dem Schreiben bleibt unverändert (ADR-016).

`create_project_from_ifc` braucht **keinen** Lock: es legt einen *neuen,
eindeutigen* Ordner an (`unique_project_dir`) — keine Read-Modify-Write-Sektion
auf einem bestehenden Projekt, kein Konkurrent auf demselben Pfad.

Verworfen:

- **Zusätzlicher dateibasierter Cross-Process-Lock** (z. B. `filelock` /
  Lockfile): nicht nötig. Der Launcher hält genau **einen** Core-Prozess auf
  Port 8765 (`viewer_launch`, `_startup_decision` tötet veraltete fgc-APIs) —
  Single-Process ist die Norm. Ein In-Process-`RLock` deckt die reale
  Nebenläufigkeit (Threadpool) vollständig ab. Sollte je echter
  Mehrprozess-/Mehrbenutzerbetrieb dazukommen, ist ein Cross-Process-Lock
  nachzurüsten (Revisionstrigger).
- **`asyncio`-Lock / Endpunkte async machen:** die Aktionen sind synchron
  (Datei-I/O, Rechnung); ein Thread-Lock passt zum Threadpool-Ausführungsmodell,
  ohne die Aktionen umzuschreiben.
- **Optimistische Nebenläufigkeit (Versions-/ETag-Vergleich, Retry):** mehr
  Mechanik als nötig für die eine lokale Schreibstelle; der pessimistische Lock
  ist kurz gehalten (nur die RMW-Sektion) und einfacher zu begründen.

## Konsequenzen

- Neue Nebenläufigkeits-Invariante der einen Schreibstelle: *jede* mutierende
  Aktion muss ihre `load→write`-Sektion mit `project_lock` umschließen — bei
  neuen Aktionen mitzupflegen (Grep-Kriterium: jede `write_project(`-Stelle in
  `actions.py` liegt in einem `with project_lock(...)`-Block).
- Parallele Requests auf *dasselbe* Projekt serialisieren (kurz); auf
  *verschiedene* Projekte laufen sie weiter parallel (Lock je Pfad).
- `write_project` hinterlässt bei Erfolg genau `project.json` (kein Temp-Rest);
  ein abgebrochener Schreibvorgang lässt höchstens eine `.tmp`-Datei zurück, nie
  ein korruptes `project.json`.

## Revisionstrigger

Wenn der Core in echtem Mehrprozess-/Mehrbenutzerbetrieb läuft (mehrere
Core-Prozesse oder Hosts auf demselben `projects/`-Verzeichnis), reicht der
In-Process-Lock nicht mehr — dann ist ein dateibasierter Cross-Process-Lock (oder
eine echte Transaktions-/DB-Schicht) nachzurüsten.
