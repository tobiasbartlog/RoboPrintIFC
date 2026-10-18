# Gegenprüfung A2.4 (Phase P2)

Stand 2026-10-18, Branch `v2/a2-4-gegenpruefung` auf `v2-nachtlauf` (eafcd4a). Rolle: Gegenprüfer.
Auftrag: „Finde ein Teil, ein Sample oder eine Pose, bei der unser Status oder der Prüfer falsch liegt.“

Klassen: **(A)** Systemstatus falsch, **(B)** Prüfer falsch oder lückenhaft, **(C)** Lücke in der SPEC.
Es wurde kein Produktionscode geändert. `spec/` und `verify/` sind unverändert; die Skripte unter
`experiments/gegenpruefung/` importieren die Orakel nur.

## Kurzfassung

Der Lauf S1 ist nach allem, was sich nachrechnen ließ, **wirklich frei**. Auch die Bewegung zwischen
den Samples ist frei. Ich habe kein Sample gefunden, dessen Status im echten Lauf falsch ist (A).
Die Prüfer sind aber deutlich schwächer, als G3/G5 vermuten lassen: **Sieben gezielt manipulierte,
physikalisch falsche Läufe bestehen `check_run` und `fake_drcf` beide** (M1–M7). Dazu kommt eine Pose,
in der die Düse in `link_4` steckt und beide Seiten `warn` mit d ≈ 20 mm melden, weil SPEC §5.1 dieses
Paar nicht prüft.

| # | Schwere | Klasse | Fund | Beleg |
|---|---|---|---|---|
| F1 | hoch | B (+C) | Schichtreihenfolge wird nicht geprüft: Obere Schicht vor der unteren gedruckt, Düse fährt danach durch die gedruckte Schicht → besteht | M4 |
| F2 | hoch | C + B | Düsenspitze ↔ Druckstand ist auch bei Travel ausgenommen: TCP 5 mm im Druckstand (26 Samples) → besteht | M7 |
| F3 | mittel | C + B | Düsenspitze ↔ Glieder nicht geprüft: Düse 6,4 mm in `link_4`, beide Seiten melden `warn` (d = 19,0 / 22,9 mm) | Pose P1 |
| F4 | mittel | B | S1-Modus: kein Abgleich Teil ↔ Szenario, keine Tischprüfung, keine Präzision der Druckbahn: halbe Höhe, 40 % neben dem Tisch und ein Ring 15 mm außerhalb des Teils → bestehen | M1, M5, M6 |
| F5 | mittel | B | Start in Home nicht verlangt: Trajektorie ohne Home-Start besteht. `movej(home)` → Start (J1 117°) bleibt ungeprüft | M3 |
| F6 | niedrig | B | `d_mm`, `pair` und `witness` werden nur über das Statusband geprüft: erfundene Werte bestehen. Der Viewer würde ein falsches Glied hervorheben | M2 |
| F7 | niedrig | C | Zwischen Samples wird nicht geprüft. Theoretisch kann d je Schritt um bis zu 2,6 mm fallen; in S1 fällt es nachgerechnet um ≤ 0,001 mm | E1 |
| F8 | niedrig | C | Reserve in Schicht 0 ist strukturell h + 1,85 mm. Mit h < 8,15 mm wird jedes Teil per Konstruktion unmachbar | E2 |
| F9 | niedrig | A (Zeit) | `timing` und DRL nutzen verschiedene Geschwindigkeiten (An-/Abfahrt, Abheben/Absenken). Druckzeit und Viewer-Uhr passen nicht zum Gerät | E3 |
| F10 | Info | — | S1-Teil liegt bündig an der Tischkante (0,0 mm Rand) | E4 |

## Nachgerechnete Basis

- `PYTHONPATH=core/src /opt/fgc-venv/bin/python -m roboprint run-scenario spec/scenarios/S1_modul_referenz.json --out runs/gp/S1`
  ergibt 93,5 s, machbar, 62 112 Samples, alle `warn`, d_min 10,834 mm (`nozzle_tip` ↔ `table`, Schicht 0).
  Platzierung (−500, 325) mm in S, Gier 0°.
