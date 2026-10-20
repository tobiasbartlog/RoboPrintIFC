# verify/

Abnahme nach `spec/SPEC.md` §11. Nach Ende P0 gesperrt (`spec/LOCKED`). Für den durchgehenden Strang
(Nutzerentscheidung 20.10.2026, SPEC §5.3) hat der Nutzer die Sperre aufgehoben; Stand: Strang-Vertrag
aus Commit 81d0f3b.

| Datei | Zweck | Entsteht |
|---|---|---|
| `run.py` | Gate-Runner, aufgerufen über `scripts/verify.py` | vorhanden |
| `oracle/robot_oracle.py` | FK und Grenzen aus der URDF mit Pinocchio | P0, A0.2 |
| `oracle/collision_oracle.py` | Abstände mit Coal auf Roh-Meshes, Paare exakt nach SPEC §5.1 | P0, A0.2 |
| `oracle/interval_checker.py` | schnelle, exakte Statusbestimmung entlang dichter Trajektorien (für `check_run`) | P0, A0.2 |
| `oracle/run_checks.py`, `oracle/run_geometry.py` | Einzelprüfungen je Teil, Schnitte, Abdeckung, IFC-Vermessung | P0, A0.2 |
| `oracle/strand_rules.py` | Strang-Regeln für G3: Ablauf, Schichtregel, Verbinder-Geometrie, Zweigwechsel je Strang (nur numpy/shapely) | Strang, 20.10.2026 |
| `oracle/test_g1_kinematics.py` | G1: vergleicht `roboprint.robot` mit `robot_oracle` | P0, A0.2 |
| `oracle/test_g2_collision.py` | G2: vergleicht `roboprint.collision` mit `collision_oracle` | P0, A0.2 |
| `check_run.py` | G3/G4: prüft einen Laufordner (SPEC §6) dicht und unabhängig. `python -m verify.check_run <dir> --scenario <json> [--jobs N]` schreibt `<dir>/check.json` und endet mit 0 genau bei Bestehen | P0, A0.2 |
| `fake_drcf/` | G5: führt DRL in CPython mit Stubs aus. `python -m verify.fake_drcf <dir>...` endet mit 0 genau bei Bestehen | P0, A0.2 |
| `fake_drcf/pump.py` | Pumpen- und Strangregeln für G5 (nur numpy) | Strang, 20.10.2026 |
| `oracle/minirun.py` | konstruierter Mini-Laufordner (FK + numerische IK + Orakel) für die Selbsttests; `strand=True` baut die Strang-Variante | P0, A0.2; Strang |

**Unabhängigkeit:**
- Die Orakel (`*_oracle.py`, `check_run.py`, `fake_drcf/`) lesen nur die URDF, die Assets und die
  Artefakte. Sie importieren `roboprint` nie.
- Nur die Vergleichstests `test_g1_*` und `test_g2_*` importieren beide Seiten, das System unter Test
  und das Orakel. Sie importieren `roboprint` ohne Skip: Fehlt das Paket, ist das Gate rot.

**Selbsttests:** `oracle/selftest_*.py` (ohne roboprint), `python -m pytest verify -q -n 2`. Die
`conftest.py` sammelt sie und lässt G1/G2 bei einer Verzeichnis-Sammlung aus, solange `roboprint` fehlt;
direkt aufgerufen (wie im Gate-Runner) schlagen G1/G2 dann fehl. Abgedeckt u. a.: bekannte Posen →
bekannte Flanschkoordinaten, ZYZ-Roundtrip bei b ∈ {0°, 1e-9°, 90°, 179.999999°, 180°}, Würfel im Glied
→ d < 0, bekannter Abstand zu einem Quader, Boden-Halbraum, Intervall-Prüfer gegen exakten Abstand,
Mini-Lauf besteht `check_run`/`fake_drcf` und fällt bei manipuliertem Status, Sprung, Schichtregel,
TCP, `ch=0`, um 180° verdrehter Düse, fehlender Fehlerbehandlung usw. durch.

