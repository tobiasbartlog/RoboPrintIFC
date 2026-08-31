# Core-Pipeline (fgc)

Python-Kern des FGC-Planners: IFC-Import, Eignungsprüfung, Slicer, (künftig)
Kinematik/Simulation/Postprozessoren. Dieses Glossar fixiert die Sprache der
Pipeline-Konzepte; Architekturentscheidungen dazu in `docs/adr/`.

## Language

**Lauf (Run)**:
Ein Ordner unter `runs/` mit den provenienz-gestempelten, schema-validierten
Artefakten genau eines Pipeline-Aufrufs (ADR-004); im Code der Typ
`pipeline.runfolder.Run`.
_Avoid_: Job, Session, Output-Ordner

**Artefakt**:
Eine schema-validierte JSON-Datei in einem Lauf (`candidates.json`,
`wallspec.json`, `toolpath.json`, `context.json`), mit `schema_version` und
Provenienzblock.
_Avoid_: Export, Ergebnisdatei

**Provenienz**:
Der Stempel eines Laufs (Quell-Kommandozeile `source`, Zeitstempel,
Git-Commit), der ihn reproduzierbar macht; genau ein Stempel je Lauf.
_Avoid_: Metadaten, Header

**Aktion**:
Eine Orchestrierungsfunktion in `pipeline/actions.py`, die einen
Pipeline-Schritt von Konfig-Beschaffung bis Lauf ausführt — die eine Tür für
CLI, Wizard und die künftige lokale API (ADR-014).
_Avoid_: Command, Service, Handler

**Eignungsprüfung (E1)**:
Die zweistufige Prüfung, ob eine Wand druckbar ist (ADR-013); Ergebnis je Wand
ist ein **Kandidat**. Das Urteil ist ein **Befund, kein Gate**: auch
ungeeignete Wände dürfen gesliced werden (Wizard wie Viewer warnen nur) —
sie werden später über Platzierung oder Zerlegung passend gemacht. Das
Urteil gilt immer *für einen bestimmten Roboter* (Workspace-Check).
_Avoid_: Filter, Validierung, Freigabe

**Kandidat**:
Eine geprüfte Wand mit Eignungsurteil und Einzel-Checks (`WallCandidate`);
Checks können `provisional` bestehen, solange Prozesszahlen fehlen.
_Avoid_: Treffer, Ergebnis

**Prozessfenster-Karte**:
Die eine Quelle für Prozessparameter (`materialcards/process_window.*.json`),
aus der E1 **und** Slicer lesen — inkl. der Planungs-Schalenzahl
`default_shells`; `provisional`, bis S1/S4 gemessene Werte liefern.
_Avoid_: Config, Settings, Materialdatei (das ist die MaterialCard)

**Setup**:
Das Artefakt je Aufspannung — die eine Stelle, an der Bauteil-Welt und
Roboter-Welt verheiratet werden (ADR-006): Lage der Wand relativ zur
Roboterbasis, Werkzeug (TCP), Kanal-Mapping (ADR-011), gemessene Totzeit
`t_tot` (ADR-012). Entsteht über das Antast-Verfahren am Roboter, nicht
durch Schätzen.
_Avoid_: Aufspannungsdatei, Roboterkonfig, Kalibrierung (das ist das
Verfahren, nicht das Artefakt)

**Projekt**:
Die langlebige, editierbare Persistenz-Einheit der GUI (ADR-016): ein
IFC-Modell plus 1..n **Druckjobs**; liegt als `project.json` unter
`projects/` und *verweist* auf Läufe, enthält sie nie. Das, was man beim
GUI-Start „öffnet".
_Avoid_: Session, Workspace, Lauf (das ist das unveränderliche Protokoll)

**Druckjob**:
Ein Druckvorhaben innerhalb eines Projekts: genau eine Wand (GlobalId) +
Roboterwahl + Zerlegungsart + Abschnitte mit je einer Platzierung + Verweise
auf die erzeugten Läufe.
_Avoid_: Auftrag, Job (zu generisch)

**Platzierung**:
Die *geplante* Relativlage zwischen Roboterbasis und Druckobjekt für einen
Druckjob bzw. dessen Teil (seitliche Position, Abstand, Aufstellhöhe). Die
Leserichtung hängt von der Zerlegungsart ab (Grill 2026-07-07, ADR-022): bei
**Abschnitt** steht das Objekt — der Roboter wird an die Wand umgesetzt, auch
in der Höhe (Podest); bei **Modul** steht der Roboter — das Modul liegt auf
der Arbeitsfläche der **Workstation**. Rechnerisch ist beides dieselbe
Relativpose. Entsteht in der GUI in zwei Modi: **Optimalvorschlag** (System
rechnet frei) oder **Bewertungsmodus** (Nutzer gibt reale
Aufstellmöglichkeiten vor, System bewertet sie — erreichbarer Wandanteil +
kinematische Marge). Ein Plan, keine Messung: verbindlich wird die Lage erst
über das Antast-Verfahren als **Setup**.
_Avoid_: Setup (das ist gemessen), Roboterposition, Basis-Frame

