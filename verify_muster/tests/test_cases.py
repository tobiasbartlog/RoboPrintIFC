"""Selbsttests: Fugenwand nach Foto, heutiges Format und Grenzfaelle knapp ueber/unter den Schwellen."""

from __future__ import annotations

import json

import numpy as np
import pytest

from verify_muster import check, rules
from verify_muster.tests import synth
from verify_muster.tests import synth_fugen as sf

N_LAYERS = 4


def _run(tmp_path, rings, mesh=None, **kw):
    mesh = synth.box_mesh(height=N_LAYERS * synth.H) if mesh is None else mesh
    synth.write_run(tmp_path, rings, mesh, **kw)
    code, rep = check.run(tmp_path)
    assert not rep["errors"], rep["errors"]
    return code, rep["parts"][0]


def _failed(part) -> set[str]:
    return set(part["failed_rules"])


def _shifted(rings, dx=0.0, dy=0.0):
    return [dict(r, xy=np.asarray(r["xy"], float) + np.array([dx, dy])) for r in rings]


# ---------------------------------------------------------------- Fugenwand (Foto)


def test_fugenwand_closed_loop_is_green_with_joints_and_nodes(tmp_path):
    rings = synth.stack(lambda L: [sf.fugenwand(28.5)], N_LAYERS)
    code, p = _run(tmp_path, rings)
    assert code == 0, (_failed(p), p["first_counterexample"])
    lay = p["metrics"]["layers"]
    # je Schicht ein Strang, 2 Fugen je Seite (3 Felder), 2 Doppelknoten und 2 Gurtkontakte
    assert all(x["n_paths"] == 1 for x in lay)
    assert all(x["contact_zones_by_type"]["joint"] == 4 for x in lay)
    assert all(x["contact_zones_by_type"]["node"] == 4 for x in lay)
    assert p["metrics"]["joint_spacing_mm"] == {"min": 200.0, "max": 200.0, "mean": 200.0}
    zones = p["rules"]["M7"]["metrics"]["zones_first_layer"]
    joints = [z for z in zones if z["type"] == "joint"]
    assert all(z["min_distance_mm"] == pytest.approx(28.5, abs=0.05) for z in joints)
    assert all(z["overlap_mm"] == pytest.approx(1.5, abs=0.05) for z in joints)
    assert sorted({abs(z["point_P"][0]) for z in joints}) == pytest.approx([100.0], abs=0.5)
    # senkrechter Schichtwechsel in der Gurtmitte, alle Wechsel als link
    m4 = p["rules"]["M4"]["metrics"]
    assert m4["share_vertical"] == 1.0 and m4["n_changes_as_link_in_trajectory"] == N_LAYERS - 1
    # Kehren r = 16 mm: hart erfuellt, Ziel w verfehlt (Warnung)
    assert p["rules"]["M6"]["pass"] and p["rules"]["M6"]["warnings"] > 0
    # Felder sind kurz: laengste gerade Aussenstrecke deutlich unter der Teilung
    assert p["metrics"]["longest_straight_unsupported_outer_mm"] < 200.0


@pytest.mark.parametrize(("contact", "ok"), [(26.0, True), (25.0, False), (24.0, False)])
def test_fugenwand_contact_depth_boundary(tmp_path, contact, ok):
    """(1 - eps)·w = 25,5 mm: 26 mm ist ein gueltiger Kontakt, 25 und 24 mm sind zu tief."""
    code, p = _run(tmp_path, synth.stack(lambda L: [sf.fugenwand(contact)], N_LAYERS))
    if ok:
        assert code == 0, (_failed(p), p["first_counterexample"])
    else:
        assert _failed(p) == {"M2"}, _failed(p)
        f = p["rules"]["M2"]["first"]
        assert f["kind"] == "too_deep" and f["distance_mm"] == pytest.approx(contact, abs=0.05)
        assert f["message"].startswith("zu tiefer Kontakt")
        assert p["first_counterexample"]["rule"] == "M2" and p["first_counterexample"]["layer"] == 0


