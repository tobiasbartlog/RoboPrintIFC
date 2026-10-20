# SPEC-Nachtrag „Druckmuster“ (Vorschlag, einfügefertig)

Stand 21.10.2026, Nachtlauf „Druckmuster“, Aufgabe M3.3. `spec/` und `verify/` sind gesperrt; dieser
Nachtrag ist der Text, den der Nutzer nach Freigabe in `spec/SPEC.md` und `spec/ARTEFAKTE.md`
einfügt. Jeder Block nennt seinen Einfügeort. Werte mit **A** sind Annahmen, die der Nutzer
bestätigen muss. Grundlagen: `docs/muster/AUFTRAG.md` (Musterregeln, Nachtrag 18:20),
`docs/muster/ARTEFAKT-FORMAT.md` (Vertrag), `verify_muster/README.md` (Orakel),
`docs/muster/fugenwand.md`, `docs/muster/topologie.md`, `docs/muster/wellen.md`,
`docs/muster/mehrfach.md`, Belege in `MUSTER-PROGRESS.md` (Gate-Einwände).

Grundsatz für alle Blöcke: **Muster sind opt-in.** Fehlen alle Musterparameter, gelten §5.1–§5.6,
§6, §10 und §11 unverändert; S1–S3 bleiben bitgleich (Toolpath sha256, Trajektorie, DRL bis auf
die Provenienzzeile), G1–G8 bleiben, wie sie sind.

---

## Block 1: neuer §5.7 „Muster“ (nach §5.6 einfügen)

### 5.7 Muster (`patterns`, opt-in)

*Nutzerauftrag 20.10.2026 mit Nachtrag 18:20:* Wandmodule können mit einem **Druckmuster**
gedruckt werden: Infill im Hohlraum zwischen den Innenschalen, Outfill als gegliederte Außenhaut
mit Sollbruchstellen (Fugenwand) oder ein Muster, das den ganzen Inselpfad baut. Ziel: je Schicht
und Insel **ein durchgehender Strang** ohne Absetzen, ohne Kreuzung, ohne Überhang, mit
**senkrechtem Schichtwechsel**.

**Begriffe.**
- *Segment*: Polylinie in Frame P mit `kind` ∈ {`outer`, `inner`, `hole`, `infill`, `web`,
  `outfill`}, offen oder geschlossen. `infill` = Muster im Hohlraum, `web` = Quer- oder Schrägsteg,
  `outfill` = gegliederte Außenhaut bzw. Endkappe.
- *Schichtpfad*: geordnete Folge der Segmente einer Schicht und Insel. Zwischen zwei Segmenten liegt
  ein Verbinder nach §5.3, im Muster meist mit waagrechter Länge 0 (Segmente stoßen aneinander).
- *Kontakt*: gewollte Berührung zweier Raupen derselben Schicht, Mittellinienabstand in
  [(1 − ε)·w, w], bei Bogenabstand > 2·w. Arten: `joint` (Fuge, Außenfeld an Außenfeld bzw. Steg),
  `node` (Knoten zwischen Stegen bzw. Gurt), `shell` (Infill oder Steg an einer Schale).
- *Naht*: Anfang und Ende des Schichtpfads; dort liegt der Schichtwechsel.

**Schichtfolge.** `layer_order = alternate` (Standard bei Mustern): Schicht L + 1 ist die exakte
Umkehrung von Schicht L (gleiche XY-Geometrie, Segmente in umgekehrter Reihenfolge, Punkte jedes
Segments umgekehrt). Gerade Schichten laufen außen → innen, ungerade innen → außen. Der
Schichtwechsel ist damit ein reiner Z-Hub um h am selben XY-Punkt. Ändert sich der Querschnitt
(Öffnung, Schräge), beginnt der Pfad neu (`restart`); ob dann ein Verbinder oder ein Travel folgt,
entscheidet §5.3. `layer_order = same` ist das heutige Verhalten und mit Muster nur zum Vergleich
erlaubt (M4-Fehler).

