"""Parameterstudie Fugenwand und Wellen (nur Kern-Vorschau, kein Roboter).

Aufruf: `python scripts/muster_studie.py [--coarse] [--skip-plots]`

Rechnet mit `patterns.preview` (Planung + `measure`, Schicht 0 und Folgeschicht) Raster über

- (a) Fugenwand, Rautenkette und Gurt (gespiegelt): Feldlänge 200…600 mm (Schritt 25) ×
  Wanddicke 200/250/300/365 × Modullänge 600/900/1200; dazu Stegwinkel- und Hakenradius-Läufe,
- (b) Sinus/Zickzack/Trapez: Wellenlänge über den ParamSpec-Bereich (80…2000 mm) ×
  Wanddicke 200/300/365 × 1 und 2 Schalen × Modullänge 600/1200,

und schreibt nach `docs/muster/studie/`: CSV je Raster, `pareto.csv`, `empfehlung.csv` (feste Auswahlregeln, siehe `recommend`), `laufzeit.json` und SVG-Diagramme.
`--coarse` halbiert die Raster (Schnelllauf). Der Bericht `docs/muster/PARAMETERSTUDIE.md` ist von Hand
geschrieben und zitiert diese Ausgaben.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "src"))

from roboprint.patterns import preview
from roboprint.patterns.preview import params_for

OUT = ROOT / "docs" / "muster" / "studie"
BASE = {"bead_width_mm": 30.0, "layer_height_mm": 10.0, "layer_order": "alternate"}
W = 30.0

FIELDS = [
    "familie", "muster", "laenge_mm", "dicke_mm", "schalen", "ziel_mm", "winkel_soll_deg",
    "hakenradius_soll_mm", "gueltig", "rueckfall", "fehler", "angepasst",
    "ist_mm", "fugenabstand_ist_mm", "felder_oder_halbwellen", "stegwinkel_min_deg",
    "kontakte", "kontakte_je_m", "kontaktlaenge_mm", "pfad_mm", "zeit_schicht_s",
    "zeit_je_m_s", "zeit_rel_schalen", "material_l_je_m", "material_rel_schalen", "zelle_spanne_mm",
    "aussenstrecke_mm", "radius_min_mm", "warn_m6", "warn_andere", "plan_ms",
]


def _baseline(cache: dict, length: float, dicke: float, shells: int) -> tuple[float, float]:
    key = (length, dicke, shells)
    if key not in cache:
        d = preview(params_for("schalen", shells=shells, **BASE), (length, dicke))
        cache[key] = (d["metrics"]["material_l_per_m_layer"], d["metrics"]["print_time_s"])
    return cache[key]


def _row(familie: str, muster: str, pv: dict, length: float, dicke: float, shells: int,
         ziel: float | None, base: tuple[float, float], winkel: float | None = None,
         radius: float | None = None) -> dict:
    meta = pv["paths"][0]["meta"] if pv["paths"] else {}
    m = pv["metrics"]
    pm = m["paths"][0]
    inf = meta.get("infill", {}) or {}
    fall = bool(meta.get("pattern_fallback") or meta.get("fallback") or inf.get("skipped"))
    errs = sorted({v["rule"] for v in pv["violations"] if v["severity"] == "error"})
    l0 = [v for v in pv["violations"] if v["layer"] == 0 and v["severity"] == "warn"]
    m6 = sum(v["rule"] == "M6" for v in l0)
    if familie.startswith("fugenwand"):
        fit = meta.get("fit", {})
        ist = meta.get("field_length_mm", fit.get("length_mm"))
        n = fit.get("count")
        sw = meta.get("web_angle_deg") or []
        sp = m.get("joint_spacing_mm") or []
        fa = (sum(sp) / len(sp)) if sp else ist
    else:
        ist = inf.get("wavelength_mm")
        n = inf.get("half_waves")
        sw = []
        fa = ist
    adj = meta.get("adjusted")
    if familie == "wellen" and ziel and ist and abs(ist - ziel) > 0.5:
        adj = (adj or "") + f"lambda {ziel:g}->{ist:g}"
    mat = m["material_l_per_m_layer"]
    base_mat, base_t = base
    rm = m["min_radius_mm"]
    return {
        "familie": familie, "muster": muster, "laenge_mm": length, "dicke_mm": dicke,
        "schalen": shells, "ziel_mm": ziel, "winkel_soll_deg": winkel,
        "hakenradius_soll_mm": radius, "gueltig": int(pv["ok"] and not fall),
        "rueckfall": int(fall), "fehler": ",".join(errs), "angepasst": json.dumps(adj) if adj else "",
        "ist_mm": None if ist is None else round(ist, 1),
        "fugenabstand_ist_mm": None if fa is None else round(fa, 1),
        "felder_oder_halbwellen": n,
        "stegwinkel_min_deg": round(min(sw), 1) if sw else None,
        "kontakte": m["contacts"], "kontakte_je_m": round(m["contacts"] / (length / 1000.0), 2),
        "kontaktlaenge_mm": m["contact_length_mm"], "pfad_mm": m["path_length_mm"],
        "zeit_schicht_s": m["print_time_s"],
        "zeit_je_m_s": round(m["print_time_s"] / (length / 1000.0), 2),
        "material_l_je_m": mat, "material_rel_schalen": round(mat / base_mat, 3),
        "zeit_rel_schalen": round(m["print_time_s"] / base_t, 3),
        "zelle_spanne_mm": pm["max_cell_span_mm"], "aussenstrecke_mm": m["longest_straight_outer_mm"],
        "radius_min_mm": rm, "warn_m6": m6, "warn_andere": len(l0) - m6,
        "plan_ms": pv["timing_ms"]["total"],
    }


def run_fugenwand(coarse: bool) -> list[dict]:
    rows, cache = [], {}
    fl = list(range(200, 601, 50 if coarse else 25))
    dicken, laengen = (200, 250, 300, 365), (600, 900, 1200)
    for muster, extra in (("raute", {"belt": False}), ("gurt", {"belt": True, "back_offset": "gespiegelt"})):
        for L in laengen:
            for d in dicken:
                base = _baseline(cache, L, d, 2)
                for F in fl:
                    pv = preview(params_for("fugenwand", field_length_mm=F, **BASE, **extra), (L, d))
                    rows.append(_row("fugenwand", muster, pv, L, d, 2, F, base))
    # Stegwinkel (Bereich der ParamSpec 0…80°), Feldlänge folgt aus dem Winkel
    for muster, extra in (("raute", {"belt": False}), ("gurt", {"belt": True, "back_offset": "gespiegelt"})):
        for d in dicken:
            base = _baseline(cache, 1200, d, 2)
            for ang in range(10, 71, 10 if coarse else 5):
                pv = preview(params_for("fugenwand", web_angle_deg=ang, **BASE, **extra), (1200, d))
                rows.append(_row("fugenwand-winkel", muster, pv, 1200, d, 2, None, base, winkel=ang))
    # Eckradius an Fuge und Knoten (ParamSpec 0…100, M6: hart >= 15, Ziel >= 30)
    for muster, extra in (("raute", {"belt": False}), ("gurt", {"belt": True, "back_offset": "gespiegelt"})):
        for d in dicken:
            base = _baseline(cache, 1200, d, 2)
            for r in (15, 20, 25, 30, 40, 50):
                pv = preview(params_for("fugenwand", field_length_mm=300, hook_radius_mm=r, **BASE, **extra), (1200, d))
                rows.append(_row("fugenwand-radius", muster, pv, 1200, d, 2, 300, base, radius=r))
    return rows


def run_wellen(coarse: bool) -> list[dict]:
    rows, cache = [], {}
    lam = [80, 100, 125, 150, 175, 200, 250, 300, 400, 500, 700, 1000, 1500, 2000]
    if coarse:
        lam = lam[::2]
    for muster in ("sinus", "zickzack", "trapez"):
        for L in (600, 1200):
            for d in (200, 300, 365):
                for sh in (1, 2):
                    base = _baseline(cache, L, d, 2)  # Bezug: zwei Schalen ohne Infill
                    for lm in lam:
                        pv = preview(params_for(muster, wavelength_mm=lm, shells=sh, **BASE), (L, d))
                        rows.append(_row("wellen", muster, pv, L, d, sh, lm, base))
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rows)


def _gl(r: dict) -> float:
    """Gliederungsmaß (kleiner ist besser): Fugenabstand bei der Fugenwand, größte Zellspannweite
    bei den Wellen. Die Kennzahl `aussenstrecke_mm` taugt dafür nur eingeschränkt: Bei der
    Fugenwand liegt ihr Boden an der Endkappe (d − 3·w), bei Wellen mit 2 Schalen zählt sie die
    ganze Außenschale."""
    if r["familie"] == "fugenwand":
        return r["fugenabstand_ist_mm"] if r["fugenabstand_ist_mm"] is not None else r["ist_mm"]
    return r["zelle_spanne_mm"]


def pareto(rows: list[dict]) -> list[dict]:
    """Nichtdominierte Zeilen je (Familie, Muster, Dicke, Länge, Schalen) über die drei Ziele
    Rissgliederung (`_gl`), Material je m (relativ zu 2 Schalen) und Druckbarkeit (M6-Warnungen);
    alle minimiert, nur gültige Zeilen. Gleiche Zielwerte (andere Ziel-Eingabe, gleiches Ergebnis)
    zählen einmal."""
    out = []
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if r["gueltig"]:
            groups.setdefault((r["familie"], r["muster"], r["dicke_mm"], r["laenge_mm"], r["schalen"]), []).append(r)

    def key(r: dict) -> tuple:
        return (_gl(r), r["material_rel_schalen"], r["warn_m6"])

    for g in groups.values():
        seen = set()
        for a in g:
            ka = key(a)
            if ka in seen:
                continue
            if not any(key(b) != ka and all(x <= y for x, y in zip(key(b), ka, strict=True)) for b in g):
                seen.add(ka)
                out.append(a)
    return out


def recommend(fw: list[dict], wl: list[dict]) -> list[dict]:
    """Empfehlung je Familie, Dicke und Modullänge nach festen Regeln (alle Schwellen A):

    - Fugenwand: gültig, keine M6-Warnung, Fugenabstand <= 300 mm (Kennzahl-Grenze, recherche.md §7),
      Rautenkette zusätzlich kleinster Stegwinkel >= 30° (recherche.md §7); dann kleinstes Material.
    - Wellen: gültig, keine M6-Warnung, größte Zellspannweite <= Wanddicke; dann kleinstes Material
      (zuerst je Schalenzahl, Muster frei).
    Ziele werden auf die kleinste Ziel-Eingabe gleichen Ergebnisses reduziert."""
    out = []
    for muster in ("raute", "gurt"):
        for d in (200, 250, 300, 365):
            for L in (600, 900, 1200):
                c = [r for r in fw if r["familie"] == "fugenwand" and r["muster"] == muster and r["dicke_mm"] == d
                     and r["laenge_mm"] == L and r["gueltig"] and r["warn_m6"] == 0 and _gl(r) <= 301.0
                     and (muster == "gurt" or (r["stegwinkel_min_deg"] or 0) >= 30.0)]
                if c:
                    out.append({**min(c, key=lambda r: (r["material_rel_schalen"], r["ziel_mm"])), "regel": "Fugenabstand<=300, M6=0"
                                + (", Steg>=30" if muster == "raute" else "")})
                else:
                    out.append({"familie": "fugenwand", "muster": muster, "dicke_mm": d, "laenge_mm": L,
                                "schalen": 2, "regel": "keine Zeile erfüllt die Regeln"})
    for sh in (1, 2):
        for d in (200, 300, 365):
            for L in (600, 1200):
                c = [r for r in wl if r["dicke_mm"] == d and r["schalen"] == sh and r["laenge_mm"] == L
                     and r["gueltig"] and r["warn_m6"] == 0 and r["zelle_spanne_mm"] <= d]
                if c:
                    out.append({**min(c, key=lambda r: (r["material_rel_schalen"], r["ziel_mm"])), "regel": "Zelle<=Dicke, M6=0"})
                else:
                    out.append({"familie": "wellen", "muster": "-", "dicke_mm": d, "laenge_mm": L, "schalen": sh,
                                "regel": "keine Zeile erfüllt die Regeln"})
    return out


# ------------------------------------------------------------------ Diagramme

def plots(fw: list[dict], wl: list[dict]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "svg.fonttype": "none", "font.family": "DejaVu Sans", "font.size": 10,
        "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False,
        "figure.dpi": 100,
    })
    col = {200: "#1b6ca8", 250: "#2a9d8f", 300: "#e9a23b", 365: "#c0392b"}
    made = []

    def save(fig, name):
        p = OUT / name
        fig.tight_layout()
        fig.savefig(p, format="svg")
        plt.close(fig)
        made.append(name)

    def sel(rows, **kw):
        return [r for r in rows if all(r[k] == v for k, v in kw.items())]

    # F1 Fugenwand: Kennzahl über Feldlänge, Linien je Dicke, Spalten je Variante (L = 1200)
    def fw_lines(key, ylabel, fname, title, extra=lambda ax: None, logy=False):
        fig, axs = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
        for ax, muster in zip(axs, ("raute", "gurt"), strict=True):
            for d, c in col.items():
                rr = sorted(sel(fw, familie="fugenwand", muster=muster, laenge_mm=1200, dicke_mm=d), key=lambda r: r["ziel_mm"])
                ok = [r for r in rr if r["gueltig"]]
                ax.plot([r["ziel_mm"] for r in ok], [r[key] for r in ok], "o-", color=c, ms=3.5, label=f"{d} mm")
                bad = [r for r in rr if not r["gueltig"]]
                ax.plot([r["ziel_mm"] for r in bad], [r[key] if r[key] is not None else 0 for r in bad], "x", color=c, ms=6)
            ax.set_title("Rautenkette (b)" if muster == "raute" else "Gurt gespiegelt (a)")
            ax.set_xlabel("Ziel-Feldlänge [mm]")
            extra(ax)
        axs[0].set_ylabel(ylabel)
        axs[1].legend(title="Wanddicke (x = ungültig/Rückfall)", fontsize=8)
        fig.suptitle(title + " (Modul 1200 mm, 2 Schalen als Bezug)")
        save(fig, fname)

    fw_lines("material_rel_schalen", "Material je m Wand, relativ zu 2 Schalen [-]", "fugenwand_material.svg",
             "Fugenwand: Materialbedarf", lambda ax: ax.axhline(1.0, color="k", lw=0.8, ls="--"))
    fw_lines("zeit_je_m_s", "Druckzeit je m Wand und Schicht [s/m]", "fugenwand_zeit.svg",
             "Fugenwand: Druckzeit")
    fw_lines("aussenstrecke_mm", "Längste gerade ungestützte Außenstrecke [mm]", "fugenwand_aussenstrecke.svg",
             "Fugenwand: Rissneigung (Kennzahl)", lambda ax: ax.axhline(300, color="k", lw=0.8, ls="--"))
    fw_lines("kontakte_je_m", "Kontaktzonen je m Wand [1/m]", "fugenwand_kontakte.svg",
             "Fugenwand: Kontaktzonen")
    fw_lines("warn_m6", "M6-Warnungen je Schicht (Radius < w) [Anzahl]", "fugenwand_warnungen.svg",
             "Fugenwand: Druckbarkeit")

    # F2 Gültigkeitskarte (Feldlänge x Dicke), L = 1200
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.4), sharey=True)
    fl = sorted({r["ziel_mm"] for r in fw if r["familie"] == "fugenwand"})
    ds = [200, 250, 300, 365]
    for ax, muster in zip(axs, ("raute", "gurt"), strict=True):
        grid = []
        for d in ds:
            row = []
            for F in fl:
                r = sel(fw, familie="fugenwand", muster=muster, laenge_mm=1200, dicke_mm=d, ziel_mm=F)[0]
                row.append(0 if not r["gueltig"] else (1 if r["warn_m6"] else 2))
            grid.append(row)
        ax.imshow(grid, aspect="auto", cmap=matplotlib.colors.ListedColormap(["#c0392b", "#e9a23b", "#2a9d8f"]), vmin=0, vmax=2,
                  extent=(fl[0] - 12.5, fl[-1] + 12.5, len(ds), 0))
        ax.set_yticks([i + 0.5 for i in range(len(ds))], [f"{d} mm" for d in ds])
        ax.set_xlabel("Ziel-Feldlänge [mm]")
        ax.set_title("Rautenkette (b)" if muster == "raute" else "Gurt gespiegelt (a)")
        ax.set_ylim(len(ds), 0)
        ax.grid(False)
    axs[0].set_ylabel("Wanddicke")
    fig.suptitle("Fugenwand: Machbarkeit, Modul 1200 mm", y=1.0)
    from matplotlib.patches import Patch

    axs[1].legend(handles=[Patch(color="#2a9d8f", label="gültig, keine Warnung"), Patch(color="#e9a23b", label="gültig, M6-Warnung (r < w)"),
                           Patch(color="#c0392b", label="ungültig / Rückfall")], loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8)
    save(fig, "fugenwand_machbarkeit.svg")

    # F3 Fugenabstand Ist gegen Ziel (alle Module)
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for L, mk in ((600, "o"), (900, "s"), (1200, "^")):
        rr = [r for r in fw if r["familie"] == "fugenwand" and r["laenge_mm"] == L and r["gueltig"] and r["muster"] == "raute" and r["dicke_mm"] == 300]
        ax.plot([r["ziel_mm"] for r in rr], [r["ist_mm"] for r in rr], mk + "-", ms=4, label=f"Modul {L} mm")
    ax.plot([200, 600], [200, 600], "k--", lw=0.8)
    ax.set_xlabel("Ziel-Feldlänge [mm]")
    ax.set_ylabel("tatsächlicher Fugenabstand (fit_to_length) [mm]")
    ax.set_title("Fugenwand 300 mm: ganze Felderzahl je Modul")
    ax.legend()
    save(fig, "fugenwand_fugenabstand.svg")

    # F4 Pareto: Material gegen ungestützte Außenstrecke
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True, sharex=True)
    for ax, muster in zip(axs, ("raute", "gurt"), strict=True):
        for d, c in col.items():
            rr = [r for r in sel(fw, familie="fugenwand", muster=muster, laenge_mm=1200, dicke_mm=d) if r["gueltig"]]
            ax.scatter([r["material_rel_schalen"] for r in rr], [_gl(r) for r in rr],
                       s=[18 if r["warn_m6"] else 34 for r in rr], color=c, alpha=0.8, label=f"{d} mm")
        ax.set_title("Rautenkette (b)" if muster == "raute" else "Gurt gespiegelt (a)")
        ax.set_xlabel("Material je m, relativ zu 2 Schalen [-]")
        ax.axhline(300, color="k", lw=0.8, ls="--")
    axs[0].set_ylabel("tatsächlicher Fugenabstand [mm]")
    axs[1].legend(title="Wanddicke (kleine Punkte = M6-Warnung)", fontsize=8)
    fig.suptitle("Fugenwand: Abwägung Rissgliederung (Fugenabstand) gegen Material (unten links ist besser; Modul 1200 mm)")
    save(fig, "fugenwand_pareto.svg")

    # F5 Stegwinkel
    for key, fam, xk, xl, fname, ttl in (
        ("stegwinkel_min_deg", "fugenwand-winkel", "winkel_soll_deg", "Ziel-Stegwinkel [°]", "fugenwand_stegwinkel.svg",
         "Fugenwand: Stegwinkel-Vorgabe (Modul 1200 mm)"),
        ("radius_min_mm", "fugenwand-radius", "hakenradius_soll_mm", "Hakenradius [mm]", "fugenwand_hakenradius.svg",
         "Fugenwand: Hakenradius (F = 300 mm, Modul 1200 mm)"),
    ):
        fig, axs = plt.subplots(1, 3, figsize=(12, 3.8))
        for ax, (k, yl) in zip(axs, (("material_rel_schalen", "Material rel. 2 Schalen [-]"),
                                      ("warn_m6", "M6-Warnungen je Schicht"),
                                      ("aussenstrecke_mm", "ungestützte Außenstrecke [mm]")), strict=True):
            for muster, ls in (("raute", "-"), ("gurt", "--")):
                for d, c in col.items():
                    rr = sorted([r for r in sel(fw, familie=fam, muster=muster, dicke_mm=d) if r["gueltig"]], key=lambda r: r[xk])
                    ax.plot([r[xk] for r in rr], [r[k] for r in rr], "o" + ls, color=c, ms=3, label=f"{muster} {d}")
            ax.set_xlabel(xl)
            ax.set_ylabel(yl)
        axs[2].legend(fontsize=6.5, ncol=2)
        fig.suptitle(ttl + " (nur gültige Läufe; durchgezogen Raute, gestrichelt Gurt)")
        save(fig, fname)

    # Wellen
    wcol = {"sinus": "#1b6ca8", "zickzack": "#e9a23b", "trapez": "#2a9d8f"}

    def wl_grid(key, ylabel, fname, title, L=600, hline=None):
        fig, axs = plt.subplots(2, 3, figsize=(12, 6.2), sharex=True, sharey="row")
        for i, sh in enumerate((2, 1)):
            for j, d in enumerate((200, 300, 365)):
                ax = axs[i][j]
                for mu, c in wcol.items():
                    rr = sorted(sel(wl, muster=mu, laenge_mm=L, dicke_mm=d, schalen=sh), key=lambda r: r["ziel_mm"])
                    ok = [r for r in rr if r["gueltig"]]
                    ax.plot([r["ziel_mm"] for r in ok], [r[key] for r in ok], "o-", ms=3, color=c, label=mu)
                    bad = [r for r in rr if not r["gueltig"]]
                    ax.plot([r["ziel_mm"] for r in bad], [r[key] or 0 for r in bad], "x", ms=6, color=c)
                ax.set_xscale("log")
                ax.set_title(f"{d} mm Wand, {sh} Schale(n) je Seite", fontsize=9)
                if hline is not None:
                    ax.axhline(hline, color="k", lw=0.8, ls="--")
                if i == 1:
                    ax.set_xlabel("Ziel-Wellenlänge [mm]")
                if j == 0:
                    ax.set_ylabel(ylabel)
        axs[0][2].legend(title="Muster (x = ungültig)")
        fig.suptitle(title + f" (Modul {L} mm)")
        fig.tight_layout()
        fig.savefig(OUT / fname, format="svg")
        plt.close(fig)
        made.append(fname)

    wl_grid("material_rel_schalen", "Material je m, relativ zu 2 Schalen [-]", "wellen_material.svg", "Wellen: Materialbedarf", hline=1.0)
    wl_grid("zeit_je_m_s", "Druckzeit je m und Schicht [s/m]", "wellen_zeit.svg", "Wellen: Druckzeit")
    wl_grid("kontakte_je_m", "Kontaktzonen je m Wand [1/m]", "wellen_kontakte.svg", "Wellen: Kontaktzonen")
    wl_grid("kontaktlaenge_mm", "Summe Kontaktlänge je Schicht [mm]", "wellen_kontaktlaenge.svg", "Wellen: Kontaktlänge")
    wl_grid("zelle_spanne_mm", "größte Zellspannweite [mm]", "wellen_zellspanne.svg", "Wellen: größte Zelle")
    wl_grid("radius_min_mm", "kleinster Radius [mm]", "wellen_radius.svg", "Wellen: kleinster Radius (Ziel >= w = 30 mm)", hline=30.0)
    wl_grid("warn_m6", "M6-Warnungen je Schicht", "wellen_warnungen.svg", "Wellen: Druckbarkeit")

    # Ist-Wellenlänge gegen Ziel
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for mu, c in wcol.items():
        for sh, ls in ((2, "-"), (1, "--")):
            rr = sorted(sel(wl, muster=mu, laenge_mm=600, dicke_mm=300, schalen=sh), key=lambda r: r["ziel_mm"])
            rr = [r for r in rr if r["ist_mm"]]
            ax.plot([r["ziel_mm"] for r in rr], [r["ist_mm"] for r in rr], "o" + ls, ms=3, color=c, label=f"{mu}, {sh} Schale(n)")
    ax.plot([80, 2000], [80, 2000], "k:", lw=0.8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Ziel-Wellenlänge [mm]")
    ax.set_ylabel("tatsächliche Wellenlänge [mm]")
    ax.set_title("Wellen: Anpassung auf ganze Halbwellen (300 mm Wand, Modul 600 mm)")
    ax.legend(fontsize=7)
    save(fig, "wellen_wellenlaenge_ist.svg")

    # Pareto Wellen
    fig, axs = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True, sharex=True)
    for ax, d in zip(axs, (200, 300, 365), strict=True):
        for mu, c in wcol.items():
            rr = [r for r in sel(wl, muster=mu, laenge_mm=600, dicke_mm=d) if r["gueltig"]]
            ax.scatter([r["material_rel_schalen"] for r in rr], [r["zelle_spanne_mm"] for r in rr],
                       s=[16 if r["warn_m6"] else 32 for r in rr],
                       color=c, alpha=0.75, label=mu)
        ax.set_title(f"{d} mm Wand")
        ax.set_xlabel("Material je m, relativ zu 2 Schalen [-]")
    axs[0].set_ylabel("größte Zellspannweite [mm]")
    axs[2].legend(title="Muster (kleine Punkte = M6-Warnung)", fontsize=8)
    fig.suptitle("Wellen: Abwägung Zellgröße gegen Material (unten links ist besser; Modul 600 mm, 1 und 2 Schalen)")
    fig.tight_layout()
    fig.savefig(OUT / "wellen_pareto.svg", format="svg")
    plt.close(fig)
    made.append("wellen_pareto.svg")
    return made


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--coarse", action="store_true", help="gröberes Raster (Schnelllauf)")
    ap.add_argument("--skip-plots", action="store_true")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    fw = run_fugenwand(a.coarse)
    t1 = time.perf_counter()
    wl = run_wellen(a.coarse)
    t2 = time.perf_counter()
    write_csv(OUT / "fugenwand.csv", fw)
    write_csv(OUT / "wellen.csv", wl)
    par = pareto([r for r in fw if r["familie"] == "fugenwand"] + wl)
    write_csv(OUT / "pareto.csv", par)
    rec = recommend(fw, wl)
    with (OUT / "empfehlung.csv").open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["regel", *FIELDS], extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rec)
    made = [] if a.skip_plots else plots(fw, wl)
    t3 = time.perf_counter()
    info = {
        "fugenwand_laeufe": len(fw), "wellen_laeufe": len(wl),
        "fugenwand_rechenzeit_s": round(t1 - t0, 1), "wellen_rechenzeit_s": round(t2 - t1, 1),
        "gesamt_s": round(t3 - t0, 1), "grob": a.coarse, "diagramme": made,
        "ungueltig_fugenwand": sum(not r["gueltig"] for r in fw),
        "ungueltig_wellen": sum(not r["gueltig"] for r in wl),
    }
    (OUT / "laufzeit.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(info, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
