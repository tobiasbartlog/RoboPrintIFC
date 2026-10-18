# Systemarchitektur — FGC-Planner (Arbeitstitel)

Planungs- und Slicing-System für funktional gradierten Lehm-3D-Druck
Version 0.1 · Stand 2026-06-10 · Status: Entwurf zur Diskussion

> Hinweis: Die Ergänzungen E1–E3 (Eignungsprüfung, Zerlegung, Simulation) sind in eine kommende v0.2 dieses Dokuments einzuarbeiten.

## 1 Zweck und Zielbild

Das System nimmt ein IFC-Modell entgegen, in dem Wände mit Zielparametern hinterlegt sind (Ziel-U-Wert, maximales Gewicht, Tragfähigkeitsanforderung). Daraus schlägt es Pareto-optimale Konfigurationen vor — Kombinationen aus Pfadmuster (Schalen, Hohlkammern, Infill) und Porositätsfeld (Schaumanteil über V_A/V_B). Nach Auswahl einer Konfiguration erzeugt es konkrete Druckpfade, simuliert die Roboterkinematik visuell und exportiert ausführbare Programme für KUKA (KRL) und Doosan M1013 (DRL).

Das System ist zugleich Forschungsdemonstrator: Es komponiert die Abbildungen aus den kumulativen Arbeiten (Prozess → Porosität aus dem Extruder-Paper, Porosität → Materialeigenschaften aus der Charakterisierung) zu einem durchgängigen Planungswerkzeug und liefert die Datengrundlage für die techno-ökonomische Bewertung.

Nicht im Scope der Version 1: Mehrroboterbetrieb, Online-Regelung mit Sensorfeedback, nichtplanares Slicing, automatisches Rückschreiben der Ergebnisse ins IFC, beliebige Bauteiltypen (nur Wände). Diese Punkte sind als Erweiterungen vorgesehen und dürfen durch Architekturentscheidungen nicht verbaut werden — mehr dazu in den Revisionstriggern der ADRs.

## 2 Leitprinzipien

**P1 — Dissertation vor Produkt.** Das System wächst als „Walking Skeleton": Zuerst steht ein dünner Ende-zu-Ende-Durchstich, dann werden einzelne Stationen vertieft. Jeder Meilenstein muss eigenständig paper-verwertbar sein. Featurearbeit, die keinem Meilenstein dient, wird zurückgestellt.

**P2 — Daten als Verträge.** Module kommunizieren über versionierte, serialisierte Artefakte (JSON, glTF), nicht über geteilte In-Memory-Objekte. Jeder Pipelinelauf hinterlässt einen Artefaktordner, aus dem das Ergebnis vollständig reproduzierbar ist. Das ist keine Software-Kosmetik, sondern eine wissenschaftliche Anforderung: Jede im Paper gezeigte Konfiguration muss aus einer Datei wiederherstellbar sein.

**P3 — Tiefe Module, schmale Schnittstellen.** Nach Ousterhout: Die komplizierten Teile (IK-Mathematik, Offsetting-Robustheit, IFC-Parsing) verschwinden hinter kleinen, stabilen APIs. Ein Modul darf intern hässlich sein, solange seine Schnittstelle einfach bleibt.

**P4 — Messung schlägt Literatur.** Materialkarten enthalten ausschließlich eigene Messdaten mit dokumentierter Unsicherheit. Platzhalterwerte sind erlaubt, müssen aber maschinenlesbar als solche gekennzeichnet sein und werden in jedem Bericht sichtbar ausgewiesen.

**P5 — Robots ist Orakel, nicht Abhängigkeit.** Das visose/Robots-Plugin (MIT) dient als Referenzimplementierung für Kinematik und Postprozessoren und als Testorakel in Grasshopper. Es wird nicht zur Laufzeit eingebunden.

**P6 — Der Viewer ist ein Abspieler.** Im Viewer lebt keine Fachlogik. Er konsumiert fertige Artefakte und stellt sie dar. Das ist die Leitplanke gegen das bekannte Risiko, dass aus dem Frontend ein zweites Produktprojekt wird.

