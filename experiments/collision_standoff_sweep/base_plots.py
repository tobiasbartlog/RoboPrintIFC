"""Basishöhen-Pilot: bringt ein Roboter-Podest machbare Bandhöhe? (data_base/)

Liest grid_ik.csv MIT `base_height_mm`-Spalte (mehrere Basishöhen). Je Basishöhe:
best-over-8 H_max (strenge Latte) und die dort rettende Konfig. Zeigt, wie viel
das Anheben der Roboterbasis an machbarer Bandhöhe bringt — und ob sich der
optimale Konfig-Gewinner mit der Basishöhe verschiebt.

Ausgabe: data_base/figures/figB1_base_vs_hmax.png + Konsolentabelle.
Aufruf:  python experiments/collision_standoff_sweep/base_plots.py [data-dir]
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

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "data_base"
FIG = DATA / "figures"
STRICT = 0.99
EXPLICIT = [f"{s}{e}{w}" for s in "ab" for e in "ab" for w in "ab"]


def _f(x):
    return None if x in (None, "", "None") else float(x)


def _i(x):
    return None if x in (None, "", "None") else int(float(x))


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    meta = json.loads((DATA / "meta_ik.json").read_text(encoding="utf-8"))
    with (DATA / "grid_ik.csv").open(encoding="utf-8") as f:
        grid = list(csv.DictReader(f))
    lh = meta["layer_height_mm"]
    bases = sorted({_f(r["base_height_mm"]) for r in grid})
    standoffs = sorted({_f(r["standoff_mm"]) for r in grid})
    layers = sorted({_i(r["layer"]) for r in grid})
    heights = [ly * lh for ly in layers]
    full = max(heights) + lh
    si = {d: i for i, d in enumerate(standoffs)}
    li = {ly: j for j, ly in enumerate(layers)}

    def mats(rows):
        d = np.full((len(layers), len(standoffs)), np.nan)
        rf = np.full((len(layers), len(standoffs)), np.nan)
        for r in rows:
            i, j = li[_i(r["layer"])], si[_f(r["standoff_mm"])]
            md = _f(r["min_dist_mm"])
            d[i, j] = np.nan if md is None else md
            v = _f(r["reach_frac"])
            rf[i, j] = np.nan if v is None else v
        return d, rf

    def feas(d, rf):
        return ((d >= 50.0) | np.isnan(d)) & (rf >= STRICT)

    def contig_hmax(fe):
        best, best_d = 0.0, None
        for jx in range(fe.shape[1]):
            h = full
            for iy in range(len(heights)):
                if not fe[iy, jx]:
                    h = heights[iy]
                    break
            if h > best:
                best, best_d = h, standoffs[jx]
        return best, best_d

    rows_out = []
    for bh in bases:
        # best-over-8 (per Zelle beste Konfig) + beste EINZEL-Konfig
        union = np.zeros((len(layers), len(standoffs)), dtype=bool)
        best_single, best_cfg = 0.0, None
        for cfg in EXPLICIT:
            sub = [r for r in grid if _f(r["base_height_mm"]) == bh and r["config"] == cfg]
            if not sub:
                continue
            d, rf = mats(sub)
            fe = feas(d, rf)
            union |= fe
            h, _ = contig_hmax(fe)
            if h > best_single:
                best_single, best_cfg = h, cfg
        h_union, d_union = contig_hmax(union)
        rows_out.append((bh, best_single, best_cfg, h_union, d_union))

    print(f"{'base':>6} {'H_max(1 Konfig)':>16} {'Konfig':>7} {'H_max(union)':>13} {'@d':>6}")
    for bh, hs, cfg, hu, du in rows_out:
        print(f"{bh:>6.0f} {hs:>16.0f} {str(cfg):>7} {hu:>13.0f} {(du or 0):>6.0f}")

    bh_x = [r[0] for r in rows_out]
    hs_y = [r[1] for r in rows_out]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(bh_x, hs_y, "o-", color="#1f77b4", lw=2, ms=7)
    for bh, hs, cfg, _hu, _du in rows_out:
        ax.annotate(f"{hs:.0f} mm\n({cfg})", (bh, hs), textcoords="offset points",
                    xytext=(6, 6), fontsize=9)
    ax.set_xlabel("Basishöhe / Roboter-Podest (mm)")
    ax.set_ylabel("max. machbare Bandhöhe H_max (beste Einzel-Konfig, streng)")
    ax.set_title(f"Bringt ein Roboter-Podest machbare Höhe?\nModul {meta['section_id']} "
                 f"{meta['module_length_mm']:.0f}×{meta['module_height_mm']:.0f} @ "
                 f"{meta['wall_thickness_mm']:.0f} mm · best-over-8 IK je Basishöhe", fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "figB1_base_vs_hmax.png", dpi=150)
    plt.close(fig)
    print(f"[plots] geschrieben nach {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
