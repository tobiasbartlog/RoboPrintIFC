"""Geometrische Bausteine für Druckmuster (Frame P, mm, nur XY).

Für Musterfamilien gedacht: Offsets mit gerundeten Ecken, Hohlraum und Mittellinienband,
Neu-Abtastung mit Sehnenfehler, Krümmungsradius, geschlossene Ringe mit Bogenlänge (`Loop`),
kubische Übergangskurven und die Abstandsprüfung entlang eines Pfads (M2).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.polygon import orient

#: Kreisbogen-Auflösung der Offsets (Viertelkreis in 16 Stücke: Sehnenfehler bei r = 15 mm ≈ 0,02 mm)
QUAD_SEGS = 16
#: Abtastung für Abstandsprüfungen
DENSE_MM = 2.0


def polygons(geom: Any) -> list[Polygon]:
    """Nicht leere Polygone einer Geometrie, sortiert nach (x_min, y_min) der Bounding-Box."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        out = [geom]
    elif isinstance(geom, MultiPolygon | GeometryCollection):
        out = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
    else:
        out = []
    return sorted((p for p in out if p.area > 1e-6), key=lambda p: (p.bounds[0], p.bounds[1]))


def _signature(geom: Any) -> list[int]:
    return [len(p.interiors) for p in polygons(geom)]


def offset_region(region: Any, offset_mm: float, corner_radius_mm: float = 0.0) -> Any:
    """Nach innen versetzte Fläche, deren Rand die Mittellinie einer Schale ist.

    Erosion um `offset_mm` mit runder Fuge: konkave Ecken (Laibungen, L-Ecken, Löcher) werden
    konzentrische Bögen mit Radius `offset_mm` um die Ecke. Konvexe Ecken werden mit
    `corner_radius_mm` gerundet (Erosion um offset + r, Dilatation um r). Ändert die Rundung die
    Topologie (Anzahl Teile oder Löcher, z. B. an schmalen Hälsen), gilt die ungerundete Fläche.
    """
    base = region.buffer(-offset_mm, join_style="round", quad_segs=QUAD_SEGS)
    if corner_radius_mm <= 0 or base.is_empty:
        return base
    r = corner_radius_mm
    rounded = region.buffer(-(offset_mm + r), join_style="round", quad_segs=QUAD_SEGS).buffer(
        r, join_style="round", quad_segs=QUAD_SEGS
    )
    return rounded if _signature(rounded) == _signature(base) else base


def offset_ring(region: Any, offset_mm: float, corner_radius_mm: float = 0.0) -> list[tuple[str, np.ndarray]]:
    """Ringe der Mittellinie im Abstand `offset_mm` innerhalb von `region`.

    Rückgabe: [("exterior" | "hole", (n, 2) geschlossen)], Außenkonturen gegen den Uhrzeigersinn,
    Löcher im Uhrzeigersinn, Teile sortiert nach (x_min, y_min)."""
    out: list[tuple[str, np.ndarray]] = []
    for sub in polygons(offset_region(region, offset_mm, corner_radius_mm)):
        sub = orient(sub, sign=1.0)
        out.append(("exterior", np.asarray(sub.exterior.coords, float)))
        out.extend(("hole", np.asarray(h.coords, float)) for h in sub.interiors)
    return out


def cavity(region: Any, shells: int, bead_width_mm: float) -> Any:
    """Hohlraum innerhalb der innersten Schale (Raupenkante), also region ⊖ shells·w.
    S1 (600 × 200, w = 30, 2 Schalen): 480 × 80 mm."""
    return region.buffer(-shells * bead_width_mm, join_style="round", quad_segs=QUAD_SEGS)


def centerline_band(region: Any, shells: int, bead_width_mm: float, overlap_mm: float = 0.0) -> Any:
    """Fläche für Infill-Mittellinien, deren Raupe die innerste Schale höchstens berührt
    (`overlap_mm` = gewollte Überlappung 0 … ε·w, M7). S1: 450 × 50 mm bei overlap 0."""
    d = shells * bead_width_mm + bead_width_mm / 2.0 - overlap_mm
    return region.buffer(-d, join_style="round", quad_segs=QUAD_SEGS)


# --------------------------------------------------------------------------- Polylinien


