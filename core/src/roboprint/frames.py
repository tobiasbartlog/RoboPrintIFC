"""Alle Frame-Uebergaenge aus SPEC §2 (G, W, B, S, F, T, P, L); sonst nirgends.

Konvention: `T_AB` ist die Pose von Frame B in Frame A, also `p_A = T_AB @ p_B`.
4x4-Matrizen, Translation in mm, Quaternionen (w, x, y, z), Spaltenvektoren.
Frame-Quellen (Workstation, Werkzeug) werden duck-typed gelesen: Objekte mit den Attributen
`pos_mm` und `quat` (siehe `roboprint.assets.Frame`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

# --------------------------------------------------------------------------- Grundlagen


@dataclass(frozen=True)
class Placement:
    """Platzierung eines Moduls auf der Arbeitsflaeche S: (x, y) in mm, Gierwinkel um Z_S in rad."""

    x_mm: float
    y_mm: float
    yaw_rad: float


def quat_normalize(q: Any) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    n = float(np.linalg.norm(q))
    if n < 1e-12:
        raise ValueError("Nullquaternion")
    return q / n


def quat_to_matrix(q: Any) -> np.ndarray:
    """Quaternion (w, x, y, z) -> 3x3 Rotationsmatrix."""
    w, x, y, z = quat_normalize(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def matrix_to_quat(R: Any) -> np.ndarray:  # noqa: N803
    """3x3 (oder 4x4) Rotationsmatrix -> Quaternion (w, x, y, z), w >= 0."""
    R = np.asarray(R, dtype=float)[:3, :3]  # noqa: N806
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = 2.0 * np.sqrt(tr + 1.0)
        q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        q = [(R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s]
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        q = [(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s]
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        q = [(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s]
    q = quat_normalize(q)
    return -q if q[0] < 0 else q


def quat_multiply(a: Any, b: Any) -> np.ndarray:
    """Hamilton-Produkt a * b, Quaternionen (w, x, y, z)."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ]
    )