def test_fugenwand_node_too_deep_is_detected(tmp_path):
    code, p = _run(tmp_path, synth.stack(lambda L: [sf.fugenwand(28.5, node_contact_mm=20.0)], N_LAYERS))
    assert _failed(p) == {"M2"}
    assert abs(p["rules"]["M2"]["first"]["point_P"][0]) < 20.0  # am Knoten ueber der Mitte (x = 0)


@pytest.mark.parametrize(("dx", "ok"), [(0.4, True), (0.6, False)])
def test_layer_change_offset_boundary(tmp_path, dx, ok):
    """Ungerade Schichten um dx versetzt: Ende L -> Anfang L+1 waagrecht dx (Grenze 0,5 mm)."""
    base = sf.fugenwand(28.5)
    rings = synth.stack(lambda L: [_shifted(base, dx if L % 2 else 0.0)], N_LAYERS)
    code, p = _run(tmp_path, rings)
    if ok:
        assert code == 0, (_failed(p), p["first_counterexample"])
    else:
        assert _failed(p) == {"M4"}, _failed(p)
        assert p["rules"]["M4"]["first"]["horizontal_mm"] == pytest.approx(dx, abs=1e-3)


def test_layer_change_as_travel_is_detected(tmp_path):
    rings = synth.stack(lambda L: [sf.fugenwand(28.5)], N_LAYERS)
    last_of_layer0 = max(i for i, r in enumerate(rings) if r["layer"] == 0)
    code, p = _run(tmp_path, rings, breaks={last_of_layer0})
    assert _failed(p) == {"M4"}, _failed(p)
    assert "Travel" in p["rules"]["M4"]["first"]["message"]
    assert p["rules"]["M1"]["pass"]  # je Schicht bleibt der Strang durchgehend


# ---------------------------------------------------------------- Grenzfaelle M3, M5, M6


@pytest.mark.parametrize(("bump", "ok"), [(1.5, True), (3.5, False)])
def test_overhang_boundary(tmp_path, bump, ok):
    """Beule in der obersten Schicht: Ueberstand bump < delta = 2 mm ist erlaubt."""
    def layer(L):
        return [synth.sine_infill(bump=bump if L == N_LAYERS - 1 else 0.0)]

    code, p = _run(tmp_path, synth.stack(layer, N_LAYERS))
    if ok:
        assert code == 0, (_failed(p), p["first_counterexample"])
    else:
        assert _failed(p) == {"M3"}, _failed(p)


@pytest.mark.parametrize(("excess", "ok"), [(0.8, True), (1.3, False)])
def test_inside_part_boundary(tmp_path, excess, ok):
    """Raupenkante steht excess ueber das Teil hinaus (Grenze 1 mm)."""
    mesh = synth.box_mesh(length=600.0 - 2.0 * excess, height=N_LAYERS * synth.H)
    code, p = _run(tmp_path, synth.stack(lambda L: [synth.sine_infill()], N_LAYERS), mesh=mesh)
    if ok:
        assert code == 0, (_failed(p), p["first_counterexample"])
    else:
        assert _failed(p) == {"M5"}, _failed(p)
        assert p["rules"]["M5"]["first"]["excess_mm"] == pytest.approx(excess - 1.0, abs=0.05)


@pytest.mark.parametrize(("r", "ok"), [(15.0, True), (14.0, False)])
def test_radius_boundary_on_closed_ring(tmp_path, r, ok):
    """Geschlossener Stadionring mit Halbkreisen vom Radius r (hart >= w/2 = 15 mm, Toleranz 5 %)."""
    rings = synth.stack(lambda L: [synth.stadium(r)], N_LAYERS)
    mesh = synth.box_mesh(length=300.0 + 2 * r + synth.W, width=2 * r + synth.W,
                          height=N_LAYERS * synth.H)
    code, p = _run(tmp_path, rings, mesh=mesh)
    assert p["rules"]["M6"]["metrics"]["min_radius_mm"] == pytest.approx(r, rel=0.01)
    if ok:
        assert code == 0, (_failed(p), p["first_counterexample"])
        assert p["rules"]["M6"]["warnings"] > 0
    else:
        assert _failed(p) == {"M6"}, _failed(p)


