"""2D-Vorschau einer Schicht (für API, CLI und Viewer, ohne Roboter) und Muster-Presets.

- `preview(spec, outline, layer)` → JSON-fähiges Dict (Aufbau siehe `preview`-Docstring).
- `preview_svg(...)` → SVG-Draufsicht als Text.
- `load_preset` / `save_preset`: benannte Muster als JSON:
  `{"schema_version": 1, "name": str, "pattern": str, "params": {...}, "outline"?: {...},
  "description"?: str}`. `pattern` ist ein registrierter Mustername (oder `schalen`/`none` für das
  Grundmuster); die Rolle des Musters bestimmt, ob es in `outfill` oder `infill` landet. `params`
  ist flach: Kernparameter (PatternParams) und Musterparameter (ParamSpecs) nebeneinander.

Der Querschnitt der Vorschau ist prismatisch: Schicht `layer` und `layer + 1` haben dieselbe
Geometrie. Rechteck = Frame P (Ursprung in der Mitte, x ∈ [−L/2, L/2], y ∈ [−d/2, d/2]).
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box

from roboprint.patterns import registry
from roboprint.patterns.geometry import arc_length, polygons
from roboprint.patterns.metrics import measure
from roboprint.patterns.plan import plan_pattern, resolve_patterns
from roboprint.patterns.types import LayerPath, PatternParams, params_from_dict

PRESET_SCHEMA_VERSION = 1
#: Grundmuster-Namen in Presets
BASE_NAMES = ("none", "schalen")
#: Abstand der Richtungspfeile entlang eines Segments (mm)
ARROW_SPACING_MM = 120.0
KIND_COLORS = {
    "outer": "#1c7ed6",
    "inner": "#74c0fc",
    "hole": "#0ca678",
    "infill": "#e8590c",
    "web": "#2f9e44",
    "outfill": "#7048e8",
}
CONTACT_COLORS = {"joint": "#ae3ec9", "node": "#f08c00", "shell": "#15aabf"}


# --------------------------------------------------------------------------- Presets


def preset_params(preset: Mapping[str, Any]) -> PatternParams:
    """PatternParams aus einem Preset-Dict (Schema siehe Modul-Docstring)."""
    params = dict(preset.get("params", {}) or {})
    name = preset.get("pattern", "none") or "none"
    if name not in BASE_NAMES and "outfill" not in params and "infill" not in params:
        role = registry.get(name).role
        params["infill" if role == "infill" else "outfill"] = name
    return params_from_dict(params)


def load_preset(path: str | Path) -> dict[str, Any]:
    """Preset lesen und prüfen (ValueError bei fehlenden Schlüsseln, falschem Muster/Parameter)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("name", "pattern", "params"):
        if key not in data:
            raise ValueError(f"Preset {path}: Schlüssel {key!r} fehlt")
    if int(data.get("schema_version", PRESET_SCHEMA_VERSION)) > PRESET_SCHEMA_VERSION:
        raise ValueError(f"Preset {path}: schema_version {data['schema_version']} ist neuer als dieser Kern")
    resolve_patterns(preset_params(data))
    return data


def save_preset(
    path: str | Path,
    name: str,
    pattern: str,
    params: PatternParams | Mapping[str, Any],
    outline: Mapping[str, Any] | None = None,
    description: str = "",
) -> Path:
    """Preset schreiben. `params` als PatternParams (dann ohne `infill`/`outfill`, die stecken in
    `pattern`) oder als flaches Dict."""
    if isinstance(params, PatternParams):
        flat = params.to_dict()
        flat.pop("infill")
        flat.pop("outfill")
    else:
        flat = dict(params)
    data: dict[str, Any] = {
        "schema_version": PRESET_SCHEMA_VERSION,
        "name": name,
        "pattern": pattern,
        "params": flat,
    }
    if outline is not None:
        data["outline"] = dict(outline)
    if description:
        data["description"] = description
    resolve_patterns(preset_params(data))
    p = Path(path)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------- Eingaben


