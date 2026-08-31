"""Spike S4 — Offset-Sweep ueber Testkonturen x Schalen x join_style/mitre_limit.

Wegwerfskript, siehe docs/spikes/s4_scripts/PLAN.md. Nicht-interaktiv:
schreibt `out/results.csv` und je Konturfamilie eine PNG-Uebersicht nach
`out/`. Kein plt.show().

Offset-Schema wie core/src/fgc/slicer/shells.py: Insets bei 0.5w + k*w,
k = 0 .. N_SHELLS-1, hier normiert mit w = 1.0 (Strangbreite unbekannt,
s. PLAN.md "Einheiten").
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # nicht-interaktiv, nur Dateien speichern
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.geometry import MultiPolygon, Polygon

from contours import W, get_all_contours

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"
OUT_DIR.mkdir(exist_ok=True)

N_SHELLS = 4  # k = 0..3, wie im Plan gefordert
JOIN_STYLES: list[tuple[str, float]] = [
    ("mitre", 1.0),
    ("mitre", 2.0),
    ("mitre", 5.0),  # Produktionscode-Default (shells.py)
    ("round", 5.0),  # mitre_limit fuer round/bevel wirkungslos, Platzhalterwert
    ("bevel", 5.0),
]

SLIVER_THRESHOLD = 0.2  # Flaeche / (Umfang * w), s. PLAN.md Schritt 2


def _as_polygons(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if not g.is_empty]
    return []  # Linien/Punkte/GeometryCollection: kein Flaechenrest


def offset_once(polygon: Polygon, inset: float, join_style: str, mitre_limit: float):
    return polygon.buffer(-inset, join_style=join_style, mitre_limit=mitre_limit, quad_segs=16)


def classify_and_measure(original: Polygon, inset: float, join_style: str, mitre_limit: float) -> dict:
    result = offset_once(original, inset, join_style, mitre_limit)
    parts = _as_polygons(result)

    is_empty = len(parts) == 0
    num_parts = len(parts)
    area = sum(p.area for p in parts)
    perimeter = sum(p.length for p in parts)
    is_valid = all(p.is_valid for p in parts) if parts else True

    if area > 0 and perimeter > 0:
        sliver_indicator = area / (perimeter * W)
    else:
        sliver_indicator = 0.0
    is_sliver = (not is_empty) and sliver_indicator < SLIVER_THRESHOLD

    # Roundtrip-Check: buffer(-d).buffer(+d) vs. Original
    if is_empty:
        roundtrip_area_loss_pct = 100.0
        roundtrip_hausdorff = float("nan")
    else:
        rt = offset_once(result if num_parts <= 1 else MultiPolygon(parts), -inset, join_style, mitre_limit)
        rt_parts = _as_polygons(rt)
        rt_area = sum(p.area for p in rt_parts)
        roundtrip_area_loss_pct = 100.0 * (original.area - rt_area) / original.area if original.area > 0 else float("nan")
        try:
            rt_geom = rt if rt_parts else Polygon()
            roundtrip_hausdorff = original.hausdorff_distance(rt_geom) if rt_parts else float("nan")
        except Exception:
            roundtrip_hausdorff = float("nan")

    # Degenerationsklasse (zusammenfassend, Prioritaet: empty > invalid > multi > sliver > ok)
    if is_empty:
        degeneration_class = "empty"
    elif not is_valid:
        degeneration_class = "invalid"
    elif num_parts > 1:
        degeneration_class = f"multipolygon({num_parts})"
    elif is_sliver:
        degeneration_class = "sliver"
    else:
        degeneration_class = "ok"

    return {
        "is_empty": is_empty,
        "num_parts": num_parts,
        "is_valid": is_valid,
        "area": area,
        "perimeter": perimeter,
        "sliver_indicator": sliver_indicator,
        "is_sliver": is_sliver,
        "roundtrip_area_loss_pct": roundtrip_area_loss_pct,
        "roundtrip_hausdorff": roundtrip_hausdorff,
        "degeneration_class": degeneration_class,
        "_result_parts": parts,  # nur fuer Plot, nicht in CSV
    }


def run_sweep() -> list[dict]:
    rows = []
    for contour in get_all_contours():
        poly = contour["polygon"]
        for k in range(N_SHELLS):
            inset = (0.5 + k) * W
            for join_style, mitre_limit in JOIN_STYLES:
                metrics = classify_and_measure(poly, inset, join_style, mitre_limit)
                row = {
                    "family": contour["family"],
                    "name": contour["name"],
                    **{f"param_{k2}": v for k2, v in contour["params"].items()},
                    "shell_k": k,
                    "inset_w": inset,
                    "join_style": join_style,
                    "mitre_limit": mitre_limit if join_style == "mitre" else "",
                    "orig_area": poly.area,
                    "is_empty": metrics["is_empty"],
                    "num_parts": metrics["num_parts"],
                    "is_valid": metrics["is_valid"],
                    "result_area": round(metrics["area"], 6),
                    "result_perimeter": round(metrics["perimeter"], 6),
                    "sliver_indicator": round(metrics["sliver_indicator"], 6),
                    "is_sliver": metrics["is_sliver"],
                    "roundtrip_area_loss_pct": round(metrics["roundtrip_area_loss_pct"], 4)
                    if not math.isnan(metrics["roundtrip_area_loss_pct"])
                    else "",
                    "roundtrip_hausdorff": round(metrics["roundtrip_hausdorff"], 6)
                    if not math.isnan(metrics["roundtrip_hausdorff"])
                    else "",
                    "degeneration_class": metrics["degeneration_class"],
                }
                rows.append(row)
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    # Unterschiedliche Konturfamilien haben unterschiedliche param_*-Spalten
    # -> Vereinigung aller Keys, feste Reihenfolge (erste Zeile zuerst, Rest
    # alphabetisch angehaengt), fehlende Werte bleiben leer.
    fieldnames: list[str] = list(rows[0].keys())
    seen = set(fieldnames)
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Plots: je Konturfamilie eine PNG-Uebersicht, join_style=mitre/mitre_limit=5
# (Produktionscode-Default) als Referenzansicht; Degenerationen markiert.
# ---------------------------------------------------------------------------

SHELL_COLORS = ["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"]  # k=0..3


def plot_family(family: str, contours: list[dict], out_path: Path) -> None:
    n = len(contours)
    ncols = min(n, 3)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.5 * ncols, 5.0 * nrows), squeeze=False)

    for idx, contour in enumerate(contours):
        ax = axes[idx // ncols][idx % ncols]
        poly = contour["polygon"]
        xo, yo = poly.exterior.xy
        ax.plot(xo, yo, color="black", linewidth=1.5, label="Original")
        for interior in poly.interiors:
            xi, yi = interior.xy
            ax.plot(xi, yi, color="black", linewidth=1.0)

        degenerate_shells = []
        for k in range(N_SHELLS):
            inset = (0.5 + k) * W
            metrics = classify_and_measure(poly, inset, "mitre", 5.0)
            parts = metrics["_result_parts"]
            color = SHELL_COLORS[k % len(SHELL_COLORS)]
            degenerate = metrics["degeneration_class"] != "ok"
            if degenerate:
                degenerate_shells.append((k, metrics["degeneration_class"]))
            style = "--" if degenerate else "-"
            for part in parts:
                xr, yr = part.exterior.xy
                ax.plot(xr, yr, color=color, linewidth=1.3, linestyle=style)
                for hole in part.interiors:
                    xh, yh = hole.xy
                    ax.plot(xh, yh, color=color, linewidth=1.0, linestyle=style)

        title = contour["name"]
        if degenerate_shells:
            flags = ", ".join(f"k{k}:{cls}" for k, cls in degenerate_shells)
            title += f"\nDegeneration: {flags}"
        ax.set_title(title, fontsize=9)
        ax.set_aspect("equal", adjustable="datalim")
        ax.tick_params(labelsize=7)

    # ungenutzte Achsen ausblenden
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")

    legend_handles = [Patch(color="black", label="Original")] + [
        Patch(color=SHELL_COLORS[k], label=f"Schale k={k} (inset={(0.5 + k) * W:g}w)") for k in range(N_SHELLS)
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=5, fontsize=8, frameon=False)
    fig.suptitle(
        f"Spike S4 — Konturfamilie '{family}' (join_style=mitre, mitre_limit=5, Produktionsdefault)\n"
        "gestrichelt = Degeneration (empty/invalid/multipolygon/sliver)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    rows = run_sweep()
    csv_path = OUT_DIR / "results.csv"
    write_csv(rows, csv_path)
    print(f"results.csv geschrieben: {csv_path} ({len(rows)} Zeilen)")

    all_contours = get_all_contours()
    families = sorted({c["family"] for c in all_contours})
    for family in families:
        family_contours = [c for c in all_contours if c["family"] == family]
        out_path = OUT_DIR / f"{family}.png"
        plot_family(family, family_contours, out_path)
        print(f"Plot geschrieben: {out_path}")


if __name__ == "__main__":
    main()