- `python -m verify.check_run runs/gp/S1 --scenario spec/scenarios/S1_modul_referenz.json --jobs 2`:
  BESTANDEN, 0 Fehler. Max. TCP-Schritt 4,71 mm, max|Δq| 0,0049 rad, Abdeckung ≥ 99,5 %, untere Schranke d ≥ 10,011 mm.
- `python -m verify.fake_drcf runs/gp/S1`: v2 und v3 BESTANDEN.
- S3: `nicht machbar`, 68 594 von 68 933 Samples `collision`, d_min −207 mm.
- Konsistent geprüft:
  - `t_s` steigt streng monoton (min. Δt 1 ms), alle Arrays sind gleich lang.
  - J3 hat ±160° in URDF, `robots/doosan_m1013.json` und `roboprint.robot.JOINT_LIMITS`. Kleinstes q3 in S1:
    −154,9° (5,1° Reserve).
  - Der Zweig ist je Ring konstant (Druck: Zweig 6). Die Zweige 2 → 4 → 6 kommen nur im ersten Transfer aus Home
    vor.
  - Der Gierwinkel ψ ist je Druckring konstant.

## Funde

### F1 (hoch, B + C) Schichtreihenfolge ungeprüft

`check_layer_rule` (verify/oracle/run_checks.py) leitet k aus `ring_layer` ab. Es prüft aber nicht, dass die
Ringe in steigender Schicht gedruckt werden. Auch SPEC §5.2/§6 und ARTEFAKTE.md verlangen das nirgends
ausdrücklich.

- **M4:** Mini-Lauf (verify/oracle/minirun.py) mit der Druckreihenfolge Schicht [1, 1, 0, 0].
  - Schicht 1 wird in die Luft gedruckt.
  - Beim `approach` auf Schicht 0 (k = 0, also kein Druckstand) fährt die Düse 10 mm tief durch die schon
    gedruckte Schicht 1.
  - Ergebnis: `check_run` BESTANDEN, `fake_drcf` BESTANDEN.
- **Aufgabe:**
  - SPEC/ARTEFAKTE: Die Druckreihenfolge ist monoton in der Schicht, und k ist entlang der Trajektorie nicht
    fallend.
  - `check_run` prüft beides.
  - Da `spec/` und `verify/` gesperrt sind: Eintrag unter „Gate-Einwände“, Nutzerentscheidung.

### F2 (hoch, C + B) Freizone gilt auch bei Travel

SPEC §5.1 nimmt `nozzle_tip` ↔ `printed` ohne Bedingung aus, beide Seiten setzen das genau so um. Die
Freizone ist aber nur beim Druck nötig: Der TCP liegt dort auf der Oberkante von Schicht k. Bei
`lift`/`transfer`/`lower` (k = L + 1) prüft niemand, ob die Düse durch das gedruckte Material fährt.

- **M7:** Mini-Lauf, in dem der Travel zum letzten Ring 5 mm *unter* der Druckstand-Oberkante läuft. 26
  Travel-Samples haben den TCP innerhalb des Druckstands. Ergebnis: `check_run` BESTANDEN, `fake_drcf` BESTANDEN.
