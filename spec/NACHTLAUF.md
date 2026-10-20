# NACHTLAUF — Orchestrierung

Du bist der **Orchestrator** einer unbeaufsichtigten Cloud-Session. Du planst, startest Agenten,
prüfst, mergst und protokollierst. Feature-Code schreiben die Agenten. Das Ziel ist grün nach
`spec/SPEC.md` §11.

## Rahmen

- Branch `v2-nachtlauf` ist dein Integrationszweig. Jede Aufgabe läuft in einem eigenen Worktree
  auf `v2/<aufgabe>`.
- Push nur auf `v2-nachtlauf` und `v2/*`, nie `--force`, nie auf `main`. Gepusht wird nach jeder
  abgeschlossenen Phase, damit nichts verloren geht, falls die Session abbricht.
- Höchstens 6 Agenten gleichzeitig (4 vCPU). Agenten nutzen `pytest -n 2`.
- Hat der Nutzer ultracode freigegeben, setzt du je Phase einen Workflow ein. Agenten-Ausgaben
  bleiben im Workflow, in deinem Kontext landen nur Ergebnisse. Ohne Freigabe (zum Beispiel in
  einer Wächter-Session) nutzt du das Agent-Tool mit Hintergrund-Subagenten in Worktrees,
  nach demselben Plan.
- **Modellwahl:**
  - `opus` für Orakel, Kollisionswelt, Planer, Zerlegung und Gegenprüfung.
  - `sonnet` für Portierungen mit klarer Vorlage, Gerüst, UI-Komponenten und Tests nach Muster.
  - Nach einem gescheiterten `sonnet`-Versuch einmal mit `opus` wiederholen.
- **Spätestens um 07:30 Europe/Berlin** (`TZ=Europe/Berlin date`) gehst du in P5, egal wie
  der Stand ist.

## Herzschlag und Wiederaufnahme

Die Cloud-VM pausiert nach wenigen Minuten ohne Aktivität. Ein Nutzungslimit kann den Lauf
deshalb stoppen. Der Zustand lebt darum vollständig im Repo:

- **Herzschlag:** Ganz oben in `PROGRESS.md` steht die Zeile
  `Herzschlag: <ISO-Zeit Europe/Berlin> · Session: <kurze Kennung> · Phase: <P0..P5>`.
  Du aktualisierst sie mindestens alle 30 Minuten und nach jedem Merge, committest sie und
  pushst auf `v2-nachtlauf`.
- **Vor jeder Phase:** `git fetch origin v2-nachtlauf`. Trägt der Remote-Herzschlag eine fremde
  Session-Kennung, hat ein Wächter übernommen. Dann beendest du deine Arbeit ohne weiteren
  Push und schreibst nur noch eine Zeile in den Chat.
- **Übernahme (Wächter-Session):** Startet eine Session und ist der Remote-Herzschlag älter als
  90 Minuten, während `MORGENBERICHT.md` fehlt, übernimmt sie. Sie setzt ihren eigenen
  Herzschlag, pusht ihn sofort und macht an der Phase in `PROGRESS.md` weiter. Halbfertige
  Worktrees ohne Commit gelten als verloren, die Aufgabe startet neu. Ist der Herzschlag jünger
  oder der Morgenbericht da, beendet sie sich sofort ohne Änderung.
- **Neustart derselben Session** (zum Beispiel nach „weiter“ vom Nutzer): Lies `PROGRESS.md`,
  setze den Herzschlag und mach an der offenen Aufgabe weiter.

## Start

1. Lies `CLAUDE.md`, `spec/SPEC.md` und `PROGRESS.md`.
2. Prüfe die Umgebung:
   - `python --version` muss 3.12 sein.
   - `python -c "import ifcopenshell, trimesh, fcl, pinocchio, coal, manifold3d"`
   - `python -c "import tesseract_robotics"` ist optional.
   - `node --version`
   - `npx playwright --version`
   Trage das Ergebnis in PROGRESS.md ein.
3. Führe `python scripts/verify.py` als Ausgangslage aus. Alles rot ist erwartet. Protokolliere es.

## Phasen

Jede Phase endet an ihrem Gate. Nach jeder Phase: `python scripts/verify.py --fast`,
PROGRESS-Eintrag, Push.

