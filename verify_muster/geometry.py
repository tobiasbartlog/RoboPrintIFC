"""Eigene Geometrie des Muster-Orakels: Querschnitte, Schichtpfade, Bogenlaenge, Kruemmung.

Alles in Frame P (Teil), mm. Ein **Schichtpfad** ist eine Folge von Elementen in Druckreihenfolge:
die Ringe einer Schicht, die mit `link_next` verbunden sind, und dazwischen die Verbinder (Gerade vom
letzten zum ersten Wegpunkt, ARTEFAKT-FORMAT). Ein Ring, dessen erster und letzter Wegpunkt
zusammenfallen, ist geschlossen; sein Schliesspunkt ist ein Knoten des Pfads (dort beruehrt sich der
Pfad gewollt selbst).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
import trimesh
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

EMPTY = Polygon()
CLOSE_TOL = 0.5  # mm, erster = letzter Wegpunkt -> geschlossen
MIN_ISLAND_AREA = 1.0  # mm², kleinere Schnittflaechen gelten als numerischer Rest


# ---------------------------------------------------------------- Querschnitt


def section(mesh: trimesh.Trimesh, z: float):
    """Querschnitt des Solids bei Hoehe z (Frame P) als shapely-(Multi)Polygon in xy."""
    try:
        sec = mesh.section(plane_origin=[0.0, 0.0, float(z)], plane_normal=[0.0, 0.0, 1.0])
    except Exception:  # noqa: BLE001 - trimesh wirft bei entarteten Schnitten
        sec = None
    if sec is None:
        return EMPTY
    T = np.eye(4)
    T[2, 3] = -float(z)
    to_2d = getattr(sec, "to_2D", None) or sec.to_planar
    planar, _ = to_2d(to_2D=T, check=False)
    polys = [p for p in planar.polygons_full if p is not None and p.area > 0]
    region = EMPTY
    for p in polys:  # even-odd, falls verschachtelte Konturen getrennt kommen
        region = region.symmetric_difference(p)
    return shapely.make_valid(region)


def islands(region) -> list:
    """Zusammenhaengende Teile eines Querschnitts (Polygone mit Loechern), groesste zuerst."""
    if region.is_empty:
        return []
    geoms = list(getattr(region, "geoms", [region]))
    polys = []
    for g in geoms:
        if g.geom_type == "Polygon":
            polys.append(g)
        elif g.geom_type == "MultiPolygon":
            polys.extend(g.geoms)
    polys = [p for p in polys if p.area >= MIN_ISLAND_AREA]
    return sorted(polys, key=lambda p: -p.area)


# ---------------------------------------------------------------- Polylinien


def arclen(pts: np.ndarray) -> np.ndarray:
    if len(pts) == 0:
        return np.zeros(0)
    d = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(d)])


def densify(pts: np.ndarray, step: float) -> np.ndarray:
    """Polylinie mit allen Originalpunkten, Segmente in Stuecke <= step geteilt."""
    pts = np.asarray(pts, float)
    if len(pts) < 2:
        return pts.copy()
    out = [pts[:1]]
    for a, b in zip(pts[:-1], pts[1:], strict=True):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        t = (np.arange(1, n + 1) / n)[:, None]
        out.append(a + t * (b - a))
    return np.vstack(out)


def resample(pts: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Gleichabstaendige Abtastung nach Bogenlaenge: (Punkte, Bogenlaenge)."""
    s = arclen(pts)
    if len(pts) < 2 or s[-1] <= 0:
        return np.asarray(pts, float)[:1], np.zeros(min(1, len(pts)))
    n = max(2, int(np.ceil(s[-1] / step)) + 1)
    t = np.linspace(0.0, s[-1], n)
    keep = np.concatenate([[True], np.diff(s) > 1e-12])
    s_u, p_u = s[keep], np.asarray(pts, float)[keep]
    out = np.column_stack([np.interp(t, s_u, p_u[:, k]) for k in range(p_u.shape[1])])
    return out, t


# ---------------------------------------------------------------- Schichtpfad


@dataclass
class Element:
    """Ring (ring >= 0) oder Verbinder (ring = -1, `link_to` = Index des folgenden Rings)."""

    ring: int
    kind: str
    xy: np.ndarray
    closed: bool
    link_to: int = -1


