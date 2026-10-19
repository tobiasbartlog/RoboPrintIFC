# SPEC — RoboPrintIFC v2

Stand 2026-10-18 · gilt für den Nachtlauf auf Branch `v2-nachtlauf`.
Diese Datei ist ab Ende P0 gesperrt. Einwände gehören nach `PROGRESS.md` → „Gate-Einwände“.

## 1 Ziel und Umfang

**Ziel:** Eine Wand aus einem IFC-Modell wird in Module zerlegt. **Jedes Modul ist am
Doosantisch mit dem Doosan M1013 und dem Werkzeug `30gut` kollisionsfrei und vollständig
erreichbar druckbar**, inklusive aller Travel-Bewegungen. Für jedes Modul entsteht ein DRL-Programm,
das der Fake-Controller akzeptiert und das genau die geprüfte Bewegung fährt. Ein Viewer
führt durch den Ablauf und zeigt Bewegung und Kollisionsbefund synchron.

**Heute im Umfang**
- Zerlegungsart **Modul**: Der Roboter steht fest am Doosantisch, jedes Modul steht aufrecht in
  Einbaulage auf der Arbeitsfläche und wird einzeln gedruckt.
- Planares Slicing mit Schalen, ohne Infill. Konstanter Pumpenwert je Programm.
- DRL in zwei Dialekten: `v2` (Default, kompatibel zu Controller-Firmware 2.x) und `v3`
  (Firmware ≥ 3.2, für das geplante Update).

**Nicht im Umfang** (die Architektur verbaut nichts davon)
- Zerlegungsart Abschnitt (in situ). Sie folgt als nächster Schritt.
- Porositätsfeld und Gradienten, Infill, Fügegeometrie, KUKA/KRL, Mehrroboter, nichtplanares Slicing.

## 2 Konventionen

**Einheiten:** Länge in mm, Winkel in rad, Zeit in s, Spannung in V. Grad gibt es nur in
DRL-Text und in UI-Anzeigen.

**Gelenke:** `q` ist immer in Doosan-Steuerungskonvention. Sie ist identisch mit der
Nullstellung der URDF in `third_party/doosan_m1013/urdf/m1013.white.urdf`.
- Achsgrenzen in dieser Konvention: J3 ±160°, alle anderen ±360°. Quelle ist `robots/doosan_m1013.json`
  (`joint_limits_rad`).
- Geschwindigkeitsgrenzen 120/120/180/225/225/225 °/s.
- Die Home-Pose (0, 0, 90, 0, 90, 0)° muss gültig sein.

**Orientierung:** Quaternion (w, x, y, z). Rotationsmatrizen wirken auf Spaltenvektoren.
`T_AB` ist die Pose von Frame B in Frame A, also `p_A = T_AB · p_B`.

**Frames**
| Frame | Bedeutung | Quelle |
|---|---|---|
| W | Workstation-Welt: Koordinaten von `workstations/doosantisch.stl`, Boden bei z = 0 | Mesh |
| B | Roboterbasis, `T_WB` | `robot_base_frame` der Workstation |
| S | Arbeitsfläche, `T_WS` | `work_surface_frame` der Workstation (Tischoberkante) |
| F | Flansch, `T_BF = FK(q)` | URDF, Glied `link_6` |
| T | TCP, `T_FT` | `tools/30gut.json` → `tcp_frame` |
| L | Wand: Ursprung an der min-Ecke der Wand, X entlang der Wandachse, Z oben, Y = Z × X; die Wand belegt x ∈ [0, Länge], y ∈ [0, Dicke], z ∈ [0, Höhe] | IFC |
| P | Teil (Modul): Ursprung in der Mitte der Bodenfläche der Teil-Bounding-Box, Achsen parallel zu L | Zerlegung |

**Platzierung** eines Moduls ist `T_SP`: Verschiebung (x, y, 0) plus Gierwinkel θ um Z_S.
Das Modul steht auf der Arbeitsfläche, z = 0 in S. Für die Montage wird `T_LP` mitgeführt.

