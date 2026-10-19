"""Unabhaengiges Kollisions-Orakel: vorzeichenbehaftete Abstaende mit Coal auf Roh-Meshes.

Geometrie (SPEC §5.1), alles aus den Original-Assets, keine Konvexzerlegung:
- Glieder `base_link` ... `link_6`: Kollisionsmeshes der URDF (.dae, Knoten-Transformationen und
  `scale` angewandt, m -> mm), im Frame des jeweiligen Glieds.
- Werkzeug: `tools/30gut.stl` ueber `mesh_transform` im Flansch-Frame. Die Dreiecke werden an der Kugel
  mit Radius r_free um den TCP aufgeteilt (Dreiecke, die die Kugel schneiden, werden bis auf 1 mm
  Kantenlaenge unterteilt und nach Schwerpunkt zugeordnet): innen `nozzle_tip`, aussen `tool_body`.
- Boden: Halbraum z <= 0 in W. Tisch: `workstations/doosantisch.stl` in W.
- Druckstand bei k fertigen Schichten: Teil-Solid (P) ∩ {z_P <= k*h}, nach W transformiert.

Abstand: Branch-and-Bound ueber eine zweistufige Hierarchie. Jedes Mesh wird in Wuerfelzellen
(Kantenlaenge `chunk_mm`) zerlegt; je Zelle gibt es eine Huellkugel, die konvexe Huelle (Coal `Convex`,
untere Schranke des Abstands) und ein Coal-BVH (OBBRSS) der Original-Dreiecke (lange Dreiecke vorher
auf <= `max_edge_mm` unterteilt, das aendert die Flaeche nicht). Der Abstand zwischen zwei Meshes ist
das Minimum der exakten BVH-Abstaende ueber alle Zellpaare; Zellpaare, deren Schranke nicht unter dem
bisher besten Wert liegt, werden uebersprungen. Ergebnis: exakter Abstand der Dreiecksflaechen
(Coal-Toleranz), Boden exakt ueber die Huellpunkte.

Eindringtiefe (Vorzeichen negativ) fuer sich schneidende oder enthaltene Paare: untere Schranke der
translatorischen Eindringtiefe, max ueber die Ecken eines Meshes, die in einem geschlossenen Solid des
anderen liegen, ihres Abstands zu dessen Oberflaeche (beide Richtungen, soweit geschlossene Solids
vorhanden sind: Glieder je Mesh-Komponente, Tischkoerper, Druckstand; Werkzeug ist offen und nur
"eindringend"). Ein Punkt in Tiefe p erzwingt eine Verschiebung >= p, also ist der Wert nie tiefer als
die wahre Eindringtiefe. Schneiden sich Dreiecke ohne eingeschlossene Ecke, gilt d = -1e-3 mm.
Vollstaendiges Enthaltensein ohne Dreiecksschnitt wird ueber Punkt-im-Solid-Tests einer Ecke je
Komponente erkannt, wenn sich die konvexen Huellen ueberlappen.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import coal
import numpy as np
import trimesh
from trimesh.remesh import subdivide_to_size

from verify.oracle.robot_oracle import (
    LINK_NAMES,
    ROOT,
    default_robot,
    urdf_collision_meshes,
    workstation_frames,
)

TABLE_STL = ROOT / "workstations" / "doosantisch.stl"
TOOL_DIR = ROOT / "tools"

MOVING_FLOOR_TABLE = ("link_2", "link_3", "link_4", "link_5", "link_6", "tool_body", "nozzle_tip")
MOVING_PRINTED = (*LINK_NAMES, "tool_body")

# Statusregel (SPEC §2, Nutzerentscheidung 19.10.2026): Diese Paare liegen konstruktiv konstant bei
# ~33 mm < d_target. Sie zaehlen fuer collision und d_hard, nicht fuer die d_target-Schwelle.
# Weitere Paare nur nach Freigabe durch den Nutzer (SPEC §2).
RELAXED_PAIRS = frozenset({frozenset(("base_link", "link_2"))})


def is_relaxed(pair) -> bool:
    """Gehoert das (ungeordnete) Paar zu den Paaren mit gelockerter Statusregel?"""
    return pair is not None and frozenset(pair) in RELAXED_PAIRS


def checked_pairs() -> list[tuple[str, str]]:
    """Genau die Paare aus SPEC §5.1 als (Glied, Hindernis)."""
    pairs: list[tuple[str, str]] = []
    pairs += [(a, "floor") for a in MOVING_FLOOR_TABLE]
    pairs += [(a, "table") for a in MOVING_FLOOR_TABLE]
    pairs += [(a, "printed") for a in MOVING_PRINTED]
    for i in range(len(LINK_NAMES)):
        for j in range(i + 2, len(LINK_NAMES)):
            pairs.append((LINK_NAMES[j], LINK_NAMES[i]))
    pairs += [("tool_body", n) for n in LINK_NAMES[:5]]
    return pairs


@dataclass
class Contact:
    d_mm: float
    pair: tuple[str, str]
    witness_W: tuple[np.ndarray, np.ndarray]
    exact: bool = True  # False: nur untere Schranke (d >= cap), siehe CollisionOracle.distance


# --------------------------------------------------------------------------- Geometrie-Bausteine


def _bvh(vertices: np.ndarray, faces: np.ndarray) -> coal.BVHModelOBBRSS:
    b = coal.BVHModelOBBRSS()
    b.beginModel(len(faces), len(vertices))
    b.addVertices(np.ascontiguousarray(vertices, dtype=float))
    b.addTriangles(np.ascontiguousarray(faces, dtype=np.int64))
    b.endModel()
    return b


def _hull(points: np.ndarray):
    """Konvexe Huelle als Coal-`Convex` (scipy/Qhull; flache Mengen mit QJ), None wenn entartet."""
    from scipy.spatial import ConvexHull, QhullError

    pts = np.unique(np.asarray(points, dtype=float), axis=0)
    if len(pts) < 4:
        return None
    for opts in (None, "QJ"):
        try:
            h = ConvexHull(pts, qhull_options=opts) if opts else ConvexHull(pts)
            break
        except (QhullError, ValueError):
            h = None
    if h is None:
        return None
    idx = {int(v): i for i, v in enumerate(h.vertices)}
    vec = coal.StdVec_Vec3s()
    for v in pts[h.vertices]:
        vec.append(np.array(v, dtype=float))
    tris = coal.StdVec_Triangle()
    for a, b, c in h.simplices:
        tris.append(coal.Triangle(idx[int(a)], idx[int(b)], idx[int(c)]))
    return coal.Convex(vec, tris)


class Chunk:
    __slots__ = ("bvh", "convex", "c", "r")

    def __init__(self, V: np.ndarray, F: np.ndarray):
        used = np.unique(F)
        remap = np.full(len(V), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        v = V[used]
        self.bvh = _bvh(v, remap[F])
        self.convex = _hull(v)
        lo, hi = v.min(0), v.max(0)
        self.c = 0.5 * (lo + hi)
        self.r = float(np.linalg.norm(v - self.c, axis=1).max())


class Body:
    """Starrer Dreieckskoerper in einem lokalen Frame, zellweise fuer Branch-and-Bound aufbereitet."""

    def __init__(self, name: str, mesh: trimesh.Trimesh, solids: list[trimesh.Trimesh] | None = None,
                 chunk_mm: float = 80.0, max_edge_mm: float = 20.0):
        self.name = name
        mesh = trimesh.Trimesh(np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces), process=False)
        mesh.remove_unreferenced_vertices()
        V = np.asarray(mesh.vertices, dtype=float)
        F = np.asarray(mesh.faces, dtype=np.int64)
        self.vertices = V
        if max_edge_mm:
            V, F = subdivide_to_size(V, F, max_edge=max_edge_mm, max_iter=20)
        cent = V[F].mean(axis=1)
        keys = np.floor(cent / chunk_mm).astype(np.int64)
        _, inv = np.unique(keys, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        self.chunks = [Chunk(V, F[inv == g]) for g in range(inv.max() + 1)]
        self.cc = np.array([c.c for c in self.chunks])
        self.cr = np.array([c.r for c in self.chunks])
        lo, hi = V.min(0), V.max(0)
        self.c = 0.5 * (lo + hi)
        self.r = float(np.linalg.norm(V - self.c, axis=1).max())
        self.convex = _hull(V)
        hull = trimesh.convex.convex_hull(V) if len(V) >= 4 else None
        self.hull_vertices = np.asarray(hull.vertices) if hull is not None else V
        self.solids = [s for s in (solids or []) if s.is_watertight]
        comps = mesh.split(only_watertight=False) if len(mesh.faces) else []
        self.probes = np.array([c.vertices[0] for c in comps]) if len(comps) else V[:1]


def _load_mesh(path: Path) -> trimesh.Trimesh:
    m = trimesh.load(str(path), force="mesh", process=True)
    m.merge_vertices()
    return m


def _transform(m: trimesh.Trimesh, T: np.ndarray, scale=None) -> trimesh.Trimesh:
    v = np.asarray(m.vertices, dtype=float)
    if scale is not None:
        v = v * np.asarray(scale, dtype=float)
    v = v @ T[:3, :3].T + T[:3, 3]
    return trimesh.Trimesh(v, np.asarray(m.faces), process=False)


def _watertight_components(m: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    return [c for c in m.split(only_watertight=False) if c.is_watertight and c.volume > 1.0]


def split_tool(tool_F: trimesh.Trimesh, tcp_F: np.ndarray, r_free: float
               ) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Werkzeugmesh (Frame F) -> (tool_body, nozzle_tip) an der Kugel r_free um den TCP."""
    V, F = np.asarray(tool_F.vertices), np.asarray(tool_F.faces)
    inside_v = np.linalg.norm(V - tcp_F, axis=1) <= r_free
    n_in = inside_v[F].sum(axis=1)
    tip_f, body_f, mixed = F[n_in == 3], F[n_in == 0], F[(n_in > 0) & (n_in < 3)]
    parts_tip, parts_body = [trimesh.Trimesh(V, tip_f, process=False)], [trimesh.Trimesh(V, body_f,
                                                                                         process=False)]
    if len(mixed):
        mv, mf = subdivide_to_size(V, mixed, max_edge=1.0, max_iter=40)
        cin = np.linalg.norm(mv[mf].mean(axis=1) - tcp_F, axis=1) <= r_free
        parts_tip.append(trimesh.Trimesh(mv, mf[cin], process=False))
        parts_body.append(trimesh.Trimesh(mv, mf[~cin], process=False))
    tip = trimesh.util.concatenate([p for p in parts_tip if len(p.faces)])
    body = trimesh.util.concatenate([p for p in parts_body if len(p.faces)])
    return body, tip


