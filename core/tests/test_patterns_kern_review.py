"""Gegenprüfung des Kerns `roboprint.patterns` (Aufgabe K): Randfälle, die die ersten Tests nicht
abgedeckt haben, und Regressionen der dabei gefundenen Fehler.

- Loop.sub ließ den Eckpunkt am Ringanfang aus (scharfe Ecke wurde zur Diagonale, M2/M5).
- Schmale Pfeiler: innere Schale fiel auf scharfe Ecken zurück statt auf einen kleineren Radius.
- Ab drei Schalen lagen zwei S-Kurven als verschobene Kopien nebeneinander (Abstand w/2, M2).
- Kontaktindizes −1 wurden beim Anhängen bzw. Umkehren falsch umgerechnet.
- M7: deklarierter, aber nicht realisierter Kontakt blieb unbemerkt.
- Abdeckung des Schalenbereichs (Maß wie G3) als Kennzahl.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import LineString, Polygon, box

from roboprint import patterns as pt
from roboprint.patterns import registry

W = 30.0
P = pt.PatternParams()
SEC = box(-300, -200, 300, 200)
L_SEC = Polygon([(0, 0), (600, 0), (600, 200), (200, 200), (200, 500), (0, 500)])


def _open(points, kind="infill"):
    return pt.LayerPath(0, 0, [pt.Segment(kind, 2, pt.densify(np.asarray(points, float), 20.0))])


def _errors(v, rule=None):
    return [x for x in v if x.severity == "error" and (rule is None or x.rule == rule)]


# --------------------------------------------------------------------------- Geometrie


def test_loop_sub_keeps_ring_start_vertex():
    ring = np.array([[585.0, 15], [585, 185], [15, 185], [15, 15], [585, 15]])
    lp = pt.Loop(ring)
    s = lp.project(np.array([15.0, 15.0]))
    sub = lp.sub(s, s - 52.0)
    # über den Ringanfang (585, 15) hinweg: der Eckpunkt muss enthalten sein
    assert any(np.allclose(q, [585.0, 15.0]) for q in sub)
    assert np.isclose(pt.arc_length(sub)[-1], lp.length - 52.0)


def test_sharp_corners_shell_chain_is_valid_and_covers_like_slicer():
    sec = box(0, 0, 600, 200)
    p = pt.PatternParams(corner_radius_mm=0.0)
    paths = pt.plan_pattern({0: sec, 1: sec}, p)
    rep = pt.measure(paths, {0: sec, 1: sec}, p)
    assert not _errors(rep.violations, "M2") and not _errors(rep.violations, "M5")
    assert rep.paths[0].shell_coverage > 0.98


def test_narrow_pillar_rounds_inner_shell_instead_of_sharp_corner():
    sec = box(0, 0, 150, 200)  # innere Schale nur 60 mm breit: r = w passt nicht
    paths = pt.plan_pattern({0: sec, 1: sec}, P)
    rep = pt.measure(paths, {0: sec, 1: sec}, P)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    assert rep.paths[0].min_radius_mm >= 0.9 * W


@pytest.mark.parametrize(
    "sec",
    [L_SEC, Polygon([(0, 0), (600, 50), (600, 250), (0, 200)]), box(0, 0, 600, 240)],
    ids=["L", "schief", "rechteck"],
)
def test_three_shells_transitions_do_not_overlap(sec):
    p = pt.PatternParams(shells=3)
    paths = pt.plan_pattern({0: sec, 1: sec}, p)
    rep = pt.measure(paths, {0: sec, 1: sec}, p)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    assert rep.paths[0].min_clearance_mm >= (1 - p.eps) * W


def test_bead_area_is_valid_geometry():
    paths = pt.plan_pattern({0: L_SEC}, pt.PatternParams(shells=3))
    assert pt.metrics.bead_area(paths[0], W).is_valid


# --------------------------------------------------------------------------- Schichtfolge


def test_alternate_is_exact_reversal_and_vertical_on_islands():
    two = box(0, 0, 400, 200).union(box(600, 0, 1000, 200))
    sec = {L: two for L in range(4)}
    paths = pt.plan_pattern(sec, P)
    by = {L: [lp for lp in paths if lp.layer == L] for L in range(4)}
    for L in range(3):
        a, b = by[L], by[L + 1]
        assert np.array_equal(a[-1].end, b[0].start)  # Ende L == Anfang L + 1, exakt
        for x, y in zip(a, reversed(b), strict=True):
            assert x.island == y.island
            assert np.array_equal(x.polyline(), y.polyline()[::-1])
    rep = pt.measure(paths, sec, P)
    assert rep.ok and all(c["status"] == "vertical" for c in rep.layer_changes)


# --------------------------------------------------------------------------- M2 / M6 / M3


def test_shallow_crossing_is_m2_error():
    """Kreuzung unter 3°: Mittellinien schneiden sich, Abstände fallen nur langsam."""
    a = math.radians(3.0)
    pts = [(-250, 0), (250, 0), (250, 150), (-250, 150 - 500 * math.tan(a) - 150)]
    _, v = pt.metrics.measure_path(_open(pts), SEC, P)
    assert _errors(v, "M2")


@pytest.mark.parametrize(("gap", "bad"), [(0.84 * W, True), (0.86 * W, False), (W, False)])
def test_near_parallel_pass_threshold(gap, bad):
    """Zwei gerade Bahnen weit auseinander im Pfad, Mittenabstand knapp unter/über (1 − ε)·w.
    Verbunden über einen großen Umweg (Radien ≫ w), damit nur M2 zählt."""
    loop = [(-250, 0), (250, 0)]
    th = np.linspace(-math.pi / 2, math.pi / 2, 60)
    loop += [(250 + 100 * math.cos(t), 100 + 100 * math.sin(t)) for t in th]
    loop += [(-150, 200)]
    th = np.linspace(math.pi / 2, 3 * math.pi / 2, 60)
    r = (200 - gap) / 2
    loop += [(-150 + r * math.cos(t), 200 - r + r * math.sin(t)) for t in th]
    loop += [(200, gap)]
    _, v = pt.metrics.measure_path(_open(loop), SEC, P)
    assert bool(_errors(v, "M2")) == bad


@pytest.mark.parametrize(("radius", "sev"), [(15.0, "warn"), (13.5, "error"), (30.0, None)])
def test_radius_hard_and_target_limits(radius, sev):
    arc = pt.arc_points(np.array([0.0, 0.0]), radius, -math.pi / 2, math.pi / 2, 0.05, 20.0)
    pts = np.vstack([[[-200.0, -radius]], arc, [[radius, 150.0]]])
    _, v = pt.metrics.measure_path(_open(pts), SEC, P)
    m6 = {x.severity for x in v if x.rule == "M6" and "Krümmung" in x.message}
    assert m6 == (set() if sev is None else {sev})


@pytest.mark.parametrize(("shift", "bad"), [(3.0, True), (1.5, False)])
def test_overhang_three_mm_is_m3_error(shift, bad):
    sec = box(0, 0, 600, 200)
    paths = pt.plan_pattern({0: sec}, P)
    l0 = paths[0]
    moved = [pt.Segment(s.kind, s.shell, s.points + [0.0, shift]) for s in l0.reversed(layer=1).segments]
    l1 = pt.LayerPath(1, 0, moved, direction="in_out")
    rep = pt.measure([l0, l1], {0: sec, 1: sec}, P)
    assert ("M3" in rep.rules_violated()) == bad


# --------------------------------------------------------------------------- M7 / Kontakte


def _web_to_shell(gap: float) -> pt.LayerPath:
    """Gerade Schale y = 0 und ein Steg, der nach großem Bogen parallel im Abstand `gap` läuft."""
    shell = pt.Segment("outer", 0, pt.densify(np.array([[-250.0, 0], [250, 0]]), 20))
    th = np.linspace(-math.pi / 2, math.pi / 2, 60)
    turn = np.column_stack([250 + 60 * np.cos(th), 60 + 60 * np.sin(th)])
    back = np.array([[250.0, 120], [0, 120], [0, gap], [-200, gap]])
    web = pt.Segment("web", 2, pt.densify(np.vstack([turn, back[1:]]), 20))
    web.points = pt.fillet_polyline(web.points, 30.0, chord_tol_mm=0.05)[0]
    return pt.LayerPath(0, 0, [shell, web], [pt.Contact("shell", (-100.0, gap / 2), 200.0, (0, 1))])


def test_declared_contact_realized_and_missing():
    _, v = pt.metrics.measure_path(_web_to_shell(W), SEC, P)
    assert not [x for x in v if x.rule in ("M2", "M7")], [x.to_dict() for x in v]
    _, v = pt.metrics.measure_path(_web_to_shell(W + 8.0), SEC, P)  # Spalt 8 mm
    assert [x for x in v if x.rule == "M7" and x.severity == "warn"]


def test_infill_contact_indices_and_reversal_keep_unassigned():
    def build(ctx):
        e = ctx.entry
        seg = pt.Segment("infill", ctx.params.shells, np.array([e, e + [0.0, 0.0001] + [5.0, 0.0]]))
        return pt.IslandPlan([seg], [pt.Contact("shell", tuple(e), 0.0, (-1, 0))])

    pt.register(pt.Pattern("t_review_infill", "infill", "Test", build, family="test"))
    try:
        sec = {0: box(0, 0, 600, 200), 1: box(0, 0, 600, 200)}
        paths = pt.plan_pattern(sec, pt.params_from_dict({"infill": "t_review_infill"}))
        n = len(paths[0].segments)
        assert paths[0].contacts[0].segments == (-1, n - 1)
        assert paths[1].contacts[0].segments == (-1, 0)  # umgekehrte Schicht
    finally:
        registry.unregister("t_review_infill")


# --------------------------------------------------------------------------- Abdeckung


def test_shell_coverage_metric_matches_g3_measure():
    sec = box(0, 0, 600, 200)
    paths = pt.plan_pattern({0: sec}, P)
    m = pt.measure(paths, {0: sec}, P).paths[0]
    reg = sec.difference(sec.buffer(-60, join_style="mitre"))
    ref = LineString(paths[0].polyline()).buffer(15).intersection(reg).area / reg.area
    assert abs(m.shell_coverage - ref) < 2e-3
    # Stand des Grundmusters (Gate-Einwand G3, siehe Paket-Docstring): 94,4 % bei r = w
    assert 0.93 < m.shell_coverage < 0.95
    p = pt.PatternParams(corner_radius_mm=22.5)
    m2 = pt.measure(pt.plan_pattern({0: sec}, p), {0: sec}, p).paths[0]
    assert m2.shell_coverage >= 0.95
