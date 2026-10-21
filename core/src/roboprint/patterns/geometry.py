"""Geometrische Bausteine für Druckmuster (Frame P, mm, nur XY).

Für Musterfamilien gedacht: Offsets mit gerundeten Ecken, Hohlraum und Mittellinienband,
Neu-Abtastung mit Sehnenfehler, Krümmungsradius, geschlossene Ringe mit Bogenlänge (`Loop`),
Kreisbögen, Biarc-Übergänge (zwei tangentenstetige Bögen) und Eckenrundung (`fillet_polyline`).
"""

from __future__ import annotations

import bisect
import math
from typing import Any

import numpy as np
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.polygon import orient

#: Kreisbogen-Auflösung der Offsets (Viertelkreis in 16 Stücke: Sehnenfehler bei r = 15 mm ≈ 0,02 mm)
QUAD_SEGS = 16
#: Abtastung für Abstandsprüfungen
DENSE_MM = 2.0
#: Faktoren auf den Eckradius, falls die volle Rundung die Topologie eines Offsets ändert
RADIUS_STEPS = (1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)


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
    Topologie (Anzahl Teile oder Löcher, z. B. an schmalen Hälsen oder bei einem Ring, der
    schmaler als 2·r ist), wird r schrittweise verkleinert (RADIUS_STEPS, größter passender Radius,
    z. B. Pfeiler 150 mm: innere Schale 60 mm breit → r = 28,5 statt einer scharfen Ecke); erst
    wenn auch r/10 nicht passt, gilt die ungerundete Fläche.
    """
    base = region.buffer(-offset_mm, join_style="round", quad_segs=QUAD_SEGS)
    if corner_radius_mm <= 0 or base.is_empty:
        return base
    sig = _signature(base)
    for k in RADIUS_STEPS:
        r = corner_radius_mm * k
        rounded = region.buffer(-(offset_mm + r), join_style="round", quad_segs=QUAD_SEGS).buffer(
            r, join_style="round", quad_segs=QUAD_SEGS
        )
        if _signature(rounded) == sig:
            return rounded
    return base


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
    seg = np.diff(p, axis=0)
    n = np.maximum(1, np.ceil(np.linalg.norm(seg, axis=1) / max_spacing_mm - 1e-9).astype(int))
    idx = np.repeat(np.arange(len(seg)), n)
    k = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n) + 1
    t = (k / n[idx])[:, None]
    return np.vstack([p[:1], p[idx] + seg[idx] * t])


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


def _greedy_chords(
    p: np.ndarray, s: np.ndarray, forced: np.ndarray, step_mm: float, chord_tol_mm: float
) -> list[int]:
    """Indizes der gierigen Sehnenwahl von `resample_curve`. Reines Python über Listen: Die Stücke
    sind kurz (≤ step_mm), und die Abweichungsprüfung bricht am ersten Punkt über chord_tol ab;
    das ist um ein Mehrfaches schneller als die frühere numpy-Fassung je Kandidat (gleiche Rechnung,
    eingefroren in tests/patterns_resample_reference.py)."""
    xs, ys, sl, fl = p[:, 0].tolist(), p[:, 1].tolist(), s.tolist(), forced.tolist()
    n, nf = len(xs), len(fl)
    out = [0]
    i = fi = 0
    while i < n - 1:
        jmax = bisect.bisect_right(sl, sl[i] + step_mm + 1e-9) - 1
        jmax = min(max(jmax, i + 1), n - 1)
        while fi < nf and fl[fi] <= i:
            fi += 1
        if fi < nf:
            jmax = min(jmax, fl[fi])
        j = jmax
        ax, ay = xs[i], ys[i]
        while j > i + 1 and _chord_exceeds(xs, ys, i, j, ax, ay, chord_tol_mm):
            j -= 1
        out.append(j)
        i = j
    return out


def _chord_exceeds(
    xs: list[float], ys: list[float], i: int, j: int, ax: float, ay: float, tol: float
) -> bool:
    """Liegt ein Punkt i + 1 … j − 1 weiter als `tol` von der Strecke i → j? (Projektion auf die
    Strecke, auf [0, 1] begrenzt, dann der Abstand.)"""
    abx, aby = xs[j] - ax, ys[j] - ay
    L2 = abx * abx + aby * aby
    sqrt = math.sqrt
    if L2 < 1e-18:
        return any(sqrt((xs[m] - ax) ** 2 + (ys[m] - ay) ** 2) > tol for m in range(i + 1, j))
    for m in range(i + 1, j):
        x, y = xs[m], ys[m]
        t = ((x - ax) * abx + (y - ay) * aby) / L2
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        ex, ey = x - (ax + t * abx), y - (ay + t * aby)
        if sqrt(ex * ex + ey * ey) > tol:
            return True
    return False


def resample_curve(
    points: np.ndarray,
    step_mm: float = 20.0,
    chord_tol_mm: float = 0.5,
    closed: bool = False,
    keep_angle_deg: float = 20.0,
) -> np.ndarray:
    """Polylinie neu abtasten: Sehnenfehler ≤ `chord_tol_mm` gegen die Eingabe-Polylinie
    (die Sollkurve, fein abgetastet), Wegpunktabstand ≤ `step_mm`.

    Gierig über die Eingabepunkte: Von jedem gewählten Punkt aus der fernste Eingabepunkt, bis zu
    dem alle Zwischenpunkte ≤ chord_tol von der Sehne liegen und die Bogenlänge ≤ step_mm ist.
    Punkte mit einer Richtungsänderung > `keep_angle_deg` (echte Ecken) bleiben erhalten. Danach
    werden zu lange Sehnen gleichmäßig auf ≤ step_mm unterteilt. Alle Ausgabepunkte liegen auf der
    Eingabe-Polylinie. `closed`: Ausgabe endet mit dem Startpunkt."""
    p = dedupe(points)
    if closed and len(p) > 1 and np.linalg.norm(p[0] - p[-1]) > 1e-9:
        p = np.vstack([p, p[:1]])
    if len(p) < 3:
        return densify(p, step_mm) if len(p) == 2 else p
    corner = _turn_deg(p[:-1] if closed else p, closed) > keep_angle_deg
    if closed:
        corner = np.append(corner, True)
    out = _greedy_chords(p, arc_length(p), np.flatnonzero(corner), step_mm, chord_tol_mm)
    res = densify(p[out], step_mm)
    if closed:
        res[-1] = res[0]
    return res


def curvature_radius(points: np.ndarray, closed: bool = False) -> np.ndarray:
    """Diskreter Krümmungsradius je Punkt (mm): Umkreisradius des Punkts und seiner beiden Nachbarn.

    Für Punkte auf einem Kreis mit Radius R ist das genau R, auch bei ungleichen Abständen. Eine
    scharfe Ecke liefert einen kleinen Wert (90° bei 20-mm-Stücken: 14,1 mm < w/2 = 15 mm; die
    Muster tasten mit step_mm ≤ 20 mm ab). Gerade Stücke und Endpunkte offener Kurven: inf.
    Punktezahl wie `dedupe(points)` (geschlossen: ohne Wiederholung des Startpunkts)."""
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
        rr = np.where(cross > 1e-9 * np.maximum(ab * bc, 1e-12), ab * bc * ca / (2.0 * cross), np.inf)
    # Umkehrpunkt (Spitze, 180°): Radius 0
    back = (np.einsum("ij,ij->i", b - a, c - b) < 0) & (cross <= 1e-9 * np.maximum(ab * bc, 1e-12))
    rr[back] = 0.0
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
        sag = np.where(
            np.isfinite(R) & (R > seg / 2.0), R - np.sqrt(np.maximum(R**2 - (seg / 2.0) ** 2, 0)), 0.0
        )
    return sag


# --------------------------------------------------------------------------- Ringe und Kurven


#: Beinahe-Duplikate eines Rings (mm), die `Loop` entfernt: shapely-Puffer mit Rundung liefern an
#: Bogenstößen gelegentlich zwei Punkte im Abstand weniger µm mit Rückwärtsschritt (Rechteckkerbe,
#: eine Schale: 0,006 mm). Der Knick bliebe beim Neu-Abtasten als „Ecke“ erhalten und gäbe einen
#: falschen M6-Fehler (r = 1,3 mm); 0,02 mm liegt weit unter dem Sehnenfehler 0,5 mm.
LOOP_DEDUPE_MM = 0.02


class Loop:
    """Geschlossener Ring mit Bogenlängen-Parametrisierung s ∈ [0, length)."""

    def __init__(self, ring: np.ndarray):
        p = dedupe(ring, LOOP_DEDUPE_MM)
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

    def points(self, s: np.ndarray) -> np.ndarray:
        """`point` für viele Bogenlängen auf einmal (elementweise dieselbe Rechnung)."""
        s = np.asarray(s, float) % self.length
        k = np.clip(np.searchsorted(self.cum, s, side="right") - 1, 0, len(self.pts) - 2)
        L = self.cum[k + 1] - self.cum[k]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(L > 0, (s - self.cum[k]) / L, 0.0)
        return self.pts[k] + t[:, None] * (self.pts[k + 1] - self.pts[k])

    def tangent(self, s: float, incoming: bool = False) -> np.ndarray:
        """Einheitstangente; an einem Eckpunkt die Richtung des folgenden Stücks
        (`incoming=True`: des ankommenden)."""
        k, _ = self._seg(s - 1e-7 if incoming else s)
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
        # Alle Eckpunkte inkl. des Ringanfangs (cum[0] + k·L): Läuft das Stück über den Ringanfang,
        # muss dessen Eckpunkt erhalten bleiben (sonst wird eine scharfe Ecke zur Diagonale).
        base = self.cum[:-1]
        inner = np.concatenate([base, base + L, base + 2 * L])
        inner = inner[(inner > s0 + 1e-9) & (inner < e - 1e-9)]
        return np.vstack([self.point(s0), self.points(inner), self.point(e)])

    def reversed(self) -> Loop:
        return Loop(self.pts[::-1].copy())


# --------------------------------------------------------------------------- Bögen


def _perp(t: np.ndarray) -> np.ndarray:
    return np.array([-t[1], t[0]])


def _cross(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def arc_points(
    center: np.ndarray,
    radius: float,
    a0: float,
    sweep: float,
    chord_tol_mm: float = 0.5,
    step_mm: float = 20.0,
) -> np.ndarray:
    """Kreisbogen ab Winkel a0 (rad) über `sweep` (rad, Vorzeichen = Drehsinn), Sehnenfehler
    ≤ chord_tol und Punktabstand ≤ step. Erster und letzter Punkt liegen exakt auf dem Bogen."""
    r = abs(radius)
    dphi = math.pi / 2
    if r > chord_tol_mm:
        dphi = min(dphi, 2.0 * math.acos(1.0 - chord_tol_mm / r))
    if r > 0:
        dphi = min(dphi, 2.0 * math.asin(min(1.0, step_mm / (2.0 * r))))
    n = max(1, math.ceil(abs(sweep) / dphi - 1e-9))
    ang = a0 + sweep * np.arange(n + 1) / n
    return np.column_stack([center[0] + r * np.cos(ang), center[1] + r * np.sin(ang)])


def _arc_radius(a: np.ndarray, ta: np.ndarray, b: np.ndarray) -> tuple[float | None, np.ndarray]:
    """Vorzeichenbehafteter Radius des Bogens von a (Richtung ta) nach b (> 0: Mittelpunkt links,
    gegen den Uhrzeigersinn; None: Gerade) und die Normale links von ta."""
    c = b - a
    n = _perp(ta)
    den = 2.0 * float(n @ c)
    if abs(den) < 1e-12 * max(1.0, float(c @ c)):
        return None, n
    return float(c @ c) / den, n


def tangent_arc(
    a: np.ndarray, ta: np.ndarray, b: np.ndarray, chord_tol_mm: float = 0.5, step_mm: float = 20.0
) -> tuple[np.ndarray, float]:
    """Bogen von a (Richtung ta) nach b. Rückgabe (Punkte, Radius; inf für eine Gerade)."""
    rs, n = _arc_radius(a, ta, b)
    if rs is None:
        return densify(np.vstack([a, b]), step_mm), math.inf
    ctr = a + rs * n
    va, vb = a - ctr, b - ctr
    sweep = math.atan2(_cross(va, vb), float(va @ vb))
    if rs > 0 and sweep < 0:
        sweep += 2 * math.pi
    elif rs < 0 and sweep > 0:
        sweep -= 2 * math.pi
    pts = arc_points(ctr, abs(rs), math.atan2(va[1], va[0]), sweep, chord_tol_mm, step_mm)
    pts[0], pts[-1] = a, b
    return pts, abs(rs)


def _biarc_mid(
    p1: np.ndarray, t1: np.ndarray, p2: np.ndarray, t2: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Verbindungspunkt pm des Biarcs und die Einheitstangenten (t1, tm) an seinen Bogenanfängen;
    None, wenn es keinen Biarc gibt."""
    t1 = t1 / np.linalg.norm(t1)
    t2 = t2 / np.linalg.norm(t2)
    v = p2 - p1
    t = t1 + t2
    vv, vt, tt = float(v @ v), float(v @ t), float(t1 @ t2)
    den = 2.0 * (1.0 - tt)
    if abs(den) < 1e-12:
        vt2 = float(v @ t2)
        if abs(vt2) < 1e-12:
            return None
        d = vv / (4.0 * vt2)
    else:
        d = (-vt + math.sqrt(vt * vt + den * vv)) / den
    if not math.isfinite(d) or d <= 1e-9:
        return None
    pm = 0.5 * (p1 + d * t1 + p2 - d * t2)
    tm = pm - (p1 + d * t1)
    if np.linalg.norm(tm) < 1e-12:
        tm = t1
    return t1, pm, tm / np.linalg.norm(tm)


