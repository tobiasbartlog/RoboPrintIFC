"""Schnittstelle des Musterkerns: Parameter, ParamSpec, Registry, fit_to_length, Geometrie-Helfer."""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import box

from roboprint import patterns as pt
from roboprint.patterns import registry


def test_params_defaults_and_validation():
    p = pt.PatternParams()
    assert (p.w, p.layer_height_mm, p.shells, p.layer_order) == (30.0, 10.0, 2, "alternate")
    assert p.corner_radius == 30.0 and p.transition_radius == 30.0
    assert (p.step_mm, p.chord_tol_mm, p.eps, p.delta_mm) == (20.0, 0.5, 0.15, 2.0)
    with pytest.raises(ValueError):
        pt.PatternParams(layer_order="zickzack").validate()
    with pytest.raises(ValueError):
        pt.PatternParams(shells=0).validate()


def test_params_from_dict_splits_extra_and_roundtrips():
    p = pt.params_from_dict({"bead_width_mm": 25, "field_length_mm": 300, "seam_corner": [1, -1]})
    assert p.w == 25 and p.get("field_length_mm") == 300 and p.seam_corner == (1, -1)
    d = p.to_dict()
    assert d["field_length_mm"] == 300 and d["seam_corner"] == [1, -1]
    assert pt.params_from_dict(d) == p


def test_paramspec_checks_range_and_choice():
    s = pt.ParamSpec("field_length_mm", "Feldlänge", 300.0, "mm", 150, 800)
    assert s.check(200) == 200.0
    with pytest.raises(ValueError):
        s.check(100)
    c = pt.ParamSpec("mirror", "Rückseite", "mirror", "", kind="choice", choices=("mirror", "offset"))
    assert c.check("offset") == "offset"
    with pytest.raises(ValueError):
        c.check("x")
    assert s.to_dict()["label"] == "Feldlänge"


@pytest.mark.parametrize(
    ("total", "target", "count", "length"),
    [(600, 250, 2, 300.0), (1000, 300, 3, 1000 / 3), (600, 1000, 1, 600.0), (900, 300, 3, 300.0)],
)
def test_fit_to_length(total, target, count, length):
    f = pt.fit_to_length(total, target)
    assert f.count == count and math.isclose(f.length_mm, length)
    assert len(f.positions_mm) == count + 1 and math.isclose(f.positions_mm[-1], total)
    assert math.isclose(f.deviation_mm, length - target)


def test_fit_to_length_bounds():
    assert pt.fit_to_length(1000, 450, max_mm=400).count == 3
    assert pt.fit_to_length(1000, 150, min_mm=200).count == 5
    assert pt.fit_to_length(100, 300, min_count=2).count == 2
    with pytest.raises(ValueError):
        pt.fit_to_length(0, 300)


def _dummy_build(ctx: pt.IslandContext) -> pt.IslandPlan:
    """Rechteckring der Schale 0 als ein geschlossenes outfill-Segment."""
    ring = ctx.lanes_of(0)[0]
    return pt.IslandPlan([pt.Segment("outfill", 0, ring, closed=True)], meta={"n": ctx.param("n")})


@pytest.fixture
def dummy_patterns():
    pt.register(
        pt.Pattern(
            "t_full",
            "full",
            "Test",
            _dummy_build,
            (pt.ParamSpec("n", "N", 3, "", 1, 9, kind="int"),),
            family="test",
        )
    )
    pt.register(pt.Pattern("t_infill", "infill", "Test", lambda ctx: [], family="test"))
    yield
    registry.unregister("t_full")
    registry.unregister("t_infill")


def test_registry_and_composition(dummy_patterns):
    assert "schalen" in pt.names() and "t_full" in pt.names("full")
    cat = {c["name"]: c for c in pt.catalog()}
    assert cat["t_full"]["params"][0]["name"] == "n"
    sec = {0: box(-300, -100, 300, 100), 1: box(-300, -100, 300, 100)}
    paths = pt.plan_pattern(sec, pt.params_from_dict({"outfill": "t_full", "n": 5}))
    assert [lp.meta["n"] for lp in paths] == [5, 5]
    assert paths[1].direction == "in_out"
    with pytest.raises(ValueError):  # Bereich der ParamSpec
        pt.plan_pattern(sec, pt.params_from_dict({"outfill": "t_full", "n": 50}))
    with pytest.raises(ValueError):  # full + zweites Muster
        pt.plan_pattern(sec, pt.params_from_dict({"outfill": "t_full", "infill": "t_infill"}))
    with pytest.raises(ValueError):  # Infill im Outfill-Platz
        pt.plan_pattern(sec, pt.params_from_dict({"outfill": "t_infill"}))
    with pytest.raises(KeyError):
        pt.plan_pattern(sec, pt.params_from_dict({"outfill": "gibt_es_nicht"}))
    # Preset: Rolle bestimmt den Platz
    assert pt.preset_params({"pattern": "t_infill", "params": {}}).infill == "t_infill"
    assert pt.preset_params({"pattern": "t_full", "params": {}}).outfill == "t_full"


