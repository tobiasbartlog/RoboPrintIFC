# S2 mit Rautenkette (Szenario S6)

Stand 21.10.2026, Nachtlauf „Druckmuster“. Szenario `docs/muster/szenarien/S6_muster_s2_raute.json`:
wie S2 (alle Wände aus `examples/Building-Architecture.ifc`, Modus Modul, Zerlegung an), dazu das
empfohlene Muster Rautenkette (Preset `fugenwand_raute`, `MUSTERKATALOG.md` „Empfehlung“) mit
`pattern_params = {"field_length_mm": 225}`. Gerechnet mit `--jobs 2` auf der Cloud-VM (4 vCPU, andere
Agenten liefen parallel). Geprüft mit `verify.check_run` (G3), `verify.fake_drcf` (G5) und
`verify_muster.check` (M1–M7) über `scripts/verify_muster.py`. **E** = gerechnet oder gemessen, **A** = Annahme.

## Kurzfassung

Nachtrag 21.10.2026 (Fix „Fugenwand an Abschrägungen“, Branch `v2/muster-fugenschraege`): Die Kopfmodule
planen die Fugenwand jetzt aus dem Vollquerschnitt, darüber fallen Raupen nur weg (`fugenwand.md`,
Abschnitt „Abschrägung“). Die Zahlen unten stammen aus dem neuen Lauf; die Tabellen „vor dem Fix“ sind
als Beleg stehen geblieben.

- **Roboterseitig ist alles machbar (E):** 172 von 172 Teilen `machbar`, d_min 10,83 mm (wie S2),
  Orakel d_min_lb 10,0 mm, 0 Kollisionen, 0 Zweigwechsel im Strang. G5 (fake_drcf): 0 Fehler.
- **Muster: M2–M7 in allen 172 Teilen grün (E, `verify_muster`).** 1 Strang je gedruckter Schicht,
  100 % senkrechte Schichtwechsel, Überhang 0 mm², keine unvollständige Schicht. Die 152 Module mit
  vollem Querschnitt sind unverändert (3 Felder à 200 mm). Die 20 Kopfmodule (45°-Schräge,
  left/front r9: 13, back r5: 7; früher hier als 22 gezählt) haben Fugen und Rauten an der Schrägseite in
  den Lagen der Module darunter bis zur letzten Vollschicht, darüber die U-Formen der Gegenseite.
- **Rot bleibt nur M1 in den 20 Kopfmodulen (physikalisch):** Ihre drei obersten Schichten sind 20,7 /
  10,7 / 0,7 mm dick, dünner als eine Raupe (w = 30 mm passt nicht in den Querschnitt ⊕ 1 mm, M5). Dort
  ist nichts druckbar; das Orakel meldet „Insel ohne Strang“, die G3-Abdeckung dieser Schichten ist 0 %.
  S2 ohne Muster druckt dort einen Ring, der über den Querschnitt hinausragt.
- **Musterrunner:** S6 bleibt „belegt nicht machbar“, jetzt mit `erwartete_regeln` = M1 (vorher M1, M2,
  M3, M4, M6). `machbar = true` geht erst mit einer Regel für Schichten dünner als w (SPEC-Nachtrag) oder
  einer Zerlegung, die den Kopf anders schneidet.
- **Laufzeit (E):** run-scenario 611 s (Last durch andere Agenten und parallele Tests; vorher 217–267 s),
  Grenze G7 1800 s. Prüfung: check_run 166–179 s, fake_drcf 40–66 s, verify_muster 359 s.
- **Material/Druckzeit (E):** Druckzeit Summe 168 287 s (vorher 171 598 s, S2 ohne Muster 174 379 s).
  Kopfmodul left/front r9 436,9 s, back r5 515,7 s (vorher 600,7 / 684,5 s, S2 702,3 / 786,5 s): Die
  Schrägschichten drucken nur die U-Formen der Gegenseite.

## Wahl der Feldlänge (Begründung)

Die Zerlegung schneidet alle Wände von S2 in **600 mm lange Module** (Dicke 200 mm). `fit_to_length`
rundet die Felderzahl: `round(600 / Ziel)`.

| Ziel-Feldlänge | Felder × Ist | Hakenradius | M6-Warnpunkte (Kern) | Pfad je Schicht | Stegwinkel |
|---|---|---|---|---|---|
| 250 mm | round(2,4) = 2 × **300 mm** | 27 mm (30 passt nicht) | 60 (E) | 2420 mm | 30,6° / 40,9° |
| **225 mm** | round(2,67) = 3 × **200 mm** | **30 mm** | **0** (E) | 2781 mm | 62,5° / 78,1° |

