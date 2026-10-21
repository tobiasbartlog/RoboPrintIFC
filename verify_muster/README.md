# verify_muster/ – unabhängiges Muster-Orakel (Vorschlag für Gate G9)

Prüft die Musterregeln M1–M7 aus `docs/muster/AUFTRAG.md` auf den Artefakten eines Laufordners im
Format `spec/ARTEFAKTE.md` mit den Erweiterungen aus `docs/muster/ARTEFAKT-FORMAT.md` (inkl. Nachtrag
18:45, Fugenwand). Das Orakel folgt denselben Regeln wie `verify/`:

- Es importiert `roboprint` nie und liest `core/src` nicht. Es rechnet mit eigener Geometrie (numpy,
  shapely, trimesh, scipy).
- Es liest nur Artefakte: `parts/<id>/toolpath.json`, `trajectory.json`, `part.stl` (Frame P),
  `part.json` (T_WP, Status; ersatzweise T_WP aus `summary.json` bzw. `scene.json`) und optional das
  Szenario (nur zur Beschriftung: `id`, `layer_order`, `infill_pattern`, `outfill_pattern`,
  `pattern_params`, `shells`). Das optionale Feld `pattern` im toolpath wird nur berichtet.
- Alle Wegpunkte und TCP-Samples werden mit p_P = T_WP⁻¹ · p_W nach P gerechnet. Die Querschnitte
  schneidet das Orakel selbst aus `part.stl` bei z = (L + 0,5)·h.

## Aufruf

```
python -m verify_muster.check <laufordner> [--scenario <json>] [--json out.json] [--part ID] [--no-trajectory]
```

`<laufordner>` ist ein Lauf mit `parts/` oder ein einzelner Teilordner. Der Bericht geht nach `--json`
(Standard `<laufordner>/check_muster.json`). Exit 0 genau dann, wenn alle harten Regeln (M1–M6, M6b)
in allen Teilen grün sind, 1 bei einer Regelverletzung, 2 bei fehlenden oder unlesbaren Artefakten.
Ohne `--no-trajectory` ist `trajectory.json` Pflicht.

Bericht je Teil: `passed`, `failed_rules`, `first_counterexample` (Regel, Schicht, Ring, Punkt in P,
Meldung; die kleinste Schicht über alle verletzten Regeln), je Regel `pass`, `n_checked`,
`n_violations`, `first`, bis zu 20 `examples`, `warnings`, `metrics`, `note`, dazu die Kennzahlen
(`metrics.layers[]` je Schicht).

Lint und Selbsttests:

```
python -m ruff check verify_muster          # eigene verify_muster/ruff.toml (wie verify/ruff.toml)
python -m pytest verify_muster -q -n 2
```

## Begriffe

- **Schichtpfad:** aufeinanderfolgende Ringe derselben Schicht, die mit `link_next = true` verbunden
  sind, mit den Verbindern dazwischen (Gerade vom letzten zum ersten Wegpunkt, auch Länge 0). Der
  Verbinder am Schichtende gehört nicht zum Schichtpfad (er ist der Schichtwechsel, M4).
- **Insel:** zusammenhängende Fläche des Querschnitts (Fläche ≥ 1 mm²). Ein Schichtpfad gehört zu der
  Insel, deren Querschnitt ⊕ 1 mm seine Punkte enthält.
- **Bogenabstand:** Abstand zweier Punkte entlang des Schichtpfads. Der Schließpunkt eines geschlossenen
  Rings (`closed`, erster = letzter Wegpunkt) ist ein Knoten; innerhalb eines geschlossenen Rings und in
  einem geschlossenen Zug (letzter Punkt des Schichtpfads = erster, z. B. Fugenwand) wird zyklisch
  gemessen.
- Dichte Abtastung: Schritt min(2 mm, w/10), alle Originalpunkte bleiben erhalten.

## Regeln und Methoden

Konstanten mit (A) sind Annahmen und gehören in den SPEC-Nachtrag (`docs/muster/SPEC-NACHTRAG-MUSTER.md`).

