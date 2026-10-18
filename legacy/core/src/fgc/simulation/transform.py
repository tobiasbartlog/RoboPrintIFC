"""Frame-Verkettung für die Simulation (ADR-006: eine Transformationsstelle).

Reine Quaternion-/Frame-Algebra ohne NumPy: Der Toolpath trägt die Ziel-Poses
(Düse/TCP) im **Wandkoordinatensystem**; die Simulation muss daraus die
**Flansch-Pose in Roboterbasis-Koordinaten** bilden, bevor sie die IK (`opw`)
befragt. Die Kette ist

    T_base_flansch = (wall_to_base ∘ target) ∘ tcp⁻¹

mit ``wall_to_base`` (Wand → Basis) und ``tcp`` (Flansch → Düse), beide aus dem
Setup. Frames folgen ADR-006: Position in mm, Einheitsquaternion ``[w, x, y, z]``,
aktive Rotation (``point_parent = R(quat)·point_local + pos``).
"""

from __future__ import annotations

import math

from fgc.domain.models import Frame

Quat = tuple[float, float, float, float]
Vec3 = tuple[float, float, float]


def quat_mul(a: Quat, b: Quat) -> Quat:
    """Hamilton-Produkt zweier Quaternionen [w, x, y, z] (a danach b anwenden)."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def quat_conj(q: Quat) -> Quat:
    """Konjugierte = Inverse für Einheitsquaternionen."""
    w, x, y, z = q
    return (w, -x, -y, -z)


def quat_normalize(q: Quat) -> Quat:
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n == 0.0:
        return (1.0, 0.0, 0.0, 0.0)
    return (w / n, x / n, y / n, z / n)


def quat_rotate(q: Quat, v: Vec3) -> Vec3:
    """Dreht Vektor ``v`` mit dem Einheitsquaternion ``q`` (Sandwich q·v·q*)."""
    qv: Quat = (0.0, v[0], v[1], v[2])
    w, x, y, z = quat_mul(quat_mul(q, qv), quat_conj(q))
    return (x, y, z)


def compose(a: Frame, b: Frame) -> Frame:
    """Verkettet zwei Frames: ``a`` (parent←mid) mit ``b`` (mid←local).

    Ergebnis bildet local → parent ab: ``pos = a.pos + R(a.quat)·b.pos``,
    ``quat = a.quat ⊗ b.quat``.
    """
    aq = quat_normalize(a.quat)
    rb = quat_rotate(aq, b.pos_mm)
    pos = (a.pos_mm[0] + rb[0], a.pos_mm[1] + rb[1], a.pos_mm[2] + rb[2])
    return Frame(pos_mm=pos, quat=quat_normalize(quat_mul(aq, quat_normalize(b.quat))))


def invert(f: Frame) -> Frame:
    """Kehrt einen Frame um: aus parent←local wird local←parent."""
    q = quat_normalize(f.quat)
    q_inv = quat_conj(q)
    r = quat_rotate(q_inv, f.pos_mm)
    return Frame(pos_mm=(-r[0], -r[1], -r[2]), quat=q_inv)


def frame_from_dict(d: dict) -> Frame:
    """Baut einen Frame aus einem Schema-Frame-Dict (pos_mm, quat)."""
    pos = tuple(float(x) for x in d["pos_mm"])
    quat = tuple(float(x) for x in d["quat"])
    return Frame(pos_mm=pos, quat=quat)  # type: ignore[arg-type]
