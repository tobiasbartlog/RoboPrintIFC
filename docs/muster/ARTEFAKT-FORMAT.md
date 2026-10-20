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
