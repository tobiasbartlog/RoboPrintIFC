"""Selbstpruefungen (roboprint.selfcheck) mit manipulierten Mini-Laeufen und die gemeinsame
Geschwindigkeitsquelle von timing und drl (roboprint.params).

Vorlagen der Manipulationen: experiments/gegenpruefung/manipulationen.py (Gegenpruefung A2.4).
Der Mini-Lauf stammt aus verify/oracle/minirun.py (Pinocchio, ohne roboprint gebaut).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

minirun = pytest.importorskip("verify.oracle.minirun")
manip = pytest.importorskip("experiments.gegenpruefung.manipulationen")

from roboprint import drl, selfcheck  # noqa: E402
from roboprint import params as speeds  # noqa: E402
from roboprint.contracts import Trajectory, load_json  # noqa: E402
from roboprint.timing import TimingParams, time_parametrize  # noqa: E402

PART = "box_0"


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _save(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj), encoding="utf-8")


def _checks(run: Path) -> set[str]:
    v = selfcheck.check_part_dir(run / "parts" / PART, run / "scenario.json")
    return {x.check for x in v}


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("selfcheck") / "base"
    minirun.build(d)
    return d


@pytest.fixture
def copy(base: Path, tmp_path: Path) -> Path:
    d = tmp_path / "run"
    shutil.copytree(base, d)
    return d


def test_basislauf_besteht(base: Path) -> None:
    assert _checks(base) == set()


def test_a_schichtreihenfolge(tmp_path: Path) -> None:
    d = tmp_path / "m4"
    manip.build_reversed_layers(d)
    assert "a" in _checks(d)


def test_b_travel_durch_druckstand(tmp_path: Path) -> None:
    d = tmp_path / "m7"
    manip.build_travel_through_print(d)
    assert "b" in _checks(d)


def test_b_lower_endet_nicht_ueber_ringstart(copy: Path) -> None:
    p = copy / "parts" / PART / "trajectory.json"
    tr = _load(p)
    last = max(i for i, k in enumerate(tr["kind"]) if k == "lower")
    tr["tcp"][last][2] += 15.0
    _save(p, tr)
    assert "b" in _checks(copy)


def test_c_teil_ueber_tischkante(tmp_path: Path) -> None:
    d = tmp_path / "m5"
    minirun.build(d, center=(780.0, 300.0))
    assert "c" in _checks(d)


def test_d_ring_ausserhalb_des_teils(tmp_path: Path) -> None:
    d = tmp_path / "m6"
    manip.build_extra_outer_ring(d)
    assert "d" in _checks(d)


def test_e_kein_home_start(copy: Path) -> None:
    p = copy / "parts" / PART / "trajectory.json"
    tr = _load(p)
    kinds = tr["kind"]
    j = next(i for i in range(len(kinds)) if kinds[i] != "transfer") - 1
    for a in (
        "t_s",
        "q",
        "tcp",
        "layer",
        "ring",
        "kind",
        "branch",
        "status",
        "d_mm",
        "pair",
        "witness",
        "psi_rad",
    ):
        tr[a] = tr[a][j:]
    st = tr["status"]
    tr["summary"].update(
        n=len(st), n_ok=st.count("ok"), n_warn=st.count("warn"), n_collision=0, n_unreachable=0
    )
    _save(p, tr)
    assert "e" in _checks(copy)


def test_f_teilmasse_ungleich_szenario(copy: Path) -> None:
    sc = _load(copy / "scenario.json")
    sc["source"]["size_mm"] = [200.0, 100.0, 40.0]
    _save(copy / "scenario.json", sc)
    assert "f" in _checks(copy)


def test_apply_setzt_teil_nicht_machbar(base: Path) -> None:
    """Die Pipeline-Naht schreibt Ursache und Status in den Planungspfad."""
    from types import SimpleNamespace

    import trimesh

    from roboprint.planner import from_overrides

    d = base / "parts" / PART
    tr = load_json(d / "trajectory.json", Trajectory)
    tp = SimpleNamespace(**_load(d / "toolpath.json"))
    tp.rings = [SimpleNamespace(**r) for r in tp.rings]
    part = _load(d / "part.json")
    job = SimpleNamespace(mesh_P=trimesh.load(d / "part.stl", force="mesh"))
    pp = SimpleNamespace(T_WP=np.array(part["T_WP"]), path=SimpleNamespace(feasible=True, cause=None))
    scn = SimpleNamespace(source=SimpleNamespace(kind="box", size_mm=[200.0, 100.0, 40.0]))
    viol = selfcheck.apply(pp, job, tr, tp, from_overrides(None), scn)
    assert {v.check for v in viol} == {"f"}
    assert pp.path.feasible is False
    assert pp.path.cause["link"] == "Selbstpruefung"
    ok_scn = SimpleNamespace(source=SimpleNamespace(kind="box", size_mm=[200.0, 100.0, 20.0]))
    pp.path.feasible, pp.path.cause = True, None
    assert selfcheck.apply(pp, job, tr, tp, from_overrides(None), ok_scn) == []
    assert pp.path.feasible


# --------------------------------------------------------------------------- Geschwindigkeiten


def _drl_text(run: Path) -> str:
    pp = drl.load_planned_part(run / "parts" / PART)
    return drl.emit(pp, "v2", allow_infeasible=True)


def test_zeitachse_nutzt_drl_geschwindigkeiten(base: Path) -> None:
    """Das DRL kommandiert dieselben Geschwindigkeiten, die `timing` je Bewegungsart annimmt."""
    tr = _load(base / "parts" / PART / "trajectory.json")
    text = _drl_text(base)
    set_v = float(re.search(r"set_velx\(([\d.]+),", text).group(1))
    assert set_v == speeds.V_PRINT_MM_S
    for k in ("lift", "lower"):
        lines = [ln for ln in text.splitlines() if f"# {k}," in ln]
        assert lines
        vs = {float(re.search(r"vel=\[([\d.]+),", ln).group(1)) for ln in lines}
        assert vs == {speeds.V_TRAVEL_MM_S}
    for k in ("approach", "retract"):
        assert all("vel=" not in ln for ln in text.splitlines() if f"# {k}," in ln)
    P = np.array(tr["tcp"])[:, :3]
    kind = np.array(tr["kind"])
    # und die Zeitparametrierung selbst, mit den Standardwerten aus einer Quelle
    q = np.array(tr["q"])
    t2 = time_parametrize(q, P, tr["kind"], tr["ring"], TimingParams())
    v2 = np.r_[0.0, np.linalg.norm(np.diff(P, axis=0), axis=1) / np.maximum(np.diff(t2), 1e-9)]
    assert v2[kind == "approach"].max() <= speeds.V_PRINT_MM_S * 1.02
    assert v2[kind == "lift"].max() <= speeds.V_TRAVEL_MM_S * 1.02


def test_geschwindigkeiten_eine_quelle() -> None:
    tp, dp = TimingParams(), drl.DrlParams()
    for name in ("v_print_mm_s", "a_print_mm_s2", "v_travel_mm_s", "a_travel_mm_s2", "joint_speed_fraction"):
        assert getattr(tp, name) == getattr(dp, name)
    assert tp.joint_acc_factor == drl._JOINT_ACC_FACTOR
    from roboprint.planner import PlannerParams

    pl = PlannerParams()
    assert (pl.v_print_mm_s, pl.v_travel_mm_s, pl.joint_speed_fraction) == (
        tp.v_print_mm_s,
        tp.v_travel_mm_s,
        tp.joint_speed_fraction,
    )
