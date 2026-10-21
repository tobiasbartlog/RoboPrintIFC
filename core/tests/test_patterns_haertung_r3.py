"""Härtung Runde 3: Regressionen der Gegenprüfung M6 (je Fehler ein Test, vor dem Fix rot)."""

from __future__ import annotations

import pytest
from shapely.geometry import LineString, Polygon

from roboprint import patterns as pt

L_WALL = Polygon([(0, 0), (1200, 0), (1200, 200), (200, 200), (200, 1200), (0, 1200)])
NOTCH = Polygon([(0, 0), (800, 0), (800, 300), (450, 300), (450, 200), (350, 200), (350, 300), (0, 300)])


@pytest.mark.parametrize("cr", [60.0, 90.0, 150.0, 200.0])
def test_corner_radius_keeps_l_legs(cr):
    """Eckenrundung rundet nur konvexe Ecken: Beide Schenkel des L bleiben in jeder Schale."""
    prm = pt.params_from_dict({"corner_radius_mm": cr})
    sec = {0: L_WALL, 1: L_WALL}
    paths = pt.plan_pattern(sec, prm)
    rep = pt.measure(paths, sec, prm)
    line = LineString(paths[0].polyline()[:, :2])
    assert rep.ok
    assert line.bounds[2] > 1150 and line.bounds[3] > 1150
    assert rep.paths[0].shell_coverage > 0.9
    for s in range(prm.shells):
        ring = [r for k, r in pt.offset_ring(L_WALL, (s + 0.5) * prm.w, cr) if k == "exterior"][0]
        assert LineString(ring).length > 0.9 * L_WALL.buffer(-(s + 0.5) * prm.w).exterior.length


def test_corner_radius_does_not_pinch_neck_under_notch():
    """Kerbe 100 × 100 in 800 × 300, drei Schalen, r = 97,5: Schale 0 bleibt an der Unterseite bei
    y = 15 (kein eingeschnürter Ring mit Knick, keine Kreuzung)."""
    prm = pt.params_from_dict({"corner_radius_mm": 97.5, "shells": 3})
    sec = {0: NOTCH, 1: NOTCH}
    paths = pt.plan_pattern(sec, prm)
    assert pt.measure(paths, sec, prm).ok
    ring = [r for k, r in pt.offset_ring(NOTCH, 15.0, 97.5) if k == "exterior"][0]
    bottom = ring[(ring[:, 0] > 300) & (ring[:, 0] < 500) & (ring[:, 1] < 150)]
    assert len(bottom) == 0 or bottom[:, 1].max() < 15.5


@pytest.mark.parametrize(("pattern", "cr"), [("schalen", 120.0), ("doppelwelle", 141.0), ("waben", 147.0)])
def test_corner_radius_l_250_preview_prints_whole_wall(pattern, cr):
    """L 800 × 800, Wand 250 mm (Vorschau/CLI): Pfad über den ganzen Querschnitt, nicht nur die Ecke."""
    outline = {"polygon": [[0, 0], [800, 0], [800, 250], [250, 250], [250, 800], [0, 800]]}
    d = pt.preview({"pattern": pattern, "params": {"corner_radius_mm": cr}, "outline": outline})
    assert d["ok"]
    assert d["metrics"]["shell_coverage"] > 0.85
    assert d["metrics"]["path_length_mm"] > 3000
