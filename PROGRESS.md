Herzschlag: 2026-10-19T16:35:00+02:00 · Session: cloud-verify · Phase: P6 abgeschlossen, Nutzertest nachgeprüft

# PROGRESS — Nachtlauf v2

Ablauf und Regeln stehen in `spec/NACHTLAUF.md`, die Gates in `spec/SPEC.md` §11.

## Gate-Stand

| Gate | Status | Kennzahl | Stand |
|---|---|---|---|
| G1 Kinematik | grün | 2000 FK + 2000 IK gegen Pinocchio | P0 Ende |
| G2 Kollision | grün | 500 Posen; d_rp ≥ 0,5 mm unter d_coal, |Δ| ≤ 4,3 mm (beide ≥ 0) | P1 A1.4 |
| G3 Referenzmodul S1 | grün | d_min 10,83 mm; 90,5 % ok / 9,5 % warn; 0 coll/unreach | Cloud-verify 19.10. (Basis gedreht) |
| G4 Beispiel-IFC S2 + S3 | grün | S2 172 Module (4 geprüft), check_run 58 s; S3 bestätigt | Cloud-verify 19.10. |
| G5 DRL | grün | fake_drcf S1 + S2 36,5 s | Cloud-verify 19.10. |
| G6 Viewer | grün | e2e 8 passed (57 s), Uhr-Invariante 50 t S1+S3 | Cloud-verify 19.10. |
| G7 Laufzeit | grün | S1 76,9 s, S2 330,5 s | Cloud-verify 19.10. |
| G8 Qualität | grün | ruff, pytest core, web lint/typecheck/test | Cloud-verify 19.10. |

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

- **G2 bei Durchdringung (Orakel A0.2, vor LOCKED übernommen):** Für sich durchdringende nichtkonvexe Meshes ist die
  Eindringtiefe nicht eindeutig. Das Orakel liefert eine Unterschranke aus Mesh-Ecken im anderen Solid. G2 verlangt
  dort d_rp ≤ 1 mm (statt d_rp ≤ d_coal + 1 mm) und gleiches Vorzeichen bei |d| > 12 mm. Das ist eine bewusste
  Lockerung gegenüber dem Wortlaut von SPEC §11 G2 nur für Kollisionsposen; der Nutzer sollte sie bestätigen.
- **Paar base_link ↔ link_2 (SPEC §5.1, Glied i ↔ j ≥ i+2):** Auf den Roh-Meshes konstant 33,2 mm < d_target 50 mm.
  Jedes Sample ist damit höchstens `warn`, nie `ok`. G3 (d ≥ d_hard = 10 mm) bleibt erreichbar. Vorschlag: Paar
  ausnehmen oder d_target nur gegen Umgebungshindernisse anwenden (Nutzerentscheidung).
- **Blending vs. Bahntreue:** r_blend = 2 mm schneidet eine 90°-Ecke um ~0,83 mm; G3 erlaubt 0,5 mm Bahnabweichung.
  Die geprüfte Trajektorie modelliert kein Blending (movel bis zum Punkt), am Gerät weicht die Bahn an Ecken also bis
  ~0,8 mm ab. Kein Gate-Fehler, aber eine Lücke zwischen Prüfung und Gerät.

- **Aus der Gegenprüfung A2.4 (`docs/gegenpruefung-a2-4.md`), Prüfer seit LOCKED nicht änderbar:**
  - Schichtreihenfolge prüft kein Gate (M4: Schicht 1 vor Schicht 0 besteht beide Prüfer).
  - Freizone Düsenspitze ↔ Druckstand gilt auch im Travel (M7: TCP 5 mm im Material besteht). S1 hält ≥ 29,9 mm.
  - SPEC §5.1 prüft Düsenspitze ↔ Glieder nicht (Pose (0,0,90,0,−145,150)°: Düse 6,4 mm in link_4, Status `warn`).
    In S1 ≥ 165 mm.
  - Im S1-Modus fehlen Abgleich Teil ↔ Szenario, Tischfläche, Druck außerhalb des Teils (M1, M5, M6);
    fake_drcf übergeht fehlendes `movej(home)` (M3); erfundene `d_mm`/`pair` bestehen (M2).
  - Zwischen Samples wird nicht geprüft (theoretisch bis 2,6 mm Abfall je Schritt; in S1 gemessen ≤ 0,001 mm).
  - Reserve Schicht 0 = h + 1,85 mm (Düsenmesh endet 1,85 mm vor dem TCP): bei h < 8,15 mm ist jedes Teil unmachbar.
  Vorschlag: Prüfer nach Nutzerfreigabe härten und M1–M7 als Selbsttests aufnehmen. Systemseitig prüft A4.2 diese
  Punkte zusätzlich selbst.

- **Mini-Lauf `verify/oracle/minirun.py` an die alte Basislage gebunden (Cloud-verify 19.10.):** Seit der Drehung der
  Basis (1acdd9d) erzeugt der Mini-Lauf (Seed J1 = −90°, Teil bei (0, −100) in S) 1183 von 1598 Samples `collision`
  (link_3/link_2 ↔ Tisch, d_min −0,001 mm), meldet im Summary aber weiter `machbar` mit n_collision 0. Kein Gate nutzt
  ihn, nur die Selbstprüfungs-Tests (`core/tests/test_selfcheck.py`), die keine Kollision prüfen. Vorschlag: Seed
  J1 = 90° (Arm zur Arbeitsfläche), Nutzerentscheidung, verify/ gesperrt. G2 nutzt denselben Seed nur für Zufallsposen
  und bleibt aussagekräftig (Abstandsvergleich, grün).
- **check_run auf S2 nicht ausführbar (Speicher):** `verify/check_run.py` lädt alle Teile gleichzeitig. Gemessen
  3,6 GB Spitze für 20 der 172 S2-Module, hochgerechnet ~30 GB; auf der 16-GB-VM beendet der OOM-Killer den
  Prüfer nach 1086 s (Exit −9, dmesg: anon-rss 13,9 GB). Systemseitig verkleinert A4.6 die Trajektorien; eine
  Prüfung Teil für Teil im Prüfer wäre die eigentliche Lösung (Nutzerentscheidung, verify/ gesperrt).

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

