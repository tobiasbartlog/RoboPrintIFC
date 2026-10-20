"""Selbsttests des Muster-Orakels: gueltige Grundfaelle sind gruen, jedes Gegenbeispiel wird erkannt."""

from __future__ import annotations

import json

import numpy as np
import pytest

from verify_muster import check, geometry, rules
from verify_muster.tests import synth

N_LAYERS = 4


def _run(tmp_path, rings, mesh=None, **kw):
    mesh = synth.box_mesh(height=N_LAYERS * synth.H) if mesh is None else mesh
    synth.write_run(tmp_path, rings, mesh, **kw)
    code, rep = check.run(tmp_path)
    assert not rep["errors"], rep["errors"]
    return code, rep["parts"][0]


def _failed(part) -> set[str]:
    return set(part["failed_rules"])


# ---------------------------------------------------------------- gueltige Faelle


def test_two_shells_alternating_is_green(tmp_path):
    code, p = _run(tmp_path, synth.stack(lambda L: [synth.two_shells()], N_LAYERS))
    assert code == 0, _failed(p)
    assert p["rules"]["M4"]["metrics"]["share_vertical"] == 1.0
    # Naht bei alternate: 0 -> 1 am Ende der Innenbahn (y = -55, 45 mm vom Rand, innen), 1 -> 2 am
    # Anfang der Aussenbahn (y = -85, auf der Sichtflaeche: Warnung), 2 -> 3 wieder innen
    assert p["rules"]["M4"]["metrics"]["n_seam_on_surface"] == 1
    assert p["rules"]["M4"]["warnings"] == 1
    assert p["rules"]["M4"]["metrics"]["n_changes_as_link_in_trajectory"] == N_LAYERS - 1
    assert p["rules"]["M6"]["warnings"] == 0
    assert p["rules"]["M1"]["metrics"]["groups_continuous"] == N_LAYERS
    m = p["metrics"]
    assert m["layers"][0]["n_islands"] == 1 and m["layers"][0]["n_paths"] == 1
    # Aussenbahn ohne Stege: Oberkante 570 - 2·60 = 450 mm gerade, dazu je Bogenende ~7 mm innerhalb
    # der Geradheitstoleranz von 1 mm
    assert 450.0 <= m["longest_straight_unsupported_outer_mm"] <= 470.0


def test_sine_infill_is_green_with_contacts(tmp_path):
    code, p = _run(tmp_path, synth.stack(lambda L: [synth.sine_infill()], N_LAYERS))
    assert code == 0, (_failed(p), [p["rules"][r]["first"] for r in _failed(p)])
    m7 = p["rules"]["M7"]
    assert m7["metrics"]["contact_zones_per_m"] > 0
    # Kontakte an Tal (unten) und Berg (oben): 2 Zonen je Schicht
    assert all(x["contact_zones"] >= 2 for x in p["metrics"]["layers"])
    # Stuetzpunkte durch das Infill verkuerzen die gerade Aussenstrecke unter die volle Laenge 485 mm
    assert p["metrics"]["longest_straight_unsupported_outer_mm"] < 480.0


def test_two_islands_alternating_is_green(tmp_path):
    def layer(L):
        return [synth.two_shells(r_out=50.0, half_len=125.0, cx=-175.0, x0=55.0),
                synth.two_shells(r_out=50.0, half_len=125.0, cx=175.0, x0=55.0)]

    rings = synth.stack(layer, N_LAYERS)
    code, p = _run(tmp_path, rings, mesh=synth.pillars_mesh(N_LAYERS * synth.H))
    assert code == 0, (_failed(p), [p["rules"][r]["first"] for r in _failed(p)])
    assert all(x["n_islands"] == 2 and x["n_paths"] == 2 for x in p["metrics"]["layers"])
    assert p["rules"]["M6"]["warnings"] > 0  # Innenradius 20 mm < w: Ziel verfehlt, hart erfuellt