**Düse:** Die Düsenachse ist +Z_T. Beim Druck zeigt sie senkrecht nach unten (−Z_W).
- **Gierwinkel ψ:** Drehung um die Düsenachse. Sie ist frei, weil die Düse als
  rotationssymmetrisch angenommen wird.
- **Kippung τ:** Abweichung der Düsenachse von der Senkrechten. Default τ_max = 0°.

**Status je Sample**, wobei d der kleinste vorzeichenbehaftete Abstand aller geprüften Paare ist:
- `collision`: d < 0
- `warn`: 0 ≤ d < d_target
- `ok`: d ≥ d_target
- `unreachable`: Für die Sollpose existiert keine gültige Gelenklösung. Das Sample bekommt
  kein d, und weder Arm noch Pose werden „eingefroren“ weitergeprüft.

*Nachtrag 19.10.2026 (Nutzerentscheidung 19.10.2026):* Das Paar `base_link` ↔ `link_2` liegt
konstruktiv konstant bei ≈ 33 mm < d_target. Der Status richtet sich deshalb nach
d_status = Minimum über alle geprüften Paare außer (`base_link`, `link_2`); ist der Abstand dieses
Paars < d_hard, geht er doch in d_status ein. Das Paar zählt also weiter für `collision` (d < 0) und
für d_hard, aber nicht für die d_target-Schwelle. In den Regeln oben steht d für d_status. Weitere
Paare kommen nur nach Freigabe durch den Nutzer hinzu.

**IK-Zweig:** drei Bits (Schulter, Ellbogen, Handgelenk), Index 0–7. Die Zuordnung definiert
`roboprint.robot` und dokumentiert sie im Docstring. Gleiche Bits müssen dieselbe Bedeutung
haben wie `sol` im Doosan-`ikin` (docs/doosan-drl.md).

## 3 Glossar

| Begriff | Bedeutung | Code |
|---|---|---|
| Wand | eine IfcWall mit Geometrie (Mesh in L), Öffnungen und Dicke | `Wall` |
| Eignung | Ist die Wand überhaupt druckbar? Heute: Dicke ≥ 2 · Strangbreite | `eligibility` |
| Modul / Teil | ein Stück der Wand, das einzeln gedruckt wird | `Part` |
| Platzierung | `T_SP` eines Moduls auf der Arbeitsfläche | `Placement` |
| Druckbahn | geschlossener Ring einer Schale in einer Schicht, mit Pumpe an gedruckt | `PrintRing` |
| Travel | Bewegung mit Pumpe aus: Abheben, Transfer, Absenken | `Travel` |
| Druckstand | bereits gedrucktes Material als Hindernis, wächst schichtweise | `PrintedVolume` |
| Freizone | Düsenspitze im Radius r_free um den TCP. Sie wird nicht gegen den Druckstand geprüft | `nozzle_tip` |
| Armstellung | IK-Zweig 0–7 | `branch` |
| Ladder-Graph | je Wegpunkt alle zulässigen Gelenklösungen als Knoten, Kanten zwischen Nachbarn | `planner` |

## 4 Architektur

`core/src/roboprint/` ist das Python-Paket (Python ≥ 3.12). Jedes Modul ist tief und hat eine
schmale Schnittstelle. Die Abhängigkeiten zeigen nur nach unten.

