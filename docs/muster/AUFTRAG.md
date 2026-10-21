# Auftrag: Druckmuster (Infill und Outfill), Nachtlauf 20./21.10.2026

Branch `v2/muster` (abgezweigt von `v2/strang`, 99c802c). Fortschritt und Herzschlag stehen in
`MUSTER-PROGRESS.md`. Diese Datei ist der Auftrag. Sie ändert sich in der Nacht nur durch
Nachträge des Nutzers. `MUSTER-PROGRESS.md` und der Code ändern sich laufend.

## Auftrag des Nutzers (Tobias, 20.10.2026, wörtlich)

> Ich möchte dass du eine online session erstellst, die von mir aus auch die ganze nacht lang laufen
> darf. Dabei sollen unterschiedliche infill pattern gebaut werden. Optimal ist es immer, wenn der
> roboter beim schichtwechsel in z richtung nur gerade nach oben fahren muss und nicht diagonal. Bei
> den beiden außenreihen könnte man ja natürlich auch auch abwechselnd von außen nach innen und von
> innen nach außen drucken damit das auf geht. Bei den infill patterns soll sich auch genau überlegt
> werden, wie gedruckt werden kann, ohne dass sich Stränge kreuzen. Sinuskurven und ähnliches kommt
> mir in den sinn. Überhänge sollen gar keine entstehen. Dazu sollen "Outfill" patterns die
> wandgeometrie auch von außen unterteilen. Wenn ich lange wände aus nur einem stück drucke, dann
> reißen sie, wenn ich die wand außen auch unterteile dann reißt sie nicht so schnell. Wichtig ist
> nur, dass Patterns gefunden werden, die innerhalb einer Schicht ohne absetzen zu drucken sind. Es
> soll durchgängig extrudiert werden. Erstele hierfür eine ausgiebige online session, die daran
> arbeitet mit workflows und mehrere agents arbeiten lässt. Wenn mein Limit gehitet wird, dann soll
> die session einfach warten, bis ich wieder limit habe.

Der Nutzer hat Workflows und mehrere Agenten ausdrücklich verlangt (ultracode-Freigabe für diesen
Lauf). Er will, dass Details selbst entschieden und begründet werden; Rückfragen gibt es in der
Nacht keine. Echte Weichen (Prozess am Gerät, Gates, Standardwerte) sammelst du mit Empfehlung
für den Morgenbericht.

## Nachtrag des Nutzers (20.10.2026, 18:20) – hat Vorrang

> Mit den Außenfugen meinte ich sozusagen sollbruchstellen. Hier auf dem Foto erkennst du ein
> Beispielmuster. […] Cool wäre ein parametrischer Musterersteller, mit dem ich die Länge der
> einzelnen Stränge anpassen kann. Das darf auch in 2d sein damit es leichter zu rechnen ist.

Foto: `docs/muster/referenz/fugenwand-foto.jpg` (Lehm, gedruckt, Blick schräg von oben auf die
Außenseite). Sieh es dir selbst an, bevor du das Muster entwirfst.

**Outfill heißt Sollbruchstellen (O2).** Die Lesart O2 ist damit bestätigt und hat Vorrang. O1 und
O3 werden nur noch gebaut, wenn Zeit bleibt.

**Was das Foto zeigt** (Lesart des Vorbereiters; prüfe sie am Bild):
- Die Außenhaut besteht aus **geraden Feldern**. An jeder Feldgrenze stoßen zwei Felder nur stumpf
  aneinander. Es entsteht eine senkrechte Fuge über die ganze Höhe: Die Raupen berühren sich dort,
  laufen aber nicht durch. Das ist die Sollbruchstelle.
- Von jeder Fuge laufen zwei **schräge Stege V-förmig nach innen**. Über jeder Fuge liegt eine Raute,
  über jedem Feld ein Dreieck bzw. Trapez. Die Stege treffen sich an Knoten und berühren sich dort.
  Sie kreuzen sich nicht.
- Die Gegenseite der Wand ist gleich aufgebaut. Innen entsteht so ein Rauten- bzw. Fachwerkraster.
- Alle Schichten liegen deckungsgleich übereinander, es gibt keinen Überhang.