def clip_below(mesh: trimesh.Trimesh, z: float) -> trimesh.Trimesh | None:
    """mesh ∩ {z' <= z} als geschlossenes Solid (manifold3d, Rueckfall trimesh slice_plane mit Deckel)."""
    lo, hi = mesh.bounds
    if z <= lo[2] + 1e-9:
        return None
    if z >= hi[2] - 1e-9:
        return mesh.copy()
    try:
        import manifold3d as mf

        man = mf.Manifold(mf.Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                                  tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))
        if man.status() != mf.Error.NoError or man.is_empty():
            raise ValueError("kein Manifold")
        cut = man.trim_by_plane((0.0, 0.0, -1.0), -float(z))
        out = cut.to_mesh()
        res = trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3].astype(float),
                              np.asarray(out.tri_verts, dtype=np.int64), process=True)
        if len(res.faces):
            return res
    except Exception:  # noqa: BLE001 - Rueckfall unten
        pass
    res = mesh.slice_plane(plane_origin=[0, 0, z], plane_normal=[0, 0, -1], cap=True)
    return res if res is not None and len(res.faces) else None


# --------------------------------------------------------------------------- Welt


@dataclass
class StaticGeometry:
    links: dict[str, Body]
    tool_body: Body
    nozzle_tip: Body
    table: Body


