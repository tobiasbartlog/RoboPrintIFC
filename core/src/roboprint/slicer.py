"""Schichten, Schalenringe, Ringstart, An- und Abfahrt eines Teils.

Alles in Frame P (mm). Schicht L belegt z_P in [L*h, (L+1)*h]; geschnitten wird bei
(L+0,5)*h, der TCP liegt beim Druck auf z_P = (L+1)*h.

Festlegungen
- Schale s liegt (s+0,5)*w innerhalb des Materials (Offset mit Mitre-Join, damit Ecken
  erhalten bleiben). Löcher wachsen dabei in die Öffnung, die Ringe liegen im Material.
- Schmale/kleine Querschnitte (Giebelspitzen, Keile): deckt der Schalenbereich (Querschnitt
  minus um shells*w nach innen gepuffertes Inneres) mit w/2 gepufferten Ringen weniger als
  COVER_TARGET ab, kommen geschlossene Zusatzringe auf kleineren Innen-Offsets dazu (bis knapp
  unter den Inkreisradius = schmaler Ring um die Mittellinie). Sie zählen als nächste Schalen.
- Umlaufsinn von oben gesehen: Außenkonturen gegen den Uhrzeigersinn, Löcher im Uhrzeigersinn.
- Ringstart: Eckpunkt, der der Bounding-Box-Ecke (x_min, y_min) des Rings am nächsten liegt
  (Gleichstand: kleinstes x, dann y). Die Naht liegt damit in jeder Schicht an derselben Stelle.
- Neu-Abtastung: alle Eckpunkte bleiben, Segmente länger als step_mm werden gleichmäßig
  unterteilt (Abstand <= step_mm). Geschlossen: letzter Punkt == erster.
- Reihenfolge je Schicht: Schale 0 vor Schale 1 usw. (außen vor innen); innerhalb einer Schale
  nächster Nachbar (Startpunkt zum Ende des vorigen Rings, Schichtanfang: zum Ende der
  Vorschicht). `kind`: outer (Außenkontur, Schale 0), inner (Außenkontur, Schale > 0), hole.
- An-/Abfahrt: Punkte approach_mm senkrecht über Ringstart bzw. -ende (Ringende == Ringstart).
- Düse: +Z_T = -Z_W. Bei psi = 0 gilt X_T = +X_W, Y_T = -Y_W, Quaternion (w,x,y,z) = (0,1,0,0).
- Verbinder (SPEC §5.3, Nutzerentscheidung 20.10.2026): `link_next` an Ring r erlaubt eine gedruckte
  Gerade vom letzten Wegpunkt von r zum ersten Wegpunkt von r + 1, wenn link_max_mm > 0, Ring r + 1
  in Schicht L(r) oder L(r) + 1 liegt, die waagrechte Länge <= link_max_mm ist und die waagrechte
  Projektion im Querschnitt der Schicht L(r + 1) liegt, beim Schichtwechsel auch in dem von L(r)
  (Toleranz LINK_TOL_MM). Ein Verbinder führt so nie über eine Öffnung oder zwischen zwei Inseln.
  Die Reihenfolge der Ringe bleibt dieselbe; ob der Planer den Verbinder nutzt, zeigt die Trajektorie.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from roboprint.contracts import Ring, Toolpath

#: Düsenachse nach unten, X_T = X_W (psi = 0): Drehung um 180 deg um X_W.
NOZZLE_DOWN_QUAT = (0.0, 1.0, 0.0, 0.0)
MITRE_LIMIT = 2.0
#: Abdeckungsziel je Schicht (Prüfer: >= 95 %), mit Reserve für die Planer-Abtastung.
COVER_TARGET = 0.97
MAX_FILL_RINGS = 3
#: Verbinder: waagrechte Projektion im Querschnitt bis auf diese Toleranz (Rundung der Offsets)
LINK_TOL_MM = 0.01


@dataclass(frozen=True)
class SliceParams:
    layer_height_mm: float = 10.0
    bead_width_mm: float = 30.0
    shells: int = 2
    step_mm: float = 20.0
    approach_mm: float = 20.0
    link_max_mm: float = 60.0  # längster Verbinder (SPEC §5.3); <= 0: keine Verbinder


@dataclass
class SlicedRing:
    layer: int
    shell: int
    kind: str  # outer | inner | hole
    points: np.ndarray  # (n, 3) in P, geschlossen
    approach: np.ndarray  # (3,) approach_mm über Start
    retract: np.ndarray  # (3,) approach_mm über Ende
    link_next: bool = False  # Verbinder zum nächsten Ring erlaubt (SPEC §5.3)


@dataclass
class SlicedPart:
    layer_height_mm: float
    bead_width_mm: float
    n_layers: int
    rings: list[SlicedRing] = field(default_factory=list)


def _section_polygons(mesh: Any, z: float) -> list[Polygon]:
    """Querschnitt bei z als Polygone (Außenkontur + Löcher), Frame P."""
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return []
    planar, _ = sec.to_2D(to_2D=np.eye(4))
    return [p.simplify(1e-6) for p in planar.polygons_full if p.area > 1e-6]


def _polys(geom: Any) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if not g.is_empty]
    return []


def _resample(coords: np.ndarray, step: float) -> np.ndarray:
    """Eckpunkte erhalten, Segmente gleichmäßig auf Abstand <= step unterteilen."""
    out = [coords[0]]
    for a, b in zip(coords[:-1], coords[1:], strict=True):
        n = max(1, math.ceil(np.linalg.norm(b - a) / step - 1e-9))
        for k in range(1, n + 1):
            out.append(a + (b - a) * (k / n))
    return np.array(out)


def _rotate_start(coords: np.ndarray) -> np.ndarray:
    """Ring (geschlossen) so rotieren, dass er an der Ecke nächst (x_min, y_min) beginnt."""
    pts = coords[:-1]
    corner = pts.min(axis=0)
    d = np.linalg.norm(pts - corner, axis=1)
    best = np.flatnonzero(d <= d.min() + 1e-9)
    i = min(best, key=lambda k: (round(pts[k][0], 6), round(pts[k][1], 6)))
    rot = np.vstack([pts[i:], pts[:i]])
    return np.vstack([rot, rot[:1]])


def _offset_rings(poly: Polygon, off: float) -> list[tuple[str, np.ndarray]]:
    """Ringe des um off nach innen versetzten Polygons: ("exterior"|"hole", Koordinaten)."""
    out: list[tuple[str, np.ndarray]] = []
    for sub in _polys(poly.buffer(-off, join_style="mitre", mitre_limit=MITRE_LIMIT)):
        sub = orient(sub, sign=1.0)  # Außen CCW, Löcher CW
        out.append(("exterior", np.array(sub.exterior.coords)))
        out.extend(("hole", np.array(h.coords)) for h in sub.interiors)
    return out


def _coverage(region: Any, rings: list[np.ndarray], w: float) -> float:
    """Anteil des Schalenbereichs, den die mit w/2 gepufferten Ringe abdecken (Prüfer-Metrik)."""
    if region.area <= 0:
        return 1.0
    if not rings:
        return 0.0
    beads = unary_union([LineString(c).buffer(w / 2.0) for c in rings])
    return float(beads.intersection(region).area / region.area)


def _inradius(poly: Polygon, hi: float) -> float:
    """Größter Innen-Offset (Bisektion), bei dem das Polygon nicht verschwindet."""
    lo = 0.0
    if not poly.buffer(-hi, join_style="mitre", mitre_limit=MITRE_LIMIT).is_empty:
        return hi
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if poly.buffer(-mid, join_style="mitre", mitre_limit=MITRE_LIMIT).is_empty:
            hi = mid
        else:
            lo = mid
    return lo


def _fill_rings(poly: Polygon, done: list[np.ndarray], p: SliceParams) -> list[list[tuple[str, np.ndarray]]]:
    """Zusatzringe für schmale/kleine Querschnitte, bis der Schalenbereich zu >= COVER_TARGET
    abgedeckt ist. Kandidaten sind Innen-Offsets zwischen 0 und dem Inkreisradius; ein Ring
    knapp unter dem Inkreisradius ist ein schmaler geschlossener Ring um die Mittellinie.
    Gewählt wird der Kandidat mit der größten Abdeckung (bei Gleichstand der äußerste)."""
    w = p.bead_width_mm
    region = poly.difference(poly.buffer(-p.shells * w, join_style="mitre"))
    rings = list(done)
    cov = _coverage(region, rings, w)
    if cov >= COVER_TARGET:
        return []
    r_max = _inradius(poly, (p.shells + 0.5) * w)
    if r_max <= 0:
        return []
    cands = [r_max * k / 16.0 for k in range(1, 16)] + [0.98 * r_max]
    extra: list[list[tuple[str, np.ndarray]]] = []
    for _ in range(MAX_FILL_RINGS):
        best, best_cov = None, cov
        for d in cands:
            rs = _offset_rings(poly, d)
            c = _coverage(region, rings + [x for _, x in rs], w) if rs else -1.0
            if c > best_cov + 1e-4:
                best, best_cov = rs, c
        if best is None:
            break
        extra.append(best)
        rings += [x for _, x in best]
        cov = best_cov
        if cov >= COVER_TARGET:
            break
    return extra


def _layer_rings(polys: list[Polygon], layer: int, p: SliceParams) -> list[tuple[int, str, np.ndarray]]:
    res: list[tuple[int, str, np.ndarray]] = []
    for poly in polys:
        n_shell, done = 0, []
        for s in range(p.shells):
            rs = _offset_rings(poly, (s + 0.5) * p.bead_width_mm)
            if not rs:
                break
            n_shell = s + 1
            for typ, c in rs:
                res.append((s, "hole" if typ == "hole" else ("outer" if s == 0 else "inner"), c))
                done.append(c)
        for k, rs in enumerate(_fill_rings(poly, done, p)):
            s = n_shell + k
            res.extend((s, "hole" if typ == "hole" else ("outer" if s == 0 else "inner"), c) for typ, c in rs)
    return res


def slice_part(part_mesh_P: Any, params: SliceParams | None = None) -> SlicedPart:
    """Zerlegt ein Teil (Frame P) in Schichten und Ringe."""
    p = params or SliceParams()
    h = p.layer_height_mm
    height = float(part_mesh_P.bounds[1][2])
    n = int(round(height / h))
    out = SlicedPart(h, p.bead_width_mm, n)
    cur: np.ndarray | None = None
    sections: dict[int, Any] = {}
    for layer in range(n):
        polys = _section_polygons(part_mesh_P, (layer + 0.5) * h)
        sections[layer] = unary_union(polys) if polys else Polygon()
        raw = _layer_rings(polys, layer, p)
        z = (layer + 1) * h
        for s in range(max((sh for sh, _, _ in raw), default=-1) + 1):
            todo = []
            for sh, kind, c in raw:
                if sh == s:
                    c = _rotate_start(c)
                    c = _resample(c, p.step_mm)
                    todo.append((kind, np.column_stack([c, np.full(len(c), z)])))
            while todo:
                if cur is None:
                    j = 0
                else:
                    j = int(np.argmin([np.linalg.norm(t[1][0, :2] - cur) for t in todo]))
                kind, pts = todo.pop(j)
                up = np.array([0.0, 0.0, p.approach_mm])
                out.rings.append(SlicedRing(layer, s, kind, pts, pts[0] + up, pts[-1] + up))
                cur = pts[-1, :2]
    for a, b in zip(out.rings[:-1], out.rings[1:], strict=True):
        a.link_next = link_allowed(a, b, sections, p.link_max_mm)
    return out


def link_allowed(a: SlicedRing, b: SlicedRing, sections: dict[int, Any], link_max_mm: float) -> bool:
    """Darf Ring `a` über einen Verbinder in den folgenden Ring `b` übergehen (SPEC §5.3)?

    `sections[L]`: Querschnitt der Schicht L in P (Vereinigung der Polygone bei (L+0,5)*h)."""
    if link_max_mm <= 0 or b.layer not in (a.layer, a.layer + 1):
        return False
    pa, pb = a.points[-1, :2], b.points[0, :2]
    if float(np.linalg.norm(pb - pa)) > link_max_mm + 1e-9:
        return False
    geom = LineString([pa, pb]) if np.linalg.norm(pb - pa) > 1e-9 else Point(pa)
    for L in {a.layer, b.layer}:
        sec = sections.get(L)
        if sec is None or sec.is_empty or not sec.buffer(LINK_TOL_MM).covers(geom):
            return False
    return True


def to_toolpath(sliced: SlicedPart, T_WP: np.ndarray, part_id: str) -> Toolpath:
    """Ringe als TCP-Posen in W (Düsenachse -Z_W, psi = 0: X_T = X_W)."""
    T = np.asarray(T_WP, float)
    pts_h = lambda a: (T[:3, :3] @ a.T).T + T[:3, 3]  # noqa: E731
    rings = []
    for r in sliced.rings:
        w = pts_h(r.points)
        poses = [[*map(float, x), *NOZZLE_DOWN_QUAT] for x in w]
        poses[-1] = list(poses[0])
        rings.append(
            Ring(
                layer=r.layer, shell=r.shell, kind=r.kind, closed=True, link_next=r.link_next, waypoints=poses
            )
        )
    return Toolpath(part_id=part_id, layer_height_mm=sliced.layer_height_mm,
                    bead_width_mm=sliced.bead_width_mm, rings=rings)
