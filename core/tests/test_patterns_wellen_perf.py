"""Wellen-Laufzeit und Rückfall statt Absturz (Aufgabe Wellen-Fix, Nachtlauf Druckmuster).

1. Gleichheit: Die schnelle Wellenplanung (Einlaufsuche mit Prüfung bei Bedarf, Radius und
   Wellenanfang ohne die ganze Welle, `_wellen_form`), die schnelle Sehnenwahl in `resample_curve`
   und der schnelle Schalenwechsel liefern dieselben Pfade wie die eingefrorenen Referenzen
   (`patterns_wellen_reference.py`, `patterns_resample_reference.py`, Stand 5dd66ee), bis 1e-6.
   Bewusste Abweichung: Bei Gleichstand der Wellenradien (Band begrenzt den Radius, z. B. Mäander
   mit λ = 100 mm auf 1200 × 200: r = A = 26,5 mm für 17 … 20 Halbwellen) entschied bisher das
   Rundungsrauschen, jetzt die Gleichstandsschwelle (`wellen.RADIUS_TIE_MM`). Dort ändert sich nur
   die Halbwellenzahl (115,67 → 109,58 mm, Ziel 100 mm); measure: gleiche Regeln (nur M6-Warnung
   r = 26,5 < w), Mindestabstand 25,87 mm und Mindestradius 26,5 mm wie zuvor.
2. Laufzeit: `preview` der vier Wellenmuster auf 600 × 200 und 1200 × 200 unter 100 ms.
3. Rückfall: Der L-Querschnitt aus dem Fehlerbericht stürzt nicht mehr ab (Restring einer Schale
   entfällt mit Hinweis in meta), und zufällige Parameter innerhalb der ParamSpecs auf Rechteck,
   L-Form und zwei Inseln stürzen nie ab.

Gemessen am 20.10.2026 auf der Cloud-VM (4 vCPU, Last 7 … 10 durch parallele Agenten), `preview`
je Anfrage (Schicht L und L + 1 samt Messung), Median aus 5 Läufen direkt nacheinander, vorher
(5dd66ee) → nachher in ms (Bestwert nachher in Klammern):

| Muster   | 600 × 200     | 1200 × 200     | 1200 × 365     |
|----------|---------------|----------------|----------------|
| sinus    | 125 → 68 (59) | 144 → 81 (73)  | 149 → 77 (76)  |
| zickzack | 142 → 70 (58) | 140 → 83 (77)  | 182 → 88 (83)  |
| trapez   | 124 → 63 (55) | 146 → 81 (77)  | 179 → 101 (89) |
| maeander | 187 → 94 (67) | 401 → 114 (85) | 249 → 167 (114)|

Rest je Anfrage (1200 × 200, Sinus): Messung ≈ 35 ms, Wellenplanung ≈ 28 ms, Schalen ≈ 8 ms.
"""

from __future__ import annotations

import importlib
import math
import statistics
import time
from typing import Any

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

import patterns_resample_reference as rref
import patterns_wellen_reference as wref
from roboprint import patterns as pt
from roboprint.patterns.families import _wellen_form as lokal
from roboprint.patterns.geometry import Loop, biarc, biarc_radius, offset_ring, resample_curve
from roboprint.patterns.preview import make_outline, params_for

wellen = importlib.import_module("roboprint.patterns.families.wellen")
shells = importlib.import_module("roboprint.patterns.shells")
geometry = importlib.import_module("roboprint.patterns.geometry")

WAVES = ("sinus", "zickzack", "trapez", "maeander")
TOL = 1e-6
L_SHAPE = Polygon([(0, 0), (1528, 0), (1528, 249), (249, 249), (249, 917), (0, 917)])
CRASH_PARAMS = {
    "bead_width_mm": 58.3,
    "shells": 4,
    "wavelength_mm": 1804.6,
    "phase_deg": 360.0,
    "contact_overlap_pct": 6.8,
    "layer_height_mm": 5.0,
    "corner_radius_mm": 13.4,
    "transition_radius_mm": 133.2,
}


