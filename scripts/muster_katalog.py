"""Musterkatalog erzeugen: Kennzahlen, SVG-Bilder und `docs/muster/MUSTERKATALOG.md`.

Aufruf: `python scripts/muster_katalog.py [--out DATEI] [--images DIR] [--presets NAME ...]
        [--sections 600x200 ...] [--report runs/verify_muster/report.json] [--no-images]`

- Presets: `core/src/roboprint/patterns/presets/*.json` und `docs/muster/presets/*.json`
  (Name = Dateiname ohne Endung; der Kern-Preset gewinnt bei gleichem Namen).
- Querschnitte (Länge x Dicke in mm): 600x200, 1000x200, 1000x300, 1000x365.
- Je Muster und Querschnitt: `patterns.preview` (Schicht 0, v = 100 mm/s) und eine SVG-Draufsicht
  nach `docs/muster/bilder/katalog/<muster>_<LxD>.svg`.
- Optional `runs/verify_muster/report.json` (Format von `scripts/verify_muster.py`): fehlt die Datei
  oder lässt sich ein Feld nicht lesen, bleiben die Roboterspalten "offen".
- Der erzeugte Teil der Markdown-Datei steht zwischen den Markern `<!-- KATALOG:... -->`. Text
  außerhalb (Abschnitt "Empfehlung") bleibt beim Neuerzeugen erhalten.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "src"))

from roboprint.patterns import load_preset, preview, preview_svg  # noqa: E402

CORE_PRESETS = ROOT / "core" / "src" / "roboprint" / "patterns" / "presets"
DOC_PRESETS = ROOT / "docs" / "muster" / "presets"
DOCS = ROOT / "docs" / "muster"
IMAGES = DOCS / "bilder" / "katalog"
OUT = DOCS / "MUSTERKATALOG.md"
REPORT = ROOT / "runs" / "verify_muster" / "report.json"
SECTIONS = ["600x200", "1000x200", "1000x300", "1000x365"]
BASELINE = "schalen"
OPEN = "offen"
#: Status eines senkrechten Schichtwechsels in `preview()["layer_change"]` (metrics.py)
VERTICAL = "vertical"

#: Kurzdoku je Mustername
DOC_OF = {
    "fugenwand": "fugenwand.md",
    "sinus": "wellen.md",
    "zickzack": "wellen.md",
    "trapez": "wellen.md",
    "maeander": "wellen.md",
}
DOC_FALLBACKS = ["topologie.md", "mehrfach.md"]
DOC_HEADS = ("Bewertung und Empfehlung", "Empfehlung")


# --------------------------------------------------------------------------- Eingaben


def find_presets(names: list[str] | None = None) -> dict[str, tuple[Path, dict[str, Any]]]:
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    for folder in (DOC_PRESETS, CORE_PRESETS):  # Kern zuletzt: gewinnt
        for p in sorted(folder.glob("*.json")):
            try:
                found[p.stem] = (p, load_preset(p))
            except (ValueError, KeyError, OSError) as exc:
                print(f"Preset {p} übersprungen: {exc}", file=sys.stderr)
    if names:
        found = {k: v for k, v in found.items() if k in names}
    return dict(sorted(found.items(), key=lambda kv: (kv[0] != BASELINE, kv[0])))


def parse_section(s: str) -> tuple[float, float]:
    a, b = s.lower().split("x")
    return float(a), float(b)


# --------------------------------------------------------------------------- Kennzahlen


def measure_one(preset: dict[str, Any], section: str) -> dict[str, Any]:
    """Kennzahlen eines Presets auf einem Querschnitt; bei Fehlern `error` statt Zahlen."""
    ln, th = parse_section(section)
    try:
        data = preview(preset, (ln, th), 0)
    except Exception as exc:  # noqa: BLE001 - jede Planungsausnahme heißt: nicht machbar
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    m = data["metrics"]
    spans = [c["span_mm"] for c in m["cells"]]
    viol = data["violations"]
    return {
        "data": data,
        "path_length_mm": m["path_length_mm"],
        "print_time_s": m["print_time_s"],
        "material_l_per_m_layer": m["material_l_per_m_layer"],
        "contacts_per_m": m["contacts_per_m"],
        "contact_length_mm": m["contact_length_mm"],
        "max_cell_span_mm": max(spans) if spans else None,
        "longest_straight_outer_mm": m["longest_straight_outer_mm"],
        "joint_spacing_mm": m["joint_spacing_mm"],
        "min_radius_mm": m["min_radius_mm"],
        "shell_coverage": m["shell_coverage"],
        "strands": m["strands"],
        "errors": sum(1 for v in viol if v["severity"] == "error"),
        "warnings": sum(1 for v in viol if v["severity"] != "error"),
        "rules": sorted({v["rule"] for v in viol}),
        "layer_change": (data.get("layer_change") or {}).get("status"),
    }


# --------------------------------------------------------------------------- Roboterbericht

ALIASES = {
    "feasible": ("feasible", "machbar", "ok", "passed", "pass", "green"),
    "d_min": ("d_min_mm", "d_min", "dmin", "min_distance_mm", "min_clearance_mm"),
    "strands": ("strands_per_layer", "strands", "straenge", "n_strands"),
    "vertical": (
        "vertical_layer_change_share",
        "vertical_layer_changes",
        "vertical_share",
        "vertical_fraction",
        "vertical_pct",
        "anteil_senkrecht",
    ),
    "print_time": ("print_time_s", "print_time", "druckzeit_s", "duration_s"),
    "planner": (
        "planner_runtime_s",
        "planner_time_s",
        "planner_s",
        "plan_time_s",
        "planner_runtime",
        "planner_ms",
    ),
}


def _flatten(d: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif not isinstance(d, list):
        out[prefix.rstrip(".")] = d
    return out


def _pick(flat: dict[str, Any], key: str) -> tuple[str, Any]:
    """(gefundener Feldname, Wert); ("", None), wenn kein Alias passt."""
    for alias in ALIASES[key]:
        for k, v in flat.items():
            if k.split(".")[-1].lower() == alias and v is not None:
                if alias.endswith("_ms") and isinstance(v, int | float):
                    return alias, v / 1000.0
                return alias, v
    return "", None


ID_KEYS = ("name", "scenario", "id", "pattern", "preset", "muster")


def _label(e: dict[str, Any], i: Any) -> str:
    return str(e.get("name") or e.get("scenario") or e.get("id") or i)


def load_robot_report(path: Path) -> list[dict[str, Any]]:
    """Einträge des Musterberichts als flache Dicts mit `_label`; leer, wenn nichts lesbar ist."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries: list[tuple[str, Any]] = []
    if isinstance(raw, list):
        entries = [(_label(e, i), e) for i, e in enumerate(raw) if isinstance(e, dict)]
    elif isinstance(raw, dict):
        for key in ("scenarios", "runs", "results", "patterns", "entries"):
            val = raw.get(key)
            if isinstance(val, list):
                entries = [(_label(e, i), e) for i, e in enumerate(val) if isinstance(e, dict)]
                break
            if isinstance(val, dict):
                entries = [(str(k), e) for k, e in val.items() if isinstance(e, dict)]
                break
    out = []
    for label, e in entries:
        flat = _flatten(e)
        flat["_label"] = label
        # Zuordnung nur über identifizierende Felder, nicht über Freitext (Beschreibungen nennen
        # z. B. "Schalen" und würden sonst jedem Muster zugeordnet).
        ids = [str(v) for k, v in flat.items() if k.split(".")[-1].lower() in ID_KEYS and isinstance(v, str)]
        flat["_text"] = " ".join([label, *ids]).lower()
        out.append(flat)
    return out


