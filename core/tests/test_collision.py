"""Tests fuer roboprint.collision (SPEC §5.1, Gate G2).

Schnell: Paare, Wuerfel im Glied, Werkzeug ueber Box, Boden, Home-Pose, Timing, Vergleich gegen eine
Coal-Referenz auf Roh-Meshes an 40 Posen. Ausfuehrlich (ROBOPRINT_SLOW=1): 500 Posen wie G2.
"""

from __future__ import annotations

import os
import time
from functools import lru_cache

import numpy as np
import pytest
import trimesh

from roboprint import collision_assets as ca
from roboprint.collision import CONST_PAIRS, LINKS, Contact, World, checked_pairs, is_const_pair, status_of
from roboprint.frames import T_from_pos_quat

slow = pytest.mark.skipif(not os.environ.get("ROBOPRINT_SLOW"), reason="ausfuehrlich: ROBOPRINT_SLOW=1")

HOME = np.deg2rad([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])
T_WS = np.eye(4)
T_WS[:3, 3] = [780.0, 605.0, 901.0]  # workstations/doosantisch.json, work_surface_frame


def box_P(size) -> trimesh.Trimesh:  # noqa: N802
    L, T, H = size  # noqa: N806
    m = trimesh.creation.box(extents=(L, T, H))
    m.apply_translation((0.0, 0.0, H / 2))
    return m


def s1_scene():
    """S1 wie im G2-Orakel: Quader 600 x 200 x 400 bei S = (0, -50), Gier 0."""
    T_SP = np.eye(4)  # noqa: N806
    T_SP[:3, 3] = [0.0, -50.0, 0.0]
    return box_P((600.0, 200.0, 400.0)), T_WS @ T_SP


@lru_cache(maxsize=1)
def s1_world() -> World:
    mesh, T_WP = s1_scene()  # noqa: N806
    return World(mesh, T_WP)


# --------------------------------------------------------------------------- Paare


def test_pairs_exact_spec():
    pairs = set(checked_pairs())
    assert len(pairs) == len(checked_pairs())
    # Ausnahmen
    for a in ("base_link", "link_1"):
        assert (a, "floor") not in pairs and (a, "table") not in pairs
    assert ("nozzle_tip", "printed") not in pairs
    assert ("link_5", "link_6") not in pairs and ("link_6", "link_5") not in pairs
    assert ("tool_body", "link_5") not in pairs and ("tool_body", "link_6") not in pairs
    # Pflichtpaare
    for a in ("link_2", "link_3", "link_4", "link_5", "link_6", "tool_body", "nozzle_tip"):
        assert (a, "floor") in pairs and (a, "table") in pairs
    for a in (*LINKS, "tool_body"):
        assert (a, "printed") in pairs
    for i in range(7):
        for j in range(i + 2, 7):
            assert (LINKS[j], LINKS[i]) in pairs
    for n in LINKS[:5]:
        assert ("tool_body", n) in pairs
    assert len(pairs) == 7 + 7 + 8 + 15 + 5


def test_pair_distances_cover_exactly_the_pairs():
    w = s1_world()
    got = set(w.pair_distances(HOME, 20))
    assert got == set(checked_pairs())
    got0 = set(w.pair_distances(HOME, 0))  # ohne Druckstand
    assert got0 == {p for p in checked_pairs() if p[1] != "printed"}
    c = w.distance(HOME, 20)
    assert c.pair in got
    assert len(c.witness_W) == 2 and all(np.shape(p) == (3,) for p in c.witness_W)


# --------------------------------------------------------------------------- Geometrie


def _world_with_box_at(center_W, size, k_layers=None):  # noqa: N803
    T_WP = np.eye(4)  # noqa: N806
    T_WP[:3, 3] = np.asarray(center_W) - [0.0, 0.0, size[2] / 2]
    w = World(box_P(size), T_WP)
    k = int(np.ceil(size[2] / 10.0)) if k_layers is None else k_layers
    return w, k


def test_cube_inside_link_is_negative():
    w0 = s1_world()
    frames = w0.frames_W(HOME)
    b3 = next(b for b in w0._moving if b.name == "link_3")
    big = int(np.argmax([np.prod(np.ptp(p.vertices, axis=0)) for p in b3.parts]))
    c_local = b3.parts[big].vertices.mean(axis=0)
    c_W = frames[LINKS.index("link_3")] @ np.append(c_local, 1.0)  # noqa: N806
    w, k = _world_with_box_at(c_W[:3], (20.0, 20.0, 20.0))
    c = w.distance(HOME, k)
    assert c.d_mm < 0
    pd = w.pair_distances(HOME, k)
    assert pd[("link_3", "printed")] < 0


