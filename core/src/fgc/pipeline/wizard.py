"""Interaktiver Einstieg (`fgc start`): Modell -> Wände -> Auswahl -> Slice -> Viewer.

Reine Dialogführung — Fachlogik lebt in ifc_io/eligibility/slicer, das
Artefakt-Schreiben in pipeline.actions, der Viewer-Start in
pipeline.viewer_launch. Die Frage-Helfer nehmen ein input_fn, damit Tests
Eingaben vortäuschen können.
"""

from __future__ import annotations

from pathlib import Path

from fgc.ifc_io import walls as ifc_walls
from fgc.paths import EXAMPLES_DIR, REPO_ROOT

DEFAULT_ROBOT = "doosan_m1013"


# --- Datei-Ermittlung -------------------------------------------------------


def discover_ifc_files(cwd: Path | None = None) -> list[Path]:
    """*.ifc aus examples/ (rekursiv) + Startverzeichnis (flach), dedupliziert."""
    cwd = (cwd or Path.cwd()).resolve()
    found: dict[Path, None] = {}
    if EXAMPLES_DIR.is_dir():
        for p in sorted(EXAMPLES_DIR.rglob("*.ifc")):
            found.setdefault(p.resolve(), None)
    for p in sorted(cwd.glob("*.ifc")):
        found.setdefault(p.resolve(), None)
    return list(found)


def display_path(path: Path) -> str:
    """Pfad relativ zum Repo, wenn möglich — kürzer zu lesen."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# --- Frage-Helfer -----------------------------------------------------------


def _read(prompt: str, input_fn) -> str | None:
    """Eine Zeile lesen; None bei Stream-Ende. BOM (gepipte Eingabe) tolerieren."""
    try:
        return input_fn(prompt).lstrip("\ufeff").strip().lower()
    except EOFError:
        return None


def ask_number(prompt: str, n: int, *, input_fn=input) -> int | None:
    """Nummer 1..n abfragen; leere Eingabe, 'q' oder Stream-Ende bricht ab (None)."""
    while True:
        raw = _read(prompt, input_fn)
        if raw is None or raw in ("", "q"):
            return None
        if raw.isdigit() and 1 <= int(raw) <= n:
            return int(raw) - 1
        print(f"  Bitte eine Zahl von 1 bis {n} eingeben (oder q = abbrechen).")


def ask_yes_no(prompt: str, *, default: bool = True, input_fn=input) -> bool:
    raw = _read(prompt, input_fn)
    if raw is None:
        return False  # Stream zu Ende -> nichts Aktives mehr tun
    if not raw:
        return default
    return raw in ("j", "ja", "y", "yes")


# --- Wand-Gruppierung -------------------------------------------------------

FILTER_LABELS = {
    "alle": "Alle Wände",
    "aussen": "Außenwände",
    "innen": "Innenwände",
    "unbekannt": "unbekannt (IsExternal fehlt im Modell)",
}


def walls_by_filter(walls) -> dict[str, list]:
    """Gruppiert Wände nach Pset_WallCommon.IsExternal für das Filter-Menü."""
    groups: dict[str, list] = {
        "alle": list(walls),
        "aussen": [w for w in walls if w.is_external is True],
        "innen": [w for w in walls if w.is_external is False],
        "unbekannt": [w for w in walls if w.is_external is None],
    }
    return groups


# --- Hauptablauf ------------------------------------------------------------


def run_wizard(*, input_fn=input) -> int:
    print("fgc start — vom IFC-Modell zur gesliceten Wand im Viewer.")
    print("(Enter oder q bricht jederzeit ab.)\n")

    # 1. Modell wählen
    files = discover_ifc_files()
    if not files:
        raw = input_fn("Keine IFC-Datei gefunden — Pfad zu einem Modell eingeben: ").strip()
        if not raw or not Path(raw).is_file():
            print("Keine Datei — Abbruch.")
            return 2
        model_path = Path(raw)
    else:
        print("Verfügbare IFC-Modelle:")
        for i, f in enumerate(files):
            print(f"  [{i + 1}] {display_path(f)}")
        idx = ask_number(f"Modell wählen [1-{len(files)}]: ", len(files), input_fn=input_fn)
        if idx is None:
            return 0
        model_path = files[idx]

    # 2. Wände lesen und nach innen/außen zählen
    print(f"\nLese {display_path(model_path)} … (bei großen Modellen dauert das)")
    walls = ifc_walls.load_walls(model_path)
    if not walls:
        print("Das Modell enthält keine IfcWall-Elemente.")
        return 1

    groups = walls_by_filter(walls)
    print(f"\n{len(walls)} Wände gefunden:")
    menu = [key for key in ("alle", "aussen", "innen", "unbekannt") if groups[key]]
    for i, key in enumerate(menu):
        print(f"  [{i + 1}] {FILTER_LABELS[key]} ({len(groups[key])})")
    idx = ask_number(f"Welche anzeigen? [1-{len(menu)}]: ", len(menu), input_fn=input_fn)
    if idx is None:
        return 0
    selected = groups[menu[idx]]

    # 3. Eignung prüfen und Wand wählen
    from fgc.domain.process_params import ProcessWindow, SliceParams
    from fgc.pipeline.actions import evaluate_walls
    from fgc.pipeline.report import candidate_reasons, candidates_table, slice_summary

    # Konfig-Beschaffung + Evaluation liegen in der Aktion; window brauchen wir
    # unten noch für die Slice-Parameter, darum hier zusätzlich geladen.
    window = ProcessWindow.load()
    candidates = evaluate_walls(model_path, DEFAULT_ROBOT, walls=selected)

    print()
    print(candidates_table(candidates, numbered=True))
    idx = ask_number(
        f"\nWand wählen [1-{len(selected)}]: ", len(selected), input_fn=input_fn
    )
    if idx is None:
        return 0
    wall, candidate = selected[idx], candidates[idx]

    if not candidate.eligible:
        print(f"WARNUNG: Wand ist laut E1 nicht druckgeeignet — {candidate_reasons(candidate)}")
        print("Slicing läuft trotzdem (explizite Auswahl).")

    # 4. Mit Defaults slicen
    from fgc.pipeline.actions import slice_to_run
    from fgc.pipeline.cli import slice_source

    params = SliceParams.from_window(window)
    print(
        f"\nSlice mit Defaults: {params.layer_height_mm} mm Schicht, "
        f"{params.strand_width_mm} mm Strang, {params.n_shells} Schalen …"
    )
    source = slice_source(model_path, wall.global_id, DEFAULT_ROBOT, params)
    run = slice_to_run(model_path, wall, params, source)
    if run is None:
        print("Slicer lieferte keine Targets (Konturen degeneriert?) — Abbruch.")
        return 1
    print(slice_summary(wall, params, run))

    # 5. Viewer öffnen? — startet dabei auch die Core-API (ADR-014).
    if ask_yes_no("\nViewer öffnen? [J/n] ", default=True, input_fn=input_fn):
        from fgc.pipeline.viewer_launch import ensure_api_server, open_run

        ensure_api_server()  # Core-API zusammen mit dem Viewer hochfahren
        open_run(run.run_dir)
    else:
        from fgc.pipeline.viewer_launch import run_url

        print(f"Später ansehen: {run_url(run.run_dir)}")
    return 0