### 2026-10-18 23:23 P3/A3.4 Player + G6-Suite (vorgezogen)
- Ergebnis: eine Uhr (`sampleAt`), Timeline, Kollisionsliste, Debug-Schnittstelle, Direkteinstieg `/?run=&part=`;
  vitest 47 grün; G6-Suite schlägt erwartungsgemäß fehl, solange `runs/verify/S1`/`S3` fehlen; mit FK-konsistenten
  Dev-Läufen waren alle 8 e2e-Tests grün.
- Commit: 9b16a28
- Annahme (Nutzer prüfen): Im G6-Glückspfad beantwortet der Test nur die beiden Job-Endpunkte per `page.route`
  und verweist auf den Lauf S1 (alles andere echte API). Ein echter Job läuft mit `G6_REAL_JOB=1`.
- Annahme: Uhr-Invariante (1 mm) nimmt `unreachable`-Samples aus (q dort nur Anzeige); Status an allen 50 t geprüft.

### 2026-10-18 23:31 P1/A1.5 DRL-Emitter (vorgezogen)
- Ergebnis: v2 und v3 bestehen einen eigenen strengen G5-Prüfer (`core/tests/drl_checker.py`, Pinocchio-FK,
  eigene ZYZ, ohne roboprint) auf einem FK-konsistenten Mini-Plan; manipulierte Programme werden abgelehnt.
  Offizielles G5 (`verify/fake_drcf`) steht noch aus (A0.2). pytest 141 passed.
- Commit: 29f69c9
- Annahmen A: Orientierungsgeschw./Beschleunigungen (Druck 60 °/s, 500 mm/s², 120 °/s²; Travel 90 °/s,
  1000 mm/s², 180 °/s²), set_accj = 4 × 30-%-Gelenkgeschw.; v3 druckt standardmäßig wie v2 mit movel.
- Offen (Gerät): ob `try/finally` in DRL 2.x läuft und ein Stopp am Teach Pendant es auslöst.

### 2026-10-18 23:53 P0/A0.2 Orakel → P0 abgeschlossen, spec/LOCKED
- Ergebnis: Orakel-Selbsttests 40 passed (~18 s), ruff grün. **G1 grün** gegen das echte `roboprint.robot`.
- Vorabprobe G5: `verify.fake_drcf` akzeptiert die vom Emitter (A1.5) erzeugten v2/v3-Programme des
  handgebauten Mini-Plans (0 Fehler).
- Unabhängigkeit: `grep roboprint verify/` zeigt Imports nur in `test_g1_*`/`test_g2_*` (sonst Kommentare).
- Commit: c96b675; LOCKED auf 69f416d
- Annahmen A0.2 (verify/README.md): fake_drcf lehnt moveb/movejx/ori_type ab, Kartesisch ≤ 1000 mm/s (Datenblatt),
  Programm endet auf dem letzten Trajektorien-Sample; Zweig-Bits als 1:1-Zuordnung zu eigenen Konfigurationsklassen
  mit Singularitätsabstand. G2-Szene: Quader bei S = (0, −50), Gier 0, k = 20, Seed 20261018.

### 2026-10-19 00:26 P1/A1.4 Kollisionswelt → P1 abgeschlossen
- Ergebnis: **G2 grün** (500 Posen; konservativ, Abweichung bei freien Posen ≤ 4,3 mm, Ø 2,1 mm). G8 grün,
  pytest core 153 passed. 1,8 ms je Pose (1,7 ms mit upper = 50 mm).
- Commit: c9938a6
- Home-Pose frei über dem Tisch, d_min 30,7 mm (base_link ↔ link_2).
- **Abweichung von SPEC §5.1 (Nutzer prüfen):** keine VHACD-Zerlegung. VHACD lieferte auf diesen Meshes hohle
  Schalen (link_1: 1,1e6 statt 4,6e6 mm³), tiefe Durchdringungen blieben unentdeckt. Stattdessen eigene
  Hüllen-Bisektion mit 5 mm Toleranz und Aufblasen, sodass jeder Roh-Oberflächenpunkt abgedeckt ist (konservativ).
  Tisch: je Komponente eine konvexe Hülle (Toleranz 25 mm, ignoriert die Nuten der Profile).
- Kaltstart des Geometrie-Caches (~/.cache/roboprint/collision) ~3,5 min; zählt bei leerem Cache gegen G7.
- Offen (P4): Frame-Übergänge in `collision.py` liest das Modul direkt aus den JSONs – in `frames.py` zusammenführen;
  `robot.py` kann auf `urdf_chain.py` umstellen.

### 2026-10-19 00:34 P4/A4.0 Konsolidierung (vorgezogen)
- Ergebnis: G1, G2, G8 grün; Kollisionswelt nutzt frames/assets statt eigener JSON-Lesung; URDF wird nur noch in
  `urdf_chain.py` geparst. `ik_batch` unverändert schnell (20k Posen ~1,9 s).
- Commit: 929fe77

### 2026-10-19 00:59 P2/A2.1 Planer, Travel, Verdichtung, timing, pipeline, CLI
- Ergebnis: **G3 grün** (S1 machbar, d_min 10,83 mm nozzle_tip ↔ table in Schicht 0, 62 112 Samples, 0 collision,
  0 unreachable, 0 Zweigwechsel); **G5 grün für S1** (v2 + v3). `verify --fast`: G1, G2, G3, G5, G8 grün.
  Laufzeit S1 run-scenario 89,8 s (Grenze 180 s), check_run 26,7 s. S3: nicht machbar, 68 594 collision-Samples,
  d_min −207 mm, check_run bestätigt.