def test_cli_writes_report_and_exit_codes(tmp_path):
    synth.write_run(tmp_path / "ok", synth.stack(lambda L: [synth.two_shells()], N_LAYERS),
                    synth.box_mesh(height=N_LAYERS * synth.H))
    out = tmp_path / "rep.json"
    assert check.main([str(tmp_path / "ok"), "--json", str(out)]) == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["passed"]
    assert set(rep["parts"][0]["rules"]) == {"M1", "M2", "M3", "M4", "M5", "M6", "M6b", "M7"}
    synth.write_run(tmp_path / "bad", synth.stack(lambda L: [synth.two_shells()], N_LAYERS, alternate=False),
                    synth.box_mesh(height=N_LAYERS * synth.H))
    assert check.main([str(tmp_path / "bad")]) == 1
    assert (tmp_path / "bad" / "check_muster.json").is_file()
    assert check.main([str(tmp_path / "leer")]) == 2


# ---------------------------------------------------------------- Gegenbeispiele


def test_crossing_is_detected(tmp_path):
    def tail(p):  # vom Sinusende quer zurueck ueber den Sinus (kreuzt bei x ≈ 10)
        return synth.line(p, (-60.0, 0.0))

    code, p = _run(tmp_path, synth.stack(lambda L: [synth.sine_infill(extra_tail=tail)], N_LAYERS))
    assert code == 1 and "M2" in _failed(p)
    first = p["rules"]["M2"]["first"]
    assert first["message"].startswith("Kreuzung") and first["layer"] == 0


def test_overhang_is_detected(tmp_path):
    def layer(L):  # nur die oberste Schicht hat eine Beule (12 mm) im Infill
        return [synth.sine_infill(bump=12.0 if L == N_LAYERS - 1 else 0.0)]

    code, p = _run(tmp_path, synth.stack(layer, N_LAYERS))
    assert _failed(p) == {"M3"}, _failed(p)
    assert p["rules"]["M3"]["first"]["layer"] == N_LAYERS - 1


def test_seam_on_outer_face_is_warned(tmp_path):
    """Sinus-Muster umgekehrt (Infill -> Aussenbahn): gerade Schichten enden am Anfang der Aussenbahn,
    die Naht liegt auf der Sichtflaeche -> Warnung, keine harte Verletzung (Wechsel 0 -> 1 und 2 -> 3)."""
    def layer(L):
        rs = synth.sine_infill()
        return [[dict(r, xy=r["xy"][::-1]) for r in reversed(rs)]]

    code, p = _run(tmp_path, synth.stack(layer, N_LAYERS))
    assert code == 0, _failed(p)
    m4 = p["rules"]["M4"]
    assert m4["metrics"]["n_seam_on_surface"] == 2 and m4["warnings"] == 2


def test_diagonal_layer_change_is_detected(tmp_path):
    code, p = _run(tmp_path, synth.stack(lambda L: [synth.two_shells()], N_LAYERS, alternate=False))
    assert _failed(p) == {"M4"}, _failed(p)
    f = p["rules"]["M4"]["first"]
    assert f["layer"] == 0 and f["horizontal_mm"] > 10.0
    assert p["rules"]["M4"]["metrics"]["share_vertical"] == 0.0


def test_gap_in_strand_trajectory_is_detected(tmp_path):
    rings = synth.stack(lambda L: [synth.two_shells()], N_LAYERS)
    # Planer setzt in Schicht 1 zwischen Ring 2 und 3 einen Travel (retract/lift/transfer/lower/approach)
    code, p = _run(tmp_path, rings, breaks={2})
    assert _failed(p) == {"M1"}, _failed(p)
    f = p["rules"]["M1"]["first"]
    assert f["layer"] == 1 and "unterbrochen" in f["message"]


def test_gap_in_strand_toolpath_is_detected(tmp_path):
    rings = synth.stack(lambda L: [synth.two_shells()], N_LAYERS)
    rings[2]["link_next"] = False  # zwei Schichtpfade in einer Insel
    code, p = _run(tmp_path, rings)
    assert "M1" in _failed(p)
    assert any("2 Schichtpfade" in e["message"] for e in p["rules"]["M1"]["examples"])


