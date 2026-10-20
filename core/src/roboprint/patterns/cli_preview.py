"""CLI-Hilfsfunktion für die Mustervorschau (noch nicht im roboprint-CLI registriert, das macht M3).

Aufruf: `python -m roboprint.patterns.cli_preview <preset.json> <ausgabe.svg> [--layer N] [--json <datei>]`
Schreibt die SVG-Draufsicht und gibt eine Zeile mit den wichtigsten Kennzahlen aus. Exit-Code 0,
wenn die Schicht ohne Regelfehler (M1–M7, Schweregrad `error`) ist, sonst 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from roboprint.patterns.preview import load_preset, preview, preview_svg


def main(
    preset_path: str | Path, svg_path: str | Path, layer: int = 0, json_path: str | Path | None = None
) -> int:
    """Preset laden, Vorschau rechnen, SVG (und optional JSON) schreiben. Rückgabe: Exit-Code."""
    preset = load_preset(preset_path)
    data = preview(preset, layer=layer)
    Path(svg_path).write_text(preview_svg(data=data), encoding="utf-8")
    if json_path is not None:
        Path(json_path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    m = data["metrics"]
    errors = [v for v in data["violations"] if v["severity"] == "error"]
    print(
        f"{preset['name']}: Pfad {m['path_length_mm']} mm, {m['print_time_s']} s, Kontakte {m['contacts']}, "
        f"Verstöße {len(errors)} Fehler / {len(data['violations']) - len(errors)} Warnungen -> {svg_path}"
    )
    return 0 if not errors else 1


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="2D-Vorschau eines Muster-Presets als SVG")
    ap.add_argument("preset")
    ap.add_argument("svg")
    ap.add_argument("--layer", type=int, default=0)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    return main(a.preset, a.svg, a.layer, a.json)


if __name__ == "__main__":
    sys.exit(_cli())
