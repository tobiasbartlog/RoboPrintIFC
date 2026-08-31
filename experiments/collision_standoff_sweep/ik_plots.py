"""IK-Pilot-Auswertung: A/B Standard-Konfig vs. best-over-8 (grid_ik.csv).

Erzeugt data_ik/figures/:
  figIK1_ab_feasible.png — zwei Feasible-Maps (Abstand×Höhe) nebeneinander:
                           auto (Standard-Konfig, = fig4) vs. best-over-8.
                           Zeigt, wie viel die freie IK-Konfigwahl rettet.
  figIK2_winner.png      — welche Konfig macht jede Zelle machbar (best-over-8).

Zusätzlich Konsolen-Vergleich H_max (strenge Latte: reach≈100% & grün) auto vs.
best-over-8.

Aufruf:  python experiments/collision_standoff_sweep/ik_plots.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "data_ik"
FIG = DATA / "figures"
MAP_REACH_TH = 0.5     # Diagnosekarte (wie fig4)
STRICT_REACH_TH = 0.99  # strenge Latte: praktisch jeder Druckpunkt erreichbar
EXPLICIT = [f"{s}{e}{w}" for s in "ab" for e in "ab" for w in "ab"]  # 8


def _f(x):
    return None if x in (None, "", "None") else float(x)


def _i(x):
    return None if x in (None, "", "None") else int(float(x))


def _matrices(rows, standoffs, layers):
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
    return dist, reachf


def _feasible(dist, reachf, reach_th):
    green = (dist >= 50.0) | np.isnan(dist)
    reach = reachf >= reach_th
    return green & reach


def _hmax(dist, reachf, heights, lh, reach_th):
    """Max. zusammenhängend machbare Höhe von unten über alle Abstände."""
    full = max(heights) + lh
    best = 0.0
    for jx in range(dist.shape[1]):
        feas = _feasible(dist[:, jx:jx + 1], reachf[:, jx:jx + 1], reach_th)[:, 0]
        h = full
        for iy in range(len(heights)):
            if not feas[iy]:
                h = heights[iy]
                break
        best = max(best, h)
    return best


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    meta = json.loads((DATA / "meta_ik.json").read_text(encoding="utf-8"))
    with (DATA / "grid_ik.csv").open(encoding="utf-8") as f:
        grid = list(csv.DictReader(f))
    lh = meta["layer_height_mm"]

    standoffs = sorted({_f(r["standoff_mm"]) for r in grid})
    layers = sorted({_i(r["layer"]) for r in grid})
    heights = [ly * lh for ly in layers]
    ext = [min(standoffs) - 50, max(standoffs) + 50, min(heights) - lh / 2, max(heights) + lh / 2]

    by_cfg = {}
    for cfg in ["auto"] + EXPLICIT:
        rows = [r for r in grid if r["config"] == cfg]
        if rows:
            by_cfg[cfg] = _matrices(rows, standoffs, layers)

    dist_auto, reach_auto = by_cfg["auto"]

    # best-over-8: je Zelle machbar, wenn IRGENDEINE der 8 Konfigs machbar ist;
    # winner = Index der (ersten) rettenden Konfig.
    shape = dist_auto.shape
    feas_best = np.zeros(shape, dtype=bool)
    winner = np.full(shape, -1, dtype=int)
    present = [c for c in EXPLICIT if c in by_cfg]
    for k, cfg in enumerate(present):
        d, rf = by_cfg[cfg]
        fe = _feasible(d, rf, MAP_REACH_TH)
        newly = fe & (~feas_best)
        winner[newly] = k
        feas_best |= fe

    def _feas_class(dist, reachf, reach_th):
        cls = np.full(dist.shape, 2)  # 2 = unerreichbar
        reach = reachf >= reach_th
        green = (dist >= 50.0) | np.isnan(dist)
        cls[reach & ~green] = 1  # Kollision/Sicherheitszone
        cls[reach & green] = 0   # machbar
        return cls

    # ---- figIK1: A/B ----
    cmap = ListedColormap(["#2ca02c", "#d62728", "#9e9e9e"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
    cls_auto = _feas_class(dist_auto, reach_auto, MAP_REACH_TH)
    # best-over-8 als Klassen: machbar wo feas_best; sonst auto-Klasse (Kollision/unerr.)
    cls_best = np.where(feas_best, 0, cls_auto)
    for ax, cls, title in ((axes[0], cls_auto, "Standard-Konfig (auto) — wie fig4"),
                           (axes[1], cls_best, "best-over-8 IK-Konfigs")):
        ax.imshow(cls, origin="lower", aspect="auto", extent=ext, cmap=cmap, norm=norm,
                  interpolation="nearest")
        ax.set_xlabel("standoff (mm)")
        ax.set_title(title, fontsize=10)
    axes[0].set_ylabel("Druckhöhe (mm)")
    hmax_auto = _hmax(dist_auto, reach_auto, heights, lh, STRICT_REACH_TH)
    # best-over-8 strenge H_max: je Zelle strenge Machbarkeit über Konfigs
    strict_best = np.zeros(shape, dtype=bool)
    for cfg in present:
        d, rf = by_cfg[cfg]
        strict_best |= _feasible(d, rf, STRICT_REACH_TH)
    full = max(heights) + lh
    hmax_best = 0.0
    for jx in range(shape[1]):
        h = full
        for iy in range(len(heights)):
            if not strict_best[iy, jx]:
                h = heights[iy]
                break
        hmax_best = max(hmax_best, h)
    fig.suptitle(f"IK-Pilot: Modul {meta['section_id']} {meta['module_length_mm']:.0f}×"
                 f"{meta['module_height_mm']:.0f} mm @ {meta['wall_thickness_mm']:.0f} mm · "
                 f"grün=machbar rot=Kollision grau=unerreichbar\n"
                 f"H_max (streng): auto {hmax_auto:.0f} mm → best-over-8 {hmax_best:.0f} mm",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(FIG / "figIK1_ab_feasible.png", dpi=150)
    plt.close(fig)

    # ---- figIK2: winner-Konfig ----
    fig, ax = plt.subplots(figsize=(9, 6))
    wshow = np.where(feas_best, winner, np.nan)
    cmap2 = plt.get_cmap("tab10")
    im = ax.imshow(wshow, origin="lower", aspect="auto", extent=ext, cmap=cmap2,
                   vmin=0, vmax=9, interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, ticks=range(len(present)))
    cb.ax.set_yticklabels(present)
    cb.set_label("rettende IK-Konfig (shoulder·elbow·wrist)")
    ax.set_xlabel("standoff (mm)")
    ax.set_ylabel("Druckhöhe (mm)")
    ax.set_title("Welche IK-Konfig macht die Zelle machbar (best-over-8)", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "figIK2_winner.png", dpi=150)
    plt.close(fig)

    print(f"H_max streng: auto={hmax_auto:.0f}mm  best-over-8={hmax_best:.0f}mm  "
          f"Gewinn={hmax_best - hmax_auto:.0f}mm")
    print(f"[plots] geschrieben nach {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
