"""Musterregeln M1–M7 messen (systemseitig, ohne Roboter) und Kennzahlen je Schichtpfad.

Das ist die Selbstprüfung des Kerns. Die unabhängige Prüfung macht `verify_muster/` (Orakel).

Messverfahren (alle Längen mm, w = Strangbreite, ε = params.eps):
- Abtastung: Jeder Pfad wird inkl. Verbindern auf ≤ 2 mm verdichtet (Bogenlänge s je Punkt).
- **M1 Durchgehend**: höchstens ein LayerPath je (Schicht, Insel) und nicht mehr Pfade als Inseln;
  jeder Verbinder ≤ `link_max_mm` (sonst „Lücke im Strang“).
- **M2 Kreuzungsfrei**: Punktpaare mit Bogenlängenabstand > 2·w (bei geschlossenem Zug zyklisch)
  und Mittellinienabstand d < (1 − ε)·w sind ein Fehler (Kreuzung bzw. Fahrt über eine liegende
  Raupe), dazu ein exakter Selbstschnitttest. d ∈ [(1 − ε)·w, w + contact_tol] ist ein **gewollter
  Kontakt** und kein Verstoß; `contact_tol` (0,5 mm) deckt den Sehnenfehler der Polylinie ab.
- **M3 Überhangfrei**: Raupenfläche (Mittellinie ⊕ w/2) von Schicht L + 1 minus (Raupenfläche von
  L ⊕ δ); Restfläche > 1 mm² ist ein Fehler.
- **M4 Senkrechter Schichtwechsel**: waagrechter Abstand Ende L → Anfang L + 1 ≤ 0,5 mm. Ändert sich
  der Querschnitt oder die Inselzahl (`restart`), ist es ein dokumentierter Neubeginn, kein Fehler.
  Liegt Anfang oder Ende eines Pfads so, dass die Raupe eine Außen- oder Stoßfläche berührt
  (layout.face_clearance ≤ 0), gibt es eine Warnung (Nahtlage).
- **M5 Im Teil**: Raupenfläche minus (Querschnitt ⊕ 1 mm); Restfläche > 1 mm² ist ein Fehler.
- **M6 Druckbar gekrümmt**: diskreter Krümmungsradius (Umkreis dreier Folgepunkte) < w/2 ist ein
  Fehler, < w eine Warnung (Ziel), beide mit 5 % Messtoleranz (RADIUS_TOL). Geschätzter
  Sehnenfehler > chord_tol + 0,05 mm: Warnung.
- **M7 Kontakt**: Kontaktzonen (zusammenhängende Läufe von Kontaktpaaren) mit Lage, Länge, Art
  (`joint` Außenfeld an Außenfeld, `node` Steg/Gurt an Steg/Gurt, sonst `shell`; ein deklarierter
  Kontakt des Musters im Umkreis w gibt die Art vor), Anzahl und Länge je Meter Wand.

Kennzahlen: Pfadlänge, Druckzeit bei v_print, Material (Liter je m Wand und Schicht, Liter je m²
Wandansicht), Zellen (Hohlräume des Querschnitts, Fläche ≥ w²/2, mit Spannweite), Kontaktlängen,
Fugenlagen und Fugenabstand, längste gerade ungestützte Außenstrecke (gerade Läufe der Segmente
`outer`/`outfill`, geteilt an Punkten mit Kontakt zu `web`/`infill`), kleinster Radius.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point

from roboprint.patterns.geometry import chord_error_estimate, curvature_radius, densify, polygons
from roboprint.patterns.layout import face_clearance
from roboprint.patterns.plan import part_bounds
from roboprint.patterns.types import CROSS_KINDS, OUTER_KINDS, Contact, LayerPath, PatternParams

DENSE_MM = 2.0
#: Restfläche, ab der M3/M5 als verletzt gelten (mm²)
AREA_TOL_MM2 = 1.0
#: M4: größter waagrechter Abstand Ende L → Anfang L + 1 (mm)
VERTICAL_TOL_MM = 0.5
#: Messtoleranz des diskreten Radius: Die Muster tasten Bögen mit Sehnenfehler ≤ 0,5 mm ab; die
#: Punkte liegen dann teils auf Sehnen, der Umkreisradius fällt bei R = w bis ≈ 0,96·R.
RADIUS_TOL = 0.05


@dataclass
class Violation:
    """Ein Regelverstoß mit Ort (Frame P). `severity`: `error` (Regel verletzt) oder `warn` (Ziel)."""

    rule: str
    severity: str
    layer: int
    island: int | None
    at: tuple[float, float] | None
    value: float | None
    limit: float | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        r = lambda v: None if v is None else round(float(v), 3)  # noqa: E731
        return {
            "rule": self.rule,
            "severity": self.severity,
            "layer": self.layer,
            "island": self.island,
            "at": None if self.at is None else [r(self.at[0]), r(self.at[1])],
            "value": r(self.value),
            "limit": r(self.limit),
            "message": self.message,
        }


@dataclass
class PathMetrics:
    """Kennzahlen eines Schichtpfads (eine Schicht, eine Insel)."""

    layer: int
    island: int
    direction: str
    path_length_mm: float
    print_time_s: float
    n_segments: int
    connectors_mm: list[float]
    min_clearance_mm: float
    min_radius_mm: float
    max_chord_error_mm: float
    contacts: list[Contact]
    longest_straight_outer_mm: float
    longest_straight_outer_at: tuple[float, float] | None
    joint_x_mm: list[float]
    joint_spacing_mm: list[float]
    cells: list[dict[str, float]]
    material_l_per_m_layer: float
    material_l_per_m2: float
    wall_length_mm: float
    start: tuple[float, float]
    end: tuple[float, float]
    w: float = 30.0

    @property
    def contact_length_mm(self) -> float:
        return float(sum(c.length_mm for c in self.contacts))

    @property
    def contacts_per_m(self) -> float:
        return len(self.contacts) / max(self.wall_length_mm / 1000.0, 1e-9)

    def to_dict(self) -> dict[str, Any]:
        rr = lambda v, n=2: None if v is None or not math.isfinite(v) else round(float(v), n)  # noqa: E731
        by_kind: dict[str, dict[str, float]] = {}
        for c in self.contacts:
            k = by_kind.setdefault(c.kind, {"count": 0, "length_mm": 0.0})
            k["count"] += 1
            k["length_mm"] = round(k["length_mm"] + c.length_mm, 2)
        return {
            "layer": self.layer,
            "island": self.island,
            "direction": self.direction,
            "path_length_mm": rr(self.path_length_mm),
            "print_time_s": rr(self.print_time_s),
            "n_segments": self.n_segments,
            "connectors_mm": [rr(c) for c in self.connectors_mm],
            "min_clearance_mm": rr(self.min_clearance_mm),
            "min_radius_mm": rr(self.min_radius_mm),
            "max_chord_error_mm": rr(self.max_chord_error_mm, 3),
            "contacts": len(self.contacts),
            "contacts_by_kind": by_kind,
            "contact_length_mm": rr(self.contact_length_mm),
            "contacts_per_m": rr(self.contacts_per_m),
            "contact_lengths_mm": [rr(c.length_mm) for c in self.contacts],
            "longest_straight_outer_mm": rr(self.longest_straight_outer_mm),
            "longest_straight_outer_at": None
            if self.longest_straight_outer_at is None
            else [rr(self.longest_straight_outer_at[0]), rr(self.longest_straight_outer_at[1])],
            "joint_x_mm": [rr(x) for x in self.joint_x_mm],
            "joint_spacing_mm": [rr(x) for x in self.joint_spacing_mm],
            "cells": self.cells,
            "n_cells": len(self.cells),
            "max_cell_area_mm2": rr(max((c["area_mm2"] for c in self.cells), default=0.0), 1),
            "max_cell_span_mm": rr(max((c["span_mm"] for c in self.cells), default=0.0), 1),
            "material_l_per_m_layer": rr(self.material_l_per_m_layer, 4),
            "material_l_per_m2": rr(self.material_l_per_m2, 3),
            "start": [rr(self.start[0]), rr(self.start[1])],
            "end": [rr(self.end[0]), rr(self.end[1])],
        }


@dataclass
class PatternReport:
    """Ergebnis von `measure`: Kennzahlen je Pfad, Verstöße, Schichtwechsel."""

    paths: list[PathMetrics]
    violations: list[Violation]
    layer_changes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def rules_violated(self) -> set[str]:
        return {v.rule for v in self.errors}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "paths": [m.to_dict() for m in self.paths],
            "violations": [v.to_dict() for v in self.violations],
            "layer_changes": self.layer_changes,
        }


# --------------------------------------------------------------------------- Abtastung


def sample_path(path: LayerPath, spacing: float = DENSE_MM) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Dichte Punkte (n, 2), Bogenlänge (n,) und Segmentindex (n,) inkl. Verbinder
    (Verbinderpunkte gehören zum folgenden Segment)."""
    pts: list[np.ndarray] = []
    idx: list[np.ndarray] = []
    prev = None
    for k, s in enumerate(path.segments):
        poly = s.points if prev is None else np.vstack([prev, s.points])
        d = densify(poly, spacing)
        if prev is not None:
            d = d[1:]
        pts.append(d)
        idx.append(np.full(len(d), k))
        prev = s.points[-1]
    p = np.vstack(pts)
    seg = np.concatenate(idx)
    keep = np.ones(len(p), bool)
    keep[1:] = np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-9
    p, seg = p[keep], seg[keep]
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    return p, arc, seg


