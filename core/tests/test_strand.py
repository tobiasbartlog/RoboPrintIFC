"""Strang mit Verbindern (SPEC §5.3, §5.5, Nutzerentscheidung 20.10.2026): Planer, Zeitachse,
Selbstpruefung. Ablaufregeln nach spec/ARTEFAKTE.md, ohne Pinocchio."""

from __future__ import annotations

import numpy as np
import pytest

from roboprint import export, frames, selfcheck
from roboprint.assets import load_tool, load_workstation
from roboprint.geometry import make_box
from roboprint.planner import PlannerParams, from_overrides, plan_part
from roboprint.planner.kin import Kin
from roboprint.planner.plan import PartPlanner
from roboprint.planner.result import IN_STRAND
from roboprint.slicer import to_toolpath
from roboprint.timing import TimingParams, time_parametrize

P = PlannerParams()
PL = frames.Placement(-500.0, -325.0, 0.0)
H = P.layer_height_mm


def _box(b: float, t: float, h: float):
    return make_box([b, t, h], origin=[-b / 2, -t / 2, 0.0])


def _segments(kind, ring) -> list[tuple[str, int, int, int]]:
    """(Art, Ring, erstes Sample, letztes Sample) je Abschnitt gleicher (Art, Ring)."""
    out: list[list] = []
    for i, (k, r) in enumerate(zip(kind, ring, strict=True)):
        if out and out[-1][0] == k and out[-1][1] == r:
            out[-1][3] = i
        else:
            out.append([k, int(r), i, i])
    return [tuple(s) for s in out]


def _strands(kind) -> list[np.ndarray]:
    """Indizes je Strang: zusammenhaengende approach/print/link/retract ohne Travel."""
    out: list[list[int]] = []
    prev = False
    for i, k in enumerate(kind):
        cur = k in IN_STRAND
        if cur and not prev:
            out.append([])
        if cur:
            out[-1].append(i)
        prev = cur
    return [np.array(x) for x in out]


def _plan(mesh, params: PlannerParams = P):
    pp = plan_part(mesh, "box", params, placement=PL)
    tr = export.trajectory(pp, Kin(load_workstation(), load_tool()), params)
    tp = to_toolpath(pp.sliced, pp.T_WP, "box")
    return pp, tr, tp


@pytest.fixture(scope="module")
def planned():
    mesh = _box(200, 100, 40)
    pp, tr, tp = _plan(mesh)
    return mesh, pp, tr, tp


# --------------------------------------------------------------------------- Planer


def test_quader_ist_ein_strang(planned) -> None:
    """Schalen- und Schichtverbinder: der ganze Quader ein Strang, Travel nur davor und danach."""
    _, pp, tr, tp = planned
    n = len(tp.rings)
    assert pp.path.feasible and n == 8
    assert [r.link_next for r in tp.rings] == [True] * (n - 1) + [False]
    segs = _segments(tr.kind, tr.ring)
    want = ["transfer", "lower", "approach", "print"] + ["link", "print"] * (n - 1) + ["retract", "lift"]
    assert [k for k, *_ in segs] == want
    assert [r for k, r, *_ in segs if k == "print"] == list(range(n))
    assert [r for k, r, *_ in segs if k == "link"] == list(range(1, n))
    assert len(_strands(tr.kind)) == 1