- Commit: 358e40d
- Verfahren: Planung mit schnellem Kugel-Double, danach jedes Sample gegen `collision.World` (3 Prozesse);
  bei Verstoß automatische Neuplanung mit der echten Welt. Platzierung S1: (−500, 325) mm, Gier 0°.
- Annahmen: nach dem letzten Ring nur `lift`, kein Rücktransfer nach Home; ein zusätzliches Druck-Sample am
  Ringstart trägt t_tot; Teil-ID bei Box `box_01`. Reserve zum Tisch in Schicht 0 knapp (10,83 mm bei d_hard 10 mm),
  weil die Düsenspitze nur 1,85 mm über dem TCP endet.
- Naht für P2/A2.2: `roboprint.decompose.scenario_parts(scenario, params) -> (walls, parts)`.

### 2026-10-19 01:09 P3 G6-Lauf gegen echte Läufe S1/S3
- Ergebnis: S3 erzeugt, check_run bestätigt (BESTANDEN). e2e: 7 passed, 1 failed – G6-Uhr-Invariante läuft in den
  Test-Timeout (120 s) bei `seek` auf den 62k-Sample-Läufen. Glückspfad und Kollisionspfad S3 grün.
- Offen: A3.5 (opus) behebt die Laufzeit von `seek`, ohne das Kriterium zu lockern.

### 2026-10-19 01:21 P2/A2.4 Gegenprüfung
- Ergebnis: kein falscher Systemstatus gefunden; S1 auch zwischen den Samples frei (1464 kritische Schritte,
  min 11,85 mm). Prüferlücken und SPEC-Lücken unter „Gate-Einwände“ eingetragen.
- Commit: 6c27a7a
- Folgeaufgabe A4.2: systemseitige Selbstprüfungen (Schichtreihenfolge, Travel über Druckstand, Teil auf Tisch,
  Druck im Teil) und `timing` aus derselben Geschwindigkeitsquelle wie `drl`.

### 2026-10-19 01:40 P4/A4.2 Selbstprüfungen + eine Geschwindigkeitsquelle
- Ergebnis: `verify --fast` G1, G2, G3, G5, G8 grün. S1 run-scenario 121 s unter Last (andere Agenten), Selbstprüfung 1,8 s.
- Commit: 85e8cf8
- `selfcheck.py`: Schichtreihenfolge, Travel über dem Druckstand, Teil auf dem Tisch und frei von der Roboterbasis,
  Druck im Material (1 mm), Start in Home (0,5°), Teilmaße wie Szenario/Zerlegung. Verletzung → `nicht machbar`.
- `params.py` ist die eine Quelle für Geschwindigkeiten; Zeitachse und DRL nutzen jetzt dieselben Werte
  (An-/Abfahrt v_print, Abheben/Absenken v_travel).

### 2026-10-19 01:47 P3/A3.5 G6-Uhr-Invariante → P3 abgeschlossen
- Ergebnis: **G6 grün** (`verify --gate G6`, 53 s, gegen echte Läufe S1/S3). Kriterium unverändert.
- Commit: a469800
- Ursachen: Kontaktlinie übersetzte bei jedem Sample den Shader neu; `seek` wartete auf gestaute Animationsframes.
  Neu: dauerhaftes Linienmaterial, `seek` wartet auf die Gelenkwinkel im Szenengraphen, `PacedRender`
  (höchstens ein Frame in der GPU), memoisierte Timeline/Liste, Druckbahn einmal nach Schicht sortiert.
- Screenshots unter `web/e2e/screenshots/` aus dem Gate-Lauf aktualisiert.

### 2026-10-19 02:04 P4/A4.1 UX-Prüfer
- Ergebnis: Befund `docs/ux-befund-a4-1.md` (Top 10); 7 behoben (Kontrast Kontaktzahl, gesperrter Schritt grün,
  seitlicher Überlauf, Zurücksetzen-Knöpfe, Export-Hervorhebung, Klartext-Ursache, Begriffe/Zahlenformat).
  G6 und G8 nach dem Merge grün; Screenshots neu.
- Commit: 54bb407
- Offen: Wandvorschau in 3D (API liefert keine Wandgeometrie), Modulraster/Druckzeit/Fortschritt je Modul in
  Schritt 2, Kerntexte ohne Umlaute, Export-Bericht; „Weiter“ bei 1280 × 800 unter dem Falz.

### 2026-10-19 02:18 P4/A4.4 UX-Folgeaufgaben
- Ergebnis: Wandvorschau in 3D (`GET /api/projects/{id}/walls/{wall_id}.stl`), Modulraster in Wandansicht,
  Kennzahlen Druckzeit/d_min, Fortschritt je Modul, Umlaute im Eignungsgrund, „Weiter“ bei 1280 × 800 sichtbar.
  G6 und G8 nach dem Merge grün; Screenshots aus dem Gate-Lauf.
- Commit: 48d047c
- Offen: Annahmenliste im DRL-Kopf in ASCII-Umschrift, Export-Bericht.

### 2026-10-19 02:45 P4/A4.3 Laufzeit (G7)
- Ergebnis: S1 137 s → 32,9 s (Agentenmessung), im Gate-Lauf nach Merge 50,1 s unter Last; Trajektorie bitgleich.
  `verify --fast`: G1, G2, G3, G5, G8 grün. Quader 600×200×600: 138 → 53 s.
- Commit: 4903d27
- `World.distance_batch` blockweise mit engerer Vorauswahl (~3× schneller); bei Durchdringung jetzt das echte
  Minimum (vorher bis 59 mm zu flach). Ring-Graphen und dichte Prüfung in einem fork-Pool; `--jobs 0` = vCPU.

### 2026-10-19 03:18 P2/A2.2 Zerlegung (nach Container-Neustart übernommen)
- Der Container wurde gegen 03:10 neu gestartet; der Agent A2.2 und sein S2-Lauf gingen verloren. Sein Commit
  (rebased auf den Stand mit A4.3) war vollständig und wurde gemerged. pytest core 188 passed, ruff grün.
