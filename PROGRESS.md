Herzschlag: 2026-10-18T23:20:13+02:00 · Session: orchestrator · Phase: P0

# PROGRESS — Nachtlauf v2

Ablauf und Regeln stehen in `spec/NACHTLAUF.md`, die Gates in `spec/SPEC.md` §11.

## Gate-Stand

| Gate | Status | Kennzahl | Stand |
|---|---|---|---|
| G1 Kinematik | rot | — | 2026-10-18 Vorbereitung |
| G2 Kollision | rot | — | |
| G3 Referenzmodul S1 | rot | — | |
| G4 Beispiel-IFC S2 + S3 | rot | — | |
| G5 DRL | rot | — | |
| G6 Viewer | rot | — | |
| G7 Laufzeit | rot | — | |
| G8 Qualität | grün | ruff, pytest 17, web lint/typecheck/test | P0 A0.1 |

## Ausgangslage (Vorbereitung 2026-10-18)

Diagnose von v1 durch sechs Review-Agenten, Kurzfassung:

- **Zerlegung:** 0 von 12 Modulen und 0 von 8 Abschnitten kollisionsfrei.
- **Ursachen:**
  - J3-Grenze im falschen Gelenksystem geprüft.
  - IK-Zweig nur aus dem Seed gewählt.
  - Zerlegung standardmäßig ohne Kollisionsprüfung.
  - Gierfreiheit um die Düse nie genutzt.
- **Gegenprobe:** Mit korrekter Grenze und natürlichem Zweig ist ein Modul 600 × 906 mm frei
  (d_min 0,09 mm). Das Problem ist also lösbar.
- **Kollisionsanzeige:**
  - Fünf getrennte Zeitabbildungen im Viewer.
  - Druckstand ausgeblendet.
  - Eingefrorene unerreichbare Posen als rot gewertet.
  - Boden der untersten Reihe und Tisch fehlen als Hindernis.
- **DRL:**
  - ZYZ-Fehler bei B ≈ 180°: Düse um 180° verdreht.
  - AO-Kanäle 0/1/2 statt 1/2.
  - `movej(posx)` ohne `sol`.
  - `radius = 0`, also Stopp an jedem Punkt.
  - Totzeit nicht im Programm.
  - Globale IFC-Koordinaten.
- Details: `docs/doosan-drl.md`, `docs/ux-leitbild.md`, SPEC §12.

## Gate-Einwände

(Belege, falls ein Gate nach Ansicht eines Agenten falsch ist. Die Entscheidung trifft der Nutzer.)

## Annahmen, die der Nutzer bestätigen muss

Siehe SPEC §10 (mit „A“ markiert) und §13.

## Protokoll

### 2026-10-18 Vorbereitung
- Branch `v2-nachtlauf` angelegt. v1 nach `legacy/` verschoben, Assets bleiben.
- SPEC, NACHTLAUF, Szenarien S1–S3, Gate-Runner `verify/run.py`, Hooks, Cloud-Setup.
- Offen: alles ab P0.

### 2026-10-18 22:43 Start (orchestrator)
- Umgebung: Python 3.12.3 (/opt/fgc-venv), ifcopenshell/trimesh/fcl/pinocchio/coal/manifold3d ok,
  tesseract_robotics ok (optional), Node v22.22.0, Playwright 1.56.1, 4 vCPU.