**Eine mögliche Einzelstrang-Topologie** (Vorschlag; prüfe sie und finde bessere Varianten): Die
Vorderseite läuft als Folge Feld A → Fuge J_AB → schräg nach innen zum Knoten N_A über der Feldmitte
von A → Gurtstück auf der Wandmitte von N_A nach N_B → schräg zurück zur Fuge J_AB → Feld B → Fuge
J_BC → schräg zu N_B → … . Jede Fuge und jeder Knoten wird zweimal **berührt** (Kontakt, keine
Kreuzung: Die Richtungen der beiden Besuche greifen nicht ineinander). An den Modulenden schließt
eine Endkappe zur Rückseite, die gespiegelt oder um eine halbe Teilung versetzt zurückläuft. Je
Schicht entsteht so ein geschlossener Ring, also ein senkrechter Schichtwechsel. Varianten:
- mit oder ohne Gurt in der Wandmitte (ohne Gurt: Die Knoten von Vorder- und Rückseite berühren sich)
- Rückseite gespiegelt (Fugen beider Seiten gegenüber, also eine durchgehende Sollbruchebene durch
  die Wand) oder um eine halbe Teilung versetzt
- Fuge stumpf (Raupen berühren sich) oder mit kleinem Spalt bzw. Kerbe nach außen
- Feldgrenzen an den Modulenden: Ein Modulstoß ist selbst eine Fuge.

**Parametrischer 2D-Musterersteller (neues Hauptziel, Priorität wie die Fugenwand selbst):**
- Der Nutzer stellt die **Länge der einzelnen Stränge** ein: Feldlänge (Außenstrang zwischen zwei
  Fugen), Länge bzw. Winkel der Schrägstege, Knoten- bzw. Gurtlänge, Fugenspalt, Eckradius,
  Versatz der Rückseite. Dazu kommen Wanddicke, Modullänge und w, mit Vorgabe aus dem gewählten
  Modul oder frei.
- Die Ansicht ist **2D-Draufsicht einer Schicht**, live beim Ziehen der Regler. Gezeigt werden: der
  Pfad nach Segmentart eingefärbt, Richtungspfeile, Start und Ende, die nächste (umgekehrte)
  Schicht blass, Fugen und Kontakte markiert, Regelverstöße M1–M7 rot. Dazu Kennzahlen: Pfadlänge
  und Druckzeit je Schicht, Material je Meter, Zellgrößen, Kontaktlängen, Fugenabstand, längste
  gerade Außenstrecke, kleinster Radius.
- **An die Modullänge anpassen:** ganze Zahl von Feldern, Rest gleichmäßig verteilt; die
  tatsächlichen Längen werden angezeigt.
- Speichern als benanntes Muster (JSON-Preset), das Slicer, Szenarien und Viewer als Musterparameter
  verwenden. Export als SVG für Doku und Katalog.
- **Architektur:** Die Geometrie rechnet `core/src/roboprint/patterns/`, nicht der Browser (SPEC §9:
  Der Viewer rechnet keine Fachlogik). Die API bekommt einen schnellen Vorschau-Endpunkt (z. B.
  `POST /api/patterns/preview` → 2D-Polylinien je Segmentart, Kontakte, Verstöße, Kennzahlen; Ziel
  < 100 ms je Schicht). Das Web zeichnet das als SVG mit Mantine-Reglern und Entprellung. Ein
  CLI-Befehl (z. B. `roboprint pattern-preview <preset.json> --svg <datei>`) erzeugt dieselbe Ansicht
  für den Katalog. Kein Roboter in der Vorschleife. Die Roboterprüfung läuft erst beim „Zerlegen &
  prüfen“ bzw. in den Musterszenarien.
- Im Viewer bekommt der Musterersteller einen eigenen, gut erreichbaren Platz (z. B. eigener Reiter
  bzw. Schritt „Muster“ oder Drawer im Parameterpanel; entscheide nach `docs/ux-leitbild.md`).
  Playwright-Test und Screenshot gehören dazu.

**Angepasste Prioritäten:**
1. Kern und Orakel (M1) wie geplant, die Kern-Schnittstelle aber von Anfang an für parametrische
   Segmentmuster mit Kontakten (Fugen, Knoten) auslegen.
2. Fugenwand (Foto) als erste Musterfamilie, mit Varianten und echter Roboterprüfung (S1-Quader,
   Testkörper, ein S2-Modul).