@dataclass
class LayerPath:
    """Ein Schichtpfad: Elemente in Druckreihenfolge und dichte Abtastung mit Graph-Koordinaten."""

    layer: int
    rings: list[int]
    elements: list[Element]
    step: float
    pts: np.ndarray = field(default=None)  # (n, 2) dichte Punkte
    s: np.ndarray = field(default=None)  # Bogenlaenge entlang des Pfads
    elem: np.ndarray = field(default=None)  # Element je Punkt
    c: np.ndarray = field(default=None)  # Bogenlaenge mit geschlossenen Ringen auf 0 gestaucht
    o: np.ndarray = field(default=None)  # Abstand zum Schliesspunkt (nur geschlossene Ringe)
    e_closed: np.ndarray = field(default=None)
    e_len: np.ndarray = field(default=None)
    e_s0: np.ndarray = field(default=None)
    cyclic: bool = False  # Pfad endet am Startpunkt (geschlossener Zug aus offenen Segmenten)
    c_total: float = 0.0  # Gesamtlaenge in c-Koordinaten

    @property
    def length(self) -> float:
        return float(self.e_len.sum()) if self.e_len is not None else 0.0

    def polyline(self) -> np.ndarray:
        """Zusammenhaengende Mittellinie (Verbinder enthalten), doppelte Punkte entfernt."""
        parts = [e.xy for e in self.elements if len(e.xy)]
        if not parts:
            return np.zeros((0, 2))
        p = np.vstack(parts)
        keep = np.concatenate([[True], np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-9])
        return p[keep]

    def ring_at(self, i: int) -> int:
        e = self.elements[int(self.elem[i])]
        return e.ring if e.ring >= 0 else e.link_to


def build_path(layer: int, ring_ids: list[int], rings_xy: dict[int, np.ndarray], kinds: dict[int, str],
               step: float) -> LayerPath:
    """Schichtpfad aus Ringen (Druckreihenfolge) mit Verbindern; dichte Abtastung mit Schrittweite step."""
    elements: list[Element] = []
    for k, r in enumerate(ring_ids):
        xy = np.asarray(rings_xy[r], float)
        if k > 0:
            prev = elements[-1].xy[-1]
            elements.append(Element(-1, "link", np.vstack([prev, xy[0]]), False, link_to=r))
        closed = len(xy) >= 3 and np.linalg.norm(xy[0] - xy[-1]) <= CLOSE_TOL
        elements.append(Element(r, kinds[r], xy, closed))
    P = LayerPath(layer, list(ring_ids), elements, step)
    pts, s_all, el, cc, oo = [], [], [], [], []
    e_len, e_s0, e_closed = [], [], []
    s_off = 0.0
    c_off = 0.0
    for j, e in enumerate(elements):
        d = densify(e.xy, step) if len(e.xy) >= 2 else e.xy
        s_loc = arclen(d)
        L = float(s_loc[-1]) if len(s_loc) else 0.0
        e_len.append(L)
        e_s0.append(s_off)
        e_closed.append(e.closed)
        if len(d):
            pts.append(d)
            s_all.append(s_off + s_loc)
            el.append(np.full(len(d), j))
            if e.closed:
                cc.append(np.full(len(d), c_off))
                oo.append(np.minimum(s_loc, L - s_loc))
            else:
                cc.append(c_off + s_loc)
                oo.append(np.zeros(len(d)))
        if not e.closed:
            c_off += L
        s_off += L
    P.pts = np.vstack(pts) if pts else np.zeros((0, 2))
    P.s = np.concatenate(s_all) if s_all else np.zeros(0)
    P.elem = np.concatenate(el) if el else np.zeros(0, int)
    P.c = np.concatenate(cc) if cc else np.zeros(0)
    P.o = np.concatenate(oo) if oo else np.zeros(0)
    P.e_len = np.array(e_len)
    P.e_s0 = np.array(e_s0)
    P.e_closed = np.array(e_closed, bool)
    P.c_total = c_off
    P.cyclic = bool(len(P.pts) >= 3 and not (len(elements) == 1 and elements[0].closed)
                    and np.linalg.norm(P.pts[0] - P.pts[-1]) <= CLOSE_TOL and c_off > 0.0)
    return P


