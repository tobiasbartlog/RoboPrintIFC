"""`roboprint pattern-preview <preset.json> --svg <datei> [--json …] [--length --thickness --layer]`."""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from roboprint import patterns as pt
from roboprint.cli import main
from roboprint.contracts import PatternPreview

PRESET = Path(pt.__file__).parent / "presets" / "schalen.json"
CORE = Path(__file__).resolve().parents[1]


def test_svg_and_json_from_builtin_preset(tmp_path, capsys):
    svg, js = tmp_path / "out" / "schalen.svg", tmp_path / "out" / "schalen.json"
    rc = main(["pattern-preview", str(PRESET), "--svg", str(svg), "--json", str(js), "--layer", "1"])
    assert rc == 0
    root = ET.fromstring(svg.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["layer"] == 1 and data["next_layer"]["layer"] == 2 and data["ok"]
    # gleiches Format wie die API (ohne die nur dort ergänzten Felder fit/timing.api)
    PatternPreview.model_validate(data)
    out = capsys.readouterr().out
    assert "Pfad" in out and str(svg) in out


def test_length_and_thickness_override_the_preset_outline(tmp_path):
    js = tmp_path / "p.json"
    assert (
        main(["pattern-preview", str(PRESET), "--json", str(js), "--length", "1200", "--thickness", "365"])
        == 0
    )
    assert json.loads(js.read_text())["outline"]["bounds"] == [-600.0, -182.5, 600.0, 182.5]


def test_rule_errors_give_exit_1(tmp_path, capsys):
    preset = tmp_path / "same.json"
    pt.save_preset(preset, "Gleiche Richtung", "schalen", {"layer_order": "same"})
    svg = tmp_path / "same.svg"
    assert main(["pattern-preview", str(preset), "--svg", str(svg)]) == 1
    assert svg.is_file() and "#e03131" in svg.read_text()
    assert "M4" in capsys.readouterr().err


def test_invalid_input_gives_exit_2(tmp_path, capsys):
    assert main(["pattern-preview", str(tmp_path / "fehlt.json"), "--svg", str(tmp_path / "x.svg")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "x", "pattern": "gibt_es_nicht", "params": {}}))
    assert main(["pattern-preview", str(bad)]) == 2
    assert main(["pattern-preview", str(PRESET), "--length", "600"]) == 2
    assert main(["pattern-preview", str(PRESET), "--length", "-1", "--thickness", "200"]) == 2
    assert "Fehler" in capsys.readouterr().err


def test_module_entry_point(tmp_path):
    svg = tmp_path / "m.svg"
    r = subprocess.run(
        [sys.executable, "-m", "roboprint", "pattern-preview", str(PRESET), "--svg", str(svg)],
        cwd=CORE,
        env={"PYTHONPATH": str(CORE / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert svg.read_text().startswith("<svg")
