"""Outfill-Familie „Außenwelle“ (O1): M1–M7 mit patterns.metrics, Geometrie gegen die Herleitung.

Geprüft auf den Quadern 600 × 200 / 300 / 365 mm mit zwei Schalen (Amplitude auf den Kontakt mit
Schale 1 gekappt), mit einer Schale ohne Infill (volle Startwerte A = 8 mm, λ = 150 mm) und mit
einer Schale plus Sinus-Infill (Amplitude auf das halbe Kontaktbudget gekappt).
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from roboprint import patterns as pt
from roboprint.patterns.families import aussenwelle
from roboprint.patterns.preview import params_for

PRESETS = Path(pt.__file__).parent / "presets"
DOC_PRESETS = Path(__file__).resolve().parents[2] / "docs" / "muster" / "presets"


def _quader(thickness, length=600.0, n=4):
    g = box(-length / 2, -thickness / 2, length / 2, thickness / 2)
    return {L: g for L in range(n)}


def _plan(sections, infill="none", **kw):
    p = params_for("aussenwelle", **kw)
    if infill != "none":
        p = replace(p, infill=infill)
    paths = pt.plan_pattern(sections, p)
    return p, paths, pt.measure(paths, sections, p)


def _outfill(lp):
    seg = [s for s in lp.segments if s.kind == "outfill"]
    assert len(seg) == 1
    return seg[0]


CASES = [(t, s, shape, 600.0) for t in (200, 300, 365) for s in (2, 1) for shape in aussenwelle.SHAPES]
CASES += [
    (200, s, shape, length) for s in (2, 1) for shape in aussenwelle.SHAPES for length in (1000.0, 1200.0)
]


@pytest.mark.parametrize(("thickness", "shells", "shape", "length"), CASES)
def test_wave_valid_on_quader(thickness, shells, shape, length):
    sec = _quader(thickness, length=length)
    p, paths, rep = _plan(sec, shells=shells, outer_shape=shape)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    assert not rep.violations, [v.to_dict() for v in rep.violations]
    # M1: ein Strang je Schicht, Schale 0 ist das Outfill
    assert [lp.layer for lp in paths] == [0, 1, 2, 3]
    assert paths[0].segments[0].kind == "outfill"
    assert all(np.allclose(a, b) for a, b in paths[0].connectors())
    # M4: alternate → Ende L == Anfang L + 1
    assert all(c["status"] == "vertical" and c["distance_mm"] == 0.0 for c in rep.layer_changes)
    # M2/M6
    assert rep.paths[0].min_clearance_mm >= (1 - p.eps) * p.w
    assert rep.paths[0].min_radius_mm >= p.w - 1e-6


@pytest.mark.parametrize("thickness", [200, 300, 365])
def test_amplitude_limits(thickness):
    """Zwei Schalen: D = ε·w − 0,5 = 4 mm (A = 2); eine Schale: volle 8 mm; mit Infill: A = 1."""
    sec = _quader(thickness, n=1)
    _, paths, _ = _plan(sec, shells=2)
    m = paths[0].meta["outfill"]
    assert m["amplitude_requested_mm"] == 8.0
    assert m["amplitude_mm"] == pytest.approx(2.0)
    assert m["amplitude_limited_by"].startswith("Schale 1")
    _, paths, _ = _plan(sec, shells=1)
    m = paths[0].meta["outfill"]
    assert m["amplitude_mm"] == pytest.approx(8.0) and m["amplitude_limited_by"] is None
    _, paths, rep = _plan(sec, infill="sinus", shells=1)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    assert not rep.violations
    assert paths[0].meta["outfill"]["amplitude_mm"] == pytest.approx(1.0)


@pytest.mark.parametrize("shape", aussenwelle.SHAPES)
def test_wave_stays_in_wall_and_flush(shape):
    """M5 ohne Toleranz: Raupe ⊆ Querschnitt; Außenkante berührt die y-Flächen (bündig), die Welle
    weicht genau um D = 2·A nach innen aus; Stoßflächen bleiben gerade (x = ±(300 − w/2))."""
    sec = _quader(200, n=1)
    p, paths, _ = _plan(sec, shells=1, outer_shape=shape)
    ring = _outfill(paths[0]).points
    region = sec[0]
    assert LineString(ring).buffer(p.w / 2).difference(region.buffer(1e-6)).area < 1.0
    face = (np.abs(ring[:, 0]) < 255 - 1e-6) & (ring[:, 1] < 0)  # lange Seite y_min
    off = ring[face, 1] - (-100 + p.w / 2)
    # Zickzack: die gerundeten Täler an der Fläche liegen um die Pfeilhöhe des Bogens innen
    assert off.min() >= -1e-6 and off.min() == pytest.approx(0.0, abs=0.05 if shape == "sinus" else 1.5)
    # Zickzack: Scheitel R = 60 mm kappt die Spitze um R·(1/cos α − 1) ≈ 1,2 mm (α = atan(2D/λ))
    assert off.max() <= 16.0 + 0.05 and off.max() == pytest.approx(16.0, abs=0.6 if shape == "sinus" else 1.5)
    side = ring[np.abs(ring[:, 1]) < 100 - p.w / 2 - p.w - 1e-6]  # Stoßflächen ohne Eckbögen
    assert np.allclose(np.abs(side[:, 0]), 300 - p.w / 2, atol=1e-6)


def test_shell1_only_touched():
    """Zwei Schalen: Die Wellentäler berühren Schale 1 (Abstand in [(1 − ε)w, w]), schneiden nie."""
    sec = _quader(200, n=1)
    p, paths, rep = _plan(sec, shells=2)
    lp = paths[0]
    ring = _outfill(lp).points
    inner = np.vstack([s.points for s in lp.segments if s.kind == "inner"])
    trough = ring[(np.abs(ring[:, 0]) < 200) & (ring[:, 1] > -85 + 3.9) & (ring[:, 1] < 0)]
    assert len(trough)
    d = min(Point(q).distance(LineString(inner)) for q in trough)
    assert (1 - p.eps) * p.w <= d <= p.w
    assert rep.paths[0].contacts_per_m > 0


def test_wavelength_fit_and_arc_gain():
    """Ganze Zahl von Wellen je gerader Strecke; Bogenzuwachs gegen die Näherung (πA/λ)²."""
    sec = _quader(200, length=1200, n=1)
    _, paths, _ = _plan(sec, shells=1)
    m = paths[0].meta["outfill"]
    assert len(m["runs"]) == 2
    for r in m["runs"]:
        assert r["length_mm"] == pytest.approx(1110.0)
        assert r["waves"] == 7 and r["wavelength_mm"] == pytest.approx(1110.0 / 7, abs=1e-3)
        A, lam = 8.0, r["wavelength_mm"]
        assert r["arc_gain_pct"] == pytest.approx(100 * (math.pi * A / lam) ** 2, rel=0.03)
        assert r["min_radius_mm"] == pytest.approx(lam**2 / (4 * math.pi**2 * A), rel=1e-3)


def test_longest_straight_outer_reduced():
    """Kennzahl: längste gerade Strecke an den langen Seiten. Grundmuster 600 × 200: 510 mm;
    Außenwelle Sinus < 50 mm (nur um die Wendepunkte), Zickzack ≈ Flankenlänge < λ/2 + 10."""
    sec = _quader(200, n=1)
    base = pt.plan_pattern(sec, params_for("schalen", shells=2))
    rep0 = pt.measure(base, sec, params_for("schalen", shells=2))
    assert rep0.paths[0].longest_straight_outer_mm == pytest.approx(510.0, abs=1.0)
    for shape, limit in (("sinus", 50.0), ("zickzack", 95.0)):
        p, paths, rep = _plan(sec, shells=2, outer_shape=shape)
        assert paths[0].meta["outfill"]["longest_straight_face_mm"] < limit
        # metrics: das Maximum liegt jetzt an der (gewollt geraden) Stoßfläche: 200 − w − 2·r = 110
        assert rep.paths[0].longest_straight_outer_mm == pytest.approx(110.0, abs=1.0)


def test_faces_choice_and_seam():
    """Nur y_min gewellt; Naht bei kleiner Auslenkung im Eckbogen, bei D = 16 mm im Wellental."""
    sec = _quader(200, n=1)
    _, paths, _ = _plan(sec, shells=2, outer_faces="y_min")
    runs = paths[0].meta["outfill"]["runs"]
    assert len(runs) == 1 and runs[0]["from"][1] < 0
    assert paths[0].meta["seam"][1] < -60 and paths[0].meta["seam"][0] < -270  # Eckbogen
    _, paths, _ = _plan(sec, shells=1)
    sx, sy = paths[0].meta["seam"]
    assert abs(sx) < 255 and sy == pytest.approx(-100 + 15 + 16, abs=0.6)  # Wellental, y_min


def test_short_wall_stays_straight():
    """Gerade Strecke kürzer als λ/2: keine Welle, Ring wie das Grundmuster."""
    sec = _quader(200, length=150, n=1)
    p, paths, rep = _plan(sec, shells=1, outer_wavelength_mm=400.0)
    assert rep.ok
    assert paths[0].meta["outfill"]["runs"] == []


def test_presets_and_preview_svg():
    pre = pt.load_preset(PRESETS / "aussenwelle.json")
    p = pt.preset_params(pre)
    assert p.outfill == "aussenwelle" and p.infill == "none"
    data = pt.preview(pre)
    assert data["ok"]
    json.dumps(data)
    root = ET.fromstring(pt.preview_svg(data=data))
    assert root.tag.endswith("svg")
    for f in sorted(DOC_PRESETS.glob("aussenwelle_*.json")):
        d = pt.preview(pt.load_preset(f))
        assert d["ok"], f.name


def _overhang_by_layer(paths, n):
    beads: dict[int, object] = {}
    for lp in paths:
        g = LineString(lp.polyline()).buffer(15.0)
        beads[lp.layer] = unary_union([beads[lp.layer], g]) if lp.layer in beads else g
    return [beads[L + 1].difference(beads[L].buffer(2.0)).area for L in range(n - 1)]


@pytest.mark.parametrize("sill", [True, False])
def test_opening_waves_aligned_over_all_layers(sill):
    """M3 über das ganze Teil: Wand 1200 × 200 mit Fenster (Brüstung bzw. Sturz). Gewellt wird nur,
    wo jede Schicht ein gerades Stück hat; die Wellen liegen deckungsgleich, die Außenwelle fügt
    dem Überhang der Laibungen (Aufgabe der Familie Topologie) nichts hinzu."""
    full, win = box(-600, -100, 600, 100), box(-200, -150, 200, 150)
    sec = {L: (full if (L < 3) == sill else full.difference(win)) for L in range(6)}
    _, paths, _ = _plan(sec, shells=1)
    base = pt.plan_pattern(sec, params_for("schalen", shells=1))
    ov, ov0 = _overhang_by_layer(paths, 6), _overhang_by_layer(base, 6)
    assert all(a <= b + 5.0 for a, b in zip(ov, ov0, strict=True)), (ov, ov0)
    xs = sorted(
        {round(x) for lp in paths for r in lp.meta["outfill"]["runs"] for x in (r["from"][0], r["to"][0])}
    )
    assert xs == [-555, -245, 245, 555]  # nur neben der Öffnung, in allen Schichten gleich
