"""Testdruck-Programme je Druckmuster (Phase M5, docs/muster/AUFTRAG.md).

    python scripts/muster_testdrucke.py                    alle Testkörper planen, prüfen, ablegen
    python scripts/muster_testdrucke.py --only sinus fermat nur diese Muster (Übersicht wird ergänzt)
    python scripts/muster_testdrucke.py --no-run           vorhandene Läufe nur neu prüfen und ablegen

Je Muster entsteht ein kleiner Testkörper (Standard 600 × 200 × 100 mm, 10 Schichten; Doppelwelle
und Waben 600 × 300 × 100 mm; Fermat als Pfeiler 300 × 200 × 100 mm) am Standard-Druckplatz
(0, −50) mm. Ablauf je Muster:

1. Szenario `docs/muster/testdrucke/<muster>/scenario.json` aus dem Musterszenario
   `docs/muster/szenarien/<basis>.json` (gleiches Preset, nur Größe, ID und Beschreibung neu).
2. Lauf und Prüfung wie `scripts/verify_muster.py` (dessen `run_scenario` wird wiederverwendet):
   `run-scenario`, `verify.check_run` (G3-Regeln, Abdeckung = bekannter Einwand),
   `verify.fake_drcf` (G5, v2 und v3), `verify_muster.check` (M1–M7). Laufordner
   `runs/muster_testdrucke/testdruck_<muster>`.
3. Nur wenn alles grün ist: `program.v2.drl`, `program.v3.drl`, `schicht0.svg` (Kernvorschau der
   Schicht 0, Folgeschicht blass) und `README.md` nach `docs/muster/testdrucke/<muster>/`.
   Sonst werden alte Programme dort entfernt und das README nennt den Grund.
4. Übersicht `docs/muster/testdrucke/README.md` mit Tabelle und Testdruckplan, Kennzahlen
   maschinenlesbar in `docs/muster/testdrucke/testdrucke.json`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core" / "src"))

from roboprint.patterns import load_preset, preview_svg  # noqa: E402

SCEN_DIR = ROOT / "docs" / "muster" / "szenarien"
DOCS = ROOT / "docs" / "muster" / "testdrucke"
RUNS = ROOT / "runs" / "muster_testdrucke"
HEIGHT_MM = 100.0
DRY_RUN = "Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck"


def _load_vm() -> Any:
    """`scripts/verify_muster.py` als Modul (Lauf und Prüfung bleiben dort an einer Stelle)."""
    spec = importlib.util.spec_from_file_location(
        "verify_muster_runner", ROOT / "scripts" / "verify_muster.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.OUT = RUNS
    return mod


#: Testkörper in der empfohlenen Druckreihenfolge (Testdruckplan). `watch`: was beim Druck zu beobachten ist.
TESTS: list[dict[str, Any]] = [
    {
        "name": "schalen_alternate",
        "base": "S4_muster_schalen_alternate",
        "size": (600, 200),
        "label": "Zwei Schalen, Schichtfolge alternate",
        "why": "Referenz ohne Muster: Haftung, Raupenbreite, senkrechter Schichtwechsel, Naht im Eckbogen.",
        "watch": "Raupe 30 mm breit und 10 mm hoch? Naht im Eckbogen ohne Klecks; S-Kurve zwischen den "
        "Schalen haftet an beiden Schalen; Schichtwechsel (Z-Hub) ohne Abriss.",
    },
    {
        "name": "fugenwand_raute",
        "base": "S4_muster_fugenwand_raute",
        "size": (600, 200),
        "label": "Fugenwand, Rautenkette (empfohlen)",
        "why": "Empfohlenes Muster des Nachtrags 18:20: Sollbruchstellen ohne Gurt, Rückseite versetzt.",
        "watch": "Fugen: Haken berühren sich, laufen aber nicht ineinander; nach dem Trocknen reißen "
        "Fugen statt Felder. Knoten der Rauten in der Wandmitte haften. Haken sauber gerundet.",
    },
    {
        "name": "sinus",
        "base": "S4_muster_sinus",
        "size": (600, 200),
        "label": "Infill Sinus",
        "why": "Einfachstes Infill-Muster: Kontakte Welle an Schale bei glatter Bahn.",
        "watch": "Kontakte der Welle an der inneren Schale haften (Überlappung 0 … 4,5 mm); "
        "keine Ausbeulung der Schale am Kontakt.",
    },
    {
        "name": "fugenwand_versetzt",
        "base": "S4_muster_fugenwand_versetzt",
        "size": (600, 200),
        "label": "Fugenwand mit Gurt, Rückseite versetzt",
        "why": "Gurtvariante; Hakenradius auf 200 mm Wand verkleinert (M6-Warnung).",
        "watch": "Kleine Haken (Radius < w): sauber oder verschmiert? Gurt in der Wandmitte haftet an den "
        "Knoten; Fugen reißen zuerst.",
    },
    {
        "name": "fugenwand_gurt",
        "base": "S4_muster_fugenwand_gurt",
        "size": (600, 200),
        "label": "Fugenwand mit Gurt, Rückseite gespiegelt",
        "why": "Lesart des Nachtrags (durchgehende Sollbruchebene); Hakenradius 21 mm < w.",
        "watch": "Gespiegelte Fugen: Riss quer durch die Wand in der Fugenebene? Haken bei r = 21 mm sauber?",
    },
    {
        "name": "zickzack",
        "base": "S4_muster_zickzack",
        "size": (600, 200),
        "label": "Infill Zickzack",
        "why": "Infill mit gerundeten Spitzen: Wenden enger als beim Sinus.",
        "watch": "Spitzen (gerundet) ohne Materialstau; Kontakte an der Schale haften.",
    },
    {
        "name": "trapez",
        "base": "S4_muster_trapez",
        "size": (600, 200),
        "label": "Infill Trapez",
        "why": "Infill mit geraden Kontaktstrecken an der Schale.",
        "watch": "Lange Kontaktstrecken an der Schale: Haftung über die ganze Länge, keine Ausbeulung.",
    },
    {
        "name": "maeander",
        "base": "S4_muster_maeander",
        "size": (600, 200),
        "label": "Infill Mäander",
        "why": "Engste Wenden der Wellen (Wenderadius 26,5 mm < w, M6-Warnung).",
        "watch": "Enge Wenden: reißt oder staucht die Raupe? Querstege senkrecht, haften an der Schale?",
    },
    {
        "name": "fugenwand_gurt_300",
        "base": "S4_muster_fugenwand_gurt_300",
        "size": (600, 300),
        "label": "Fugenwand mit Gurt auf 300 mm Wand",
        "why": "Gurtvariante mit vollem Hakenradius r = w (ab 230 mm Wanddicke).",
        "watch": "Vergleich zu fugenwand_gurt: Sind die Haken mit r = w sichtbar sauberer?",
    },
    {
        "name": "doppelwelle_300",
        "base": "S4_muster_doppelwelle_300",
        "size": (600, 300),
        "label": "Infill Doppelwelle (300 mm Wand)",
        "why": "Zwei gegenphasige Wellen; auf 200 mm nicht machbar (Band 50 mm < 55,5 mm).",
        "watch": "Kontakte der beiden Wellen untereinander (Knoten) und an den Schalen haften.",
    },
    {
        "name": "waben_300",
        "base": "S4_muster_waben_300",
        "size": (600, 300),
        "label": "Infill Waben (300 mm Wand)",
        "why": "Sechseckzellen aus zwei Trapezwellen; auf 200 mm nicht machbar.",
        "watch": "Gerade Kontaktstrecken zwischen den Trapezwellen haften, keine Lücke; Zellen zu.",
    },
    {
        "name": "fermat",
        "base": "S4_muster_fermat",
        "size": (300, 200),
        "label": "Fermat-Spirale als Pfeiler",
        "why": "Ganzer Inselpfad als Spirale, für Pfeiler gedacht; Naht an der Sichtfläche, Wende r = w/2.",
        "watch": "Wende in der Mitte (r = w/2) ohne Klecks; Naht an der Sichtfläche sichtbar?",
    },
]


# --------------------------------------------------------------------------- Hilfen


def de(v: Any, nd: int = 1) -> str:
    if v is None:
        return "–"
    if isinstance(v, (int, float)):
        return f"{v:,.{nd}f}".replace(",", " ").replace(".", ",")
    return str(v)


def _load(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def write_scenario(t: dict[str, Any]) -> Path:
    base = _load(SCEN_DIR / f"{t['base']}.json")
    if base is None:
        raise SystemExit(f"Musterszenario fehlt: {t['base']}")
    length, thick = t["size"]
    preset = base["params"].get("pattern_preset")
    sc = dict(base)
    sc["id"] = f"testdruck_{t['name']}"
    sc["beschreibung"] = (
        f"Testkörper {length} x {thick} x {int(HEIGHT_MM)} mm (Länge x Dicke x Höhe, 10 Schichten), Modus "
        f"Modul am Doosantisch, Standard-Druckplatz (0, -50) mm, lange Seite zum Roboter. "
        f"Muster: {t['label']} "
        f"(Preset {preset}). Abgeleitet aus {rel(SCEN_DIR / (t['base'] + '.json'))} "
        "durch scripts/muster_testdrucke.py."
    )
    sc["source"] = {"kind": "box", "size_mm": [length, thick, int(HEIGHT_MM)]}
    exp = dict(sc.get("expect") or {})
    mu = dict(exp.get("muster") or {})
    mu["fast"] = False
    exp["muster"] = mu
    sc["expect"] = exp
    sc["limits"] = {"wall_time_s": 200}
    out = DOCS / t["name"] / "scenario.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _poly_len(pts: list[list[float]]) -> float:
    return sum(math.dist(a[:3], b[:3]) for a, b in zip(pts, pts[1:], strict=False))


def run_extras(run: Path) -> dict[str, Any]:
    """Pfadlänge, Material, Druckzeiten und DRL-Kopf eines (einteiligen) Laufs."""
    summary = _load(run / "summary.json") or {}
    params = summary.get("params", {})
    w = float(params.get("bead_width_mm", 30.0))
    h = float(params.get("layer_height_mm", 10.0))
    parts = summary.get("parts", [])
    path_mm = link_mm = 0.0
    print_s = total_s = 0.0
    layers: set[int] = set()
    drl_head: list[str] = []
    for p in parts:
        pdir = run / "parts" / p["part_id"]
        tp = _load(pdir / "toolpath.json") or {}
        rings = tp.get("rings", [])
        for i, r in enumerate(rings):
            layers.add(int(r["layer"]))
            path_mm += _poly_len(r["waypoints"])
            if r.get("link_next") and i + 1 < len(rings):
                a, b = r["waypoints"][-1], rings[i + 1]["waypoints"][0]
                link_mm += math.dist(a[:2], b[:2])
        tr = _load(pdir / "trajectory.json") or {}
        ts, kinds = tr.get("t_s", []), tr.get("kind", [])
        for i in range(1, len(ts)):
            if kinds[i] in ("print", "link"):
                print_s += ts[i] - ts[i - 1]
        total_s += float((tr.get("summary") or {}).get("dauer_s") or 0.0)
        if not drl_head:
            drl_head = drl_assumptions(pdir / "program.v2.drl")
    length = path_mm + link_mm
    return {
        "n_collision": sum(int(p.get("n_collision") or 0) for p in parts),
        "n_unreachable": sum(int(p.get("n_unreachable") or 0) for p in parts),
        "w_mm": w,
        "h_mm": h,
        "layers": len(layers),
        "path_length_m": round(length / 1000.0, 3),
        "material_l": round(w * h * length / 1e6, 2),
        "print_time_pump_s": round(print_s, 1),
        "total_time_s": round(total_s, 1),
        "t_tot_s": float(params.get("t_tot_s", 0.0)),
        "drl_assumptions": drl_head,
    }


def drl_assumptions(drl: Path) -> list[str]:
    try:
        lines = drl.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out, inside = [], False
    for ln in lines:
        if ln.startswith("# Provisorische Werte"):
            inside = True
            continue
        if inside:
            if not ln.startswith("#   "):
                break
            out.append(ln[1:].rstrip())
    return out


# --------------------------------------------------------------------------- Ablage


def write_svg(t: dict[str, Any], scen: Path) -> str | None:
    sc = _load(scen) or {}
    preset_rel = (sc.get("params") or {}).get("pattern_preset")
    if not preset_rel:
        return None
    preset = load_preset(ROOT / preset_rel)
    svg = preview_svg(preset, tuple(float(x) for x in t["size"]), 0)
    out = DOCS / t["name"] / "schicht0.svg"
    out.write_text(svg + "\n", encoding="utf-8")
    return out.name


def part_readme(
    t: dict[str, Any], e: dict[str, Any], x: dict[str, Any] | None, svg: str | None, day: str
) -> str:
    length, thick = t["size"]
    m = e.get("metrics") or {}
    chk = e.get("checks") or {}
    g3 = chk.get("check_run") or {}
    mu = chk.get("verify_muster") or {}
    lines = [
        f"# Testdruck {t['name']}: {t['label']}",
        "",
        f"Testkörper {length} × {thick} × {int(HEIGHT_MM)} mm (10 Schichten zu 10 mm), Standard-Druckplatz "
        "(0, −50) mm, lange Seite zum Roboter. Szenario: `scenario.json`; erzeugt mit "
        "`python scripts/muster_testdrucke.py --only " + t["name"] + "`.",
        "",
        t["why"],
        "",
    ]
    if not e.get("feasible") or x is None:
        lines += [
            "**Kein Programm:** Der Testkörper ist nicht machbar oder eine Prüfung ist rot.",
            "",
            f"- Ergebnis: {e.get('verdict')}",
            f"- G3 (check_run): {e.get('g3')}, G5 (fake_drcf): {e.get('g5')}, M1–M7: {e.get('muster')} "
            f"{mu.get('failed_rules') or ''}",
            *[f"- {err}" for err in (g3.get("errors") or [])[:5]],
            "",
            f"Prüfstand {day}.",
            "",
        ]
        return "\n".join(lines)
    share = m.get("vertical_layer_change_share")
    lines += [
        f"**{DRY_RUN}** (ohne Material, `change_operation_speed` 10 … 20 %).",
        "",
        f"![Schicht 0, Folgeschicht blass]({svg})" if svg else "",
        "",
        "Bild: Vorschau des Musterkerns für diesen Querschnitt (Schicht 0, Schicht 1 blass; Kreis = Start, "
        "Quadrat = Ende).",
        "",
        "| Kennzahl | Wert |",
        "|---|---|",
        "| Programme | `program.v2.drl` (Firmware 2.x), `program.v3.drl` |",
        f"| Druckzeit gesamt | {de(x['total_time_s'] / 60, 1)} min "
        f"({de(x['total_time_s'], 0)} s, mit Anfahrt) |",
        f"| davon Pumpe an | {de(x['print_time_pump_s'], 0)} s "
        f"(+ {de(x['t_tot_s'], 0)} s Vorlauf je Strang) |",
        f"| Pfadlänge | {de(x['path_length_m'], 2)} m (alle Schichten, mit Verbindern) |",
        f"| Material | {de(x['material_l'], 1)} l (Annahme, siehe unten) |",
        f"| Stränge je Schicht | {m.get('strands_per_layer')} (gesamt {m.get('strands_total')}) |",
        f"| senkrechte Schichtwechsel | {m.get('vertical_layer_changes')} von {m.get('layer_changes')}"
        + ("" if share is None else f" ({de(100 * share, 0)} %)")
        + " |",
        f"| d_min | {de(m.get('d_min_mm'), 1)} mm (d_hard = 10 mm) |",
        f"| Ringe / Samples | {m.get('rings')} / {m.get('samples')} |",
        f"| Planerlaufzeit | {de(m.get('planner_runtime_s'), 1)} s |",
        "",
        f"Materialannahme (A): Raupenquerschnitt rechteckig "
        f"w × h = {de(x['w_mm'], 0)} × {de(x['h_mm'], 0)} mm, "
        "mal Pfadlänge der Mittellinie (Ringe plus Verbinder). Überlappung an Kontakten, Ecken und "
        "Schwinden sind nicht abgezogen; Vorlauf t_tot und Anfahrmaterial nicht eingerechnet.",
        "",
        "## Provisorische Werte (A) aus dem DRL-Kopf",
        "",
        "```",
        *x["drl_assumptions"],
        "```",
        "",
        "## Beobachten",
        "",
        t["watch"],
        "",
        "## Prüfstatus",
        "",
        f"Stand {day}, Lauf `runs/muster_testdrucke/testdruck_{t['name']}`:",
        "",
        f"- Planer: machbar ({', '.join(f'{k} {v}' for k, v in (m.get('part_status') or {}).items())}), "
        f"{x['n_collision']} collision, {x['n_unreachable']} unreachable",
        f"- G3 `python -m verify.check_run`: grün außer Abdeckung "
        f"({'Einwand' if g3.get('abdeckung') == 'einwand' else 'grün'}, min. "
        f"{de(100 * g3['abdeckung_min'], 1) if g3.get('abdeckung_min') is not None else '–'} %; "
        "Gate-Einwand 1 in MUSTER-PROGRESS.md)",
        "- G5 `python -m verify.fake_drcf`: v2 und v3 akzeptiert",
        "- M1–M7 `python -m verify_muster.check`: grün"
        + (
            f" (Warnungen: {', '.join(f'{k} {v}' for k, v in sorted(mu['warnings'].items()))})"
            if mu.get("warnings")
            else ""
        ),
        "",
    ]
    return "\n".join(lines)


PLAN_TEXT = """## Testdruckplan