3. 2D-Musterersteller (API + Web + CLI).
4. Danach die Infill-Wellen (Sinus usw.) und die alternierende Schichtfolge für das heutige Muster.
5. O1/O3 und weitere Varianten nur, wenn Zeit bleibt.
Der Recherche-Agent sucht zusätzlich nach Sollbruchstellen bzw. Kontrollfugen in Lehm-, Cob- und
Stampflehmwänden (übliche Fugenabstände, Fugenausbildung) und nach gedruckten Fachwerk- bzw.
Rautenwänden.

## Ziel

Für Wandmodule entstehen Druckmuster, die je Schicht und Insel als **ein durchgehender Strang**
gedruckt werden: ohne Absetzen, mit durchlaufender Pumpe, ohne Kreuzung, ohne Überhang, und mit
**senkrechtem Schichtwechsel** (Schichtende und Anfang der nächsten Schicht liegen in XY übereinander).

1. **Schichtfolge:** Die Richtung wechselt je Schicht. Gerade Schichten laufen außen → innen, ungerade
   innen → außen, jeweils als Umkehrung derselben Bahn. Der Schichtwechsel ist dann ein reiner Z-Hub um h.
   Das gilt auch für das heutige Muster (zwei Schalen ohne Infill).
2. **Infill:** Muster im Hohlraum zwischen den inneren Schalen, z. B. Sinus, Zickzack mit Rundung,
   Trapez oder Mäander, Doppelwelle bzw. Kettenglied für dicke Wände, Fermat-Spirale für kleine Inseln.
3. **Outfill:** Muster, die die Wand auch von außen gliedern, damit lange Wände weniger reißen
   (Schwinden beim Trocknen). Mindestens zwei Familien, siehe unten.
4. **Einbau** in Slicer, Planer, DRL und Viewer. Dazu eine unabhängige Prüfung der Musterregeln und
   Testdruck-Programme je Muster.

**Morgens erwartet der Nutzer:**
- einen bebilderten Musterkatalog mit Kennzahlen und Empfehlung (`docs/muster/MUSTERKATALOG.md`)
- kleine Testdruck-DRLs je Muster, vom Planer geprüft (`docs/muster/testdrucke/`)
- Muster im Viewer wählbar, mit 2D-Vorschau einer Schicht
- den parametrischen 2D-Musterersteller (Nachtrag 18:20) mit der Fugenwand aus dem Foto als erstem Muster
- G1–G8 weiter grün, die Musterprüfung grün
- `MORGENBERICHT-MUSTER.md` und einen Draft-PR `v2/muster → v2/strang`

## Musterregeln M1–M7

Diese Regeln gelten für jede Schicht jedes Teils, das mit Muster gedruckt wird. Die Zahlen sind
Startwerte. Mit **A** markierte Werte sind Annahmen und kommen in den SPEC-Nachtrag.

- **M1 Durchgehend:** Je Schicht und je zusammenhängender Querschnittsinsel gibt es genau einen
  Strang: Pumpe an, kein Halt, kein Travel. Inseln (z. B. Pfeiler neben einer Öffnung) dürfen eigene
  Stränge haben, ihre Zahl ist minimal.
- **M2 Kreuzungsfrei:** Die Mittellinie des Schichtpfads ist einfach, sie schneidet sich also nicht
  selbst. Zwei Pfadpunkte, die entlang des Pfads mehr als 2·w auseinanderliegen, haben einen
  Abstand ≥ (1 − ε)·w, mit ε = 0,15 (A). Gewollte Kontakte (Steg an Schale) liegen bei
  (1 − ε)·w … w. Kein Pfadstück fährt über eine Raupe, die in derselben Schicht schon liegt.
- **M3 Überhangfrei:** Die Raupenfläche (Mittellinie ⊕ w/2) von Schicht L+1 liegt in der
  Raupenfläche von Schicht L ⊕ δ, mit δ = 2 mm (A). Grundsatz: Jede Schicht hat dieselbe
  XY-Geometrie, nur die Richtung wechselt. Ändert sich der Querschnitt innerhalb eines Teils
  (Brüstung, Laibung, Modulkante), muss jede neue Kante der höheren Schicht auf Raupen der tieferen
  Schicht stehen. Das heißt: Querstege an allen künftigen Laibungen, bestimmt aus dem ganzen Teil
  und nicht Schicht für Schicht.