def test_verbinder_auf_der_geraden_im_zweig_und_mit_schichtregel(planned) -> None:
    _, _, tr, tp = planned
    pos = np.asarray(tr.tcp)[:, :3]
    for k, r, a, b in _segments(tr.kind, tr.ring):
        if k != "link":
            continue
        A = np.asarray(tp.rings[r - 1].waypoints[-1][:3])  # noqa: N806
        B = np.asarray(tp.rings[r].waypoints[0][:3])  # noqa: N806
        assert np.linalg.norm(pos[a - 1] - A) < 1e-3  # beginnt am Ende von Ring r - 1
        assert np.linalg.norm(pos[b] - B) < 1e-3  # endet am Start von Ring r
        ab = B - A
        t = np.clip((pos[a : b + 1] - A) @ ab / (ab @ ab), 0.0, 1.0)
        assert np.linalg.norm(pos[a : b + 1] - (A + t[:, None] * ab), axis=1).max() <= 0.5
        assert np.hypot(*ab[:2]) <= P.link_max_mm
        # k = Schicht des folgenden Rings; beim Schichtwechsel steigt der Verbinder um h
        assert set(tr.layer[a : b + 1]) == {tp.rings[r].layer}
        dz = tp.rings[r].layer - tp.rings[r - 1].layer
        assert pos[b, 2] - pos[a - 1, 2] == pytest.approx(dz * H, abs=1e-3)
    for idx in _strands(tr.kind):
        assert len(set(np.asarray(tr.branch)[idx].tolist())) == 1
    assert tr.summary.zweig_wechsel_in_ringen == 0


def test_pumpe_laeuft_im_strang_durch(planned) -> None:
    """Pumpe an genau bei print/link: ein Block, davor approach, danach retract; der Pumpen-Vorlauf
    t_tot steht einmal am Strangbeginn, sonst haelt der Roboter im Strang nicht."""
    _, _, tr, _ = planned
    on = np.array([k in ("print", "link") for k in tr.kind])
    starts = np.flatnonzero(on[1:] & ~on[:-1]) + 1
    ends = np.flatnonzero(on[:-1] & ~on[1:])
    assert len(starts) == len(ends) == 1
    assert tr.kind[starts[0] - 1] == "approach" and tr.kind[ends[0] + 1] == "retract"
    dt = np.diff(np.asarray(tr.t_s))
    big = np.flatnonzero(dt >= P.t_tot_s)
    assert big.tolist() == [starts[0] - 1]
    pos = np.asarray(tr.tcp)[:, :3]
    seg = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    inner = np.arange(starts[0] + 1, ends[0])  # Schritte i -> i + 1 im Strang nach dem Vorlauf
    assert (seg[inner] > 0).all()  # kein Stillstand im Strang


def test_strangbruch_fuehrt_zu_travel(monkeypatch, tmp_path) -> None:
    """Geht der Verbinder nach Ring 3 nicht, endet der Strang an Ring 2 (Abfahren, Abheben) und
    Ring 3 beginnt nach einem Travel einen neuen Strang; danach wird wieder verbunden. Das Programm
    schaltet die Pumpe je Strang einmal ein (mit Vorlauf) und einmal aus."""
    import json

    from roboprint.contracts import Toolpath, Trajectory, load_json
    from roboprint.pipeline import run_scenario

    orig = PartPlanner._link_motion

    def no_link_to_3(self, task, path, op, b):
        return None if task.index == 3 else orig(self, task, path, op, b)

    monkeypatch.setattr(PartPlanner, "_link_motion", no_link_to_3)
    scn = {
        "schema_version": "1", "id": "T_strangbruch", "beschreibung": "Quader 200 x 100 x 30 mm",
        "mode": "modul", "source": {"kind": "box", "size_mm": [200, 100, 30]}, "decompose": False,
        "robot": "robots/doosan_m1013.json", "urdf": "third_party/doosan_m1013/urdf/m1013.white.urdf",
        "tool": "tools/30gut.json", "workstation": "workstations/doosantisch.json", "params": {},
        "planner_mode": "collision_aware",
        "placement_override": {"x_mm": PL.x_mm, "y_mm": PL.y_mm, "yaw_deg": 0.0},
        "expect": {"parts": "all_feasible"}, "limits": {"wall_time_s": 180},
    }  # fmt: skip
    (tmp_path / "scen.json").write_text(json.dumps(scn), encoding="utf-8")
    assert run_scenario(tmp_path / "scen.json", tmp_path / "run") == 0
    pdir = tmp_path / "run" / "parts" / "box_01"
    tr = load_json(pdir / "trajectory.json", Trajectory)
    tp = load_json(pdir / "toolpath.json", Toolpath)
    assert json.loads((pdir / "part.json").read_text(encoding="utf-8"))["status"] == "machbar"
    segs = [(k, r) for k, r, *_ in _segments(tr.kind, tr.ring)]
    i = segs.index(("print", 2))
    assert segs[i + 1 : i + 8] == [
        ("retract", 2), ("lift", 2), ("transfer", 3), ("lower", 3), ("approach", 3), ("print", 3),
        ("link", 4),
    ]  # fmt: skip
    assert len(_strands(tr.kind)) == 2 and tp.rings[2].link_next  # erlaubt, aber nicht genutzt
    # Schichtregel am Bruch: lift nach Schicht L(2) + 1
    a = next(j for j, k in enumerate(tr.kind) if k == "lift")
    assert tr.layer[a] == tp.rings[2].layer + 1
    for d in ("v2", "v3"):
        text = (pdir / f"program.{d}.drl").read_text(encoding="ascii")
        assert text.count("set_analog_output(ch=1, val=5.000)") == 2
        assert sum(1 for ln in text.splitlines() if ln.strip().startswith("wait(")) == 2