### P0 Fundament (≈ 1 h) — Ende: Gerüst steht, Orakel stehen und prüfen sich selbst, `spec/LOCKED` existiert

Drei Agenten, parallel:

- **A0.1 Gerüst** (sonnet). Ende: `ruff`, `pytest core` und `npm --prefix web run lint|typecheck|test`
  laufen grün auf leeren Tests, und die CI ruft sie auf.
  - `core/pyproject.toml`: Paket `roboprint`, Python ≥ 3.12, Abhängigkeiten aus
    `.claude/cloud/setup.sh`, Extras `dev`, CLI-Einstiegspunkt `roboprint`. In
    `[tool.pytest.ini_options]` steht `pythonpath = ["src"]`, damit jeder Worktree seinen eigenen
    Code testet.
  - Modul-Stubs nach SPEC §4.
  - `web/`: Vite, React, TS strict, Mantine, R3F/drei, Zustand, Vitest, Playwright, ESLint,
    jeweils mit gepinnten Versionen.
  - `.github/workflows/ci.yml` auf die neue Struktur umstellen (G8 sowie G1/G2, sobald vorhanden).
  - `scripts/dev.sh` startet API und Web.
- **A0.2 Orakel** (opus, **unabhängig**: liest SPEC und Artefakt-Verträge, nie `core/src`).
  Ende: Die Selbsttests der Orakel sind grün.
  - `verify/oracle/robot_oracle.py`: Pinocchio aus der URDF.
  - `verify/oracle/collision_oracle.py`: Coal auf Roh-Meshes, Paare exakt nach SPEC §5.1.
  - `verify/check_run.py`: G3/G4-Prüfer für Laufordner.
  - `verify/fake_drcf/`: Dialekte v2/v3 nach `docs/doosan-drl.md`, mit eigener ZYZ-Umrechnung.
  - Die Testdateien, die `verify/run.py` aufruft.
  - Selbsttests mit bekannten Posen und konstruierten Fällen: ein Würfel genau im Glied ergibt
    d < 0; ein DRL-Text mit `ch=0` wird abgelehnt.
- **A0.3 Verträge** (sonnet). Ende: Schema-Export und TS-Typgenerierung laufen, ein Test prüft
  die Aktualität.
  - `roboprint.contracts`: Pydantic-Modelle nach SPEC §6, `roboprint export-contracts`.
  - `web/src/contracts/` mit generierten Typen.
  - `web/fixtures/`: kleiner, handgebauter Laufordner, damit P3 vor dem Planer arbeiten kann.

Danach prüfst du selbst: `verify/` importiert `roboprint` nicht (`grep -r "roboprint" verify/`).
Dann committest du `spec/LOCKED` (Inhalt: Zeitstempel und Commit). Ab dann blockiert der Hook
Änderungen an `spec/` und `verify/`.

### P1 Module (≈ 1,5 h) — Ende: G1, G2 und die Unit-Tests aller Module grün

Sechs Agenten, parallel, je ein Modul nach SPEC §4 und §12:

| Agent | Inhalt | Modell |
|---|---|---|
| A1.1 | `robot`: FK, IK, Doosan-Konvention, Zweig-Bits | opus |
| A1.2 | `ifc` + `frames` + `geometry` | sonnet |
| A1.3 | `slicer` mit An-/Abfahrt und Löchern | sonnet |
| A1.4 | `collision`: Welt, VHACD, Druckstand, Paare | opus |
| A1.5 | `drl`: Emitter v2/v3. Muss den Fake-Controller mit einem handgebauten Plan bestehen | opus |
| A1.6 | Tesseract-Spike, Timebox 60 min, nur Bericht in PROGRESS.md, kein Merge in `core` | sonnet |

### P2 Planer und Zerlegung (≈ 2 h) — Ende: G3, G4 und G5 grün

Nacheinander, mit Gegenprüfung:

1. **A2.1 Planer + Travel + Verdichtung + `timing` + `pipeline` + CLI** (opus). Ende: G3 grün.
2. **A2.2 Zerlegung** (opus). Ende: G4 grün, inklusive S3.
3. **A2.3 DRL-Integration** (sonnet). Ende: G5 grün für alle Teile aus S1 und S2.
4. **A2.4 Gegenprüfer** (opus, frischer Kontext). Auftrag: „Finde ein Teil, ein Sample oder eine
   Pose, bei der unser Status oder der Prüfer falsch liegt.“ Funde werden Aufgaben für den
   nächsten Durchgang.