def _same(a: Any, b: Any, where: str = "") -> None:
    if isinstance(a, pt.LayerPath | pt.Segment | pt.Contact):
        for k in vars(a):
            _same(getattr(a, k), getattr(b, k), f"{where}.{k}")
    elif isinstance(a, dict):
        assert set(a) == set(b), where
        for k in a:
            _same(a[k], b[k], f"{where}[{k!r}]")
    elif isinstance(a, list | tuple):
        assert len(a) == len(b), f"{where}: {len(a)} != {len(b)}"
        for k, (x, y) in enumerate(zip(a, b, strict=True)):
            _same(x, y, f"{where}[{k}]")
    elif isinstance(a, np.ndarray):
        assert a.shape == b.shape, f"{where}: {a.shape} != {b.shape}"
        np.testing.assert_allclose(a, b, atol=TOL, rtol=0, err_msg=where)
    elif isinstance(a, float) and not isinstance(a, bool):
        if math.isinf(a) or math.isnan(a):
            assert (math.isinf(b) and a == b) or (math.isnan(a) and math.isnan(b)), where
        else:
            assert abs(a - b) <= TOL, f"{where}: {a!r} != {b!r}"
    else:
        assert a == b, f"{where}: {a!r} != {b!r}"


def _use_reference(m: pytest.MonkeyPatch) -> None:
    m.setattr(wellen, "build_wave", wref.build_wave)
    m.setattr(shells, "lane_change", wref.lane_change)
    m.setattr(shells, "clear_end", wref.clear_end)
    for mod in (shells, wellen, geometry):
        m.setattr(mod, "resample_curve", rref.resample_curve)


def _random_value(rng: np.random.Generator, spec: Any) -> Any:
    if spec.kind == "bool":
        return bool(rng.random() < 0.5)
    if spec.kind == "choice":
        return str(rng.choice(list(spec.choices)))
    if spec.kind == "int":
        return int(rng.integers(int(spec.minimum), int(spec.maximum) + 1))
    if rng.random() < 0.15:  # Bereichsgrenzen
        return float(rng.choice([spec.minimum, spec.maximum]))
    return round(float(rng.uniform(spec.minimum, spec.maximum)), 1)


def _random_case(rng: np.random.Generator) -> tuple[str, dict[str, Any], dict[int, Any]]:
    name = str(rng.choice(WAVES))
    d: dict[str, Any] = {s.name: _random_value(rng, s) for s in pt.CORE_PARAM_SPECS}
    d.update({s.name: _random_value(rng, s) for s in pt.registry.get(name).params})
    d["infill"] = name
    ln, th = rng.uniform(300, 2000), rng.uniform(120, 450)
    kind = int(rng.integers(0, 4))
    if kind == 0:
        g = box(-ln / 2, -th / 2, ln / 2, th / 2)
    elif kind == 1:
        gap = rng.uniform(80, 300)
        g = MultiPolygon([box(-ln / 2, -th / 2, -gap / 2, th / 2), box(gap / 2, -th / 2, ln / 2, th / 2)])
    elif kind == 2:
        th = min(th, 0.45 * ln)  # sonst überschneidet sich das L selbst (ungültige Eingabe)
        g = Polygon([(0, 0), (ln, 0), (ln, th), (th, th), (th, 0.6 * ln), (0, 0.6 * ln)])
    else:
        g = L_SHAPE
    return name, d, {0: g, 1: g}


# --------------------------------------------------------------------------- Bausteine


def test_resample_curve_equals_reference():
    rng = np.random.default_rng(3)
    curves = []
    for g in (box(-300, -100, 300, 100), L_SHAPE):
        for d, r in ((15, 30), (45, 30), (75, 0), (20, 13)):
            curves += [(ring, True) for _, ring in offset_ring(g, d, r)]
    for _ in range(300):
        pts = np.cumsum(rng.normal(size=(int(rng.integers(2, 60)), 2)) * rng.choice([0.5, 3.0, 30.0]), axis=0)
        curves.append((pts, False))
    t = np.linspace(0, 6 * math.pi, 900)
    curves.append((np.column_stack([t * 40, 25 * np.cos(t)]), False))
    for k, (c, closed) in enumerate(curves):
        for step, tol in ((20.0, 0.5), (5.0, 0.05), (20.0, 0.0)):
            a = resample_curve(c, step, tol, closed=closed)
            b = rref.resample_curve(c, step, tol, closed=closed)
            assert a.shape == b.shape and np.array_equal(a, b), k