- **M4 Senkrechter Schichtwechsel:** Ende von Schicht L und Anfang von Schicht L+1 liegen waagrecht
  ≤ 0,5 mm auseinander. Der Übergang ist ein Verbinder mit waagrechter Länge 0, also ein reiner
  Z-Hub um h. Ausnahmen gibt es nur, wo sich die Inselzahl ändert; dort gelten SPEC §5.3 und der
  Travel. Die Naht legst du dorthin, wo der Materialpunkt des Hubs nicht stört: nicht auf die
  sichtbare Außenfläche und nicht auf die Stoßfläche zum Nachbarmodul. Begründe die Wahl.
- **M5 Im Teil:** Die Raupenfläche liegt im Querschnitt ⊕ 1 mm. Es wird nie außerhalb des Teils
  und nie über Öffnungen gedruckt. Outfill bleibt innerhalb der IFC-Wanddicke.
- **M6 Druckbar gekrümmt:** Der Krümmungsradius der Mittellinie ist hart ≥ w/2 und als Ziel ≥ w (A).
  Der Sehnenfehler der Polylinie gegen die Sollkurve ist ≤ 0,5 mm.
- **M7 Kontakt:** Infill und Stege berühren die Schalen mit einer Überlappung von 0 … ε·w. Anzahl
  und Länge der Kontaktzonen je Meter Wand werden berichtet.

Dazu gilt alles Bisherige: Pumpe nur in `print` und `link`, kein Zweigwechsel im Strang, d ≥ d_hard,
Verbinder gerade, ≤ `link_max_mm` lang und nur über Material (SPEC §5.3). Ein Muster, das ohne
Absetzen nicht geht, ist kein gültiges Muster. Ist eine Wunschform physikalisch oder geometrisch
unmöglich (z. B. Doppelwelle bei 80 mm Hohlraum), belegst du das mit Zahlen. Das ist ein gültiges
Ergebnis.

## Outfill: was gemeint sein kann

*Nach dem Nachtrag oben ist O2 (Sollbruchstellen, Foto) bestätigt und hat Vorrang.* Ursprünglicher
Text: Der Wortlaut lässt mehrere Lesarten zu. Baue und vergleiche mindestens zwei davon:

- **O1 Gewellte oder gefaltete Außenschale:** Welle, Zickzack oder Trapez im Wanddickenband. Die
  Hülle bleibt in der IFC-Dicke, die Fläche ist nicht mehr eben. Schwinden in Wandlängsrichtung
  baut sich durch Verformung der Welle ab, statt eine lange gerade Raupe zu reißen.
- **O2 Gegliederte Außenschale:** Eine ebene Außenhaut mit Sollrissfugen bzw. Kerben in festem
  Abstand, jeweils an der Stelle eines Querstegs. Risse sammeln sich in den Fugen.
- **O3 Zellwand:** Querstege reichen bis an die Außenhaut (z. B. Haarnadel-Stege, Rechteckwelle
  mit doppeltem Steg), sodass die Außenhaut aus kurzen Feldern zwischen Stegen besteht.

Kennzahl für die Rissneigung ist die **längste gerade, ungestützte Außenstrecke** je Schicht, dazu
der Gliederungsabstand. Lies die Literatur zu Schwindrissen im Lehm- bzw. Cob-3D-Druck
(Recherche-Agent) und begründe damit Abstände und Formen. Eine Schwindsimulation ist nicht verlangt.

## Ausgangslage im Code

- `core/src/roboprint/slicer.py`: Ringe je Schale (Offset mit Mitre), Ringstart an der Ecke nächst
  (x_min, y_min), Verbinder nach SPEC §5.3 (`link_allowed`). Ein senkrechter Verbinder (waagrechte
  Länge 0) ist schon zulässig (Fall `Point`).
- Vertrag `Ring` (`contracts/artifacts.py`): `kind` outer|inner|hole, `closed`, `link_next`,
  `waypoints`. `closed = false` erlaubt der Vertrag schon, erzeugt wird es bisher nicht.
- S1: Quader 600 × 200 × 400 mm, w = 30 mm, 2 Schalen. Der Hohlraum ist 80 mm breit, das Band für
  Infill-Mittellinien, die beide Innenschalen berühren, ist 50 mm breit. Die Wände in S2 sind
  200 mm dick, ein Teil der Module hat Öffnungen (mehrere Inseln in manchen Schichten).
- Zweite Option je Muster: eine Schale je Seite und ein breiteres Infill-Band (140 mm bei 200 mm
  Wand). Prüfe auch 300 und 365 mm dicke Quader.