| Modul | Verantwortung | Kern-Schnittstelle |
|---|---|---|
| `contracts` | Pydantic-Modelle aller Artefakte (§6), JSON-Schema-Export | `Summary`, `PartArtifact`, `Toolpath`, `Trajectory`, `Scene` |
| `assets` | Roboter (URDF), Werkzeug, Workstation und Prozessparameter laden | `load_robot()`, `load_tool()`, `load_workstation()` |
| `frames` | alle Frame-Übergänge aus §2, sonst nirgends | `wall_frame_from_ifc()`, `T_WP(placement)` |
| `robot` | FK aus der URDF-Kette, analytische IK (OPW, portiert und auf Doosan-Konvention umgestellt), alle 8 Zweige, Grenzen | `fk(q) -> T_BF`, `ik(T_BF) -> list[(branch, q)]` |
| `ifc` | IFC → `Wall` in L (m → mm, global → lokal), Öffnungen | `read_walls(path) -> list[Wall]` |
| `geometry` | Booleans und Schnitte (manifold3d / trimesh) | `cut_box(mesh, box)` |
| `slicer` | Schichten, Schalenringe, Ringstart, An- und Abfahrt | `slice_part(part, params) -> Toolpath` |
| `collision` | Kollisionswelt: Glieder, Werkzeugkörper, Düsenspitze, Boden, Tisch, Druckstand, Selbstkollision; Abstand je Pose | `World.distance(q, layer) -> Contact` |
| `planner` | Ladder-Graph über (Zweig × ψ × τ) je Wegpunkt, Travel-Planung, dichte Gelenktrajektorie | `plan_part(...) -> PlannedPart` |
| `decompose` | Eignung, Modulraster, Platzierungssuche, Planer im Loop | `decompose_wall(...) -> list[Part]` |
| `timing` | Zeitparametrierung unter Gelenk- und Bahngrenzen | `time_parametrize(...)` |
| `drl` | Emitter für die Dialekte v2/v3 | `emit(planned_part, dialect) -> str` |
| `pipeline` | Szenario ausführen, Laufordner schreiben, Fortschritt melden | `run_scenario(path, out)` |
| `api` | FastAPI: Projekte, Jobs mit Fortschritt und Abbruch, Artefakte ausliefern | §8 |
| `cli` | `roboprint run-scenario`, `roboprint serve`, `roboprint export-contracts` | §7 |

**Backend-Naht:** Der Planer rechnet Abstände über ein Protokoll `CollisionBackend`. Default ist
python-fcl auf VHACD-Zerlegungen. Tesseract darf als zweites Backend daneben, wenn der Spike
in P1 überzeugt (§5.2).

## 5 Algorithmen

### 5.1 Kollisionswelt (`collision`)

**Geometrie**
- Glieder: Kollisionsmeshes der URDF (`third_party/doosan_m1013/meshes/m1013_collision`) als
  VHACD-Konvexzerlegung, formtreu ±6 mm. Sie werden einmal erzeugt und mit einem Hash der
  Quellmeshes gespeichert.
- Werkzeug: `tools/30gut.stl` über `mesh_transform` am Flansch, ebenfalls per VHACD (keine
  einzelne konvexe Hülle). Die Düsenspitze ist der Teil des Werkzeugmeshes innerhalb der Kugel
  mit Radius r_free um den TCP; der Rest heißt Werkzeugkörper.
- Boden: Halbraum z ≤ 0 in W, immer aktiv.
- Tisch: `workstations/doosantisch.stl`, immer aktiv.
- Druckstand bei Schicht k: Teil-Solid ∩ {z_P ≤ k · h}, also alle fertigen Schichten. Die
  aktuelle Schicht ist kein Hindernis. Bei Travel nach Schicht k zählt Schicht k als fertig.

**Geprüfte Paare** (genau diese, auch das Orakel prüft genau diese)
| Paar | Ausnahme |
|---|---|
| jedes Glied `base_link`…`link_6` und Werkzeugkörper ↔ Boden | `base_link` und `link_1` gegen den Boden entfallen |
| jedes Glied und Werkzeugkörper ↔ Tisch | `base_link` und `link_1` gegen den Tisch entfallen |
| jedes Glied und Werkzeugkörper ↔ Druckstand | — |
| Düsenspitze ↔ Boden, Tisch | Düsenspitze ↔ Druckstand entfällt (Freizone) |
| Glied i ↔ Glied j für j ≥ i + 2 | — |
| Werkzeugkörper ↔ `base_link`…`link_4` | — |

**Ausgabe je Pose:** d_min, das Paar mit d_min (Glied- und Hindernisname) und die beiden
Zeugenpunkte in W.

*Nachtrag 19.10.2026 (Nutzerentscheidung 19.10.2026):* Für den Status zählt d_status nach §2
(`base_link` ↔ `link_2` nur, wenn < d_hard). Die Paarliste oben bleibt unverändert; G2 vergleicht
weiter die Abstände über alle Paare.

### 5.2 Planer (`planner`)

