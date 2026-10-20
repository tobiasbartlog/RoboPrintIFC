# Artefaktformat für Druckmuster (Festlegung des Orchestrators, M0)

Stand 20.10.2026, Session `start`. Diese Datei legt fest, wie Muster in den bestehenden
Artefakten (`spec/ARTEFAKTE.md`) erscheinen, damit Kern (`core/src/roboprint/patterns/`), Einbau
(Slicer, Planer, DRL) und das unabhängige Muster-Orakel (`verify_muster/`) gegen denselben Vertrag
arbeiten. Sie geht später in `docs/muster/SPEC-NACHTRAG-MUSTER.md` ein. Bei Widerspruch zu
`spec/ARTEFAKTE.md` für Teile **ohne** Muster gilt ARTEFAKTE.

## toolpath.json

Unverändert: `rings [{layer, shell, kind, closed, link_next, waypoints}]`, Wegpunkte in W,
Düsenachse −Z_W, Ringe in Druckreihenfolge.

Erweiterungen (alle opt-in, ohne Muster bleibt die Datei bitgleich zu heute):

- `kind` ∈ {`outer`, `inner`, `hole`, `infill`, `web`, `outfill`}.
  - `outer`/`inner`/`hole` wie bisher (Schalen).
  - `infill`: Muster im Hohlraum zwischen den inneren Schalen (Welle, Zickzack, Spirale …).
  - `web`: Quersteg (z. B. an einer künftigen Laibung, M3, oder ein Zellsteg O3).
  - `outfill`: gegliederte oder gewellte Außenhaut (O1/O2/O3), ersetzt dann die Schale 0 `outer`.
- `closed = false` ist erlaubt: ein offenes Segment. Bei `closed = false` gilt nicht, dass der
  letzte Wegpunkt dem ersten gleicht.
- **Ein Schichtpfad** je Schicht und Insel ist eine Folge aufeinanderfolgender Ringe derselben
  Schicht, die alle mit `link_next = true` verbunden sind. Der Verbinder zwischen zwei Segmenten
  eines Schichtpfads ist die Gerade vom letzten zum ersten Wegpunkt (SPEC §5.3); im Muster ist er in
  der Regel kurz (≤ w) oder hat die Länge 0 (Segmente stoßen aneinander).
- **Senkrechter Schichtwechsel (M4):** Der letzte Ring von Schicht L und der erste Ring von
  Schicht L + 1 sind mit `link_next = true` verbunden, und deren Endpunkt bzw. Startpunkt liegen
  waagrecht ≤ 0,5 mm auseinander. Der Verbinder ist dann ein reiner Z-Hub um h.
- **Schichtfolge `alternate`:** Der Schichtpfad von Schicht L + 1 ist die Umkehrung des Schichtpfads
  von Schicht L (gleiche XY-Geometrie, Ringe in umgekehrter Reihenfolge, Wegpunkte jedes Rings
  umgekehrt), solange sich der Querschnitt nicht ändert.
- Optional auf oberster Ebene: `pattern` (Objekt oder fehlt) mit
  `{layer_order, infill, outfill, params {…}}`. Das Orakel darf es zur Beschriftung lesen, prüft aber
  nur die Geometrie.

## trajectory.json

Unverändert. Verbinder heißen weiter `link`, Druck weiter `print`. Ein Verbinder der waagrechten
Länge 0 besteht aus Samples auf der senkrechten Geraden (TCP steigt um h bzw. bleibt bei Länge 0
in derselben Schicht stehen; Letzteres vermeidet der Slicer, indem er stoßende Segmente nicht als
Verbinder der Länge 0 in derselben Schicht ausgibt, sondern zu einem Ring zusammenfasst, wenn
`kind` gleich ist).

## Szenario

