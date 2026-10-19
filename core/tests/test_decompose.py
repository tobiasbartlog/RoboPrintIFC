"""Zerlegung (SPEC §5.4) mit injizierter Fake-Machbarkeit."""

import numpy as np
import pytest
import trimesh

from roboprint import decompose as dc
from roboprint import geometry as geo
from roboprint.frames import Placement
from roboprint.ifc import Opening, Wall

PL = Placement(0.0, 300.0, 0.0)


def _wall(mesh, name="test - synthetic wall", openings=()):
    lo, hi = mesh.bounds
    size = hi - lo
    return Wall(
        wall_id="W1",
        name=name,
        mesh=mesh,
        length_mm=float(size[0]),
        thickness_mm=float(size[1]),
        height_mm=float(size[2]),
        volume_mm3=geo.volume(mesh),
        T_GL=np.eye(4),
        openings=list(openings),
    )


def _window_wall():
    """3000 x 200 x 2500 mit Fenster x 1000..1800, z 800..1600."""
    wall = geo.make_box((3000, 200, 2500))
    hole = geo.make_box((800, 400, 800), origin=(1000, -100, 800))
    mesh = geo._from_manifold(geo._to_manifold(wall) - geo._to_manifold(hole))
    return _wall(mesh, openings=[Opening(1000, 1800, 800, 1600)])


def fake_feasible(mesh_P):  # noqa: N803
    """Machbar, wenn Hoehe <= 500 mm und Breite <= 800 mm."""
    w, _, h = mesh_P.extents
    ok = h <= 500 + 1e-6 and w <= 800 + 1e-6
    return ok, 100.0 + (800 - w) / 10 if ok else -5.0, PL if ok else None


def _check_tiling(wall, parts):
    vols = [p.volume_mm3 for p in parts]
    total = sum(vols)
    assert total == pytest.approx(wall.volume_mm3, rel=5e-3)
    union = geo.union([p.mesh_L() for p in parts])
    overlap = total - geo.volume(union)
    assert overlap <= 1e-3 * wall.volume_mm3


def _check_frames(parts):
    for p in parts:
        lo, hi = p.mesh_P.bounds
        assert lo[2] == pytest.approx(0.0, abs=1e-6)
        assert (lo[0] + hi[0]) / 2 == pytest.approx(0.0, abs=1e-6)
        assert (lo[1] + hi[1]) / 2 == pytest.approx(0.0, abs=1e-6)
        assert np.allclose(p.T_LP[:3, :3], np.eye(3))


def test_window_wall_volume_overlap_overhang():
    wall = _window_wall()
    stats = dc.DecomposeStats()
    parts = dc.decompose_wall(wall, {}, fake_feasible, stats=stats)
    assert parts and all(p.feasible and p.placement == PL for p in parts)
    _check_tiling(wall, parts)
    _check_frames(parts)
    assert dc.overhang_violations(wall, parts) == []
    # wie verify.check_run: Teil-Unterkanten in L aus T_LP und part.stl (in P)
    bottoms = [p.T_LP[2, 3] + p.mesh_P.bounds[0][2] for p in parts]
    assert any(abs(z - 1600.0) <= 1.0 for z in bottoms)
    # Spalten, die das Fenster beruehren, haben eine Schnittebene genau auf der Sturzlinie
    touching = [p for p in parts if p.cell_min_L[0] < 1800 and p.cell_max_L[0] > 1000]
    assert touching and all(any(abs(q.cell_max_L[2] - 1600) < 1e-6 for q in touching if q.col == p.col)
                            for p in touching)
    # n = 4 Spalten zu 750 mm: 5 + 6 + 6 + 5 = 22 Module (minimal unter allen Breiten)
    assert stats.chosen.n_cols == 4 and len(parts) == 22
    for p in parts:
        assert p.mesh_P.extents[2] <= 500 + 1e-6 and p.mesh_P.extents[0] <= 800 + 1e-6
    assert len({p.part_id for p in parts}) == len(parts)
    assert parts[0].part_id.startswith("synthetic_wall_r0_c0")


def test_overhang_rule_detects_violation():
    wall = _window_wall()
    parts = dc.decompose_wall(wall, {}, fake_feasible)
    bad = parts[0]
    bad.cell_min_L = np.array([1000.0, 0.0, 1500.0])
    bad.cell_max_L = np.array([1500.0, 200.0, 1700.0])
    assert dc.overhang_violations(wall, [bad])


