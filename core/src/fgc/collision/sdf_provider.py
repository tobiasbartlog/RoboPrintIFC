"""SdfObstacleProvider: SDF-Backend am Hindernis-Provider-Vertrag (PRD #183 AP 1, Issue #213).

Verheiratet die beiden AP-1-Standbeine zur **Punkt-gegen-Glied-SDF-Inversion**
(invertiert nach Shen 2026): das statische Glied-SDF (:mod:`fgc.collision.
glied_sdf`, #207) und den Druckstand als wachsende Punktwolke
(:mod:`fgc.collision.druckstand_punkte`, #208). Der Provider **erfüllt den
bestehenden Hindernis-Provider-Vertrag** ``obstacle_provider: Callable[[int],
ObstacleSet]`` (:mod:`fgc.collision.check`): ``provider(layer_index)`` liefert
weiterhin den echten Mesh-Hindernissatz je Schicht — den braucht der
**FCL-Nachprüfer** im Grenzband. Zusätzlich trägt er die SDF-Abfrageflächen,
die :func:`fgc.collision.check.find_collisions` per Duck-Typing erkennt
(injizierter Provider = Backend-Schalter; s. :mod:`fgc.collision.backend`).

**Konservativer Kern (US 16): die Schranke unterschätzt, nie überschätzt.**
Je Glied und Sample entsteht eine **untere Schranke** der exakten
FCL-Urteilsdistanz aus drei Quellen, deren Minimum gilt:

- **AABB-Breitphase je Punkt**: Distanz Punkt→Glied-AABB (exakte untere
  Schranke, AABB ⊇ Glied) minus **Deckungsradius** — nur nahe Punkte gehen
  weiter in die SDF-Abfrage (Top-K), ferne urteilen über ihre AABB-Schranke.
- **Glied-SDF batchweise**: die nahen Punkte werden ins Gliedframe
  transformiert und vektorisiert abgefragt; das SDF selbst überschätzt nie
  (#207-Kernvertrag, Interpolationsband inklusive), der Deckungsradius wird
  als ``safety_band_mm`` zusätzlich abgezogen.
- **Melderadius-Faltung**: Punkte außerhalb des Bin-Melderadius liegen
  beweisbar weiter als ``report_radius_mm`` — ihre Schranke ist die Konstante
  ``report_radius_mm − Deckung`` (Grün-Distanzen bleiben ehrliche untere
  Schranken, werden aber oberhalb des Melderadius nicht weiter aufgelöst).

Der **Deckungsradius** schließt die Lücke zwischen Punktwolke und wahrer
Oberfläche: jeder Oberflächenpunkt des Hindernisses hat einen Wolkenpunkt im
Deckungsradius (Grundriss-Gitter ``√2·spacing`` in der Ebene, ``layer_height``
vertikal; Mesh-Subdivision ``spacing/√3``). **Voraussetzung** ist ein
Punktabstand deutlich unter der dünnsten Grundriss-Feature-Breite (Wanddicke) —
dieselbe Annahme wie Shen 2026 („Punktabstand deutlich unter dem
Sicherheitsabstand", Design-Log 2026-07-12; Wanddicken ≥ 100 mm bei 15 mm
Abstand). Liegt die Schranke ≤ Sicherheitsabstand, ruft ``find_collisions``
den **FCL-Nachprüfer** — denselben Referenzpfad (Gruppen, Freizone,
VHACD-Distanzen) wie das FCL-Backend. Rote/gelbe Befunde (Verursacher-Glied,
Eindringtiefe) sind dadurch **byte-identisch** zur Referenz (US 2); nur im
sicher-grünen Bereich unterscheiden sich die (beiderseits konservativen)
Abstandszahlen.

**Selbstkollision im selben Schema** (Punkte von Glied A gegen SDF von
Glied B): :meth:`link_points_local` sampelt einmalig die Urteilsgeometrie je
Glied als Punktwolke (dieselbe deterministische Sampling-Funktion wie die
statischen Hindernisse, #208); :meth:`points_vs_link_bound` liefert die
Schranke des Paars. Die frühere **bedingte Kapsel-/FCL-Distanztabelle entfällt**
im SDF-Backend — FCL urteilt Paare nur noch im Grenzband.

**Reinheit / Modularität.** Geo-Pakete *lazy* (Core startet geo-frei); alle
Sampling-/Bin-Strukturen deterministisch (feste Gitter, ``argpartition`` auf
festen Eingaben) — Wiederholung ist bitgleich. Der Backend-**Schalter** lebt
nicht hier, sondern als injizierbares Modul auf App-Ebene
(:mod:`fgc.collision.backend`, PRD-Kommentar 2026-07-14) — und ausdrücklich
**nicht** in ``CollisionConfig``; die GPU-Naht (#205) dockt ausschließlich an
``check_representative`` an und bleibt von diesem Modul unberührt.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from fgc.collision import druckstand as _ds
from fgc.collision.druckstand_punkte import (
    DEFAULT_POINT_SPACING_MM,
    DruckstandPunkte,
    DruckstandPunkteSpec,
    _mesh_surface_points,
)

if TYPE_CHECKING:  # nur für Typprüfer — kein Laufzeit-Import (geo-frei startbar)
    from fgc.collision.druckstand import DruckstandSpec, ObstacleSet
    from fgc.collision.glied_sdf import GliedSdf
    from fgc.collision.robot_geometry import RobotCollisionGeometry

GEO_HINT = (
    "Das SDF-Kollisions-Backend braucht die Geo-Extras (numpy, trimesh, shapely). "
    "Installiere sie mit  pip install fgc-core[geo]  (bereits im Projekt-venv)."
)

#: Obergrenze der Punkte je SDF-Batch-Abfrage (Top-K nach AABB-Nähe). Verworfene
#: Punkte urteilen weiter über ihre AABB-Schranke — die Kappung bleibt konservativ.
DEFAULT_TOP_K = 4096

#: Kantenlänge (mm) der räumlichen Bins über der Hindernis-Punktwolke — klein
#: genug, dass „nahe Bins einsammeln" wenig Übermaß holt, groß genug für eine
#: kleine Bin-Zahl in der vektorisierten Bin-Breitphase.
DEFAULT_BIN_MM = 150.0

#: Melderadius (mm): bis hierhin werden Grün-Distanzen punktgenau aufgelöst;
#: weiter entfernte Punkte falten zur Konstante ``report_radius − Deckung``
#: (untere Schranke bleibt gültig, nur die Auflösung endet).
DEFAULT_REPORT_RADIUS_MM = 150.0


def _require_np():
    """Lazy-Import von numpy mit freundlichem Fehlpfad statt Import-Crash."""
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - Pfad nur ohne [geo]-Extras
        raise ImportError(GEO_HINT) from exc
    return numpy


def _aabb_point_sq(pts, lo, hi, np):
    """Quadrierte Distanz je Punkt zur AABB ``[lo, hi]`` (0 innerhalb) — untere Schranke."""
    d = np.maximum(np.maximum(lo - pts, pts - hi), 0.0)
    return np.einsum("ij,ij->i", d, d)


class SdfObstacleProvider:
    """Adapter am Hindernis-Provider-Vertrag mit SDF-Abfrageflächen (Issue #213).

    ``provider(layer_index)`` liefert den echten :class:`ObstacleSet` je Schicht
    (delegiert an :func:`fgc.collision.druckstand.obstacle_provider` — die eine
    Quelle des FCL-Nachprüfers). Die zusätzlichen Methoden (``prime``,
    ``obstacle_bound``, ``points_vs_link_bound``, ``link_points_local``,
    ``surface_points``) erkennt ``find_collisions`` per Duck-Typing und schaltet
    damit auf die Punkt-gegen-Glied-SDF-Inversion um. ``link_points`` kann ein
    geteiltes (App-gecachtes) Dict sein — der Provider füllt es lazily.
    """

    def __init__(
        self,
        spec: DruckstandSpec,
        glied_sdf: GliedSdf,
        geo: RobotCollisionGeometry,
        *,
        point_spacing_mm: float = DEFAULT_POINT_SPACING_MM,
        top_k: int = DEFAULT_TOP_K,
        bin_mm: float = DEFAULT_BIN_MM,
        report_radius_mm: float = DEFAULT_REPORT_RADIUS_MM,
        link_points: dict[int, Any] | None = None,
    ) -> None:
        self.spec = spec
        self.glied_sdf = glied_sdf
        self._geo = geo
        self.point_spacing_mm = float(point_spacing_mm)
        self.top_k = int(top_k)
        self.bin_mm = float(bin_mm)
        self.report_radius_mm = float(report_radius_mm)
        #: Deckungsradius (mm) der Hindernis-Punktwolke: Grundriss-Gitter deckt
        #: die Prismen-Oberfläche mit ``√2·spacing`` in der Ebene und
        #: ``layer_height`` vertikal; die statischen Mesh-Samples (``spacing/√3``)
        #: liegen darunter. Voraussetzung s. Moduldocstring (Feature-Breite).
        self.obstacle_cover_mm = math.hypot(
            math.sqrt(2.0) * self.point_spacing_mm, float(spec.layer_height_mm)
        )
        #: Deckungsradius (mm) der Glied-/Tool-Punktwolken (Mesh-Subdivision:
        #: Kantenlänge ≤ spacing ⇒ jeder Oberflächenpunkt ≤ spacing/√3 vom Knoten).
        self.link_cover_mm = self.point_spacing_mm / math.sqrt(3.0)
        self._fcl = _ds.obstacle_provider(spec)
        self._punkte = DruckstandPunkte(
            DruckstandPunkteSpec.from_druckstand_spec(spec, point_spacing_mm=point_spacing_mm)
        )
        self._link_points = link_points if link_points is not None else {}
        self._mesh_points: dict[int, tuple[Any, Any]] = {}
        self._primed_layer = -1
        self._cloud: Any = None
        self._offsets: list[int] = []
        #: Parallele Bin-Strukturen (prime): Box-Lo-Ecke je Bin ``(B, 3)``, je Bin
        #: das aufsteigend sortierte Punkt-Index-Array, und der kleinste Index je
        #: Bin (Schicht-Präfix-Filter ohne Gather).
        self._bin_lo: Any = None
        self._bin_arrays: list[Any] = []
        self._bin_first: Any = None
        #: Je Glied das zuletzt eingesammelte Nahe-Bins-Paket (Schicht + Bin-Satz →
        #: Punktarray): aufeinanderfolgende Samples treffen fast immer denselben Satz.
        self._gather_cache: dict[int, tuple[Any, Any]] = {}
        #: Drift-Anker je Glied: (Punktlimit, Sicherheitsabstand, Welt-Pose, Schranke).
        #: Die Schranke ist 1-Lipschitz in der Glied-Bewegung — innerhalb der
        #: Drift ``m`` bleibt die Entscheidung beweisbar gleich (s. ``obstacle_bound``).
        self._bound_cache: dict[int, tuple[int, float, Any, float]] = {}
        self._reach_cache: dict[int, float] = {}
        #: Diagnose-Zähler (Tests #213, Messung #215): wie oft die Schranke ins
        #: Grenzband fiel (FCL-Nachprüfer läuft) bzw. sicher grün übersprang.
        self.n_grenzband = 0
        self.n_broad_skip = 0

    # --- Hindernis-Provider-Vertrag (FCL-Sätze für den Nachprüfer) -----------

    def __call__(self, layer_index: int) -> ObstacleSet:
        return self._fcl(layer_index)

    # --- Punktwolke + Bins (einmal je Bahn, Schicht-Views per Präfix) --------

    def prime(self, max_layer_index: int) -> None:
        """Baut Punktwolke + Bins einmalig bis zur höchsten Schicht der Bahn.

        Statik zuerst, dann die Schicht-Scheiben in Reihenfolge — der Punktsatz
        der Schicht ``L`` ist damit der Präfix-View ``cloud[:offsets[L]]``
        (reines Anhängen, #208). Erneutes ``prime`` mit gleicher oder kleinerer
        Schicht ist ein No-Op (Prüf-Tür + voller Befund teilen den Provider).
        """
        np = _require_np()
        target = max(0, min(int(max_layer_index), int(self.spec.n_layers)))
        if self._cloud is not None and target <= self._primed_layer:
            return
        self._punkte.advance_layer(target)
        static = self._punkte.static_points_mm
        growing = self._punkte.growing_points_mm
        self._cloud = np.concatenate([static, growing], axis=0)
        offsets = [len(static)]
        for count in self._punkte.growing_layer_counts:
            offsets.append(offsets[-1] + int(count))
        self._offsets = offsets
        self._primed_layer = target
        self._build_bins(np)

    def _build_bins(self, np) -> None:
        """Räumliche Bins als parallele Arrays (Box-Ecken, sortierte Punkt-Indizes).

        Die Bin-Indizes je Bin sind aufsteigend sortiert (stabiles Argsort über
        die Wolke in Anhäng-Reihenfolge) — der Schicht-Präfix ``idx < limit`` ist
        damit je Bin ein ``searchsorted``-Schnitt, kein Filter.
        """
        if self._cloud is None or len(self._cloud) == 0:
            self._bin_lo = np.zeros((0, 3), dtype=float)
            self._bin_arrays = []
            self._bin_first = np.zeros(0, dtype=np.int64)
            return
        keys = np.floor(self._cloud / self.bin_mm).astype(np.int64)
        kmin = keys.min(axis=0)
        rel = keys - kmin
        dims = rel.max(axis=0) + 1
        flat = (rel[:, 0] * dims[1] + rel[:, 1]) * dims[2] + rel[:, 2]
        order = np.argsort(flat, kind="stable")  # stabil ⇒ je Bin aufsteigende Indizes
        sorted_flat = flat[order]
        boundaries = np.flatnonzero(np.diff(sorted_flat)) + 1
        groups = np.split(order, boundaries)
        lo_keys = np.empty((len(groups), 3), dtype=np.int64)
        for b, group in enumerate(groups):
            f = int(flat[group[0]])
            z = f % int(dims[2])
            y = (f // int(dims[2])) % int(dims[1])
            x = f // int(dims[2] * dims[1])
            lo_keys[b] = (x + kmin[0], y + kmin[1], z + kmin[2])
        self._bin_lo = lo_keys.astype(float) * self.bin_mm
        self._bin_arrays = groups
        self._bin_first = np.asarray([int(g[0]) for g in groups], dtype=np.int64)

    def n_obstacle_points(self, layer_index: int) -> int:
        """Punktzahl des Hindernissatzes der Schicht (Statik + Scheiben ≤ Schicht)."""
        if not self._offsets:
            return 0
        clamped = max(0, min(int(layer_index), len(self._offsets) - 1))
        return int(self._offsets[clamped])

    # --- Schranken (Punkt-gegen-Glied-SDF-Inversion) --------------------------

    #: Punktzahl der Grenzband-Sonde (gleichverteilt aus dem nächstliegenden Bin).
    PROBE_N = 256

    def obstacle_bound(
        self, layer_index: int, link_index: int, world_matrix, aabb_lo, aabb_hi, safety_mm: float
    ) -> float:
        """Konservative untere Schranke Glied↔Druckstand für **eine** Schicht/Pose.

        Dreistufig, jede Stufe eine gültige untere Schranke:

        1. **Bin-Breitphase** (vektorisiert über alle Bins): Distanz Bin-Box↔
           Glied-AABB; Bins jenseits des Melderadius falten zur Konstante,
           Kandidaten-Bins über dem Grenzband urteilen über ihre Box-Distanz —
           ganz ohne Punkt-Gather.
        2. **Sonde**: gleichverteilte Punkte aus dem nächstliegenden Bin in die
           SDF-Batch-Abfrage — meldet ein Punkt ≤ Sicherheitsabstand, steht das
           Grenzband fest (früher Ausstieg, der chronisch nahe Glieder billig
           macht).
        3. **Vollpfad**: AABB-Breitphase je Punkt + Top-K in die SDF-Abfrage
           (:meth:`_points_bound`) über die eingesammelten nahen Bins.

        ``≤ safety_mm`` heißt Grenzband — der Aufrufer lässt den FCL-Nachprüfer
        (Referenzpfad) laufen.

        **Drift-Anker** (dichte Bahnen): die Schranke ist 1-Lipschitz in der
        Bewegung der Glied-Geometrie — bewegt sich das Glied seit dem letzten
        frisch gerechneten Anker um höchstens ``m`` (Translation plus Rotation ×
        Wirkradius), gilt ``|Schranke_neu − Schranke_alt| ≤ m``. Liegt der Anker
        um mehr als ``m`` auf einer Seite des Sicherheitsabstands, steht die
        Entscheidung ohne Neuberechnung fest; zurückgegeben wird die weiterhin
        gültige untere Schranke ``Anker − m``. Chronisch nahe (tief rote) wie
        chronisch freie Glieder rechnen so nur alle ~Sicherheitsabstand-Millimeter
        Armbewegung neu statt je Sample.
        """
        np = _require_np()
        limit = self.n_obstacle_points(layer_index)
        if limit <= 0 or self._bin_lo is None or not len(self._bin_arrays):
            return float("inf")
        hit = self._bound_cache.get(link_index)
        if hit is not None and hit[0] == limit and hit[1] == float(safety_mm):
            old_mat, old_bound = hit[2], hit[3]
            rho = self._reach_mm(link_index, safety_mm, np)
            m = float(
                np.linalg.norm(world_matrix[:3, 3] - old_mat[:3, 3])
                + np.linalg.norm(world_matrix[:3, :3] - old_mat[:3, :3]) * rho
            )
            if old_bound + m <= safety_mm or old_bound - m > safety_mm:
                self._count(old_bound - m, safety_mm)
                return float(old_bound - m)
        bound = self._obstacle_bound_fresh(
            limit, link_index, world_matrix, aabb_lo, aabb_hi, safety_mm, np
        )
        self._bound_cache[link_index] = (
            limit,
            float(safety_mm),
            np.array(world_matrix, dtype=float),
            float(bound),
        )
        self._count(bound, safety_mm)
        return float(bound)

    def _reach_mm(self, link_index: int, safety_mm: float, np) -> float:
        """Wirkradius (mm) der Drift-Abschätzung: Glied-Eckradius + Band + Bin-Übermaß."""
        r = self._reach_cache.get(link_index)
        if r is None:
            lo, hi = self._geo.link(link_index).broadphase_hull.bounds
            corners = np.array(
                [
                    [x, y, z]
                    for x in (lo[0], hi[0])
                    for y in (lo[1], hi[1])
                    for z in (lo[2], hi[2])
                ]
            )
            r = float(np.linalg.norm(corners, axis=1).max())
            self._reach_cache[link_index] = r
        # Alle SDF-abgefragten Punkte liegen im Band um die Glied-AABB (Sonde wie
        # Vollpfad filtern darauf) — der Wirkradius braucht kein Bin-Übermaß.
        return r + float(safety_mm) + self.obstacle_cover_mm

    def _obstacle_bound_fresh(
        self, limit: int, link_index: int, world_matrix, aabb_lo, aabb_hi, safety_mm: float, np
    ) -> float:
        """Frische Drei-Stufen-Schranke (Bin-Breitphase, Sonde, Vollpfad) — s. oben."""
        cover = self.obstacle_cover_mm
        band = float(safety_mm) + cover
        lo = np.asarray(aabb_lo, dtype=float)
        hi = np.asarray(aabb_hi, dtype=float)

        # 1) Bin-Breitphase: Distanz jeder Bin-Box zur Glied-AABB (untere Schranke
        # für alle Punkte des Bins), Schicht-Filter über den kleinsten Punkt-Index.
        d = np.maximum(np.maximum(self._bin_lo - hi, lo - self._bin_lo - self.bin_mm), 0.0)
        gap2 = np.einsum("ij,ij->i", d, d)
        active = self._bin_first < limit
        r = max(self.report_radius_mm, band)
        in_radius = active & (gap2 <= r * r)
        bound = float("inf")
        if bool((active & ~in_radius).any()):
            bound = r - cover  # aktive Bins jenseits des Melderadius: Faltung
        cand = np.flatnonzero(in_radius)
        if len(cand) == 0:
            return float(bound)
        gaps = np.sqrt(gap2[cand])
        far = gaps > band
        if bool(far.any()):
            bound = min(bound, float(gaps[far].min()) - cover)
        near_bins = cand[~far]
        if len(near_bins) == 0:
            return float(bound)
        near_bins = near_bins[np.argsort(gaps[~far], kind="stable")]

        # Nahe Bins einsammeln — gecacht: aufeinanderfolgende Samples desselben
        # Glieds treffen fast immer dieselben Bins derselben Schicht.
        cache_key = (int(limit), tuple(int(b) for b in near_bins))
        hit = self._gather_cache.get(link_index)
        if hit is not None and hit[0] == cache_key:
            pts = hit[1]
        else:
            chunks = []
            for b in near_bins:
                arr = self._bin_arrays[b]
                cut = int(np.searchsorted(arr, limit))
                if cut:
                    chunks.append(arr[:cut])
            if chunks:
                pts = self._cloud[np.concatenate(chunks)]
            else:
                pts = self._cloud[:0]
            self._gather_cache[link_index] = (cache_key, pts)
        if len(pts) == 0:
            return float(bound)

        # 2) Sonde: gleichverteilte Teilmenge der nahen Punkte — früher
        # Grenzband-Beweis (jeder Punkt mit SDF ≤ Sicherheit genügt).
        rot = world_matrix[:3, :3]
        trans = world_matrix[:3, 3]
        lk = self.glied_sdf.link(link_index)
        if len(pts) > self.PROBE_N:
            step = max(1, len(pts) // self.PROBE_N)
            probe = pts[::step][: self.PROBE_N]
            # Nur Sondenpunkte im Band abfragen — hält den Drift-Wirkradius
            # (:meth:`_reach_mm`) frei vom Bin-Übermaß.
            d2 = _aabb_point_sq(probe, lo, hi, np)
            probe = probe[d2 <= band * band]
            if len(probe):
                dist, _ = lk.distance((probe - trans) @ rot, safety_band_mm=cover)
                m = float(dist.min())
                if m <= safety_mm:
                    # Grenzband bewiesen — der Rückgabewert wird nur als „≤ Sicherheit"
                    # gelesen (der Aufrufer urteilt exakt per FCL); als Drift-Anker
                    # bleibt der Sonden-Wert gültig (Vollpfad-Minimum ≤ Sonden-Minimum).
                    return float(min(bound, m))

        # 3) Vollpfad über die eingesammelten nahen Punkte.
        bound = min(
            bound,
            self._points_bound(pts, link_index, world_matrix, lo, hi, safety_mm, cover, np),
        )
        return float(bound)

    def _count(self, bound: float, safety_mm: float) -> None:
        if bound <= safety_mm:
            self.n_grenzband += 1
        else:
            self.n_broad_skip += 1

    def points_vs_link_bound(
        self,
        points_world,
        link_index: int,
        world_matrix,
        aabb_lo,
        aabb_hi,
        safety_mm: float,
        *,
        cover_mm: float,
    ) -> float:
        """Konservative untere Schranke Punktmenge↔Glied — die Selbstkollisions-Naht.

        ``points_world`` sind Oberflächen-Samples des Gegenglieds (bzw. der
        Tool-Hülle) in Weltkoordinaten; ``cover_mm`` deren Deckungsradius.
        Dieselbe Drei-Quellen-Schranke wie :meth:`obstacle_bound`, nur ohne
        Bins/Faltung (Glied-Punktmengen sind klein).
        """
        np = _require_np()
        pts = np.asarray(points_world, dtype=float).reshape(-1, 3)
        if len(pts) == 0:
            return float("inf")
        lo = np.asarray(aabb_lo, dtype=float)
        hi = np.asarray(aabb_hi, dtype=float)
        bound = self._points_bound(pts, link_index, world_matrix, lo, hi, safety_mm, cover_mm, np)
        if bound <= safety_mm:
            self.n_grenzband += 1
        else:
            self.n_broad_skip += 1
        return float(bound)

    def _points_bound(
        self, pts_world, link_index: int, world_matrix, lo, hi, safety_mm, cover_mm, np
    ) -> float:
        """Drei-Quellen-Minimum: SDF (Top-K der nahen Punkte), AABB-Schranken des Rests."""
        d2 = _aabb_point_sq(pts_world, lo, hi, np)
        band = float(safety_mm) + float(cover_mm)
        near = d2 <= band * band
        bound = float("inf")
        far = ~near
        if far.any():
            bound = math.sqrt(float(d2[far].min())) - cover_mm
        sel = np.where(near)[0]
        if len(sel):
            if len(sel) > self.top_k:
                part = np.argpartition(d2[sel], self.top_k - 1)
                keep = sel[part[: self.top_k]]
                dropped = sel[part[self.top_k :]]
                bound = min(bound, math.sqrt(float(d2[dropped].min())) - cover_mm)
            else:
                keep = sel
            rot = world_matrix[:3, :3]
            trans = world_matrix[:3, 3]
            local = (pts_world[keep] - trans) @ rot
            dist, _ = self.glied_sdf.link(link_index).distance(local, safety_band_mm=cover_mm)
            bound = min(bound, float(dist.min()))
        return bound

    # --- Punktwolken der Glieder / der Tool-Hülle (Selbstkollision) -----------

    def link_points_local(self, link_index: int):
        """Oberflächen-Punkte der **Urteilsgeometrie** eines Glieds im Gliedframe.

        Einmalig deterministisch gesampelt (dieselbe Funktion wie die statischen
        Hindernisse, #208) und gecacht — Punkte von Glied A gegen SDF von Glied B
        ist das Selbstkollisions-Schema des SDF-Backends.
        """
        pts = self._link_points.get(link_index)
        if pts is None:
            np = _require_np()
            import trimesh

            parts = self._geo.link(link_index).judgment_parts
            arrs = [
                _mesh_surface_points(p, self.point_spacing_mm, np, trimesh) for p in parts
            ]
            pts = np.concatenate(arrs, axis=0)
            self._link_points[link_index] = pts
        return pts

    def surface_points(self, mesh):
        """Deterministische Oberflächen-Punkte eines Meshes (Tool-Hülle), gecacht."""
        key = id(mesh)
        hit = self._mesh_points.get(key)
        if hit is None:
            np = _require_np()
            import trimesh

            pts = _mesh_surface_points(mesh, self.point_spacing_mm, np, trimesh)
            # Mesh-Referenz halten: id()-Schlüssel bleibt über die Lebenszeit stabil.
            self._mesh_points[key] = (mesh, pts)
            return pts
        return hit[1]
