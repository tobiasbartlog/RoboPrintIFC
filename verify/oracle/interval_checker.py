"""Schnelle, exakte Statusbestimmung entlang dichter Trajektorien (fuer check_run).

Der Status eines Samples und alle Pruefkriterien haengen nur davon ab, auf welcher Seite fester
Schwellen der kleinste Abstand d liegt (0, d_hard, 12, d_target - 1, d_target + 12, ...). Statt d auf jedem
Sample exakt zu berechnen, haelt der Pruefer fuer jedes Paar aus SPEC §5.1 ein Intervall [lb, ub]:

- lb: eine beim letzten Nachrechnen bewiesene untere Schranke, vermindert um die seither maximal
  moegliche Verschiebung beider Koerper (Odometer: Summe je Schritt von |dR c + dt| + ||dR||_2 r ueber
  die Huellkugel (c, r) des Koerpers; Abstaende aendern sich hoechstens um die Summe der Verschiebungen).
- ub: Abstand des zuletzt gefundenen Zeugenpunktpaars (je ein Punkt auf beiden Oberflaechen, im
  Koerper-Frame gespeichert) in der aktuellen Pose; das ist immer eine obere Schranke.

Liegt eine Schwelle t zwischen min(lb) und min(ub), werden alle Paare mit lb < t gegen t nachgerechnet
(Huellkugeln, konvexe Huellen, Coal-BVH auf den Roh-Dreiecken wie in collision_oracle). Danach ist
entweder d >= t bewiesen oder ein exakter Abstand < t bekannt. Kollisionen (Dreiecksschnitt oder
Enthaltensein) werden exakt erkannt; ihre Tiefe wird hier nicht bestimmt.
"""

from __future__ import annotations

from dataclasses import dataclass

import coal
import numpy as np

from verify.oracle.collision_oracle import CollisionOracle, _ascending, _contained

COLLISION_D = -1e-3


@dataclass
class Interval:
    lb: float  # untere Schranke von d (-inf bei Kollision)
    ub: float  # obere Schranke von d (COLLISION_D bei Kollision)
    pair: tuple[str, str]  # Paar, das ub liefert
    witness_W: tuple[np.ndarray, np.ndarray] | None

    @property
    def collision(self) -> bool:
        return self.ub < 0


def _disp(c: np.ndarray, r: float, T0: np.ndarray, T1: np.ndarray) -> float:
    """Obere Schranke der Verschiebung aller Punkte der Kugel (c, r) im Koerper-Frame zwischen T0, T1."""
    dR = T1[:3, :3] - T0[:3, :3]
    lin = dR @ c + (T1[:3, 3] - T0[:3, 3])
    return float(np.sqrt(lin @ lin) + np.sqrt((dR * dR).sum() / 2.0) * r)


