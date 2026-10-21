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
    assert "*Entwurf" in text
    out.write_text(text.replace("*Entwurf", "EIGENER TEXT *Entwurf", 1), encoding="utf-8")
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


def test_roboterbericht_spezifischstes_muster(tmp_path):
    """Ein Szenario zu "fugenwand_raute" gehört nicht zu "fugenwand"; Freitext ordnet nichts zu."""
    mk = _load()
    rep = tmp_path / "report.json"
    entries = [
        {"name": "S4_muster_fugenwand_raute", "feasible": False, "note": "zwei schalen, fugenwand"},
        {"name": "S4_muster_fugenwand", "feasible": True, "vertical_layer_changes": 3},
    ]
    rep.write_text(json.dumps({"scenarios": entries}), encoding="utf-8")
    known = ["schalen", "fugenwand", "fugenwand_raute"]
    loaded = mk.load_robot_report(rep)
    fw = mk.robot_rows(loaded, "fugenwand", known)
    assert [r["label"] for r in fw] == ["S4_muster_fugenwand"]
    assert fw[0]["vertical"] == "3"  # Anzahl, kein Prozentwert
    raute = mk.robot_rows(loaded, "fugenwand_raute", known)
    assert [r["label"] for r in raute] == ["S4_muster_fugenwand_raute"]
    assert mk.robot_rows(loaded, "schalen", known) == []


def test_senkrechter_schichtwechsel_kein_nachteil():
    """preview() meldet einen senkrechten Wechsel als "vertical"; das ist kein Nachteil."""
    mk = _load()
    r = mk.measure_one(mk.load_preset(mk.CORE_PRESETS / "sinus.json"), "600x200")
    assert r["layer_change"] == "vertical"
    _, cons = mk.pros_cons({"600x200": r}, {}, ["600x200"])
    assert not any("Schichtwechsel" in c for c in cons)
    _, cons = mk.pros_cons({"600x200": dict(r, layer_change="diagonal")}, {}, ["600x200"])
    assert any("Schichtwechsel nicht überall senkrecht (diagonal)" in c for c in cons)


def test_saetze_enden_mit_punkt(tmp_path):
    """Dezimalkomma nur in Zahlen: Satzpunkte und Listennummern ("1.") bleiben Punkte."""
    mk = _load()
    assert mk.main(_args(tmp_path)) == 0
    text = (tmp_path / "katalog.md").read_text(encoding="utf-8")
    assert "1. **sinus**" in text
    bullets = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert bullets and all(not ln.endswith(",") for ln in bullets)
    assert any("Material 1,21- bis 1,21-fach gegenüber „schalen“." in ln for ln in bullets)


def test_katalogzahlen_unabhaengig_nachgerechnet():
    """Pfadlänge, Zeit und Material aus den rohen Pfadpunkten (Polylinie samt Verbindern)."""
    import numpy as np

    mk = _load()
    for name in ("sinus", "fugenwand"):
        r = mk.measure_one(mk.load_preset(mk.CORE_PRESETS / f"{name}.json"), "600x200")
        pts = np.array([p for path in r["data"]["paths"] for s in path["segments"] for p in s["points"]])
        length = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
        assert abs(length - r["path_length_mm"]) < 0.5
        assert abs(length / 100.0 - r["print_time_s"]) < 0.01
        material = length * 30.0 * 10.0 / 1e6 / 0.6  # l je m Wand und Schicht
        assert abs(material - r["material_l_per_m_layer"]) < 1e-3
