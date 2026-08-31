# DRL-Nutzungsplan — Was DRL kann, was wir nutzen, wo es hingehört

Stand: 2026-07-09 · Analyse-Session (nur lesend, keine Code-Änderungen).
Quelle: Doosan DRL Programming Manual V2.10.1 (nicht mitgeliefert — urheberrechtlich geschützt; Zeilenangaben
unten = Zeilen in dieser Datei) + Codebestand `core/src/fgc/`.

Zweck: Landkarte „DRL-Fähigkeit → Nutzen für den Lehm-Druck → Implementierungsort
im FGC-Planner", plus Befunde am heutigen Emitter. Kein PRD — Grundlage für
spätere Issues/Grilling.

---

## 1. Ist-Zustand: Was unser Tool heute mit DRL macht

**Datenfluss:** IFC → druckbare Wände → Slicen → **Toolpath** (roboterunabhängige
Targets: Pose im Wand-Frame, `v_mm_s`, logische IO-Werte, `kind` print/travel)
→ + **Setup** (`wall_to_base` aus 3-Punkt-Antastung, TCP, `io_channels`-Mapping,
Totzeit) → + **MotionParams** (`process_params.motion`) → `emit_drl` → DRL-Text.

**Implementierungsorte (heute):**

| Baustein | Ort |
|---|---|
| DRL-Emitter (einzige Stelle, die DRL-Text erzeugt) | `core/src/fgc/postproc/emitter.py` |
| Bewegungsparameter `MotionParams` + erlaubte Job-Keys `MOTION_PARAM_KEYS` | `core/src/fgc/simulation/motion.py:66` / `:109` |
| Job-Anbindung `motion_from_job` (`process_params.motion`) | `core/src/fgc/simulation/motion.py:654` |
| Emit-Aktion `emit_drl_run` (+ Aufrufer mit `motion_from_job`) | `core/src/fgc/pipeline/actions.py:425` / `:575` |
| Setup-Artefakt (robot, `wall_to_base`, tcp, `io_channels`, deadtime) | `core/src/fgc/setup/__init__.py:62` (Provisorien `:39`–`:59`) |
| Parameter-Rail für Jobs (`set_process_params`) | `core/src/fgc/pipeline/actions.py:2617`, API `core/src/fgc/pipeline/api.py:1893` |

**Was das erzeugte DRL heute enthält:** Kommentar-Header + Provisorik-Stempel,
`set_mode_analog_output` je Analogkanal, dann pro Target ggf. `set_analog_output`/
`set_digital_output` (Change-on-Delta) + genau ein `movel(posx(...), vel, acc,
radius, ref)` (Druck) bzw. `movej(posx(...), ...)` (Travel), zum Schluss alle
Kanäle auf 0/False. Posen werden **vorab** host-seitig via `wall_to_base` nach
Roboterbasis transformiert (ADR-006), Orientierung als ZYZ-Euler in Grad —
das deckt sich mit der Manual-Konvention für `posx` (Z. 1022, ZYZ bestätigt
Z. 1042–1049).

**Bereits vorhandene Lücke im Rail:** `set_process_params` kennt nur die Gruppen
`slice`/`orientation`/`ik_config`/`sections` — **`motion` hat keinen API-/UI-Rail**,
die Werte sind nur direkt im Projekt-JSON setzbar. Der Viewer exponiert
`blending_mm`/`tcp_vel_mm_s`/`tcp_acc_mm_s2` nirgends (Grep leer).

---

## 2. Befunde am heutigen Emitter (Korrekturbedarf, P0)

1. **`movej(posx(...))` ist die falsche Befehlsform.** `movej` erwartet `posj`
   (Gelenkwinkel, Grad); die posx-Variante mit Solution-Space heißt `movejx`
   (Manual Z. 2253/2501). Zusätzlich sind `vel`/`acc` bei movej/movejx
   Gelenkgrößen (deg/s, deg/s²) — wir übergeben mm/s-Werte
   (`emitter.py:153–158`). Fix-Optionen: (a) `movejx(posx, sol=…)` mit dem in
   der Simulation gewählten Solution-Space (die IK-Konfiguration ist seit #129
   end-to-end wählbar), oder (b) `posj` aus der simulierten Gelenklösung
   emittieren. Beide brauchen getrennte Travel-Dynamikfelder (deg/s) in
   `MotionParams`.