def test_island_change_exempts_layer_change_but_not_overhang(tmp_path):
    """Oeffnung ab Schicht 2: Inselzahl 1 -> 2. Der Wechsel 1 -> 2 ist von M4 ausgenommen; die neuen
    Pfeilerkanten an der Laibung stehen aber nicht auf Raupen der Schicht 1 (keine Querstege) -> M3."""
    import trimesh

    lower = synth.box_mesh(height=20.0)
    upper = synth.pillars_mesh(20.0)
    upper.apply_translation((0.0, 0.0, 20.0))
    mesh = trimesh.util.concatenate([lower, upper])

    def layer(L):
        if L < 2:
            return [synth.two_shells()]
        return [synth.two_shells(r_out=50.0, half_len=125.0, cx=-175.0, x0=55.0),
                synth.two_shells(r_out=50.0, half_len=125.0, cx=175.0, x0=55.0)]

    code, p = _run(tmp_path, synth.stack(layer, N_LAYERS), mesh=mesh)
    m4 = p["rules"]["M4"]
    assert m4["pass"] and m4["metrics"]["n_exempt_island_change"] == 1
    assert [x["n_islands"] for x in p["metrics"]["layers"]] == [1, 1, 2, 2]
    assert "M3" in _failed(p) and p["rules"]["M3"]["first"]["layer"] == 2


# ---------------------------------------------------------------- heutiges Format


def test_todays_format_is_reported_without_crash(tmp_path):
    """Zwei geschlossene Mitre-Ringe je Schicht, jede Schicht gleich (layer_order same): kein Absturz;
    M4 (diagonaler Wechsel ueber Verbinder) und M6 (spitze Ecken) sind rot, M1 und M5 gruen."""
    code, p = _run(tmp_path, synth.stack(lambda L: [synth.mitre_rings()], N_LAYERS, alternate=False))
    assert code == 1
    assert {"M4", "M6"} <= _failed(p)
    assert p["rules"]["M1"]["pass"] and p["rules"]["M5"]["pass"] and p["rules"]["M3"]["pass"]
    assert p["has_pattern_kinds"] is False
    shell = p["rules"]["M7"]["metrics"]["contact_zones_per_m_by_type"]["shell"]
    assert shell > 0  # Aussen- und Innenschale beruehren sich (Abstand w)


def test_scenario_is_read_and_reported(tmp_path):
    synth.write_run(tmp_path / "run", synth.stack(lambda L: [sf.fugenwand(28.5)], N_LAYERS),
                    synth.box_mesh(height=N_LAYERS * synth.H))
    sc = tmp_path / "S4_muster_fugenwand.json"
    sc.write_text(json.dumps({"id": "S4_muster_fugenwand", "params": {
        "layer_order": "alternate", "outfill_pattern": "fugenwand", "pattern_params": {"field_mm": 200}}}))
    out = tmp_path / "rep.json"
    assert check.main([str(tmp_path / "run"), "--scenario", str(sc), "--json", str(out)]) == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["scenario"]["id"] == "S4_muster_fugenwand"
    assert rep["scenario"]["pattern_params"]["outfill_pattern"] == "fugenwand"
    assert rep["constants"]["eps"] == rules.EPS


def test_no_trajectory_mode(tmp_path):
    synth.write_run(tmp_path, synth.stack(lambda L: [sf.fugenwand(28.5)], N_LAYERS),
                    synth.box_mesh(height=N_LAYERS * synth.H))
    (tmp_path / "parts" / "box_m0" / "trajectory.json").unlink()
    assert check.main([str(tmp_path)]) == 2  # Pflichtartefakt fehlt
    assert check.main([str(tmp_path), "--no-trajectory"]) == 0