**Zerlegung**:
Die Teilung einer Wand in nacheinander druckbare Teile. Zwei Arten, in der
GUI als prägende Weiche wählbar: **Abschnitt** — in place an der Endposition
gedruckt, Reihenfolge unten→oben, je Abschnitt eigene Platzierung (Roboter
wird umgesetzt), Anschlussfuge = Druckunterbrechung; **Modul** — stehend in
Einbauorientierung an der **Workstation** vorproduziert, danach versetzt und
montiert; Montagereihenfolge unten→oben = Default-Druckreihenfolge. Modul v1
mit ebenen Stoßfugen, Fügegeometrie folgt später (ADR-022). Modulgröße
begrenzen der Arbeitsraum (hart) und optionale max. Länge/Höhe; das Gewicht
(Volumen × Dichte) ist Befund, kein Gate. Die Schnittebenen selbst sind
zerlegungsart-neutral — ein Artwechsel behält sie und markiert den Plan nur
als ungeprüft; Platzierungs-Overrides verfallen dabei, Slicing-Overrides
bleiben.
_Avoid_: Segment/Segmentierung (im Slicer vergeben: `segment_id` =
Layer/Kontur/Schale/Ring), Bauteil-Splitting

**Zerlegungsplan**:
Der aus den *Plan-Eingaben* eines **Druckjobs** (Zerlegungsart, Schnittebenen,
Fugen-Versatz, Overrides, Workstation, Aufstell-Toggle, Modulgrenzen)
abgeleitete Stand der **Zerlegung**: Teile mit Grenzen und je einer
**Platzierung**. Wird immer rekonstruiert, nie persistiert (ADR-016: der
Druckjob trägt nur Plan-Eingaben und Lauf-Verweise); die eine
Rekonstruktions-Tür ist `pipeline.actions.plan_for_job` (Design-Log
2026-07-08) — Reiter Druckplan und Simulation zeigen dadurch per Bauart
denselben Plan.
_Avoid_: Schnittplan (nur die Schnittebenen-Eingaben), Zerlegung (die
Teilung/Weiche selbst, nicht ihr abgeleiteter Stand)

**Prüf-Tür**:
Die Druckbarkeits-Prüfung der Teile eines **Zerlegungsplans** an ihrer
**Platzierung**, zweistufig: Stufe 1 urteilt gratis (`too_thick`, sonst
`unchecked` — nie stilles Grün), die teure Stufe 2 prüft je Höhenreihe einen
Repräsentanten per Abschnitts-Simulation samt **Kollisionskontrolle** und
vererbt das Urteil auf die Reihe. Läuft nur auf expliziten Anstoß oder als
Hintergrundlauf (Fortschritt, Abbruch, Ergebnis-Cache); das Urteil ist ein
Befund, kein Gate.
_Avoid_: Eignungsprüfung (das ist E1 auf Wand-Ebene), Druckbarkeits-Gate (es
gatet nichts), Kollisionskontrolle (die prüft je Bahnpunkt — die Prüf-Tür
urteilt je Teil)

**Workstation**:
Die projektunabhängige Aufstell-Umgebung des Roboters (stationäre Zelle oder
mobil): Mobilität, Podesthöhen-Satz, Sicherheits-Mindestabstand,
Kompatibilitäts-Tags; optional Mesh, `robot_base_frame` (Montageort der
Basis) und `work_surface_frame` (Arbeitsfläche) (ADR-021). Bei Zerlegungsart
**Modul** ist sie der Druckort: der Roboter sitzt fest an `robot_base_frame`,
jedes Modul wird auf der Arbeitsfläche positioniert (ADR-022).
_Avoid_: Druckstation (kein eigener Begriff — das ist die Workstation),
Zelle, Aufstellort (das ist die Platzierung am Einbauort)

**Endeffektor**:
Das Werkzeug am Flansch als eigenes, projektunabhängiges Artefakt
(`tools/<name>.json` + Mesh): TCP-Frame relativ Flansch, Gewicht/Schwerpunkt
(v1: nur statischer Payload-Check) und die *Deklaration* seiner logischen
Kanäle (z. B. `pump_a`, `pump_b`, `foam`). Das **Setup** mappt diese Kanäle
weiterhin auf physische Ausgänge (ADR-011): Deklaration im Endeffektor,
Mapping im Setup. Ein **Druckjob** referenziert Roboter *und* Endeffektor.
_Avoid_: Tool (Robots-GH-Jargon), Düse (das ist nur die Spitze; ihr
Durchmesser gehört zur Prozessfenster-Karte)

