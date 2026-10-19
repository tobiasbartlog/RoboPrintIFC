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
D_HARD_MM = 10.0  # SPEC §10; ab dieser Schwelle zaehlt das konstruktive Paar CONST_PAIR doch
#: Konstruktiv konstantes Paar (~31-33 mm): zaehlt fuer `collision` und d_hard, nicht fuer d_target.
#: Statusregel (Nutzerentscheidung 2026-10-19): d_status = min ueber alle Paare ausser CONST_PAIR;
#: liegt dessen Abstand unter d_hard, geht er trotzdem ein.
CONST_PAIR = ("link_2", "base_link")
_BLOCK = 256  # Posen je vektorisiertem Block in `distance_batch`

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
        # Orientierte Box je Teil (Hauptachsen der Ecken, ohne Aufmass) fuer die Trennachsen-Schranke
        obb = [_obb(p.vertices) for p in parts]
        self.obb_c = np.array([o[0] for o in obb]).reshape(-1, 3)
        self.obb_ax = np.array([o[1] for o in obb]).reshape(-1, 3, 3)
        self.obb_h = np.array([o[2] for o in obb]).reshape(-1, 3)
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
        self.obb_c = np.vstack([b.obb_c for b in bodies])
        self.obb_ax = np.concatenate([b.obb_ax for b in bodies])
        self.obb_h = np.vstack([b.obb_h for b in bodies])
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
        # Bodenteile mit aufgefuellten Ecken (gleiche Anzahl je Teil, Auffuellung = erste Ecke)
        self.floor_parts = np.array(
            [i for bi in self.floor_bodies for i in range(offs[bi], offs[bi + 1])], dtype=np.int64
        )
        all_parts = [p for b in bodies for p in b.parts]
        nv = max((len(all_parts[i].vertices) for i in self.floor_parts), default=1)
        self.floor_V = np.empty((len(self.floor_parts), nv, 3))  # noqa: N815
        for r, i in enumerate(self.floor_parts):
            v = all_parts[i].vertices
            self.floor_V[r] = np.vstack([v, np.repeat(v[:1], nv - len(v), axis=0)])
        self.floor_index = {int(i): r for r, i in enumerate(self.floor_parts)}
        self.pa = np.concatenate(pa) if pa else np.zeros(0, dtype=np.int64)
        self.pb = np.concatenate(pb) if pb else np.zeros(0, dtype=np.int64)
        self.pid = np.concatenate(pid) if pid else np.zeros(0, dtype=np.int64)
        # Teilpaare des konstruktiv konstanten Paars (zaehlen nur unter d_hard)
        const = np.array([n == CONST_PAIR for n in self.pair_names], dtype=bool)
        self.k_const = const[self.pid] if self.pid.size else np.zeros(0, dtype=bool)
        # Statische Hindernisteile (Frame W): achsparallele Box (mit Aufmass) als engere Schranke.
        w = frame_index["W"]
        lo = np.vstack([p.vertices.min(axis=0) for b in bodies for p in b.parts])
        hi = np.vstack([p.vertices.max(axis=0) for b in bodies for p in b.parts])
        self.part_lo = lo - self.margins[:, None]
        self.part_hi = hi + self.margins[:, None]
        # Koerperebene: Paarbloecke in pa/pb (Index = Start + i_a * n_b + i_b), Huellkugeln bzw.
        # Boxen (statisch) je Koerper
        counts = np.bincount(self.pid, minlength=len(self.pair_names))
        self.pair_start = np.concatenate([[0], np.cumsum(counts)])
        self.pair_parts = [
            (np.arange(offs[a], offs[a + 1]), np.arange(offs[b], offs[b + 1])) for a, b in self.pair_bodies
        ]
        self.body_frame = np.array([frame_index[b.frame] for b in bodies])
        self.body_center = np.array([b.bcenter for b in bodies])
        self.body_radius = np.array([b.bradius for b in bodies])
        self.body_lo = np.array([b.blo for b in bodies])
        self.body_hi = np.array([b.bhi for b in bodies])
        self.pba = np.array([a for a, _ in self.pair_bodies], dtype=np.int64)
        self.pbb = np.array([b for _, b in self.pair_bodies], dtype=np.int64)
        self.pair_static = self.body_frame[self.pbb] == w