Strang-Selbsttests: Die Strang-Variante des Mini-Laufs (Ring 0 → 1 in derselben Schicht und 1 → 2 mit
Schichtwechsel über Verbinder, danach Travel zu Ring 3, dessen erlaubter Verbinder ungenutzt bleibt,
`link_max_mm` = 60) besteht `check_run` und `fake_drcf` (v2, v3); der alte Mini-Lauf läuft mit
`link_max_mm` = 0. Durchfallen müssen: `link` ohne `link_next`, Verbinder 1,5 mm neben der Geraden,
Verbinder über einer Bohrung im Teil, Verbinder länger als `link_max_mm` oder bei `link_max_mm` = 0,
falsche Schicht im Verbinder, Zweigwechsel im Verbinder, falsches `zweig_wechsel_in_ringen`, Pumpe aus
zwischen `print` und `link`, Pumpe an während `retract`, Halt im Strang (`radius = 0` oder `wait`, auch
mit erneutem Pumpe-an ohne Zustandswechsel), `wait` am Strangende vor Pumpe aus, zu großer Radius am
Verbinder, fehlendes `toolpath.json`. `oracle/selftest_strand.py` prüft dieselben
Regeln zusätzlich auf synthetischen Daten; diese Datei braucht weder Pinocchio noch Coal.

## Methoden

**Kinematik.** Pinocchio-Modell direkt aus `m1013.white.urdf` (m → mm), Flansch = `link_6`,
TCP = Flansch · `tcp_frame` aus `tools/30gut.json`. Grenzen aus `robots/doosan_m1013.json`
(`joint_limits_rad`, `joint_velocity_limits_rad_s`). Die URDF rundet π/2 auf 1,571: Die Kette ist
dadurch nicht exakt sphärisch (Nullstellung x = 0,14 mm, Handgelenk-Flip ~0,02 mm). Maßgeblich ist
die URDF; eine rein analytische IK auf Nennmaßen verfehlt G1 (0,01 mm), sie muss nachiterieren.

**Zweig-Klassifikation (eigene).** Vorzeichen von (Schulter: Handgelenkzentrum vor/hinter der J1-Achse
entlang a2 × a1; Ellbogen: Ellbogen links/rechts der Linie Schulter → Handgelenk um die J2-Achse;
Handgelenk: sin q5). Die Polarität gegen Lefty/Righty usw. ist offen; geprüft wird, dass die Zuordnung
eigene Klasse ↔ `branch` eineindeutig ist (abseits der Singularitäten: 50 mm bzw. |sin q5| ≥ 0,05) und
dass sich innerhalb eines Strangs (`approach`, `print`, `link`, `retract` ohne Travel dazwischen) weder
`branch` noch die eigene Klasse ändert (je Ring des Strangs etwa 50 Stichproben, dazu das letzte Sample).

**Kollision.** Geometrie wie SPEC §5.1 aus den Roh-Meshes (URDF-.dae mit Knoten-Transformationen,
Werkzeug-STL über `mesh_transform`, Tisch-STL, `part.stl` ∩ {z_P ≤ k·h} per manifold3d). Düsenspitze =
Werkzeugdreiecke in der Kugel r_free um den TCP (Grenzdreiecke auf 1 mm unterteilt, Zuordnung nach
Schwerpunkt), Rest = Werkzeugkörper. Paare exakt nach SPEC §5.1 (`checked_pairs()`, 42 Paare).
- Abstand: Branch-and-Bound über Würfelzellen (80 mm, Tisch 160 mm) mit Hüllkugel und konvexer Hülle
  als unteren Schranken und Coal-BVH (OBBRSS) auf den Original-Dreiecken als exaktem Abstand. Boden:
  min z der Hüllpunkte (exakt).
- Durchdringung: Coal-Dreiecksschnitt; Enthaltensein ohne Dreiecksschnitt über Windungszahl einer Ecke
  je Komponente (nur wenn sich die konvexen Hüllen überlappen).