**Toolpath**:
Das roboterunabhängige Bahn-Artefakt (Targets mit print/travel, Schichten,
logischen IO-Kanälen nach ADR-011) samt `summary`-Kennzahlen (`n_layers`,
`n_targets`, `n_print`), die nur der Core berechnet.
_Avoid_: Trajektorie (das ist das spätere roboter-spezifische Artefakt), G-Code

**Druckpunkt (Target)**:
Ein einzelner Bahnpunkt des **Toolpath**: Pose, Geschwindigkeit, Zielart
(print/travel) und die Werte der logischen Kanäle an dieser Stelle. Träger
der _ausgewerteten_ Prozessgrößen — nicht ihrer Definition (die liegt in
Parametern und Feldern, s. **Porositätsfeld**).
_Avoid_: Punkt, Waypoint, Segment (im Slicer anders belegt)

**Porositätsfeld (φ-Feld)**:
Die ortsaufgelöste Vorgabe der Ziel-Porosität über der Wandgeometrie,
definiert im Wand-Koordinatensystem und unabhängig vom Slicing (ADR-023).
Besteht aus einer geordneten Liste von **Feld-Features**; der Slicer tastet
das Feld an jedem **Druckpunkt** ab — das Feld bleibt gültig, wenn sich
Slicing-Parameter ändern.
_Avoid_: Punkt-Porosität (Punkte tasten ab, sie definieren nicht),
Porositätsgradient (ein Gradient ist nur eine mögliche Feature-Art)

