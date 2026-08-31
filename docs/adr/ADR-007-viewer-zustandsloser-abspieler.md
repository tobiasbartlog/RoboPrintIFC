# ADR-007 — Viewer ist zustandsloser Abspieler

Status: angenommen · 2026-06-10 · teilweise revidiert durch ADR-014 (2026-07-02): der Viewer darf Läufe über die lokale Core-API anstoßen, rechnet aber weiterhin nichts selbst

## Kontext
Bekanntes Risiko: aus dem Frontend wird ein zweites Produktprojekt (P6).

## Entscheidung
Der Viewer parst trajectory.json, toolpath.json und glTF, rendert und animiert. Er rechnet keine Kinematik, kein Slicing, keine KPIs. Einzige „aktive" Funktionen: Laufordner wechseln, Anzeigen ein-/ausblenden.

## Konsequenzen
Alles, was der Viewer zeigen soll, muss der Core vorher als Artefakt berechnen — auch spätere Komfortfunktionen wie die klickbare Wandauswahl (E1).

## Revisionstrigger
Identisch mit ADR-001 (FastAPI-Wrapper statt Logik im Viewer).

## Klarstellung 2026-07-04 (Grill-Session „interaktiver Viewer")

„Rechnet nichts" meint **Fach**-Rechnung (Slicing, IK, Eignung, KPIs) —
nicht Darstellungsmathematik. Die Zeit-Interpolation der
Trajektorien-Animation (Issue #14) war schon immer Viewer-Sache; dazu zählt
künftig auch **Präsentations-FK**: die Vorwärtskinematik aus `joints_rad`
zur Arm-Visualisierung in der Simulation. Leitplanke: Die Viewer-FK wird
per Testorakel gegen die Core-FK validiert (ADR-009-Muster) und erzeugt
keine Entscheidungsdaten — alle Urteile (Erreichbarkeit, Warnungen,
Bewertungen) kommen weiterhin aus Core-Artefakten. Die gegenteilige
Einzelentscheidung im Design-Log zu Issue #14 („TCP aus joints_rad per FK
verworfen") ist damit überholt.

## Klarstellung 2026-07-05 (Arm-Replay: feste Basis, Issue #66)

Der Viewer **verankert** den Präsentations-Arm, berechnet die Verankerung aber
nicht selbst: die feste Roboterbasis im Wandsystem kommt als Core-Artefaktdatum
`trajectory.meta.base_frame` (= `invert(wall_to_base)`); der Viewer setzt sie nur
als konstante `group.matrix`. Damit steht die Basis fix an der geplanten Lage, die
Präsentations-FK bewegt die Gelenke, und der TCP (nicht der Flansch) fährt die
Bahn ab. Der zuvor viewer-seitig pro Frame gerechnete Anker
(`anchorFlangeToTarget`) bleibt nur noch als Rückfall für Altläufe ohne
`base_frame` — er verletzte den Grundsatz insofern, als er die Lage Wand↔Basis
implizit selbst rekonstruierte statt sie als Artefakt zu lesen.
