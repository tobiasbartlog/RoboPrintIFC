"""Grundmuster „Schalen ohne Infill“ und alternierende Schichtfolge (AUFTRAG Ziel 1, M1–M7)."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from roboprint import patterns as pt


def _prism(geom, n=4):
    return {L: geom for L in range(n)}


def _check_clean(paths, sections, params):
    rep = pt.measure(paths, sections, params)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    return rep


@pytest.mark.parametrize("thickness", [200.0, 300.0, 365.0])
def test_two_shells_rectangle(thickness):
    sec = _prism(box(-300, -thickness / 2, 300, thickness / 2))
    p = pt.PatternParams()
    paths = pt.plan_pattern(sec, p)
    assert [lp.layer for lp in paths] == [0, 1, 2, 3]  # M1: ein Strang je Schicht
    rep = _check_clean(paths, sec, p)
    assert not rep.violations  # auch keine Warnungen (Radius ≥ w, Naht frei)
    lp = paths[0]
    assert [s.kind for s in lp.segments] == ["outer", "inner"] and lp.direction == "out_in"
    assert all(np.allclose(a, b) for a, b in lp.connectors())  # Verbinder Länge 0
    # alternate: ungerade Schicht ist die exakte Umkehrung, Wechsel senkrecht
    rev = [s.points for s in paths[1].segments]
    assert all(np.array_equal(a, b.points[::-1]) for a, b in zip(rev, lp.segments[::-1], strict=True))
    assert all(c["status"] == "vertical" and c["distance_mm"] == 0.0 for c in rep.layer_changes)
    # kein Doppelmaterial: kleinster Abstand bei Bogenlängenabstand > 2w ist ≥ (1 − ε)·w
    m = rep.paths[0]
    assert m.min_clearance_mm >= (1 - p.eps) * p.w
    assert m.min_radius_mm >= p.w * 0.999
    assert {c.kind for c in m.contacts} == {"shell"}
    # Naht (M4): Raupe berührt weder Außen- (y) noch Stoßfläche (x)
    for e in (lp.start, lp.end):
        assert pt.face_clearance(e[None, :], sec[0], (-300, -thickness / 2, 300, thickness / 2), p.w)[0] > 0
    assert lp.meta["fallback"] is False
    # Außenstrecke: gerade Länge der Längsseite (600 − 2·(w/2 + r))
    assert m.longest_straight_outer_mm == pytest.approx(600 - 2 * (15 + 30), abs=0.5)


def test_same_order_has_diagonal_layer_change():
    sec = _prism(box(-300, -100, 300, 100))
    p = pt.PatternParams(layer_order="same")
    paths = pt.plan_pattern(sec, p)
    assert all(lp.direction == "out_in" for lp in paths)
    rep = pt.measure(paths, sec, p)
    assert rep.rules_violated() == {"M4"}
    assert all(c["status"] == "diagonal" for c in rep.layer_changes)


def test_l_section_seam_off_protected_faces():
    poly = Polygon([(0, 0), (600, 0), (600, 200), (200, 200), (200, 600), (0, 600)])
    sec = _prism(poly)
    p = pt.PatternParams()
    paths = pt.plan_pattern(sec, p)
    rep = _check_clean(paths, sec, p)
    seam = np.array(paths[0].meta["seam"])
    # Naht an der Innenecke des L, nicht an einer Ebene der Bounding-Box
    assert 150 < seam[0] < 250 and 150 < seam[1] < 250
    assert all(c["status"] == "vertical" for c in rep.layer_changes)


def test_two_islands_each_one_strand_and_vertical_change():
    geom = MultiPolygon([box(-300, -100, -50, 100), box(50, -100, 300, 100)])
    sec = _prism(geom)
    p = pt.PatternParams()
    paths = pt.plan_pattern(sec, p)
    assert [(lp.layer, lp.island) for lp in paths] == [
        (0, 0),
        (0, 1),
        (1, 1),
        (1, 0),
        (2, 0),
        (2, 1),
        (3, 1),
        (3, 0),
    ]
    rep = _check_clean(paths, sec, p)
    assert all(c["status"] == "vertical" for c in rep.layer_changes)
    # Naht an der Laibung (x = ±50 ist keine geschützte Ebene des Teils)
    assert abs(paths[0].meta["seam"][0]) < 100


def test_section_change_is_documented_restart():
    sec = {
        0: box(-300, -100, 300, 100),
        1: box(-300, -100, 300, 100),
        2: MultiPolygon([box(-300, -100, -50, 100), box(50, -100, 300, 100)]),
    }
    p = pt.PatternParams()
    paths = pt.plan_pattern(sec, p)
    assert [lp.restart for lp in paths] == [False, False, True, False]
    rep = pt.measure(paths, sec, p)
    statuses = [c["status"] for c in rep.layer_changes]
    assert statuses[0] == "vertical" and statuses[1] in ("restart", "vertical")
    assert "M4" not in rep.rules_violated()


@pytest.mark.parametrize("shells", [1, 3])
def test_other_shell_counts(shells):
    sec = _prism(box(-300, -150, 300, 150), 2)
    p = pt.PatternParams(shells=shells)
    paths = pt.plan_pattern(sec, p)
    assert len(paths[0].segments) == shells
    if shells == 1:
        assert paths[0].segments[0].closed and paths[0].closed
    _check_clean(paths, sec, p)


def test_layer_invariant_cache_shares_geometry():
    sec = _prism(box(-300, -100, 300, 100), 6)
    paths = pt.plan_pattern(sec)
    assert paths[0].segments[0].points is paths[2].segments[0].points
    assert not paths[0].segments[0].points.flags.writeable


@pytest.mark.parametrize(
    "name,w,shells,size",
    [("schalen", 40, 3, (600, 200)), ("sinus", 35, 3, (1200, 150)), ("waben", 40, 3, (600, 180))],
)
def test_missing_offset_ring_reports_dropped_shells(name, w, shells, size):
    """Passt eine Schale gar nicht mehr (Offset-Ring leer), steht das wie beim Restring in
    meta.shells_dropped mit Hinweis, statt die Schalenzahl still zu verringern."""
    d = pt.preview({"pattern": name, "params": {"bead_width_mm": w, "shells": shells}}, size)
    m = d["paths"][0]["meta"]
    assert m["shells"] < shells
    note = m["shells_dropped"]
    assert note["from_shell"] == m["shells"] and note["count"] == shells - m["shells"]
    assert "passt nicht" in note["hint"]


@pytest.mark.parametrize(
    "spec,size",
    [
        ({"pattern": "schalen", "params": {"bead_width_mm": 30, "shells": 2}}, (600, 120)),
        ({"pattern": "schalen", "params": {"bead_width_mm": 35, "shells": 3}}, (600, 200)),
        ({"pattern": "schalen", "params": {"bead_width_mm": 40, "shells": 2}}, (600, 150)),
        ({"pattern": "trapez", "params": {"bead_width_mm": 40, "shells": 2}}, (600, 150)),
        ({"pattern": "aussenwelle", "params": {"bead_width_mm": 35, "shells": 2}}, (2000, 120)),
        (
            {
                "pattern": "fugenwand",
                "params": {
                    "bead_width_mm": 35,
                    "belt": True,
                    "web_angle_deg": 80,
                    "joint_gap_mm": 30,
                    "hook_radius_mm": 15,
                },
            },
            (250, 120),
        ),
    ],
)
def test_too_narrow_inner_shell_falls_back_to_fewer_shells(spec, size):
    """Ein innerer Schalenring, der lang genug, aber zu schmal ist (Stadion von w Breite, Radius
    < w/2), entfällt mit Hinweis statt M2/M5/M6-Fehler zu erzeugen (wie `topologie`)."""
    d = pt.preview(spec, size)
    assert d["ok"], [v for v in d["violations"] if v["severity"] == "error"][:3]
    metas = [d["paths"][0]["meta"]]
    metas += [v for k, v in metas[0].items() if isinstance(v, dict)]
    note = next(m["shells_dropped"] for m in metas if "shells_dropped" in m)
    assert note["count"] >= 1 and note["hint"]


@pytest.mark.parametrize("name", ["schalen", "sinus", "fugenwand"])
def test_narrow_second_pier_planned_without_errors(name):
    from roboprint.patterns.preview import params_for

    g = MultiPolygon([box(0, 0, 400, 200), box(600, 0, 710, 200)])
    sec = {0: g, 1: g}
    pp = params_for(name)
    rep = pt.measure(pt.plan_pattern(sec, pp), sec, pp)
    assert rep.ok, [v.to_dict() for v in rep.errors][:3]


@pytest.mark.parametrize("T,depth", [(250, 60), (200, 80), (250, 80), (200, 60)])
@pytest.mark.parametrize("extra", [{}, {"infill": "sinus"}, {"infill": "trapez"}])
def test_v_notch_base_pattern_stays_inside_and_printable(T, depth, extra):
    """V-Kerbe 60 mm breit, 60…80 mm tief: Das Grundmuster (und die Infill-Familien darauf)
    druckte außerhalb des Teils (M5) bzw. mit Knick (M6); jetzt Rückfall auf weniger Schalen."""
    g = Polygon([(0, 0), (270, 0), (300, depth), (330, 0), (600, 0), (600, T), (0, T)])
    p = pt.params_from_dict({"shells": 2, **extra})
    sec = {0: g, 1: g}
    rep = pt.measure(pt.plan_pattern(sec, p), sec, p)
    assert rep.ok, [v.to_dict() for v in rep.errors][:3]


@pytest.mark.parametrize("length", [600.0, 1200.0])
@pytest.mark.parametrize("extra", [{}, {"outfill": "topologie"}, {"infill": "sinus"}])
def test_rect_notch_single_shell_has_no_near_duplicate_kink(length, extra):
    """Rechteckkerbe, eine Schale: Der gerundete Offset-Ring hatte am Bogenstoß einen Rückwärts-
    schritt von 0,006 mm; er blieb beim Abtasten als Ecke erhalten (falscher M6-Fehler r = 1,3 mm)."""
    g = box(0, 0, length, 200).difference(box(length / 2 - 30, -1, length / 2 + 30, 20))
    p = pt.params_from_dict({"shells": 1, **extra})
    sec = {0: g, 1: g}
    paths = pt.plan_pattern(sec, p)
    for seg in paths[0].segments:
        steps = np.linalg.norm(np.diff(seg.points, axis=0), axis=1)
        assert steps.min() > 0.02, (seg.kind, steps.min())
    rep = pt.measure(paths, sec, p)
    assert rep.ok, [v.to_dict() for v in rep.errors][:3]