def test_lexicographic_objective_tie_break_by_d_min():
    """1600 x 200 x 1000: n=2 (800 breit, 2 Reihen) und n=4 (400 breit, 1 Reihe) haben je 4
    Module; n=4 hat den groesseren kleinsten d_min und gewinnt."""
    wall = _wall(geo.make_box((1600, 200, 1000)))

    def feas(m):
        w, _, h = m.extents
        ok = w * h <= 400_000 + 1 and h <= 1000 + 1e-6
        return ok, 200 - w / 10, PL

    stats = dc.DecomposeStats()
    parts = dc.decompose_wall(wall, None, feas, stats=stats)
    assert len(parts) == 4
    assert stats.chosen.n_cols == 4
    assert stats.chosen.d_est_mm == pytest.approx(160.0)
    _check_tiling(wall, parts)


def test_module_count_dominates_d_min():
    """Weniger Module gehen vor, auch wenn ein anderes Raster groesseren d_min haette."""
    wall = _wall(geo.make_box((1600, 200, 400)))

    def feas(m):
        w, _, h = m.extents
        return w <= 800 + 1e-6 and h <= 400 + 1e-6, 1000 - w, PL  # schmal = grosser d_min

    stats = dc.DecomposeStats()
    parts = dc.decompose_wall(wall, None, feas, stats=stats)
    assert stats.chosen.n_cols == 2 and len(parts) == 2


def test_ineligible_wall_has_reason_and_no_parts():
    wall = _wall(geo.make_box((3800, 24, 2200)), name="plumbing wall")
    ok, reason = dc.wall_eligibility(wall, {"bead_width_mm": 30})
    assert not ok and "24.0 mm < 60.0 mm" in reason
    entry = dc.wall_entry(wall, [], {"bead_width_mm": 30})
    assert entry["eligible"] is False and entry["reason"] and entry["part_ids"] == []
    calls = []
    assert dc.decompose_wall(wall, None, lambda m: calls.append(1) or (True, 1, PL)) == []
    assert not calls


def test_hstar_bisection_10mm_and_cache():
    calls = []

    def check(m):
        calls.append(m.extents[2])
        return m.extents[2] <= 437 + 1e-6, 50.0, PL

    hs = dc.HStar(check, step=10, h_min=100)
    h = hs(600, 200, 2000)
    assert 437 - 10 < h <= 437 and h % 10 == pytest.approx(0)
    assert len(calls) <= 10
    n = len(calls)
    assert hs(600, 200, 2000) == h  # Cache: keine neuen Aufrufe
    assert len(calls) == n and hs.hits > 0
    # Monotonie: schmalere Spalte nutzt die Ergebnisse der breiteren
    hs(500, 200, 2000)
    assert len(calls) - n <= 5
    # obere Schranke machbar: ein Aufruf
    hs2 = dc.HStar(check)
    assert hs2(600, 200, 400) == 400 and hs2.calls == 1
    # schon h_min scheitert
    hs3 = dc.HStar(lambda m: (False, None, None))
    assert hs3(600, 200, 2000) == 0.0


def test_hstar_volle_planung_bestaetigt_die_vorpruefung():
    """Die Vorpruefung ist optimistisch (hier bis 1000 mm), die volle Planung schafft nur 800 mm:
    Bei einer Nutzergrenze von 1000 mm wird 800 mm vorgeschlagen, bei 400 mm bleibt es bei 400."""
    full = []

    def verify(m):
        full.append(round(m.extents[2]))
        return m.extents[2] <= 800 + 1e-6, 20.0, PL

    hs = dc.HStar(lambda m: (m.extents[2] <= 1000 + 1e-6, 50.0, PL), step=10, h_min=100, verify=verify)
    assert hs(600, 200, 1000) == 800
    assert len(full) <= 6 and all(h % 50 == 0 for h in full)
    n = len(full)
    assert hs(600, 200, 400) == 400 and len(full) == n  # aus dem Cache der vollen Planung (Monotonie)
    hs2 = dc.HStar(lambda m: (True, 50.0, PL), verify=verify)
    assert hs2(600, 200, 400) == 400 and len(full) == n + 1  # machbare Grenze: ein voller Plan