- Parallel läuft (seit 17:16) die Cloud-Abnahme des Strangs auf `v2/strang`. Übernimm deren Fixes
  zu Beginn jeder Phase mit `git fetch origin v2/strang && git merge origin/v2/strang`.

## Rahmen

- **Sperre bleibt:** `spec/` und `verify/` sind gesperrt (Hook). Du änderst dort nichts, auch nicht
  über Worktree-Pfade oder Skripte. Stattdessen:
  - SPEC-Ergänzungen schreibst du als einfügefertigen Nachtrag nach
    `docs/muster/SPEC-NACHTRAG-MUSTER.md` (neuer §5.7 „Muster“, Parameter für §10, Gate G9 für §11,
    Szenarien, ARTEFAKTE-Ergänzung). Annahmen markierst du mit A.
  - Das Muster-Orakel entsteht als **Vorschlag für G9** in `verify_muster/` (oberste Ebene). Es folgt
    denselben Regeln wie `verify/`: Es importiert `roboprint` nie, liest nur Artefakte (`toolpath.json`,
    `trajectory.json`, `part.stl`, Szenario) und hat Selbsttests mit konstruierten Gegenbeispielen
    (Kreuzung, Überhang, diagonaler Schichtwechsel, Lücke im Strang, Druck außerhalb des Teils,
    zu enger Radius). Geschrieben wird es von einem Agenten, der `core/src` nicht liest.
  - Musterszenarien liegen in `docs/muster/szenarien/` (z. B. `S4_muster_<name>.json` als
    S1-Quader mit Muster, `S5_muster_oeffnung.json` als Modul mit Öffnung aus S2). Die bestehenden
    Orakel nutzt du lesend: `python -m verify.check_run <lauf> --scenario <json>` (G3-Regeln) und
    `verify/fake_drcf` (G5-Regeln).
  - Runner `scripts/verify_muster.py`: rechnet die Musterszenarien, prüft mit check_run, fake_drcf
    und `verify_muster`, schreibt `runs/verify_muster/report.json` und endet mit 0 nur, wenn alles
    grün ist.
  - Wo ein bestehendes Kriterium mit einem Muster kollidiert (z. B. G3-Abdeckung des
    Schalenbereichs bei gewellter Außenhaut), änderst du das Kriterium nicht. Du belegst es unter
    „Gate-Einwände“ in `MUSTER-PROGRESS.md` und schlägst im Nachtrag eine Regel vor.
- **Standardwerte bleiben SPEC-konform:** Ohne Musterparameter verhält sich alles wie heute, S1–S3
  und G1–G8 bleiben unverändert grün. Neue Parameter sind opt-in, z. B. `layer_order`
  (`same` | `alternate`), `infill_pattern`, `outfill_pattern` und Musterparameter wie Wellenlänge,
  Amplitude und Stegabstand. Ob `alternate` und ein bestimmtes Muster Standard werden, entscheidet
  der Nutzer; du empfiehlst.