1. **Wegpunkte.** Jeder Druckring wird alle Δs = 20 mm neu abgetastet; Ecken bleiben erhalten.
2. **Knoten je Wegpunkt.** Für ψ ∈ {0°, 15°, …, 345°} und τ ∈ {0°} (bei τ_max > 0: τ ∈ {0, τ_max/2, τ_max}
   × 8 Azimute) wird die Sollpose `T_WT` gebildet und die IK über alle Zweige gelöst. Ein Knoten ist
   ein Tupel (Zweig, q, ψ, τ). Er bleibt nur, wenn er die Grenzen einhält und d ≥ d_hard gegen
   die Welt der Schicht des Wegpunkts gilt.
3. **Kanten.** Kanten gibt es zwischen aufeinanderfolgenden Wegpunkten desselben Rings, nur bei
   gleichem Zweig und max|Δq| ≤ Δq_max.
   Kosten: gewichtete Gelenkdistanz + λ_d · max(0, d_target − d)/d_target + λ_ψ · |Δψ|.
4. **Suche.** Dynamische Programmierung (Viterbi) je Ring. Zwischen Ringen und Schichten
   verbindet die Travel-Planung (5.3). Die Zweigwahl für das ganze Teil wird bevorzugt
   beibehalten, das ist eine weiche Strafe.
5. **Verdichtung.** Die gewählte Folge wird so interpoliert, wie die Steuerung fährt:
   - Druck und An-/Abfahrt als `movel`, kartesisch linear mit Orientierungs-Slerp. Die IK läuft
     entlang der Bahn, jeweils der Lösung des Vorgängers am nächsten und im selben Zweig.
   - Transfers als `movej`, gelenklinear.
   - Abtastung, bis zwischen zwei Samples der TCP ≤ 5 mm wandert und max|Δq| ≤ 0,005 rad bleibt.
     Jedes Sample wird geprüft und bekommt einen Status.
6. **Ergebnis:** `machbar`, wenn kein Sample `collision` oder `unreachable` hat, überall d ≥ d_hard
   gilt und kein Zweigwechsel innerhalb eines Rings vorkommt. Sonst `nicht machbar` mit Ursache:
   erstes kritisches Sample, Glied, Hindernis.

Ein **Tesseract-Spike** in P1 (Timebox 60 min) prüft, ob Descartes mit `sampleToolAxis` dieselbe
Aufgabe für S1 schneller oder besser löst. Das Ergebnis kommt nach PROGRESS.md. Übernommen
wird es nur hinter der Backend-Naht und nur, wenn G3 dadurch nicht schlechter wird.

### 5.3 Travel

Die Folge von Ringende zu Ringstart besteht aus drei Stücken:
1. Abheben senkrecht um z_lift über die Oberkante des aktuellen Druckstands, als `movel`.
2. Transfer als `movej` zwischen den Gelenklösungen über Endpunkt und Startpunkt.
3. Absenken senkrecht auf den Ringstart, als `movel`.

Ist der Transfer nicht frei, wird ein Zwischenpunkt höher und mittig darüber eingefügt.
Bleibt er unfrei, wird die Zweigwahl gewechselt, und zwar nur hier. Jeder Travel wird wie Druck
dicht geprüft.

### 5.4 Zerlegung (`decompose`, Modus Modul)

1. **Eignung.** Dicke T ≥ 2 · w, sonst `eligible = false` mit Begründung.
2. **Überhang-Regel.** Jede Oberkante einer Öffnung (Sturzlinie) muss auf einer horizontalen
   Schnittebene liegen. So entsteht in keinem Modul ein Überhang über Luft.
3. **Machbarkeitsfunktion.** H*(Breite) ist die größte Modulhöhe, die der Planer für einen
   Vollquader Breite × T × H bei bester Platzierung als machbar einstuft. Gesucht wird per
   Bisektion auf 10 mm genau, mit Cache über (Breite, T, Höhe). Platzierungssuche: θ ∈ {0°, 90°, 180°, 270°},
   (x, y) auf einem 25-mm-Raster innerhalb der Arbeitsfläche, ohne Überschneidung mit der
   Roboterbasis; Ziel ist das maximale d_min.