- Eindringtiefe (nur G2): untere Schranke der translatorischen Eindringtiefe = größter Abstand einer
  Ecke des einen Körpers, die per Windungszahl im geschlossenen Solid des anderen liegt, zu dessen
  Oberfläche (beide Richtungen; Glieder je geschlossener Mesh-Komponente, Tischkörper, Druckstand;
  das offene Werkzeugmesh nur als eindringender Körper; höchstens 400 Kandidaten je Solid). Ein Punkt
  in Tiefe p erzwingt eine Verschiebung ≥ p, der Wert ist also nie tiefer als die wahre Tiefe. Ohne
  bestätigte Ecke gilt d = −0,001 mm.

**G2-Auslegung.** Szene S1: Quader 600 × 200 × 400 bei S = (0, −50), Gier 0, k = 20. 250 gleichverteilte
und 250 teilnahe Posen (numerische IK auf Ziele um den Druckstand), Seed 20261018. Bei d_coal ≥ 0 gilt
d_rp ≤ d_coal + 1 mm; bei d_coal < 0 wird nur d_rp ≤ 1 mm verlangt (die Tiefe nichtkonvexer Körper ist
nicht eindeutig, eine VHACD-Stückzerlegung liefert legitim andere Tiefen); wo |d_coal| > 12 mm gleiches
Vorzeichen; wo beide ≥ 0 |d_rp − d_coal| ≤ 12 mm.

**check_run (G3/G4).** Je Sample eigene FK (`tcp` ≤ 0,05 mm / 1e-4 rad), Grenzen, Schichtregel und Ablauf
je Strang nach ARTEFAKTE, Abtastdichte (TCP ≤ 5,05 mm, max|Δq| ≤ 0,005 rad + 1e-6 zwischen erreichbaren
Nachbarn, auch in Verbindern), Druck-Samples ≤ 0,5 mm neben dem Druckring, jeder Ringpunkt ≤ 1 mm an der
gefahrenen Druckbahn (Ringstart = letztes `approach`- oder `link`-Sample desselben Rings), Wegpunkte auf
z_P = (L+1)·h, Düsenachse ≤ τ_max + 0,1° (Druck und Verbinder), Zweige (s. o.), Abdeckung je Schicht
≥ 95 % des Schalenbereichs (Schnitt von `part.stl` bei z = (L+0,5)·h, Schalenbereich = Schnitt minus
innerer Puffer shells·w, Druckbahnen mit w/2 gepuffert, shapely), Summen in `trajectory.summary`.
- Strang (`strand_rules.py`, ARTEFAKTE, SPEC §5.3): `layer` von `link` = Schicht des folgenden Rings
  (= `ring[i]`); Travel = Schicht des zuletzt gedruckten Rings + 1. Je Ring genau ein `print`-Abschnitt;
  direkt davor `approach` oder `link` desselben Rings, direkt danach `retract` desselben Rings oder `link`
  des Rings r + 1. `link` mit Ring r + 1 nur direkt zwischen `print` r und `print` r + 1 und nur bei
  `toolpath.rings[r].link_next = true` (fehlt der Schlüssel: false).
- Verbinder von Ring r nach r + 1, A = letzter Wegpunkt von r, B = erster Wegpunkt von r + 1: jedes
  erreichbare `link`-Sample ≤ 0,5 mm neben der Strecke A–B (3D, beim Schichtwechsel steigt sie um h);
  das letzte `print`-Sample von r oder das erste `link`-Sample liegt ≤ 0,5 mm an A, das letzte
  `link`-Sample ≤ 0,5 mm an B; Schichtsprung L(r+1) − L(r) ∈ {0, 1}; waagrechte Länge |A–B|_xy ≤
  `link_max_mm` + 0,01 mm, bei `link_max_mm` = 0 ist kein Verbinder erlaubt; die waagrechte Projektion
  von A–B (Frame P) liegt im Querschnitt von `part.stl` bei z = (L(r+1)+0,5)·h, beim Schichtwechsel auch
  bei z = (L(r)+0,5)·h, Toleranz 1 mm (Querschnitt um 1 mm gepuffert). `link_max_mm` kommt aus `summary.json params`
  (Default 60 mm, SPEC §10); nennt das Szenario einen Wert, muss `summary.json` ihn tragen.
