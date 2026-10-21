"""Ein Teil planen: Ringe (Ladder-Graph), Straenge mit Verbindern, Travel (SPEC §5.3), Verdichtung,
Pruefung, Ergebnis.

Ablauf je Strang (spec/ARTEFAKTE.md): transfer -> lower -> approach -> print r -> [link r+1 ->
print r+1]* -> retract -> lift. Der erste Strang beginnt mit `transfer` aus der Home-Pose (Sample 0
ist Home), nach dem letzten Ring folgt ein `lift`.

Strang (Nutzerentscheidung 20.10.2026): Hat Ring r `link_next`, plant der Planer Ring r + 1 im Zweig
am Ende von r (`force_branch`, Start nahe der Gelenkstellung am Ende von r, Gewicht lambda_link) und
verbindet beide mit einem Verbinder (`link`: movel vom Ende von r zum Start von r + 1, psi linear).
Verbinder und Ring r + 1 werden wie Druck geprueft (k = Schicht von r + 1). Geht das nicht
(unerreichbar, d < d_hard bei collision_aware, Zweigwechsel noetig, Ring-Nachplanung mit `mark_hard`
erfolglos), endet der Strang an r: Abfahren und Abheben von r, dann Travel zu r + 1. Abfahren und
Abheben eines Rings werden deshalb erst angehaengt, wenn feststeht, dass kein Verbinder folgt. Das
Verweil-Sample (Pumpe an, wait t_tot) steht nur am Strangbeginn.

`layer[i]` ist die Anzahl k fertiger Schichten: print/approach/retract von Schicht L: k = L; link vor
einem Ring in Schicht L: k = L; lift nach Schicht L: k = L + 1; transfer/lower vor einem Strang:
k = (Schicht des vorigen Rings) + 1, vor dem ersten Ring 0.

Druckmuster (opt-in, docs/muster/ARTEFAKT-FORMAT.md): Ringe duerfen offen sein (`closed = false`,
Ende != Anfang); der Planer behandelt jeden Ring als Wegpunktfolge vom ersten zum letzten Punkt,
offen oder geschlossen gleich. Verbinder ohne waagrechte Laenge (`is_zero_link`, <= 0,5 mm) sind in
der Schicht ein `link`-Sample am selben Ort, beim Schichtwechsel ein reiner Z-Hub um h (senkrechter
Schichtwechsel, M4); der Folgering behaelt dort psi (`psi_hold`), damit sich die Duese mit
laufender Pumpe nicht auf der Stelle dreht. So wird ein Muster ueber alle Ringe und Schichten ein
Strang. Kurven bringen dichtere Wegpunkte (Sehnenfehler <= 0,5 mm); Knoten gibt es weiter je
Wegpunkt (Laufzeit S1 mit Muster: docs/muster/ARTEFAKT-FORMAT.md, Nachtrag M3.2).

Hoehensuche (`stop_at_bad`): Ein Praefix des Plans bis zu einer Schichtgrenze ist der Plan des
niedrigeren Teils. Fuehrt dort ein Verbinder in die naechste Schicht, plant der Planer das Strangende
(Abfahren, Abheben) zusaetzlich als `Tail`; `truncate` haengt es an. Die Hoehensuche stoppt an der
ersten Schicht, deren Ringe, Verbinder oder Strangende nicht gehen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from roboprint.robot import HOME_Q
from roboprint.selfcheck import TOL_LIFT_MM

from .backend import can_fork_pool, contacts_batch, contacts_parallel
from .densify import Dense, movej, movel, print_dense
from .graph import N_BRANCH, RingGraph, RingPath, build_graph, mark_hard, solve_ring
from .kin import Kin, nearest_variant
from .params import PlannerParams
from .result import PlannedPath, Tail, summarize, truncate
from .samples import (
    Cursor,
    OpenStrand,
    Piece,
    RingTask,
    Samples,
    branch_order,
    branch_q,
    last_ok,
    pieces_bad,
    reanchor,
    samples_bad,
    tail_of,
)

_RING_RETRIES = 2
#: Verbinder mit waagrechter Laenge bis hier sind "Laenge 0" (in der Schicht) bzw. ein reiner Z-Hub
#: (Schichtwechsel, Muster-Regel M4: <= 0,5 mm); der Folgering behaelt dann psi (`psi_hold`).
ZERO_LINK_MM = 0.5
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
class _Motion:
    """Geplante Bewegung eines Rings: Zugang (lower/approach bzw. Verbinder), Druck, Abfahren."""

    pre: list[Piece]  # vor dem Druck (lower, approach bzw. link)
    dp: Dense
    cp: list[Any]
    dr: Dense
    cr: list[Any]
    q_e: np.ndarray  # Gelenkstellung am Ringende
    psi_e: float
    bad_wp: np.ndarray  # Wegpunkte, deren Knoten neu gewaehlt werden sollen
    core_bad: bool = False  # Verbinder oder Druck geht nicht (nur Verbinder-Versuch)
    q_ls: np.ndarray | None = None  # Gelenkstellung ueber dem Ringstart (Travel)


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
        stop_at_bad: bool = False,
    ) -> None:
        self.kin, self.rings, self.p = kin, rings, params
        self.T_WP = np.asarray(T_WP, float)
        self.real, self.screen = real, screen
        # `final`: Backend der Abschlusspruefung aller Samples (echte Welt); `real` prueft waehrend
        # der Planung (Travel-Entscheidungen, Ring-Nachplanung) und darf ein schnelles Double sein.
        self.final = final if final is not None else real
        # Hoehensuche: Jeder Ring wird sofort mit der echten Welt geprueft (`checker`), die Planung
        # stoppt an der ersten Schicht, die nicht geht; `layers_ok` zaehlt die Schichten darunter.
        self.stop_at_bad = stop_at_bad
        self.checker = self.final if stop_at_bad else self.real
        self.layers_ok: int | None = None
        self.procs = procs
        self.aware = collision_aware
        self.z0 = float(self.T_WP[2, 3])
        n_layers = 1 + max((r.layer for r in rings), default=0)
        self.height = part_height_mm if part_height_mm is not None else n_layers * params.layer_height_mm
        # xy-Box des Teils in W: Darueber haelt der Transfer die Mindesthoehe der Selbstpruefung (b).
        pts = np.vstack([r.p_W[:, :2] for r in rings]) if rings else np.zeros((1, 2))
        self._xy_lo = pts.min(axis=0) - 0.5 * params.bead_width_mm
        self._xy_hi = pts.max(axis=0) + 0.5 * params.bead_width_mm
        self.s = Samples()
        self.timings = {"graph": 0.0, "dense": 0.0, "check": 0.0}
        self._graphs: dict[int, RingGraph] = {}
        self._graph_iter: Any = None
        # Abschlusspruefung im Pool, waehrend der Hauptprozess weiterplant (nur mit Double-Planung)
        self._pool: Any = None
        self._pending: list[tuple[int, int, Any]] = []  # (erstes Sample, Anzahl, AsyncResult)
        self._sent = 0  # Samples bis hierher an den Pool gegeben
        self._final_done = np.zeros(0, bool)
        # Strang: offener Ring (Ende steht aus), Stand nach dem letzten Strangende, Strangenden je
        # Schichtgrenze mit Verbinder (fuer `truncate`)
        self._open: OpenStrand | None = None
        self._cur: Cursor | None = None
        self.tails: dict[int, Tail] = {}
        self._k_lower = 0

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
        if not force and self.final is not self.checker:
            return out
        idx = np.nonzero(d.ok)[0]
        if idx.size:
            cs = contacts_batch(self.checker, d.q[idx], np.full(len(idx), layer))
            for i, c in zip(idx, cs, strict=True):
                out[i] = c
        self.timings["check"] += time.perf_counter() - t
        return out

    def _bad(self, contacts: list[Any], d: Dense) -> np.ndarray:
        dd = np.array([c.d_mm if c is not None else np.inf for c in contacts])
        return (dd < self.p.d_hard_mm) | ~d.ok

    def _sags(self, d: Dense, k: int) -> bool:
        """Sackt ein Transfer (movej) ueber dem Teil unter z_lift - TOL_LIFT_MM ueber den Druckstand?
        Dann ist er nicht frei: Die Selbstpruefung (b) wuerde das Teil sonst verwerfen."""
        if k <= 0:
            return False
        over = np.all((d.p_W[:, :2] >= self._xy_lo) & (d.p_W[:, :2] <= self._xy_hi), axis=1)
        floor = self.stand_top_W(k) + self.p.z_lift_mm - TOL_LIFT_MM
        return bool(np.any(over & (d.p_W[:, 2] < floor)))

    def _block_bad(self, n0: int, i0: int, free: bool) -> bool:
        """Hoehensuche: Geht das Stueck ab Sample `n0` nicht? Unerreichbar, unter d_hard (mit der
        echten Welt geprueft), Zweigwechsel im Strang oder unfreier Transfer."""
        if self.aware and not free:
            return True
        s = self.s
        return samples_bad(
            np.vstack(s.q[i0:]), np.concatenate(s.ok[i0:]), s.contacts[n0:], s.kind[n0:], self.p.d_hard_mm
        )

    def _ik_branch(self, p_W: np.ndarray, psi: float, branch: int, q_ref: np.ndarray):  # noqa: N803
        Q, ok = self.kin.ik(p_W[None], np.array([psi]))
        if ok[0, branch]:
            return nearest_variant(Q[0, branch], q_ref)
        return None

    def _movel(self, p_a, psi_a, p_b, psi_b, q_a, branch) -> Dense:
        t = time.perf_counter()
        d = movel(self.kin, p_a, psi_a, p_b, psi_b, q_a, branch, self.p)
        self.timings["dense"] += time.perf_counter() - t
        return d

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

    def _solve(
        self,
        g: RingGraph,
        q_prev,
        b_prev,
        force_branch=None,
        link: bool = False,
        psi_hold: float | None = None,
    ) -> RingPath:
        t = time.perf_counter()
        w = self.p.lambda_link if link else None
        real = self.real if self.aware else None
        path = solve_ring(g, self.p, real, q_prev, b_prev, force_branch, w_start=w, psi_hold=psi_hold)
        self.timings["graph"] += time.perf_counter() - t
        return path

    def _print_dense(self, task: RingTask, path: RingPath) -> tuple[Dense, np.ndarray]:
        t = time.perf_counter()
        out = print_dense(self.kin, task.p_W, path, self.p)
        self.timings["dense"] += time.perf_counter() - t
        return out

    def _retract(self, task: RingTask, q_e: np.ndarray, psi_e: float) -> Dense:
        end = task.p_W[-1]
        return self._movel(end, psi_e, end + np.array([0, 0, self.p.approach_mm]), psi_e, q_e, branch_q(q_e))

    # -------------------------------------------------------------- Travel
    def _transfer(self, q_a: np.ndarray, q_b: np.ndarray, p_a: np.ndarray, p_b: np.ndarray, k: int):
        """movej q_a -> q_b, bei Bedarf ueber einen Zwischenpunkt hoeher und mittig (SPEC §5.3).

        Liefert (Liste von (Dense, Kontakte)), frei?
        """
        t = time.perf_counter()
        d = movej(self.kin, q_a, q_b, self.p)
        self.timings["dense"] += time.perf_counter() - t
        c = self._check(d, k, force=True)
        if not self.aware or not (self._bad(c, d).any() or self._sags(d, k)):
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
                if self._bad(c1, d1).any() or self._sags(d1, k):
                    continue
                d2 = movej(self.kin, qv, q_b, self.p)
                c2 = self._check(d2, k, force=True)
                if not (self._bad(c2, d2).any() or self._sags(d2, k)):
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
                if self.final is not self.checker:
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
        done[: len(self._final_done)] = self._final_done
        for start, ix, res in self._pending:
            for i, c in zip(ix, res.get(), strict=True):
                self.s.contacts[start + int(i)] = c
            done[start + ix] = True
        self._pending = []
        self._final_done = done
        self.timings["final_check"] = time.perf_counter() - t

    def _run(self) -> None:
        s = self.s
        q0 = HOME_Q.copy()
        p0 = self.kin.tcp_W(q0[None])[0, :3, 3]
        home = Dense(q0[None], np.ones(1, bool), p0[None], np.zeros(1), np.zeros(1))
        s.add(home, "transfer", 0, 0, self._check(home, 0))
        s.psi[0] = np.array([_psi_q(self.kin, q0)])
        self._cur = Cursor(q0, p0, float(s.psi[0][0]), None, 0)
        self._open = None
        for task in self.rings:
            op = self._open
            if op is not None and op.task.link_next and task.index == op.task.index + 1:
                n0, i0 = s.n, len(s.q)
                if self._link(op, task):
                    if self.stop_at_bad and self._block_bad(n0, i0, True):
                        self.layers_ok = task.layer
                        break
                    self._submit_checks()
                    continue
            if op is not None and not self._close():
                break
            if not self._strand_start(task):
                break
            self._submit_checks()
        if self._open is not None:  # letzter Strang (nach einem Abbruch der Hoehensuche ohne Bewertung)
            self._close(evaluate=self.layers_ok is None)
        if self.stop_at_bad and self.layers_ok is None:
            self.layers_ok = 1 + max((r.layer for r in self.rings), default=-1)

    # -------------------------------------------------------------- Strang
    def _strand_end(self, op: OpenStrand) -> list[Piece]:
        """Abfahren (schon geplant) und Abheben des offenen Rings; Abheben um z_lift ueber den
        Druckstand nach der Schicht des Rings (k = L + 1)."""
        L = op.task.layer
        k = L + 1
        p_r = op.dr.p_W[-1]
        z_lift = max(self.stand_top_W(k) + self.p.z_lift_mm, p_r[2])
        q_r = last_ok(op.dr, None, None, op.q_end)
        psi_r = float(op.dr.psi[-1])
        dlift = self._movel(p_r, psi_r, np.array([p_r[0], p_r[1], z_lift]), psi_r, q_r, branch_q(q_r))
        return [
            (op.dr, "retract", op.task.index, L, op.cr),
            (dlift, "lift", op.task.index, k, self._check(dlift, k)),
        ]

    def _close(self, evaluate: bool = True) -> bool:
        """Strangende: Abfahren und Abheben des offenen Rings anhaengen. False: Hoehensuche stoppt."""
        op, s = self._open, self.s
        assert op is not None
        self._open = None
        n0, i0 = s.n, len(s.q)
        pieces = self._strand_end(op)
        for d, kind, ring, k, c in pieces:
            s.add(d, kind, ring, k, c)
        dlift = pieces[-1][0]
        q = last_ok(dlift, op.dr, None, op.q_end)
        self._cur = Cursor(q, dlift.p_W[-1], float(op.dr.psi[-1]), branch_q(q), op.task.layer + 1)
        if evaluate and self.stop_at_bad and self._block_bad(n0, i0, True):
            self.layers_ok = op.task.layer
            return False
        return True

    def _link(self, op: OpenStrand, task: RingTask) -> bool:
        """Ring `task` ueber einen Verbinder an den offenen Strang haengen (SPEC §5.3). False: geht
        nicht, der Strang endet an `op`."""
        b = op.branch
        g = self._graph(task)
        hold = op.psi_end if is_zero_link(op.task.p_W[-1], task.p_W[0]) else None
        path = self._solve(g, op.q_end, b, b, link=True, psi_hold=hold)
        best: _Motion | None = None
        for attempt in range(_RING_RETRIES + 1):
            mo = self._link_motion(task, path, op, b)
            if mo is None:
                break
            if not mo.core_bad:
                best = mo
                if mo.bad_wp.size == 0:
                    break
            if not self.aware or mo.bad_wp.size == 0 or attempt == _RING_RETRIES:
                break
            mark_hard(g, path, mo.bad_wp)
            path = self._solve(g, op.q_end, b, b, link=True, psi_hold=hold)
        if best is None:
            return False
        s = self.s
        if task.layer != op.task.layer:
            # Schichtgrenze: Strangende fuer einen Plan, der hier endet (Hoehensuche, `truncate`)
            tail = self._strand_end(op)
            if self.stop_at_bad and pieces_bad(tail, self.p.d_hard_mm):
                return False
            self.tails[s.n] = tail_of(tail)
        for d, kind, ring, k, c in best.pre:
            s.add(d, kind, ring, k, c)
        s.add(best.dp, "print", task.index, task.layer, best.cp)
        self._open = OpenStrand(task, best.q_e, best.psi_e, best.dr, best.cr)
        return True

    def _link_motion(self, task: RingTask, path: RingPath, op: OpenStrand, b: int) -> _Motion | None:
        """Verbinder (movel Ende von r -> Start von r + 1) und Druck von r + 1 im Zweig `b`; None, wenn
        das im Zweig nicht geht (unerreichbar, Sprung, Zweigwechsel)."""
        if (path.states < 0).any() or (path.branch != b).any() or path.restarts:
            return None
        L = task.layer
        dk = self._movel(op.task.p_W[-1], op.psi_end, task.p_W[0], float(path.psi[0]), op.q_end, b)
        if not dk.ok.all():
            return None
        dp, seg = self._print_dense(task, reanchor(path, dk.q[-1]))
        if len(dp.q) == 0 or not dp.ok.all():
            return None
        from roboprint.robot import branch_of

        if (np.asarray(branch_of(np.vstack([dk.q, dp.q])), int).reshape(-1) != b).any():
            return None
        q_e, psi_e = dp.q[-1], float(path.psi[-1])
        dr = self._retract(task, q_e, psi_e)
        ck, cp, cr = self._check(dk, L), self._check(dp, L), self._check(dr, L)
        bad_wp, core_bad = np.zeros(0, int), False
        if self.aware:
            bk, bp = self._bad(ck, dk), self._bad(cp, dp)
            core_bad = bool(bk.any() or bp.any())
            if bk.any():
                bad_wp = np.array([0])
            if bp.any():
                bad_wp = np.unique(np.concatenate([bad_wp, seg[bp], seg[bp] - 1]))
            if self._bad(cr, dr).any():
                bad_wp = np.unique(np.concatenate([bad_wp, [len(task.p_W) - 1]]))
        pre: list[Piece] = [(dk, "link", task.index, L, ck)]
        return _Motion(pre, dp, cp, dr, cr, q_e, psi_e, bad_wp, core_bad)

    def _strand_start(self, task: RingTask) -> bool:
        """Travel zum Ring `task` (Zweigwechsel nur hier, falls der Transfer unfrei bleibt), Anfahrt,
        Verweil-Sample und Druck: Beginn eines neuen Strangs. False: Hoehensuche stoppt."""
        p, s, cur = self.p, self.s, self._cur
        assert cur is not None
        L = task.layer
        n0, i0 = s.n, len(s.q)
        start = task.p_W[0]
        self._k_lower = cur.k
        appr = start + np.array([0.0, 0.0, p.approach_mm])
        z_travel = max(self.stand_top_W(cur.k) + p.z_lift_mm, appr[2])
        p_ls = np.array([appr[0], appr[1], z_travel])
        order: list[int | None] = [None]
        chosen = None
        for force in order:
            g = self._graph(task)
            path = self._solve(g, cur.q, cur.branch, force)
            for _ in range(_RING_RETRIES + 1):
                mo = self._ring_motion(task, path, p_ls, appr, L)
                if mo is None or not self.aware or mo.bad_wp.size == 0:
                    break
                mark_hard(g, path, mo.bad_wp)
                path = self._solve(g, cur.q, cur.branch, force)
            if mo is None:
                continue
            assert mo.q_ls is not None
            legs, free = self._transfer(cur.q, mo.q_ls, cur.p, p_ls, cur.k)
            if free or not self.aware:
                chosen = (mo, legs, free)
                break
            if chosen is None:
                chosen = (mo, legs, free)
            if force is None:
                b0 = int(path.branch[0])
                order += [b for b in branch_order(g) if b != b0]
        if chosen is None:  # Ring gar nicht erreichbar
            d = Dense(cur.q[None], np.zeros(1, bool), start[None], np.array([cur.psi]), np.ones(1))
            s.add(d, "print", task.index, L, [None])
            if self.stop_at_bad:
                self.layers_ok = L
                return False
            return True
        mo, legs, free = chosen
        for d, c in legs:
            s.add(d, "transfer", task.index, cur.k, c)
        for d, kind, ring, k, c in mo.pre:
            s.add(d, kind, ring, k, c)
        # Verweil-Sample am Strangbeginn (Pumpe an, wait t_tot) gehoert zum Druck
        da, ca = mo.pre[-1][0], mo.pre[-1][4]
        dwell = Dense(da.q[-1:], da.ok[-1:], da.p_W[-1:], da.psi[-1:], np.ones(1))
        s.add(dwell, "print", task.index, L, ca[-1:])
        s.add(mo.dp, "print", task.index, L, mo.cp)
        self._open = OpenStrand(task, mo.q_e, mo.psi_e, mo.dr, mo.cr)
        if self.stop_at_bad and self._block_bad(n0, i0, free):
            self.layers_ok = L
            return False
        return True

    def _ring_motion(self, task: RingTask, path: RingPath, p_ls, appr, L) -> _Motion | None:
        """lower, approach, print, retract fuer einen Ringpfad; None, wenn Ringstart unerreichbar."""
        if path.states[0] < 0:
            return None
        b = int(path.branch[0])
        q0, psi0 = path.q[0], float(path.psi[0])
        q_ls = self._ik_branch(p_ls, psi0, b, q0)
        if q_ls is None:
            return None
        dl = self._movel(p_ls, psi0, appr, psi0, q_ls, b)
        q_a = last_ok(dl, None, None, q_ls)
        da = self._movel(appr, psi0, task.p_W[0], psi0, q_a, b)
        dp, seg = self._print_dense(task, reanchor(path, last_ok(da, None, None, q_a)))
        q_e = last_ok(dp, da, None, q_a)
        psi_e = float(path.psi[-1]) if path.states[-1] >= 0 else psi0
        dr = self._retract(task, q_e, psi_e)
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
        pre: list[Piece] = [(dl, "lower", task.index, self._k_lower, cl), (da, "approach", task.index, L, ca)]
        return _Motion(pre, dp, cp, dr, cr, q_e, psi_e, bad_wp, q_ls=q_ls)

    def _finish(self) -> PlannedPath:
        s, p = self.s, self.p
        q = np.vstack(s.q)
        ok = np.concatenate(s.ok)
        t = time.perf_counter()
        done = np.zeros(len(q), bool)
        done[: len(self._final_done)] = self._final_done  # schon im Pool geprueft
        if self.final is not self.checker:
            todo = [i for i in range(len(q)) if ok[i] and not done[i]]
        else:
            todo = [i for i, c in enumerate(s.contacts) if c is None and ok[i]]
        if todo:
            cs = contacts_parallel(self.final, q[todo], np.array([s.layer[i] for i in todo]), self.procs)
            for i, c in zip(todo, cs, strict=True):
                s.contacts[i] = c
        # Strangenden an Schichtgrenzen (nur fuer `truncate`): ungepruefte Samples mit der echten Welt
        tt = [
            (tl, i)
            for tl in self.tails.values()
            for i in range(len(tl.q))
            if tl.ok[i] and tl.contacts[i] is None
        ]
        if tt:
            qs = np.array([tl.q[i] for tl, i in tt])
            cs = contacts_parallel(self.final, qs, np.array([tl.layer[i] for tl, i in tt]), self.procs)
            for (tl, i), c in zip(tt, cs, strict=True):
                tl.contacts[i] = c
        self.timings["final_check"] = self.timings.get("final_check", 0.0) + time.perf_counter() - t
        path = summarize(
            q, ok, np.vstack(s.p_W), np.concatenate(s.psi), s.kind, s.ring, s.layer, s.contacts, p,
            dict(self.timings),
        )  # fmt: skip
        path.layers_ok = self.layers_ok
        path.tails = self.tails
        return path


def is_zero_link(p_end: np.ndarray, p_start: np.ndarray) -> bool:
    """Verbinder ohne waagrechte Laenge (<= ZERO_LINK_MM): Laenge 0 in der Schicht oder reiner Z-Hub."""
    return bool(np.hypot(*(np.asarray(p_start, float)[:2] - np.asarray(p_end, float)[:2])) <= ZERO_LINK_MM)


def _psi_q(kin: Kin, q: np.ndarray) -> float:
    from .kin import psi_of

    return float(psi_of(kin.tcp_W(q[None])[:, :3, :3])[0])


__all__ = ["ZERO_LINK_MM", "PartPlanner", "PlannedPath", "RingTask", "is_zero_link", "summarize", "truncate"]
