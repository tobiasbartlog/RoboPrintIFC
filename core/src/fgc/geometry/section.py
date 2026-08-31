"""Horizontaler Mesh-Schnitt: Mesh + Schnitthöhe → Umriss-Polygon(e) (ADR-015).

Neutrales Geometrie-Modul — kennt weder Eignungslogik noch Pfadplanung.
Hängt ab von trimesh/shapely, nicht von anderen fgc-Modulen.

Genutzt von:
  - ``fgc.slicer.sections`` (Schichtschnitte für den Toolpath)
  - ``fgc.eligibility`` (Grundriss-Polygon für check_footprint)

Keines dieser Module hängt vom anderen ab (Abhängigkeits-Invariante §5,
ADR-015).
"""

from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


def section_at(mesh: trimesh.Trimesh, z_mm: float) -> list[Polygon]:
    """Horizontaler Schnitt durch *mesh* bei *z_mm* (Welt-XY, mm).

    Liefert 0..n Umriss-Polygone in Welt-XY (Exterior CCW, Löcher CW),
    sortiert nach Schwerpunkt (x, dann y). Leere Liste, wenn der Schnitt
    kein Material trifft (z außerhalb der Mesh-Ausdehnung oder Lücke im Mesh).

    S2-Befund eingeplant: ein Schnitt kann mehrere disjunkte Polygone ergeben
    (z. B. schräge Oberkante, zwei separate Wandabschnitte).
    Löcher (Öffnungen) landen als interiors im shapely-Polygon.
    """
    section = mesh.section(plane_origin=[0, 0, z_mm], plane_normal=[0, 0, 1])
    if section is None:
        return []
    planar, to_3d = section.to_2D()
    polygons = []
    for poly in planar.polygons_full:
        if poly is None or poly.is_empty:
            continue
        polygons.append(orient(_to_world_xy(poly, to_3d), sign=1.0))
    # deterministische Reihenfolge: nach Schwerpunkt (x, dann y)
    polygons.sort(key=lambda p: (p.centroid.x, p.centroid.y))
    return polygons


def _to_world_xy(poly: Polygon, to_3d: np.ndarray) -> Polygon:
    """Path2D-Koordinaten zurück in Welt-XY (der Schnitt ist horizontal)."""

    def ring_to_world(coords) -> list[tuple[float, float]]:
        pts = np.asarray(coords, dtype=float)
        homogeneous = np.column_stack([pts, np.zeros(len(pts)), np.ones(len(pts))])
        world = (to_3d @ homogeneous.T).T
        return [(float(x), float(y)) for x, y, _, _ in world]

    return Polygon(
        ring_to_world(poly.exterior.coords),
        [ring_to_world(hole.coords) for hole in poly.interiors],
    )
