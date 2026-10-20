"""fgc CLI — Orchestrierung der dateibasierten Pipeline (ADR-004).

Befehle:
    fgc start                             -> interaktiver Einstieg (Wizard)
    fgc walls list <model.ifc>            -> Laufordner mit candidates.json
    fgc slice <model.ifc> --wall <GlobalId> -> Laufordner mit wallspec.json,
        toolpath.json und context.json (Gebäudekontext, abwählbar via --no-context)
    fgc setup new                         -> setup.json aus 3 Roboterposen
        (3-Punkt-Antastverfahren, ADR-006, §9.3 Umsetzungsplan)
    fgc simulate --run <lauf> --setup <setup.json> -> trajectory.json im Lauf
        (Zeitinterpolation + Totzeitkompensation, Strang C, ADR-012)
    fgc emit-drl --run <lauf> --setup <setup.json> -> program.drl im Lauf
        (DRL-Postprozessor, per Target movel/movej, Change-on-Delta, ADR-011)

Die CLI verdrahtet nur Module — Logik lebt in ifc_io, eligibility, slicer,
pipeline.actions, setup.frame3p, simulation, postproc; der Dialog in pipeline.wizard.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fgc.domain.process_params import ProcessWindow, SliceParams
from fgc.ifc_io import walls as ifc_walls


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fgc", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser(
        "start",
        help="interaktiver Einstieg: Modell wählen, Wand wählen, slicen, Viewer öffnen",
    )

    walls = sub.add_parser("walls", help="Wände eines IFC-Modells listen/prüfen (E1)")
    walls_sub = walls.add_subparsers(dest="walls_command")
    walls_list = walls_sub.add_parser("list", help="druckbare Kandidaten -> candidates.json")
    walls_list.add_argument("model", help="Pfad zum IFC-Modell")
    walls_list.add_argument("--robot", default="doosan_m1013", help="Roboterdefinition aus robots/")

    slice_ = sub.add_parser("slice", help="Wand slicen -> toolpath.json")
    slice_.add_argument("model", help="Pfad zum IFC-Modell")
    slice_.add_argument("--wall", required=True, help="GlobalId der Wand (aus candidates.json)")
    slice_.add_argument("--robot", default="doosan_m1013", help="Roboterdefinition aus robots/")
    slice_.add_argument("--layer-height", type=float, default=None, help="Schichthöhe in mm")
    slice_.add_argument("--strand-width", type=float, default=None, help="Strangbreite in mm")
    slice_.add_argument("--shells", type=int, default=None, help="Anzahl Schalen je Kontur")
    slice_.add_argument(
        "--no-context",
        action="store_true",
        help="kein context.json (Gebäudekontext für den Viewer) schreiben",
    )

    # --- fgc simulate --------------------------------------------------------
    simulate = sub.add_parser(
        "simulate",
        help="Toolpath-Lauf + Setup -> trajectory.json (Zeit + Totzeit, Strang C)",
    )
    simulate.add_argument(
        "--run",
        required=True,
        metavar="LAUFORDNER",
        help="Laufordner mit toolpath.json (aus fgc slice)",
    )
    simulate.add_argument(
        "--setup",
        required=True,
        metavar="SETUP.JSON",
        help="Setup-Artefakt (aus fgc setup new)",
    )
    simulate.add_argument(
        "--robot",
        default=None,
        help="Roboterdefinition überschreiben (default: robot-Eintrag des Setups)",
    )

    # --- fgc emit-drl --------------------------------------------------------
    emit_drl = sub.add_parser(
        "emit-drl",
        help="Toolpath-Lauf + Setup -> program.drl (DRL-Postprozessor, ADR-011, Strang C)",
    )
    emit_drl.add_argument(
        "--run",
        required=True,
        metavar="LAUFORDNER",
        help="Laufordner mit toolpath.json (aus fgc slice)",
    )
    emit_drl.add_argument(
        "--setup",
        required=True,
        metavar="SETUP.JSON",
        help="Setup-Artefakt mit Kanal-Mapping (aus fgc setup new)",
    )

    # --- fgc setup -----------------------------------------------------------
    setup = sub.add_parser("setup", help="Setup-Artefakt verwalten (ADR-006)")
    setup_sub = setup.add_subparsers(dest="setup_command")
    setup_new = setup_sub.add_parser(
        "new",
        help="3-Punkt-Antasten → schema-validierte setup.json (ADR-006, §9.3)",
    )
    setup_new.add_argument(
        "--p0",
        metavar="X,Y,Z",
        help=(
            "Wandursprung in mm (Teach-Pendant-Ablesung). "
            "Wenn nicht angegeben: interaktive Eingabe."
        ),
    )
    setup_new.add_argument(
        "--p1",
        metavar="X,Y,Z",
        help="Punkt auf der positiven X-Achse (Wandlängsrichtung) in mm.",
    )
    setup_new.add_argument(
        "--p2",
        metavar="X,Y,Z",
        help="Punkt in der XY-Ebene (Wandhöhenrichtung, nicht auf X-Achse) in mm.",
    )
    setup_new.add_argument(
        "--robot",
        default="doosan_m1013",
        help="Roboterdefinition aus robots/ (default: doosan_m1013)",
    )
    setup_new.add_argument(
        "--output",
        default="setup.json",
        help="Ausgabedatei (default: setup.json im aktuellen Verzeichnis)",
    )
    setup_new.add_argument(
        "--template",
        metavar="PATH",
        help=(
            "Vorlage-setup.json: TCP, Kanal-Mapping und Totzeit werden daraus "
            "übernommen. Ohne --template: provisorische Standardwerte."
        ),
    )

    # --- fgc campaign --------------------------------------------------------
    campaign = sub.add_parser(
        "campaign",
        help=(
            "Datenkampagne: Kandidatenraum systematisch sampeln + exakt etikettieren "
            "-> Datensatz-Artefakt (Surrogat-Kaltstart, PRD #183 Stufe 4)"
        ),
    )
    campaign.add_argument(
        "--out",
        default="datasets/surrogate_dataset.json",
        help="Ausgabepfad des Datensatz-Artefakts (default: datasets/surrogate_dataset.json)",
    )
    campaign.add_argument(
        "--robot", default="doosan_m1013", help="Roboterdefinition aus robots/"
    )
    campaign.add_argument(
        "--lengths", default=None, metavar="L1,L2,…", help="Wandlängen (mm), komma-getrennt"
    )
    campaign.add_argument(
        "--heights", default=None, metavar="H1,H2,…", help="Wandhöhen (mm), komma-getrennt"
    )
    campaign.add_argument(
        "--thicknesses", default=None, metavar="T1,T2,…", help="Wanddicken (mm), komma-getrennt"
    )
    campaign.add_argument(
        "--cap", type=int, default=None, help="Teilungs-Deckel je Achse (Band-Raster #216)"
    )
    campaign.add_argument(
        "--limit", type=int, default=None, help="Mini-Stichprobe: nur die ersten N Kandidaten"
    )
    campaign.add_argument(
        "--seconds-per-label", type=float, default=None,
        help="Grobe Kosten je Etikett (s) für die Umfangsansage (default: AP-1-Messwert)",
    )
    campaign.add_argument(
        "--yes", action="store_true", help="Umfangsansage bestätigen ohne Rückfrage"
    )
    campaign.add_argument(
        "--dry-run", action="store_true", help="nur die Umfangsansage zeigen, nicht etikettieren"
    )

    # --- fgc surrogate-train -------------------------------------------------
    surrogate = sub.add_parser(
        "surrogate-train",
        help=(
            "Surrogat-Vorsortierer deterministisch aus einem Datensatz-Artefakt trainieren "
            "-> versioniertes Modell-Artefakt (PRD #183 Stufe 4, Issue #219)"
        ),
    )
    surrogate.add_argument(
        "--dataset", default="datasets/surrogate_dataset.json",
        help="Datensatz-Artefakt aus `fgc campaign` (default: datasets/surrogate_dataset.json)",
    )
    surrogate.add_argument(
        "--out", default="models/surrogate.json",
        help="Ausgabepfad des Modell-Artefakts (default: models/surrogate.json)",
    )
    surrogate.add_argument(
        "--seed", type=int, default=0, help="Trainings-Seed (fester Seed ⇒ bit-gleiches Modell)"
    )
    surrogate.add_argument(
        "--n-estimators", type=int, default=60, help="Anzahl Boosting-Runden (default: 60)"
    )
    surrogate.add_argument(
        "--learning-rate", type=float, default=0.1, help="Boosting-Schrittweite (default: 0.1)"
    )
    surrogate.add_argument(
        "--max-depth", type=int, default=3, help="max. Baumtiefe je Runde (default: 3)"
    )

    # --- fgc benchmark -------------------------------------------------------
    benchmark = sub.add_parser(
        "benchmark",
        help=(
            "Benchmark-Harness: Arme Greedy/Beam/Beam+Surrogat auf demselben eingefrorenen "
            "Stand, byte-vergleichbar -> Protokoll-Artefakt (Vergleichspaper, PRD #183, #220)"
        ),
    )
    benchmark.add_argument("--project", required=True, help="Projekt-Slug (der eingefrorene Stand)")
    benchmark.add_argument("--job", default="default", help="Druckjob-ID (default: default)")
    benchmark.add_argument(
        "--model", default=None,
        help=(
            "Surrogat-Modell-Artefakt fuer den dritten Arm (Sollbruch-Gate): fehlt es / "
            "ist es ungueltig, laeuft der Benchmark zweiarmig (ohne Warten)."
        ),
    )
    benchmark.add_argument(
        "--out", default="benchmarks/benchmark_protocol.json",
        help="Ausgabepfad des Protokoll-Artefakts (default: benchmarks/benchmark_protocol.json)",
    )
    benchmark.add_argument(
        "--call-budget", type=int, default=None,
        help="Aufruf-Kontingent je Arm (default: DEFAULT_CALL_BUDGET #215) — pinnt alle Arme",
    )
    benchmark.add_argument(
        "--robot", default="doosan_m1013", help="Roboterdefinition aus robots/"
    )

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command == "start":
        from fgc.pipeline.wizard import run_wizard

        return run_wizard()
    if args.command == "walls":
        if getattr(args, "walls_command", None) != "list":
            walls.print_help()
            return 2
        return _cmd_walls_list(args)
    if args.command == "slice":
        return _cmd_slice(args)
    if args.command == "simulate":
        return _cmd_simulate(args)
    if args.command == "emit-drl":
        return _cmd_emit_drl(args)
    if args.command == "setup":
        if getattr(args, "setup_command", None) != "new":
            setup.print_help()
            return 2
        return _cmd_setup_new(args)
    if args.command == "campaign":
        return _cmd_campaign(args)
    if args.command == "surrogate-train":
        return _cmd_surrogate_train(args)
    if args.command == "benchmark":
        return _cmd_benchmark(args)
    return 2


# --- Provenienz-Quellstrings ------------------------------------------------
# Co-lokalisiert mit den argparse-Flags in main(): hier — und nur hier —
# werden die CLI-Flag-Namen zu einem reproduzierbaren Aufruf für den
# Provenienzblock nachbuchstabiert. Wird ein Flag umbenannt, zieht es hier
# nach. Die Aktionsschicht (actions.slice_to_run) und die künftige API bekommen
# den fertigen String und kennen die Flag-Namen nicht.


def walls_list_source(model_path: Path, robot_name: str) -> str:
    return f"fgc walls list {model_path.name} --robot {robot_name}"


def slice_source(
    model_path: Path, wall_global_id: str, robot_name: str, params: SliceParams
) -> str:
    return (
        f"fgc slice {model_path.name} --wall {wall_global_id} --robot {robot_name} "
        f"--layer-height {params.layer_height_mm} --strand-width {params.strand_width_mm} "
        f"--shells {params.n_shells}"
    )


def simulate_source(run_dir: Path, setup_path: Path, robot_name: str) -> str:
    return (
        f"fgc simulate --run {run_dir.name} --setup {setup_path.name} "
        f"--robot {robot_name}"
    )


def emit_drl_source(run_dir: Path, setup_path: Path) -> str:
    return f"fgc emit-drl --run {run_dir.name} --setup {setup_path.name}"


def campaign_source(
    robot: str, out: str, plan_dict: dict, limit: int | None
) -> str:
    """Reproduzierbarer Aufruf für die Provenienz des Datensatz-Artefakts (ADR-004)."""

    def fmt(vals: list) -> str:
        return ",".join(str(v) for v in vals)

    parts = [
        "fgc campaign",
        f"--robot {robot}",
        f"--out {out}",
        f"--lengths {fmt(plan_dict['lengths_mm'])}",
        f"--heights {fmt(plan_dict['heights_mm'])}",
        f"--thicknesses {fmt(plan_dict['thicknesses_mm'])}",
        f"--cap {plan_dict['cap']}",
    ]
    if limit is not None:
        parts.append(f"--limit {limit}")
    return " ".join(parts)


def surrogate_train_source(dataset: str, out: str, seed: int) -> str:
    """Reproduzierbarer Aufruf für die Provenienz des Surrogat-Modell-Artefakts (ADR-004)."""
    return f"fgc surrogate-train --dataset {dataset} --out {out} --seed {seed}"


def benchmark_source(
    project: str, job: str, out: str, model: str | None, call_budget: int
) -> str:
    """Reproduzierbarer Aufruf für die Provenienz des Benchmark-Protokolls (ADR-004)."""
    parts = [
        "fgc benchmark",
        f"--project {project}",
        f"--job {job}",
        f"--out {out}",
        f"--call-budget {call_budget}",
    ]
    if model is not None:
        parts.append(f"--model {model}")
    return " ".join(parts)


def setup_new_source(
    p0: list[float], p1: list[float], p2: list[float], robot: str, output: str
) -> str:
    """Reproduzierbarer Aufruf für den Provenienzblock von setup.json."""

    def fmt(pts: list[float]) -> str:
        return ",".join(str(round(v, 3)) for v in pts)

    return (
        f"fgc setup new "
        f"--p0 {fmt(p0)} --p1 {fmt(p1)} --p2 {fmt(p2)} "
        f"--robot {robot} --output {output}"
    )


# --- Hilfsfunktionen --------------------------------------------------------


def _parse_xyz(text: str, label: str) -> list[float]:
    """Parst 'x,y,z'-String zu Liste von 3 Floats."""
    parts = [s.strip() for s in text.split(",")]
    if len(parts) != 3:
        raise ValueError(
            f"{label}: Erwartet drei Komma-getrennte Zahlen (x,y,z), "
            f"erhalten: {text!r}"
        )
    try:
        return [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError(
            f"{label}: Keine gültige Zahl in {text!r} — erwartet z. B. '1000,500,0'"
        ) from exc


def _prompt_xyz(label: str) -> list[float]:
    """Interaktive Eingabe einer x,y,z-Pose (Teach-Pendant-Ablesung)."""
    while True:
        try:
            raw = input(f"  {label} (x,y,z in mm): ").strip()
        except EOFError:
            raise SystemExit(1) from None
        if not raw:
            print("  (Eingabe leer — bitte Zahlen eingeben)", file=sys.stderr)
            continue
        try:
            return _parse_xyz(raw, label)
        except ValueError as exc:
            print(f"  Fehler: {exc}", file=sys.stderr)


def _cmd_walls_list(args: argparse.Namespace) -> int:
    from fgc.pipeline.actions import walls_to_run
    from fgc.pipeline.report import candidates_table

    model_path = Path(args.model)
    source = walls_list_source(model_path, args.robot)
    result = walls_to_run(model_path, args.robot, source)

    print(candidates_table(result.candidates))
    print(f"\ncandidates.json: {result.candidates_path}")
    print(f"model.glb:       {result.model_glb_path}")
    print(f"model_map.json:  {result.model_map_path}")
    return 0


def _cmd_slice(args: argparse.Namespace) -> int:
    from fgc.pipeline.actions import evaluate_walls, slice_to_run
    from fgc.pipeline.report import candidate_reasons, slice_summary

    model_path = Path(args.model)
    window = ProcessWindow.load()
    params = SliceParams.from_window(
        window,
        layer_height_mm=args.layer_height,
        strand_width_mm=args.strand_width,
        n_shells=args.shells,
    )

    try:
        wall = ifc_walls.load_wall(model_path, args.wall)
    except (KeyError, RuntimeError) as exc:
        print(f"fgc slice: {exc}", file=sys.stderr)
        return 1

    candidate = evaluate_walls(model_path, args.robot, walls=[wall])[0]
    if not candidate.eligible:
        print(
            f"WARNUNG: Wand ist laut E1 nicht druckgeeignet — {candidate_reasons(candidate)}",
            file=sys.stderr,
        )
        print("Slicing läuft trotzdem (explizite Auswahl per GlobalId).", file=sys.stderr)

    source = slice_source(model_path, wall.global_id, args.robot, params)
    run = slice_to_run(
        model_path, wall, params, source, with_context=not args.no_context
    )
    if run is None:
        print("fgc slice: Slicer lieferte keine Targets (Konturen degeneriert?)", file=sys.stderr)
        return 1

    print(slice_summary(wall, params, run))
    return 0


def _cmd_simulate(args: argparse.Namespace) -> int:
    """fgc simulate: Toolpath-Lauf + Setup → trajectory.json (Strang C, ADR-012)."""
    import json

    from fgc.pipeline.actions import simulate_run

    run_dir = Path(args.run)
    setup_path = Path(args.setup)
    if not run_dir.is_dir():
        print(f"fgc simulate: Laufordner nicht gefunden: {run_dir}", file=sys.stderr)
        return 1

    # Robotername für den Provenienz-String: CLI-Override oder Setup-Eintrag.
    robot_name = args.robot
    if robot_name is None:
        try:
            robot_name = json.loads(setup_path.read_text(encoding="utf-8"))["robot"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
            print(f"fgc simulate: Setup nicht lesbar: {exc}", file=sys.stderr)
            return 1

    source = simulate_source(run_dir, setup_path, robot_name)
    try:
        result = simulate_run(run_dir, setup_path, source, robot_name=args.robot)
    except FileNotFoundError as exc:
        print(f"fgc simulate: {exc}", file=sys.stderr)
        return 1

    print(f"trajectory.json: {result.trajectory_path}")
    print(
        f"  {result.n_samples} Samples, "
        f"Gesamtdauer {result.duration_s:.3f} s (Druckzeitschätzung)"
    )
    print(f"  io totzeitkompensiert: {'ja' if result.io_compensated else 'nein'}")
    if result.n_warnings:
        print(f"  {result.n_warnings} Kinematik-Warnung(en) in meta.warnings", file=sys.stderr)
    return 0


def _cmd_emit_drl(args: argparse.Namespace) -> int:
    """fgc emit-drl: Trajectory-Lauf + Setup → program.drl (Strang C, ADR-011)."""
    from fgc.pipeline.actions import emit_drl_run

    run_dir = Path(args.run)
    setup_path = Path(args.setup)
    if not run_dir.is_dir():
        print(f"fgc emit-drl: Laufordner nicht gefunden: {run_dir}", file=sys.stderr)
        return 1

    source = emit_drl_source(run_dir, setup_path)
    try:
        result = emit_drl_run(run_dir, setup_path, source)
    except FileNotFoundError as exc:
        print(f"fgc emit-drl: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"fgc emit-drl: {exc}", file=sys.stderr)
        return 1

    print(f"program.drl: {result.drl_path}")
    print(f"  {result.n_targets} Targets emittiert")
    return 0


def _parse_floats(text: str | None, label: str) -> tuple[float, ...] | None:
    """Parst 'a,b,c' zu einem Float-Tupel — oder ``None`` (Plan-Default)."""
    if text is None:
        return None
    try:
        return tuple(float(s.strip()) for s in text.split(",") if s.strip())
    except ValueError as exc:
        raise ValueError(f"{label}: keine gültige Zahl in {text!r}") from exc


def _cmd_campaign(args: argparse.Namespace) -> int:
    """fgc campaign: Kandidatenraum sampeln + exakt etikettieren -> Datensatz (PRD #183 St. 4)."""
    from fgc.decompose.kampagne import (
        DEFAULT_CAP,
        DEFAULT_SECONDS_PER_LABEL,
        SamplingPlan,
        campaign_scope,
    )

    # Sampling-Plan aus den (optionalen) Achsen-Overrides — sonst der dokumentierte Default.
    try:
        lengths = _parse_floats(args.lengths, "--lengths")
        heights = _parse_floats(args.heights, "--heights")
        thicknesses = _parse_floats(args.thicknesses, "--thicknesses")
    except ValueError as exc:
        print(f"fgc campaign: {exc}", file=sys.stderr)
        return 1

    plan_kwargs: dict = {}
    if lengths is not None:
        plan_kwargs["lengths_mm"] = lengths
    if heights is not None:
        plan_kwargs["heights_mm"] = heights
    if thicknesses is not None:
        plan_kwargs["thicknesses_mm"] = thicknesses
    plan_kwargs["cap"] = args.cap if args.cap is not None else DEFAULT_CAP
    try:
        plan = SamplingPlan(**plan_kwargs)
    except ValueError as exc:
        print(f"fgc campaign: {exc}", file=sys.stderr)
        return 1

    spl = (
        args.seconds_per_label
        if args.seconds_per_label is not None
        else DEFAULT_SECONDS_PER_LABEL
    )
    scope = campaign_scope(plan, seconds_per_label=spl)

    # --- Umfangsansage vor Start (Muster #175) -------------------------------
    print(scope.announcement())
    if args.limit is not None:
        print(f"  (Mini-Stichprobe: nur die ersten {args.limit} Kandidaten)")
    if args.dry_run:
        print("(dry-run: keine Etikettierung)")
        return 0

    # Bewusste Nutzerwahl: der Lauf ist teuer (CPU-exakt, ~Sekunden je Etikett).
    if not args.yes:
        try:
            answer = input("Kampagne starten? [j/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("j", "ja", "y", "yes"):
            print("Abgebrochen (keine Bestätigung).")
            return 0

    from fgc.pipeline.kampagne import run_data_campaign

    out = args.out
    source = campaign_source(args.robot, out, plan.to_dict(), args.limit)

    def _progress(done: int, total: int) -> None:
        if done == total or done % 25 == 0:
            print(f"  etikettiert {done}/{total}", file=sys.stderr)

    print(f"Etikettiere (CPU-exakt, Roboter {args.robot}) — Abbruch mit Ctrl-C, Teilstand bleibt.")
    try:
        result = run_data_campaign(
            plan, Path(out), source,
            robot_name=args.robot, seconds_per_label=spl,
            on_progress=_progress, limit=args.limit,
        )
    except KeyboardInterrupt:
        print(
            "\nAbgebrochen — kein Teilstand geschrieben (vor dem ersten Etikett).",
            file=sys.stderr,
        )
        return 130

    art = result.artifact
    print(f"\nDatensatz: {result.dataset_path.resolve()}")
    print(f"  Etiketten: {art['n_samples']} / {art['n_candidates_planned']} geplant")
    print(f"  Teilstand: {'ja' if art['partial'] else 'nein'}")
    print(f"  Herkunftsverteilung: {art['label_source_distribution']}")
    print(
        f"  trainingstauglich: {art['training']['training_safe_count']}, "
        f"nicht: {art['training']['non_training_count']}"
    )
    return 0


def _cmd_surrogate_train(args: argparse.Namespace) -> int:
    """fgc surrogate-train: Datensatz-Artefakt → deterministisch trainiertes Modell (#219)."""
    import json

    from fgc.decompose.surrogat import save_surrogat, train_surrogat
    from fgc.pipeline.provenance import make_provenance

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(
            f"fgc surrogate-train: Datensatz {dataset_path} nicht gefunden — "
            "zuerst `fgc campaign` laufen lassen.",
            file=sys.stderr,
        )
        return 1
    try:
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"fgc surrogate-train: Datensatz nicht lesbar: {exc}", file=sys.stderr)
        return 1

    source = surrogate_train_source(args.dataset, args.out, args.seed)
    try:
        model = train_surrogat(
            dataset,
            source=source,
            provenance=make_provenance(source),
            seed=args.seed,
            n_estimators=args.n_estimators,
            learning_rate=args.learning_rate,
            max_depth=args.max_depth,
        )
    except ValueError as exc:
        print(f"fgc surrogate-train: {exc}", file=sys.stderr)
        return 1

    out_path = save_surrogat(model, Path(args.out))
    t = model.training
    print(f"Modell: {out_path.resolve()}")
    print(f"  Trainingszeilen: {t['n_used']} / {t['n_total']} (Policy v1)")
    print(
        f"  verworfen: nicht-trainingstauglich {t['n_rejected_non_training']}, "
        f"ohne Urteil {t['n_rejected_bad_verdict']}"
    )
    print(f"  benutzte Label-Quellen: {t['label_source_distribution_used']}")
    print(
        f"  Seed {model.seed}, {len(model.gb.trees)} Boosting-Runden, "
        f"Merkmale {len(model.features)}"
    )
    return 0


def _cmd_benchmark(args: argparse.Namespace) -> int:
    """fgc benchmark: Arme Greedy/Beam/Beam+Surrogat byte-vergleichbar -> Protokoll (#220)."""
    from fgc.decompose.propose import DEFAULT_CALL_BUDGET
    from fgc.pipeline.benchmark import run_benchmark

    call_budget = args.call_budget if args.call_budget is not None else DEFAULT_CALL_BUDGET
    model_path = Path(args.model) if args.model else None
    source = benchmark_source(args.project, args.job, args.out, args.model, call_budget)

    try:
        result = run_benchmark(
            args.project, source, Path(args.out),
            job_id=args.job, model_path=model_path,
            call_budget=call_budget, robot_name=args.robot,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"fgc benchmark: {exc}", file=sys.stderr)
        return 1

    gate = result.protocol["gate"]
    print(f"Protokoll: {result.protocol_path.resolve()}")
    print(f"  Gate-Entscheid: {gate['arm_label']} — Arme {gate['arms']}")
    print(
        f"  dritter Arm (Beam+Surrogat): "
        f"{'JA' if gate['surrogat_arm']['ok'] else 'NEIN'} "
        f"({gate['surrogat_arm']['reason']})"
    )
    print(f"  vierter Arm (Beam+GPU): NEIN ({gate['gpu_arm']['reason']})")
    n_cases = result.protocol["frozen_state"]["n_cases"]
    print(f"  Läufe: {len(result.runs)} ({gate['arm_count']} Arme × {n_cases} Fall/Fälle)")
    return 0


def _cmd_setup_new(args: argparse.Namespace) -> int:
    """fgc setup new: 3 Roboterposen → schema-validierte setup.json (ADR-006, §9.3)."""
    import json

    from fgc import domain
    from fgc.pipeline.provenance import make_provenance
    from fgc.setup import (
        PROVISIONAL_DEADTIME,
        PROVISIONAL_IO_CHANNELS,
        PROVISIONAL_TCP,
        setup_artifact,
        three_point_frame,
    )

    # --- Posen einlesen (CLI-Arg oder interaktiv) ----------------------------
    print("3-Punkt-Antastverfahren (ADR-006): Posen vom Teach-Pendant ablesen.")
    try:
        p0 = _parse_xyz(args.p0, "P0") if args.p0 else _prompt_xyz("P0 — Wandursprung")
        p1 = _parse_xyz(args.p1, "P1") if args.p1 else _prompt_xyz("P1 — Punkt auf X-Achse")
        p2 = (
            _parse_xyz(args.p2, "P2")
            if args.p2
            else _prompt_xyz("P2 — Punkt in XY-Ebene (Wandhöhe)")
        )
    except ValueError as exc:
        print(f"fgc setup new: {exc}", file=sys.stderr)
        return 1

    # --- Frame berechnen -----------------------------------------------------
    try:
        pos_mm, quat = three_point_frame(p0, p1, p2)
    except ValueError as exc:
        print(f"fgc setup new: Geometriefehler — {exc}", file=sys.stderr)
        return 1

    wall_to_base = {"pos_mm": [round(v, 3) for v in pos_mm], "quat": quat}

    # --- TCP / IO-Kanäle / Totzeit: Vorlage oder provisorische Defaults ------
    provisional_warn = False
    if args.template:
        tmpl_path = Path(args.template)
        try:
            tmpl = json.loads(tmpl_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(f"fgc setup new: Vorlage nicht gefunden: {tmpl_path}", file=sys.stderr)
            return 1
        except json.JSONDecodeError as exc:
            print(f"fgc setup new: Vorlage ist kein gültiges JSON: {exc}", file=sys.stderr)
            return 1
        tcp = tmpl.get("tcp", PROVISIONAL_TCP)
        io_channels = tmpl.get("io_channels", PROVISIONAL_IO_CHANNELS)
        deadtime = tmpl.get("deadtime", PROVISIONAL_DEADTIME)
    else:
        tcp = PROVISIONAL_TCP
        io_channels = PROVISIONAL_IO_CHANNELS
        deadtime = PROVISIONAL_DEADTIME
        provisional_warn = True

    # --- Provenienz und Artefakt ---------------------------------------------
    source = setup_new_source(p0, p1, p2, args.robot, args.output)
    provenance = make_provenance(source)
    artifact = setup_artifact(
        robot=args.robot,
        wall_to_base=wall_to_base,
        tcp=tcp,
        io_channels=io_channels,
        deadtime=deadtime,
        provenance=provenance,
    )

    # --- Schema-Validierung --------------------------------------------------
    try:
        domain.validate(artifact, "setup")
    except Exception as exc:  # noqa: BLE001
        print(f"fgc setup new: Schema-Validierung fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    # --- Schreiben -----------------------------------------------------------
    output_path = Path(args.output)
    output_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nsetup.json:    {output_path.resolve()}")
    print(f"wall_to_base:  pos_mm={[round(v, 3) for v in pos_mm]}")
    print(f"               quat  ={[round(v, 6) for v in quat]}")
    print(f"robot:         {args.robot}")

    if provisional_warn:
        print(
            "\nHINWEIS: TCP, Kanal-Mapping und Totzeit sind provisorische Standardwerte.",
            file=sys.stderr,
        )
        print(
            "  Bitte nach Spike S1/S1b mit Messwerten aktualisieren oder",
            file=sys.stderr,
        )
        print(
            "  --template <gemessenes_setup.json> übergeben.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
