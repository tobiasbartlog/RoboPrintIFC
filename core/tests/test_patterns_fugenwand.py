"""Musterfamilie Fugenwand (Sollbruchstellen, Nutzer-Nachtrag 18:20): M1–M7 mit patterns/metrics.py
für alle Varianten und Dicken, Topologie, Einteilung, Kontakte, Naht, Rückfälle, Presets."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon, box

from roboprint import patterns as pt
from roboprint.patterns.families import _fugenwand_geom as fg
from roboprint.patterns.families import fugenwand as fw
from roboprint.patterns.preview import params_for

ROOT = Path(__file__).resolve().parents[2]
DOC_PRESETS = ROOT / "docs" / "muster" / "presets"
CORE_PRESET = Path(pt.__file__).parent / "presets" / "fugenwand.json"

VARIANTS = {
    "a_gurt_gespiegelt": {"belt": True, "back_offset": "gespiegelt"},
    "b_raute": {"belt": False, "back_offset": "versetzt"},
    "c_gurt_versetzt": {"belt": True, "back_offset": "versetzt"},
}


def _sections(length, thickness, n=4):
    g = box(-length / 2, -thickness / 2, length / 2, thickness / 2)
    return {L: g for L in range(n)}


def _plan(length, thickness, n=4, **kw):
    sec = _sections(length, thickness, n)
    p = params_for("fugenwand", **kw)
    return sec, p, pt.plan_pattern(sec, p)


def _assert_valid(sec, p, paths):
    """M1–M7 ohne Fehler, ein geschlossener Strang je Schicht, senkrechter Schichtwechsel."""
    rep = pt.measure(paths, sec, p)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    assert [lp.layer for lp in paths] == sorted(sec)  # M1: ein Strang je Schicht und Insel
    for lp in paths:
        assert lp.closed  # geschlossener Zug, Anfang = Ende
        assert all(np.allclose(a, b) for a, b in lp.connectors())  # Verbinder Länge 0
        assert LineString(lp.polyline()).is_simple  # M2: keine Kreuzung (exakt)
        assert "pattern_fallback" not in lp.meta
    assert all(c["status"] == "vertical" and c["distance_mm"] == 0.0 for c in rep.layer_changes)  # M4
    for m in rep.paths:
        assert m.min_clearance_mm >= (1 - p.eps) * p.w - 1e-6  # M2: kein Doppelmaterial
        assert m.min_radius_mm >= 0.95 * p.w / 2  # M6 hart
        assert m.max_chord_error_mm <= p.chord_tol_mm + 0.05  # M6 Sehnenfehler
    rules_warned = {v.rule for v in rep.violations if v.severity == "warn"}
    assert rules_warned <= {"M6"}, rules_warned  # Naht (M4) frei, Kontakte (M7) gemessen
    return rep


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("thickness", [200.0, 300.0, 365.0])
def test_variants_valid_m1_m7(variant, thickness):
    sec, p, paths = _plan(600.0, thickness, **VARIANTS[variant])
    rep = _assert_valid(sec, p, paths)
    lp = paths[0]
    kinds = {s.kind for s in lp.segments}
    assert {"outfill", "web"} <= kinds and kinds <= {"outfill", "web", "infill"}
    assert ("infill" in kinds) == VARIANTS[variant]["belt"]
    m = rep.paths[0]
    by_kind = {c.kind for c in m.contacts}
    assert {"joint", "node"} <= by_kind  # Fugen und Knoten berühren sich
    # Fugenkontakt: Mittellinienabstand in [(1 − ε)·w, w + tol] (stumpf, keine Kreuzung)
    for c in m.contacts:
        assert (1 - p.eps) * p.w <= c.distance_mm <= p.w + p.contact_tol_mm
    # Naht im Wandinneren: Raupe am Anfang weit weg von Außen- und Stoßflächen
    clr = pt.face_clearance(lp.start[None, :], sec[0], sec[0].bounds, p.w)[0]
    assert clr > p.w
    # alternate: Schicht 1 ist die exakte Umkehrung von Schicht 0
    a, b = paths[0].polyline(), paths[1].polyline()
    assert np.array_equal(a[::-1], b)


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("length", [300.0, 450.0, 750.0, 1200.0])
def test_lengths_300_to_1200(variant, length):
    sec, p, paths = _plan(length, 300.0, n=2, **VARIANTS[variant])
    _assert_valid(sec, p, paths)
    fit = paths[0].meta["fit"]
    assert fit["count"] * fit["length_mm"] == pytest.approx(length, abs=1e-6)


def test_fit_to_length_and_actual_lengths_in_meta():
    sec, p, paths = _plan(1000.0, 300.0, n=2, belt=False, field_length_mm=300.0)
    meta = paths[0].meta
    assert meta["fit"]["count"] == 3 and meta["field_length_mm"] == pytest.approx(1000 / 3, abs=1e-3)
    assert meta["joints_front_x"] == pytest.approx([-500 + 1000 / 3, -500 + 2000 / 3])
    # Rückseite um eine halbe Teilung versetzt
    assert meta["joints_back_x"][0] == pytest.approx(-500 + 500 / 3)
    rep = pt.measure(paths, sec, p)
    # gemessene Fugen liegen an den geplanten Stellen, Fugenabstand = Feldlänge
    m = rep.paths[0]
    assert m.joint_spacing_mm and all(s == pytest.approx(1000 / 3, abs=1.0) for s in m.joint_spacing_mm)
    xs = sorted(round(x) for x in m.joint_x_mm)
    planned = sorted(round(x) for x in meta["joints_front_x"] + meta["joints_back_x"])
    assert xs == planned


def test_topology_rautenkette_alternates_front_back():
    """Ohne Gurt hängen die Rauten abwechselnd an Vorder- und Rückseite; die Knoten liegen in der
    Wandmitte, je eine Raute links und rechts (ein Kontaktpaar, keine Kreuzung)."""
    sec, p, paths = _plan(1200.0, 365.0, n=2, belt=False)
    meta = paths[0].meta
    front, back = meta["joints_front_x"], meta["joints_back_x"]
    allj = sorted([(x, "f") for x in front] + [(x, "b") for x in back])
    assert all(a[1] != b[1] for a, b in zip(allj[:-1], allj[1:], strict=True))
    rep = pt.measure(paths, sec, p)
    nodes = [c for c in rep.paths[0].contacts if c.kind == "node"]
    assert len(nodes) == len(meta["nodes_x"])
    assert all(abs(c.at[1]) < p.w / 2 for c in nodes)  # Wandmitte


def test_mirrored_without_belt_builds_rautenkette_with_note():
    sec, p, paths = _plan(600.0, 300.0, belt=False, back_offset="gespiegelt")
    assert "unmöglich" in paths[0].meta["note"]
    _assert_valid(sec, p, paths)


def test_belt_variant_double_belt_touches():
    sec, p, paths = _plan(1200.0, 365.0, n=2, belt=True, back_offset="gespiegelt")
    rep = _assert_valid(sec, p, paths)
    belts = [s for s in paths[0].segments if s.kind == "infill"]
    ys = sorted({round(float(y), 3) for s in belts for y in s.points[:, 1]})
    assert ys == pytest.approx([-p.w / 2 + 0.5, p.w / 2 - 0.5])  # y_m ∓ δ/2
    node = [c for c in rep.paths[0].contacts if c.kind == "node"]
    assert sum(c.length_mm for c in node) > 600  # Doppelgurt berührt sich auf ganzer Länge


def test_joint_gap_opens_joint():
    sec, p, paths = _plan(1000.0, 300.0, n=2, belt=False, joint_gap_mm=5.0)
    rep = _assert_valid(sec, p, paths)
    assert paths[0].meta["joint_distance_mm"] == pytest.approx(35.0)
    assert not [c for c in rep.paths[0].contacts if c.kind == "joint"]


@pytest.mark.parametrize("key", ["joint_contact_mm", "node_length_mm", "apex_length_mm"])
def test_contact_lengths(key):
    base = _plan(1000.0, 300.0, n=2, belt=False)
    sec, p, paths = _plan(1000.0, 300.0, n=2, belt=False, **{key: 40.0})
    rep = _assert_valid(sec, p, paths)
    kind = {"joint_contact_mm": "joint", "node_length_mm": "node", "apex_length_mm": "shell"}[key]
    longer = sum(c.length_mm for c in rep.paths[0].contacts if c.kind == kind)
    rep0 = pt.measure(base[2], base[0], base[1])
    shorter = sum(c.length_mm for c in rep0.paths[0].contacts if c.kind == kind)
    n = len([c for c in paths[0].contacts if c.kind == kind])  # deklarierte Kontakte dieser Art
    assert n and longer >= shorter + 0.9 * 40.0 * n


def test_web_angle_sets_field_length():
    sec, p, paths = _plan(1200.0, 365.0, n=2, belt=True, back_offset="gespiegelt", web_angle_deg=45.0)
    meta = paths[0].meta
    assert meta["web_angle_reached_deg"] == pytest.approx(45.0, abs=0.5)
    assert meta["field_length_mm"] < 300.0
    _assert_valid(sec, p, paths)


def test_radius_steps_down_for_thin_wall():
    """Gurt bei 200 mm: Haken mit r = w passen nicht (Knotenhaken säße auf dem Feld,
    d_min = w + 2·0,85·w + 4·r + δ = 230 mm). r wird bis ≥ w/2 verkleinert, nur M6-Warnungen."""
    sec, p, paths = _plan(600.0, 200.0, belt=True, back_offset="gespiegelt")
    meta = paths[0].meta
    assert p.w / 2 <= meta["hook_radius_mm"] < p.w
    assert "Hakenradius" in meta["adjusted"]
    rep = _assert_valid(sec, p, paths)
    assert any(v.rule == "M6" and v.severity == "warn" for v in rep.violations)


def test_too_thin_wall_falls_back_to_shells():
    sec, p, paths = _plan(600.0, 150.0, belt=True)
    assert "nicht baubar" in paths[0].meta["pattern_fallback"]
    assert pt.measure(paths, sec, p).ok


def test_rautenkette_thin_wall_limit():
    """Rautenkette geht bis 120 mm (= 4·w) mit Haken r = w/2; darunter Rückfall."""
    sec, p, paths = _plan(1200.0, 120.0, n=2, belt=False)
    assert paths[0].meta["hook_radius_mm"] == pytest.approx(15.0)
    _assert_valid(sec, p, paths)
    sec, p, paths = _plan(1200.0, 110.0, n=2, belt=False)
    assert "pattern_fallback" in paths[0].meta


def test_non_rectangular_section_falls_back():
    lsec = Polygon([(0, 0), (600, 0), (600, 200), (200, 200), (200, 500), (0, 500)])
    sec = {L: lsec for L in range(2)}
    p = params_for("fugenwand")
    paths = pt.plan_pattern(sec, p)
    assert "kein Rechteck" in paths[0].meta["pattern_fallback"]
    assert pt.measure(paths, sec, p).ok


def test_two_islands_opening():
    g = MultiPolygon([box(-600, -100, -150, 100), box(150, -100, 600, 100)])
    sec = {L: g for L in range(2)}
    p = params_for("fugenwand", belt=False)
    paths = pt.plan_pattern(sec, p)
    assert [(lp.layer, lp.island) for lp in paths] == [(0, 0), (0, 1), (1, 1), (1, 0)]
    rep = pt.measure(paths, sec, p)
    assert rep.ok, [v.to_dict() for v in rep.errors]
    assert all("pattern_fallback" not in lp.meta for lp in paths)


def test_segment_kinds_and_shell_index():
    sec, p, paths = _plan(1000.0, 365.0, n=1, belt=True, back_offset="gespiegelt")
    for s in paths[0].segments:
        assert s.shell == (0 if s.kind == "outfill" else p.shells)
    # Schichtpfad beginnt und endet auf dem Gurt (Naht im Wandinneren)
    assert paths[0].segments[0].kind == "infill" and paths[0].segments[-1].kind == "infill"


def test_declared_contacts_reference_segments():
    _, _, paths = _plan(1000.0, 300.0, n=1, belt=False)
    lp = paths[0]
    assert lp.contacts
    for c in lp.contacts:
        i, j = c.segments
        assert 0 <= i <= j < len(lp.segments)


def test_tangent_and_geometry_errors():
    a = fg.Pulley(0.0, 0.0, 10.0, +1, "web")
    b = fg.Pulley(15.0, 0.0, 10.0, -1, "web")
    with pytest.raises(fg.GeometryError):
        fg.tangent(a, b)  # innere Tangente bei überlappenden Kreisen
    c = fg.Pulley(100.0, 0.0, 10.0, +1, "web")
    s, e = fg.tangent(a, c)  # äußere Tangente unten (gegen den Uhrzeigersinn: unten nach +x)
    assert s == pytest.approx([0.0, -10.0]) and e == pytest.approx([100.0, -10.0])
    pcs = fg.loop_pieces([a, c], ["web", "outfill"], 0.5, 20.0)
    pl = np.vstack([pc.points for pc in pcs])
    assert LineString(pl).is_simple and pl[:, 1].max() == pytest.approx(10.0)


def test_check_loop_detects_crossing_and_near_miss():
    sq = np.array([[0, 0], [200, 200], [200, 0], [0, 200], [0, 0]], float)
    assert fw.check_loop([("web", sq)], 30.0, 0.15) == "Selbstschnitt"
    near = np.array([[0, 0], [300, 0], [300, 20], [0, 20], [0, 0]], float)
    assert "zu nah" in fw.check_loop([("web", near)], 30.0, 0.15)


def test_catalog_entry_german_labels():
    entry = next(e for e in pt.catalog() if e["name"] == "fugenwand")
    assert entry["role"] == "full" and entry["family"] == "fugenwand"
    names = {p["name"] for p in entry["params"]}
    assert {
        "field_length_mm",
        "web_angle_deg",
        "belt",
        "back_offset",
        "joint_gap_mm",
        "node_length_mm",
        "hook_radius_mm",
    } <= names
    assert all(p["label"] for p in entry["params"])


@pytest.mark.parametrize("path", sorted(DOC_PRESETS.glob("fugenwand_*.json")) + [CORE_PRESET])
def test_presets_load_and_preview(path):
    preset = pt.load_preset(path)
    assert preset["pattern"] == "fugenwand"
    data = pt.preview(preset)
    assert data["ok"], [v for v in data["violations"] if v["severity"] == "error"]
    assert data["layer_change"]["status"] == "vertical"
    assert len(data["paths"]) == 1 and data["paths"][0]["meta"]["fit"]["count"] >= 1
    json.dumps(data)


def test_doc_presets_cover_variants():
    names = {p.stem for p in DOC_PRESETS.glob("fugenwand_*.json")}
    assert {"fugenwand_gurt", "fugenwand_raute", "fugenwand_versetzt"} <= names


def test_preview_svg_and_timing():
    spec = params_for("fugenwand", belt=False)
    pt.preview(spec, (600.0, 200.0))  # Aufwärmen (Import, Registry)
    t0 = time.perf_counter()
    data = pt.preview(spec, (600.0, 200.0))
    dt = time.perf_counter() - t0
    assert data["ok"]
    # Ziel < 100 ms je Schicht; die Vorschau rechnet zwei Schichten plus Messung (großzügig für CI)
    assert dt < 1.0
    svg = pt.preview_svg(data=data)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
