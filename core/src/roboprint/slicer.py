"""Schichten, Schalenringe, Ringstart, An- und Abfahrt eines Teils.

Alles in Frame P (mm). Schicht L belegt z_P in [L*h, (L+1)*h]; geschnitten wird bei
(L+0,5)*h, der TCP liegt beim Druck auf z_P = (L+1)*h.

Festlegungen
- Schale s liegt (s+0,5)*w innerhalb des Materials (Offset mit Mitre-Join, damit Ecken
  erhalten bleiben). Löcher wachsen dabei in die Öffnung, die Ringe liegen im Material.
- Umlaufsinn von oben gesehen: Außenkonturen gegen den Uhrzeigersinn, Löcher im Uhrzeigersinn.
- Ringstart: Eckpunkt, der der Bounding-Box-Ecke (x_min, y_min) des Rings am nächsten liegt
  (Gleichstand: kleinstes x, dann y). Die Naht liegt damit in jeder Schicht an derselben Stelle.
- Neu-Abtastung: alle Eckpunkte bleiben, Segmente länger als step_mm werden gleichmäßig
  unterteilt (Abstand <= step_mm). Geschlossen: letzter Punkt == erster.
- Reihenfolge je Schicht: Schale 0 vor Schale 1 usw. (außen vor innen); innerhalb einer Schale
  nächster Nachbar (Startpunkt zum Ende des vorigen Rings, Schichtanfang: zum Ende der
  Vorschicht). `kind`: outer (Außenkontur, Schale 0), inner (Außenkontur, Schale > 0), hole.
- An-/Abfahrt: Punkte 20 mm senkrecht über Ringstart bzw. -ende (Ringende == Ringstart).
- Düse: +Z_T = -Z_W. Bei psi = 0 gilt X_T = +X_W, Y_T = -Y_W, Quaternion (w,x,y,z) = (0,1,0,0).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient

from roboprint.contracts import Ring, Toolpath

#: Düsenachse nach unten, X_T = X_W (psi = 0): Drehung um 180 deg um X_W.
NOZZLE_DOWN_QUAT = (0.0, 1.0, 0.0, 0.0)
MITRE_LIMIT = 2.0


@dataclass(frozen=True)
class SliceParams:
    layer_height_mm: float = 10.0
    bead_width_mm: float = 30.0
    shells: int = 2
    step_mm: float = 20.0
    approach_mm: float = 20.0


@dataclass
class SlicedRing:
    layer: int
    shell: int
    kind: str  # outer | inner | hole
    points: np.ndarray  # (n, 3) in P, geschlossen
    approach: np.ndarray  # (3,) 20 mm über Start
    retract: np.ndarray  # (3,) 20 mm über Ende


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


def _layer_rings(polys: list[Polygon], layer: int, p: SliceParams) -> list[tuple[int, str, np.ndarray]]:
    res: list[tuple[int, str, np.ndarray]] = []
    for s in range(p.shells):
        off = (s + 0.5) * p.bead_width_mm
        for poly in polys:
            for sub in _polys(poly.buffer(-off, join_style="mitre", mitre_limit=MITRE_LIMIT)):
                sub = orient(sub, sign=1.0)  # Außen CCW, Löcher CW
                res.append((s, "outer" if s == 0 else "inner", np.array(sub.exterior.coords)))
                for h in sub.interiors:
                    res.append((s, "hole", np.array(h.coords)))
    return res


def slice_part(part_mesh_P: Any, params: SliceParams | None = None) -> SlicedPart:
    """Zerlegt ein Teil (Frame P) in Schichten und Ringe."""
    p = params or SliceParams()
    h = p.layer_height_mm
    height = float(part_mesh_P.bounds[1][2])
    n = int(round(height / h))
    out = SlicedPart(h, p.bead_width_mm, n)
    cur: np.ndarray | None = None
    for layer in range(n):
        polys = _section_polygons(part_mesh_P, (layer + 0.5) * h)
        raw = _layer_rings(polys, layer, p)
        z = (layer + 1) * h
        for s in range(p.shells):
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
    return out


def to_toolpath(sliced: SlicedPart, T_WP: np.ndarray, part_id: str) -> Toolpath:
    """Ringe als TCP-Posen in W (Düsenachse -Z_W, psi = 0: X_T = X_W)."""
    T = np.asarray(T_WP, float)
    pts_h = lambda a: (T[:3, :3] @ a.T).T + T[:3, 3]  # noqa: E731
    rings = []
    for r in sliced.rings:
        w = pts_h(r.points)
        poses = [[*map(float, x), *NOZZLE_DOWN_QUAT] for x in w]
        poses[-1] = list(poses[0])
        rings.append(Ring(layer=r.layer, shell=r.shell, kind=r.kind, closed=True, waypoints=poses))
    return Toolpath(part_id=part_id, layer_height_mm=sliced.layer_height_mm,
                    bead_width_mm=sliced.bead_width_mm, rings=rings)
