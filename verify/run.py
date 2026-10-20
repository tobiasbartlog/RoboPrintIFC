"""Gate-Runner fuer die Abnahme nach spec/SPEC.md Paragraph 11.

Fuehrt die Gates G1-G8 als Unterprozesse aus, schreibt runs/verify/report.json und endet mit
Exit-Code 0 genau dann, wenn alle ausgewaehlten Gates gruen sind.

    python scripts/verify.py              alle Gates
    python scripts/verify.py --fast       ohne S2 (G4, G7) und ohne Viewer-E2E (G6)
    python scripts/verify.py --gate G3 G5 nur diese Gates

Nur Standardbibliothek. Die Orakel, die die Gates aufrufen, liegen in verify/oracle,
verify/check_run.py und verify/fake_drcf/ und entstehen in Phase P0.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "verify"
SCEN = ROOT / "spec" / "scenarios"
PY = sys.executable

S1 = SCEN / "S1_modul_referenz.json"
S2 = SCEN / "S2_beispiel_ifc_modul.json"
S3 = SCEN / "S3_kollision_negativ.json"


@dataclass
class Step:
    name: str
    cmd: list[str]
    requires: list[str] = field(default_factory=list)  # Pfade relativ zu ROOT
    timeout_s: int = 1800
    clean: str | None = None  # Ordner relativ zu ROOT, der vor dem Schritt geleert wird


@dataclass
class Gate:
    gid: str
    title: str
    steps: list[Step]
    slow: bool = False


def _run_scenario(scenario: Path, tag: str, timeout_s: int) -> Step:
    out = f"runs/verify/{tag}"
    return Step(
        name=f"{tag}: run-scenario",
        cmd=[PY, "-m", "roboprint", "run-scenario", str(scenario.relative_to(ROOT)), "--out", out],
        requires=["core/src/roboprint/__main__.py", str(scenario.relative_to(ROOT))],
        timeout_s=timeout_s,
        clean=out,
    )


def _check_run(scenario: Path, tag: str) -> Step:
    return Step(
        name=f"{tag}: check_run",
        cmd=[PY, "-m", "verify.check_run", f"runs/verify/{tag}", "--scenario",
             str(scenario.relative_to(ROOT))],
        requires=["verify/check_run.py"],
    )


def gates(fast: bool) -> list[Gate]:
    g5_runs = ["runs/verify/S1"] if fast else ["runs/verify/S1", "runs/verify/S2"]
    return [
        Gate("G1", "Kinematik gegen Pinocchio/URDF", [
            Step("pytest G1", [PY, "-m", "pytest", "verify/oracle/test_g1_kinematics.py", "-q"],
                 requires=["verify/oracle/test_g1_kinematics.py"]),
        ]),
        Gate("G2", "Kollisionsabstand gegen Coal", [
            Step("pytest G2", [PY, "-m", "pytest", "verify/oracle/test_g2_collision.py", "-q"],
                 requires=["verify/oracle/test_g2_collision.py"]),
        ]),
        Gate("G3", "Referenzmodul S1 kollisionsfrei", [
            _run_scenario(S1, "S1", timeout_s=900),
            _check_run(S1, "S1"),
        ]),
        Gate("G4", "Beispiel-IFC S2 zerlegt + Negativfall S3", [
            _run_scenario(S2, "S2", timeout_s=3600),
            _check_run(S2, "S2"),
            _run_scenario(S3, "S3", timeout_s=900),
            _check_run(S3, "S3"),
        ], slow=True),
        Gate("G5", "DRL im Fake-Controller", [
            Step("fake_drcf", [PY, "-m", "verify.fake_drcf", *g5_runs],
                 requires=["verify/fake_drcf/__main__.py"]),
        ]),
        Gate("G6", "Viewer-E2E (Playwright)", [
            Step("e2e", ["npm", "--prefix", "web", "run", "e2e"],
                 requires=["web/package.json"], timeout_s=1800),
        ], slow=True),
        Gate("G7", "Laufzeit S1 <= 180 s, S2 <= 1800 s", [], slow=True),
        Gate("G8", "Lint, Typen, Unit-Tests", [
            Step("ruff", [PY, "-m", "ruff", "check", "core", "verify"],
                 requires=["core/pyproject.toml"]),
            Step("pytest core", [PY, "-m", "pytest", "core", "-q"],
                 requires=["core/pyproject.toml"]),
            Step("web lint", ["npm", "--prefix", "web", "run", "lint"], requires=["web/package.json"]),
            Step("web typecheck", ["npm", "--prefix", "web", "run", "typecheck"],
                 requires=["web/package.json"]),
            Step("web test", ["npm", "--prefix", "web", "run", "test"],
                 requires=["web/package.json"]),
        ]),
    ]


def _env() -> dict[str, str]:
    env = dict(os.environ)
    # Jeder Worktree testet seinen eigenen Code, nicht die editierbare Installation.
    src = str(ROOT / "core" / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("PYTHONUTF8", "1")
    return env


def run_step(step: Step) -> dict:
    missing = [p for p in step.requires if not (ROOT / p).exists()]
    if missing:
        return {"step": step.name, "status": "fehlt", "missing": missing, "seconds": 0.0}
    if step.clean:
        shutil.rmtree(ROOT / step.clean, ignore_errors=True)
    cmd = step.cmd
    if os.name == "nt" and cmd[0] == "npm":
        cmd = ["npm.cmd", *cmd[1:]]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=ROOT, env=_env(), capture_output=True, text=True, check=False,
                              encoding="utf-8", errors="replace", timeout=step.timeout_s)
        code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code = -1
        out = f"TIMEOUT nach {step.timeout_s} s\n{exc.stdout or ''}{exc.stderr or ''}"
    except FileNotFoundError as exc:
        code, out = -2, f"Befehl nicht gefunden: {exc}"
    seconds = round(time.monotonic() - t0, 1)
    tail = "\n".join(out.strip().splitlines()[-40:])
    return {"step": step.name, "status": "gruen" if code == 0 else "rot", "exit_code": code,
            "seconds": seconds, "tail": tail}


def gate_g7(results: dict[str, dict]) -> dict:
    """Laufzeit aus den Szenario-Schritten von G3 und G4 ableiten."""
    limits = {"S1: run-scenario": 180.0, "S2: run-scenario": 1800.0}
    measured, ok = {}, True
    for gid in ("G3", "G4"):
        for step in results.get(gid, {}).get("steps", []):
            if step["step"] in limits:
                measured[step["step"]] = step["seconds"]
                ok &= step["status"] == "gruen" and step["seconds"] <= limits[step["step"]]
    ok &= len(measured) == len(limits)
    return {"status": "gruen" if ok else "rot", "measured_s": measured, "limits_s": limits}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--fast", action="store_true", help="ohne S2 (G4, G7) und ohne G6")
    ap.add_argument("--gate", nargs="+", metavar="GID", help="nur diese Gates, z. B. G3 G5")
    args = ap.parse_args(argv)

    selected = [g for g in gates(args.fast)
                if (not args.gate or g.gid in args.gate) and not (args.fast and g.slow)]
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    for gate in selected:
        print(f"== {gate.gid} {gate.title}", flush=True)
        if gate.gid == "G7":
            results["G7"] = {"title": gate.title, **gate_g7(results)}
            print(f"   {results['G7']['status']}  {results['G7']['measured_s']}", flush=True)
            continue
        steps = []
        for step in gate.steps:
            res = run_step(step)
            steps.append(res)
            print(f"   {res['status']:6} {res['seconds']:>7.1f} s  {step.name}", flush=True)
            if res["status"] != "gruen":
                break  # Folgeschritte haengen am Ergebnis dieses Schritts
        status = "gruen" if steps and all(s["status"] == "gruen" for s in steps) else "rot"
        results[gate.gid] = {"title": gate.title, "status": status, "steps": steps}

    all_green = bool(results) and all(r["status"] == "gruen" for r in results.values())
    skipped = sorted({g.gid for g in gates(args.fast)} - set(results))
    report = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mode": "fast" if args.fast else ("partial" if args.gate else "full"),
        "all_green": all_green,
        "skipped": skipped,
        "gates": results,
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    print("\nGate  Status")
    for gid, r in results.items():
        print(f"{gid:5} {r['status']}")
    if skipped:
        print(f"nicht geprueft: {', '.join(skipped)}")
    print(f"Bericht: {(OUT / 'report.json').relative_to(ROOT)}")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
