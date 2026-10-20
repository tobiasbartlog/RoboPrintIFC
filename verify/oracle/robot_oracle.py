"""Unabhaengiges Kinematik-Orakel: FK und Grenzen des Doosan M1013 aus der URDF mit Pinocchio.

Liest nur die URDF (`third_party/doosan_m1013/urdf/m1013.white.urdf`), `tools/30gut.json`,
`workstations/doosantisch.json` und aus `robots/doosan_m1013.json` die Gelenk- und
Geschwindigkeitsgrenzen. Importiert `roboprint` nie.

Einheiten: Laengen in mm (die URDF rechnet in m und wird hier umgerechnet), Winkel in rad,
q in Doosan-Steuerungskonvention (= URDF-Nullstellung). Quaternionen (w, x, y, z).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np
import pinocchio as pin

ROOT = Path(__file__).resolve().parents[2]
URDF = ROOT / "third_party" / "doosan_m1013" / "urdf" / "m1013.white.urdf"
ROBOT_JSON = ROOT / "robots" / "doosan_m1013.json"
TOOL_JSON = ROOT / "tools" / "30gut.json"
WORKSTATION_JSON = ROOT / "workstations" / "doosantisch.json"

LINK_NAMES = ("base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6")
FLANGE = "link_6"
HOME_RAD = np.deg2rad([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])


# --------------------------------------------------------------------------- Mathematik


def quat_to_R(q_wxyz) -> np.ndarray:
    w, x, y, z = (float(v) for v in q_wxyz)
    n = np.sqrt(w * w + x * x + y * y + z * z)
    if n == 0.0:
        raise ValueError("Quaternion mit Norm 0")
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def R_to_quat(R: np.ndarray) -> np.ndarray:
    """Rotationsmatrix -> Quaternion (w, x, y, z) mit w >= 0 (Shepperd)."""
    R = np.asarray(R, dtype=float)
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = [(R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s]
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = [(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s]
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = [(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s]
    q = np.array(q)
    q /= np.linalg.norm(q)
    return -q if q[0] < 0 else q


def pose_to_T(pos_mm, quat_wxyz) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = quat_to_R(quat_wxyz)
    T[:3, 3] = np.asarray(pos_mm, dtype=float)
    return T


def pose7_to_T(p7) -> np.ndarray:
    """[x, y, z, qw, qx, qy, qz] -> 4x4."""
    return pose_to_T(p7[:3], p7[3:7])


def T_to_pose7(T: np.ndarray) -> np.ndarray:
    return np.concatenate([T[:3, 3], R_to_quat(T[:3, :3])])


def inv_T(T: np.ndarray) -> np.ndarray:
    Ti = np.eye(4)
    Ti[:3, :3] = T[:3, :3].T
    Ti[:3, 3] = -T[:3, :3].T @ T[:3, 3]
    return Ti


def rot_angle(Ra: np.ndarray, Rb: np.ndarray) -> float:
    """Winkel der Relativdrehung Ra^T Rb in rad, numerisch stabil auch nahe 0 und pi."""
    Rr = np.asarray(Ra).T @ np.asarray(Rb)
    s = 0.5 * np.linalg.norm([Rr[2, 1] - Rr[1, 2], Rr[0, 2] - Rr[2, 0], Rr[1, 0] - Rr[0, 1]])
    c = 0.5 * (np.trace(Rr) - 1.0)
    return float(np.arctan2(s, c))


def Rz(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def Ry(b: float) -> np.ndarray:
    c, s = np.cos(b), np.sin(b)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def zyz_to_R(a_deg: float, b_deg: float, c_deg: float) -> np.ndarray:
    """Doosan-posx-Orientierung: R = Rz(A) * Ry(B) * Rz(C), Winkel in Grad."""
    return Rz(np.deg2rad(a_deg)) @ Ry(np.deg2rad(b_deg)) @ Rz(np.deg2rad(c_deg))


def R_to_zyz(R: np.ndarray) -> tuple[float, float, float]:
    """Unabhaengige Umkehrung von zyz_to_R in Grad, B in [0, 180]. Gimbal-Faelle B = 0 / 180:
    C = 0 und A traegt die gesamte Drehung (bei B = 180 gilt R = Rz(A - C) * Ry(180))."""
    R = np.asarray(R, dtype=float)
    cb = float(np.clip(R[2, 2], -1.0, 1.0))
    sb = float(np.hypot(R[0, 2], R[1, 2]))
    b = np.arctan2(sb, cb)
    if sb > 1e-9:
        a = np.arctan2(R[1, 2], R[0, 2])
        c = np.arctan2(R[2, 1], -R[2, 0])
    elif cb > 0:  # B = 0: R = Rz(A + C)
        a, c = np.arctan2(R[1, 0], R[0, 0]), 0.0
    else:  # B = 180: R = Rz(A - C) * diag(-1, 1, -1)
        a, c = np.arctan2(-R[0, 1], R[1, 1]), 0.0
    return float(np.rad2deg(a)), float(np.rad2deg(b)), float(np.rad2deg(c))


def wrap_pi(x):
    return (np.asarray(x) + np.pi) % (2 * np.pi) - np.pi


# --------------------------------------------------------------------------- Assets


def load_json(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_package_uri(uri: str, urdf_path: Path = URDF) -> Path:
    """`package://dsr_description2/meshes/...` -> Datei unter third_party/doosan_m1013/meshes."""
    if uri.startswith("package://"):
        rest = uri[len("package://"):].split("/", 1)[1]  # Paketname abtrennen
        return (urdf_path.parent.parent / rest).resolve()
    if uri.startswith("file://"):
        return Path(uri[len("file://"):])
    return (urdf_path.parent / uri).resolve()


def urdf_collision_meshes(urdf_path: Path = URDF) -> dict[str, list[tuple[Path, np.ndarray, np.ndarray]]]:
    """Je Glied die Kollisionsmeshes: (Datei, T_link_mesh in mm, Skalierung nach mm)."""
    root = ET.parse(urdf_path).getroot()
    out: dict[str, list] = {}
    for link in root.findall("link"):
        items = []
        for col in link.findall("collision"):
            origin = col.find("origin")
            xyz = np.array([float(v) for v in (origin.get("xyz", "0 0 0") if origin is not None
                                               else "0 0 0").split()]) * 1000.0
            rpy = [float(v) for v in (origin.get("rpy", "0 0 0") if origin is not None
                                      else "0 0 0").split()]
            mesh = col.find("geometry/mesh")
            if mesh is None:
                raise ValueError(f"Kollisionsgeometrie von {link.get('name')} ist kein Mesh")
            scale = np.array([float(v) for v in mesh.get("scale", "1 1 1").split()]) * 1000.0
            T = np.eye(4)
            T[:3, :3] = pin.rpy.rpyToMatrix(*rpy)
            T[:3, 3] = xyz
            items.append((resolve_package_uri(mesh.get("filename"), urdf_path), T, scale))
        out[link.get("name")] = items
    return out


# --------------------------------------------------------------------------- Roboter


class RobotOracle:
    """FK des M1013 aus der URDF. Alle Posen in B (Roboterbasis), mm."""

    def __init__(self, urdf_path: Path = URDF, robot_json: Path = ROBOT_JSON, tool_json: Path = TOOL_JSON):
        self.urdf_path = Path(urdf_path)
        self.model = pin.buildModelFromUrdf(str(self.urdf_path))
        self.data = self.model.createData()
        self.link_ids = [self.model.getFrameId(n) for n in LINK_NAMES]
        self.flange_id = self.model.getFrameId(FLANGE)
        kin = load_json(robot_json)["kinematics"]
        self.limits = np.array(kin["joint_limits_rad"], dtype=float)  # 6x2
        self.vel_limits = np.array(kin["joint_velocity_limits_rad_s"], dtype=float)
        tool = load_json(tool_json)
        self.tool = tool
        self.T_FT = pose_to_T(tool["tcp_frame"]["pos_mm"], tool["tcp_frame"]["quat"])
        self.T_F_toolmesh = pose_to_T(tool["mesh_transform"]["pos_mm"], tool["mesh_transform"]["quat"])

    # FK ---------------------------------------------------------------------
    def _update(self, q) -> None:
        q = np.asarray(q, dtype=float).reshape(6)
        pin.forwardKinematics(self.model, self.data, q)
        pin.updateFramePlacements(self.model, self.data)

    @staticmethod
    def _se3_mm(M) -> np.ndarray:
        T = np.eye(4)
        T[:3, :3] = M.rotation
        T[:3, 3] = M.translation * 1000.0
        return T

    def fk(self, q) -> np.ndarray:
        """T_BF (Flansch `link_6` in B), mm."""
        self._update(q)
        return self._se3_mm(self.data.oMf[self.flange_id])

    def fk_links(self, q) -> list[np.ndarray]:
        """T_B,link fuer base_link ... link_6 (Reihenfolge LINK_NAMES), mm."""
        self._update(q)
        return [self._se3_mm(self.data.oMf[i]) for i in self.link_ids]

    def fk_tcp(self, q) -> np.ndarray:
        """T_BT = T_BF * T_FT, mm."""
        return self.fk(q) @ self.T_FT

    def ik_numeric(self, T_BF_target: np.ndarray, q0, iters: int = 200, tol_mm: float = 1e-6,
                   damping: float = 1e-6) -> tuple[np.ndarray, bool]:
        """Numerische IK (gedaempfte kleinste Quadrate) fuer Testfaelle: nur lokal, kein Zweig-Begriff.
        Gibt (q, konvergiert) zurueck. q wird nicht in die Grenzen geklemmt."""
        target = pin.SE3(np.asarray(T_BF_target[:3, :3]), np.asarray(T_BF_target[:3, 3]) / 1000.0)
        q = np.asarray(q0, dtype=float).copy()
        for _ in range(iters):
            self._update(q)
            cur = self.data.oMf[self.flange_id]
            err = pin.log6(cur.actInv(target)).vector
            if np.linalg.norm(err[:3]) * 1000.0 < tol_mm and np.linalg.norm(err[3:]) < tol_mm * 1e-3:
                return wrap_pi(q), True
            pin.computeJointJacobians(self.model, self.data, q)
            J = pin.getFrameJacobian(self.model, self.data, self.flange_id, pin.LOCAL)
            dq = J.T @ np.linalg.solve(J @ J.T + damping * np.eye(6), err)
            n = np.abs(dq).max()
            q = q + (dq * (0.3 / n) if n > 0.3 else dq)
        return wrap_pi(q), False

    # Grenzen -----------------------------------------------------------------
    def in_limits(self, q, tol: float = 1e-9) -> bool:
        q = np.asarray(q, dtype=float)
        return bool(np.all(q >= self.limits[:, 0] - tol) and np.all(q <= self.limits[:, 1] + tol))

    # Zweig ---------------------------------------------------------------------
    def branch_signs(self, q, eps: float = 1e-3) -> tuple[int, int, int]:
        """Eigene geometrische Zweig-Klassifikation (Schulter, Ellbogen, Handgelenk) als Vorzeichen
        in {-1, 0, +1}; 0 heisst singulaer/unentschieden (|Wert| < eps).

        - Schulter: Lage des Handgelenkzentrums (Ursprung `link_5`) vor/hinter der J1-Achse, gemessen
          entlang f = a2 x a1 (a1, a2: Achsen von J1, J2) relativ zum J2-Ursprung, in mm/1000.
        - Ellbogen: Lage des Ellbogens (Ursprung `link_3`) links/rechts der Linie Schulter -> Handgelenk
          um die J2-Achse (Vorzeichen von sin(Ellbogenwinkel)).
        - Handgelenk: Vorzeichen von sin(q5).
        Die Polaritaet gegen die Doosan-Bezeichnungen (Lefty/Righty usw.) ist bewusst offen; die
        Pruefer verlangen nur eine eineindeutige Zuordnung zu den Zweig-Bits.
        """
        self._update(q)
        o = self.data.oMf
        idx = {n: self.model.getFrameId(n) for n in ("link_1", "link_2", "link_3", "link_5")}
        a1 = o[idx["link_1"]].rotation[:, 2]
        a2 = o[idx["link_2"]].rotation[:, 2]
        p2 = o[idx["link_2"]].translation
        p3 = o[idx["link_3"]].translation
        pw = o[idx["link_5"]].translation
        f = np.cross(a2, a1)
        shoulder = float(np.dot(pw - p2, f))
        elbow = float(np.dot(np.cross(pw - p2, p3 - p2), a2)) / max(np.linalg.norm(pw - p2), 1e-9)
        wrist = float(np.sin(np.asarray(q, dtype=float)[4]))

        def sgn(v: float) -> int:
            return 0 if abs(v) < eps else (1 if v > 0 else -1)

        return sgn(shoulder), sgn(elbow), sgn(wrist)


@lru_cache(maxsize=1)
def default_robot() -> RobotOracle:
    return RobotOracle()


def workstation_frames(ws_json: Path = WORKSTATION_JSON) -> tuple[np.ndarray, np.ndarray, dict]:
    """(T_WB, T_WS, Workstation-JSON)."""
    ws = load_json(ws_json)
    T_WB = pose_to_T(ws["robot_base_frame"]["pos_mm"], ws["robot_base_frame"]["quat"])
    T_WS = pose_to_T(ws["work_surface_frame"]["pos_mm"], ws["work_surface_frame"]["quat"])
    return T_WB, T_WS, ws