**Musterregeln M1–M7** (gelten für jede Schicht jedes Teils mit Muster; Prüfung siehe G9):
- **M1 Durchgehend.** Je Schicht und zusammenhängender Querschnittsinsel genau ein Schichtpfad.
  In der Trajektorie liegen zwischen dem ersten und dem letzten `print` einer (Schicht, Insel) nur
  `print` und `link` dieser Ringe; Pumpe an genau in `print`/`link`. Inseln (Pfeiler neben einer
  Öffnung) haben je einen eigenen Strang; ihre Zahl ist minimal.
- **M2 Kreuzungsfrei.** Die Mittellinie einschließlich der Verbinder schneidet sich nicht. Zwei
  Punkte mit Bogenabstand > 2·w haben Abstand ≥ (1 − ε)·w, ε = 0,15 (**A**). Kein Pfadstück
  fährt über eine Raupe derselben Schicht.
- **M3 Überhangfrei.** Raupenfläche (Mittellinie ⊕ w/2) von L + 1 ⊆ Raupenfläche von L ⊕ δ,
  δ = 2 mm (**A**), Restfläche ≤ 1 mm² (**A**). Ändert sich der Querschnitt innerhalb eines Teils,
  muss jede neue Kante der höheren Schicht auf Raupen der tieferen stehen: Querstege an allen
  künftigen Laibungen, bestimmt aus dem ganzen Teil.
- **M4 Senkrechter Schichtwechsel.** Ende von L und Anfang von L + 1 liegen waagrecht ≤ 0,5 mm
  (**A**) auseinander, verbunden mit `link_next = true` und in der Trajektorie als `link` gefahren.
  Ausgenommen sind Wechsel, an denen sich die Inselzahl ändert (dort §5.3).
- **M5 Im Teil.** Die Raupenfläche liegt im Querschnitt ⊕ 1 mm (**A**); nie außerhalb des Teils,
  nie über Öffnungen. Outfill bleibt in der IFC-Wanddicke. Wegpunkthöhe (L + 1)·h ± 0,5 mm.
- **M6 Druckbar gekrümmt.** Krümmungsradius der Mittellinie hart ≥ w/2, Ziel ≥ w (**A**,
  Unterschreitung des Ziels ist eine Warnung). Sehnenfehler der Polylinie gegen die Sollkurve
  ≤ 0,5 mm (**A**). Im Artefakt steht keine Sollkurve; prüfbar ist deshalb **M6b**: jedes `print`-
  Sample ≤ 0,5 mm neben dem Ring, jedes `link`-Sample ≤ 0,5 mm neben der Verbindergeraden, keine
  ausgelassene Ringlänge > 1 mm (**A**).
- **M7 Kontakt.** Infill und Stege berühren Schalen bzw. einander mit Überlappung 0 … ε·w.
  Anzahl und Länge der Kontaktzonen je Meter Wand werden berichtet (kein hartes Kriterium).

**Naht (M4).** Der Kern legt die Naht auf den Außenring an die Stelle mit dem größten Freiabstand
der Raupenkante zu den geschützten Flächen (Außenflächen y_min/y_max und Stoßflächen x_min/x_max
des Teils), bei Gleichstand an die Ecke nächst (x_min, y_min) (`seam_corner`). Beim Grundmuster
ist das die Mitte eines Eckbogens (Freiabstand 8,8 mm bei r = w = 30 mm). Begründung: Der
Materialpunkt des Z-Hubs liegt dann weder auf der Sichtfläche noch auf der Stoßfläche zum
Nachbarmodul, und der Eckbogen ist ohnehin keine ebene Fläche. Bei der Fugenwand liegt die Naht im
Inneren (Gurt bzw. Knoten), bei `topologie` wird jeder Nahtkandidat auf Flächenabstand geprüft.
Grenze: Bei `alternate` mit Schalen endet jede zweite Schicht am Anfang der Außenbahn; das Orakel
zählt Nähte ≤ w/2 + 1 mm neben dem Rand als Warnung (`n_seam_on_surface`).

