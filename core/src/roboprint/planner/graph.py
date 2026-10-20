"""Ladder-Graph je Druckring (SPEC §5.2/2-4): Knoten (Zweig x psi) je Wegpunkt, Viterbi.

Knoten: fuer jeden Wegpunkt i und jedes psi des Rasters die IK aller 8 Zweige (`ik_batch`),
zulaessig nur in den Grenzen. Zustand s = p * 8 + b (p: psi-Index, b: Zweig).
Kanten nur zwischen gleichen Zweigen und mit max|dq| <= dq_max (dq modulo 2pi fuer die
+-360-Grad-Gelenke). Kosten: gewichtete Gelenkdistanz + lambda_psi * |dpsi| an den Kanten,
lambda_d * max(0, d_target - d) / d_target an den Knoten.

Abstaende werden in zwei Stufen bestimmt (Laufzeit): eine schnelle Vorauswahl (`screen`,
Kugel-Double ohne Selbstkollision) bewertet alle Knoten fuer den Kostenterm; die echte Welt
prueft nur die Knoten des gewaehlten Pfads (lazy). Ein Knoten mit echtem d < d_hard faellt aus
(Kosten HARD), danach wird neu gesucht, bis der Pfad nur aus geprueften Knoten besteht.

Falls kein zulaessiger Pfad existiert, erlaubt die Suche einen "Neustart" (beliebiger Zustand,
Kosten BIG). Das ist ein Zweigwechsel bzw. Sprung im Ring und macht das Teil nicht machbar;
so bleibt das Ergebnis aber vollstaendig und die Ursache sichtbar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .backend import d_batch
from .kin import JOINT_WEIGHTS, Kin, joint_diff, unwrap_sequence, wrap_pi
from .params import PlannerParams

BIG = 1.0e4  # Neustart im Ring (Sprung)
HARD = 1.0e6  # Knoten mit d < d_hard (echte Welt)
N_BRANCH = 8


@dataclass
class RingGraph:
    p_W: np.ndarray  # (n,3) Wegpunkte in W  # noqa: N815
    psi: np.ndarray  # (P,)
    layer_k: int  # Druckstand k fuer die Knotenpruefung
    Q: np.ndarray  # (n,S,6) kanonisch, S = P*8
    valid: np.ndarray  # (n,S)
    d_screen: np.ndarray  # (n,S), inf wenn nicht bewertet
    d_real: np.ndarray  # (n,S), nan = ungeprueft
    edge: np.ndarray = field(repr=False, default=None)  # (n-1, 8, P, P) Kantenkosten

    @property
    def n(self) -> int:
        return len(self.p_W)

    @property
    def n_psi(self) -> int:
        return len(self.psi)


@dataclass
class RingPath:
    states: np.ndarray  # (n,) Zustand je Wegpunkt, -1 = unerreichbar
    q: np.ndarray  # (n,6) stetig (2pi-Varianten aufgeloest); nan bei -1
    psi: np.ndarray  # (n,)
    branch: np.ndarray  # (n,)
    cost: float
    restarts: int


def build_graph(
    kin: Kin,
    p_W: np.ndarray,
    layer_k: int,
    params: PlannerParams,
    screen: Any | None,  # noqa: N803
) -> RingGraph:
    psi = params.psi_grid
    n, P = len(p_W), len(psi)
    pw = np.repeat(p_W, P, axis=0)
    ps = np.tile(psi, n)
    Qa, ok = kin.ik(pw, ps)  # (n*P,8,6)
    Q = Qa.reshape(n, P * N_BRANCH, 6)
    valid = ok.reshape(n, P * N_BRANCH)
    d_screen = np.full((n, P * N_BRANCH), np.inf)
    if screen is not None and valid.any():
        d_screen = _screen(screen, Q, valid, layer_k, n, P)
    g = RingGraph(p_W, psi, layer_k, Q, valid, d_screen, np.full((n, P * N_BRANCH), np.nan))
    g.edge = _edge_costs(g, params)
    return g


def _screen(
    screen: Any, Q: np.ndarray, valid: np.ndarray, k: int, n: int, P: int, w_step: int = 4
) -> np.ndarray:  # noqa: N803
    """Vorauswahl-Abstaende nur fuer jeden `w_step`-ten Wegpunkt und jedes dritte psi (Laufzeit);
    dazwischen gilt das Minimum der Nachbarn (konservativ fuer den Kostenterm)."""
    wi = np.unique(np.r_[np.arange(0, n, w_step), n - 1])
    pi = np.arange(0, P, 3)
    D = np.full((n, P, N_BRANCH), np.nan)  # noqa: N806
    Qv = Q.reshape(n, P, N_BRANCH, 6)[np.ix_(wi, pi)]  # noqa: N806
    V = valid.reshape(n, P, N_BRANCH)[np.ix_(wi, pi)]  # noqa: N806
    sub = np.full(V.shape, np.nan)
    if V.any():
        sub[V] = d_batch(screen, Qv[V], np.full(int(V.sum()), k), self_collision=False)
    D[np.ix_(wi, pi)] = sub
    # psi-Luecken: Minimum der beiden ausgewerteten Nachbarn
    for p in range(P):
        if p % 3:
            a, b = p - p % 3, (p - p % 3 + 3) % P
            D[wi, p] = np.fmin(D[wi, a], D[wi, b])
    # Wegpunkt-Luecken: Minimum der umgebenden ausgewerteten Wegpunkte
    for a, b in zip(wi[:-1], wi[1:], strict=True):
        if b > a + 1:
            D[a + 1 : b] = np.fmin(D[a], D[b])[None]
    D = np.where(np.isnan(D), np.inf, D)  # noqa: N806
    return D.reshape(n, P * N_BRANCH)


def _by_branch(X: np.ndarray, P: int) -> np.ndarray:
    """(..., S, ...) mit S = P*8 -> (..., 8, P, ...)."""
    sh = X.shape
    return np.moveaxis(X.reshape(*sh[:1], P, N_BRANCH, *sh[2:]), 2, 1)


def _edge_costs(g: RingGraph, params: PlannerParams) -> np.ndarray:
    P = g.n_psi
    Qb = _by_branch(g.Q, P)  # (n,8,P,6)
    Vb = _by_branch(g.valid, P)  # (n,8,P)
    dpsi = np.abs(wrap_pi(g.psi[None, :] - g.psi[:, None]))  # (P,P) [von, nach]
    out = np.full((max(g.n - 1, 0), N_BRANCH, P, P), np.inf)
    for i in range(g.n - 1):
        dq = joint_diff(Qb[i + 1][:, None, :, :], Qb[i][:, :, None, :])  # (8,P_von,P_nach,6)
        adq = np.abs(dq)
        c = (adq * JOINT_WEIGHTS).sum(-1) + params.lambda_psi * dpsi[None]
        ok = (adq.max(-1) <= params.dq_max_rad) & Vb[i][:, :, None] & Vb[i + 1][:, None, :]
        out[i] = np.where(ok, c, np.inf)
    return out


def node_costs(g: RingGraph, params: PlannerParams, collision_aware: bool) -> np.ndarray:
    c = np.where(g.valid, 0.0, np.inf)
    if not collision_aware:
        return c
    # Kostenterm nur aus der Vorauswahl (Umgebungspaare ohne Selbstkollision): konstante Paare wie
    # base_link <-> link_2 (~33 mm) duerfen ihn nicht dominieren. d_real entscheidet nur hart.
    d = g.d_screen
    pen = params.lambda_d * np.clip(params.d_target_mm - d, 0.0, None) / params.d_target_mm
    pen = np.where(np.isfinite(pen), pen, 0.0)
    pen = pen + np.where(g.d_screen < params.d_hard_mm, BIG / 10, 0.0) * np.isnan(g.d_real)
    pen = pen + np.where(g.d_real < params.d_hard_mm, HARD, 0.0)
    return c + pen


def viterbi(g: RingGraph, node_cost: np.ndarray, start_cost: np.ndarray) -> tuple[np.ndarray, float, int]:
    """Kuerzester Pfad; liefert Zustaende (-1 = Wegpunkt ohne Knoten), Kosten, Anzahl Neustarts."""
    n, S = node_cost.shape
    P = g.n_psi
    cost = np.empty((n, S))
    back = np.full((n, S), -1, dtype=np.int64)
    cost[0] = start_cost + node_cost[0]
    for i in range(n - 1):
        prev = cost[i]
        if not np.isfinite(prev).any():
            cost[i + 1] = node_cost[i + 1] + BIG
            continue
        pb = _by_branch(prev[None], P)[0]  # (8,P)
        tot = pb[:, :, None] + g.edge[i]  # (8,P_von,P_nach)
        arg = np.argmin(tot, axis=1)  # (8,P_nach)
        best = np.take_along_axis(tot, arg[:, None, :], axis=1)[:, 0, :]
        # zurueck auf Zustandsindex: s = p*8 + b
        b_idx = np.arange(N_BRANCH)[:, None]
        from_state = arg * N_BRANCH + b_idx  # (8,P_nach)
        best_s = np.moveaxis(best, 0, 1).reshape(S)
        from_s = np.moveaxis(from_state, 0, 1).reshape(S)
        g_arg = int(np.argmin(prev))
        restart = prev[g_arg] + BIG
        use_restart = ~(best_s <= restart)
        cost[i + 1] = np.where(use_restart, restart, best_s) + node_cost[i + 1]
        back[i + 1] = np.where(use_restart, g_arg, from_s)
    states = np.full(n, -1, dtype=np.int64)
    s: int | None = None
    total = float(np.min(cost[-1])) if np.isfinite(cost[-1]).any() else np.inf
    restarts = 0
    for i in range(n - 1, -1, -1):
        if s is None:
            if not np.isfinite(cost[i]).any():
                continue
            s = int(np.argmin(cost[i]))
        states[i] = s
        if i > 0:
            bp = int(back[i, s])
            if bp < 0:
                s = None
            else:
                if not _is_edge(g, i - 1, bp, s):
                    restarts += 1
                s = bp
    return states, total, restarts


def _is_edge(g: RingGraph, i: int, s_from: int, s_to: int) -> bool:
    b1, p1 = s_from % N_BRANCH, s_from // N_BRANCH
    b2, p2 = s_to % N_BRANCH, s_to // N_BRANCH
    return b1 == b2 and bool(np.isfinite(g.edge[i, b1, p1, p2]))


def start_costs(
    g: RingGraph,
    params: PlannerParams,
    q_prev: np.ndarray | None,
    b_prev: int | None,
    w_start: float | None = None,
) -> np.ndarray:
    """Kosten des Ringstarts: Zweig ungleich `b_prev` (lambda_branch) und gewichtete Gelenkdistanz
    zu `q_prev` mal `w_start` (Standard lambda_transfer; Verbinder: lambda_link, wie eine Kante)."""
    S = g.Q.shape[1]
    c = np.zeros(S)
    br = np.arange(S) % N_BRANCH
    if b_prev is not None:
        c += params.lambda_branch * (br != b_prev)
    if q_prev is not None:
        w = params.lambda_transfer if w_start is None else w_start
        dq = np.abs(joint_diff(g.Q[0], q_prev))
        c += w * np.nan_to_num((dq * JOINT_WEIGHTS).sum(-1), nan=0.0)
    return c


def solve_ring(
    g: RingGraph,
    params: PlannerParams,
    real: Any | None,
    q_prev: np.ndarray | None,
    b_prev: int | None,
    force_branch: int | None = None,
    max_iter: int = 12,
    w_start: float | None = None,
) -> RingPath:
    """Viterbi mit lazy Pruefung der Pfadknoten gegen die echte Welt (`real`; None = ohne)."""
    collision_aware = real is not None
    sc = start_costs(g, params, q_prev, b_prev, w_start)
    if force_branch is not None:
        sc = sc + np.where(np.arange(len(sc)) % N_BRANCH == force_branch, 0.0, HARD)
    for _ in range(max_iter):
        nc = node_costs(g, params, collision_aware)
        states, total, restarts = viterbi(g, nc, sc)
        if not collision_aware:
            break
        idx = np.nonzero(states >= 0)[0]
        todo = idx[np.isnan(g.d_real[idx, states[idx]])]
        if todo.size == 0:
            break
        Qn = g.Q[todo, states[todo]]
        g.d_real[todo, states[todo]] = d_batch(real, Qn, np.full(len(todo), g.layer_k), self_collision=True)
    return _path(g, states, total, restarts, q_prev)


def _path(
    g: RingGraph, states: np.ndarray, total: float, restarts: int, q_prev: np.ndarray | None
) -> RingPath:
    n = g.n
    q = np.full((n, 6), np.nan)
    psi = np.full(n, np.nan)
    branch = np.full(n, -1, dtype=int)
    ok = states >= 0
    if ok.any():
        idx = np.nonzero(ok)[0]
        Qs = g.Q[idx, states[idx]]
        ref = Qs[0] if q_prev is None else q_prev
        q[idx] = unwrap_sequence(Qs, ref)
        psi[idx] = g.psi[states[idx] // N_BRANCH]
        branch[idx] = states[idx] % N_BRANCH
    return RingPath(states, q, psi, branch, total, restarts)


def mark_hard(g: RingGraph, path: RingPath, waypoints: np.ndarray) -> None:
    """Pfadknoten an den Wegpunkten `waypoints` als unzulaessig markieren (z. B. nach der
    Dichtepruefung), damit eine neue Suche sie meidet."""
    for i in np.unique(waypoints):
        s = path.states[i]
        if s >= 0:
            g.d_real[i, s] = -1.0
