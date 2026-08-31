# Spike S5b — AP-1-Baseline: FCL-Referenz produktiv verdünnt, je Aufrufort (Issue #206, PRD #183)

Status: **grün (Messung abgeschlossen)** · 2026-07-14

> Vorher-Hälfte von US 13 der PRD #183 (Arbeitspaket 1 — Glied-SDF-Prüf-Tür).
> Dieser Spike **misst**, er optimiert nicht: kein Produktivcode geändert
> (`core/src/fgc/collision/*` unberührt). Alle Zahlen sind reproduzierbar über die
> S5-Sonden unter `docs/spikes/s5_scripts/` (erweitert, nicht neu gebaut).

## Frage

Was kostet die **FCL-Referenz** (`fgc.collision.check.find_collisions`) auf der
**produktiv verdünnten** Konfiguration — also mit `travel_stride=5` wie im realen
Prüf-Tür-Pfad (`finding.check_part_clearance`) — **getrennt nach Aufrufort**
(Arm↔Hindernis vs. Selbstkollision/Arm↔Arm)? Diese Zahl ist die **Baseline**, gegen
die die AP-1-Abnahme (#215) den Glied-SDF-Pfad misst; der Paper-Beleg „SDF
beschleunigt Y-fach je Posten" (US 13, US 21) braucht eine **konfigurationsgleiche**
Vorher-Messung — kein Kostenblock darf übersehen werden.

## Warum eine neue Messung (Abgrenzung zu S5)

Die S5-Messung (`S5_profiling_kollision_abschnitt1.md`, 2026-07-09) lief
**unverdünnt** (stride=1, jedes Sample) und nannte 52,8 % `set_transform` bzw.
~11,5 s für `find_collisions`. Der reale Prüf-Tür-Pfad dünnt Travel aber vorher mit
`DEFAULT_TRAVEL_STRIDE = 5` aus (`finding.thin_travel_indices` → alle Druck-Samples +
jedes 5. Travel-Sample, Endpunkte je Travel-Lauf erhalten). Eine Baseline für den
Vorher/Nachher-Beleg muss auf **derselben verdünnten Sample-Auswahl** laufen, die
auch der Realpfad prüft — sonst vergleicht #215 Äpfel (verdünnt, SDF) mit Birnen
(unverdünnt, FCL).

**Drift seit S5 (festgehalten, nicht kaschiert):** Die Pipeline (Slicer/Decompose/
Kinematik) ist seit dem 2026-07-09-Lauf um dutzende Commits fortgeschritten. Der
gespeicherte Lauf `runs/20260709-140251_slice_Denkmal` reproduziert **nicht mehr
byte-genau** (S5: 19 535 Samples, 8688/2405/8442, min −290,444 mm). Der aktuelle
Produktivpfad `slice_and_simulate_section("denkmal","abschnitt-1")` liefert
deterministisch **16 203 Samples, 6187/1938/8078, min −147,453 mm** (voller Befund,
stride=1, self=False). Die S5-Sonden wurden auf diesen Stand re-gepinnt
(`s5_harness.py`, Kommentar `RE-PINNED 2026-07-14 (#206)`); die AP-1-Baseline fußt
auf **diesem** deterministischen Fingerabdruck, nicht auf den historischen
S5-Zahlen.

## Messkonfiguration (festgeschrieben — #215 muss konfigurationsgleich laufen)

| Parameter | Wert |
|---|---|
| Lauf / Bahn | `runs/20260709-140251_slice_Denkmal` — Druckjob `default`, Projekt `projects/denkmal`, `section_id = abschnitt-1` |
| Reproduktion | `fgc.pipeline.actions.slice_and_simulate_section(artifact, job, "abschnitt-1")` → `find_collisions` (kein Lauf geschrieben) |
| Zerlegungsart | `modul` (freizone 40 mm, safety 50 mm) |
| Endeffektor | Tool `30gut`, provisorische Hülle aktiv (`tool_hull = True`) |
| **Travel-Stride** | **5** (`finding.DEFAULT_TRAVEL_STRIDE`, Auswahl über `finding.thin_travel_indices` — dieselbe Funktion wie der Realpfad) |
| Samples voll (stride=1) | 16 203 (davon 5445 Travel) |
| **Samples verdünnt (stride=5)** | **11 968** |
| Schichten | 55 |
| `self_collision` produktiv | **False** (so baut `finding` den Befund; Selbstkollision hier als *eigener* Aufrufort separat vermessen) |
| Rechner | Windows 11 (10.0.26200), Python 3.14.0, Intel64 Family 6 Model 197 (Core Ultra), Projekt-venv, `python-fcl 0.7.0.11`, Roboter `doosan_m1013` (VHACD-Urteilsgeometrie + Hüllen-Breitphase, S0/#125) |

**Determinismus:** `find_collisions` auf der verdünnten Auswahl liefert über zwei
Läufe byte-identisch **5106 rot / 1142 gelb / 5720 grün, min −149,824 mm, worst_index
9794** (Gate `identical: true`; python-fcl bytegleich, S0). Die instrumentierte
Nachbildung (Aufrufort-Trennung) trifft dieselben rot/gelb/grün-Zahlen (Gate
`instrumented_match: true` für beide Aufruforte). **Absolutzeiten sind Messwerte**
(Einzelmaschine, keine isolierte Bank) — belastbar sind die **Zählwerte** und die
**Konfiguration**.

## Sonde

`docs/spikes/s5_scripts/s5_ap1_baseline.py` (Sonde 4) — baut auf
`s5_harness.build_inputs()` (reale Abschnitt-1-Eingaben) und spiegelt den
`find_collisions`-Loop wie `s5_instrumented.py`, aber (a) auf der **verdünnten**
Auswahl und (b) mit Timern **getrennt nach Aufrufort**. Aufruf (venv, Repo-Root):

    ./.venv/Scripts/python.exe docs/spikes/s5_scripts/s5_ap1_baseline.py

Schreibt `docs/spikes/s5_scripts/last_ap1_baseline.json` (die hier zitierten Zahlen).

## Ergebnis

### 1 — Gesamtlaufzeit (produktiv verdünnt, self=False = Produktiv-Befund)

`find_collisions` auf der verdünnten Auswahl (11 968 Samples), drei Läufe:
**6,82 / 7,03 / 7,17 s** → **~7,0 s** (Median 7,03 s, Min 6,82 s). Das liegt im von
der PRD genannten Fenster „7–16 s je Teil" und bestätigt: die Realpfad-Zahl enthält
bereits stride=5. Kontext: Slice+Simulation ~5,85 s, FK `link_frames` ~0,96 s (nicht
Teil von `find_collisions`).

Zum Vergleich der volle Befund (stride=1, 16 203 Samples, self=False) reproduziert
6187/1938/8078, min −147,453 mm.

### 2 — FCL-Referenz je Aufrufort (der eigentliche Baseline-Wert)

| Aufrufort | fcl-Aufrufe | fcl-Zeit gesamt | ms/Aufruf | `set_transform` | Breitphase (verworfen) |
|---|---:|---:|---:|---:|---:|
| **Arm↔Hindernis** (self=False, produktiv) | 23 468 | **0,94 s** | **0,040** | 3,40 s | 82 257 (71,5 %) |
| **Selbstkollision / Arm↔Arm** (self=True, produktiv AUS) | 54 248 | **122,59 s** | **2,260** | 13,56 s | 251 328 (78,4 %) |

**Kernbefund für #215:** Die beiden Aufruforte sind **völlig verschiedene
Kostenblöcke** und müssen im Vorher/Nachher getrennt bilanziert werden:

- **Arm↔Hindernis** ist billig in der fcl-Distanz (0,94 s / 0,040 ms je Aufruf).
  Wie in S5 dominiert hier **nicht** die Distanz, sondern das Positionieren der
  VHACD-Urteilsgeometrie (`set_transform`, 3,40 s — ~3,6× die fcl-Zeit). Der Arm
  läuft gegen den Druckstand (ein Hindernis-Manager je Gruppe).
- **Selbstkollision** ist der **teure** Block: 2,26 ms je Aufruf, **~56× teurer**
  als ein Arm↔Hindernis-Aufruf, in Summe **122,6 s** fcl-Zeit. Ursache: Hier prüft
  `min_distance_other(Glied-Manager_i, Glied-Manager_j)` **zwei** VHACD-Manager mit
  je ~36 Konvexstücken gegeneinander (~36×36 Stückpaare je Aufruf), nicht Glied gegen
  einen kompakten Hindernis-Mesh. Der volle self=True-Lauf (verdünnt) misst
  **147,7 s** wall.

Genau diesen zweiten Block hätte eine reine self=False-Baseline **übersehen** — die
PRD verlangt „kein Kostenblock übersehen" (US 13). Für die SDF-Ablösung heißt das:
Der Glied-SDF-Pfad muss vor allem den **Arm↔Arm**-Block drücken, wo FCL 122,6 s
kostet; der Y-fach-Faktor je Aufrufort wird daher sehr unterschiedlich ausfallen und
ist getrennt zu berichten.

### 3 — Breitphase greift (beide Aufruforte)

Der AABB-Breitphasenfilter verwirft **71,5 %** der Arm↔Hindernis-Paare und **78,4 %**
der Arm↔Arm-Paare, bevor fcl befragt wird — konsistent mit S5 (67,8 %). Der
Hindernis-Rebuild je Schicht ist vernachlässigbar (55 Rebuilds, 0,076 s gesamt; der
`group_cache` greift).

## Baseline-Kennzahlen (Kopiervorlage für die #215-Abnahme)

| Kennzahl | Wert (FCL-Referenz, verdünnt) |
|---|---|
| Samples verdünnt / voll | 11 968 / 16 203 |
| Befund verdünnt (rot/gelb/grün) | 5106 / 1142 / 5720 (min −149,824 mm) |
| `find_collisions` self=False (Produktiv) | Median **7,03 s** (Min 6,82 s) |
| **Arm↔Hindernis** fcl | 23 468 Aufrufe, **0,94 s**, 0,040 ms/Aufruf |
| **Selbstkollision** fcl | 54 248 Aufrufe, **122,59 s**, 2,260 ms/Aufruf |
| `set_transform` Arm↔Hindernis / Arm↔Arm | 3,40 s / 13,56 s |
| `find_collisions` self=True (verdünnt) wall | 147,7 s |

## Einschränkungen / Unsicherheiten

- **Selbstkollision ist produktiv AUS.** Sie wird hier als *eigener Aufrufort* auf
  derselben verdünnten Auswahl vermessen, weil die SDF-Ablösung (US 13) beide
  Aufruforte ersetzt („Punkte von Glied A gegen SDF von Glied B", PRD Lösung 1). Die
  122,6 s sind **kein** Teil des heutigen Produktiv-Befunds — der reale Prüf-Tür-Lauf
  kostet ~7 s (self=False).
- **Absolutzeiten sind maschinen-/lastabhängig** (Einzelmaschine). Die
  **relativen** Anteile und **Zählwerte** (fcl-Aufrufe, Samples, rot/gelb/grün) sind
  die belastbare Grundlage; die fcl-Distanzen selbst sind deterministisch (S0).
  **#215 muss auf demselben Rechner** (oder mit ausgewiesenem Rechner) und
  **derselben Konfiguration** (Tabelle oben) laufen, sonst ist der Y-Faktor nicht
  aussagekräftig.
- **Drift-Vorbehalt.** Ändert sich Slicer/Decompose/Kinematik erneut, verschiebt sich
  der Fingerabdruck (16 203/11 968 Samples). #215 sollte die Baseline **unmittelbar
  vor** der Nachher-Messung mit dieser Sonde neu erheben (dieselbe Sonde liefert beide
  Hälften konfigurationsgleich), statt die hier gedruckten Absolutzahlen zu
  übernehmen.
- Zahlen gelten für **diesen** Modul-Lauf (ein wachsendes Hindernis, kein Boden, keine
  früheren Teile). Ein Abschnitt-Modus-Lauf mit Boden + früheren Teilen hätte mehr
  Hindernisgruppen und mehr Arm↔Hindernis-fcl-Aufrufe; die Arm↔Arm-Kosten (arm-intern)
  blieben qualitativ gleich.

## Sonden (Stand nach #206)

- `s5_harness.py` — reproduziert die reale Bahn + Gate (auf aktuellen Stand re-gepinnt).
- `s5_cprofile.py` → `last_cprofile.txt` (S5).
- `s5_instrumented.py` → `last_instrumented.json` (S5, unverdünnt).
- `s5_threshold.py` → `last_threshold.json` (S5).
- **`s5_ap1_baseline.py` → `last_ap1_baseline.json` (neu, #206) — AP-1-Baseline,
  verdünnt, je Aufrufort.**