**Grundmuster „Schalen“ (Preset `schalen`).** Alle Schalen einer Insel als ein Strang. Der
Schalenwechsel ist eine S-Kurve aus zwei Bögen mit Radius w ohne Doppelmaterial; Ecken gerundet
mit `corner_radius_mm` (Standard w).

**Fugenwand (Outfill O2, Sollbruchstellen, Foto `docs/muster/referenz/fugenwand-foto.jpg`).**
Die Außenhaut besteht aus geraden Feldern (`outfill`) der Länge F. An jeder Feldgrenze stoßen zwei
Felder stumpf aneinander: senkrechte Fuge über die ganze Höhe (Kontakt `joint`, keine
durchlaufende Raupe). Von jeder Fuge laufen Schrägstege (`web`) V-förmig nach innen zu Knoten
(`node`); mit Gurt verbindet ein Gurtstück (`infill`) in der Wandmitte die Knoten. Endkappen
(`outfill`) schließen an den Modulenden zur Gegenseite. Je Schicht entsteht ein geschlossener
Zug, also ein senkrechter Schichtwechsel. Varianten: Rautenkette ohne Gurt mit Rückseite um F/2
versetzt (Empfehlung des Katalogs), Gurt mit Rückseite gespiegelt (durchgehende Sollbruchebene),
Gurt versetzt. Modullänge wird in eine ganze Zahl gleicher Felder geteilt (`fit_to_length`), die
tatsächliche Länge steht in `toolpath.pattern` bzw. in der Vorschau. Mindestdicke für Gurtvarianten
mit Hakenradius w: 230 mm; bei 200 mm verkleinert der Kern den Hakenradius auf 21 mm (M6-Warnung).

**Öffnungen (Muster `topologie`).** Ein Strang je Insel. Die Pfeilerbahnen über der Brüstung laufen
in den Brüstungsschichten schon mit; ihre Laibungsschenkel sind dort Querstege (`web`) an den
künftigen Laibungen. Damit steht jede Pfeilerraupe auf einer Raupe darunter (M3, 0 mm²
Überhang). Grenzen: ein oder zwei Randpfeiler je Teil (kein Mittelpfeiler), Pfeiler ≥ 151 mm,
Wand ≥ 150 mm, `shells = 2`; je Laibung entsteht eine Fuge auf einer Wandseite. Prismatische
Muster (Fugenwand, Wellen) sind über einer Brüstung nicht überhangfrei (M3) und deshalb für Teile
mit Öffnung nicht zulässig (Beleg: S5_muster_oeffnung_fugenwand).

**Infill-Familien.** `sinus`, `zickzack` (Scheitelradius w), `trapez` (Plateaus an den Schalen),
`maeander` (senkrechte Flanken) mit Wellenlänge, Phase und Kontaktüberlappung; Kontakt an beiden
Innenschalen. `doppelwelle` und `waben` brauchen ein Infill-Band ≥ 55,5 mm, also bei zwei Schalen
eine Wand ≥ 206 mm (bei 200 mm entfällt der Infill mit Hinweis in `meta.infill.skipped`).
`fermat` (Connected Fermat Spiral) für kleine Inseln (Pfeiler).

**Planer (Ergänzung zu §5.2/§5.3).**
- Verbinder der Länge 0 in derselben Schicht sind gültige Verbinder (ein `link`-Sample am Ringende).
  Der senkrechte Schichtwechsel ist ein Verbinder mit Z-Hub um h (3 bis 6 `link`-Samples).
- Bei einem Verbinder ohne waagrechte Länge (≤ 0,5 mm) behält der Folgering die Drehung ψ der Düse
  (`psi_hold`); sonst würde sich die Düse (TCP 134 mm neben der Flanschachse) mit laufender Pumpe auf
  der Stelle drehen. Geht das nicht, ist eine Drehung auf der Stelle erlaubt und wird im DRL als Halt
  mit `radius = 0` ausgegeben (Warnung im Bericht).
