"""W×T-Gitter-Auswertung: H_max(W,T)-Heatmap + Gewinner-Hebel je Zelle.

Liest data_grid/meta_wt.json (hmax_by_wt) und erzeugt:
  figG1_hmax.png    — Heatmap H_max(Breite, Dicke), Zelle annotiert mit H_max +
                      Gewinner-Konfig + Basishöhe (zeigt, dass die optimalen Hebel
                      pro Geometrie variieren).
  figG2_baender.png — abgeleitete Modulzahl für eine 3060-mm-Wand: ⌈3060/H_max⌉.

Aufruf:  python experiments/collision_standoff_sweep/grid_plots.py [data-dir]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "data_grid"
FIG = DATA / "figures"
REF_WALL_H = 3060.0


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    meta = json.loads((DATA / "meta_wt.json").read_text(encoding="utf-8"))
    widths = sorted(meta["widths"])
    thicks = sorted(meta["thicks"])
    hmax = meta["hmax_by_wt"]  # "W_T" -> [h, base, cfg, standoff]

    H = np.full((len(thicks), len(widths)), np.nan)
    ann = {}
    for ti, t in enumerate(thicks):
        for wi, w in enumerate(widths):
            key = f"{int(w)}_{int(t)}"
            if key in hmax:
                h, base, cfg, standoff = hmax[key]
                H[ti, wi] = h
                ann[(ti, wi)] = (h, base, cfg, standoff)

    # ---- figG1: H_max(W,T) ----
    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(H, origin="lower", aspect="auto", cmap="viridis",
                   extent=[min(widths) - 150, max(widths) + 150,
                           min(thicks) - 75, max(thicks) + 75])
    cb = fig.colorbar(im, ax=ax)
    cb.set_label("H_max — max. machbare Bandhöhe (mm)")
    for (ti, wi), (h, base, cfg, standoff) in ann.items():
        ax.text(widths[wi], thicks[ti], f"{h:.0f}\n{cfg}·b{int(base)}",
                ha="center", va="center", fontsize=9,
                color="white" if h < np.nanmax(H) * 0.6 else "black")
    ax.set_xticks(widths)
    ax.set_yticks(thicks)
    ax.set_xlabel("Modul-Breite W (mm)")
    ax.set_ylabel("Wand-Dicke T (mm)")
    ax.set_title("Prädikat-Gitter: H_max(W,T) — optimiert über Abstand×Basishöhe×IK\n"
                 "Zelle: H_max · Gewinner-Konfig · Basishöhe (Hebel variieren mit der Geometrie)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "figG1_hmax.png", dpi=150)
    plt.close(fig)

    # ---- figG2: Bänder für 3060-mm-Wand ----
    bands = np.where(H > 0, np.ceil(REF_WALL_H / np.where(H > 0, H, np.nan)), np.nan)
    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(bands, origin="lower", aspect="auto", cmap="magma_r",
                   extent=[min(widths) - 150, max(widths) + 150,
                           min(thicks) - 75, max(thicks) + 75])
    cb = fig.colorbar(im, ax=ax)
    cb.set_label(f"Höhenbänder für eine {REF_WALL_H:.0f}-mm-Wand = ⌈{REF_WALL_H:.0f}/H_max⌉")
    for (ti, wi), (h, _b, _c, _s) in ann.items():
        nb = math.ceil(REF_WALL_H / h) if h > 0 else None
        ax.text(widths[wi], thicks[ti], "∞" if nb is None else str(nb),
                ha="center", va="center", fontsize=11, color="white")
    ax.set_xticks(widths)
    ax.set_yticks(thicks)
    ax.set_xlabel("Modul-Breite W (mm)")
    ax.set_ylabel("Wand-Dicke T (mm)")
    ax.set_title(f"Abgeleitet: Höhenbänder für eine {REF_WALL_H:.0f}-mm-Wand", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "figG2_baender.png", dpi=150)
    plt.close(fig)

    # Konsolentabelle
    print(f"{'T\\W':>6}", *[f"{w:>10.0f}" for w in widths])
    for ti, t in enumerate(thicks):
        cells = []
        for wi in range(len(widths)):
            a = ann.get((ti, wi))
            cells.append(f"{a[0]:.0f}({a[2]})" if a else "-")
        print(f"{t:>6.0f}", *[f"{c:>10}" for c in cells])
    print(f"[plots] geschrieben nach {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
