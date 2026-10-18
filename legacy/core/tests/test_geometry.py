"""Tests für das neutrale Schnittmodul fgc.geometry.section (ADR-015).

Bekannte Meshes → erwartete Polygon-Anzahl und -Geometrie; Konsistenz mit
der bisherigen section_layers-Schnittstelle des Slicers.
"""

import pytest
import trimesh
from shapely.geometry import Polygon

from fgc.geometry.section import section_at


def box_mesh(
    length: float = 2000.0, thickness: float = 200.0, height: float = 1000.0
) -> trimesh.Trimesh:
    """Einfache Quader-Wand, z von 0 bis height."""
    mesh = trimesh.creation.box(extents=[length, thickness, height])
    mesh.apply_translation([0, 0, height / 2])
    return mesh


# ---------------------------------------------------------------------------
# Grundlegende section_at-Tests
# ---------------------------------------------------------------------------


def test_section_at_box_returns_one_polygon():
    """Schnitt durch eine Quader-Wand ergibt genau ein Polygon."""
    polys = section_at(box_mesh(), 500.0)
    assert len(polys) == 1
    assert isinstance(polys[0], Polygon)


def test_section_at_box_approximate_area():
    """Fläche des Schnittpolygons stimmt ungefähr mit Länge × Dicke überein."""
    length, thickness = 2000.0, 200.0
    polys = section_at(box_mesh(length=length, thickness=thickness), 500.0)
    assert polys[0].area == pytest.approx(length * thickness, rel=1e-3)


def test_section_at_above_mesh_returns_empty():
    """Schnitt oberhalb des Meshs liefert eine leere Liste."""
    polys = section_at(box_mesh(height=1000.0), 1500.0)
    assert polys == []


def test_section_at_below_mesh_returns_empty():
    """Schnitt unterhalb des Meshs liefert eine leere Liste."""
    polys = section_at(box_mesh(height=1000.0), -100.0)
    assert polys == []


def test_section_at_two_disjoint_boxes_gives_two_polygons():
    """S2-Befund: zwei getrennte Wandabschnitte ergeben zwei Polygone (sortiert)."""
    a = box_mesh(length=500.0)
    b = box_mesh(length=500.0)
    b.apply_translation([1000.0, 0.0, 0.0])
    combined = trimesh.util.concatenate([a, b])
    polys = section_at(combined, 500.0)
    assert len(polys) == 2
    # Sortierung: erster Schwerpunkt hat kleinere x-Koordinate
    assert polys[0].centroid.x < polys[1].centroid.x


def test_section_at_polygon_is_exterior_ccw():
    """Außenring ist gegen den Uhrzeigersinn orientiert (shapely-Konvention)."""
    polys = section_at(box_mesh(), 500.0)
    # shapely: exterior.is_ccw == True ⟺ CCW
    assert polys[0].exterior.is_ccw


# ---------------------------------------------------------------------------
# Konsistenz mit dem Slicer
# ---------------------------------------------------------------------------


def test_section_at_consistent_with_section_layers():
    """section_at und section_layers liefern für dieselbe Höhe dasselbe Polygon.

    Stellt sicher, dass die Extraktion des Schnitts in das neutrale Modul das
    Slicer-Verhalten nicht verändert (Regressionstest).
    """
    from fgc.slicer.sections import section_layers

    mesh = box_mesh(height=1000.0)
    layer_height = 100.0
    layers = section_layers(mesh, layer_height_mm=layer_height)

    # Erste Schicht bei z = 0 + 0.5 * 100 = 50 mm
    direct = section_at(mesh, 50.0)
    assert len(direct) == 1
    assert len(layers[0].polygons) == 1
    assert direct[0].area == pytest.approx(layers[0].polygons[0].area, rel=1e-6)

    # Alle Schichten konsistent
    for layer in layers:
        via_module = section_at(mesh, layer.z_mm)
        assert len(via_module) == len(layer.polygons)
        for p_module, p_layer in zip(via_module, layer.polygons, strict=True):
            assert p_module.area == pytest.approx(p_layer.area, rel=1e-6)