- **S1 selbst ist frei:**
  - Kleinster TCP-Abstand über der Druckstand-Oberkante, solange der TCP über dem Grundriss liegt: Transfer
    29,91 mm (#2167), Lift 21,67 mm, Lower 20,00 mm.
  - Reproduktion: `experiments/gegenpruefung/travel_nozzle.py`.
- **Aufgabe:**
  - SPEC §5.1: Die Freizone gilt nur für `approach`/`print`/`retract`. Bei Travel wird `nozzle_tip` ↔
    `printed` geprüft (d ≥ 0, bei Bedarf d ≥ d_hard).
  - In `roboprint.collision` und im Orakel gleich umsetzen.

### F3 (mittel, C + B) Düsenspitze gegen Glieder nicht geprüft

SPEC §5.1 prüft `nozzle_tip` nur gegen Boden und Tisch, `tool_body` gegen `base_link`…`link_4`.
`nozzle_tip` ↔ Glieder fehlt ganz, `tool_body` ↔ `link_5` ebenfalls.

- **Pose P1:** q = (0, 0, 90, 0, −145, 150)°, Teil wie S1, k = 0.
  - Orakel auf Roh-Meshes: `nozzle_tip` ↔ `link_4` d = **−6,40 mm**, die Düse steckt im Glied.
  - Orakel, Paare nach SPEC: d = 22,92 mm (`tool_body`/`link_4`).
  - roboprint `World.distance`: d = 19,04 mm (`tool_body`/`link_4`), Status **`warn`**, also zulässig für G3.
- **Gitter** q5 ∈ [−180°, 180°] (5°) × q6 (10°): 78 Posen mit `nozzle_tip` ↔ `link_4` < 0. Bei 6 davon ist das
  kleinste geprüfte Selbstkollisions-d ≥ d_hard.
- **Ausgelassene Paare in S1** (jedes 50. Sample):
  - `nozzle_tip` gegen `base_link`…`link_5`: ≥ 111 mm.
  - `tool_body` ↔ `link_5`: ≥ 60,5 mm. Dieses Paar hängt nur von q6 ab, und das Minimum über alle q6 ist 60,5 mm.
    Der Ausschluss ist also harmlos.
- **Aufgabe:** SPEC §5.1 ergänzen um `nozzle_tip` ↔ `base_link`…`link_4`. System und Orakel nachziehen.

### F4 (mittel, B) S1-Modus prüft Teil, Tisch und Präzision nicht

In `check_run.run` läuft `check_placement` nur für S2. Für Szenarien mit `source.kind = box` wird
`part.stl` nicht gegen `source.size_mm` geprüft. `check_coverage` misst nur, ob der Schalenbereich
abgedeckt ist, nicht, ob außerhalb des Teils gedruckt wird.

- **M1:** Szenario verlangt 200 × 100 × 40, der Lauf druckt 200 × 100 × 20. Ergebnis: BESTANDEN / BESTANDEN.
- **M5:** Teil bei S = (780, 300). Grundriss W x 1460…1660, **40 % neben der Tischplatte**. Ergebnis:
  BESTANDEN / BESTANDEN.
- **M6:** Dritte Schale 15 mm *außerhalb* des Teils, der Strang landet neben dem Teil. Ergebnis:
  BESTANDEN / BESTANDEN.
- **Aufgabe:**
  - G3 im Prüfer: `part.stl` = Quader aus `source.size_mm` (Volumen ± 0,5 %); Grundriss in der Tischplatte und
    kein Schnitt mit `base_link` wie in S2.
  - Kein Druck-Sample weiter als w/2 außerhalb des Teilschnitts, als Präzision neben der Abdeckung.

### F5 (mittel, B) Home-Start nicht verlangt

`fake_drcf.check_program` sucht die erste Bewegung `movej(home)` per `_match` in der Trajektorie. Findet es
sie nicht, bleibt `idx[0] = None`, und es gibt **keinen Fehler**. `check_run` prüft den Start nicht.

- **M3:** Die 652 Transfer-Samples aus Home werden entfernt. Die Trajektorie beginnt bei
  q = (−117,1; 36,7; 109,8; 66,9; 104,6; −149,5)°. Das DRL fährt weiter `movej(home)` und danach `movej(Start)`.
  Diese Bewegung (J1 117°) ist in keinem Sample enthalten. Ergebnis: BESTANDEN / BESTANDEN.
- **Echter Lauf S1:** Sample 0 ist Home. Der Fund betrifft also nur den Prüfer.
- **Aufgabe:** `fake_drcf` verlangt, dass `movej(home)` auf Sample 0 fällt. `check_run` verlangt q[0] = Home.

### F6 (niedrig, B) Abstandswerte und Paar nicht gegengeprüft

`check_status` vergleicht nur das Statusband (`warn`/`ok`/`collision`). `d_mm`, `pair` und `witness` werden
gegen den Prüfer nicht verglichen; summary.parts.d_min/n_collision nur teilweise.

- **M2:** Auf allen `warn`-Samples steht `d_mm = 49`, `pair = (link_6, floor)` und `witness = 0`. Ergebnis:
  BESTANDEN / BESTANDEN.
- **Folge:** Viewer (G6) und Ursache-Meldung würden ein falsches Glied und Hindernis zeigen.
- **Aufgabe:** Auf einer Stichprobe prüfen:
  - d_rp ∈ [d − 12, d + 1] mm.
  - `pair` ist das Paar mit dem kleinsten d (oder liegt innerhalb der Toleranz daran).
  - Die Zeugenpunkte liegen auf den Oberflächen.

### F7 (niedrig, C) Zwischen Samples wird nicht geprüft

G3 verlangt d ≥ d_hard nur auf den Samples. Ein Körperpunkt bewegt sich zwischen zwei Samples in S1 um bis zu
**5,28 mm** (Hüllkugel-Odometer). d kann also theoretisch um ~2,6 mm fallen, das ist mehr als die Reserve
in Schicht 0 (Orakel 11,85 mm).

- **Nachrechnung:** Alle 1464 Schritte, deren grobe Schranke unter d_hard liegt, an je 3 Zwischenstellungen
  (Orakel, gelenklinear; Abweichung von der kartesischen Geraden ≤ 0,002 mm).
  - Kleinstes d zwischen Samples: **11,852 mm** (#1082).
  - Größter Abfall gegenüber den Enden: **0,001 mm**.
- **Ergebnis:** S1 ist auch zwischen den Samples frei.
- **Aufgabe:** SPEC: d_hard gilt für die Bewegung. Dazu genügt eine Schranke d_i − Verschiebung/2 je Schritt, und
  nur kritische Schritte werden nachgerechnet.

### F8 (niedrig, C) Reserve in Schicht 0 ist strukturell

- Das Werkzeugmesh endet entlang +Z_T bei z_T = **−1,85 mm**, also 1,85 mm vor dem TCP (Spitzenradius ~3,1 mm).
  Beim Druck von Schicht 0 steht der TCP h über dem Tisch.
- d(`nozzle_tip` ↔ `table`) = h + 1,85 mm: Orakel 11,85 mm, roboprint 10,83 mm (≈ 1 mm konservativ).
- **Folge:**
  - Mit h ≤ 8,1 mm (Annahme A in §10) ist jedes Teil per Konstruktion `nicht machbar`.
  - d_hard gegen den Tisch ist für die Düse kein Sicherheitsabstand, sondern eine Mindest-Schichthöhe.
- **Aufgabe (Nutzer):**
  - Düse ↔ Tisch: eigene Schwelle (z. B. ≥ 0 oder ≥ h/2), statt d_hard.
  - TCP-Lage gegenüber der Düsenöffnung (1,85 mm) bestätigen.

### F9 (niedrig, A für die Zeitachse) `timing` ≠ DRL-Geschwindigkeit

| Bewegung | Zeitachse (`trajectory.json`) | DRL |
|---|---|---|
| An- und Abfahrt | v_travel, bis 134 mm/s | ohne `vel`, also `set_velx(100)` |
| Abheben, Absenken | ≤ 90,8 mm/s | `vel=[250, 90]` |
| Transfer aus Home | TCP-Spitze 907 mm/s | `movej` mit 30 % der Gelenkgrenzen |
| Transfer zwischen Ringen | ≤ 292 mm/s | `movej` mit 30 % der Gelenkgrenzen |

Für den Transfer aus Home ist der TCP-Wert konsistent mit 30 % der Gelenkgrenzen, liegt aber weit über
v_travel 250 mm/s.

- **Folge:** Die Druckzeitschätzung und die Viewer-Uhr bilden das Gerät nicht exakt ab. Das ist kein Gate-Fehler.
- **Reproduktion:** `experiments/gegenpruefung/timing_psi.py`.
- **Aufgabe:** `timing` übernimmt dieselben Geschwindigkeiten wie der DRL-Emitter, aus einer Quelle.

### F10 (Info) S1 liegt an der Tischkante

- Grundriss in W: x −20…580. Die Tischplatte beginnt bei x = −20, der Rand ist also 0,0 mm.
- `check_placement` (S2-Regel, Toleranz 0,5 mm) besteht.
- Die SPEC verlangt keinen Rand. Der Nutzer sollte entscheiden, ob ein Mindestabstand zur Kante gelten soll.

### Bereits bekannt, bestätigt

Blending r_blend = 2 mm gegen 0,5 mm Bahntoleranz (PROGRESS, Gate-Einwand). Das DRL setzt `radius=2` an allen
Ecken, außer am Ringende.

### Nicht bestätigt: Statusfehler in S3

`check_run` prüft in S3 nur die als `collision` gemeldeten Samples. Nachgerechnet habe ich 404 Samples: den
Statuswechsel ±3 sowie 300 Zufalls-Samples aus `warn` und 100 aus `collision`.

- Eine Abweichung: #339 `transfer`, roboprint −0,79 mm, Orakel +0,61 mm (`link_3`/`table`).
- Diese Abweichung ist konservativ und nach der G2-Regel erlaubt (|d| < 12 mm).
- Ergebnis: kein falsch-freies Sample.

## Reproduktion

Alle Befehle aus der Repo-Wurzel; Läufe unter `runs/gp/` (gitignored).

| Beleg | Befehl | Laufzeit |
|---|---|---|
| Basis | `PYTHONPATH=core/src /opt/fgc-venv/bin/python -m roboprint run-scenario spec/scenarios/S1_modul_referenz.json --out runs/gp/S1` (S3 analog), dann `check_run` / `fake_drcf` wie oben | ~95 s |
| M1–M7 | `/opt/fgc-venv/bin/python -m experiments.gegenpruefung.manipulationen runs/gp/manip` | ~3 min |
| E1 (F7) | `/opt/fgc-venv/bin/python -m experiments.gegenpruefung.between_samples runs/gp/S1 --all --fractions 5` | ~6 min |
| P1, Gitter (F3) | `PYTHONPATH=core/src /opt/fgc-venv/bin/python -m experiments.gegenpruefung.nozzle_link4_pose` und `… -m experiments.gegenpruefung.unchecked_pairs runs/gp/S1 --every 50` | ~1 / ~6 min |
| F2 | `/opt/fgc-venv/bin/python experiments/gegenpruefung/travel_nozzle.py runs/gp/S1/parts/box_01` | s |
| E3 (F9) | `/opt/fgc-venv/bin/python -m experiments.gegenpruefung.timing_psi runs/gp/S1` | s |
| E4 (F10) | `/opt/fgc-venv/bin/python -m experiments.gegenpruefung.placement_s1 runs/gp/S1` | s |
| S3-Status | `/opt/fgc-venv/bin/python -m experiments.gegenpruefung.s3_status runs/gp/S3 --n 300` | ~1 min |

E2 (F8): Werkzeugmesh über `mesh_transform` in F, dann mit T_FT⁻¹ in T; max z_T = −1,853 mm (siehe Text).

## Vorgeschlagene Aufgaben

1. **Gate-Einwand (Nutzer):** In SPEC §5.1 und §11 aufnehmen:
   - Freizone nur beim Druck (F2).
   - Paar `nozzle_tip` ↔ `base_link`…`link_4` (F3).
   - Monotone Schichtreihenfolge (F1).
   - Prüfung der Bewegung zwischen den Samples (F7).
   - Eigene Schwelle Düse ↔ Tisch (F8).
2. **Prüfer-Härtung (nach Freigabe, verify/ ist gesperrt):**
   - Schichtreihenfolge und k monoton (F1).
   - Teil = Szenario-Quader, Tisch und Basis auch für S1/S3, Präzision der Druckbahn (F4).
   - Home-Start in `check_run` und `fake_drcf` (F5).
   - Stichprobe für d_mm, pair und witness (F6).
   - Jede Manipulation M1–M7 als Selbsttest in `verify/oracle/selftest_check_run.py` aufnehmen.
3. **System:**
   - `roboprint.collision` und Planer um die neuen Paare und die Travel-Regel erweitern, sobald die SPEC es
     verlangt (F2, F3).
   - `timing` aus derselben Geschwindigkeitsquelle wie `drl` speisen (F9).
   - Optional: Mindestrand zur Tischkante in der Platzierungssuche (F10).