def test_loop_points_equal_point():
    rng = np.random.default_rng(4)
    for _, ring in offset_ring(L_SHAPE, 45.0, 30.0):
        lp = Loop(ring)
        s = np.concatenate([rng.uniform(-2 * lp.length, 3 * lp.length, 500), lp.cum, lp.cum + lp.length])
        assert np.array_equal(lp.points(s), np.array([lp.point(x) for x in s]))


def test_biarc_radius_equals_biarc():
    rng = np.random.default_rng(5)
    for _ in range(500):
        p1, p2 = rng.normal(size=2) * 50, rng.normal(size=2) * 50
        t1, t2 = rng.normal(size=2), rng.normal(size=2)
        res, r = biarc(p1, t1, p2, t2), biarc_radius(p1, t1, p2, t2)
        assert (res is None) == (r is None)
        if res is not None:
            assert res[1] == r


@pytest.mark.parametrize("shape", ("zickzack", "trapez", "maeander"))
def test_local_radius_and_start_match_full_wave(shape):
    """`trapezoid_radius` und `wave_start` (ohne Welle) gleichen Radius und ersten zwei Punkten der
    ganzen gerundeten Welle."""
    rng = np.random.default_rng(6)
    n = 0
    for _ in range(300):
        lam, amp = rng.uniform(80, 600), rng.uniform(10, 80)
        phase, sigma = rng.uniform(0, 2 * math.pi), float(rng.choice([-1.0, 1.0]))
        radius = rng.uniform(15.5, 120)
        pl = {"zickzack": 0.0, "maeander": lam / 2}.get(shape, rng.uniform(0, lam / 2))
        u_s = rng.uniform(-600, 0)
        u_e = u_s + lam * rng.uniform(1, 5)
        uv, rmin, _ = wellen.trapezoid_uv(u_s, u_e, lam, amp, phase, sigma, pl, radius)
        r = wellen.trapezoid_radius(lam, amp, phase, sigma, pl, radius)
        if not len(uv):
            assert r == 0.0
            continue
        assert abs(r - rmin) <= 1e-9 * max(1.0, rmin)
        verts = wellen._trapezoid_verts(u_s, min(u_e, u_s + lam), lam, amp, phase, sigma, pl, radius)
        st = lokal.wave_start(verts, radius, u_s, 0.05, wellen.FINE_MM)
        if st is not None:
            np.testing.assert_allclose(np.array(st), uv[:2], atol=1e-9, rtol=0)
            n += 1
    assert n > 100


@pytest.mark.parametrize("shape", WAVES)
def test_prefix_wave_equals_start_of_full_wave(shape):
    opts = {"w": 30.0, "wavelength_mm": 250.0, "phase_deg": 45.0, "round_radius_mm": 30.0, "plateau_mm": 60.0}
    for u_s in (-550.0, -523.0, -400.5):
        full, lam, n, _ = wellen.wave_uv(shape, u_s, 525.0, 26.5, opts, 1.0)
        part, lam2, n2, _ = wellen.wave_uv(shape, u_s, 525.0, 26.5, opts, 1.0, None, (2.0, 70.0))
        assert (lam2, n2) == (lam, n)
        assert np.array_equal(part[:-1], full[: len(part) - 1])
        start = wellen.wave_uv(shape, u_s, 525.0, 26.5, opts, 1.0, start_only=True)[0]
        np.testing.assert_allclose(start, full[:2], atol=1e-9, rtol=0)


# --------------------------------------------------------------------------- Pfade wie die Referenz


