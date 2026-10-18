"""Kollisionswelt: Glieder, Werkzeugkoerper, Duesenspitze, Boden, Tisch, Druckstand, Selbstkollision.

Schnittstelle nach spec/ARTEFAKTE.md. `layer` ist die Anzahl k fertiger Schichten;
Hindernis = Teil-Solid mit z_P <= k*h.

Geometrie (SPEC §5.1): jeder Koerper ist eine Menge konvexer Teile mit Aufmass (siehe
`roboprint.collision_assets`), konservativ gegenueber den Roh-Meshes. Abstaende rechnet das
Default-Backend mit python-fcl (GJK/EPA, vorzeichenbehaftet) je Teilpaar minus Aufmass; der Boden
(Halbraum z <= 0 in W) ist analytisch. Branch-and-Bound ueber Huellkugeln: Teilpaare werden
aufsteigend nach ihrer unteren Schranke ausgewertet, bis die Schranke den besten Wert erreicht.

Geprueft werden genau die Paare aus SPEC §5.1 (`checked_pairs`).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import fcl
import numpy as np
import trimesh

from roboprint import collision_assets as ca
from roboprint import frames as fm
from roboprint.assets import load_tool, load_workstation, tool_mesh_path, workstation_mesh_path
from roboprint.urdf_chain import load_chain

REPO_ROOT = Path(__file__).resolve().parents[3]

LINKS = ("base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6")
TOOL_BODY = "tool_body"
NOZZLE_TIP = "nozzle_tip"
FLOOR, TABLE, PRINTED = "floor", "table", "printed"
R_FREE_MM = 40.0  # SPEC §10

_FLOOR_TABLE = ("link_2", "link_3", "link_4", "link_5", "link_6", TOOL_BODY, NOZZLE_TIP)
_PRINTED_MOVERS = (*LINKS, TOOL_BODY)


def checked_pairs() -> list[tuple[str, str]]:
    """Genau die Paare aus SPEC §5.1 als (Glied, Hindernis)."""
    pairs = [(a, FLOOR) for a in _FLOOR_TABLE]
    pairs += [(a, TABLE) for a in _FLOOR_TABLE]
    pairs += [(a, PRINTED) for a in _PRINTED_MOVERS]
    pairs += [(LINKS[j], LINKS[i]) for i in range(len(LINKS)) for j in range(i + 2, len(LINKS))]
    pairs += [(TOOL_BODY, n) for n in LINKS[:5]]
    return pairs


@dataclass
class Contact:
    d_mm: float  # vorzeichenbehaftet, < 0 bei Durchdringung
    pair: tuple[str, str]  # (Glied, Hindernis)
    witness_W: tuple[np.ndarray, np.ndarray]  # Zeugenpunkte in W, mm  # noqa: N815


class CollisionBackend(Protocol):
    """Backend-Naht (SPEC §4): Abstand je Pose bei k fertigen Schichten."""

    def distance(self, q: np.ndarray, layer: int, upper: float | None = None) -> Contact: ...

    def distance_batch(
        self,
        Q: np.ndarray,
        layers,
        upper: float | None = None,  # noqa: N803
    ) -> list[Contact]: ...


# --------------------------------------------------------------------------- Geometrie


def _fcl_convex(part: ca.ConvexPart) -> fcl.CollisionObject:
    f = np.asarray(part.faces, dtype=np.int64)
    flat = np.hstack([np.full((len(f), 1), 3), f]).ravel()
    return fcl.CollisionObject(fcl.Convex(np.asarray(part.vertices, float), len(f), flat))


class _Body:
    """Starrer Koerper aus konvexen Teilen, angehaengt an einen Frame (Glied oder W)."""

    def __init__(self, name: str, frame: str, parts: list[ca.ConvexPart]) -> None:
        self.name = name
        self.frame = frame
        self.parts = parts
        self.centers = np.array([p.center for p in parts]).reshape(-1, 3)
        self.radii = np.array([p.radius for p in parts])
        self.margins = np.array([p.margin for p in parts])
        self.objs = [_fcl_convex(p) for p in parts]
        self.verts = np.vstack([p.vertices for p in parts]) if parts else np.zeros((0, 3))
        self.vmargin = (
            np.concatenate([np.full(len(p.vertices), p.margin) for p in parts]) if parts else np.zeros(0)
        )
        if parts:
            lo = np.min([p.vertices.min(axis=0) - p.margin for p in parts], axis=0)
            hi = np.max([p.vertices.max(axis=0) + p.margin for p in parts], axis=0)
            self.bcenter = 0.5 * (lo + hi)
            self.bradius = float(np.max(np.linalg.norm(self.centers - self.bcenter, axis=1) + self.radii))
            self.blo, self.bhi = lo, hi
        else:
            self.bcenter, self.bradius = np.zeros(3), 0.0
            self.blo = self.bhi = np.zeros(3)


@dataclass
class _Static:
    chain: object
    T_WB: np.ndarray  # noqa: N815
    T_FT: np.ndarray  # noqa: N815
    links: dict[str, list[ca.ConvexPart]]
    tool_body: list[ca.ConvexPart]
    nozzle_tip: list[ca.ConvexPart]
    table: list[ca.ConvexPart]


@lru_cache(maxsize=4)
def _static_assets(root: Path, r_free_mm: float) -> _Static:
    """Glieder, Werkzeug und Tisch aus den Default-Assets (einmal je Prozess, Platte gecacht)."""
    chain = load_chain(root)
    ws = load_workstation(root)
    tool = load_tool(root)
    T_WB = fm.T_WB(ws)  # noqa: N806
    T_FT = fm.T_FT(tool)  # noqa: N806
    tool_mesh = trimesh.load(str(tool_mesh_path(tool, root)), force="mesh", process=True)
    tool_mesh.apply_transform(fm.T_F_mesh(tool))
    body, tip = ca.tool_parts(tool_mesh, T_FT[:3, 3], r_free_mm)
    table_mesh = trimesh.load(str(workstation_mesh_path(ws, root)), force="mesh", process=True)
    return _Static(
        chain=chain,
        T_WB=T_WB,
        T_FT=T_FT,
        links=ca.link_parts(chain),
        tool_body=body,
        nozzle_tip=tip,
        table=ca.table_parts(table_mesh),
    )


# --------------------------------------------------------------------------- Welt


class _LayerScene:
    """Alle Teile und Kandidaten-Teilpaare fuer einen Druckstand k."""

    def __init__(self, bodies: list[_Body], frame_index: dict[str, int]) -> None:
        self.bodies = bodies
        idx = {b.name: i for i, b in enumerate(bodies)}
        offs = np.cumsum([0] + [len(b.parts) for b in bodies])
        self.part_body = np.concatenate(
            [np.full(len(b.parts), i, dtype=np.int64) for i, b in enumerate(bodies)]
        )
        self.part_frame = np.array([frame_index[bodies[i].frame] for i in self.part_body])
        self.centers = np.vstack([b.centers for b in bodies])
        self.radii = np.concatenate([b.radii for b in bodies])
        self.margins = np.concatenate([b.margins for b in bodies])
        self.objs = [o for b in bodies for o in b.objs]
        pa, pb, pid = [], [], []
        self.pair_names: list[tuple[str, str]] = []
        self.floor_bodies: list[int] = []
        self.pair_bodies: list[tuple[int, int]] = []
        for a, b in checked_pairs():
            if a not in idx:
                continue
            if b == FLOOR:
                self.floor_bodies.append(idx[a])
                continue
            if b not in idx:
                continue
            ia, ib = idx[a], idx[b]
            na, nb = len(bodies[ia].parts), len(bodies[ib].parts)
            if not na or not nb:
                continue
            ga = np.repeat(np.arange(offs[ia], offs[ia + 1]), nb)
            gb = np.tile(np.arange(offs[ib], offs[ib + 1]), na)
            pa.append(ga)
            pb.append(gb)
            pid.append(np.full(len(ga), len(self.pair_names)))
            self.pair_names.append((a, b))
            self.pair_bodies.append((ia, ib))
        self.pa = np.concatenate(pa) if pa else np.zeros(0, dtype=np.int64)
        self.pb = np.concatenate(pb) if pb else np.zeros(0, dtype=np.int64)
        self.pid = np.concatenate(pid) if pid else np.zeros(0, dtype=np.int64)
        self.rsum = self.radii[self.pa] + self.radii[self.pb]
        # Statische Hindernisteile (Frame W): achsparallele Box als engere Schranke als die Kugel.
        w = frame_index["W"]
        lo = np.vstack([p.vertices.min(axis=0) for b in bodies for p in b.parts])
        hi = np.vstack([p.vertices.max(axis=0) for b in bodies for p in b.parts])
        self.static_pair = np.flatnonzero(self.part_frame[self.pb] == w)
        sb = self.pb[self.static_pair]
        self.static_lo = lo[sb] - self.margins[sb, None]
        self.static_hi = hi[sb] - 0.0 + self.margins[sb, None]
        self.static_ra = self.radii[self.pa[self.static_pair]]
        # Koerperebene: Paarbloecke in pa/pb, Huellkugeln bzw. Boxen (statisch) je Koerper
        counts = np.bincount(self.pid, minlength=len(self.pair_names))
        self.pair_start = np.concatenate([[0], np.cumsum(counts)])
        self.pba = np.array([a for a, _ in self.pair_bodies], dtype=np.int64)
        self.pbb = np.array([b for _, b in self.pair_bodies], dtype=np.int64)
        self.body_frame = np.array([frame_index[b.frame] for b in bodies])
        self.body_center = np.array([b.bcenter for b in bodies])
        self.body_radius = np.array([b.bradius for b in bodies])
        self.body_lo = np.array([b.blo for b in bodies])
        self.body_hi = np.array([b.bhi for b in bodies])
        self.pair_static = self.body_frame[self.pbb] == w
        # Position jedes Paares in der Liste der statischen Paare (fuer die Box-Schranke)
        self.static_pos = np.full(len(self.pa), -1, dtype=np.int64)
        self.static_pos[self.static_pair] = np.arange(len(self.static_pair))
        self.pair_range = [
            np.arange(self.pair_start[i], self.pair_start[i + 1]) for i in range(len(self.pair_names))
        ]


class World:
    """Kollisionswelt aus Default-Assets plus Teilmesh und Druckstand (Default-Backend fcl)."""

    def __init__(
        self,
        part_mesh_P,  # noqa: N803 - trimesh.Trimesh
        T_WP: np.ndarray,  # noqa: N803
        layer_height_mm: float = 10.0,
        root: Path = REPO_ROOT,
        r_free_mm: float = R_FREE_MM,
    ) -> None:
        self.root = Path(root).resolve()
        self.h = float(layer_height_mm)
        self.T_WP = np.asarray(T_WP, dtype=float)
        self.part_mesh_P = part_mesh_P
        st = _static_assets(self.root, float(r_free_mm))
        self.chain = st.chain
        self.T_WB = st.T_WB
        self.T_FT = st.T_FT
        # Frames: 0..6 Glieder, 7 = W (statisch)
        self._frame_index = {n: i for i, n in enumerate(LINKS)}
        self._frame_index["W"] = len(LINKS)
        self._moving = [_Body(n, n, st.links.get(n, [])) for n in LINKS]
        self._moving.append(_Body(TOOL_BODY, "link_6", st.tool_body))
        self._moving.append(_Body(NOZZLE_TIP, "link_6", st.nozzle_tip))
        self._table = _Body(TABLE, "W", st.table)
        self._scenes: dict[int, _LayerScene] = {}
        self._req = fcl.DistanceRequest(enable_nearest_points=True, enable_signed_distance=True)
        self._warm: dict[int, int] = {}

    # -------------------------------------------------------------- Druckstand
    def _printed_z_cut(self, layer: int) -> float:
        return max(0, int(layer)) * self.h

    def _scene(self, layer: int) -> _LayerScene:
        k = int(layer)
        if k not in self._scenes:
            bodies = [*self._moving, self._table]
            if self.part_mesh_P is not None and k > 0:
                parts_P = ca.printed_parts(self.part_mesh_P, self._printed_z_cut(k))
                parts_W = [
                    ca.ConvexPart(p.vertices @ self.T_WP[:3, :3].T + self.T_WP[:3, 3], p.faces, p.margin)
                    for p in parts_P
                ]
                if parts_W:
                    bodies.append(_Body(PRINTED, "W", parts_W))
            self._scenes[k] = _LayerScene(bodies, self._frame_index)
        return self._scenes[k]

    # -------------------------------------------------------------- Posen
    def frames_W(self, q: np.ndarray) -> np.ndarray:  # noqa: N802
        """(8,4,4): T_W,link fuer base_link...link_6 und W selbst."""
        lp = self.chain.link_poses_array(np.asarray(q, dtype=float))
        out = np.empty((len(LINKS) + 1, 4, 4))
        out[: len(LINKS)] = self.T_WB @ lp
        out[len(LINKS)] = np.eye(4)
        return out

    def tcp_W(self, q: np.ndarray) -> np.ndarray:  # noqa: N802
        return self.frames_W(q)[LINKS.index("link_6")] @ self.T_FT

    # -------------------------------------------------------------- Abstand
    def distance(self, q: np.ndarray, layer: int, upper: float | None = None) -> Contact:
        """Kleinster vorzeichenbehafteter Abstand der Pose q bei k = `layer` fertigen Schichten.

        Mit `upper` darf die Suche abbrechen, sobald d >= upper feststeht; `d_mm` ist dann eine
        untere Schranke >= upper (Paar und Zeugen gehoeren zur kleinsten Schranke).
        """
        return self._distance(self.frames_W(q), self._scene(layer), upper)

    def distance_batch(
        self,
        Q: np.ndarray,
        layers,
        upper: float | None = None,  # noqa: N803
    ) -> list[Contact]:
        Q = np.atleast_2d(np.asarray(Q, dtype=float))  # noqa: N806
        layers = np.broadcast_to(np.asarray(layers, dtype=np.int64), (len(Q),))
        lp = self.chain.link_poses_batch(Q)
        out = []
        frames = np.empty((len(LINKS) + 1, 4, 4))
        frames[len(LINKS)] = np.eye(4)
        for i in range(len(Q)):
            frames[: len(LINKS)] = self.T_WB @ lp[i]
            out.append(self._distance(frames, self._scene(int(layers[i])), upper))
        return out

    def pair_distances(self, q: np.ndarray, layer: int) -> dict[tuple[str, str], float]:
        """Abstand je geprueftem Paar (fuer Tests und Diagnose; langsamer als `distance`)."""
        frames = self.frames_W(q)
        sc = self._scene(layer)
        out: dict[tuple[str, str], float] = {}
        for bi in sc.floor_bodies:
            b = sc.bodies[bi]
            T = frames[self._frame_index[b.frame]]  # noqa: N806
            out[(b.name, FLOOR)] = float((b.verts @ T[2, :3] + T[2, 3] - b.vmargin).min())
        tfs = {}
        for i, f in enumerate(frames):
            tfs[i] = fcl.Transform(f[:3, :3].copy(), f[:3, 3].copy())
        for pid, name in enumerate(sc.pair_names):
            ks = np.flatnonzero(sc.pid == pid)
            best = np.inf
            for k in ks:
                a, b = int(sc.pa[k]), int(sc.pb[k])
                sc.objs[a].setTransform(tfs[int(sc.part_frame[a])])
                sc.objs[b].setTransform(tfs[int(sc.part_frame[b])])
                d = fcl.distance(sc.objs[a], sc.objs[b], self._req, fcl.DistanceResult())
                best = min(best, d - sc.margins[a] - sc.margins[b])
            out[name] = float(best)
        return out

    def _distance(self, frames: np.ndarray, sc: _LayerScene, upper: float | None) -> Contact:
        lim_up = np.inf if upper is None else float(upper)
        best = np.inf
        best_pair: tuple[str, str] = ("", "")
        best_w = (np.full(3, np.nan), np.full(3, np.nan))

        # Boden: Minimum von z ueber die Ecken minus Aufmass, exakt fuer konvexe Teile.
        for bi in sc.floor_bodies:
            b = sc.bodies[bi]
            if not len(b.verts):
                continue
            T = frames[self._frame_index[b.frame]]  # noqa: N806
            z = b.verts @ T[2, :3] + T[2, 3] - b.vmargin
            j = int(np.argmin(z))
            if z[j] < best:
                best = float(z[j])
                p = T[:3, :3] @ b.verts[j] + T[:3, 3]
                best_pair = (b.name, FLOOR)
                best_w = (p - np.array([0.0, 0.0, b.vmargin[j]]), np.array([p[0], p[1], 0.0]))

        if not len(sc.pa):
            return _contact(best, lim_up, best_pair, best_w)

        tf_cache: dict[int, fcl.Transform] = {}
        placed: set[int] = set()

        def place(part: int) -> None:
            if part in placed:
                return
            fi = int(sc.part_frame[part])
            tf = tf_cache.get(fi)
            if tf is None:
                T = frames[fi]  # noqa: N806
                tf = fcl.Transform(T[:3, :3].copy(), T[:3, 3].copy())
                tf_cache[fi] = tf
            sc.objs[part].setTransform(tf)
            placed.add(part)

        done: set[int] = set()

        def evaluate(k: int) -> None:
            nonlocal best, best_pair, best_w
            done.add(k)
            a, b = int(sc.pa[k]), int(sc.pb[k])
            place(a)
            place(b)
            res = fcl.DistanceResult()
            d = fcl.distance(sc.objs[a], sc.objs[b], self._req, res) - sc.margins[a] - sc.margins[b]
            if d < best:
                best = float(d)
                best_pair = sc.pair_names[int(sc.pid[k])]
                pa_, pb_ = (np.asarray(x, dtype=float) for x in res.nearest_points)
                best_w = _shift_witness(pa_, pb_, sc.margins[a], sc.margins[b], d)
                self._warm[id(sc)] = k

        # Warmstart: das Teilpaar mit dem Minimum der letzten Abfrage liefert frueh eine gute Schranke.
        warm = self._warm.get(id(sc))
        if warm is not None:
            evaluate(warm)

        # Koerperebene: Paare, deren Schranke schon >= best ist, entfallen ganz.
        fr = frames[sc.body_frame]
        cb = np.einsum("nij,nj->ni", fr[:, :3, :3], sc.body_center) + fr[:, :3, 3]
        ca_, cb_ = cb[sc.pba], cb[sc.pbb]
        blb = np.linalg.norm(ca_ - cb_, axis=1) - sc.body_radius[sc.pba] - sc.body_radius[sc.pbb]
        st = sc.pair_static
        if st.any():
            lo_b, hi_b = sc.body_lo[sc.pbb[st]], sc.body_hi[sc.pbb[st]]
            gap = np.maximum(np.maximum(lo_b - ca_[st], ca_[st] - hi_b), 0)
            blb[st] = np.maximum(blb[st], np.linalg.norm(gap, axis=1) - sc.body_radius[sc.pba[st]])
        live = np.flatnonzero(blb < min(best, lim_up))
        if not len(live):
            return _contact(best, lim_up, best_pair, best_w, blb.min() if len(blb) else None)
        sel = np.concatenate([sc.pair_range[p] for p in live])

        # Teilebene: Kugel- bzw. Box-Schranken, dann aufsteigend auswerten.
        fp = frames[sc.part_frame]
        cw = np.einsum("nij,nj->ni", fp[:, :3, :3], sc.centers) + fp[:, :3, 3]
        pa_s = sc.pa[sel]
        diff = cw[pa_s] - cw[sc.pb[sel]]
        lb = np.sqrt(np.einsum("ij,ij->i", diff, diff)) - sc.rsum[sel]
        spos = sc.static_pos[sel]
        m = spos >= 0
        if m.any():
            c = cw[pa_s[m]]
            gp = np.maximum(np.maximum(sc.static_lo[spos[m]] - c, c - sc.static_hi[spos[m]]), 0.0)
            lb[m] = np.maximum(lb[m], np.sqrt(np.einsum("ij,ij->i", gp, gp)) - sc.static_ra[spos[m]])
        keep = np.flatnonzero(lb < min(best, lim_up))
        sel, lb = sel[keep], lb[keep]
        next_lb = None
        while len(sel):
            n = min(len(sel), 32)
            part = np.argpartition(lb, n - 1)[:n] if n < len(sel) else np.arange(len(sel))
            part = part[np.argsort(lb[part], kind="stable")]
            stop = False
            for i in part:
                if lb[i] >= min(best, lim_up):
                    next_lb = (float(lb[i]), int(sel[i]))
                    stop = True
                    break
                if int(sel[i]) not in done:
                    evaluate(int(sel[i]))
            if stop:
                break
            rest = np.ones(len(sel), dtype=bool)
            rest[part] = False
            sel, lb = sel[rest], lb[rest]
            keep = lb < min(best, lim_up)
            if not keep.all():
                if (~keep).any():
                    j = int(np.argmin(np.where(keep, np.inf, lb)))
                    if next_lb is None or lb[j] < next_lb[0]:
                        next_lb = (float(lb[j]), int(sel[j]))
                sel, lb = sel[keep], lb[keep]
        if best >= lim_up and next_lb is not None and next_lb[0] < best:
            k = next_lb[1]
            best = next_lb[0]
            best_pair = sc.pair_names[int(sc.pid[k])]
            best_w = (cw[sc.pa[k]], cw[sc.pb[k]])
        return _contact(best, lim_up, best_pair, best_w)


def _contact(best, lim_up, pair, witness, bound=None) -> Contact:
    if best >= lim_up and bound is not None and bound < best:
        best = max(float(bound), lim_up)
    if not np.isfinite(best):
        best = lim_up if np.isfinite(lim_up) else 1e9
    return Contact(float(best), pair, witness)


def _shift_witness(pa: np.ndarray, pb: np.ndarray, ma: float, mb: float, d: float):
    """Zeugenpunkte von den Kernteilen auf die aufgeblasenen Oberflaechen verschieben."""
    v = pb - pa
    n = np.linalg.norm(v)
    if n < 1e-9:
        return pa, pb
    u = v / n
    if d + ma + mb < 0:  # Kerne durchdringen sich: Richtung zeigt von b nach a
        u = -u
    return pa + u * ma, pb - u * mb
