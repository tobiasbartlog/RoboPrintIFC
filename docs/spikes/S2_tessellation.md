# Spike S2 — IFC-Tessellation (prüft ADR-005)

Status: **vorläufig grün** (Grundtest bestanden, aber Testmodell schwächer als ursprünglich geplant — siehe Einschränkungen)

## Frage
Revit-IFC → ifcopenshell-Tessellation → trimesh-Schnitt: Sind die Schnittkonturen geschlossen (wasserdicht) und konsistent orientiert? Entscheidet, ob ADR-005 ohne Mesh-Healing auskommt.

## Vorgehen
1. Aus Revit exportieren: je eine Wand **ohne** und **mit** Fensteröffnung → `examples/` (IFC4)
2. ifcopenshell: Geometrie tessellieren (Settings dokumentieren: `USE_WORLD_COORDS`, Toleranzen)
3. trimesh: horizontale Schnitte in mehreren Höhen (`trimesh.intersections.mesh_plane`)
4. Prüfen je Schnitt: geschlossene Polygone? Orientierung konsistent (Außenkontur CCW)? Löcher korrekt als Inseln?

Skript: `docs/spikes/s2_scripts/tessellate_check.py`.

## Ergebnis
- [x] Konturen geschlossen: **ja**, für alle 4 Wände und alle getesteten Schnitthöhen
- [x] Orientierung konsistent: **ja**, alle Außenkonturen CCW, Mesh insgesamt `winding_consistent=True`
- [x] Mesh-Healing nötig: **nein**, für dieses Testmodell — keine Lücken, keine invertierten Normalen
- [x] Tessellations-Settings als Empfehlung für `ifc_io` notiert: `settings.set(settings.USE_WORLD_COORDS, True)`, keine Toleranz-Overrides nötig; Default-Triangulation war sauber

## Einschränkungen (wichtig für Bewertung)
- Testmodell ist ein **SketchUp-Export** (`examples/Building-Architecture.ifc`, `IFC4X3`), **kein Revit-Export** wie im Vorgehen vorgesehen. Revit-spezifische Tessellations-Eigenheiten (andere Meshing-Strategie, ggf. andere Kantenverdopplung) sind damit **nicht** getestet.
- Modell enthält **keine Wand mit Öffnung** (`IfcOpeningElement`-Anzahl: 0). Der für E1-Stufe-1 relevante Fall „Loch korrekt als Insel im Schnittpolygon" ist damit **nicht geprüft** — offener Punkt, siehe unten.
- Nur 4 Wände, alle einfache Quader bis auf eine dünne Installationswand mit schräger Oberkante (Giebelanschluss) — kein Stresstest für komplexe Grundrisse oder gekrümmte Wände (ADR-005-Revisionstrigger).

## Nächster Schritt (offen)
Ein zweites Beispiel mit Fensteröffnung aus Revit besorgen (laut Umsetzungsplan §2 ohnehin für E1 nötig) und denselben Check gegen dieses Modell laufen lassen — insbesondere die Loch-als-Insel-Prüfung (`interiors`/`Loecher_gesamt` im Skript). Erst dann ist die ursprüngliche Frage vollständig beantwortet.

## Protokoll

**2026-07-02**, ifcopenshell 0.8.5, Python 3.14.0 (venv), trimesh 4.12.2, shapely 2.1.2.

Laufzeit-Abhängigkeiten von `trimesh.section()`/`polygons_full`, die im `geo`-Extra fehlten und nachinstalliert wurden: `scipy`, `networkx`, `rtree` (jetzt in `core/pyproject.toml` ergänzt).

Befunde je Wand (`examples/Building-Architecture.ifc`, 3 Schnitthöhen je Wand):

| Wand | GlobalId | vertices/faces | watertight | winding_consistent | Polygone je Schnitt | Löcher |
|---|---|---|---|---|---|---|
| house right front | `1AQAupaRP1txwK1AGiN61V` | 8/12 | True | True | 1 | 0 |
| house right back | `3wdauVJT5Fx9drrREiDqA$` | 8/12 | True | True | 1 | 0 |
| house left | `0OfZwWc8j9QP5uX8xPTxDH` | 8/12 | True | True | 1 | 0 |
| plumbing wall | `1uS5vfZPn9R8PlAaVd73on` | 16/24 | True | True | 2 | 0 |

Die drei Außenwände sind einfache Quader. Die „plumbing wall" ist planar (liegt bei konstantem x, Dicke ≈ 24 mm), hat aber eine gestufte/schräge Oberkante (folgt vermutlich einem Giebel) — deshalb schneidet die horizontale Ebene sie an manchen Höhen in zwei getrennte, aber jeweils geschlossene Konturen statt in eine. Das ist kein Tessellations-Defekt, sondern korrekt abgebildete Geometrie; für den Slicer bedeutet es, dass „ein Schnitt kann mehrere disjunkte Polygone ergeben" von Anfang an eingeplant werden muss (nicht nur „ein Außenkontur + n Löcher", sondern potenziell mehrere unabhängige Konturen je Höhe).