def rot_z(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def make_T(R: Any = None, p: Any = None) -> np.ndarray:  # noqa: N802, N803
    """4x4 aus Rotation (3x3) und Translation (3)."""
    T = np.eye(4)  # noqa: N806
    if R is not None:
        T[:3, :3] = np.asarray(R, dtype=float)
    if p is not None:
        T[:3, 3] = np.asarray(p, dtype=float)
    return T


def T_from_pos_quat(pos_mm: Any, quat: Any) -> np.ndarray:  # noqa: N802
    return make_T(quat_to_matrix(quat), pos_mm)


def pose7(T: Any) -> np.ndarray:  # noqa: N803
    """4x4 -> [x, y, z, qw, qx, qy, qz] (mm, Quaternion w-zuerst)."""
    T = np.asarray(T, dtype=float)  # noqa: N806
    return np.concatenate([T[:3, 3], matrix_to_quat(T[:3, :3])])


def T_from_pose7(pose: Any) -> np.ndarray:  # noqa: N802
    """[x, y, z, qw, qx, qy, qz] -> 4x4."""
    pose = np.asarray(pose, dtype=float)
    return T_from_pos_quat(pose[:3], pose[3:7])


def invert(T: Any) -> np.ndarray:  # noqa: N803
    """Inverse einer starren Transformation (ohne allgemeine Matrixinversion)."""
    T = np.asarray(T, dtype=float)  # noqa: N806
    R = T[:3, :3]  # noqa: N806
    return make_T(R.T, -R.T @ T[:3, 3])


def transform_points(T: Any, pts: Any) -> np.ndarray:  # noqa: N803
    """Wendet T auf (n, 3)-Punkte an."""
    T = np.asarray(T, dtype=float)  # noqa: N806
    pts = np.asarray(pts, dtype=float)
    return pts @ T[:3, :3].T + T[:3, 3]


def _frame(obj: Any) -> np.ndarray:
    return T_from_pos_quat(obj.pos_mm, obj.quat)


# --------------------------------------------------------------------------- Workstation


def T_WB(ws: Any) -> np.ndarray:  # noqa: N802
    """Roboterbasis B in W (`robot_base_frame`)."""
    return _frame(ws.robot_base_frame)


def T_WS(ws: Any) -> np.ndarray:  # noqa: N802
    """Arbeitsflaeche S in W (`work_surface_frame`, Tischoberkante)."""
    return _frame(ws.work_surface_frame)


def T_BW(ws: Any) -> np.ndarray:  # noqa: N802
    """W in der Roboterbasis B."""
    return invert(T_WB(ws))


def T_SW(ws: Any) -> np.ndarray:  # noqa: N802
    """W in der Arbeitsflaeche S."""
    return invert(T_WS(ws))


def T_BS(ws: Any) -> np.ndarray:  # noqa: N802
    """Arbeitsflaeche S in der Roboterbasis B."""
    return T_BW(ws) @ T_WS(ws)


# --------------------------------------------------------------------------- Werkzeug


def T_FT(tool: Any) -> np.ndarray:  # noqa: N802
    """TCP T im Flansch F (`tcp_frame`)."""
    return _frame(tool.tcp_frame)


def T_F_mesh(tool: Any) -> np.ndarray:  # noqa: N802
    """Werkzeugmesh im Flansch F (`mesh_transform`; ohne Eintrag Identitaet)."""
    mt = getattr(tool, "mesh_transform", None)
    return np.eye(4) if mt is None else _frame(mt)


def T_BT(T_BF: Any, tool: Any) -> np.ndarray:  # noqa: N802, N803
    """TCP in der Basis B: T_BF @ T_FT (DRL-Posen sind T_BT)."""
    return np.asarray(T_BF, dtype=float) @ T_FT(tool)


def T_BF_from_T_BT(T_BT_: Any, tool: Any) -> np.ndarray:  # noqa: N802, N803
    """Flanschpose aus TCP-Pose in B (Eingabe fuer die IK)."""
    return np.asarray(T_BT_, dtype=float) @ invert(T_FT(tool))


def T_WT(ws: Any, tool: Any, T_BF: Any) -> np.ndarray:  # noqa: N802, N803
    """TCP in W."""
    return T_WB(ws) @ T_BT(T_BF, tool)


# --------------------------------------------------------------------------- Teil und Platzierung


def T_SP(placement: Placement) -> np.ndarray:  # noqa: N802
    """Teil P auf der Arbeitsflaeche S: Verschiebung (x, y, 0) und Gierwinkel um Z_S."""
    return make_T(rot_z(placement.yaw_rad), [placement.x_mm, placement.y_mm, 0.0])


def T_WP(ws: Any, placement: Placement) -> np.ndarray:  # noqa: N802
    """Teil P in W: T_WS @ T_SP."""
    return T_WS(ws) @ T_SP(placement)


def T_BP(ws: Any, placement: Placement) -> np.ndarray:  # noqa: N802
    """Teil P in der Roboterbasis B."""
    return T_BW(ws) @ T_WP(ws, placement)


def T_LP(bbox_min_L: Any, bbox_max_L: Any) -> np.ndarray:  # noqa: N802, N803
    """Teil P in der Wand L: Ursprung in der Mitte der Bodenflaeche der Teil-Bounding-Box (in L),
    Achsen parallel zu L."""
    lo = np.asarray(bbox_min_L, dtype=float)
    hi = np.asarray(bbox_max_L, dtype=float)
    return make_T(None, [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])


# --------------------------------------------------------------------------- Wand


def wall_frame_from_ifc(vertices_mm: Any, axis_hint: Any = None) -> np.ndarray:
    """Wand-Frame L als `T_GL` (4x4, mm): Pose von L im globalen IFC-Frame G.

    `vertices_mm` sind die Wandvertices in G (n, 3). X_L liegt entlang der langen Seite des
    Grundriss-Rechtecks kleinster Flaeche (Wandachse), Z_L = Z_G, Y_L = Z x X (rechtshaendig).
    Der Ursprung ist die min-Ecke der Wand (min x_L, min y_L, min z). `axis_hint` (Vektor in G,
    z. B. die X-Achse der IFC-Platzierung) legt nur das Vorzeichen von X_L fest; ohne Hinweis
    gilt eine kanonische Richtung (x-Anteil positiv, bei Gleichstand y-Anteil positiv).
    """
    from shapely.geometry import MultiPoint

    v = np.asarray(vertices_mm, dtype=float)
    if v.ndim != 2 or v.shape[1] != 3 or len(v) < 4:
        raise ValueError(f"Erwarte (n,3)-Vertices, bekam {v.shape}")
    rect = MultiPoint(v[:, :2]).minimum_rotated_rectangle
    if rect.geom_type != "Polygon":
        raise ValueError("Wandgrundriss ist degeneriert")
    c = np.asarray(rect.exterior.coords)[:4]
    e0, e1 = c[1] - c[0], c[2] - c[1]
    e = e0 if np.linalg.norm(e0) >= np.linalg.norm(e1) else e1
    x2 = e / np.linalg.norm(e)
    if axis_hint is not None:
        h = np.asarray(axis_hint, dtype=float)[:2]
        flip = float(x2 @ h) < 0
    else:
        flip = x2[0] < -1e-9 or (abs(x2[0]) <= 1e-9 and x2[1] < 0)
    if flip:
        x2 = -x2
    x2 = np.where(np.abs(x2) < 1e-12, 0.0, x2)
    x_axis = np.array([x2[0], x2[1], 0.0])
    z_axis = np.array([0.0, 0.0, 1.0])
    y_axis = np.cross(z_axis, x_axis)
    R = np.column_stack([x_axis, y_axis, z_axis])  # noqa: N806
    origin = np.array([v @ x_axis, v @ y_axis, v @ z_axis]).min(axis=1)
    return make_T(R, R @ origin)


def T_LG(T_GL: Any) -> np.ndarray:  # noqa: N802, N803
    """Globales IFC G in der Wand L (zum Umrechnen von Meshes G -> L)."""
    return invert(T_GL)
