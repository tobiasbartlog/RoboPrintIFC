"""Planer und Zeitachse mit Druckmustern (M3.2, docs/muster/ARTEFAKT-FORMAT.md): offene Ringe,
Verbinder der Laenge 0, senkrechter Schichtwechsel (Z-Hub um h), ein Strang ueber alle Ringe und
Schichten. Geprueft wird Verhalten gegen die Ablaufregeln (spec/ARTEFAKTE.md, SPEC §5.3/§5.5) und
die Musterregel M4, ohne Pinocchio."""

from __future__ import annotations

import numpy as np
import pytest

from roboprint import export, selfcheck
from roboprint.assets import load_tool, load_workstation
from roboprint.geometry import make_box
from roboprint.planner import PlannerParams, from_overrides, plan_part
from roboprint.planner.graph import BIG, build_graph, solve_ring
from roboprint.planner.kin import Kin, wrap_pi
from roboprint.planner.plan import ZERO_LINK_MM, is_zero_link
from roboprint.slicer import to_toolpath
from roboprint.timing import sections

FUGENWAND = "core/src/roboprint/patterns/presets/fugenwand.json"


def _box(b: float, t: float, h: float):
    return make_box([b, t, h], origin=[-b / 2, -t / 2, 0.0])


def _plan(mesh, overrides: dict):
    params = from_overrides(overrides, 50.0)
    pp = plan_part(mesh, "box", params)
    tr = export.trajectory(pp, Kin(load_workstation(), load_tool()), params)
    tp = to_toolpath(pp.sliced, pp.T_WP, "box")
    return params, pp, tr, tp


@pytest.fixture(scope="module")
def alternate():
    mesh = _box(300, 200, 30)
    return (mesh, *_plan(mesh, {"layer_order": "alternate"}))


@pytest.fixture(scope="module")
def fugenwand():
    mesh = _box(600, 200, 30)
    return (mesh, *_plan(mesh, {"pattern_preset": FUGENWAND}))


def _segments(kind, ring) -> list[tuple[str, int, int, int]]:
    out: list[list] = []
    for i, (k, r) in enumerate(zip(kind, ring, strict=True)):
        if out and out[-1][0] == k and out[-1][1] == r:
            out[-1][3] = i
        else:
            out.append([k, int(r), i, i])
    return [tuple(s) for s in out]


def _psi(tcp: np.ndarray) -> np.ndarray:
    """Drehung um die (senkrechte) Duesenachse aus dem Quaternion (w, x, y, z)."""
    w, x, y, z = tcp[:, 3], tcp[:, 4], tcp[:, 5], tcp[:, 6]
    return np.arctan2(2 * (x * y + w * z), 1 - 2 * (y * y + z * z))


@pytest.mark.parametrize("name", ["alternate", "fugenwand"])
def test_muster_ein_strang_ueber_alle_schichten(request, name) -> None:
    """Ein Strang: Travel nur vor dem ersten Ring, danach print (link print)* retract lift."""
    _, params, pp, tr, tp = request.getfixturevalue(name)
    n = len(tp.rings)
    assert pp.path.feasible
    assert tp.pattern is not None
    assert [r.link_next for r in tp.rings] == [True] * (n - 1) + [False]
    segs = _segments(tr.kind, tr.ring)
    want = ["transfer", "lower", "approach", "print"] + ["link", "print"] * (n - 1) + ["retract", "lift"]
    assert [k for k, *_ in segs] == want
    assert [r for k, r, *_ in segs if k == "print"] == list(range(n))
    assert len(set(np.asarray(tr.branch)[np.isin(tr.kind, ["print", "link"])].tolist())) == 1
    assert tr.summary.zweig_wechsel_in_ringen == 0
    # ein Abschnitt der Zeitachse fuer den ganzen Strang (ein Trapez, SPEC §5.5)
    strand = [s for s in sections(list(tr.kind), list(tr.ring)) if tr.kind[s[0]] in ("print", "link")]
    assert len(strand) == 1
    assert np.all(np.diff(tr.t_s) > 0)


def test_offene_ringe_enden_am_letzten_wegpunkt(fugenwand) -> None:
    """Offene Ringe (closed = false): Der Druck endet am letzten Wegpunkt, nicht am ersten."""
    _, _, _, tr, tp = fugenwand
    pos = np.asarray(tr.tcp)[:, :3]
    open_rings = [i for i, r in enumerate(tp.rings) if not r.closed]
    assert open_rings, "Fugenwand liefert offene Segmente"
    for k, r, a, b in _segments(tr.kind, tr.ring):
        if k != "print" or r not in open_rings:
            continue
        wp = np.asarray(tp.rings[r].waypoints)[:, :3]
        assert np.linalg.norm(wp[-1] - wp[0]) > 1.0
        assert np.linalg.norm(pos[b] - wp[-1]) < 1e-3
        # jeder Wegpunkt liegt auf einem Druck-Sample (Wegpunkte bleiben exakt Samples)
        seg = pos[max(a - 1, 0) : b + 1]
        d = np.linalg.norm(seg[None, :, :] - wp[:, None, :], axis=2).min(axis=1)
        assert d.max() < 1e-3


