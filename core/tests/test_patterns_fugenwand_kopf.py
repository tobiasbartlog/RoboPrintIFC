"""Fugenwand an Abschrägungen (Kopfmodule der S2-Wände, Szenario S6): Einteilung aus dem ganzen Teil,
Raupen fallen nach oben nur weg, Übergang auf die U-Formen der Abschrägungslösung ohne Überhang.

Geprüft mit `patterns.metrics.measure` (M1–M7) und einer eigenen shapely-Nachrechnung von M3
(Raupen von L + 1 ⊆ Raupen von L ⊕ δ; bei gleichem Querschnitt auch umgekehrt, wie das Orakel).
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from roboprint import patterns as pt
from roboprint.patterns.families import _fugenwand_kopf as kopf
from roboprint.patterns.families import fugenwand as fw
from roboprint.patterns.plan import island_context, part_bounds
from roboprint.patterns.preview import load_preset, params_for, preset_params

ROOT = Path(__file__).resolve().parents[2]
#: Szenario S6: Preset Rautenkette, Ziel-Feldlänge 225 mm (3 × 200 mm bei 600-mm-Modulen)
S6 = preset_params(load_preset(ROOT / "docs" / "muster" / "presets" / "fugenwand_raute.json")).with_extra(
    field_length_mm=225.0
)
DELTA = 2.0


def bevel(X=600.0, T=200.0, slope_deg=45.0, n_full=5, side="top", first=0.7):
    """Teil X × T, n_full volle Schichten, dann eine Schräge: Dicke je Schicht um h/tan(Neigung)
    kleiner (45°: 10 mm, 60°: 5,8 mm), bis unter 1 mm (wie die S2-Köpfe: 190,7 … 0,7 mm)."""
    dt = 10.0 / math.tan(math.radians(slope_deg))
    s = {L: box(-X / 2, -T / 2, X / 2, T / 2) for L in range(n_full)}
    t, L = T - dt + first, n_full
    while t > 0.5:
        s[L] = (
            box(-X / 2, -T / 2, X / 2, -T / 2 + t) if side == "top" else box(-X / 2, T / 2 - t, X / 2, T / 2)
        )
        t, L = t - dt, L + 1
    return s


def _beads(paths, L, w):
    g = [LineString(lp.polyline()).buffer(w / 2.0) for lp in paths if lp.layer == L]
    return shapely.union_all(g) if g else shapely.Polygon()


def own_m3(paths, sections, w):
    """Eigene Nachrechnung (unabhängig von metrics): größter Überhang und größte fehlende Raupe bei
    gleichem Querschnitt (mm²)."""
    over = miss = 0.0
    for L in sorted(sections):
        if L + 1 not in sections:
            continue
        a, b = _beads(paths, L, w), _beads(paths, L + 1, w)
        over = max(over, b.difference(a.buffer(DELTA, quad_segs=16)).area)
        if not b.is_empty and sections[L].symmetric_difference(sections[L + 1]).area <= 1.0:
            miss = max(miss, a.difference(b.buffer(DELTA, quad_segs=16)).area)
    return over, miss


def assert_kopf_valid(sections, p, paths):
    rep = pt.measure(paths, sections, p)
    assert rep.ok, [v.to_dict() for v in rep.errors][:5]
    over, miss = own_m3(paths, sections, p.w)
    assert over <= 1.0 and miss <= 1.0, (over, miss)
    layers = [lp.layer for lp in paths]
    assert len(layers) == len(set(layers))  # M1: ein Strang je Schicht
    assert {c["status"] for c in rep.layer_changes} == {"vertical"}  # M4 senkrecht
    for a, b in zip(paths[:-1], paths[1:], strict=True):
        assert np.linalg.norm(a.end - b.start) <= 0.5 and not b.restart
    for m in rep.paths:
        assert m.min_radius_mm >= 0.95 * p.w / 2  # M6 hart
        assert m.min_clearance_mm >= (1 - p.eps) * p.w - 1e-6  # M2
    # leer bleiben nur Schichten, in die keine Raupe passt (Dicke < w − 1 mm, M5)
    thin = {L for L, g in sections.items() if g.bounds[3] - g.bounds[1] < p.w - 1.0}
    assert set(sections) - set(layers) == thin
    assert {v.rule for v in rep.violations if v.rule == "M1"} <= {"M1"}
    assert all(v.severity == "warn" for v in rep.violations if v.rule == "M1")  # Kappe über Raupe
    return rep


# --------------------------------------------------------------------------- echte Kopfmodule (S6)


def _s6_head(wall_idx: int, z0: float, x0: float = 0.0):
    """Kopfmodul aus der Zerlegung von examples/Building-Architecture.ifc (Frame P): 600 mm lang, ab
    z0 bis zur Wandoberkante. Wand 0 „house right front“ (r9 ab 3330 mm), Wand 1 „house right back“
    (r5 ab 1900 mm)."""
    from roboprint.decompose import _cut_part
    from roboprint.ifc import read_walls
    from roboprint.slicer import _section_polygons

    wall = read_walls(ROOT / "examples" / "Building-Architecture.ifc")[wall_idx]
    mesh, _ = _cut_part(wall, np.array([x0, 0.0, z0]), np.array([x0 + 600.0, 0.0, wall.height_mm]))
    n = int(round(mesh.bounds[1, 2] / 10.0))
    return {L: unary_union(_section_polygons(mesh, (L + 0.5) * 10.0)) for L in range(n)}


@pytest.fixture(scope="module")
def s6_heads():
    return {"front_r9": _s6_head(0, 3330.0), "back_r5": _s6_head(1, 1900.0)}


@pytest.mark.parametrize("name, n_layers, n_full", [("front_r9", 30, 10), ("back_r5", 33, 13)])
def test_s6_head_modules_rule_conform(s6_heads, name, n_layers, n_full):
    sec = s6_heads[name]
    assert len(sec) == n_layers
    th = [g.bounds[3] - g.bounds[1] for g in sec.values()]
    assert th[n_full - 1] == pytest.approx(200.0, abs=0.1) and th[n_full] == pytest.approx(190.7, abs=0.1)
    paths = pt.plan_pattern(sec, S6)
    assert_kopf_valid(sec, S6, paths)
    full = [lp for lp in paths if lp.meta.get("zone") == "voll"]
    assert [lp.layer for lp in full] == list(range(n_full))
    # Fugenlagen der Schrägseite (Rückseite y+) wie im vollen Modul darunter: −200, 0, 200 mm
    ref = pt.plan_pattern({0: sec[0]}, S6)[0].meta
    assert full[0].meta["joints_x"] == pytest.approx(ref["joints_back_x"])
    assert full[0].meta["side"] == "top"
    rep = pt.measure(full[:1], {0: sec[0]}, S6)
    joints = [c for c in rep.paths[0].contacts if c.kind == "joint"]
    assert sorted(round(c.at[0]) for c in joints) == [-200, 0, 200]
    assert all(c.at[1] > 0 for c in joints)  # Fugen an der Schrägseite (y+), Gegenseite ohne Fuge
    # Die drei obersten Schichten (20,7 / 10,7 / 0,7 mm) bleiben leer, mit Hinweis
    assert {lp.layer for lp in paths} == set(range(n_layers - 3))
    notes = pt.layer_notes(paths, sec)
    assert any(
        "dünner als eine Raupe" in t and f"Schichten {n_layers - 3}–{n_layers - 1}" in t for t in notes
    )


def test_s6_head_transition_full_to_bevel_is_subset(s6_heads):
    """Erste Schrägschicht: nur Raupen, die schon in der letzten Vollschicht liegen (die Schrägseite
    mit Fugen und Rauten fällt weg, die U-Formen der Gegenseite bleiben)."""
    sec = s6_heads["front_r9"]
    paths = pt.plan_pattern(sec, S6)
    a, b = _beads(paths, 9, S6.w), _beads(paths, 10, S6.w)
    assert b.difference(a.buffer(0.5)).area < 1.0  # bis auf die Abtastung (Sehnenfehler ≤ 0,5 mm)
    lp10 = next(lp for lp in paths if lp.layer == 10)
    assert lp10.meta["zone"] == "schraege" and {s.kind for s in lp10.segments} <= {"outer", "inner"}
    assert "Abschrägung" in lp10.meta["note"]


def test_s6_head_planning_is_fast_and_cached(s6_heads):
    import time

    sec = s6_heads["back_r5"]
    t0 = time.perf_counter()
    pt.plan_pattern(sec, S6)
    t1 = time.perf_counter()
    pt.plan_pattern(sec, S6)
    t2 = time.perf_counter()
    assert t1 - t0 < 10.0 and t2 - t1 < t1 - t0 + 0.5


# --------------------------------------------------------------------------- synthetische Schrägen


@pytest.mark.parametrize("slope", [45.0, 60.0])
@pytest.mark.parametrize("T", [200.0, 300.0])
@pytest.mark.parametrize("side", ["top", "bottom"])
def test_synthetic_bevels(slope, T, side):
    sec = bevel(T=T, slope_deg=slope, side=side)
    paths = pt.plan_pattern(sec, S6)
    assert_kopf_valid(sec, S6, paths)
    assert {lp.meta.get("variant") for lp in paths} == {"kopf"}
    assert "pattern_fallback" not in paths[0].meta
    full = paths[0].meta
    assert full["side"] == side and full["zone"] == "voll"
    # Fugen an der Schrägseite in den Lagen des Vollquerschnitts
    ref = pt.plan_pattern({0: sec[0]}, S6)[0].meta
    key = "joints_back_x" if side == "top" else "joints_front_x"
    assert full["joints_x"] == pytest.approx(ref[key])


@pytest.mark.parametrize("variant", [{}, {"belt": True}, {"belt": True, "back_offset": "gespiegelt"}])
@pytest.mark.parametrize("X", [300.0, 900.0, 1200.0])
def test_bevel_variants_and_lengths(variant, X):
    p = params_for("fugenwand", **variant)
    sec = bevel(X=X, T=250.0, slope_deg=45.0, n_full=4)
    assert_kopf_valid(sec, p, pt.plan_pattern(sec, p))


@pytest.mark.parametrize("n_full", [1, 2, 3, 4])
def test_bevel_parity_of_last_full_layer(n_full):
    """Der Übergang Vollschicht → Schräge teilt das Strangende von Spur 1; liegt die letzte
    Vollschicht ungerade, wird die Bahn aller Schichten umgedreht (`flipped`)."""
    sec = bevel(n_full=n_full)
    paths = pt.plan_pattern(sec, S6)
    assert_kopf_valid(sec, S6, paths)
    assert paths[0].meta["flipped"] == ((n_full - 1) % 2 == 1)


def test_bevel_with_repeated_sections_keeps_layers_complete():
    """Stufe in der Schräge (zwei bis drei Schichten mit gleichem Querschnitt): Die höhere bleibt
    vollständig (Orakel: bei gleichem Querschnitt auch L in L + 1 ⊕ δ), Wechsel bleiben senkrecht."""
    src = bevel()
    sec, k = {}, 0
    for L in sorted(src):
        reps = 3 if L in (8, 12, 20) else 1
        for _ in range(reps):
            sec[k] = src[L]
            k += 1
    assert_kopf_valid(sec, S6, pt.plan_pattern(sec, S6))


def test_thin_wall_bevel_without_joints():
    """150 mm: Rauten passen nicht zwischen Schrägseite und Spur 1 (Fugen an der Schrägseite erst ab
    ≈ 175 mm bei F = 200 mm); die Schrägseite läuft ohne Fuge, der Rest bleibt (Hinweis `adjusted`)."""
    sec = bevel(T=150.0)
    paths = pt.plan_pattern(sec, S6)
    assert_kopf_valid(sec, S6, paths)
    assert "Schrägseite ohne Fuge" in paths[0].meta["adjusted"]
    assert paths[0].meta["joints_x"] == []


@pytest.mark.parametrize("T", [100.0, 120.0])
def test_too_thin_wall_uses_topologie(T):
    """Unter ≈ 140 mm passen Wende und Eckbogen am Stirnende nicht übereinander: Abschrägungslösung
    von `topologie` mit Hinweis."""
    sec = bevel(T=T)
    paths = pt.plan_pattern(sec, S6)
    assert "topologie" in paths[0].meta["pattern_fallback"]
    assert pt.measure(paths, sec, S6).ok


def test_layer_order_same_keeps_m3():
    p = replace(S6, layer_order="same")
    sec = bevel()
    paths = pt.plan_pattern(sec, p)
    over, _ = own_m3(paths, sec, p.w)
    assert over <= 1.0  # M4 ist mit `same` ohnehin diagonal (Kernsemantik)


# --------------------------------------------------------------------------- Beleg: keine Fuge auf G


def test_joint_notch_on_fixed_side_cannot_close():
    """Beleg für „Gegenseite ohne Fuge“: Über einer Fuge der Rautenkette (Kerbe von außen bis zum
    Hakenkontakt) hinge ein durchgehender Lauf an der Außenfläche, wie ihn die obersten Schichten
    (Dicke < 2·w) brauchen. Gemessen: Überhang je Fuge weit über der Toleranz."""
    sec = {0: box(-300, -100, 300, 100)}
    lp = pt.plan_pattern(sec, S6)[0]
    run = LineString([(-255.0, -85.0), (255.0, -85.0)]).buffer(15.0)
    over = run.difference(LineString(lp.polyline()).buffer(15.0).buffer(DELTA, quad_segs=16))
    n_front_joints = len(lp.meta["joints_front_x"])
    assert n_front_joints == 2
    assert over.area > 100.0 * n_front_joints  # je Fuge > 100 mm² (Toleranz 1 mm²)


# --------------------------------------------------------------------------- Rechteck unverändert


@pytest.mark.parametrize(
    "dims, kw",
    [
        ((600.0, 200.0), {"field_length_mm": 225.0}),
        ((600.0, 300.0), {}),
        ((1000.0, 300.0), {"belt": True}),
        ((1200.0, 365.0), {"belt": True, "back_offset": "gespiegelt"}),
        ((500.0, 110.0), {}),
    ],
)
def test_rectangle_sections_unchanged(dims, kw):
    """Volle Fugenwand-Module ändern sich nicht: Jede Schicht eines Prismas ist genau der Inselpfad
    von `build_plan` (prismatische Fugenwand wie vor dem Kopfmodul), Schicht 1 die Umkehrung."""
    X, T = dims
    g = box(-X / 2, -T / 2, X / 2, T / 2)
    sec = {L: g for L in range(4)}
    p = params_for("fugenwand", **kw)
    paths = pt.plan_pattern(sec, p)
    ctx = replace(island_context(0, 0, g, sec, part_bounds(sec), p), spec=pt.get("fugenwand").params)
    ref = fw.build_plan(ctx, {s.name: ctx.param(s.name) for s in fw.PARAMS})
    for lp in paths:
        segs = lp.segments if lp.layer % 2 == 0 else [s.reversed() for s in reversed(lp.segments)]
        assert len(segs) == len(ref.segments)
        for a, b in zip(segs, ref.segments, strict=True):
            assert a.kind == b.kind and a.shell == b.shell and np.array_equal(a.points, b.points)
        assert lp.meta == ref.meta and "zone" not in lp.meta
    assert kopf.detect(sec) is None