Reihenfolge wie in der Tabelle: vom einfachen zum anspruchsvollen Muster, damit jeder Druck eine
neue Frage beantwortet und die vorige als geklärt voraussetzt.

1. **schalen_alternate** zuerst, als Referenz ohne Muster: Stimmen Raupenbreite (30 mm) und
   Schichthöhe (10 mm), haftet die erste Schicht, ist der senkrechte Schichtwechsel (reiner Z-Hub)
   ohne Abriss und die Naht im Eckbogen sauber? Erst wenn das passt, lohnt ein Muster.
2. **fugenwand_raute** (empfohlen): Hauptfrage des Nachtrags 18:20. Beobachten: **Fugen** – die
   Haken berühren sich, laufen aber nicht ineinander; beim Trocknen sollen Risse in den Fugen
   entstehen, nicht in den Feldern (Fotos nach 1, 3 und 7 Tagen). **Haken** – sauber gerundet,
   ohne Klecks am Umkehrpunkt. **Kontakte** – die Rautenknoten in der Wandmitte haften.
3. **sinus**: einfachstes Infill; prüft, ob Kontakte Welle an Schale haften (Überlappung 0 … ε·w).
4. **fugenwand_versetzt** und **fugenwand_gurt**: Haken mit verkleinertem Radius (< w) auf 200 mm.
   Sind sie unsauber, gilt die Gurtvariante erst ab 230 mm Wand (dann **fugenwand_gurt_300**).