- Commit: d5b0bc1
- Vorlauf des Agenten (vor dem Rebase, alter Planer): S2 mit 172 Modulen, alle machbar; plumbing wall ungeeignet
  mit Grund; Zerlegung 1100 s. Gate G4/G7 läuft jetzt mit dem aktuellen Stand.

### 2026-10-19 04:24 P4 G4/G5/G7-Lauf mit S2
- Ergebnis: S2 run-scenario **1271,9 s** (Grenze 1800 s), 172 Module, alle machbar, plumbing wall ungeeignet mit Grund.
  **G5 grün** inkl. S2 (fake_drcf, 1071 s). **G4 rot:** check_run vom OOM-Killer beendet (siehe Gate-Einwände).
  G7 rot nur, weil S1 in diesem Teil-Lauf nicht gemessen wurde.
- Stichprobe check_run (20 Module der Giebelwand): echte Funde – Abdeckung < 95 % in den obersten Schichten der
  Giebelmodule `house_right_front_r9_c0/_c1` (Schicht 27–29: 0 %), weil die Schalen-Offsets im schmalen
  Querschnitt verschwinden.
- Aufgaben: A4.5 (Slicer, Schmalstellen-Abdeckung), A4.6 (adaptive Verdichtung, weniger Samples → weniger Speicher).

### 2026-10-19 04:30 P4/A4.5 Slicer Schmalstellen
- Ergebnis: Prüferwerte reproduziert (76,5 / 85,9 / 0 %), Ursache: Schalenringe verschwinden im schmalen Querschnitt.
  Fix: bis zu 3 geschlossene Zusatzringe mit kleinerem Versatz, wenn die Abdeckung < 97 %. Giebelmodul r9_c0 jetzt
  ≥ 98,4 % je Schicht. Unit-Tests + G3 (S1) grün. S2-Neulauf steht aus.
- Commit: f6974a4

### 2026-10-19 04:32 P4/A4.6 adaptive Verdichtung
- Ergebnis: S1 62 112 → 52 124 Samples (−16 %); bindend ist max|Δq| ≤ 0,005 rad (Untergrenze ~44 400 Druck-Samples),
  nicht der 5-mm-Schritt. G3 grün, Prüfer-Untergrenze d 10,014 mm. Speicherspitze check_run S1 642 → 623 MB:
  der Speicherbedarf je Teil im Prüfer hängt kaum an der Samplezahl. Das S2-OOM ist systemseitig nicht lösbar.
- Commit: 59b01d0

### 2026-10-19 05:29 P4 voller verify-Lauf
- Ergebnis: G1, G2, G3, G5, G6, G7, G8 **grün**; G4 **rot**, weil check_run auf S2 erneut vom OOM-Killer beendet
  wurde (1048 s, Exit −9). S2 run-scenario 1132,8 s, S1 33,6 s. G5 prüfte alle 172 S2-Programme + S1 (954,6 s).
- Commit: adec38b
- Nachweis-Lauf: check_run je Wand bzw. in Blöcken zu 20 Modulen und S3 separat (läuft).

### 2026-10-19 07:00 P5 Abschluss
- S2-Nachweis in Teilmengen (unveränderter Prüfer): 172/172 Module ohne Fehler je Modul; Giebelwand komplett
  bestanden; Blockvolumina summieren sich zum Wandvolumen. S3 separat BESTANDEN (61 010 bestätigte Kollisionen).
- README v2 und MORGENBERICHT.md committet, Draft-PR v2-nachtlauf → main geöffnet (nicht gemerged).
- Endstand Gate-Runner: G1, G2, G3, G5, G6, G7, G8 grün; G4 rot (Prüfer-Speicher, siehe Gate-Einwände).

### 2026-10-19 08:25 Nacharbeit nach Nutzerentscheidung
- **Nutzerfreigabe (Tobias, Chat):** `verify/` darf geändert werden, damit der Prüfer Teil für Teil prüft und
  allgemein ressourcenschonend wird. Das Paar base_link ↔ link_2 (~33 mm) ist akzeptabel: Es zählt künftig für
  collision und d_hard, aber nicht mehr für die d_target-Schwelle (warn). G2-Lockerung bei Durchdringung erklärt.
- Aufgaben: A6.1 Prüfer Teil für Teil + Cache (verify/, SPEC-Nachtrag), A6.2 Statusregel base_link ↔ link_2 (core),
  A6.3 Laufzeit Zerlegen/Export (core).

### 2026-10-19 09:11 P6/A6.3 Zerlegen und Export schneller
- Ergebnis: S2 run-scenario **1131 s → 266 s** (decompose 486 → 246 s, export 645 → 19,5 s), Ergebnisse unverändert
  (172/172 machbar, gleiche Teile und d_min). S1 55 → 38 s. G3 grün, pytest 195 passed, fake_drcf auf S1 + neuem S2 bestanden.
- Commit: 32570b0
- Ursache: Der bestbewertete Platzierungskandidat des Hauptmoduls war nicht machbar und löste eine teure
  Nachplanung (~385 s) aus, bevor der zweite Kandidat geprüft wurde. Jetzt erst alle Kandidaten mit dem schnellen
  Double, Nachplanung nur, wenn keiner machbar ist. Export: Teile mit gleichem Plan (gleiche Geometrie und
  Platzierung) einmal aufbereiten, Kopien nur mit neuer part_id. Neues Feld `summary.parts[].same_as`.

### 2026-10-19 10:00 P6 voller verify-Lauf nach A6.1–A6.3
- Ergebnis: **G1–G8 alle grün.** S1 33,7 s, S2 195,0 s, check_run S2 555,8 s (Teil für Teil, Inhalts-Cache),
  S3 run 81,8 s + check 175,9 s, fake_drcf 33,6 s, e2e 54,9 s.