2. **AO-Kanäle: 0-basiert und zu viele.** `PROVISIONAL_IO_CHANNELS` mappt
   pump_a/pump_b/foam auf Index 0/1/2 (`setup/__init__.py:47`). Laut Manual sind
   Controller-AO-Kanäle **1 und 2** (Z. 10170/10289) — es gibt nur **zwei**
   Analogausgänge, `ch=0` ist ungültig. Drei Analogkanäle passen nicht auf den
   Controller → dritter Kanal braucht Modbus/Serial/Feldbus oder externe
   Hardware (s. §3.3). DO-Indizes sind ebenfalls 1–16 (Z. 9183), Flansch-DO 1–6
   bzw. 1–4 je Flanschversion (Z. 9682).
3. **Kein `set_tcp` im Programm.** Das Setup kennt einen TCP (provisorisch
   200 mm Flansch-Z, `setup/__init__.py:39`), aber das DRL setzt ihn nie — die
   posx-Ziele sind TCP-Posen und stimmen nur, wenn am Controller zufällig
   derselbe TCP aktiv ist. Der Emitter sollte im Header `set_tcp("<name>")`
   emittieren (Manual Z. 2025; TCP muss am Teach Pendant registriert sein —
   der Name gehört ins Setup-Artefakt) und das Programm sollte die Annahme
   dokumentieren.
4. **Kein Programm-Rahmen.** Kein `set_velj`/`set_accj`/`set_velx`/`set_accx`
   (Initialwert aller Globals ist 0.0, Z. 1638 ff. — solange wir überall
   explizite vel/acc mitgeben unkritisch, aber fragil), keine sichere
   Anfangs-/Endpose, kein `set_ref_coord`. Ein definierter Prolog/Epilog macht
   das Programm robust gegen Controller-Vorzustand.
5. **Einrückung/Namensregeln des Generators festschreiben.** DRL ist ein
   Python-Subset; Einrückung pro Block einheitlich (Z. 430), DRL-Befehlsnamen
   sind reserviert (Z. 490). Betrifft uns erst, wenn wir Funktionen/Threads
   emittieren — dann Konvention „immer 4 Spaces, Präfix `fn_`/`var_`" fixieren.

---

## 3. DRL-Fähigkeiten und wo wir sie einbauen würden

### 3.1 Bahnqualität & Taktzeit (größter Hebel für Druckqualität)

