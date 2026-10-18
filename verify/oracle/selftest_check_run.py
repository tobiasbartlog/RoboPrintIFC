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
    tr["status"][5] = "ok"  # d_mm bleibt < 50
    tr["summary"]["n_ok"] += 1
    tr["summary"]["n_warn"] -= 1
    _save(p, tr)
    ok, rep = _check(minirun_copy)
    assert not ok and any("status passt nicht zu d_mm" in e for e in rep["errors"])


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
