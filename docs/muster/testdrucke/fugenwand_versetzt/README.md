# Testdruck fugenwand_versetzt: Fugenwand mit Gurt, Rückseite versetzt

Testkörper 600 × 200 × 100 mm (10 Schichten zu 10 mm), Standard-Druckplatz (0, −50) mm, lange Seite zum Roboter. Szenario: `scenario.json`; erzeugt mit `python scripts/muster_testdrucke.py --only fugenwand_versetzt`.

Gurtvariante; Hakenradius auf 200 mm Wand verkleinert (M6-Warnung).

**Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck** (ohne Material, `change_operation_speed` 10 … 20 %).

![Schicht 0, Folgeschicht blass](schicht0.svg)

Bild: Vorschau des Musterkerns für diesen Querschnitt (Schicht 0, Schicht 1 blass; Kreis = Start, Quadrat = Ende).

| Kennzahl | Wert |
|---|---|
| Programme | `program.v2.drl` (Firmware 2.x), `program.v3.drl` |
| Druckzeit gesamt | 6,0 min (361 s, mit Anfahrt) |
| davon Pumpe an | 358 s (+ 3 s Vorlauf je Strang) |
| Pfadlänge | 35,33 m (alle Schichten, mit Verbindern) |
| Material | 10,6 l (Annahme, siehe unten) |
| Stränge je Schicht | 1 (gesamt 1) |
| senkrechte Schichtwechsel | 9 von 9 (100 %) |
| d_min | 10,8 mm (d_hard = 10 mm) |
| Ringe / Samples | 130 / 13244 |
| Planerlaufzeit | 33,8 s |

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
   A Muster-Preset             docs/muster/presets/fugenwand_versetzt.json
```

## Beobachten

Kleine Haken (Radius < w): sauber oder verschmiert? Gurt in der Wandmitte haftet an den Knoten; Fugen reißen zuerst.

## Prüfstatus

Stand 2026-10-20, Lauf `runs/muster_testdrucke/testdruck_fugenwand_versetzt`:

- Planer: machbar (box_01 machbar), 0 collision, 0 unreachable
- G3 `python -m verify.check_run`: grün außer Abdeckung (Einwand, min. 88,1 %; Gate-Einwand 1 in MUSTER-PROGRESS.md)
- G5 `python -m verify.fake_drcf`: v2 und v3 akzeptiert
- M1–M7 `python -m verify_muster.check`: grün (Warnungen: M6 10)
