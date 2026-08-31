"""Kanonische Druck-Orientierung (ADR-006) und der bahn-relative Anstellwinkel.

Beim Drucken zeigt die Düse senkrecht nach unten (TCP-z auf −z der Wandwelt).
Diese Konvention ist die **einzige Quelle** für die Orientierung: der Slicer
backt sie in jedes Toolpath-Ziel ein, und die Erreichbarkeitsbewertung
(``fgc.placement`` / ``fgc.decompose``) leitet ihre Anfluggeometrie daraus ab.

Vor Issue #51 emittierte der Slicer stattdessen eine Identitäts-Orientierung,
während ``placement`` mit Düse-nach-unten rechnete — dieselbe Wand galt im
Druckplan als 100 % erreichbar, in der Simulation als 0 % (keine IK-Lösung).
Eine geteilte Quelle schließt dieses Auseinanderdriften aus.

Scheibe 3 (Issue #61) macht daraus die reine Funktion :func:`nozzle_quat`, die
zusätzlich einen **bahn-relativen Lead-/Lag-Winkel** und einen **Kipp-Winkel**
anlegt. Slicer *und* ``placement`` rufen dieselbe Funktion — der Slicer mit der
echten Bahntangente (aufeinanderfolgende Ringpunkte), ``placement`` mit seiner
angenommenen horizontalen Tangente entlang der Wandlänge. So bleibt der
Regressionsschutz von #51 auch mit angestellter Düse bestehen: Erreichbarkeit
und Simulation ziehen ihre Rotation aus **einer** Quelle.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

#: Düse senkrecht nach unten: 180°-Drehung um die Wand-x-Achse
#: (Rotationsmatrix ``diag(1, -1, -1)``). Einheitsquaternion ``[w, x, y, z]``
#: nach ADR-006. Zugleich der Nullpunkt von :func:`nozzle_quat` (Lead 0 / Kipp 0).
NOZZLE_DOWN_QUAT: tuple[float, float, float, float] = (0.0, 1.0, 0.0, 0.0)

Quat = tuple[float, float, float, float]


def _normalize3(v: Sequence[float]) -> tuple[float, float, float] | None:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n == 0.0:
        return None
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _axis_angle_quat(axis: Sequence[float], angle_rad: float) -> Quat:
    """Einheitsquaternion einer Drehung ``angle_rad`` um ``axis`` ([w, x, y, z])."""
    unit = _normalize3(axis)
    if unit is None or angle_rad == 0.0:
        return (1.0, 0.0, 0.0, 0.0)
    half = angle_rad / 2.0
    s = math.sin(half)
    return (math.cos(half), unit[0] * s, unit[1] * s, unit[2] * s)


def _quat_mul(a: Quat, b: Quat) -> Quat:
    """Hamilton-Produkt ``a ⊗ b`` ([w, x, y, z]) — Verkettung ``R_a @ R_b``."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _canonical(q: Quat) -> Quat:
    """Normiert und wählt das Vorzeichen ``w ≥ 0`` (kanonisch, wie ``_rot_to_quat``)."""
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n == 0.0:
        return NOZZLE_DOWN_QUAT
    if w < 0.0:
        n = -n
    return (w / n, x / n, y / n, z / n)


def nozzle_quat(
    tangent: Sequence[float],
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
) -> Quat:
    """Düsen-Orientierung (Quaternion [w, x, y, z]) für eine Bahntangente + Anstellung.

    **Die eine geteilte Orientierungsquelle** (Issue #61): Slicer und
    ``placement`` leiten hieraus ihre Rotation ab — keine Duplikation, kein Drift
    (Regressionsschutz #51).

    ``tangent`` ist die Bahn-Fahrtrichtung in Wandkoordinaten (x = Wandlänge,
    y = Wanddicke/Front, z = Höhe); nur die horizontale Komponente (x, y) zählt.
    Aus einem **CCW-orientierten Ring** ist die Wand-Außenseite eindeutig die
    rechte Seite der Fahrtrichtung, ``n_out = tangent × ẑ`` (Innenraum liegt bei
    CCW links). Darauf beruht die Vorzeichenkonvention:

    - ``+lead`` kippt die Düsenachse **in Fahrtrichtung** (Lead; ``−`` = Lag),
      Drehung um ``n_out``.
    - ``+kipp`` kippt die Düsenachse **zur Wand-Außenseite** (``n_out``),
      Drehung um die Tangente.

    Nullpunkt ``lead = kipp = 0`` ⇒ exakt :data:`NOZZLE_DOWN_QUAT` (heutiges
    Verhalten, senkrecht von oben) — **unabhängig von der Tangente**. Eine
    degenerierte (Null-)Tangente fällt ebenfalls auf ``NOZZLE_DOWN_QUAT`` zurück.
    """
    if lead_rad == 0.0 and kipp_rad == 0.0:
        return NOZZLE_DOWN_QUAT
    t = _normalize3((float(tangent[0]), float(tangent[1]), 0.0))
    if t is None:
        return NOZZLE_DOWN_QUAT
    n_out = _cross(t, (0.0, 0.0, 1.0))  # rechte Seite der Fahrt = Wand-Außenseite (CCW)
    q_lead = _axis_angle_quat(n_out, lead_rad)  # +lead → Düse in Fahrtrichtung
    q_kipp = _axis_angle_quat(t, -kipp_rad)  # +kipp → Düse zur Außenseite (n_out)
    return _canonical(_quat_mul(q_lead, _quat_mul(q_kipp, NOZZLE_DOWN_QUAT)))