def dedupe(points: np.ndarray, tol: float = 1e-9) -> np.ndarray:
    """Aufeinanderfolgende doppelte Punkte entfernen."""
    p = np.asarray(points, float)
    if len(p) < 2:
        return p
    keep = np.ones(len(p), bool)
    keep[1:] = np.linalg.norm(np.diff(p, axis=0), axis=1) > tol
    return p[keep]


def arc_length(points: np.ndarray) -> np.ndarray:
    """Kumulierte Bogenlänge (n,), beginnend bei 0."""
    p = np.asarray(points, float)
    if len(p) == 0:
        return np.zeros(0)
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def densify(points: np.ndarray, max_spacing_mm: float = DENSE_MM) -> np.ndarray:
    """Alle Punkte behalten, Stücke länger als `max_spacing_mm` gleichmäßig unterteilen."""
    p = dedupe(points)
    if len(p) < 2:
        return p
    out = [p[:1]]
    for a, b in zip(p[:-1], p[1:], strict=True):
        n = max(1, math.ceil(np.linalg.norm(b - a) / max_spacing_mm - 1e-9))
        t = np.arange(1, n + 1)[:, None] / n
        out.append(a + (b - a) * t)
    return np.vstack(out)


def _turn_deg(p: np.ndarray, closed: bool) -> np.ndarray:
    """Richtungsänderung je Punkt in Grad (Endpunkte offener Kurven: 0)."""
    n = len(p)
    turn = np.zeros(n)
    if n < 3:
        return turn
    if closed:
        prev = np.roll(p, 1, axis=0)
        nxt = np.roll(p, -1, axis=0)
        idx = np.arange(n)
    else:
        prev, nxt, idx = p[:-2], p[2:], np.arange(1, n - 1)
    cur = p[idx]
    a, b = cur - prev, nxt - cur
    na, nb = np.linalg.norm(a, axis=1), np.linalg.norm(b, axis=1)
    ok = (na > 1e-12) & (nb > 1e-12)
    cos = np.ones(len(idx))
    cos[ok] = np.clip(np.einsum("ij,ij->i", a[ok], b[ok]) / (na[ok] * nb[ok]), -1.0, 1.0)
    turn[idx] = np.degrees(np.arccos(cos))
    return turn


