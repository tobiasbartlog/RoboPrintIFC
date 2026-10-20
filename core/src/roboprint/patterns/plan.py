"""`plan_pattern`: Querschnitte des ganzen Teils + Parameter → Schichtpfade in Druckreihenfolge.

Ablauf je Schicht L (aufsteigend) und Insel i (Polygone nach (x_min, y_min) sortiert):
1. Kontext bauen (Schalenringe, Hohlraum, Band, Teil-Bounding-Box).
2. Muster zusammensetzen:
   - ein Muster mit Rolle `full` (in `outfill` oder `infill`) baut den ganzen Inselpfad; der andere
     Platz muss `none` sein;
   - sonst Grundmuster `shell_chain`, wobei ein `outfill`-Muster den Außenring der Schale 0 ersetzt
     und ein `infill`-Muster danach angehängt wird (ab `ctx.entry`).
3. Schichtfolge: `same` → jede Schicht außen → innen. `alternate` → Schichten mit geradem L außen →
   innen, mit ungeradem L die exakte Umkehrung (`reverse_layer`: Inseln rückwärts, jeder Pfad
   rückwärts). Ende L = Anfang L + 1 in XY, solange sich der Querschnitt nicht ändert.
4. Neubeginn: Ändert sich der Querschnitt (Fläche der symmetrischen Differenz > 1 mm²) oder die
   Inselzahl gegenüber L − 1, bekommt der erste Pfad von L `restart = True`. Die Richtung folgt
   trotzdem der Parität von L; ob Ende und Anfang zufällig übereinanderliegen, misst M4 nicht als
   Fehler (Ausnahme laut AUFTRAG M4, Übergang nach SPEC §5.3: Verbinder oder Travel).

Muster mit `layer_invariant = True` werden je gleicher Inselgeometrie nur einmal gerechnet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import numpy as np
from shapely.ops import unary_union

from roboprint.patterns import registry
from roboprint.patterns.geometry import polygons
from roboprint.patterns.registry import Pattern
from roboprint.patterns.shells import SHELLS, island_band, island_cavity, shell_chain, shell_lanes
from roboprint.patterns.types import (
    Contact,
    IslandContext,
    IslandPlan,
    LayerPath,
    PatternParams,
    Segment,
    reverse_layer,
)

#: Fläche der symmetrischen Differenz, ab der ein Querschnitt als geändert gilt (mm²)
SECTION_CHANGE_MM2 = 1.0


def _normalize(res: IslandPlan | list[Segment]) -> IslandPlan:
    if isinstance(res, IslandPlan):
        return res
    return IslandPlan(list(res))


def part_bounds(sections: Mapping[int, Any]) -> tuple[float, float, float, float]:
    """(x_min, y_min, x_max, y_max) aller nicht leeren Querschnitte."""
    geoms = [g for g in sections.values() if g is not None and not g.is_empty]
    if not geoms:
        return (0.0, 0.0, 0.0, 0.0)
    b = np.array([g.bounds for g in geoms])
    return (float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 2].max()), float(b[:, 3].max()))


def resolve_patterns(params: PatternParams) -> tuple[Pattern | None, Pattern | None, Pattern | None]:
    """(full, outfill, infill) nach den Regeln im Modul-Docstring; ValueError bei Widerspruch.
    Prüft auch die Musterparameter gegen ihre ParamSpecs."""
    out = registry.get(params.outfill) if params.outfill != "none" else None
    inf = registry.get(params.infill) if params.infill != "none" else None
    for pat in (out, inf):
        if pat is not None:
            pat.resolve(dict(params.extra))
    if out is not None and out.role == "infill":
        raise ValueError(f"{out.name!r} ist ein Infill-Muster und gehört nach `infill`")
    if inf is not None and inf.role == "outfill":
        raise ValueError(f"{inf.name!r} ist ein Outfill-Muster und gehört nach `outfill`")
    fulls = [p for p in (out, inf) if p is not None and p.role == "full"]
    if fulls:
        if out is not None and inf is not None:
            raise ValueError(f"{fulls[0].name!r} baut den ganzen Pfad; der andere Platz muss `none` sein")
        return fulls[0], None, None
    if out is None and inf is None:
        return SHELLS, None, None
    return None, out, inf


def island_context(
    layer: int,
    island: int,
    region: Any,
    sections: Mapping[int, Any],
    bounds: tuple[float, float, float, float],
    params: PatternParams,
) -> IslandContext:
    """Kontext einer Insel ohne Musterbezug (spec leer, kein entry)."""
    return IslandContext(
        layer=layer,
        island=island,
        region=region,
        sections=sections,
        part_bounds=bounds,
        params=params,
        lanes=shell_lanes(region, params),
        cavity=island_cavity(region, params),
        band=island_band(region, params),
    )


def build_island(
    ctx: IslandContext, full: Pattern | None, out: Pattern | None, inf: Pattern | None
) -> IslandPlan:
    """Inselpfad (außen → innen) aus den aufgelösten Mustern."""
    if full is not None:
        return _normalize(full.build(replace(ctx, spec=full.params)))
    ring0, kind0, meta = None, "outer", {}
    if out is not None:
        o = _normalize(out.build(replace(ctx, spec=out.params)))
        if o.segments:
            ring0 = np.vstack([o.segments[0].points] + [s.points[1:] for s in o.segments[1:]])
            if np.linalg.norm(ring0[0] - ring0[-1]) > 1e-6:
                raise ValueError(f"Outfill {out.name!r} muss einen geschlossenen Ring liefern")
            kind0 = "outfill"
        meta["outfill"] = o.meta
    plan = shell_chain(ctx, ring0, kind0, open_end=inf is not None)
    plan.meta.update(meta)
    if inf is not None and plan.segments:
        last = plan.segments[-1].points
        t = last[-1] - last[-2]
        ictx = replace(
            ctx,
            spec=inf.params,
            entry=last[-1].copy(),
            entry_tangent=t / np.linalg.norm(t),
            printed=tuple(plan.segments),
        )
        ip = _normalize(inf.build(ictx))
        off = len(plan.segments)
        plan.segments.extend(ip.segments)
        plan.contacts.extend(
            Contact(c.kind, c.at, c.length_mm, (c.segments[0] + off, c.segments[1] + off), c.distance_mm)
            if min(c.segments) >= 0
            else c
            for c in ip.contacts
        )
        plan.meta["infill"] = ip.meta
    return plan


def _freeze(plan: IslandPlan) -> IslandPlan:
    for s in plan.segments:
        s.points.flags.writeable = False
    return plan


def plan_pattern(sections: Mapping[int, Any], params: PatternParams | None = None) -> list[LayerPath]:
    """Schichtpfade des ganzen Teils in Druckreihenfolge (siehe Modul-Docstring).

    `sections`: {Schicht: Polygon | MultiPolygon} in Frame P, alle Schichten des Teils.
    Rückgabe: je Schicht und Insel ein LayerPath (leere Inseln entfallen). Die Punktarrays sind
    schreibgeschützt und können zwischen Schichten geteilt sein."""
    p = (params or PatternParams()).validate()
    full, out, inf = resolve_patterns(p)
    invariant = all(x is None or x.layer_invariant for x in (full, out, inf))
    bounds = part_bounds(sections)
    cache: dict[bytes, IslandPlan] = {}
    result: list[LayerPath] = []
    prev_geom, prev_n = None, -1
    for L in sorted(sections):
        geom = sections[L]
        isl = polygons(geom)
        paths: list[LayerPath] = []
        for i, region in enumerate(isl):
            key = region.wkb
            plan = cache.get(key) if invariant else None
            if plan is None:
                plan = _freeze(
                    build_island(island_context(L, i, region, sections, bounds, p), full, out, inf)
                )
                if invariant:
                    cache[key] = plan
            if not plan.segments:
                continue
            paths.append(
                LayerPath(L, i, list(plan.segments), list(plan.contacts), "out_in", meta=dict(plan.meta))
            )
        if p.layer_order == "alternate" and L % 2 == 1:
            paths = reverse_layer(paths)
        changed = prev_geom is None or len(isl) != prev_n or _changed(prev_geom, geom)
        if paths and changed and prev_geom is not None:
            paths[0].restart = True
        prev_geom, prev_n = geom, len(isl)
        result.extend(paths)
    return result


def _changed(a: Any, b: Any) -> bool:
    if a is None or b is None or a.is_empty or b.is_empty:
        return True
    if a.equals_exact(b, 1e-9):
        return False
    return float(a.symmetric_difference(b).area) > SECTION_CHANGE_MM2


def section_union(polys: list[Any]) -> Any:
    """Hilfsfunktion für Aufrufer: Polygonliste → eine Geometrie."""
    return unary_union(polys)