Das 250-mm-Ziel der Aufgabe ist bei 600-mm-Modulen **nicht** warnungsfrei: es ergibt 300-mm-Felder,
bei denen der Fugenhaken in der 200-mm-Wand nur mit r = 27 mm passt (`PARAMETERSTUDIE.md`, Weiche 3;
`studie/fugenwand.csv`, Zeile 600/200/250). Die Tabelle der Parameterstudie nennt für Modul 600 mm
„225…250 mm → 200 mm“; das gilt nur bis zum Ziel 239 mm. Gewählt ist deshalb **225 mm → 200 mm**:
0 Warnungen, r = w, Fugenabstand innerhalb der Kennzahl-Grenze 300 mm. Preis: 15 % mehr Pfad als
mit 300-mm-Feldern (2781 gegen 2420 mm je Schicht).

## Wände und Module

| Wand | Länge × Höhe | Module | Teile | Ergebnis |
|---|---|---|---|---|
| house left | 6000 × 3626 mm | 10 Spalten × 10 Reihen | 100 | r0–r8 (90) grün; r9 (10, Kopf) nur M1 rot (3 Schichten < w) |
| house right front | 1800 × 3626 mm | 3 × 10 | 30 | r0–r8 (27) grün; r9 (3, Kopf) nur M1 rot |
| house right back | 4200 × 2226 mm | 7 × 6 | 42 | r0–r4 (35) grün; r5 (7, Kopf) nur M1 rot |
| plumbing wall | 3800 × 2226 mm, 24 mm dick | – | 0 | ungeeignet: 24 mm < 60 mm (2·w), wie S2 |

Die Teile sind inhaltsgleich zu vier Vertretern (`same_as`); die Zahlen gelten je Vertreter für alle
Teile seiner Gruppe. Material = Pfadlänge aller Ringe; S2 = derselbe Teil ohne Muster.

**Kopfmodule nach dem Fix (E, Lauf `runs/verify_muster/S6_muster_s2_raute`):**

| Kennzahl | Kopf 296 (left/front r9) | Kopf 326 (back r5) |
|---|---|---|
| M1–M7 (Orakel) | M2–M7 grün; M1 rot: 3 leere Schichten (27–29, Dicke < w) | M2–M7 grün; M1 rot: Schichten 30–32 |
| Stränge je Schicht / je Teil | 1 / 27 (eine je gedruckter Schicht) | 1 / 30 |
| Senkrechte Schichtwechsel | 26 / 26 (100 %), 12 Nähte an einer Fläche (Warnung) | 29 / 29 (100 %) |
| Überhang / fehlende Raupe bei gleichem Querschnitt | 0 / 0 mm² | 0 / 0 mm² |
| Vollschichten mit Fugenwand | 0–9: Fugen y+ bei x = −200, 0, 200 mm (wie darunter), Rauten r = 27 mm, y− zwei Spuren ohne Fuge | 0–12 |
| Schrägschichten | 10–25: U-Formen (Doppel-U bis 104 mm Dicke, dann einfaches U, ab 59 mm ein Lauf) | 13–28 |
| M6 (Orakel) | kleinster Radius 14,5 mm (Wende r = w/2, in Toleranz), 24 Pfade unter Ziel | wie links |
| Kontaktzonen je m (M7, Schicht 0) | 7,6 (Fuge 1,7, Schale 5,9) | wie links |
| Druckzeit je Teil (S6 / S2) | 436,9 / 702,3 s | 515,7 / 786,5 s |
| Hinweise im Toolpath | Kopfmodul (Schichten 0–9), Abschrägung (10–25), „Schichten 27–29 ohne Strang: Dicke 20,7…0,7 mm, dünner als eine Raupe“ | entsprechend |

**Vor dem Fix (prismatische Fugenwand, Beleg):**

