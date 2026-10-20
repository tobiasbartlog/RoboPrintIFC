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
  waagrecht übereinander (≤ 10⁻⁹ mm, Fall `Point`): senkrechter Schichtwechsel. Mit ausdrücklich
  gesetztem `same` bleibt der Schichtwechsel ein gewöhnlicher (diagonaler) Verbinder, wenn er
  ≤ `link_max_mm` ist (M4-Fehler, nur zum Vergleich).
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
`pattern_params`. `layer_order` fehlt (intern leer): ohne Muster heutige Folge, mit Muster die des
Presets bzw. des Kerns (`alternate`, M4); ausdrücklich gesetzt gilt es auch gegen das Preset.
`layer_order = same` allein ist kein Muster (Gegenprüfung M3.1: vorher ergab z. B.
`infill_pattern = sinus` ohne `layer_order` die Folge `same`, also auf 600 × 200 einen diagonalen
Schichtwechsel von 504 mm als Travel). w, h, `step_mm` und `link_max_mm` kommen immer aus dem Szenario. Unbekannte
Muster oder widersprüchliche Kombinationen (z. B. Fugenwand plus Infill) sind ein Fehler beim Start.

**summary.json und DRL:** `summary.params` führt die Musterparameter nur, wenn sie gesetzt sind
(`pattern_params` als JSON-Text, damit `params` skalar bleibt). `summary.assumptions` bekommt dann
eine Zeile „Druckmuster (opt-in, A): Schichtfolge …, Infill …, Outfill …, Parameter …“, der
DRL-Kopf einen Block „A Schichtfolge / A Muster / A Muster-Preset / A Musterparameter“. Schichtfolge
und Muster stehen dort aufgelöst (aus `Toolpath.pattern`), also auch bei einem Preset richtig.

**Vertragsname:** Das Objekt `Toolpath.pattern` heißt im Schema `ToolpathPattern` (der Katalog-Eintrag
der Muster-API heißt `PatternInfo`; beide kamen beim Merge von `v2/muster` zusammen).

## Nachtrag M3.2: Planer, Timing und DRL

Umgesetzt in `core/src/roboprint/planner/` (`plan.py`, `graph.py`, `backend.py`, `__init__.py`),
`timing.py` und `drl_steps.py`. Ohne Musterparameter bleibt alles bitgleich: S1 vor und nach M3.2
hat gleiche `trajectory.json` (summary, t_s, q, tcp, kind, ring, layer, branch, status, d_mm, pair),
gleichen Toolpath (sha256) und gleiche DRL-Befehlszeilen; nur die Provenienz-Zeile weicht ab.

**Was der Planer schon konnte und jetzt abgesichert ist.** Der Planer behandelt jeden Ring als
Wegpunktfolge vom ersten zum letzten Punkt; offene Ringe (`closed = false`) laufen wie geschlossene.
Verbinder der Laenge 0 in der Schicht werden ein `link`-Sample am Ringende (Ablaufregel des Pruefers:
mindestens ein `link`-Sample), der senkrechte Schichtwechsel ein Z-Hub um h (3 bis 6 Samples). Ein
Muster ist ueber alle Ringe und Schichten **ein** Strang (ein Vorlauf, ein Trapez, Pumpe einmal an
und aus).

**Neu:**
- `psi_hold` (Planer): Bei einem Verbinder ohne waagrechte Laenge (≤ 0,5 mm, `plan.is_zero_link`)
  behaelt der Folgering das psi am Ende des Vorgaengers (Startzustaende mit anderem psi kosten BIG).
  Sonst koennte sich die Duese (TCP 134 mm neben der Flanschachse) mit laufender Pumpe auf der Stelle
  drehen. In allen Laeufen unten war die Drehung an Verbindern 0°, max|Δq| am Verbinder 0,026 rad.
- **Double mit Paar Werkzeugkoerper ↔ link_4 bei Mustern** (`backend.PATTERN_SELF_PAIRS`, nur wenn
  `params.uses_pattern`): Mit `alternate` endet jede ungerade Schicht an der Naht der Aussenschale. An
  der Oberkante von S1 faltet das Handgelenk dort so, dass der Werkzeugkoerper link_4 unter d_hard
  kommt (Double-Plan: d = 9,8 mm in Schicht 37, Kollision −2,9 mm beim Abheben nach Schicht 39). Das
  Double kannte das Paar nicht, die Abschlusspruefung verwarf den Plan, und die Nachplanung mit der
  echten Welt kostete das 2,6- bis 2,8-Fache von S1. Mit dem Paar ist der Double-Plan machbar.
- DRL: Der Ringkommentar nennt Musterverbinder (`# Ring r (ueber Verbinder, senkrecht, Z +10.0 mm)`
  bzw. `(ueber Verbinder, Laenge 0)`); Verbinder mit waagrechter Laenge behalten den bisherigen Text.
  Ein Verbinder der Laenge 0 faellt mit dem Ringende zusammen und ist dessen Ziel (kein Segment der
  Laenge 0, kein radius 0 im Strang). radius = min(r_blend, ½ angrenzende Segmente) wie bisher; der
  Z-Hub hat radius ≤ 2 mm (h/2 = 5 mm). `movesx` (v3, opt-in) nur fuer Straenge aus einem Ring mit
  ≤ 100 Zielen; Musterstraenge haben Verbinder und bleiben `movel` mit Blending.

**Laufzeit** (S1-Quader 600 × 200 × 400 mm, 40 Schichten, `--jobs 2`, VM mit anderen Agenten geteilt,
daher ±30 % Rauschen; Szenarien unter `docs/muster/szenarien/`):

| Lauf | Ringe | Wegpunkte | Samples | Planung vor M3.2 | Planung nach M3.2 | Faktor zu S1 | Druckzeit |
|---|---|---|---|---|---|---|---|
| S1 ohne Muster | 80 | 5680 | 41 074 | 54,7 s | 58,1 s (bitgleich) | 1,0 | 1129 s |
| `S4_muster_alternate` | 80 | 6440 | 38 281 | 149,5 s (Nachplanung) | 75,2 s | 1,3 | 1032 s |
| `S4_muster_fugenwand` | 280 | 7760 | 37 194 | 52,8 s | 52 … 88 s | 0,9 … 1,5 | 979 s |
| `S4_muster_sinus` | 120 | 7880 | 46 026 | 146,4 s (Nachplanung) | 67,8 s | 1,2 | 1250 s |

Die Kurven bringen 1,1- bis 1,4-mal so viele Wegpunkte wie S1 (Fugenwand 10 mm Abstand auf den
Geraden, Sinus bis 2,9 mm in den Boegen). Die Planung bleibt damit weit unter 3 × S1; Knoten nur
alle Δs = 20 mm (Verdichtung dazwischen per movel-IK) ist deshalb nicht noetig und nicht eingebaut.

**Pruefung** (nur aufgerufen): `python -m verify.check_run` (G3-Regeln) meldet fuer alle drei Laeufe
nur die Abdeckung (alternate 94,4 %, Sinus 94,6 %, Fugenwand 64,6 % < 95 %; Gate-Einwand 1); 0
collision, 0 unreachable, d_min 10,83 mm, Verbinder, Ablauf, Pfad und Zweig gruen. `verify/fake_drcf`:
v2 und v3 aller drei Laeufe ok. `python -m verify_muster.check`: GRUEN M1–M7 fuer alle drei.