def test_missing_top_layer_is_detected(tmp_path):
    """toolpath endet eine Schicht zu frueh (Teil 4 Schichten hoch, Ringe nur fuer 3): M1."""
    rings = synth.stack(lambda L: [synth.two_shells()], N_LAYERS - 1)
    code, p = _run(tmp_path, rings)
    assert _failed(p) == {"M1"}, _failed(p)
    f = p["rules"]["M1"]["first"]
    assert f["layer"] == N_LAYERS - 1 and f["n_paths"] == 0


def test_empty_toolpath_is_not_green(tmp_path):
    synth.write_run(tmp_path, synth.stack(lambda L: [synth.two_shells()], 1),
                    synth.box_mesh(height=N_LAYERS * synth.H))
    pdir = tmp_path / "parts" / "box_m0"
    tp = json.loads((pdir / "toolpath.json").read_text(encoding="utf-8"))
    tp["rings"] = []
    (pdir / "toolpath.json").write_text(json.dumps(tp), encoding="utf-8")
    (pdir / "trajectory.json").unlink()
    code, rep = check.run(tmp_path, need_trajectory=False)
    assert code == 1 and "M1" in rep["parts"][0]["failed_rules"]


def test_print_outside_part_is_detected(tmp_path):
    mesh = synth.box_mesh(length=560.0, height=N_LAYERS * synth.H)
    code, p = _run(tmp_path, synth.stack(lambda L: [synth.sine_infill()], N_LAYERS), mesh=mesh)
    assert _failed(p) == {"M5"}, _failed(p)
    assert p["rules"]["M5"]["first"]["excess_mm"] > 10.0


def test_too_tight_radius_is_detected(tmp_path):
    code, p = _run(tmp_path, synth.stack(lambda L: [synth.two_shells(r_out=35.0)], N_LAYERS))
    assert _failed(p) == {"M6"}, _failed(p)
    assert p["rules"]["M6"]["first"]["radius_mm"] < 0.5 * synth.W


def test_print_over_opening_is_detected(tmp_path):
    mesh = synth.pillars_mesh(N_LAYERS * synth.H)
    code, p = _run(tmp_path, synth.stack(lambda L: [synth.two_shells()], N_LAYERS), mesh=mesh)
    assert {"M5", "M1"} <= _failed(p)
    assert any("mehrere Inseln" in e["message"] for e in p["rules"]["M1"]["examples"])
    pt = p["rules"]["M5"]["first"]["point_P"]
    assert -50.0 <= pt[0] <= 50.0  # der schlimmste Punkt liegt ueber der Oeffnung


def test_trajectory_off_toolpath_is_detected(tmp_path):
    def shift(traj):
        out = list(traj)
        i = next(k for k, s in enumerate(out) if s[1] == "print" and s[2] == 1)
        p, kind, r, k = out[i + 5]
        out[i + 5] = (p + np.array([0.0, 2.0, 0.0]), kind, r, k)
        return out

    code, p = _run(tmp_path, synth.stack(lambda L: [synth.two_shells()], N_LAYERS), traj_mutator=shift)
    assert _failed(p) == {"M6b"}, _failed(p)


def _drop_print(ring: int, a: int, b: int):
    """Mutator: entfernt die print-Samples a..b-1 (Zaehlung innerhalb des Rings) aus der Trajektorie."""
    def mut(traj):
        pos = [k for k, s in enumerate(traj) if s[1] == "print" and s[2] == ring]
        drop = set(pos[a:b])
        return [s for k, s in enumerate(traj) if k not in drop]
    return mut


