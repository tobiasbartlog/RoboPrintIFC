import numpy as np
import pytest
import trimesh

from roboprint import geometry as geo


def _wall_with_window():
    """Wand 3000 x 200 x 2500 mit Fensterloch x 1000..1800, z 800..1600 (Volumen exakt bekannt)."""
    wall = geo.make_box((3000, 200, 2500))
    hole = geo.make_box((800, 400, 800), origin=(1000, -100, 800))
    res = geo._to_manifold(wall) - geo._to_manifold(hole)
    return geo._from_manifold(res), 3000 * 200 * 2500 - 800 * 200 * 800


def test_make_box():
    b = geo.make_box((10, 20, 30), origin=(1, 2, 3))
    assert b.is_watertight
    assert b.bounds.tolist() == [[1, 2, 3], [11, 22, 33]]
    assert geo.volume(b) == pytest.approx(6000)
    with pytest.raises(ValueError):
        geo.make_box((0, 1, 1))


def test_cut_box_volume_and_bounds():
    wall, vol = _wall_with_window()
    assert wall.is_watertight and geo.volume(wall) == pytest.approx(vol, rel=1e-6)
    part = geo.cut_box(wall, (500, -10, 0), (1500, 300, 1000))
    assert part.is_watertight
    assert part.bounds[0] == pytest.approx([500, 0, 0], abs=1e-3)
    assert part.bounds[1] == pytest.approx([1500, 200, 1000], abs=1e-3)
    # Quader 1000 x 200 x 1000 minus Fensteranteil x 1000..1500, z 800..1000
    assert geo.volume(part) == pytest.approx(1000 * 200 * 1000 - 500 * 200 * 200, rel=1e-6)
    assert geo.is_empty(geo.cut_box(wall, (5000, 0, 0), (6000, 100, 100)))


def test_raster_blocks_conserve_volume():
    wall, vol = _wall_with_window()
    xs = [0, 750, 1500, 2250, 3000]
    zs = [0, 800, 1600, 2500]  # Schnittebenen auf Fensterober- und -unterkante
    total = 0.0
    for x0, x1 in zip(xs[:-1], xs[1:], strict=True):
        for z0, z1 in zip(zs[:-1], zs[1:], strict=True):
            blk = geo.cut_box(wall, (x0, -1, z0), (x1, 201, z1))
            if not geo.is_empty(blk):
                assert blk.is_watertight
            total += geo.volume(blk)
    assert total == pytest.approx(vol, rel=1e-3)
    assert total == pytest.approx(geo.volume(wall), rel=1e-3)


def test_clip_below():
    wall, _ = _wall_with_window()
    c = geo.clip_below(wall, 1200)
    assert c.is_watertight
    assert c.bounds[1][2] == pytest.approx(1200, abs=1e-3)
    assert geo.volume(c) == pytest.approx(3000 * 200 * 1200 - 800 * 200 * 400, rel=1e-6)
    assert geo.is_empty(geo.clip_below(wall, -5))
    assert geo.volume(geo.clip_below(wall, 1e6)) == pytest.approx(geo.volume(wall), rel=1e-9)


def test_slice_section_with_hole_and_window():
    wall, _ = _wall_with_window()
    s = geo.slice_section(wall, 1200)  # durch das Fenster: zwei getrennte Pfeiler
    assert s.geom_type == "MultiPolygon" and len(s.geoms) == 2
    assert s.area == pytest.approx((3000 - 800) * 200, rel=1e-6)
    s2 = geo.slice_section(wall, 400)
    assert s2.geom_type == "Polygon" and s2.area == pytest.approx(3000 * 200, rel=1e-6)
    assert geo.slice_section(wall, 3000).is_empty


def test_slice_section_polygon_with_hole():
    outer = geo.make_box((100, 100, 50))
    inner = geo.make_box((40, 40, 60), origin=(30, 30, -5))
    ring = geo._from_manifold(geo._to_manifold(outer) - geo._to_manifold(inner))
    s = geo.slice_section(ring, 25)
    assert s.geom_type == "Polygon" and len(s.interiors) == 1
    assert s.area == pytest.approx(100 * 100 - 40 * 40, rel=1e-9)


def test_overlap_and_intersection_volume():
    a = geo.make_box((10, 10, 10))
    b = geo.make_box((10, 10, 10), origin=(5, 0, 0))
    c = geo.make_box((10, 10, 10), origin=(10, 0, 0))  # beruehrt nur
    assert geo.intersection_volume(a, b) == pytest.approx(500)
    assert geo.overlaps(a, b) and not geo.overlaps(a, c)


def test_ensure_watertight_repairs_open_and_unwelded_mesh():
    box = trimesh.creation.box(extents=(10, 10, 10))
    # unverschweisst: jedes Dreieck mit eigenen Vertices
    tri = box.vertices[box.faces].reshape(-1, 3)
    soup = trimesh.Trimesh(tri, np.arange(len(tri)).reshape(-1, 3), process=False)
    assert not soup.is_watertight
    fixed = geo.ensure_watertight(soup)
    assert fixed.is_watertight and geo.volume(fixed) == pytest.approx(1000)
    # ein Dreieck fehlt (Loch)
    holey = trimesh.Trimesh(box.vertices, box.faces[1:], process=False)
    assert not holey.is_watertight
    fixed = geo.ensure_watertight(holey)
    assert fixed.is_watertight and geo.volume(fixed) == pytest.approx(1000, rel=1e-6)