@lru_cache(maxsize=4)
def static_geometry(r_free_mm: float = 40.0, chunk_mm: float = 80.0) -> StaticGeometry:
    """Glieder, Werkzeug (geteilt an r_free) und Tisch aus den Default-Assets; einmal je Prozess."""
    return _build_static(float(r_free_mm), float(chunk_mm))


def _build_static(r_free_mm: float, chunk_mm: float) -> StaticGeometry:
    robot = default_robot()
    links: dict[str, Body] = {}
    for name, items in urdf_collision_meshes(robot.urdf_path).items():
        if name not in LINK_NAMES:
            continue
        meshes = [_transform(_load_mesh(p), T, scale) for p, T, scale in items]
        solids = [c for m in meshes for c in _watertight_components(m)]
        links[name] = Body(name, trimesh.util.concatenate(meshes), solids, chunk_mm)
    tool_F = _transform(_load_mesh(TOOL_DIR / robot.tool["mesh"]), robot.T_F_toolmesh)
    body, tip = split_tool(tool_F, robot.T_FT[:3, 3], float(r_free_mm))
    table = _load_mesh(TABLE_STL)
    return StaticGeometry(links, Body("tool_body", body, None, chunk_mm),
                          Body("nozzle_tip", tip, None, chunk_mm),
                          Body("table", table, _watertight_components(table), 2 * chunk_mm, max_edge_mm=50.0))


