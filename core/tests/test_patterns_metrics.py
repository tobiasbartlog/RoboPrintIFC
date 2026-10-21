"""metrics.py gegen konstruierte Gegenbeispiele (Kreuzung, Überhang, diagonaler Wechsel, enger
Radius, außerhalb, Lücke) und gegen den gewollten Kontakt, der KEIN Verstoß ist."""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import box

from roboprint import patterns as pt

W = 30.0
P = pt.PatternParams()
SEC = box(-300, -200, 300, 200)


def _path(points, layer=0, kind="infill", closed=False, island=0):
    pts = pt.densify(np.asarray(points, float), 20.0)
    return pt.LayerPath(layer, island, [pt.Segment(kind, 2, pts, closed=closed)])


def _hairpin(gap: float) -> list:
    """Zwei gerade Schenkel im Mittenabstand `gap`, verbunden über einen Halbkreis."""
    r = gap / 2
    arc = [(200 + r * math.sin(t), -r * math.cos(t)) for t in np.linspace(0, math.pi, 40)]
    return [(-200, -r), *arc, (-200, r)]


def test_intended_contact_is_not_a_violation():
    lp = _path(_hairpin(W))  # Schenkel berühren sich genau (Abstand w), Wenderadius w/2
    m, v = pt.metrics.measure_path(lp, SEC, P)
    assert not [x for x in v if x.severity == "error"], [x.to_dict() for x in v]
    assert len(m.contacts) == 1 and m.contacts[0].length_mm > 300
    assert abs(m.contacts[0].distance_mm - W) < 0.1
    # Wenderadius w/2 ist hart erlaubt, aber unter dem Ziel w: nur Warnung
    assert {x.rule for x in v} == {"M6"} and all(x.severity == "warn" for x in v)


def test_contact_with_overlap_up_to_eps_is_ok_beyond_is_error():
    _, v = pt.metrics.measure_path(_path(_hairpin(0.86 * W)), SEC, P)
    assert "M2" not in {x.rule for x in v if x.severity == "error"}
    _, v = pt.metrics.measure_path(_path(_hairpin(0.8 * W)), SEC, P)
    assert "M2" in {x.rule for x in v if x.severity == "error"}


def test_crossing_is_m2_error_with_location():
    lp = _path([(-150, -100), (150, 100), (150, -100), (-150, 100)])
    _, v = pt.metrics.measure_path(lp, SEC, P)
    m2 = [x for x in v if x.rule == "M2"]
    assert m2 and np.hypot(*m2[0].at) < 20  # Kreuzung bei (0, 0)


def test_tight_radius_is_m6_error():
    lp = _path([(-100, 0), (0, 0), (0, 100)])  # scharfe 90°-Ecke
    _, v = pt.metrics.measure_path(lp, SEC, P)
    m6 = [x for x in v if x.rule == "M6" and x.severity == "error"]
    assert m6 and np.allclose(m6[0].at, (0, 0))


def test_outside_part_is_m5_error():
    lp = _path([(-100, 0), (100, 0), (100, 195)])
    _, v = pt.metrics.measure_path(lp, SEC, P)
    assert "M5" in {x.rule for x in v if x.severity == "error"}


def test_gap_in_strand_is_m1_error():
    a = pt.Segment("infill", 2, pt.densify(np.array([[-200.0, 0], [-50, 0]]), 20))
    b = pt.Segment("infill", 2, pt.densify(np.array([[50.0, 0], [200, 0]]), 20))
    _, v = pt.metrics.measure_path(pt.LayerPath(0, 0, [a, b]), SEC, P)
    assert "M1" in {x.rule for x in v}


def test_two_strands_for_one_island_is_m1_error():
    a = _path([(-200, -100), (200, -100)])
    b = _path([(-200, 100), (200, 100)])
    rep = pt.measure([a, b], {0: SEC}, P)
    assert "M1" in rep.rules_violated()


def _ring(dx=0.0):
    return np.array(
        [(-285 + dx, -185), (285 + dx, -185), (285 + dx, 185), (-285 + dx, 185), (-285 + dx, -185)]
    )


def test_overhang_is_m3_error():
    sec = {0: SEC, 1: SEC}
    rr, _ = pt.fillet_polyline(_ring(), 30.0, closed=True, chord_tol_mm=0.05)
    shifted = rr + [10.0, 0.0]  # 10 mm > δ = 2 mm Versatz nach x
    l0 = pt.LayerPath(0, 0, [pt.Segment("outer", 0, rr, closed=True)])
    l1 = pt.LayerPath(1, 0, [pt.Segment("outer", 0, shifted[::-1], closed=True)], direction="in_out")
    rep = pt.measure([l0, l1], sec, P)
    assert "M3" in rep.rules_violated()
    ok = pt.LayerPath(1, 0, [pt.Segment("outer", 0, (rr + [1.5, 0])[::-1], closed=True)])
    assert "M3" not in pt.measure([l0, ok], sec, P).rules_violated()


