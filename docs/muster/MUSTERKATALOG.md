# Musterkatalog

Vergleich der Druckmuster (Infill und Outfill) für Wandmodule. Alle Zahlen stammen aus der
2D-Vorschau (`roboprint.patterns.preview`, Schicht 0, Strangbreite 30 mm, Schichthöhe 10 mm,
100 mm/s) und gelten für prismatische Querschnitte. Die Roboterspalten (Erreichbarkeit,
Kollisionsabstand, Planerlaufzeit) kommen aus dem Musterlauf `scripts/verify_muster.py`.

Neu erzeugen: `python scripts/muster_katalog.py`. Nur der Text zwischen den Markern wird
überschrieben.

<!-- KATALOG:VERGLEICH:BEGIN -->
## Vergleich

Material je m relativ zu „schalen“ (zwei Schalen ohne Infill = 1,00). Zeit und Pfad je Schicht. Die Spalte „Roboter machbar“ kommt aus `runs/verify_muster/report.json` (sonst „offen“).

**600x200 mm** (Schicht 0)

| Muster | Status | Pfad mm | Zeit s | Material rel. | Kontakte/m | Zelle mm | gerade Außen mm | R min mm | Roboter machbar |
|---|---|---|---|---|---|---|---|---|---|
| [schalen](#schalen) | ok | 2552 | 25,5 | 1,00 | 8,3 | 509 | 510 | 30,0 | offen |
| [fugenwand](#fugenwand) | ok, 30 Warn. | 2420 | 24,2 | 0,95 | 13,3 | 140 | 110 | 27,0 | offen |
| [fugenwand_foto](#fugenwand_foto) | ok, 16 Warn. | 3540 | 35,4 | 1,39 | 23,3 | 481 | 220 | 20,0 | offen |
| [fugenwand_gurt](#fugenwand_gurt) | ok, 16 Warn. | 3550 | 35,5 | 1,39 | 43,3 | 182 | 170 | 21,0 | offen |
| [fugenwand_raute](#fugenwand_raute) | ok, 30 Warn. | 2420 | 24,2 | 0,95 | 13,3 | 140 | 110 | 27,0 | offen |
| [fugenwand_versetzt](#fugenwand_versetzt) | ok, 24 Warn. | 3533 | 35,3 | 1,38 | 60,0 | 182 | 170 | 21,0 | offen |
| [maeander](#maeander) | ok, 16 Warn. | 3160 | 31,6 | 1,24 | 16,7 | 145 | 510 | 26,5 | offen |
| [sinus](#sinus) | ok | 3097 | 31,0 | 1,21 | 16,7 | 195 | 510 | 30,0 | offen |
| [trapez](#trapez) | ok | 3119 | 31,2 | 1,22 | 16,7 | 167 | 510 | 30,0 | offen |
| [zickzack](#zickzack) | ok | 3093 | 30,9 | 1,21 | 16,7 | 199 | 510 | 29,9 | offen |

**1000x200 mm** (Schicht 0)

| Muster | Status | Pfad mm | Zeit s | Material rel. | Kontakte/m | Zelle mm | gerade Außen mm | R min mm | Roboter machbar |
|---|---|---|---|---|---|---|---|---|---|
| [schalen](#schalen) | ok | 4152 | 41,5 | 1,00 | 5,0 | 909 | 910 | 30,0 | offen |
| [fugenwand](#fugenwand) | ok, 50 Warn. | 4024 | 40,2 | 0,97 | 14,0 | 140 | 114 | 27,0 | offen |
| [fugenwand_foto](#fugenwand_foto) | ok, 48 Warn. | 5841 | 58,4 | 1,41 | 36,0 | 286 | 181 | 20,0 | offen |
| [fugenwand_gurt](#fugenwand_gurt) | ok, 32 Warn. | 5909 | 59,1 | 1,42 | 50,0 | 212 | 198 | 21,0 | offen |
| [fugenwand_raute](#fugenwand_raute) | ok, 50 Warn. | 4024 | 40,2 | 0,97 | 14,0 | 140 | 114 | 27,0 | offen |
| [fugenwand_versetzt](#fugenwand_versetzt) | ok, 40 Warn. | 5891 | 58,9 | 1,42 | 58,0 | 212 | 198 | 21,0 | offen |
| [maeander](#maeander) | ok, 28 Warn. | 5249 | 52,5 | 1,26 | 13,0 | 154 | 910 | 26,5 | offen |
| [sinus](#sinus) | ok | 5133 | 51,3 | 1,24 | 13,0 | 214 | 910 | 30,0 | offen |
| [trapez](#trapez) | ok | 5165 | 51,6 | 1,24 | 13,0 | 184 | 910 | 30,0 | offen |
| [zickzack](#zickzack) | ok | 5124 | 51,2 | 1,23 | 13,0 | 219 | 910 | 30,0 | offen |

**1000x300 mm** (Schicht 0)

| Muster | Status | Pfad mm | Zeit s | Material rel. | Kontakte/m | Zelle mm | gerade Außen mm | R min mm | Roboter machbar |
|---|---|---|---|---|---|---|---|---|---|
| [schalen](#schalen) | ok | 4552 | 45,5 | 1,00 | 5,0 | 909 | 910 | 30,0 | offen |
| [fugenwand](#fugenwand) | ok | 4968 | 49,7 | 1,09 | 14,0 | 240 | 210 | 30,0 | offen |
| [fugenwand_foto](#fugenwand_foto) | ok, 48 Warn. | 6149 | 61,5 | 1,35 | 36,0 | 286 | 181 | 20,0 | offen |
| [fugenwand_gurt](#fugenwand_gurt) | ok | 6268 | 62,7 | 1,38 | 25,0 | 411 | 244 | 30,0 | offen |
| [fugenwand_raute](#fugenwand_raute) | ok | 4968 | 49,7 | 1,09 | 14,0 | 240 | 210 | 30,0 | offen |
| [fugenwand_versetzt](#fugenwand_versetzt) | ok | 6287 | 62,9 | 1,38 | 28,0 | 411 | 244 | 30,0 | offen |
| [maeander](#maeander) | ok | 6328 | 63,3 | 1,39 | 13,0 | 165 | 910 | 30,0 | offen |
| [sinus](#sinus) | ok | 5773 | 57,7 | 1,27 | 11,0 | 314 | 910 | 30,0 | offen |
| [trapez](#trapez) | ok | 6098 | 61,0 | 1,34 | 13,0 | 202 | 910 | 30,0 | offen |
| [zickzack](#zickzack) | ok | 6022 | 60,2 | 1,32 | 13,0 | 221 | 910 | 30,0 | offen |

**1000x365 mm** (Schicht 0)

| Muster | Status | Pfad mm | Zeit s | Material rel. | Kontakte/m | Zelle mm | gerade Außen mm | R min mm | Roboter machbar |
|---|---|---|---|---|---|---|---|---|---|
| [schalen](#schalen) | ok | 4812 | 48,1 | 1,00 | 5,0 | 909 | 910 | 30,0 | offen |
| [fugenwand](#fugenwand) | ok | 5687 | 56,9 | 1,18 | 14,0 | 305 | 275 | 30,0 | offen |
| [fugenwand_foto](#fugenwand_foto) | ok, 48 Warn. | 6487 | 64,9 | 1,35 | 36,0 | 286 | 181 | 20,0 | offen |
| [fugenwand_gurt](#fugenwand_gurt) | ok | 6434 | 64,3 | 1,34 | 25,0 | 411 | 244 | 30,0 | offen |
| [fugenwand_raute](#fugenwand_raute) | ok | 5687 | 56,9 | 1,18 | 14,0 | 305 | 275 | 30,0 | offen |
| [fugenwand_versetzt](#fugenwand_versetzt) | ok | 6478 | 64,8 | 1,35 | 28,0 | 411 | 244 | 30,0 | offen |
| [maeander](#maeander) | ok | 7043 | 70,4 | 1,46 | 13,0 | 230 | 910 | 30,0 | offen |
| [sinus](#sinus) | ok | 6113 | 61,1 | 1,27 | 10,0 | 397 | 910 | 30,0 | offen |
| [trapez](#trapez) | ok | 6767 | 67,7 | 1,41 | 13,0 | 257 | 910 | 30,0 | offen |
| [zickzack](#zickzack) | ok | 6697 | 67,0 | 1,39 | 13,0 | 260 | 910 | 30,0 | offen |

### Entwurf der Empfehlung

**Entwurf aus den Zahlen (nicht abgestimmt; der Orchestrator schreibt ihn um).**

1. **fugenwand_versetzt**: Material im Mittel 1,38-fach gegenüber „schalen“, bis 60,0 Kontaktzonen je m, größte Zelle 411 mm, Druckzeit 35 s je Schicht auf 600x200.
2. **fugenwand_gurt**: Material im Mittel 1,38-fach gegenüber „schalen“, bis 50,0 Kontaktzonen je m, größte Zelle 411 mm, Druckzeit 36 s je Schicht auf 600x200.
3. **fugenwand_foto**: Material im Mittel 1,37-fach gegenüber „schalen“, bis 36,0 Kontaktzonen je m, größte Zelle 481 mm, Druckzeit 35 s je Schicht auf 600x200.

Rangfolge nach Materialverbrauch, Kontaktzonen und Zellgröße. Erreichbarkeit und Kollision des Roboters fließen nicht ein, solange die Roboterspalten „offen“ sind.
<!-- KATALOG:VERGLEICH:END -->

## Empfehlung

*Platzhalter: Den Text schreibt der Orchestrator nach dem Musterlauf. Ein Entwurf aus den Zahlen
steht oben im Abschnitt "Vergleich".*

<!-- KATALOG:DETAILS:BEGIN -->
## Muster im Einzelnen

### schalen

*Zwei Schalen, senkrechter Schichtwechsel*  
Preset: `core/src/roboprint/patterns/presets/schalen.json`

Grundmuster: zwei Schalen als ein Strang, S-Kurve beim Schalenwechsel, Naht im Eckbogen.

![schalen 600x200](bilder/katalog/schalen_600x200.svg)

![schalen 1000x200](bilder/katalog/schalen_1000x200.svg)

![schalen 1000x300](bilder/katalog/schalen_1000x300.svg)

![schalen 1000x365](bilder/katalog/schalen_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok | ok | ok | ok |
| Pfadlänge je Schicht | 2552 mm | 4152 mm | 4552 mm | 4812 mm |
| Druckzeit je Schicht (100 mm/s) | 25,5 s | 41,5 s | 45,5 s | 48,1 s |
| Material je m, relativ zu „schalen“ | 1,00 | 1,00 | 1,00 | 1,00 |
| Kontaktzonen je m | 8,3 | 5,0 | 5,0 | 5,0 |
| Größte Zellspannweite | 509 mm | 909 mm | 909 mm | 909 mm |
| Längste gerade ungestützte Außenstrecke | 510 mm | 910 mm | 910 mm | 910 mm |
| Fugenabstand | – | – | – | – |
| Kleinster Krümmungsradius | 30,0 mm | 30,0 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 94,4 % | 96,5 % | 96,8 % | 97,0 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Material 1,00- bis 1,00-fach gegenüber „schalen“.
- Viele Kontaktzonen (bis 8,3 je m) verzahnen Schalen und Füllung.
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Große Zellen (Spannweite bis 909 mm).
- Auf 600x200 verläuft die Außenhaut ungegliedert gerade (510 mm): Rissgefahr beim Trocknen.

Keine Kurzdoku vorhanden; Vor- und Nachteile aus den Zahlen.

### fugenwand

*Fugenwand (Rautenkette)*  
Preset: `core/src/roboprint/patterns/presets/fugenwand.json`

Empfehlung: An jeder Fuge eine Raute, Rauten berühren sich an Knoten in der Wandmitte, Rautenspitze stützt das Feld der Gegenseite; Fugen der Rückseite um F/2 versetzt.

![fugenwand 600x200](bilder/katalog/fugenwand_600x200.svg)

![fugenwand 1000x200](bilder/katalog/fugenwand_1000x200.svg)

![fugenwand 1000x300](bilder/katalog/fugenwand_1000x300.svg)

![fugenwand 1000x365](bilder/katalog/fugenwand_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok, 30 Warn. | ok, 50 Warn. | ok | ok |
| Pfadlänge je Schicht | 2420 mm | 4024 mm | 4968 mm | 5687 mm |
| Druckzeit je Schicht (100 mm/s) | 24,2 s | 40,2 s | 49,7 s | 56,9 s |
| Material je m, relativ zu „schalen“ | 0,95 | 0,97 | 1,09 | 1,18 |
| Kontaktzonen je m | 13,3 | 14,0 | 14,0 | 14,0 |
| Größte Zellspannweite | 140 mm | 140 mm | 240 mm | 305 mm |
| Längste gerade ungestützte Außenstrecke | 110 mm | 114 mm | 210 mm | 275 mm |
| Fugenabstand | 300 mm | 333, 333, 333 mm | 333, 333, 333 mm | 333, 334, 333 mm |
| Kleinster Krümmungsradius | 27,0 mm | 27,0 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 30 (M6) | 0 / 50 (M6) | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 64,6 % | 65,0 % | 62,0 % | 61,3 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 14,0 je m) verzahnen Schalen und Füllung.
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 0,95- bis 1,18-fach gegenüber „schalen“.
- Kleinster Radius 27,0 mm liegt unter der Strangbreite (M6-Warnung).

Kurzdoku: [fugenwand.md](fugenwand.md)

Einschätzung der Kurzdoku:

> 1. **Standard: Rautenkette (b), F = 300 mm, r = w.** Sie verbraucht am wenigsten Material
>    (600 × 200: 1,21 l/(m·Schicht), weniger als zwei Schalen mit 1,28) und hat die kürzeste Druckzeit.
>    Jede Fuge beider Seiten ist echt. Das Feld der Gegenseite wird in der Mitte gestützt. Sie sieht
>    aus wie das Foto: Raute über der Fuge, Dreieck über dem Feld, Knoten berühren sich. Ab 300 mm
>    Dicke gibt es keine Warnung, bei 200 mm r = 27 mm (M6-Warnung, Ziel knapp verfehlt).
> 2. **Gurt (a, c)** nur bei Wänden ≥ 365 mm oder mit r ≈ 20 mm (Preset `foto`). Er ist steifer
>    (Doppelgurt, viele Kontakte), braucht aber mehr Material als die Rautenkette (600 × 200: +47 %, 1000 × 300: +26 %, 1200 × 365: +6 %). In
>    200–300 mm Wänden wird er bei r = w zum Mäander. Gespiegelt (a) gibt eine durchgehende
>    Sollbruchebene durch die Wand, versetzt (c) verteilt die Fugen.
> 3. **Fugenabstand:** 300 mm, wie in der Recherche (160–300 mm, Fugenöffnung ≤ 3 mm bei 1 %
>    Schwinden). Sie belegt aber keinen Wert für gedruckten Lehm. Das ist eine Weiche für den Testdruck.

### fugenwand_foto

*Fugenwand mit Gurt wie Foto (a, Haken r = 20 mm)*  
Preset: `docs/muster/presets/fugenwand_foto.json`

Variante (a) mit engeren Haken (r = 20 mm < w: M6-Warnung, kein Fehler), damit die Stege bei 300 mm Wand schräg (V-förmig, 14–31°) laufen wie auf dem Foto. Bei 200 mm Wand bleibt auch dieses Preset ein Mäander (Stegwinkel ≈ 3°).

![fugenwand_foto 600x200](bilder/katalog/fugenwand_foto_600x200.svg)

![fugenwand_foto 1000x200](bilder/katalog/fugenwand_foto_1000x200.svg)

![fugenwand_foto 1000x300](bilder/katalog/fugenwand_foto_1000x300.svg)

![fugenwand_foto 1000x365](bilder/katalog/fugenwand_foto_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok, 16 Warn. | ok, 48 Warn. | ok, 48 Warn. | ok, 48 Warn. |
| Pfadlänge je Schicht | 3540 mm | 5841 mm | 6149 mm | 6487 mm |
| Druckzeit je Schicht (100 mm/s) | 35,4 s | 58,4 s | 61,5 s | 64,9 s |
| Material je m, relativ zu „schalen“ | 1,39 | 1,41 | 1,35 | 1,35 |
| Kontaktzonen je m | 23,3 | 36,0 | 36,0 | 36,0 |
| Größte Zellspannweite | 481 mm | 286 mm | 286 mm | 286 mm |
| Längste gerade ungestützte Außenstrecke | 220 mm | 181 mm | 181 mm | 181 mm |
| Fugenabstand | – | 250, 250, 250, 250 mm | 250, 250, 250, 250 mm | 250, 250, 250, 250 mm |
| Kleinster Krümmungsradius | 20,0 mm | 20,0 mm | 20,0 mm | 20,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 16 (M6) | 0 / 48 (M6) | 0 / 48 (M6) | 0 / 48 (M6) |
| Schalenabdeckung | 88,7 % | 87,9 % | 65,5 % | 63,0 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 36,0 je m) verzahnen Schalen und Füllung.
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 1,35- bis 1,41-fach gegenüber „schalen“.
- Große Zellen (Spannweite bis 481 mm).
- Kleinster Radius 20,0 mm liegt unter der Strangbreite (M6-Warnung).

Kurzdoku: [fugenwand.md](fugenwand.md)

### fugenwand_gurt

*Fugenwand mit Gurt, gespiegelt (a)*  
Preset: `docs/muster/presets/fugenwand_gurt.json`

Vorschlag des Nutzers: je Fuge Schleife Haken – Steg – Knoten – Gurt – Knoten – Steg – Haken; Doppelgurt in Wandmitte, Fugen beider Seiten gegenüber (durchgehende Sollbruchebene).

![fugenwand_gurt 600x200](bilder/katalog/fugenwand_gurt_600x200.svg)

![fugenwand_gurt 1000x200](bilder/katalog/fugenwand_gurt_1000x200.svg)

![fugenwand_gurt 1000x300](bilder/katalog/fugenwand_gurt_1000x300.svg)

![fugenwand_gurt 1000x365](bilder/katalog/fugenwand_gurt_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok, 16 Warn. | ok, 32 Warn. | ok | ok |
| Pfadlänge je Schicht | 3550 mm | 5909 mm | 6268 mm | 6434 mm |
| Druckzeit je Schicht (100 mm/s) | 35,5 s | 59,1 s | 62,7 s | 64,3 s |
| Material je m, relativ zu „schalen“ | 1,39 | 1,42 | 1,38 | 1,34 |
| Kontaktzonen je m | 43,3 | 50,0 | 25,0 | 25,0 |
| Größte Zellspannweite | 182 mm | 212 mm | 411 mm | 411 mm |
| Längste gerade ungestützte Außenstrecke | 170 mm | 198 mm | 244 mm | 244 mm |
| Fugenabstand | – | 334, 333 mm | 333, 333 mm | 333, 333 mm |
| Kleinster Krümmungsradius | 21,0 mm | 21,0 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 16 (M6) | 0 / 32 (M6) | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 88,6 % | 88,8 % | 60,0 % | 59,4 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 50,0 je m) verzahnen Schalen und Füllung.
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 1,34- bis 1,42-fach gegenüber „schalen“.
- Große Zellen (Spannweite bis 411 mm).
- Kleinster Radius 21,0 mm liegt unter der Strangbreite (M6-Warnung).

Kurzdoku: [fugenwand.md](fugenwand.md)

### fugenwand_raute

*Fugenwand Rautenkette (b, ohne Gurt)*  
Preset: `docs/muster/presets/fugenwand_raute.json`

Empfehlung: An jeder Fuge eine Raute, Rauten berühren sich an Knoten in der Wandmitte, Rautenspitze stützt das Feld der Gegenseite; Fugen der Rückseite um F/2 versetzt.

![fugenwand_raute 600x200](bilder/katalog/fugenwand_raute_600x200.svg)

![fugenwand_raute 1000x200](bilder/katalog/fugenwand_raute_1000x200.svg)

![fugenwand_raute 1000x300](bilder/katalog/fugenwand_raute_1000x300.svg)

![fugenwand_raute 1000x365](bilder/katalog/fugenwand_raute_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok, 30 Warn. | ok, 50 Warn. | ok | ok |
| Pfadlänge je Schicht | 2420 mm | 4024 mm | 4968 mm | 5687 mm |
| Druckzeit je Schicht (100 mm/s) | 24,2 s | 40,2 s | 49,7 s | 56,9 s |
| Material je m, relativ zu „schalen“ | 0,95 | 0,97 | 1,09 | 1,18 |
| Kontaktzonen je m | 13,3 | 14,0 | 14,0 | 14,0 |
| Größte Zellspannweite | 140 mm | 140 mm | 240 mm | 305 mm |
| Längste gerade ungestützte Außenstrecke | 110 mm | 114 mm | 210 mm | 275 mm |
| Fugenabstand | 300 mm | 333, 333, 333 mm | 333, 333, 333 mm | 333, 334, 333 mm |
| Kleinster Krümmungsradius | 27,0 mm | 27,0 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 30 (M6) | 0 / 50 (M6) | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 64,6 % | 65,0 % | 62,0 % | 61,3 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 14,0 je m) verzahnen Schalen und Füllung.
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 0,95- bis 1,18-fach gegenüber „schalen“.
- Kleinster Radius 27,0 mm liegt unter der Strangbreite (M6-Warnung).

Kurzdoku: [fugenwand.md](fugenwand.md)

### fugenwand_versetzt

*Fugenwand mit Gurt, versetzt (c)*  
Preset: `docs/muster/presets/fugenwand_versetzt.json`

Wie (a), Fugen der Rückseite um eine halbe Teilung versetzt; Endfeldknoten an der Endkappe.

![fugenwand_versetzt 600x200](bilder/katalog/fugenwand_versetzt_600x200.svg)

![fugenwand_versetzt 1000x200](bilder/katalog/fugenwand_versetzt_1000x200.svg)

![fugenwand_versetzt 1000x300](bilder/katalog/fugenwand_versetzt_1000x300.svg)

![fugenwand_versetzt 1000x365](bilder/katalog/fugenwand_versetzt_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok, 24 Warn. | ok, 40 Warn. | ok | ok |
| Pfadlänge je Schicht | 3533 mm | 5891 mm | 6287 mm | 6478 mm |
| Druckzeit je Schicht (100 mm/s) | 35,3 s | 58,9 s | 62,9 s | 64,8 s |
| Material je m, relativ zu „schalen“ | 1,38 | 1,42 | 1,38 | 1,35 |
| Kontaktzonen je m | 60,0 | 58,0 | 28,0 | 28,0 |
| Größte Zellspannweite | 182 mm | 212 mm | 411 mm | 411 mm |
| Längste gerade ungestützte Außenstrecke | 170 mm | 198 mm | 244 mm | 244 mm |
| Fugenabstand | 300 mm | 333, 333, 333 mm | 333, 333, 333 mm | 333, 333, 333 mm |
| Kleinster Krümmungsradius | 21,0 mm | 21,0 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 24 (M6) | 0 / 40 (M6) | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 88,1 % | 88,5 % | 60,8 % | 60,2 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 60,0 je m) verzahnen Schalen und Füllung.
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 1,35- bis 1,42-fach gegenüber „schalen“.
- Große Zellen (Spannweite bis 411 mm).
- Kleinster Radius 21,0 mm liegt unter der Strangbreite (M6-Warnung).

Kurzdoku: [fugenwand.md](fugenwand.md)

### maeander

*Mäander*  
Preset: `core/src/roboprint/patterns/presets/maeander.json`

Mäander mit senkrechten Flanken; im 50-mm-Band ist r ≤ 26,5 mm (M6-Warnung).

![maeander 600x200](bilder/katalog/maeander_600x200.svg)

![maeander 1000x200](bilder/katalog/maeander_1000x200.svg)

![maeander 1000x300](bilder/katalog/maeander_1000x300.svg)

![maeander 1000x365](bilder/katalog/maeander_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok, 16 Warn. | ok, 28 Warn. | ok | ok |
| Pfadlänge je Schicht | 3160 mm | 5249 mm | 6328 mm | 7043 mm |
| Druckzeit je Schicht (100 mm/s) | 31,6 s | 52,5 s | 63,3 s | 70,4 s |
| Material je m, relativ zu „schalen“ | 1,24 | 1,26 | 1,39 | 1,46 |
| Kontaktzonen je m | 16,7 | 13,0 | 13,0 | 13,0 |
| Größte Zellspannweite | 145 mm | 154 mm | 165 mm | 230 mm |
| Längste gerade ungestützte Außenstrecke | 510 mm | 910 mm | 910 mm | 910 mm |
| Fugenabstand | – | – | – | – |
| Kleinster Krümmungsradius | 26,5 mm | 26,5 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 16 (M6) | 0 / 28 (M6) | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 94,6 % | 96,6 % | 96,9 % | 97,1 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 16,7 je m) verzahnen Schalen und Füllung.
- Kleine Zellen (Spannweite höchstens 230 mm).
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 1,24- bis 1,46-fach gegenüber „schalen“.
- Kleinster Radius 26,5 mm liegt unter der Strangbreite (M6-Warnung).
- Auf 600x200 verläuft die Außenhaut ungegliedert gerade (510 mm): Rissgefahr beim Trocknen.

Kurzdoku: [wellen.md](wellen.md)

Einschätzung der Kurzdoku:

> - **S1-Wand 200 mm, zwei Schalen:** **Sinus** oder **Zickzack** mit λ ≈ 220 mm (Wunsch 250 mm). Beide
>   haben 8,3 Kontakte je m, 21 % mehr Material und Radius ≥ w. Das Trapez hat die längsten
>   Kontaktzonen (257 mm je 0,6 m) bei gleicher Pfadlänge (+0,7 %). Der Mäander verfehlt das
>   Radiusziel (26,5 mm).
> - **300 bzw. 365 mm Wand:** **Trapez** oder **Zickzack** mit zwei Schalen (λ ≈ 220 mm, 8,3 Kontakte
>   je m, Zellen ≤ Wanddicke). Mit einer Schale je Seite sinkt das Material auf 0,91–0,96 bei gleicher
>   Kontaktzahl.
> - **Eine Schale je Seite** spart bei 200 mm Wand 11–20 % Material gegenüber zwei Schalen ohne
>   Infill. Dafür ist die Außenhaut nur eine Raupe dick. Ob das reicht, muss der Testdruck zeigen.

### sinus

*Sinuswelle*  
Preset: `core/src/roboprint/patterns/presets/sinus.json`

Sinus-Infill zwischen den Innenschalen, Berge und Täler berühren beide Schalen.

![sinus 600x200](bilder/katalog/sinus_600x200.svg)

![sinus 1000x200](bilder/katalog/sinus_1000x200.svg)

![sinus 1000x300](bilder/katalog/sinus_1000x300.svg)

![sinus 1000x365](bilder/katalog/sinus_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok | ok | ok | ok |
| Pfadlänge je Schicht | 3097 mm | 5133 mm | 5773 mm | 6113 mm |
| Druckzeit je Schicht (100 mm/s) | 31,0 s | 51,3 s | 57,7 s | 61,1 s |
| Material je m, relativ zu „schalen“ | 1,21 | 1,24 | 1,27 | 1,27 |
| Kontaktzonen je m | 16,7 | 13,0 | 11,0 | 10,0 |
| Größte Zellspannweite | 195 mm | 214 mm | 314 mm | 397 mm |
| Längste gerade ungestützte Außenstrecke | 510 mm | 910 mm | 910 mm | 910 mm |
| Fugenabstand | – | – | – | – |
| Kleinster Krümmungsradius | 30,0 mm | 30,0 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 94,6 % | 96,6 % | 96,9 % | 97,1 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 16,7 je m) verzahnen Schalen und Füllung.
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 1,21- bis 1,27-fach gegenüber „schalen“.
- Auf 600x200 verläuft die Außenhaut ungegliedert gerade (510 mm): Rissgefahr beim Trocknen.

Kurzdoku: [wellen.md](wellen.md)

### trapez

*Trapezwelle*  
Preset: `core/src/roboprint/patterns/presets/trapez.json`

Trapezwelle mit 60-mm-Plateaus an den Schalen (lange Kontaktzonen).

![trapez 600x200](bilder/katalog/trapez_600x200.svg)

![trapez 1000x200](bilder/katalog/trapez_1000x200.svg)

![trapez 1000x300](bilder/katalog/trapez_1000x300.svg)

![trapez 1000x365](bilder/katalog/trapez_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok | ok | ok | ok |
| Pfadlänge je Schicht | 3119 mm | 5165 mm | 6098 mm | 6767 mm |
| Druckzeit je Schicht (100 mm/s) | 31,2 s | 51,6 s | 61,0 s | 67,7 s |
| Material je m, relativ zu „schalen“ | 1,22 | 1,24 | 1,34 | 1,41 |
| Kontaktzonen je m | 16,7 | 13,0 | 13,0 | 13,0 |
| Größte Zellspannweite | 167 mm | 184 mm | 202 mm | 257 mm |
| Längste gerade ungestützte Außenstrecke | 510 mm | 910 mm | 910 mm | 910 mm |
| Fugenabstand | – | – | – | – |
| Kleinster Krümmungsradius | 30,0 mm | 30,0 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 94,6 % | 96,6 % | 96,9 % | 97,1 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 16,7 je m) verzahnen Schalen und Füllung.
- Kleine Zellen (Spannweite höchstens 257 mm).
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 1,22- bis 1,41-fach gegenüber „schalen“.
- Auf 600x200 verläuft die Außenhaut ungegliedert gerade (510 mm): Rissgefahr beim Trocknen.

Kurzdoku: [wellen.md](wellen.md)

### zickzack

*Zickzack gerundet*  
Preset: `core/src/roboprint/patterns/presets/zickzack.json`

Zickzack mit Scheitelradius w.

![zickzack 600x200](bilder/katalog/zickzack_600x200.svg)

![zickzack 1000x200](bilder/katalog/zickzack_1000x200.svg)

![zickzack 1000x300](bilder/katalog/zickzack_1000x300.svg)

![zickzack 1000x365](bilder/katalog/zickzack_1000x365.svg)

Kennzahlen (Schicht 0):

| Kennzahl | 600x200 | 1000x200 | 1000x300 | 1000x365 |
|---|---|---|---|---|
| Status (M1–M7) | ok | ok | ok | ok |
| Pfadlänge je Schicht | 3093 mm | 5124 mm | 6022 mm | 6697 mm |
| Druckzeit je Schicht (100 mm/s) | 30,9 s | 51,2 s | 60,2 s | 67,0 s |
| Material je m, relativ zu „schalen“ | 1,21 | 1,23 | 1,32 | 1,39 |
| Kontaktzonen je m | 16,7 | 13,0 | 13,0 | 13,0 |
| Größte Zellspannweite | 199 mm | 219 mm | 221 mm | 260 mm |
| Längste gerade ungestützte Außenstrecke | 510 mm | 910 mm | 910 mm | 910 mm |
| Fugenabstand | – | – | – | – |
| Kleinster Krümmungsradius | 29,9 mm | 30,0 mm | 30,0 mm | 30,0 mm |
| Verstöße (Fehler / Warnungen) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Schalenabdeckung | 94,6 % | 96,6 % | 96,9 % | 97,1 % |
| Stränge je Schicht | 1 | 1 | 1 | 1 |

Roboter (aus `verify_muster`):

machbar offen, d_min offen, Stränge je Schicht offen, senkrechte Schichtwechsel offen, Druckzeit offen, Planerlaufzeit offen.

**Vorteile**

- Regelkonform (keine M1–M7-Fehler) auf 600x200, 1000x200, 1000x300, 1000x365.
- Viele Kontaktzonen (bis 16,7 je m) verzahnen Schalen und Füllung.
- Kleine Zellen (Spannweite höchstens 260 mm).
- Ein Strang je Schicht und Insel (M1).

**Nachteile**

- Material 1,21- bis 1,39-fach gegenüber „schalen“.
- Kleinster Radius 29,9 mm liegt unter der Strangbreite (M6-Warnung).
- Auf 600x200 verläuft die Außenhaut ungegliedert gerade (510 mm): Rissgefahr beim Trocknen.

Kurzdoku: [wellen.md](wellen.md)

<!-- KATALOG:DETAILS:END -->