@pytest.mark.parametrize("name", ["alternate", "fugenwand"])
def test_verbinder_laenge_null_und_senkrechter_schichtwechsel(request, name) -> None:
    """Musterverbinder haben keine waagrechte Laenge: in der Schicht ein Sample am selben Ort, beim
    Schichtwechsel ein reiner Z-Hub um h (M4). psi bleibt, die Gelenke drehen nicht auf der Stelle."""
    _, params, _, tr, tp = request.getfixturevalue(name)
    pos = np.asarray(tr.tcp)[:, :3]
    psi = _psi(np.asarray(tr.tcp))
    q = np.asarray(tr.q)
    hubs = 0
    for k, r, a, b in _segments(tr.kind, tr.ring):
        if k != "link":
            continue
        A, B = pos[a - 1], pos[b]  # noqa: N806
        assert np.hypot(*(B - A)[:2]) <= ZERO_LINK_MM
        assert np.hypot(*(pos[a : b + 1] - A)[:, :2].T).max() <= ZERO_LINK_MM
        dz = tp.rings[r].layer - tp.rings[r - 1].layer
        assert B[2] - A[2] == pytest.approx(dz * params.layer_height_mm, abs=1e-3)
        assert np.abs(wrap_pi(psi[a - 1 : b + 1] - psi[a - 1])).max() < 1e-6
        if dz == 0:
            assert b == a  # ein link-Sample (Ablaufregel), kein Weg, keine Drehung
            assert np.abs(q[b] - q[a - 1]).max() < 1e-6
        else:
            hubs += 1
            assert tr.t_s[b] - tr.t_s[a - 1] <= 2.0 * params.layer_height_mm / params.v_print_mm_s
    assert hubs == 2  # 3 Schichten


def test_selbstpruefung_mit_muster(fugenwand) -> None:
    mesh, params, pp, tr, tp = fugenwand
    v = selfcheck.check_part(
        mesh, pp.T_WP, tr, tp, layer_height_mm=params.layer_height_mm, link_max_mm=params.link_max_mm
    )
    assert v == []


def test_is_zero_link() -> None:
    assert is_zero_link(np.array([0.0, 0, 0]), np.array([0.0, 0, 10]))
    assert is_zero_link(np.array([0.0, 0, 0]), np.array([0.3, 0.3, 0]))
    assert not is_zero_link(np.array([0.0, 0, 0]), np.array([30.0, 30, 10]))


def test_psi_hold_haelt_psi_am_ringstart() -> None:
    """`psi_hold` legt den Ringstart auf das gehaltene psi (Verbinder ohne Laenge), auch wenn ein
    anderes psi naeher an der Vorgaengerstellung laege; ohne `psi_hold` unveraendert."""
    params = PlannerParams()
    kin = Kin(load_workstation(), load_tool())
    p_W = np.array([[600.0, 300.0, 950.0], [620.0, 300.0, 950.0], [640.0, 300.0, 950.0]])  # noqa: N806
    g = build_graph(kin, p_W, 0, params, None)
    free = solve_ring(g, params, None, None, None)
    assert free.states[0] >= 0
    b = int(free.branch[0])
    target = float(wrap_pi(free.psi[0] + np.radians(90.0)))
    held = solve_ring(g, params, None, free.q[0], b, b, psi_hold=target)
    assert held.cost < BIG  # psi + 90 Grad ist im Zweig erreichbar
    assert abs(wrap_pi(held.psi[0] - target)) < 1e-9
    assert abs(wrap_pi(held.psi[0] - free.psi[0])) > 1.0
    again = solve_ring(g, params, None, free.q[0], b, b)
    assert abs(wrap_pi(again.psi[0] - free.psi[0])) < 1e-9


def test_ohne_muster_kein_psi_hold(monkeypatch) -> None:
    """Ohne Muster (S1-Format: diagonale Verbinder) bleibt der Planer beim bisherigen Aufruf."""
    import roboprint.planner.plan as plan_mod

    seen: list = []
    orig = plan_mod.solve_ring

    def spy(*a, **kw):
        seen.append(kw.get("psi_hold"))
        return orig(*a, **kw)

    monkeypatch.setattr(plan_mod, "solve_ring", spy)
    plan_part(_box(200, 100, 20), "box", PlannerParams())
    assert seen and all(s is None for s in seen)