def biarc(
    p1: np.ndarray,
    t1: np.ndarray,
    p2: np.ndarray,
    t2: np.ndarray,
    chord_tol_mm: float = 0.5,
    step_mm: float = 20.0,
) -> tuple[np.ndarray, float] | None:
    """Tangentenstetiger Übergang aus zwei Kreisbögen von p1 (Richtung t1) nach p2 (Richtung t2),
    mit gleich langen Tangentenhenkeln. Zwischen zwei parallelen Geraden im Abstand d mit
    Längsversatz 2·sqrt(R² − (R − d/2)²) sind das genau zwei Bögen mit Radius R (S-Kurve).
    Rückgabe (Punkte, kleinerer Radius) oder None, wenn es keinen Biarc gibt."""
    mid = _biarc_mid(p1, t1, p2, t2)
    if mid is None:
        return None
    t1, pm, tm = mid
    a1, r1 = tangent_arc(p1, t1, pm, chord_tol_mm, step_mm)
    a2, r2 = tangent_arc(pm, tm, p2, chord_tol_mm, step_mm)
    return np.vstack([a1, a2[1:]]), min(r1, r2)


def biarc_radius(p1: np.ndarray, t1: np.ndarray, p2: np.ndarray, t2: np.ndarray) -> float | None:
    """Kleinerer Radius des Biarcs wie `biarc`, ohne Punkte (None, wenn es keinen gibt)."""
    mid = _biarc_mid(p1, t1, p2, t2)
    if mid is None:
        return None
    t1, pm, tm = mid
    r1, _ = _arc_radius(p1, t1, pm)
    r2, _ = _arc_radius(pm, tm, p2)
    return min(math.inf if r1 is None else abs(r1), math.inf if r2 is None else abs(r2))