`params` bekommt opt-in-Schlüssel (alle fehlen = heutiges Verhalten):
`layer_order` (`same` | `alternate`), `infill_pattern` (`none` | Mustername), `outfill_pattern`
(`none` | Mustername), `pattern_params` (Objekt, z. B. `wavelength_mm`, `amplitude_mm`,
`web_spacing_mm`, `phase`), `shells` (Anzahl Schalen je Seite, Standard 2).

## Nachtrag 18:45: Fugenwand (Sollbruchstellen, Nutzer-Nachtrag 18:20)

- Segmentarten der Fugenwand: Außenfeld zwischen zwei Fugen = `outfill`, Schrägsteg von der Fuge
  zum Knoten = `web`, Gurtstück in der Wandmitte = `infill`, Endkappe am Modulende = `outfill`.
  Ein Schichtpfad der Fugenwand ist ein einziger geschlossener Zug (Ringe mit `link_next`, Verbinder
  der Länge 0 zwischen stoßenden Segmenten werden zu einem Ring zusammengefasst, wenn `kind` gleich
  ist; sonst Verbinder der Länge 0, der im Planer als `link` mit 0 Samples Länge zählt oder vom
  Slicer vermieden wird: entscheidet M3).
- **Gewollte Kontakte** (Fuge, Knoten, Steg an Schale): Mittellinienabstand in [(1 − ε)·w, w] bei
  Bogenlängenabstand > 2·w. Sie sind keine Kreuzung. Kern und Orakel berichten sie als Kontaktzonen
  (Lage, Länge, Art `joint` | `node` | `shell`).
- Vorschau-Ausgabe des Kerns (für API, CLI und Viewer, ohne Roboter): je Schicht die Polylinien je
  Segmentart, Start und Ende, Kontakte, Regelverstöße M1–M7 und Kennzahlen, als JSON.

## Nachtrag M3: Slicer und Vertrag (M3.1)

Umgesetzt in `core/src/roboprint/slicer_patterns.py` (vom Slicer aufgerufen) und den Verträgen.

**Verbinder der Länge 0 in derselben Schicht sind gültig.** Geprüft mit dem unabhängigen Prüfer
`python -m verify.check_run` (nur aufgerufen, nicht geändert) an zwei Läufen auf dem Quader
600 × 200 × 60 mm (6 Schichten, Standard-Druckplatz):

| Lauf | Ringe | Verbinder | längster Verbinder | Ablauf-, Verbinder-, Pfadfehler | `verify_muster` | `fake_drcf` |
|---|---|---|---|---|---|---|
| `layer_order = alternate` (2 Schalen) | 12 | 11 (6 in der Schicht, 5 Schichtwechsel) | 9·10⁻¹³ mm | keine | GRÜN (M1–M7) | v2/v3 ok |
| Preset `fugenwand.json` (Rautenkette) | 42 | 41 | 0,0 mm | keine | GRÜN (M1–M7) | v2/v3 ok |

Einziger Fehler beider Läufe ist die G3-Abdeckung (94,4 % bzw. 64,6 % < 95 %), siehe
Gate-Einwand 1 in `MUSTER-PROGRESS.md`. Die Bedingungen des Prüfers für einen Verbinder
(`verify/oracle/strand_rules.py`): Schichtsprung 0 oder 1; waagrechte Länge ≤ `link_max_mm`;
Projektion (bei Länge 0 ein Punkt) im Querschnitt ± 1 mm; jedes `link`-Sample ≤ 0,5 mm neben der
Strecke; **mindestens ein `link`-Sample** direkt zwischen `print r` und `print r + 1`
(Ablaufregel) und `link_next = true` an Ring r. Der heutige Planer erzeugt für einen Verbinder der
Länge 0 in der Schicht ein `link`-Sample und für den senkrechten Schichtwechsel drei (Z-Hub um h).

