"""CLI der Mustervorschau: `roboprint pattern-preview <preset.json> --svg <datei> [--json <datei>]
[--length L --thickness D] [--layer N] [--width-px W]`.

Auch direkt aufrufbar: `python -m roboprint.patterns.cli_preview <preset.json> <ausgabe.svg> …`.
Schreibt die SVG-Draufsicht (und optional das Vorschau-JSON wie `POST /api/patterns/preview`)
und gibt eine Zeile mit den wichtigsten Kennzahlen aus. `--length`/`--thickness` ersetzen den
Querschnitt des Presets durch ein Rechteck. Exit-Code 0, wenn die Schicht ohne Regelfehler
(M1–M7, Schweregrad `error`) ist, 1 bei Regelfehlern, 2 bei ungültiger Eingabe.
"""

from __future__ import annotations

import argparse
import math
import json
import sys
from pathlib import Path
from typing import Any

from roboprint.patterns.checks import check_outline, check_spec, flag_empty
from roboprint.patterns.preview import load_preset, preview, preview_svg


def _fit_summary(data: dict[str, Any]) -> str:
    """Tatsächliche Feldlängen aus `fit_to_length` (meta.fit der Pfade), falls das Muster sie meldet."""
    parts = []
    for lp in data["paths"]:
        fit = (lp.get("meta") or {}).get("fit")
        if isinstance(fit, dict) and {"count", "length_mm"} <= set(fit):
            parts.append(f"{fit['count']} Felder à {float(fit['length_mm']):.1f} mm")
    return (", " + "; ".join(parts)) if parts else ""


def main(
    preset_path: str | Path,
    svg_path: str | Path | None,
    layer: int = 0,
    json_path: str | Path | None = None,
    *,
    length_mm: float | None = None,
    thickness_mm: float | None = None,
    width_px: int = 1000,
) -> int:
    """Preset laden, Vorschau rechnen, SVG (und optional JSON) schreiben. Rückgabe: Exit-Code."""
    preset = load_preset(preset_path)
    check_spec(preset)
    outline = None
    if length_mm is not None or thickness_mm is not None:
        if length_mm is None or thickness_mm is None:
            raise ValueError("--length und --thickness nur zusammen angeben")
        outline = {"length_mm": float(length_mm), "thickness_mm": float(thickness_mm)}
    check_outline(outline if outline is not None else preset.get("outline"))
    data = flag_empty(preview(preset, outline, layer=layer))
    if svg_path is not None:
        Path(svg_path).parent.mkdir(parents=True, exist_ok=True)
        Path(svg_path).write_text(preview_svg(data=data, width_px=width_px), encoding="utf-8")
    if json_path is not None:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    m = data["metrics"]
    errors = [v for v in data["violations"] if v["severity"] == "error"]
    target = f" -> {svg_path}" if svg_path is not None else ""
    print(
        f"{preset['name']}: Pfad {m['path_length_mm']} mm, {m['print_time_s']} s, Kontakte {m['contacts']}"
        f"{_fit_summary(data)}, Verstöße {len(errors)} Fehler / {len(data['violations']) - len(errors)} "
        f"Warnungen{target}"
    )
    for v in errors:
        print(f"  {v['rule']} Schicht {v['layer']}: {v['message']}", file=sys.stderr)
    return 0 if not errors else 1


def add_arguments(ap: argparse.ArgumentParser, *, svg_positional: bool) -> None:
    """Argumente für `roboprint pattern-preview` und den Modulaufruf."""
    ap.add_argument("preset", type=Path, help="Preset-JSON (name, pattern, params, outline)")
    if svg_positional:
        ap.add_argument("svg", type=Path, help="SVG-Ausgabe")
    else:
        ap.add_argument("--svg", type=Path, default=None, help="SVG-Ausgabe")
    ap.add_argument("--json", type=Path, default=None, help="Vorschau als JSON (Format wie die API)")
    ap.add_argument("--length", type=float, default=None, help="Modullänge in mm (mit --thickness)")
    ap.add_argument("--thickness", type=float, default=None, help="Wanddicke in mm (mit --length)")
    ap.add_argument("--layer", type=int, default=0, help="Schicht (Folgeschicht wird blass gezeigt)")
    ap.add_argument("--width-px", type=int, default=1000, help="Breite der SVG in Pixeln")


def run(args: argparse.Namespace) -> int:
    """Argumente ausführen; ungültige Eingaben ergeben Exit-Code 2 mit Meldung."""
    if any(v is not None and not (math.isfinite(v) and v > 0) for v in (args.length, args.thickness)):
        print("Fehler: --length und --thickness müssen endliche Zahlen > 0 sein", file=sys.stderr)
        return 2
    if args.layer < 0 or args.width_px < 200 or args.width_px > 4000:
        print("Fehler: --layer muss ≥ 0 und --width-px in [200, 4000] liegen (wie die API)", file=sys.stderr)
        return 2
    try:
        return main(
            args.preset,
            args.svg,
            args.layer,
            args.json,
            length_mm=args.length,
            thickness_mm=args.thickness,
            width_px=args.width_px,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="2D-Vorschau eines Muster-Presets als SVG")
    add_arguments(ap, svg_positional=True)
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(_cli())