- Die schnelle Kollisionsnäherung kennt bei Teilen mit Muster zusätzlich das Paar Werkzeugkörper ↔
  `link_4` (Oberkante S1 mit `alternate`). Ohne Muster bleibt sie unverändert.

**DRL (Ergänzung zu §5.6).** Ein Verbinder der Länge 0 fällt mit dem Ringende zusammen und ist dessen
Ziel (kein Segment der Länge 0), aber nur bei gleicher Orientierung. Der Ringkommentar nennt den
Verbinder („über Verbinder, senkrecht, Z +10.0 mm“ bzw. „Länge 0“). `movesx` (v3) bleibt Strängen
aus einem Ring mit ≤ 100 Zielen vorbehalten; Musterstränge sind `movel` mit Blending.

---

## Block 2: Ergänzung §10 „Parameter und Annahmen“ (Tabelle am Ende anhängen)

Alle Musterparameter sind opt-in. Fehlen sie, gilt das heutige Verhalten.

| Parameter | Wert | |
|---|---|---|
| layer_order | `alternate` bei Mustern, sonst heutige Folge (`same`); ausdrücklich gesetzt gilt es auch gegen das Preset | A (Empfehlung: Standard `alternate` erst nach Testdruck) |
| infill_pattern, outfill_pattern | `none` \| Mustername aus `patterns.catalog()` (`sinus`, `zickzack`, `trapez`, `maeander`, `doppelwelle`, `waben`; Rolle `full`: `fugenwand`, `schalen`, `topologie`, `fermat`) | Nutzer wählt |
| pattern_preset | Pfad zu einem Preset-JSON relativ zum Repo (`core/src/roboprint/patterns/presets/*.json`, `docs/muster/presets/*.json`); Rangfolge Preset → abweichende Szenariowerte → `pattern_params` | |
| pattern_params | Objekt mit Musterparametern (Namen aus den ParamSpecs) | |
| ε (Kontakt-/Kreuzungstoleranz) | 0,15 · w (Kontakt bei (1 − ε)·w … w) | A |
| δ (Überhang-Toleranz M3) | 2 mm, Restfläche ≤ 1 mm² | A |
| senkrechter Schichtwechsel (M4) | waagrecht ≤ 0,5 mm | A |
| Toleranz im Teil (M5) | Querschnitt ⊕ 1 mm | A |
| Krümmungsradius (M6) | hart ≥ w/2 = 15 mm, Ziel ≥ w = 30 mm | A |
| Sehnenfehler (M6) | ≤ 0,5 mm; Abtastung Δs ≤ `step_mm` = 20 mm | A |
| corner_radius_mm | w (30 mm); 22,5 mm hebt die Abdeckung des Grundmusters auf 600 × 200 von 94,4 % auf 95,5 % (M6-Warnung) | A |
| transition_radius_mm | w (S-Kurve des Schalenwechsels) | A |
| field_length_mm (Fugenwand) | 300 mm Fugenabstand je Seite (Recherche: 160–300 mm) | A |
| belt, back_offset (Fugenwand) | Empfehlung: ohne Gurt, `versetzt` (Rautenkette) | A |
| hook_radius_mm (Fugenwand) | 0 = Eckradius; bei Gurt auf 200 mm Wand 21 mm | A |
| joint_gap_mm (Fugenwand) | 0 (stumpfe Fuge, Raupen berühren sich) | A |
| wavelength_mm (Wellen) | 250 mm, Phase 0°, Kontaktüberlappung 5 % von w | A |
| Mindestdicke mit Öffnung (`topologie`) | 150 mm, Randpfeiler ≥ 151 mm | |

---

## Block 3: Ergänzung §11 „Abnahme-Gates“

**Neue Zeile in der Gate-Tabelle:**

