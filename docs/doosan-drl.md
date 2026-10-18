# Doosan M1013 und DRL: belegte Semantik

Recherche vom 2026-10-18 gegen das offizielle Programming Manual (manual.doosanrobotics.com) und
gegen v1. Jede Aussage hat eine Quelle. Was **offen** ist, wird vor der Nutzung in der verlinkten
Seite nachgelesen und hier ergänzt. Das gilt ab P0 als Teil der Spezifikation: Der Fake-Controller
akzeptiert nur, was hier steht.

## Steuerung und Dialekt

- Laut Nutzer läuft auf dem Controller vermutlich Firmware **2.x**, ein Update ist geplant.
  `docs/drl-nutzungsplan.md` aus v1 (jetzt `legacy/docs/`) wurde nach Manual V2.10.1 verfasst.
- Dialekt `v2` nutzt nur Befehle, die es in 2.x gibt. Dialekt `v3` darf die mit „ab V3“
  markierten Befehle nutzen.
- Die Versionsnummer liest der Nutzer am Teach Pendant ab (offen).

## Gelenke und Kinematik

- Die Gelenkkonvention der Steuerung ist identisch mit der URDF-Nullstellung
  (`third_party/doosan_m1013/urdf`). v1 rechnete intern mit q_dh = q_doosan + (−180°, +90°, +90°, 0, 0, 0)
  und prüfte die Grenzen fälschlich im DH-System. Das war die Hauptursache der Kollisionen.
- Kenndaten:
  - Reichweite 1300 mm
  - J3 ±160°, J1, J2, J4, J5, J6 ±360°
  - Gelenkgeschwindigkeit 120/120/180/225/225/225 °/s
  - URDF-Maße: d1 = 152,5, Seitenversatz 34,5, a2 = 620, d4 = 559, d6 = 121 mm
  - Das Handgelenk ist sphärisch (gegen die URDF geprüft).
- Die Beschleunigungsgrenzen in `robots/doosan_m1013.json` sind geschätzt (4 × v_max/s).
- `ikin(pos, sol_space, ref)`: `sol_space` 0–7 wählt den Zweig (Schulter, Ellbogen, Handgelenk).
  0 = Lefty/Below/NoFlip … 7 = Righty/Above/Flip. Ab Manual 3.4 bedeutet `sol_space = 255` die
  Lösung, die der aktuellen am nächsten liegt.
  - Quelle: https://manual.doosanrobotics.com/en/programming-manual/3.4.0/publish/ikin-pos-sol_space-ref-ref_pos_opt-iter_threshold
  - **Offen:** die genaue Bitzuordnung (welches Bit welches Gelenk) aus der Tabelle dort
    übernehmen. `roboprint.robot` nutzt dieselbe Zuordnung.
- Der Controller rechnet `ikin` mit kalibrierten DH-Parametern, der Host mit den Nennwerten.
  Der Unterschied liegt unter 1 mm.

## Posen

- `posx(x, y, z, a, b, c)`: mm und Grad, Euler **ZYZ**, R = Rz(a)·Ry(b)·Rz(c). Eine Liste mit
  6 Werten ist zulässig.
  - Quelle: https://manual.doosanrobotics.com/en/programming-manual/3.2.2/publish/posx-x-0-y-0-z-0-a-0-b-0-c-0
- Ab V3: `posx([...quat], ori_type=DR_QUAT)` (gleiche Quelle). Nur im Dialekt `v3`.
- **Gimbal-Fall:** Bei b ≈ 0° oder b ≈ 180° sind a und c gekoppelt. Bei Düse senkrecht nach unten ist
  b ≈ 180° der Normalfall. v1 rechnete dort falsch (`a = atan2(r21, r11)` statt
  `atan2(−r21, −r11)` bei b ≈ π) und verdrehte die Düse um 180°, der Flansch lag dadurch etwa 146 mm
  daneben. Pflicht ist ein Roundtrip-Test R → ZYZ → R für b ∈ {0°, 1e-9°, 90°, 179.999999°, 180°}.
- `posj(j1, …, j6)` in Grad.

## Bewegungsbefehle

- `movej(posj, vel, acc)`: gelenkinterpoliert, vel in °/s, acc in °/s².
  - `movej(posx)` gibt es erst ab V3.2 und entspricht dann `movejx`. Ohne `sol` wählt der
    Controller den Zweig selbst. Im Dialekt `v2` deshalb nur `movej(posj)`.
  - Quelle: https://manual.doosanrobotics.com/en/programming-manual/3.4.0/publish/movej
