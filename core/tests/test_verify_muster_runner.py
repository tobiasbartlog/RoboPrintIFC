"""Musterrunner (scripts/verify_muster.py): grün nur bei echtem Grün.

Geprüft ohne Roboterlauf: Prüferberichte zählen nur frisch und passend zum Exitcode, das Muster
des Szenarios muss im Toolpath stehen, ein abgebrochener Prüfer macht kein "belegt nicht machbar".
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCEN = ROOT / "docs" / "muster" / "szenarien"


@pytest.fixture()
def vm():
    spec = importlib.util.spec_from_file_location(
        "verify_muster_runner", ROOT / "scripts" / "verify_muster.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def out_dir(vm, monkeypatch):
    out = ROOT / "runs" / f"_test_verify_muster_{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    monkeypatch.setattr(vm, "OUT", out)
    yield out
    shutil.rmtree(out, ignore_errors=True)


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _fake_run(run: Path, pattern: dict | None, kinds=("outer", "inner")) -> None:
    _write(run / "summary.json", {"parts": [{"part_id": "p1", "status": "machbar"}], "timings_s": {}})
    rings = [{"layer": 0, "kind": k, "link_next": True, "waypoints": [[0, 0, 10], [1, 0, 10]]} for k in kinds]
    tp = {"rings": rings}
    if pattern is not None:
        tp["pattern"] = pattern
    _write(run / "parts" / "p1" / "toolpath.json", tp)


def _step(code: int) -> dict:
    return {"step": "x", "exit_code": code, "seconds": 0.0, "tail": ""}


COV = "p1: Abdeckung < 95 %: 3 Verstoesse, z. B. Schicht 0: 94.4 %"


def test_check_run_only_coverage_is_einwand(vm, tmp_path):
    _write(tmp_path / "check.json", {"passed": False, "errors": [COV], "parts": {}})
    r = vm.check_run_result(tmp_path, _step(1))
    assert r["status"] == "gruen" and r["abdeckung"] == "einwand"


@pytest.mark.parametrize(
    "check",
    [
        {"errors": ["p1: Abdeckung < 95 %: 1 Verstoesse, z. B. Schicht 9: 0.0 % von 81600 mm2"], "parts": {}},
        {"errors": [COV], "parts": {"p1": {"coverage_min": 0.31}}},
    ],
)
def test_check_run_coverage_below_floor_is_red(vm, tmp_path, check):
    """Gegenprüfung: Eine Abdeckung weit unter den musterbedingten 60–95 % (z. B. eine Schicht mit
    0 %) ist kein Einwand, sondern rot (vorher pauschal Einwand und grün)."""
    _write(tmp_path / "check.json", {"passed": False, **check})
    r = vm.check_run_result(tmp_path, _step(1))
    assert r["status"] == "rot" and any("Untergrenze" in e for e in r["errors"]), r


def test_check_run_scenario_floor(vm, tmp_path):
    """O1 mit einer Schale je Seite deckt gewollt nur 53 % ab: Einwand mit Szenario-Untergrenze 0,5,
    sonst rot."""
    check = {"passed": False, "errors": [COV], "parts": {"p1": {"coverage_min": 0.533}}}
    _write(tmp_path / "check.json", check)
    assert vm.check_run_result(tmp_path, _step(1))["status"] == "rot"
    r = vm.check_run_result(tmp_path, _step(1), 0.5)
    assert r["status"] == "gruen" and r["abdeckung"] == "einwand", r


def test_check_run_hard_error_is_red(vm, tmp_path):
    _write(tmp_path / "check.json", {"passed": False, "errors": [COV, "p1: 2 collision, 0 unreachable"]})
    assert vm.check_run_result(tmp_path, _step(1))["status"] == "rot"


@pytest.mark.parametrize("code", [-1, 2, 3])
def test_check_run_exitcode_must_match_report(vm, tmp_path, code):
    # z. B. Zeitlimit (-1) oder Aufruffehler (2) neben einem gruenen Bericht
    _write(tmp_path / "check.json", {"passed": True, "errors": []})
    assert vm.check_run_result(tmp_path, _step(code))["status"] == "rot"


def test_check_run_exit1_without_errors_is_red(vm, tmp_path):
    _write(tmp_path / "check.json", {"passed": False, "errors": []})
    assert vm.check_run_result(tmp_path, _step(1))["status"] == "rot"


def test_muster_exit1_without_failed_rule_is_crash(vm, tmp_path):
    _write(tmp_path / "check_muster.json", {"passed": False, "parts": [{"failed_rules": []}], "errors": []})
    r = vm.muster_result(tmp_path, _step(1))
    assert r["status"] == "rot" and r["failed_rules"] == []


def test_muster_green_needs_exit0_and_passed(vm, tmp_path):
    _write(tmp_path / "check_muster.json", {"passed": True, "parts": [], "errors": []})
    assert vm.muster_result(tmp_path, _step(0))["status"] == "gruen"
    assert vm.muster_result(tmp_path, _step(-1))["status"] == "rot"


def test_pattern_check(vm, tmp_path):
    sc = json.loads((SCEN / "S4_muster_sinus.json").read_text(encoding="utf-8"))
    _fake_run(
        tmp_path,
        {"layer_order": "alternate", "infill": "sinus", "outfill": "none"},
        kinds=("outer", "inner", "infill"),
    )
    assert vm.pattern_check(tmp_path, sc)["status"] == "gruen"
    _fake_run(tmp_path, {"layer_order": "alternate", "infill": "sinus", "outfill": "none"})
    assert "weggelassen" in vm.pattern_check(tmp_path, sc)["errors"][0]  # Infill vom Kern entfallen
    _fake_run(tmp_path, None)  # Preset still verloren: Lauf ohne Muster
    assert vm.pattern_check(tmp_path, sc)["status"] == "rot"
    sch = json.loads((SCEN / "S4_muster_schalen_alternate.json").read_text(encoding="utf-8"))
    _fake_run(tmp_path, {"layer_order": "alternate", "infill": "none", "outfill": "none"})
    assert vm.pattern_check(tmp_path, sch)["status"] == "gruen"
    assert vm.pattern_check(tmp_path, {"params": {}})["status"] == "rot"


def test_every_scenario_names_a_readable_preset(vm):
    paths = vm.find_scenarios(None, False)
    assert len(paths) >= 2 and any(p.name.startswith("S5_") for p in paths)
    for p in paths:
        sc = json.loads(p.read_text(encoding="utf-8"))
        preset = json.loads((ROOT / sc["params"]["pattern_preset"]).read_text(encoding="utf-8"))
        assert preset.get("pattern"), p.name
        assert sc["expect"]["muster"]["preset"] == sc["params"]["pattern_preset"], p.name


def test_stale_reports_never_make_not_feasible_green(vm, out_dir, monkeypatch):
    """--no-run mit altem check_muster.json (M3 verletzt) und abstuerzendem Pruefer: rot."""
    path = SCEN / "S5_muster_oeffnung_fugenwand.json"
    sid = json.loads(path.read_text(encoding="utf-8"))["id"]
    run = out_dir / sid
    _fake_run(
        run, {"layer_order": "alternate", "infill": "none", "outfill": "fugenwand"}, kinds=("outfill", "web")
    )
    _write(run / "check.json", {"passed": True, "errors": [], "parts": {}})
    _write(run / "check_muster.json", {"passed": False, "errors": [], "parts": [{"failed_rules": ["M3"]}]})

    def crash(name, cmd, timeout_s, log):  # jeder Pruefer bricht ab, ohne Bericht zu schreiben
        return {"step": name, "exit_code": 1, "seconds": 0.0, "log": "", "tail": "Traceback"}

    monkeypatch.setattr(vm, "run_cmd", crash)
    e = vm.run_scenario(path, 1, no_run=True)
    assert e["status"] == "rot"
    assert not (run / "check_muster.json").exists()

    def ok(name, cmd, timeout_s, log):  # Pruefer laufen und schreiben frische Berichte
        if name == "check_run":
            _write(run / "check.json", {"passed": True, "errors": [], "parts": {}})
            return _step(0)
        if name == "verify_muster":
            _write(
                run / "check_muster.json",
                {"passed": False, "errors": [], "parts": [{"failed_rules": ["M3"]}]},
            )
            return _step(1)
        return _step(0)

    monkeypatch.setattr(vm, "run_cmd", ok)
    assert vm.run_scenario(path, 1, no_run=True)["status"] == "gruen"
    _fake_run(run, None)  # gleicher Befund, aber Muster nicht angewendet: rot
    assert vm.run_scenario(path, 1, no_run=True)["status"] == "rot"


def test_s5_ifc_is_deterministic_wall_with_one_opening(tmp_path):
    """S5: Generator bitgleich zur eingecheckten Datei, eine Wand mit genau einem Fenster."""
    from roboprint.ifc import read_walls

    spec = importlib.util.spec_from_file_location("muster_s5_ifc", ROOT / "scripts" / "muster_s5_ifc.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a, b = mod.build(tmp_path / "a.ifc"), mod.build(tmp_path / "b.ifc")
    committed = SCEN / "S5_fensterwand.ifc"
    assert a.read_bytes() == b.read_bytes() == committed.read_bytes()
    (wall,) = read_walls(committed)
    assert len(wall.openings) == 1
    o = wall.openings[0]
    assert (o.x0, o.x1, o.z0, o.z1) == pytest.approx((180.0, 420.0, 150.0, 400.0))
    assert wall.volume_mm3 == pytest.approx(600 * 200 * 400 - 240 * 250 * 200)


def test_s6_whole_ifc_scenario_is_found_but_not_fast(vm):
    """S6 (ganze S2-IFC mit Zerlegung und Rautenkette) gehört zum vollen Lauf, nicht zu --fast."""
    full = [p.name for p in vm.find_scenarios(None, False)]
    fast = [p.name for p in vm.find_scenarios(None, True)]
    assert "S6_muster_s2_raute.json" in full
    assert "S6_muster_s2_raute.json" not in fast
    last_s5 = max(i for i, n in enumerate(full) if n.startswith("S5_"))
    assert full.index("S6_muster_s2_raute.json") > last_s5
    sc = json.loads((SCEN / "S6_muster_s2_raute.json").read_text(encoding="utf-8"))
    assert sc["decompose"] is True and sc["source"]["path"] == "examples/Building-Architecture.ifc"
    assert sc["limits"]["wall_time_s"] == 1800  # G7-Grenze von S2
    assert json.loads(sc["params"]["pattern_params"]) == {"field_length_mm": 225.0}


def test_s6_report_counts_match_strands_and_beleg():
    """S2-RAUTENKETTE.md und S6-Beleg zählen die Teile wie der Prüferbericht: 152 Module mit vollem
    Querschnitt und 20 Kopfmodule, zusammen 172 (vorher stand dort 150/22). Nach dem Fix „Fugenwand an
    Abschrägungen“ ist in den Kopfmodulen nur M1 rot (oberste Schichten dünner als w)."""
    doc = (ROOT / "docs" / "muster" / "S2-RAUTENKETTE.md").read_text(encoding="utf-8")
    green = int(re.search(r"Die (\d+) Module mit\s+vollem Querschnitt", doc).group(1))
    red = int(re.search(r"Die (\d+) Kopfmodule", doc).group(1))
    assert (green, red) == (152, 20) and green + red == 172
    sc = json.loads((SCEN / "S6_muster_s2_raute.json").read_text(encoding="utf-8"))
    muster = sc["expect"]["muster"]
    assert f"Die {red} Kopfmodule" in muster["beleg"] and "172 Teile" in muster["beleg"]
    assert muster["machbar"] is False and muster["erwartete_regeln"] == ["M1"]