class IntervalChecker:
    def __init__(self, oracle: CollisionOracle, thresholds):
        self.o = oracle
        self.T = sorted({float(t) for t in thresholds})
        self.pairs = [p for p in oracle.pairs if p[1] != "floor"]
        self.floor = [p[0] for p in oracle.pairs if p[1] == "floor"]
        self.moving = sorted({p[0] for p in oracle.pairs} | {p[1] for p in self.pairs
                                                             if p[1] in oracle.links})
        self.reset()

    def reset(self) -> None:
        P = len(self.pairs)
        self.layer = None
        self.prev_poses: dict[str, np.ndarray] | None = None
        self.odo = {n: 0.0 for n in self.moving}
        self.lb_ref = np.full(P, -np.inf)
        self.odo_a = np.zeros(P)
        self.odo_b = np.zeros(P)
        self.wit: list[tuple[np.ndarray, np.ndarray] | None] = [None] * P
        self.coll_ref: list[bool] = [False] * P
        self.fresh = np.zeros(P, dtype=bool)  # Kollision in genau dieser Pose festgestellt

    # ------------------------------------------------------------------------
    def evaluate(self, q, layer: int) -> Interval:
        o = self.o
        poses = o.body_poses(q)
        k = int(layer)
        if k != self.layer:
            for i, (_, b) in enumerate(self.pairs):
                if b == "printed":
                    self.lb_ref[i] = -np.inf
                    self.wit[i] = None
                    self.coll_ref[i] = False
            self.layer = k
        if self.prev_poses is not None:
            for n in self.moving:
                B = o._body(n, k)
                self.odo[n] += _disp(B.c, B.r, self.prev_poses[n], poses[n])
        self.prev_poses = poses
        self._tf: dict[str, coal.Transform3s] = {}
        self.fresh[:] = False

        # Boden exakt
        f_best, f_pair, f_w = np.inf, None, None
        for a in self.floor:
            A = o._body(a, k)
            T = poses[a]
            z = A.hull_vertices @ T[2, :3] + T[2, 3]
            i = int(np.argmin(z))
            if z[i] < f_best:
                p = T[:3, :3] @ A.hull_vertices[i] + T[:3, 3]
                f_best, f_pair, f_w = float(z[i]), (a, "floor"), (p, np.array([p[0], p[1], 0.0]))

        active = [i for i, (a, b) in enumerate(self.pairs) if o._body(b, k) is not None]
        oa = np.array([self.odo.get(self.pairs[i][0], 0.0) for i in active])
        ob = np.array([self.odo.get(self.pairs[i][1], 0.0) for i in active])
        act = np.array(active, dtype=int)
        lb = self.lb_ref[act] - (oa - self.odo_a[act]) - (ob - self.odo_b[act])
        lb = np.where(np.isfinite(lb), lb, -np.inf)
        ub = np.full(len(act), np.inf)
        for j, i in enumerate(act):
            if self.coll_ref[i]:
                lb[j] = -np.inf  # Kollision gilt nur in ihrer Pose; neu rechnen
        tmax = self.T[-1]
        for j, i in enumerate(act):
            if lb[j] < tmax:
                ub[j] = self._ub(i, poses)

        for _ in range(len(self.T) + 2):
            L = min(float(lb.min()) if len(lb) else np.inf, f_best)
            U = min(float(ub.min()) if len(ub) else np.inf, f_best)
            open_t = [t for t in self.T if L < t <= U]
            if not open_t:
                break
            t = open_t[-1]
            for j in np.argsort(lb):
                if lb[j] >= t:
                    break
                lb[j], ub[j] = self._refine(int(act[j]), t, poses, k)
        L = min(float(lb.min()) if len(lb) else np.inf, f_best)
        if len(ub) and float(ub.min()) < f_best:
            j = int(np.argmin(ub))
            i = int(act[j])
            pair = self.pairs[i]
            w = self._witness_W(i, poses)
            return Interval(L, float(ub[j]), pair, w)
        return Interval(L, f_best, f_pair, f_w)

    # ------------------------------------------------------------------------
    def _ub(self, i: int, poses) -> float:
        if self.fresh[i]:
            return COLLISION_D
        w = self.wit[i]
        if w is None:
            return np.inf
        a, b = self.pairs[i]
        Ta, Tb = poses.get(a, np.eye(4)), poses.get(b, np.eye(4))
        d = (Ta[:3, :3] @ w[0] + Ta[:3, 3]) - (Tb[:3, :3] @ w[1] + Tb[:3, 3])
        return float(np.sqrt(d @ d))

    def _witness_W(self, i: int, poses):
        w = self.wit[i]
        if w is None:
            return None
        a, b = self.pairs[i]
        Ta, Tb = poses.get(a, np.eye(4)), poses.get(b, np.eye(4))
        return (Ta[:3, :3] @ w[0] + Ta[:3, 3], Tb[:3, :3] @ w[1] + Tb[:3, 3])

    def _coal_tf(self, key: str, T: np.ndarray) -> coal.Transform3s:
        if key not in self._tf:
            self._tf[key] = coal.Transform3s(np.ascontiguousarray(T[:3, :3]), np.ascontiguousarray(T[:3, 3]))
        return self._tf[key]

    def _store(self, i: int, lbv: float, wit_W=None, Ta=None, Tb=None, collision: bool = False) -> None:
        a, b = self.pairs[i]
        self.lb_ref[i] = lbv
        self.odo_a[i] = self.odo.get(a, 0.0)
        self.odo_b[i] = self.odo.get(b, 0.0)
        self.coll_ref[i] = collision
        self.fresh[i] = collision
        if wit_W is not None:
            pa = Ta[:3, :3].T @ (wit_W[0] - Ta[:3, 3])
            pb = Tb[:3, :3].T @ (wit_W[1] - Tb[:3, 3])
            self.wit[i] = (pa, pb)

    def _refine(self, i: int, t: float, poses, k: int) -> tuple[float, float]:
        """Paar i gegen Schwelle t nachrechnen. Rueckgabe (lb, ub) in der aktuellen Pose."""
        o = self.o
        a, b = self.pairs[i]
        A, B = o._body(a, k), o._body(b, k)
        Ta, Tb = poses.get(a, np.eye(4)), poses.get(b, np.eye(4))
        ta = self._coal_tf("tool" if a in ("tool_body", "nozzle_tip") else a, Ta)
        tb = self._coal_tf(b if b in o.links else "world", Tb)
        dreq = coal.DistanceRequest()
        overlap = True
        if A.convex is not None and B.convex is not None:
            lb2 = coal.distance(A.convex, ta, B.convex, tb, dreq, coal.DistanceResult())
            if lb2 >= t:
                self._store(i, lb2)
                return lb2, self._ub(i, poses)
            overlap = lb2 <= 0
        cwa = A.cc @ Ta[:3, :3].T + Ta[:3, 3]
        cwb = B.cc @ Tb[:3, :3].T + Tb[:3, 3]
        D = (np.linalg.norm(cwa[:, None, :] - cwb[None, :, :], axis=2)
             - A.cr[:, None] - B.cr[None, :]).ravel()
        sel = np.flatnonzero(D < t)
        rest = np.ones(len(D), dtype=bool)
        rest[sel] = False
        lb_min = float(D[rest].min()) if rest.any() else np.inf
        best, best_w = np.inf, None
        nB = len(B.chunks)
        hit = False
        for f in _ascending(D, sel):
            lim = min(t, best)
            if D[f] >= lim:
                lb_min = min(lb_min, float(D[f]))
                break
            ci, cj = A.chunks[f // nB], B.chunks[f % nB]
            if ci.convex is not None and cj.convex is not None:
                lb3 = coal.distance(ci.convex, ta, cj.convex, tb, dreq, coal.DistanceResult())
                if lb3 >= lim:
                    lb_min = min(lb_min, lb3)
                    continue
            res = coal.DistanceResult()
            d = coal.distance(ci.bvh, ta, cj.bvh, tb, dreq, res)
            if d <= 0:
                hit = True
                break
            if d < best:
                if best < np.inf:
                    lb_min = min(lb_min, best)
                best, best_w = float(d), (np.array(res.getNearestPoint1()), np.array(res.getNearestPoint2()))
            else:
                lb_min = min(lb_min, d)
        if not hit and overlap and (_contained(A, Ta, B, Tb) or _contained(B, Tb, A, Ta)):
            hit = True
        if hit:
            self._store(i, -np.inf, collision=True)
            return -np.inf, COLLISION_D
        if best < t:
            self._store(i, best, best_w, Ta, Tb)
            return best, best
        lbv = min(best, lb_min)
        self._store(i, lbv, best_w, Ta, Tb)
        return lbv, self._ub(i, poses)
