"""Wandanalyse-Heuristiken (fgc.ifc_io.analysis) mit synthetischen Meshes."""

import numpy as np
import pytest
import trimesh

from fgc.ifc_io.analysis import analyze_wall_mesh


def box_wall(length=2000.0, thickness=200.0, height=1000.0) -> np.ndarray:
    box = trimesh.creation.box(extents=[length, thickness, height])
    return np.asarray(box.vertices) + np.array([500.0, 300.0, height / 2])


def test_box_wall_dimensions():
    g = analyze_wall_mesh(box_wall())
    assert g.length_mm == pytest.approx(2000.0)
    assert g.height_mm == pytest.approx(1000.0)
    assert g.thickness_mm == pytest.approx(200.0)


def test_box_wall_is_planar():
    g = analyze_wall_mesh(box_wall())
    assert g.is_planar
    assert g.planarity_deviation_mm == pytest.approx(0.0, abs=1e-9)


def test_rotated_wall_dimensions_invariant():
    """Wandmaße dürfen nicht von der Grundriss-Ausrichtung abhängen (PCA)."""
    verts = box_wall()
    angle = np.deg2rad(37.0)
    rot = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0],
            [np.sin(angle), np.cos(angle), 0],
            [0, 0, 1],
        ]
    )
    g = analyze_wall_mesh(verts @ rot.T)
    assert g.length_mm == pytest.approx(2000.0)
    assert g.thickness_mm == pytest.approx(200.0)
    assert g.is_planar


def test_l_shaped_wall_fails_planarity():
    """Zwei rechtwinklige Schenkel — v1 gilt das als nicht planar (ADR-005)."""
    leg_a = trimesh.creation.box(extents=[2000, 200, 1000])
    leg_b = trimesh.creation.box(extents=[200, 2000, 1000])
    leg_b.apply_translation([900, 900, 0])
    l_wall = trimesh.util.concatenate([leg_a, leg_b])
    g = analyze_wall_mesh(np.asarray(l_wall.vertices))
    assert not g.is_planar


def test_degenerate_input_raises():
    with pytest.raises(ValueError):
        analyze_wall_mesh(np.zeros((2, 3)))