def test_layer_zero_has_no_printed_obstacle():
    w0 = s1_world()
    pd = w0.pair_distances(HOME, 0)
    assert not any(p[1] == "printed" for p in pd)


def test_known_distance_tool_body_to_box():
    """Box unter der Duese: Abstand Werkzeugkoerper-Box = tiefster Rohpunkt des Koerpers - Box-Oberkante."""
    w0 = s1_world()
    T_W6 = w0.frames_W(HOME)[LINKS.index("link_6")]  # noqa: N806
    tcp_W = (T_W6 @ w0.T_FT)[:3, 3]  # noqa: N806
    # Rohe Werkzeugpunkte ausserhalb der Freizone, in W
    tool = trimesh.load(str(w0.root / "tools" / "30gut.stl"), force="mesh")
    import json

    tj = json.loads((w0.root / "tools" / "30gut.json").read_text())
    tool.apply_transform(T_from_pos_quat(tj["mesh_transform"]["pos_mm"], tj["mesh_transform"]["quat"]))
    tool.apply_transform(T_W6)
    v = np.asarray(tool.vertices)
    body = v[np.linalg.norm(v - tcp_W, axis=1) > 40.0]
    z_body = float(body[:, 2].min())
    gap = 30.0
    top = z_body - gap
    # breite, flache Box, Oberkante bei `top`, mittig unter dem TCP; die Duesenspitze zaehlt nicht
    size = (800.0, 800.0, 20.0)
    w, k = _world_with_box_at([tcp_W[0], tcp_W[1], top - 10.0], size)
    pd = w.pair_distances(HOME, k)
    d = pd[("tool_body", "printed")]
    assert d <= gap + 1.0
    assert d >= gap - 12.0
    assert ("nozzle_tip", "printed") not in pd


def test_floor_distance_matches_raw_mesh():
    w = s1_world()
    q = np.deg2rad([30.0, 60.0, 80.0, 10.0, -40.0, 20.0])
    frames = w.frames_W(q)
    pd = w.pair_distances(q, 0)
    for name in ("link_4", "link_6"):
        raw = ca.link_mesh(w.chain.collision[name])
        z_raw = float(
            (raw.vertices @ frames[LINKS.index(name)][:3, :3].T)[:, 2].min() + frames[LINKS.index(name)][2, 3]
        )
        d = pd[(name, "floor")]
        assert d <= z_raw + 1.0
        assert d >= z_raw - 12.0


def test_home_pose_free_over_table():
    w = s1_world()
    c = w.distance(HOME, 0)
    print(f"Home-Pose k=0: d_min = {c.d_mm:.1f} mm, Paar {c.pair}")
    assert c.d_mm > 10.0  # d_hard


def test_upper_bound_early_exit_is_consistent():
    w = s1_world()
    rng = np.random.default_rng(1)
    for q in rng.uniform(-np.pi, np.pi, (20, 6)):
        q[2] = np.clip(q[2], -2.79, 2.79)
        full = w.distance(q, 20).d_mm
        cut = w.distance(q, 20, upper=50.0).d_mm
        if full < 50.0:
            assert cut == pytest.approx(full, abs=1e-9)
        else:
            assert cut >= 50.0 - 1e-9


def test_branch_and_bound_equals_min_over_pairs():
    w = s1_world()
    rng = np.random.default_rng(4)
    for q in rng.uniform(-np.pi, np.pi, (15, 6)):
        q[2] = np.clip(q[2], -2.79, 2.79)
        pd = w.pair_distances(q, 20)
        c = w.distance(q, 20)
        # Statusregel: CONST_PAIRS zaehlt nur unter d_hard
        rest = min(v for k, v in pd.items() if not is_const_pair(k) or v < w.d_hard_mm)
        assert c.d_mm == pytest.approx(rest, abs=1e-6)
        assert pd[c.pair] == pytest.approx(c.d_mm, abs=1e-6)


