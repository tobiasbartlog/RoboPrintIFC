"""Unabhaengiger Pruefer fuer einen Laufordner (G3/G4, spec/SPEC.md §11, spec/ARTEFAKTE.md).

    python -m verify.check_run <laufordner> --scenario <szenario.json> [--jobs N]

Schreibt <laufordner>/check.json und endet mit 0 genau dann, wenn alle Kriterien der Erwartung
(`expect` im Szenario) erfuellt sind. Rechnet mit Pinocchio/Coal auf URDF und Roh-Meshes; importiert
roboprint nicht. Methoden und Toleranzen: verify/README.md.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

from verify.oracle import run_geometry as rg
from verify.oracle.collision_oracle import (
    Body,
    CollisionOracle,
    _transform,
    bodies_intersect,
    static_geometry,
)
from verify.oracle.interval_checker import IntervalChecker
from verify.oracle.robot_oracle import ROOT, default_robot, inv_T, workstation_frames
from verify.oracle.run_checks import (
    Findings,
    Params,
    PartData,
    check_branches,
    check_coverage,
    check_density,
    check_kinematics,
    check_layer_rule,
    check_status,
    check_summary,
    check_toolpath,
    load_json,
    load_part,
)

_WORK: dict[str, tuple] = {}
_ORACLES: dict[str, CollisionOracle] = {}


# --------------------------------------------------------------------------- Abstaende (parallel)


def _eval(task):
    key, idx = task
    mesh, T_WP, prm, q, layer = _WORK[key]
    if key not in _ORACLES:
        _ORACLES[key] = CollisionOracle(mesh, T_WP, prm.h, prm.r_free)
    ic = IntervalChecker(_ORACLES[key], prm.thresholds())
    lb = np.empty(len(idx))
    ub = np.empty(len(idx))
    pairs = []
    for n, i in enumerate(idx):
        iv = ic.evaluate(q[i], int(layer[i]))
        lb[n], ub[n] = iv.lb, iv.ub
        pairs.append(iv.pair)
    return key, idx, lb, ub, pairs


def evaluate_distances(parts: list[PartData], masks: dict[str, np.ndarray], prm: Params, jobs: int):
    """Intervall [lb, ub] des kleinsten Abstands je ausgewaehltem Sample (alle Schwellen entschieden)."""
    static_geometry(float(prm.r_free), 80.0)  # vor dem Fork bauen, Kinder erben sie
    tasks = []
    out = {}
    for P in parts:
        _WORK[P.pid] = (P.mesh, P.T_WP, prm, P.q, P.layer)
        idx = np.flatnonzero(masks[P.pid])
        out[P.pid] = (np.full(P.N, np.nan), np.full(P.N, np.nan), [None] * P.N)
        nblk = max(1, min(len(idx) // 1500, jobs * 4)) if len(idx) else 0
        for blk in np.array_split(idx, nblk) if nblk else []:
            if len(blk):
                tasks.append((P.pid, blk))
    if jobs > 1 and len(tasks) > 1:
        with mp.get_context("fork").Pool(jobs) as pool:
            results = list(pool.imap_unordered(_eval, tasks))
    else:
        results = [_eval(t) for t in tasks]
    for key, idx, lb, ub, pairs in results:
        L, U, PR = out[key]
        L[idx], U[idx] = lb, ub
        for n, i in enumerate(idx):
            PR[i] = pairs[n]
    return out


# --------------------------------------------------------------------------- Lauf-Ebene


def params_for(scenario: dict, ws: dict) -> Params:
    p = scenario.get("params", {}) or {}
    return Params(h=float(p.get("layer_height_mm", 10.0)), w=float(p.get("bead_width_mm", 30.0)),
                  shells=int(p.get("shells", 2)), d_hard=float(p.get("d_hard_mm", 10.0)),
                  d_target=float(p.get("d_target_mm", ws.get("safety_min_distance_mm", 50.0))),
                  r_free=float(p.get("r_free_mm", 40.0)), tau_max_deg=float(p.get("tau_max_deg", 0.0)))


def check_run_level(run: Path, scenario: dict, prm: Params, F: Findings):
    summary = scene = None
    for name in ("summary.json", "scene.json"):
        if not (run / name).is_file():
            F.err(f"{name} fehlt")
    if (run / "summary.json").is_file():
        summary = load_json(run / "summary.json")
        keys = ("scenario_id", "params", "assumptions", "walls", "parts", "timings_s", "provenance")
        miss = [k for k in keys if k not in summary]
        if miss or summary.get("schema_version") != "2":
            F.err(f"summary.json: Schluessel fehlen {miss} oder schema_version != '2'")
        if summary.get("scenario_id") != scenario.get("id"):
            F.err(f"summary.json: scenario_id {summary.get('scenario_id')!r} != {scenario.get('id')!r}")
        sp = summary.get("params", {})
        for key, val in (("layer_height_mm", prm.h), ("bead_width_mm", prm.w), ("d_hard_mm", prm.d_hard),
                         ("d_target_mm", prm.d_target), ("r_free_mm", prm.r_free)):
            if key in sp and abs(float(sp[key]) - val) > 1e-9:
                F.err(f"summary.params.{key} = {sp[key]}, erwartet {val}")
            if key not in sp:
                F.err(f"summary.params.{key} fehlt")
    if (run / "scene.json").is_file():
        scene = load_json(run / "scene.json")
        T_WB, T_WS, _ = workstation_frames()
        robot = default_robot()
        try:
            checks = [("workstation.T_WB", scene["workstation"]["T_WB"], T_WB),
                      ("workstation.T_WS", scene["workstation"]["T_WS"], T_WS),
                      ("tool.T_FT", scene["tool"]["T_FT"], robot.T_FT),
                      ("tool.mesh_transform", scene["tool"]["mesh_transform"], robot.T_F_toolmesh)]
            for name, got, exp in checks:
                if np.abs(np.array(got, dtype=float) - exp).max() > 1e-6:
                    F.err(f"scene.json: {name} weicht von den Assets ab")
            sp = scene["params"]
            for key, val in (("d_hard_mm", prm.d_hard), ("d_target_mm", prm.d_target),
                             ("r_free_mm", prm.r_free), ("layer_height_mm", prm.h)):
                if abs(float(sp[key]) - val) > 1e-9:
                    F.err(f"scene.params.{key} = {sp[key]}, erwartet {val}")
            if scene.get("schema_version") != "2":
                F.err("scene.json: schema_version != '2'")
        except (KeyError, TypeError, ValueError) as exc:
            F.err(f"scene.json unvollstaendig: {exc!r}")
    return summary, scene


def check_walls(run: Path, scenario: dict, summary: dict, parts: dict[str, PartData], prm: Params,
                F: Findings) -> list[dict]:
    """S2: Eignung, vollstaendige Zerlegung, Ueberlappung, Ueberhang-Regel (unabhaengig aus dem IFC)."""
    src = scenario["source"]
    walls_ifc = rg.ifc_walls(ROOT / src["path"])
    swalls = summary.get("walls", [])
    report = []
    for w in walls_ifc:
        sw = next((x for x in swalls if x.get("wall_id") == w["global_id"]), None) or next(
            (x for x in swalls if x.get("name") == w["name"] or x.get("wall_id") == w["name"]), None)
        rep = {"ifc": w["global_id"], "name": w["name"], "thickness_mm": w.get("thickness_mm")}
        report.append(rep)
        if sw is None:
            F.err(f"Wand {w['name']} ({w['global_id']}) fehlt in summary.walls")
            continue
        if w["volume_mm3"] is None:
            F.err(f"Wand {w['name']}: keine Geometrie im IFC lesbar")
            continue
        thin = w["thickness_mm"] < 2 * prm.w
        if not sw.get("eligible"):
            if not sw.get("reason"):
                F.err(f"Wand {w['name']}: ungeeignet ohne Grund")
            if not thin:
                F.err(f"Wand {w['name']}: ungeeignet, aber Dicke {w['thickness_mm']:.1f} >= 2*w")
            continue
        if thin:
            F.err(f"Wand {w['name']}: Dicke {w['thickness_mm']:.1f} < 2*w, aber als geeignet markiert")
        pids = sw.get("part_ids", [])
        mine = [parts[p] for p in pids if p in parts]
        if len(mine) != len(pids) or not mine:
            F.err(f"Wand {w['name']}: Teile fehlen ({len(mine)}/{len(pids)})")
            continue
        meshes_L = [_transform(P.mesh, np.array(P.part["T_LP"], dtype=float)) for P in mine]
        vol = float(sum(m.volume for m in meshes_L))
        rep.update(volume_ifc_mm3=w["volume_mm3"], volume_parts_mm3=vol)
        if abs(vol - w["volume_mm3"]) > 0.005 * w["volume_mm3"]:
            F.err(f"Wand {w['name']}: Teilvolumen {vol:.4g} != Wandvolumen {w['volume_mm3']:.4g} (+-0,5 %)")
        ov = 0.0
        for a in range(len(meshes_L)):
            for b in range(a + 1, len(meshes_L)):
                ov += rg.intersection_volume(meshes_L[a], meshes_L[b])
        rep["overlap_mm3"] = ov
        if ov > 0.001 * w["volume_mm3"]:
            F.err(f"Wand {w['name']}: Ueberlappung der Teile {ov:.4g} mm3 > 0,1 %")
        cuts = [float(np.array(P.part["T_LP"])[2, 3]) + float(P.mesh.bounds[0][2]) for P in mine]
        for z in w["lintels_mm"]:
            if not any(abs(z - c) <= 1.0 for c in cuts):
                F.err(f"Wand {w['name']}: Oeffnungsoberkante z_L = {z:.1f} liegt auf keiner Schnittebene")
    return report


def check_placement(P: PartData, F: Findings) -> None:
    """S2: Teil steht auf der Arbeitsflaeche, innerhalb der Tischplatte, schneidet die Basis nicht."""
    _, T_WS, _ = workstation_frames()
    T_WB = workstation_frames()[0]
    vS = P.mesh.vertices @ (inv_T(T_WS) @ P.T_WP)[:3, :3].T + (inv_T(T_WS) @ P.T_WP)[:3, 3]
    if abs(vS[:, 2].min()) > 0.5:
        F.err(f"{P.pid}: Unterkante in S bei z = {vS[:, 2].min():.2f} mm, erwartet 0")
    vW = P.mesh.vertices @ P.T_WP[:3, :3].T + P.T_WP[:3, 3]
    top = rg.table_top_outline()
    if not top.buffer(0.5).contains(rg.footprint_xy(vW)):
        F.err(f"{P.pid}: Grundriss liegt nicht innerhalb der Tischplatte")
    g = static_geometry(40.0, 80.0)
    partW = Body("part", trimesh.Trimesh(vW, P.mesh.faces, process=False), [], 80.0, max_edge_mm=25.0)
    if bodies_intersect(g.links["base_link"], T_WB, partW, np.eye(4)):
        F.err(f"{P.pid}: Teil schneidet die Roboterbasis (base_link)")


def run(run_dir: Path, scenario_path: Path, jobs: int) -> tuple[bool, dict]:
    t0 = time.monotonic()
    scenario = load_json(scenario_path)
    _, T_WS, ws = workstation_frames()
    prm = params_for(scenario, ws)
    T_WB = workstation_frames()[0]
    F = Findings()
    expect = scenario.get("expect", {})
    mode = "s3" if expect.get("parts") == "collision_detected" else (
        "s2" if "eligible_walls" in expect else "s1")
    summary, _ = check_run_level(run_dir, scenario, prm, F)
    parts: dict[str, PartData] = {}
    part_findings: dict[str, Findings] = {}
    pdirs = sorted(p for p in (run_dir / "parts").glob("*") if p.is_dir())
    if summary is not None:
        listed = [p.get("part_id") for p in summary.get("parts", [])]
        if sorted(listed) != sorted(p.name for p in pdirs):
            F.err(f"summary.parts {sorted(listed)} != Ordner {[p.name for p in pdirs]}")
    if not pdirs:
        F.err("keine Teile im Laufordner")
    robot = default_robot()
    for pdir in pdirs:
        PF = Findings()
        part_findings[pdir.name] = PF
        P = load_part(pdir, T_WS, PF)
        if P is None:
            continue
        parts[P.pid] = P
        pos, rot = check_kinematics(P, robot, T_WB, PF)
        check_layer_rule(P, PF)
        if mode != "s3":
            check_density(P, pos, PF)
            check_toolpath(P, pos, rot, prm, PF)
            check_branches(P, robot, PF)
            check_coverage(P, pos, prm, PF)
            check_summary(P, prm, PF)
            n_c = sum(s == "collision" for s in P.status)
            n_u = sum(s == "unreachable" for s in P.status)
            if n_c or n_u:
                PF.err(f"{P.pid}: {n_c} collision, {n_u} unreachable (G3 verlangt 0)")
            if P.part.get("status") != "machbar":
                PF.err(f"{P.pid}: part.status = {P.part.get('status')!r}, erwartet 'machbar'")
            if mode == "s2":
                check_placement(P, PF)
    # Abstaende: S1/S2 jedes erreichbare Sample; S3 die von roboprint als Kollision gemeldeten
    masks = {}
    for P in parts.values():
        if mode == "s3":
            masks[P.pid] = np.array([s == "collision" for s in P.status])
        else:
            masks[P.pid] = P.reach.copy()
    t1 = time.monotonic()
    dist = evaluate_distances(list(parts.values()), masks, prm, jobs)
    t_dist = time.monotonic() - t1
    n_rp_coll = n_confirmed = 0
    for P in parts.values():
        lb, ub, pairs = dist[P.pid]
        PF = part_findings[P.pid]
        if mode == "s3":
            n_rp_coll += int(masks[P.pid].sum())
            n_confirmed += int(np.sum(masks[P.pid] & (ub < 0)))
            PF.metrics["n_roboprint_collision"] = int(masks[P.pid].sum())
            PF.metrics["n_confirmed_collision"] = int(np.sum(masks[P.pid] & (ub < 0)))
        else:
            check_status(P, lb, ub, pairs, prm, PF, masks[P.pid])
    if mode == "s3":
        if n_rp_coll == 0:
            F.err("S3: roboprint meldet kein Sample mit status collision")
        elif n_confirmed == 0:
            F.err(f"S3: keines der {n_rp_coll} collision-Samples vom Pruefer bestaetigt")
    if summary is not None:
        for sp in summary.get("parts", []):
            if mode != "s3" and sp.get("status") != "machbar":
                F.err(f"summary: Teil {sp.get('part_id')} status {sp.get('status')!r}")
    walls = []
    if mode == "s2" and summary is not None:
        walls = check_walls(run_dir, scenario, summary, parts, prm, F)
    errors = list(F.errors) + [e for PF in part_findings.values() for e in PF.errors]
    passed = not errors
    report = {
        "schema_version": "2", "scenario": scenario.get("id"), "expect": expect, "mode": mode,
        "passed": passed, "errors": errors,
        "params": prm.__dict__, "walls": walls,
        "parts": {k: {"n": parts[k].N if k in parts else None, **v.metrics}
                  for k, v in part_findings.items()},
        "seconds": {"total": round(time.monotonic() - t0, 1), "distances": round(t_dist, 1)},
        "jobs": jobs,
    }
    return passed, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--scenario", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("VERIFY_JOBS", "0")) or
                    max(1, min(3, (os.cpu_count() or 2) - 1)))
    args = ap.parse_args(argv)
    run_dir = args.run_dir if args.run_dir.is_absolute() else Path.cwd() / args.run_dir
    scen = args.scenario if args.scenario.is_absolute() else Path.cwd() / args.scenario
    if not run_dir.is_dir():
        print(f"Laufordner fehlt: {run_dir}", file=sys.stderr)
        return 2
    try:
        passed, report = run(run_dir, scen, max(1, args.jobs))
    except Exception as exc:  # noqa: BLE001 - jeder Absturz ist ein Fehlschlag mit Bericht
        import traceback

        passed = False
        report = {"schema_version": "2", "passed": False,
                  "errors": [f"Pruefer abgebrochen: {exc!r}"], "traceback": traceback.format_exc()}
    (run_dir / "check.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                                        encoding="utf-8")
    for e in report["errors"][:40]:
        print(f"FEHLER {e}")
    print(f"check_run: {'BESTANDEN' if passed else 'NICHT BESTANDEN'} ({len(report['errors'])} Fehler)")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