| Gate | Prüft | Kriterium |
|---|---|---|
| **G9 Muster** | `python scripts/verify_muster.py`: jedes Szenario in `docs/muster/szenarien/` (S4, S5) wird gerechnet und vom unabhängigen Orakel `verify_muster/` (importiert `roboprint` nie) sowie von `verify/check_run.py` und `verify/fake_drcf` geprüft | Für Szenarien mit `expect.muster.machbar = true`: alle Teile `machbar`; alle G3-Kriterien außer der Abdeckung (siehe unten); G5 für `program.v2.drl` und `program.v3.drl`; M1–M6 und M6b hart, M7 berichtet. Für `machbar = false` („belegt nicht machbar“): der Lauf läuft durch und `verify_muster` scheitert mindestens an den belegten Regeln `expect.muster.erwartete_regeln`. Bericht `runs/verify_muster/report.json` mit machbar, d_min, Strängen je Schicht, Anteil senkrechter Schichtwechsel, Druckzeit und Planerlaufzeit je Szenario. |

**Abdeckungsregel bei Mustern (Vorschlag, ersetzt für Teile mit Muster den Satz zur Abdeckung in G3
und G4):** „Teile ohne Musterparameter: Abdeckung je Schicht ≥ 95 % des Schalenbereichs. Teile mit
Musterparametern: Die Abdeckung wird berichtet, nicht bewertet. An ihre Stelle treten M3
(überhangfrei) und M5 (im Teil) aus G9 sowie eine Untergrenze für den Schalenbereich der
**Außenfläche**: Die Raupenfläche deckt jede Außenfläche (y_min, y_max) außerhalb der Fugen
(Fugenbreite ≤ w) zu ≥ 95 % ihrer Länge in der Tiefe w/2 ab (**A**).“

Begründung (Belege in `MUSTER-PROGRESS.md`, Gate-Einwand 1): Die heutige Regel misst die
Raupenfläche gegen „Querschnitt minus Innenpuffer 2·w“. Gerundete Ecken (M6) und der Zwickel am
Schalenwechsel kosten beim Grundmuster 5,6 % (94,4 % auf 600 × 200), die Fugenwand deckt gewollt
nur 60–89 % ab, weil Stege schräg nach innen laufen und Fugen keine durchlaufende Raupe haben.
Gemessen auf dem S1-Quader (Runner, Tabelle unten): Schalen 94,4 %, Sinus 94,6 %, Fugenwand-Raute
64,6 %. Keine dieser Lücken ist ein Druckfehler; die Regel misst Füllung, nicht Tragfähigkeit.
Alternative ohne Regeländerung: `corner_radius_mm = 22,5` für `schalen` (95,5 %, M6-Warnung); für
die Fugenwand gibt es keine Alternative.

**Ergänzung G5 (Vorschlag):** G5 prüft zusätzlich die DRL-Programme aller G9-Szenarien.

**Ergänzung `scripts/verify.py` (Vorschlag):** G9 als langsames Gate (nicht in `--fast`), mit
`--fast` des Runners (Szenarien mit `expect.muster.fast = true`) im Schnelllauf.

---

## Block 4: Szenarien (Ergänzung §7 bzw. `spec/scenarios/`)

Die Szenarien liegen heute in `docs/muster/szenarien/` und ziehen bei Freigabe nach
`spec/scenarios/`. Alle S4 sind der S1-Quader (600 × Dicke × 400 mm, Standard-Druckplatz (0, −50)
mm, `collision_aware`) mit einem Preset. `expect` trägt neben `parts` das Objekt `muster`
{`machbar`, `fast`, `preset`, bei `machbar = false` zusätzlich `erwartete_regeln` und `beleg`}.