def test_ohne_verbinder_alter_ablauf() -> None:
    """link_max_mm = 0: kein link_next, jeder Ring ein Strang mit eigenem Vorlauf (alter Ablauf)."""
    params = from_overrides({"link_max_mm": 0})
    pp, tr, tp = _plan(_box(200, 100, 20), params)
    n = len(tp.rings)
    assert not any(r.link_next for r in tp.rings) and "link" not in tr.kind
    assert len(_strands(tr.kind)) == n
    assert sum(1 for k, *_ in _segments(tr.kind, tr.ring) if k == "retract") == n
    assert int((np.diff(tr.t_s) >= params.t_tot_s).sum()) == n


def test_link_max_als_szenario_parameter() -> None:
    """Der Viewer sendet link_max_mm als Szenario-Override; er erreicht Slicer, summary und DRL-Kopf."""
    from roboprint import drl
    from roboprint.planner import slice_params

    p = from_overrides({"link_max_mm": 45})
    assert p.link_max_mm == 45.0 and slice_params(p).link_max_mm == 45.0
    assert p.as_summary()["link_max_mm"] == 45.0
    assert drl.DrlParams.from_params(p.as_summary()).link_max_mm == 45.0


def test_praefix_der_hoehensuche_endet_mit_strangende() -> None:
    """Ein Verbinder in die naechste Schicht: der abgeschnittene Plan endet trotzdem mit Abfahren und
    Abheben (Tail), und der oberste Ring hat im niedrigeren Teil keinen Verbinder."""
    from roboprint.planner import truncate_plan

    tall = plan_part(_box(200, 100, 40), "a", P, placement=PL)
    assert tall.path.tails
    cut = truncate_plan(tall, 2, P)
    assert cut.path.kind[-1] == "lift" and "retract" in cut.path.kind[-40:]
    assert not cut.sliced.rings[-1].link_next and cut.sliced.rings[0].link_next
    assert cut.path.feasible and len(_strands(cut.path.kind)) == 1


# --------------------------------------------------------------------------- Zeitachse


def _line_run(kinds_rings: list[tuple[str, int, int]]):
    """Gerade Bahn in x, je Eintrag (Art, Ring, Anzahl Samples) mit 2 mm Schritt; q fest."""
    kind, ring = [], []
    for k, r, m in kinds_rings:
        kind += [k] * m
        ring += [r] * m
    n = len(kind)
    tcp = np.column_stack([2.0 * np.arange(n), np.zeros(n), np.zeros(n)])
    return np.zeros((n, 6)), tcp, kind, ring