def bead_area(path: LayerPath, w: float) -> Any:
    """Raupenfläche: Mittellinie ⊕ w/2 (runde Enden)."""
    pl = path.polyline()
    if len(pl) < 2:
        return Point(pl[0]).buffer(w / 2.0)
    return LineString(pl).buffer(w / 2.0, quad_segs=8)


def _runs(order_vals: np.ndarray, gap: float) -> list[np.ndarray]:
    """Indizes (in sortierter Reihenfolge) in Läufe teilen, wo der Wert um mehr als `gap` springt."""
    if len(order_vals) == 0:
        return []
    cut = np.flatnonzero(np.diff(order_vals) > gap) + 1
    return np.split(np.arange(len(order_vals)), cut)


def _contact_kind(ka: str, kb: str) -> str:
    if ka == "outfill" and kb == "outfill":
        return "joint"
    if ka in CROSS_KINDS and kb in CROSS_KINDS:
        return "node"
    return "shell"


# --------------------------------------------------------------------------- je Pfad


def measure_path(
    path: LayerPath,
    section: Any,
    params: PatternParams,
    bounds: tuple[float, float, float, float] | None = None,
) -> tuple[PathMetrics, list[Violation]]:
    """M1 (Verbinder), M2, M4 (Nahtlage), M5, M6, M7 und Kennzahlen für einen Schichtpfad."""
    p = params
    w, eps = p.w, p.eps
    bounds = bounds or tuple(section.bounds)
    L, isl = path.layer, path.island
    viol: list[Violation] = []
    pts, arc, seg = sample_path(path)
    total = float(arc[-1])
    closed = path.closed
    kinds = [s.kind for s in path.segments]

    # M1: Verbinder
    conns = [float(np.linalg.norm(b - a)) for a, b in path.connectors()]
    for (a, b), c in zip(path.connectors(), conns, strict=True):
        if c > p.link_max_mm + 1e-9:
            viol.append(
                Violation(
                    "M1",
                    "error",
                    L,
                    isl,
                    tuple((a + b) / 2),
                    c,
                    p.link_max_mm,
                    "Lücke im Strang: Verbinder länger als link_max_mm",
                )
            )

    # M2 / M7: Paare
    tree = cKDTree(pts)
    pairs = tree.query_pairs(w + p.contact_tol_mm, output_type="ndarray")
    min_clear = math.inf
    contacts: list[Contact] = []
    if len(pairs):
        i, j = pairs.min(axis=1), pairs.max(axis=1)
        sep = np.abs(arc[j] - arc[i])
        if closed:
            sep = np.minimum(sep, total - sep)
        m = sep > 2.0 * w
        i, j = i[m], j[m]
        d = np.linalg.norm(pts[i] - pts[j], axis=1)
        if len(d):
            min_clear = float(d.min())
        bad = d < (1.0 - eps) * w
        if np.any(bad):
            bi, bj, bd = i[bad], j[bad], d[bad]
            o = np.argsort(arc[bi])
            for run in _runs(arc[bi][o], 3 * DENSE_MM):
                k = o[run][int(np.argmin(bd[o[run]]))]
                at = (pts[bi[k]] + pts[bj[k]]) / 2
                viol.append(
                    Violation(
                        "M2",
                        "error",
                        L,
                        isl,
                        tuple(at),
                        float(bd[k]),
                        (1 - eps) * w,
                        "Kreuzung oder Fahrt über liegende Raupe (Abstand < (1−ε)·w)",
                    )
                )
        ok = ~bad
        contacts = _contact_zones(path, pts, arc, seg, i[ok], j[ok], d[ok], kinds, w)
    if not LineString(path.polyline()).is_simple and not any(v.rule == "M2" for v in viol):
        viol.append(Violation("M2", "error", L, isl, tuple(path.start), 0.0, (1 - eps) * w, "Selbstschnitt"))

    # M4: Nahtlage (Anfang/Ende)
    ends = [path.start] if closed else [path.start, path.end]
    clr = face_clearance(np.array(ends), section, bounds, w)
    for e, c in zip(ends, clr, strict=True):
        if c <= 0.0:
            viol.append(
                Violation(
                    "M4", "warn", L, isl, tuple(e), float(c), 0.0, "Naht berührt Außen- oder Stoßfläche"
                )
            )

    # M5: im Teil
    beads = bead_area(path, w)
    out = beads.difference(section.buffer(1.0))
    if out.area > AREA_TOL_MM2:
        big = max(polygons(out), key=lambda g: g.area, default=out)
        viol.append(
            Violation(
                "M5",
                "error",
                L,
                isl,
                tuple(big.centroid.coords[0]),
                float(out.area),
                AREA_TOL_MM2,
                "Raupe außerhalb des Querschnitts ⊕ 1 mm (Fläche in mm²)",
            )
        )

    # M6: Krümmung und Sehnenfehler
    pl = path.polyline()
    pl_cl = pl[:-1] if closed else pl
    rad = curvature_radius(pl, closed=closed)
    min_r = float(rad.min()) if len(rad) else math.inf
    hard, target = (1 - RADIUS_TOL) * w / 2.0, (1 - RADIUS_TOL) * w
    for lim, sev, msg in (
        (hard, "error", "Krümmungsradius < w/2"),
        (target, "warn", "Krümmungsradius < w (Ziel)"),
    ):
        lo = np.flatnonzero(rad < lim)
        if sev == "warn":
            lo = lo[rad[lo] >= hard]
        for run in _runs(lo.astype(float), 1.5):
            k = lo[run][int(np.argmin(rad[lo[run]]))]
            viol.append(Violation("M6", sev, L, isl, tuple(pl_cl[k]), float(rad[k]), lim, msg))
    sag = chord_error_estimate(pl, closed=closed)
    max_sag = float(sag.max()) if len(sag) else 0.0
    if max_sag > p.chord_tol_mm + 0.05:
        k = int(np.argmax(sag))
        viol.append(
            Violation(
                "M6",
                "warn",
                L,
                isl,
                tuple(pl[min(k, len(pl) - 1)]),
                max_sag,
                p.chord_tol_mm,
                "geschätzter Sehnenfehler > chord_tol",
            )
        )

    # Kennzahlen
    wall_len = max(bounds[2] - bounds[0], 1e-9)
    straight, straight_at = _longest_unsupported(path, pts, seg, w + p.contact_tol_mm)
    joints = sorted(c.at[0] for c in contacts if c.kind == "joint")
    ymid = 0.5 * (bounds[1] + bounds[3])
    spacing: list[float] = []
    for side in (-1, 1):
        xs = sorted(c.at[0] for c in contacts if c.kind == "joint" and (c.at[1] - ymid) * side > 0)
        spacing.extend(float(b - a) for a, b in zip(xs[:-1], xs[1:], strict=True))
    cells = []
    for g in polygons(section.difference(beads)):
        if g.area >= w * w / 2.0:
            mrr = np.asarray(g.minimum_rotated_rectangle.exterior.coords)
            sides = np.linalg.norm(np.diff(mrr, axis=0), axis=1)
            cells.append(
                {
                    "area_mm2": round(float(g.area), 1),
                    "span_mm": round(float(sides.max()), 1),
                    "at": [round(float(g.centroid.x), 1), round(float(g.centroid.y), 1)],
                }
            )
    vol = total * w * p.layer_height_mm
    met = PathMetrics(
        layer=L,
        island=isl,
        direction=path.direction,
        path_length_mm=total,
        print_time_s=total / p.v_print_mm_s,
        n_segments=len(path.segments),
        connectors_mm=conns,
        min_clearance_mm=min_clear,
        min_radius_mm=min_r,
        max_chord_error_mm=max_sag,
        contacts=contacts,
        longest_straight_outer_mm=straight,
        longest_straight_outer_at=straight_at,
        joint_x_mm=joints,
        joint_spacing_mm=spacing,
        cells=cells,
        material_l_per_m_layer=vol / 1e6 / (wall_len / 1000.0),
        material_l_per_m2=total * w / wall_len,
        wall_length_mm=wall_len,
        start=tuple(map(float, path.start)),
        end=tuple(map(float, path.end)),
        w=w,
    )
    return met, viol