def _seg_dev(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Größter Abstand der Punkte zur Strecke a-b."""
    if len(pts) == 0:
        return 0.0
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-18:
        return float(np.linalg.norm(pts - a, axis=1).max())
    t = np.clip((pts - a) @ ab / L2, 0.0, 1.0)
    return float(np.linalg.norm(pts - (a + t[:, None] * ab), axis=1).max())


def resample_curve(
    points: np.ndarray,
    step_mm: float = 20.0,
    chord_tol_mm: float = 0.5,
    closed: bool = False,
    keep_angle_deg: float = 20.0,
) -> np.ndarray:
    """Polylinie neu abtasten: Sehnenfehler ≤ `chord_tol_mm` gegen die Eingabe-Polylinie
    (die Sollkurve, fein abgetastet), Wegpunktabstand ≤ `step_mm`.

    Punkte mit einer Richtungsänderung > `keep_angle_deg` (echte Ecken) bleiben erhalten.
    Gierig: von jedem gewählten Punkt aus der fernste Punkt, der beide Grenzen einhält.
    `closed`: Ausgabe endet mit dem Startpunkt."""
    p = dedupe(points)
    if closed and len(p) > 1 and np.linalg.norm(p[0] - p[-1]) > 1e-9:
        p = np.vstack([p, p[:1]])
    if len(p) < 3:
        return densify(p, step_mm) if len(p) == 2 else p
    corner = _turn_deg(p[:-1] if closed else p, closed) > keep_angle_deg
    if closed:
        corner = np.append(corner, True)
    # fein unterteilen, Ecken markieren
    fine_spacing = min(step_mm / 4.0, 1.0)
    parts, flags = [p[:1]], [np.array([True])]
    for k, (a, b) in enumerate(zip(p[:-1], p[1:], strict=True)):
        n = max(1, math.ceil(np.linalg.norm(b - a) / fine_spacing - 1e-9))
        t = np.arange(1, n + 1)[:, None] / n
        parts.append(a + (b - a) * t)
        f = np.zeros(n, bool)
        f[-1] = bool(corner[k + 1])
        flags.append(f)
    d = np.vstack(parts)
    forced = np.flatnonzero(np.concatenate(flags))
    s = arc_length(d)
    n = len(d)
    out = [0]
    i = 0
    while i < n - 1:
        jmax = int(np.searchsorted(s, s[i] + step_mm + 1e-9, side="right")) - 1
        jmax = min(max(jmax, i + 1), n - 1)
        f = forced[np.searchsorted(forced, i, side="right") :]
        if len(f):
            jmax = min(jmax, int(f[0]))
        j = jmax
        while j > i + 1 and _seg_dev(d[i + 1 : j], d[i], d[j]) > chord_tol_mm:
            j -= 1
        out.append(j)
        i = j
    res = d[out]
    if closed:
        res[-1] = res[0]
    return res


def curvature_radius(points: np.ndarray, closed: bool = False) -> np.ndarray:
    """Krümmungsradius je Punkt als Umkreisradius des Punkts und seiner beiden Nachbarn (mm).

    Gerade Stücke und Endpunkte offener Kurven: inf. Für eine abgetastete Kurve mit Punkten auf der
    Sollkurve ist das der Radius der Sollkurve; eine scharfe Ecke liefert einen kleinen Wert."""
    p = dedupe(points)
    if closed and len(p) > 1 and np.linalg.norm(p[0] - p[-1]) < 1e-9:
        p = p[:-1]
    n = len(p)
    r = np.full(n, np.inf)
    if n < 3:
        return r
    if closed:
        a, b, c = np.roll(p, 1, axis=0), p, np.roll(p, -1, axis=0)
        idx = np.arange(n)
    else:
        a, b, c = p[:-2], p[1:-1], p[2:]
        idx = np.arange(1, n - 1)
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    cross = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        rr = np.where(cross > 1e-9, ab * bc * ca / (2.0 * cross), np.inf)
    r[idx] = rr
    return r


def chord_error_estimate(points: np.ndarray, closed: bool = False) -> np.ndarray:
    """Geschätzter Sehnenfehler je Stück: Pfeilhöhe des Kreises durch die Nachbarpunkte
    (Radius = größerer der beiden Endpunkt-Radien; gerade Stücke 0)."""
    p = dedupe(points)
    if closed and len(p) > 1 and np.linalg.norm(p[0] - p[-1]) < 1e-9:
        p = np.vstack([p[:-1], p[:1]])
        r = curvature_radius(p, closed=True)
        r = np.append(r, r[0])
    else:
        r = curvature_radius(p, closed=False)
    if len(p) < 2:
        return np.zeros(0)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    R = np.maximum(r[:-1], r[1:])
    with np.errstate(invalid="ignore"):
        sag = np.where(np.isfinite(R) & (R > seg / 2.0), R - np.sqrt(np.maximum(R**2 - (seg / 2.0) ** 2, 0)), 0.0)
    return sag


def min_clearance(points: np.ndarray, arc: np.ndarray, first: int, sep_mm: float, radius_mm: float) -> tuple[float, int]:
    """Kleinster Abstand zwischen Punktpaaren (i < j, j ≥ first), die entlang des Pfads mehr als
    `sep_mm` auseinanderliegen (M2), gesucht bis `radius_mm`.

    Rückgabe (Abstand, kleinstes j mit Abstand < radius_mm) bzw. (inf, -1). Punkte verschiedener
    Pfade bekommen einen großen Bogenlängen-Versatz, dann zählen alle ihre Paare."""
    if len(points) < 2:
        return math.inf, -1
    tree = cKDTree(points)
    pairs = tree.query_pairs(radius_mm, output_type="ndarray")
    if len(pairs) == 0:
        return math.inf, -1
    i, j = pairs.min(axis=1), pairs.max(axis=1)
    m = (j >= first) & (np.abs(arc[j] - arc[i]) > sep_mm)
    if not np.any(m):
        return math.inf, -1
    i, j = i[m], j[m]
    d = np.linalg.norm(points[i] - points[j], axis=1)
    return float(d.min()), int(j.min())


# --------------------------------------------------------------------------- Ringe und Kurven


class Loop:
    """Geschlossener Ring mit Bogenlängen-Parametrisierung s ∈ [0, length)."""

    def __init__(self, ring: np.ndarray):
        p = dedupe(ring)
        if np.linalg.norm(p[0] - p[-1]) > 1e-9:
            p = np.vstack([p, p[:1]])
        self.pts = p
        self.cum = arc_length(p)
        self.length = float(self.cum[-1])

    def _seg(self, s: float) -> tuple[int, float]:
        s = s % self.length
        k = int(np.clip(np.searchsorted(self.cum, s, side="right") - 1, 0, len(self.pts) - 2))
        L = self.cum[k + 1] - self.cum[k]
        return k, (s - self.cum[k]) / L if L > 0 else 0.0

    def point(self, s: float) -> np.ndarray:
        k, t = self._seg(s)
        return self.pts[k] + t * (self.pts[k + 1] - self.pts[k])

    def tangent(self, s: float) -> np.ndarray:
        """Einheitstangente; an einem Eckpunkt die Richtung des folgenden Stücks."""
        k, _ = self._seg(s)
        v = self.pts[k + 1] - self.pts[k]
        return v / np.linalg.norm(v)

    def project(self, q: np.ndarray) -> float:
        """Bogenlänge des nächstgelegenen Ringpunkts zu q."""
        a, b = self.pts[:-1], self.pts[1:]
        ab = b - a
        L2 = np.einsum("ij,ij->i", ab, ab)
        t = np.clip(np.einsum("ij,ij->i", q - a, ab) / np.where(L2 > 0, L2, 1), 0, 1)
        d = np.linalg.norm(a + t[:, None] * ab - q, axis=1)
        k = int(np.argmin(d))
        return float(self.cum[k] + t[k] * np.sqrt(L2[k]))

    def sub(self, s0: float, s1: float) -> np.ndarray:
        """Polylinie vorwärts von s0 nach s1 (mod length; s1 ≤ s0 heißt: über den Ringanfang)."""
        L = self.length
        s0 %= L
        e = s1 % L
        if e <= s0 + 1e-9:
            e += L
        inner = np.concatenate([self.cum[1:-1], self.cum[1:-1] + L, self.cum[1:-1] + 2 * L])
        inner = inner[(inner > s0 + 1e-9) & (inner < e - 1e-9)]
        return np.vstack([self.point(s0), *[self.point(x) for x in inner], self.point(e)])

    def reversed(self) -> Loop:
        return Loop(self.pts[::-1].copy())


def cubic_transition(a: np.ndarray, ta: np.ndarray, b: np.ndarray, tb: np.ndarray, n: int = 64) -> tuple[np.ndarray, float]:
    """Kubische Bézierkurve von a (Richtung ta) nach b (Richtung tb), tangentenstetig (G1).

    Henkellänge wie beim Kreisbogen gleichen Sehnen- und Drehwinkels, (4/3)·tan(θ/4)·R; ist die
    Lage symmetrisch, ist die Kurve (fast) ein Kreisbogen. Rückgabe: Punkte (n, 2) und kleinster
    Krümmungsradius (analytisch)."""
    c = float(np.linalg.norm(b - a))
    cosang = float(np.clip(ta @ tb, -1.0, 1.0))
    th = math.acos(cosang)
    if th < 1e-3:
        h = c / 3.0
    else:
        R = c / (2.0 * math.sin(th / 2.0)) if math.sin(th / 2.0) > 1e-9 else c
        h = min((4.0 / 3.0) * math.tan(th / 4.0) * R, c)
    p0, p1, p2, p3 = a, a + h * ta, b - h * tb, b
    t = np.linspace(0.0, 1.0, n)[:, None]
    pts = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t**2 * p2 + t**3 * p3
    tt = np.linspace(0.0, 1.0, 4 * n)[:, None]
    d1 = 3 * (1 - tt) ** 2 * (p1 - p0) + 6 * (1 - tt) * tt * (p2 - p1) + 3 * tt**2 * (p3 - p2)
    d2 = 6 * (1 - tt) * (p2 - 2 * p1 + p0) + 6 * tt * (p3 - 2 * p2 + p1)
    cross = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
    speed = np.linalg.norm(d1, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rad = np.where(cross > 1e-12, speed**3 / cross, np.inf)
    return pts, float(rad.min())
