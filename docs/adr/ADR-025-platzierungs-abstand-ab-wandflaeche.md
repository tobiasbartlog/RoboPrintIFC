# ADR-025 — Platzierungs-Abstand (`standoff_mm`) misst ab der Wandfläche

Status: angenommen · 2026-07-12 (Tobias-Entscheidung zu Issue #160, ausgelöst
durch die Denkmal-Kollision: Simulation stellte den Roboter 255 mm näher an
die Wand als die Slicing-Ansicht versprach)

## Kontext

`standoff_mm` („Abstand") trug zwei Bedeutungen zugleich:

- **Rechnung (Core):** `placement.evaluate`, `collision.coarse`,
  `_planned_setup` (Simulation) und `module_pose` setzten den Wert direkt als
  y-Koordinate im PCA-zentrierten Wandsystem ein — dort ist y = 0 die
  **Mittelebene**. Der reale Freiraum vor der nächstliegenden Wandfläche war
  also `standoff − Dicke/2`.
- **Anzeige (Viewer) und Docstrings:** Basis-Marker und Roboter-Vorschau am
  Einbauort addierten die halbe Wanddicke („vor der Wandfront") — sie zeigten
  den Roboter eine halbe Wanddicke weiter weg, als der Core plante.

Beim 510 mm dicken Denkmal wurde die Diskrepanz sichtbar: Override
„Abstand 535" → Anzeige suggerierte 535 mm Freiraum, die Simulation stellte
die Basis real 280 mm vor die Fläche; das Kollisionsurteil des Laufs meldete
−120,6 mm Durchdringung (4023 rote Samples). Die Grobkollisions-Box
(`coarse._wall_box`) modellierte den Wandkörper zusätzlich um eine halbe
Dicke zu tief (y ∈ [−Dicke, 0] statt ±Dicke/2).

Physische Frage an den Aufsteller: Was misst man am Tisch — Basis bis
Wand-/Modul**kante** oder bis Wand**mitte**? Antwort (Tobias, 2026-07-12):
die Kante; der Abstand ist das Zollstock-Maß vor der Fläche.

## Entscheidung

**`standoff_mm` ist der freie Abstand der Roboterbasis vor der
nächstliegenden Wand-/Modulfläche.** Die Umrechnung in die
Wandsystem-Koordinate geschieht an **einer** Naht:

- `fgc.placement.base_position_in_wall(placement, thickness_mm)` →
  `(lateral, Dicke/2 + standoff, stand_height)`; Inverse
  `standoff_from_base_y`. `thickness_mm <= 0` (unbekannte Dicke) degeneriert
  ehrlich zu `y = standoff` — kein Raten einer Ersatzdicke.
- Alle Frame-Bauer laufen durch diese Naht: `placement.evaluate`
  (`_flange_targets`), `collision.coarse` (inkl. Wandbox jetzt ±Dicke/2),
  `pipeline._planned_setup` (Simulations-Setup, `thickness_mm` ist Pflicht),
  `decompose.module_pose` (`placement_frame`/`placement_from_pose`).
- `decompose.propose._module_placement` leitet den Abstand aus den
  Workstation-Frames jetzt als `horizontale Frame-Distanz − Dicke/2` ab —
  die physische Modul-Pose an der Workstation bleibt identisch.
- Viewer-Marker (`basemarker.ts`, `placement-markers.ts`: `+Dicke/2`) und
  Sicherheitsmargen-Anzeige (`standoff − Mindestabstand`) sind unter der
  neuen Semantik unverändert korrekt; das Formular heißt „Abstand vor der
  Wand (mm)".

## Verworfene Alternativen

1. **Mittelebenen-Semantik behalten, nur Anzeige fixen:** kleinster Eingriff,
   aber die Zahl im Formular bliebe beim Einrichten dauerhaft unintuitiv
   (Zollstock misst keine Mittelebene) — vom Domänenexperten abgelehnt.
2. **Beides anzeigen (Mitte + abgeleitete Freidistanz):** verdoppelt die
   Begriffe statt sie zu klären; die Wurzel (zwei Konventionen im selben
   Feld) bliebe bestehen.

## Konsequenzen

- **Gespeicherte Werte werden reinterpretiert, nicht migriert.** Bestehende
  `standoff_mm`-Werte (Projekt-Overrides, erfasste Aufstellmöglichkeiten,
  Zerlegungs-Placements) bedeuten fortan Freiraum ab Fläche — der Roboter
  steht eine halbe Wanddicke **weiter weg** als bisher gerechnet (sichere
  Richtung). Alte Läufe/Bewertungen sind unter der neuen Lesart veraltet:
  nach dem Update Zerlegung/Platzierung neu bewerten. Ein numerisches
  Umschreiben je Projekt hätte die Wanddicke jedes Jobs beim Laden gebraucht
  (IFC-Zugriff im Lade-Pfad) — abgelehnt.
- Der Fallback-Standardabstand (`DEFAULT_STANDOFF_MM = 700`,
  „Bedienersicherheitsabstand") liefert erstmals wirklich 700 mm Freiraum;
  synthetische Testwände verlieren dadurch ehrlich ein paar Eck-Stichproben.
- Die Erreichbarkeits-Stichproben von `placement.evaluate` liegen weiterhin
  auf der Mittelebene (y = 0), nicht über die Dicke verteilt — bekannter,
  separater Vorbehalt aus Issue #160 (nicht Teil dieses ADR).