| Regel | hart | Prüfung |
|---|---|---|
| M1 Durchgehend | ja | Je Schicht und Insel genau ein Schichtpfad (Inselzahl aus `part.stl`; Schichten aus dem toolpath und aus der Teilhoehe ceil(H/h) wie G3, eine fehlende Schicht hat also 0 Schichtpfade); ein Pfad über mehrere Inseln (über eine Öffnung) oder außerhalb jeder Insel ist ein Fehler. In der Trajektorie liegen zwischen dem ersten und dem letzten `print`-Sample der Ringe einer (Schicht, Insel) nur `print`/`link` dieser Ringe, also kein `retract`/`lift`/`transfer`/`lower`/`approach`. Die Ringe kommen dort in Druckreihenfolge des toolpath (Ringindex steigt, kein Rücksprung auf einen verlassenen Ring), und ein Wechsel `print`(Ring a) → `print`(Ring b) ohne `link` ist höchstens w lang (Verbinder der Länge 0); sonst läge bei laufender Pumpe eine Raupe quer über der Wand, die M6b je Ring nicht sieht. Pumpe = an genau in `print` und `link` (aus der Bewegungsart abgeleitet; DRL-Pumpenbefehle prüft G5). Ein `link` von Ring r − 1 nach r zwischen zwei Inseln derselben Schicht ist ein Fehler (Strang über die Öffnung, auch zwischen zwei sauberen Gruppen). Jeder Ring hat `print`-Samples. |
| M2 Kreuzungsfrei | ja | Alle Punktpaare mit Bogenabstand > 2·w und Abstand < (1 − ε)·w, ε = 0,15 (A), sind Fehler: Abstand < 1,5 Abtastschritte = `crossing`, sonst `too_deep` (zu tiefer Kontakt bzw. Überfahren einer gelegten Raupe derselben Schicht). Verbinder zählen mit, die Mittellinie einschließlich Verbinder muss also einfach sein. |
| Kontaktzonen | – | Paare mit Bogenabstand > 2·w und Abstand in [(1 − ε)·w, w + 0,5 mm] (A) sind gewollte Kontakte. Zusammenhängende Läufe entlang des Pfads werden paarweise zu Zonen mit Lage, Länge, kleinstem Abstand, Überlappung und Art zusammengefasst: `joint` (Segmentarten im Umkreis w beider Seiten nur `outfill`/`web`, mit `outfill`), `node` (nur `web`/`infill`), sonst `shell`. |
| M3 Überhangfrei | ja | Raupenfläche (Mittellinie ⊕ w/2, Schichtpfade vereinigt) von L + 1 minus Raupenfläche von L ⊕ δ, δ = 2 mm (A); Restfläche > 1 mm² ist ein Fehler. Grundsatz gleiche XY-Geometrie: Ist der Querschnitt von L und L + 1 gleich (symmetrische Differenz ≤ max(1 mm², 10⁻⁴·Fläche)), gilt dasselbe umgekehrt (Raupe von L in L + 1 ⊕ δ); eine schrumpfende bzw. unvollständige Schicht (z. B. oberste Schicht ohne Außenbahn) ist ein Fehler. Eine ganz leere Schicht meldet M1. Gegenbeispiel: größtes Reststück. |
| M4 Senkrechter Schichtwechsel | ja | Letzter Ring von L → erster Ring von L + 1: `link_next`, aufeinanderfolgende Indizes, waagrecht ≤ 0,5 mm (A) und, falls eine Trajektorie da ist, als `link` gefahren (nicht als Travel): Zwischen dem letzten `print` von L und dem ersten `print` von L + 1 liegen nur `print`/`link`-Samples und mindestens ein `link` (ein `link` mit anschließendem retract/lift/transfer/lower/approach ist ein Absetzen). Ausgenommen sind Wechsel mit Änderung der Inselzahl. Kennzahlen: Anteil senkrechter Wechsel gesamt und ohne Ausnahmen. Warnung (nicht hart) `n_seam_on_surface`: Naht ≤ w/2 + 1 mm neben dem Querschnittsrand (Sichtfläche, Laibung, Modulstoß). Bei `alternate` mit Schalen liegt jede zweite Naht am Anfang der Außenbahn und damit auf der Sichtfläche, das ist eine Eigenschaft der Schichtfolge. |
| M5 Im Teil | ja | Jeder Mittellinienpunkt (inkl. Verbinder) liegt in (Querschnitt ⊕ 1 mm) ⊖ w/2, d. h. die Raupenscheibe liegt im Querschnitt ⊕ 1 mm (A); damit auch nie über Öffnungen. Dasselbe gilt für die `link`-Samples der Trajektorie (Pumpe an) gegen die Schicht des Rings davor bzw. danach. Zusätzlich: Wegpunkthöhe = (L + 1)·h ± 0,5 mm. |
| M6 Krümmung | ja | Fenstermethode (siehe unten): Radius ≥ w/2 · (1 − tol) hart; < w · (1 − tol) ist eine Warnung (Ziel). tol je Punkt aus der längsten Originalsehne im Fenster: 0,5 % (A) bei feiner Abtastung bis 5 % (A) bei Sehnenfehler 0,5 mm. |
| M6b Trajektorie folgt toolpath | ja | Jedes `print`-Sample liegt ≤ 0,5 mm neben der dicht abgetasteten Ringpolylinie, jedes `link`-Sample ≤ 0,5 mm neben der Verbindergeraden; ein `link` nach Ring r ist nur erlaubt, wenn `toolpath.rings[r].link_next` true ist. Ersetzt den Sehnenfehler gegen die Sollkurve, die im Artefakt nicht steht. **Abdeckung:** Die `print`-Samples eines Rings (dazu das angrenzende `link`/`approach`/`retract`-Sample, wenn es auf Ringanfang bzw. -ende liegt) werden auf den Ring projiziert; ausgelassene Ringlänge (Δs − Sehne) zwischen zwei Samples, ein Rücksprung, ein fehlender Ringanfang bzw. -ende ein nicht ganz umlaufener oder mehr als einmal umlaufener geschlossener Ring (Summe der Bogenschritte ≠ L, zweite Runde über die frische Raupe) > 1 mm (A) ist ein Fehler (z. B. abgeschnittene Kehre bei laufender Pumpe). |
| M7 Kontakt | nein (Bericht) | Kontaktzonen je Schicht und je Meter Wand (Wandlänge = längste Grundrisskante von `part.stl`), getrennt nach Art, Kontaktlänge je Meter, Zonen der ersten Schicht mit Lage und Überlappung. |