def test_print_gap_inside_ring_is_detected(tmp_path):
    """Strang laeuft weiter (keine Unterbrechung, jedes Sample auf dem Ring), aber die Duese schneidet
    die rechte untere Kehre ab (80 mm Bogen als Sehne): ≈ 6 mm Raupenlaenge fehlen. M1 sieht das
    nicht, M6b (Abdeckung) schon.
    Ausgelassene Samples auf einer Geraden sind dagegen keine Luecke (die Duese faehrt dieselbe Gerade)."""
    rings = synth.stack(lambda L: [synth.two_shells()], N_LAYERS)
    # Ring 0: Unterkante ab x = -100 in 2-mm-Samples bis x = 225 (Sample 163), dann Kehre r = 60
    code, p = _run(tmp_path, rings, traj_mutator=_drop_print(0, 165, 205))
    assert _failed(p) == {"M6b"}, _failed(p)
    f = p["rules"]["M6b"]["first"]
    assert "uebersprungen" in f["message"] and f["gap_mm"] > 5.0 and f["ring"] == 0
    code, p = _run(tmp_path / "gerade", rings, traj_mutator=_drop_print(0, 20, 100))
    assert code == 0, _failed(p)


def test_print_backwards_is_detected(tmp_path):
    """Zwei print-Samples vertauscht: die Duese faehrt ein Stueck zurueck (Doppelraupe)."""
    def swap(traj):
        out = list(traj)
        pos = [k for k, s in enumerate(out) if s[1] == "print" and s[2] == 2]
        i, j = pos[10], pos[14]
        out[i], out[j] = out[j], out[i]
        return out

    code, p = _run(tmp_path, synth.stack(lambda L: [synth.two_shells()], N_LAYERS), traj_mutator=swap)
    assert _failed(p) == {"M6b"}, _failed(p)


def test_oracle_never_imports_roboprint_or_verify():
    """Unabhaengigkeit (AUFTRAG, Rahmen): kein Modul von verify_muster importiert roboprint oder verify."""
    import ast
    from pathlib import Path

    root = Path(check.__file__).parent
    for f in root.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                top = n.split(".")[0]
                assert top not in ("roboprint", "verify", "core"), f"{f.name} importiert {n}"


# ---------------------------------------------------------------- Methoden


@pytest.mark.parametrize("r", [15.0, 30.0, 60.0])
@pytest.mark.parametrize("seg", [0.5, 2.0, 7.0])
def test_window_radius_independent_of_sampling(r, seg):
    """Kreisbogen mit Sehnenlaenge seg (bis zum Sehnenfehler ~0,4 mm): Radius innerhalb R_REL_TOL."""
    n = int(np.ceil(1.5 * np.pi * r / seg))
    pts = synth.arc((0, 0), r, 0.0, 1.5 * np.pi, step=1.5 * np.pi * r / n)
    R, _, _, ch = geometry.window_radius(pts, 1.0, 15.0, with_chord=True)
    tol = rules.radius_tolerance(ch, r, 15.0)
    assert len(R) and np.all(R >= r * (1 - tol)) and R.max() <= r * (1 + rules.R_REL_TOL)
    assert ch.max() == pytest.approx(seg, rel=0.15)
    if seg <= 2.0:  # fein abgetastet: Toleranz hoechstens ~1 %
        assert tol.max() <= 0.011


def test_window_radius_sharp_corner_and_reversal():
    corner = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0]])
    R, _, _ = geometry.window_radius(corner, 1.0, 15.0)
    assert R.min() == pytest.approx(15.0 / np.sqrt(2.0), rel=0.02)
    back = np.array([[0.0, 0.0], [100.0, 0.0], [0.0, 0.0]])
    R, _, _ = geometry.window_radius(back, 1.0, 15.0)
    assert R.min() == 0.0


def test_graph_distance_closure_is_a_node():
    sq = np.array([[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]], float)
    out = np.array([[0, 0], [0, -50]], float)
    P = geometry.build_path(0, [0, 1], {0: sq, 1: out}, {0: "outer", 1: "web"}, 2.0)
    i = np.flatnonzero(P.elem == 0)[1]  # 2 mm hinter dem Start im geschlossenen Ring
    j = np.flatnonzero(P.elem == 2)[-1]  # Ende des offenen Rings (50 mm hinter dem Schliesspunkt)
    assert geometry.graph_distance(P, np.array([i]), np.array([j]))[0] == pytest.approx(52.0)
