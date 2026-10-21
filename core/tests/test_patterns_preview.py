"""Vorschau (JSON, SVG), Presets, CLI-Hilfsfunktion und Laufzeit der Vorschau."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from roboprint import patterns as pt
from roboprint.patterns import cli_preview

PRESETS = Path(pt.__file__).parent / "presets"


def test_preview_json_structure():
    d = pt.preview(None, (600, 200), layer=2)
    json.dumps(d)  # JSON-fähig
    assert d["layer"] == 2 and d["next_layer"]["layer"] == 3 and d["ok"]
    path, nxt = d["paths"][0], d["next_layer"]["paths"][0]
    assert path["direction"] == "out_in" and nxt["direction"] == "in_out"
    assert nxt["start"] == path["end"] and d["layer_change"]["status"] == "vertical"
    seg = path["segments"][0]
    assert {"kind", "points", "start", "end", "start_dir", "end_dir", "arrows", "length_mm"} <= set(seg)
    assert seg["kind"] == "outer" and seg["arrows"]
    m = d["metrics"]
    for key in (
        "path_length_mm",
        "print_time_s",
        "material_l_per_m_layer",
        "contacts",
        "contact_length_mm",
        "joint_spacing_mm",
        "longest_straight_outer_mm",
        "min_radius_mm",
        "cells",
    ):
        assert key in m
    assert m["print_time_s"] == pytest.approx(m["path_length_mm"] / 100.0, abs=0.01)
    assert all({"kind", "at", "length_mm", "overlap_mm"} <= set(c) for c in d["contacts"])


def test_preview_outline_variants_and_violations_have_location():
    poly = {"polygon": [[0, 0], [600, 0], [600, 200], [200, 200], [200, 600], [0, 600]]}
    d = pt.preview({"shells": 2}, poly)
    assert d["ok"] and d["outline"]["bounds"] == [0.0, 0.0, 600.0, 600.0]
    d = pt.preview({"layer_order": "same"}, (600, 200))
    m4 = [v for v in d["violations"] if v["rule"] == "M4"]
    assert m4 and m4[0]["at"] is not None and not d["ok"]


def test_preview_runtime_below_100ms_per_layer():
    pt.preview(None, (600, 200))  # Aufwärmen (Import, Registry)
    best = min(_timed(lambda: pt.preview(None, (600, 200))) for _ in range(5))
    per_layer = best / 2  # Vorschau rechnet Schicht und Folgeschicht
    assert per_layer < 100.0, f"{per_layer:.1f} ms je Schicht"


def _timed(fn) -> float:
    t = time.perf_counter()
    fn()
    return (time.perf_counter() - t) * 1e3


def test_preview_svg_is_valid_and_marks_everything():
    svg = pt.preview_svg(None, (600, 200))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert svg.count("<polyline") >= 4 and "Start" in svg and "Ende" in svg and "Kontakt" in svg
    bad = pt.preview_svg({"layer_order": "same"}, (600, 200))
    assert "#e03131" in bad  # Verstoß rot


def test_presets_roundtrip_and_builtin(tmp_path):
    data = pt.load_preset(PRESETS / "schalen.json")
    assert data["pattern"] == "schalen" and pt.preset_params(data).outfill == "none"
    out = pt.save_preset(
        tmp_path / "x.json",
        "Test",
        "schalen",
        pt.PatternParams(shells=3),
        outline={"length_mm": 800, "thickness_mm": 300},
    )
    back = pt.load_preset(out)
    assert back["name"] == "Test" and pt.preset_params(back).shells == 3
    d = pt.preview(back)
    assert d["name"] == "Test" and d["outline"]["bounds"] == [-400.0, -150.0, 400.0, 150.0]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "x", "pattern": "gibt_es_nicht", "params": {}}))
    with pytest.raises(KeyError):
        pt.load_preset(bad)
    bad.write_text(json.dumps({"name": "x", "params": {}}))
    with pytest.raises(ValueError):
        pt.load_preset(bad)


def test_all_builtin_presets_load_and_preview():
    for f in sorted(PRESETS.glob("*.json")):
        d = pt.preview(pt.load_preset(f))
        assert d["paths"], f.name


def test_cli_preview_main(tmp_path, capsys):
    svg, js = tmp_path / "s.svg", tmp_path / "s.json"
    rc = cli_preview.main(PRESETS / "schalen.json", svg, layer=1, json_path=js)
    assert rc == 0 and svg.read_text().startswith("<svg")
    assert json.loads(js.read_text())["layer"] == 1
    assert "Pfad" in capsys.readouterr().out
