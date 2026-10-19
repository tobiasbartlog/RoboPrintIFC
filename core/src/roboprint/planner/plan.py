"""Ein Teil planen: Ringe (Ladder-Graph), Travel (SPEC §5.3), Verdichtung, Pruefung, Ergebnis.

Ablauf je Ring (spec/ARTEFAKTE.md): lift -> transfer -> lower -> approach -> print -> retract.
Der erste Ring beginnt mit `transfer` aus der Home-Pose (Sample 0 ist Home), nach dem letzten
Ring folgt ein `lift`. `layer[i]` ist die Anzahl k fertiger Schichten:
print/approach/retract von Schicht L: k = L; lift nach Schicht L: k = L + 1;
transfer/lower vor einem Ring: k = (Schicht des vorigen Rings) + 1, vor dem ersten Ring 0.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from roboprint.robot import HOME_Q

from .backend import can_fork_pool, contacts_batch, contacts_parallel
from .densify import Dense, movej, movel, movel_chain
from .graph import N_BRANCH, RingGraph, RingPath, build_graph, mark_hard, solve_ring
from .kin import Kin, nearest_variant
from .params import PlannerParams

_RING_RETRIES = 2
#: Planer, dessen Ring-Graphen die Pool-Prozesse bauen (fork erbt ihn, siehe `_graph_worker`)
_POOL_PLANNER: Any = None


#: Abschlusspruefung waehrend der Planung: Samples blockweise an den Pool, sobald so viele da sind
_CHECK_BLOCK = 2000


def _graph_worker(i: int) -> tuple[int, RingGraph]:
    pp = _POOL_PLANNER
    task = pp.rings[i]
    return task.index, build_graph(pp.kin, task.p_W, task.layer, pp.p, pp.screen if pp.aware else None)


def _check_worker(args: tuple[np.ndarray, np.ndarray]) -> list[Any]:
    return contacts_batch(_POOL_PLANNER.final, *args)


@dataclass
class RingTask:
    """Ein Druckring in W: Wegpunkte (geschlossen), Schicht, Index im Toolpath."""

    index: int
    layer: int
    p_W: np.ndarray  # (n,3)  # noqa: N815


@dataclass
class Samples:
    q: list[np.ndarray] = field(default_factory=list)
    ok: list[np.ndarray] = field(default_factory=list)
    p_W: list[np.ndarray] = field(default_factory=list)  # noqa: N815
    psi: list[np.ndarray] = field(default_factory=list)
    kind: list[str] = field(default_factory=list)
    ring: list[int] = field(default_factory=list)
    layer: list[int] = field(default_factory=list)
    contacts: list[Any] = field(default_factory=list)
    n: int = 0

    def add(self, d: Dense, kind: str, ring: int, layer: int, contacts: list[Any] | None = None) -> range:
        m = len(d.q)
        self.q.append(d.q)
        self.ok.append(d.ok)
        self.p_W.append(d.p_W)
        self.psi.append(d.psi)
        self.kind += [kind] * m
        self.ring += [ring] * m
        self.layer += [layer] * m
        self.contacts += contacts if contacts is not None else [None] * m
        r = range(self.n, self.n + m)
        self.n += m
        return r


@dataclass
class PlannedPath:
    """Ergebnis des Planers fuer ein Teil (vor der Zeitparametrierung)."""

    q: np.ndarray  # (N,6)
    reachable: np.ndarray  # (N,)
    p_W: np.ndarray  # (N,3) Soll-TCP  # noqa: N815
    psi: np.ndarray  # (N,)
    kind: list[str]
    ring: list[int]
    layer: list[int]
    branch: np.ndarray  # (N,)
    contacts: list[Any]  # Contact | None (unreachable)
    status: list[str]
    feasible: bool
    cause: dict[str, Any] | None
    d_min_mm: float | None
    branch_switches_in_rings: int
    timings_s: dict[str, float] = field(default_factory=dict)


def _status(c: Any, ok: bool, p: PlannerParams) -> str:
    if not ok:
        return "unreachable"
    if c.d_mm < 0.0:
        return "collision"
    return "warn" if c.d_mm < p.d_target_mm else "ok"


class PartPlanner:
    """Plant ein Teil an einer festen Platzierung (T_WP)."""

    def __init__(
        self,
        kin: Kin,
        rings: list[RingTask],
        T_WP: np.ndarray,  # noqa: N803
        params: PlannerParams,
        real: Any,
        screen: Any | None,
        collision_aware: bool = True,
        part_height_mm: float | None = None,
        final: Any | None = None,
        procs: int = 1,
    ) -> None:
        self.kin, self.rings, self.p = kin, rings, params
        self.T_WP = np.asarray(T_WP, float)
        self.real, self.screen = real, screen
        # `final`: Backend der Abschlusspruefung aller Samples (echte Welt); `real` prueft waehrend
        # der Planung (Travel-Entscheidungen, Ring-Nachplanung) und darf ein schnelles Double sein.
        self.final = final if final is not None else real
        self.procs = procs
        self.aware = collision_aware
        self.z0 = float(self.T_WP[2, 3])
        n_layers = 1 + max((r.layer for r in rings), default=0)
        self.height = part_height_mm if part_height_mm is not None else n_layers * params.layer_height_mm
        self.s = Samples()
        self.timings = {"graph": 0.0, "dense": 0.0, "check": 0.0}
        self._graphs: dict[int, RingGraph] = {}
        self._graph_iter: Any = None
        # Abschlusspruefung im Pool, waehrend der Hauptprozess weiterplant (nur mit Double-Planung)
        self._pool: Any = None
        self._pending: list[tuple[int, int, Any]] = []  # (erstes Sample, Anzahl, AsyncResult)
        self._sent = 0  # Samples bis hierher an den Pool gegeben
        self._final_done = np.zeros(0, bool)

    # -------------------------------------------------------------- Hilfen
    def stand_top_W(self, k: int) -> float:  # noqa: N802
        return self.z0 + min(k * self.p.layer_height_mm, self.height)

    def _check(self, d: Dense, layer: int, force: bool = False) -> list[Any]:
        """Kontakte fuer die erreichbaren Samples (None fuer unreachable oder ungeprueft).

        Plant der Planer mit dem Double (`real` ist nicht `final`), werden nur Travel-Stuecke
        (`force`) waehrend der Planung geprueft; alles andere prueft die Abschlusspruefung.
        """
        t = time.perf_counter()
        out: list[Any] = [None] * len(d.q)
        if not force and self.final is not self.real:
            return out
        idx = np.nonzero(d.ok)[0]
        if idx.size:
            cs = contacts_batch(self.real, d.q[idx], np.full(len(idx), layer))
            for i, c in zip(idx, cs, strict=True):
                out[i] = c
        self.timings["check"] += time.perf_counter() - t
        return out

    def _bad(self, contacts: list[Any], d: Dense) -> np.ndarray:
        dd = np.array([c.d_mm if c is not None else np.inf for c in contacts])
        return (dd < self.p.d_hard_mm) | ~d.ok

    def _ik_branch(self, p_W: np.ndarray, psi: float, branch: int, q_ref: np.ndarray):  # noqa: N803
        Q, ok = self.kin.ik(p_W[None], np.array([psi]))
        if ok[0, branch]:
            return nearest_variant(Q[0, branch], q_ref)
        return None

    # -------------------------------------------------------------- Ring
    def _graph(self, task: RingTask) -> RingGraph:
        """Ring-Graph (IK, Vorauswahl, Kanten) haengt nicht vom Vorgaenger ab: aus dem Pool, falls
        vorausgebaut, sonst hier. Jede Suche bekommt frische Pruefwerte `d_real`."""
        while task.index not in self._graphs and self._graph_iter is not None:
            try:
                i, g = next(self._graph_iter)
            except StopIteration:
                self._graph_iter = None
                break
            self._graphs[i] = g
        g = self._graphs.get(task.index)
        if g is None:
            g = build_graph(self.kin, task.p_W, task.layer, self.p, self.screen if self.aware else None)
            self._graphs[task.index] = g
        for k in [k for k in self._graphs if k < task.index]:
            del self._graphs[k]
        return replace(g, d_real=np.full_like(g.d_real, np.nan))

    def _plan_ring(self, task: RingTask, q_prev, b_prev, force_branch=None):
        t = time.perf_counter()
        g = self._graph(task)
        path = solve_ring(g, self.p, self.real if self.aware else None, q_prev, b_prev, force_branch)
        self.timings["graph"] += time.perf_counter() - t
        return g, path

    def _print_dense(self, task: RingTask, path: RingPath) -> tuple[Dense, np.ndarray]:
        """Druck-Samples entlang des Pfads; liefert auch den Wegpunkt-Index (Segmentende) je Sample.

        Zusammenhaengend erreichbare Wegpunkte werden in einem Zug verdichtet (`movel_chain`);
        ein Wegpunkt ohne Knoten wird ein `unreachable`-Sample, danach geht es mit einem Sprung
        weiter (faellt in der Dichtepruefung auf, das Teil ist dann nicht machbar)."""
        t = time.perf_counter()
        parts, seg = [], []
        n = len(task.p_W)
        q_cur = path.q[0]
        psi_cur = float(path.psi[0])
        i = 0
        while i < n - 1:
            if path.states[i] >= 0 and path.states[i + 1] >= 0:
                j = i + 1
                while j + 1 < n and path.states[j + 1] >= 0:
                    j += 1
                d, si = movel_chain(
                    self.kin, task.p_W[i : j + 1], path.psi[i : j + 1], q_cur, path.branch[i : j + 1], self.p
                )
                parts.append(d)
                seg.append(si + i)
                if d.ok.any():
                    q_cur = d.q[np.nonzero(d.ok)[0][-1]]
                psi_cur = float(path.psi[j])
                i = j
                continue
            if path.states[i + 1] < 0:  # Wegpunkt ohne Gelenkloesung: unreachable
                d = Dense(
                    q_cur[None], np.zeros(1, bool), task.p_W[i + 1][None], np.array([psi_cur]), np.ones(1)
                )
            else:  # wieder erreichbar: Sprung
                q_cur, psi_cur = path.q[i + 1], float(path.psi[i + 1])
                d = Dense(
                    q_cur[None], np.ones(1, bool), task.p_W[i + 1][None], np.array([psi_cur]), np.ones(1)
                )
            parts.append(d)
            seg.append(np.full(1, i + 1))
            i += 1
        self.timings["dense"] += time.perf_counter() - t
        return _cat(parts), np.concatenate(seg) if seg else np.zeros(0, int)

    # -------------------------------------------------------------- Travel
    def _transfer(self, q_a: np.ndarray, q_b: np.ndarray, p_a: np.ndarray, p_b: np.ndarray, k: int):
        """movej q_a -> q_b, bei Bedarf ueber einen Zwischenpunkt hoeher und mittig (SPEC §5.3).

        Liefert (Liste von (Dense, Kontakte)), frei?
        """
        t = time.perf_counter()
        d = movej(self.kin, q_a, q_b, self.p)
        self.timings["dense"] += time.perf_counter() - t
        c = self._check(d, k, force=True)
        if not self.aware or not self._bad(c, d).any():
            return [(d, c)], True
        best = [(d, c)]
        mid = 0.5 * (p_a + p_b)
        for hgt in self.p.via_heights_mm:
            p_via = np.array([mid[0], mid[1], self.stand_top_W(k) + hgt])
            q_ref = 0.5 * (q_a + q_b)
            cands = []
            for psi in self.p.psi_grid[::2]:
                Q, ok = self.kin.ik(p_via[None], np.array([psi]))
                for b in range(N_BRANCH):
                    if ok[0, b]:
                        qv = nearest_variant(Q[0, b], q_ref)
                        cands.append((float(np.abs(qv - q_a).max() + np.abs(qv - q_b).max()), qv))
            cands.sort(key=lambda x: x[0])
            for _, qv in cands[:4]:
                d1 = movej(self.kin, q_a, qv, self.p)
                c1 = self._check(d1, k, force=True)
                if self._bad(c1, d1).any():
                    continue
                d2 = movej(self.kin, qv, q_b, self.p)
                c2 = self._check(d2, k, force=True)
                if not self._bad(c2, d2).any():
                    return [(d1, c1), (d2, c2)], True
        return best, False

    # -------------------------------------------------------------- Hauptablauf
    def run(self) -> PlannedPath:
        """Plant alle Ringe; mit `procs` > 1 bauen Pool-Prozesse die Ring-Graphen voraus."""
        import multiprocessing as mp

        global _POOL_PLANNER
        if self.procs <= 1 or len(self.rings) < 2 or not can_fork_pool():
            self._run()
            return self._finish()
        _POOL_PLANNER = self
        try:
            with mp.get_context("fork").Pool(self.procs) as pool:
                self._graph_iter = pool.imap(_graph_worker, range(len(self.rings)))
                if self.final is not self.real:
                    self._pool = pool
                self._run()
                self._collect_checks()
        finally:
            _POOL_PLANNER = None
            self._graph_iter = self._pool = None
            self._graphs = {}
        return self._finish()

    def _submit_checks(self, flush: bool = False) -> None:
        """Neue erreichbare Samples (ab `_sent`) blockweise an den Pool zur Abschlusspruefung."""
        n = self.s.n
        if self._pool is None or n - self._sent < (1 if flush else _CHECK_BLOCK):
            return
        q = np.vstack(self.s.q)[self._sent :]
        ok = np.concatenate(self.s.ok)[self._sent :]
        lay = np.asarray(self.s.layer[self._sent :])
        idx = np.flatnonzero(ok)
        for a in range(0, len(idx), _CHECK_BLOCK):
            ix = idx[a : a + _CHECK_BLOCK]
            res = self._pool.apply_async(_check_worker, ((q[ix], lay[ix]),))
            self._pending.append((self._sent, ix, res))
        self._sent = n

    def _collect_checks(self) -> None:
        """Rest abschicken, auf alle Pool-Pruefungen warten, Kontakte eintragen."""
        if self._pool is None:
            return
        t = time.perf_counter()
        self._submit_checks(flush=True)
        done = np.zeros(self.s.n, bool)
        for start, ix, res in self._pending:
            for i, c in zip(ix, res.get(), strict=True):
                self.s.contacts[start + int(i)] = c
            done[start + ix] = True
        self._pending = []
        self._final_done = done
        self.timings["final_check"] = time.perf_counter() - t

    def _run(self) -> None:
        p, s = self.p, self.s
        up = np.array([0.0, 0.0, p.approach_mm])
        q_cur = HOME_Q.copy()
        p_cur = self.kin.tcp_W(q_cur[None])[0, :3, 3]
        s.add(
            Dense(q_cur[None], np.ones(1, bool), p_cur[None], np.zeros(1), np.zeros(1)),
            "transfer",
            0,
            0,
            self._check(Dense(q_cur[None], np.ones(1, bool), p_cur[None], np.zeros(1), np.zeros(1)), 0),
        )
        s.psi[0] = np.array([float(_psi_q(self.kin, q_cur))])
        b_prev: int | None = None
        k_travel = 0
        psi_cur = float(s.psi[0][0])
        for task in self.rings:
            L = task.layer
            start = task.p_W[0]
            self._k_lower = k_travel
            appr = start + up
            z_travel = max(self.stand_top_W(k_travel) + p.z_lift_mm, appr[2])
            p_ls = np.array([appr[0], appr[1], z_travel])
            # Ring planen; Zweigwechsel nur am Transfer, falls dieser unfrei bleibt
            order: list[int | None] = [None]
            chosen = None
            for force in order:
                g, path = self._plan_ring(task, q_cur, b_prev, force)
                for _ in range(_RING_RETRIES + 1):
                    res = self._ring_motion(task, path, p_ls, appr, L)
                    if res is None:
                        break
                    bad_wp = res[-1]
                    if not self.aware or bad_wp.size == 0:
                        break
                    mark_hard(g, path, bad_wp)
                    t = time.perf_counter()
                    path = solve_ring(g, p, self.real, q_cur, b_prev, force)
                    self.timings["graph"] += time.perf_counter() - t
                if res is None:
                    continue
                q_ls = res[0]
                legs, free = self._transfer(q_cur, q_ls, p_cur, p_ls, k_travel)
                if free or not self.aware:
                    chosen = (path, res, legs)
                    break
                if chosen is None:
                    chosen = (path, res, legs)
                if force is None:
                    b0 = int(path.branch[0])
                    order += [b for b in _branch_order(g) if b != b0]
            if chosen is None:  # Ring gar nicht erreichbar
                d = Dense(q_cur[None], np.zeros(1, bool), start[None], np.array([psi_cur]), np.ones(1))
                s.add(d, "print", task.index, L, [None])
                continue
            path, res, legs = chosen
            q_ls, dl, cl, da, ca, dp, cp, dr, cr, _bad = res
            for d, c in legs:
                s.add(d, "transfer", task.index, k_travel, c)
            s.add(dl, "lower", task.index, k_travel, cl)
            s.add(da, "approach", task.index, L, ca)
            # Verweil-Sample am Ringstart (Pumpe an, wait t_tot) gehoert zum Druck
            last = Dense(da.q[-1:], da.ok[-1:], da.p_W[-1:], da.psi[-1:], np.ones(1))
            s.add(last, "print", task.index, L, ca[-1:])
            s.add(dp, "print", task.index, L, cp)
            s.add(dr, "retract", task.index, L, cr)
            # Abheben
            k_travel = L + 1
            p_r = dr.p_W[-1]
            z_lift = max(self.stand_top_W(k_travel) + p.z_lift_mm, p_r[2])
            q_r = _last_ok(dr, dp, path)
            psi_r = float(dr.psi[-1])
            dlift = movel(
                self.kin, p_r, psi_r, np.array([p_r[0], p_r[1], z_lift]), psi_r, q_r, _branch_q(q_r), p
            )
            s.add(dlift, "lift", task.index, k_travel, self._check(dlift, k_travel))
            q_cur = _last_ok(dlift, dr, path)
            p_cur = dlift.p_W[-1]
            psi_cur = psi_r
            b_prev = _branch_q(q_cur)
            self._submit_checks()

    def _ring_motion(self, task: RingTask, path: RingPath, p_ls, appr, L):
        """lower, approach, print, retract fuer einen Ringpfad; None, wenn Ringstart unerreichbar."""
        p = self.p
        if path.states[0] < 0:
            return None
        b = int(path.branch[0])
        q0, psi0 = path.q[0], float(path.psi[0])
        q_ls = self._ik_branch(p_ls, psi0, b, q0)
        if q_ls is None:
            return None
        t = time.perf_counter()
        dl = movel(self.kin, p_ls, psi0, appr, psi0, q_ls, b, p)
        q_a = _last_ok(dl, None, None, q_ls)
        da = movel(self.kin, appr, psi0, task.p_W[0], psi0, q_a, b, p)
        self.timings["dense"] += time.perf_counter() - t
        dp, seg = self._print_dense(task, _reanchor(path, _last_ok(da, None, None, q_a)))
        q_e = _last_ok(dp, da, None, q_a)
        psi_e = float(path.psi[-1]) if path.states[-1] >= 0 else psi0
        t = time.perf_counter()
        dr = movel(
            self.kin,
            task.p_W[-1],
            psi_e,
            task.p_W[-1] + np.array([0, 0, p.approach_mm]),
            psi_e,
            q_e,
            _branch_q(q_e),
            p,
        )
        self.timings["dense"] += time.perf_counter() - t
        cl = self._check(dl, self._k_lower)
        ca = self._check(da, L)
        cp = self._check(dp, L)
        cr = self._check(dr, L)
        bad_wp = np.zeros(0, int)
        if self.aware:
            bad = self._bad(cp, dp)
            if bad.any():
                bad_wp = np.unique(np.concatenate([seg[bad], seg[bad] - 1]))
            if self._bad(ca, da).any() or self._bad(cl, dl).any():
                bad_wp = np.unique(np.concatenate([bad_wp, [0]]))
            if self._bad(cr, dr).any():
                bad_wp = np.unique(np.concatenate([bad_wp, [len(task.p_W) - 1]]))
        return q_ls, dl, cl, da, ca, dp, cp, dr, cr, bad_wp

    def _finish(self) -> PlannedPath:
        s, p = self.s, self.p
        q = np.vstack(s.q)
        ok = np.concatenate(s.ok)
        t = time.perf_counter()
        done = np.zeros(len(q), bool)
        done[: len(self._final_done)] = self._final_done  # schon im Pool geprueft
        if self.final is not self.real:
            todo = [i for i in range(len(q)) if ok[i] and not done[i]]
        else:
            todo = [i for i, c in enumerate(s.contacts) if c is None and ok[i]]
        if todo:
            cs = contacts_parallel(self.final, q[todo], np.array([s.layer[i] for i in todo]), self.procs)
            for i, c in zip(todo, cs, strict=True):
                s.contacts[i] = c
        self.timings["final_check"] = self.timings.get("final_check", 0.0) + time.perf_counter() - t
        status = [_status(c, o, p) for c, o in zip(s.contacts, ok, strict=True)]
        from roboprint.robot import branch_of

        branch = np.asarray(branch_of(q), int).reshape(-1)
        d = np.array([c.d_mm if c is not None else np.inf for c in s.contacts])
        d_min = float(d[np.isfinite(d)].min()) if np.isfinite(d).any() else None
        switches = 0
        in_ring = {"approach", "print", "retract"}
        for i in range(1, len(q)):
            if s.kind[i] in in_ring and s.kind[i - 1] in in_ring and s.ring[i] == s.ring[i - 1]:
                if branch[i] != branch[i - 1] and ok[i] and ok[i - 1]:
                    switches += 1
        cause = None
        for i, st in enumerate(status):
            c = s.contacts[i]
            if st in ("collision", "unreachable") or (c is not None and c.d_mm < p.d_hard_mm):
                if st == "unreachable":
                    cause = {
                        "sample": i,
                        "link": "-",
                        "obstacle": "-",
                        "message": f"Sample {i} ({s.kind[i]}, Ring {s.ring[i]}): keine Gelenkloesung",
                    }
                else:
                    cause = {
                        "sample": i,
                        "link": c.pair[0],
                        "obstacle": c.pair[1],
                        "message": f"Sample {i} ({s.kind[i]}, Ring {s.ring[i]}, k={s.layer[i]}): "
                        f"d = {c.d_mm:.1f} mm < d_hard = {p.d_hard_mm:.0f} mm "
                        f"({c.pair[0]} / {c.pair[1]})",
                    }
                break
        if cause is None and switches:
            i = next(
                i
                for i in range(1, len(q))
                if s.kind[i] in in_ring and branch[i] != branch[i - 1] and s.ring[i] == s.ring[i - 1]
            )
            cause = {
                "sample": i,
                "link": "-",
                "obstacle": "-",
                "message": f"Zweigwechsel im Ring {s.ring[i]}",
            }
        return PlannedPath(
            q=q,
            reachable=ok,
            p_W=np.vstack(s.p_W),
            psi=np.concatenate(s.psi),
            kind=s.kind,
            ring=s.ring,
            layer=s.layer,
            branch=branch,
            contacts=s.contacts,
            status=status,
            feasible=cause is None,
            cause=cause,
            d_min_mm=d_min,
            branch_switches_in_rings=switches,
            timings_s=dict(self.timings),
        )


def _cat(parts: list[Dense]) -> Dense:
    if not parts:
        return Dense.empty()
    return Dense(*(np.concatenate([getattr(d, f) for d in parts]) for f in ("q", "ok", "p_W", "psi", "u")))


def _last_ok(d: Dense, fallback: Dense | None, path: RingPath | None, q_default=None) -> np.ndarray:
    for x in (d, fallback):
        if x is not None and x.ok.any():
            return x.q[np.nonzero(x.ok)[0][-1]]
    if q_default is not None:
        return q_default
    if path is not None:
        return path.q[np.nonzero(path.states >= 0)[0][-1]]
    raise ValueError("keine gueltige Gelenkstellung")


def _branch_q(q: np.ndarray) -> int:
    from roboprint.robot import branch_of

    return int(branch_of(q))


def _psi_q(kin: Kin, q: np.ndarray) -> float:
    from .kin import psi_of

    return float(psi_of(kin.tcp_W(q[None])[:, :3, :3])[0])


def _reanchor(path: RingPath, q_start: np.ndarray) -> RingPath:
    """Pfad an die tatsaechliche Startstellung (Ende der Anfahrt) anschliessen."""
    q = path.q.copy()
    q[0] = q_start
    return RingPath(path.states, q, path.psi, path.branch, path.cost, path.restarts)


def _branch_order(g) -> list[int]:
    """Zweige nach Anzahl gueltiger Knoten am Ringstart (fuer den Zweigwechsel am Transfer)."""
    v = g.valid[0].reshape(-1, N_BRANCH).sum(0)
    return [int(b) for b in np.argsort(-v) if v[b] > 0]


__all__ = ["PartPlanner", "PlannedPath", "RingTask"]
