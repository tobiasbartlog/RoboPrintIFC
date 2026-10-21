"""Musterrunner (Vorschlag Gate G9): rechnet die Musterszenarien und prüft jeden Lauf.

    python scripts/verify_muster.py                       alle Szenarien in docs/muster/szenarien/
    python scripts/verify_muster.py --fast                nur Szenarien mit expect.muster.fast = true
    python scripts/verify_muster.py --scenario S4_muster_sinus S5_muster_oeffnung
    python scripts/verify_muster.py --no-run              vorhandene Läufe nur neu prüfen
    python scripts/verify_muster.py --scenario X --merge  Ergebnis in den vorhandenen Bericht einfügen

Je Szenario (Laufordner `runs/verify_muster/<id>`):

1. `python -m roboprint run-scenario <szenario> --out <lauf> --jobs N` (wie `scripts/verify.py`),
   Laufzeit gemessen (Wanduhr) und aus `summary.timings_s` (Planer).
2. `python -m verify.check_run <lauf> --scenario <szenario>` (G3-Regeln, nur aufgerufen). Die
   G3-Abdeckung („≥ 95 % des Schalenbereichs“) bleibt unverändert, wird aber in einer eigenen
   Spalte als **Einwand** gewertet (Gate-Einwand 1 in MUSTER-PROGRESS.md): Muster mit Fugen,
   Stegen oder gerundeten Ecken decken den Schalenbereich gewollt nicht voll ab. Alle anderen
   G3-Kriterien sind hart.
3. `python -m verify.fake_drcf <lauf>` (G5-Regeln, hart).
4. `python -m verify_muster.check <lauf> --scenario <szenario>` (M1–M7, hart nach verify_muster).
5. Musterprobe (hart): `toolpath.pattern` jedes Teils trägt das Muster des Szenarios (Preset bzw.
   `infill_pattern`/`outfill_pattern`), Infill-Muster haben Ringe `kind = infill`.

Ein Prüferbericht zählt nur, wenn er frisch ist (alte `check.json`/`check_muster.json` werden vor
dem Aufruf gelöscht) und zum Exitcode passt: check_run 0 mit `passed`, oder 1 nur mit
Abdeckungsfehlern; verify_muster 0 mit `passed`, oder 1 mit mindestens einer verletzten Regel.

Erwartung je Szenario in `expect.muster` (Szenariovertrag: `expect` ist ein freies Objekt):
`machbar = true`: grün, wenn alle Teile machbar sind und G3 (ohne Abdeckung), G5 und M1–M7 grün
sind. `machbar = false` („belegt nicht machbar“): grün, wenn der Lauf durchläuft und
verify_muster genau an den belegten Regeln `erwartete_regeln` scheitert (mindestens an allen
genannten); sonst rot. `fast = true` nimmt das Szenario in `--fast` auf.

Kennzahlen je Lauf (aus den Artefakten, ohne `roboprint` zu importieren): machbar, d_min,
Stränge je Schicht, Anteil senkrechter Schichtwechsel, Druckzeit, Planerlaufzeit, Abdeckung.
Bericht: `runs/verify_muster/report.json` (Format liest auch `scripts/muster_katalog.py`).
Exit 0 genau dann, wenn alle ausgewählten Szenarien grün sind.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "docs" / "muster" / "szenarien"
OUT = ROOT / "runs" / "verify_muster"
PY = sys.executable
COVERAGE_RE = re.compile(r"^[^:]+: Abdeckung < 95 %")
COVERAGE_PCT_RE = re.compile(r"Schicht \d+: ([0-9.]+) %")
#: (A) Untergrenze der Abdeckung, die noch als musterbedingt gilt (Einwand statt rot). Gate-Einwand 1/3
#: belegen 60–95 % (kleinster Wert Fugenwand-Gurt 300 mm: 62,7 %); darunter fehlt Material (z. B. eine
#: unvollständige Schicht mit 0 %), das ist ein Fehler und kein Einwand.
COVERAGE_FLOOR = 0.55
EINWAND_REF = "MUSTER-PROGRESS.md, Gate-Einwände 1 (G3-Abdeckung gegen Muster)"
VERTICAL_TOL_MM = 0.5  # M4 (A)


# --------------------------------------------------------------------------- Hilfen


def _env() -> dict[str, str]:
    env = dict(os.environ)
    src = str(ROOT / "core" / "src")  # dieser Worktree, nicht die editierbare Installation
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("PYTHONUTF8", "1")
    return env


def run_cmd(name: str, cmd: list[str], timeout_s: int, log: Path) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=_env(),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code = -1
        out = f"TIMEOUT nach {timeout_s} s\n{exc.stdout or ''}{exc.stderr or ''}"
    seconds = round(time.monotonic() - t0, 1)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f"$ {' '.join(cmd)}\n{out}", encoding="utf-8")
    tail = "\n".join(out.strip().splitlines()[-15:])
    return {
        "step": name,
        "exit_code": code,
        "seconds": seconds,
        "log": str(log.relative_to(ROOT)),
        "tail": tail,
    }


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def find_scenarios(selected: list[str] | None, fast: bool) -> list[Path]:
    paths = sorted(SCEN_DIR.glob("S[45]_muster_*.json"))
    if selected:
        out = []
        for s in selected:
            p = Path(s)
            cand = p if p.suffix == ".json" and (ROOT / p).exists() else SCEN_DIR / f"{p.stem}.json"
            cand = cand if cand.is_absolute() else ROOT / cand
            if not cand.exists():
                raise SystemExit(f"Szenario nicht gefunden: {s}")
            out.append(cand)
        paths = out
    if fast:
        paths = [p for p in paths if (_load(p) or {}).get("expect", {}).get("muster", {}).get("fast")]
    # schnelle zuerst, dann S4 vor S5, sonst alphabetisch
    return sorted(
        paths, key=lambda p: (not (_load(p) or {}).get("expect", {}).get("muster", {}).get("fast"), p.name)
    )


# --------------------------------------------------------------------------- Kennzahlen


def toolpath_metrics(tp: dict[str, Any]) -> dict[str, Any]:
    """Stränge je Schicht und senkrechte Schichtwechsel aus `toolpath.json` (Ringe in Druckfolge)."""
    rings = tp.get("rings", [])
    strand = 0
    strands_of_layer: dict[int, set[int]] = {}
    changes = vertical = 0
    for i, r in enumerate(rings):
        if i > 0 and not rings[i - 1].get("link_next"):
            strand += 1
        strands_of_layer.setdefault(int(r["layer"]), set()).add(strand)
        if i + 1 < len(rings):
            nxt = rings[i + 1]
            if int(nxt["layer"]) == int(r["layer"]) + 1:
                changes += 1
                a, b = r["waypoints"][-1], nxt["waypoints"][0]
                if r.get("link_next") and math.hypot(a[0] - b[0], a[1] - b[1]) <= VERTICAL_TOL_MM:
                    vertical += 1
    per_layer = [len(v) for v in strands_of_layer.values()] or [0]
    return {
        "strands_total": strand + 1 if rings else 0,
        "strands_min": min(per_layer),
        "strands_max": max(per_layer),
        "layer_changes": changes,
        "vertical_changes": vertical,
        "rings": len(rings),
        "waypoints": sum(len(r["waypoints"]) for r in rings),
    }


def run_metrics(run: Path) -> dict[str, Any]:
    summary = _load(run / "summary.json") or {}
    parts = summary.get("parts", [])
    tps, d_mins, dauer, samples = [], [], 0.0, 0
    for p in parts:
        pdir = run / "parts" / p["part_id"]
        tp = _load(pdir / "toolpath.json")
        if tp:
            tps.append(toolpath_metrics(tp))
        tr = _load(pdir / "trajectory.json")
        s = (tr or {}).get("summary", {})
        if s.get("d_min_mm") is not None:
            d_mins.append(float(s["d_min_mm"]))
        dauer += float(s.get("dauer_s") or 0.0)
        samples += int(s.get("n") or 0)
    t = summary.get("timings_s", {})
    smin = min((m["strands_min"] for m in tps), default=None)
    smax = max((m["strands_max"] for m in tps), default=None)
    changes = sum(m["layer_changes"] for m in tps)
    vert = sum(m["vertical_changes"] for m in tps)
    return {
        "n_parts": len(parts),
        "machbar": bool(parts) and all(p.get("status") == "machbar" for p in parts),
        "part_status": {p["part_id"]: p.get("status") for p in parts},
        "d_min_mm": round(min(d_mins), 3) if d_mins else None,
        "strands_per_layer": None if smin is None else (str(smin) if smin == smax else f"{smin}–{smax}"),
        "strands_per_layer_min": smin,
        "strands_per_layer_max": smax,
        "strands_total": sum(m["strands_total"] for m in tps),
        "layer_changes": changes,
        "vertical_layer_changes": vert,
        "vertical_layer_change_share": round(vert / changes, 4) if changes else None,
        "rings": sum(m["rings"] for m in tps),
        "waypoints": sum(m["waypoints"] for m in tps),
        "samples": samples,
        "print_time_s": round(dauer, 1),
        # Mit Zerlegung (IFC) plant die Zerlegung die Teile; dann zaehlen die Teilzeiten `<teil>.plan`
        "planner_runtime_s": t.get("plan") or round(sum(v for k, v in t.items() if k.endswith(".plan")), 3),
        "plan_final_check_s": round(sum(v for k, v in t.items() if k.endswith(".plan_final_check")), 3),
        "decompose_s": t.get("decompose"),
        "total_runtime_s": t.get("total"),
    }


def check_run_result(run: Path, step: dict[str, Any]) -> dict[str, Any]:
    """G3 aus `check.json`, nur gültig, wenn der Exitcode dazu passt: 0 mit `passed`, oder 1 mit
    ausschließlich Abdeckungsfehlern. Alles andere (Abbruch, Zeitlimit, Aufruffehler 2, Bericht und
    Exitcode widersprechen sich) ist rot."""
    rep = _load(run / "check.json")
    if rep is None:
        return {"status": "rot", "abdeckung": "rot", "errors": [f"check.json fehlt ({step['tail'][-300:]})"]}
    errors = list(rep.get("errors", []))
    cov = [e for e in errors if COVERAGE_RE.match(e)]
    hard = [e for e in errors if not COVERAGE_RE.match(e)]
    code = step.get("exit_code")
    consistent = (code == 0 and rep.get("passed") is True and not errors) or (
        code == 1 and rep.get("passed") is False and bool(cov) and not hard
    )
    if not consistent and not hard:
        msg = f"check_run: Exitcode {code} passt nicht zum Bericht (passed={rep.get('passed')!r}, "
        hard = [msg + f"{len(errors)} Fehler)"]
    cov_min = [
        m.get("coverage_min")
        for m in (rep.get("parts") or {}).values()
        if isinstance(m, dict) and m.get("coverage_min") is not None
    ]
    # Einwand nur für musterbedingte Lücken: Liegt die Abdeckung eines Teils (Bericht oder Beispiel
    # in der Meldung) unter COVERAGE_FLOOR, fehlt Material, und G3 bleibt rot.
    seen = [float(v) for v in cov_min] if cov else []
    seen += [float(x) / 100.0 for e in cov for x in COVERAGE_PCT_RE.findall(e)]
    if seen and min(seen) < COVERAGE_FLOOR:
        hard.append(
            f"Abdeckung {100 * min(seen):.1f} % unter der Untergrenze {100 * COVERAGE_FLOOR:.0f} % für "
            "musterbedingte Lücken (Gate-Einwand 1/3 begründet nur 60–95 %): Material fehlt"
        )
    return {
        "status": "gruen" if not hard else "rot",
        "abdeckung": "gruen" if not cov else "einwand",
        "abdeckung_min": round(min(cov_min), 4) if cov_min else None,
        "abdeckung_ref": EINWAND_REF if cov else None,
        "errors": hard[:20],
        "n_errors": len(hard),
        "coverage_errors": cov[:5],
        "checker_d_min_lb_mm": min(
            (
                m.get("checker_d_min_lb_mm")
                for m in (rep.get("parts") or {}).values()
                if isinstance(m, dict) and m.get("checker_d_min_lb_mm") is not None
            ),
            default=None,
        ),
    }


def muster_result(run: Path, step: dict[str, Any]) -> dict[str, Any]:
    rep = _load(run / "check_muster.json")
    if rep is None or step["exit_code"] not in (0, 1, 2):
        return {
            "status": "rot",
            "failed_rules": [],
            "errors": [
                f"check_muster.json fehlt oder Abbruch (Exit {step['exit_code']}): {step['tail'][-300:]}"
            ],
        }
    failed: set[str] = set()
    first, share, n_ch, n_v, warn = [], [], 0, 0, {}
    for p in rep.get("parts", []):
        failed |= set(p.get("failed_rules") or [])
        if p.get("first_counterexample"):
            first.append({"part": p.get("part_id"), **p["first_counterexample"]})
        m4 = ((p.get("rules") or {}).get("M4") or {}).get("metrics") or {}
        n_ch += int(m4.get("n_changes") or 0)
        n_v += int(m4.get("n_vertical") or 0)
        for rid, r in (p.get("rules") or {}).items():
            if r.get("warnings"):
                warn[rid] = warn.get(rid, 0) + int(r["warnings"])
        if m4.get("share_vertical") is not None:
            share.append(m4["share_vertical"])
    if step["exit_code"] == 1 and (rep.get("passed") or not failed):
        # Exit 1 heisst Regelverletzung; ohne verletzte Regel ist es ein Abbruch (Traceback)
        return {
            "status": "rot",
            "exit_code": step["exit_code"],
            "failed_rules": [],
            "errors": ["verify_muster: Exitcode 1 ohne verletzte Regel im Bericht"],
        }
    return {
        "status": "gruen" if step["exit_code"] == 0 and rep.get("passed") is True else "rot",
        "exit_code": step["exit_code"],
        "failed_rules": sorted(failed),
        "first_counterexample": first[:3],
        "orakel_vertical_share": round(n_v / n_ch, 4) if n_ch else None,
        "warnings": warn,
        "errors": list(rep.get("errors", []))[:10],
    }


def pattern_check(run: Path, sc: dict[str, Any]) -> dict[str, Any]:
    """Wurde das Muster des Szenarios wirklich gedruckt? Ein Lauf, der das Preset still verliert
    (oder dessen Infill der Kern mangels Bandbreite weglässt), prüft sonst ein anderes Muster.
    Erwartet: `toolpath.pattern` in jedem Teil, Mustername aus dem Preset bzw. aus
    `infill_pattern`/`outfill_pattern` als `infill` oder `outfill`, bei Infill Ringe mit
    `kind = infill`; `schalen` heißt `infill = outfill = none`."""
    params = sc.get("params") or {}
    want: set[str] = set()
    preset = params.get("pattern_preset")
    if preset:
        pr = _load(ROOT / preset)
        if not isinstance(pr, dict) or not pr.get("pattern"):
            return {"status": "rot", "expected": [], "errors": [f"Preset nicht lesbar: {preset}"]}
        want.add(str(pr["pattern"]))
    for key in ("infill_pattern", "outfill_pattern"):
        if params.get(key) and params[key] != "none":
            want.add(str(params[key]))
    errors: list[str] = []
    if not want:
        errors.append("Szenario ohne Musterparameter")
    parts = (_load(run / "summary.json") or {}).get("parts", [])
    if not parts:
        errors.append("keine Teile im Lauf")
    for p in parts:
        tp = _load(run / "parts" / p["part_id"] / "toolpath.json") or {}
        pat = tp.get("pattern")
        if not isinstance(pat, dict):
            errors.append(f"{p['part_id']}: toolpath.pattern fehlt (Muster nicht angewendet)")
            continue
        got = {pat.get("infill"), pat.get("outfill")} - {None, "none"}
        kinds = {r.get("kind") for r in tp.get("rings", [])}
        for name in sorted(want):
            if name == "schalen":
                if got:
                    errors.append(f"{p['part_id']}: schalen erwartet, Muster {sorted(got)}")
            elif name not in got:
                errors.append(f"{p['part_id']}: Muster {name} fehlt (toolpath.pattern {sorted(got)})")
            elif pat.get("infill") == name and "infill" not in kinds:
                errors.append(f"{p['part_id']}: Infill {name} ohne Ring kind=infill (weggelassen)")
    return {"status": "rot" if errors else "gruen", "expected": sorted(want), "errors": errors[:10]}


# --------------------------------------------------------------------------- Szenario


def run_scenario(path: Path, jobs: int, no_run: bool) -> dict[str, Any]:
    sc = _load(path) or {}
    sid = sc.get("id", path.stem)
    exp = (sc.get("expect") or {}).get("muster") or {}
    machbar_soll = bool(exp.get("machbar", True))
    run = OUT / sid
    rel_scen = str(path.relative_to(ROOT))
    steps: list[dict[str, Any]] = []
    entry: dict[str, Any] = {
        "name": sid,
        "scenario": rel_scen,
        "preset": exp.get("preset"),
        "expect_machbar": machbar_soll,
    }
    print(f"== {sid} (Erwartung: {'machbar' if machbar_soll else 'belegt nicht machbar'})", flush=True)

    if no_run and (run / "summary.json").exists():
        rs = {"step": "run-scenario", "exit_code": 0, "seconds": None, "tail": "wiederverwendet"}
    else:
        shutil.rmtree(run, ignore_errors=True)
        limit = float((sc.get("limits") or {}).get("wall_time_s", 600))
        rs = run_cmd(
            "run-scenario",
            [
                PY,
                "-m",
                "roboprint",
                "run-scenario",
                rel_scen,
                "--out",
                str(run.relative_to(ROOT)),
                "--jobs",
                str(jobs),
            ],
            timeout_s=int(max(3600, 6 * limit)),
            log=OUT / "logs" / f"{sid}.run.log",
        )
    steps.append(rs)
    print(f"   run-scenario  exit {rs['exit_code']}  {rs['seconds']} s", flush=True)
    ran = rs["exit_code"] == 0 and (run / "summary.json").exists()

    metrics = run_metrics(run) if ran else {}
    pat: dict[str, Any] = pattern_check(run, sc) if ran else {"status": "rot", "errors": ["kein Lauf"]}
    if ran:
        print(f"   Muster        {pat['status']} {pat['errors'] or pat['expected']}", flush=True)
    g3: dict[str, Any] = {"status": "rot", "abdeckung": "rot", "errors": ["Lauf fehlgeschlagen"]}
    g5: dict[str, Any] = {"status": "rot"}
    mu: dict[str, Any] = {"status": "rot", "failed_rules": []}
    if ran:
        for stale in ("check.json", "check_muster.json"):  # --no-run: nie einen alten Bericht werten
            (run / stale).unlink(missing_ok=True)
        cr = run_cmd(
            "check_run",
            [
                PY,
                "-m",
                "verify.check_run",
                str(run.relative_to(ROOT)),
                "--scenario",
                rel_scen,
                "--jobs",
                str(jobs),
            ],
            timeout_s=3600,
            log=OUT / "logs" / f"{sid}.check_run.log",
        )
        steps.append(cr)
        g3 = check_run_result(run, cr)
        print(
            f"   check_run     {g3['status']} (Abdeckung: {g3['abdeckung']})  {cr['seconds']} s", flush=True
        )
        fd = run_cmd(
            "fake_drcf",
            [PY, "-m", "verify.fake_drcf", "--jobs", str(jobs), str(run.relative_to(ROOT))],
            timeout_s=3600,
            log=OUT / "logs" / f"{sid}.fake_drcf.log",
        )
        steps.append(fd)
        g5 = {"status": "gruen" if fd["exit_code"] == 0 else "rot", "tail": fd["tail"][-600:]}
        print(f"   fake_drcf     {g5['status']}  {fd['seconds']} s", flush=True)
        vm = run_cmd(
            "verify_muster",
            [PY, "-m", "verify_muster.check", str(run.relative_to(ROOT)), "--scenario", rel_scen],
            timeout_s=3600,
            log=OUT / "logs" / f"{sid}.verify_muster.log",
        )
        steps.append(vm)
        mu = muster_result(run, vm)
        print(f"   verify_muster {mu['status']} {mu['failed_rules'] or ''} {vm['seconds']} s", flush=True)

    feasible = bool(
        ran
        and metrics.get("machbar")
        and pat["status"] == "gruen"
        and g3["status"] == "gruen"
        and g5["status"] == "gruen"
        and mu["status"] == "gruen"
    )
    if machbar_soll:
        status = "gruen" if feasible else "rot"
        verdict = "machbar" if feasible else "nicht machbar (unerwartet)"
    else:
        want = set(exp.get("erwartete_regeln") or [])
        hit = (
            ran
            and pat["status"] == "gruen"
            and mu.get("exit_code") == 1
            and bool(want)
            and want <= set(mu["failed_rules"])
        )
        status = "gruen" if hit else "rot"
        verdict = (
            ("belegt nicht machbar (" + ", ".join(sorted(want)) + ")")
            if hit
            else ("machbar entgegen der Erwartung" if feasible else "nicht machbar, aber nicht wie belegt")
        )
    entry.update(
        {
            "status": status,
            "verdict": verdict,
            "feasible": feasible,
            **{
                k: metrics.get(k)
                for k in (
                    "d_min_mm",
                    "strands_per_layer",
                    "vertical_layer_change_share",
                    "print_time_s",
                    "planner_runtime_s",
                )
            },
            "runtime_s": rs["seconds"],
            "g3": g3["status"],
            "g3_abdeckung": g3["abdeckung"],
            "g5": g5["status"],
            "muster": mu["status"],
            "pattern_applied": pat["status"],
            "metrics": metrics,
            "checks": {"pattern": pat, "check_run": g3, "fake_drcf": g5, "verify_muster": mu},
            "expect_detail": exp,
            "steps": steps,
        }
    )
    print(f"   => {status.upper()}: {verdict}", flush=True)
    return entry


def _f(v: Any) -> str:
    return "–" if v is None else str(v)


def table_row(e: dict[str, Any]) -> str:
    share = e["vertical_layer_change_share"]
    cells = [
        f"{e['name']:37}",
        f"{e['status']:6}",
        f"{'machbar' if e['expect_machbar'] else 'nicht':9}",
        f"{'ja' if e['feasible'] else 'nein':7}",
        f"{_f(e['d_min_mm']):>6}",
        f"{_f(e['strands_per_layer']):>7}",
        f"{'–' if share is None else f'{100 * share:.0f} %':>6}",
        f"{_f(e['planner_runtime_s']):>7}",
        f"{_f(e['runtime_s']):>7}",
        f"{e['g3']:5}",
        f"{e['g3_abdeckung']:10}",
        f"{e['g5']:5}",
        e["muster"],
    ]
    return " ".join(cells)


def merge_entries(old: Any, new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Alte Eintraege (anderer Szenarien) behalten, neue ersetzen gleichnamige; Reihenfolge nach Name."""
    fresh = {e["name"] for e in new}
    kept = [e for e in (old or {}).get("scenarios", []) if isinstance(e, dict) and e.get("name") not in fresh]
    return sorted(kept + new, key=lambda e: (not e["name"].startswith("S4"), e["name"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scenario", nargs="+", metavar="ID", help="nur diese Szenarien (ID oder Pfad)")
    ap.add_argument("--fast", action="store_true", help="nur Szenarien mit expect.muster.fast = true")
    ap.add_argument(
        "--jobs",
        type=int,
        default=int(os.environ.get("VERIFY_JOBS", "0")) or 2,
        help="Prozesse fuer run-scenario, check_run und fake_drcf (Standard 2)",
    )
    ap.add_argument("--no-run", action="store_true", help="vorhandene Laufordner nur neu pruefen")
    ap.add_argument(
        "--merge",
        action="store_true",
        help="Eintraege anderer Szenarien aus dem vorhandenen report.json behalten",
    )
    args = ap.parse_args(argv)

    scen = find_scenarios(args.scenario, args.fast)
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    entries = [run_scenario(p, max(1, args.jobs), args.no_run) for p in scen]
    if args.merge:
        entries = merge_entries(_load(OUT / "report.json"), entries)
    all_green = bool(entries) and all(e["status"] == "gruen" for e in entries)
    report = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mode": "merged"
        if args.merge
        else ("fast" if args.fast else ("partial" if args.scenario else "full")),
        "all_green": all_green,
        "seconds": round(time.monotonic() - t0, 1),
        "rules": {
            "g3": "verify.check_run, alle Kriterien hart ausser der Abdeckung",
            "g3_abdeckung": f"Einwand, nicht hart: {EINWAND_REF}",
            "g5": "verify.fake_drcf, hart",
            "muster": "verify_muster.check (M1–M7), hart",
            "pattern_applied": "toolpath.pattern traegt das Muster des Szenarios in jedem Teil, hart",
        },
        "scenarios": entries,
    }
    out = OUT / "report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(
        "\nSzenario                              Status  Erwartung  machbar  d_min Str./S. senkr.  Plan s  "
        "Lauf s  G3    Abdeckung  G5    M1–M7"
    )
    for e in entries:
        print(table_row(e))
    print(f"Bericht: {out.relative_to(ROOT)}  ({'GRUEN' if all_green else 'ROT'})")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