5. **zickzack**, **trapez**, **maeander**: engere Wenden und lange Kontaktstrecken; Mäander hat
   den kleinsten Wenderadius (26,5 mm < w).
6. **doppelwelle_300**, **waben_300**: nur für 300-mm-Wände; Knoten zwischen den Wellen haften?
7. **fermat** als Pfeiler zuletzt: Wende r = w/2 in der Mitte und Naht an der Sichtfläche.

Je Druck festhalten: Datum, Lehmmischung und Feuchte, tatsächliche Raupenbreite und -höhe,
Stellen mit Abriss oder Stau (Ring- und Sample-Nummer aus dem DRL-Kommentar), Fotos von oben und
von der Außenseite, nach dem Trocknen Lage und Breite der Risse.
"""


def overview(results: list[dict[str, Any]], day: str) -> str:
    head = [
        "# Testdrucke je Druckmuster",
        "",
        "Kleine Testkörper (10 Schichten, 100 mm hoch) je Muster am Standard-Druckplatz (0, −50) mm,",
        "vom Planer als machbar eingestuft und geprüft. Erzeugt mit `python scripts/muster_testdrucke.py`",
        f"(Stand {day}). Je Ordner: `scenario.json`, `program.v2.drl`, `program.v3.drl`, `schicht0.svg`,",
        "`README.md`.",
        "",
        f"**{DRY_RUN}** (ohne Material, `change_operation_speed` 10 … 20 %). Alle Werte mit (A) im",
        "DRL-Kopf sind provisorisch.",
        "",
        "| Nr. | Muster | Testkörper (mm) | Status | Druckzeit | Material | Stränge/Schicht | "
        "senkrechte Wechsel | d_min | Abdeckung G3 (< 95 %: Einwand 1) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    rows = []
    for i, r in enumerate(results, 1):
        t, e, x = r["test"], r["entry"], r.get("extras")
        m = e.get("metrics") or {}
        g3 = (e.get("checks") or {}).get("check_run") or {}
        size = f"{t['size'][0]} × {t['size'][1]} × {int(HEIGHT_MM)}"
        ok = bool(e.get("feasible") and x)
        link = f"[{t['name']}]({t['name']}/README.md)"
        share = m.get("vertical_layer_change_share")
        rows.append(
            "| "
            + " | ".join(
                [
                    str(i),
                    link,
                    size,
                    "machbar, geprüft" if ok else f"kein Programm ({e.get('verdict')})",
                    f"{de(x['total_time_s'] / 60, 1)} min" if ok else "–",
                    f"{de(x['material_l'], 1)} l" if ok else "–",
                    str(m.get("strands_per_layer") or "–"),
                    "–" if share is None else f"{de(100 * share, 0)} %",
                    f"{de(m.get('d_min_mm'), 1)} mm" if m.get("d_min_mm") is not None else "–",
                    f"{de(100 * g3['abdeckung_min'], 1)} %" if g3.get("abdeckung_min") is not None else "–",
                ]
            )
            + " |"
        )
    foot = [
        "",
        "Prüfung je Testkörper: `python -m verify.check_run` (G3-Regeln; die Abdeckung < 95 % ist bei",
        "Mustern gewollt und als Gate-Einwand 1 in MUSTER-PROGRESS.md geführt), `python -m verify.fake_drcf`",
        "(G5, v2 und v3) und `python -m verify_muster.check` (M1–M7). Material: Annahme Raupenquerschnitt",
        "w × h = 30 × 10 mm mal Pfadlänge, ohne Abzug der Überlappung an Kontakten.",
        "",
        PLAN_TEXT,
    ]
    return "\n".join(head + rows + foot)


# --------------------------------------------------------------------------- Ablauf


def process(vm: Any, t: dict[str, Any], jobs: int, no_run: bool, day: str) -> dict[str, Any]:
    scen = write_scenario(t)
    entry = vm.run_scenario(scen, jobs, no_run)
    folder = DOCS / t["name"]
    run = RUNS / f"testdruck_{t['name']}"
    extras = None
    svg = None
    for f in ("program.v2.drl", "program.v3.drl", "schicht0.svg"):
        (folder / f).unlink(missing_ok=True)
    if entry.get("feasible") and entry.get("n_parts", (entry.get("metrics") or {}).get("n_parts")) == 1:
        pdir = next((run / "parts").iterdir())
        for f in ("program.v2.drl", "program.v3.drl"):
            shutil.copyfile(pdir / f, folder / f)
        extras = run_extras(run)
        svg = write_svg(t, scen)
    (folder / "README.md").write_text(part_readme(t, entry, extras, svg, day), encoding="utf-8")
    slim = {k: v for k, v in entry.items() if k not in ("steps", "checks")}
    return {"test": t, "entry": entry, "extras": extras, "slim": slim}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--only", nargs="+", metavar="MUSTER", help="nur diese Testkörper")
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("VERIFY_JOBS", "0")) or 2)
    ap.add_argument("--no-run", action="store_true", help="vorhandene Läufe nur neu prüfen")
    args = ap.parse_args(argv)
    names = {t["name"] for t in TESTS}
    if args.only and not set(args.only) <= names:
        raise SystemExit(f"Unbekannt: {sorted(set(args.only) - names)}; bekannt: {sorted(names)}")
    vm = _load_vm()
    RUNS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    day = time.strftime("%Y-%m-%d")
    old = {r["name"]: r for r in (_load(DOCS / "testdrucke.json") or {}).get("tests", [])}
    results = []
    for t in TESTS:
        if args.only and t["name"] not in args.only:
            prev = old.get(t["name"])
            if prev:
                results.append({"test": t, "entry": prev["entry"], "extras": prev.get("extras")})
            continue
        results.append(process(vm, t, max(1, args.jobs), args.no_run, day))
    (DOCS / "README.md").write_text(overview(results, day), encoding="utf-8")
    dump = {
        "created": day,
        "tests": [
            {
                "name": r["test"]["name"],
                "size_mm": [*r["test"]["size"], int(HEIGHT_MM)],
                "entry": r.get("slim")
                or {k: v for k, v in r["entry"].items() if k not in ("steps", "checks")},
                "extras": r.get("extras"),
            }
            for r in results
        ],
    }
    # `checks` je Lauf bleiben im Laufordner; hier nur Kennzahlen und Status
    for d, r in zip(dump["tests"], results, strict=True):
        chk = r["entry"].get("checks") or {}
        d["entry"]["checks"] = {
            "check_run": {
                k: (chk.get("check_run") or {}).get(k) for k in ("status", "abdeckung", "abdeckung_min")
            },
            "verify_muster": {
                k: (chk.get("verify_muster") or {}).get(k) for k in ("status", "failed_rules", "warnings")
            },
        }
    (DOCS / "testdrucke.json").write_text(
        json.dumps(dump, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    ok = [r for r in results if r["entry"].get("feasible")]
    print(f"\nTestdrucke: {len(ok)} von {len(results)} machbar und geprüft -> {rel(DOCS / 'README.md')}")
    return 0 if len(ok) == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