def test_const_pairs_are_neighbour_links():
    """Gliedpaare mit genau einem Gelenk dazwischen, ungeordnet; sie sind geprueft (Sicherheitsnetz)."""
    assert len(CONST_PAIRS) == 5
    for i in range(5):
        assert is_const_pair((LINKS[i], LINKS[i + 2])) and is_const_pair((LINKS[i + 2], LINKS[i]))
    assert not is_const_pair(("link_1", "link_4")) and not is_const_pair(("link_2", "floor"))
    assert not is_const_pair(("tool_body", "link_2")) and not is_const_pair(("link_6", "printed"))
    checked = {frozenset(p) for p in checked_pairs()}
    assert CONST_PAIRS <= checked


def test_const_pair_below_target_does_not_count():
    """Home-Pose: base_link <-> link_2 liegt konstruktiv bei ~31 mm < d_target 50 mm, ist aber nicht
    das Minimum von d_status; d_mm gehoert zu einem anderen Paar, der Status ist ok."""
    w = s1_world()
    pd = w.pair_distances(HOME, 0)
    const = ("link_2", "base_link")
    assert 20.0 < pd[const] < 50.0
    c = w.distance(HOME, 0)
    assert not is_const_pair(c.pair)
    assert c.d_mm == pytest.approx(min(v for k, v in pd.items() if not is_const_pair(k)), abs=1e-6)
    assert c.d_mm > pd[const]
    assert status_of(c, 50.0, 20.0) == "ok"


def test_other_const_pair_below_target_does_not_count():
    """Andere i <-> i+2-Paare: bei eingeklapptem Ellbogen liegt ein solches Paar unter d_target;
    es loest kein warn aus, solange es >= d_hard bleibt, und bestimmt d_mm nicht."""
    w = s1_world()
    q = np.deg2rad([103.7, 37.0, 4.3, -72.8, -107.1, -39.7])  # (link_2, link_4), (link_4, link_6) ~37 mm
    pd = w.pair_distances(q, 0)
    near = [k for k in pd if is_const_pair(k) and w.d_hard_mm <= pd[k] < 50.0]
    assert {frozenset(k) for k in near} >= {frozenset(("link_2", "link_4")), frozenset(("link_4", "link_6"))}
    assert min(v for k, v in pd.items() if not is_const_pair(k)) >= 50.0
    c = w.distance(q, 0)
    rest = min(v for k, v in pd.items() if not is_const_pair(k) or v < w.d_hard_mm)
    assert c.d_mm == pytest.approx(rest, abs=1e-6)
    assert not is_const_pair(c.pair) or c.d_mm < w.d_hard_mm
    if min(v for k, v in pd.items() if not is_const_pair(k)) >= 50.0:
        assert status_of(c, 50.0, 20.0) == "ok"


def test_const_pair_below_d_hard_counts():
    """Unterschreitet ein solches Paar d_hard (hier kuenstlich 100 mm), geht es in d_status ein."""
    mesh, T_WP = s1_scene()  # noqa: N806
    w = World(mesh, T_WP, d_hard_mm=100.0)
    pd = w.pair_distances(HOME, 0)
    c = w.distance(HOME, 0)
    const = ("link_2", "base_link")
    assert pd[const] < 100.0
    assert c.d_mm == pytest.approx(min(pd.values()), abs=1e-6)
    if min(pd, key=pd.get) == const:
        assert c.pair == const


def test_status_per_pair_targets():
    """Statusregel: Druckstand warnt erst unter d_target_printed (20), alles uebrige unter d_target (50)."""
    w = (np.zeros(3), np.zeros(3))
    pr, ot = ("tool_body", "printed"), ("link_3", "table")
    assert status_of(Contact(41.0, pr, w, 41.0, 90.0), 50.0, 20.0) == "ok"
    assert status_of(Contact(19.0, pr, w, 19.0, 90.0), 50.0, 20.0) == "warn"
    assert status_of(Contact(45.0, ot, w, 70.0, 45.0), 50.0, 20.0) == "warn"
    assert status_of(Contact(-1.0, pr, w, -1.0, 90.0), 50.0, 20.0) == "collision"
    # Druckstand ok, aber ein anderes Paar unter 50: warn
    assert status_of(Contact(30.0, pr, w, 30.0, 45.0), 50.0, 20.0) == "warn"
    # ohne Klassenwerte entscheidet das Paar des Minimums
    assert status_of(Contact(41.0, pr, w), 50.0, 20.0) == "ok"
    assert status_of(Contact(41.0, ot, w), 50.0, 20.0) == "warn"


