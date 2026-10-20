# Testdrucke je Druckmuster

Kleine Testkörper (10 Schichten, 100 mm hoch) je Muster am Standard-Druckplatz (0, −50) mm,
vom Planer als machbar eingestuft und geprüft. Erzeugt mit `python scripts/muster_testdrucke.py`
(Stand 2026-10-20). Je Ordner: `scenario.json`, `program.v2.drl`, `program.v3.drl`, `schicht0.svg`,
`README.md`.

**Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck** (ohne Material, `change_operation_speed` 10 … 20 %). Alle Werte mit (A) im
DRL-Kopf sind provisorisch.

| Nr. | Muster | Testkörper (mm) | Status | Druckzeit | Material | Stränge/Schicht | senkrechte Wechsel | d_min | Abdeckung G3 (< 95 %: Einwand 1) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | [schalen_alternate](schalen_alternate/README.md) | 600 × 200 × 100 | machbar, geprüft | 4,4 min | 7,7 l | 1 | 100 % | 10,8 mm | 94,4 % |
| 2 | [fugenwand_raute](fugenwand_raute/README.md) | 600 × 200 × 100 | machbar, geprüft | 4,2 min | 7,3 l | 1 | 100 % | 10,8 mm | 64,6 % |
| 3 | [sinus](sinus/README.md) | 600 × 200 × 100 | machbar, geprüft | 5,3 min | 9,3 l | 1 | 100 % | 10,8 mm | 94,6 % |
| 4 | [fugenwand_versetzt](fugenwand_versetzt/README.md) | 600 × 200 × 100 | machbar, geprüft | 6,0 min | 10,6 l | 1 | 100 % | 10,8 mm | 88,1 % |
| 5 | [fugenwand_gurt](fugenwand_gurt/README.md) | 600 × 200 × 100 | machbar, geprüft | 6,0 min | 10,7 l | 1 | 100 % | 10,8 mm | 88,6 % |
| 6 | [zickzack](zickzack/README.md) | 600 × 200 × 100 | machbar, geprüft | 5,3 min | 9,3 l | 1 | 100 % | 10,8 mm | 94,6 % |
| 7 | [trapez](trapez/README.md) | 600 × 200 × 100 | machbar, geprüft | 5,3 min | 9,4 l | 1 | 100 % | 10,8 mm | 94,6 % |
| 8 | [maeander](maeander/README.md) | 600 × 200 × 100 | machbar, geprüft | 5,4 min | 9,5 l | 1 | 100 % | 10,8 mm | 94,6 % |
| 9 | [fugenwand_gurt_300](fugenwand_gurt_300/README.md) | 600 × 300 × 100 | machbar, geprüft | 6,5 min | 11,5 l | 1 | 100 % | 10,8 mm | 62,7 % |
| 10 | [doppelwelle_300](doppelwelle_300/README.md) | 600 × 300 × 100 | machbar, geprüft | 6,8 min | 12,1 l | 1 | 100 % | 10,8 mm | 95,3 % |
| 11 | [waben_300](waben_300/README.md) | 600 × 300 × 100 | machbar, geprüft | 7,1 min | 12,6 l | 1 | 100 % | 10,8 mm | 95,3 % |
| 12 | [fermat](fermat/README.md) | 300 × 200 × 100 | machbar, geprüft | 3,0 min | 5,2 l | 1 | 100 % | 10,8 mm | 92,0 % |

Prüfung je Testkörper: `python -m verify.check_run` (G3-Regeln; die Abdeckung < 95 % ist bei
Mustern gewollt und als Gate-Einwand 1 in MUSTER-PROGRESS.md geführt), `python -m verify.fake_drcf`
(G5, v2 und v3) und `python -m verify_muster.check` (M1–M7). Material: Annahme Raupenquerschnitt
w × h = 30 × 10 mm mal Pfadlänge, ohne Abzug der Überlappung an Kontakten.

## Testdruckplan

Reihenfolge wie in der Tabelle: vom einfachen zum anspruchsvollen Muster, damit jeder Druck eine
neue Frage beantwortet und die vorige als geklärt voraussetzt.

1. **schalen_alternate** zuerst, als Referenz ohne Muster: Stimmen Raupenbreite (30 mm) und
   Schichthöhe (10 mm), haftet die erste Schicht, ist der senkrechte Schichtwechsel (reiner Z-Hub)
   ohne Abriss und die Naht im Eckbogen sauber? Erst wenn das passt, lohnt ein Muster.
2. **fugenwand_raute** (empfohlen): Hauptfrage des Nachtrags 18:20. Beobachten: **Fugen** – die
   Haken berühren sich, laufen aber nicht ineinander; beim Trocknen sollen Risse in den Fugen
   entstehen, nicht in den Feldern (Fotos nach 1, 3 und 7 Tagen). **Haken** – sauber gerundet,
   ohne Klecks am Umkehrpunkt. **Kontakte** – die Rautenknoten in der Wandmitte haften.
3. **sinus**: einfachstes Infill; prüft, ob Kontakte Welle an Schale haften (Überlappung 0 … ε·w).
4. **fugenwand_versetzt** und **fugenwand_gurt**: Haken mit verkleinertem Radius (< w) auf 200 mm.
   Sind sie unsauber, gilt die Gurtvariante erst ab 230 mm Wand (dann **fugenwand_gurt_300**).
5. **zickzack**, **trapez**, **maeander**: engere Wenden und lange Kontaktstrecken; Mäander hat
   den kleinsten Wenderadius (26,5 mm < w).
6. **doppelwelle_300**, **waben_300**: nur für 300-mm-Wände; Knoten zwischen den Wellen haften?
7. **fermat** als Pfeiler zuletzt: Wende r = w/2 in der Mitte und Naht an der Sichtfläche.

Je Druck festhalten: Datum, Lehmmischung und Feuchte, tatsächliche Raupenbreite und -höhe,
Stellen mit Abriss oder Stau (Ring- und Sample-Nummer aus dem DRL-Kommentar), Fotos von oben und
von der Außenseite, nach dem Trocknen Lage und Breite der Risse.