4. **Raster.**
   - Spalten gleicher Breite b ≤ b_max, gewählt aus {300, 400, …, 1200} mm.
   - Reihen von unten nach oben mit Höhe ≤ H*(b); Pflicht-Schnitte aus Regel 2 gehen vor.
   - Ziel lexikographisch: (1) Anzahl Module minimal, (2) kleinster d_min aller Module maximal.
5. **Jedes Teil wird einzeln geplant**, auch Teile mit Öffnungen. Der Cache greift nur bei
   gleicher Geometrie. Danach wird jedes Teil dicht simuliert und geprüft (5.2, Schritt 5).

### 5.5 Zeitparametrierung (`timing`)

- Druck: konstante Bahngeschwindigkeit v_print.
- Travel: v_travel kartesisch bzw. Gelenkgeschwindigkeit innerhalb der Grenzen.
- Trapezprofile.

Die Zeiten dienen der Wiedergabe und der Druckzeitschätzung. Geprüft wird geometrisch.

### 5.6 DRL (`drl`)

Jedes Detail mit Beleg steht in `docs/doosan-drl.md`. Für den Emitter verbindlich:
- **Prolog:** `set_velx`/`set_accx`/`set_velj`/`set_accj` mit Werten aus §10; `set_tcp(<tcp_name>)`;
  `set_singularity_handling(DR_VAR_VEL)`; `set_mode_analog_output(ch=1, mod=DR_ANALOG_VOLTAGE)`;
  danach `movej(posj(home))`.
- **Je Ring:**
  1. `movej(posj(q_über_start))` als Transfer
  2. `movel` absenken
  3. `set_analog_output(ch=1, val=V_pump)` und `wait(t_tot)`
  4. Druck-`movel` je Wegpunkt mit `radius = r_blend` und `ra = DR_MV_RA_DUPLICATE`. Im Dialekt v3
     sind statt der Einzelbefehle `movesx`-Blöcke mit ≤ 100 Punkten und `vel_opt = DR_MVS_VEL_CONST` erlaubt.
  5. `set_analog_output(ch=1, val=0)`
  6. `movel` abheben
- **Posen:** `posx` kartesisch in mm und Grad, Euler ZYZ (A, B, C) mit R = Rz(A)·Ry(B)·Rz(C),
  `ref = DR_BASE`. Gelenkziele `posj` in Grad, Doosan-Konvention.
- **Bezug:** Bewegungsziele kommen ausschließlich aus der geplanten Trajektorie, also aus genau dem
  Zweig, der geprüft wurde.
- **Kopfkommentar:** Provenienz, Dialekt, Szenario, Teil, alle provisorischen Werte sowie der
  Hinweis „Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck“.
- **Fehlerfall:** Analogausgang auf 0 setzen, über eine Abschlusssequenz am Programmende und
  über Exception-Handling, soweit der Dialekt es erlaubt.

## 6 Artefakte (Laufordner)

`roboprint run-scenario <szenario.json> --out <dir>` schreibt:

```
<dir>/
  summary.json            Szenario-ID, Parameter, Wände (Eignung + Grund), Teile mit Status,
                          Laufzeiten je Stufe, Provenienz (git commit, Zeit, Kommandozeile)
  scene.json              Workstation (Pfad Mesh, T_WB, T_WS), Werkzeug (Pfad Mesh, T_FT,
                          mesh_transform), Roboter (URDF-Pfad), Parameter d_hard, d_target, r_free
  parts/<part_id>/
    part.json             part_id, wall_id, T_LP, T_SP, T_WP, Bounding-Box in P,
                          Volumen, Status machbar/nicht machbar + Ursache
    part.stl              Teil-Solid in Frame P, mm
    toolpath.json         Schichthöhe h, Ringe: layer, shell, kind, Wegpunkte als TCP-Posen in W
                          [x, y, z, qw, qx, qy, qz]
    trajectory.json       Arrays gleicher Länge N:
                            t_s[N], q[N][6] (rad, Doosan), tcp[N][7] (W), layer[N], ring[N],
                            kind[N] ∈ {print, approach, retract, lift, transfer, lower},
                            branch[N], status[N], d_mm[N] (null bei unreachable),
                            pair[N] = [glied, hindernis] | null, witness[N] = [[x,y,z],[x,y,z]] | null
                          sowie summary: n, n_ok, n_warn, n_collision, n_unreachable, d_min_mm,
                          dauer_s, zweig_wechsel_in_ringen
    program.v2.drl
    program.v3.drl
```

