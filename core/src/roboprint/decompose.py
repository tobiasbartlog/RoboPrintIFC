"""Zerlegung einer Wand in Module (SPEC §5.4, Modus Modul).

Ablauf (`decompose_wall`):
1. Eignung: Dicke T >= 2 * w, sonst keine Teile (Grund: `wall_eligibility`).
2. Ueberhang-Regel: jede Sturzlinie (Oeffnungsoberkante z1) ist ein Pflicht-Schnitt in jeder
   Spalte, die die Oeffnung beruehrt. Kein Modul hat dadurch Material ueber Luft.
3. H*(b): groesste Modulhoehe, die die Machbarkeitspruefung fuer einen Vollquader b x T x H als
   machbar einstuft. Bisektion auf `h_step_mm` (10 mm) mit Cache ueber (b, T, H). Der Cache
   nutzt zusaetzlich Monotonie: machbar bei (b', H') => machbar fuer b <= b', H <= H';
   nicht machbar bei (b', H') => nicht machbar fuer b >= b', H >= H'. So kommen spaetere
   Breiten mit wenigen Aufrufen aus. Mit `scan` (Hoehensuche der vollen Planung) wird das
   Ergebnis der optimistischen Vorpruefung danach in einem Durchgang bestaetigt: ein Plan von
   unten bis zu dieser Hoehe, H* ist die Oberkante der letzten Schicht, die geht.
4. Raster: Spalten gleicher Breite L/n mit n = ceil(L/b), b aus {300, 400, ..., 1200} mm,
   b <= b_max. Reihen je Spalte von unten nach oben zwischen den Pflicht-Schnitten, jeweils
   ceil(s/H*) gleich hohe Reihen (moeglichst auf Vielfache der Schichthoehe). Ziel
   lexikographisch: (1) Anzahl Module minimal, (2) kleinster d_min aller Module maximal
   (geschaetzt aus den Quader-Pruefungen der vorkommenden Zellmasse).
5. Jedes Teil = `geometry.cut_box(wall.mesh, Zelle)` wird einzeln voll geprueft (Cache nur bei
   gleicher Geometrie). Schafft die Pruefung ein Teil nicht, wird die Zelle geteilt (erst die
   Hoehe, dann die Breite halbiert), bis sie machbar ist oder die Mindestgroesse erreicht;
   dann bleibt das Teil `nicht machbar` mit Ursache. Teile gleicher Geometrie bekommen aus dem
   Cache denselben Plan und damit dieselbe Platzierung: Ihre Welt (Teil, Arbeitsflaeche,
   Roboter) ist identisch, also gilt die dichte Simulation und Pruefung des Repraesentanten fuer
   jede Kopie (SPEC §5.4/5 bei gleicher Geometrie und gleicher Platzierung erfuellt). Die
   Ausgabe (`roboprint.export`) schreibt jede Kopie und nennt den Repraesentanten in
   `summary.parts[].same_as`.

Die Machbarkeit ist injiziert: `feasible(part_mesh_P) -> Feasibility` (oder ein Tupel
(machbar, d_min, placement[, cause[, planned]])). `prefeasible` ist eine optionale schnellere
Vorpruefung fuer die H*-Bisektion; ohne sie wird `feasible` verwendet. Teil-Frame P: Ursprung in
der Mitte der Bodenflaeche der Teil-Bounding-Box, Achsen parallel zu L (`frames.T_LP`).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import trimesh

from roboprint import frames
from roboprint import geometry as geo
from roboprint.frames import Placement
from roboprint.ifc import Opening, Wall, eligibility

ProgressCallback = Callable[[str, float, str], None]

DEFAULT_WIDTHS_MM: tuple[float, ...] = tuple(float(b) for b in range(300, 1201, 100))
_EPS = 1e-6
_MARGIN = 1.0  # Schnittboxen ragen ueber die Wand hinaus, damit nichts verloren geht


# --------------------------------------------------------------------------- Datentypen


@dataclass(frozen=True)
class Feasibility:
    """Ergebnis einer Machbarkeitspruefung fuer ein Teilmesh in P."""

    feasible: bool
    d_min_mm: float | None = None
    placement: Placement | None = None
    cause: str | None = None
    planned: Any = None  # z. B. `PlannedPart` des Planers, wird unveraendert durchgereicht


FeasibleFn = Callable[[trimesh.Trimesh], Any]
#: Hoehensuche: (Breite, Dicke, Obergrenze) -> groesste machbare Hoehe <= Obergrenze, 0 wenn keine
ScanFn = Callable[[float, float, float], float]


def as_feasibility(res: Any) -> Feasibility:
    """Normiert die Rueckgabe einer Machbarkeitsfunktion auf `Feasibility`."""
    if isinstance(res, Feasibility):
        return res
    if isinstance(res, tuple | list):
        vals = list(res) + [None] * (5 - len(res))
        ok, d, pl, cause, planned = vals[:5]
        return Feasibility(bool(ok), None if d is None else float(d), pl, cause, planned)
    raise TypeError(f"Unbekanntes Machbarkeitsergebnis: {type(res)!r}")


@dataclass
class DecomposeParams:
    bead_width_mm: float = 30.0
    layer_height_mm: float = 10.0
    widths_mm: tuple[float, ...] = DEFAULT_WIDTHS_MM
    b_max_mm: float = 1200.0
    h_step_mm: float = 10.0  # Genauigkeit der H*-Bisektion
    h_min_mm: float = 100.0  # kleinste sinnvolle Modulhoehe fuer H*
    h_upper_mm: float | None = None  # obere Schranke fuer H* (None: Wandhoehe)
    min_cell_width_mm: float = 150.0  # Mindestgroesse beim Verfeinern
    min_cell_height_mm: float = 50.0
    max_refine_depth: int = 4  # hoechstens so oft halbieren

    @classmethod
    def from_any(cls, params: DecomposeParams | Mapping[str, Any] | None) -> DecomposeParams:
        if params is None:
            return cls()
        if isinstance(params, DecomposeParams):
            return params
        known = {f for f in cls.__dataclass_fields__}
        kw = {k: v for k, v in params.items() if k in known and v is not None}
        if "widths_mm" in kw:
            kw["widths_mm"] = tuple(float(b) for b in kw["widths_mm"])
        return cls(**kw)


@dataclass
class Part:
    """Ein Modul: Mesh in P, Lage in der Wand (`T_LP`) und Platzierung auf der Arbeitsflaeche."""

    part_id: str
    wall_id: str
    mesh_P: trimesh.Trimesh  # noqa: N815
    T_LP: np.ndarray  # noqa: N815
    cell_min_L: np.ndarray  # noqa: N815 - Rasterzelle in L (Schnittbox ohne Rand)
    cell_max_L: np.ndarray  # noqa: N815
    row: int
    col: int
    feasibility: Feasibility

    @property
    def placement(self) -> Placement | None:
        return self.feasibility.placement

    @property
    def feasible(self) -> bool:
        return self.feasibility.feasible

    @property
    def status(self) -> str:
        return "machbar" if self.feasibility.feasible else "nicht machbar"

    @property
    def volume_mm3(self) -> float:
        return geo.volume(self.mesh_P)

    def mesh_L(self) -> trimesh.Trimesh:  # noqa: N802
        return self.mesh_P.copy().apply_transform(self.T_LP)


@dataclass
class Grid:
    """Raster einer Wand: Spaltengrenzen in x und je Spalte die Reihengrenzen in z (in L)."""

    xs: list[float]
    zs: list[list[float]]  # je Spalte aufsteigend, inkl. 0 und Spaltenoberkante
    h_star: float
    n_modules: int
    d_est_mm: float | None = None

    @property
    def n_cols(self) -> int:
        return len(self.xs) - 1

    @property
    def width_mm(self) -> float:
        return self.xs[1] - self.xs[0]


@dataclass
class DecomposeStats:
    box_checks: int = 0  # Aufrufe der (Vor-)Pruefung fuer Vollquader
    part_checks: int = 0  # Aufrufe der vollen Pruefung fuer Teile
    part_cache_hits: int = 0
    h_star: dict[float, float] = field(default_factory=dict)  # Spaltenbreite -> H*
    chosen: Grid | None = None  # Raster der zuletzt zerlegten Wand
    grids: dict[str, Grid] = field(default_factory=dict)  # wall_id -> Raster


# --------------------------------------------------------------------------- Eignung, Ueberhang


def wall_eligibility(wall: Wall, params: DecomposeParams | Mapping[str, Any] | None = None):
    """(geeignet, Grund|None) nach SPEC §5.4/1."""
    p = DecomposeParams.from_any(params)
    return eligibility(wall, p.bead_width_mm)


def wall_entry(wall: Wall, parts: list[Part], params: DecomposeParams | Mapping[str, Any] | None = None):
    """Eintrag fuer `summary.walls` (ARTEFAKTE): wall_id ist die IFC-GlobalId, part_ids der Wand."""
    ok, reason = wall_eligibility(wall, params)
    return {
        "wall_id": wall.wall_id,
        "name": wall.name,
        "eligible": ok,
        "reason": reason,
        "length_mm": wall.length_mm,
        "thickness_mm": wall.thickness_mm,
        "height_mm": wall.height_mm,
        "volume_mm3": wall.volume_mm3,
        "part_ids": [p.part_id for p in parts if p.wall_id == wall.wall_id],
    }


def _touches(o: Opening, x0: float, x1: float) -> bool:
    return o.x0 < x1 - _EPS and o.x1 > x0 + _EPS


def mandatory_cuts(openings: list[Opening], x0: float, x1: float, top: float) -> list[float]:
    """Pflicht-Schnitthoehen (Sturzlinien) fuer die Spalte [x0, x1] unterhalb von `top`."""
    zs = sorted({round(o.z1, 6) for o in openings if _touches(o, x0, x1) and _EPS < o.z1 < top - _EPS})
    return [float(z) for z in zs]


def overhang_violations(wall: Wall, parts: list[Part]) -> list[str]:
    """Teile, deren z-Bereich eine Sturzlinie einer beruehrten Oeffnung im Inneren schneidet."""
    out = []
    for p in parts:
        lo, hi = p.cell_min_L, p.cell_max_L
        for o in wall.openings:
            if _touches(o, lo[0], hi[0]) and lo[2] + _EPS < o.z1 < hi[2] - _EPS:
                out.append(f"{p.part_id}: Sturzlinie z={o.z1:.1f} liegt in ({lo[2]:.1f}, {hi[2]:.1f})")
    return out


# --------------------------------------------------------------------------- H* (Bisektion)


def box_mesh_P(width: float, thickness: float, height: float) -> trimesh.Trimesh:  # noqa: N802
    """Vollquader in P (Ursprung Mitte Bodenflaeche)."""
    return geo.make_box((width, thickness, height), origin=(-width / 2, -thickness / 2, 0.0))


class HStar:
    """H*(Breite) per Bisektion auf `step` mm mit Cache ueber (Breite, Dicke, Hoehe).

    Mit `scan` (Hoehensuche der vollen Planung) wird das Ergebnis der schnellen Vorpruefung
    `check` bestaetigt: Die Vorpruefung ist optimistisch und haelt zu hohe Quader fuer machbar.
    Die Hoehensuche plant den Quader einmal von unten bis zu dieser Hoehe und liefert die Oberkante
    der letzten Schicht, die geht.
    """

    def __init__(
        self,
        check: FeasibleFn,
        step: float = 10.0,
        h_min: float = 100.0,
        scan: ScanFn | None = None,
        note: Callable[[str], None] | None = None,
    ) -> None:
        self.check = check
        self.step = float(step)
        self.h_min = float(h_min)
        self.cache: dict[tuple[float, float, float], Feasibility] = {}
        self.calls = 0
        self.hits = 0
        self.scan = scan
        self.scanned: dict[tuple[float, float], tuple[float, float]] = {}  # (b, t) -> (Obergrenze, H)
        self.note = note or (lambda msg: None)

    @staticmethod
    def _key(b: float, t: float, h: float) -> tuple[float, float, float]:
        return (round(b, 3), round(t, 3), round(h, 3))

    def _implied(self, b: float, t: float, h: float) -> bool | None:
        """Ergebnis aus dem Cache per Monotonie in Breite und Hoehe (gleiche Dicke)."""
        kb, kt, kh = self._key(b, t, h)
        for (cb, ct, ch), r in self.cache.items():
            if ct != kt:
                continue
            if r.feasible and cb >= kb and ch >= kh:
                return True
            if not r.feasible and cb <= kb and ch <= kh:
                return False
        return None

    def box(self, b: float, t: float, h: float) -> Feasibility:
        """Pruefergebnis fuer den Vollquader (immer echt geprueft, gecacht)."""
        k = self._key(b, t, h)
        if k in self.cache:
            self.hits += 1
            return self.cache[k]
        self.calls += 1
        r = as_feasibility(self.check(box_mesh_P(b, t, h)))
        self.cache[k] = r
        return r

    def ok(self, b: float, t: float, h: float) -> bool:
        """Machbarkeit des Quaders, aus dem Cache (auch per Monotonie) oder geprueft."""
        return self._ok(b, t, h)

    def _ok(self, b: float, t: float, h: float) -> bool:
        imp = self._implied(b, t, h)
        if imp is not None:
            self.hits += 1
            return imp
        return self.box(b, t, h).feasible

    def __call__(self, b: float, t: float, h_upper: float) -> float:
        """Groesste machbare Hoehe <= h_upper; 0, wenn schon h_min scheitert."""
        h = self._pre(b, t, float(h_upper))
        if self.scan is None or h <= _EPS:
            return h
        return self._scanned(b, t, h)

    def _scanned(self, b: float, t: float, h: float) -> float:
        """Hoehensuche bis h, gecacht: Ein Ergebnis unter seiner Obergrenze ist die echte Grenze und
        gilt fuer jede hoehere Obergrenze; darunter ist jede Hoehe machbar (Praefix des Plans)."""
        k = (round(b, 3), round(t, 3))
        if k in self.scanned:
            upper, res = self.scanned[k]
            if h <= res + _EPS:
                return h
            if res < upper - _EPS:
                return res
        self.note(f"Modulhoehe: {b:.0f} x {t:.0f} mm bis {h:.0f} mm schichtweise planen")
        res = float(self.scan(b, t, h))
        self.scanned[k] = (h, res)
        return res

    def _pre(self, b: float, t: float, h_upper: float) -> float:
        """Bisektion mit der Vorpruefung auf `step` genau."""
        if self._ok(b, t, h_upper):
            return h_upper
        h_lo = min(self.h_min, h_upper)
        if not self._ok(b, t, h_lo):
            return 0.0
        # Gitter k*step; lo machbar, hi nicht machbar
        lo = h_lo
        hi = h_upper
        while hi - lo > self.step + _EPS:
            mid = math.floor((lo + hi) / 2 / self.step) * self.step
            if mid <= lo + _EPS:
                mid = lo + self.step
            if mid >= hi - _EPS:
                break
            if self._ok(b, t, mid):
                lo = mid
            else:
                hi = mid
        return lo


# --------------------------------------------------------------------------- Raster


def _split_rows(a: float, b: float, h_star: float, layer: float) -> list[float]:
    """Innere Schnitthoehen, die [a, b] in ceil((b-a)/H*) Reihen <= H* teilen."""
    s = b - a
    k = max(1, math.ceil(s / h_star - 1e-9))
    if k == 1:
        return []
    r = math.ceil(s / k / layer - 1e-9) * layer
    if r > h_star + _EPS or s - (k - 1) * r < 0.5 * r:
        r = s / k  # gleich hohe Reihen statt eines Rests
    return [a + i * r for i in range(1, k)]


def _cell_empty(openings: list[Opening], x0: float, x1: float, z0: float, z1: float) -> bool:
    return any(
        o.x0 <= x0 + _EPS and o.x1 >= x1 - _EPS and o.z0 <= z0 + _EPS and o.z1 >= z1 - _EPS
        for o in openings
    )


def _column_top(wall: Wall, x0: float, x1: float) -> float:
    col = geo.cut_box(
        wall.mesh, (x0, -_MARGIN, -_MARGIN), (x1, wall.thickness_mm + _MARGIN, wall.height_mm + _MARGIN)
    )
    return 0.0 if geo.is_empty(col) else float(col.bounds[1, 2])


def build_grid(wall: Wall, n_cols: int, h_star: float, layer: float, tops: list[float] | None = None) -> Grid:
    """Raster mit `n_cols` gleich breiten Spalten und Reihen <= H* (Pflicht-Schnitte zuerst)."""
    length = wall.length_mm
    xs = [length * i / n_cols for i in range(n_cols + 1)]
    zs_all: list[list[float]] = []
    count = 0
    for c in range(n_cols):
        x0, x1 = xs[c], xs[c + 1]
        top = tops[c] if tops is not None else _column_top(wall, x0, x1)
        if top <= _EPS:
            zs_all.append([0.0])
            continue
        stops = [0.0, *mandatory_cuts(wall.openings, x0, x1, top), top]
        zs = [0.0]
        for a, b in zip(stops[:-1], stops[1:], strict=True):
            zs += _split_rows(a, b, h_star, layer) + [b]
        zs_all.append(zs)
        cells = zip(zs[:-1], zs[1:], strict=True)
        count += sum(1 for z0, z1 in cells if not _cell_empty(wall.openings, x0, x1, z0, z1))
    return Grid(xs=xs, zs=zs_all, h_star=h_star, n_modules=count)


def _candidate_cols(length: float, p: DecomposeParams) -> list[int]:
    widths = [b for b in p.widths_mm if b <= p.b_max_mm + _EPS]
    ns = sorted({max(1, math.ceil(length / b - 1e-9)) for b in widths}) if widths else [1]
    return ns


def choose_grid(
    wall: Wall, p: DecomposeParams, hstar: HStar, stats: DecomposeStats | None = None
) -> Grid | None:
    """Waehlt das Raster lexikographisch (Anzahl Module, dann groesster kleinster d_min)."""
    t = wall.thickness_mm
    h_upper = wall.height_mm if p.h_upper_mm is None else min(p.h_upper_mm, wall.height_mm)
    grids: list[Grid] = []
    # Untere Schranke je Spaltenzahl: Raster mit H* = h_upper. Kandidaten nach Schranke
    # sortiert; sobald die Schranke ueber der besten echten Anzahl liegt, ist Schluss. So
    # braucht die H*-Suche nur die aussichtsreichen Breiten.
    cands = []
    for n in _candidate_cols(wall.length_mm, p):
        tops = [_column_top(wall, wall.length_mm * i / n, wall.length_mm * (i + 1) / n) for i in range(n)]
        lb = build_grid(wall, n, h_upper, p.layer_height_mm, tops).n_modules
        cands.append((lb, n, tops))
    cands.sort(key=lambda c: (c[0], c[1]))
    best = math.inf
    for lb, n, tops in cands:
        if lb > best:
            break
        width = wall.length_mm / n
        if best < math.inf:
            # Branch and Bound: kann diese Breite die beste Anzahl ueberhaupt erreichen?
            h_need = _h_needed(wall, n, tops, best, h_upper, p.layer_height_mm)
            if h_need is None or not hstar.ok(width, t, h_need):
                continue
        hs = hstar(width, t, h_upper)
        if stats is not None:
            stats.h_star[round(width, 3)] = hs
        if hs <= _EPS:
            continue
        g = build_grid(wall, n, hs, p.layer_height_mm, tops)
        grids.append(g)
        best = min(best, g.n_modules)
    if not grids:
        return None
    best_n = min(g.n_modules for g in grids)
    ties = [g for g in grids if g.n_modules == best_n]
    for g in ties:
        g.d_est_mm = _estimate_d_min(g, t, hstar) if len(ties) > 1 else None
    ties.sort(key=lambda g: (-(g.d_est_mm if g.d_est_mm is not None else -math.inf), g.n_cols))
    return ties[0]


def _h_needed(
    wall: Wall, n: int, tops: list[float], target: int, h_upper: float, layer: float
) -> float | None:
    """Kleinste Reihenhoehe (1 mm genau), mit der `n` Spalten hoechstens `target` Module ergeben."""

    def count(h: float) -> int:
        return build_grid(wall, n, h, layer, tops).n_modules

    if count(h_upper) > target:
        return None
    lo, hi = 1.0, h_upper  # count(lo) > target angenommen, count(hi) <= target
    while hi - lo > 1.0:
        mid = (lo + hi) / 2
        if count(mid) <= target:
            hi = mid
        else:
            lo = mid
    return hi


def _estimate_d_min(g: Grid, t: float, hstar: HStar) -> float:
    """Kleinster d_min ueber die vorkommenden Zellmasse (Quader-Pruefung, gecacht)."""
    heights = {round(z1 - z0, 3) for zs in g.zs for z0, z1 in zip(zs[:-1], zs[1:], strict=True)}
    ds = []
    for h in heights:
        r = hstar.box(g.width_mm, t, h)
        ds.append(r.d_min_mm if (r.feasible and r.d_min_mm is not None) else -math.inf)
    return min(ds) if ds else -math.inf


# --------------------------------------------------------------------------- Teile


def wall_short_name(wall: Wall) -> str:
    """Kurzname fuer part_ids: letzter Abschnitt des Namens nach ' - ', als Slug."""
    name = (wall.name or "").split(" - ")[-1].strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return slug or re.sub(r"[^A-Za-z0-9]+", "_", wall.wall_id)[:12]


def _mesh_key(mesh: trimesh.Trimesh) -> str:
    v = np.round(np.asarray(mesh.vertices, dtype=float), 2) + 0.0
    v = v[np.lexsort(v.T[::-1])]
    h = hashlib.sha1(v.tobytes())
    h.update(str(len(mesh.faces)).encode())
    h.update(f"{geo.volume(mesh):.0f}".encode())
    return h.hexdigest()


FeasibleManyFn = Callable[[list[trimesh.Trimesh]], list[Any]]


class _PartChecker:
    """Volle Pruefung je Teil, gebuendelt je Runde (parallelisierbar ueber `many`); Cache nur bei
    gleicher Geometrie (SPEC §5.4/5)."""

    def __init__(
        self,
        feasible: FeasibleFn | None,
        stats: DecomposeStats,
        cache: dict[str, Feasibility] | None = None,
        many: FeasibleManyFn | None = None,
    ) -> None:
        self.feasible = feasible
        self.many = many
        self.stats = stats
        self.cache: dict[str, Feasibility] = {} if cache is None else cache

    def check_all(self, meshes: list[trimesh.Trimesh]) -> list[Feasibility]:
        keys = [_mesh_key(m) for m in meshes]
        todo: dict[str, trimesh.Trimesh] = {}
        for k, m in zip(keys, meshes, strict=True):
            if k not in self.cache and k not in todo:
                todo[k] = m
        self.stats.part_checks += len(todo)
        self.stats.part_cache_hits += len(meshes) - len(todo)
        if todo:
            ms = list(todo.values())
            if self.many is not None:
                res = list(self.many(ms))
            else:
                assert self.feasible is not None
                res = [self.feasible(m) for m in ms]
            for k, r in zip(todo, res, strict=True):
                self.cache[k] = as_feasibility(r)
        return [self.cache[k] for k in keys]


def _cut_part(wall: Wall, lo: np.ndarray, hi: np.ndarray) -> tuple[trimesh.Trimesh, np.ndarray] | None:
    """Schnitt der Zelle; liefert (Mesh in P, T_LP) oder None bei leerem Teil."""
    t, h, length = wall.thickness_mm, wall.height_mm, wall.length_mm
    blo = np.array([lo[0] if lo[0] > _EPS else -_MARGIN, -_MARGIN, lo[2] if lo[2] > _EPS else -_MARGIN])
    bhi = np.array(
        [
            hi[0] if hi[0] < length - _EPS else length + _MARGIN,
            t + _MARGIN,
            hi[2] if hi[2] < h - _EPS else h + _MARGIN,
        ]
    )
    m = geo.cut_box(wall.mesh, blo, bhi)
    if geo.is_empty(m) or geo.volume(m) < 1.0:
        return None
    T_LP = frames.T_LP(m.bounds[0], m.bounds[1])  # noqa: N806
    return m.apply_transform(frames.invert(T_LP)), T_LP


@dataclass
class _Cell:
    wall_idx: int
    row: int
    col: int
    lo: np.ndarray
    hi: np.ndarray
    depth: int = 0
    suffix: str = ""


def _split(cell: _Cell, p: DecomposeParams) -> list[_Cell] | str:
    """Teilt eine nicht machbare Zelle (Hoehe vor Breite) oder liefert den Grund, warum nicht."""
    lo, hi = cell.lo, cell.hi
    w, h = hi[0] - lo[0], hi[2] - lo[2]
    if cell.depth >= p.max_refine_depth:
        return "Verfeinerungstiefe erreicht"
    if h >= 2 * p.min_cell_height_mm - _EPS:
        zm = lo[2] + h / 2
        if h / 2 > 2 * p.layer_height_mm:
            zm = lo[2] + math.ceil(h / 2 / p.layer_height_mm - 1e-9) * p.layer_height_mm
            zm = min(zm, hi[2] - p.layer_height_mm)
        boxes = [(lo, np.array([hi[0], hi[1], zm])), (np.array([lo[0], lo[1], zm]), hi)]
    elif w >= 2 * p.min_cell_width_mm - _EPS:
        xm = lo[0] + w / 2
        boxes = [(lo, np.array([xm, hi[1], hi[2]])), (np.array([xm, lo[1], lo[2]]), hi)]
    else:
        return f"Mindestzelle {w:.0f} x {h:.0f} mm erreicht"
    return [
        _Cell(cell.wall_idx, cell.row, cell.col, a, b, cell.depth + 1, f"{cell.suffix}_s{j}")
        for j, (a, b) in enumerate(boxes)
    ]


def _plan_cells(
    walls: list[Wall], cells: list[_Cell], checker: _PartChecker, p: DecomposeParams, prog: ProgressCallback
) -> list[Part]:
    """Plant alle Zellen rundenweise; nicht machbare Zellen werden geteilt und neu geplant."""
    shorts = [wall_short_name(w) for w in walls]
    parts: list[Part] = []
    pending, rnd = cells, 0
    while pending:
        cut = [(c, _cut_part(walls[c.wall_idx], c.lo, c.hi)) for c in pending]
        cut = [(c, x) for c, x in cut if x is not None]
        prog("decompose", 0.5, f"Runde {rnd}: {len(cut)} Teile pruefen")
        results = checker.check_all([x[0] for _, x in cut])
        nxt: list[_Cell] = []
        for (c, (mesh_P, T_LP)), res in zip(cut, results, strict=True):  # noqa: N806
            pieces = None if res.feasible else _split(c, p)
            if isinstance(pieces, list):
                nxt += pieces
                continue
            if not res.feasible:
                why = f"{res.cause or 'Planer findet keine machbare Platzierung'}; {pieces}"
                res = Feasibility(False, res.d_min_mm, res.placement, why, res.planned)
            w = walls[c.wall_idx]
            pid = f"{shorts[c.wall_idx]}_r{c.row}_c{c.col}{c.suffix}"
            parts.append(Part(pid, w.wall_id, mesh_P, T_LP, c.lo, c.hi, c.row, c.col, res))
        pending, rnd = nxt, rnd + 1
    order = {id(w): i for i, w in enumerate(walls)}
    wall_of = {w.wall_id: order[id(w)] for w in walls}
    parts.sort(key=lambda q: (wall_of[q.wall_id], q.col, q.cell_min_L[2], q.cell_min_L[0]))
    return parts


def decompose_walls(
    walls: list[Wall],
    params: DecomposeParams | Mapping[str, Any] | None = None,
    feasible: FeasibleFn | None = None,
    progress: ProgressCallback | None = None,
    *,
    prefeasible: FeasibleFn | None = None,
    feasible_many: FeasibleManyFn | None = None,
    stats: DecomposeStats | None = None,
    hstar: HStar | None = None,
    part_cache: dict[str, Feasibility] | None = None,
    scan: ScanFn | None = None,
) -> list[Part]:
    """Zerlegt mehrere Waende (SPEC §5.4); H*-Cache und Geometrie-Cache gelten wanduebergreifend,
    die volle Pruefung laeuft je Runde fuer alle Waende gebuendelt (`feasible_many`). `scan`
    bestaetigt H* mit der Hoehensuche der vollen Planung (`HStar`)."""
    p = DecomposeParams.from_any(params)
    st = stats if stats is not None else DecomposeStats()
    prog = progress or (lambda stage, frac, msg: None)
    if feasible is None and feasible_many is None:
        raise ValueError("feasible oder feasible_many angeben (Planer: roboprint.decompose_plan)")
    checker = _PartChecker(feasible, st, part_cache, feasible_many)
    if hstar is None:
        check = prefeasible or feasible or (lambda m: feasible_many([m])[0])  # type: ignore[misc]
        hstar = HStar(check, p.h_step_mm, p.h_min_mm, scan=scan, note=lambda msg: prog("decompose", 0.0, msg))
    cells: list[_Cell] = []
    for i, wall in enumerate(walls):
        short = wall_short_name(wall)
        if not eligibility(wall, p.bead_width_mm)[0]:
            prog("decompose", 0.0, f"{short}: nicht geeignet")
            continue
        calls0 = hstar.calls
        prog("decompose", 0.0, f"{short}: H*-Suche")
        grid = choose_grid(wall, p, hstar, st)
        st.box_checks += hstar.calls - calls0
        if grid is None:  # nicht einmal h_min machbar: ueber die Verfeinerung versuchen
            grid = build_grid(wall, max(_candidate_cols(wall.length_mm, p)), p.h_min_mm, p.layer_height_mm)
        st.chosen = grid
        st.grids[wall.wall_id] = grid
        prog("decompose", 0.0, f"{short}: {grid.n_cols} Spalten, H* = {grid.h_star:.0f} mm")
        for c in range(grid.n_cols):
            zs = grid.zs[c]
            for r, (z0, z1) in enumerate(zip(zs[:-1], zs[1:], strict=True)):
                lo = np.array([grid.xs[c], 0.0, z0])
                hi = np.array([grid.xs[c + 1], wall.thickness_mm, z1])
                cells.append(_Cell(i, r, c, lo, hi))
    parts = _plan_cells(walls, cells, checker, p, prog)
    prog("decompose", 1.0, f"{len(parts)} Teile")
    return parts


def decompose_wall(
    wall: Wall,
    params: DecomposeParams | Mapping[str, Any] | None = None,
    feasible: FeasibleFn | None = None,
    progress: ProgressCallback | None = None,
    **kwargs: Any,
) -> list[Part]:
    """Zerlegt eine Wand in Module (SPEC §5.4) und liefert `list[Part]`.

    `feasible(part_mesh_P)` ist die volle Pruefung je Teil (Planer mit Platzierungssuche);
    `prefeasible` optional eine schnellere Vorpruefung fuer die H*-Bisektion. Ungeeignete Wand:
    leere Liste (Grund ueber `wall_eligibility`). Teile, die auch nach Verfeinerung nicht machbar
    sind, bleiben mit Status `nicht machbar` und Ursache in der Liste. Weitere Schluesselwoerter
    wie `decompose_walls`.
    """
    return decompose_walls([wall], params, feasible, progress, **kwargs)


def scenario_parts(scenario: Any, params: Any, jobs: int = 1, progress: ProgressCallback | None = None):
    """Naht fuer `pipeline` (source.kind = ifc): (summary.walls, PartJobs mit fertigem Plan)."""
    from roboprint.decompose_plan import scenario_parts as _impl

    return _impl(scenario, params, jobs=jobs, progress=progress)
