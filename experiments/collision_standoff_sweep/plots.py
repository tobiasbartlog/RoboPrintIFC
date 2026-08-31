"""Paper-Abbildungen aus dem Abstand-Sweep (grid.csv / summary.csv / meta.json).

Erzeugt drei Figuren nach data/figures/:
  fig1_clearance.png   — Heatmap Abstand×Höhe, signierte Mindestdistanz (mm);
                         Konturen bei 0 mm (harte Kollision) und 50 mm (Sicherheit),
                         plus onset-Kurve h_frei(d) = unterste nicht-grüne Höhe.
  fig2_limiter.png     — Je Zelle das limitierende Glied (nur nicht-grüne Zellen):
                         zeigt, welches Glied unten vs. oben die Grenze setzt.
  fig3_tradeoff.png    — Zielkonflikt: nutzbare Druckhöhe (Kollisionsgrenze) steigt
                         mit dem Abstand, Reichweite-Warnungen steigen ebenfalls.

Aufruf:  python experiments/collision_standoff_sweep/plots.py
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
from matplotlib.colors import BoundaryNorm, ListedColormap, TwoSlopeNorm

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "data"
FIG = DATA / "figures"


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(x):
    return None if x in (None, "", "None") else float(x)


def _i(x):
    return None if x in (None, "", "None") else int(float(x))


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    grid = _read_csv(DATA / "grid.csv")
    summ = _read_csv(DATA / "summary.csv")
    link_names = {int(k): v for k, v in meta["link_names"].items()}

    standoffs = sorted({_f(r["standoff_mm"]) for r in grid})
    layers = sorted({_i(r["layer"]) for r in grid})
    lh = meta["layer_height_mm"]
    si = {d: i for i, d in enumerate(standoffs)}
    li = {ly: j for j, ly in enumerate(layers)}

    dist = np.full((len(layers), len(standoffs)), np.nan)
    link = np.full((len(layers), len(standoffs)), -1, dtype=int)
    reachf = np.full((len(layers), len(standoffs)), np.nan)
    for r in grid:
        j = si[_f(r["standoff_mm"])]
        i = li[_i(r["layer"])]
        md = _f(r["min_dist_mm"])
        dist[i, j] = np.nan if md is None else md
        wl = _i(r["worst_link"])
        link[i, j] = -1 if wl is None else wl
        rf = _f(r.get("reach_frac"))
        reachf[i, j] = np.nan if rf is None else rf

    heights = [ly * lh for ly in layers]
    extent = [min(standoffs) - 25, max(standoffs) + 25, min(heights) - lh / 2, max(heights) + lh / 2]
    subtitle = (f"Modul {meta['module_index']} ({meta['section_id']}) · "
                f"{meta['module_length_mm']:.0f}×{meta['module_height_mm']:.0f} mm · "
                f"Projekt {meta['project']} · {meta['scene_mode']}-Modus")

    # ---- fig1: signierte Mindestdistanz -------------------------------------
    fig, ax = plt.subplots(figsize=(9, 6))
    vabs = np.nanmax(np.abs(np.clip(dist, -150, 150)))
    norm = TwoSlopeNorm(vmin=-vabs, vcenter=0.0, vmax=vabs)
    im = ax.imshow(np.clip(dist, -150, 150), origin="lower", aspect="auto",
                   extent=extent, cmap="RdBu", norm=norm, interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, extend="both")
    cb.set_label("worst-case Mindestdistanz je Zelle (mm)\n<0 Durchdringung · <50 Sicherheitszone")
    # Konturen 0 (Kollision) und 50 (Sicherheit)
    Xc, Yc = np.meshgrid(standoffs, heights)
    with np.errstate(invalid="ignore"):
        ax.contour(Xc, Yc, dist, levels=[0.0], colors="k", linewidths=1.6)
        ax.contour(Xc, Yc, dist, levels=[50.0], colors="k", linewidths=0.8, linestyles="--")
    # onset-Kurve: unterste nicht-grüne Höhe je Abstand
    xs, ys = [], []
    for r in summ:
        h = _f(r["lowest_nongreen_height_mm"])
        xs.append(_f(r["standoff_mm"]))
        ys.append(h if h is not None else max(heights) + lh)
    ax.plot(xs, ys, "o-", color="black", ms=4, lw=1.4,
            label="h_frei(d): unterste nicht-grüne Höhe (Kollisionsbeginn von unten)")
    ax.set_xlabel("Abstand Basis↔Wandfront  standoff (mm)")
    ax.set_ylabel("Druckhöhe (mm)")
    ax.set_title(f"Kollisions-Landschaft über Abstand und Höhe\n{subtitle}", fontsize=10)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(FIG / "fig1_clearance.png", dpi=150)
    plt.close(fig)

    # ---- fig2: limitierendes Glied (nur nicht-grüne Zellen) -----------------
    # grün = Mindestdistanz >= 50 ODER kein Verursacher
    present = sorted({int(v) for v in np.unique(link) if v >= 0})
    palette = {1: "#8c564b", 2: "#d62728", 3: "#ff7f0e", 4: "#1f77b4",
               5: "#9467bd", 6: "#7f7f7f", 7: "#2ca02c"}
    cats = present
    cmap = ListedColormap([palette.get(c, "#cccccc") for c in cats])
    bounds = np.arange(len(cats) + 1) - 0.5
    norm2 = BoundaryNorm(bounds, cmap.N)
    limg = np.full(link.shape, np.nan)
    green = (dist >= 50.0) | np.isnan(dist)
    for idx, c in enumerate(cats):
        limg[(link == c) & (~green)] = idx
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.set_facecolor("#eef7ee")  # grün = frei
    im = ax.imshow(limg, origin="lower", aspect="auto", extent=extent,
                   cmap=cmap, norm=norm2, interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, ticks=range(len(cats)))
    cb.ax.set_yticklabels([f"Glied {c} ({link_names.get(c, '?')})" for c in cats])
    cb.set_label("limitierendes Glied (nicht-grüne Zellen); heller Grund = frei")
    ax.set_xlabel("Abstand Basis↔Wandfront  standoff (mm)")
    ax.set_ylabel("Druckhöhe (mm)")
    ax.set_title(f"Welches Glied setzt die Grenze — unten vs. oben\n{subtitle}", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "fig2_limiter.png", dpi=150)
    plt.close(fig)

    # ---- fig3: Zielkonflikt als "Schere" ------------------------------------
    # zwei gegenläufige Bedingungen über den Abstand, je als max. zusammenhängende
    # Höhe von unten:
    #   h_kollfrei(d) = erste Höhe mit Mindestdistanz < 50 mm  (steigt mit d)
    #   h_reach(d)    = erste Höhe mit Erreichbarkeit < 50 %   (fällt mit d)
    #   h_machbar(d)  = min(beide)                              (nach oben beschränkt)
    full_h = max(heights) + lh
    h_coll, h_reach, h_feas = [], [], []
    for jx in range(len(standoffs)):
        hc = full_h
        for iy in range(len(heights)):
            dv = dist[iy, jx]
            if not np.isnan(dv) and dv < 50.0:
                hc = heights[iy]
                break
        hr = full_h
        for iy in range(len(heights)):
            rv = reachf[iy, jx]
            if not np.isnan(rv) and rv < 0.5:
                hr = heights[iy]
                break
        h_coll.append(hc)
        h_reach.append(hr)
        h_feas.append(min(hc, hr))
    best_j = int(np.argmax(h_feas))
    best_feas = h_feas[best_j]
    best_d = standoffs[best_j]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(standoffs, h_coll, "o-", color="#1f77b4",
            label="h_kollfrei: kollisionsfrei von unten (steigt mit Abstand)")
    ax.plot(standoffs, h_reach, "s--", color="#d62728",
            label="h_reach: erreichbar von unten (fällt mit Abstand)")
    ax.plot(standoffs, h_feas, "D-", color="black", lw=2, ms=5,
            label="h_machbar = min(beide)")
    ax.axhline(meta["module_height_mm"], color="gray", ls=":", lw=1,
               label=f"volle Modulhöhe {meta['module_height_mm']:.0f} mm")
    ax.annotate(f"max. machbare Bandhöhe ≈ {best_feas:.0f} mm\nbei standoff {best_d:.0f} mm",
                xy=(best_d, best_feas), xytext=(best_d + 120, best_feas + 220),
                fontsize=9, arrowprops=dict(arrowstyle="->", color="black"))
    ax.set_xlabel("Abstand Basis↔Wandfront  standoff (mm)")
    ax.set_ylabel("max. zusammenhängende Druckhöhe von unten (mm)")
    ax.set_ylim(0, full_h + 60)
    ax.legend(loc="upper center", fontsize=8, framealpha=0.9)
    ax.set_title("Die Schere: Kollisionsfreiheit und Reichweite sind im Abstand "
                 "gegenläufig\n" + subtitle, fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "fig3_tradeoff.png", dpi=150)
    plt.close(fig)
    print(f"[analyse] max. machbare Bandhöhe von unten = {best_feas:.0f} mm "
          f"bei standoff {best_d:.0f} mm; volle Modulhöhe {meta['module_height_mm']:.0f} mm "
          f"→ mind. {int(np.ceil(meta['module_height_mm'] / best_feas))} Höhenbänder")

    # ---- fig4: machbare Region (kollisionsfrei UND erreichbar) --------------
    # 0 = machbar (grün & erreichbar), 1 = Kollision/Sicherheitszone (erreichbar,
    # aber <50 mm), 2 = unerreichbar (IK-Reichweite < 50 % der Samples der Höhe)
    REACH_TH = 0.5
    feas = np.full(dist.shape, np.nan)
    reachable = reachf >= REACH_TH
    green = (dist >= 50.0) | np.isnan(dist)
    feas[reachable & green] = 0
    feas[reachable & ~green] = 1
    feas[~reachable] = 2
    cmap4 = ListedColormap(["#2ca02c", "#d62728", "#9e9e9e"])
    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(feas, origin="lower", aspect="auto", extent=extent,
                   cmap=cmap4, norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3),
                   interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, ticks=[0, 1, 2])
    cb.ax.set_yticklabels(["machbar\n(frei & erreichbar)", "Kollision /\nSicherheitszone",
                           "unerreichbar\n(IK)"])
    # machbare Druckhöhe von unten je Abstand (erste nicht-machbare Höhe)
    xs2, ys2 = [], []
    for jx, d in enumerate(standoffs):
        col = feas[:, jx]
        h = max(heights) + lh
        for iy in range(len(heights)):
            if col[iy] != 0:
                h = heights[iy]
                break
        xs2.append(d)
        ys2.append(h)
    ax.plot(xs2, ys2, "o-", color="black", ms=4, lw=1.5,
            label="machbare Druckhöhe von unten")
    ax.set_xlabel("Abstand Basis↔Wandfront  standoff (mm)")
    ax.set_ylabel("Druckhöhe (mm)")
    ax.set_title("Machbare Region: kein Abstand deckt den vollen Modul\n" + subtitle,
                 fontsize=10)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(FIG / "fig4_feasible.png", dpi=150)
    plt.close(fig)

    print(f"[plots] geschrieben nach {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
