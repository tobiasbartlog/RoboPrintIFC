"""Kollisions-Befund je Sample: Link-Frames + Druckstand → min. Abstand (ADR-024, #126).

Tiefes Kernmodul der **Kollisionskontrolle**. Eingang sind die Glied-Frames (FK,
je Sample) und der schichtweise **Druckstand** (:mod:`fgc.collision.druckstand`),
Ausgang der minimale Abstand aller Armglieder samt Endeffektor zu den
Hindernissen je Sample, sein **Verursacher** (Glied + Hindernis) und die
verdichteten Intervalle. **Befund, kein Gate**, zweistufig: Abstand < 0 mm =
Kollision (rot), < Sicherheitsabstand = Warnung (gelb).

**Zweiphasen-Rezept (Spike S0, ADR-024 Punkt 1):** zuerst ein **billiger
Breitphasen-Filter je Glied** — die AABB des Glieds (aus der #125-Hülle,
rein rechnerisch ohne fcl) gegen die Hindernis-AABB; ihre Lücke ist eine
**untere Schranke** der echten Distanz (AABB ⊇ Hülle ⊇ Mesh). Liegt sie über dem
Sicherheitsabstand, ist das Glied sicher grün und die teure Abfrage entfällt. Nur
für **nahe** Glieder urteilt die **VHACD-Konvexzerlegung** (formtreu ±5,5 mm).
Weil der Filter eine untere Schranke ist, kann kein Sample fälschlich als sicher
durchrutschen. (Gemessen: AABB-Filter → 30 s für die 25 217-Sample-Foto-Bahn;
per-Glied-Hüllendistanz als Filter kostete das 5-fache an fcl-Aufrufen.)

**Selbstkollision** nur über **nicht-benachbarte** Gliedpaare (|i−j| ≥ 2) —
benachbarte teilen sich konstruktiv das Gelenk. **Basis↔Boden** ist ausgenommen
(erlaubter Dauerkontakt, montiert): die Basis (Glied 0) wird nicht gegen die
Hindernisse geprüft.

**Endeffektor:** provisorische Kollisionshülle = konvexe Hülle des Tool-Meshes am
TCP-Frame, als ``provisional`` geführt (offener PRD-Punkt 3 bleibt offen).

**Reinheit / Modularität.** Kein I/O, keine Kinematik-Abhängigkeit: die Frames
kommen fertig herein (``OpwKinematics.link_frames`` beim Aufrufer), die Frame-
Verkettung läuft über die *eine* Transformationsstelle
(:mod:`fgc.simulation.transform`, ADR-006). Die Distanzen sind deterministisch
(python-fcl bitgleich bei Wiederholung, Spike S0) — Goldens sind möglich. Die
Geo-Pakete werden *lazy* importiert (Core startet geo-frei).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from fgc.domain.models import Frame
from fgc.simulation import transform

if TYPE_CHECKING:  # nur für Typprüfer — kein Laufzeit-Import (geo-frei startbar)
    import trimesh

    from fgc.collision.druckstand import ObstacleSet
    from fgc.collision.robot_geometry import RobotCollisionGeometry

GEO_HINT = (
    "Die Kollisionsprüfung braucht die Geo-Extras (trimesh, python-fcl, vhacdx). "
    "Installiere sie mit  pip install fgc-core[geo]  (bereits im Projekt-venv)."
)

#: Sicherheitsabstand (mm) — weicher Lehm macht „knapp vorbei" zum Schaden.
DEFAULT_SAFETY_DISTANCE_MM = 50.0

#: Logischer Index des Endeffektors (hinter Flansch = Glied 6).
TOOL_INDEX = 7

Status = Literal["red", "yellow", "green"]


def _require_geo():
    """Lazy-Import der Geo-Pakete mit freundlichem Fehlpfad statt Import-Crash."""
    try:
        import numpy
        import trimesh
        from trimesh.collision import CollisionManager  # noqa: F401
    except ImportError as exc:  # pragma: no cover - Pfad nur ohne [geo]-Extras
        raise ImportError(GEO_HINT) from exc
    return numpy, trimesh


# ---------------------------------------------------------------------------
# Ergebnis-Typen
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SampleResult:
    """Kollisions-Befund eines einzelnen Bahn-Samples."""

    index: int
    distance_mm: float
    status: Status
    #: Verursachendes Glied (0..6, :data:`TOOL_INDEX` = Endeffektor) oder None (grün ohne Nahpaar).
    link: int | None
    #: Verursachendes Hindernis bzw. ``"link{j}"`` bei Selbstkollision, sonst None.
    against: str | None
    phase: Literal["broad", "judgment"]


@dataclass(frozen=True)
class Interval:
    """Verdichtetes Intervall gleichbleibenden Status über zusammenhängende Samples."""

    status: Status
    start_index: int
    end_index: int
    min_distance_mm: float
    worst_index: int
    link: int | None
    against: str | None


@dataclass(frozen=True)
class CollisionReport:
    """Gesamtbefund einer Bahn gegen einen (wachsenden) Druckstand."""

    samples: tuple[SampleResult, ...]
    intervals: tuple[Interval, ...]
    min_distance_mm: float
    worst_index: int
    safety_distance_mm: float
    n_red: int
    n_yellow: int
    n_green: int
    #: Der Endeffektor ist als provisorische Hülle geführt (offener PRD-Punkt 3).
    tool_provisional: bool

    def distances(self) -> list[float]:
        """Abstandskurve (mm) je Sample — Grundlage der Distanz-Goldens."""
        return [s.distance_mm for s in self.samples]


# ---------------------------------------------------------------------------
# Geometrie-Helfer
# ---------------------------------------------------------------------------


def matrix(frame: Frame):
    """Frame (pos_mm, quat [w,x,y,z]) → homogene 4×4 (mm). Nutzt die opw-Rotation.

    Öffentlicher numpy-Geometrie-Helfer (Issue #201): der Grob-Check
    (:mod:`fgc.collision.coarse`, Schwester-Modul) bringt damit die Glied-Frames
    (Basiskoordinaten) ins Wandsystem — dieselbe eine Frame→Matrix-Umrechnung wie
    hier, kein Duplikat.
    """
    import numpy as np

    from fgc.kinematics.opw import _quat_to_rot

    t = np.eye(4)
    t[:3, :3] = _quat_to_rot(frame.quat)
    t[:3, 3] = frame.pos_mm
    return t


def provisional_tool_hull(
    tool_mesh: trimesh.Trimesh, mesh_transform: Frame, tcp_frame: Frame
) -> trimesh.Trimesh:
    """Provisorische Endeffektor-Hülle: konvexe Hülle des Tool-Meshes **im TCP-Frame**.

    ``mesh_transform`` bringt das Tool-Mesh in Flanschkoordinaten (tools/*.json),
    ``tcp_frame`` ist Flansch→TCP. Die zurückgegebene Hülle liegt im TCP-Frame, ist
    also über ``worldTCP·hull`` platzierbar. Offener PRD-Punkt 3 (echte Tool-
    Kollisionsgeometrie) bleibt offen — daher ``provisional``.
    """
    _, _trimesh = _require_geo()
    mesh = tool_mesh.copy()
    mesh.apply_transform(matrix(mesh_transform))
    mesh.apply_transform(matrix(transform.invert(tcp_frame)))
    return mesh.convex_hull


def _classify(distance_mm: float, safety_mm: float) -> Status:
    if distance_mm < 0.0:
        return "red"
    if distance_mm < safety_mm:
        return "yellow"
    return "green"


def nonadjacent_pairs(indices: Sequence[int]) -> list[tuple[int, int]]:
    """Nicht-benachbarte Gliedpaare (|i−j| ≥ 2) — die Selbstkollisions-Paare.

    Benachbarte Glieder teilen sich konstruktiv das Gelenk und berühren sich
    erlaubt; sie fallen heraus. Die Basis (0) bleibt drin (Basis↔Glied2 ist eine
    echte Selbstkollision), nur Basis↔**Boden** ist anderswo ausgenommen.
    """
    idx = list(indices)
    return [
        (idx[a], idx[b])
        for a in range(len(idx))
        for b in range(a + 1, len(idx))
        if idx[b] - idx[a] >= 2
    ]


# ---------------------------------------------------------------------------
# Breitphasen-Filter (AABB) + VHACD-Manager je Glied und Hindernisgruppe
# ---------------------------------------------------------------------------


def corner_box(mesh, np):
    """Die 8 homogenen Ecken der lokalen AABB eines Meshes als 4×8-Matrix.

    Öffentlicher numpy-Geometrie-Helfer (Issue #201): der Grob-Check
    (:mod:`fgc.collision.coarse`) transformiert damit die Breitphasen-Hüllen je
    Glied und testet ihre AABB gegen das Wandvolumen — dieselbe Ecken-Bildung wie
    der Breitphasen-Filter hier.
    """
    lo, hi = mesh.bounds
    pts = [
        [x, y, z, 1.0]
        for x in (lo[0], hi[0])
        for y in (lo[1], hi[1])
        for z in (lo[2], hi[2])
    ]
    return np.asarray(pts, dtype=float).T


def _aabb_gap(alo, ahi, blo, bhi, np) -> float:
    """Euklidischer Abstand zweier achsenparalleler Boxen (0 bei Überlappung).

    Eine **untere Schranke** der echten Mesh-Distanz (AABB ⊇ Mesh): ist sie
    größer als der Sicherheitsabstand, kann das exakte Urteil nur größer sein —
    das Glied ist sicher grün, die teure VHACD-Abfrage entfällt.
    """
    d = np.maximum(np.maximum(blo - ahi, alo - bhi), 0.0)
    return float(np.sqrt(d @ d))


def _set_parts(part_mgr, names, matrix, i: int, ready: set) -> None:
    """Setzt die VHACD-Stück-Transformationen eines Glieds — genau einmal je Sample."""
    if i in ready:
        return
    for nm in names:
        part_mgr.set_transform(nm, matrix)
    ready.add(i)


def _sdf_surface(provider):
    """SDF-Backend-Oberfläche des Providers (Issue #213) per Duck-Typing — oder ``None``.

    Der Backend-Schalter FCL↔SDF ist der **injizierte Provider selbst**
    (:mod:`fgc.collision.backend`, App-Ebene): ein schlichter Callable urteilt
    wie bisher über den FCL-Referenzpfad (Altläufe byte-identisch, US 12); ein
    :class:`fgc.collision.sdf_provider.SdfObstacleProvider` bringt zusätzlich
    die Punkt-gegen-Glied-SDF-Inversion mit, die hier als **konservative
    Vorstufe** vor dem FCL-Nachprüfer läuft.
    """
    needed = (
        "prime",
        "obstacle_bound",
        "points_vs_link_bound",
        "link_points_local",
        "surface_points",
        "link_cover_mm",
    )
    return provider if all(hasattr(provider, name) for name in needed) else None


def _sdf_self_bound(sdf, i: int, j: int, mats, aabb_i, tool_hull, safety_mm: float):
    """Selbstkollisions-Schranke im Punkt-Schema: Punkte von Glied ``j`` gegen SDF von ``i``.

    ``j`` ist der höhere Index des nicht-benachbarten Paars; für den Endeffektor
    (``TOOL_INDEX``, kein eigenes SDF) liefert die Tool-Hülle die Punktseite.
    """
    if j == TOOL_INDEX:
        pts_local = sdf.surface_points(tool_hull)
    else:
        pts_local = sdf.link_points_local(j)
    m = mats[j]
    pts_world = pts_local @ m[:3, :3].T + m[:3, 3]
    return sdf.points_vs_link_bound(
        pts_world, i, mats[i], aabb_i[0], aabb_i[1], safety_mm, cover_mm=sdf.link_cover_mm
    )


def _obstacle_groups(obstacle_set: ObstacleSet, freizone_mm: float, np):
    """Hindernisse zu Gruppen ``[(manager, exempt, aabb_lo, aabb_hi), …]`` bündeln.

    Ohne Freizone landen alle Hindernisse in *einer* Gruppe; mit Freizone liegt das
    freizone-ausgenommene (wachsende) Teil separat, damit ``check`` es je Sample im
    Freizonen-Radius ausnehmen kann. Je Gruppe die AABB für den Breitphasen-Filter.
    """
    _require_geo()
    from trimesh.collision import CollisionManager

    split = freizone_mm > 0.0
    buckets: dict[bool, list] = {False: [], True: []}
    for obs in obstacle_set.obstacles:
        buckets[bool(split and obs.freizone_exempt)].append(obs)

    groups = []
    for exempt in (False, True):
        obs_list = buckets[exempt]
        if not obs_list:
            continue
        mgr = CollisionManager()
        lo = np.full(3, np.inf)
        hi = np.full(3, -np.inf)
        for obs in obs_list:
            mgr.add_object(obs.name, obs.mesh)
            b = obs.mesh.bounds
            lo = np.minimum(lo, b[0])
            hi = np.maximum(hi, b[1])
        groups.append((mgr, exempt, lo, hi))
    return groups


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------


def find_collisions(
    geo: RobotCollisionGeometry,
    base_frame: Frame,
    link_frames_per_sample: Sequence[Sequence[Frame]],
    sample_layers: Sequence[int],
    obstacle_provider: Callable[[int], ObstacleSet],
    *,
    tcp_frame: Frame | None = None,
    tool_hull: trimesh.Trimesh | None = None,
    safety_distance_mm: float = DEFAULT_SAFETY_DISTANCE_MM,
    self_collision: bool = True,
) -> CollisionReport:
    """Prüft eine Bahn gegen den wachsenden Druckstand und liefert den Befund.

    ``link_frames_per_sample`` = je Sample die 7 Glied-Frames in **Basis**-
    koordinaten (``OpwKinematics.link_frames``; Index 0 = Basis … 6 = Flansch).
    ``base_frame`` = Basis in Welt-/Wandkoordinaten (Trajektorien-``meta.base_frame``);
    die Glieder werden über ``compose(base_frame, link)`` in Weltkoordinaten
    verkettet — dieselbe eine Transformationsstelle wie die Simulation.

    ``sample_layers`` = Schicht-Index je Sample **aus dem Toolpath**
    (:func:`fgc.collision.druckstand.layer_per_sample`); ``obstacle_provider``
    liefert je Schicht den (gecachten) Hindernissatz. ``tcp_frame`` + ``tool_hull``
    ergänzen den provisorischen Endeffektor am TCP; fehlen sie, prüft nur der Arm.

    **SDF-Backend (Issue #213):** trägt der injizierte Provider die
    SDF-Abfrageflächen (:func:`_sdf_surface`), läuft je Glied zuerst die
    Punkt-gegen-Glied-SDF-Inversion als konservative untere Schranke; nur im
    **Grenzband** (Schranke ≤ Sicherheitsabstand) urteilt der unveränderte
    FCL-Referenzpfad nach — rote/gelbe Befunde bleiben dadurch byte-identisch
    zur Referenz (US 2/16). Die Selbstkollision läuft im selben Punkt-Schema
    (Punkte von Glied A gegen SDF von Glied B); die frühere bedingungslose
    FCL-Paar-Distanz entfällt dort im SDF-Backend. Der Endeffektor (ohne
    eigenes SDF) urteilt gegen Hindernisse weiter über den Referenzpfad.
    """
    np, _ = _require_geo()
    from trimesh.collision import CollisionManager

    # Basis (Glied 0) nie gegen Hindernisse — Basis↔Boden ist erlaubter Dauerkontakt.
    check_links = list(range(1, len(geo.links))) + ([TOOL_INDEX] if tool_hull is not None else [])
    self_links = tuple(range(len(geo.links))) + ((TOOL_INDEX,) if tool_hull is not None else ())
    self_pairs = nonadjacent_pairs(self_links) if self_collision else []

    # Je Glied: lokale AABB-Ecken als **Breitphasen-Filter** (ADR-024 Punkt 1 —
    # „billiger AABB-Filter je Glied begrenzt die exakten FCL-Abfragen"; abgeleitet
    # aus der #125-Hülle, also weiterhin eine untere Schranke der echten Distanz)
    # plus ein VHACD-Manager je Glied (Urteilsgeometrie, nur bei Nähe befragt). Der
    # Endeffektor nutzt seine provisorische Hülle als Ecke UND als Urteilsgeometrie.
    corners: dict[int, object] = {}
    part_of: dict[int, CollisionManager] = {}
    part_names: dict[int, list[str]] = {}
    for i in range(len(geo.links)):
        lk = geo.link(i)
        corners[i] = corner_box(lk.broadphase_hull, np)
        pm = CollisionManager()
        names = []
        for p, part in enumerate(lk.judgment_parts):
            nm = f"{i}#{p}"
            pm.add_object(nm, part)
            names.append(nm)
        part_of[i] = pm
        part_names[i] = names
    if tool_hull is not None:
        corners[TOOL_INDEX] = corner_box(tool_hull, np)
        tm = CollisionManager()
        tm.add_object("tool", tool_hull)
        part_of[TOOL_INDEX] = tm
        part_names[TOOL_INDEX] = ["tool"]

    # SDF-Backend? Punktwolke + Bins einmal je Bahn bauen (Schicht-Views per Präfix).
    sdf = _sdf_surface(obstacle_provider)
    if sdf is not None and len(link_frames_per_sample):
        sdf.prime(max(int(layer) for layer in sample_layers))

    # Hindernisgruppen je Schicht cachen (Rebuild je Schicht, nicht je Sample):
    # (freizone, [(manager, exempt, aabb_lo, aabb_hi), …]).
    group_cache: dict[int, tuple] = {}

    def groups_for(layer_index: int):
        hit = group_cache.get(layer_index)
        if hit is None:
            oset = obstacle_provider(layer_index)
            hit = (oset.freizone_radius_mm, _obstacle_groups(oset, oset.freizone_radius_mm, np))
            group_cache[layer_index] = hit
        return hit

    results: list[SampleResult] = []

    for k, link_frames in enumerate(link_frames_per_sample):
        # Weltframes der Glieder (Basis-Verkettung über die eine Transformationsstelle).
        world = [transform.compose(base_frame, lf) for lf in link_frames]
        mats = {i: matrix(world[i]) for i in range(len(world))}

        # Druckpunkt am TCP (worldFlansch ∘ tcp): Anker der **Freizone**. Er hängt
        # nur am TCP-Frame, nicht am Endeffektor-Mesh — so wirkt die Freizone auch
        # arm-only (ohne provisorische Tool-Hülle, Issue #127). Die Tool-Hülle wird
        # zusätzlich am selben TCP platziert, falls vorhanden.
        print_point = None
        if tcp_frame is not None:
            world_tcp = transform.compose(world[6], tcp_frame)
            print_point = np.asarray(world_tcp.pos_mm, dtype=float)
            if tool_hull is not None:
                mats[TOOL_INDEX] = matrix(world_tcp)

        # Welt-AABB je geprüftem Glied (Ecken durch die Pose transformiert).
        aabb: dict[int, tuple] = {}
        for i in set(check_links) | set(self_links):
            wc = (mats[i] @ corners[i])[:3]
            aabb[i] = (wc.min(axis=1), wc.max(axis=1))

        freizone, groups = groups_for(int(sample_layers[k]))
        parts_ready: set[int] = set()
        best: tuple[float, int | None, str | None, str] = (float("inf"), None, None, "broad")

        # --- Arm↔Hindernisse: AABB-Breitphase, VHACD-Urteil nur bei Nähe ---
        for i in check_links:
            wlo, whi = aabb[i]
            # SDF-Backend (Issue #213): konservative Punkt-gegen-Glied-SDF-Schranke,
            # lazy je Glied — nur falls eine Gruppe die AABB-Breitphase passiert.
            # Der Endeffektor hat kein eigenes SDF und bleibt im Referenzpfad.
            sdf_bound = None
            for gm, exempt, glo, ghi in groups:
                gap = _aabb_gap(wlo, whi, glo, ghi, np)
                if gap > safety_distance_mm:  # AABB-Lücke > Sicherheit ⇒ Glied sicher grün
                    if gap < best[0]:
                        best = (float(gap), None, None, "broad")
                    continue
                # Transform-Historie bleibt exakt die der FCL-Referenz: fcl-Distanzen
                # *penetrierender* Paare hängen an der set_transform-Historie des
                # Managers (Early-Exit im AABB-Baum) — nur die Distanz-ABFRAGE ist
                # read-only. Darum setzt auch das SDF-Backend die Transformationen
                # nach dem Referenz-Muster und spart nur Abfragen (Byte-Identität
                # der Eindringtiefen, US 2; verifiziert 2026-07-14).
                _set_parts(part_of[i], part_names[i], mats[i], i, parts_ready)
                if sdf is not None and i != TOOL_INDEX:
                    if sdf_bound is None:
                        sdf_bound = sdf.obstacle_bound(
                            int(sample_layers[k]), i, mats[i], wlo, whi, safety_distance_mm
                        )
                    if sdf_bound > safety_distance_mm:  # sicher grün — Abfrage entfällt
                        if sdf_bound < best[0]:
                            best = (float(sdf_bound), None, None, "broad")
                        continue
                dj, jn, jd = part_of[i].min_distance_other(
                    gm, return_names=True, return_data=True
                )
                if exempt and _in_freizone(jd, jn, print_point, freizone, np):
                    continue
                if dj < best[0]:
                    best = (float(dj), i, jn[1], "judgment")

        # --- Selbstkollision (nicht-benachbarte Paare) ---------------------
        if self_collision:
            for i, j in self_pairs:
                if _aabb_gap(*aabb[i], *aabb[j], np) > safety_distance_mm:
                    continue  # Paar sicher getrennt (arm-intern) — kein Beitrag
                # Transform-Historie wie die Referenz (s. Hindernis-Schleife), dann
                # die Selbstkollision im Punkt-Schema (Punkte von Glied j gegen SDF
                # von Glied i, #213): die frühere bedingungslose FCL-Paar-Distanz
                # entfällt im SDF-Backend — FCL urteilt Paare nur noch im Grenzband.
                _set_parts(part_of[i], part_names[i], mats[i], i, parts_ready)
                _set_parts(part_of[j], part_names[j], mats[j], j, parts_ready)
                if sdf is not None:
                    bound = _sdf_self_bound(
                        sdf, i, j, mats, aabb[i], tool_hull, safety_distance_mm
                    )
                    if bound > safety_distance_mm:
                        continue  # sicher getrennt — exakte Paar-Abfrage entfällt
                d = part_of[i].min_distance_other(part_of[j])
                if d < best[0]:
                    best = (float(d), i, f"link{j}", "judgment")

        dist = best[0]
        if dist == float("inf"):
            results.append(SampleResult(k, dist, "green", None, None, "broad"))
        else:
            results.append(
                SampleResult(
                    k, dist, _classify(dist, safety_distance_mm), best[1], best[2], best[3]
                )
            )

    return _report(results, safety_distance_mm, tool_provisional=tool_hull is not None)


def _in_freizone(data, names, print_point, freizone_mm: float, np) -> bool:
    """Liegt der nächste Punkt auf dem ausgenommenen Hindernis in der Freizone?"""
    if print_point is None or freizone_mm <= 0.0:
        return False
    try:
        pt = np.asarray(data.point(names[1]), dtype=float)
    except Exception:  # pragma: no cover - defensiv, falls fcl keinen Punkt liefert
        return False
    return bool(np.linalg.norm(pt - print_point) <= freizone_mm)


def _report(
    results: list[SampleResult], safety_mm: float, *, tool_provisional: bool
) -> CollisionReport:
    """Verdichtet die Sample-Befunde zu Intervallen + Kennzahlen."""
    intervals: list[Interval] = []
    if results:
        run_start = 0
        for k in range(1, len(results) + 1):
            end = k == len(results)
            if end or results[k].status != results[run_start].status:
                span = results[run_start:k]
                worst = min(span, key=lambda s: s.distance_mm)
                intervals.append(
                    Interval(
                        status=span[0].status,
                        start_index=run_start,
                        end_index=k - 1,
                        min_distance_mm=worst.distance_mm,
                        worst_index=worst.index,
                        link=worst.link,
                        against=worst.against,
                    )
                )
                run_start = k

    finite = [s for s in results if s.distance_mm != float("inf")]
    worst = min(finite, key=lambda s: s.distance_mm, default=None)
    return CollisionReport(
        samples=tuple(results),
        intervals=tuple(intervals),
        min_distance_mm=worst.distance_mm if worst else float("inf"),
        worst_index=worst.index if worst else -1,
        safety_distance_mm=safety_mm,
        n_red=sum(1 for s in results if s.status == "red"),
        n_yellow=sum(1 for s in results if s.status == "yellow"),
        n_green=sum(1 for s in results if s.status == "green"),
        tool_provisional=tool_provisional,
    )