| Fähigkeit | Manual | Nutzen | Implementierungsort |
|---|---|---|---|
| `movesx(pos_list, vel_opt=DR_MVS_VEL_CONST)` — Spline durch posx-Wegpunkte, **konstante Bahngeschwindigkeit** | Z. 2950, 2988 | Gleichmäßiger Materialauftrag ohne Ruckler; ein Aufruf pro Bahnabschnitt statt movel-Kette. Kein Online-Blending mit Nachbar-Moves → Abschnitte an natürlichen Nähten schneiden. | Neuer Emit-Modus im Emitter (`print_emit: "movel" \| "movesx"`), Gruppierung zusammenhängender Print-Targets zu `pos_list`-Blöcken; Feld in `MotionParams` + `MOTION_PARAM_KEYS`. Simulation: `build_motion` bräuchte ein Spline-Zeitmodell (heute Trapez je Segment) — als provisorisches Modell markieren (S1-Stempel). |
| `moveb([posb(...)], …)` — Linien-/Kreis-Segmentkette, konstante Geschwindigkeit, explizite Eck-Radien, max. 50 Segmente | Z. 3103, 1193 | Ideal für Konturen aus Geraden+Bögen; entspricht 1:1 unserem heutigen Blending-Wunsch (Issue #63). Letztes Segment radius=0; gleichgerichtete Line-Line-Folgen verboten (Z. 3164) → Generator muss kollineare Targets zusammenfassen. | Wie movesx: Emit-Modus + Segment-Gruppierung (50er-Chunks). Das Bézier-Blending in `motion.py:blend_corner` ist unser Sim-Gegenstück — Vergleich in S1 messen. |
| `radius`-Blending der movel-Kette + `ra=DR_MV_RA_DUPLICATE`; ab SW V2.8 Auto-Clamp auf ½ Segmentlänge | Z. 2360–2437 | Heute schon emittiert (`radius=blending_mm`). Deckelung `r ≤ ½·min(Segmentlänge)` machen wir in der Sim (`blend_corner`), der Controller clamps selbst — Verhalten konsistent halten, SW-Version des Controllers dokumentieren. | Kein Codebedarf, aber S1-Messpunkt: echtes Controller-Blending vs. unser Bézier-Modell. |
| `begin_blend(radius)` / `end_blend()` | Z. 4748 | Einheitlicher Blend-Radius für einen Block statt pro-Move-Argument — kompakteres DRL. | Kosmetik im Emitter (ein Header-Befehl, `radius` je Move weglassen). |
| `set_velx/set_accx/set_velj/set_accj` — globale Defaults | Z. 1640–1962 | Programm-Prolog; Moves ohne explizite Werte fallen sonst auf 0.0 zurück. | Emitter-Prolog aus `MotionParams`. |
| `set_motion_end(DR_CHECK_OFF)` | Z. 7155 | Spart Stoppzeit-Prüfung zwischen Segmenten (Taktzeit). Reset bei Programmende. | Optionaler Prolog-Schalter in `MotionParams`. |
| `set_singularity_handling(DR_VAR_VEL \| DR_TASK_STOP \| DR_AVOID)` | Z. 6948 | **Wichtig:** Default `DR_AVOID` verlässt ggf. die Sollbahn (= Materialfehler). `DR_VAR_VEL` hält Bahntreue bei variabler Geschwindigkeit; `DR_TASK_STOP` bricht ehrlich ab — passt zu unserer „ehrliche Befunde"-Philosophie (Sim friert ein statt zu kaschieren). | Prolog-Schalter in `MotionParams`; Wahl im Design-Log begründen. Unsere Singularitäts-Warnungen (`select_along_path`) sagen vorher, wo es relevant wird. |
| `change_operation_speed(10–100)` | Z. 4998 | Laufzeit-Speed-Override für alle Folge-Moves — z. B. Erstschicht langsamer, per Bediener-Eingabe skalieren. | Emitter: optionaler Prolog (`tp_get_user_input` → `change_operation_speed`), s. §3.4. |
| `set_auto_acceleration_mode(mode, ratio)` | Z. 2161 | Auto-v/a-Anpassung bei Momentüberschreitung; für Druck ratio=1.0 empfohlen. **Achtung: überlebt Programmende.** | Prolog + Epilog-Reset; erst nach S1 anfassen. |
| `move_spiral(rev, rmax, lmax, …)` | Z. 3271 | Vasen-/Spiralmodus: kontinuierliche Z-Zustellung ohne Schichtnaht. | Ferne Option — bräuchte eigenen Slicer-Modus, nicht nur Emitter. |

### 3.2 Werkzeug & Koordinatensysteme

| Fähigkeit | Manual | Nutzen | Implementierungsort |
|---|---|---|---|
| `set_tcp(name)` | Z. 2025 | Befund §2.3 — Pflicht im Prolog. | Emitter + Setup-Feld `tcp_name`. |
| `set_tool(name)` / `set_tool_shape(name)` | Z. 6881 / 6832 | Extruder-Gewicht/-Schwerpunkt und Kollisionsgeometrie am Controller aktivieren — bessere Schwerkraftkompensation und SLF-Prüfung. Namen sind Teach-Pendant-Registrierungen → gehören als Strings ins Setup. | Setup-Schema erweitern (`tool_name`, `tool_shape_name`), Emitter-Prolog. |
| `set_workpiece_weight(...)` — dynamische Payload | Z. 6743 | Schwindendes Materialgewicht nachführen. **Heikel:** Änderung im Auto-Mode erfordert gemutete Collision Detection/TCP-SLF (Z. 6751). | Vormerken, nicht bauen. |
| `set_user_cart_coord(x1,x2,x3,pos)` (3-Punkt-Frame, ID 101–200), `set_ref_coord(DR_USRxx)`, `coord_transform` | Z. 8369, 2088, 9001 | **Architektur-Alternative zu ADR-006:** Statt host-seitig via `wall_to_base` vorzutransformieren, könnte der Controller das Wand-Frame selbst halten (unsere 3-Punkt-Antastung `fgc.setup.three_point_frame` hat ihr exaktes DRL-Gegenstück) und alle posx blieben wand-lokal. Vorteile: Posen im DRL menschenlesbar (wand-lokal), Neuantasten ohne Neu-Emission. Nachteile: Frame flüchtig bei Programmende (außer `overwrite_user_cart_coord(…, DR_PERMANENT)`), Bruch mit „die eine Transformationsstelle ist das Setup" (ADR-006). | Entscheidung fürs Grillen; wenn ja: Emitter-Option `ref: "user"` + Prolog, der das Frame aus den drei Antastpunkten setzt (Punkte ins Setup-Artefakt aufnehmen). |
| `parallel_axis` / `align_axis` / `get_normal` | Z. 7846–8090 | Düse senkrecht zu eingemessener (schiefer) Aufstandsfläche stellen. | Nur für spätere Einricht-Programme (Antast-/Kalibrier-DRL), nicht im Druckprogramm. |

### 3.3 IO & Extruder-Ansteuerung

| Fähigkeit | Manual | Nutzen | Implementierungsort |
|---|---|---|---|
| `set_analog_output(ch, val)` — ch **1/2**, Spannung 0–10 V oder Strom **4–20 mA** (`set_mode_analog_output`) | Z. 10289, 10170 | Heutiger Kern. Befund §2.2: nur 2 Kanäle, 1-basiert; Strommodus beginnt bei 4 mA (unsere `physical_range` müsste [4,20] sein, Mapping prüfen). | `PROVISIONAL_IO_CHANNELS` korrigieren; Emitter unverändert (mappt generisch). Setup-Schema: Kanalzahl gegen Robotermodell validieren. |
| `set_digital_output(index, val, time, val2)` — getaktetes Schalten | Z. 9373 | Prime/Retract-Pulse, Auto-Off nach Zeit — ohne `wait` im Hauptfluss. | Emitter, wenn Toolpath Puls-Semantik bekommt (heute nur Pegel). |
| Flansch-IO `set_tool_digital_output` etc. (1–6 bzw. 1–4) | Z. 9674 | Extruder-Signale direkt am Flansch (kurze Kabel). | Neuer `kind` im `io_channels`-Schema (`flange_digital`), Emitter-Zweig. Alternativ generisch: `set_output(port_type, …)` Z. 10403 als einziger Emit-Pfad. |
| `get_analog_input` / `wait_analog_input(ch, condition, val)` | Z. 10348, 10779 | Materialdruck-Feedback: Prime abwarten („fahre erst los, wenn Druck ≥ x"), Überdruck-Guard. | Emitter-Bausteine „Prime-Sequenz" und Watchdog (§3.4); Setup braucht AI-Kanalbeschreibung. |
| Modbus (`add_modbus_signal`, `set_modbus_output`, `wait_modbus_input` …) | Z. 14515 ff. | **Ausweg aus dem 2-AO-Limit:** Pumpen mit Modbus-Interface bekommen Sollwerte als Register — feingranular, mit Rückkanal. | `io_channels`-Schema um `kind: "modbus_register"` (+ ip/port/reg) erweitern; Emitter emittiert `add_modbus_signal` im Prolog, `set_modbus_output` statt AO. ADR-011 fortschreiben. |
| Serial (`serial_open("COM"/"COM_USB", …)`) | Z. 13183 ff. | Alternative für Extruder-Controller mit serieller Schnittstelle. | Wie Modbus — nur bei Hardware-Bedarf. |
| Industrial Ethernet Register (EtherNet/IP, PROFINET) | Z. 15763 ff. | SPS-Anbindung, falls Zellensteuerung kommt. | Vormerken. |
| Totzeit (`deadtime.t_tot_s=3 s`, heute `compensation: "simulation_shift"`) | Setup `:55` | DRL-seitige Alternative: IO-Befehle zeitversetzt zur Bahn schalten (async-Moves + `wait`, oder Thread). Heute macht das die Simulation — im DRL fehlt jede Kompensation. | Klären (Grillen): Wer kompensiert — Sim-Shift der IO-Werte im Toolpath (dann ist das DRL automatisch richtig) oder DRL-Konstrukt? Bezug ADR-012. |

### 3.4 Programm-Robustheit & Bedienerführung

| Fähigkeit | Manual | Nutzen | Implementierungsort |
|---|---|---|---|
| `thread_run(fn, loop=True)` — max. 4 Threads, **keine Motion-Befehle im Thread** | Z. 11115 | Watchdog parallel zur Bewegung: Not-Halt-DI/Druck-AI überwachen → `set_analog_output(…,0)` + `exit()`. | Emitter-Baustein „Watchdog-Thread" (Template-Funktion im Prolog); Kanäle/Schwellen aus Setup. |
| `tp_popup` / `tp_log` / `tp_get_user_input` | Z. 10907–11028 | Bediener-Gates („Material bereit?"), Layer-Fortschritt als Log, Laufzeit-Parameter (Speed-Faktor, Startlayer). Max 256 B, kein `\n`. | Emitter: optionale Prolog-Gates + `tp_log` je Layer-Wechsel (Targets tragen `layer`). |
| `drl_report_line(0)` | Z. 11626 | Deutlich schnellere Ausführung langer generierter Programme (tausende Zeilen); deaktiviert Zeilen-Monitoring. | Emitter-Prolog-Schalter (Debug an/aus). |
| `sub_program_run(name)` — Subprogramme, keine geteilten Globals, Pflicht-Header `from DRCF import *` | Z. 11564 | Sehr große Jobs in Teil-Dateien (z. B. je Abschnitt/Modul — passt zu unserem Abschnitts-Konzept). | Emitter-Splitting erst, wenn Programmgröße real drückt. |
| `stop(DR_SSTOP)` etc. | Z. 4919 | Saubere Pausen-/Abbruchlogik (stoppt Motion, nicht Programm). | Watchdog-/Gate-Bausteine. |
| `get_robot_model()` | Z. 11710 | Laufzeit-Guard: Programm prüft selbst, ob es auf dem erwarteten Modell läuft (`!= "M1013"` → `tp_popup` + `exit()`). | Billiger Emitter-Prolog-Check — passt zur Workstation-Entität. |

### 3.5 Kraftregelung & Antasten (Bezug: Antast-Gate, Issue #116, ROS2-Plan)

Musterablauf im Manual (Z. 7481–7524): anfahren → `task_compliance_ctrl` →
`set_desired_force` (z. B. −20 N in Z) → `check_force_condition` bis Kontakt →
Ist-Pose lesen (`get_current_posx`) → `release_force` → `release_compliance_ctrl`.

- **Nutzen:** automatisiertes 3-Punkt-Antasten der Wand/Druckfläche direkt als
  DRL-Programm — heute ist `wall_to_base` manuell angetastet. Ergebnisposen
  könnten per TCP-Socket zurück an den Host (§3.6) oder als User-Frame direkt
  am Controller gesetzt werden (§3.2). Das bedient genau das „Antast-Gate hart
  für Material" aus der ROS2-Planung und Issue #116 (Antast-Frame → Sensorik).
- **Voraussetzung klären:** M1013 = M-Serie (damping/force_factor verfügbar,
  Z. 7665/7753); ob ein FT-Sensor (FTS) verbaut ist, entscheidet über die
  Kraftschätzqualität (`check_robot_fts()`, Z. 11786).
- **Implementierungsort:** eigenständiges Einricht-DRL (neuer Emitter-Baustein
  „Antastprogramm" neben dem Druckprogramm), nicht Teil des Druck-Emits.
  `fgc.setup.three_point_frame` bleibt das Host-Gegenstück.

### 3.6 Live-Steuerung / Streaming (Zukunft: ROS2-Bridge)

| Fähigkeit | Manual | Nutzen | Einordnung |
|---|---|---|---|
| `client_socket_open/read/write` + Thread-Muster (Thread liest Socket → globale Var → Main bewegt) | Z. 13711, 11415 | **Blaupause für die geplante ROS2-Bridge** (segmentweise Goals, Bridge autonom): DRL-Programm verbindet sich zum Linux-Druckserver, empfängt Segment-Kommandos, quittiert. | Emulator-Spike der ROS2-Planung; noch kein Emitter-Code. |
| `servol(posx, …)` / `speedl` — Ziel-/Geschwindigkeits-Streaming, ~0.1-s-Watchdog, kein Blending/Override/Force | Z. 5618, 5807 | Feinste externe Bahnkontrolle (Host generiert Bahn in ~10 Hz+). Hohe Komplexität — erst relevant, falls segmentweise `movesx`-Goals nicht reichen. | Option für die Bridge, im Spike vergleichen. |
| `enable_alter_motion` / `alter_motion(d)` — Live-Bahn-Offset aus User-Thread (Achtung: fixed-XYZ, nicht ZYZ) | Z. 5227, 5321 | Echtzeit-Z-Korrektur (Schichthöhen-Nachführung per Sensor) **ohne** die Bahn neu zu emittieren — Mittelweg zwischen statischem DRL und Voll-Streaming. | Starker Kandidat fürs Sensorik-Kapitel (nach #116). |

---

## 4. Priorisierte Roadmap (Vorschlag, vor Umsetzung grillen)

**P0 — Korrektheit (kleine Emitter-Fixes + Setup-Daten):**
1. Travel-Emission fixen: `movejx(…, sol=…)` oder `posj` aus Sim-Lösung; Travel-Dynamik in deg/s (§2.1).
2. AO-Kanäle 1-basiert, max. 2, Strommodus-Range 4–20 mA; `PROVISIONAL_IO_CHANNELS` korrigieren (§2.2).
3. Prolog/Epilog: `set_tcp`, globale vel/acc-Defaults, definierte Endpose/IO-Aus (§2.3/2.4). Setup-Schema um `tcp_name`/`tool_name` erweitern.

**P1 — Quick Wins ohne Architekturänderung:**
4. Prolog-Schalter in `MotionParams`: `set_singularity_handling`, `set_motion_end`, `drl_report_line`, `get_robot_model`-Guard.
5. `tp_log` je Layer + optionales Bediener-Gate (`tp_popup`) und Speed-Faktor (`tp_get_user_input` → `change_operation_speed`).
6. `process_params.motion` einen API-/UI-Rail geben (`set_process_params` um Gruppe `motion` erweitern + Viewer-Formular) — sonst bleiben alle neuen Schalter unbedienbar.

**P2 — Bahnqualität (je ein Spike, Sim-Modell mitziehen):**
7. Emit-Modus `movesx` (`DR_MVS_VEL_CONST`) für Print-Blöcke; alternativ/ergänzend `moveb`+`posb` für Geraden+Bögen. S1-Messung: Controller-Blending vs. unser Bézier-Modell.
8. Watchdog-Thread + Prime-Sequenz (`wait_analog_input`) als Emitter-Bausteine.

**P3 — Architektur-Entscheidungen (Grillen, ggf. ADR):**
9. User-Frame am Controller statt Host-Vortransformation (ADR-006-Revision?) (§3.2).
10. Totzeit-Kompensation: Sim-Shift vs. DRL-Konstrukt (ADR-012-Bezug) (§3.3).
11. Modbus/Serial für >2 Analogkanäle bzw. Pumpen mit Bus-Interface (ADR-011-Fortschreibung) (§3.3).
12. Antast-DRL mit Kraftregelung (Issue #116) und später `alter_motion`/Streaming für die ROS2-Bridge (§3.5/3.6).

---

## 5. Offene Fragen (vor Umsetzung klären)

- Controller-SW-Version ≥ 2.8? (Auto-Clamp des Blend-Radius, Flanschversion → Tool-IO-Anzahl.)
- Ist am M1013 ein FT-Sensor verbaut (`check_robot_fts`)? Bestimmt die Qualität der Kraft-/Antastfunktionen.
- Wie viele Analogkanäle braucht der Endausbau wirklich (pump_a/pump_b/foam = 3 > 2 Controller-AOs)? → Hardwarefrage vor ADR-011-Fortschreibung.
- Wegpunkt-Obergrenze von `movesx` (im Manual nicht beziffert) — im Emulator-Spike austesten.
- Wer misst wann S1 (vel/acc/Blending am Gerät)? Viele Punkte oben tragen den Provisorik-Stempel bis dahin.