- Commit: aad5ffd
- Offen (A6.4, in Arbeit): Gliedpaare i ↔ i+2 nur gegen collision/d_hard; Warnschwelle 20 mm gegen den Druckstand
  (beide Nutzerentscheidungen 19.10.2026).

### 2026-10-19 11:35 P6 Abschluss: voller verify-Lauf
- Ergebnis: **G1–G8 grün.** S1 36,2 s (90,2 % ok, 9,8 % warn, d_min 10,83 mm), S2 225,8 s, check_run S2 55,4 s
  (4 von 172 Modulen geprüft, Rest byteidentische Kopien), S3 bestätigt, fake_drcf 28,7 s, e2e 42,2 s.
- Commit: 83be8ac
- A6.4: Gliedpaare i ↔ i+2 nur gegen collision/d_hard, d_target_printed 20 mm (Nutzerentscheidungen 19.10.2026).
  Im Prüfer sind am Druckstand zwischen 20 und 50 mm `ok` und `warn` zulässig; collision und d_hard bleiben streng.
- A6.5: Kopien schreiben part.stl/part.json byteidentisch zum Repräsentanten (Geometrie-Toleranz 0,01 mm).
- A6.6: Leistungseinbruch durch A6.4 behoben (S1 426 s → 36 s, Ergebnis identisch).

### 2026-10-19 12:55 Lokaler Start unter Windows
- Ergebnis: v2 läuft lokal unter Windows 11 mit Python 3.14 (`.venv`, `pip install -e "core[dev]"`, `npm --prefix web ci`).
  S1 machbar, d_min 10,83 mm, 0 collision, 0 unreachable, 208 s (Cloud 36 s). S3 nicht machbar, 61 011 collision, 49 s.
  API-Job Giebelwand (house right front) per curl ohne Parameter: 30/30 Module machbar, 264 s. Viewer rendert Lauf S1.
  (Korrektur 13:20: nicht über den Viewer gestartet; der Viewer schickt alle Parameter, siehe nächster Eintrag.)
- Neu: `scripts/dev.ps1` (Gegenstück zu `dev.sh`), Windows-Hinweise in der README.
- Ursache der Laufzeit: Windows kennt kein `fork`, alle Pools fallen auf einen Prozess zurück (`can_fork_pool`).
- Offen: Die Beispiele „Referenzmodul“ und „Kollisionsbeispiel“ im Schritt Modell schlagen fehl
  (`POST /api/projects` → 422 „Szenario hat keine IFC-Quelle“), weil S1/S3 eine Box als Quelle haben. G6 deckt das
  nicht ab, die e2e-Tests öffnen Läufe direkt über `?run=`.

### 2026-10-19 13:20 Viewer-Jobs repariert (Nutzertest Tobias)
- **Jeder Job aus dem Viewer scheiterte** mit „Unbekannter Parameter im Szenario: pump_voltage_v“. Der Viewer schickt
  alle Parameter aus `web/src/state/params.ts` mit, zwei Schlüssel wichen von `PlannerParams` ab
  (`pump_voltage_v` → `v_pump_v`, `ds_mm` → `step_mm`). Die API prüft Parameter jetzt beim Anlegen (422 mit Klartext)
  statt erst im Jobprozess. Test `test_web_default_params_accepted` liest `params.ts` und schickt die Standardwerte.
- **Quader-Beispiele S1/S3 im Schritt Modell**: Projekt mit einer Wand `box`, Wandmesh als Quader im Frame L. Der Job
  übernimmt das Beispielszenario (Quelle, Planermodus, `placement_override`), nur `params` kommen vom Viewer.
  Geprüft im Browser (Edge, headless): Kollisionsbeispiel → 61 011 collision, nicht machbar, Kollisionsliste.
- **Windows: `status.json`-Sperrkonflikt.** `os.replace` scheitert mit PermissionError, solange die API die Datei liest.
  Folge: erfolgreiche Jobs als failed gemeldet, Abbruch mitten im Lauf über den Fortschritts-Callback, verlorene
  Fehlermeldungen („Jobprozess beendet (Exit-Code 1)“). Jetzt kurze Wiederholung bei PermissionError und eine
  Temp-Datei je Prozess/Thread. Test `test_status_file_concurrent_read_write` (2000 Schreibvorgänge gegen Leser).
- Bekannt, nicht behoben: `test_traversal_symlink` scheitert unter Windows ohne Symlink-Recht (WinError 1314),
  unabhängig von diesen Änderungen.
- Zum Beispiel-IFC: Es enthält nur 4 IfcWall (links, rechts vorne, rechts hinten, Installationswand); die Giebelseiten
  vorne und hinten sind nicht modelliert. Die Wandvorschau legt die Wände als Raster nebeneinander (`layoutWalls`),
  nicht in Gebäudelage.

### 2026-10-19 14:30 Roboter gedreht, Transfer-Mindesthöhe, Hausansicht (Nutzertest Tobias)
- **Roboterbasis stand 180° verdreht.** Das Kabel tritt bei −Y_B aus `base_link` aus (URDF-Mesh, bis −349 mm) und
  lag mit `quat` (1, 0, 0, 0) auf dem Tisch (Kabelende y_W = 741 mm). Real hängt es über die nahe hintere Kante
  (y_W = 1230). Jetzt `quat` (0, 0, 0, 1): S liegt bei +485 mm in Y_B statt −485 mm. Folge vorher: Tisch und Teile im
  Basis-Frame gespiegelt, also DRL-Ziele hinter dem Roboter; die Sperrzone der Platzierung (konvexe Hülle von
  `base_link` samt Kabel) ragte 349 mm über die Arbeitsfläche. Test `test_cable_hangs_off_the_table`.
  **Alle Läufe und Gates vor diesem Eintrag gelten für die falsche Ausrichtung; voller verify-Lauf steht aus**
  (lokal fehlen Pinocchio und Coal, also in der Cloud).