def test_class_minima_consistent():
    """d_mm = min(d_printed, d_other); die Klassenwerte sind nie kleiner als die wahren Klassenminima."""
    w = s1_world()
    rng = np.random.default_rng(6)
    for q in rng.uniform(-np.pi, np.pi, (12, 6)):
        q[2] = np.clip(q[2], -2.79, 2.79)
        pd = w.pair_distances(q, 20)
        c = w.distance(q, 20)
        cnt = {k: v for k, v in pd.items() if not is_const_pair(k) or v < w.d_hard_mm}
        true_p = min((v for k, v in cnt.items() if k[1] == "printed"), default=np.inf)
        true_o = min((v for k, v in cnt.items() if k[1] != "printed"), default=np.inf)
        assert c.d_mm == pytest.approx(min(c.d_printed_mm, c.d_other_mm), abs=1e-6)
        assert c.d_printed_mm >= true_p - 1e-6 and c.d_other_mm >= true_o - 1e-6
        if true_o < 50.0:
            assert c.d_other_mm == pytest.approx(true_o, abs=1e-6)
        if true_p < 50.0 and true_p <= true_o:
            assert c.d_printed_mm == pytest.approx(true_p, abs=1e-6)


def test_seeds_skip_const_pairs():
    """Saaten aus i <-> i+2-Paaren liefern keine obere Schranke (sie zaehlen erst unter d_hard) und
    machen die Branch-and-Bound-Suche um Groessenordnungen langsamer; sie duerfen nie Saat sein."""
    from roboprint.collision import _BlockBounds

    w = s1_world()
    rng = np.random.default_rng(8)
    Q = rng.uniform(-np.pi, np.pi, (16, 6))  # noqa: N806
    Q[:, 2] = np.clip(Q[:, 2], -2.79, 2.79)
    F = np.empty((len(Q), len(LINKS) + 1, 4, 4))  # noqa: N806
    F[:, : len(LINKS)] = w.T_WB @ w.chain.link_poses_batch(Q)
    F[:, len(LINKS)] = np.eye(4)
    sc = w._scene(20)
    _, ks = _BlockBounds(F, sc).seeds(2)
    assert ks and not any(sc.k_const[k] for k in ks)


def test_batch_equals_single():
    w = s1_world()
    rng = np.random.default_rng(2)
    Q = rng.uniform(-np.pi, np.pi, (10, 6))  # noqa: N806
    Q[:, 2] = np.clip(Q[:, 2], -2.79, 2.79)
    batch = w.distance_batch(Q, 20)
    for q, c in zip(Q, batch, strict=True):
        assert c.d_mm == pytest.approx(w.distance(q, 20).d_mm, abs=1e-9)


def test_timing():
    w = s1_world()
    rng = np.random.default_rng(3)
    Q = rng.uniform(-np.pi, np.pi, (200, 6))  # noqa: N806
    Q[:, 2] = np.clip(Q[:, 2], -2.79, 2.79)
    w.distance(Q[0], 20)
    t = time.perf_counter()
    w.distance_batch(Q, 20)
    full = (time.perf_counter() - t) / len(Q) * 1e3
    t = time.perf_counter()
    w.distance_batch(Q, 20, upper=50.0)
    capped = (time.perf_counter() - t) / len(Q) * 1e3
    print(f"distance: {full:.2f} ms/Pose, mit upper=50: {capped:.2f} ms/Pose")
    assert capped < 10.0 and full < 20.0  # grobe Schranke gegen Ausreisser auf geteilter VM


# --------------------------------------------------------------------------- Coal-Referenz


def _coal_compare(n_uniform: int, n_near: int, seed: int):
    coal_ref = pytest.importorskip("coal_reference", reason="Referenz fehlt")
    return coal_ref.compare(s1_world(), s1_scene(), n_uniform, n_near, seed)


def test_against_coal_reference_small():
    bad, stats = _coal_compare(20, 20, 7)
    assert not bad, "\n".join(bad[:10])


@slow
def test_against_coal_reference_g2_500():
    bad, stats = _coal_compare(250, 250, 20261018)
    assert stats["n_neg"] >= 20 and stats["n_near"] >= 20, stats
    assert not bad, f"{len(bad)} Verletzungen:\n" + "\n".join(bad[:20])