**Feld-Feature**:
Ein Baustein des **Porositätsfelds**, der die Frage „φ an Punkt p?" in
seinem Geltungsbereich beantwortet: deklarativ (Basiswert, Zone, Höhenband,
Gradient), semantisch referenzierend („um Öffnung X, Randbreite r") oder —
später — importiertes Raster (FEM). Kombination im Maler-Modell: spätere
Features überschreiben frühere.
_Avoid_: Layer (mit Druckschicht verwechselbar), Regel

**MaterialCard**:
Die eine Quelle der Material-Kalibrierung (`materialcards/`): übersetzt
Ziel-Porosität φ in Pumpen-Anteile (Stützstellen-Tabelle, interpoliert) und
künftig in Stoffeigenschaften; `provisional`, bis gemessene Kalibrierdaten
vorliegen.
_Avoid_: Prozessfenster-Karte (das sind die Prozess-, nicht die
Materialdaten), Rezeptur (das ist eine einzelne Stützstelle)

**Infill**:
Die Füllung des Wandinneren zwischen den Schalen als eigene Bahnfamilie —
geometrische (Makro-)Porosität, gesteuert über Muster, Winkel und
Linienabstand als normale Slice-Parameter. Getrennt von der
Material-(Mikro-)Porosität des **Porositätsfelds**.
_Avoid_: Füllgrad (das ist nur der Linienabstand), Porosität (ohne
Zusatz — mehrdeutig zwischen Mikro und Makro)

**Kollisionskontrolle**:
Die geometrische Prüfung Arm↔Umgebung je Bahnpunkt der Simulation: minimaler
Abstand aller Armglieder samt Endeffektor zu den Hindernissen (**Druckstand**,
Boden/Podest/Arbeitsfläche, zuschaltbar Gebäudekontext, Selbstkollision) über
exakte Kollisionsmeshes (ADR-024). Das Ergebnis ist ein **Befund, kein Gate**,
zweistufig: Abstand < 0 = Kollision (rot), Abstand < Sicherheitsabstand =
Warnung (gelb, weicher Lehm); gespeichert als Abstandskurve je Sample +
verdichtete Intervalle im Trajektorien-Artefakt.
_Avoid_: Kollisionsvermeidung (das ist der **Kollisions-Advisor**),
Clearance-Check (das ist der skalare Basis-Abstand `safety_min_distance_mm`)

**Druckstand**:
Das zeitabhängig wachsende Volumen des bereits Gedruckten als Hindernis der
**Kollisionskontrolle**: in Druckreihenfolge frühere Teile voll, das aktuelle
Teil als Footprint-Prisma (echtes Slicer-Umriss-Polygon, extrudiert) bis zur
aktuellen Schicht. Die Wand *oberhalb* der aktuellen Schicht existiert noch
nicht und ist kein Hindernis. Bei Zerlegungsart Modul: nur das wachsende Modul
auf der Arbeitsfläche (kein Gebäudekontext an der Workstation).
_Avoid_: Wandvolumen (statisch — genau der Fehlalarm, den der Druckstand
vermeidet), Werkstück

**Freizone**:
Der konfigurierbare Radius um den aktuellen Druckpunkt, in dem die
**Kollisionskontrolle** den **Druckstand** nicht bewertet — Düse und frischer
Wulst berühren sich dort prozessbedingt.
_Avoid_: Toleranz (zu generisch)

**IK-Konfiguration**:
Der Lösungszweig der analytischen IK — Schulter links/rechts, Ellbogen
oben/unten, Handgelenk normal/geflippt (3 Bits, bis zu 8 Lösungen je Pose,
`kinematics/opw.py`). Je Teil wählbar als drei Einzelschalter, Default überall
**auto** (= gelenkraum-nächste Wahl wie bisher); gesetzte Schalter filtern die
Lösungen *hart*, unter der Vorgabe unerreichbare Bahnpunkte werden Warnung im
Lauf (Befund, kein Gate).
_Avoid_: Pose (das ist eine konkrete Gelenkstellung), Roboterkonfiguration
(das ist die Katalogdatei)

**Kollisions-Advisor**:
Das Gegenstück zum Singularitäts-Advisor (ADR-020) für Kollisionsbefunde:
prüft auf Knopfdruck die Hebel **IK-Konfiguration**, Kipp/Lead und Platzierung
per Neu-Simulation und liefert eine **gerankte Liste** gangbarer Optionen
(kollisionsfrei ja/nein, min. Abstand und Marge vorher/nachher) — anders als
der Singularitäts-Advisor also mehrere Vorschläge, jeder über die bestehenden
Schreibstellen anwendbar. Der Kollisions-*Befund* entsteht dagegen automatisch
bei jeder Simulation.
_Avoid_: Kollisionsvermeidung (verspricht Automatik ohne Nutzerentscheid),
Autofix

## Relationships

- Eine **Aktion** erzeugt höchstens einen **Lauf**; ein **Lauf** enthält 1..n
  **Artefakte** und trägt genau eine **Provenienz**.
- Die **Eignungsprüfung (E1)** liest die **Prozessfenster-Karte** und erzeugt
  je Wand einen **Kandidaten** (Artefakt `candidates.json`).
- Der Slicer liest dieselbe **Prozessfenster-Karte** und erzeugt einen
  **Toolpath**; der Viewer spielt **Artefakte** nur ab (ADR-007) und liest
  Kennzahlen aus dem Toolpath-`summary` statt sie abzuleiten.
- Der Slicer tastet das **Porositätsfeld** an jedem **Druckpunkt** ab; die
  **MaterialCard** übersetzt das abgetastete φ in Kanalwerte, das **Setup**
  mappt die Kanäle auf physische Ausgänge (ADR-011, ADR-023).
- Die **Kollisionskontrolle** rechnet in der Simulation gegen den
  **Druckstand**; der **Kollisions-Advisor** bewertet seine Hebel mit
  *derselben* Simulation — keine Parallel-Metrik (ADR-024, Muster ADR-020).
- Die **Prüf-Tür** urteilt mit *derselben* Simulation wie die
  **Kollisionskontrolle** (keine Parallel-Metrik) und schreibt ihr Urteil an
  die Teile des **Zerlegungsplans**.

## Example dialogue

> **Dev:** „Der Wizard prüft Wände — schreibt der dann auch einen **Lauf**?"
> **Domain expert:** „Nein. Er ruft die **Aktion** `evaluate_walls`, die nur
> **Kandidaten** liefert. Ein **Lauf** entsteht erst beim Slicen — dann mit
> `wallspec`, `toolpath` und `context` als **Artefakten** unter einer
> **Provenienz**. Willst du das `candidates.json`-Artefakt, nimm
> `walls_to_run` — das ist derselbe Weg, den die CLI geht."

## Flagged ambiguities

- „Schalenzahl" existierte doppelt (`default_shells` in der Karte für E1,
  eigenes Default in `SliceParams`) — aufgelöst 2026-07-03: die
  **Prozessfenster-Karte** ist die eine Quelle, `SliceParams.from_window`
  übernimmt ihren Wert, explizite Overrides gewinnen.
- „Toolpath" vs. „Trajektorie": Toolpath ist roboterunabhängig (aus dem
  Slicer), Trajektorie ist roboter-spezifisch (aus der künftigen Kinematik) —
  nicht synonym verwenden.
