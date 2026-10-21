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


LOCH = {
    "polygon": [[0, 0], [1200, 0], [1200, 365], [0, 365]],
    "holes": [[[400, 120], [800, 120], [800, 245], [400, 245]]],
}


@pytest.mark.parametrize(
    ("size", "params"),
    [
        ((600, 300), {"transition_radius_mm": 150, "infill": "sinus"}),
        ((600, 300), {"transition_radius_mm": 200, "infill": "zickzack"}),
        ((600, 365), {"transition_radius_mm": 185.8, "infill": "sinus", "shells": 1}),
        ((450, 250), {"transition_radius_mm": 170.9, "infill": "maeander", "shells": 3,
                      "bead_width_mm": 24.8}),  # fmt: skip
        ((1200, 300), {"transition_radius_mm": 125, "infill": "zickzack", "bead_width_mm": 22.6}),
    ],
)
def test_large_transition_radius_with_infill_stays_in_part(size, params):
    """Gegenprüfung M6 (Runde 3, gemeldet: Schale 1 bis 13 mm außerhalb der Stirnfläche, M5). Auf
    v2/muster-haertung nicht nachstellbar (Kern, Vorschau und run-scenario + verify_muster grün);
    der Test hält das Verhalten fest: kein M5, Pfad ok."""
    from shapely.geometry import box

    sec0 = box(-size[0] / 2, -size[1] / 2, size[0] / 2, size[1] / 2)
    sec = {i: sec0 for i in range(3)}
    prm = pt.params_from_dict(params)
    rep = pt.measure(pt.plan_pattern(sec, prm), sec, prm)
    assert rep.ok, [(v.rule, v.value, v.at) for v in rep.errors][:3]


HOLE_PATTERNS =["schalen", "topologie", "fugenwand", "aussenwelle", "fermat", "maeander"]


@pytest.mark.parametrize("pattern", HOLE_PATTERNS)
@pytest.mark.parametrize("shells", [2, 1])
def test_section_with_hole_is_one_simple_strand(pattern, shells):
    """Querschnitt mit Innenloch: Vorher hing jedes Muster das Loch mit einem 340–373 mm langen
    Verbinder quer über die Schalen an (M1/M2, Pfad nicht einfach). Jetzt läuft jede Schale durch
    einen Schlitz an der dünnsten Stelle um das Loch: ein einfacher, kreuzungsfreier Strang."""
    d = pt.preview({"pattern": pattern, "params": {"shells": shells}, "outline": LOCH})
    assert d["ok"], [(v["rule"], v["message"]) for v in d["violations"] if v["severity"] == "error"]
    assert len(d["paths"]) == 1
    pts = [q for seg in d["paths"][0]["segments"] for q in seg["points"]]
    line = LineString(pts)
    assert line.is_simple
    hole = Polygon(LOCH["holes"][0])
    assert line.distance(hole.exterior) < 30.0  # das Loch hat eine Schale
    steps = [LineString([a, b]).length for a, b in zip(pts[:-1], pts[1:], strict=False)]
    assert max(steps) <= 60.0


def test_keyhole_slit_at_thinnest_place():
    reg = Polygon(LOCH["polygon"], [LOCH["holes"][0]])
    kh = pt.keyhole(reg)
    assert not kh.interiors and abs(kh.area - reg.area) < 0.1 * 120 + 1
    slit = reg.difference(kh)
    x0, y0, x1, y1 = slit.bounds
    assert abs((x0 + x1) / 2 - 600) < 1 and (y1 - y0) > 119  # Mitte des 400-mm-Stegs, 120 mm lang
    assert pt.keyhole(Polygon(LOCH["polygon"])).equals(Polygon(LOCH["polygon"]))


@pytest.mark.parametrize("pattern", ["sinus", "zickzack", "trapez", "maeander"])
@pytest.mark.parametrize(("w", "t"), [(25.0, 100.0), (30.0, 120.0), (40.0, 160.0)])
def test_single_ring_infill_never_skips_outer_lane(pattern, w, t):
    """Einzelring + Infill bei Wanddicke ≈ 4·w: Die S-Kurve ins Infill ließ 54–91 mm der Außenbahn
    aus (M1), ohne Hinweis. Jetzt entfällt das Infill mit Hinweis und der Ring bleibt geschlossen."""
    params = {"bead_width_mm": w, "shells": 1, "layer_order": "alternate"}
    d = pt.preview({"pattern": pattern, "params": params}, (600.0, t))
    assert d["ok"], [(v["rule"], v["message"]) for v in d["violations"] if v["severity"] == "error"]
    kinds = [s["kind"] for s in d["paths"][0]["segments"]]
    if "infill" not in kinds:
        assert any("Infill entfällt" in n for n in d["notes"])


@pytest.mark.parametrize("name", ["sinus", "zickzack", "schalen", "fugenwand", "waben"])
def test_contact_metrics_do_not_depend_on_print_direction(name):
    """M7: Schicht L + 1 (alternate) ist die Umkehrung von Schicht L. Anzahl und Länge der
    Kontaktzonen sind Eigenschaften der Geometrie und deshalb in beiden Schichten gleich."""
    from pathlib import Path

    preset = pt.load_preset(Path(pt.__file__).parent / "presets" / f"{name}.json")
    m0, m1 = (pt.preview(preset, None, layer)["metrics"] for layer in (0, 1))
    assert m0["path_length_mm"] == pytest.approx(m1["path_length_mm"])
    assert m0["contacts"] == m1["contacts"]
    assert m0["contact_length_mm"] == pytest.approx(m1["contact_length_mm"], abs=0.05)
    assert m0["contacts_per_m"] == pytest.approx(m1["contacts_per_m"], abs=0.01)


@pytest.mark.parametrize(("pattern", "cr"), [("schalen", 120.0), ("doppelwelle", 141.0), ("waben", 147.0)])
def test_corner_radius_l_250_preview_prints_whole_wall(pattern, cr):
    """L 800 × 800, Wand 250 mm (Vorschau/CLI): Pfad über den ganzen Querschnitt, nicht nur die Ecke."""
    outline = {"polygon": [[0, 0], [800, 0], [800, 250], [250, 250], [250, 800], [0, 800]]}
    d = pt.preview({"pattern": pattern, "params": {"corner_radius_mm": cr}, "outline": outline})
    assert d["ok"]
    assert d["metrics"]["shell_coverage"] > 0.85
    assert d["metrics"]["path_length_mm"] > 3000