## 3 Systemkontext

| Richtung | Schnittstelle | Format / Quelle |
|---|---|---|
| Eingang | Gebäudemodell | IFC4 (Revit, Archicad oder eigene Autorierung) |
| Eingang | Materialkarten | JSON, aus Laborversuchen (Probekörper) |
| Eingang | Roboterdefinitionen | Eigenes JSON + glTF-Meshes, abgeleitet aus der Robots-Library (XML + 3DM, einmalig konvertiert) |
| Eingang | Aufspannung („Setup") | JSON: Lage der Wand relativ zur Roboterbasis, Werkzeugdefinition (TCP) |
| Ausgang | Roboterprogramme | KRL (.src/.dat), DRL (.drl) |
| Ausgang | Simulationsdaten | trajectory.json + glTF für den Viewer |
| Ausgang | Konfigurationsbericht | JSON/Markdown: KPIs, Pareto-Front, Provenienz — Rohmaterial für Paper-Abbildungen |

Primärer Nutzer ist der Forschende selbst; sekundär Studierende und Hiwis, die mit vorbereiteten Setups Versuche fahren. Daraus folgt: CLI zuerst, GUI ist Komfort.

## 4 Containersicht

Das System besteht aus zwei Containern, die ausschließlich über das Dateisystem kommunizieren.

**Container A: fgc-core** — ein Python-Paket mit CLI. Enthält die gesamte Fachlogik von IFC-Import bis Programmexport. Headless lauffähig (wichtig für Batchläufe der Ablationsstudien und für CI-Tests).

**Container B: fgc-viewer** — eine statische Web-App (TypeScript, three.js, Vite). Lädt einen Artefaktordner und visualisiert Wand, Pfade, Porositätsfeld (Farbkodierung) und die animierte Robotertrajektorie mit Zeit-Slider. Kein Backend, kein Server; läuft aus dem Dateisystem oder von einem statischen Host (Demo-Tauglichkeit für Konferenzen).

Ein optionaler dünner FastAPI-Wrapper um fgc-core ist als spätere Erweiterung vorgesehen (interaktives Parameter-Tuning aus dem Viewer heraus), aber bewusst nicht Teil der Version 1.

## 5 Module in fgc-core

Die Abhängigkeiten zeigen strikt nach unten in Richtung domain. Kein Modul kennt seinen Nachfolger in der Pipeline; die Verkettung liegt allein in pipeline.

| Modul | Verantwortung | Hängt ab von | Kennt bewusst nicht |
|---|---|---|---|
| domain | Reine Datentypen und Validierung: WallSpec, MaterialCard, Configuration, Toolpath, Trajectory, Setup | — | alles andere |
| ifc_io | IFC → WallSpec (Geometrie als Mesh, Properties, Zielparameter) | ifcopenshell, domain | Roboter, Slicing, Material |
| materials | Materialkarten laden, interpolieren (V_A/V_B → φ → λ, ρ, σ), Unsicherheitsbänder propagieren | domain | Geometrie |
| thermal | U-Wert-Berechnung; Interface ThermalModel mit Implementierungen Iso6946Analytic (v1) und FemAdapter (später) | materials, domain | Slicing, Roboter |
| configurator | Konfigurationsraum (deklarativ), Sampling, Constraint-Prüfung, KPI-Berechnung, Pareto-Filter | materials, thermal, domain | Roboterdetails |
| slicer | WallSpec + Configuration → Toolpath: Konturen, Offsets, Nähte, Hohlkammern, φ-Feld → V_A/V_B je Segment, Geschwindigkeitsfeld, Travel-Erkennung | trimesh, shapely, domain | IK, Controllersyntax |
| kinematics | FK/IK: KukaSphericalWrist, DoosanOffsetWrist (Port aus Robots), Konfigurationswahl, Achsgrenzen, Singularitätsnähe | numpy, domain | IFC, Material |
| simulation | Zeitinterpolation unter Achsgeschwindigkeits-/Beschleunigungsgrenzen → Trajectory, Druckzeitschätzung | kinematics, domain | Controllersyntax |
| postproc | Emitter-Interface; KrlEmitter (inkl. Programmsplitting für KRC-Größenlimits, ANOUT), DrlEmitter (AO-Strategie) | domain | Geometrieentstehung |
| pipeline / CLI | Orchestrierung, Artefaktordner, Logging, Provenienz (Git-Hash, Eingabedateien, Zeitstempel) | alle | — |

Zwei Modulgrenzen sind absichtlich „zu früh" gezogen: ThermalModel als Interface (obwohl v1 nur die Analytik braucht) und das Emitter-Interface in postproc (obwohl es nur zwei Controller gibt). Beide kosten jetzt fast nichts und verhindern später teure Umbauten — FEM-Kopplung und ein dritter Roboter sind realistische Erweiterungen.

## 6 Datenverträge

Die fünf zentralen Artefakte sind die „Währungen" des Systems. Alle JSON-Schemas liegen versioniert in schemas/ (Single Source of Truth für Core und Viewer) und tragen schema_version sowie einen Provenienzblock (source, created, git_commit).

**WallSpec** — was gebaut werden soll. Geometrie als trianguliertes Mesh (mm), Öffnungen, plus die Zielparameter: target_u_value (W/m²K, aus Pset_WallCommon.ThermalTransmittance), load_bearing (Boolean, ebenda), max_weight und min_compressive_strength aus einem eigenen PropertySet Pset_FGC_Targets, dessen Definition Teil des Repos ist.

**MaterialCard** — was das Material kann. Stützstellen der gemessenen Abbildungen V_A/V_B → Porosität φ und φ → (λ, ρ, σ_c), jeweils mit Unsicherheit; Gültigkeitsbereich; Mischungs-/Chargenkennung; Flag provisional für Platzhalterdaten.

**Configuration** — eine Antwort des Konfigurators. Die Entwurfsparameter (Schalenanzahl, Kammerbreite, Stegteilung, Porositätsgradient als 2–3 Parameter, Infilldichte) plus die daraus vorwärtsgerechneten KPIs (U-Wert mit Unsicherheitsband, Gewicht, Festigkeits-Proxy, Druckzeit, Materialkosten) und der Verweis auf die verwendete MaterialCard.

**Toolpath** — die geometrische Druckanweisung, roboterunabhängig. Sequenz von Targets: {frame: {pos_mm, quat}, v_mm_s, io: {V_A, V_B}, kind: print | travel, layer, segment_id}. Hier endet die Welt der Geometrie; alles danach ist Roboterwelt.

**Trajectory** — die ausführbare Bewegung. Zeitreihe {t_s, joints_rad[6], io} plus Metadaten (Gesamtdauer, Achsauslastung, Warnungen zu Singularitätsnähe). Genau dieses Format konsumiert der Viewer; mehr muss er nie verstehen.

## 7 Architekturentscheidungen (ADRs)

Jede Entscheidung mit Status, Begründung, Konsequenzen und — wichtig — dem Trigger, bei dem sie revidiert werden muss. Die ADRs leben weiter in docs/adr/ und werden bei Änderung nicht überschrieben, sondern durch neue ersetzt.

**ADR-001 — Hybrid: Python-Kern + TypeScript-Viewer.** Status: angenommen. Die geometrische Schwerstarbeit (Mesh-Schnitt, Offsetting, IFC) ist in Python gelöst verfügbar (ifcopenshell, trimesh, shapely), die bestehende GHPython-Logik portiert nahezu wörtlich; die Visualisierung ist in three.js am stärksten. Konsequenz: zwei Sprachen, daher gilt P2/P6 strikt — die Grenze ist eine Datei, keine API. Revisionstrigger: Wenn interaktives Parameter-Tuning im Viewer zur Kernanforderung wird, kommt der FastAPI-Wrapper, nicht eine Logikverlagerung in den Viewer.

**ADR-002 — Kinematik selbst portieren, Robots als Orakel.** Status: angenommen. Die IK-Solver aus visose/Robots (MIT) werden nach Python portiert (je ~300–600 Zeilen lineare Algebra): Spherical-Wrist für KUKA, Offset-Wrist für den Doosan M1013 — die Solverwahl je Roboter ist im Code von Robots zu verifizieren, bevor portiert wird. Keine Laufzeitabhängigkeit von Robots oder RhinoCommon. Attribution in NOTICE. Konsequenz: Validierungspflicht (siehe ADR-009). Revisionstrigger: Roboter mit Kinematik außerhalb beider Solverfamilien (z. B. 7-Achser).

**ADR-003 — Vorwärtsmodell + Pareto-Suche statt Inversion.** Status: angenommen. Das Problem „Zielwerte → Konfiguration" ist unterbestimmt; statt analytischer Inversion wird der niedrigdimensionale Konfigurationsraum (4–6 Parameter) gesampelt (Grid oder Latin Hypercube), vorwärts bewertet und als Pareto-Front präsentiert. Festigkeit ist Constraint, U-Wert und Gewicht sind Ziele, Zeit und Kosten sind Berichtgrößen. Konsequenz: Der Konfigurator bleibt trivial testbar und erklärbar (Paper!). Revisionstrigger: Konfigurationsraum wächst über ~8 Dimensionen oder die Vorwärtsrechnung wird teuer (FEM im Loop) — dann Surrogatmodell oder Optimierer.

**ADR-004 — Dateibasierte Artefakt-Pipeline.** Status: angenommen. Jeder Pipelineschritt ist einzeln per CLI aufrufbar und liest/schreibt Artefakte in einem Laufordner (runs/2026-06-10_wand-a/...). Begründung: Reproduzierbarkeit (P2), Debugbarkeit (jeder Zwischenstand inspizierbar, auch im Viewer), Batchfähigkeit für Studien. Konsequenz: etwas Serialisierungs-Boilerplate; bewusst in Kauf genommen. Revisionstrigger: Interaktivität mit Latenzanforderung < ~1 s.

**ADR-005 — Geometrie-Kernel: Mesh-basiert, nicht BRep.** Status: angenommen, ausdrücklich revisionsfähig. Slicing arbeitet auf triangulierten Meshes (Tessellation aus ifcopenshell) mit trimesh für Schnitte und shapely/pyclipper für 2D-Offsets. Begründung: Wände sind planar-prismatisch; die BRep-Präzision von OpenCascade kauft hier nichts, kostet aber erheblich Komplexität. Konsequenz: Das Slicer-Modul kapselt seine Geometriezugriffe hinter einer internen SlicerGeometry-Schicht. Revisionstrigger: gekrümmte Wände oder nichtplanares Slicing → pythonocc hinter derselben Schicht.

**ADR-006 — Einheiten, Frames und die eine Transformationsstelle.** Status: angenommen. Dies ist die klassische Spätfehlerquelle — deshalb hier am strengsten. Intern gilt durchgängig: Millimeter, Radiant, rechtshändige Koordinatensysteme, Quaternionen für Orientierung. IFC (Meter) wird ausschließlich in ifc_io konvertiert; Grad existieren ausschließlich in den Emittern. Es gibt genau eine Stelle, an der Bauteilwelt und Roboterwelt verheiratet werden: das Setup-Artefakt (Lage der Wand relativ zur Roboterbasis plus TCP-Definition), das der Slicer-Ausgang konsumiert. Kein Modul außer dieser Stelle darf implizite Annahmen über die Aufspannung treffen. Konsequenz: Ein Kalibrier-/Registrierworkflow (Wandnullpunkt am Roboter antasten → Setup schreiben) ist von Anfang an Teil des Systems, nicht nachgerüstetes Beiwerk.

**ADR-007 — Viewer ist zustandsloser Abspieler.** Status: angenommen. Der Viewer parst trajectory.json, toolpath.json und glTF, rendert und animiert. Er rechnet keine Kinematik, kein Slicing, keine KPIs. Einzige „aktive" Funktion: Laufordner wechseln und Anzeigen ein-/ausblenden. Revisionstrigger: identisch mit ADR-001.

**ADR-008 — Konfigurationsraum deklarativ.** Status: angenommen. Parameterräume, Constraints und Sampling-Strategie stehen in einer YAML-Datei im Laufordner, nicht im Code. Begründung: Studien (z. B. Sensitivitätsanalysen fürs techno-ökonomische Paper) sind damit Daten, nicht Codeänderungen — dieselbe Lehre wie aus der P1–P8-Ablationsstudie des EPD-Matchers.

**ADR-009 — Drei Testorakel.** Status: angenommen. (a) Kinematik: 1000 Zufallsposen, Roundtrip FK→IK→FK mit Toleranzprüfung, plus Differenzvergleich identischer Targets gegen Robots in Grasshopper. (b) Thermik: 2D-FEM-Stichprobe (stationäre Wärmeleitung, Abaqus/Ansys) für die finalen Pareto-Kandidaten — zugleich die Validierungssektion des Papers. (c) Material: gedruckte Probekörper gegen MaterialCard-Vorhersage. Konsequenz: Die Orakel sind Teil der Definition of Done je Meilenstein.

**ADR-010 — Lizenz und Provenienz.** Status: vorgeschlagen. Empfehlung: MIT oder Apache-2.0 für den Demonstrator (maximale Zitier- und Nachnutzbarkeit im Forschungskontext; anders als bei LocalBib gibt es kein kommerzielles Schutzinteresse). NOTICE-Datei mit Attribution der portierten Robots-Solver. KI-Assistenz bei der Entwicklung wird im Commit-Log dokumentiert — die Provenienz-Lehre aus der NLnet-Auseinandersetzung gilt hier präventiv, falls das Repo je in einen Förder- oder Publikationskontext mit FLOSS-Anforderungen gerät.

## 8 Offene Entscheidungen mit Fälligkeit

**OD-1 — Doosan: analoge Ausgänge bahnsynchron?** Fällig: vor Meilenstein 1, per Hardware-Spike. Das ist die folgenreichste offene Frage des Projekts. Wenn DRL analoge Ausgänge nur diskret zwischen Bewegungsbefehlen setzen kann, muss der Slicer Pfade in kurze Segmente zerlegen, deren Länge die räumliche Auflösung des Porositätsfelds bestimmt — das ist eine Slicer-Designentscheidung, keine Postprozessor-Fußnote. Deshalb darf der Slicer-Feinschliff nicht vor diesem Spike passieren.

**OD-2 — KUKA: ANOUT nutzen?** Fällig: vor KRL-Emitter. KRL kennt mit ANOUT ON/OFF eine bahnsynchrone analoge Ausgabe (aus Schweiß-/Klebeanwendungen) inklusive Vorlaufzeit-Kompensation. Zu klären: verfügbar auf dem konkreten Controller, Kanalzahl, ob V_A und V_B beide synchron fahrbar sind. Positiver Befund würde die Segmentierungsstrategie für KUKA vereinfachen.

**OD-3 — Öffnungen (Fenster/Türen) in v1?** Fällig: vor Slicer-Konturlogik. Öffnungen machen aus einfachen Ringkonturen Konturen mit Inseln und erzwingen Überbrückungs-/Sturzstrategien. Empfehlung: v1 ohne Öffnungen starten, aber WallSpec trägt sie von Anfang an (billig), damit der Slicer sie später nur noch behandeln, nicht erst kennenlernen muss.

**OD-4 — FEM-Kopplung automatisiert oder manuell?** Fällig: vor Meilenstein 3. Abaqus-Scripting (Python-API) ist machbar, aber Aufwand; die manuelle Stichprobe reicht für die Dissertation. Das FemAdapter-Interface hält beide Wege offen.

**OD-5 — Rückschreiben der gewählten Konfiguration ins IFC?** Fällig: nach Meilenstein 2. Attraktiv für die BIM2Field-Erzählung (Verbindung zum ZIM-Projekt), aber kein Pflichtteil.

## 9 Risiken und Spikes (vor dem ersten „richtigen" Code)

Die ersten Wochen gehören kleinen, wegwerfbaren Experimenten, die jeweils ein Architekturrisiko entschärfen:

**S1 — Doosan-AO am Gerät (entscheidet OD-1):** Testprogramm, das während einer Linearbewegung V_A/V_B variiert; messen, mit welcher Latenz und Granularität die Ausgänge folgen. Höchstes Risiko, weil hardwareabhängig und durch nichts am Schreibtisch ersetzbar.

**S2 — IFC-Tessellation:** Eine Wand mit Fensteröffnung aus Revit exportieren, mit ifcopenshell tessellieren, mit trimesh schneiden — sind die Konturen wasserdicht und orientiert? Entscheidet, ob ADR-005 ohne Reparaturschicht (Mesh-Healing) auskommt.

**S3 — IK-Roundtrip:** Doosan-Offset-Wrist-Solver portieren und das Orakel aus ADR-009a laufen lassen, bevor irgendetwas darauf aufbaut.

**S4 — Offset-Robustheit:** shapely-Offsets an spitzen Ecken und schmalen Stegen prüfen; daraus die Druckbarkeitsregeln ableiten (Mindestradien, Mindeststegbreite als Funktion der Strangbreite), die der Konfigurator als Constraints braucht.

## 10 Repository-Struktur

```
fgc/                        Monorepo
├── core/                   Python-Paket (pyproject.toml)
│   └── src/fgc/
│       ├── domain/  ifc_io/  materials/  thermal/
│       ├── configurator/  slicer/  kinematics/
│       ├── simulation/  postproc/  pipeline/
├── viewer/                 Vite + TypeScript + three.js
├── schemas/                JSON-Schemas, versioniert (Single Source für Core und Viewer)
├── robots/                 Roboterdefinitionen (JSON) + Gelenkmeshes (glTF)
├── materialcards/          Gemessene und provisorische Karten
├── examples/               IFC-Beispieldateien, Setups
├── runs/                   Laufordner (gitignored)
└── docs/adr/               Entscheidungshistorie
```

## 11 Meilensteine (Walking Skeleton)

**M0 — Skelett steht.** IFC-Wand laden → planar slicen → Konturen je Schicht → Viewer zeigt Wand und Pfade. Noch kein Roboter, keine Porosität. Wert: Der gesamte Datenfluss inklusive Artefaktordner und Schemas existiert; jede spätere Arbeit vertieft nur noch Stationen.

**M1 — Roboter bewegt sich.** IK + Simulation, animierte Trajektorie im Viewer, KRL/DRL-Export, Trockenlauf am Roboter ohne Material. Voraussetzung: Spikes S1 und S3 abgeschlossen. Wert: Kinematik-Validierung dokumentiert; Druckzeitmodell für die Techno-Ökonomie steht.

**M2 — Konfigurator schlägt vor.** Materialkarten v0 (ehrlich als provisorisch markiert), Vorwärtsmodell, Pareto-Front, Konfigurationsbericht. Wert: Die Methodik des Konfigurators ist publizierbar, unabhängig von finalen Messwerten.

**M3 — Validiert.** Gemessene Materialkarten, FEM-Stichprobe der Pareto-Kandidaten, gedruckter Wandabschnitt mit gewählter Konfiguration. Wert: Demonstrator-Paper.

## Anhang: Entscheidungen, die dieses Dokument bewusst NICHT trifft

Werkzeugwahl unterhalb der Architekturebene (Test-Framework, Linter, CI-Anbieter), GUI-Gestaltung des Viewers, konkrete Parametrisierung des Porositätsgradienten (Fachfrage, nicht Architekturfrage) und die Wahl des endgültigen Projektnamens.
