# Recherche: Stand der Technik — kollisionsgetriebene Zerlegung von Wänden für robotischen 3D-Druck

**Datum:** 2026-07-10
**Frage:** Gibt es bereits Tools/Forschung, die Gebäudeelemente (insb. Wände) automatisch so
in Segmente zerlegen, dass ein Roboterarm sie kollisionsfrei additiv fertigen kann?
Und: Ist die RoboPrintIFC-Pipeline (IFC → Filterung → kollisionsgetriebene Zerlegung →
Slicing → DRL/KRL für gradierten Lehmdruck) publikationsfähig?

**Methode:** Deep-Research-Lauf (105 Agenten, 5 Suchstränge, 23 Quellen, 113 extrahierte
Behauptungen, davon 25 adversarial verifiziert — alle 25 bestätigt, 0 widerlegt).
Der wichtigste „Nahe-dran"-Kandidat (Frontiers of Architectural Research 2024) wurde
anschließend manuell nachgeprüft.

---

## Kurzantwort

**Nein, ein Tool, das das leistet, existiert nach dieser Quellenlage nicht.**
Alle Bausteine existieren einzeln — BIM→Druck-Pipelines, kollisionsbewusstes
Objekt-Chunking, Robotik-Planungsbibliotheken — aber niemand verbindet sie zu einer
automatischen, erreichbarkeitsgetriebenen Wandzerlegung aus IFC-Daten mit nativer
Roboterprogramm-Erzeugung. **Eine Veröffentlichung ist realistisch.**

## Befunde im Detail

### 1. BIM-zu-Roboterdruck-Pipelines existieren — aber Revit/Dynamo-basiert, ohne Zerlegung

- **Du et al. 2024** (Virtual and Physical Prototyping): BIM→Robotersteuerung für
  3D-Betondruck mit Bewehrungsintegration. Druckpfade per **Dynamo**-Skripten, Export
  via Excel nach ROS. „Kollisionsfrei" meint dort nur Düse-vs-Bewehrungsstab (21 mm
  Abstand). Volltext enthält kein einziges Vorkommen von „IFC".
  https://www.tandfonline.com/doi/full/10.1080/17452759.2024.2332423
- **Anane et al. 2022/23** (CSCE/Springer): Dynamo zur verlustarmen BIM→Roboterarm-Übergabe;
  benennt BIM↔3DCP-Interoperabilität selbst als offene Forschungslücke.
  https://link.springer.com/chapter/10.1007/978-3-031-34593-7_37
- **Rojas & Hasanzadeh 2025** (ASCE J. Computing in Civil Engineering): hebt BIM-Elemente
  auf LOD 400, erzeugt **G-Code** mit vom Bauunternehmer manuell definierter Drucksequenz.
  Keine Reachability-Analyse, kein DRL/KRL.
  https://ascelibrary.org/doi/10.1061/JCCEE5.CPENG-6188

**Bemerkenswert:** Die Gap-Analysen dieser Literatur rahmen das Problem als
Interoperabilität/LOD — kollisions-/erreichbarkeitsgetriebene Bauteilzerlegung wird
**nicht einmal als Lücke formuliert**.

### 2. Kollisionsbewusstes Chunking ist etabliert — aber auf Objekt-/Mesh-Ebene, nie BIM/Bau

- **Dai et al., SIGGRAPH/ACM TOG 2018**: Skalarfeld-Optimierung, deren konvexe Iso-Flächen
  kollisionsfreie Druckkopf-Navigation *konstruktiv garantieren* (Multi-Achs-FDM).
  https://dl.acm.org/doi/10.1145/3197517.3201342
- **Wu et al., IEEE T-ASE 2019**: Beam-Search über sequenzielle Schnittebenen; Kollisionsfreiheit
  implizit durch planares Clipping, **nicht explizit geprüft**. Desktop-FDM (UR5, 0,4 mm
  Schichten). Volltextsuche nach BIM/IFC/wall/clay/concrete: null Treffer.
  https://arxiv.org/pdf/1812.00606