def fmt_robot(key: str, v: Any, field: str = "") -> str:
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, str):
        return {"true": "ja", "false": "nein", "pass": "ja", "fail": "nein"}.get(v.lower(), v)
    if key == "vertical" and isinstance(v, int | float):
        if field.endswith("_changes"):  # Anzahl, kein Anteil
            return str(int(v)) if float(v).is_integer() else f"{v:.1f}".replace(".", ",")
        if field.endswith("_pct"):
            return f"{v:.0f} %"
        return f"{v * 100:.0f} %" if v <= 1.0 else f"{v:.0f} %"
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    return str(v)


def _mentions(text: str, name: str) -> bool:
    """`name` steht als eigenes Wort in `text` (`_` trennt, Buchstaben und Ziffern nicht)."""
    return re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", text) is not None


def owner(text: str, known: list[str]) -> str | None:
    """Das spezifischste bekannte Muster im Text: "fugenwand_raute" schlägt "fugenwand"."""
    hits = [n for n in known if _mentions(text, n)]
    return max(hits, key=len) if hits else None


def robot_rows(
    entries: list[dict[str, Any]], preset: str, known: list[str] | None = None
) -> list[dict[str, str]]:
    names = sorted(set(known or []) | {preset})
    rows = []
    for e in entries:
        if owner(e["_text"], names) != preset:
            continue
        row = {"label": e["_label"]}
        for k in ALIASES:
            field, v = _pick(e, k)
            row[k] = OPEN if v is None else fmt_robot(k, v, field)
        rows.append(row)
    return rows