| Szenario | Dicke | Muster (Preset) | Erwartung | fast |
|---|---|---|---|---|
| S4_muster_schalen_alternate | 200 | `schalen` (2 Schalen, alternate) | machbar | ja |
| S4_muster_fugenwand_raute | 200 | `fugenwand_raute` (Empfehlung) | machbar | ja |
| S4_muster_fugenwand_gurt | 200 | `fugenwand_gurt` (Haken 21 mm) | machbar | |
| S4_muster_fugenwand_gurt_300 | 300 | `fugenwand_gurt` (Haken w) | machbar | |
| S4_muster_fugenwand_versetzt | 200 | `fugenwand_versetzt` | machbar | |
| S4_muster_sinus | 200 | `sinus` | machbar | ja |
| S4_muster_zickzack | 200 | `zickzack` | machbar | |
| S4_muster_trapez | 200 | `trapez` | machbar | |
| S4_muster_maeander | 200 | `maeander` | machbar | |
| S4_muster_fermat | 200 | `fermat` | machbar | |
| S4_muster_doppelwelle_300 | 300 | `doppelwelle` | machbar | |
| S4_muster_waben_300 | 300 | `waben` | machbar | |
| S5_muster_oeffnung | 200 | `topologie` (Laibungsstege) | machbar | ja |
| S5_muster_oeffnung_fugenwand | 200 | `fugenwand_raute` | belegt nicht machbar (M3) | |

Nicht als Szenario: `doppelwelle` und `waben` auf 200 mm (Band 50 mm < 55,5 mm, der Infill entfällt;
der Lauf wäre das Grundmuster) und `topologie` auf dem Quader (prismatisch identisch mit `schalen`).

**S5 (Modul mit Öffnung).** `examples/Building-Architecture.ifc` (S2) enthält keine Öffnung: kein
`IfcOpeningElement`, `IfcWindow` oder `IfcDoor`, `read_walls` liefert für alle vier Wände
`openings = []`; der einzige Querschnittswechsel in S2 ist die 45°-Schräge am Wandkopf. S5 nimmt
deshalb eine synthetische Wand wie die S2-Außenwände: `docs/muster/szenarien/S5_fensterwand.ifc`
(erzeugt von `scripts/muster_s5_ifc.py`, feste GlobalIds), 600 × 200 × 400 mm, Fenster x = 180 …
420 mm, Brüstung bis z = 150 mm, Sturz z = 400 mm. Das ist das untere Modul einer höheren Wand mit
Sturz bei 400 mm (die Zerlegung schneidet an der Sturzlinie, §5.4/2). Die Zerlegung ergibt genau
ein Modul: Schichten 0–14 voller Querschnitt (Brüstung), ab Schicht 15 zwei Inseln (Pfeiler je
180 mm). Gewählt, weil es beide Fälle von M1/M3 enthält: Inselwechsel (zwei Stränge ab Schicht
15) und künftige Laibungen über der Brüstung.

---

## Block 5: Ergänzung `spec/ARTEFAKTE.md` (neuer Abschnitt „Druckmuster“ am Ende)

### Druckmuster (opt-in, SPEC §5.7)

Ohne Musterparameter bleiben alle Dateien bitgleich zu heute. Mit Muster gilt zusätzlich:

**toolpath.json**
- `kind` ∈ {`outer`, `inner`, `hole`, `infill`, `web`, `outfill`}.
- `closed = false` ist erlaubt (offenes Segment, ≥ 2 Wegpunkte); dann gleicht der letzte Wegpunkt
  nicht dem ersten. `closed = true` genau dann, wenn der letzte Wegpunkt den ersten trifft
  (≤ 10⁻⁶ mm, dann exakt gleich gesetzt).
- Ein Schichtpfad je Schicht und Insel ist eine Folge aufeinanderfolgender Ringe derselben Schicht,
  alle mit `link_next = true` verbunden. Stoßen zwei Segmente **gleicher** `kind` aneinander, sind
  sie ein Ring; Segmente verschiedener `kind` bleiben eigene Ringe mit einem Verbinder der Länge 0.
  `shell` ist die Schale des ersten Segments eines Rings (Infill und Stege: `shell = shells`).