- `movel(posx, vel=[mm/s, °/s], acc=[mm/s², °/s²], radius, ref, ra)`: kartesisch linear und
  **synchron**.
  - Bei `radius = 0` hält der Roboter am Ziel an. Beim Extrudieren entsteht dort ein Materialbatzen.
  - Bei `radius > 0` beginnt der nächste Befehl beim Eintritt in die Blending-Zone. Ein dort
    stehendes `set_analog_output` schaltet also um den Radius zu früh.
  - `ra = DR_MV_RA_DUPLICATE` hängt Blends aneinander.
  - Quelle: https://manual.doosanrobotics.com/en/programming-manual/3.7.0/publish/movel
- `movesx(pos_list, vel, acc, vel_opt=DR_MVS_VEL_CONST)`: Spline durch **höchstens 100**
  Wegpunkte bei konstanter Geschwindigkeit, ohne Online-Blending zum nächsten Befehl.
  `spline_type = DR_HERMITE` und `amovesx` zum Verketten gibt es nur in neuerer Firmware.
  - Quelle: https://manual.doosanrobotics.com/en/programming-manual/3.7.0/publish/movesx
- `moveb(seg_list, …)`: Linien- und Kreissegmente mit Blending, höchstens 50 Segmente
  (offen: Verfügbarkeit in 2.x prüfen).
- Der Präfix `a…` (z. B. `amovel`) startet eine Bewegung asynchron. Mit `mwait()` wartet man auf ihr
  Ende, `check_motion()` fragt den Zustand ab.
- Thread-Funktionen dürfen keine Bewegungsbefehle enthalten.

## Einstellungen

- `set_tcp("<name>")`: Der TCP muss am Teach Pendant unter diesem Namen angelegt sein, sonst sind
  alle `posx` falsch. Geplanter Name `FGC_30GUT` mit den Werten aus `tools/30gut.json`: Position
  (134, 0, 73) mm, 90° um Flansch-Y.
- `set_velx(v, w)`, `set_accx(a, aw)`, `set_velj(v)`, `set_accj(a)`: globale Defaults.
- `set_singularity_handling(DR_VAR_VEL)`: Die Bahn bleibt erhalten, die Geschwindigkeit wird
  variabel. Der Default `DR_AVOID` weicht von der Bahn ab und ist für den Druck ungeeignet.

## Analogausgänge

- Die Kanäle heißen **1 und 2**, nicht 0. Spannungsmodus 0–10 V, Strommodus 4–20 mA.
  - `set_mode_analog_output(ch=1, mod=DR_ANALOG_VOLTAGE)`
  - `set_analog_output(ch=1, val=5.0)`
  - Quelle: https://manual.doosanrobotics.com/en/programming-manual/3.2.1/publish/set_analog_output-ch-val
- v1 nutzte die Indizes 0/1/2. Damit bricht `ch=0` das Programm ab, und `pump_b` landete auf dem
  Kanal von `pump_a`.
- **Totzeit:** v1 kompensierte nur in der Simulation, das Programm bekam unverschobene Werte.
  v2 setzt heute „Pumpe an am Ringstart + `wait(t_tot)`“ (SPEC §5.6). Eine bahnsynchrone Lösung
  (asynchrone Bewegung plus Zeitplan, oder räumlich vorgezogenes Schalten) folgt nach den
  Messungen am Gerät.

## Programmstruktur

- Für große Programme Posenlisten plus Schleife statt Tausender Einzelzeilen. Je Teil ein Programm.
  Eine harte Größengrenze ist nicht dokumentiert (offen). Alternativen sind `sub_program_run` und
  Streaming über API-DRFL (C++, https://github.com/doosan-robotics/API-DRFL).
- Am Programmende und im Fehlerfall Analogausgänge auf 0 setzen.

## Validierung

- **Fake-Controller** (`verify/fake_drcf`, Gate G5):
  - führt den DRL-Text in CPython mit Stubs aus
  - prüft Signaturen, Dialekt, Kanäle, Wertebereiche, Grenzwerte, die Grenze von 100 Punkten
    und Blending-Radien
  - prüft, ob jede Pose der geplanten entspricht, mit eigener ZYZ-Umrechnung
- **Emulator** (optional, später):
  - Ablauf: `doosan-robot2` (ROS 2 Humble) startet das Docker-Image
    `doosanrobot/dsr_emulator:3.0.1` mit `mode:=virtual model:=m1013`; DRL geht über den Service
    `drl/DrlStart`.
    Quellen: https://github.com/DoosanRobotics/doosan-robot2 · https://manual.doosanrobotics.com/en/ros/2.00/Publish/drlstart-srv
  - Grenzen: Ein Emulator mit V3 akzeptiert mehr als ein Controller mit 2.x, und das AO-Timing ist
    nicht emulierbar.
- DART Studio und Simulator führen keine IOs aus.
  Quelle: https://manual.doosanrobotics.com/en/dartsimulatorset/2.8.2/Publish/what-is-dart-simulator
- **Am Gerät:** Vor dem ersten Druck ein Trockenlauf ohne Material mit `change_operation_speed(10…20)`,
  erst danach die Messungen zu AO-Latenz und Totzeit.
