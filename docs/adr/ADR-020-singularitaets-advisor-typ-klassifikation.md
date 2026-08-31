# ADR-020 — Singularitäts-Advisor: Typ-Klassifikation + gezielte Vorschläge im Core

Status: angenommen · 2026-07-06 (Issue #65, Scheibe 6 von PRD #57)

## Kontext
Die Kinematik liefert seit Issue #11 ein **reziprokes Konditionsmaß**
(`OpwKinematics.singularity_measure`, 0 = singulär … 1 = gut konditioniert) und
eine Warnschwelle. Das sagt **wie nah** eine Pose an einer Singularität ist —
aber nicht **welcher Art** (Handgelenk / Ellbogen / Schulter) und nicht **was
dagegen hilft**. Für die Platzierungs-/Prozessschleife (PRD #57) fehlte damit der
Schritt von der bloßen Warnung zum **gezielten Hebel**: derselbe niedrige
Marge-Wert verlangt je nach Ursache eine andere Gegenmaßnahme (Düse kippen vs.
Basis umstellen vs. Konfiguration flippen).

ADR-007 verlangt zugleich, dass **der Core urteilt und der Viewer nur setzt**: die
gesamte Typ-Klassifikation, Vorschlagsberechnung und Neubewertung gehört in den
Core; der „Anwenden"-Knopf darf nur eine Core-Aktion/Route auslösen.

## Entscheidung
Zwei tiefe, isoliert testbare Core-Module — **kein neues Skalarmaß**, sondern
Typ + Hebel *oberhalb* des vorhandenen Konditionsmaßes:

- **`fgc.kinematics.singularity`** (reine Typ-Klassifikation): `classify(kin,
  joints)` klassifiziert die Nähe aus den **Gelenkwinkeln** nach Typ. Drei
  dimensionslose, geometrisch motivierte Schwere-Werte ∈ [0, 1] (1 = genau an der
  Bedingung), der größte bestimmt den dominanten Typ:
  - **Handgelenk**: Beugeachse J5 (`joints[4]`) nahe 0/±π (Achsen J4∥J6 koppeln,
    derselbe Zweig wie `opw.SINGULARITY_THRESHOLD_RAD`);
  - **Ellbogen**: Schulter→Handwurzel-Abstand nahe Streckung `c2+c3` bzw. Faltung
    `|c2−c3|` (J3 nahe Streckung);
  - **Schulter**: radialer Abstand der Handwurzel von der Basisachse z0 fällt auf
    den geometrischen Mindestabstand (Schulter-Offset `b`).
  Die *Nähe* bleibt `singularity_measure` (wiederverwendet, nicht neu erfunden).
- **`fgc.placement.advisor`** (Typ + Kontext → gezielter Vorschlag): `advise(ctx)`
  klassifiziert die **schlechtest-konditionierte erreichte Pose** der gewählten
  Platzierung und leitet den Hebel ab — **Handgelenk → Kipp-Delta**
  (`process_params.orientation`), **Reichweite/Ellbogen → Platzierungsoption**
  (`fgc.placement.suggest`), **Schulter/konfig-abhängig → Konfigurations-Flip**
  (andere IK-Konfiguration). Die **Vorher/Nachher-Marge** kommt aus **derselben**
  Core-Bewertung `placement.evaluate` (keine Parallel-Metrik): der Kipp-Hebel
  sucht das Delta, das die kinematische Marge in der Neubewertung anhebt, ohne den
  erreichbaren Anteil zu senken — nachweisbar per pytest.

**Anwenden = bestehende Schreibstelle + Neubewertung (ADR-016):** Die
Viewer-„Anwenden"-Aktion schreibt **nichts Neues**: der Kipp-Delta geht über
`PUT …/process-params` in `process_params.orientation` (die eine
Orientierungsquelle `nozzle_quat`, Issue #61), die Platzierung über
Bewertung/Auswahl (Issue #22). Der Schreibvorgang bumpt den `process`-Revisions­
zähler → Zerlegung/Simulation/Export veralten (ADR-017). Der Config-Flip ist in v1
**rein beratend** (keine Schreibstelle für die Konfigurationswahl).

**Referenzposen bewusst weggelassen (nur Start-Seed):** Der Advisor bewertet die
real gesampelte Wandbahn (Konfigurationswahl mit Null-Seed, Issue #11), **keine**
hinterlegten Sollposen. Das ist eine bewusste Scope-Grenze dieser Scheibe.

## Verworfene Alternativen
- *Ein weiteres Skalarmaß je Typ* (separate „Handgelenks-/Ellbogen-/Schulter-
  Zahl"): verworfen — dupliziert die Rangbetrachtung, driftet gegen
  `singularity_measure`. Stattdessen bleibt die Nähe das Konditionsmaß, nur die
  Typ-Aufteilung kommt dazu.
- *Klassifikation im Viewer* (aus `joints_rad` des Replays): verworfen — verletzt
  ADR-007 (Urteilendes gehört in den Core). Der Viewer bekommt Typ + Vorschlag als
  Daten.
- *Eigener Bewertungspfad für die Vorher/Nachher-Marge*: verworfen — die
  Verbesserung muss in **derselben** `placement.evaluate` sichtbar sein, sonst
  wäre der Nachweis wertlos.
- *Referenzposen-Katalog als Orakel*: bewusst auf später vertagt (nur Start-Seed),
  um die Scheibe klein und prüfbar zu halten (Acceptance-Kriterium #65).

## Konsequenzen
Warnungen tragen jetzt einen **Typ** und einen **anwendbaren Hebel** statt nur
einer Zahl. Der Kipp-Hebel schließt die Schleife Ampel → Vorschlag → Anwenden →
Neubewertung end-to-end (pytest belegt die Margenverbesserung). Rückwärts­
kompatibel: ohne gewählte Platzierung/ohne Roboter gibt es keinen Vorschlag (kein
Fehler); der Config-Flip wartet auf eine spätere Persistenz der Konfigurationswahl.
`fgc.placement.advisor` hängt (in Importrichtung sauber) von `placement.evaluate`/
`.suggest` und `fgc.kinematics.singularity` ab — kein Zyklus.

## Revisionstrigger
- Persistenz der IK-Konfigurationswahl am Druckjob → Config-Flip wird anwendbar
  (heute rein beratend).
- Referenzposen-Katalog (Sollposen als Orakel) → Advisor bewertet nicht mehr nur
  die gesampelte Bahn.
- Gemessene Achs-/Singularitätsgrenzen (Spike S1) → Bänder (`WRIST_BAND_RAD`,
  `SHOULDER_/ELBOW_BAND_FRACTION`, `ADVISE_MARGIN_BELOW`) neu kalibrieren.
