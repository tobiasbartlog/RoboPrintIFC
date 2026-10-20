"""Infill-Familie „Wellen“ (Sinus, Zickzack, Trapez, Mäander): M1–M7 mit patterns.metrics.

Geprüft auf den Quadern 600 × 200 / 300 / 365 mm mit zwei Schalen und mit einer Schale je Seite,
dazu Grenzfälle mit Zahlen (Mäander im 50-mm-Band, Zickzack λ ≤ 4·r, Einlauf ohne `open_end`).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from roboprint import patterns as pt
from roboprint.patterns.families import wellen
from roboprint.patterns.metrics import bead_area
from roboprint.patterns.plan import island_context, part_bounds
from roboprint.patterns.preview import params_for
from roboprint.patterns.shells import shell_chain

SHAPES = ("sinus", "zickzack", "trapez", "maeander")
PRESETS = Path(pt.__file__).parent / "presets"


def _prism(geom, n=4):
    return {L: geom for L in range(n)}


def _quader(thickness, n=4):
    return _prism(box(-300, -thickness / 2, 300, thickness / 2), n)


def _plan(shape, sections, **kw):
    p = params_for(shape, **kw)
    paths = pt.plan_pattern(sections, p)
    return p, paths, pt.measure(paths, sections, p)


CASES = [(200, 2), (300, 2), (365, 2), (200, 1), (300, 1), (365, 1)]


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize(("thickness", "shells"), CASES)
def test_wave_valid_on_quader(shape, thickness, shells):
    sec = _quader(thickness)
    p, paths, rep = _plan(shape, sec, shells=shells)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    # M1: ein Strang je Schicht, Infill hängt ohne Verbinder (Länge 0) am Schalenpfad
    assert [lp.layer for lp in paths] == [0, 1, 2, 3]
    lp = paths[0]
    assert lp.segments[-1].kind == "infill" and lp.segments[-1].shell == shells
    assert all(np.allclose(a, b) for a, b in lp.connectors())
    assert "skipped" not in lp.meta["infill"]
    # M4: alternate → Ende L == Anfang L+1, reiner Z-Hub
    assert all(c["status"] == "vertical" and c["distance_mm"] == 0.0 for c in rep.layer_changes)
    assert np.array_equal(paths[1].start, paths[0].end)
    # M2: kein Doppelmaterial (Bogenlängenabstand > 2w → Abstand ≥ (1 − ε)·w)
    assert rep.paths[0].min_clearance_mm >= (1 - p.eps) * p.w
    # M6: hart ≥ w/2 überall; das Ziel w verfehlt nur der Mäander im 50-mm-Band (Test unten)
    assert rep.paths[0].min_radius_mm >= p.w / 2
    if shape == "maeander" and (thickness, shells) == (200, 2):
        assert {(v.rule, v.severity) for v in rep.violations} == {("M6", "warn")}
    else:
        assert not rep.violations, [v.to_dict() for v in rep.violations]
    assert lp.meta["infill"]["lead_in_radius_mm"] >= 0.95 * p.w


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize(("thickness", "shells"), [(200, 2), (365, 2), (200, 1)])
def test_wave_touches_both_inner_shells(shape, thickness, shells):
    """M7: Berge und Täler berühren beide Innenschalen mit Mittellinienabstand in [(1 − ε)w, w]."""
    sec = _quader(thickness, 1)
    p, paths, _ = _plan(shape, sec, shells=shells)
    lp = paths[0]
    contacts = lp.contacts
    assert len(contacts) >= 3
    w = p.w
    for c in contacts:
        assert c.kind == "shell"
        assert (1 - p.eps) * w <= c.distance_mm <= w + p.contact_tol_mm
    ys = np.array([c.at[1] for c in contacts])
    inner_y = thickness / 2 - (shells - 0.5) * w  # Mittellinie der innersten Schale
    edge = inner_y - w / 2  # Raupenkante, an der der Kontakt liegt
    assert np.any(ys > edge - 5) and np.any(ys < -edge + 5)
    # Amplitude aus dem Band: A = halbe Bandbreite + Überlappung (5 % von w)
    info = lp.meta["infill"]
    assert info["amplitude_mm"] == pytest.approx(info["band_mm"][1] / 2 + 0.05 * w)
    assert info["band_mm"][1] == pytest.approx(thickness - 2 * shells * w - w)


def test_sine_radius_and_wavelength_fit():
    sec = _quader(300, 1)
    p, paths, rep = _plan("sinus", sec, wavelength_mm=250.0)
    info = paths[0].meta["infill"]
    lam, amp = info["wavelength_mm"], info["amplitude_mm"]
    # kleinster Sinusradius λ²/(4π²A) ≥ w: bei A = 76,5 mm wären 4 Halbwellen (λ ≈ 220) nur 16 mm
    assert lam**2 / (4 * math.pi**2 * amp) >= p.w
    assert info["wave_min_radius_mm"] >= p.w
    assert info["half_waves"] < round(450 / 125)
    assert rep.ok


def test_meander_radius_limited_by_band():
    """Mäander im 50-mm-Band (S1, 2 Schalen): Ecken r ≤ A = 26,5 mm < w → nur M6-Warnung."""
    sec = _quader(200)
    p, paths, rep = _plan("maeander", sec)
    assert rep.ok
    info = paths[0].meta["infill"]
    assert info["wave_min_radius_mm"] == pytest.approx(26.5, abs=0.01)
    assert {(v.rule, v.severity) for v in rep.violations} == {("M6", "warn")}
    # mit 12 % Überlappung (3,6 mm ≤ ε·w) wird A = 28,6 mm ≥ (1 − 5 %)·w: keine Warnung mehr
    p2, paths2, rep2 = _plan("maeander", sec, contact_overlap_pct=12.0)
    assert rep2.ok and not rep2.violations, [v.to_dict() for v in rep2.violations]
    assert paths2[0].meta["infill"]["wave_min_radius_mm"] == pytest.approx(28.6, abs=0.01)


def test_overlap_above_eps_rejected():
    with pytest.raises(ValueError):
        pt.plan_pattern(_quader(200, 1), params_for("sinus", contact_overlap_pct=15.0, eps=0.1))


def test_zigzag_needs_wavelength_above_four_radii():
    # λ ≤ 4·r: der Bogenabzug wächst schneller als die Scheitelhöhe, A ist unerreichbar
    assert wellen.zigzag_height(120.0, 26.5, 30.0) == math.inf
    h = wellen.zigzag_height(220.0, 26.5, 30.0)
    alpha = math.atan(4 * h / 220.0)
    assert h - 30.0 * (1 / math.cos(alpha) - 1) == pytest.approx(26.5, abs=1e-6)
    # Wunsch λ = 150 bei 450 mm Band → 3 Halbwellen à 150 (λ = 300 > 120) statt λ ≤ 120
    _, paths, rep = _plan("zickzack", _quader(200, 1), wavelength_mm=100.0)
    assert rep.ok and paths[0].meta["infill"]["wavelength_mm"] > 120.0


def test_core_without_open_end_leaves_no_room_for_lead_in():
    """Beleg für `shell_chain(open_end=True)`: Endet die innere Schale wie ohne Infill (Spitze an
    der ankommenden S-Kurve), kommt jede Viertelkehre mit R ≥ w/2 der S-Kurve näher als (1 − ε)·w."""
    g = box(-300, -100, 300, 100)
    sec = {0: g}
    p = pt.PatternParams()
    ctx = island_context(0, 0, g, sec, part_bounds(sec), p)
    inner = shell_chain(ctx).segments[1].points
    head = pt.densify(inner[:8], 1.0)  # S-Kurve Schale 0 → 1
    e = inner[-1]
    assert e[0] == pytest.approx(-255.0) and inner[-1][1] < inner[-2][1]  # endet links, nach unten
    for R in (15.0, 20.0, 30.0):
        a = np.linspace(np.pi, 1.5 * np.pi, 91)
        arc = e + np.array([R, 0.0]) + R * np.c_[np.cos(a), np.sin(a)]
        d = np.min(np.linalg.norm(arc[:, None] - head[None], axis=2))
        assert d < (1 - p.eps) * p.w  # 24,4 mm bei R = 15
    # mit open_end endet sie früher, das Infill findet einen Einlauf mit R = w
    _, paths, rep = _plan("sinus", _quader(200, 1))
    assert rep.ok and paths[0].meta["infill"]["lead_in_radius_mm"] == pytest.approx(30.0)


@pytest.mark.parametrize("shells", [1, 2])
@pytest.mark.parametrize("thickness", [170, 200, 365])
def test_wall_stays_closed(shells, thickness):
    """Kein Durchgang von der Außenfläche in den Hohlraum: Bei einer Schale schließt die S-Kurve
    am Ringende an den Ringanfang an (virtuelle Bahn konzentrisch, Ecke im Abstand w)."""
    g = box(-300, -thickness / 2, 300, thickness / 2)
    p, paths, rep = _plan("sinus", {0: g}, shells=shells)
    lp = paths[0]
    assert rep.ok
    assert [s.kind for s in lp.segments][-1] == "infill" and not lp.segments[0].closed
    # Kontakt (Abstand ≤ w + contact_tol) zählt als geschlossen: Raupen um contact_tol/2 breiter
    voids = [v for v in pt.polygons(g.difference(bead_area(lp, p.w + p.contact_tol_mm))) if v.area > 1.0]
    cavity = g.buffer(-shells * p.w - 2.0)
    through = [v for v in voids if v.intersects(g.exterior.buffer(0.5)) and v.intersects(cavity)]
    assert not through, [v.centroid.coords[0] for v in through]
    assert "open_wall" not in lp.meta


@pytest.mark.parametrize("phase", [90.0, 180.0, 270.0])
def test_phase_variants_valid(phase):
    sec = _quader(200, 2)
    _, paths, rep = _plan("sinus", sec, phase_deg=phase)
    assert rep.ok
    assert paths[0].meta["infill"]["phase_deg"] == phase


def test_two_islands_each_with_wave():
    geom = MultiPolygon([box(-300, -100, -50, 100), box(50, -100, 300, 100)])
    sec = _prism(geom)
    _, paths, rep = _plan("sinus", sec)
    assert rep.ok
    assert [(lp.layer, lp.island) for lp in paths][:4] == [(0, 0), (0, 1), (1, 1), (1, 0)]
    assert all(lp.segments[-1 if lp.layer % 2 == 0 else 0].kind == "infill" for lp in paths)
    assert all(c["status"] == "vertical" for c in rep.layer_changes)


def test_non_rectangular_band_skips_infill_and_stays_valid():
    poly = Polygon([(0, 0), (600, 0), (600, 200), (200, 200), (200, 600), (0, 600)])
    sec = _prism(poly)
    _, paths, rep = _plan("sinus", sec)
    assert rep.ok
    assert "skipped" in paths[0].meta["infill"]
    assert all(s.kind != "infill" for s in paths[0].segments)


@pytest.mark.parametrize("shape", SHAPES)
def test_preset_preview_and_svg(shape):
    preset = pt.load_preset(PRESETS / f"{shape}.json")
    assert preset["pattern"] == shape
    data = pt.preview(preset)
    assert data["ok"]
    assert any(sg["kind"] == "infill" for lp in data["paths"] for sg in lp["segments"])
    svg = pt.preview_svg(data=data)
    assert svg.startswith("<svg") and "infill" in svg
    names = {c["name"] for c in pt.catalog()}
    assert set(SHAPES) <= names
