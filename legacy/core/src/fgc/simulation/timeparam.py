"""Zeitparametrierung einer Gelenkfolge unter Achsgrenzen (Issue #12, Strang C).

Aus einer Folge von Gelenklösungen (aus der Konfigurationswahl #11) und der
kartesischen Bahngeschwindigkeit ``v_mm_s`` des Toolpath entsteht die Zeitachse
``t_s`` der Trajectory: *wann* der Roboter *wo* ist. Jedem Segment wird eine
Dauer zugewiesen, die drei Untergrenzen respektiert:

1. **Bahngeschwindigkeit** — die kommandierte Druck-/Fahrgeschwindigkeit
   (kartesische Distanz / ``v_mm_s``); sie liefert die Druckzeitschätzung.
2. **Achsgeschwindigkeitsgrenze** — kein Gelenk bewegt sich schneller als
   ``v_max`` (Segmentdauer ≥ max_j |Δq_j| / v_max_j).
3. **Achsbeschleunigungsgrenze** — die Änderung der Segment-Gelenkgeschwindigkeit
   zwischen benachbarten Segmenten bleibt unter ``a_max`` (iterative Streckung,
   danach ein globaler Sicherungs-Skalierungsschritt als Garantie).

Modell (v0): stückweise konstante Gelenkgeschwindigkeit je Segment; die
Beschleunigung ist die endliche Differenz der Segmentgeschwindigkeiten über die
halbe Summe der Nachbardauern. Ergebnis ist eine **streng monotone** Zeitachse,
die Geschwindigkeits- und Beschleunigungsinvarianten je Gelenk einhält.
"""

from __future__ import annotations

from collections.abc import Sequence

Joints = Sequence[float]

#: Mindest-Segmentdauer (s), damit identische/sehr nahe Targets die Zeitachse
#: streng monoton halten (keine zwei Samples mit gleichem t_s).
DT_FLOOR_S = 1e-3


def segment_velocities(
    joints: list[tuple[float, ...]], dt: list[float]
) -> list[list[float]]:
    """Segment-Gelenkgeschwindigkeiten w_i,j = Δq_i,j / dt_i (rad/s)."""
    return [
        [(joints[i + 1][j] - joints[i][j]) / dt[i] for j in range(len(joints[i]))]
        for i in range(len(dt))
    ]


def node_accelerations(
    vel: list[list[float]], dt: list[float]
) -> list[list[float]]:
    """Beschleunigung an inneren Knoten a_i,j = (w_i − w_{i−1}) / T_i (rad/s²).

    T_i = halbe Summe der Nachbar-Segmentdauern. Liste hat len(dt)−1 Einträge
    (je innerer Knoten einen), leer bei ≤ 1 Segment.
    """
    acc: list[list[float]] = []
    for i in range(1, len(vel)):
        t_i = 0.5 * (dt[i - 1] + dt[i])
        acc.append([(vel[i][j] - vel[i - 1][j]) / t_i for j in range(len(vel[i]))])
    return acc


def _worst_ratios(
    joints: list[tuple[float, ...]],
    dt: list[float],
    v_max: Sequence[float],
    a_max: Sequence[float],
) -> tuple[float, float]:
    """Größte Ausnutzung (Geschwindigkeit, Beschleunigung) über alle Gelenke/Knoten."""
    vel = segment_velocities(joints, dt)
    rv = max(
        (
            abs(vel[i][j]) / v_max[j]
            for i in range(len(vel))
            for j in range(len(v_max))
            if v_max[j] > 0
        ),
        default=0.0,
    )
    acc = node_accelerations(vel, dt)
    ra = max(
        (
            abs(acc[i][j]) / a_max[j]
            for i in range(len(acc))
            for j in range(len(a_max))
            if a_max[j] > 0
        ),
        default=0.0,
    )
    return rv, ra


def parametrize(
    joints: list[tuple[float, ...]],
    cart_dist_mm: list[float],
    v_cmd_mm_s: list[float],
    v_max: Sequence[float],
    a_max: Sequence[float],
    *,
    dt_floor_s: float = DT_FLOOR_S,
    relax_iterations: int = 200,
) -> list[float]:
    """Berechnet die Zeitachse ``t_s`` (streng monoton) für die Gelenkfolge.

    ``joints`` in Bahnreihenfolge (je Target ein 6-Tupel), ``cart_dist_mm`` und
    ``v_cmd_mm_s`` je Segment (Länge len(joints)−1). Rückgabe: Zeiten je Target
    ab 0.0. Nach Rückkehr gilt für jedes Gelenk/Segment
    |Δq|/Δt ≤ v_max und für jeden inneren Knoten |Δw|/T ≤ a_max.
    """
    n = len(joints)
    if n <= 1:
        return [0.0] * n
    n_j = len(joints[0])

    # 1) Grunddauer aus Bahngeschwindigkeit + Achsgeschwindigkeitsgrenze.
    dt: list[float] = []
    for i in range(n - 1):
        dq = [abs(joints[i + 1][j] - joints[i][j]) for j in range(n_j)]
        t_vel = max(
            (dq[j] / v_max[j] for j in range(n_j) if v_max[j] > 0), default=0.0
        )
        t_cart = cart_dist_mm[i] / v_cmd_mm_s[i] if v_cmd_mm_s[i] > 0 else 0.0
        dt.append(max(t_vel, t_cart, dt_floor_s))

    # 2) Beschleunigung: lokale Streckung (monoton wachsende dt → konvergiert).
    for _ in range(relax_iterations):
        vel = segment_velocities(joints, dt)
        changed = False
        for i in range(1, len(vel)):
            t_i = 0.5 * (dt[i - 1] + dt[i])
            worst = 0.0
            for j in range(n_j):
                if a_max[j] <= 0:
                    continue
                a = abs(vel[i][j] - vel[i - 1][j]) / t_i
                worst = max(worst, a / a_max[j])
            if worst > 1.0 + 1e-9:
                factor = worst**0.5
                dt[i - 1] *= factor
                dt[i] *= factor
                changed = True
        if not changed:
            break

    # 3) Sicherungsnetz: ein globaler Skalierungsschritt garantiert die Grenzen
    #    (globale Skalierung um f teilt v durch f und a durch f²).
    rv, ra = _worst_ratios(joints, dt, v_max, a_max)
    f = max(1.0, rv, ra**0.5)
    if f > 1.0:
        dt = [d * f for d in dt]

    times = [0.0]
    for d in dt:
        times.append(times[-1] + d)
    return times


def axis_utilization(
    joints: list[tuple[float, ...]], times: list[float], v_max: Sequence[float]
) -> list[float]:
    """Spitzen-Achsauslastung je Gelenk ∈ [0, 1] (max |w_j| / v_max_j)."""
    n_j = len(v_max)
    if len(joints) <= 1:
        return [0.0] * n_j
    dt = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    vel = segment_velocities(joints, dt)
    util = []
    for j in range(n_j):
        if v_max[j] <= 0:
            util.append(0.0)
            continue
        peak = max(abs(vel[i][j]) for i in range(len(vel))) / v_max[j]
        util.append(min(1.0, peak))
    return util