| Kennzahl | Voll 370 (left/front r0–r8) | Voll 380 (back r0–r4) | Kopf 296 (left/front r9) | Kopf 326 (back r5) |
|---|---|---|---|---|
| Teile | 117 | 35 | 13 | 7 |
| Maße (L × D × H) | 600 × 200 × 370 mm, 37 Schichten | 600 × 200 × 380 mm, 38 Schichten | 600 × 200 × 295,7 mm, 30 Schichten | 600 × 200 × 325,7 mm, 33 Schichten |
| Roboter machbar / d_min | ja / 10,83 mm | ja / 10,83 mm | ja / 10,83 mm | ja / 10,83 mm |
| M1–M7 | grün | grün | **rot**: M1 3, M2 3, M3 16, M4 17, M6 3 Verstöße | **rot**: M1 3, M2 3, M3 16, M4 17, M6 3 |
| G3 (ohne Abdeckung) / Abdeckung min. | grün / 71,9 % (Einwand 1) | grün / 71,9 % (Einwand 1) | **rot** / 0 % (Schichten 27–29 leer) | **rot** / 0 % (Schichten 30–32 leer) |
| Stränge je Schicht / je Teil | 1 / 1 | 1 / 1 | 1 / 5 | 1 / 5 |
| Senkrechte Schichtwechsel (≤ 0,5 mm) | 36 / 36 (100 %) | 37 / 37 (100 %) | 9 / 26 (35 %) | 12 / 29 (41 %) |
| Fugen je Schicht (Seite y+ / y−) | 2 / 3 | 2 / 3 | 2 / 3 bis Schicht 17, darüber keine | 2 / 3 bis Schicht 20, darüber keine |
| Feldlänge Ist | 3 × 200,0 mm | 3 × 200,0 mm | 200 mm, Haken r 30 → 15 mm | 200 mm, Haken r 30 → 15 mm |
| Kontaktzonen je m (M7) | 23,3 (386 mm/m) | 23,3 (386 mm/m) | 14,2 | 15,1 |
| Druckzeit je Teil (S6 / S2) | 1039,6 / 1044,5 s | 1067,5 / 1072,5 s | 600,7 / 702,3 s | 684,5 / 786,5 s |
| Material relativ zu S2-Schalen | 1,022 | 1,022 | 0,845 | 0,864 |
| Planerlaufzeit (S6 / S2) | in der Zerlegung (Scan 147 / 76 s für alle vollen Module) | wie links | 90,9 / 61,7 s | 94,7 / 70,1 s |

**Lage der Fugen (E, Frame P, x = 0 Modulmitte, Stöße bei x = ±300 mm):** Seite y+ x = −100 und +100 mm,
Seite y− x = −200, 0, +200 mm (um F/2 versetzt), Rautenknoten in der Wandmitte bei x = ±50, ±150 mm.
Über die Modulreihe gesehen liegen die Fugen der Seite y+ mit dem Stoß in einem durchgehenden
200-mm-Raster (… 100 | **300 = Stoß** | 500 …). Auf der Seite y− fällt der Stoß in die Mitte eines
Feldes (Fugen bei 200 und 400, Stoß bei 300): dort entstehen zwei 100-mm-Felder. Der Stoß wirkt als
zusätzliche Fuge; die Endkappe ist 110 mm lang. In der Höhe liegen die Fugen aller Modulreihen
übereinander (gleiches Muster in jedem Modul), die Fugenlinie läuft also über die ganze Wandhöhe
bis in das Kopfmodul. Naht (M4) bei (32,1 / −19,2) mm im Wandinneren auf einem Steg, keine Naht an
Sicht- oder Stoßfläche (`n_seam_on_surface = 0`).

**Orakel-M6-Warnungen in den vollen Modulen (E):** 1 je Schicht, kleinster Radius 26,84 mm (Ziel 30,
hart 15). Der Kern misst auf seiner Sollkurve 0 Warnungen; das Orakel sieht die Polylinie nach dem
Resampling des Slicers (`step_mm = 20`). Kein Fehler, nur Hinweis.

## Kopfmodule: Ursache (vor dem Fix)

Die 20 Kopfmodule tragen die 45°-Schräge des Wandkopfs. Ihr Querschnitt bleibt 600 mm lang, die Dicke
nimmt ab Schicht 10 (left/front r9) bzw. 13 (back r5) je Schicht um 10 mm ab (200 → 190,7 → … → 0,7 mm). Eine
Laibung gibt es nicht (S2 enthält keine Öffnungen, `topologie.md`).

Ablauf im Kern (E, aus `toolpath.pattern.notes` und Nachrechnung mit `plan_pattern`):

| Dicke | Schichten (r9) | Verhalten der Fugenwand | Folge |
|---|---|---|---|
| 200 mm | 0–9 | 3 × 200 mm, r = 30 mm | grün |
| 190,7…120,7 mm | 10–17 | neu eingeteilt je Schicht, Hakenradius 30 → 27 → 24 → 21 → 18 → 15 mm | Geometrie wandert: M3-Überhang bis 4279 mm² je Schicht, M4 nicht senkrecht (6…116 mm), 187 M6-Warnpunkte |
| 110,7…30,7 mm | 18–26 | „Fugenwand nicht baubar: keine Tangente zwischen Kreisen … Abstand 39…49 mm < 60 mm“ → Grundmuster Schalen, nur 1 Schale (18–20: zwei Schalen hätten 4 Regelfehler; ab 21 passt Schale 2 nicht) | Naht wandert mit der Schräge (M4 14,1 mm = 10·√2), M2 Kreuzung 0,74 mm, M6 r = 6,7 mm, Strang abgesetzt (5 Stränge je Teil) |
| 20,7…0,7 mm | 27–29 | keine Bahn (Schale passt nicht, < w) | M1: Insel ohne Strang, G3-Abdeckung 0 % (S2 ohne Muster druckt hier je einen Ring) |

