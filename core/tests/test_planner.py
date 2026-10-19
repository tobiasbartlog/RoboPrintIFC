"""Planer: Viterbi, Verdichtung, Statusvergabe, Travel-Ablauf, k-Semantik, Zeitachse, Artefakte."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from roboprint.assets import load_tool, load_workstation
from roboprint.contracts import PartArtifact, Scene, Summary, Toolpath, Trajectory, load_json
from roboprint.planner import PlannerParams
from roboprint.planner.densify import movej, movel, movel_chain
from roboprint.planner.graph import HARD, N_BRANCH, RingGraph, _edge_costs, node_costs, viterbi
from roboprint.planner.kin import Kin
from roboprint.planner.result import _status
from roboprint.robot import HOME_Q, fk_batch
from roboprint.timing import time_parametrize, trapezoid_times

P = PlannerParams()


@pytest.fixture(scope="module")
def kin() -> Kin:
    return Kin(load_workstation(), load_tool())


# --------------------------------------------------------------------------- Viterbi


def _toy_graph(n: int = 4) -> RingGraph:
    """Zwei psi-Werte, nur Zweig 0 gueltig; psi-Index 0 liegt ueberall bei q = 0, psi 1 bei q1 = 0,1."""
    psi = np.array([0.0, np.pi / 2])
    S = 2 * N_BRANCH
    Q = np.zeros((n, S, 6))
    valid = np.zeros((n, S), bool)
    for p in range(2):
        s = p * N_BRANCH
        valid[:, s] = True
        Q[:, s, 0] = 0.1 * p
    g = RingGraph(np.zeros((n, 3)), psi, 0, Q, valid, np.full((n, S), np.inf), np.full((n, S), np.nan))
    g.edge = _edge_costs(g, P)
    return g


def test_viterbi_bleibt_auf_billigem_pfad_und_meidet_harte_knoten() -> None:
    g = _toy_graph()
    states, cost, restarts = viterbi(g, node_costs(g, P, True), np.zeros(g.Q.shape[1]))
    assert (states == 0).all() and restarts == 0 and cost == pytest.approx(0.0)
    # Knoten (Wegpunkt 2, psi 0) ist zu nah (echte Welt): der Pfad weicht auf psi 1 aus
    g.d_real[2, 0] = 0.0
    nc = node_costs(g, P, True)
    assert nc[2, 0] >= HARD
    states, cost, _ = viterbi(g, nc, np.zeros(g.Q.shape[1]))
    assert states[2] == N_BRANCH  # psi-Index 1, Zweig 0
    assert cost < HARD


def test_viterbi_kanten_nur_im_selben_zweig_und_mit_dq_grenze() -> None:
    g = _toy_graph(3)
    g.Q[1, N_BRANCH, 0] = 1.0  # psi 1 springt um 0,9 rad > dq_max
    g.edge = _edge_costs(g, P)
    assert not np.isfinite(g.edge[0, 0, 0, 1])
    assert np.isfinite(g.edge[0, 0, 0, 0])


# --------------------------------------------------------------------------- Verdichtung und Status


def _check_density(q0: np.ndarray, d, kin: Kin) -> None:
    q = np.vstack([q0[None], d.q])
    ok = np.concatenate([[True], d.ok])
    tcp = kin.tcp_W(q)[:, :3, 3]
    both = ok[1:] & ok[:-1]
    assert np.abs(np.diff(q, axis=0)).max(axis=1)[both].max() <= 0.005
    assert np.linalg.norm(np.diff(tcp, axis=0), axis=1)[both].max() <= 5.0


def test_movel_dicht_linear_und_im_zweig(kin: Kin) -> None:
    p_a = np.array([700.0, 500.0, 1100.0])
    p_b = p_a + np.array([150.0, -40.0, 0.0])
    Q, ok = kin.ik(p_a[None], np.array([0.3]))
    b = int(np.nonzero(ok[0])[0][0])
    q0 = Q[0, b]
    d = movel(kin, p_a, 0.3, p_b, 0.5, q0, b, P)
    assert d.ok.all()
    _check_density(q0, d, kin)
    tcp = kin.tcp_W(d.q)[:, :3, 3]
    u = (tcp - p_a) @ (p_b - p_a) / np.dot(p_b - p_a, p_b - p_a)
    off = np.linalg.norm(tcp - (p_a + u[:, None] * (p_b - p_a)), axis=1)
    assert off.max() < 1e-3 and np.all(np.diff(u) > 0)
    assert np.allclose(tcp[-1], p_b, atol=1e-3)


def test_movel_chain_haelt_ecken(kin: Kin) -> None:
    pts = np.array([[700.0, 500.0, 1000.0], [760.0, 500.0, 1000.0], [760.0, 540.0, 1000.0]])
    Q, ok = kin.ik(pts[:1], np.zeros(1))
    b = int(np.nonzero(ok[0])[0][0])
    d, seg = movel_chain(kin, pts, np.zeros(3), Q[0, b], b, P)
    tcp = kin.tcp_W(d.q)[:, :3, 3]
    assert np.min(np.linalg.norm(tcp - pts[1], axis=1)) < 1e-3  # Ecke ist ein Sample
    assert set(seg.tolist()) == {1, 2}
    _check_density(Q[0, b], d, kin)


def test_movel_chain_nicht_dichter_als_noetig(kin: Kin) -> None:
    """A4.6: je Segment hoechstens ceil(Bedarf) + Reserve Samples, Bedarf aus TCP-Weg und Gelenkweg."""
    pts = np.array(
        [[700.0, 500.0, 1000.0], [720.0, 500.0, 1000.0], [720.0, 520.0, 1000.0], [900.0, 520.0, 1000.0]]
    )
    psi = np.array([0.0, 0.4, 0.4, 0.4])
    Q, ok = kin.ik(pts[:1], psi[:1])
    b = int(np.nonzero(ok[0])[0][0])
    q0 = Q[0, b]
    d, seg = movel_chain(kin, pts, psi, q0, b, P)
    assert d.ok.all()
    _check_density(q0, d, kin)
    q = np.vstack([q0[None], d.q])
    tcp = kin.tcp_W(q)[:, :3, 3]
    for s in (1, 2, 3):
        idx = np.flatnonzero(seg == s)
        assert np.linalg.norm(tcp[idx[-1] + 1] - pts[s]) < 1e-3  # Wegpunkt ist ein Sample
        steps = np.abs(np.diff(q[idx[0] : idx[-1] + 2], axis=0))
        need_q = steps.sum(axis=0).max() / 0.005  # Gelenkweg des fuehrenden Gelenks
        need_p = np.linalg.norm(pts[s] - pts[s - 1]) / 5.0
        lower = int(np.ceil(max(need_q, need_p)))
        assert lower <= len(idx) <= int(np.ceil(1.1 * max(need_q, need_p) + 1e-9)) + 1


def test_movej_dicht(kin: Kin) -> None:
    q_b = HOME_Q + np.array([0.4, -0.2, 0.3, 0.5, -0.3, 1.0])
    d = movej(kin, HOME_Q, q_b, P)
    _check_density(HOME_Q, d, kin)
    assert np.allclose(d.q[-1], q_b)


def test_transfer_sackt_unter_mindesthoehe() -> None:
    """Selbstpruefung (b): Ueber dem Teil bleibt der Transfer >= z_lift - TOL_LIFT_MM ueber dem
    Druckstand. Sackt die movej tiefer, gilt er als unfrei und bekommt den Zwischenpunkt (SPEC 5.3)."""
    from roboprint.planner.densify import Dense
    from roboprint.planner.plan import PartPlanner, RingTask
    from roboprint.selfcheck import TOL_LIFT_MM

    p = PlannerParams()
    ring = np.array([[0.0, 0.0, 10.0], [600.0, 0.0, 10.0], [600.0, 200.0, 10.0], [0.0, 200.0, 10.0]])
    T_WP = np.eye(4)  # noqa: N806
    pp = PartPlanner(None, [RingTask(0, 0, ring), RingTask(1, 5, ring + [0, 0, 50])], T_WP, p, None, None)
    k = 3  # Druckstand-Oberkante 30 mm
    floor = pp.stand_top_W(k) + p.z_lift_mm - TOL_LIFT_MM

    def dense(z: float, x: float = 300.0) -> Dense:
        pts = np.array([[x, 100.0, z]])
        return Dense(np.zeros((1, 6)), np.ones(1, bool), pts, np.zeros(1), np.ones(1))

    assert not pp._sags(dense(floor + 0.1), k)
    assert pp._sags(dense(floor - 0.1), k)
    assert not pp._sags(dense(floor - 0.1, x=900.0), k)  # neben dem Teil egal
    assert not pp._sags(dense(0.0), 0)  # vor dem ersten Ring gibt es keinen Druckstand


def test_unerreichbar_ist_eigener_status(kin: Kin) -> None:
    p_a = np.array([780.0, 600.0, 1200.0])
    p_b = np.array([780.0, -1500.0, 1200.0])  # weit ausserhalb der Reichweite
    Q, ok = kin.ik(p_a[None], np.zeros(1))
    b = int(np.nonzero(ok[0])[0][0])
    d = movel(kin, p_a, 0.0, p_b, 0.0, Q[0, b], b, P)
    assert not d.ok[-1] and d.ok[0]
    # unerreichbar: q bleibt die letzte gueltige Loesung (nur Anzeige)
    last_ok = d.q[np.nonzero(d.ok)[0][-1]]
    assert np.allclose(d.q[-1], last_ok)
    assert _status(None, False, P) == "unreachable"

    class C:
        d_mm = -1.0

    assert _status(C, True, P) == "collision"
    C.d_mm = 20.0
    assert _status(C, True, P) == "warn"
    C.d_mm = 60.0
    assert _status(C, True, P) == "ok"


# --------------------------------------------------------------------------- Prozess-Pools


def test_pools_aendern_das_ergebnis_nicht() -> None:
    """Graphen-Vorausbau und Abschlusspruefung im Pool liefern dasselbe wie seriell."""
    from roboprint import frames
    from roboprint.geometry import make_box
    from roboprint.planner import plan_part

    mesh = make_box([200, 100, 40], origin=[-100, -50, 0.0])
    pl = frames.Placement(-500.0, -325.0, 0.0)
    a = plan_part(mesh, "a", P, placement=pl, procs=1).path
    b = plan_part(mesh, "b", P, placement=pl, procs=2).path
    assert np.array_equal(a.q, b.q) and a.status == b.status and a.feasible
    assert [c and (c.d_mm, c.pair) for c in a.contacts] == [c and (c.d_mm, c.pair) for c in b.contacts]


# --------------------------------------------------------------------------- Hoehensuche

PL_SMALL = (-500.0, -325.0, 0.0)


def test_niedrigeres_prisma_ist_praefix_des_hoeheren() -> None:
    """Grundlage der Hoehensuche: Der Plan eines 30 mm hohen Quaders ist exakt der untere Teil
    des Plans eines 60 mm hohen an derselben Platzierung (gleiche Ringe, gleicher Druckstand)."""
    from roboprint import frames
    from roboprint.geometry import make_box
    from roboprint.planner import plan_part, truncate_plan

    pl = frames.Placement(*PL_SMALL)
    tall = plan_part(make_box([200, 100, 60], origin=[-100, -50, 0.0]), "a", P, placement=pl)
    low = plan_part(make_box([200, 100, 30], origin=[-100, -50, 0.0]), "b", P, placement=pl)
    cut = truncate_plan(tall, 3, P)
    assert low.path.feasible and cut.path.feasible
    assert np.array_equal(cut.path.q, low.path.q) and cut.path.status == low.path.status
    assert [c and c.d_mm for c in cut.path.contacts] == [c and c.d_mm for c in low.path.contacts]
    assert cut.sliced.n_layers == 3 and len(cut.sliced.rings) == len(low.sliced.rings)


def test_hoehensuche_stoppt_an_der_ersten_schicht_die_nicht_geht() -> None:
    """Ab k = 5 fertigen Schichten ist (kuenstlich) alles Kollision: Das Abheben nach Schicht 4
    scheitert, also gehen 4 Schichten. Darueber wird nichts mehr geplant."""
    from dataclasses import replace

    from roboprint import frames
    from roboprint.assets import REPO_ROOT
    from roboprint.geometry import make_box
    from roboprint.planner import _prefix_len, _setup, make_world, slice_params
    from roboprint.planner.plan import PartPlanner, truncate
    from roboprint.slicer import slice_part

    mesh = make_box([200, 100, 80], origin=[-100, -50, 0.0])
    sliced = slice_part(mesh, slice_params(P))
    T_WP, final, screen, height, kin, tasks = _setup(  # noqa: N806
        mesh, sliced, frames.Placement(*PL_SMALL), P, REPO_ROOT, make_world
    )

    class Blocked:
        def distance(self, q, k):
            c = final.distance(q, k)
            return replace(c, d_mm=-1.0) if k >= 5 else c

    path = PartPlanner(kin, tasks, T_WP, P, screen, screen, True, height, Blocked(), stop_at_bad=True).run()
    assert path.layers_ok == 4
    first_ring_l4 = next(r.index for r in tasks if r.layer == 4)
    assert max(path.ring) == first_ring_l4 and not path.feasible
    cut = truncate(path, _prefix_len(path, sliced, 4), P)
    assert cut.feasible and max(cut.layer) == 4 and cut.kind[-1] == "lift"


def test_quaderzelle_bekommt_den_ausschnitt_der_hoehensuche() -> None:
    """Eine aus der Wand geschnittene Vollquader-Zelle bekommt den abgeschnittenen Plan der
    Hoehensuche, identisch mit einer eigenen Planung; Zellen mit Oeffnung werden neu geplant."""
    from roboprint import decompose as dc
    from roboprint import frames
    from roboprint import geometry as geo
    from roboprint.decompose_plan import _from_scan
    from roboprint.ifc import Opening, Wall
    from roboprint.planner import plan_part

    pl = frames.Placement(*PL_SMALL)
    scan = plan_part(make_box_P(200, 100, 60), "scan", P, placement=pl)
    scan.path.layers_ok = 6
    hole = geo.make_box((100, 200, 20), origin=(250, -50, 0))
    mesh = geo._from_manifold(geo._to_manifold(geo.make_box((400, 100, 60))) - geo._to_manifold(hole))
    wall = Wall("W", "w", mesh, 400.0, 100.0, 60.0, geo.volume(mesh), np.eye(4), [Opening(250, 350, 0, 20)])
    cell, _ = dc._cut_part(wall, np.array([0.0, 0.0, 0.0]), np.array([200.0, 100.0, 30.0]))
    got = _from_scan(cell, [scan], P)
    assert got is not None and got.feasible
    own = plan_part(cell, "own", P, placement=pl).path
    assert np.array_equal(got.planned.path.q, own.q) and got.planned.path.status == own.status
    with_hole, _ = dc._cut_part(wall, np.array([200.0, 0.0, 0.0]), np.array([400.0, 100.0, 30.0]))
    assert _from_scan(with_hole, [scan], P) is None
    too_high, _ = dc._cut_part(wall, np.array([0.0, 0.0, 0.0]), np.array([200.0, 100.0, 60.0]))
    scan.path.layers_ok = 5
    assert _from_scan(too_high, [scan], P) is None


def make_box_P(b: float, t: float, h: float):  # noqa: N802
    from roboprint.geometry import make_box

    return make_box([b, t, h], origin=[-b / 2, -t / 2, 0.0])


def test_platzierung_parallel_wie_seriell(kin: Kin) -> None:
    from roboprint import frames
    from roboprint.geometry import make_box
    from roboprint.planner import SphereWorld
    from roboprint.planner.placement import _scores, _scores_parallel, probe_points

    mesh = make_box([300, 200, 60], origin=[-150, -100, 0.0])
    world = SphereWorld(mesh, np.eye(4), P.layer_height_mm)
    world.skip_tip = True
    ws = load_workstation()
    T = [frames.T_WP(ws, frames.Placement(x, y, 0.0)) for x in (-600, -500, -400, -300) for y in (-350, -250)]
    probes, psi = probe_points(mesh, P.layer_height_mm, False), P.psi_grid[::6]
    assert np.array_equal(
        _scores(kin, world, T, probes, psi, False), _scores_parallel(kin, world, T, probes, psi, False, 2)
    )


# --------------------------------------------------------------------------- Zeit


def test_trapez_und_monotonie() -> None:
    s = np.linspace(0, 1000, 201)
    t = trapezoid_times(s, 100.0, 500.0)
    assert np.all(np.diff(t) > 0)
    assert t[-1] == pytest.approx(1000 / 100 + 100 / 500, rel=1e-6)
    q = np.zeros((5, 6))
    tcp = np.zeros((5, 3))  # Stillstand: trotzdem streng monoton
    ts = time_parametrize(q, tcp, ["transfer", "transfer", "print", "print", "lift"], [0, 0, 0, 0, 0])
    assert np.all(np.diff(ts) > 0)
    assert ts[2] - ts[1] >= 3.0  # Verweilzeit t_tot vor dem ersten Druck-Sample


# --------------------------------------------------------------------------- Ende-zu-Ende


SCEN = {
    "schema_version": "1",
    "id": "T_klein",
    "beschreibung": "kleiner Quader 200 x 100 x 40 mm",
    "mode": "modul",
    "source": {"kind": "box", "size_mm": [200, 100, 40]},
    "decompose": False,
    "robot": "robots/doosan_m1013.json",
    "urdf": "third_party/doosan_m1013/urdf/m1013.white.urdf",
    "tool": "tools/30gut.json",
    "workstation": "workstations/doosantisch.json",
    "params": {},
    "planner_mode": "collision_aware",
    "placement_override": {"x_mm": -500.0, "y_mm": -325.0, "yaw_deg": 0.0},
    "expect": {"parts": "all_feasible"},
    "limits": {"wall_time_s": 180},
}


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    from roboprint.pipeline import run_scenario

    d = tmp_path_factory.mktemp("lauf")
    scn = d / "scen.json"
    scn.write_text(json.dumps(SCEN), encoding="utf-8")
    stages = []
    assert run_scenario(scn, d / "run", progress=lambda s, f, m: stages.append((s, f))) == 0
    fr = [f for _, f in stages]
    assert fr == sorted(fr) and fr[-1] == 1.0
    return d / "run"


def test_artefakte_validieren(run_dir: Path) -> None:
    summ = load_json(run_dir / "summary.json", Summary)
    load_json(run_dir / "scene.json", Scene)
    pdir = run_dir / "parts" / summ.parts[0].part_id
    part = load_json(pdir / "part.json", PartArtifact)
    load_json(pdir / "toolpath.json", Toolpath)
    load_json(pdir / "trajectory.json", Trajectory)
    assert part.status == "machbar" and summ.parts[0].status == "machbar"
    assert (pdir / "part.stl").is_file()
    for d in ("v2", "v3"):
        assert "movej(posj(" in (pdir / f"program.{d}.drl").read_text(encoding="ascii")


def test_ablauf_und_schichtsemantik(run_dir: Path) -> None:
    pdir = next((run_dir / "parts").iterdir())
    tr = load_json(pdir / "trajectory.json", Trajectory)
    tp = load_json(pdir / "toolpath.json", Toolpath)
    kind, ring, layer = tr.kind, tr.ring, tr.layer
    assert np.allclose(tr.q[0], HOME_Q) and kind[0] == "transfer" and layer[0] == 0
    # Reihenfolge je Ring: (lift) -> transfer -> lower -> approach -> print -> retract
    order = {"lift": 0, "transfer": 1, "lower": 2, "approach": 3, "print": 4, "retract": 5}
    runs = [(kind[0], ring[0])]
    for k, r in zip(kind[1:], ring[1:], strict=True):
        if (k, r) != runs[-1]:
            runs.append((k, r))
    for r in range(len(tp.rings)):
        seq = [k for k, rr in runs if rr == r and k != "lift"]
        assert seq == sorted(seq, key=order.get) and seq[-1] == "retract"
        assert {"transfer", "approach", "print", "retract"} <= set(seq)
    assert kind[-1] == "lift"
    for i in range(len(kind)):
        L = tp.rings[ring[i]].layer
        if kind[i] in ("print", "approach", "retract"):
            assert layer[i] == L
        elif kind[i] == "lift":
            assert layer[i] == L + 1
        elif i > 0:  # transfer/lower vor Ring r: Schicht des vorigen Rings + 1 (erster Ring: 0)
            prev = tp.rings[ring[i] - 1].layer + 1 if ring[i] > 0 else 0
            assert layer[i] == prev
    assert all(np.diff(tr.t_s) > 0)
    st = Counter(tr.status)
    assert st["collision"] == 0 and st["unreachable"] == 0
    assert min(d for d in tr.d_mm if d is not None) >= P.d_hard_mm
    assert tr.summary.zweig_wechsel_in_ringen == 0
    # Abtastdichte ueber alle Samples (auch Travel)
    q = np.asarray(tr.q)
    tcp = np.asarray(tr.tcp)[:, :3]
    assert np.abs(np.diff(q, axis=0)).max() <= 0.005 + 1e-9
    assert np.linalg.norm(np.diff(tcp, axis=0), axis=1).max() <= 5.0
    # TCP-Artefakt = FK
    T = load_workstation()
    from roboprint import frames

    W = frames.T_WB(T) @ fk_batch(q[::50]) @ frames.T_FT(load_tool())
    assert np.abs(W[:, :3, 3] - tcp[::50]).max() < 1e-6
