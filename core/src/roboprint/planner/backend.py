"""Backend-Naht des Planers (SPEC §4): Protokoll `CollisionBackend`, Batch-Adapter, Kugel-Double.

Der Planer rechnet Abstaende nur ueber `CollisionBackend.distance(q, layer) -> Contact`
(Schnittstelle aus spec/ARTEFAKTE.md). Hat ein Backend zusaetzlich
`distance_batch(Q, layers)`, nutzt der Adapter `contacts_batch`/`d_batch` diese.

`SphereWorld` ist ein schnelles, vektorisiertes Ersatzmodell derselben Paare wie SPEC §5.1:
Glieder und Werkzeug als Kugelmengen (k-Means ueber die Vertices der URDF-Kollisionsmeshes
bzw. des Werkzeug-STL, Radius = groesster Abstand der zugeordneten Vertices), Boden als
Halbraum, Tisch und Druckstand als Quader (Druckstand = Bounding-Box des Teils bis k*h).
Es dient dem Planer als Vorauswahl (Kostenterm, Vorpruefung des Druckplatzes) und als Ersatz, solange
`roboprint.collision.World` noch nicht implementiert ist. Die Abnahme rechnet mit `World`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from roboprint import frames
from roboprint.assets import REPO_ROOT, URDF_PATH, load_robot, load_tool, load_workstation, tool_mesh_path
from roboprint.collision import CollisionBackend, Contact  # noqa: F401 - Re-Export der Naht

LINKS = ("base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6")
TOOL_BODY = "tool_body"
NOZZLE_TIP = "nozzle_tip"
OWNERS = (*LINKS, TOOL_BODY, NOZZLE_TIP)


# --------------------------------------------------------------------------- Adapter


def contacts_batch(backend: Any, Q: np.ndarray, layers: np.ndarray) -> list[Contact]:
    """Kontakte fuer viele Posen; nutzt `distance_batch`, falls vorhanden."""
    Q = np.asarray(Q, float).reshape(-1, 6)
    layers = np.broadcast_to(np.asarray(layers, int), (len(Q),))
    if len(Q) == 0:
        return []
    fb = getattr(backend, "distance_batch", None)
    if fb is not None:
        res = fb(Q, layers)
        if isinstance(res, list) and (not res or isinstance(res[0], Contact) or hasattr(res[0], "d_mm")):
            return res
    return [backend.distance(q, int(k)) for q, k in zip(Q, layers, strict=True)]


def d_batch(backend: Any, Q: np.ndarray, layers: np.ndarray, self_collision: bool = True) -> np.ndarray:
    """Nur die Abstaende (mm) fuer viele Posen."""
    f = getattr(backend, "d_batch", None)
    if f is not None:
        return f(Q, layers, self_collision=self_collision)
    return np.array([c.d_mm for c in contacts_batch(backend, Q, layers)], dtype=float)


# --------------------------------------------------------------------------- Punktmodell

_CULL_MM = 50.0  # weiter weg reicht die Huellkugel als (konservative) Schranke
#: base_link <-> link_2: nahezu konstanter Abstand (Orakel/Coal 33,15 mm, `collision.World` 30,7 mm,
#: link_2 dreht um die J2-Achse, die naechsten Stellen sind rotationssymmetrisch). Statusregel
#: (collision.CONST_PAIRS): zaehlt nur unter d_hard, was konstruktiv nie eintritt; das Punkt-Double
#: laesst das Paar daher ganz weg.


@dataclass(frozen=True)
class _Body:
    owner: int  # Index in OWNERS
    frame: int  # Index des Gliedframes (0..6); Werkzeug haengt am Flansch (6)
    pts: np.ndarray  # (n,3) Oberflaechenpunkte im Gliedframe
    r: float  # Ueberdeckungsradius der Punkte
    pts_c: np.ndarray  # grobe Punkte fuer Selbstkollision
    r_c: float
    center: np.ndarray  # Huellkugel
    R: float  # noqa: N815


def _surface_points(mesh: Any, spacing: float) -> np.ndarray:
    import trimesh

    n = int(np.clip(4.0 * mesh.area / spacing**2, 50, 200000))
    pts, _ = trimesh.sample.sample_surface(mesh, n, seed=0)
    pts = np.vstack([pts, mesh.vertices])
    key = np.floor(pts / spacing).astype(np.int64)
    _, first = np.unique(key, axis=0, return_index=True)
    return pts[np.sort(first)]


def _body(
    owner: int, frame: int, meshes: list[Any], spacing: float = 30.0, chunk: float = 120.0
) -> list[_Body]:
    """Oberflaechenpunkte, in Stuecke mit eigener Huellkugel (~chunk mm) geteilt."""
    import trimesh
    from scipy.cluster.vq import kmeans2

    m = trimesh.util.concatenate(meshes)
    pts = _surface_points(m, spacing)
    r = spacing * 0.75
    ext = float(np.max(pts.max(0) - pts.min(0)))
    k = int(min(max(1, np.ceil(ext / chunk) ** 2), len(pts) // 4 or 1))
    if k > 1:
        _, lab = kmeans2(pts, k, seed=0, minit="++", iter=20)
    else:
        lab = np.zeros(len(pts), int)
    out = []
    for i in np.unique(lab):
        sub = pts[lab == i]
        c = 0.5 * (sub.min(0) + sub.max(0))
        R = float(np.linalg.norm(sub - c, axis=1).max()) + r  # noqa: N806
        out.append(_Body(owner, frame, sub, r, sub, r, c, R))
    return out


def _urdf_collision_meshes(root: Path) -> dict[str, list[Path]]:
    tree = ET.parse(root / URDF_PATH).getroot()
    out: dict[str, list[Path]] = {}
    for link in tree.findall("link"):
        paths = []
        for col in link.findall("collision"):
            mesh = col.find("geometry/mesh")
            if mesh is None:
                continue
            fn = re.sub(r"^package://[^/]+/", "", mesh.get("filename", ""))
            paths.append(root / "third_party" / "doosan_m1013" / fn)
        out[link.get("name", "")] = paths
    return out


@lru_cache(maxsize=2)
def _bodies(root: Path, r_free_mm: float) -> tuple[_Body, ...]:
    import trimesh

    out = []
    meshes = _urdf_collision_meshes(root)
    for i, name in enumerate(LINKS):
        ms = [trimesh.load(p, force="mesh") for p in meshes.get(name, [])]  # DAE in mm
        out += _body(i, i, ms)
    tool = load_tool(root)
    tm = trimesh.load(tool_mesh_path(tool, root), force="mesh")
    tm.apply_transform(frames.T_F_mesh(tool))
    tcp_F = frames.T_FT(tool)[:3, 3]  # noqa: N806
    tip = np.linalg.norm(tm.triangles_center - tcp_F, axis=1) <= r_free_mm
    for owner, sel, sp in ((7, ~tip, 20.0), (8, tip, 1.0)):
        sub = tm.submesh([np.nonzero(sel)[0]], append=True)
        out += _body(owner, 6, [sub], spacing=sp, chunk=80.0)
    return tuple(out)


def link_frames_batch(Q: np.ndarray) -> np.ndarray:  # noqa: N803
    """Gliedframes in B fuer (N,6) -> (N,7,4,4): base_link, link_1 ... link_6."""
    robot = load_robot()
    Q = np.asarray(Q, float).reshape(-1, 6)  # noqa: N806
    n = len(Q)
    out = np.empty((n, 7, 4, 4))
    T = np.broadcast_to(np.eye(4), (n, 4, 4)).copy()  # noqa: N806
    out[:, 0] = T
    for i, j in enumerate(robot.joints):
        T = T @ j.origin  # noqa: N806
        c, s = np.cos(Q[:, i]), np.sin(Q[:, i])
        Rz = np.zeros((n, 4, 4))  # noqa: N806
        Rz[:, 0, 0], Rz[:, 0, 1], Rz[:, 1, 0], Rz[:, 1, 1] = c, -s, s, c
        Rz[:, 2, 2] = Rz[:, 3, 3] = 1.0
        T = T @ Rz  # alle Achsen der M1013-URDF sind +z  # noqa: N806
        out[:, i + 1] = T
    return out


def _box_sd(p: np.ndarray, lo: np.ndarray, hi: np.ndarray, closest: bool = True):
    """Vorzeichenbehafteter Abstand Punkt -> Quader und (optional) naechster Quaderpunkt."""
    c = (lo + hi) * 0.5
    h = (hi - lo) * 0.5
    q = np.abs(p - c)
    q -= h
    m = q.max(axis=-1)
    np.maximum(q, 0.0, out=q)
    d = np.sqrt(np.einsum("...i,...i->...", q, q)) + np.minimum(m, 0.0)
    return d, (np.clip(p, lo, hi) if closest else None)


def _self_pairs() -> list[tuple[int, int]]:
    """Selbstkollisionspaare des Doubles: nur die ueber mindestens zwei Glieder getrennten Paare
    der Handgelenk-/Werkzeugseite gegen Basis, Schulter und Oberarm (Faltstellungen). Die
    Nachbarpaare (z. B. link_4 <-> link_6, base_link <-> link_2) sind mit Punktwolken zu grob und
    liegen dauerhaft nahe beieinander; vollstaendig nach SPEC §5.1 prueft die echte Welt."""
    pairs = [(i, 7) for i in range(4)]  # Werkzeugkoerper <-> base_link ... link_3
    pairs += [(i, 6) for i in range(4)]  # link_6 <-> base_link ... link_3
    pairs += [(i, 5) for i in range(3)]  # link_5 <-> base_link ... link_2
    pairs += [(0, 4), (1, 4)]
    return pairs


#: Zusatzpaar des Doubles fuer Teile mit Druckmuster (opt-in, M3.2): Werkzeugkoerper <-> link_4.
#: Mit `layer_order = alternate` endet jede ungerade Schicht an der Naht der Aussenschale; an der
#: Oberkante von S1 (400 mm) faltet das Handgelenk dort so, dass der Werkzeugkoerper link_4 auf
#: < d_hard nahekommt. Ohne das Paar sieht das Double das nicht, die Abschlusspruefung verwirft den
#: Plan, und die Nachplanung mit der echten Welt kostet das 2,6- bis 2,8-Fache von S1. Ohne Muster
#: bleibt das Double unveraendert (S1-S3 bitgleich).
PATTERN_SELF_PAIRS: tuple[tuple[int, int], ...] = ((4, 7),)


def _unit(u: np.ndarray) -> np.ndarray:
    return u / np.maximum(np.linalg.norm(u, axis=-1, keepdims=True), 1e-9)


@lru_cache(maxsize=2)
def table_box(root: Path) -> tuple[np.ndarray, np.ndarray]:
    """Bounding-Box des Tisch-Meshes in W (mm)."""
    import trimesh

    ws = load_workstation(root)
    tm = trimesh.load(root / "workstations" / str(ws.mesh), force="mesh")
    return np.asarray(tm.bounds[0], float), np.asarray(tm.bounds[1], float)


class SphereWorld:
    """Punkt-/Kugel-Ersatzmodell der Kollisionswelt mit derselben Schnittstelle wie `collision.World`.

    Glieder und Werkzeug als Oberflaechenpunkte mit Ueberdeckungsradius (konservativ um etwa
    den Radius), Huellkugeln zum Aussortieren ferner Paare (dann zaehlt die Huellkugel als
    Schranke). Tisch und Druckstand als Quader, Druckstand = Bounding-Box des Teils bis k*h.
    """

    def __init__(
        self,
        part_mesh_P: Any,  # noqa: N803
        T_WP: np.ndarray,  # noqa: N803
        layer_height_mm: float = 10.0,
        root: Path = REPO_ROOT,
        r_free_mm: float = 40.0,
        part_bbox_P: np.ndarray | None = None,  # noqa: N803
        extra_self_pairs: tuple[tuple[int, int], ...] = (),
    ) -> None:
        self.root = Path(root)
        self._tpw: np.ndarray | None = None
        self._want_cp = True
        self.skip_tip = False  # Vorpruefung: Duesenspitze haengt nicht von der Platzierung ab
        self.h = float(layer_height_mm)
        self.bodies = _bodies(self.root, float(r_free_mm))
        self._first = {o: next(i for i, b in enumerate(self.bodies) if b.owner == o) for o in (0, 2)}
        own = {(a, c) for a, c in (*_self_pairs(), *extra_self_pairs)}
        self._pairs = [
            (i, j)
            for i, A in enumerate(self.bodies)
            for j, C in enumerate(self.bodies)
            if (A.owner, C.owner) in own
        ]
        ws = load_workstation(self.root)
        self.T_WB = frames.T_WB(ws)
        self.T_WP = np.asarray(T_WP, float)
        self.T_PW = frames.invert(self.T_WP)
        self.table_lo, self.table_hi = table_box(self.root)
        if part_bbox_P is None and part_mesh_P is not None:
            part_bbox_P = np.asarray(part_mesh_P.bounds, float)  # noqa: N806
        self.part_bbox = None if part_bbox_P is None else np.asarray(part_bbox_P, float)

    # ------------------------------------------------------------------ Kern
    def _obstacle_sd(self, kind: int, P: np.ndarray, top: np.ndarray | None, rows: np.ndarray | None = None):  # noqa: N803
        """Abstand von Punkten P (...,3) in W zum Hindernis und naechste Hindernispunkte.
        `rows`: Zeilen in `self._tpw` (Platzierung je Pose, nur fuer die Vorpruefung)."""
        if kind == 0:
            if not self._want_cp:
                return P[..., 2], None
            w = P.copy()
            w[..., 2] = np.minimum(P[..., 2], 0.0)
            return P[..., 2], w
        if kind == 1:
            return _box_sd(P, self.table_lo, self.table_hi, self._want_cp)
        lo = np.array([self.part_bbox[0, 0], self.part_bbox[0, 1], 0.0])
        hi = np.empty(np.shape(top) + (3,))
        hi[..., :2] = self.part_bbox[1, :2]
        hi[..., 2] = top
        if self._tpw is not None and rows is not None:
            T = self._tpw[rows]  # (r,4,4) T_PW  # noqa: N806
            if P.ndim == 2:
                Pp = np.einsum("rij,rj->ri", T[:, :3, :3], P) + T[:, :3, 3]  # noqa: N806
            else:
                Pp = np.einsum("rij,rkj->rki", T[:, :3, :3], P) + T[:, None, :3, 3]  # noqa: N806
            d, _ = _box_sd(Pp, lo, hi, False)
            return d, None  # Zeugen werden in der Suche nicht gebraucht
        Pp = P @ self.T_PW[:3, :3].T + self.T_PW[:3, 3]  # noqa: N806
        d, cp = _box_sd(Pp, lo, hi, self._want_cp)
        return d, (cp @ self.T_WP[:3, :3].T + self.T_WP[:3, 3] if cp is not None else None)

    def _eval(self, Q: np.ndarray, layers: np.ndarray, self_collision: bool, witness: bool):  # noqa: N803
        self._want_cp = witness
        n = len(Q)
        L = self.T_WB @ link_frames_batch(Q)  # (N,7,4,4) in W  # noqa: N806
        best = np.full(n, np.inf)
        pair = np.zeros((n, 2), dtype=int)  # (Koerper, Hindernis-Code >= 0 bzw. -(Koerper+1))
        wit = np.zeros((n, 2, 3))
        top = None
        if self.part_bbox is not None:
            top = np.minimum(layers * self.h, self.part_bbox[1, 2]).astype(float)
        centers = [L[:, b.frame, :3, :3] @ b.center + L[:, b.frame, :3, 3] for b in self.bodies]
        nt = OWNERS.index(NOZZLE_TIP)
        for oi, b in enumerate(self.bodies):
            T = L[:, b.frame]  # noqa: N806
            for kind in (0, 1, 2):
                if kind < 2 and b.owner < 2 or (self.skip_tip and b.owner == nt):
                    continue
                if kind == 2:
                    if top is None or b.owner == nt:
                        continue
                    act = layers > 0
                else:
                    act = np.ones(n, bool)
                db, cpb = self._obstacle_sd(kind, centers[oi], top, np.arange(n))
                db = db - b.R
                upd = act & (db < best) & (db >= _CULL_MM)
                if upd.any():
                    best[upd] = db[upd]
                    pair[upd] = (oi, kind)
                    if witness:
                        u = _unit(centers[oi][upd] - cpb[upd])
                        wit[upd, 0] = centers[oi][upd] - b.R * u
                        wit[upd, 1] = cpb[upd]
                near = np.nonzero(act & (db < _CULL_MM) & (db < best))[0]
                if near.size == 0:
                    continue
                P = np.einsum("nij,kj->nki", T[near, :3, :3], b.pts) + T[near, None, :3, 3]  # noqa: N806
                d, cp = self._obstacle_sd(kind, P, None if top is None else top[near, None], near)
                k = np.argmin(d, axis=1)
                rows = np.arange(len(near))
                dm = d[rows, k] - b.r
                upd = dm < best[near]
                idx = near[upd]
                best[idx] = dm[upd]
                pair[idx] = (oi, kind)
                if witness and idx.size:
                    pk, ck = P[rows[upd], k[upd]], cp[rows[upd], k[upd]]
                    u = _unit(pk - ck)
                    wit[idx, 0] = pk - b.r * u
                    wit[idx, 1] = ck
        if self_collision:
            for a, c in self._pairs:
                A, C = self.bodies[a], self.bodies[c]  # noqa: N806
                db = np.linalg.norm(centers[a] - centers[c], axis=1) - A.R - C.R
                upd = (db < best) & (db >= _CULL_MM)
                if upd.any():
                    best[upd] = db[upd]
                    pair[upd] = (c, -(a + 1))
                    u = _unit(centers[a][upd] - centers[c][upd])
                    wit[upd, 0] = centers[c][upd] + C.R * u
                    wit[upd, 1] = centers[a][upd] - A.R * u
                near = np.nonzero((db < _CULL_MM) & (db < best))[0]
                if near.size == 0:
                    continue
                step = max(1, int(3e6 // (len(A.pts_c) * len(C.pts_c))))
                for c0 in range(0, len(near), step):
                    self._self_chunk(L, near[c0 : c0 + step], A, C, a, c, best, pair, wit, witness)
        return best, pair, wit

    def _self_chunk(self, L, near, A, C, a, c, best, pair, wit, witness) -> None:  # noqa: N803
        Ta, Tc = L[near, A.frame], L[near, C.frame]  # noqa: N806
        Pa = np.einsum("nij,kj->nki", Ta[:, :3, :3], A.pts_c) + Ta[:, None, :3, 3]  # noqa: N806
        Pc = np.einsum("nij,kj->nki", Tc[:, :3, :3], C.pts_c) + Tc[:, None, :3, 3]  # noqa: N806
        D = np.linalg.norm(Pa[:, :, None, :] - Pc[:, None, :, :], axis=-1)  # noqa: N806
        flat = D.reshape(len(near), -1)
        k = np.argmin(flat, axis=1)
        rows = np.arange(len(near))
        dm = flat[rows, k] - A.r_c - C.r_c
        upd = dm < best[near]
        idx = near[upd]
        best[idx] = dm[upd]
        pair[idx] = (c, -(a + 1))
        if witness and idx.size:
            ka, kc = np.divmod(k[upd], C.pts_c.shape[0])
            pa, pc = Pa[rows[upd], ka], Pc[rows[upd], kc]
            u = _unit(pa - pc)
            wit[idx, 0] = pc + C.r_c * u
            wit[idx, 1] = pa - A.r_c * u

    # ------------------------------------------------------------------ API
    def d_batch_placed(
        self, Q: np.ndarray, layers: np.ndarray, T_WP: np.ndarray, self_collision: bool = False
    ):  # noqa: N803
        """Wie d_batch, aber mit eigener Teilplatzierung T_WP (N,4,4) je Pose (Vorpruefung)."""
        Q = np.asarray(Q, float).reshape(-1, 6)  # noqa: N806
        T_PW = np.linalg.inv(np.asarray(T_WP, float))  # noqa: N806
        out = []
        for a in range(0, len(Q), 2048):
            self._tpw = T_PW[a : a + 2048]
            try:
                out.append(self._eval(Q[a : a + 2048], layers[a : a + 2048], self_collision, False)[0])
            finally:
                self._tpw = None
        return np.concatenate(out) if out else np.zeros(0)

    def d_batch(self, Q: np.ndarray, layers: np.ndarray, self_collision: bool = True) -> np.ndarray:  # noqa: N803
        Q = np.asarray(Q, float).reshape(-1, 6)  # noqa: N806
        layers = np.broadcast_to(np.asarray(layers, int), (len(Q),))
        out = [
            self._eval(Q[a : a + 2048], layers[a : a + 2048], self_collision, False)[0]
            for a in range(0, len(Q), 2048)
        ]
        return np.concatenate(out) if out else np.zeros(0)

    def distance_batch(self, Q: np.ndarray, layers: np.ndarray) -> list[Contact]:  # noqa: N803
        Q = np.asarray(Q, float).reshape(-1, 6)  # noqa: N806
        layers = np.broadcast_to(np.asarray(layers, int), (len(Q),))
        names = ("floor", "table", "printed")
        res: list[Contact] = []
        for a in range(0, len(Q), 2048):
            d, pair, wit = self._eval(Q[a : a + 2048], layers[a : a + 2048], True, True)
            for i in range(len(d)):
                o, h = self.bodies[int(pair[i, 0])].owner, int(pair[i, 1])
                obst = names[h] if h >= 0 else OWNERS[self.bodies[-h - 1].owner]
                res.append(Contact(float(d[i]), (OWNERS[o], obst), (wit[i, 0].copy(), wit[i, 1].copy())))
        return res

    def distance(self, q: np.ndarray, layer: int) -> Contact:
        return self.distance_batch(np.asarray(q, float)[None], np.array([layer]))[0]


def make_world(
    part_mesh_P: Any,  # noqa: N803
    T_WP: np.ndarray,  # noqa: N803
    layer_height_mm: float,
    root: Path,
    r_free_mm: float,
    d_target_mm: float = 50.0,
):
    """Echte Kollisionswelt `roboprint.collision.World` (SPEC §5.1)."""
    from roboprint.collision import World

    return World(part_mesh_P, T_WP, layer_height_mm, root, r_free_mm, d_target_mm=d_target_mm)


_POOL_BACKEND: Any = None


def can_fork_pool() -> bool:
    """Prozess-Pools (fork) moeglich? Nicht in daemonischen Prozessen (z. B. API-Job)."""
    import multiprocessing as mp

    return "fork" in mp.get_all_start_methods() and not mp.current_process().daemon


def _pool_worker(args: tuple[np.ndarray, np.ndarray]) -> list[Contact]:
    Q, layers = args  # noqa: N806
    return contacts_batch(_POOL_BACKEND, Q, layers)


def contacts_parallel(backend: Any, Q: np.ndarray, layers: np.ndarray, procs: int = 1) -> list[Contact]:  # noqa: N803
    """Kontakte fuer viele Posen, auf `procs` Prozesse verteilt (fork; das Backend wird vorher fuer
    alle vorkommenden Schichten aufgewaermt und vererbt)."""
    import multiprocessing as mp

    global _POOL_BACKEND
    Q = np.asarray(Q, float).reshape(-1, 6)  # noqa: N806
    layers = np.broadcast_to(np.asarray(layers, int), (len(Q),))
    if procs <= 1 or len(Q) < 4000 or not can_fork_pool():
        return contacts_batch(backend, Q, layers)
    for k in np.unique(layers):  # Druckstand-Szenen vor dem fork bauen
        i = int(np.argmax(layers == k))
        backend.distance(Q[i], int(k))
    _POOL_BACKEND = backend
    n_chunks = procs * 6
    parts = [(Q[ix], layers[ix]) for ix in np.array_split(np.arange(len(Q)), n_chunks)]
    try:
        with mp.get_context("fork").Pool(procs) as pool:
            res = pool.map(_pool_worker, parts)
    finally:
        _POOL_BACKEND = None
    return [c for r in res for c in r]
