# ADR-005 — Geometrie-Kernel: Mesh-basiert, nicht BRep

Status: angenommen, ausdrücklich revisionsfähig · 2026-06-10

## Kontext
Wände sind planar-prismatisch; BRep-Präzision (OpenCascade) kauft hier nichts, kostet aber erheblich Komplexität.

## Entscheidung
Slicing auf triangulierten Meshes (Tessellation aus ifcopenshell), trimesh für Schnitte, shapely/pyclipper für 2D-Offsets.

## Konsequenzen
Das Slicer-Modul kapselt Geometriezugriffe hinter einer internen SlicerGeometry-Schicht. Spike S2 prüft, ob Revit-Tessellation ohne Mesh-Healing auskommt.

## Revisionstrigger
Gekrümmte Wände oder nichtplanares Slicing → pythonocc hinter derselben Schicht.