- **Git:** Integrationszweig `v2/muster`; jede Aufgabe in einem eigenen Worktree auf
  `v2/muster-<aufgabe>`. Push nur auf `v2/muster` und `v2/muster-*`, nie `--force`, nie auf `main`,
  `v2-nachtlauf` oder `v2/strang`. Conventional Commits, je erledigter Aufgabe einer, jede Nachricht
  endet mit `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nach jedem Merge pushen.
- **Rechner:** 4 vCPU. Höchstens 5 Agenten gleichzeitig, Tests mit `pytest -n 2`. Python immer über
  `/opt/fgc-venv/bin/python`.
- **Workflows:** Je Phase ein Workflow (Workflow-Tool; der Nutzer hat es für diesen Lauf ausdrücklich
  verlangt). In deinem Kontext landen nur Ergebnisse. Fehlt das Workflow-Tool, nimmst du
  Hintergrund-Agenten in Worktrees nach demselben Plan.
- **Modellwahl:** `opus` für Geometrie und Topologie der Muster, Orakel, Planer und Gegenprüfung.
  `sonnet` für Viewer-Komponenten, Bilder, Tests nach Muster, Doku und Recherche. Nach einem
  gescheiterten `sonnet`-Versuch einmal mit `opus` wiederholen.
- Lies vor der Arbeit: `CLAUDE.md`, `spec/SPEC.md` (§2, §3, §5.2, §5.3, §5.5, §5.6, §10, §11),
  `spec/ARTEFAKTE.md`, `docs/doosan-drl.md` (vor DRL-Arbeit) und `docs/ux-leitbild.md` (vor Web-Arbeit).

## Phasen

Jede Phase endet mit `/opt/fgc-venv/bin/python scripts/verify.py --fast`, dem Musterrunner (sobald
er existiert), einem Eintrag in `MUSTER-PROGRESS.md`, Herzschlag und Push.

**M0 Einrichtung (Orchestrator allein, ≤ 30 min).** Umgebung prüfen, `verify.py --fast` als
Ausgangslage, Aufgabenliste in `MUSTER-PROGRESS.md` anlegen.

**M1 Grundlagen (parallel, ein Workflow):**
- *R Recherche* (sonnet, WebSearch): Infill- und Wandmuster im Lehm-, Cob- und Beton-3D-Druck
  (z. B. WASP, TECLA, IAAC, Arbeiten von Gomaa u. a.), Schwindrisse und Gegenmittel (Fugen, Wellen,
  Fasern), übliche Raupenüberlappung, kleinste Biegeradien, durchgehende Bahnen ohne Kreuzung
  (z. B. Connected Fermat Spirals, Zhao et al. 2016), Nahtstrategien. Ergebnis:
  `docs/muster/recherche.md` mit Quellen und je Quelle der Folgerung für uns.
- *K Kern* (opus): reines Geometriemodul `core/src/roboprint/patterns/`, ohne Roboter. Es bietet
  eine schmale Schnittstelle (Querschnitt(e) des ganzen Teils, Schicht, Parameter → geordnete
  Schichtbahn aus Segmenten mit `kind`, offen oder geschlossen, und die Verbinder dazwischen) sowie
  `patterns/metrics.py`, das M1–M7 systemseitig misst. Dazu die alternierende Schichtfolge und
  das Grundmuster „2 Schalen ohne Infill, senkrechter Schichtwechsel“. Ende: Unit-Tests grün, die
  Schnittstelle ist in einem Docstring dokumentiert, damit M2 parallel bauen kann.
- *O Orakel* (opus, unabhängig, liest `core/src` nicht): `verify_muster/` nach den Regeln oben.
  Ende: Selbsttests mit allen Gegenbeispielen grün.

**M2 Musterfamilien (parallel, ein Workflow, gegen die Schnittstelle aus K):**
- *I-Wellen* (opus): Sinus, Zickzack mit Rundung, Trapez/Mäander. Parameter Wellenlänge und Phase,
  Kontakt an den Innenschalen.
- *I-Mehrfach* (opus): Doppelwelle bzw. Kettenglied und Waben aus zwei gegenphasigen, sich berührenden
  Wellen, für Wände ≥ 300 mm bzw. für eine Schale je Seite. Fermat-Spirale für kleine Inseln.
- *Outfill* (opus): O1, O2, O3 nach dem Abschnitt oben.
- *Topologie* (opus): allgemeine Querschnitte, also Öffnungen, mehrere Inseln und Kerben;
  Querstege an künftigen Laibungen (M3); Wahl der Naht (M4); Übergänge Schale → Schale → Infill
  ohne Doppelmaterial (z. B. spiraliger Übergang statt geschlossenem Ring plus Querverbinder).
Jede Familie bringt Tests, die M1–M7 mit `patterns/metrics.py` und mit `verify_muster` prüfen,
und je ein Bild (Draufsicht zweier Schichten mit Richtungspfeilen, Start, Ende und Kontakten).

**M3 Einbau (nacheinander):**
1. Slicer und Vertrag: Musterparameter, offene Segmente (`closed = false`), neue `kind`-Werte
   (z. B. `infill`, `web`), senkrechte Verbinder. Schema-Export und TS-Typen nachziehen.
2. Planer, Timing und DRL: offene Segmente, Verbinder der Länge 0, Strang über alle Schichten;
   Laufzeit beobachten (Kurven brauchen dichtere Wegpunkte; Sehnenfehler ≤ 0,5 mm).
3. Musterszenarien, `scripts/verify_muster.py`, SPEC-Nachtrag.
Ende: G1–G8 grün wie zuvor, Musterrunner grün für alle Szenarien, die machbar sein sollen.

**M4 Viewer (parallel zu M3, sonnet, nach `docs/ux-leitbild.md`):** Musterwahl im Parameterpanel,
2D-Vorschau einer Schicht (Pfad, Richtung, Start und Ende, Nachbarschicht blass), neue Bewegungsarten
in der Legende, Kennzahlen je Muster. G6 bleibt grün, Screenshots aktualisieren.

**M5 Vergleich und Testdrucke:**
- Jedes Muster auf dem S1-Quader und auf zwei bis drei S2-Modulen (mindestens eins mit Öffnung)
  planen. Kennzahlen je Muster: machbar, d_min, Stränge je Schicht, Anteil senkrechter
  Schichtwechsel, Pfadlänge und Druckzeit je Schicht, Materialvolumen relativ zu „2 Schalen“,
  Kontaktzonen je m, größte Zellspannweite, längste ungestützte gerade Außenstrecke, kleinster
  Krümmungsradius, Planerlaufzeit.
- `docs/muster/MUSTERKATALOG.md`: je Muster Bild, Kennzahlen, Vor- und Nachteile, Empfehlung.
- `docs/muster/testdrucke/<muster>/`: Testkörper 600 × 200 × 100 mm (10 Schichten) am Standard-
  Druckplatz, `program.v2.drl`, `program.v3.drl` und ein Kurz-README mit Druckzeit und Material.
  Nur Programme, die der Planer als machbar einstuft und fake_drcf akzeptiert.

**M6 Gegenprüfung und Härtung:** Ein frischer Agent (opus) sucht gezielt Fehler: eine Schicht mit
Kreuzung, Überhang, diagonalem Schichtwechsel oder Lücke; ein Sample, bei dem Status oder Prüfer
falsch liegt; ein Muster, das bei einer anderen Wanddicke oder Öffnung zerfällt. Funde werden
Aufgaben. Danach voller Lauf `scripts/verify.py` (G1–G8) und `scripts/verify_muster.py`.

**M7 Abschluss:** `MORGENBERICHT-MUSTER.md` mit Katalog-Auszug und Bildern, Empfehlung für Standard-
Schichtfolge und Standardmuster, den Weichen für den Nutzer (gebündelt, je mit Empfehlung),
Gate-Einwänden und den nächsten Schritten (Testdruckplan). Kurzer Eintrag in `PROGRESS.md`. Draft-PR
`v2/muster → v2/strang` mit dem Morgenbericht als Beschreibung, nicht mergen. Herzschlag auf
`FERTIG`.

**Zeitrahmen (Europe/Berlin):** Um 08:30 schreibst du einen Zwischenstand in den Morgenbericht,
egal wie weit du bist. Um 09:15 beginnt M7. Um 10:00 steht der Herzschlag auf `FERTIG`.
**Backlog**, falls vorher Zeit bleibt: weitere Varianten, Parameterstudie (Wellenlänge gegen
Kontaktzahl und Druckzeit), alle geeigneten S2-Wände mit dem empfohlenen Muster, Laufzeit der Planung.

## Betrieb: Herzschlag, Limit und Wächter

Ein Nutzungslimit oder eine Pause der VM kann deine Session jederzeit stoppen. Dann übernimmt eine
der stündlichen Wächter-Sessions (Routinen von 19:00 bis 09:00). Der Zustand lebt deshalb vollständig
im Repo:

- **Herzschlag:** Die erste Zeile von `MUSTER-PROGRESS.md` setzt
  `python scripts/herzschlag.py setzen --session <kennung> --phase <M0…M7>` (mit `--status FERTIG`
  am Ende). Danach committest und pushst du sie. Das tust du mindestens alle 30 Minuten und nach
  jedem Merge. Lange Läufe (verify, Workflows) startest du im Hintergrund und wartest mit Monitor in
  Abschnitten von höchstens 20 Minuten, damit du dazwischen den Herzschlag setzen kannst. Beende
  deinen Zug nie, solange Hintergrundarbeit läuft.
- **Vor jeder Phase und vor jedem Push:** `git fetch origin v2/muster` und
  `python scripts/herzschlag.py pruefen --session <kennung>`. Endet das mit 3, hat eine andere
  Session übernommen. Dann hörst du ohne weiteren Push auf.
- **Wiederaufnahme:** Halbfertige Worktrees ohne Commit gelten als verloren, die Aufgabe startet
  neu. Committe deshalb lieber kleine fertige Schritte.
- Die Aufgabenliste in `MUSTER-PROGRESS.md` (Aufgabe, Status, Branch, Commit) hältst du aktuell,
  damit ein Wächter ohne deinen Kontext weitermachen kann.
