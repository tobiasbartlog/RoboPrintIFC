"""Presets, Bilder und Kennzahltabelle der Musterfamilie Fugenwand erzeugen.

Aufruf: `python scripts/muster_fugenwand.py [--table]`

- Presets je Variante nach `docs/muster/presets/fugenwand_*.json` und das Standard-Preset
  `core/src/roboprint/patterns/presets/fugenwand.json`.
- SVG-Draufsichten (Schicht 0 und blass Schicht 1, Pfeile, Start/Ende, Kontakte, Verstöße) nach
  `docs/muster/bilder/fugenwand_<variante>_<L>x<d>.svg` für 600 × 200 und 1000 × 300.
- `--table`: Machbarkeit über Dicke 200/300/365 und Länge 300…1200 mm sowie Kennzahlen je Variante
  als Markdown (für `docs/muster/fugenwand.md`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "src"))

from roboprint.patterns import preview, preview_svg, save_preset
from roboprint.patterns.preview import params_for

PRESETS = ROOT / "docs" / "muster" / "presets"
IMAGES = ROOT / "docs" / "muster" / "bilder"
CORE_PRESET = (
    ROOT / "core" / "src" / "roboprint" / "patterns" / "presets" / "fugenwand.json"
)

BASE = {"bead_width_mm": 30.0, "layer_height_mm": 10.0, "layer_order": "alternate"}

#: Varianten: (Dateiname, Anzeigename, Musterparameter, Beschreibung)
VARIANTS = [
    (
        "raute",
        "Fugenwand Rautenkette (b, ohne Gurt)",
        {"belt": False, "back_offset": "versetzt", "field_length_mm": 300.0},
        (
            "Empfehlung: An jeder Fuge eine Raute, Rauten berühren sich an Knoten in der Wandmitte, "
            "Rautenspitze stützt das Feld der Gegenseite; Fugen der Rückseite um F/2 versetzt."
        ),
    ),
    (
        "gurt",
        "Fugenwand mit Gurt, gespiegelt (a)",
        {"belt": True, "back_offset": "gespiegelt", "field_length_mm": 300.0},
        (
            "Vorschlag des Nutzers: je Fuge Schleife Haken – Steg – Knoten – Gurt – Knoten – Steg – Haken; "
            "Doppelgurt in Wandmitte, Fugen beider Seiten gegenüber (durchgehende Sollbruchebene)."
        ),
    ),
    (
        "versetzt",
        "Fugenwand mit Gurt, versetzt (c)",
        {"belt": True, "back_offset": "versetzt", "field_length_mm": 300.0},
        "Wie (a), Fugen der Rückseite um eine halbe Teilung versetzt; Endfeldknoten an der Endkappe.",
    ),
    (
        "foto",
        "Fugenwand mit Gurt wie Foto (a, Haken r = 20 mm)",
        {
            "belt": True,
            "back_offset": "gespiegelt",
            "field_length_mm": 250.0,
            "hook_radius_mm": 20.0,
        },
        (
            "Variante (a) mit engeren Haken (r = 20 mm < w: M6-Warnung, kein Fehler), damit die Stege "
            "auch bei 300 mm Wand schräg (V-förmig) laufen wie auf dem Foto."
        ),
    ),
]
OUTLINES = [(600.0, 200.0), (1000.0, 300.0)]


def write_presets() -> list[Path]:
    PRESETS.mkdir(parents=True, exist_ok=True)
    out = []
    for key, name, vals, desc in VARIANTS:
        out.append(
            save_preset(
                PRESETS / f"fugenwand_{key}.json",
                name,
                "fugenwand",
                {**BASE, **vals},
                {"length_mm": 600.0, "thickness_mm": 200.0},
                desc,
            )
        )
    key, name, vals, desc = VARIANTS[0]
    out.append(
        save_preset(
            CORE_PRESET,
            "Fugenwand (Rautenkette)",
            "fugenwand",
            {**BASE, **vals},
            {"length_mm": 600.0, "thickness_mm": 200.0},
            desc,
        )
    )
    return out


def write_images() -> list[Path]:
    IMAGES.mkdir(parents=True, exist_ok=True)
    out = []
    for key, _name, vals, _desc in VARIANTS:
        for L, d in OUTLINES:
            p = IMAGES / f"fugenwand_{key}_{L:.0f}x{d:.0f}.svg"
            p.write_text(
                preview_svg(params_for("fugenwand", **BASE, **vals), (L, d)),
                encoding="utf-8",
            )
            out.append(p)
    return out


def _cell(data: dict) -> str:
    meta = data["paths"][0]["meta"]
    if meta.get("pattern_fallback"):
        return "–"
    errs = {v["rule"] for v in data["violations"] if v["severity"] == "error"}
    warns = {v["rule"] for v in data["violations"] if v["severity"] == "warn"}
    s = f"{meta['fit']['count']}×{meta['field_length_mm']:.0f}"
    if meta["hook_radius_mm"] < 30 - 1e-6:
        s += f" r{meta['hook_radius_mm']:g}"
    if errs:
        s += " FEHLER " + ",".join(sorted(errs))
    elif warns - {"M6"}:
        s += " W " + ",".join(sorted(warns))
    return s


def table() -> str:
    lines = [
        "| Variante | Dicke | "
        + " | ".join(f"{L} mm" for L in (300, 400, 500, 600, 750, 900, 1000, 1200))
        + " |"
    ]
    lines.append("|---|---|" + "---|" * 8)
    for key, _name, vals, _desc in VARIANTS:
        for d in (200.0, 300.0, 365.0):
            row = [
                _cell(preview(params_for("fugenwand", **BASE, **vals), (L, d)))
                for L in (300, 400, 500, 600, 750, 900, 1000, 1200)
            ]
            lines.append(f"| {key} | {d:.0f} | " + " | ".join(row) + " |")
    lines.append("")
    lines.append(
        "| Variante | Querschnitt | Felder × F | r | Pfad mm | Zeit s | Material l/(m·Schicht) | "
        "Kontakte Fuge/Knoten/Schale | längste Außenstrecke mm | größte Zelle mm² (Spannweite) | Stegwinkel ° | Warn. |"
    )
    lines.append("|---" * 12 + "|")
    for key, _name, vals, _desc in VARIANTS:
        for L, d in ((600.0, 200.0), (1000.0, 300.0), (1200.0, 365.0)):
            data = preview(params_for("fugenwand", **BASE, **vals), (L, d))
            meta = data["paths"][0]["meta"]
            m = data["metrics"]
            pm = m["paths"][0]
            ck = pm["contacts_by_kind"]
            nw = sum(
                v["severity"] == "warn" for v in data["violations"] if v["layer"] == 0
            )
            cont = "/".join(
                str(ck.get(k, {}).get("count", 0)) for k in ("joint", "node", "shell")
            )
            lines.append(
                f"| {key} | {L:.0f}×{d:.0f} | {meta['fit']['count']}×{meta['field_length_mm']:.0f} | "
                f"{meta['hook_radius_mm']:g} | {m['path_length_mm']:.0f} | {m['print_time_s']:.0f} | "
                f"{m['material_l_per_m_layer']:.3f} | {cont} | {m['longest_straight_outer_mm']:.0f} | "
                f"{pm['max_cell_area_mm2']:.0f} ({pm['max_cell_span_mm']:.0f}) | "
                f"{', '.join(f'{a:g}' for a in meta['web_angle_deg'])} | {nw} |"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--table",
        action="store_true",
        help="Machbarkeit und Kennzahlen als Markdown ausgeben",
    )
    a = ap.parse_args(argv)
    for p in write_presets() + write_images():
        print(p.relative_to(ROOT))
    if a.table:
        print(table())
    return 0


if __name__ == "__main__":
    sys.exit(main())