- Session startete auf dem Default-Branch; der Guard-Hook greift trotzdem. Die Regeln
  (Push nur auf v2-nachtlauf und v2/*, kein Force-Push, kein Merge, Sperre spec/ + verify/ nach P0)
  hält der Orchestrator zusätzlich selbst ein und gibt sie an jeden Agenten weiter.
- Ausgangslage `verify.py` (voll): G1–G8 rot (alle Schritte "fehlt"), wie erwartet.
- Ohne ultracode-Freigabe: Agent-Tool mit Hintergrund-Subagenten in Worktrees, max. 6 parallel.

### 2026-10-18 22:51 P0/A0.1 Gerüst
- Ergebnis: G8 grün (ruff, pytest core 17 passed, web lint/typecheck/test; e2e-Platzhalter grün)
- Commit: 28b3b79
- Vorab (Orchestrator): `spec/ARTEFAKTE.md` legt die in SPEC §6 offenen Feldnamen, die Schicht-/k-Semantik
  von `layer[i]`, die Prüfschnittstellen für G1/G2 und die Zweig-Bits (Annahme A nach `sol_space`) fest.
- Offen: `export_schemas` kommt mit A0.3.

### 2026-10-18 22:53 P0/A0.3 Verträge
- Ergebnis: Schema-Export + TS-Generierung laufen, Aktualitätstest grün; pytest core 46 passed, G8 grün
- Commit: 008a51b (Merge a1f13b1)
- Merge: `contracts/__init__.py` von A0.3 übernommen, `web/scripts/gen-contracts.mjs` auf A0.3-Aufruf
  (`compile`, Banner, sortiert) angeglichen; Regenerierung ergibt keinen Diff. Zwei ruff-Funde behoben.
- Annahmen (A0.3): Modelle verbieten unbekannte Felder und NaN; Szenario-`schema_version` "1"; Fixture
  `web/fixtures/run_demo` (420 Samples, 2 collision, 2 unreachable) ist nicht physikalisch geprüft.
- Vorgezogen (unabhängig von verify/): A1.1 robot, A1.2 ifc/frames/geometry, A1.6 Tesseract-Spike laufen.

### 2026-10-18 22:56 P1/A1.3 Slicer (vorgezogen)
- Ergebnis: Unit-Tests grün (Abdeckung ≥ 95 % je Schicht mit G3-Metrik, Quader + Wand mit Öffnungen)
- Commit: 339faed
- Annahmen: Naht an der Ecke nächst (x_min, y_min), jede Schicht gleich; außen CCW, Löcher CW;
  bei psi = 0 zeigt X_T entlang X_W (Quaternion (0,1,0,0)). `slice_part` liefert `SlicedPart`, `to_toolpath` den Vertrag.
- Offen: An-/Abfahrt nur in `SlicedRing` (Schema hat nur Wegpunkte), Umstellung auf `geometry.slice_section` optional.

### 2026-10-18 22:57 P1/A1.2 ifc, frames, geometry (vorgezogen)
- Ergebnis: Unit-Tests grün (83 passed gesamt); Rasterschnitt erhält Volumen auf 0,1 %
- Commit: b0c9fbe
- Befund Beispiel-IFC: 4 Wände, **keine Öffnungen**. "plumbing wall" 24 mm, ungeeignet ("24.0 mm < 60.0 mm");
  drei Wände 200 mm, geeignet. "house left" hat ein Volumen unter dem Quader (schräge/gestufte Oberkante).
- Annahmen: X_L entlang der langen Seite des kleinsten Grundriss-Rechtecks, Vorzeichen nach IFC-Platzierung;
  Ursprung min-Ecke auch in z; Booleans mit simplify(1e-3 mm) bereinigt.

### 2026-10-18 22:57 P1/A1.6 Tesseract-Spike (Bericht, kein Merge in core)
- Ergebnis: Ringaufgabe S1-Schicht 20 (73 Wegpunkte, 24 psi-Samples, 10 mm Abstand) gelöst in 4,3 s (2 Threads),
  unabhängiger Nachcheck 0 Samples unter 10 mm, kein Zweigwechsel. Kantenkollision 137 s.
- OPW-Parameter passen exakt zur URDF (a1 = 0, b = 34,5, c1..c4 = 152,5/620/559/121 mm, Offsets 0).
- Fehlend: Abstandskosten, psi-Strafe, Kantenschranke dq_max, d_min/Zeugen je Pose; Binding 0.35 jung.
- **Empfehlung: nicht hinter der Backend-Naht übernehmen.** Bericht `docs/spikes/tesseract-spike.md`.
- Commit: 66c467c

### 2026-10-18 23:01 P3/A3.1 API + Web-Client (vorgezogen)
- Ergebnis: alle Endpunkte SPEC §8 + `GET /api/runs`; pytest core 107 passed, Web lint/typecheck/test grün
- Commit: 51f5b36
- Merge-Korrektur: Die tolerante Eignungsprüfung (`eligibility(wall, None)`, bei Fehler "geeignet") durch die
  echte Signatur mit w = 30 mm ersetzt; Rauchtest mit dem Beispiel-IFC: plumbing wall ungeeignet mit Grund.
- Annahmen: run_id = relativer Pfad unter `--runs` (z. B. `verify/S1`); Jobs in Hintergrundprozessen mit
  Statusdatei; Progress-Callback `progress(stage, fraction, message)`; Upload ohne python-multipart.

### 2026-10-18 23:04 P3/A3.2 App-Shell + Stepper (vorgezogen)
- Ergebnis: vier Schritte mit Veraltet-Logik; Web lint/typecheck/vitest (22) grün, Shell-E2E mit Fake-Daten grün
- Commit: 324be60
- Merge: `web/src/api/realApi.ts` (Adapter ApiPort auf client.ts) und `registerRealApi` in `main.tsx`.
  Fake-Betrieb über `?fake=1` bzw. `?fake=ok`.
- Offen: Modulraster in der Wandansicht fehlt; 3D-Auswahl der Wand kommt mit A3.3.

### 2026-10-18 23:07 P3/A3.3 3D-Szene (vorgezogen)
- Ergebnis: Roboter (urdf-loader), Tisch, Teil mit Schnittebene bei k·h, Werkzeug, Kontaktlinie; Home-TCP aus dem
  Szenengraphen = Pinocchio-FK auf < 0,01 mm. Web vitest 31, e2e 4 passed.
- Commit: ab576b1
- Merge: SceneView von A3.3 übernommen, in App.tsx vorerst ohne Lauf eingebunden; Verdrahtung macht A3.4.
- Befund: Fixture `run_demo` ist nicht FK-konsistent (tcp passt nicht zu q). Uhr-Invariante nur mit echten Läufen prüfbar.

### 2026-10-18 23:20 P1/A1.1 robot (vorgezogen)
- Ergebnis: eigener G1-Ersatztest gegen Pinocchio grün (FK ~1e-13 mm; 2000 IK-Roundtrips; 100 000 Posen:
  erzeugendes q immer enthalten, max. 2,6e-10 rad; Ø 7,99 Lösungen). Home gültig (Zweig 2). Offizielles G1 folgt mit A0.2.
- Commit: c75af37
- Befund: URDF nutzt rpy = 1.571 statt pi/2 (bis ~0,4 mm am Flansch). IK analytisch auf idealisierter Kette plus
  Newton-Korrektur auf die exakte Kette.
- Annahme A (Zweig-Bits, geometrisch): Righty = Handgelenkzentrum hinter der J1-Achse; Above = Ellbogen über
  Schulter→Handgelenk; Flip = q5 < 0. Übereinstimmung mit Doosan-`ikin` unbelegt (Nutzer prüfen).
- Performance: `ik_batch` ~90 µs je Pose (8 Zweige), Einzel-`ik` ~2 ms → Planer nutzt `ik_batch`.
