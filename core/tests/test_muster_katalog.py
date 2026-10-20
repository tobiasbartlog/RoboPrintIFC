"""Katalog-Generator (scripts/muster_katalog.py): läuft auf einem Preset, Ausgabe ist gültig."""

from __future__ import annotations

import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("muster_katalog", ROOT / "scripts" / "muster_katalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _args(tmp_path):
    return [
        "--out", str(tmp_path / "katalog.md"),
        "--images", str(tmp_path / "img"),
        "--presets", "sinus",
        "--sections", "600x200",
        "--report", str(tmp_path / "fehlt.json"),
    ]  # fmt: skip


def test_katalog_ein_preset(tmp_path):
    mk = _load()
    out = tmp_path / "katalog.md"
    assert mk.main(_args(tmp_path)) == 0
    text = out.read_text(encoding="utf-8")
    assert "KATALOG:VERGLEICH:BEGIN" in text and "KATALOG:DETAILS:END" in text
    assert "## Empfehlung" in text and "Entwurf" in text
    assert "machbar offen" in text  # kein Roboterbericht
    assert (tmp_path / "img" / "schalen_600x200.svg").exists()
    ET.fromstring((tmp_path / "img" / "sinus_600x200.svg").read_text(encoding="utf-8"))  # gültiges XML

    # Neu erzeugen: Text außerhalb der Marker bleibt erhalten
    out.write_text(text.replace("*Platzhalter", "EIGENER TEXT *Platzhalter"), encoding="utf-8")
    assert mk.main(_args(tmp_path)) == 0
    assert "EIGENER TEXT" in out.read_text(encoding="utf-8")


def test_roboterbericht_robust(tmp_path):
    mk = _load()
    rep = tmp_path / "report.json"
    entry = {
        "name": "S4_muster_sinus",
        "feasible": True,
        "metrics": {"d_min_mm": 12.5, "strands_per_layer": 1, "vertical_share": 1.0},
    }
    rep.write_text(json.dumps({"scenarios": [entry]}), encoding="utf-8")
    rows = mk.robot_rows(mk.load_robot_report(rep), "sinus")
    assert rows[0]["feasible"] == "ja" and rows[0]["d_min"] == "12,50" and rows[0]["vertical"] == "100 %"
    assert rows[0]["planner"] == "offen"
    rep.write_text("kaputt", encoding="utf-8")
    assert mk.load_robot_report(rep) == []