**Gewählte Form:**
- Je Schichtpfad werden die Segmente in Druckreihenfolge zu Ringen. Stößt ein Segment (Verbinder
  ≤ 10⁻⁶ mm) an ein Segment **gleicher** `kind`, sind beide ein Ring. Segmente **verschiedener**
  `kind` bleiben eigene Ringe, verbunden durch einen Verbinder der Länge 0 (`link_next = true`).
  So bleibt die Segmentart im Toolpath und in der Trajektorie (`ring`) sichtbar; ein Zusammenfassen
  verschiedener Arten ist nicht nötig. `shell` ist die Schale des ersten Segments eines Rings.
- `closed = true` genau dann, wenn der letzte Wegpunkt den ersten trifft (≤ 10⁻⁶ mm, dann exakt
  gleich gesetzt), sonst `closed = false`. Beispiel: Schalenkette mit S-Kurve = zwei offene Ringe;
  eine Schale je Seite = ein geschlossener Ring.
- Wegpunkte: alle Punkte der Mustersegmente bleiben erhalten (Kurven sind schon dicht, Sehnenfehler
  ≤ 0,5 mm); Stücke länger als `step_mm` werden wie bisher gleichmäßig unterteilt, doppelte
  Punkte entfallen.
- `link_next` zwischen allen aufeinanderfolgenden Ringen nach derselben Regel wie ohne Muster
  (`slicer.link_allowed`, SPEC §5.3). Mit `alternate` liegen Ende von L und Anfang von L + 1
  waagrecht übereinander (≤ 10⁻⁹ mm, Fall `Point`): senkrechter Schichtwechsel. Mit `same` bleibt
  der Schichtwechsel ein gewöhnlicher (diagonaler) Verbinder, wenn er ≤ `link_max_mm` ist.
  Ändert sich der Querschnitt (`restart` im Kern), entscheidet dieselbe Regel (Verbinder oder Travel).
- `link_max_mm = 0` schaltet auch die Musterverbinder ab (jeder Ring ein eigener Strang, M1 verletzt;
  so gewollt, damit die Bedeutung des Parameters gleich bleibt).

**Vertrag** (`core/src/roboprint/contracts`, Schemas `web/src/contracts/schemas`, TS-Typen):
- `Ring.kind` ∈ {outer, inner, hole, infill, web, outfill}; `closed = false` braucht ≥ 2 Wegpunkte.
- `Toolpath.pattern` = `{layer_order, infill, outfill, params}` nur bei Teilen mit Muster; ohne
  Muster fehlt der Schlüssel ganz (Datei bitgleich, Test `test_default_s1_toolpath_bit_identical`).
  `params` enthält die musterspezifischen Werte und die Kernwerte, die vom Standard abweichen.
- Szenario- und Job-`params` erlauben genau ein Objekt: `pattern_params`. Alle anderen Werte
  bleiben skalar.

**Szenario-Parameter** (alle opt-in; fehlen alle, schneidet der Slicer wie bisher):
`layer_order` (`same` | `alternate`), `infill_pattern`, `outfill_pattern` (`none` | Mustername),
`pattern_params` (Objekt, z. B. `{"field_length_mm": 250, "corner_radius_mm": 22.5}`),
`pattern_preset` (Pfad zu einem Preset-JSON, relativ zum Repo, z. B.
`core/src/roboprint/patterns/presets/fugenwand.json` oder `docs/muster/presets/fugenwand_gurt.json`),
`shells` (wie bisher). Rangfolge: Preset → Szenariowerte, die vom Standard abweichen →
`pattern_params`. w, h, `step_mm` und `link_max_mm` kommen immer aus dem Szenario. Unbekannte
Muster oder widersprüchliche Kombinationen (z. B. Fugenwand plus Infill) sind ein Fehler beim Start.

**summary.json und DRL:** `summary.params` führt die Musterparameter nur, wenn sie gesetzt sind
(`pattern_params` als JSON-Text, damit `params` skalar bleibt). `summary.assumptions` bekommt dann
eine Zeile „Druckmuster (opt-in, A): Schichtfolge …, Infill …, Outfill …, Parameter …“, der
DRL-Kopf einen Block „A Schichtfolge / A Muster / A Muster-Preset / A Musterparameter“.