def test_register_rejects_bad_names_and_duplicates(dummy_patterns):
    with pytest.raises(ValueError):
        pt.Pattern("Groß", "full", "x", _dummy_build)
    with pytest.raises(ValueError):
        pt.Pattern("x", "irgendwas", "x", _dummy_build)
    with pytest.raises(ValueError):
        pt.register(pt.Pattern("t_full", "infill", "anders", _dummy_build, family="andere"))


def test_segment_and_layerpath_reverse():
    a = pt.Segment("outer", 0, [[0, 0], [10, 0], [10, 10]])
    b = pt.Segment("inner", 1, [[10, 10], [20, 10]])
    lp = pt.LayerPath(0, 0, [a, b], [pt.Contact("shell", (5, 5), 3.0, (0, 1))])
    r = lp.reversed()
    assert np.allclose(r.start, lp.end) and np.allclose(r.end, lp.start)
    assert np.allclose(r.polyline(), lp.polyline()[::-1])
    assert r.direction == "in_out" and r.contacts[0].segments == (0, 1)
    with pytest.raises(ValueError):
        pt.Segment("diagonal", 0, [[0, 0], [1, 1]])
    with pytest.raises(ValueError):
        pt.Segment("outer", 0, [[0, 0], [1, 1], [2, 0]], closed=True)


def test_resample_curve_chord_and_step():
    th = np.linspace(0, math.pi, 2000)
    circ = np.column_stack([100 * np.cos(th), 100 * np.sin(th)])
    line = np.array([[-100, 0.0], [-100, -300]])
    pts = pt.resample_curve(np.vstack([circ, line[1:]]), 20.0, 0.5)
    assert np.all(np.linalg.norm(np.diff(pts, axis=0), axis=1) <= 20.0 + 1e-6)
    on_arc = pts[pts[:, 1] >= 0]
    mids = (on_arc[1:] + on_arc[:-1]) / 2
    assert np.all(100 - np.linalg.norm(mids, axis=1) <= 0.5 + 1e-6)  # Sehnenfehler
    assert np.allclose(pts[-1], [-100, -300])


def test_biarc_s_curve_is_exact_two_arcs():
    w = 30.0
    ell = 2 * math.sqrt(w**2 - (w - w / 2) ** 2)
    pts, r = pt.biarc(np.array([0.0, 0]), np.array([1.0, 0]), np.array([ell, w]), np.array([1.0, 0]), 0.05)
    assert math.isclose(r, w, rel_tol=1e-9)
    # Abstand genau w zum Mittelpunkt (0, w) bzw. (ell, 0): Kontakt, keine Überlappung
    assert np.linalg.norm(pts - [0, w], axis=1).min() >= w - 1e-6
    assert np.linalg.norm(pts - [ell, 0], axis=1).min() >= w - 1e-6


def test_fillet_and_curvature_radius():
    q, r = pt.fillet_polyline(np.array([[0, 0], [100, 0], [100, 100.0]]), 30.0, chord_tol_mm=0.05)
    assert math.isclose(r, 30.0)
    rad = pt.curvature_radius(q)
    assert np.nanmin(rad) == pytest.approx(30.0, rel=1e-6)
    sharp = pt.curvature_radius(np.array([[0, 0], [20, 0], [20, 20.0]]))
    assert sharp[1] < 15.0  # scharfe Ecke < w/2


def test_loop_and_offsets():
    ring = pt.offset_ring(box(-300, -100, 300, 100), 15.0, 30.0)
    assert len(ring) == 1 and ring[0][0] == "exterior"
    lp = pt.Loop(ring[0][1])
    s = lp.project(np.array([0.0, -85.0]))
    assert np.allclose(lp.point(s), [0, -85.0], atol=1e-6)
    seg = lp.sub(s, s + 100.0)
    assert math.isclose(pt.arc_length(seg)[-1], 100.0, rel_tol=1e-6)
