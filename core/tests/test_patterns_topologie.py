"""Familie „Topologie“: Öffnungen, mehrere Inseln, Laibungsstege (M3), Naht (M4), Kerben, Schräge.

Geprüft wird mit `patterns.metrics.measure` (M1–M7) über alle Schichten eines Teils. Das
Muster-Orakel `verify_muster/` gibt es auf diesem Zweig noch nicht.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.ops import unary_union

from roboprint import patterns as pt
from roboprint.patterns.families import topologie as topo
from roboprint.patterns.metrics import bead_area

P = pt.params_from_dict({"outfill": "topologie"})
REPO = Path(__file__).resolve().parents[2]


def window(z_sill=800.0, z_top=2000.0, X=1200.0, T=200.0, a=300.0, b=900.0, h=10.0):
    """Wand X × T × z_top mit Fenster [a, b] ab Brüstung z_sill bis Oberkante (Frame P zentriert)."""
    full = box(-X / 2, -T / 2, X / 2, T / 2)
    piers = MultiPolygon([box(-X / 2, -T / 2, -X / 2 + a, T / 2), box(-X / 2 + b, -T / 2, X / 2, T / 2)])
    return {L: full if (L + 0.5) * h < z_sill else piers for L in range(int(round(z_top / h)))}


def edge(n_sill=6, n_top=5, X=1200.0, T=200.0, a=500.0, right=False):
    s = {L: box(0, 0, X, T) for L in range(n_sill)}
    for L in range(n_sill, n_sill + n_top):
        s[L] = box(X - a, 0, X, T) if right else box(0, 0, a, T)
    return s


def bevel(X=1200.0, T=200.0, n_full=6, side="top"):
    s = {L: box(0, 0, X, T) for L in range(n_full)}
    t, L = T - 4.3, n_full
    while t > 1:
        s[L] = box(0, 0, X, t) if side == "top" else box(0, T - t, X, T)
        t, L = t - 10.0, L + 1
    return s


def _ok(sections, params=P):
    paths = pt.plan_pattern(sections, params)
    rep = pt.measure(paths, sections, params)
    assert rep.ok, [v.to_dict() for v in rep.errors][:5]
    return paths, rep


def _mode(paths):
    return {lp.meta["topology"]["mode"] for lp in paths}


# --------------------------------------------------------------------------- Fenster


def test_window_module_all_layers_ok_and_one_strand_per_island():
    sec = window()  # 1200 × 200 × 2000, Fenster 600 breit ab 800 mm: 80 + 120 Schichten
    paths, rep = _ok(sec)
    assert _mode(paths) == {"oeffnung"}
    by = {}
    for lp in paths:
        by.setdefault(lp.layer, []).append(lp)
    assert all(len(by[L]) == 1 for L in range(80)) and all(len(by[L]) == 2 for L in range(80, 200))
    # Schichtwechsel: senkrecht, auch an der Brüstungsoberkante (Ende Brüstung = Start Pfeiler)
    assert {c["status"] for c in rep.layer_changes} == {"vertical"}
    # Warnungen nur M4 (Pfeilerende an der Laibungsecke) und M6 (Wende r = w/2), keine Fehler
    assert {v.rule for v in rep.violations} <= {"M4", "M6"}
    assert all(v.value >= P.w / 2 - 0.5 for v in rep.violations if v.rule == "M6")


def test_window_reveal_webs_below_sill_carry_the_piers():
    sec = window(z_sill=60.0, z_top=120.0)
    paths = pt.plan_pattern(sec, P)
    sill = next(lp for lp in paths if lp.layer == 5)
    pier = [lp for lp in paths if lp.layer == 6]
    webs = [s for s in sill.segments if s.kind == "web"]
    # Querstege an beiden künftigen Laibungen (x = ±300) quer durch die Wand
    for x in (-300.0, 300.0):
        near = [s for s in webs if np.min(np.abs(s.points[:, 0] - x)) < 50]
        assert near, x
        ys = np.concatenate([s.points[:, 1] for s in near])
        assert ys.max() - ys.min() > 90.0
    # dieselben Schenkel sind in den Pfeilern Außenschale (Laibung)
    reveal = [s for lp in pier for s in lp.segments if s.kind == "outer" and np.ptp(s.points[:, 1]) > 150]
    assert reveal
    # M3 ausdrücklich: Pfeilerraupen liegen auf den Brüstungsraupen ⊕ δ
    up = unary_union([bead_area(lp, P.w) for lp in pier])
    lo = bead_area(sill, P.w).buffer(P.delta_mm)
    assert up.difference(lo).area <= 1.0


def test_standard_shells_overhang_at_reveal():
    sec = window(z_sill=60.0, z_top=120.0)
    rep = pt.measure(pt.plan_pattern(sec, pt.PatternParams()), sec, pt.PatternParams())
    assert "M3" in rep.rules_violated()


@pytest.mark.parametrize("thickness", [300.0, 365.0])
def test_window_thick_walls(thickness):
    paths, _ = _ok(window(z_sill=60.0, z_top=120.0, T=thickness))
    assert _mode(paths) == {"oeffnung"}


def test_window_asymmetric_and_sill_middle_param():
    sec = window(z_sill=60.0, z_top=120.0, a=200.0, b=700.0)
    paths, _ = _ok(sec)
    p2 = pt.params_from_dict({"outfill": "topologie", "sill_middle_mm": 70.0})
    paths2, _ = _ok(sec, p2)
    mid = [s for s in paths2[0].segments if s.label == "Brüstung Mitte"][0]
    assert np.median(mid.points[:, 1]) == pytest.approx(-100.0 + 70.0, abs=0.01)


@pytest.mark.parametrize("right", [False, True])
def test_edge_opening(right):
    paths, rep = _ok(edge(right=right))
    assert _mode(paths) == {"oeffnung"}
    assert {lp.meta["topology"]["case"] for lp in paths} == {"randoeffnung"}
    # Brüstung: Start im Pfeiler innen, Ende im Feld innen (Naht nicht an einer Fläche)
    sill = paths[0]
    for e in (sill.start, sill.end):
        assert pt.face_clearance(e[None, :], box(0, 0, 1200, 200), (0, 0, 1200, 200), P.w)[0] > 0


def test_too_narrow_pier_falls_back_to_general():
    sec = window(z_sill=40.0, z_top=80.0, a=120.0, b=1080.0)
    paths = pt.plan_pattern(sec, P)
    assert _mode(paths) == {"allgemein"}
    assert "zu schmal" in paths[0].meta["topology"]["note"]


# --------------------------------------------------------------------------- Abschrägung


@pytest.mark.parametrize("side", ["top", "bottom"])
def test_bevel_layers_ok_and_standard_fails(side):
    sec = bevel(side=side)
    paths, rep = _ok(sec)
    assert _mode(paths) == {"abschraegung"}
    std = pt.measure(pt.plan_pattern(sec, pt.PatternParams()), sec, pt.PatternParams())
    assert {"M3"} <= std.rules_violated()
    # eine Insel, ein Strang je Schicht, bis die Wand dünner als eine Raupe ist
    assert len({lp.layer for lp in paths}) == len(paths)
    thin = [L for L, g in sec.items() if g.bounds[3] - g.bounds[1] < P.w - 1]
    assert not {lp.layer for lp in paths} & set(thin)


def test_real_s2_module_with_bevel():
    """Oberstes Modul der Wand „house right front“ (S2): 900 × 200 mm, 600 mm hoch, die letzten
    ~200 mm mit 45°-Schräge (Dicke nimmt je Schicht um 10 mm ab). Das IFC enthält keine
    Öffnungen; der Querschnittswechsel in S2 ist diese Schräge."""
    from roboprint.decompose import _cut_part
    from roboprint.ifc import read_walls
    from roboprint.slicer import _section_polygons

    wall = read_walls(REPO / "examples/Building-Architecture.ifc")[0]
    mesh, _ = _cut_part(wall, np.array([0.0, 0, 3026.0]), np.array([900.0, 0, wall.height_mm]))
    n = int(round(mesh.bounds[1, 2] / 10.0))
    sec = {L: unary_union(_section_polygons(mesh, (L + 0.5) * 10.0)) for L in range(n)}
    sec = {L: g for L, g in sec.items() if not g.is_empty}
    assert len({round(g.bounds[3] - g.bounds[1], 1) for g in sec.values()}) > 10  # Schräge
    paths, rep = _ok(sec)
    assert _mode(paths) == {"abschraegung"}
    std = pt.measure(pt.plan_pattern(sec, pt.PatternParams()), sec, pt.PatternParams())
    assert not std.ok and "M3" in std.rules_violated()


# --------------------------------------------------------------------------- allgemein


SHAPES = {
    "L": Polygon([(0, 0), (600, 0), (600, 200), (200, 200), (200, 600), (0, 600)]),
    "U": Polygon([(0, 0), (900, 0), (900, 500), (700, 500), (700, 200), (200, 200), (200, 500), (0, 500)]),
    "T": Polygon([(0, 0), (900, 0), (900, 200), (550, 200), (550, 600), (350, 600), (350, 200), (0, 200)]),
    "kerbe_v": Polygon([(0, 0), (280, 0), (300, 40), (320, 0), (600, 0), (600, 200), (0, 200)]),
    "kerbe_rechteck": Polygon(
        [(0, 0), (270, 0), (270, 60), (330, 60), (330, 0), (600, 0), (600, 200), (0, 200)]
    ),
    "tuer": MultiPolygon([box(0, 0, 300, 200), box(900, 0, 1200, 200)]),
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_general_shapes_ok(name):
    sec = {L: SHAPES[name] for L in range(3)}
    paths, rep = _ok(sec)
    assert _mode(paths) == {"allgemein"}
    assert len(paths) == 3 * len(pt.polygons(SHAPES[name]))
    assert {c["status"] for c in rep.layer_changes} == {"vertical"}
    assert all(v.severity == "warn" and v.rule == "M6" for v in rep.violations)
    radius = [v for v in rep.violations if "Radius" in v.message or "radius" in v.message]
    assert all(v.value >= 0.95 * P.w / 2 for v in radius)


def test_rectangular_notch_rounded_corners():
    # Seit dem Kern-Fix 074763c verkleinert auch offset_region den Radius schrittweise; das
    # Grundmuster ist hier gültig. Topologie bleibt gültig und hält Radius ≥ w/2 überall.
    sec = {L: SHAPES["kerbe_rechteck"] for L in range(2)}
    _, rep = _ok(sec)
    assert all(m.min_radius_mm >= 0.95 * P.w / 2 for m in rep.paths)


def test_deep_notch_reduces_shells():
    g = Polygon([(0, 0), (270, 0), (270, 100), (330, 100), (330, 0), (600, 0), (600, 200), (0, 200)])
    paths, _ = _ok({L: g for L in range(2)})
    assert paths[0].meta["topology"]["shells_used"] == 1  # Hals 100 mm < 4·w


def test_rectangle_equals_core_seam():
    sec = {L: box(-300, -100, 300, 100) for L in range(2)}
    paths, rep = _ok(sec)
    assert not rep.violations
    core = pt.plan_pattern(sec, pt.PatternParams())
    assert np.allclose(paths[0].start, core[0].start, atol=2.0)
    assert paths[0].meta["topology"]["seam_candidate"] == 0


def test_seam_check_off_uses_first_candidate():
    sec = {L: SHAPES["U"] for L in range(2)}
    p = pt.params_from_dict({"outfill": "topologie", "seam_check": False})
    paths = pt.plan_pattern(sec, p)
    assert paths[0].meta["topology"]["seam_candidate"] == 0


def test_lanes_keep_rounding_where_core_falls_back():
    lanes = topo.island_lanes(SHAPES["kerbe_rechteck"], pt.PatternParams(), 2)
    from roboprint.patterns.geometry import curvature_radius

    for ln in lanes:
        r = curvature_radius(pt.resample_curve(ln.ring, 20.0, 0.5, closed=True), closed=True)
        assert r.min() >= 0.95 * 15.0


# --------------------------------------------------------------------------- Vorschau, Preset


def test_part_preview_and_svg_two_layers():
    sec = window(z_sill=60.0, z_top=120.0)
    d = topo.part_preview(sec, P, 5, name="Brüstung → Pfeiler")
    json.dumps(d)
    assert d["ok"] and len(d["paths"]) == 1 and len(d["next_layer"]["paths"]) == 2
    svg = pt.preview_svg(data=d)
    assert svg.startswith("<svg") and "polyline" in svg
    root = __import__("xml.etree.ElementTree", fromlist=["x"]).fromstring(svg)
    assert root.tag.endswith("svg")


def test_preset_and_catalog():
    preset = pt.load_preset(Path(pt.__file__).parent / "presets" / "topologie.json")
    d = pt.preview(preset)
    assert d["ok"] and d["paths"]
    cat = {c["name"]: c for c in pt.catalog()}
    assert cat["topologie"]["role"] == "full" and not cat["topologie"]["layer_invariant"]
    assert {q["name"] for q in cat["topologie"]["params"]} == {"sill_middle_mm", "seam_check"}


def test_meta_is_json_and_names_mode():
    for sec in (window(z_sill=40.0, z_top=60.0), bevel(), {0: SHAPES["L"], 1: SHAPES["L"]}):
        for lp in pt.plan_pattern(sec, P):
            json.dumps(lp.meta)
            assert lp.meta["topology"]["mode"] in {"allgemein", "abschraegung", "oeffnung"}


def test_rect_detection():
    assert topo.as_rect(box(0, 0, 10, 5)) == topo.Rect(0, 0, 10, 5)
    assert topo.as_rect(SHAPES["L"]) is None
    assert topo.as_rect(box(0, 0, 100, 100).difference(box(40, 40, 60, 60))) is None
    # Raupen verlaufen nicht über die Öffnung (M5): keine Raupe zwischen den Pfeilern oberhalb
    sec = window(z_sill=40.0, z_top=60.0)
    for lp in pt.plan_pattern(sec, P):
        if lp.layer >= 4:
            hit = shapely.intersection(LineString(lp.polyline()), box(-290, -100, 290, 100))
            assert hit.is_empty


# --------------------------------------------------------------------------- Gegenprüfung


def _own_overhang(paths, sections, params=P):
    """Unabhängige M3-Nachrechnung mit shapely: größte Fläche (mm²) der Raupen von L + 1, die
    nicht auf den Raupen von L ⊕ δ liegt (Raupe = Mittellinie ⊕ w/2, runde Enden)."""
    w = params.w
    by: dict[int, list] = {}
    for lp in paths:
        by.setdefault(lp.layer, []).append(lp)

    def beads(lps):
        return unary_union([LineString(lp.polyline()).buffer(w / 2.0, quad_segs=16) for lp in lps])

    worst = 0.0
    for L in sorted(sections):
        if L + 1 in by and L in by:
            worst = max(worst, beads(by[L + 1]).difference(beads(by[L]).buffer(params.delta_mm)).area)
    return worst


def _no_crossing(lp):
    """Mittellinie ohne echte Kreuzung oder Überdeckung (nicht benachbarte Stücke)."""
    pl = lp.polyline()
    segs = [LineString(pl[i : i + 2]) for i in range(len(pl) - 1)]
    tree = shapely.STRtree(segs)
    for i, s in enumerate(segs):
        if s.length < 1e-9:
            continue
        for j in tree.query(s):
            if j > i + 1 and segs[j].length > 1e-9 and (s.crosses(segs[j]) or s.overlaps(segs[j])):
                return False
    return True


def two_windows(X=2400.0, T=200.0, wins=((300.0, 900.0), (1500.0, 2100.0)), n_sill=6, n_top=6):
    full = box(0, 0, X, T)
    piers = full
    for a, b in wins:
        piers = piers.difference(box(a, -1, b, T + 1))
    return {L: full if L < n_sill else piers for L in range(n_sill + n_top)}


OPENINGS = {
    "fenster": lambda: window(z_sill=60.0, z_top=120.0),
    "fenster_kante_152": lambda: window(z_sill=60.0, z_top=120.0, a=152.0, b=1048.0),
    "fenster_schmal_62": lambda: window(z_sill=60.0, z_top=120.0, a=569.0, b=631.0),
    "bruestung_eine_schicht": lambda: window(z_sill=10.0, z_top=60.0),
    "fenster_365": lambda: window(z_sill=60.0, z_top=120.0, T=365.0),
    "rand_rechts_160": lambda: edge(a=160.0, right=True),
    "rand_1000": lambda: edge(a=1000.0),
}


@pytest.mark.parametrize("name", sorted(OPENINGS))
def test_openings_own_m3_islands_no_crossing(name):
    sec = OPENINGS[name]()
    paths, _ = _ok(sec)
    assert _mode(paths) == {"oeffnung"}
    assert _own_overhang(paths, sec) <= 1.0  # Laibungsstege unter jeder neuen Kante
    count: dict[int, int] = {}
    for lp in paths:
        count[lp.layer] = count.get(lp.layer, 0) + 1
    assert all(count[L] == len(pt.polygons(g)) for L, g in sec.items())  # ein Strang je Insel
    assert all(_no_crossing(lp) for lp in paths)


def test_door_to_floor_is_prismatic_and_ok():
    g = box(0, 0, 1200, 200).difference(box(300, -1, 900, 201))
    paths, _ = _ok({L: g for L in range(4)})
    assert _mode(paths) == {"allgemein"} and len(paths) == 8


def test_two_windows_middle_pier_is_reported_not_hidden():
    """Mittelpfeiler: nicht unterstützt. Das Muster muss das sagen, und die Prüfung muss den
    Überhang an den Laibungen melden (nicht still „ok“)."""
    sec = two_windows()
    paths = pt.plan_pattern(sec, P)
    assert _mode(paths) == {"allgemein"}
    assert all("nicht unterstützt" in lp.meta["topology"]["note"] for lp in paths)
    rep = pt.measure(paths, sec, P)
    assert "M3" in rep.rules_violated() and _own_overhang(paths, sec) > 1000.0
    # derselbe Inselzwischenspeicher trägt den Hinweis nicht in ein prismatisches Teil
    g = sec[max(sec)]
    plain = pt.plan_pattern({0: g, 1: g}, P)
    assert all("note" not in lp.meta["topology"] for lp in plain)


@pytest.mark.parametrize("T", [136.0, 140.0, 149.0])
@pytest.mark.parametrize("kind", ["fenster", "rand"])
def test_walls_thinner_than_pier_minimum_do_not_crash(T, kind):
    sec = window(z_sill=60.0, z_top=120.0, T=T) if kind == "fenster" else edge(T=T)
    paths = pt.plan_pattern(sec, P)
    assert _mode(paths) == {"allgemein"} and "zu dünn" in paths[0].meta["topology"]["note"]


def test_pier_minimum_thickness_is_exact():
    from roboprint.patterns.families._topologie_bahnen import pillar_min_thickness

    assert pillar_min_thickness(30.0, 30.0) == pytest.approx(150.0)
    paths, _ = _ok(window(z_sill=60.0, z_top=120.0, T=150.0))
    assert _mode(paths) == {"oeffnung"}


@pytest.mark.parametrize("ym", [10.0, 45.0, 155.0, 160.0, 300.0])
def test_sill_middle_is_clamped(ym):
    p = pt.params_from_dict({"outfill": "topologie", "sill_middle_mm": ym})
    sec = window(z_sill=60.0, z_top=120.0)
    paths, _ = _ok(sec, p)
    used = paths[0].meta["topology"]["sill_middle_mm"]
    assert 45.0 - 1e-9 <= used <= 155.0 + 1e-9
    assert ("note" in paths[0].meta["topology"]) == (not 45.0 <= ym <= 155.0)


def test_bevel_wide_bead_cap_does_not_hang_over_turn():
    """w = 40 mm: Der Stirnschenkel der U-Form ragte 10 mm über die Wende der Schicht darunter
    (Grenze 9,1 mm), 4,4 mm² Überhang. Jetzt begrenzt (`turn_cap_reach`)."""
    from roboprint.patterns.families._topologie_bahnen import turn_cap_reach

    assert turn_cap_reach(30.0, 2.0) == pytest.approx(7.8, abs=0.15)
    assert turn_cap_reach(40.0, 2.0) == pytest.approx(9.0, abs=0.15)
    p = pt.params_from_dict({"outfill": "topologie", "bead_width_mm": 40.0})
    sec = bevel(X=888.0, T=282.0, n_full=2)
    paths, _ = _ok(sec, p)
    assert _own_overhang(paths, sec, p) <= 1.0


def test_corner_radius_below_half_bead_is_raised():
    p = pt.params_from_dict({"outfill": "topologie", "corner_radius_mm": 12.0})
    for sec in (edge(), bevel(X=900.0, T=166.0, n_full=2)):
        _ok(sec, p)


def test_tiny_pier_islands_do_not_crash():
    # Inseln 96 × 104 mm: die innere Spur ist kürzer als 2·w (Kern `clear_end` brach ab)
    paths = pt.plan_pattern(edge(n_sill=3, n_top=3, X=545.0, T=104.0, a=96.0), P)
    assert paths and _mode(paths) == {"allgemein"}