def test_strang_ein_trapez_ohne_rampe_an_ringgrenzen() -> None:
    tp = TimingParams()
    q, tcp, kind, ring = _line_run(
        [("approach", 0, 1), ("print", 0, 100), ("link", 1, 20), ("print", 1, 100)]
    )
    t = time_parametrize(q, tcp, kind, ring, tp)
    # ein Vorlauf am Strangbeginn, dann eine Gerade mit einem Trapez: Gesamtzeit wie aus einem Stueck
    s = 2.0 * (len(kind) - 1)
    want = tp.t_tot_s + s / tp.v_print_mm_s + tp.v_print_mm_s / tp.a_print_mm_s2
    assert t[-1] - t[0] == pytest.approx(want, rel=1e-6)
    v = 2.0 / np.diff(t)
    ramp = int(np.ceil(tp.v_print_mm_s**2 / (2 * tp.a_print_mm_s2) / 2.0)) + 1
    mid = v[2 + ramp : -ramp]
    assert np.allclose(mid, tp.v_print_mm_s, rtol=1e-6)  # auch ueber die Ringgrenzen 0 | link | 1
    assert int((np.diff(t) >= tp.t_tot_s).sum()) == 1


def test_ohne_verbinder_zwei_straenge_zwei_vorlaeufe() -> None:
    tp = TimingParams()
    q, tcp, kind, ring = _line_run([("approach", 0, 1), ("print", 0, 100), ("print", 1, 100)])
    t = time_parametrize(q, tcp, kind, ring, tp)
    assert int((np.diff(t) >= tp.t_tot_s).sum()) == 2  # Ring 1 ohne Verbinder: neuer Strang


# --------------------------------------------------------------------------- Selbstpruefung


def _checks(mesh, pp, tr, tp, **kw) -> list[selfcheck.Violation]:
    return selfcheck.check_part(mesh, pp.T_WP, tr, tp, layer_height_mm=H, **kw)


def test_selbstpruefung_besteht(planned) -> None:
    mesh, pp, tr, tp = planned
    assert _checks(mesh, pp, tr, tp) == []


def test_selbstpruefung_link_ohne_link_next(planned) -> None:
    mesh, pp, tr, tp = planned
    bad = tp.model_copy(deep=True)
    bad.rings[2].link_next = False
    v = _checks(mesh, pp, tr, bad)
    assert [x.check for x in v] == ["a"] and "link_next" in v[0].message


def test_selbstpruefung_link_schichtregel(planned) -> None:
    mesh, pp, tr, tp = planned
    bad = tr.model_copy(deep=True)
    i = next(i for i, (k, r) in enumerate(zip(bad.kind, bad.ring, strict=True)) if k == "link" and r == 2)
    bad.layer[i] = 0  # Verbinder in Schicht 1: k = 1
    assert {x.check for x in _checks(mesh, pp, bad, tp)} == {"a"}


def test_selbstpruefung_link_neben_der_geraden(planned) -> None:
    mesh, pp, tr, tp = planned
    bad = tr.model_copy(deep=True)
    idx = [i for i, k in enumerate(bad.kind) if k == "link"]
    bad.tcp[idx[len(idx) // 2]][1] += 2.0
    v = _checks(mesh, pp, bad, tp)
    assert [x.check for x in v] == ["d"] and "Geraden" in v[0].message


def test_selbstpruefung_link_ueber_oeffnung_und_zu_lang(planned) -> None:
    """Ein Schacht (6 x 6 mm) mitten unter dem Schalenverbinder: Druckringe bleiben im Material, der
    Verbinder nicht. Und link_max_mm kleiner als der Verbinder (42 mm)."""
    from roboprint import geometry as geo

    mesh, pp, tr, tp = planned
    # Mitte (-70, -20) in P: zwischen Ende Ring 0 (-85, -35) und Start Ring 1 (-55, -5)
    shaft = geo.make_box((6, 6, 60), origin=(-73, -23, -10))
    holed = geo._from_manifold(geo._to_manifold(mesh) - geo._to_manifold(shaft))
    v = _checks(holed, pp, tr, tp)
    assert {x.check for x in v} == {"d"} and all("Verbinder" in x.message for x in v)
    v = _checks(mesh, pp, tr, tp, link_max_mm=30.0)
    assert [x.check for x in v] == ["d"] and "link_max_mm" in v[0].message