### Krümmung (M6), robuste Fenstermethode

Die Mittellinie des Schichtpfads wird gleichabständig (Schritt min(1 mm, w/30)) neu abgetastet. Je
Punkt p(s) ist der Radius der Umkreis von p(s − a), p(s), p(s + a) mit a = w/2. Für Punkte auf einem
Kreis liefert das dessen Radius unabhängig von der Abtastdichte der Eingabe; Polylinien mit Sehnenfehler
≤ 0,5 mm (Sehne bis ≈ 7,7 mm bei r = 15 mm) weichen um höchstens ≈ 4 % ab. Die Toleranz hängt deshalb
von der längsten Originalsehne c im Fenster ab: e = c²/(8·r_ref), S = r_ref·(1 − cos(a/r_ref)),
tol = 0,5 % + 1,15·e/S, höchstens 5 % (`rules.radius_tolerance`). Ein fein abgetasteter Bogen
(Sehne ≤ 2 mm) wird damit auf ≈ 1 % genau geprüft (r = 14,85 mm und 14,6 mm sind rot); nur eine grobe,
aber noch zulässige Polylinie bekommt die vollen 5 %.
Ein Knick mit Ablenkung φ ergibt a / (2 sin(φ/2)), eine Umkehr 0. Offene Schichtpfade werden ohne die
Enden (a) ausgewertet, geschlossene Züge zyklisch (die Naht wird mitgeprüft).

Grenzen: Ein Bogen, der kürzer ist als das Fenster 2a, wird geglättet (eine Viertelkehre mit r = 5 mm
ergibt ≈ 11,6 mm, ist aber trotzdem rot). Ein scharfer Knick mit Ablenkung ≤ ≈ 63° liegt bei w = 30 mm
nicht unter der harten Grenze; das Ziel ≥ w meldet ihn ab ≈ 29° als Warnung.

### Kennzahlen

- `longest_straight_unsupported_outer_mm`: Punkte der Arten `outer`/`outfill` im Abstand 5 mm; gestützt
  ist ein Punkt, an dem ein Punkt der Arten `infill`/`web` ≤ w + 0,5 mm entfernt liegt. Ein gerader
  Abschnitt wächst, solange alle Punkte ≤ 1 mm (A) neben der Sehne liegen und keiner gestützt ist.
  Felder der Fugenwand enden an der Fuge, weil die Bahn dort kehrt.
- `joint_spacing_mm`: Mittelpunkte der `joint`-Zonen je Schicht, je Wandseite (Vorzeichen der
  Querkoordinate zum Schwerpunkt der Bahn) entlang der Wandachse sortiert; Abstand benachbarter Fugen.
- `path_length_mm_per_layer` (min, max, Mittel) und je Schicht `path_length_mm` (inkl. Verbinder in
  der Schicht), `contact_zones`, `contact_zones_by_type`, `contact_length_mm`, `n_islands`, `n_paths`.
- `share_vertical_layer_change` (M4), `min_radius_mm` (M6), `contact_zones_per_m` (M7).

## Teile ohne Muster (heutiges Format)

Das Orakel stürzt nicht ab und prüft M1–M7 genauso; das Ergebnis ist ein Bericht. Erwartet und belegt
(Selbsttest `test_todays_format_is_reported_without_crash`, dazu ein echter S1-Lauf mit 6 Schichten):
M1, M3 und M5 sind grün; M4 ist rot (gleiche Schichtfolge, diagonaler Verbinder zur nächsten Schicht),
M6 ist rot (Mitre-Ecken, Fensterradius ≈ 7,6 mm), und M2 kann am diagonalen Verbinder vom Außen- zum
Innenring rot sein (er schneidet die Ecke der Außenraupe: Abstand ≈ 23 mm bei Bogenabstand ≈ 60 mm).
Außen- und Innenschale berühren sich auf ganzer Länge: Das ergibt `shell`-Kontaktzonen.

