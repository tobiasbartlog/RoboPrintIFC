"""Testdruck-Programme (scripts/muster_testdrucke.py): Kennzahlen und abgelegte Programme."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "muster" / "testdrucke"


def _load():
    spec = importlib.util.spec_from_file_location(
        "muster_testdrucke", ROOT / "scripts" / "muster_testdrucke.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DRL_HEAD = """# RoboPrintIFC v2 - DRL-Programm
# Provisorische Werte (SPEC 10, A = Annahme, vom Nutzer zu bestaetigen; N = Nutzervorgabe):
#   A Schichthoehe h            10.0 mm
#   A t_tot                     3.0 s Pumpen-Vorlauf am Strangbeginn (provisorisch)
# Weitere Laufparameter: spot_x_mm=0.0
"""


def _run(tmp_path: Path) -> Path:
    """Ein Teil, zwei Schichten zu je einem offenen Ring (100 mm), Schichtwechsel als Z-Hub um 10 mm."""
    run = tmp_path / "run"
    pdir = run / "parts" / "box_01"
    pdir.mkdir(parents=True)
    params = {"bead_width_mm": 30.0, "layer_height_mm": 10.0, "t_tot_s": 3.0}
    (run / "summary.json").write_text(
        json.dumps({"params": params, "parts": [{"part_id": "box_01", "status": "machbar"}]}),
        encoding="utf-8",
    )
    rings = [
        {"layer": 0, "link_next": True, "waypoints": [[0, 0, 10], [100, 0, 10]]},
        {"layer": 1, "link_next": False, "waypoints": [[100, 0, 20], [0, 0, 20]]},
    ]
    (pdir / "toolpath.json").write_text(json.dumps({"rings": rings}), encoding="utf-8")
    tr = {
        "t_s": [0.0, 2.0, 3.0, 4.0, 4.1, 5.1, 5.5],
        "kind": ["transfer", "transfer", "print", "print", "link", "print", "lift"],
        "summary": {"dauer_s": 5.5},
    }
    (pdir / "trajectory.json").write_text(json.dumps(tr), encoding="utf-8")
    (pdir / "program.v2.drl").write_text(DRL_HEAD, encoding="utf-8")
    return run


def test_kennzahlen_mit_hub_und_vorlauf(tmp_path):
    mt = _load()
    x = mt.run_extras(_run(tmp_path))
    # 2 x 100 mm Ringe + 10 mm Z-Hub (Pumpe läuft, fördert Material)
    assert x["path_length_m"] == pytest.approx(0.210)
    assert x["material_l"] == pytest.approx(round(30 * 10 * 210 / 1e6, 2))
    assert x["strands"] == 1
    # Trajektorie 5,5 s plus wait(t_tot) = 3 s je Strang (steht im DRL, nicht in der Trajektorie)
    assert x["trajectory_time_s"] == pytest.approx(5.5)
    assert x["total_time_s"] == pytest.approx(8.5)
    assert x["print_time_pump_s"] == pytest.approx(3.1)
    assert x["drl_assumptions"] == [
        "   A Schichthoehe h            10.0 mm",
        "   A t_tot                     3.0 s Pumpen-Vorlauf am Strangbeginn (provisorisch)",
    ]


def test_zwei_straenge_zwei_vorlaeufe(tmp_path):
    mt = _load()
    run = _run(tmp_path)
    tp = run / "parts" / "box_01" / "toolpath.json"
    d = json.loads(tp.read_text(encoding="utf-8"))
    d["rings"][0]["link_next"] = False
    tp.write_text(json.dumps(d), encoding="utf-8")
    x = mt.run_extras(run)
    assert x["strands"] == 2
    assert x["total_time_s"] == pytest.approx(5.5 + 2 * 3.0)
    assert x["path_length_m"] == pytest.approx(0.200)


def test_kein_programm_ohne_gruene_pruefung():
    mt = _load()
    t = mt.TESTS[0]
    entry = {"feasible": False, "verdict": "nicht machbar (unerwartet)", "g3": "rot", "g5": "gruen"}
    assert not mt.published(entry, {"total_time_s": 1.0})
    assert not mt.published({"feasible": True}, None)  # mehrteilig: keine Kennzahlen, kein Programm
    text = mt.part_readme(t, entry, None, None, "2026-10-20")
    assert "Kein Programm" in text and "program.v2.drl" not in text


def test_g3_zeile_ohne_widerspruch():
    mt = _load()
    assert "grün außer Abdeckung (min. 64,6 % < 95 %" in mt.g3_line(
        {"abdeckung": "einwand", "abdeckung_min": 0.646}
    )
    ok = mt.g3_line({"abdeckung": "gruen", "abdeckung_min": 0.953})
    assert "außer" not in ok and "95,3 %" in ok


def _abgelegt() -> list[Path]:
    return sorted(p.parent for p in DOCS.glob("*/program.v2.drl"))


@pytest.mark.skipif(not (DOCS / "testdrucke.json").exists(), reason="keine Testdrucke abgelegt")
def test_abgelegte_programme_sind_geprueft():
    """Jedes abgelegte Programm: machbar, G3/G5/M1–M7 grün, Standard-Druckplatz, Kopf mit A-Werten."""
    data = json.loads((DOCS / "testdrucke.json").read_text(encoding="utf-8"))
    by = {t["name"]: t for t in data["tests"]}
    folders = _abgelegt()
    assert folders
    for f in folders:
        t = by[f.name]
        e = t["entry"]
        assert e["feasible"] and e["g3"] == e["g5"] == e["muster"] == "gruen", f.name
        assert e["metrics"]["machbar"] and e["metrics"]["n_parts"] == 1, f.name
        assert t["size_mm"][2] == 100, f.name
        sc = json.loads((f / "scenario.json").read_text(encoding="utf-8"))
        assert sc["source"]["size_mm"] == t["size_mm"], f.name
        for d in ("v2", "v3"):
            head = (f / f"program.{d}.drl").read_text(encoding="utf-8")[:6000]
            assert f"Szenario: testdruck_{f.name}" in head
            assert "Trockenlauf mit reduzierter Geschwindigkeit" in head
            assert re.search(r"spot_x_mm=0\.0, spot_y_mm=-50\.0", head), f.name
            assert "#   A Strangbreite w" in head and "#   A t_tot" in head
        readme = (f / "README.md").read_text(encoding="utf-8")
        assert "Trockenlauf" in readme and "Material" in readme and "Druckzeit" in readme