def _contact_zones(
    path: LayerPath,
    pts: np.ndarray,
    arc: np.ndarray,
    seg: np.ndarray,
    i: np.ndarray,
    j: np.ndarray,
    d: np.ndarray,
    kinds: list[str],
    w: float,
) -> list[Contact]:
    zones: list[Contact] = []
    if len(i) == 0:
        return zones
    key = seg[i] * 100000 + seg[j]
    for kv in np.unique(key):
        sel = np.flatnonzero(key == kv)
        o = sel[np.argsort(arc[i[sel]])]
        cut = (np.diff(arc[i[o]]) > 3 * DENSE_MM) | (np.abs(np.diff(arc[j[o]])) > w)
        for run in np.split(o, np.flatnonzero(cut) + 1):
            k = run[int(np.argmin(d[run]))]
            si, sj = int(seg[i[k]]), int(seg[j[k]])
            mid = run[len(run) // 2]
            at = (pts[i[mid]] + pts[j[mid]]) / 2
            length = float(arc[i[run]].max() - arc[i[run]].min()) + DENSE_MM
            kind = _contact_kind(kinds[si], kinds[sj])
            for c in path.contacts:
                if np.hypot(c.at[0] - at[0], c.at[1] - at[1]) <= w:
                    kind = c.kind
                    break
            zones.append(Contact(kind, tuple(at), length, (min(si, sj), max(si, sj)), float(d[k])))
    zones.sort(key=lambda c: (c.at[0], c.at[1]))
    return zones


def _longest_unsupported(
    path: LayerPath, pts: np.ndarray, seg: np.ndarray, reach: float
) -> tuple[float, tuple[float, float] | None]:
    cross = np.isin(seg, [k for k, s in enumerate(path.segments) if s.kind in CROSS_KINDS])
    tree = cKDTree(pts[cross]) if np.any(cross) else None
    best, best_at = 0.0, None
    for s in path.segments:
        if s.kind not in OUTER_KINDS:
            continue
        p = s.points
        v = np.diff(p, axis=0)
        ang = np.arctan2(v[:, 1], v[:, 0])
        turn = np.abs((np.diff(ang) + np.pi) % (2 * np.pi) - np.pi)
        breaks = np.flatnonzero(np.degrees(turn) > 1.0) + 1
        for a, b in zip(np.r_[0, breaks], np.r_[breaks, len(p) - 1], strict=True):
            if b <= a:
                continue
            dense = densify(p[a : b + 1], DENSE_MM)
            sup = np.zeros(len(dense), bool)
            sup[0] = sup[-1] = True
            if tree is not None:
                sup |= np.isfinite(tree.query(dense, distance_upper_bound=reach)[0])
            s_arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
            idx = np.flatnonzero(sup)
            gaps = np.diff(s_arc[idx])
            if len(gaps) and gaps.max() > best:
                k = int(np.argmax(gaps))
                best = float(gaps[k])
                best_at = tuple(map(float, (dense[idx[k]] + dense[idx[k + 1]]) / 2))
    return best, best_at


# --------------------------------------------------------------------------- ganzes Teil


def measure(
    paths: Sequence[LayerPath],
    sections: Mapping[int, Any],
    params: PatternParams | None = None,
    layers: Sequence[int] | None = None,
) -> PatternReport:
    """M1–M7 für alle Schichtpfade (`layers` schränkt die je Pfad gemessenen Schichten ein; M3/M4
    werden dann nur für Übergänge innerhalb dieser Schichten geprüft)."""
    p = params or PatternParams()
    w = p.w
    bounds = part_bounds(sections)
    sel = None if layers is None else set(layers)
    metrics: list[PathMetrics] = []
    viol: list[Violation] = []
    by_layer: dict[int, list[LayerPath]] = {}
    for lp in paths:
        by_layer.setdefault(lp.layer, []).append(lp)
    beads: dict[int, Any] = {}
    for L in sorted(by_layer):
        if sel is not None and L not in sel:
            continue
        lps = by_layer[L]
        n_isl = len(polygons(sections.get(L)))
        seen: dict[int, int] = {}
        for lp in lps:
            seen[lp.island] = seen.get(lp.island, 0) + 1
        if len(lps) > max(n_isl, 1) or any(n > 1 for n in seen.values()):
            viol.append(
                Violation(
                    "M1",
                    "error",
                    L,
                    None,
                    tuple(lps[0].start),
                    float(len(lps)),
                    float(n_isl),
                    "mehr Stränge als Inseln in der Schicht",
                )
            )
        for lp in lps:
            m, v = measure_path(lp, sections[L], p, bounds)
            metrics.append(m)
            viol.extend(v)
        beads[L] = shapely.union_all([bead_area(lp, w) for lp in lps])
    changes: list[dict[str, Any]] = []
    order = sorted(beads)
    for La, Lb in zip(order[:-1], order[1:], strict=True):
        if Lb != La + 1:
            continue
        diff = beads[Lb].difference(beads[La].buffer(p.delta_mm))
        if diff.area > AREA_TOL_MM2:
            big = max(polygons(diff), key=lambda g: g.area, default=diff)
            viol.append(
                Violation(
                    "M3",
                    "error",
                    Lb,
                    None,
                    tuple(big.centroid.coords[0]),
                    float(diff.area),
                    AREA_TOL_MM2,
                    "Überhang: Raupe von L+1 nicht auf Raupe von L ⊕ δ (mm²)",
                )
            )
        a, b = by_layer[La][-1], by_layer[Lb][0]
        dist = float(np.linalg.norm(b.start - a.end))
        restart = b.restart
        status = "vertical" if dist <= VERTICAL_TOL_MM else ("restart" if restart else "diagonal")
        changes.append({"from": La, "to": Lb, "distance_mm": round(dist, 3), "status": status})
        if status == "diagonal":
            viol.append(
                Violation(
                    "M4",
                    "error",
                    Lb,
                    b.island,
                    tuple(a.end),
                    dist,
                    VERTICAL_TOL_MM,
                    "Schichtwechsel nicht senkrecht (Ende L → Anfang L+1)",
                )
            )
    return PatternReport(metrics, viol, changes)