Für G9 wird deshalb vorgeschlagen, das Orakel nur auf Teile mit Musterparametern (Szenario
`params.layer_order`/`infill_pattern`/`outfill_pattern`) hart anzuwenden und für die übrigen nur zu
berichten. `has_pattern_kinds` im Bericht zeigt, ob der toolpath Musterarten (`infill`, `web`,
`outfill`) enthält.

## Laufzeit

Gemessen auf der Cloud-VM (ein Kern): echter S1-Lauf (40 Schichten, 80 Ringe, 18 MB Trajektorie) ≈ 3 s
je Teil; synthetische Fugenwand mit 40 Schichten (680 Ringe) ≈ 4 s. Der Bericht nennt `runtime_s` je Teil.

## Grenzen und offene Punkte

- Ob ein Kontakt gewollt ist, kennt das Orakel nicht: Ein Steg, der die Schale um mehr als 0,5 mm
  verfehlt, ist kein Fehler, er fehlt nur in den Kontaktzonen (M7). Ein Soll-Kontaktplan im Artefakt
  (z. B. `pattern.contacts`) würde das prüfbar machen.
- M2 bewertet Punktpaare der dichten Abtastung; der gemessene Abstand ist nie kleiner als der wahre,
  höchstens um ≈ Schritt²/(8r) größer (≤ 0,1 mm). Kreuzungen innerhalb von 2·w Bogenabstand sind nur
  mit Radien < w/2 möglich und fallen dann unter M6.
- M3 vergleicht nur benachbarte Schichten und rechnet die Raupe als Mittellinie ⊕ w/2 (keine
  Raupenverformung).
- Die Art einer Kontaktzone folgt aus den `kind`-Werten; ein `web`, der ein `outfill`-Feld mitten im
  Feld berührt (O3), zählt als `joint`.
- Die Pumpe wird aus den Bewegungsarten abgeleitet, nicht aus dem DRL (das prüft G5 mit `fake_drcf`).

## Dateien

| Datei | Zweck |
|---|---|
| `check.py` | CLI, Bericht, Exit-Code |
| `artifacts.py` | Artefakte lesen, nach P rechnen |
| `geometry.py` | Querschnitt, Inseln, Schichtpfad, Bogenabstand, Fensterradius, gerade Abschnitte |
| `contacts.py` | Paaranalyse: Kreuzung, zu tiefer Kontakt, Kontaktzonen |
| `rules.py` | M1–M6, M6b |
| `metrics.py` | M7 und Kennzahlen |
| `tests/synth.py` | synthetische Laufordner (toolpath, trajectory, part.stl über trimesh, gedrehte T_WP) |
| `tests/synth_fugen.py` | Fugenwand nach Foto als geschlossener Zug („Riemen um Rollen“, Kontakte exakt einstellbar) |
| `tests/test_rules.py`, `tests/test_cases.py` | gültige Fälle, Gegenbeispiele, Grenzfälle, Methodentests |

Selbsttests – gültig: zwei Schalen alternierend mit senkrechtem Wechsel; Sinus-Infill mit Kontakten;
Fugenwand mit Feldern, Fugenkontakt, V-Stegen, Doppelknoten und Gurtkontakt als ein geschlossener Zug je
Schicht; zwei Inseln mit je eigenem Strang. Gegenbeispiele: Kreuzung, Überhang, diagonaler
Schichtwechsel, Schichtwechsel als Travel, Lücke im Strang (Trajektorie und toolpath), Druck außerhalb
des Teils, zu enger Radius, Druck über einer Öffnung, zu tiefer Kontakt an Fuge und Knoten, Trajektorie
neben dem toolpath, abgeschnittene Kehre und Rücksprung bei laufender Pumpe (Abdeckung M6b), fehlende
oberste Schicht, leerer toolpath. Grenzfälle knapp über/unter: Kontakt genau 25,5 mm gültig, 25,45/25/24 mm
zu tief (Schwelle 25,5), 26 mm gültig; Versatz 0,4/0,6 mm (0,5); Überstand als ebenes Plateau
1,5/1,9/2,1/2,5 mm (δ = 2; die Gauß-Beule auf der steilen Sinusflanke ist normal zur Bahn nur ≈ 1/2,3 mm
und kein exakter Grenzfall); Überstand über das Teil 0,8/1,3 mm (1); Radius fein 15/14,85/14,6/14 mm und
grob (Sehne 7,7 mm) 15/14 mm (w/2). Ein AST-Test stellt sicher, dass kein Modul `roboprint`, `verify` oder
`core` importiert.