def make_outline(outline: Any = None) -> Polygon | MultiPolygon:
    """Querschnitt aus: None (600 × 200), (Länge, Dicke), {"length_mm", "thickness_mm"},
    {"polygon": [[x, y], …], "holes": [[[x, y], …], …]}, Punktliste oder shapely-Geometrie."""
    if outline is None:
        outline = (600.0, 200.0)
    if isinstance(outline, Polygon | MultiPolygon):
        return outline
    if isinstance(outline, Mapping):
        if "polygon" in outline:
            return Polygon(outline["polygon"], outline.get("holes") or None)
        outline = (outline["length_mm"], outline["thickness_mm"])
    a = list(outline)
    if len(a) == 2 and np.isscalar(a[0]):
        ln, th = float(a[0]), float(a[1])
        return box(-ln / 2, -th / 2, ln / 2, th / 2)
    return Polygon(a)


def _resolve_input(spec: Any) -> tuple[PatternParams, str | None, Any]:
    if spec is None:
        return PatternParams(), None, None
    if isinstance(spec, PatternParams):
        return spec.validate(), None, None
    if isinstance(spec, Mapping):
        if "pattern" in spec or "params" in spec:
            return preset_params(spec), spec.get("name"), spec.get("outline")
        return params_from_dict(spec), None, None
    raise TypeError(f"Unbekannte Eingabe für preview: {type(spec).__name__}")


# --------------------------------------------------------------------------- Vorschau


def _xy(a: Any) -> list[float]:
    return [round(float(a[0]), 2), round(float(a[1]), 2)]


def _unit(v: np.ndarray) -> list[float]:
    n = float(np.linalg.norm(v))
    return [0.0, 0.0] if n < 1e-12 else [round(float(v[0] / n), 4), round(float(v[1] / n), 4)]