class World:
    """Kollisionswelt aus Default-Assets plus Teilmesh und Druckstand (Default-Backend fcl)."""

    def __init__(
        self,
        part_mesh_P,  # noqa: N803 - trimesh.Trimesh
        T_WP: np.ndarray,  # noqa: N803
        layer_height_mm: float = 10.0,
        root: Path = REPO_ROOT,
        r_free_mm: float = R_FREE_MM,
        d_hard_mm: float = D_HARD_MM,
    ) -> None:
        self.root = Path(root).resolve()
        self.d_hard_mm = float(d_hard_mm)
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
        untere Schranke >= upper (Paar und Zeugen gehoeren zum kleinsten ausgewerteten Paar).
        """
        return self.distance_batch(np.asarray(q, dtype=float)[None], [int(layer)], upper)[0]

    def distance_batch(
        self,
        Q: np.ndarray,
        layers,
        upper: float | None = None,  # noqa: N803
    ) -> list[Contact]:
        """`distance` fuer viele Posen. Die Schranken (Koerperpaar, Teil gegen Huelle des anderen
        Koerpers, Teilpaar) werden blockweise vektorisiert, nur die fcl-Abfragen laufen einzeln."""
        Q = np.atleast_2d(np.asarray(Q, dtype=float))  # noqa: N806
        n = len(Q)
        layers = np.broadcast_to(np.asarray(layers, dtype=np.int64), (n,))
        if n == 0:
            return []
        F = np.empty((n, len(LINKS) + 1, 4, 4))  # noqa: N806
        F[:, : len(LINKS)] = self.T_WB @ self.chain.link_poses_batch(Q)
        F[:, len(LINKS)] = np.eye(4)
        lim = np.inf if upper is None else float(upper)
        out: list[Contact | None] = [None] * n
        for k in np.unique(layers):
            idx = np.flatnonzero(layers == k)
            sc = self._scene(int(k))
            for s in range(0, len(idx), _BLOCK):
                ii = idx[s : s + _BLOCK]
                for i, c in zip(ii, self._distance_block(F[ii], sc, lim, self.d_hard_mm), strict=True):
                    out[i] = c
        return out  # type: ignore[return-value]

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

    def _distance_block(
        self,
        F: np.ndarray,  # noqa: N803
        sc: _LayerScene,
        lim: float,
        d_hard: float = D_HARD_MM,
    ) -> list[Contact]:
        """Branch-and-Bound fuer einen Block von Posen (F: (M, 8, 4, 4) Frames in W).

        Exakt: Jedes Teilpaar, dessen untere Schranke kleiner als das Endergebnis ist, wird mit
        fcl ausgewertet. Die Schranken sind Huellkugeln bzw. Boxen (statische Hindernisse) auf
        Koerper- und Teilebene; zusaetzlich faellt ein Teil weg, dessen Schranke gegen die Huelle
        des anderen Koerpers schon >= best ist (spart das volle Teilpaar-Kreuzprodukt).

        Statusregel: Teilpaare von CONST_PAIR gehen nur ein, wenn ihr Abstand < d_hard ist; sonst
        bleibt d das Minimum der uebrigen Paare (d_status).
        """
        M = len(F)  # noqa: N806
        best = np.full(M, np.inf)
        best_k = np.full(M, -1, dtype=np.int64)  # Teilpaar des Minimums, -1: Boden
        wit: list[tuple[np.ndarray, np.ndarray] | None] = [None] * M

        # Boden: Minimum von z ueber die Ecken minus Aufmass, exakt fuer konvexe Teile. Ecken nur
        # fuer Teile, deren Kugelschranke unter der kleinsten oberen Schranke liegt.
        floor_p = np.full(M, -1, dtype=np.int64)  # Teil (global) des Boden-Minimums
        floor_j = np.zeros(M, dtype=np.int64)
        fpart = sc.floor_parts
        if fpart.size:
            Fz = F[:, sc.part_frame[fpart], 2, :]  # (M, Teile, 4) z-Zeile  # noqa: N806
            cz = np.einsum("mpj,pj->mp", Fz[..., :3], sc.centers[fpart]) + Fz[..., 3]
            r = sc.radii[fpart]
            m_i, p_i = np.nonzero(cz - r <= (cz + r).min(axis=1)[:, None])
            z = np.einsum("cvj,cj->cv", sc.floor_V[p_i], Fz[m_i, p_i, :3]) + Fz[m_i, p_i, 3, None]
            j = np.argmin(z, axis=1)
            zj = z[np.arange(len(j)), j] - sc.margins[fpart[p_i]]
            order = np.lexsort((zj, m_i))
            first = order[np.r_[True, m_i[order][1:] != m_i[order][:-1]]]
            best[m_i[first]] = zj[first]
            floor_p[m_i[first]] = fpart[p_i[first]]
            floor_j[m_i[first]] = j[first]

        if len(sc.pa):
            objs, pa, pb, mg, pfr = sc.objs, sc.pa, sc.pb, sc.margins, sc.part_frame
            req = self._req
            k_const = sc.k_const
            tfs: list[dict[int, fcl.Transform]] = [{} for _ in range(M)]

            def place(m: int, part: int) -> None:
                fi = int(pfr[part])
                tf = tfs[m].get(fi)
                if tf is None:
                    T = F[m, fi]  # noqa: N806
                    tf = tfs[m][fi] = fcl.Transform(T[:3, :3].copy(), T[:3, 3].copy())
                objs[part].setTransform(tf)

            def evaluate(m: int, k: int) -> None:
                a, b = int(pa[k]), int(pb[k])
                place(m, a)
                place(m, b)
                res = fcl.DistanceResult()
                d = fcl.distance(objs[a], objs[b], req, res) - mg[a] - mg[b]
                if d >= d_hard and k_const[k]:
                    return
                if d < best[m]:
                    best[m] = d
                    best_k[m] = k
                    p_a, p_b = (np.asarray(x, dtype=float) for x in res.nearest_points)
                    wit[m] = _shift_witness(p_a, p_b, mg[a], mg[b], d)

            # Warmstart: das Teilpaar des letzten Minimums liefert frueh eine gute Schranke, dazu
            # je Pose eine Saat aus den Koerperpaaren mit der kleinsten Schranke.
            warm = self._warm.get(id(sc))
            if warm is not None:
                for m in range(M):
                    evaluate(m, warm)
            bb = _BlockBounds(F, sc)
            for m, k in zip(*bb.seeds(2), strict=True):
                if k != warm:
                    evaluate(m, k)
            cand_m, cand_k, cand_lb = bb.candidates(np.minimum(best, lim))
            if cand_m.size:
                order = np.lexsort((cand_lb, cand_m))
                starts = np.searchsorted(cand_m[order], np.arange(M + 1))
                ks, lbs = cand_k[order].tolist(), cand_lb[order].tolist()
                for m in range(M):
                    for i in range(int(starts[m]), int(starts[m + 1])):
                        if lbs[i] >= min(best[m], lim):
                            break
                        if k_const[ks[i]] and lbs[i] >= d_hard:
                            continue
                        if ks[i] != warm:
                            evaluate(m, ks[i])
            last = best_k[best_k >= 0]
            if last.size:
                self._warm[id(sc)] = int(last[-1])

        out = []
        for m in range(M):
            d = float(best[m])
            k = int(best_k[m])
            if k >= 0:
                pair = sc.pair_names[int(sc.pid[k])]
                w = wit[m]
            elif floor_p[m] >= 0:
                part = int(floor_p[m])
                T = F[m, sc.part_frame[part]]  # noqa: N806
                p = T[:3, :3] @ sc.floor_V[sc.floor_index[part], floor_j[m]] + T[:3, 3]
                pair = (sc.bodies[int(sc.part_body[part])].name, FLOOR)
                w = (p - np.array([0.0, 0.0, sc.margins[part]]), np.array([p[0], p[1], 0.0]))
            else:
                pair, w = ("", ""), (np.full(3, np.nan), np.full(3, np.nan))
            if d >= lim:  # Abbruch: alle Paare mit Schranke < lim sind ausgewertet, also d >= lim
                d = lim
            if not np.isfinite(d):
                d = 1e9
            out.append(Contact(d, pair, w))  # type: ignore[arg-type]
        return out


class _BlockBounds:
    """Untere Schranken eines Posen-Blocks (M Posen) fuer eine Druckstand-Szene.

    Koerperpaar: Huellkugeln (statisch: Box des Hindernisses). Teil gegen Huelle des anderen
    Koerpers, dann Teilpaar (Kugeln bzw. Teilbox). Alle Schranken gelten auch bei Durchdringung
    (vorzeichenbehafteter Abstand Kugel -> Box), weil die Teile in Kugeln bzw. Boxen liegen.
    """

    def __init__(self, F: np.ndarray, sc: _LayerScene) -> None:  # noqa: N803
        self.sc = sc
        self.F = F
        fr = F[:, sc.body_frame]
        self.cb = np.einsum("mnij,nj->mni", fr[..., :3, :3], sc.body_center) + fr[..., :3, 3]
        fp = F[:, sc.part_frame]
        self.cw = np.einsum("mnij,nj->mni", fp[..., :3, :3], sc.centers) + fp[..., :3, 3]
        brad = sc.body_radius
        ca_ = self.cb[:, sc.pba]
        blb = _norm(ca_ - self.cb[:, sc.pbb]) - brad[sc.pba] - brad[sc.pbb]
        st = sc.pair_static
        if st.any():
            b = sc.pbb[st]
            blb[:, st] = np.maximum(
                blb[:, st], _box_sd(ca_[:, st], sc.body_lo[b], sc.body_hi[b]) - brad[sc.pba[st]]
            )
        self.blb = blb  # (M, Koerperpaare)

    def _part_bounds(self, p: int, mm: np.ndarray):
        sc, cw, cb = self.sc, self.cw, self.cb
        ia, ib = sc.pair_bodies[p]
        A, B = sc.pair_parts[p]  # noqa: N806
        rad, brad = sc.radii, sc.body_radius
        cA = cw[mm[:, None], A[None, :]]  # noqa: N806
        dA = _norm(cA - cb[mm, ib][:, None]) - rad[A] - brad[ib]  # noqa: N806
        sA = cb[mm, ia][:, None]  # noqa: N806
        dB = _norm(cw[mm[:, None], B[None, :]] - sA) - rad[B] - brad[ia]  # noqa: N806
        if sc.pair_static[p]:
            dA = np.maximum(dA, _box_sd(cA, sc.body_lo[ib], sc.body_hi[ib]) - rad[A])  # noqa: N806
            dB = np.maximum(dB, _box_sd(sA, sc.part_lo[B], sc.part_hi[B]) - brad[ia])  # noqa: N806
        return dA, dB, A, B

    def seeds(self, n: int) -> tuple[list[int], list[int]]:
        """Je Pose fuer die n Koerperpaare mit kleinster Schranke das Teilpaar der jeweils
        naechsten Teile: (Pose, Paarindex) zum Vorab-Auswerten (obere Schranke)."""
        top = np.argsort(self.blb, axis=1)[:, :n]
        out_m, out_k = [], []
        for p in np.unique(top):
            mm = np.flatnonzero((top == p).any(axis=1))
            dA, dB, _, B = self._part_bounds(int(p), mm)  # noqa: N806
            out_m.append(mm)
            out_k.append(self.sc.pair_start[p] + dA.argmin(axis=1) * len(B) + dB.argmin(axis=1))
        if not out_m:
            return [], []
        return np.concatenate(out_m).tolist(), np.concatenate(out_k).tolist()

    def _obb_sep(self, m: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Untere Schranke je Teilpaar: groesste Trennung der orientierten Boxen entlang der
        Mittenlinie und der sechs Boxachsen, minus Aufmass (gilt auch bei Durchdringung)."""
        sc = self.sc
        Fa, Fb = self.F[m, sc.part_frame[a]], self.F[m, sc.part_frame[b]]  # noqa: N806
        ca_ = np.einsum("cij,cj->ci", Fa[:, :3, :3], sc.obb_c[a]) + Fa[:, :3, 3]
        cb_ = np.einsum("cij,cj->ci", Fb[:, :3, :3], sc.obb_c[b]) + Fb[:, :3, 3]
        Aa, Ab = Fa[:, :3, :3] @ sc.obb_ax[a], Fb[:, :3, :3] @ sc.obb_ax[b]  # noqa: N806
        dc = cb_ - ca_
        u = dc / np.maximum(_norm(dc), 1e-9)[:, None]
        axes = np.concatenate([u[:, :, None], Aa, Ab], axis=2)  # (c,3,7) Spalten = Achsen
        ra = (np.abs(np.einsum("cik,cij->cjk", axes, Aa)) * sc.obb_h[a][:, :, None]).sum(1)
        rb = (np.abs(np.einsum("cik,cij->cjk", axes, Ab)) * sc.obb_h[b][:, :, None]).sum(1)
        gap = np.abs(np.einsum("ci,cik->ck", dc, axes)) - ra - rb
        return gap.max(axis=1) - sc.margins[a] - sc.margins[b]

    def candidates(self, bound: np.ndarray):
        """Teilpaare mit unterer Schranke < bound je Pose: (Pose, Paarindex, Schranke)."""
        sc, cw, rad = self.sc, self.cw, self.sc.radii
        out_m, out_k, out_lb = [], [], []
        for p in range(len(sc.pair_bodies)):
            mm = np.flatnonzero(self.blb[:, p] < bound)
            if not mm.size:
                continue
            bnd = bound[mm][:, None]
            dA, dB, A, B = self._part_bounds(p, mm)  # noqa: N806
            r, ja, jb = np.nonzero((dA < bnd)[:, :, None] & (dB < bnd)[:, None, :])
            if not r.size:
                continue
            ga, gb, mr = A[ja], B[jb], mm[r]
            c = cw[mr, ga]
            lb = _norm(c - cw[mr, gb]) - rad[ga] - rad[gb]
            if sc.pair_static[p]:
                lb = np.maximum(lb, _box_sd(c, sc.part_lo[gb], sc.part_hi[gb]) - rad[ga])
            keep = lb < bound[mr]
            if keep.any():  # Trennachsen der orientierten Boxen: engere Schranke vor fcl
                mr, ja, jb, lb = mr[keep], ja[keep], jb[keep], lb[keep]
                lb = np.maximum(lb, self._obb_sep(mr, A[ja], B[jb]))
                keep = lb < bound[mr]
            out_m.append(mr[keep])
            out_k.append(sc.pair_start[p] + ja[keep] * len(B) + jb[keep])
            out_lb.append(lb[keep])
        if not out_m:
            return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
        return np.concatenate(out_m), np.concatenate(out_k), np.concatenate(out_lb)


def _norm(v: np.ndarray) -> np.ndarray:
    return np.sqrt(np.einsum("...i,...i->...", v, v))


def _obb(v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Orientierte Box um Punkte (Hauptachsen): Mitte, Achsen (Spalten), halbe Kantenlaengen."""
    c0 = v.mean(axis=0)
    _, ax = np.linalg.eigh(np.cov((v - c0).T))
    p = (v - c0) @ ax
    lo, hi = p.min(axis=0), p.max(axis=0)
    return c0 + ax @ (0.5 * (lo + hi)), ax, 0.5 * (hi - lo) + 1e-9


def _box_sd(c: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Vorzeichenbehafteter Abstand Punkt -> achsparallele Box (innen negativ)."""
    gap = np.maximum(np.maximum(lo - c, c - hi), 0.0)
    inner = np.maximum(np.minimum(c - lo, hi - c).min(axis=-1), 0.0)
    return _norm(gap) - inner


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