def robot_summary(rows: list[dict[str, str]]) -> str:
    vals = [r["feasible"] for r in rows if r["feasible"] != OPEN]
    if not vals:
        return OPEN
    return "ja" if all(v == "ja" for v in vals) else "nein"


# --------------------------------------------------------------------------- Markdown


def num(v: Any, nd: int = 1, unit: str = "") -> str:
    if v is None:
        return "–"
    return f"{v:.{nd}f}".replace(".", ",") + unit


def rel(v: float, base: float | None) -> str:
    return "–" if not base else f"{v / base:.2f}".replace(".", ",")


def status_of(r: dict[str, Any]) -> str:
    if "error" in r:
        return "nicht machbar"
    if r["errors"]:
        return f"{r['errors']} Fehler"
    return "ok" if not r["warnings"] else f"ok, {r['warnings']} Warn."


def kennzahlen_table(res: dict[str, dict[str, Any]], base: dict[str, dict[str, Any]], secs: list[str]) -> str:
    def bm(s: str) -> float | None:
        b = base.get(s)
        return None if not b or "error" in b else b["material_l_per_m_layer"]

    rows = [
        ("Status (M1–M7)", lambda r, s: status_of(r)),
        ("Pfadlänge je Schicht", lambda r, s: num(r["path_length_mm"], 0, " mm")),
        ("Druckzeit je Schicht (100 mm/s)", lambda r, s: num(r["print_time_s"], 1, " s")),
        ("Material je m, relativ zu „schalen“", lambda r, s: rel(r["material_l_per_m_layer"], bm(s))),
        ("Kontaktzonen je m", lambda r, s: num(r["contacts_per_m"], 1)),
        ("Größte Zellspannweite", lambda r, s: num(r["max_cell_span_mm"], 0, " mm")),
        ("Längste gerade ungestützte Außenstrecke", lambda r, s: num(r["longest_straight_outer_mm"], 0, " mm")),
        (
            "Fugenabstand",
            lambda r, s: ", ".join(num(x, 0) for x in r["joint_spacing_mm"][:6]) + " mm"
            if r["joint_spacing_mm"]
            else "–",
        ),
        ("Kleinster Krümmungsradius", lambda r, s: num(r["min_radius_mm"], 1, " mm")),
        (
            "Verstöße (Fehler / Warnungen)",
            lambda r, s: f"{r['errors']} / {r['warnings']}" + (f" ({', '.join(r['rules'])})" if r["rules"] else ""),
        ),
        ("Schalenabdeckung", lambda r, s: num(r["shell_coverage"] * 100, 1, " %")),
        ("Stränge je Schicht", lambda r, s: str(r["strands"])),
    ]
    lines = ["| Kennzahl | " + " | ".join(secs) + " |", "|---|" + "---|" * len(secs)]
    for label, fn in rows:
        cells = []
        for s in secs:
            r = res[s]
            if "error" in r:
                cells.append("nicht machbar" if label.startswith("Status") else "–")
            else:
                cells.append(fn(r, s))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def doc_section(doc: str) -> str | None:
    p = DOCS / doc
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    for head in DOC_HEADS:
        m = re.search(rf"^## {re.escape(head)}\s*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def pros_cons(
    res: dict[str, dict[str, Any]], base: dict[str, dict[str, Any]], secs: list[str], w_mm: float = 30.0
) -> tuple[list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []
    ok = [s for s in secs if "error" not in res[s]]
    bad = [s for s in secs if "error" in res[s]]
    if bad:
        cons.append(f"Nicht machbar auf {', '.join(bad)} (die Planung meldet eine Ausnahme).")
    if not ok:
        return pros, cons
    clean = [s for s in ok if res[s]["errors"] == 0]
    if len(clean) < len(ok):
        cons.append(f"Regelfehler (M1–M7) auf {', '.join(s for s in ok if s not in clean)}.")
    else:
        pros.append(f"Regelkonform (keine M1–M7-Fehler) auf {', '.join(clean)}.")
    mats = [
        res[s]["material_l_per_m_layer"] / base[s]["material_l_per_m_layer"]
        for s in ok
        if s in base and "error" not in base[s]
    ]
    if mats:
        lo, hi = min(mats), max(mats)
        txt = f"Material {num(lo, 2)}- bis {num(hi, 2)}-fach gegenüber „schalen“."
        (pros if hi <= 1.05 else cons).append(txt)
    cpm = max(res[s]["contacts_per_m"] for s in ok)
    if cpm >= 6:
        pros.append(f"Viele Kontaktzonen (bis {num(cpm, 1)} je m) verzahnen Schalen und Füllung.")
    elif cpm == 0:
        cons.append("Keine Kontaktzonen: Schalen und Füllung sind nur über den Strang verbunden.")
    spans = [res[s]["max_cell_span_mm"] for s in ok if res[s]["max_cell_span_mm"] is not None]
    if spans and max(spans) <= 300:
        pros.append(f"Kleine Zellen (Spannweite höchstens {max(spans):.0f} mm).")
    elif spans and max(spans) > 400:
        cons.append(f"Große Zellen (Spannweite bis {max(spans):.0f} mm).")
    radii = [res[s]["min_radius_mm"] for s in ok if res[s]["min_radius_mm"] is not None]
    if radii and min(radii) < w_mm:
        cons.append(f"Kleinster Radius {num(min(radii), 1)} mm liegt unter der Strangbreite (M6-Warnung).")
    if max(res[s]["strands"] for s in ok) == 1:
        pros.append("Ein Strang je Schicht und Insel (M1).")
    lc = {res[s]["layer_change"] for s in ok} - {VERTICAL, None}
    if lc:
        cons.append(f"Schichtwechsel nicht überall senkrecht ({', '.join(sorted(map(str, lc)))}).")
    for s in ok:
        ln = parse_section(s)[0]
        st = res[s]["longest_straight_outer_mm"]
        if st is not None and st >= 0.8 * ln:
            cons.append(f"Auf {s} verläuft die Außenhaut ungegliedert gerade ({st:.0f} mm): Rissgefahr beim Trocknen.")
            break
    return pros, cons


def draft_recommendation(summary: list[dict[str, Any]], secs: list[str]) -> str:
    cand = [s for s in summary if s["name"] != BASELINE and s["clean_all"]]
    if not cand:
        return "**Entwurf:** Kein Muster ist auf allen Querschnitten regelkonform; ein Entwurf entfällt."

    def score(s: dict[str, Any]) -> float:
        return s["material"] - 0.02 * s["contacts"] - 0.0003 * s["span"]

    lines = ["**Entwurf aus den Zahlen (nicht abgestimmt; der Orchestrator schreibt ihn um).**", ""]
    for k, s in enumerate(sorted(cand, key=score)[:3], 1):
        lines.append(
            f"{k}. **{s['name']}**: Material im Mittel {num(s['material'], 2)}-fach gegenüber „schalen“, "
            f"bis {num(s['contacts'], 1)} Kontaktzonen je m, größte Zelle {num(s['span'], 0)} mm, "
            f"Druckzeit {num(s['time'], 0)} s je Schicht auf {secs[0]}."
        )
    nr = [s["name"] for s in summary if s["name"] != BASELINE and not s["clean_all"]]
    if nr:
        lines += ["", f"Nicht auf allen Querschnitten regelkonform: {', '.join(nr)}."]
    lines += [
        "",
        (
            "Rangfolge nach Materialverbrauch, Kontaktzonen und Zellgröße. Erreichbarkeit und Kollision "
            "des Roboters fließen nicht ein, solange die Roboterspalten „offen“ sind."
        ),
    ]
    return "\n".join(lines)


def build(
    presets: dict[str, tuple[Path, dict[str, Any]]],
    secs: list[str],
    entries: list[dict[str, Any]],
    images_dir: Path,
    write_images: bool,
) -> tuple[str, str]:
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for name, (_, preset) in presets.items():
        results[name] = {s: measure_one(preset, s) for s in secs}
        if write_images:
            images_dir.mkdir(parents=True, exist_ok=True)
            for s in secs:
                r = results[name][s]
                if "error" not in r:
                    (images_dir / f"{name}_{s}.svg").write_text(preview_svg(data=r["data"]) + "\n", encoding="utf-8")
    base = results.get(BASELINE, {})

    def bmat(s: str) -> float | None:
        b = base.get(s)
        return None if not b or "error" in b else b["material_l_per_m_layer"]

    comp: list[str] = []
    for s in secs:
        comp += [
            f"**{s} mm** (Schicht 0)",
            "",
            (
                "| Muster | Status | Pfad mm | Zeit s | Material rel. | Kontakte/m | Zelle mm "
                "| gerade Außen mm | R min mm | Roboter machbar |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name in presets:
            r = results[name][s]
            rob = robot_summary(robot_rows(entries, name, list(presets)))
            if "error" in r:
                comp.append(f"| {name} | nicht machbar | – | – | – | – | – | – | – | {rob} |")
                continue
            comp.append(
                f"| [{name}](#{name}) | {status_of(r)} | {num(r['path_length_mm'], 0)} | "
                f"{num(r['print_time_s'], 1)} | {rel(r['material_l_per_m_layer'], bmat(s))} | "
                f"{num(r['contacts_per_m'], 1)} | {num(r['max_cell_span_mm'], 0)} | "
                f"{num(r['longest_straight_outer_mm'], 0)} | {num(r['min_radius_mm'], 1)} | {rob} |"
            )
        comp.append("")

    summary = []
    for name in presets:
        pairs = [(s, results[name][s]) for s in secs if "error" not in results[name][s]]
        if not pairs:
            summary.append({"name": name, "clean_all": False, "material": 9, "contacts": 0, "span": 0, "time": 0})
            continue
        mats = [r["material_l_per_m_layer"] / bmat(s) for s, r in pairs if bmat(s)]
        summary.append(
            {
                "name": name,
                "clean_all": len(pairs) == len(secs) and all(r["errors"] == 0 for _, r in pairs),
                "material": sum(mats) / len(mats) if mats else 1.0,
                "contacts": max(r["contacts_per_m"] for _, r in pairs),
                "span": max(r["max_cell_span_mm"] or 0 for _, r in pairs),
                "time": pairs[0][1]["print_time_s"],
            }
        )

    block1 = [
        "## Vergleich",
        "",
        (
            "Material je m relativ zu „schalen“ (zwei Schalen ohne Infill = 1,00). Zeit und Pfad je Schicht. "
            "Die Spalte „Roboter machbar“ kommt aus `runs/verify_muster/report.json` (sonst „offen“)."
        ),
        "",
        *comp,
        "### Entwurf der Empfehlung",
        "",
        draft_recommendation(summary, secs),
    ]

    det: list[str] = ["## Muster im Einzelnen", ""]
    shown_docs: set[str] = set()
    for name, (path, preset) in presets.items():
        det += [f"### {name}", "", f"*{preset.get('name', name)}*  ", f"Preset: `{path.relative_to(ROOT).as_posix()}`", ""]
        if preset.get("description"):
            det += [preset["description"], ""]
        for s in secs:
            if "error" in results[name][s]:
                det += [f"**{s}**: nicht machbar. `{results[name][s]['error']}`", ""]
            else:
                det += [f"![{name} {s}](bilder/katalog/{name}_{s}.svg)", ""]
        det += ["Kennzahlen (Schicht 0):", "", kennzahlen_table(results[name], base, secs), ""]
        rob = robot_rows(entries, name, list(presets))
        det += ["Roboter (aus `verify_muster`):", ""]
        if rob:
            det += [
                "| Szenario | machbar | d_min | Stränge/Schicht | senkrechte Wechsel | Druckzeit | Planerlaufzeit |",
                "|---|---|---|---|---|---|---|",
            ]
            det += [
                f"| {x['label']} | {x['feasible']} | {x['d_min']} | {x['strands']} | {x['vertical']} "
                f"| {x['print_time']} | {x['planner']} |"
                for x in rob
            ]
        else:
            det.append(
                f"machbar {OPEN}, d_min {OPEN}, Stränge je Schicht {OPEN}, senkrechte Schichtwechsel {OPEN}, "
                f"Druckzeit {OPEN}, Planerlaufzeit {OPEN}."
            )
        det.append("")
        w_mm = float((preset.get("params") or {}).get("bead_width_mm", 30.0))
        pros, cons = pros_cons(results[name], base, secs, w_mm)
        det += ["**Vorteile**", "", *(f"- {p}" for p in (pros or ["–"])), ""]
        det += ["**Nachteile**", "", *(f"- {c}" for c in (cons or ["–"])), ""]
        pat = preset.get("pattern", "")
        docs = [d for d in (DOC_OF.get(name), DOC_OF.get(pat)) if d]
        if not docs and pat:
            docs = [
                d
                for d in DOC_FALLBACKS
                if (DOCS / d).exists() and pat in (DOCS / d).read_text(encoding="utf-8")
            ]
        docs = list(dict.fromkeys(d for d in docs if (DOCS / d).exists()))
        for d in docs:
            det.append(f"Kurzdoku: [{d}]({d})")
            sec = doc_section(d)
            if sec and d not in shown_docs:
                shown_docs.add(d)
                det += ["", "Einschätzung der Kurzdoku:", "", *(("> " + ln) if ln else ">" for ln in sec.splitlines())]
            det.append("")
        if not docs:
            det += ["Keine Kurzdoku vorhanden; Vor- und Nachteile aus den Zahlen.", ""]
    return "\n".join(block1), "\n".join(det)


HEAD = """# Musterkatalog

Vergleich der Druckmuster (Infill und Outfill) für Wandmodule. Alle Zahlen stammen aus der
2D-Vorschau (`roboprint.patterns.preview`, Schicht 0, Strangbreite 30 mm, Schichthöhe 10 mm,
100 mm/s) und gelten für prismatische Querschnitte. Die Roboterspalten (Erreichbarkeit,
Kollisionsabstand, Planerlaufzeit) kommen aus dem Musterlauf `scripts/verify_muster.py`.

Neu erzeugen: `python scripts/muster_katalog.py`. Nur der Text zwischen den Markern wird
überschrieben.
"""

EMPFEHLUNG = """## Empfehlung

*Platzhalter: Den Text schreibt der Orchestrator nach dem Musterlauf. Ein Entwurf aus den Zahlen
steht oben im Abschnitt "Vergleich".*
"""


def block(name: str, body: str) -> str:
    return f"<!-- KATALOG:{name}:BEGIN -->\n{body}\n<!-- KATALOG:{name}:END -->"


def render(existing: str | None, b1: str, b2: str) -> str:
    def repl(text: str, name: str, body: str) -> str:
        pat = re.compile(rf"<!-- KATALOG:{name}:BEGIN -->.*?<!-- KATALOG:{name}:END -->", re.DOTALL)
        return pat.sub(lambda m: block(name, body), text, count=1)

    if existing and "KATALOG:VERGLEICH:BEGIN" in existing and "KATALOG:DETAILS:BEGIN" in existing:
        return repl(repl(existing, "VERGLEICH", b1), "DETAILS", b2)
    return "\n".join([HEAD, block("VERGLEICH", b1), "", EMPFEHLUNG, block("DETAILS", b2), ""])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Musterkatalog erzeugen")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--images", type=Path, default=IMAGES)
    ap.add_argument("--presets", nargs="*", help="nur diese Presets (Dateiname ohne Endung); schalen kommt dazu")
    ap.add_argument("--sections", nargs="*", default=SECTIONS)
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument("--no-images", action="store_true")
    a = ap.parse_args(argv)

    names = sorted(set(a.presets) | {BASELINE}) if a.presets else None
    presets = find_presets(names)
    if not presets:
        print("Keine Presets gefunden", file=sys.stderr)
        return 1
    entries = load_robot_report(a.report) if a.report.exists() else []
    b1, b2 = build(presets, a.sections, entries, a.images, not a.no_images)
    existing = a.out.read_text(encoding="utf-8") if a.out.exists() else None
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(existing, b1, b2), encoding="utf-8")
    print(f"{a.out}: {len(presets)} Muster x {len(a.sections)} Querschnitte, Roboterbericht: {len(entries)} Einträge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