- Senkrechter Schichtwechsel: letzter Ring von L und erster Ring von L + 1 mit `link_next = true`,
  Endpunkt bzw. Startpunkt waagrecht ≤ 0,5 mm auseinander.
- Optional auf oberster Ebene `pattern` = {`layer_order`, `infill`, `outfill`, `params`} (Schema
  `ToolpathPattern`), nur bei Teilen mit Muster; ohne Muster fehlt der Schlüssel. Prüfer dürfen
  es zur Beschriftung lesen, geprüft wird nur die Geometrie.

**trajectory.json** unverändert. Ein Verbinder der Länge 0 in der Schicht ist ein `link`-Sample am
Ringende (Ablaufregel „mindestens ein `link`-Sample“), der senkrechte Schichtwechsel 3 bis 6
`link`-Samples auf der Senkrechten. Ein Muster ist über alle Ringe und Schichten ein Strang (bei
mehreren Inseln je Insel einer).

**summary.json** `params` führt die Musterparameter nur, wenn sie gesetzt sind (`pattern_params` als
JSON-Text, damit `params` skalar bleibt); `assumptions` bekommt dann die Zeile „Druckmuster (opt-in,
A): Schichtfolge …, Infill …, Outfill …, Parameter …“.

**DRL** Kopfblock „A Schichtfolge / A Muster / A Muster-Preset / A Musterparameter“ (aufgelöst aus
`toolpath.pattern`). Ringkommentar mit Verbinderart.

**Szenario** `params` erlaubt opt-in `layer_order` (`same` | `alternate`), `infill_pattern`,
`outfill_pattern` (`none` | Mustername), `pattern_preset` (Pfad), `pattern_params` (einziges
Objekt in `params`), `shells`. Unbekannte Muster oder widersprüchliche Kombinationen (z. B. ein
`full`-Muster plus Infill) sind ein Fehler beim Start.

**Musterbericht** `runs/verify_muster/report.json`: `all_green`, `rules`, `scenarios[]` mit `name`,
`status` (`gruen`/`rot`), `verdict`, `feasible`, `d_min_mm`, `strands_per_layer`,
`vertical_layer_change_share`, `print_time_s`, `planner_runtime_s`, `runtime_s`, `g3`,
`g3_abdeckung` (`gruen`/`einwand`), `g5`, `muster`, `metrics`, `checks`, `steps`. Je Lauf schreibt
`verify_muster.check` `check_muster.json` (Format `verify_muster/README.md`).

---

## Ergebnis des Runners (M3.3)

<!-- ERGEBNIS:BEGIN -->
Lauf vom 20.10.2026, 20:50–21:45, `python scripts/verify_muster.py` in zwei Teilläufen (3 + 11
Szenarien, `--jobs 2`, VM mit anderen Agenten geteilt, Last 7–15; Zeiten schwanken deshalb um
±50 %), Bericht zusammengeführt in `runs/verify_muster/report.json`: **alle 14 Szenarien grün**
(13 machbar wie erwartet, 1 belegt nicht machbar wie erwartet).

