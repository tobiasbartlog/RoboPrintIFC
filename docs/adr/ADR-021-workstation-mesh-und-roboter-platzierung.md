# ADR-021 — Workstation-Mesh, Roboter-Platzierung & Bohrbild-Erkennung

Status: **Angenommen** (2026-07-07, Issue #78)
Kontext-Grill: 2026-07-07 (Nutzerwunsch nach dem Bibliothek-Redesign #71–#77)

## Kontext

Die Workstation wurde in #72/#75 **bewusst mesh-frei** modelliert — „reine
strukturierte Zahlenfelder" (Mobilität, Podesthöhen bzw. Höhenbereich,
Sicherheitsabstand, Kompatibilitäts-Tags). Diese Entscheidung ist an mehreren
Stellen dokumentiert (Docstring `domain/workstation`, `WorkstationRequest`,
`index.html`, `workstation-library.ts`, `workstation-payload.ts`).

Der Nutzer (Grill 2026-07-07) verlangt für die **stationären** Workstations:

1. einen **Mesh-Upload** der Aufstell-Umgebung,
2. den **Roboter auf einer Fläche positionieren** — Flächen-Mittelpunkt wählen
   und drehen, „wie beim Endeffektor",
3. die **Arbeitsfläche** wählen,
4. die **4 Basis-Bohrlöcher** des Roboters auf dem Mesh **erkennen** und den
   Roboter darauf ausrichten (der Lochradius darf leicht abweichen, das Bild
   muss passen).

Außerdem missfällt das zentrierte, nebeneinander liegende Rubriken-Menü der
Bibliothek.

## Entscheidung

**Die mesh-freie Workstation wird umgekehrt — additiv und rückwärtskompatibel.**

1. **Optionale Felder** auf `workstation.schema.json` / `WorkstationDef` /
   API: `mesh` (Dateiname), `robot_base_frame`, `work_surface_frame` (Frames
   `{pos_mm, quat[w,x,y,z]}`, ADR-006). Alle drei fehlen bei Altbestand → die
   Workstation bleibt dann reine Zahlenfelder wie zuvor (Migrationsschutz, wie
   `compatible_robots` seit #71). `additionalProperties:false` bleibt.

2. **Mesh-Upload spiegelt den Endeffektor** (ADR-014): base64-in-JSON
   (`mesh_base64` + `mesh_filename`), Validierung über die geteilten Helfer aus
   `domain/tool` (`mesh_suffix`/`validate_mesh_bytes`, STL/OBJ/GLB, ≤ 50 MB),
   Ablage als `<name><suffix>` neben `<name>.json` in `workstations/`. Beim
   Bearbeiten ohne Re-Upload bleibt das Mesh erhalten; Löschen entfernt das
   Mesh-Geschwister.

3. **Roboter-auf-Fläche** nutzt die bestehende reine Mathematik
   (`ui/face-align.ts`, three.js-frei) mit **einer neuen, vorzeichen-gedrehten
   Funktion** `mountBaseToSurface`: Basis-+z-Achse → **Flächennormale** (statt
   Werkzeug-Normale → −Flansch-z), Ursprung im Flächen-Mittelpunkt, Drehung um
   die Normale. Der Workstation-Editor bekommt dafür ein WebGL-Sichtfeld
   (bisher reines Formular) mit derselben Raycast-/Hover-/Region-Pipeline wie
   der Endeffektor-Konfigurator.

4. **Roboter-Bohrbild als maschinenlesbare Daten** auf `robot.schema.json`:
   optionales `base_mount` (`hole_count`, `hole_diameter_mm`,
   `bolt_circle_diameter_mm`, `hole_positions_mm`, `provisional`). Für den
   Doosan M1013 **provisorisch** aus dem Installationshandbuch (§3.3.1):
   4 × Ø9 mm für M8, auf einem 150 × 150 mm-Quadrat (Mitten ±75, BCD Ø212,1),
   Montageebene z=0. Roboter bleiben **read-only** — nur Daten, keine
   Editier-UI (Kinematik weiterhin hart verdrahtet, #69).

5. **Bohrbild-Erkennung im Core** (`fgc.geometry.holes`), nicht im Viewer:
   Mesh an der obersten horizontalen Fläche schneiden (reuses das
   `section.py`-Muster `polygons_full → interiors` = Löcher), Kreise fitten,
   ein zum `base_mount` passendes N-Loch-Bild per 2D-Starrkörper-Abgleich
   suchen (Radius-Toleranz, weil der reale Lochradius abweichen darf), und den
   **`robot_base_frame` vorschlagen** (Zentroid + Normale + Drehung; bit-gleich
   zur Viewer-Konvention). Route `POST /workstations/{name}/detect-base-holes`.
   **Befund, kein Gate** (ADR-013): bei Treffer schnappt der Editor den Roboter
   darauf, sonst nur eine Warnung — nie eine Sperre.

6. **Bibliothek-Rubrikenmenü** wird zur **linken Seitenleiste** (reines CSS).

## Konsequenzen

- Die mesh-freie Schlichtheit ist für die Workstation aufgegeben; der Editor
  trägt jetzt WebGL. Weil Mesh/Frames **optional** sind, funktionieren
  reine-Zahlen-Workstations unverändert weiter (keine Migration nötig).
- Die Platzierungs-Frames sind **Workstation-Stammdaten**. Der #77-Seam bleibt
  gültig: eine Workstation-Änderung veraltet **weiterhin keine** Outputs — die
  Frames konsumiert erst der Druckplan-Automatismus (#70). In diesem Schritt
  fließen `robot_base_frame`/`work_surface_frame` **noch nicht** in Trajektorien.
- Die M1013-Bohrbild-Maße sind **provisorisch** (`provisional:true`),
  datenblatt-abgeleitet und vor dem realen Bohren zu bestätigen — analog zur
  provisorischen vel/acc/Blending-Kennzeichnung (ADR-006/012/019).
- Die Erkennung setzt v1 eine **horizontale obere Montagefläche** voraus
  (dokumentiert in `holes.py`); schräge Flächen kann der Nutzer manuell per
  Flächenklick bedienen. Ein späterer Ausbau kann die Ebene aus der gewählten
  Fläche ableiten.

## Verworfene Alternativen

- **Bohrbild als reine Zahlen** (BCD/Anzahl/Ø) am Workstation statt Erkennung —
  verworfen: der Nutzer will die Löcher **auf dem realen Mesh** erkannt haben.
- **Hartes Kompatibilitäts-Gate** bei fehlendem Passbild — verworfen (ADR-013,
  „Befund, kein Gate", konsistent zum ganzen Kompatibilitätsmodell #74).
- **Mesh nur für `stationary`** (Feld je Mobilität) — verworfen zugunsten eines
  für alle optionalen Feldes (kein Sonderfall, kleinere Schema-Fläche).
- **Detektion im Viewer** (three.js) — verworfen: der Core hat trimesh/shapely
  und das erprobte `section.py`-Loch-Muster; Urteilendes gehört in den Core
  (ADR-007).
- **Frei-Drag-Gizmo** zum Platzieren — verworfen aus demselben Grund wie beim
  Endeffektor (#28/#52): Frames werden **berechnet**, nicht aus der
  three.js-Objektlage zurückgelesen.