def fillet_polyline(
    points: np.ndarray,
    radius_mm: float,
    closed: bool = False,
    chord_tol_mm: float = 0.5,
    step_mm: float = 20.0,
    min_turn_deg: float = 1.0,
) -> tuple[np.ndarray, float]:
    """Ecken einer Polylinie mit Radius `radius_mm` runden (Kreisbogen tangential an beide Stücke).

    Reicht ein Stück nicht für die Tangentenlänge r·tan(θ/2), wird der Radius an dieser Ecke so
    verkleinert, dass höchstens die halbe Stücklänge verbraucht wird. Rückgabe (Punkte, kleinster
    tatsächlich verwendeter Radius; inf ohne Ecken). Geschlossen: Ein- und Ausgabe enden am Start."""
    p = dedupe(points)
    if closed and np.linalg.norm(p[0] - p[-1]) < 1e-9:
        p = p[:-1]
    n = len(p)
    if n < 3 or radius_mm <= 0:
        out = np.vstack([p, p[:1]]) if closed else p
        return out, math.inf
    # Alle Ecken auf einmal, bitgleich zur Rechnung Ecke für Ecke: Skalarprodukte über gestapeltes
    # matmul (dieselbe BLAS-Routine wie `u @ v`), elementweise Arithmetik in derselben Reihenfolge,
    # Winkelfunktionen über `math` je Ecke wie in `tangent_arc`/`arc_points`.
    i = np.arange(n) if closed else np.arange(1, n - 1)
    a, b, c = p[i - 1], p[i], p[(i + 1) % n]
    u, v = b - a, c - b
    la, lb = np.sqrt(_rowdot(u, u)), np.sqrt(_rowdot(v, v))
    u, v = u / la[:, None], v / lb[:, None]
    th = np.array([math.acos(x) for x in np.clip(_rowdot(u, v), -1.0, 1.0).tolist()])
    sel = np.array([math.degrees(x) >= min_turn_deg for x in th.tolist()], bool)
    if not np.any(sel):
        out = np.vstack([p, p[:1]]) if closed else p
        return dedupe(out), math.inf
    i, b, u, v = i[sel], b[sel], u[sel], v[sel]
    tl_list: list[float] = []
    rmin = math.inf
    for t, x, y in zip(th[sel].tolist(), la[sel].tolist(), lb[sel].tolist(), strict=True):
        tan_h = math.tan(t / 2.0)
        tl = min(radius_mm * tan_h, 0.5 * x, 0.5 * y)
        rmin = min(rmin, tl / tan_h)
        tl_list.append(tl)
    tl_arr = np.array(tl_list)[:, None]
    arcs, sizes = _corner_arcs(b - tl_arr * u, u, b + tl_arr * v, chord_tol_mm, step_mm)
    # Zusammensetzen: Ecke i → Bogen, sonst der Punkt selbst
    counts = np.ones(n, int)
    counts[i] = sizes
    res = np.empty((int(counts.sum()), 2))
    start = np.concatenate([[0], np.cumsum(counts)[:-1]])
    plain = np.ones(n, bool)
    plain[i] = False
    res[start[plain]] = p[plain]
    res[np.repeat(start[i], sizes) + _ramp(sizes)] = arcs
    if closed:
        res = np.vstack([res, res[:1]])
    return dedupe(res), rmin