- `trajectory.summary.zweig_wechsel_in_ringen` = Anzahl der `branch`-Wechsel zwischen aufeinanderfolgenden
  erreichbaren Samples innerhalb eines Strangs (ARTEFAKTE), exakt nachgezählt; G3 verlangt zusätzlich 0.
- Status: Der Prüfer hält je Paar ein Intervall [lb, ub] (`interval_checker.py`): lb aus der letzten
  exakten Rechnung minus der seither möglichen Verschiebung beider Körper, ub aus dem Abstand des
  letzten Zeugenpunktpaars. Liegt eine der Schwellen {0, d_hard, 12, d_target − 1, d_target,
  d_target + 12} zwischen min lb und min ub, wird exakt nachgerechnet. Damit ist auf jedem Sample
  entschieden, auf welcher Seite jeder Schwelle d liegt; das genügt für alle Kriterien.
- Statusvergleich: roboprint-Status muss zu seinem `d_mm` passen (SPEC §2). Gegen den Prüfer ist jeder
  Status erlaubt, der für ein d' ∈ [d − 12, d + 1] gilt (roboprint darf bis 12 mm konservativer, höchstens
  1 mm optimistischer sein, wie G2); sieht der Prüfer `collision`, muss roboprint `collision` melden.
  d ≥ d_hard gilt für Prüfer und roboprint.
- S2 zusätzlich: Wände unabhängig mit ifcopenshell (Volumen mit Öffnungen, Dicke = kleinere horizontale
  Ausdehnung im Platzierungs-Frame, Sturzhöhen); Teilvolumen = Wandvolumen ± 0,5 %, paarweise
  Überlappung in L ≤ 0,1 % (manifold3d), Teil steht bei z_S = 0 ± 0,5 mm, Grundriss in der Tischplatte
  (Schnitt der Tisch-STL bei z = 900), kein Schnitt mit `base_link`, Sturzlinien auf einer Teil-Unterkante
  (± 1 mm). S3: roboprint meldet ≥ 1 `collision`, der Prüfer bestätigt ≥ 1 davon.
- Statusregel (SPEC §2, Nachtrag 19.10.2026): Der Prüfer rechnet das Intervall von d_status. Das Paar
  `base_link` ↔ `link_2` (`RELAXED_PAIRS` in `collision_oracle.py`) wird zuerst gegen d_hard
  entschieden und fällt darüber aus dem Minimum heraus. `--old-status-rule` prüft mit der alten Regel
  (alle Paare), nur zum Vergleich alter Läufe.
- Laufzeit und Speicher: Teil für Teil. Je Arbeitsprozess wird ein Teil geladen (Trajektorie sofort in
  numpy-Arrays, Listen verworfen), geprüft und freigegeben; die Abstände laufen danach in Blöcken
  (`--jobs`, Default min(4, CPUs), Umgebungsvariable `VERIFY_JOBS`), der Orakel-Cache je Prozess hält
  höchstens zwei Teile. Wandprüfungen nutzen nur `part.stl`, `T_LP` und `T_WP` je Teil. Geometrie wird
  vor dem Fork einmal gebaut (~10 s).
- Inhalts-Cache (`oracle/content_hash.py`): Teile mit gleichem SHA-256 über `part.stl`,
  `trajectory.json` und `toolpath.json` (Wert von `part_id` ausgenommen) und `part.json` (ohne
  `part_id`, `wall_id`, `T_LP`, die nur die Wandprüfung liest) werden einmal geprüft; Duplikate
  übernehmen Fehler und Kennzahlen mit `same_as`. Jede andere Abweichung prüft das Teil einzeln.
  `fake_drcf` ebenso: gleiche Trajektorie, gleicher Toolpath (je ohne `part_id`) und gleicher DRL-Text
  bis auf Kommentarzeilen (Zeilennummern bleiben) → einmal ausführen, Vermerk `(wie <Teil>)`; `--jobs`
  wie oben.