- Alle JSON-Dateien tragen `schema_version` und validieren gegen die exportierten Schemas.
- `t_s` steigt strikt monoton. Der Viewer leitet alles aus `t_s` ab, es gibt nur diese eine Uhr.

## 7 CLI

- `roboprint run-scenario <json> --out <dir> [--jobs N]`: führt ein Szenario aus `spec/scenarios/`
  aus. Exit-Code 0 auch bei unmachbaren Teilen, das Ergebnis steht in `summary.json`.
  Exit-Code ≠ 0 nur bei Programmfehlern.
- `roboprint serve [--port 8765] [--runs runs/]`: startet die API.
- `roboprint export-contracts <dir>`: schreibt die JSON-Schemas. Der Web-Build erzeugt daraus
  TS-Typen; ein Test prüft, dass sie aktuell sind.

**Szenario-Format** (`spec/scenarios/*.json`):
- `source.kind`: `box` (Vollquader `size_mm` = [Länge, Dicke, Höhe]) oder `ifc` (`path`, `walls`).
- `decompose`: Bei `false` ist die Quelle genau ein Teil.
- `params`: Overrides für §10, leer heißt Defaults.
- `planner_mode`:
  - `collision_aware`: Normalfall.
  - `ignore_collision`: IK nur nach Grenzen und Gelenknähe. Die Prüfung und Statusvergabe
    danach läuft trotzdem vollständig.
- `placement_override`: feste Platzierung (x, y in S, yaw), keine Suche.
- `expect`: Erwartung für G3/G4.