class CollisionOracle:
    """Kollisionswelt nach SPEC §5.1 fuer ein Teil. Alle Ausgaben in W, mm.

    Roboter, Werkzeug und Workstation kommen aus den Default-Assets (URDF, tools/30gut.json,
    workstations/doosantisch.json); das Teil als Solid in Frame P mit T_WP."""

    def __init__(self, part_mesh_P: trimesh.Trimesh | None = None, T_WP: np.ndarray | None = None,
                 layer_height_mm: float = 10.0, r_free_mm: float = 40.0, chunk_mm: float = 80.0):
        self.robot = default_robot()
        self.T_WB = workstation_frames()[0]
        self.h = float(layer_height_mm)
        self.r_free = float(r_free_mm)
        self.chunk_mm = chunk_mm
        g = static_geometry(float(r_free_mm), float(chunk_mm))
        self.links, self.tool_body, self.nozzle_tip, self.table = g.links, g.tool_body, g.nozzle_tip, g.table
        self._part_P = part_mesh_P
        self.T_WP = None if T_WP is None else np.asarray(T_WP, dtype=float)
        self._printed: dict[int, Body | None] = {}
        self.pairs = checked_pairs()

    # Druckstand ---------------------------------------------------------------
    def printed(self, k: int) -> Body | None:
        k = int(k)
        if k not in self._printed:
            body = None
            if self._part_P is not None and k > 0:
                clipped = clip_below(self._part_P, k * self.h)
                if clipped is not None:
                    cw = _transform(clipped, self.T_WP)
                    body = Body("printed", cw, [cw], self.chunk_mm, max_edge_mm=25.0)
            self._printed[k] = body
        return self._printed[k]

    # Posen -------------------------------------------------------------------
    def body_poses(self, q) -> dict[str, np.ndarray]:
        Ts = self.robot.fk_links(q)
        poses = {n: self.T_WB @ T for n, T in zip(LINK_NAMES, Ts, strict=True)}
        poses["tool_body"] = poses["link_6"]
        poses["nozzle_tip"] = poses["link_6"]
        return poses

    def _body(self, name: str, k: int) -> Body | None:
        if name in self.links:
            return self.links[name]
        return {"tool_body": self.tool_body, "nozzle_tip": self.nozzle_tip, "table": self.table,
                "printed": self.printed(k) if name == "printed" else None}.get(name)

    # Abstand -----------------------------------------------------------------
    def status_contact(self, q, layer: int, d_hard: float, depth: bool = True) -> Contact:
        """d_status nach SPEC §2 (Nutzerentscheidung 19.10.2026): Minimum ueber alle Paare ausser
        RELAXED_PAIRS; deren Abstand zaehlt nur, wenn er < d_hard ist."""
        main = [p for p in self.pairs if not is_relaxed(p)]
        rel = [p for p in self.pairs if is_relaxed(p)]
        c = self.distance(q, layer, depth=depth, pairs=main)
        if rel:
            r = self.distance(q, layer, depth=depth, pairs=rel)
            if r.d_mm < d_hard and r.d_mm < c.d_mm:
                return r
        return c

    def distance(self, q, layer: int, cap: float | None = None, depth: bool = True,
                 pairs: list[tuple[str, str]] | None = None) -> Contact:
        """Kleinster vorzeichenbehafteter Abstand aller Paare aus SPEC §5.1 fuer Pose q, k = layer.

        - `cap`: Die Suche darf abbrechen, sobald feststeht, dass d >= cap ist; dann ist
          `exact = False` und `d_mm` eine untere Schranke >= cap.
        - `depth=False`: Bei Durchdringung wird nur das Vorzeichen bestimmt (d = -1e-3 mm), ohne
          Eindringtiefe. Fuer die Statusvergabe genuegt das.
        - `pairs`: nur diese Paare (Default alle aus SPEC §5.1)."""
        use = self.pairs if pairs is None else pairs
        poses = self.body_poses(q)
        I4 = np.eye(4)
        bound = np.inf if cap is None else float(cap)
        best = np.inf
        best_pair: tuple[str, str] = ("", "")
        best_w = (np.full(3, np.nan), np.full(3, np.nan))

        # Boden: exakt ueber die Huellpunkte (Minimum einer linearen Funktion liegt in einer Ecke)
        for a, b in use:
            if b != "floor":
                continue
            A = self._body(a, layer)
            T = poses[a]
            hv = A.hull_vertices @ T[:3, :3].T + T[:3, 3]
            i = int(np.argmin(hv[:, 2]))
            if hv[i, 2] < best:
                best = float(hv[i, 2])
                best_pair = (a, "floor")
                best_w = (hv[i].copy(), np.array([hv[i, 0], hv[i, 1], 0.0]))

        dreq = coal.DistanceRequest()
        creq = coal.CollisionRequest()
        tfs: dict[str, coal.Transform3s] = {}

        def tf(name: str, T: np.ndarray) -> coal.Transform3s:
            if name not in tfs:
                tfs[name] = coal.Transform3s(np.ascontiguousarray(T[:3, :3]), np.ascontiguousarray(T[:3, 3]))
            return tfs[name]

        # Paarebene: Huellkugeln, dann konvexe Huellen; Reihenfolge aufsteigend nach Huellenabstand
        centers: dict[str, np.ndarray] = {}
        cand = []
        for a, b in use:
            if b == "floor":
                continue
            A, B = self._body(a, layer), self._body(b, layer)
            if A is None or B is None:
                continue
            Ta, Tb = poses.get(a, I4), poses.get(b, I4)
            if a not in centers:
                centers[a] = Ta[:3, :3] @ A.c + Ta[:3, 3]
            if b not in centers:
                centers[b] = Tb[:3, :3] @ B.c + Tb[:3, 3]
            lb = float(np.sqrt(((centers[a] - centers[b]) ** 2).sum())) - A.r - B.r
            if _prune(lb, min(best, bound)):
                continue
            ta = tf("tool" if a in ("tool_body", "nozzle_tip") else a, Ta)
            tb = tf(b if b in self.links else "world", Tb)
            if A.convex is not None and B.convex is not None:
                lb = max(lb, coal.distance(A.convex, ta, B.convex, tb, dreq, coal.DistanceResult()))
            cand.append((lb, a, b, A, B, Ta, Tb, ta, tb))
        cand.sort(key=lambda x: x[0])

        colliding: list[tuple] = []
        overlap_hulls: list[tuple] = []
        for lb, a, b, A, B, Ta, Tb, ta, tb in cand:
            lim = min(best, bound)
            if _prune(lb, lim):
                break
            if lb <= 0:
                overlap_hulls.append((a, b, A, B, Ta, Tb))
            # Zellebene, lazy aufsteigend nach Kugelschranke
            cwa = A.cc @ Ta[:3, :3].T + Ta[:3, 3]
            cwb = B.cc @ Tb[:3, :3].T + Tb[:3, 3]
            D = (np.linalg.norm(cwa[:, None, :] - cwb[None, :, :], axis=2)
                 - A.cr[:, None] - B.cr[None, :]).ravel()
            sel = np.flatnonzero(D < lim) if lim > 0 else np.flatnonzero(D <= 0)
            if not len(sel):
                continue
            nB = len(B.chunks)
            pair_hit = False
            for f in _ascending(D, sel):
                lim = min(best, bound)
                if _prune(D[f], lim):
                    break
                ci, cj = A.chunks[f // nB], B.chunks[f % nB]
                if ci.convex is not None and cj.convex is not None:
                    lb3 = coal.distance(ci.convex, ta, cj.convex, tb, dreq, coal.DistanceResult())
                    if _prune(lb3, lim):
                        continue
                if best <= 0:  # Kollision bekannt: nur noch weitere Kollisionen suchen
                    if coal.collide(ci.bvh, ta, cj.bvh, tb, creq, coal.CollisionResult()):
                        pair_hit = True
                        break
                    continue
                res = coal.DistanceResult()
                d = coal.distance(ci.bvh, ta, cj.bvh, tb, dreq, res)
                if d <= 0:
                    pair_hit = True
                    best, best_pair = 0.0, (a, b)
                    best_w = (np.array(res.getNearestPoint1()), np.array(res.getNearestPoint2()))
                    break
                if d < best:
                    best, best_pair = float(d), (a, b)
                    best_w = (np.array(res.getNearestPoint1()), np.array(res.getNearestPoint2()))
            if pair_hit:
                colliding.append((a, b, A, B, Ta, Tb))

        # Enthaltensein ohne Dreiecksschnitt (nur moeglich, wenn sich die Huellen ueberlappen)
        hit_keys = {(c[0], c[1]) for c in colliding}
        for item in overlap_hulls:
            a, b, A, B, Ta, Tb = item
            if (a, b) not in hit_keys and (_contained(A, Ta, B, Tb) or _contained(B, Tb, A, Ta)):
                colliding.append(item)
                if best > 0:
                    best, best_pair = 0.0, (a, b)
                    best_w = (Ta[:3, :3] @ A.probes[0] + Ta[:3, 3], Ta[:3, :3] @ A.probes[0] + Ta[:3, 3])
        # Eindringtiefe
        for a, b, A, B, Ta, Tb in colliding:
            if depth:
                dpt, pa, pb = penetration_lower_bound(A, Ta, B, Tb)
            else:
                dpt, pa, pb = 0.0, None, None
            dd = -max(dpt, 1e-3)
            if dd < best:
                best, best_pair = dd, (a, b)
                if pa is not None:
                    best_w = (pa, pb)
        exact = not (cap is not None and best >= cap)
        if not np.isfinite(best):
            best, exact = float(bound), False
        return Contact(float(best), best_pair, best_w, exact)


def _ascending(D: np.ndarray, sel: np.ndarray, head: int = 256):
    """Indizes aus sel aufsteigend nach D; bei vielen Kandidaten erst die kleinsten `head` sortiert."""
    if len(sel) <= head:
        yield from sel[np.argsort(D[sel], kind="stable")]
        return
    part = np.argpartition(D[sel], head)
    first, rest = sel[part[:head]], sel[part[head:]]
    yield from first[np.argsort(D[first], kind="stable")]
    yield from rest[np.argsort(D[rest], kind="stable")]


def _prune(lb: float, lim: float) -> bool:
    """Schranke reicht zum Verwerfen: lb >= bester Wert (bzw. > 0, sobald eine Kollision bekannt ist)."""
    return lb >= lim if lim > 0 else lb > 0


# --------------------------------------------------------------------------- Punkt im Solid


def winding_inside(tris: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Verallgemeinerte Windungszahl (Van Oosterom/Strackee) je Punkt; innen bei |w| > 0,5.
    tris: (F, 3, 3), pts: (P, 3). Robust fuer geschlossene Meshes, unabhaengig von Strahlrichtungen."""
    out = np.zeros(len(pts), dtype=bool)
    batch = max(1, int(4e5 // max(len(tris), 1)))
    for s in range(0, len(pts), batch):
        p = pts[s:s + batch]
        a = tris[None, :, 0, :] - p[:, None, :]
        b = tris[None, :, 1, :] - p[:, None, :]
        c = tris[None, :, 2, :] - p[:, None, :]
        la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
        det = np.einsum("pfi,pfi->pf", a, np.cross(b, c))
        div = (la * lb * lc + np.einsum("pfi,pfi->pf", a, b) * lc + np.einsum("pfi,pfi->pf", a, c) * lb
               + np.einsum("pfi,pfi->pf", b, c) * la)
        w = np.arctan2(det, div).sum(axis=1) / (2 * np.pi)
        out[s:s + batch] = np.abs(w) > 0.5
    return out


def _solid_tris(s: trimesh.Trimesh) -> np.ndarray:
    t = getattr(s, "_oracle_tris", None)
    if t is None:
        t = np.asarray(s.triangles, dtype=float)
        s._oracle_tris = t
    return t


def _contained(A: Body, Ta: np.ndarray, B: Body, Tb: np.ndarray) -> bool:
    """Liegt eine Komponente von A ganz in einem Solid von B (ohne Dreiecksschnitt)?"""
    if not B.solids:
        return False
    p_W = A.probes @ Ta[:3, :3].T + Ta[:3, 3]
    p_B = (p_W - Tb[:3, 3]) @ Tb[:3, :3]
    for s in B.solids:
        lo, hi = s.bounds
        m = np.all((p_B >= lo) & (p_B <= hi), axis=1)
        if m.any() and winding_inside(_solid_tris(s), p_B[m]).any():
            return True
    return False


def _inside_depths(A: Body, Ta: np.ndarray, B: Body, Tb: np.ndarray, max_pts: int = 400):
    """Max. Tiefe der Ecken von A in den Solids von B: (Tiefe, Punkt in W, Oberflaechenpunkt in W).

    Kandidaten: Ecken von A in der Bounding-Box eines Solids (hoechstens max_pts, deterministisch
    ausgeduennt), deren Oberflaechen-Lot nach innen zeigt; absteigend nach Abstand wird die erste per
    Windungszahl bestaetigte Ecke genommen. Ergebnis ist immer eine untere Schranke der Tiefe."""
    best = (0.0, None, None)
    if not B.solids:
        return best
    p_W = A.vertices @ Ta[:3, :3].T + Ta[:3, 3]
    p_B = (p_W - Tb[:3, 3]) @ Tb[:3, :3]
    for s in B.solids:
        lo, hi = s.bounds
        m = np.flatnonzero(np.all((p_B >= lo) & (p_B <= hi), axis=1))
        if not len(m):
            continue
        if len(m) > max_pts:
            m = m[np.linspace(0, len(m) - 1, max_pts).astype(int)]
        cp, dist, tid = trimesh.proximity.closest_point(s, p_B[m])
        inward = ((p_B[m] - cp) * s.face_normals[tid]).sum(axis=1) < 0
        order = np.flatnonzero(inward)
        order = order[np.argsort(-dist[order])]
        tris = _solid_tris(s)
        for k in range(0, min(len(order), 64), 8):
            blk = order[k:k + 8]
            if dist[blk[0]] <= best[0]:
                break
            ins = winding_inside(tris, p_B[m[blk]])
            if ins.any():
                j = blk[int(np.argmax(ins))]
                best = (float(dist[j]), p_W[m[j]].copy(), Tb[:3, :3] @ cp[j] + Tb[:3, 3])
                break
    return best


def penetration_lower_bound(A: Body, Ta: np.ndarray, B: Body, Tb: np.ndarray):
    """Untere Schranke der Eindringtiefe zweier sich schneidender Koerper (>= 0) mit Zeugen (A, B)."""
    d1, pa1, pb1 = _inside_depths(A, Ta, B, Tb)
    d2, pb2, pa2 = _inside_depths(B, Tb, A, Ta)
    if d2 > d1:
        return d2, pa2, pb2
    return d1, pa1, pb1


def box_part_mesh(size_mm) -> trimesh.Trimesh:
    """Quader Laenge x Dicke x Hoehe in Frame P (Ursprung Mitte Bodenflaeche)."""
    L, T, H = (float(v) for v in size_mm)
    m = trimesh.creation.box(extents=(L, T, H))
    m.apply_translation((0.0, 0.0, H / 2))
    return m


def bodies_intersect(A: Body, Ta: np.ndarray, B: Body, Tb: np.ndarray) -> bool:
    """Schneiden oder enthalten sich zwei Koerper (Dreiecksschnitt aller Zellpaare oder Enthaltensein)?"""
    ta = coal.Transform3s(np.ascontiguousarray(Ta[:3, :3]), np.ascontiguousarray(Ta[:3, 3]))
    tb = coal.Transform3s(np.ascontiguousarray(Tb[:3, :3]), np.ascontiguousarray(Tb[:3, 3]))
    cwa = A.cc @ Ta[:3, :3].T + Ta[:3, 3]
    cwb = B.cc @ Tb[:3, :3].T + Tb[:3, 3]
    D = np.linalg.norm(cwa[:, None, :] - cwb[None, :, :], axis=2) - A.cr[:, None] - B.cr[None, :]
    creq = coal.CollisionRequest()
    for i, j in np.argwhere(D <= 0):
        if coal.collide(A.chunks[i].bvh, ta, B.chunks[j].bvh, tb, creq, coal.CollisionResult()):
            return True
    return _contained(A, Ta, B, Tb) or _contained(B, Tb, A, Ta)
