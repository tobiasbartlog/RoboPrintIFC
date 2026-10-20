# RoboPrintIFC v2

Vom IFC-Wandmodell zu kollisionsfrei druckbaren Modulen und einem lauffähigen Doosan-M1013-Programm
(DRL) für den Lehm-3D-Druck.

Eine Wand aus einem IFC-Modell wird in Module zerlegt. Jedes Modul steht aufrecht auf dem Doosantisch
und wird mit dem Roboter M1013 und dem Werkzeug `30gut` gedruckt. Das System plant Platzierung,
Bahn und Gelenkbewegung so, dass der gesamte Ablauf einschließlich aller Travel-Bewegungen frei von
Kollisionen und vollständig erreichbar ist. Pro Modul entsteht ein DRL-Programm in zwei Dialekten
(`v2`, Firmware 2.x, Default; `v3`, Firmware ≥ 3.2). Ein Web-Viewer führt durch Modell, Zerlegung,
Simulation und Export und zeigt Bewegung und Kollisionsbefund auf einer gemeinsamen Zeitachse.

Dies ist ein geführter Neustart. `legacy/` enthält v1 und wird nur gelesen. Die Spezifikation steht in
[`spec/SPEC.md`](spec/SPEC.md); dort sind Umfang (§1), Konventionen (§2), Algorithmen (§5), Artefakte (§6)
und Abnahme-Gates (§11) festgelegt.

![Wiedergabe der Simulation für das Referenzmodul S1](web/e2e/screenshots/g6-3-wiedergabe.png)

## Status

Der aktuelle Gate-Stand steht in [`PROGRESS.md`](PROGRESS.md), die Zusammenfassung des Nachtlaufs im
Morgenbericht (`MORGENBERICHT.md`). G4 (Beispiel-IFC) und G7 (Laufzeit) waren bei Redaktionsschluss dieser
Datei noch offen: siehe Morgenbericht. Abgenommen wird ausschließlich mit `python scripts/verify.py`.

## Installation

**Cloud-Umgebung (claude.ai/code):** `.claude/cloud/setup.sh` als Setup-Skript der Umgebung eintragen
(System- und Toolchain-Teile, venv unter `/opt/fgc-venv`). `.claude/hooks/session-start.sh` installiert
beim Start jeder Session das Projekt selbst.

**Lokal:**

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e "core[dev]"
npm --prefix web ci
```

**Windows (PowerShell):** gleiche Schritte, die venv aktiviert man mit `.\.venv\Scripts\Activate.ps1`.
Geprüft mit Python 3.14 am 2026-10-19. Windows kennt kein `fork`, deshalb rechnen Planer und Export dort in
einem Prozess und brauchen deutlich länger als auf der Cloud-VM.

## Beispiellauf: Referenzmodul S1

S1 ist ein Quader 600 × 200 × 400 mm, der als ein Teil (`box_01`) gedruckt wird.

```bash
PYTHONPATH=core/src python -m roboprint run-scenario spec/scenarios/S1_modul_referenz.json --out runs/readme/S1
```

Gemessen auf der Cloud-VM (4 vCPU) am 2026-10-19, Stand Commit 834efe0:

| Kennzahl | Wert |
|---|---|
| Status (`summary.json`) | `machbar` |
| Samples n (`trajectory.json`) | 62 112 |
| Status je Sample | 62 112 `warn`, 0 `ok`, 0 `collision`, 0 `unreachable` |
| d_min | 10,83 mm (d_hard = 10 mm) |
| Druckdauer (`dauer_s`) | 1458,9 s, entspricht 24:18,9 min |
| Zweigwechsel in Ringen | 0 |
| Laufzeit des Laufs | 36,8 s (`timings_s.total`), 38,2 s Wanduhr |

Dass alle Samples `warn` tragen, ist bekannt: Das Paar `base_link` ↔ `link_2` bleibt auf den Roh-Meshes
konstant bei 33,2 mm und liegt damit unter d_target (50 mm). Siehe „Gate-Einwände“ in `PROGRESS.md`.

Die Tabelle stammt vom Stand vor dem durchgehenden Strang. Seit dem 20.10.2026 druckt S1 alle 80 Ringe in
einem Strang mit 79 Verbindern. Lokal unter Windows gemessen: Druckdauer 1128,7 s (18:48,7 min) statt
1459,9 s mit `link_max_mm` = 0, d_min 10,83 mm, Zweigwechsel 0. Die Messung auf der Cloud-VM steht aus.

Der Lauf schreibt unter `runs/readme/S1/` die Artefakte nach SPEC §6: `summary.json`, `scene.json` und je
Teil `part.stl`, `toolpath.json`, `trajectory.json`, `program.v2.drl`, `program.v3.drl`. `runs/` wird
nicht versioniert.

## Druckablauf: Strang mit Verbindern

Jede Schicht besteht aus Ringen, je Schale ein geschlossener Ring. Die Ringe werden über gedruckte
**Verbinder** zu einem **Strang** verbunden (Nutzerentscheidung 20.10.2026, SPEC §5.3):

- Ein Verbinder ist die Gerade vom Ende eines Rings zum Start des nächsten. Er liegt über Material, ist
  höchstens `link_max_mm` lang (Standard 60 mm) und steigt beim Schichtwechsel um die Schichthöhe h.
- Im Strang läuft die Pumpe durch, und der Roboter hält nicht an. Alle `movel` sind geblendet, auch an den
  Ringgrenzen; nur das letzte `movel` des Strangs hat `radius = 0`.
- Der Pumpen-Vorlauf `t_tot` fällt einmal am Strangbeginn an: Stillstand, Pumpe an, `wait(t_tot)`.
- Abfahren und Abheben um `z_lift`, Transfer, Absenken und Anfahren (`approach_mm`) gibt es nur zwischen
  Strängen. Ein Strang endet, wo kein Verbinder geht: Öffnung im Querschnitt, Abstand über `link_max_mm`,
  anderer IK-Zweig, unerreichbar oder Abstand unter d_hard.
- `link_max_mm` = 0 schaltet die Verbinder ab. Dann ist jeder Ring ein eigener Strang wie vor dem
  20.10.2026: Halt am Ringende, Pumpe aus, Abheben, Transfer, Pumpe an und `wait(t_tot)` je Ring.

## Viewer

```bash
scripts/dev.sh            # Linux, macOS
.\scripts\dev.ps1         # Windows (PowerShell)
```

Das Skript startet die API (`127.0.0.1:8765`) und den Vite-Dev-Server (`http://localhost:5173`). Getrennt
geht es so:

```bash
PYTHONPATH=core/src python -m roboprint serve --runs runs     # API
npm --prefix web run dev                                      # Viewer, leitet /api an die API weiter
```

Den Lauf von oben öffnet man direkt mit `/?run=readme/S1&part=box_01` an der Adresse des Dev-Servers.
Rot bedeutet Kollision, Gelb Abstand unter dem Sollwert, gestreift unerreichbar. Bei einer Kollision
(Szenario S3) listet der Viewer die Befunde auf und springt auf Klick an die betreffende Zeit.

![Kollisionsbefund im Negativszenario S3](web/e2e/screenshots/g6-s3-kollision.png)

## Abnahme

```bash
python scripts/verify.py              # alle Gates G1-G8
python scripts/verify.py --fast       # ohne die langen Szenarien G4/G7
python scripts/verify.py --gate G3    # ein einzelnes Gate
```

Der Bericht liegt unter `runs/verify/report.json`. Die Orakel in `verify/` rechnen unabhängig mit Pinocchio,
Coal und der URDF, lesen nur Artefakte und importieren `roboprint` nie. Weitere Prüfungen:
`python -m pytest core -q -n 2`, `python -m ruff check core verify`, `npm --prefix web run lint|typecheck|test|e2e`.

## Verzeichnisstruktur

```
core/         Python-Paket roboprint (Kinematik, Kollision, Zerlegung, Planung, DRL, API, CLI)
web/          React-Viewer mit Playwright-Tests und Screenshots (web/e2e/screenshots/)
verify/       unabhängige Orakel und Gate-Runner (gesperrt)
spec/         SPEC, Nachtlauf-Ablauf, Artefaktformate, Szenarien S1-S3 (gesperrt)
legacy/       v1, nur lesen; Portierungsliste in SPEC §12
docs/         DRL-Semantik, UX-Leitbild, ADRs, Gegenprüfung, Recherche, Spikes
robots/ tools/ workstations/ third_party/   Roboter, Werkzeug, Doosantisch, URDF und Meshes
examples/     Beispiel-IFC (Building-Architecture.ifc)
scripts/      verify.py, dev.sh
```

## Offene Annahmen

Mehrere Prozessparameter sind Annahmen (in SPEC §10 mit „A“ markiert, auch im Kopf jedes DRL-Programms
und in `summary.json` mit den tatsächlich genutzten Werten aufgeführt): Schichthöhe, Strangbreite, Druck- und
Fahrgeschwindigkeit (v_print gilt auch in Verbindern), Abhebehöhe z_lift und An-/Abfahrt (beide nur zwischen
Strängen), Pumpenwert, Pumpen-Vorlauf t_tot (einmal je Strang, provisorisch), r_blend, d_hard und τ_max.
`link_max_mm` (60 mm) ist eine Nutzervorgabe vom 20.10.2026. Hinzu kommen die Firmware-Version des Controllers,
die Rotationssymmetrie der Düse und der am Teach Pendant anzulegende TCP `FGC_30GUT`. Die vollständige Liste
steht in SPEC §13 und muss vom Nutzer bestätigt werden. Kein DRL-Programm ist bisher an einem realen Controller
gelaufen.

## Lizenz, Attribution, Zitation

Der eigene Code steht unter der MIT-Lizenz ([`LICENSE`](LICENSE)). Fremdbestandteile, insbesondere das
Doosan-M1013-Robotermodell unter `third_party/`, sind mit Herkunft und Lizenz in [`NOTICE`](NOTICE)
ausgewiesen. Zum Zitieren siehe [`CITATION.cff`](CITATION.cff).

Autor: Tobias Bartlog, RWTH Aachen University. Die Entwicklung erfolgte KI-gestützt; fachliche Konzeption,
Architektur- und Domänenentscheidungen sowie Prüfung und Abnahme liegen beim Autor (Näheres in `NOTICE`).