- **Transfer sackte unter die Mindesthöhe.** Die movej zwischen zwei Ringen sank über dem Teil knapp unter
  z_lift − TOL_LIFT_MM (25 mm); der Planer hielt sie für frei, die Selbstprüfung (b) verwarf das Teil danach.
  Jetzt gilt so ein Transfer als unfrei und bekommt den Zwischenpunkt (SPEC §5.3). Test `test_transfer_sackt_unter_mindesthoehe`.
- **Höhenexperiment** (Quader 600 × 200, gedrehte Basis, mit Transfer-Fix, Windows seriell): 400 mm (S1) machbar
  θ = 90°; 500/600 mm machbar θ = 0° seitlich; 800 mm machbar θ = 90° (Suche) und θ = 0° direkt vor dem Roboter
  (lange Seite zum Roboter, d_min 10,00 mm). Laufzeit 4–7 min je Quader. Die Zerlegung begrenzt H* weiterhin auf
  `h_upper_mm` = 400 (`decompose_plan.DECOMPOSE_DEFAULTS`, Laufzeitannahme aus dem Nachtlauf); Anheben ist eine
  Nutzerentscheidung (Laufzeit G7, Prozess).
- **Hausansicht** im Schritt Modell: Umschalter „Wände nebeneinander | Haus“. API: `ProjectInfo.building_mm`,
  `GET .../walls/{id}.stl?frame=building` (Wand in Gebäudelage, Ursprung = min-Ecke der Wände in G),
  `GET .../context.stl` (Decken, Dach, Stützen usw. aus `ifc.read_context`). Quader-Projekte haben keine Hausansicht.

### 2026-10-19 16:00 Modulhöhe höchstens als Parameter (Nutzerentscheidung Tobias)
- **Neuer Parameter `module_height_max_mm`** (Standard 400 mm, Lehm unter Eigengewicht) in `PlannerParams` und im
  Viewer („Modulhöhe höchstens“). Er ist die obere Schranke der H*-Bisektion (`scenario_parts` → `h_upper_mm`).
- **H* wird mit voller Planung bestätigt** (`DecomposeParams.h_verify`, an in `DECOMPOSE_DEFAULTS`): Die Vorprüfung
  (Kugel-Double) hält Quader bis ~1000 mm für machbar. Danach bisektiert die volle Planung in 50-mm-Schritten
  zwischen h_min und dem Vorprüfungs-H*. Ergebnisse werden gecacht, Monotonie in Breite und Höhe genutzt. Test
  `test_hstar_volle_planung_bestaetigt_die_vorpruefung`. Viewer zeigt „höchstes Modul (Grenze X mm)“.
- **Giebelwand `1AQAupaRP1txwK1AGiN61V`, Windows seriell:** Grenze 400 mm → 30 Teile, alle machbar, höchstens 370 mm
  (10 Reihen à 370, letzte 296), 449 s. Grenze 1000 mm nach 1 h 45 min abgebrochen, ohne Ergebnis.
- **Offen: Laufzeit bei hoher Grenze.** Jeder Bestätigungsschritt über der Kollisionsgrenze ist eine volle Planung,
  die erst nach allen Platzierungen scheitert. Unter Windows seriell ist das für die App zu langsam. Messung mit
  4 vCPU und fork im Cloud-Lauf.

### 2026-10-19 16:21 Voller verify-Lauf nach gedrehter Roboterbasis (1acdd9d) und Testfix
- Ergebnis: **G1–G8 grün.** S1 59,0 s (40 718 Samples, 90,5 % ok, 0 collision/unreachable, d_min 10,83 mm),
  S2 259,9 s (172/172 machbar), check_run S2 47,1 s, S3 bestätigt, fake_drcf 24,0 s, e2e 45,9 s.
- Testfix b02740f: DRL- und Selbstprüfungstest lasen fest kodierte Werte aus der alten Basisorientierung.
- Commit: b02740f

### 2026-10-19 16:35 Cloud-verify nach Nutzertest
- Anlass: Basis um 180° gedreht (1acdd9d), Transfer-Mindesthöhe (55124ee), `module_height_max_mm` und `h_verify`
  (7e42743), API/Viewer (39340a5, 5019db7). Lauf auf der Cloud-VM (4 vCPU), Python `/opt/fgc-venv`.
- Parallel lief eine zweite Session (anderer Container, Eintrag 16:21, Testfix b02740f) mit demselben Befund; ihre
  Teständerungen und Screenshots sind übernommen, sie entsprechen meinen.
- Vorab `pytest core -n 2`: **2 rot**, beide Testannahmen der alten Basislage, kein Produktfehler:
  - `test_drl.py::test_checker_rejects_bad_programs` suchte den ZYZ-Text `180, 180, 0`; mit gedrehter Basis lautet
    die Düsenorientierung in B `0, 180, 0`. Die Mutation versetzt jetzt den ersten ZYZ-Winkel der ersten passenden
    `posx` um 180° (Basislage-unabhängig); der Prüfer schlägt weiter an.
  - `test_selfcheck.py::test_e_kein_home_start` setzte nach dem Abschneiden n_collision = 0 fest; der Mini-Lauf aus
    `verify/` hat seit der Drehung Kollisionssamples (siehe Gate-Einwände), also widersprach das Summary den Arrays.
    Der Test zählt die Status jetzt aus den Arrays; geprüft wird weiter Check (e).
- Danach `ruff` grün, web lint/typecheck/test grün (57 Tests).
- **Voller verify-Lauf: G1–G8 grün** (907 s gesamt, Bericht `runs/verify/report.json`):

