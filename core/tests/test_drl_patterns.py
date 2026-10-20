"""DRL mit Druckmustern (M3.2, SPEC §5.6, docs/doosan-drl.md): offene Ringe, Verbinder der Laenge 0,
senkrechter Schichtwechsel, ein Strang ueber alle Schichten.

Der Lauf entsteht ueber `run_scenario` (Quader 600 x 200 x 30 mm mit Fugenwand bzw. 300 x 200 x 30 mm
mit `layer_order = alternate`). Geprueft wird mit dem strengen Pruefer der Tests (`drl_checker`:
Befehle, Pumpe, Blending, Bahn) und direkt am Programmtext: Pumpe einmal an und aus, kein Halt im
Strang, radius <= min(r_blend, 1/2 angrenzende Segmente), kein Segment der Laenge ~0, `movesx` nur
mit <= 100 Punkten. Die posx-Pruefung des Pruefers braucht Pinocchio und wird sonst uebersprungen.
"""

from __future__ import annotations

import importlib.util
import json
import re

import numpy as np
import pytest

from drl_checker import check, run_program
from roboprint import drl
from roboprint.contracts import Toolpath, Trajectory, load_json

FUGENWAND = "core/src/roboprint/patterns/presets/fugenwand.json"
PUMP_ON = "set_analog_output(ch=1, val=5.000)"
PUMP_OFF = "set_analog_output(ch=1, val=0.0)"
HAS_PINOCCHIO = importlib.util.find_spec("pinocchio") is not None


def _scenario(size, params) -> dict:
    return {
        "schema_version": "1", "id": "T_muster_drl", "beschreibung": "Quader mit Druckmuster",
        "mode": "modul", "source": {"kind": "box", "size_mm": list(size)}, "decompose": False,
        "robot": "robots/doosan_m1013.json", "urdf": "third_party/doosan_m1013/urdf/m1013.white.urdf",
        "tool": "tools/30gut.json", "workstation": "workstations/doosantisch.json", "params": params,
        "planner_mode": "collision_aware", "expect": {"parts": "all_feasible"},
        "limits": {"wall_time_s": 180},
    }  # fmt: skip


def _run(tmp_path_factory, name, size, params):
    from roboprint.pipeline import run_scenario

    out = tmp_path_factory.mktemp(name)
    (out / "scen.json").write_text(json.dumps(_scenario(size, params)), encoding="utf-8")
    assert run_scenario(out / "scen.json", out / "run") == 0
    pdir = out / "run" / "parts" / "box_01"
    assert json.loads((pdir / "part.json").read_text(encoding="utf-8"))["status"] == "machbar"
    return pdir


@pytest.fixture(scope="module")
def fugenwand(tmp_path_factory):
    return _run(tmp_path_factory, "drl_fugenwand", (600, 200, 30), {"pattern_preset": FUGENWAND})


@pytest.fixture(scope="module")
def alternate(tmp_path_factory):
    return _run(tmp_path_factory, "drl_alternate", (300, 200, 30), {"layer_order": "alternate"})


def _text(pdir, dialect: str) -> str:
    return (pdir / f"program.{dialect}.drl").read_text(encoding="ascii")


@pytest.mark.parametrize("name", ["fugenwand", "alternate"])
@pytest.mark.parametrize("dialect", ["v2", "v3"])
def test_programm_besteht_strengen_pruefer(request, name, dialect) -> None:
    pdir = request.getfixturevalue(name)
    errs = check(_text(pdir, dialect), dialect, pdir)
    if not HAS_PINOCCHIO:  # nur die posx-FK-Pruefung braucht Pinocchio
        errs = [e for e in errs if "posx" not in e]
    assert errs == []


