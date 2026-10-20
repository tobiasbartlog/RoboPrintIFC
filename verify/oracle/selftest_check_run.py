"""Selbsttests von check_run auf einem konstruierten Mini-Laufordner (ohne roboprint)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from verify.check_run import run


def _traj(run_dir: Path) -> tuple[Path, dict]:
    p = run_dir / "parts" / "box_0" / "trajectory.json"
    return p, json.loads(p.read_text(encoding="utf-8"))


def _save(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj), encoding="utf-8")


def _check(run_dir: Path) -> tuple[bool, dict]:
    return run(run_dir, run_dir / "scenario.json", jobs=1)


def test_minirun_passes(minirun_copy):
    ok, rep = _check(minirun_copy)
    assert ok, rep["errors"]
    m = rep["parts"]["box_0"]
    assert m["coverage_min"] >= 0.95 and m["max_path_dev_mm"] < 0.01
    assert m["checker_d_min_lb_mm"] >= 10.0


def test_manipulated_status_fails(minirun_copy):
    """warn -> ok mit passendem d_mm, obwohl der Pruefer d < 50 - 12 sieht: eigener Status != Pruefer."""
    p, tr = _traj(minirun_copy)
    i = int(np.argmin(tr["d_mm"]))
    tr["status"][i] = "ok"
    tr["d_mm"][i] = 80.0
    tr["summary"]["n_ok"] += 1
    tr["summary"]["n_warn"] -= 1
    tr["summary"]["d_min_mm"] = float(min(tr["d_mm"]))
    _save(p, tr)
    ok, rep = _check(minirun_copy)
    assert not ok
    assert any("eigener Status != Pruefer-Status" in e for e in rep["errors"]), rep["errors"]


def test_inconsistent_status_fails(minirun_copy):
    p, tr = _traj(minirun_copy)
    # Paar ausserhalb des Druckstands mit d_mm = 15 < d_target = 50 verlangt warn (am Druckstand waeren
    # 20 <= d < 50 mit ok vereinbar, Nutzerentscheidung 19.10.2026)
    tr["status"][5] = "ok"
    tr["d_mm"][5] = 15.0
    tr["pair"][5] = ["link_3", "table"]
    tr["summary"]["n_ok"] += 1
    tr["summary"]["n_warn"] -= 1
    _save(p, tr)
    ok, rep = _check(minirun_copy)
    assert not ok and any("status passt nicht zu d_mm" in e for e in rep["errors"])


def test_allowed_statuses_per_pair_target():
    """Statusregel (Nutzerentscheidung 19.10.2026): Druckstand warnt unter 20 mm, sonst unter 50 mm."""
    from verify.oracle.run_checks import Params, allowed_statuses

    prm = Params()
    assert allowed_statuses(-0.001, True, prm) == {"collision"}
    assert allowed_statuses(15.0, True, prm) == {"warn"}
    assert allowed_statuses(41.0, True, prm) == {"ok", "warn"}  # ok, wenn auch kein anderes Paar < 50
    assert allowed_statuses(55.0, True, prm) == {"ok"}
    assert allowed_statuses(41.0, False, prm) == {"warn"}
    assert allowed_statuses(55.0, False, prm) == {"ok"}
    assert prm.printed_shift == 30.0 and prm.status_thresholds() == [49.0, 50.0, 62.0]


def test_large_step_fails(minirun_copy):
    """Zwei Druck-Samples entfernen: TCP-Sprung > 5 mm."""
    p, tr = _traj(minirun_copy)
    i = tr["kind"].index("print") + 3
    for key in ("t_s", "q", "tcp", "layer", "ring", "kind", "branch", "status", "d_mm", "pair", "witness",
                "psi_rad"):
        del tr[key][i:i + 2]
    tr["summary"]["n"] -= 2
    tr["summary"]["n_warn"] -= 2
    _save(p, tr)
    ok, rep = _check(minirun_copy)
    assert not ok
    assert any("TCP-Schritt > 5 mm" in e for e in rep["errors"]), rep["errors"]


def test_wrong_layer_rule_fails(minirun_copy):
    p, tr = _traj(minirun_copy)
    i = tr["kind"].index("lift")
    tr["layer"][i] -= 1
    _save(p, tr)
    ok, rep = _check(minirun_copy)
    assert not ok and any("layer-Regel" in e for e in rep["errors"])


def test_tcp_mismatch_fails(minirun_copy):
    p, tr = _traj(minirun_copy)
    i = tr["kind"].index("print") + 10
    tr["tcp"][i][0] += 0.2
    _save(p, tr)
    ok, rep = _check(minirun_copy)
    assert not ok and any("tcp[i] != FK(q[i])" in e for e in rep["errors"])


def test_collision_detected_mode(minirun_copy):
    """S3-Logik: Pruefer bestaetigt eine gemeldete Kollision nur, wenn sie wirklich vorliegt."""
    scen = json.loads((minirun_copy / "scenario.json").read_text())
    scen["expect"] = {"parts": "collision_detected"}
    (minirun_copy / "scenario.json").write_text(json.dumps(scen))
    p, tr = _traj(minirun_copy)
    i = tr["kind"].index("print") + 3
    tr["status"][i] = "collision"
    tr["d_mm"][i] = -1.0
    _save(p, tr)
    ok, rep = _check(minirun_copy)
    assert not ok and any("bestaetigt" in e for e in rep["errors"]), rep["errors"]


def test_ifc_wall_measurement():
    from verify.oracle.robot_oracle import ROOT
    from verify.oracle.run_geometry import ifc_walls

    walls = {w["name"]: w for w in ifc_walls(ROOT / "examples" / "Building-Architecture.ifc")}
    assert abs(walls["plumbing wall"]["thickness_mm"] - 24.0) < 0.1
    assert abs(walls["house - outer wall - house left"]["thickness_mm"] - 200.0) < 0.1
    assert all(w["volume_mm3"] > 1e8 for w in walls.values())


def test_table_outline_and_coverage():
    from shapely.geometry import box as sbox

    from verify.oracle.run_geometry import coverage, table_top_outline

    top = table_top_outline()
    assert abs(top.area - 1600 * 1250) < 1.0
    sec = sbox(-100, -50, 100, 50)
    ring = np.array([[-85, -35], [85, -35], [85, 35], [-85, 35], [-85, -35]], dtype=float)
    cov_one, area = coverage(sec, [ring], 2, 30.0)
    assert abs(area - 200 * 100) < 1e-6 and 0.5 < cov_one < 0.95
    inner = np.array([[-55, -5], [55, -5], [55, 5], [-55, 5], [-55, -5]], dtype=float)
    cov_two, _ = coverage(sec, [ring, inner], 2, 30.0)
    assert cov_two >= 0.95


# --------------------------------------------------------------------------- Teil fuer Teil, Inhalts-Cache


def _duplicate(run_dir: Path, src: str = "box_0", dst: str = "box_1") -> Path:
    """Kopie eines Teils unter neuer part_id (wie identische Module einer Wand)."""
    import shutil

    sdir, ddir = run_dir / "parts" / src, run_dir / "parts" / dst
    shutil.copytree(sdir, ddir)
    for name in ("part.json", "toolpath.json", "trajectory.json"):  # nur die part_id im Text tauschen
        text = (ddir / name).read_text(encoding="utf-8")
        assert text.count(f'"{src}"') == 1
        (ddir / name).write_text(text.replace(f'"{src}"', f'"{dst}"'), encoding="utf-8")
    summ = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    entry = next(p for p in summ["parts"] if p["part_id"] == src)
    summ["parts"].append({**entry, "part_id": dst})
    _save(run_dir / "summary.json", summ)
    return ddir


def test_duplicate_checked_once(minirun_copy):
    _duplicate(minirun_copy)
    ok, rep = _check(minirun_copy)
    assert ok, rep["errors"]
    assert rep["dedup"] == {"parts": 2, "checked": 1}
    assert rep["parts"]["box_1"]["same_as"] == "box_0"
    assert "same_as" not in rep["parts"]["box_0"]


def test_manipulated_duplicate_not_cached(minirun_copy):
    """Kleine Abweichung in der Trajektorie: das Duplikat wird eigenstaendig geprueft und faellt durch."""
    ddir = _duplicate(minirun_copy)
    tr = json.loads((ddir / "trajectory.json").read_text(encoding="utf-8"))
    i = tr["kind"].index("print") + 10
    tr["tcp"][i][0] += 0.2
    _save(ddir / "trajectory.json", tr)
    ok, rep = _check(minirun_copy)
    assert not ok and rep["dedup"] == {"parts": 2, "checked": 2}
    assert "same_as" not in rep["parts"]["box_1"]
    bad = [e for e in rep["errors"] if "tcp[i] != FK(q[i])" in e]
    assert bad and all(e.startswith("box_1") for e in bad), rep["errors"]


def test_hardlinked_duplicate_and_parallel(minirun_copy):
    """Hardlinks zaehlen als identisch; jobs = 2 (Pool, Teil fuer Teil) liefert dasselbe wie jobs = 1."""
    import os

    ddir = _duplicate(minirun_copy)
    src = minirun_copy / "parts" / "box_0"
    for name in ("trajectory.json", "toolpath.json", "part.stl"):
        (ddir / name).unlink()
        os.link(src / name, ddir / name)
    ok1, rep1 = _check(minirun_copy)
    ok2, rep2 = run(minirun_copy, minirun_copy / "scenario.json", jobs=2)
    assert ok1 and ok2, (rep1["errors"], rep2["errors"])
    assert rep1["dedup"]["checked"] == rep2["dedup"]["checked"] == 1
    assert rep1["parts"] == rep2["parts"]


# --------------------------------------------------------------------------- Strang (SPEC §5.3, ARTEFAKTE)


def _toolpath(run_dir: Path) -> tuple[Path, dict]:
    p = run_dir / "parts" / "box_0" / "toolpath.json"
    return p, json.loads(p.read_text(encoding="utf-8"))


def _link_samples(tr: dict, ring: int) -> list[int]:
    pairs = zip(tr["kind"], tr["ring"], strict=True)
    return [i for i, (k, r) in enumerate(pairs) if k == "link" and r == ring]


def _set_link_max(run_dir: Path, value: float) -> None:
    summ = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    summ["params"]["link_max_mm"] = value
    _save(run_dir / "summary.json", summ)


def test_strand_minirun_passes(minirun_strand_copy):
    """Ring 0 -> 1 (gleiche Schicht) -> 2 (Schichtwechsel) ueber Verbinder, Travel zu Ring 3."""
    ok, rep = _check(minirun_strand_copy)
    assert ok, rep["errors"]
    m = rep["parts"]["box_0"]
    assert m["n_links"] == 2 and m["max_link_dev_mm"] < 0.01 and abs(m["max_link_len_mm"] - 42.43) < 0.01
    assert m["coverage_min"] >= 0.95 and m["branch_changes_in_strands"] == 0
    assert m["checker_d_min_lb_mm"] >= 10.0


def test_link_without_link_next_fails(minirun_strand_copy):
    p, tp = _toolpath(minirun_strand_copy)
    tp["rings"][0]["link_next"] = False
    _save(p, tp)
    ok, rep = _check(minirun_strand_copy)
    assert not ok and any("link_next ist nicht true" in e for e in rep["errors"]), rep["errors"]


def test_link_beside_line_fails(minirun_strand_copy):
    """Ein Verbinder-Sample 1,5 mm seitlich der Geraden (q per IK, tcp = FK): Verbinder neben der Geraden."""
    from verify.oracle.minirun import _Builder
    from verify.oracle.robot_oracle import T_to_pose7

    p, tr = _traj(minirun_strand_copy)
    _, tp = _toolpath(minirun_strand_copy)
    idx = _link_samples(tr, 1)
    i = idx[len(idx) // 2]
    A = np.array(tp["rings"][0]["waypoints"][-1][:3])
    B = np.array(tp["rings"][1]["waypoints"][0][:3])
    n = np.array([-(B - A)[1], (B - A)[0], 0.0])
    b = _Builder()
    q = b.ik(np.array(tr["tcp"][i][:3]) + 1.5 * n / np.linalg.norm(n), np.array(tr["q"][i]))
    tr["q"][i] = q.tolist()
    tr["tcp"][i] = T_to_pose7(b.tcp_W(q)).tolist()
    _save(p, tr)
    ok, rep = _check(minirun_strand_copy)
    assert not ok and any("neben der Geraden" in e for e in rep["errors"]), rep["errors"]


def test_link_outside_section_fails(minirun_strand_copy):
    """Senkrechte Bohrung (r = 4 mm) im Teil genau unter dem Verbinder Ring 0 -> 1: Verbinder ueber einer
    Oeffnung."""
    import trimesh

    from verify.oracle.collision_oracle import box_part_mesh
    from verify.oracle.minirun import SIZE

    hole = trimesh.creation.cylinder(radius=4.0, height=3 * SIZE[2], sections=32)
    hole.apply_translation((-70.0, -20.0, SIZE[2] / 2))  # Mitte zwischen (-85, -35) und (-55, -5), Frame P
    mesh = trimesh.boolean.difference([box_part_mesh(SIZE), hole], engine="manifold")
    mesh.export(str(minirun_strand_copy / "parts" / "box_0" / "part.stl"))
    ok, rep = _check(minirun_strand_copy)
    assert not ok, rep["errors"]
    assert any("verlaesst den Querschnitt der Schicht 0" in e for e in rep["errors"]), rep["errors"]


def test_link_too_long_or_disabled_fails(minirun_strand_copy):
    _set_link_max(minirun_strand_copy, 40.0)
    ok, rep = _check(minirun_strand_copy)
    assert not ok and any("> link_max_mm 40" in e for e in rep["errors"]), rep["errors"]
    _set_link_max(minirun_strand_copy, 0.0)
    ok, rep = _check(minirun_strand_copy)
    assert not ok and any("link_max_mm = 0" in e for e in rep["errors"]), rep["errors"]


def test_link_layer_rule_fails(minirun_strand_copy):
    """Verbinder beim Schichtwechsel (Ring 1 -> 2) zaehlt die Schicht des folgenden Rings (k = 1)."""
    p, tr = _traj(minirun_strand_copy)
    i = _link_samples(tr, 2)[3]
    assert tr["layer"][i] == 1
    tr["layer"][i] = 0
    _save(p, tr)
    ok, rep = _check(minirun_strand_copy)
    assert not ok and any("layer-Regel" in e for e in rep["errors"]), rep["errors"]


def test_branch_change_in_link_fails(minirun_strand_copy):
    p, tr = _traj(minirun_strand_copy)
    i = _link_samples(tr, 1)[5]
    tr["branch"][i] = (tr["branch"][i] + 1) % 8
    _save(p, tr)
    ok, rep = _check(minirun_strand_copy)
    assert not ok and any("Zweigwechsel innerhalb eines Strangs" in e for e in rep["errors"]), rep["errors"]
    assert any("zweig_wechsel_in_ringen = 0, gezaehlt 2" in e for e in rep["errors"]), rep["errors"]


def test_summary_branch_changes_must_match(minirun_strand_copy):
    p, tr = _traj(minirun_strand_copy)
    tr["summary"]["zweig_wechsel_in_ringen"] = 1
    _save(p, tr)
    ok, rep = _check(minirun_strand_copy)
    assert not ok, rep["errors"]
    assert any("zweig_wechsel_in_ringen = 1, gezaehlt 0" in e for e in rep["errors"]), rep["errors"]