| Gate | Ergebnis | Laufzeit | Kernzahlen |
|---|---|---|---|
| G1 | grün | 8,9 s | FK/IK gegen Pinocchio |
| G2 | grün | 43,5 s | 500 Posen gegen Coal |
| G3 | grün | 76,9 s, check 22,9 s | S1 machbar, d_min 10,83 mm, 90,5 % ok / 9,5 % warn, 0 coll/unreach, 40 718 Samples |
| G4 | grün | S2 330,5 s, check 57,6 s; S3 42,0 s, check 63,0 s | S2 172 Teile, alle machbar (168 Kopien), höchstes Modul 380 mm, d_min 10,83 mm; S3 nicht machbar, Prüfer bestätigt |
| G5 | grün | 36,5 s | fake_drcf S1 und S2, 0 Fehler |
| G6 | grün | 57,0 s | e2e 8 passed; Screenshots unter `web/e2e/screenshots/` aktualisiert |
| G7 | grün | — | S1 76,9 s (≤ 180), S2 330,5 s (≤ 1800) |
| G8 | grün | 168 s | ruff, pytest core (151,7 s), web lint/typecheck/test |

- Gegenüber 2a43c6b (falsche Ausrichtung) S1 36 → 77 s, S2 226 → 331 s (Lauf 16:21: 59 s / 260 s, Streuung der VMs):
  andere Platzierungen und volle H*-Bestätigung (`h_verify`). S1 weiter d_min 10,83 mm.

### 2026-10-19 17:35 Laufzeitmessung Giebelwand, Modulhöhe höchstens 1000 mm (Cloud, 4 vCPU)
- Szenario `/tmp/giebel_h1000.json`: Kopie von S2, nur Wand `1AQAupaRP1txwK1AGiN61V`, `module_height_max_mm` = 1000,
  `expect` = {}. Lauf `timeout 3600 … run-scenario … --out runs/local/giebel_h1000`, Start 14:33 UTC.
- **Ergebnis: Timeout nach 3600 s (Exit 124), kein Ergebnis**, 0 Teile, kein höchstes Modul. Der Lauf kam nicht über
  die H*-Suche der ersten Wand hinaus (`choose_grid` → `HStar._confirm`); es wurde noch kein Teil geplant.
- Wo die Zeit hängt (py-spy-Stichprobe alle 30 s, Stack des Hauptprozesses; Quader 600 × 200 × h, 3 Kandidaten):

| Zeit (UTC) | Schritt `_verified_ok` | Phase | Dauer | Ergebnis |
|---|---|---|---|---|
| 14:33–14:37 | h = 1000 | Double-Planung, Kandidat 1–3 | ~4 min | keiner machbar |
| 14:37–14:48 | h = 1000 | Nachplanung (`replan_at`), Kandidat 1–3 | ~11 min | nicht machbar |
| 14:48–14:49 | h = 550 | Double-Planung, Kandidat 1–2 | ~1,5 min | machbar (Kandidat 2) |
| 14:49–14:59 | h = 750 | Double-Planung, Kandidat 1–3 | ~10 min | keiner machbar |
| 14:59–15:33 | h = 750 | Nachplanung Kandidat 1 | > 33 min | beim Timeout offen |

- Befund: Die Bestätigung bisektiert 1000 → 550 → 750 → …; jeder Schritt über der Grenze kostet bis zu 3 Double-Planungen
  **plus** 3 Nachplanungen mit der echten Welt. Die Nachplanung ist der Engpass: bei h = 1000 scheitert sie früh
  (~3,5 min je Kandidat), bei h = 750 nahe an der Grenze plant sie tief und brauchte für einen einzigen Kandidaten
  über 33 min. Bis zur 50-mm-Genauigkeit folgen noch mindestens 2–3 weitere Schritte (650/700/800), danach erst die
  Zellplanung der Wand. Die Erwartung „Grenze bei ~800 mm“ ließ sich in 1 h nicht bestätigen; sicher ist nur
  550 machbar, 1000 nicht machbar, 750 offen.
- Nur gemessen, nichts getunt. Ansatzpunkte für später (Nutzerentscheidung): Nachplanung in der H*-Bestätigung
  weglassen oder auf einen Kandidaten begrenzen, Bisektion bei der Quader-Höhe aus dem Höhenexperiment (800 mm)
  beginnen, Zeitlimit je Bestätigungsschritt.

### 2026-10-19 18:40 Höhensuche statt Bisektion der vollen Planung (Nutzerentscheidung Tobias)
- **Anlass:** Mit `h_verify` lief die Giebelwand bei Grenze 1000 mm lokal 1 h 45 min und in der Cloud 1 h ohne
  Ergebnis (Eintrag 17:35). Jeder Bisektionsschritt plante von Schicht 1 neu, gescheiterte Schritte mit Nachplanung.
- **Prinzip (exakt bei fester Platzierung und gleicher Diskretisierung):** Ob Schicht k geht, hängt nur vom Druckstand
  darunter ab; ein niedrigerer Quader besteht aus den unteren Schichten des höheren. `planner.scan_height` plant den
  Quader b × T × H*_vor deshalb einmal von unten, prüft jeden Ring sofort mit der echten Welt
  (`PartPlanner(stop_at_bad=True)`, mit lokaler Ring-Nachbesserung) und stoppt an der ersten Schicht, die nicht geht
  (unerreichbar, d < d_hard, Zweigwechsel im Ring, unfreier Transfer). H* = Oberkante der Schicht darunter.
  Vollquader-Zellen bis H* bekommen den Plan als Ausschnitt (`truncate_plan`), wenn ihre Ringe exakt gleich sind;
  sonst normale Planung. Nicht global optimal: Der Planer entscheidet Schicht für Schicht, über 3 Platzierungen.
- **Tests:** `test_niedrigeres_prisma_ist_praefix_des_hoeheren` (Plan 30 mm = Ausschnitt des 60-mm-Plans, bitgleich),
  `test_hoehensuche_stoppt_an_der_ersten_schicht_die_nicht_geht`, `test_quaderzelle_bekommt_den_ausschnitt_der_hoehensuche`,
  `test_hstar_hoehensuche_bestaetigt_die_vorpruefung`. pytest core 169 grün (ohne Symlink-Test, Windows).
- **Giebelwand `1AQAupaRP1txwK1AGiN61V`, Windows seriell:**

