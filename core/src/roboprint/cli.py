"""Kommandozeile: `roboprint run-scenario | serve | export-contracts` (SPEC §7)."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

# Parallel wird ueber Prozesse gerechnet (Pools je Teil, --jobs); BLAS-Threads je Prozess wuerden
# sich nur um die vCPU streiten. Muss vor dem ersten numpy-Import gesetzt sein; die Ergebnisse
# haengen nicht davon ab.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roboprint", description="RoboPrintIFC v2")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run-scenario", help="Szenario ausfuehren und Laufordner schreiben")
    run.add_argument("scenario", type=Path, help="Szenario-JSON")
    run.add_argument("--out", type=Path, required=True, help="Ausgabeordner")
    run.add_argument(
        "--jobs", type=int, default=0, help="Teile parallel in so vielen Prozessen (0 = Anzahl vCPU)"
    )

    serve = sub.add_parser("serve", help="API starten")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--runs", type=Path, default=Path("runs"))

    exp = sub.add_parser("export-contracts", help="JSON-Schemas der Artefakte schreiben")
    exp.add_argument("dir", type=Path, help="Zielordner")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-scenario":
        from roboprint.pipeline import run_scenario

        result = run_scenario(args.scenario, args.out, jobs=args.jobs)
        return int(result or 0)
    if args.command == "serve":
        import uvicorn

        from roboprint.api import create_app

        uvicorn.run(create_app(args.runs), host=args.host, port=args.port)
        return 0
    if args.command == "export-contracts":
        from roboprint.contracts import export_schemas

        export_schemas(args.dir)
        return 0
    return 2
