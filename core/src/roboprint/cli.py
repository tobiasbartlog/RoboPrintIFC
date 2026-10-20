"""Kommandozeile: `roboprint run-scenario | serve | export-contracts | pattern-preview` (SPEC §7).

`pattern-preview` zeichnet die 2D-Vorschau eines Muster-Presets (docs/muster/AUFTRAG.md, Nachtrag
18:20); Details in `roboprint.patterns.cli_preview`.
"""

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
    serve.add_argument(
        "--presets", type=Path, default=None, help="Ordner eigener Muster-Presets (Default <runs>/presets)"
    )

    exp = sub.add_parser("export-contracts", help="JSON-Schemas der Artefakte schreiben")
    exp.add_argument("dir", type=Path, help="Zielordner")

    # Argumente wie `patterns.cli_preview.add_arguments`, hier ohne den schweren Import des Pakets
    pp = sub.add_parser(
        "pattern-preview",
        help="2D-Vorschau eines Muster-Presets als SVG/JSON (Exit 1 bei Regelfehlern M1-M7)",
    )
    pp.add_argument("preset", type=Path, help="Preset-JSON (name, pattern, params, outline)")
    pp.add_argument("--svg", type=Path, default=None, help="SVG-Ausgabe")
    pp.add_argument("--json", type=Path, default=None, help="Vorschau als JSON (Format wie die API)")
    pp.add_argument("--length", type=float, default=None, help="Modullaenge in mm (mit --thickness)")
    pp.add_argument("--thickness", type=float, default=None, help="Wanddicke in mm (mit --length)")
    pp.add_argument("--layer", type=int, default=0, help="Schicht (Folgeschicht wird blass gezeigt)")
    pp.add_argument("--width-px", type=int, default=1000, help="Breite der SVG in Pixeln")
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

        uvicorn.run(create_app(args.runs, presets_dir=args.presets), host=args.host, port=args.port)
        return 0
    if args.command == "export-contracts":
        from roboprint.contracts import export_schemas

        export_schemas(args.dir)
        return 0
    if args.command == "pattern-preview":
        from roboprint.patterns.cli_preview import run

        return run(args)
    return 2