@pytest.mark.parametrize("size", [(600.0, 200.0), (1200.0, 200.0), (1200.0, 365.0), (600.0, 300.0)])
@pytest.mark.parametrize("shape", WAVES)
def test_plan_equals_reference(shape, size, monkeypatch):
    geom = make_outline(size)
    sections = {0: geom, 1: geom}
    for extra in ({}, {"phase_deg": 180.0}, {"shells": 1}, {"shells": 3}, {"wavelength_mm": 400.0}):
        p = params_for(shape, **extra)
        new = pt.plan_pattern(sections, p)
        with monkeypatch.context() as m:
            _use_reference(m)
            old = pt.plan_pattern(sections, p)
        _same(new, old, f"{shape} {size} {extra}")


@pytest.mark.parametrize("seed", range(6))
def test_random_params_equal_reference(seed, monkeypatch):
    rng = np.random.default_rng(2000 + seed)
    for _ in range(4):
        name, d, sections = _random_case(rng)
        p = pt.params_from_dict(d)
        new = pt.plan_pattern(sections, p)
        with monkeypatch.context() as m:
            _use_reference(m)
            try:
                old = pt.plan_pattern(sections, p)
            except ValueError:
                continue  # Absturz der Referenz (Restring), siehe Rückfall unten
        _same(new, old, f"{name} {d}")
        assert pt.measure(new, sections, p).to_dict() == pt.measure(old, sections, p).to_dict()


# --------------------------------------------------------------------------- Laufzeit


@pytest.mark.parametrize("shape", WAVES)
def test_preview_waves_below_100ms(shape):
    """Ziel: < 100 ms je Vorschau für 600 × 200 und 1200 × 200. Wie test_patterns_perf: Bestwert
    aus 5 Läufen < 100 ms, Median < 150 ms (belastete VM mit parallelen Tests)."""
    data = {"pattern": shape, "params": {}}
    for size in ((600.0, 200.0), (1200.0, 200.0)):
        pt.preview(data, size)  # Aufwärmen
        ts = []
        for _ in range(5):
            t = time.perf_counter()
            pt.preview(data, size)
            ts.append((time.perf_counter() - t) * 1e3)
        med, best = statistics.median(ts), min(ts)
        assert best < 100.0, f"{shape} {size}: Bestwert {best:.1f} ms (Median {med:.1f} ms)"
        assert med < 150.0, f"{shape} {size}: Median {med:.1f} ms"


# --------------------------------------------------------------------------- Rückfall statt Absturz


def test_l_section_from_report_falls_back_with_hint():
    """Fehlerbericht: Sinus auf dem L-Querschnitt, w = 58,3 mm, 4 Schalen warf `ValueError: x must
    consist of vectors of length 2 but has shape (0,)` (Schale 2 ist in der Innenecke nur ein
    Restring von 1,4 mm, `clear_end` fand kein Ende)."""
    data = pt.preview(
        {"pattern": "sinus", "params": CRASH_PARAMS}, {"polygon": list(L_SHAPE.exterior.coords)}
    )
    (path,) = data["paths"]
    drop = path["meta"]["shells_dropped"]
    assert drop["from_shell"] == 2 and drop["count"] == 2 and "Restring" in drop["hint"]
    assert path["meta"]["shells"] == 2
    assert "skipped" in path["meta"]["infill"]  # kein Infill-Band mehr
    # M6-Fehler stammen vom eingegebenen Eckradius 13,4 mm < w/2, nicht vom Rückfall
    assert {v["rule"] for v in data["violations"] if v["severity"] == "error"} <= {"M6"}
    assert data["layer_change"]["status"] == "vertical"


@pytest.mark.parametrize("seed", range(10))
def test_random_wave_params_never_crash(seed):
    """Zufallsparameter innerhalb der ParamSpecs (inkl. Grenzen) auf Rechteck, zwei Inseln und
    L-Formen: Planen, Messen und Vorschau stürzen nie ab."""
    rng = np.random.default_rng(7000 + seed)
    for _ in range(6):
        name, d, sections = _random_case(rng)
        p = pt.params_from_dict(d)
        paths = pt.plan_pattern(sections, p)
        pt.measure(paths, sections, p)
        assert paths, f"{name} {d}"