def test_nonbox_top_like_house_left():
    """Schraege Oberkante quer zur Wand (wie 'house left'): Teile oben sind keine Quader."""
    L, T, H0, H1 = 1600.0, 200.0, 900.0, 1100.0  # noqa: N806
    pts = [(x, y, 0.0) for x in (0, L) for y in (0, T)] + [(x, 0.0, H1) for x in (0, L)]
    pts += [(x, T, H0) for x in (0, L)]
    wall = _wall(trimesh.convex.convex_hull(np.array(pts)), name="house - outer wall - house left")
    stats = dc.DecomposeStats()
    parts = dc.decompose_wall(wall, None, fake_feasible, stats=stats)
    assert all(p.feasible for p in parts)
    _check_tiling(wall, parts)
    _check_frames(parts)
    top = [p for p in parts if p.cell_max_L[2] >= H1 - 1e-6]
    assert top and all(p.volume_mm3 < np.prod(p.mesh_P.extents) * 0.999 for p in top)
    assert parts[0].part_id.startswith("house_left_r")


def test_refines_cells_the_planner_rejects():
    """Vorpruefung grosszuegig, volle Pruefung nur bis 250 mm Hoehe: Zellen werden geteilt."""
    wall = _wall(geo.make_box((600, 200, 400)))

    def full(m):
        return m.extents[2] <= 250 + 1e-6, 80.0, PL

    parts = dc.decompose_wall(wall, None, full, prefeasible=lambda m: (True, 99.0, PL))
    assert len(parts) == 2 and all(p.feasible for p in parts)
    assert sorted(p.part_id for p in parts) == ["synthetic_wall_r0_c0_s0", "synthetic_wall_r0_c0_s1"]
    _check_tiling(wall, parts)


def test_unfeasible_after_min_size_keeps_cause():
    wall = _wall(geo.make_box((600, 200, 400)))
    parts = dc.decompose_wall(
        wall,
        {"max_refine_depth": 2},
        lambda m: (False, -3.0, None, "Kollision link_3 / table"),
        prefeasible=lambda m: (True, 99.0, PL),
    )
    assert parts and not any(p.feasible for p in parts)
    assert all("link_3" in p.feasibility.cause for p in parts)
    assert all(p.status == "nicht machbar" for p in parts)
    _check_tiling(wall, parts)


def test_identical_parts_hit_geometry_cache():
    wall = _wall(geo.make_box((2400, 200, 1000)))
    stats = dc.DecomposeStats()
    parts = dc.decompose_wall(wall, None, fake_feasible, stats=stats)
    assert len(parts) == 6  # 3 x 800, 2 Reihen zu 500
    assert stats.part_checks == 1 and stats.part_cache_hits == 5


def test_split_rows_prefers_layer_multiples():
    cuts = dc._split_rows(0.0, 1005.0, 600.0, 10.0)
    assert cuts == [510.0]
    assert dc._split_rows(0.0, 400.0, 600.0, 10.0) == []


def test_decompose_walls_batches_unique_geometry_across_walls():
    """Zwei gleich dicke Waende: H*- und Geometrie-Cache wanduebergreifend, volle Pruefung
    rundenweise gebuendelt; ungeeignete Wand liefert keine Teile."""
    a = _wall(geo.make_box((2400, 200, 1000)), name="x - wall a")
    b = _wall(geo.make_box((1600, 200, 1000)), name="x - wall b")
    b.wall_id = "W2"
    thin = _wall(geo.make_box((1000, 24, 1000)), name="x - thin")
    thin.wall_id = "W3"
    batches = []

    def many(meshes):
        batches.append(len(meshes))
        return [fake_feasible(m) for m in meshes]

    stats = dc.DecomposeStats()
    parts = dc.decompose_walls([a, thin, b], None, feasible_many=many, prefeasible=fake_feasible, stats=stats)
    assert batches == [1]  # alle Teile 800 x 200 x 500: eine Planung
    assert {p.wall_id for p in parts} == {"W1", "W2"}
    assert sum(p.wall_id == "W1" for p in parts) == 6 and sum(p.wall_id == "W2" for p in parts) == 4
    assert set(stats.grids) == {"W1", "W2"}
    for w in (a, b):
        _check_tiling(w, [p for p in parts if p.wall_id == w.wall_id])
    entry = dc.wall_entry(b, parts)
    assert entry["eligible"] and len(entry["part_ids"]) == 4
