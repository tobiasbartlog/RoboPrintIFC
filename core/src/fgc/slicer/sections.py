"""Stufe 1 des Slicers: Mesh -> planare Schichtpolygone (ADR-005, ADR-015).

S2-Befund eingeplant: ein Schnitt kann MEHRERE disjunkte Polygone ergeben
(z. B. schräge Oberkante) — je Schicht kommt deshalb eine Polygonliste zurück.
Löcher (Öffnungen) landen als interiors im shapely-Polygon.

Der horizontale Mesh-Schnitt liegt im neutralen Modul ``fgc.geometry.section``
(ADR-015): Slicer und Eignungsprüfung rufen dasselbe Modul, keiner hängt vom
anderen ab.
"""

from __future__ import annotations

from dataclasses import dataclass

import trimesh
from shapely.geometry import Polygon

from fgc.geometry.section import section_at


@dataclass
class LayerSection:
    layer: int
    z_mm: float
    polygons: list[Polygon]  # Welt-XY in mm, Exterior CCW, Löcher CW


def section_layers(mesh: trimesh.Trimesh, layer_height_mm: float) -> list[LayerSection]:
    """Horizontale Schnitte in Schichtmitte: z_i = z_min + (i + 0.5) * h."""
    z_min, z_max = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    layers: list[LayerSection] = []
    i = 0
    while True:
        z = z_min + (i + 0.5) * layer_height_mm
        if z >= z_max:
            break
        layers.append(LayerSection(layer=i, z_mm=z, polygons=section_at(mesh, z)))
        i += 1
    return layers