| Grenze | vorher | jetzt | Ergebnis |
|---|---|---|---|
| 400 mm | 449 s | 194 s (Suche 57 s, schräge Oberreihe 116 s) | 30 Teile à 370 mm, alle machbar, d_min 10,83 mm |
| 1000 mm | > 1 h 45 min, abgebrochen | 801 s (Suche 568 s, schräge Oberreihe 212 s) | 12 Teile à 910 mm (oben 896), alle machbar, d_min 10,06 mm |

- H* ≥ 910 mm liegt über den erwarteten ~800 mm: Die Suche bessert jeden Ring gegen die echte Welt nach, was der reine
  Double-Plan nicht tut. Jeder Sample ist mit der echten Welt geprüft, Selbstprüfung grün; Orakel-Bestätigung im
  nächsten Cloud-verify.
- `DecomposeParams.h_verify` und `h_verify_step_mm` entfallen; `scenario_parts` übergibt die Höhensuche im Modus
  `collision_aware`.

### 2026-10-19 18:45 Druckeinstellungen nach Kategorien (Variante A, Entwurf freigegeben von Tobias)
- Branch `v2/params-akkordeon` von `origin/v2-nachtlauf` (b0fa62f), nur `web/` und dieser Eintrag. Nicht gemergt;
  der Merge folgt nach dem Nutzertest.
- **Panel „Druckeinstellungen“** wie bei Kunststoff-Slicern: Akkordeon mit acht Kategorien (Schicht & Strang, Module,
  Geschwindigkeit, Pumpe, Bewegung, Abstände, Bahnplanung, Steuerung & Export), alle zugeklappt mit Kurzfassung
  („10 mm · 30 mm · 2 Schalen“, „100 · 250 mm/s“, „DRL v2“). Modus „Grundlegend | Alle“: 9 von 21 Parametern
  grundlegend. Suche über Label und Gruppentitel (ohne Groß-/Kleinschreibung und Umlaute, jedes Wort muss passen)
  ignoriert den Modus und klappt Gruppen mit Treffern auf. Hinweis „12 weitere Parameter unter „Alle““ mit Badge der
  versteckten Änderungen; ein Klick schaltet auf „Alle“ und klappt deren Gruppen auf. „Ergibt bis zu ⌊H/h⌋ Schichten
  je Modul.“ Keine Profil-Auswahl.
- Geändert = Primärfarbe (Punkt, fettes Label, Rand und Tönung des Felds, Badge „N geändert“ je Gruppe und im Kopf),
  das Gelb entfällt. Annahme = gelbes „A“ (gefüllt, `autoContrast`) mit Tooltip und zugänglichem Text, bei `t_tot_s`
  „Annahme, vorläufig“. Reset-Knopf je Zeile nur bei Änderung, Platz reserviert. Icons als Inline-SVG
  (`ParamIcons.tsx`), Tabler ist keine Abhängigkeit.
- Logik als reine Funktionen in `web/src/state/params.ts` (`PARAMS`, `PARAM_GROUPS`, `visibleParams`, `groupViews`,
  `hiddenInfo`, `groupSummary`, `secondaryLine`, `layersPerModule`); `tcp_name` und `dialect` sind Text- bzw.
  Auswahlparameter im selben Modell. Schlüssel und Defaults unverändert.
- **Kopplung an den Kern:** `core/tests/test_api.py::test_web_default_params_accepted` liest `params.ts` mit Regex
  (Schlüssel und Default im selben Objektliteral, Zahl der Schlüssel-Literale = Zahl der Zahlenparameter,
  `tcp_name`/`dialect` als eigene Zeile). Deshalb stehen die Text- und Auswahlparameter nach Feldnamen und die
  Defaults in `STRING_DEFAULTS`; ein Vitest prüft dieselben Ausdrücke, damit eine Web-Änderung den Kerntest nicht
  still bricht.
- „Zerlegen & prüfen“ samt Grund sitzt `sticky` am unteren Rand der Seitenleiste (Hintergrund `--mantine-color-body`).
  Geprüft bei 1280 × 800 und 1024 × 800 (Seitenleiste 440/340 px), hell und dunkel: Knopf im Bild, kein
  horizontaler Überlauf. Unter `lg` sind Feld 100 px und Labels 12 px breit bzw. groß, sonst brachen Labels mitten im
  Wort. Hinweis im Export auf „Druckeinstellungen → Steuerung & Export“ angepasst.
- e2e `shell.spec.ts`: `params-toggle` entfällt; der Test klappt Pumpe und Geschwindigkeit auf und erwartet
  „vorläufig“ am Kennzeichen von `t_tot_s`. Neue Test-IDs: `param-group-<id>`, `param-mode`, `param-search`,
  `param-hidden-note`.
- Checks lokal (Windows 11, Node 24): web lint, typecheck und test grün (79 Tests, davon 22 neu in `params.test.ts`
  und `ParamsPanel.test.tsx`). e2e **8 passed** (29,8 s) gegen lokal erzeugte Läufe `runs/verify/S1` (2 min) und
  `runs/verify/S3` (57 s), Playwright-Chromium dafür nachinstalliert. `pytest core/tests/test_api.py -k
  web_default_params` grün. Screenshots `2-zerlegen.png` und `g6-2-zerlegen.png` zeigen das neue Panel.
- Cloud-Prüfung nach Merge von v2-nachtlauf (Merge f591f9f, PROGRESS-Konflikt: beide Einträge in zeitlicher Reihenfolge, sonst konfliktfrei): web lint, typecheck grün, vitest 79 passed; ruff grün; pytest core -n 2 216 passed, 2 skipped; `verify.py --fast` G1, G2, G3, G5, G8 grün (`--fast` lässt G6 aus, weil G6 `slow` ist); e2e separat gegen S1 (verify.py) und S3 (`run-scenario`, check_run bestanden): 9 passed, davon neu `params.spec.ts` (kein Überlauf bei 1280 × 800, Knopf sticky, hell und dunkel). G4 und G7 nicht geprüft.
