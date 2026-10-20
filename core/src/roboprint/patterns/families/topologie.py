"""Familie „Topologie“: allgemeine Querschnitte, Öffnungen, Inseln, Laibungsstege und Naht.

Ein Muster `topologie` (Rolle `full`, schichtabhängig). Es schaut auf die Querschnitte des ganzen
Teils (`ctx.sections`) und wählt je Teil eine von drei Betriebsarten:

1. **allgemein** (gleichbleibender Querschnitt, beliebige Polygone, mehrere Inseln, L/U/T-Formen,
   Kerben): je Insel ein Strang nach dem Grundmuster (Schalen, S-Kurven-Wechsel), aber mit
   **geprüfter Naht** (M4): Die Kandidaten sind die Punkte des Außenrings mit dem größten
   Freiabstand zu Außen- und Stoßflächen (wie `layout.choose_seam`); jeder Kandidat wird gebaut und
   mit `metrics.measure_path` geprüft, der erste ohne Fehler gewinnt. So landet die Naht z. B. nicht
   in einer schmalen Kerbe, in der die S-Kurve keinen Platz hat (dort entstünden Radius < w/2 und
   Doppelmaterial).
2. **Abschrägung** (Rechteck, Länge gleich, Dicke nimmt Schicht für Schicht von einer Seite ab,
   z. B. die 45°-Schräge am Kopf der S2-Wände): Fermat-Doppelring mit Wende am Stirnende. Fallen
   die oberen Schenkel weg, werden die Spuren zu U-Formen, die an der Wende hängen bleiben. Die
   Wende sinkt mit; die Raupen jeder Schicht liegen auf Raupen der Schicht darunter (M3).
3. **Öffnung** (Rechteck, das sich ab einer Schicht in ein oder zwei Randpfeiler teilt, z. B.
   Brüstung + Fenster): Die Pfeiler laufen ab der Brüstung genau so weiter, wie sie in den Schichten
   darunter schon gedruckt wurden. Unter der Brüstung liegen also bereits die Laibungsschenkel
   beider Spuren als Querstege (`web`) an der künftigen Laibung (M3, „aus dem ganzen Teil
   bestimmt“). Das Brüstungsfeld dazwischen hängt mit einer Fuge (Raupen berühren sich) an den
   Pfeilern und verbindet sie zu einem Strang.

Warum es ohne Fuge nicht geht (Beleg, siehe docs/muster/topologie.md): Ein Laibungssteg über einer
durchgehenden Brüstungsschale muss an beiden Enden stumpf (Kappe) an der Schale enden, sonst bleibt
an seinem Bogen ein Zwickel, über dem der Pfeiler hängt (Fläche ≫ 1 mm², δ = 2 mm). Zwei Kappen
sind zwei freie Strangenden; ein Strang hat aber nur zwei Enden, und schon das Fenster braucht
zwei Stege. Also muss die Außenschale der Brüstung an jeder Laibung einmal unterbrochen werden.

Naht (M4, Begründung): Vollquerschnitt in der Mitte des Eckbogens am Stirnende (Freiabstand
0,29·w zu Stirn- und Außenfläche); Pfeiler innen auf Spur 1 (nicht sichtbar) bzw. an der
Laibungsecke; Abschrägung am oberen Ende des Stirnschenkels (jedes freie Ende einer U-Form liegt
an einer Fläche; die Stoßfläche ist dem Sichtbereich vorzuziehen).

Betriebsart und Gründe stehen in `meta["topology"]` jedes Inselpfads.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from roboprint.patterns.families._topologie_bahnen import (
    Frame,
    Piece,
    fermat_rect,
    fermat_yu,
    field_between,
    field_to_end,
    pillar_left,
    pillar_min_thickness,
    pillar_min_width,
    reverse_pieces,
    sill_middle_range,
)
from roboprint.patterns.families._topologie_naht import best_chain, island_lanes
from roboprint.patterns.geometry import polygons, resample_curve
from roboprint.patterns.registry import pattern
from roboprint.patterns.types import (
    IslandContext,
    IslandPlan,
    ParamSpec,
    PatternParams,
    Segment,
)

#: Toleranz der Rechteckerkennung und des Vergleichs von Querschnitten (mm)
RECT_TOL_MM = 0.5
#: Planzwischenspeicher (Teile), damit `build` je Schicht und Insel nicht neu rechnet
_CACHE: OrderedDict[tuple, _PartPlan] = OrderedDict()
_CACHE_SIZE = 8
#: Inselpfade der Betriebsart „allgemein“ je Inselgeometrie
_ISLANDS: OrderedDict[tuple, IslandPlan] = OrderedDict()

PARAMS = [
    ParamSpec(
        "sill_middle_mm",
        "Mittellauf der Brüstung",
        0.0,
        "mm",
        0.0,
        400.0,
        5.0,
        help="Lage des mittleren Laufs im Brüstungsfeld, gemessen von der Außenfläche; 0 = Wandmitte",
    ),
    ParamSpec(
        "seam_check",
        "Naht prüfen",
        True,
        "",
        kind="bool",
        help="Nahtkandidaten bauen und mit M1–M7 prüfen (allgemeine Querschnitte)",
    ),
]


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    def same_x(self, o: Rect, tol: float = RECT_TOL_MM) -> bool:
        return abs(self.x0 - o.x0) <= tol and abs(self.x1 - o.x1) <= tol

    def same_y(self, o: Rect, tol: float = RECT_TOL_MM) -> bool:
        return abs(self.y0 - o.y0) <= tol and abs(self.y1 - o.y1) <= tol

    def same(self, o: Rect, tol: float = RECT_TOL_MM) -> bool:
        return self.same_x(o, tol) and self.same_y(o, tol)


def as_rect(poly: Any, tol: float = RECT_TOL_MM) -> Rect | None:
    """Achsparalleles Rechteck (Bounding-Box), wenn das Polygon sie bis auf `tol` füllt."""
    if poly is None or poly.is_empty or len(poly.interiors):
        return None
    x0, y0, x1, y1 = poly.bounds
    if poly.area < (x1 - x0) * (y1 - y0) - tol * 2.0 * ((x1 - x0) + (y1 - y0)):
        return None
    return Rect(x0, y0, x1, y1)


@dataclass
class _PartPlan:
    mode: str
    islands: dict[tuple[int, int], IslandPlan] = field(default_factory=dict)
    note: str = ""


# --------------------------------------------------------------------------- Stücke → Segmente


def _segments(pieces: list[Piece], frame: Frame, p: PatternParams) -> list[Segment]:
    """Stücke (kanonisch) → Segmente in P; aufeinanderfolgende Stücke gleicher Art verschmelzen."""
    merged: list[Piece] = []
    for q in pieces:
        if merged and merged[-1].kind == q.kind and merged[-1].shell == q.shell:
            last = merged[-1]
            merged[-1] = Piece(q.kind, q.shell, np.vstack([last.pts, q.pts[1:]]), last.label)
        else:
            merged.append(q)
    out = []
    for q in merged:
        pts = resample_curve(frame.apply(q.pts), p.step_mm, p.chord_tol_mm)
        out.append(Segment(q.kind, q.shell, pts, label=q.label))
    return out


def _plan(pieces: list[Piece], frame: Frame, p: PatternParams, meta: dict[str, Any]) -> IslandPlan:
    segs = _segments(pieces, frame, p) if pieces else []
    if segs:
        meta = {**meta, "seam": [round(float(v), 3) for v in segs[0].start]}
    return IslandPlan(segs, meta={"topology": meta})


# --------------------------------------------------------------------------- Teil analysieren


def _rects(sections: Mapping[int, Any]) -> dict[int, list[Rect]] | None:
    out: dict[int, list[Rect]] = {}
    for L in sorted(sections):
        rs = [as_rect(g) for g in polygons(sections[L])]
        if any(r is None for r in rs):
            return None
        out[L] = rs  # type: ignore[assignment]
    return out


def _bevel(rects: dict[int, list[Rect]]) -> tuple[Rect, str, dict[int, float]] | None:
    """Abschrägung: eine Insel, gleiche Länge, Dicke nimmt monoton von einer Seite ab."""
    layers = sorted(rects)
    if not layers or any(len(rects[L]) != 1 for L in layers):
        return None
    base = rects[layers[0]][0]
    rs = [rects[L][0] for L in layers]
    if all(r.same(base) for r in rs) or not all(r.same_x(base) for r in rs):
        return None
    for side in ("top", "bottom"):
        fixed_ok = all(
            abs((r.y0 - base.y0) if side == "top" else (r.y1 - base.y1)) <= RECT_TOL_MM for r in rs
        )
        if not fixed_ok:
            continue
        t = {
            L: (r.y1 - base.y0) if side == "top" else (base.y1 - r.y0)
            for L, r in zip(layers, rs, strict=True)
        }
        vals = [t[L] for L in layers]
        if all(b <= a + RECT_TOL_MM for a, b in zip(vals[:-1], vals[1:], strict=True)):
            return base, side, t
    return None


def _split(rects: dict[int, list[Rect]]) -> tuple[Rect, list[Rect], int] | None:
    """Öffnung: Rechteck, ab Schicht k ein oder zwei gleichbleibende Randpfeiler voller Dicke."""
    layers = sorted(rects)
    if len(layers) < 2 or len(rects[layers[0]]) != 1:
        return None
    base = rects[layers[0]][0]
    k = next((L for L in layers if not (len(rects[L]) == 1 and rects[L][0].same(base))), None)
    if k is None or any(L >= k and L not in rects for L in layers):
        return None
    top = rects[k]
    if not 1 <= len(top) <= 2:
        return None
    for L in layers:
        if L >= k and (
            len(rects[L]) != len(top) or not all(a.same(b) for a, b in zip(rects[L], top, strict=True))
        ):
            return None
    for r in top:
        if not r.same_y(base) or r.x0 < base.x0 - RECT_TOL_MM or r.x1 > base.x1 + RECT_TOL_MM:
            return None
        if abs(r.x0 - base.x0) > RECT_TOL_MM and abs(r.x1 - base.x1) > RECT_TOL_MM:
            return None  # Mittelpfeiler: nicht unterstützt
    if len(top) == 2 and not (
        abs(top[0].x0 - base.x0) <= RECT_TOL_MM and abs(top[1].x1 - base.x1) <= RECT_TOL_MM
    ):
        return None
    return base, top, k


def _corner(p: PatternParams) -> float:
    """Eckradius der Rechteckbahnen: mindestens w/2 (kleiner wäre ein M6-Fehler, die Bahnen
    hätten keinen Vorteil davon)."""
    return max(p.corner_radius, p.w / 2.0)


def _plan_bevel(sections, rects, p: PatternParams, base: Rect, side: str, t: dict[int, float]) -> _PartPlan:
    w, rc, eps = p.w, _corner(p), p.eps
    T = base.y1 - base.y0
    frame = Frame(base.x0, base.y0, 1.0, 1.0) if side == "top" else Frame(base.x0, base.y1, 1.0, -1.0)
    yu = fermat_yu(T, w, rc, eps)
    plan = _PartPlan("abschraegung", note=f"Dicke {T:.1f} → {min(t.values()):.1f} mm ({side})")
    done: dict[float, IslandPlan] = {}
    for L, tl in t.items():
        key = round(tl, 3)
        if key not in done:
            pieces = fermat_rect(base.width, T, tl, w, rc, eps, yu, p.delta_mm)
            meta = {"mode": "abschraegung", "side": side, "thickness_mm": round(tl, 2)}
            if not pieces:
                meta["empty"] = "zu dünn für eine Raupe"
            done[key] = _plan(pieces, frame, p, meta)
        plan.islands[(L, 0)] = done[key]
    return plan


def _plan_split(sections, rects, p: PatternParams, base: Rect, top: list[Rect], k: int) -> _PartPlan | None:
    w, rc, eps = p.w, _corner(p), p.eps
    T = base.y1 - base.y0
    W = base.width
    ym_lo, ym_hi = sill_middle_range(T, w)
    ym_req = float(p.get("sill_middle_mm", 0.0) or 0.0) or T / 2.0
    ym = min(max(ym_req, ym_lo), ym_hi)
    left = next((r for r in top if abs(r.x0 - base.x0) <= RECT_TOL_MM), None)
    right = next((r for r in top if abs(r.x1 - base.x1) <= RECT_TOL_MM and r is not left), None)
    fL = Frame(base.x0, base.y0, 1.0, 1.0)
    fR = Frame(base.x1, base.y1, -1.0, -1.0)
    if T < pillar_min_thickness(w, rc) or any(r.width < pillar_min_width(w, rc, eps) for r in top):
        return None
    if left is not None and right is not None:
        a, b = left.x1 - base.x0, right.x0 - base.x0
        if b - a < 2 * w + 1.0:
            return None
        pl_lo = pillar_left(a, T, w, rc, eps, below=True)
        pr_lo = pillar_left(W - b, T, w, rc, eps, below=True)
        pr_in_l = [
            Piece(q.kind, q.shell, np.column_stack([W - q.pts[:, 0], T - q.pts[:, 1]]), q.label)
            for q in pr_lo
        ]
        lower = pl_lo + field_between(a, b, T, w, ym) + reverse_pieces(pr_in_l)
        uppers = [(left, fL, a), (right, fR, W - b)]
        case = "fenster"
    else:
        one = left or right
        assert one is not None
        frame = fL if one is left else fR
        a = one.width
        if W - a < 3 * w + 2 * rc:
            return None
        lower = pillar_left(a, T, w, rc, eps, below=True) + field_to_end(a, W, T, w, rc, eps)
        uppers = [(one, frame, a)]
        fL = frame
        case = "randoeffnung"
    plan = _PartPlan("oeffnung", note=f"{case}: Brüstung bis Schicht {k - 1}, Pfeiler ab Schicht {k}")
    base_meta = {"mode": "oeffnung", "case": case, "split_layer": k}
    sill_meta = {**base_meta, "zone": "bruestung"}
    if case == "fenster":
        sill_meta["sill_middle_mm"] = round(ym, 2)
        if abs(ym - ym_req) > 1e-6:
            sill_meta["note"] = (
                f"Mittellauf {ym_req:.1f} mm auf {ym:.1f} mm begrenzt (zulässig {ym_lo:.1f}…{ym_hi:.1f} mm)"
            )
    sill = _plan(lower, fL, p, sill_meta)
    pillars = [
        (rr, _plan(pillar_left(a, T, w, rc, eps, below=False), fr, p, {**base_meta, "zone": "pfeiler"}))
        for rr, fr, a in uppers
    ]
    for L in sorted(rects):
        if L < k:
            plan.islands[(L, 0)] = sill
            continue
        for i, r in enumerate(rects[L]):
            for rr, pp in pillars:
                if r.same(rr):
                    plan.islands[(L, i)] = pp
    return plan


def _changes(sections: Mapping[int, Any]) -> bool:
    """Ändert sich der Querschnitt zwischen zwei Schichten (mehr als Rundung)?"""
    layers = sorted(sections)
    return any(
        not sections[a].equals_exact(sections[b], 1e-6)
        and sections[a].symmetric_difference(sections[b]).area > 1.0
        for a, b in zip(layers[:-1], layers[1:], strict=True)
    )


def _fingerprint(sections: Mapping[int, Any], p: PatternParams) -> tuple:
    rows = []
    for L in sorted(sections):
        for g in polygons(sections[L]):
            rows.append((L, tuple(round(b, 3) for b in g.bounds), round(g.area, 2), len(g.exterior.coords)))
    return (tuple(rows), tuple(sorted((k, repr(v)) for k, v in p.to_dict().items())))


#: (Identität der Querschnitte, Parameter, Schlüssel) des letzten Aufrufs: `build` wird je Schicht
#: und Insel mit demselben `sections` gerufen; der volle Fingerabdruck kostet O(Schichten)
_LAST_KEY: list[Any] = [None, None, None]


def part_plan(ctx: IslandContext) -> _PartPlan:
    """Plan des ganzen Teils (zwischengespeichert)."""
    ident = tuple((L, id(g)) for L, g in ctx.sections.items())
    if _LAST_KEY[0] == ident and _LAST_KEY[1] == ctx.params:
        key = _LAST_KEY[2]
    else:
        key = _fingerprint(ctx.sections, ctx.params)
        _LAST_KEY[:] = [ident, ctx.params, key]
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    p = ctx.params
    plan = _PartPlan("allgemein")
    rects = _rects(ctx.sections) if p.shells == 2 else None
    if rects is not None:
        bev = _bevel(rects)
        spl = _split(rects) if bev is None else None
        try:
            if bev is not None:
                plan = _plan_bevel(ctx.sections, rects, p, *bev)
            elif spl is not None:
                plan = _plan_split(ctx.sections, rects, p, *spl) or _PartPlan(
                    "allgemein", note="Öffnung zu schmal oder Wand zu dünn für Pfeiler und Brüstungsfeld"
                )
        except ValueError as exc:
            # Sicherheitsnetz: Bahnbausteine passen nicht in den Querschnitt (Maße am Rand der
            # Mindestwerte); lieber allgemein mit Hinweis als ein Abbruch der Planung
            plan = _PartPlan("allgemein", note=f"Bahnbau nicht möglich ({exc}); allgemein geplant")
    if plan.mode == "allgemein" and not plan.note and _changes(ctx.sections):
        # z. B. zwei Fenster (Mittelpfeiler), Sturz im Modul, Öffnung + Schräge: keine passende
        # Betriebsart; jede Schicht für sich, M3 an neuen Kanten meldet die Prüfung
        plan.note = (
            "Querschnittswechsel nicht unterstützt (Mittelpfeiler, Sturz im Modul, Nicht-Rechteck "
            "oder shells ≠ 2); Schichten einzeln geplant"
        )
    _CACHE[key] = plan
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return plan


@pattern(
    "topologie",
    role="full",
    label="Topologie (Öffnungen, Inseln, Laibungsstege)",
    params=PARAMS,
    description="Ein Strang je Insel für allgemeine Querschnitte mit geprüfter Naht; Abschrägungen "
    "als Fermat-Doppelring, der Schicht für Schicht zu U-Formen abbaut; Öffnungen mit Querstegen an "
    "den künftigen Laibungen und Fuge zwischen Brüstungsfeld und Pfeilern (M3 ohne Überhang).",
    layer_invariant=False,
)
def build(ctx: IslandContext) -> IslandPlan:
    plan = part_plan(ctx)
    res = plan.islands.get((ctx.layer, ctx.island))
    if res is None:
        # allgemein: hängt nur von Insel, Teil-Bounding-Box und Parametern ab
        key = (ctx.region.wkb, tuple(round(b, 3) for b in ctx.part_bounds), _fingerprint({}, ctx.params))
        res = _ISLANDS.get(key)
        if res is None:
            res = best_chain(ctx)
            _ISLANDS[key] = res
            while len(_ISLANDS) > 256:
                _ISLANDS.popitem(last=False)
    # Kopie: der Zwischenspeicher wird über Teile hinweg geteilt (Hinweis gehört zum Teil)
    meta = {k: dict(v) if isinstance(v, dict) else v for k, v in res.meta.items()}
    if plan.mode == "allgemein" and plan.note:
        meta.setdefault("topology", {})["note"] = plan.note
    return replace(res, segments=list(res.segments), contacts=list(res.contacts), meta=meta)


def part_preview(
    sections: Mapping[int, Any], params: PatternParams, layer: int, name: str | None = None
) -> dict[str, Any]:
    """Vorschau-Dict wie `preview.preview`, aber für Schicht `layer` eines Teils mit wechselndem
    Querschnitt (Folgeschicht = `layer + 1` des Teils). Für `preview_svg(data=...)`."""
    from roboprint.patterns.metrics import measure
    from roboprint.patterns.plan import plan_pattern
    from roboprint.patterns.preview import _outline_dict, path_to_dict

    paths = plan_pattern(sections, params)
    rep = measure(paths, sections, params, layers=[layer, layer + 1])
    cur = [lp for lp in paths if lp.layer == layer]
    nxt = [lp for lp in paths if lp.layer == layer + 1]
    pm = [m for m in rep.paths if m.layer == layer]
    total = sum(m.path_length_mm for m in pm)
    contacts = [c for m in pm for c in m.contacts]
    radii = [m.min_radius_mm for m in pm if math.isfinite(m.min_radius_mm)]
    return {
        "schema_version": 1,
        "name": name,
        "layer": layer,
        "pattern": {
            "infill": params.infill,
            "outfill": params.outfill,
            "layer_order": params.layer_order,
            "resolved": {"full": "topologie", "outfill": None, "infill": None},
        },
        "params": params.to_dict(),
        "outline": _outline_dict(sections[layer]),
        "paths": [path_to_dict(lp) for lp in cur],
        "next_layer": {"layer": layer + 1, "paths": [path_to_dict(lp) for lp in nxt]},
        "layer_change": next((c for c in rep.layer_changes if c["from"] == layer), None),
        "contacts": [c.to_dict(params.w) for c in contacts],
        "violations": [v.to_dict() for v in rep.violations if v.layer in (layer, layer + 1)],
        "ok": rep.ok,
        "metrics": {
            "path_length_mm": round(total, 2),
            "print_time_s": round(total / params.v_print_mm_s, 2),
            "v_print_mm_s": params.v_print_mm_s,
            "strands": len(cur),
            "material_l_per_m_layer": round(sum(m.material_l_per_m_layer for m in pm), 4),
            "contacts": len(contacts),
            "contact_length_mm": round(sum(c.length_mm for c in contacts), 2),
            "contacts_per_m": round(sum(m.contacts_per_m for m in pm), 2),
            "joint_spacing_mm": [],
            "longest_straight_outer_mm": round(
                max((m.longest_straight_outer_mm for m in pm), default=0.0), 2
            ),
            "min_radius_mm": round(min(radii), 2) if radii else None,
        },
    }


__all__ = ["Rect", "as_rect", "best_chain", "build", "island_lanes", "part_plan", "part_preview"]