| Szenario | Ergebnis | d_min mm | Stränge je Schicht | senkrechte Wechsel | Druckzeit s | Planer s | Lauf s | G3 ohne Abdeckung | Abdeckung min | G5 | M1–M7 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S4_muster_schalen_alternate | machbar | 10,83 | 1 | 39/39 (100 %) | 1032 | 92,7 | 97,4 | grün | 94,4 % (Einwand) | grün | grün |
| S4_muster_fugenwand_raute | machbar | 10,83 | 1 | 39/39 | 979 | 250,4 | 258,3 | grün | 64,6 % (Einwand) | grün | grün |
| S4_muster_fugenwand_gurt | machbar | 10,83 | 1 | 39/39 | 1431 | 55,6 | 61,7 | grün | 88,6 % (Einwand) | grün | grün |
| S4_muster_fugenwand_gurt_300 | machbar | 10,83 | 1 | 39/39 | 1543 | 100,7 | 106,6 | grün | 62,7 % (Einwand) | grün | grün |
| S4_muster_fugenwand_versetzt | machbar | 10,83 | 1 | 39/39 | 1424 | 87,0 | 92,5 | grün | 88,1 % (Einwand) | grün | grün |
| S4_muster_sinus | machbar | 10,83 | 1 | 39/39 | 1250 | 106,0 | 111,2 | grün | 94,6 % (Einwand) | grün | grün |
| S4_muster_zickzack | machbar | 10,83 | 1 | 39/39 | 1248 | 45,1 | 50,3 | grün | 94,6 % (Einwand) | grün | grün |
| S4_muster_trapez | machbar | 10,83 | 1 | 39/39 | 1259 | 49,2 | 54,3 | grün | 94,6 % (Einwand) | grün | grün |
| S4_muster_maeander | machbar | 10,83 | 1 | 39/39 | 1275 | 47,6 | 52,8 | grün | 94,6 % (Einwand) | grün | grün |
| S4_muster_fermat | machbar | 10,83 | 1 | 39/39 | 1423 | 51,3 | 57,4 | grün | 95,5 % | grün | grün |
| S4_muster_doppelwelle_300 | machbar | 10,83 | 1 | 39/39 | 1619 | 63,1 | 69,1 | grün | 95,3 % | grün | grün |
| S4_muster_waben_300 | machbar | 10,83 | 1 | 39/39 | 1693 | 58,3 | 64,9 | grün | 95,3 % | grün | grün |
| S5_muster_oeffnung (`topologie`) | machbar | 10,83 | 1–2 (= Inseln) | 38/39 (1 Inselwechsel, ausgenommen) | 1016 | 52,6 | 138,5 | grün | 77,0 % (Einwand) | grün | grün |
| S5_muster_oeffnung_fugenwand | belegt nicht machbar (M3) | 10,83 | 1–2 | 38/39 | 946 | 43,6 | 134,9 | grün | 64,6 % (Einwand) | grün | rot: M3, 16 429 mm² Überhang in Schicht 15 über Schicht 14 |

Anmerkungen:
- „Planer s“ = `summary.timings_s.plan` (bei S5 Summe der Teilzeiten `<teil>.plan`; die Zerlegung
  braucht dort zusätzlich ≈ 130 s). „Lauf s“ = Wanduhr von `run-scenario`. Ein früherer Probelauf
  von S5_muster_oeffnung unter Last 15 brauchte 919 s, davon 535 s in der Abschlussprüfung
  (`plan_final_check`); im Runner 138,5 s. Die Streuung kommt aus der Last bzw. einer Nachplanung,
  nicht aus dem Muster; eine Laufzeitgrenze ist für G9 deshalb nicht vorgeschlagen.
- d_min = 10,83 mm in allen Läufen, gleich wie S1 ohne Muster: Die engste Stelle liegt nicht im
  Musterpfad. Der unabhängige Prüfer bestätigt d ≥ 10,00 mm (untere Schranke).
- S5: Die Brüstung (Schichten 0–14) ist ein Strang; ab Schicht 15 je Pfeiler ein Schichtpfad
  (2 Stränge je Schicht, 27 Stränge im Teil). Der eine nicht senkrechte Wechsel ist 14 → 15
  (Inselzahl 1 → 2, nach M4 ausgenommen).
- Warnungen (nicht hart): M6 in allen Läufen (Radius < w an Haken, Wenden oder Eckbögen), M4
  (Naht am Rand) bei `fermat` 19 und bei S5 12.
- Die G3-Abdeckung ist das einzige G3-Kriterium, das bei Mustern verfehlt wird (Gate-Einwand 1);
  alle anderen G3-Kriterien, G5 und M1–M7 sind in allen machbaren Szenarien grün.
<!-- ERGEBNIS:END -->
