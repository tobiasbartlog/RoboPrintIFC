"""Zeitparametrierung (SPEC §5.5): Trapezprofile je Bewegungsabschnitt, `t_s` streng monoton.

- Strang (SPEC §5.3, Nutzerentscheidung 20.10.2026): alle `print`- und `link`-Samples ohne
  Unterbrechung sind **ein** Abschnitt mit konstanter Bahngeschwindigkeit v_print und einem
  Trapezprofil (Rampen mit a_print nur am Strangbeginn und -ende, an Ringgrenzen im Strang keine).
  Ein neuer Strang beginnt nach jeder anderen Bewegungsart und bei `print` eines anderen Rings ohne
  Verbinder dazwischen.
- An-/Abfahrt: kartesisch mit v_print (wie im DRL ohne `vel=`); Abheben, Absenken: v_travel.
  Zuordnung und Standardwerte stehen in `roboprint.params` (eine Quelle fuer `timing` und `drl`).
- Transfer (movej): gelenklinear mit hoechstens `joint_speed_fraction` der Achsgrenzen.
- In jedem Abschnitt gilt zusaetzlich |dq_j| / dt <= Achsgrenze (Strang: volle Grenze, Travel:
  Anteil); wo das greift, wird die Zeit gestreckt.
- Pumpen-Vorlauf t_tot einmal je Strang: Das erste Sample des Strangs (Duplikat des Ringstarts nach
  der Anfahrt) bekommt t_tot zusaetzlich (Stillstand, Pumpe an, `wait(t_tot)` im DRL).

Die Zeiten dienen der Wiedergabe und der Druckzeitschaetzung; geprueft wird geometrisch.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from roboprint import params as speeds
from roboprint.robot import JOINT_VEL_LIMITS

DT_FLOOR_S = 1e-3
_CARTESIAN = speeds.CARTESIAN_KINDS
_STRAND = ("print", "link")


@dataclass(frozen=True)
class TimingParams:
    """Standardwerte aus `roboprint.params` (eine Quelle mit dem DRL-Emitter)."""

    v_print_mm_s: float = speeds.V_PRINT_MM_S
    a_print_mm_s2: float = speeds.A_PRINT_MM_S2
    v_travel_mm_s: float = speeds.V_TRAVEL_MM_S
    a_travel_mm_s2: float = speeds.A_TRAVEL_MM_S2
    joint_speed_fraction: float = speeds.JOINT_SPEED_FRACTION
    joint_acc_factor: float = speeds.JOINT_ACC_FACTOR  # Gelenkbeschleunigung = Faktor x Gelenkgeschw. (1/s)
    t_tot_s: float = 3.0


def trapezoid_times(s: np.ndarray, v: float, a: float) -> np.ndarray:
    """Zeit, zu der die Bogenlaenge s (aufsteigend, ab 0) im Trapezprofil erreicht wird."""
    s = np.asarray(s, float)
    S = float(s[-1]) if len(s) else 0.0  # noqa: N806
    if S <= 0.0:
        return np.zeros_like(s)
    s_acc = v * v / (2.0 * a)
    if S >= 2.0 * s_acc:
        t_acc = v / a
        t_cruise = (S - 2.0 * s_acc) / v
        t = np.where(
            s <= s_acc,
            np.sqrt(2.0 * np.maximum(s, 0.0) / a),
            np.where(
                s <= S - s_acc,
                t_acc + (s - s_acc) / v,
                t_acc + t_cruise + t_acc - np.sqrt(2.0 * np.maximum(S - s, 0.0) / a),
            ),
        )
    else:
        vp = np.sqrt(S * a)
        th = vp / a
        t = np.where(
            s <= S / 2,
            np.sqrt(2.0 * np.maximum(s, 0.0) / a),
            2 * th - np.sqrt(2.0 * np.maximum(S - s, 0.0) / a),
        )
    return t


def _joined(kind: list[str], ring: list[int], i: int) -> bool:
    """Gehoert Sample i zum Abschnitt von Sample i - 1? Im Strang verbindet `link` die Ringe."""
    a, b = kind[i - 1], kind[i]
    if a in _STRAND and b in _STRAND:
        return ring[i] == ring[i - 1] or b == "link"
    return a == b and ring[i] == ring[i - 1]


def sections(kind: list[str], ring: list[int]) -> list[tuple[int, int]]:
    """Bewegungsabschnitte (Start, Ende exklusiv): je Strang einer, sonst gleiche (Art, Ring)."""
    runs, s = [], 0
    for i in range(1, len(kind) + 1):
        if i == len(kind) or not _joined(kind, ring, i):
            runs.append((s, i))
            s = i
    return runs


def time_parametrize(
    q: np.ndarray,
    tcp_mm: np.ndarray,
    kind: list[str],
    ring: list[int],
    params: TimingParams | None = None,
) -> np.ndarray:
    """Zeitstempel t_s (N,) fuer die dichte Trajektorie; Sample 0 bei t = 0."""
    p = params or TimingParams()
    q = np.asarray(q, float)
    P = np.asarray(tcp_mm, float)  # noqa: N806
    n = len(q)
    dt = np.zeros(n)
    vj_full = JOINT_VEL_LIMITS
    vj_travel = p.joint_speed_fraction * JOINT_VEL_LIMITS
    for a, b in sections(kind, ring):
        if a == 0:
            a = 1  # Sample 0 ist der Start (Home)
            if b <= a:
                continue
        k = kind[a]
        idx = np.arange(a, b)
        dq = np.abs(q[idx] - q[idx - 1])
        if k in _CARTESIAN:
            ds = np.linalg.norm(P[idx] - P[idx - 1], axis=1)
            v, acc = speeds.cartesian_speed(
                k, p.v_print_mm_s, p.a_print_mm_s2, p.v_travel_mm_s, p.a_travel_mm_s2
            )
            t = trapezoid_times(np.concatenate([[0.0], np.cumsum(ds)]), v, acc)
            d = np.diff(t)
            vlim = vj_full if k in _STRAND else vj_travel
        else:  # transfer, gelenklinear: Fortschritt in "Zeit bei Hoechstgeschwindigkeit"
            du = (dq / vj_travel).max(axis=1)
            t = trapezoid_times(np.concatenate([[0.0], np.cumsum(du)]), 1.0, p.joint_acc_factor)
            d = np.diff(t)
            vlim = vj_travel
        d = np.maximum(d, (dq / vlim).max(axis=1))
        dt[idx] = np.maximum(d, DT_FLOOR_S)
        if k == "print":  # Strangbeginn: Pumpen-Vorlauf
            dt[a] += p.t_tot_s
    return np.cumsum(dt)
