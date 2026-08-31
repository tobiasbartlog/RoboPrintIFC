"""Dicken-Studie: Abbildungen aus grid_thickness.csv / meta_thickness.json.

Erzeugt nach data_thickness/figures/:
  figT1_band_vs_thickness.png — max. machbare Bandhöhe (kollisionsfrei & erreichbar)
                                über alle Abstände, je Wand, gegen die Wandstärke.
                                Punkte mit Modul-Länge annotiert (Confound sichtbar).
  figT2_feasible_maps.png     — Feasible-Maps (Abstand × Höhe) je Wand als
                                Kleinmultiple, nach Dicke sortiert.

Aufruf:  python experiments/collision_standoff_sweep/thickness_plots.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "data_thickness"
FIG = DATA / "figures"
REACH_TH = 0.5


def _f(x):
    return None if x in (None, "", "None") else float(x)


def _i(x):
    return None if x in (None, "", "None") else int(float(x))


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    meta = json.loads((DATA / "meta_thickness.json").read_text(encoding="utf-8"))
    with (DATA / "grid_thickness.csv").open(encoding="utf-8") as f:
        grid = list(csv.DictReader(f))

    info_by_gid = {w["gid"]: w for w in meta["walls"]}
    gids = [w["gid"] for w in sorted(meta["walls"], key=lambda w: w["thickness_mm"])]

    # je Wand: Matrix (standoff × layer) für min_dist und reach_frac
    per_wall = {}
    for gid in gids:
        rows = [r for r in grid if r["gid"] == gid]
        standoffs = sorted({_f(r["standoff_mm"]) for r in rows})
        layers = sorted({_i(r["layer"]) for r in rows})
        si = {d: i for i, d in enumerate(standoffs)}
        li = {ly: j for j, ly in enumerate(layers)}
        dist = np.full((len(layers), len(standoffs)), np.nan)
        reachf = np.full((len(layers), len(standoffs)), np.nan)
        for r in rows:
            i = li[_i(r["layer"])]
            j = si[_f(r["standoff_mm"])]
            md = _f(r["min_dist_mm"])
            dist[i, j] = np.nan if md is None else md
            rf = _f(r["reach_frac"])
            reachf[i, j] = np.nan if rf is None else rf
        lh = info_by_gid[gid]["layer_height_mm"]
        heights = [ly * lh for ly in layers]
        per_wall[gid] = dict(standoffs=standoffs, heights=heights, dist=dist, reachf=reachf, lh=lh)

    # max. machbare Bandhöhe von unten je Wand
    def feasible_band(w):
        dist, reachf = w["dist"], w["reachf"]
        heights, standoffs = w["heights"], w["standoffs"]
        full = max(heights) + w["lh"]
        best = 0.0
        best_d = None
        for jx in range(len(standoffs)):
            h = full
            for iy in range(len(heights)):
                dv, rv = dist[iy, jx], reachf[iy, jx]
                green = np.isnan(dv) or dv >= 50.0
                reach = (not np.isnan(rv)) and rv >= REACH_TH
                if not (green and reach):
                    h = heights[iy]
                    break
            if h > best:
                best, best_d = h, standoffs[jx]
        return best, best_d

    # ---- figT1: Bandhöhe vs Dicke ------------------------------------------
    ths, bands, mlens, best_ds = [], [], [], []
    for gid in gids:
        b, bd = feasible_band(per_wall[gid])
        ths.append(info_by_gid[gid]["thickness_mm"])
        bands.append(b)
        mlens.append(info_by_gid[gid]["module_length_mm"])
        best_ds.append(bd)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    sc = ax.scatter(ths, bands, c=mlens, cmap="viridis", s=90, zorder=3, edgecolor="k")
    ax.plot(ths, bands, "-", color="gray", lw=1, zorder=2)
    cb = fig.colorbar(sc, ax=ax)
    cb.set_label("Modul-Länge (mm) — Confound")
    for th, b, bd in zip(ths, bands, best_ds):
        ax.annotate(f"{b:.0f} mm\n@{bd:.0f}" if bd else f"{b:.0f} mm",
                    (th, b), textcoords="offset points", xytext=(6, 6), fontsize=8)
    ax.set_xlabel("Wandstärke (mm)")
    ax.set_ylabel("max. machbare Bandhöhe von unten (mm)")
    ax.set_title("Machbare Bandhöhe über Wandstärke (reale öffnungsfreie Wände, Höhe ≈ 3060 mm)",
                 fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "figT1_band_vs_thickness.png", dpi=150)
    plt.close(fig)

    # ---- figT2: Feasible-Maps je Wand --------------------------------------
    n = len(gids)
    cols = min(4, n)
    rows_n = math.ceil(n / cols)
    cmap = ListedColormap(["#2ca02c", "#d62728", "#9e9e9e"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3)
    fig, axes = plt.subplots(rows_n, cols, figsize=(4 * cols, 3.4 * rows_n), squeeze=False)
    for k, gid in enumerate(gids):
        ax = axes[k // cols][k % cols]
        w = per_wall[gid]
        dist, reachf = w["dist"], w["reachf"]
        heights, standoffs = w["heights"], w["standoffs"]
        feas = np.full(dist.shape, np.nan)
        reachable = reachf >= REACH_TH
        green = (dist >= 50.0) | np.isnan(dist)
        feas[reachable & green] = 0
        feas[reachable & ~green] = 1
        feas[~reachable] = 2
        ext = [min(standoffs) - 50, max(standoffs) + 50, min(heights) - w["lh"] / 2,
               max(heights) + w["lh"] / 2]
        ax.imshow(feas, origin="lower", aspect="auto", extent=ext, cmap=cmap, norm=norm,
                  interpolation="nearest")
        wi = info_by_gid[gid]
        ax.set_title(f"{wi['thickness_mm']:.0f} mm dick\nModul {wi['module_length_mm']:.0f}×"
                     f"{wi['module_height_mm']:.0f}", fontsize=9)
        ax.set_xlabel("standoff (mm)", fontsize=8)
        ax.set_ylabel("Höhe (mm)", fontsize=8)
        ax.tick_params(labelsize=7)
    for k in range(n, rows_n * cols):
        axes[k // cols][k % cols].axis("off")
    fig.suptitle("Machbare Region (grün) über Wandstärke — kollisionsfrei & erreichbar\n"
                 "rot = Kollision/Sicherheitszone · grau = unerreichbar", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(FIG / "figT2_feasible_maps.png", dpi=150)
    plt.close(fig)

    # ---- Konsolen-Tabelle ---------------------------------------------------
    print(f"{'thick':>7} {'modLen':>7} {'modH':>6} {'band':>6} {'@d':>6} {'bänder':>7}")
    for gid, th, b, ml, bd in zip(gids, ths, bands, mlens, best_ds):
        wh = info_by_gid[gid]["wall_height_mm"]
        nb = math.ceil(wh / b) if b > 0 else None
        print(f"{th:>7.0f} {ml:>7.0f} {info_by_gid[gid]['module_height_mm']:>6.0f} "
              f"{b:>6.0f} {(bd or 0):>6.0f} {str(nb):>7}")
    print(f"[plots] geschrieben nach {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
