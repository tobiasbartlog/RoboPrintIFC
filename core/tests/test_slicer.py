"""Tests für den Slicer (A1.3)."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from roboprint.contracts import Toolpath
from roboprint.slicer import SliceParams, slice_part, to_toolpath

P = SliceParams()


def _box(lx, ly, lz):
    m = trimesh.creation.box([lx, ly, lz])
    m.apply_translation([0, 0, lz / 2])
    return m


def _wall_with_window():
    wall = trimesh.creation.box([1000, 200, 500])
    win = trimesh.creation.box([300, 300, 200])
    bore = trimesh.creation.box([100, 60, 700])  # senkrechte Aussparung -> echtes Loch
    bore.apply_translation([400, 0, 0])
    m = wall.difference(win).difference(bore)
    m.apply_translation([0, 0, 250])
    return m


def _section_poly(mesh, z):
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    planar, _ = sec.to_2D(to_2D=np.eye(4))
    return unary_union(planar.polygons_full)


def _signed_area(xy):
    x, y = xy[:, 0], xy[:, 1]
    return 0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])


def test_box_rings():
    sl = slice_part(_box(600, 200, 400), P)
    assert sl.n_layers == 40
    for L in range(40):
        rs = [r for r in sl.rings if r.layer == L]
        assert len(rs) == 2
        assert [r.shell for r in rs] == [0, 1]
        assert [r.kind for r in rs] == ["outer", "inner"]
        for r in rs:
            assert np.allclose(r.points[:, 2], (L + 1) * 10)
            assert np.allclose(r.points[0], r.points[-1])
            assert np.allclose(r.approach, r.points[0] + [0, 0, 20])
            assert np.allclose(r.retract, r.points[-1] + [0, 0, 20])
    xy = sl.rings[0].points[:, :2]
    assert np.isclose(xy[:, 0].max(), 285) and np.isclose(xy[:, 1].min(), -85)
    assert np.allclose(xy[0], [-285, -85])  # Ringstart an (x_min, y_min)


def test_sampling_corners_orientation():
    sl = slice_part(_box(600, 200, 100), P)
    xy = sl.rings[0].points[:, :2]
    assert np.linalg.norm(np.diff(xy, axis=0), axis=1).max() <= 20 + 1e-6
    for c in [(-285, -85), (285, -85), (285, 85), (-285, 85)]:
        assert np.min(np.linalg.norm(xy - c, axis=1)) < 1e-6
    assert _signed_area(xy) > 0


def test_window_holes_and_coverage():
    mesh = _wall_with_window()
    sl = slice_part(mesh, P)
    assert sl.n_layers == 50
    assert {r.kind for r in sl.rings if r.layer == 20} == {"outer", "inner", "hole"}
    assert len([r for r in sl.rings if r.layer == 20 and r.shell == 0 and r.kind == "outer"]) == 2
    assert {r.kind for r in sl.rings if r.layer == 2} == {"outer", "inner", "hole"}
    for r in sl.rings:
        a = _signed_area(r.points[:, :2])
        assert (a < 0) if r.kind == "hole" else (a > 0)
    for L in range(50):
        sec = _section_poly(mesh, (L + 0.5) * 10)
        shell_area = sec.difference(sec.buffer(-2 * 30, join_style="mitre"))
        lines = [LineString(r.points[:, :2]) for r in sl.rings if r.layer == L]
        cov = unary_union([ln.buffer(15) for ln in lines]).intersection(shell_area)
        assert cov.area / shell_area.area >= 0.95, L


def test_two_contours_order():
    a, b = _box(200, 200, 100), _box(200, 200, 100)
    b.apply_translation([600, 0, 0])
    sl = slice_part(trimesh.util.concatenate([a, b]), P)
    rs = [r for r in sl.rings if r.layer == 0]
    assert [r.shell for r in rs] == [0, 0, 1, 1]


def test_thin_wall_drops_second_shell():
    sl = slice_part(_box(300, 50, 30), P)
    assert [r.shell for r in sl.rings if r.layer == 0] == [0]


def test_toolpath_valid():
    sl = slice_part(_box(600, 200, 100), P)
    T = np.eye(4)
    T[:3, 3] = [1000, 500, 800]
    tp = to_toolpath(sl, T, "p0")
    Toolpath.model_validate(tp.model_dump())
    w = tp.rings[0].waypoints
    assert w[0][2] == pytest.approx(810) and w[0][3:] == [0.0, 1.0, 0.0, 0.0]
    assert w[0] == w[-1]


# --- A4.5: schmale und kleine Querschnitte (Prüfer-Metrik aus verify/oracle/run_geometry.coverage) ---


def _oracle_coverage(sec, rings_xy, shells=2, w=30.0):
    region = sec.difference(sec.buffer(-shells * w, join_style="mitre"))
    if region.area <= 0:
        return 1.0
    beads = [LineString(p).buffer(w / 2.0) for p in rings_xy if len(p) >= 2]
    if not beads:
        return 0.0
    return unary_union(beads).intersection(region).area / region.area


def _assert_layers_covered(mesh, sl):
    H = float(mesh.bounds[1][2])
    for L in range(sl.n_layers):
        z = (L + 0.5) * 10
        if z >= H:
            continue
        sec = _section_poly(mesh, z)
        rs = [r.points[:, :2] for r in sl.rings if r.layer == L]
        assert _oracle_coverage(sec, rs) >= 0.95, L
        grown = sec.buffer(1.0)  # Selbstprüfung (d): Druckpunkt im Material, Toleranz 1 mm
        for p in rs:
            assert all(grown.contains(Point(*q)) for q in p), L


def _gable():
    """Giebelteil wie house_right_front_r9: 600 x 200, Oberkante in y abfallend (Dachneigung)."""
    prof = Polygon([(-100, 0), (100, 0), (100, 180), (-100, 296)])  # (y, z)
    m = trimesh.creation.extrude_polygon(prof, 600)  # Profil in xy, extrudiert in z
    perm = np.array([[0, 0, 1, -300], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1.0]])
    m.apply_transform(perm)  # (y, z, x) -> (x, y, z)
    return m


def test_gable_top_layers_covered():
    mesh = _gable()
    assert np.allclose(mesh.bounds, [[-300, -100, 0], [300, 100, 296]], atol=1e-6)
    sl = slice_part(mesh, P)
    _assert_layers_covered(mesh, sl)
    assert any(r.layer == 29 for r in sl.rings)  # Spitze (2 mm breit) wird gedruckt


def test_narrow_wedge_covered():
    wedge = Polygon([(0, -40), (0, 40), (600, 0)])  # Grundriss läuft spitz zu
    mesh = trimesh.creation.extrude_polygon(wedge, 40)
    sl = slice_part(mesh, P)
    _assert_layers_covered(mesh, sl)


def test_small_area_gets_path():
    mesh = _box(12, 8, 30)
    sl = slice_part(mesh, P)
    assert {r.layer for r in sl.rings} == {0, 1, 2}
    _assert_layers_covered(mesh, sl)
