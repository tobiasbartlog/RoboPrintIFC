"""Familie „Mehrfach“ (Doppelwelle, Waben, Fermat-Spirale): M1–M7 mit patterns.metrics, Gegenprobe
ohne metrics und mit dem unabhängigen Orakel `verify_muster`.

Quader 600 × 200 / 300 / 365 mm mit zwei Schalen und mit einer Schale je Seite, Pfeiler 300 × 200
und kleinere Inseln. Grenzfälle mit Zahlen: S1-Band 50 mm ist zu schmal für zwei Wellen.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, Polygon, box

from roboprint import patterns as pt
from roboprint.patterns.families import _mehrfach_fermat as fermat
from roboprint.patterns.families import mehrfach
from roboprint.patterns.preview import params_for

DOUBLE = ("doppelwelle", "waben")
PRESETS = Path(pt.__file__).parent / "presets"
REPO = Path(__file__).resolve().parents[2]
W = 30.0


def _prism(geom, n=3):
    return {L: geom for L in range(n)}


def _quader(thickness, n=3):
    return _prism(box(-300, -thickness / 2, 300, thickness / 2), n)


def _plan(name, sections, **kw):
    p = params_for(name, **kw)
    paths = pt.plan_pattern(sections, p)
    return p, paths, pt.measure(paths, sections, p)


def _infill(lp):
    return [s for s in lp.segments if s.kind == "infill"]


# --------------------------------------------------------------------------- Doppelwelle / Waben

CASES = [(300, 2), (365, 2), (200, 1), (300, 1), (365, 1)]


@pytest.mark.parametrize("name", DOUBLE)
@pytest.mark.parametrize(("thickness", "shells"), CASES)
def test_double_valid_on_quader(name, thickness, shells):
    sec = _quader(thickness)
    p, paths, rep = _plan(name, sec, shells=shells)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    assert not rep.violations, [v.to_dict() for v in rep.violations]
    # M1: ein Strang je Schicht; Welle 1, Wende, Welle 2 stoßen ohne Verbinder (Länge 0) aneinander
    assert [lp.layer for lp in paths] == [0, 1, 2]
    lp = paths[0]
    inf = _infill(lp)
    assert len(inf) == 3 and all(s.shell == shells for s in inf)
    assert all(np.allclose(a, b) for a, b in lp.connectors())
    info = lp.meta["infill"]
    assert "skipped" not in info and info["lead_in_radius_mm"] >= 0.95 * p.w
    # M4: alternate → reiner Z-Hub
    assert all(c["status"] == "vertical" and c["distance_mm"] == 0.0 for c in rep.layer_changes)
    # M2/M6
    m = rep.paths[0]
    assert m.min_clearance_mm >= (1 - p.eps) * p.w
    assert m.min_radius_mm >= p.w * 0.95
    # M7: Mittelkontakte (node) zwischen Welle 1 und Welle 2, Abstand w − Überlappung
    nodes = [c for c in m.contacts if c.kind == "node"]
    assert len(nodes) >= info["wavelengths"]
    for c in nodes:
        assert (1 - p.eps) * p.w <= c.distance_mm <= p.w + p.contact_tol_mm
        assert abs(c.at[1]) < 5.0  # in der Bandmitte
    # beide Innenschalen werden berührt
    shell_y = [c.at[1] for c in m.contacts if c.kind == "shell" and abs(c.at[0]) < 150]
    assert min(shell_y) < -thickness / 4 and max(shell_y) > thickness / 4


@pytest.mark.parametrize("name", DOUBLE)
def test_wave_two_mirrors_wave_one(name):
    """Welle 2 ist das Spiegelbild von Welle 1 an der Bandachse (gegenphasig, Kontakt in der Mitte)."""
    sec = _quader(300, 1)
    _, paths, _ = _plan(name, sec, shells=2)
    w1, turn, w2 = _infill(paths[0])
    info = paths[0].meta["infill"]
    # Welle 1 ohne Einlauf: Punkte mit x ≥ Wellenanfang
    x0 = -225.0 + info["u_start_mm"] + 1.0
    a = w1.points[w1.points[:, 0] >= x0]
    mirror = np.column_stack([a[:, 0], -a[:, 1]])
    d = LineString(w2.points).distance
    assert max(d(LineString([q, q + 1e-6])) for q in mirror) < 0.6
    # Wende: Halbkreis mit Radius = Scheitelhöhe, berührt die Stirnschale
    r = info["turn_radius_mm"]
    assert r == pytest.approx(info["crest_v_mm"])
    assert turn.points[:, 0].max() == pytest.approx(225.0 + info["overlap_mm"], abs=0.6)


def test_s1_band_too_narrow_with_numbers():
    """S1 (200 mm, 2 Schalen, Hohlraum 80 mm, Band 50 mm): Hub je Welle 2A = (B − w)/2 + 1,5·o
    = 12,25 mm < w/2 → Doppelwelle und Waben entfallen, der Schalenpfad bleibt gültig."""
    sec = _quader(200)
    for name in DOUBLE:
        p, paths, rep = _plan(name, sec)
        info = paths[0].meta["infill"]
        assert rep.ok and "skipped" in info
        assert info["stroke_mm"] == pytest.approx((50 - 30) / 2 + 1.5 * 1.5)
        assert info["turn_radius_mm"] == pytest.approx(26.5)  # < w: Wende wäre M6-Warnung
        assert "55.5" in info["skipped"]  # Mindestband w + 2·w/2 − 3·o
        assert not _infill(paths[0])
    # Waben bei 60°: zwei Eckbögen r ≥ w/2 brauchen den Hub 2·r·(1 − cos 60°) = 15 mm > 12,25 mm;
    # auch ohne Mindesthub entsteht keine gültige Wabe (Eckradius < w/2)
    p, paths, rep = _plan("waben", sec, min_stroke_mm=0.0)
    assert rep.ok
    assert "skipped" in paths[0].meta["infill"] or rep.paths[0].min_radius_mm >= 0.95 * p.w / 2
    assert 2 * 15.0 * (1 - math.cos(math.radians(60))) > 12.25


def test_s1_doppelwelle_without_min_stroke_is_degenerate():
    """Ohne Mindesthub geht die Doppelwelle im 50-mm-Band geometrisch (M2/M6 hart erfüllt), ist aber
    keine: Amplitude 6,1 mm, Wende r = 26,5 mm < w (M6-Warnung)."""
    sec = _quader(200)
    p, paths, rep = _plan("doppelwelle", sec, min_stroke_mm=0.0)
    assert rep.ok
    info = paths[0].meta["infill"]
    assert info["amplitude_mm"] == pytest.approx(6.12, abs=0.01)
    assert ("M6", "warn") in {(v.rule, v.severity) for v in rep.violations}


def test_double_wavelength_fit_and_radius():
    sec = _quader(300)
    _, paths, _ = _plan("doppelwelle", sec, shells=1)
    info = paths[0].meta["infill"]
    amp = info["amplitude_mm"]
    # Sinusradius λ²/(4π²A) ≥ w; Wellenlänge = (u_e − u_s)/k
    assert info["wavelength_mm"] ** 2 / (4 * math.pi**2 * amp) >= W
    assert info["wave_min_radius_mm"] >= W


def test_honeycomb_regular_hexagon_target():
    sec = _quader(200)
    _, paths, _ = _plan("waben", sec, shells=1)
    info = paths[0].meta["infill"]
    s = info["stroke_mm"]
    th = math.radians(60)
    assert info["wavelength_target_mm"] == pytest.approx(
        2 * s / math.sin(th) + 2 * s / math.tan(th), abs=0.05
    )
    assert info["plateau_mm"] > 2 * 30.0 * math.tan(th / 2)  # Platz für beide Eckbögen
    assert info["wavelengths"] == 3


def test_double_two_islands():
    g = box(-600, -150, 600, 150).difference(box(-100, -160, 100, 160))
    sec = _prism(g, 2)
    _, paths, rep = _plan("doppelwelle", sec)
    assert rep.ok
    assert len([lp for lp in paths if lp.layer == 0]) == 2
    assert all("skipped" not in lp.meta["infill"] for lp in paths)


def test_overlap_above_eps_rejected():
    with pytest.raises(ValueError):
        _plan("doppelwelle", _quader(300), contact_overlap_pct=16.0)


# --------------------------------------------------------------------------- Fermat


def _fermat(geom, n=3, **kw):
    sec = _prism(geom, n)
    p, paths, rep = _plan("fermat", sec, **kw)
    return sec, p, paths, rep


def test_fermat_pillar_300x200():
    sec, p, paths, rep = _fermat(box(0, 0, 300, 200))
    assert rep.ok, [v.to_dict() for v in rep.errors]
    # nur Warnungen: Naht am Rand (gewollt, Start auf Ring 0) und Radien < w (Kehre w/2, Ring 2)
    assert {v.rule for v in rep.violations} <= {"M4", "M6"}
    lp = paths[0]
    meta = lp.meta
    assert meta["rows"] == 3 and "fermat_skipped" not in meta
    assert [s.shell for s in lp.segments] == [0, 2, 1]
    assert [s.kind for s in lp.segments] == ["outer", "inner", "inner"]
    assert all(np.allclose(a, b) for a, b in lp.connectors())
    # Start am Rand (Ring 0), Ende eine Raupe weiter innen daneben (Ring 1)
    region = sec[0]
    start, end = lp.start, lp.end
    assert region.exterior.distance(LineString([start, start + 1e-6])) == pytest.approx(15.0, abs=0.01)
    assert region.exterior.distance(LineString([end, end + 1e-6])) == pytest.approx(45.0, abs=0.01)
    assert np.linalg.norm(end - start) < 2 * p.w
    # M4 durch Umkehrung
    assert all(c["status"] == "vertical" and c["distance_mm"] == 0.0 for c in rep.layer_changes)
    assert np.allclose(paths[1].polyline(), lp.polyline()[::-1])
    m = rep.paths[0]
    assert m.min_clearance_mm >= (1 - p.eps) * p.w
    assert m.min_radius_mm >= 0.95 * p.w / 2
    assert meta["turn_radius_mm"] == pytest.approx(15.0)
    # Fläche: drei Ringe; offen bleiben die Mittelzelle (≈ 120 × 20 mm = 4 %), die gerundeten Ecken
    # und die Bruchstelle: 87,3 % des Querschnitts sind Raupe
    beads = LineString(lp.polyline()).buffer(p.w / 2)
    assert beads.intersection(region).area / region.area > 0.85


@pytest.mark.parametrize(
    ("geom", "rows"),
    [
        (box(0, 0, 200, 300), 3),  # Pfeiler hochkant
        (box(0, 0, 200, 150), 2),
        (box(0, 0, 240, 180), 2),  # Ring 2 hätte Eckradius 15 mm → nur zwei Ringe
        (box(0, 0, 200, 200), 2),  # Ring 2 (50 × 50) zu kurz für die Bruchstelle → zwei Ringe
        (Polygon([(0, 0), (300, 0), (300, 200), (150, 200), (150, 400), (0, 400)]), 2),
    ],
)
def test_fermat_small_islands(geom, rows):
    _, p, paths, rep = _fermat(geom)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    lp = paths[0]
    assert lp.meta["rows"] == rows and "fermat_skipped" not in lp.meta
    assert all(c["status"] == "vertical" for c in rep.layer_changes)
    assert rep.paths[0].min_clearance_mm >= (1 - p.eps) * p.w


def test_fermat_wide_island_falls_back_to_shells():
    _, _, paths, rep = _fermat(box(-300, -182.5, 300, 182.5))
    assert rep.ok
    assert "fermat_skipped" in paths[0].meta and paths[0].meta["rows"] == 5
    assert "Welle" in paths[0].meta["fermat_skipped"]


def test_fermat_tiny_island_single_ring():
    _, _, paths, rep = _fermat(box(0, 0, 100, 100))
    assert rep.ok
    assert paths[0].meta["rows"] == 1 and len(paths[0].segments) == 1 and paths[0].segments[0].closed


def test_fermat_two_pillars_one_strand_each():
    g = box(-500, -100, 500, 100).difference(box(-100, -110, 100, 110))
    _, _, paths, rep = _fermat(g, n=2)
    assert rep.ok
    assert sorted((lp.layer, lp.island) for lp in paths) == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert all(lp.meta["rows"] == 3 for lp in paths)


def test_fermat_rows_spacing():
    rows = fermat.fermat_rows(box(0, 0, 300, 200), W, W, 0.15)
    assert len(rows) == 3
    # Nachbarringe im Abstand w (Kontakt), innerster Ring 150 × 50 mm
    for a, b in zip(rows[:-1], rows[1:], strict=True):
        assert LineString(a.pts).distance(Point(b.pts[0])) == pytest.approx(W, abs=0.01)


# --------------------------------------------------------------------------- Presets, Vorschau, Orakel


@pytest.mark.parametrize("name", ["doppelwelle", "waben", "fermat"])
def test_preset_preview_and_svg(name):
    preset = pt.load_preset(PRESETS / f"{name}.json")
    assert preset["pattern"] == name
    data = pt.preview(preset)
    assert data["ok"] and data["metrics"]["strands"] == 1
    svg = pt.preview_svg(data=data)
    assert svg.startswith("<svg")
    names = {c["name"]: c for c in pt.catalog()}
    assert name in names and names[name]["family"] == "mehrfach"
    if name != "fermat":
        assert any(sg["kind"] == "infill" for lp in data["paths"] for sg in lp["segments"])


def test_module_constants():
    assert mehrfach.LABELS["sinus"] == "Doppelwelle"
    assert fermat.MAX_ROWS == 3


def _oracle(tmp_path, name, geom, length, thickness, **kw):
    trimesh = pytest.importorskip("trimesh")
    n = 4
    p = params_for(name, **kw)
    rings = []
    for lp in pt.plan_pattern(_prism(geom, n), p):
        z = (lp.layer + 1) * p.layer_height_mm
        for s in lp.segments:
            wp = [[x, y, z, 0.0, 1.0, 0.0, 0.0] for x, y in s.points.tolist()]
            rings.append({"layer": lp.layer, "shell": s.shell, "kind": s.kind, "closed": s.closed,
                          "link_next": True, "waypoints": wp})  # fmt: skip
    rings[-1]["link_next"] = False
    d = tmp_path / "parts" / "teil"
    d.mkdir(parents=True)
    tp = {"part_id": "teil", "bead_width_mm": p.w, "layer_height_mm": p.layer_height_mm, "rings": rings}
    (d / "toolpath.json").write_text(json.dumps(tp))
    mesh = trimesh.creation.box(extents=(length, thickness, n * p.layer_height_mm))
    c = geom.centroid
    mesh.apply_translation((c.x, c.y, n * p.layer_height_mm / 2))
    mesh.export(d / "part.stl")
    (d / "part.json").write_text(json.dumps({"T_WP": np.eye(4).tolist(), "status": "ok"}))
    cmd = [sys.executable, "-m", "verify_muster.check", str(tmp_path), "--no-trajectory"]
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=600)


@pytest.mark.skipif(not (REPO / "verify_muster" / "check.py").is_file(), reason="verify_muster fehlt")
@pytest.mark.parametrize(
    ("name", "thickness", "shells"), [("doppelwelle", 300, 2), ("waben", 200, 1), ("doppelwelle", 365, 1)]
)
def test_oracle_verify_muster_double(tmp_path, name, thickness, shells):
    """Gegenprobe mit dem unabhängigen Orakel (importiert roboprint nicht)."""
    g = box(-300, -thickness / 2, 300, thickness / 2)
    res = _oracle(tmp_path, name, g, 600, thickness, shells=shells)
    assert res.returncode == 0, res.stdout + res.stderr


@pytest.mark.skipif(not (REPO / "verify_muster" / "check.py").is_file(), reason="verify_muster fehlt")
def test_oracle_verify_muster_fermat_pillar(tmp_path):
    res = _oracle(tmp_path, "fermat", box(-150, -100, 150, 100), 300, 200)
    assert res.returncode == 0, res.stdout + res.stderr


# --------------------------------------------------------------------------- Gegenprobe ohne metrics


def _dense(p, h):
    out = [p[:1]]
    for a, b in zip(p[:-1], p[1:], strict=True):
        k = max(1, math.ceil(float(np.linalg.norm(b - a)) / h))
        out.append(a + (b - a) * np.linspace(0, 1, k + 1)[1:, None])
    return np.vstack(out)


def _circumradius(poly):
    a, b, c = poly[:-2], poly[1:-1], poly[2:]
    cr = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
    num = np.linalg.norm(b - a, axis=1) * np.linalg.norm(c - b, axis=1) * np.linalg.norm(a - c, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = num / (2 * cr)
    r[cr < 1e-9] = np.inf
    return r


@pytest.mark.parametrize(
    ("name", "geom", "shells"),
    [
        ("doppelwelle", box(-300, -150, 300, 150), 2),
        ("waben", box(-300, -182.5, 300, 182.5), 1),
        ("fermat", box(0, 0, 300, 200), 2),
    ],
)
def test_independent_recheck(name, geom, shells):
    """Ohne metrics: einfache Mittellinie, kein Doppelmaterial (Bogenlängenabstand > 2·w →
    Abstand ≥ (1 − ε)·w), r ≥ w/2, Raupe im Teil, Folgeschicht ohne Überhang."""
    sec = _prism(geom, 2)
    p, paths, _ = _plan(name, sec, shells=shells)
    poly = paths[0].polyline()
    d = _dense(poly, 0.25)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(d, axis=0), axis=1))])
    pairs = cKDTree(d).query_pairs(p.w, output_type="ndarray")
    pairs = pairs[np.abs(s[pairs[:, 0]] - s[pairs[:, 1]]) > 2 * p.w]
    clear = np.linalg.norm(d[pairs[:, 0]] - d[pairs[:, 1]], axis=1).min() if len(pairs) else np.inf
    assert LineString(poly).is_simple
    assert clear >= (1 - p.eps) * p.w
    assert _circumradius(poly).min() >= p.w / 2 * 0.99
    beads = [LineString(lp.polyline()).buffer(p.w / 2) for lp in paths]
    assert beads[0].difference(geom.buffer(1.0)).area < 1.0
    assert beads[1].difference(beads[0].buffer(p.delta_mm)).area < 1.0