def _rowdot(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Zeilenweise `a[k] @ b[k]`, bitgleich zum Einzelaufruf (gestapeltes matmul)."""
    return np.matmul(a[:, None, :], b[:, :, None])[:, 0, 0]


def _ramp(sizes: np.ndarray) -> np.ndarray:
    """0, 1, …, sizes[0] − 1, 0, 1, …, sizes[1] − 1, …"""
    return np.arange(int(sizes.sum())) - np.repeat(np.cumsum(sizes) - sizes, sizes)


def _corner_arcs(
    a: np.ndarray, ta: np.ndarray, b: np.ndarray, chord_tol_mm: float, step_mm: float
) -> tuple[np.ndarray, np.ndarray]:
    """`tangent_arc(a[k], ta[k], b[k])[0]` für alle k (bitgleich); Rückgabe (alle Punkte
    hintereinander, Punktzahl je k). Entartete Bögen (Geraden) laufen über `tangent_arc`."""
    c = b - a
    nrm = np.column_stack([-ta[:, 1], ta[:, 0]])
    den = 2.0 * _rowdot(nrm, c)
    cc = _rowdot(c, c)
    if np.any(np.abs(den) < 1e-12 * np.maximum(1.0, cc)):
        pieces = [tangent_arc(a[k], ta[k], b[k], chord_tol_mm, step_mm)[0] for k in range(len(a))]
        return np.vstack(pieces), np.array([len(q) for q in pieces], int)
    rs = cc / den
    ctr = a + rs[:, None] * nrm
    va, vb = a - ctr, b - ctr
    cross = va[:, 0] * vb[:, 1] - va[:, 1] * vb[:, 0]
    a0_l, sw_l, r_l, cnt_l = [], [], [], []
    for cr, dt, r_s, x, y in zip(
        cross.tolist(),
        _rowdot(va, vb).tolist(),
        rs.tolist(),
        va[:, 0].tolist(),
        va[:, 1].tolist(),
        strict=True,
    ):
        sweep = math.atan2(cr, dt)
        if r_s > 0 and sweep < 0:
            sweep += 2 * math.pi
        elif r_s < 0 and sweep > 0:
            sweep -= 2 * math.pi
        r = abs(r_s)
        dphi = math.pi / 2
        if r > chord_tol_mm:
            dphi = min(dphi, 2.0 * math.acos(1.0 - chord_tol_mm / r))
        if r > 0:
            dphi = min(dphi, 2.0 * math.asin(min(1.0, step_mm / (2.0 * r))))
        a0_l.append(math.atan2(y, x))
        sw_l.append(sweep)
        r_l.append(r)
        cnt_l.append(max(1, math.ceil(abs(sweep) / dphi - 1e-9)))
    cnt = np.array(cnt_l, int)
    sizes = cnt + 1
    rep = np.repeat(np.arange(len(cnt)), sizes)
    ang = np.array(a0_l)[rep] + np.array(sw_l)[rep] * _ramp(sizes) / cnt[rep]
    r_rep = np.array(r_l)[rep]
    pts = np.empty((len(rep), 2))
    pts[:, 0] = ctr[rep, 0] + r_rep * np.cos(ang)
    pts[:, 1] = ctr[rep, 1] + r_rep * np.sin(ang)
    last = np.cumsum(sizes) - 1
    pts[last - cnt] = a  # Anfang und Ende exakt (wie `tangent_arc`)
    pts[last] = b
    return pts, sizes