Wenn G3 an der Physik scheitert, zum Beispiel weil S1 bei d_hard nicht machbar ist, belegt der
Agent das mit d_min, Glied, Schicht und der besten gefundenen Platzierung in PROGRESS.md. Danach
arbeitet die Zerlegung mit kleineren Modulen weiter. G4 bleibt erreichbar, weil H* die Modulhöhe senkt.

### P3 Viewer (≈ 2 h, parallel zu P2 ab Ende P0) — Ende: G6 grün

Vier Agenten nach `docs/ux-leitbild.md`. Sie arbeiten zuerst gegen `web/fixtures/`, danach gegen
echte Läufe.

| Agent | Inhalt | Modell |
|---|---|---|
| A3.1 | `api` (FastAPI, Jobs mit Fortschritt und Abbruch) + API-Client im Web | sonnet |
| A3.2 | App-Shell, Stepper, Schritte Modell / Zerlegen & prüfen / Export | sonnet |
| A3.3 | 3D-Szene: urdf-loader, Tisch, Teil mit Schnittebene, Werkzeug, Kamera | sonnet |
| A3.4 | Player mit einer Uhr, Timeline mit Bereichs-Balken, Kollisionsliste, Hervorhebung, Kontaktlinie, Debug-Schnittstelle, Playwright-Suite | opus |

### P4 Härtung — Ende: G1–G8 grün

- **A4.1 UX-Prüfer** (opus, liest Screenshots). Bewertet `web/e2e/screenshots/` gegen die
  Checkliste in `docs/ux-leitbild.md` und schreibt die Top-10-Mängel als Aufgaben.
- Aufgaben aus A2.4 und A4.1 abarbeiten.
- G7 messen und Engpässe profilieren: Cache, Vektorisierung, Parallelisierung über Teile mit `--jobs`.
- Volles `python scripts/verify.py`.

### P5 Abschluss — Ende: `MORGENBERICHT.md` committet und gepusht, Draft-PR offen

1. `README.md` für v2 neu schreiben: kurz, mit echtem Lauf und Screenshot.
2. `MORGENBERICHT.md` schreiben:
   - Gate-Tabelle mit Zahlen
   - was jetzt funktioniert, mit Screenshots
   - was nicht funktioniert und warum
   - Gate-Einwände
   - Annahmen, die der Nutzer bestätigen muss (SPEC §10, §13)
   - die nächsten Schritte
3. `legacy/` bleibt bis zur Abnahme durch den Nutzer stehen.
4. Draft-PR `v2-nachtlauf → main` mit dem Morgenbericht als Beschreibung. Nicht mergen.

## Agenten-Auftrag (Vorlage)

Jeder Agent bekommt:
- Aufgabe, Ziel-Gate und Ende-Kriterium wörtlich aus diesem Plan
- die SPEC-Abschnitte, die er lesen muss (Nummern)
- den Worktree und den Branch `v2/<aufgabe>`
- **Batch-Kontext:** was frühere Aufgaben schon geändert haben, in 2–4 Sätzen
- das Mandat: Implementierung samt Tests; das Ziel-Gate und die Modultests laufen lassen;
  Rebase auf `v2-nachtlauf`; genau ein Commit; kein Push
- einen Bericht von höchstens 10 Zeilen: Was geändert, Gate-Ergebnis, offene Punkte

## Merge-Ablauf

Nach jedem Agenten:
1. Diff prüfen
2. betroffenes Gate und `--fast` laufen lassen
3. Ende-Kriterium Punkt für Punkt gegen den Diff abhaken
4. mergen
5. PROGRESS-Eintrag schreiben

**Bei Fehlschlag:** einmal mit stärkerem Modell und dem Fehlerkontext wiederholen. Scheitert auch
das, wird die Aufgabe offen protokolliert, abhängige Aufgaben werden zurückgestellt, unabhängige
gehen weiter.

## PROGRESS.md-Format

Je Eintrag:
```
### <Zeit Europe/Berlin> <Phase/Aufgabe>
- Ergebnis: <Gate> grün|rot (<Kennzahl>)
- Commit: <sha>
- Offen: …
```
Die Gate-Tabelle oben in PROGRESS.md hältst du aktuell.