Roboterseitig sind diese Teile trotzdem machbar (d_min 10,83 mm, 0 Kollisionen); der Fehler liegt
allein im Schichtpfad.

## Fund: Kopfmodule brauchen die Abschrägungslösung (umgesetzt, siehe oben)

Gegenprobe (E): dieselben Querschnitte der beiden Kopf-Vertreter mit dem Muster `topologie`
(Fall `abschraegung`, Fermat-Doppelring ab Schicht 0, Raupen fallen nur weg, wandern nicht):

| Vertreter | Rautenkette (Kern-`measure`) | topologie (Kern-`measure`) | Pfad topologie / S2 |
|---|---|---|---|
| left/front r9 | M2 4, M3 16, M4 17, M6 6 Fehler; 187 Warnungen | **0 Fehler**; Warnungen M6 36, M4 26, M1 3 | 0,62 |
| back r5 | wie links | **0 Fehler**; Warnungen M6 44, M4 24, M1 3 | 0,68 |

Umgesetzt am 21.10.2026 als Variante „Raupen fallen nur weg“ (`fugenwand.md`, Abschnitt „Abschrägung“).
Abweichung vom Vorschlag: Die Fugen der Gegenseite können nicht durchlaufen (eine Kerbe schließt nach oben
nie, die obersten Schichten brauchen einen durchgehenden Lauf; Überhang 644 mm² je Fuge), deshalb hat die
Gegenseite im Kopfmodul keine Fuge. Ursprünglicher Vorschlag: Die prismatische Fugenwand erkennt einen
Teil mit veränderlichem Querschnitt (Schräge) aus `sections` und plant dann den ganzen Teil mit der
Abschrägungslösung von `topologie`, statt je Schicht neu einzuteilen. Besser für die Optik: eine
Fugenwand-Variante nach dem Prinzip „Raupen fallen nur weg“, also die Einteilung des Vollquerschnitts
für alle Schichten festhalten, die Rauten an der Schrägseite als U-Formen am Knoten enden lassen und
die Fugen der Gegenseite durchlaufen lassen. Offen bleiben in beiden Fällen die drei obersten
Schichten unter w = 30 mm Dicke (auch topologie druckt dort nichts; S2 ohne Muster druckt einen
Ring auf weniger als einer Raupenbreite). Das betrifft G3 (Abdeckung) und gehört als Regel in den
SPEC-Nachtrag (Schichten dünner als w an der Schräge).

## Laufzeit gegen S2 (Lauf vor dem Fix; neuer Lauf siehe Kurzfassung)

| | S2 ohne Muster | S6 Rautenkette |
|---|---|---|
| run-scenario (Wanduhr, `--jobs 2`) | 170 s | 218 s (erster Lauf), 267 s (Runner, parallel zu anderen Agenten) |
| davon Zerlegung | 150,7 s (Scan 76,5 s) | 202,5 s bzw. 247,4 s (Scan 147,3 s) |
| Planer Kopf-Vertreter (Summe) | 131,8 s | 185,6 s |
| Teile machbar | 172 | 172 |
| Stränge gesamt | 172 | 252 (Kopfmodule je 5) |
| Senkrechte Schichtwechsel | 100 / 6108 (1,6 %) | 5708 / 6048 (94,4 %) |
| Druckzeit Summe | 174 379 s | 171 598 s |
| Pfad gesamt | 16,80 km | 16,94 km (1,008) |

Die Musterplanung verdoppelt den Scan der vollen Module (mehr Wegpunkte: 1,44 Mio. gegen 0,88 Mio.),
bleibt aber bei 12…15 % der G7-Grenze.

## Neu rechnen

    python scripts/verify_muster.py --scenario S6_muster_s2_raute --jobs 2
    python -m roboprint run-scenario spec/scenarios/S2_beispiel_ifc_modul.json --out runs/verify_muster/S2_ohne_muster --jobs 2

Laufordner `runs/verify_muster/S6_muster_s2_raute` (Prüferberichte `check.json`, `check_muster.json`,
Logs unter `runs/verify_muster/logs/`).