def test_diagonal_layer_change_is_m4_error_and_vertical_is_ok():
    sec = {0: SEC, 1: SEC}
    pts = pt.densify(np.array([[-200.0, -100], [200, -100], [200, 100], [-200, 100]]), 20)
    lp = pt.LayerPath(0, 0, [pt.Segment("inner", 1, pts)])
    diag = pt.LayerPath(1, 0, [pt.Segment("inner", 1, pts.copy())])  # beginnt wieder vorn
    rep = pt.measure([lp, diag], sec, P)
    assert "M4" in rep.rules_violated() and rep.layer_changes[0]["status"] == "diagonal"
    rep = pt.measure([lp, lp.reversed(layer=1)], sec, P)
    assert "M4" not in rep.rules_violated() and rep.layer_changes[0]["status"] == "vertical"


def test_seam_on_outer_face_is_m4_warning():
    pts = pt.densify(np.array([[0.0, -185], [200, -185], [200, 0]]), 20)
    pts, _ = pt.fillet_polyline(pts, 40.0, chord_tol_mm=0.05)
    _, v = pt.metrics.measure_path(pt.LayerPath(0, 0, [pt.Segment("outer", 0, pts)]), SEC, P)
    assert any(x.rule == "M4" and x.severity == "warn" for x in v)


def test_joint_and_node_contacts_and_unsupported_outer():
    """Zwei Außenfelder stoßen stumpf (Fuge), ein Steg stützt das zweite Feld."""
    w = W
    f1 = pt.Segment("outfill", 0, pt.densify(np.array([[-280.0, -185], [-15, -185]]), 20))
    up, _ = pt.fillet_polyline(
        np.array([[-15.0, -185], [-15, -60], [-15 + w, -60], [-15 + w, -185]]), w / 2, chord_tol_mm=0.05
    )
    web = pt.Segment("web", 2, up)
    f2 = pt.Segment("outfill", 0, pt.densify(np.array([[15.0, -185], [280, -185]]), 20))
    lp = pt.LayerPath(0, 0, [f1, web, f2])
    m, v = pt.metrics.measure_path(lp, SEC, P)
    assert not [x for x in v if x.severity == "error"], [x.to_dict() for x in v]
    kinds = {c.kind for c in m.contacts}
    assert kinds == {"joint", "node"}  # Fuge zwischen den Feldern, Knoten zwischen den Steg-Schenkeln
    joint = next(c for c in m.contacts if c.kind == "joint")
    assert np.allclose(joint.at, (0, -185), atol=2) and m.joint_x_mm == [joint.at[0]]
    assert m.longest_straight_outer_mm < 270  # Feld endet am Steg bzw. an der Fuge


def test_section_change_with_same_island_count_is_no_m4_exception():
    """AUFTRAG M4 nimmt nur Inselzahlwechsel aus (wie das Orakel): Ein diagonaler Wechsel bei
    geändertem Querschnitt, aber gleicher Inselzahl, ist ein Fehler, auch mit `restart`."""
    sec = {0: SEC, 1: box(-300, -200, 300, 180)}
    pts = pt.densify(np.array([[-200.0, -100], [200, -100], [200, 100], [-200, 100]]), 20)
    lp = pt.LayerPath(0, 0, [pt.Segment("inner", 1, pts)])
    diag = pt.LayerPath(1, 0, [pt.Segment("inner", 1, pts[:-1].copy())], restart=True)
    rep = pt.measure([lp, diag], sec, P)
    assert rep.layer_changes[0]["status"] == "diagonal" and "M4" in {v.rule for v in rep.errors}
    # Inselzahl ändert sich: dokumentierter Neubeginn, kein Fehler
    two = {0: SEC, 1: box(-300, -200, -10, 200).union(box(10, -200, 300, 200))}
    rep = pt.measure([lp, diag], two, P)
    assert rep.layer_changes[0]["status"] == "restart" and "M4" not in {v.rule for v in rep.errors}


@pytest.mark.parametrize("name", ["schalen", "sinus", "fugenwand"])
def test_island_without_strand_is_m1_error(name):
    """Ein 25 mm breiter Pfeiler ist mit w = 30 nicht druckbar; er darf nicht still entfallen
    (measure meldete ok=True mit weniger Strängen als Inseln)."""
    from shapely.geometry import MultiPolygon

    from roboprint.patterns.preview import params_for

    g = MultiPolygon([box(0, 0, 400, 200), box(600, 0, 625, 200)])
    sec = {0: g, 1: g}
    pp = params_for(name)
    paths = pt.plan_pattern(sec, pp)
    assert {lp.island for lp in paths} == {0}
    rep = pt.measure(paths, sec, pp)
    missing = [v for v in rep.errors if v.rule == "M1" and v.island == 1]
    assert {v.layer for v in missing} == {0, 1} and not rep.ok
    assert all("ohne Strang" in v.message for v in missing)
