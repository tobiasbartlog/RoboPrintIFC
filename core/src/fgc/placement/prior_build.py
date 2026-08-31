"""fgc.placement.prior_build — Generator der W×T-Prior-Tabelle (ADR-026 Punkt 3, #230).

Baut aus dem gemessenen W×T-Praedikat-Gitter
(``experiments/collision_standoff_sweep/data_grid/meta_wt.json``) die **kompakte,
versionierte** Prior-Tabelle: je (Breite, Dicke) H_max + Best-Setup (Abstand,
Basishoehe, IK-Konfig), geschluesselt auf **Roboter + Tool**, mit ADR-004-Provenienz
(Herkunfts-Commit, Gitter-Parameter — Muster des Surrogat-Ausweises #219). Die
Roh-Zeilen des Gitters wandern **nicht** ins Artefakt (nur die Zusammenfassung).

Die im Gitter **abgebrochenen** Zellen (nicht in ``hmax_by_wt`` = das volle
W×T-Produkt minus die vermessenen) gehen als Status ``angenommen-unmachbar`` hinein —
**ehrliche Annahme, nie erfundener Messwert** (Ersatz durch Messung: #226).

**Regenerieren erfordert keine Codeaenderung** — nur ein Aufruf::

    PYTHONPATH=core/src python -m fgc.placement.prior_build \\
        --grid-meta experiments/collision_standoff_sweep/data_grid/meta_wt.json \\
        --robot doosan_m1013 --tool 30gut

(Alle Argumente haben Defaults, die genau das eingecheckte Artefakt reproduzieren.)

``build_prior_artifact`` ist die **reine** Kernfunktion (Gitter-Meta + Referenz-Tool
→ Artefakt-Dict), byte-stabil serialisiert ueber ``sort_keys`` — Golden-Roundtrip #230.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fgc.placement.prior import (
    PRIOR_ARTIFACT_KIND,
    PRIOR_SCHEMA_VERSION,
    STATUS_ASSUMED_INFEASIBLE,
    STATUS_MEASURED,
)

if TYPE_CHECKING:
    from fgc.domain.tool import ToolDef

#: Die Gitter-Parameter-Schluessel aus ``meta_wt.json``, die als Provenienz ins
#: Artefakt wandern (die vollstaendigen Stuetzstellen + Messkonvention).
_GRID_KEYS = (
    "widths",
    "thicks",
    "standoffs",
    "base_heights",
    "box_height_mm",
    "configs",
    "strict_reach",
    "safety_mm",
)


def _cell_key(width_mm: float, thickness_mm: float) -> str:
    return f"{int(round(width_mm))}_{int(round(thickness_mm))}"


def tool_reference(tool: ToolDef) -> dict[str, Any]:
    """Der Referenz-Tool-Ausweis fuers Artefakt: Name + TCP-Versatz + Huellmass.

    TCP-Versatz + Huellmass sind die beiden Groessen der Aehnlichkeits-Regel (ADR-026
    Punkt 4). Fehlt das Huellmass (Altbestand vor #229), steht ``null`` — der Prior
    passt dann nur zum namensgleichen Tool selbst („unbekannt", kein Uebertrag).
    """
    pos = None
    if tool.tcp_frame and tool.tcp_frame.get("pos_mm"):
        pos = [float(c) for c in tool.tcp_frame["pos_mm"][:3]]
    env = None
    if tool.envelope_mm:
        env = {
            "radius_mm": float(tool.envelope_mm["radius_mm"]),
            "length_mm": float(tool.envelope_mm["length_mm"]),
        }
    return {"name": tool.name, "tcp_pos_mm": pos, "envelope_mm": env}


def build_prior_artifact(
    grid_meta: dict[str, Any],
    robot_name: str,
    tool_ref: dict[str, Any],
    *,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """**Reine** Kernfunktion: Gitter-Meta + Referenz-Tool → Prior-Artefakt-Dict.

    Baut das volle W×T-Produkt aus ``widths`` × ``thicks``; jede in ``hmax_by_wt``
    vermessene Zelle wird ``measured`` mit H_max + Best-Setup, jede fehlende
    ``angenommen-unmachbar`` (H_max unbekannt, kein Best-Setup). Deterministisch und
    unabhaengig von der Zeilenreihenfolge (``sort_keys`` beim Schreiben).
    """
    hmax_by_wt = grid_meta.get("hmax_by_wt") or {}
    widths = [float(w) for w in grid_meta.get("widths") or []]
    thicks = [float(t) for t in grid_meta.get("thicks") or []]

    cells: dict[str, dict[str, Any]] = {}
    for w in widths:
        for t in thicks:
            key = _cell_key(w, t)
            cell: dict[str, Any] = {"width_mm": w, "thickness_mm": t}
            entry = hmax_by_wt.get(key)
            if entry:
                # Gitter-Format je Zelle: [H_max, base_height, config, standoff].
                h_max, base_height, config, standoff = entry
                cell["status"] = STATUS_MEASURED
                cell["h_max_mm"] = float(h_max)
                cell["best"] = {
                    "standoff_mm": float(standoff),
                    "base_height_mm": float(base_height),
                    "ik_config": str(config),
                }
            else:
                # Abgebrochene Messzelle — ehrliche Annahme, nie erfundener Messwert (#226).
                cell["status"] = STATUS_ASSUMED_INFEASIBLE
                cell["h_max_mm"] = None
                cell["best"] = None
            cells[key] = cell

    grid = {k: grid_meta[k] for k in _GRID_KEYS if k in grid_meta}
    return {
        "kind": PRIOR_ARTIFACT_KIND,
        "schema_version": PRIOR_SCHEMA_VERSION,
        "robot": robot_name,
        "tool": tool_ref,
        "grid": grid,
        "provenance": provenance,
        "cells": cells,
    }


def _grid_provenance(source: str, grid_meta: dict[str, Any], grid_meta_path: str) -> dict[str, Any]:
    from fgc.pipeline.provenance import make_provenance

    prov = make_provenance(source)
    prov["grid_meta_path"] = grid_meta_path
    prov["grid_project"] = grid_meta.get("project")
    prov["grid_generated_by"] = grid_meta.get("generated_by")
    prov["grid_git_commit"] = grid_meta.get("git_commit")
    prov["grid_partial"] = bool(grid_meta.get("partial"))
    prov["grid_n_done"] = grid_meta.get("n_done")
    return prov


def dump_artifact(artifact: dict[str, Any]) -> str:
    """Byte-stabile Serialisierung (``sort_keys`` — Golden-Roundtrip #230)."""
    return json.dumps(
        artifact, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False
    ) + "\n"


# --------------------------------------------------------------------------- #
# CLI (regenerieren ohne Codeaenderung)
# --------------------------------------------------------------------------- #


def _default_grid_meta() -> Path:
    from fgc.paths import REPO_ROOT

    return REPO_ROOT / "experiments" / "collision_standoff_sweep" / "data_grid" / "meta_wt.json"


def _default_out(robot: str, tool: str) -> Path:
    from fgc.paths import PRIORS_DIR

    return PRIORS_DIR / f"placement_prior.{robot}.{tool}.json"


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(
        prog="python -m fgc.placement.prior_build",
        description="Baut die versionierte W×T-Prior-Tabelle aus dem Sweep-Gitter (#230).",
    )
    ap.add_argument("--grid-meta", default=None, help="Pfad zu meta_wt.json (Default: data_grid/)")
    ap.add_argument("--robot", default="doosan_m1013", help="Roboterdefinition aus robots/")
    ap.add_argument("--tool", default="30gut", help="Endeffektor aus tools/ (Referenz-Tool)")
    ap.add_argument(
        "--out", default=None,
        help="Ausgabepfad (Default: priors/placement_prior.<robot>.<tool>.json)",
    )
    args = ap.parse_args(argv)

    from fgc.domain.tool import ToolDef

    grid_meta_path = Path(args.grid_meta) if args.grid_meta else _default_grid_meta()
    if not grid_meta_path.exists():
        print(f"prior_build: Gitter-Meta {grid_meta_path} nicht gefunden.", file=sys.stderr)
        return 2
    grid_meta = json.loads(grid_meta_path.read_text(encoding="utf-8"))

    try:
        tool = ToolDef.load(args.tool)
    except FileNotFoundError as exc:
        print(f"prior_build: {exc}", file=sys.stderr)
        return 2

    # Repo-relativen Pfad stempeln (byte-stabil ueber Maschinen/Worktrees).
    from fgc.paths import REPO_ROOT

    try:
        rel = grid_meta_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = grid_meta_path.name
    source = (
        f"python -m fgc.placement.prior_build --grid-meta {rel} "
        f"--robot {args.robot} --tool {args.tool}"
    )
    provenance = _grid_provenance(source, grid_meta, rel)
    artifact = build_prior_artifact(
        grid_meta, args.robot, tool_reference(tool), provenance=provenance
    )

    out = Path(args.out) if args.out else _default_out(args.robot, args.tool)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump_artifact(artifact), encoding="utf-8")
    n_measured = sum(1 for c in artifact["cells"].values() if c["status"] == STATUS_MEASURED)
    n_assumed = len(artifact["cells"]) - n_measured
    print(
        f"prior_build: {len(artifact['cells'])} Zellen "
        f"({n_measured} measured, {n_assumed} angenommen-unmachbar) → {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