@pytest.mark.parametrize("name", ["fugenwand", "alternate"])
def test_ein_strang_pumpe_einmal_kein_halt(request, name) -> None:
    """Ein Strang ueber alle Ringe und Schichten: Pumpe einmal an (mit Vorlauf) und einmal aus;
    radius 0 nur am letzten Druck-movel; radius <= min(r_blend, 1/2 angrenzende Segmente)."""
    pdir = request.getfixturevalue(name)
    for dialect in ("v2", "v3"):
        text = _text(pdir, dialect)
        assert text.count(PUMP_ON) == 1
        assert sum(1 for ln in text.splitlines() if ln.strip().startswith("wait(")) == 1
        lines = [ln.strip() for ln in text.splitlines()]
        a = lines.index(PUMP_ON)
        b = next(i for i in range(a, len(lines)) if lines[i] == PUMP_OFF)
        strand = [ln for ln in lines[a:b] if ln.startswith("movel(")]
        radii = [float(re.search(r"radius=([0-9.]+)", s).group(1)) for s in strand]
        assert all(r > 0 for r in radii[:-1]) and radii[-1] == 0.0
        assert max(radii) <= 2.0


@pytest.mark.parametrize("name", ["fugenwand", "alternate"])
def test_keine_segmente_der_laenge_null_im_strang(request, name) -> None:
    """Verbinder der Laenge 0 fallen mit dem Ringende zusammen: Zwischen zwei Druckzielen liegt nie
    ein Segment < 0,01 mm (fake_drcf: MIN_SEGMENT_MM), und jedes Ziel hat radius <= 1/2 Segment."""
    pdir = request.getfixturevalue(name)
    text = _text(pdir, "v2")
    st = run_program(text, "v2")
    pts = [np.array(m.target.v[:3]) for m in st.motions]
    pump = [m.pump for m in st.motions]
    for k in range(1, len(pts)):
        if pump[k] and pump[k - 1]:
            assert np.linalg.norm(pts[k] - pts[k - 1]) >= 0.01
    for k in range(1, len(pts) - 1):
        r = st.motions[k].radius
        if r > 0:
            seg = min(np.linalg.norm(pts[k] - pts[k - 1]), np.linalg.norm(pts[k + 1] - pts[k]))
            assert r <= 0.5 * seg + 1e-6


def test_senkrechter_schichtwechsel_im_programm(alternate) -> None:
    """Der Schichtwechsel ist ein movel genau um h nach oben (gleiches x, y), der Ringkommentar
    nennt ihn; Verbinder der Laenge 0 in der Schicht sind als solche benannt."""
    pdir = alternate
    tp = load_json(pdir / "toolpath.json", Toolpath)
    text = _text(pdir, "v2")
    n_layers = 1 + max(r.layer for r in tp.rings)
    assert text.count("(ueber Verbinder, senkrecht, Z +10.0 mm)") == n_layers - 1
    same = sum(1 for r in range(1, len(tp.rings)) if tp.rings[r].layer == tp.rings[r - 1].layer)
    assert text.count("(ueber Verbinder, Laenge 0)") == same
    st = run_program(text, "v2")
    hubs = 0
    for k in range(1, len(st.motions)):
        d = np.array(st.motions[k].target.v[:3]) - np.array(st.motions[k - 1].target.v[:3])
        if st.motions[k].pump and st.motions[k - 1].pump and np.hypot(d[0], d[1]) < 1e-3 and d[2] > 0:
            hubs += 1
            assert d[2] == pytest.approx(10.0, abs=1e-3)
    assert hubs == n_layers - 1


def test_v3_movesx_nur_bis_100_punkte(alternate) -> None:
    """v3 mit `movesx`: Straenge mit Verbindern bleiben movel mit Blending; jeder Block <= 100 Punkte."""
    pp = drl.load_planned_part(alternate, drl.DrlParams(v3_movesx=True))
    text = drl.emit(pp, "v3")
    for block in re.findall(r"movesx\(\[(.*?)\]", text, flags=re.S):
        assert block.count("posx(") <= drl.MOVESX_MAX_POINTS
    tr = load_json(alternate / "trajectory.json", Trajectory)
    if "link" in tr.kind:  # ein Strang mit Verbindern: kein movesx
        assert "movesx(" not in text
    errs = check(text, "v3", alternate)
    assert [e for e in errs if HAS_PINOCCHIO or "posx" not in e] == []
