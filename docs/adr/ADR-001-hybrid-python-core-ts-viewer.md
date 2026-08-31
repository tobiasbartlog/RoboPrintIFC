# ADR-001 — Hybrid: Python-Kern + TypeScript-Viewer

Status: angenommen · 2026-06-10

## Kontext
Geometrische Schwerstarbeit (Mesh-Schnitt, Offsetting, IFC) ist in Python gelöst verfügbar (ifcopenshell, trimesh, shapely); die bestehende GHPython-Logik portiert nahezu wörtlich. Visualisierung ist in three.js am stärksten.

## Entscheidung
fgc-core als Python-Paket mit CLI; fgc-viewer als statische Web-App (TypeScript, three.js, Vite). Kommunikation ausschließlich über Dateien.

## Konsequenzen
Zwei Sprachen — daher gelten P2 (Daten als Verträge) und P6 (Viewer ist Abspieler) strikt. Die Grenze ist eine Datei, keine API.

## Revisionstrigger
Wird interaktives Parameter-Tuning im Viewer Kernanforderung, kommt der FastAPI-Wrapper — nicht eine Logikverlagerung in den Viewer.