def path_to_dict(lp: LayerPath) -> dict[str, Any]:
    """Schichtpfad als JSON-fähiges Dict (Polylinien je Segment, Start/Ende, Richtung, Pfeile)."""
    segs = []
    for k, s in enumerate(lp.segments):
        pts = s.points
        arc = arc_length(pts)
        arrows = []
        n = max(1, int(arc[-1] // ARROW_SPACING_MM))
        for q in (np.arange(n) + 0.5) * arc[-1] / n:
            i = int(np.clip(np.searchsorted(arc, q) - 1, 0, len(pts) - 2))
            t = (q - arc[i]) / max(arc[i + 1] - arc[i], 1e-12)
            arrows.append({"at": _xy(pts[i] + t * (pts[i + 1] - pts[i])), "dir": _unit(pts[i + 1] - pts[i])})
        segs.append(
            {
                "index": k,
                "kind": s.kind,
                "shell": s.shell,
                "label": s.label,
                "closed": s.closed,
                "points": [_xy(p) for p in pts],
                "start": _xy(pts[0]),
                "end": _xy(pts[-1]),
                "start_dir": _unit(pts[1] - pts[0]),
                "end_dir": _unit(pts[-1] - pts[-2]),
                "length_mm": round(float(arc[-1]), 2),
                "arrows": arrows,
            }
        )
    conns = [
        {"from": _xy(a), "to": _xy(b), "length_mm": round(float(np.linalg.norm(b - a)), 2)}
        for a, b in lp.connectors()
    ]
    return {
        "layer": lp.layer,
        "island": lp.island,
        "direction": lp.direction,
        "restart": lp.restart,
        "closed": lp.closed,
        "start": _xy(lp.start),
        "end": _xy(lp.end),
        "segments": segs,
        "connectors": conns,
        "length_mm": round(lp.length, 2),
        "meta": lp.meta,
        "declared_contacts": [c.to_dict() for c in lp.contacts],
    }


def _outline_dict(geom: Any) -> dict[str, Any]:
    polys = polygons(geom)
    return {
        "polygons": [
            {
                "exterior": [_xy(p) for p in g.exterior.coords],
                "holes": [[_xy(p) for p in h.coords] for h in g.interiors],
            }
            for g in polys
        ],
        "bounds": [round(float(b), 2) for b in geom.bounds],
    }


def preview(spec: Any = None, outline: Any = None, layer: int = 0) -> dict[str, Any]:
    """Vorschau der Schicht `layer` und der Folgeschicht als JSON-fähiges Dict.

    `spec`: PatternParams, flaches Parameter-Dict oder Preset-Dict ({name, pattern, params, outline?}).
    `outline`: siehe `make_outline`; fehlt es, gilt das Preset-`outline`, sonst 600 × 200.

    Rückgabe:
    `{schema_version, name, layer, pattern {infill, outfill, layer_order, resolved}, params,
      outline {polygons [{exterior, holes}], bounds}, paths [Pfad], next_layer {layer, paths},
      layer_change {distance_mm, status}, contacts [Kontakt], violations [Verstoß],
      metrics {Summen der Schicht, paths [Kennzahlen je Insel]}, timing_ms}`
    mit Pfad = `path_to_dict`, Kontakt = `Contact.to_dict` (gemessen, inkl. overlap_mm), Verstoß =
    `Violation.to_dict` (rule, severity, layer, island, at, value, limit, message)."""
    t0 = time.perf_counter()
    params, name, preset_outline = _resolve_input(spec)
    geom = make_outline(outline if outline is not None else preset_outline)
    sections = {layer: geom, layer + 1: geom}
    full, out, inf = resolve_patterns(params)
    paths = plan_pattern(sections, params)
    t1 = time.perf_counter()
    rep = measure(paths, sections, params)
    t2 = time.perf_counter()
    cur = [lp for lp in paths if lp.layer == layer]
    nxt = [lp for lp in paths if lp.layer == layer + 1]
    pm = [m for m in rep.paths if m.layer == layer]
    total = sum(m.path_length_mm for m in pm)
    contacts = [c for m in pm for c in m.contacts]
    straight = max(pm, key=lambda m: m.longest_straight_outer_mm, default=None)
    summary = {
        "path_length_mm": round(total, 2),
        "print_time_s": round(total / params.v_print_mm_s, 2),
        "v_print_mm_s": params.v_print_mm_s,
        "strands": len(cur),
        "material_l_per_m_layer": round(sum(m.material_l_per_m_layer for m in pm), 4),
        "material_l_per_m2": round(sum(m.material_l_per_m2 for m in pm), 3),
        "contacts": len(contacts),
        "contact_length_mm": round(sum(c.length_mm for c in contacts), 2),
        "contacts_per_m": round(sum(m.contacts_per_m for m in pm), 2),
        "joint_spacing_mm": [round(x, 2) for m in pm for x in m.joint_spacing_mm],
        "longest_straight_outer_mm": None
        if straight is None
        else round(straight.longest_straight_outer_mm, 2),
        "min_radius_mm": round(min((m.min_radius_mm for m in pm), default=float("inf")), 2)
        if pm and np.isfinite(min(m.min_radius_mm for m in pm))
        else None,
        "min_clearance_mm": round(min((m.min_clearance_mm for m in pm), default=float("inf")), 2)
        if pm and np.isfinite(min(m.min_clearance_mm for m in pm))
        else None,
        "cells": [c for m in pm for c in m.cells],
        "shell_coverage": round(min((m.shell_coverage for m in pm), default=1.0), 4),
        "paths": [m.to_dict() for m in pm],
    }
    lc = next((c for c in rep.layer_changes if c["from"] == layer), None)
    t3 = time.perf_counter()
    return {
        "schema_version": 1,
        "name": name,
        "layer": layer,
        "pattern": {
            "infill": params.infill,
            "outfill": params.outfill,
            "layer_order": params.layer_order,
            "resolved": {"full": full and full.name, "outfill": out and out.name, "infill": inf and inf.name},
        },
        "params": params.to_dict(),
        "outline": _outline_dict(geom),
        "paths": [path_to_dict(lp) for lp in cur],
        "next_layer": {"layer": layer + 1, "paths": [path_to_dict(lp) for lp in nxt]},
        "layer_change": lc,
        "contacts": [c.to_dict(params.w) for c in contacts],
        "violations": [v.to_dict() for v in rep.violations if v.layer in (layer, layer + 1)],
        "ok": not any(v.severity == "error" for v in rep.violations),
        "metrics": summary,
        "timing_ms": {
            "plan": round((t1 - t0) * 1e3, 1),
            "measure": round((t2 - t1) * 1e3, 1),
            "total": round((t3 - t0) * 1e3, 1),
        },
    }


# --------------------------------------------------------------------------- SVG


def preview_svg(
    spec: Any = None,
    outline: Any = None,
    layer: int = 0,
    *,
    width_px: int = 1000,
    data: Mapping[str, Any] | None = None,
) -> str:
    """SVG-Draufsicht: Querschnitt, Folgeschicht blass, Raupen und Mittellinien nach Segmentart,
    Richtungspfeile, Start (Kreis) und Ende (Quadrat), Kontakte, Verstöße rot, Kennzahlen.
    `data`: fertiges Ergebnis von `preview` (sonst wird es aus spec/outline/layer gerechnet)."""
    d = dict(data) if data is not None else preview(spec, outline, layer)
    w = float(d["params"]["bead_width_mm"])
    x0, y0, x1, y1 = d["outline"]["bounds"]
    m = w
    s = (width_px - 20) / max(x1 - x0 + 2 * m, 1e-9)
    H = (y1 - y0 + 2 * m) * s + 20
    legend_h = 150
    X = lambda x: 10 + (x - x0 + m) * s  # noqa: E731
    Y = lambda y: 10 + (y1 + m - y) * s  # noqa: E731
    P = lambda pts: " ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in pts)  # noqa: E731
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{H + legend_h:.0f}" '
        f'viewBox="0 0 {width_px} {H + legend_h:.0f}" font-family="sans-serif" font-size="12">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for poly in d["outline"]["polygons"]:
        path = "M " + P(poly["exterior"]) + " Z " + " ".join("M " + P(h) + " Z" for h in poly["holes"])
        out.append(f'<path d="{path}" fill="#f1f3f5" stroke="#adb5bd" fill-rule="evenodd"/>')
    for lp in d["next_layer"]["paths"]:
        for sg in lp["segments"]:
            out.append(
                f'<polyline points="{P(sg["points"])}" fill="none" stroke="#868e96" '
                f'stroke-opacity="0.35" stroke-width="1.5" stroke-dasharray="6 4"/>'
            )
    for lp in d["paths"]:
        for sg in lp["segments"]:
            col = KIND_COLORS.get(sg["kind"], "#000")
            out.append(
                f'<polyline points="{P(sg["points"])}" fill="none" stroke="{col}" stroke-opacity="0.18" '
                f'stroke-width="{w * s:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        for c in lp["connectors"]:
            if c["length_mm"] > 1e-6:
                out.append(
                    f'<polyline points="{P([c["from"], c["to"]])}" stroke="#212529" stroke-width="1.5" '
                    'stroke-dasharray="3 3"/>'
                )
        for sg in lp["segments"]:
            col = KIND_COLORS.get(sg["kind"], "#000")
            out.append(
                f'<polyline points="{P(sg["points"])}" fill="none" stroke="{col}" stroke-width="2">'
                f"<title>{escape(sg['kind'])} {escape(sg['label'])} {sg['length_mm']} mm</title></polyline>"
            )
            for a in sg["arrows"]:
                ax, ay, dx, dy = X(a["at"][0]), Y(a["at"][1]), a["dir"][0], -a["dir"][1]
                L, B = 9.0, 4.5
                pts = [
                    (ax + dx * L / 2, ay + dy * L / 2),
                    (ax - dx * L / 2 - dy * B, ay - dy * L / 2 + dx * B),
                    (ax - dx * L / 2 + dy * B, ay - dy * L / 2 - dx * B),
                ]
                out.append(
                    '<polygon points="' + " ".join(f"{u:.1f},{v:.1f}" for u, v in pts) + f'" fill="{col}"/>'
                )
        sx, sy = X(lp["start"][0]), Y(lp["start"][1])
        ex, ey = X(lp["end"][0]), Y(lp["end"][1])
        out.append(
            f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="7" fill="none" stroke="#2b8a3e" stroke-width="2.5">'
            "<title>Start</title></circle>"
        )
        out.append(
            f'<rect x="{ex - 5:.1f}" y="{ey - 5:.1f}" width="10" height="10" fill="none" stroke="#c92a2a" '
            'stroke-width="2.5"><title>Ende</title></rect>'
        )
    for c in d["contacts"]:
        col = CONTACT_COLORS.get(c["kind"], "#000")
        out.append(
            f'<circle cx="{X(c["at"][0]):.1f}" cy="{Y(c["at"][1]):.1f}" r="3.5" fill="{col}">'
            f"<title>Kontakt {c['kind']} {c['length_mm']} mm</title></circle>"
        )
    for v in d["violations"]:
        if v["at"] is None:
            continue
        col = "#e03131" if v["severity"] == "error" else "#f59f00"
        out.append(
            f'<circle cx="{X(v["at"][0]):.1f}" cy="{Y(v["at"][1]):.1f}" r="{max(w * s / 2, 6):.1f}" '
            f'fill="none" stroke="{col}" stroke-width="2"><title>{escape(v["rule"])}: '
            f"{escape(v['message'])}</title></circle>"
        )
    met = d["metrics"]
    ly = H + 18
    items = list(KIND_COLORS.items())
    for k, (kind, col) in enumerate(items):
        out.append(
            f'<rect x="{10 + k * 110}" y="{ly - 9}" width="18" height="6" fill="{col}"/>'
            f'<text x="{32 + k * 110}" y="{ly}">{kind}</text>'
        )
    title = d.get("name") or (d["pattern"]["resolved"]["full"] or d["pattern"]["outfill"])
    nerr = sum(1 for v in d["violations"] if v["severity"] == "error")
    nwarn = len(d["violations"]) - nerr
    lines = [
        f"{escape(str(title))} · Schicht {d['layer']} ({d['pattern']['layer_order']}), "
        f"Folgeschicht gestrichelt · Start ○  Ende □",
        f"Pfad {met['path_length_mm']} mm · Druckzeit {met['print_time_s']} s "
        f"bei {met['v_print_mm_s']} mm/s · "
        f"Material {met['material_l_per_m_layer']} l je m und Schicht · Stränge {met['strands']}",
        f"Kontakte {met['contacts']} ({met['contact_length_mm']} mm, {met['contacts_per_m']} je m) · "
        f"Fugenabstand {met['joint_spacing_mm'] or '–'} · längste gerade Außenstrecke "
        f"{met['longest_straight_outer_mm']} mm · kleinster Radius {met['min_radius_mm']} mm",
        f"Regelverstöße: {nerr} Fehler, {nwarn} Warnungen"
        + (
            f" · Schichtwechsel {d['layer_change']['status']} ({d['layer_change']['distance_mm']} mm)"
            if d.get("layer_change")
            else ""
        ),
    ]
    for k, t in enumerate(lines):
        color = "#e03131" if k == 3 and nerr else "#212529"
        out.append(f'<text x="10" y="{ly + 24 + 20 * k:.0f}" fill="{color}">{t}</text>')
    out.append("</svg>")
    return "\n".join(out)


def params_for(pattern_name: str, **values: Any) -> PatternParams:
    """Bequemlichkeit für Tests und Skripte: PatternParams mit Muster im richtigen Platz."""
    return preset_params({"pattern": pattern_name, "params": values})


__all__ = [
    "load_preset",
    "make_outline",
    "params_for",
    "path_to_dict",
    "preset_params",
    "preview",
    "preview_svg",
    "save_preset",
]
