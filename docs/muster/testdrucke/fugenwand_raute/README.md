# Testdruck fugenwand_raute: Fugenwand, Rautenkette (empfohlen)

Testkörper 600 × 200 × 100 mm (10 Schichten zu 10 mm), Standard-Druckplatz (0, −50) mm, lange Seite zum Roboter. Szenario: `scenario.json`; erzeugt mit `python scripts/muster_testdrucke.py --only fugenwand_raute`.

Empfohlenes Muster des Nachtrags 18:20: Sollbruchstellen ohne Gurt, Rückseite versetzt.

**Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck** (ohne Material, `change_operation_speed` 10 … 20 %).

![Schicht 0, Folgeschicht blass](schicht0.svg)

Bild: Vorschau des Musterkerns für diesen Querschnitt (Schicht 0, Schicht 1 blass; Kreis = Start, Quadrat = Ende).

| Kennzahl | Wert |
|---|---|
| Programme | `program.v2.drl` (Firmware 2.x), `program.v3.drl` |
| Druckzeit gesamt | 4,2 min (253 s: Zeitmodell des Planers ab Home mit Anfahrt und Abheben, plus 3 s Pumpen-Vorlauf je Strang) |
| davon Pumpe an | 246 s (Drucken und Verbinder, ohne Vorlauf) |
| Pfadlänge | 24,29 m (alle Schichten, mit Verbindern) |
| Material | 7,3 l (Annahme, siehe unten) |
| Stränge je Schicht | 1 (gesamt 1) |
| senkrechte Schichtwechsel | 9 von 9 (100 %) |
| d_min | 10,8 mm (d_hard = 10 mm) |
| Ringe / Samples | 70 / 9800 |
| Planerlaufzeit | 23,2 s |

Materialannahme (A): Raupenquerschnitt rechteckig w × h = 30 × 10 mm, mal Pfadlänge der Mittellinie (Ringe plus Verbinder). Überlappung an Kontakten, Ecken und Schwinden sind nicht abgezogen; Vorlauf t_tot und Anfahrmaterial nicht eingerechnet.

## Provisorische Werte (A) aus dem DRL-Kopf

```
   A Schichthoehe h            10.0 mm
   A Strangbreite w            30.0 mm
   A v_print                   100.0 mm/s, 60.0 deg/s (acc 500.0 mm/s2, 120.0 deg/s2)
   A v_travel                  250.0 mm/s, 90.0 deg/s (acc 1000.0 mm/s2, 180.0 deg/s2)
   A Gelenke                   30 % der Grenzen: [36.0, 36.0, 54.0, 67.5, 67.5, 67.5] deg/s, acc = 4 x vel
   A z_lift                    30.0 mm ueber Druckstand-Oberkante
   A An- und Abfahrt           senkrecht 20.0 mm
   A V_pump                    5.0 V konstant auf AO 1 (pump_a)
   A t_tot                     3.0 s Pumpen-Vorlauf am Strangbeginn (provisorisch)
   N link_max_mm               60.0 mm, laengster Verbinder (0 = aus)
   A r_blend                   min(2.0 mm, 1/2 Segmentlaenge)
   A d_hard                    10.0 mm
   A tau_max                   0.0 deg
   A tcp_name                  FGC_30GUT (am Teach Pendant anlegen: tools/30gut.json,
                               Position (134, 0, 73) mm, 90 deg um Flansch-Y)
   A Dialekt                   v2 (Firmware am Teach Pendant pruefen)
   A Schichtfolge              alternate (Druckmuster, opt-in)
   A Muster                    Infill none, Outfill fugenwand
   A Muster-Preset             docs/muster/presets/fugenwand_raute.json
```

## Beobachten

Fugen: Haken berühren sich, laufen aber nicht ineinander; nach dem Trocknen reißen Fugen statt Felder. Knoten der Rauten in der Wandmitte haften. Haken sauber gerundet.

## Prüfstatus

Stand 2026-10-20, Lauf `runs/muster_testdrucke/testdruck_fugenwand_raute`:

- Planer: machbar (box_01 machbar), 0 collision, 0 unreachable
- G3 `python -m verify.check_run`: grün außer Abdeckung (min. 64,6 % < 95 %; Gate-Einwand 1 in MUSTER-PROGRESS.md)
- G5 `python -m verify.fake_drcf`: v2 und v3 akzeptiert
- M1–M7 `python -m verify_muster.check`: grün (Warnungen: M6 10)