- **Stamatopoulos et al., ICRA 2024**: Mesh-Chunking für aeriellen Druck (UAV-Flotten);
  Extruder als Bounding-Rechteck begrenzt Schnittwinkel — konservative geometrische
  Schranke, keine Arm-Kinematik. Methodisch der nächste Verwandte zum RoboPrintIFC-Zerlegungsschritt.
  https://arxiv.org/pdf/2402.05853
- **LayerLock, Computer-Aided Design 2022**: Voronoi-/Delaunay-Loft-Zerlegung in verzahnte
  Segmente für simultanen Zwei-Roboter-Druck — Kollisionsfreiheit durch räumliche
  Tessellation, nicht durch Reachability.
  https://www.researchgate.net/publication/362635696
- **McPherson & Zhou 2018** (Rapid Prototyping Journal): Chunk-based Slicing für kooperative
  mobile Drucker (das „Georgia-Tech-artige" Chunking).
  https://par.nsf.gov/biblio/10209027-chunk-based-slicer-cooperative-printing

**Muster:** Kollisionsfreiheit wird in dieser Literatur *konstruktiv* erreicht (planare
Schnitte, konvexe Flächen, Voronoi-Zellen) statt durch explizite Erreichbarkeits-/
Freigang-Analyse eines konkreten Arms — und nie auf Gebäudeelementen oder Lehm/Beton.

### 3. Tool-Landschaft: Bausteine ja, Zerlegungsschritt nein

- **COMPAS FAB** (ETH/Gramazio Kohler, MIT-Lizenz): Kollisionsprüfung, IK, Bahnplanung
  über 5 Backends (PyBullet, ROS 2 + MoveIt 2 seit v2, Juni 2026). Keine IFC-Eingabe,
  keine Zerlegung (IFC lebt separat in `compas_ifc`, das ebenfalls nicht zerlegt).
  https://github.com/compas-dev/compas_fab/
- **COMPAS Slicer**: planares + gekrümmtes Slicing, Export nur JSON/G-Code. Kein IFC,
  kein KRL/DRL, keine Zerlegung. https://github.com/compas-dev/compas_slicer
- **HAL Robotics**: diagnostiziert Kollisionen/Machbarkeit nur simulativ auf
  Programmebene — Kollision ist nie Kriterium einer automatischen Bauteilzerlegung.
  https://hal-robotics.com/

### 4. Der wichtigste „Nahe-dran"-Kandidat — manuell nachgeprüft

**„From BIM model to 3D construction printing: A framework proposal"**
(Frontiers of Architectural Research, 2024,
https://www.sciencedirect.com/science/article/pii/S2095263524000463) behandelt als
einziges gefundenes Paper explizit Wand-Segmentierung + Arm-Reichweite aus BIM. Aber:

> "A common strategy to run the segmentation process consists of **drawing the maximum
> printing area** of the printer or robotic arm **in the building layout** and locating
> it in successive positions to reach each part to be printed."

> "…review the reach in height in elements close to the contours, given that the
> **workspace is hemispherical**…"

Die Segmentierung ist also eine **manuelle Zeichenstrategie im Grundriss** mit
hemisphärischem Arbeitsraum als Faustregel — keine automatische, kollisionsgeprüfte
Zerlegung, keine Kinematik-Simulation, kein DRL/KRL-Output, konzeptioneller
Framework-Vorschlag. **Dieses Paper muss im Related-Work-Teil einer Veröffentlichung
zwingend zitiert und abgegrenzt werden** (Volltext vor Einreichung vollständig lesen —
hier nur Abstract + Suchauszüge geprüft).

## Novelty-Einschätzung

Drei separate Alleinstellungsmerkmale der RoboPrintIFC-Pipeline, jeweils durch die
Quellenlage gestützt:

1. **Offenes IFC als Input** statt Revit/Dynamo (alle gefundenen BIM→Druck-Pipelines sind
   Dynamo-basiert).
2. **Arm-Erreichbarkeit/Freigang als explizites, automatisches Zerlegungskriterium**
   statt konstruktiver Garantie oder manueller Grundriss-Strategie.
3. **Native DRL/KRL-Erzeugung + funktionale Materialgradierung (Lehm)** statt G-Code
   für Portalanlagen.

Die Kombination — durchgängige Pipeline IFC → erreichbarkeitsgetriebene Wandzerlegung →
Slicing → DRL/KRL für gradierten Lehmdruck — ist nach dieser Recherche unbesetzt.
Ein 2026er Review (Int. J. Adv. Manuf. Technol.,
https://link.springer.com/article/10.1007/s00170-025-17274-0) benennt „task division"
großskaliger Druckaufgaben sogar explizit als offenes Kernproblem — das ist ein
zitierfähiger Beleg für die Relevanz.

**Einschränkungen der Einschätzung** (Confidence: mittel — Novelty ist prinzipiell nur
falsifizierbar, nie beweisbar):
- Mehrere Kernquellen waren paywalled; Negativ-Aussagen („erwähnt X nicht") stützen
  sich dort auf Abstract/Metadaten.
- Zu AMBIT, WASP-Krandruck und ROS-basierten Bau-Pipelines überlebten keine
  verifizierten Claims — Abwesenheit heißt hier „nicht geprüft", nicht „nichts da".
- Die Materialseite (funktional gradierter Lehmdruck) wurde von keinem verifizierten
  Claim abgedeckt — eigene Kurz-Recherche vor dem Schreiben des Papers sinnvoll.

## Passende Venues

Abgeleitet aus den Publikationsorten der Vorarbeiten:

| Venue | Passung |
|---|---|
| **Automation in Construction** (Elsevier) | Erste Wahl: BIM + Robotik + Bau, dort erschien auch der Ton-Wanddruck-Vorläufer |
| **Construction Robotics** (Springer) | Sehr gute Passung, praxisnäher, schnellere Durchlaufzeit |
| **Virtual and Physical Prototyping** | Hoher Impact, dort erschien Du et al. 2024 |
| **ASCE J. Computing in Civil Engineering** | BIM-Workflow-Schiene (Rojas & Hasanzadeh) |
| **RobArch** (Konferenz) | Architektur-Robotik-Community, gut für frühen Systemvortrag |
| **ICRA / CASE** (Konferenz) | Wenn der Zerlegungsalgorithmus als Robotik-Beitrag geframt wird (vgl. Stamatopoulos ICRA 2024) |

## Offene Fragen (vor Paper-Einreichung klären)

1. Volltext von „From BIM model to 3D construction printing" (FAR 2024) vollständig
   lesen und sauber abgrenzen.
2. AMBIT, WASP-Krandruck, HAL-Plugins: leisten sie doch etwas Richtung
   erreichbarkeitsgetriebener Zerlegung? (Kurzprüfung)
3. Literatur speziell zu funktional gradiertem Lehm-/Tondruck mit Roboterarmen sichten
   (Materialseite des Novelty-Claims).
4. Wurde `compas_ifc` + `compas_fab` schon publiziert zu einer Bau-Pipeline verdrahtet
   (ETH/Gramazio Kohler)?

## Vollständige Quellenliste

Primärquellen (verifiziert): siehe Links oben. Weitere gesichtete Quellen des Laufs:
- https://link.springer.com/chapter/10.1007/978-981-19-1029-6_25 (Anane et al. 2021/22, Gap-Analyse)
- https://www.sciencedirect.com/science/article/abs/pii/S0965997824001613 (Multi-Robot-Partitionierung, AES 2024)
- https://www.sciencedirect.com/science/article/abs/pii/S0926580519300718 (Robotic 3D clay printing of prefabricated wall components, Automation in Construction)
- https://link.springer.com/article/10.1007/s41693-024-00120-2 (Construction Robotics)
- https://www.mdpi.com/2075-5309/14/11/3410 und https://www.mdpi.com/2075-5309/15/18/3336 (Buildings, Surveys)
- https://www.researchgate.net/publication/354666353 (The Use of BIM for Robotic 3D Concrete Printing)
- https://arxiv.org/pdf/2408.04827 (C-RAM Survey)
- https://scholarworks.uark.edu/etd/4245/ (Dissertation, chunk-based cooperative printing)
- https://www.mdpi.com/2075-5309/12/2/229 (Buildings, Review)