def graph_distance(P: LayerPath, i: np.ndarray, j: np.ndarray) -> np.ndarray:
    """Abstand entlang des Pfads zwischen dichten Punkten i und j; Schliesspunkte geschlossener Ringe
    sind Knoten (Abkuerzung der Laenge 0). Innerhalb eines geschlossenen Rings zyklisch; ist der ganze
    Schichtpfad ein geschlossener Zug (Ende = Start, z. B. Fugenwand), ebenfalls zyklisch."""
    ei, ej = P.elem[i], P.elem[j]
    same = ei == ej
    ds = np.abs(P.s[i] - P.s[j])
    L = P.e_len[ei]
    cyc = np.where(P.e_closed[ei], np.minimum(ds, L - ds), ds)
    dc = np.abs(P.c[i] - P.c[j])
    other = P.o[i] + P.o[j] + dc
    gd = np.where(same, cyc, other)
    if P.cyclic:  # geschlossener Zug: auch der Weg ueber den Start-/Endpunkt zaehlt
        gd = np.minimum(gd, P.o[i] + P.o[j] + (P.c_total - dc))
    return gd


def bead_region(paths: list[LayerPath], w: float):
    """Raupenflaeche: Mittellinie ⊕ w/2 (Vereinigung ueber die Schichtpfade)."""
    beads = []
    for P in paths:
        line = P.polyline()
        if len(line) >= 2:
            beads.append(LineString(line).buffer(w / 2.0, quad_segs=16))
        elif len(line) == 1:
            beads.append(shapely.Point(line[0]).buffer(w / 2.0, quad_segs=16))
    return unary_union(beads) if beads else EMPTY


# ---------------------------------------------------------------- Kruemmung


def window_radius(pts: np.ndarray, step: float, window: float,
                  closed: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Kruemmungsradius ueber ein Bogenlaengen-Fenster: Umkreis von p(s - a), p(s), p(s + a).

    Die Mittellinie wird gleichabstaendig (step) abgetastet, a = window. Fuer Punkte auf einem Kreis
    liefert der Umkreis genau dessen Radius, unabhaengig von der Abtastdichte der Eingabe. Ein Knick mit
    Ablenkung φ liefert a / (2 sin(φ/2)). Kollineare Punkte -> inf, Umkehr (p(s ± a) auf derselben
    Seite) -> 0. Rueckgabe: (Radius, Bogenlaenge, Punkt) je auswertbarem Punkt; die Enden
    (s < a, s > S - a) werden bei offenen Pfaden nicht ausgewertet. Bei `closed` (Ende = Start) wird
    zyklisch fortgesetzt, damit auch die Naht geprueft wird.
    """
    q, s = resample(pts, step)
    k = max(1, int(round(window / step)))
    if closed and len(q) > 2 * k + 2:
        q = np.vstack([q[-k - 1 : -1], q, q[1 : k + 1]])
        s = np.concatenate([s[-k - 1 : -1] - s[-1], s, s[1 : k + 1] + s[-1]])
    if len(q) < 2 * k + 1:
        return np.zeros(0), np.zeros(0), np.zeros((0, 2))
    a, b, c = q[: -2 * k], q[k:-k], q[2 * k :]
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    cross = (b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0]
    area2 = np.abs(cross)
    with np.errstate(divide="ignore", invalid="ignore"):
        R = ab * bc * ca / (2.0 * area2)
    flat = area2 <= 1e-9 * np.maximum(ab * bc, 1e-12)
    straight = np.einsum("ij,ij->i", a - b, c - b) < 0
    R = np.where(flat, np.where(straight, np.inf, 0.0), R)
    return R, s[k:-k], b


def straight_runs(pts: np.ndarray, s: np.ndarray, supported: np.ndarray, tol: float) -> list[tuple]:
    """Gerade, ungestuetzte Abschnitte: (Laenge, i0, i1). Ein Abschnitt waechst, solange alle Punkte
    hoechstens tol von der Sehne liegen und kein Punkt gestuetzt ist."""
    runs = []
    n = len(pts)
    i = 0
    while i < n - 1:
        if supported[i]:
            i += 1
            continue
        j = i + 1
        while j < n and not supported[j]:
            d = pts[j] - pts[i]
            L = np.linalg.norm(d)
            if L > 1e-9:
                mid = pts[i + 1 : j] - pts[i]
                dev = np.abs(mid[:, 0] * d[1] - mid[:, 1] * d[0]) / L if len(mid) else np.zeros(0)
                if len(dev) and dev.max() > tol:
                    break
            j += 1
        runs.append((float(s[j - 1] - s[i]), i, j - 1))
        i = j - 1 if j - 1 > i else i + 1
    return runs
