# ADR-024 — Kollisionskontrolle: exakte Mesh-Distanzen (trimesh + fcl) gegen den wachsenden Druckstand

Status: angenommen · 2026-07-08 (Grill-Session Kollisionskontrolle, PRD folgt)

## Kontext

Das Trajektorien-Replay ist ehrlich beschriftet: „keine Kollisionsprüfung"
(ADR-006-Badge). Ein Nutzer-Foto (M1013-Ellbogen taucht beim Abspielen von
Abschnitt 1 durch das Wandvolumen) machte die Lücke konkret. Die
Kollisionskontrolle war in v1 mehrfach bewusst ausgelassen (Design-Log
2026-07-05 u. a.), aber vorbereitet: die URDF-`<collision>`-Meshes des M1013
sind unter `third_party/doosan_m1013/meshes/m1013_collision/` genau dafür
gevendort; die Trajektorie trägt `joints_rad` je Sample + `base_frame`; die
Link-Frames liefert `OpwKinematics.link_frames`.

Zwei Besonderheiten des Lehm-Drucks prägen die Entscheidung:

1. **Die Wand wächst.** Beim Drucken existiert die Wand oberhalb der aktuellen
   Schicht nicht — eine Prüfung gegen das statische Wandvolumen meldete
   Dauerkollision (die Düse fährt definitionsgemäß „in" der künftigen Wand).
2. **Der Arm arbeitet prozessbedingt nah am Gedruckten.** Handgelenk +
   Endeffektor bewegen sich dauerhaft im Standoff-Abstand vor der Wand.
   Konservative Hüllgeometrie (dicke Kapseln) würde dort chronisch falsch
   warnen — ein Advisor, der immer warnt, ist wertlos.

ADR-007 verlangt: der Core urteilt, der Viewer spielt ab.

## Entscheidung

**1. Exakte Kollisionsmeshes statt Kapseln.** Die Distanzrechnung
Arm↔Hindernis nutzt die gevendorten URDF-Kollisionsmeshes des Roboters
(einmalig offline in ein core-eigenes Format konvertiert, Muster
`convert_robot_meshes.py`, referenziert im Roboterkatalog). Bibliothek:
**`python-fcl` als neue Core-Dependency**, angesprochen über das bereits
vorhandene `trimesh` (`trimesh.collision.CollisionManager.min_distance_*`).
Ein **billiger Breitphasen-Filter** (AABB/Kapsel je Glied) begrenzt die
exakten FCL-Abfragen auf nahe Glied-Hindernis-Paare — exakt, wo es zählt,
schnell, wo es egal ist.

**2. Hindernis = wachsender Druckstand, nicht die fertige Wand.** Je Schicht
(nicht je Bahnpunkt) wird das Hindernisvolumen neu gebaut: in Druckreihenfolge
(= Montagereihenfolge, ADR-022) frühere Teile voll, das aktuelle Teil als
**Footprint-Prisma** (echtes Slicer-Umriss-Polygon aus `geometry/section.py`,
extrudiert bis zur aktuellen Schicht). Um den aktuellen Druckpunkt bleibt eine
konfigurierbare **Freizone** (Düse↔Wulst berühren sich prozessbedingt).
Weitere Hindernisse: Boden/Podest/Arbeitsfläche, **zuschaltbar** der
Gebäudekontext (bei Modulen an der Workstation gegenstandslos),
Selbstkollision des Arms.

**3. Befund, kein Gate — zweistufig mit Abstandszahl.** Je Sample wird der
minimale Abstand gerechnet (analog `kinematic_margin`): < 0 mm = Kollision
(rot), < konfigurierbarer Sicherheitsabstand = Warnung (gelb — weicher Lehm
macht „knapp vorbei" zum Schaden). Additiv im Trajektorien-Schema:
Abstandskurve + Verursacher je Sample, verdichtete Intervalle in `meta`.
Altläufe laden byte-gleich; die Platzierungs-Ampel bleibt unangetastet
(eigenes Kollisions-Badge, zwei Bewertungszeitpunkte werden nicht vermischt).

**4. IK-Konfiguration wird wählbar — harter Filter.** Die vorhandenen
IK-Konfigurationsbits (`SHOULDER/ELBOW/WRIST`, `opw.py`) bekommen je Teil drei
Einzelschalter (auto/fixiert). Gesetzte Bits filtern die Lösungen in
`select_along_path` hart; unter der Vorgabe unerreichbare Bahnpunkte werden
Warnung im Lauf. Damit wird zugleich der bislang rein beratende Config-Flip
des Singularitäts-Advisors anwendbar (Revisionstrigger aus ADR-020 erfüllt).

**5. Kollisions-Advisor nach dem ADR-020-Muster, aber mit Optionsliste.**
Der Befund entsteht automatisch bei jeder Simulation; der Advisor läuft auf
Knopfdruck (teuer: je Kandidat eine Neu-Simulation) und prüft drei Hebel —
**IK-Konfiguration**, **Kipp/Lead-Sweep**, **Platzierung** — mit derselben
Simulations-/Bewertungsmaschinerie (keine Parallel-Metrik). Ergebnis ist eine
**gerankte Liste** gangbarer Optionen (kollisionsfrei ja/nein, min. Abstand +
Marge vorher/nachher), jede über bestehende Schreibstellen anwendbar
(process-params, placement-override, neu: Konfigurationswahl).

## Verworfene Alternativen

- **Kapseln je Glied als Urteilsgeometrie** (empfohlen wegen Reinheit/ohne
  Dependency): verworfen — im Nahbereich Wand↔Handgelenk chronisch
  falsch-positiv (Punkt 2 im Kontext). Kapseln/AABBs bleiben als
  *Breitphasen-Filter* erhalten, urteilen aber nicht.
- **Statisches Wandvolumen als Hindernis**: verworfen — Dauerkollision der
  Düse, nur durch Blind-Ausnahmen heilbar.
- **Bounding-Box je Teil statt Footprint-Prisma**: verworfen — bei
  nicht-rechteckigen/gekrümmten Grundrissen falsch-positiv.
- **Kollisionsprüfung im Viewer** (aus `joints_rad` des Replays): verworfen —
  verletzt ADR-007, zweite Geometrie-Wahrheit neben dem Core.
- **Konfigurationswahl als weiche Präferenz (Seed statt Filter)**: verworfen —
  nicht erklärbar („warum hängt der Ellbogen trotz Vorgabe wieder unten?"),
  schwer testbar.
- **Kollision übersteuert die Teil-Ampel**: verworfen — die Ampel existiert
  vor jeder Simulation und würde je nach Zeitpunkt Verschiedenes bedeuten.

## Konsequenzen

- Neue Binärabhängigkeit `python-fcl` (Windows-Wheels vorhanden); ein
  blockierender **Spike** prüft Installation + Performance mit echter
  `trajectory.json`, bevor Scheiben geschnitten umgesetzt werden.
- Trajektorien-Schema wächst additiv (Abstandskurve, Intervalle);
  Determinismus bleibt (gleiche Meshes → gleiche Distanzen, Goldens möglich).
- Der Viewer zeigt im Replay Glied-Einfärbung, Timeline-Marker, den
  wachsenden Druckstand statt der Voll-Box und (abschaltbar) die
  Live-Abstandszahl — alles reine Darstellung aus dem Artefakt.
- Die Platzierungsbewertung bekommt als Ausbaustufe einen Grob-Check, damit
  der Optimalvorschlag keine Aufstellungen liefert, die erst in der Sim
  durchfallen.
- Sample-basierte Prüfung kann Zwischenzustände überspringen (Tunneling bei
  schnellen Travel-Moves) — bewusste v1-Grenze, im PRD als offener Punkt.

## Revisionstrigger

- ~~Spike scheitert (fcl auf Windows instabil oder zu langsam) → Rückfall auf
  schlank handkalibrierte Kapseln (Option lag auf dem Tisch).~~ *Abgeräumt —
  Spike S0 grün, s. Nachtrag.*
- Travel-Move-Entschärfung (Abhebe-/Rückzugswege) wird gebaut → Advisor
  bekommt einen vierten Hebel, der in die Bahnplanung eingreift.
- Gemessene Prozessdaten (weicher Lehm, zulässige Annäherung) → Kalibrierung
  von Sicherheitsabstand + Freizone.

## Nachtrag 2026-07-08 — Spike S0 grün, Urteilsgeometrie präzisiert

Der blockierende Spike (Protokoll `docs/spikes/S0_kollision_python_fcl.md`,
Sonden `docs/spikes/s0_scripts/`) bestätigt die Entscheidung und präzisiert
die Ausprägung:

- **Installation/Determinismus grün:** `python-fcl 0.7.0.11` läuft auf
  Windows/Python 3.14 ohne Auffälligkeiten; Distanzen sind bei Wiederholung
  und Manager-Neuaufbau bitgleich (Goldens möglich). Zusatz-Dependencies:
  `mapbox-earcut` (Kappen/Extrusion), `vhacdx` (Konvexzerlegung).
- **Präzisierung: die *Urteilsgeometrie* je Glied ist die
  VHACD-Konvexzerlegung der exakten URDF-Kollisionsmeshes** (formtreu
  ±5 mm, ⌀ 0,3 mm gegen die Roh-Meshes), die *Breitphase* die konvexe Hülle
  je Glied (untere Distanz-Schranke: > Sicherheitsabstand ⇒ sicher grün).
  Die Roh-Meshes direkt zu befragen ist 14× langsamer (602 s statt 44 s für
  25 217 Samples der Foto-Trajektorie) — Kostentreiber ist die signierte
  Distanz großer BVH-Paare. Der Geist der Entscheidung (formtreu statt
  dick-konservativ, keine chronischen Fehlwarnungen im Nahbereich) bleibt
  unverändert; Dezimierung wurde verworfen, weil sie bis +20 mm Abstand
  *erfindet*. Hüllen+VHACD entstehen einmalig offline in
  `fgc.collision.robot_geometry` (Muster `convert_robot_meshes.py`).
- **Travel-Tunneling bestätigt:** Druckzüge sind dicht gesampelt (p99
  20 mm), Travel-Moves springen bis ~1 m je Schritt — die v1-Grenze bleibt,
  der Befund soll Travel-Abschnitte als „nicht lückenlos geprüft"
  beschriften.
