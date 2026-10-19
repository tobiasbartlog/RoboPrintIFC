"""Verdichtung (SPEC §5.2/5): Abtastung so, wie die Steuerung faehrt.

- `movel`: TCP kartesisch linear, Orientierung per Slerp (bei senkrechter Duese: psi linear auf
  dem kuerzeren Bogen). IK entlang der Bahn im festen Zweig, je Sample die 2pi-Variante nahe
  am Vorgaenger. Gibt es im Zweig keine Loesung, ist das Sample `unreachable` (q bleibt die
  letzte gueltige Loesung, nur zur Anzeige; nie eingefroren weitergeprueft).
  `movel_chain` verdichtet eine ganze Folge von movel-Stuecken (ein Druckring) vektorisiert.
- `movej`: gelenklinear.
- Abtastung, bis zwischen zwei Samples der TCP <= dense_tcp_mm wandert und max|dq| <= dense_dq_rad.

Jede Funktion liefert die Samples **ohne** den Startpunkt (der ist das Ende des Vorgaengers)
und **mit** dem Endpunkt.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .kin import Kin, joint_diff, nearest_variant, psi_of, wrap_pi
from .params import PlannerParams

_MAX_REFINE = 8


@dataclass
class Dense:
    q: np.ndarray  # (m,6)
    ok: np.ndarray  # (m,) False = unreachable
    p_W: np.ndarray  # (m,3) Soll-TCP-Position  # noqa: N815
    psi: np.ndarray  # (m,)
    u: np.ndarray  # (m,) Bahnparameter (Segmentindex + Anteil 0..1, Ende = Segment + 1)

    @staticmethod
    def empty() -> Dense:
        return Dense(np.zeros((0, 6)), np.zeros(0, bool), np.zeros((0, 3)), np.zeros(0), np.zeros(0))


def _follow(Qc: np.ndarray, okc: np.ndarray, q0: np.ndarray) -> np.ndarray:  # noqa: N803
    """Kanonische Loesungen stetig an q0 anschliessen (vektorisiert); unerreichbar -> letzte gueltige."""
    out = np.empty_like(Qc)
    idx = np.nonzero(okc)[0]
    if idx.size == 0:
        out[:] = q0
        return out
    R = Qc[idx]  # noqa: N806
    first = nearest_variant(R[0], q0)
    steps = joint_diff(R[1:], R[:-1])
    seq = np.vstack([first[None], first + np.cumsum(steps, axis=0)])
    # Grenzen: nur wenn die Stetigkeit ein +-360-Gelenk hinaus treibt, sequentiell korrigieren
    from roboprint.robot import JOINT_LIMITS

    if ((seq < JOINT_LIMITS[:, 0] - 1e-9) | (seq > JOINT_LIMITS[:, 1] + 1e-9)).any():
        prev = q0
        for k in range(len(R)):
            prev = nearest_variant(R[k], prev)
            seq[k] = prev
    # unerreichbare Samples behalten die letzte gueltige Loesung
    pos = np.searchsorted(idx, np.arange(len(Qc)), side="right") - 1
    out[:] = np.where((pos >= 0)[:, None], seq[np.maximum(pos, 0)], q0)
    return out


def _uniform_u(m: np.ndarray) -> np.ndarray:
    """m[s] gleichmaessige Schritte je Segment s; global u = s + i/m[s], i = 1..m[s]."""
    seg = np.repeat(np.arange(len(m)), m)
    frac = np.concatenate([np.arange(1, k + 1) / k for k in m])
    return seg + frac


def _adaptive_u(
    kin: Kin,
    P: np.ndarray,  # noqa: N803
    psi: np.ndarray,
    dpsi: np.ndarray,
    seg_len: np.ndarray,
    q_a: np.ndarray,
    br: np.ndarray,
    params: PlannerParams,
) -> np.ndarray:
    """Bahnparameter so dicht wie die Regel verlangt, nicht dichter (A4.6).

    Eine Vorabtastung (halbe TCP-Schrittweite) liefert je Schritt den Bedarf
    c = max(TCP-Weg / dense_tcp_mm, max|dq| / dense_dq_rad). Je Segment ergibt die Summe die
    Sampleanzahl n = ceil(sum c); die Samples liegen bei gleichen Anteilen des kumulierten
    Bedarfs, also dicht, wo die Gelenke schnell laufen, und weit, wo nur der TCP-Weg zaehlt.
    Segmentenden (Toolpath-Wegpunkte) bleiben exakt Samples. Die anschliessende Pruefschleife
    in `movel_chain` faengt Restverletzungen durch Nichtlinearitaet ab.
    """
    m_p = np.maximum(2, np.ceil(seg_len / (0.5 * params.dense_tcp_mm)).astype(int))
    up = _uniform_u(m_p)
    s_i = np.minimum(np.floor(up - 1e-12).astype(int), len(P) - 2)
    f = up - s_i
    pts = P[s_i] + f[:, None] * (P[s_i + 1] - P[s_i])
    Qn, okn = kin.ik(pts, psi[s_i] + f * dpsi[s_i])  # noqa: N806
    b = br[s_i + 1]
    ok = okn[np.arange(len(b)), b]
    q = _follow(Qn[np.arange(len(b)), b], ok, q_a)
    prev = np.vstack([q_a[None], q[:-1]])
    prev_ok = np.concatenate([[True], ok[:-1]])
    dq = np.abs(q - prev).max(axis=1)
    dp = np.repeat(seg_len / m_p, m_p)
    # Reserve 3 % auf die Gelenkgrenze: zwischen den Vorabsamples ist q nicht exakt linear.
    c = np.maximum(dp / params.dense_tcp_mm, np.where(ok & prev_ok, dq / (0.97 * params.dense_dq_rad), 0.0))
    c = c + 1e-9
    starts = np.concatenate([[0], np.cumsum(m_p)[:-1]])
    c_seg = np.add.reduceat(c, starts)
    n_seg = np.maximum(1, np.ceil(c_seg - 1e-6).astype(int))
    G = np.concatenate([[0.0], np.cumsum(c)])  # noqa: N806
    xu = np.concatenate([[0.0], up])
    seg = np.repeat(np.arange(len(n_seg)), n_seg)
    frac = np.concatenate([np.arange(1, k + 1) / k for k in n_seg])
    level = G[starts][seg] + frac * c_seg[seg]
    u = np.interp(level, G, xu)
    u = np.clip(u, seg + 1e-9, seg + 1.0)
    ends = np.cumsum(n_seg) - 1
    u[ends] = np.arange(len(n_seg)) + 1.0  # Wegpunkte exakt
    return u


def movel_chain(
    kin: Kin,
    P: np.ndarray,  # noqa: N803
    psi: np.ndarray,
    q_a: np.ndarray,
    branch: np.ndarray | int,
    params: PlannerParams,
) -> tuple[Dense, np.ndarray]:
    """Folge von movel-Stuecken P[i] -> P[i+1] (Duese senkrecht, psi linear auf dem kurzen Bogen).

    `branch` je Zielpunkt (Laenge n) oder fest. Liefert die Samples und je Sample den Index des
    Zielwegpunkts (i + 1).
    """
    P = np.asarray(P, float)  # noqa: N806
    psi = np.asarray(psi, float)
    n = len(P)
    if n < 2:
        return Dense.empty(), np.zeros(0, int)
    br = np.broadcast_to(np.asarray(branch, int), (n,))
    dpsi = wrap_pi(psi[1:] - psi[:-1])
    seg_len = np.linalg.norm(P[1:] - P[:-1], axis=1)
    u = _adaptive_u(kin, P, psi, dpsi, seg_len, q_a, br, params)
    Qc = np.zeros((0, 6))  # noqa: N806
    okc = np.zeros(0, bool)
    new = np.ones(len(u), bool)
    for _ in range(_MAX_REFINE):
        s_i = np.minimum(np.floor(u - 1e-12).astype(int), n - 2)
        f = u - s_i
        pts = P[s_i] + f[:, None] * (P[s_i + 1] - P[s_i])
        ps = psi[s_i] + f * dpsi[s_i]
        if new.any():
            Qn, okn = kin.ik(pts[new], ps[new])  # noqa: N806
            b = br[s_i[new] + 1]
            Qfull = np.zeros((len(u), 6))  # noqa: N806
            okfull = np.zeros(len(u), bool)
            Qfull[~new], okfull[~new] = Qc, okc
            Qfull[new] = Qn[np.arange(len(b)), b]
            okfull[new] = okn[np.arange(len(b)), b]
            Qc, okc = Qfull, okfull  # noqa: N806
        q = _follow(Qc, okc, q_a)
        prev = np.vstack([q_a[None], q[:-1]])
        prev_ok = np.concatenate([[True], okc[:-1]])
        need = np.ceil(np.abs(q - prev).max(axis=1) / params.dense_dq_rad).astype(int)
        need = np.where(okc & prev_ok, need, 1)
        if (need <= 1).all():
            break
        u_prev = np.concatenate([[0.0], u[:-1]])
        add = [
            u_prev[k] + (u[k] - u_prev[k]) * np.arange(1, need[k]) / need[k] for k in np.nonzero(need > 1)[0]
        ]
        u_add = np.concatenate(add)
        u_all = np.concatenate([u, u_add])
        order = np.argsort(u_all, kind="stable")
        new = np.concatenate([np.zeros(len(u), bool), np.ones(len(u_add), bool)])[order]
        Qc = np.concatenate([Qc, np.zeros((len(u_add), 6))])[order]  # noqa: N806
        okc = np.concatenate([okc, np.zeros(len(u_add), bool)])[order]
        Qc, okc = Qc[~new], okc[~new]  # noqa: N806
        u = u_all[order]
    else:
        # Verfeinerungsgrenze erreicht: die zuletzt eingefuegten Samples brauchen noch IK, sonst
        # passen q (alte Laenge) und u (neue Laenge) nicht zusammen (A2.2, IndexError in plan.py).
        s_i = np.minimum(np.floor(u - 1e-12).astype(int), n - 2)
        f = u - s_i
        pts = P[s_i] + f[:, None] * (P[s_i + 1] - P[s_i])
        ps = psi[s_i] + f * dpsi[s_i]
        Qn, okn = kin.ik(pts[new], ps[new])  # noqa: N806
        b = br[s_i[new] + 1]
        Qfull = np.zeros((len(u), 6))  # noqa: N806
        okfull = np.zeros(len(u), bool)
        Qfull[~new], okfull[~new] = Qc, okc
        Qfull[new] = Qn[np.arange(len(b)), b]
        okfull[new] = okn[np.arange(len(b)), b]
        Qc, okc = Qfull, okfull  # noqa: N806
        q = _follow(Qc, okc, q_a)
    s_i = np.minimum(np.floor(u - 1e-12).astype(int), n - 2)
    f = u - s_i
    pts = P[s_i] + f[:, None] * (P[s_i + 1] - P[s_i])
    ps = wrap_pi(psi[s_i] + f * dpsi[s_i])
    return Dense(q, okc, pts, ps, u), s_i + 1


def movel(
    kin: Kin,
    p_a: np.ndarray,
    psi_a: float,
    p_b: np.ndarray,
    psi_b: float,
    q_a: np.ndarray,
    branch: int,
    params: PlannerParams,
) -> Dense:
    d, _ = movel_chain(kin, np.array([p_a, p_b], float), np.array([psi_a, psi_b]), q_a, branch, params)
    return d


def movej(kin: Kin, q_a: np.ndarray, q_b: np.ndarray, params: PlannerParams) -> Dense:
    q_a, q_b = np.asarray(q_a, float), np.asarray(q_b, float)
    dq = q_b - q_a
    m = max(1, int(np.ceil(np.abs(dq).max() / params.dense_dq_rad)))
    for _ in range(_MAX_REFINE):
        u = np.linspace(0.0, 1.0, m + 1)
        Q = q_a + u[:, None] * dq  # noqa: N806
        T = kin.tcp_W(Q)  # noqa: N806
        step = np.linalg.norm(np.diff(T[:, :3, 3], axis=0), axis=1).max()
        if step <= params.dense_tcp_mm:
            break
        m = int(np.ceil(m * step / params.dense_tcp_mm * 1.05))
    else:  # Grenze erreicht: Samples zum zuletzt bestimmten m (sonst Laengen-Mismatch)
        u = np.linspace(0.0, 1.0, m + 1)
        Q = q_a + u[:, None] * dq  # noqa: N806
        T = kin.tcp_W(Q)  # noqa: N806
    return Dense(Q[1:], np.ones(m, bool), T[1:, :3, 3], psi_of(T[1:, :3, :3]), u[1:])