**fake_drcf (G5).** DRL wird mit `exec` in einem Namensraum ausgeführt, der nur die in
`docs/doosan-drl.md` belegten Befehle (posj, posx, movej/amovej, movel/amovel, movesx/amovesx nur v3,
set_velx/accx/velj/accj, set_tcp, set_singularity_handling, set_mode_analog_output, set_analog_output,
wait, mwait, check_motion, change_operation_speed), die DR_-Konstanten und harmlose Builtins enthält.
Abgelehnt: `movej(posx)`, `ori_type`, `movesx` in v2, > 100 Punkte, `vel_opt` ≠ DR_MVS_VEL_CONST,
`moveb`/`movejx` (nicht belegt bzw. nicht im Emitter vorgesehen), Kanal ∉ {1, 2}, AO ohne Modus oder
außerhalb 0–10 V, Gelenk-vel/acc über den Grenzen (Skalar gegen die kleinste Grenze), kartesisch
> 1000 mm/s, `ref` ≠ DR_BASE, relative Bewegungen. Prolog: set_vel*/acc*, `set_tcp("FGC_30GUT")`,
`set_singularity_handling(DR_VAR_VEL)`, AO-Modus und als erste Bewegung `movej(posj(home))`.
Bewegungsziele müssen eine monotone Teilfolge der Samples sein (`posj` ≤ 0,001°, `posx` gegen eigene FK
mit eigener ZYZ-Umrechnung, Vergleich über Rotationsmatrizen, ≤ 0,1 mm / 0,05°), das Programm endet
am letzten Sample, Samples zwischen zwei `movel`-Zielen liegen auf der Geraden (≤ 0,5 mm), zwischen
zwei `movej`-Zielen auf der Gelenkgeraden (≤ 1e-4 rad). `radius` ≤ ½ der Nachbarsegmente (auch am
Verbinder). Programmende setzt jeden AO-Kanal auf 0; ein zweiter Lauf löst bei der ersten Bewegung mit
Pumpe einen Fehler aus und verlangt danach AO = 0 (Exception-Handling).
- Pumpe und Strang (`fake_drcf/pump.py`, SPEC §5.3/§5.6, ARTEFAKTE). Bewegung k fährt die Samples
  idx[k−1]+1 … idx[k]. Pumpe an (AO 1 oder 2 > 0) nur in Bewegungen über `print`/`link`, jede Bewegung
  über `print`/`link` mit Pumpe. Einschalten nur im Stillstand am Strangbeginn: die letzte Bewegung
  endet auf `approach`, das nächste Sample ist `print`, synchron mit radius 0. Ausschalten nur im
  Stillstand am Strangende: letzte Bewegung endet auf `print`, das nächste Sample ist `retract`, synchron
  mit radius 0; damit gibt es kein Pumpe-aus zwischen `print` und `link`. Kein Halt im Strang: ein
  `movel` zwischen zwei Bewegungen mit Pumpe (ohne Pumpenwechsel dazwischen) hat radius > 0, außer ein
  Nachbarsegment ist kürzer als 0,01 mm. Ein AO-Befehl ohne Zustandswechsel (z. B. erneut 5 V bei
  laufender Pumpe) ist kein Pumpenwechsel und zwischen zwei Bewegungen mit Pumpe selbst ein Fehler
  (SPEC §5.6). Kein Verweilen mit laufender Pumpe: `wait` (> 0 s) und `mwait` nur direkt nach dem
  Einschalten (Pumpen-Vorlauf t_tot, SPEC §5.5); im Stillstand am Strangende vor dem Ausschalten ist nur
  `mwait(0)` erlaubt. `movesx`-Punkte zählen ohne Radius.
- Jeder Wegpunkt aus `toolpath.json` liegt ≤ 1 mm an einem Bahnstück seines Rings (Ringstart = letztes
  `approach`-/`link`-Sample, dann die `print`-Samples), und die Bewegung über dieses Stück läuft mit
  Pumpe. `toolpath.json` fehlt → Fehler.
