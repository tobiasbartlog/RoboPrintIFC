"""Muster-Orakel (Vorschlag G9): prueft die Musterregeln M1-M7 eines Laufordners.

    python -m verify_muster.check <laufordner> [--scenario <json>] [--json out.json] [--part ID]
                                  [--no-trajectory]

Liest je Teil part.json (T_WP), part.stl (Frame P), toolpath.json und trajectory.json; das Szenario
nur zur Beschriftung (id, Musterparameter). Schreibt den Bericht nach --json (Default
<laufordner>/check_muster.json) und endet mit 0 genau dann, wenn alle harten Regeln (M1-M6, M6b) in
allen geprueften Teilen gruen sind; 1 bei Regelverletzung, 2 bei fehlenden oder unlesbaren Artefakten.
Importiert roboprint nicht. Methoden: verify_muster/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from verify_muster import rules
from verify_muster.artifacts import ArtifactError, load_json, load_part, part_dirs

SCHEMA_VERSION = "1"
PATTERN_KEYS = ("layer_order", "infill_pattern", "outfill_pattern", "pattern_params", "shells")


def check_part(pdir: Path, need_trajectory: bool = True) -> dict:
    t0 = time.perf_counter()
    part = load_part(pdir, need_trajectory=need_trajectory)
    C = rules.build_ctx(part)
    rs = [rules.check_m1(C), rules.check_m2(C), rules.check_m3(C), rules.check_m4(C), rules.check_m5(C),
          rules.check_m6(C), rules.check_m6b(C)]
    m7, metrics = rules.check_m7_and_metrics(C)
    rs.append(m7)
    metrics["share_vertical_layer_change"] = rs[3].metrics.get("share_vertical")
    metrics["min_radius_mm"] = rs[5].metrics.get("min_radius_mm")
    metrics["contact_zones_per_m"] = m7.metrics.get("contact_zones_per_m")
    passed = all(r.passed for r in rs if r.hard)
    return {"part_id": part.part_id, "dir": str(pdir), "status": part.status, "pattern": part.pattern,
            "params": {"bead_width_mm": part.w, "layer_height_mm": part.h},
            "passed": passed, "failed_rules": [r.name for r in rs if r.hard and not r.passed],
            "rules": {r.name: r.to_json() for r in rs}, "metrics": metrics,
            "runtime_s": round(time.perf_counter() - t0, 3)}


def run(run_dir: Path, scenario: Path | None = None, part: str | None = None,
        need_trajectory: bool = True) -> tuple[int, dict]:
    report: dict = {"schema_version": SCHEMA_VERSION, "tool": "verify_muster", "run_dir": str(run_dir),
                    "constants": {"eps": rules.EPS, "delta_mm": rules.DELTA_MM, "m4_tol_mm": rules.M4_TOL_MM,
                                  "m5_margin_mm": rules.M5_MARGIN_MM, "r_rel_tol": rules.R_REL_TOL,
                                  "follow_tol_mm": rules.FOLLOW_TOL_MM,
                                  "contact_tol_mm": rules.CONTACT_TOL_MM,
                                  "straight_tol_mm": rules.STRAIGHT_TOL_MM,
                                  "assumptions": "eps, delta, Toleranzen mit (A) gekennzeichnet, README"},
                    "parts": [], "errors": []}
    if scenario is not None:
        try:
            sc = load_json(scenario)
            report["scenario"] = {"path": str(scenario), "id": sc.get("id"),
                                  "pattern_params": {k: v for k, v in (sc.get("params") or {}).items()
                                                     if k in PATTERN_KEYS}}
        except ArtifactError as exc:
            report["errors"].append(str(exc))
    try:
        dirs = part_dirs(run_dir)
    except ArtifactError as exc:
        report["errors"].append(str(exc))
        dirs = []
    if part is not None:
        dirs = [d for d in dirs if d.name == part]
    for d in dirs:
        try:
            report["parts"].append(check_part(d, need_trajectory=need_trajectory))
        except ArtifactError as exc:
            report["errors"].append(f"{d.name}: {exc}")
    if not report["parts"] and not report["errors"]:
        report["errors"].append("keine Teile gefunden")
    report["passed"] = not report["errors"] and all(p["passed"] for p in report["parts"])
    code = 0 if report["passed"] else (2 if report["errors"] else 1)
    return code, report


def _jsonable(o):
    """numpy-Skalare und -Arrays fuer json.dumps."""
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"nicht serialisierbar: {type(o)}")


def _summary_lines(report: dict) -> list[str]:
    out = []
    for p in report["parts"]:
        flags = " ".join(f"{k}:{'ok' if v['pass'] else 'FAIL'}" for k, v in p["rules"].items())
        out.append(f"{p['part_id']}: {'GRUEN' if p['passed'] else 'ROT'}  {flags}")
        for name in p["failed_rules"]:
            f = p["rules"][name]["first"]
            out.append(f"  {name}: Schicht {f['layer']}, Ring {f['ring']}, Punkt {f['point_P']}: "
                       f"{f['message']}")
    out.extend(f"Fehler: {e}" for e in report["errors"])
    out.append("verify_muster: " + ("GRUEN" if report["passed"] else "ROT"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--scenario", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None, 
                    help="Bericht (Default <laufordner>/check_muster.json)")
    ap.add_argument("--part", default=None, help="nur dieses Teil pruefen")
    ap.add_argument("--no-trajectory", action="store_true", 
                    help="nur toolpath (M1 ohne Trajektorie, ohne M6b)")
    a = ap.parse_args(argv)
    code, report = run(a.run_dir, a.scenario, a.part, need_trajectory=not a.no_trajectory)
    out = a.json or (a.run_dir / "check_muster.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=_jsonable), encoding="utf-8")
    except OSError as exc:
        print(f"Bericht nicht geschrieben: {exc}", file=sys.stderr)
    print("\n".join(_summary_lines(report)))
    return code


if __name__ == "__main__":
    sys.exit(main())