## 8 API (FastAPI, für `web/`)

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/health` | Lebenszeichen und Versionen |
| GET | `/api/examples` | mitgelieferte IFC-Modelle und Szenarien |
| POST | `/api/projects` | Projekt aus Beispiel-Pfad oder Upload anlegen → `{project_id}` |
| GET | `/api/projects/{id}` | Wände mit Maßen, Eignung und Grund |
| POST | `/api/projects/{id}/jobs` | Job `decompose_and_plan` für eine Wand mit Parametern → `{job_id}` |
| GET | `/api/jobs/{job_id}` | `{state, progress 0..1, stage, message, run_id}` |
| DELETE | `/api/jobs/{job_id}` | Job abbrechen |
| GET | `/api/runs/{run_id}/{pfad}` | Artefakte aus §6 (JSON, STL, DRL) |
| GET | `/api/assets/{pfad}` | URDF, Robotermeshes, Werkzeug- und Tisch-STL |

Jobs laufen in einem Hintergrundprozess und lassen sich abbrechen. Fortschritt gibt es je Stufe
und je Teil.

## 9 Viewer (`web/`)

- Stack: Vite, React, TypeScript strict, react-three-fiber und drei, Mantine, Zustand, Vitest,
  Playwright, ESLint. Den Roboter rendert `urdf-loader` aus derselben URDF.
- Vier Schritte: **Modell → Zerlegen & prüfen → Simulation → Export.** Details und Gestaltung
  siehe `docs/ux-leitbild.md`.
- **Eine Uhr:** Der Store hält `t` in Sekunden. Armpose, TCP, Druckstand (Schnittebene am Teilmesh
  auf Höhe der Schicht zu `t`), Strangfortschritt, Status und Abstand werden per binärer Suche in
  `t_s` bestimmt. Es gibt keine zweite Zeitabbildung.
- Der Viewer rechnet keine Fachlogik. Er spielt Artefakte ab.
- **Debug-Schnittstelle für Tests:** `window.__roboprint.debug()` liefert
  `{t, sampleIndex, tcpRendered[3], tcpArtifact[3], status, highlightedLinks[], obstacleVisible}`.

## 10 Parameter und Annahmen

Werte mit **A** sind Annahmen, die der Nutzer bestätigen muss. Sie stehen im Kopf jedes
DRL-Programms und in `summary.json`.

| Parameter | Wert | |
|---|---|---|
| Schichthöhe h | 10 mm | A |
| Strangbreite w | 30 mm | A (Düse `30gut`) |
| Schalen | 2 | aus Prozesskarte |
| v_print | 100 mm/s | A |
| v_travel | 250 mm/s; Gelenke ≤ 30 % der Grenzen | A |
| z_lift | 30 mm über Druckstand-Oberkante | A |
| An- und Abfahrt | senkrecht 20 mm | A |
| V_pump | 5,0 V konstant auf AO 1 (`pump_a`) | A |
| t_tot | 3,0 s Verweilzeit am Ringstart | A, provisorisch |
| r_blend | min(2 mm, ½ Segmentlänge) | A |
| d_hard | 10 mm, hartes Abnahmekriterium | A |
| d_target | 50 mm (`safety_min_distance_mm` der Workstation) | |
| r_free | 40 mm | aus v1 |
| τ_max | 0° | A |
| Δψ-Raster | 15° | |
| Δs | 20 mm | |
| Δq_max | 0,3 rad je Wegpunktkante | |
| tcp_name | `FGC_30GUT`, muss am Teach Pendant angelegt sein | A |
| Dialekt | `v2` | Nutzer: Firmware vermutlich 2.x, Update geplant |

## 11 Abnahme-Gates

`python scripts/verify.py` führt G1–G8 aus. Jedes Gate ist binär. Die Orakel liegen in `verify/`
und importieren `roboprint` nicht.

| Gate | Prüft | Kriterium |
|---|---|---|
| **G1 Kinematik** | `roboprint.robot` gegen Pinocchio auf der URDF | 2000 Zufalls-q in den Grenzen: Positionsfehler < 0,01 mm, Rotationsfehler < 1e-6 rad. 2000 Zufallsposen: Jede IK-Lösung erfüllt die FK auf 0,01 mm, und die erzeugende Lösung ist in der Menge enthalten (modulo 2π). Home-Pose gültig. |
| **G2 Kollision** | `roboprint.collision` gegen Coal auf Roh-Meshes (URDF-Kollisionsmeshes, Werkzeug-STL, Tisch-STL, Teil-STL) | 500 Zufallsposen in der Szene S1 mit halb gedrucktem Teil: roboprint ist konservativ, d_rp ≤ d_coal + 1 mm auf jeder Pose. Wo \|d_coal\| > 12 mm, stimmt das Vorzeichen überein. Wo beide ≥ 0, gilt \|d_rp − d_coal\| ≤ 12 mm. Konservativ werden darf über Aufblasen der Näherungsgeometrie. |
| **G3 Referenzmodul** | Lauf S1 vom unabhängigen Prüfer `verify/check_run.py` dicht nachgerechnet | 0 `collision`, 0 `unreachable`, d_min ≥ d_hard auf **jedem** Sample, auch Travel. Abtastdichte nach 5.2/5. TCP folgt dem Toolpath: Position ≤ 0,5 mm, Düsenachse ≤ τ_max + 0,1°. Kein Zweigwechsel in Ringen. Abdeckung je Schicht ≥ 95 % des Schalenbereichs (aus `part.stl` unabhängig geschnitten). Eigener Status = Prüferstatus. |
| **G4 Beispiel-IFC** | Lauf S2 (alle Wände) und S3 (Negativfall) | S2: Jede geeignete Wand ist vollständig zerlegt (Volumen der Teile = Wandvolumen ± 0,5 %, Überlappung ≤ 0,1 %), jedes Teil besteht alle G3-Kriterien, liegt auf der Arbeitsfläche und schneidet die Roboterbasis nicht. Jede ungeeignete Wand hat einen Grund, der die Regel aus 5.4/1 tatsächlich erfüllt. Überhang-Regel eingehalten. S3: Der eigene Status meldet `collision`, und der Prüfer bestätigt ≥ 1 Kollisionssample. |
| **G5 DRL** | `verify/fake_drcf` führt jedes `program.v2.drl` und `program.v3.drl` aus S1 und S2 aus | Läuft ohne Fehler. Nur Befehle und Signaturen, die laut `docs/doosan-drl.md` im Dialekt existieren. AO-Kanal ∈ {1, 2}, 0–10 V. vel/acc in den Grenzen. `movesx` ≤ 100 Punkte, `r_blend` ≤ ½ Segment. Jedes `posj` ist das geplante q (≤ 0,001°). Jedes `posx` entspricht der FK des geplanten q (≤ 0,1 mm, ≤ 0,05°) bei unabhängiger ZYZ-Umrechnung. Pumpe ist nur in Druckringen an. |
| **G6 Viewer** | `npm --prefix web run e2e` (Playwright, startet API und Web mit den Läufen S1 und S3) | Glückspfad: Projekt → Wand → „Zerlegen & prüfen“ → alle Teile grün → Wiedergabe → Export. Kollisionspfad S3: Liste „Kollisionen (n > 0)“; Klick pausiert bei t, das betroffene Glied ist hervorgehoben, das Hindernis sichtbar. Uhr-Invariante an 50 Zufalls-t: \|tcpRendered − tcpArtifact\| ≤ 1 mm, Status passt zum Sample. Screenshots unter `web/e2e/screenshots/`. |
| **G7 Laufzeit** | gemessen durch `verify` auf der Cloud-VM (4 vCPU) | S1 ≤ 180 s, S2 ≤ 1800 s |
| **G8 Qualität** | Lint, Typen, Unit-Tests | `ruff check core verify`, `pytest core`, `npm --prefix web run lint`, `run typecheck`, `run test`: alle grün |

## 12 Portierung aus `legacy/`

| Quelle | Ziel | Was zu ändern ist |
|---|---|---|
| `legacy/core/src/fgc/ifc_io/*` | `ifc` | L-Frame nach §2 (rechtshändig prüfen), global → lokal, m → mm |
| `legacy/core/src/fgc/slicer/*` | `slicer` | Ringstart, An- und Abfahrt, mehrere Konturen und Löcher je Schicht |
| `legacy/core/src/fgc/kinematics/opw.py` | `robot` | Parametrierung auf q = q_doosan umstellen, Grenzen in dieser Konvention, Zweig-Bits wie `ikin` |
| `legacy/core/src/fgc/simulation/motion.py`, `timeparam.py` | `planner` (Verdichtung), `timing` | `movel` kartesisch, `movej` gelenklinear. Unerreichbar wird ein eigener Status, kein Einfrieren |
| `legacy/core/src/fgc/collision/check.py` | `collision` | Boden immer, Tisch, Selbstkollision, Werkzeug-VHACD, Freizone nur für die Düsenspitze |
| `legacy/core/scripts/convert_robot_collision.py` | `assets` | VHACD aus den URDF-Meshes, im Frame der URDF-Glieder |
| `legacy/core/src/fgc/domain/{tool,workstation}.py` | `assets` | als Pydantic-Modelle |
| `legacy/core/src/fgc/postproc/emitter.py` | nur Referenz | Neuschreiben: ZYZ-Fehler bei B ≈ 180°, AO-Kanäle, `movej(posx)` ohne `sol`, `radius = 0` |
| `legacy/viewer/src/ui/*-state.ts` | nur Referenz | Ideen für Stepper und Veraltet-Logik |

Nicht portiert werden Beam-Suche, Surrogat, Kampagne, Benchmark, Prior, Reichweitenkarte, Glied-SDF
und `pipeline/actions.py`.

## 13 Offene Punkte für den Nutzer

1. Die Annahmen in §10 bestätigen, vor allem h, w, v_print, V_pump, t_tot, d_hard und τ_max.
2. Die Firmware-Version am Teach Pendant ablesen, um den Dialekt festzulegen.
3. Klären, ob die Düse rotationssymmetrisch ist. Davon hängt die freie Wahl von ψ ab.
4. Den TCP `FGC_30GUT` am Teach Pendant mit den Werten aus `tools/30gut.json` anlegen.
