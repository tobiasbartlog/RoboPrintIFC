"""Roboter (URDF), Werkzeug, Workstation und Prozessparameter laden (SPEC §4).

Laengen in mm, Winkel in rad, Quaternionen (w, x, y, z).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

# --- A1.1: Roboter (URDF-Kette und Grenzen) ----------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
URDF_PATH = Path("third_party/doosan_m1013/urdf/m1013.white.urdf")
ROBOT_JSON_PATH = Path("robots/doosan_m1013.json")

# Datenblatt M1013 (docs/doosan-drl.md): 120/120/180/225/225/225 Grad/s.
JOINT_VEL_LIMITS: np.ndarray = np.radians([120.0, 120.0, 180.0, 225.0, 225.0, 225.0])


def rpy_to_rot(rpy) -> np.ndarray:
    """URDF-rpy (fest um X, dann Y, dann Z): R = Rz(yaw) Ry(pitch) Rx(roll)."""
    r, p, y = rpy
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


@dataclass(frozen=True)
class UrdfJoint:
    """Ein Drehgelenk der URDF-Kette; `origin` ist T_parent,joint (4x4, mm)."""

    name: str
    parent: str
    child: str
    origin: np.ndarray
    axis: np.ndarray


@dataclass(frozen=True)
class Robot:
    """Seriell verkettete Drehgelenke Basis -> Flansch plus Grenzen in Doosan-Konvention."""

    urdf_path: Path
    joints: tuple[UrdfJoint, ...]
    joint_limits: np.ndarray  # 6x2 rad
    vel_limits: np.ndarray  # 6 rad/s


def _parse_urdf_chain(path: Path) -> tuple[UrdfJoint, ...]:
    root = ET.parse(path).getroot()
    by_parent: dict[str, UrdfJoint] = {}
    for j in root.findall("joint"):
        if j.get("type") not in ("revolute", "continuous"):
            continue
        o = j.find("origin")
        xyz = [float(v) for v in (o.get("xyz", "0 0 0") if o is not None else "0 0 0").split()]
        rpy = [float(v) for v in (o.get("rpy", "0 0 0") if o is not None else "0 0 0").split()]
        ax = j.find("axis")
        axis = np.array([float(v) for v in (ax.get("xyz") if ax is not None else "1 0 0").split()])
        T = np.eye(4)
        T[:3, :3] = rpy_to_rot(rpy)
        T[:3, 3] = np.array(xyz) * 1000.0  # m -> mm
        parent = j.find("parent").get("link")  # type: ignore[union-attr]
        child = j.find("child").get("link")  # type: ignore[union-attr]
        by_parent[parent] = UrdfJoint(j.get("name", ""), parent, child, T, axis / np.linalg.norm(axis))
    chain: list[UrdfJoint] = []
    link = "base_link"
    while link in by_parent:
        chain.append(by_parent[link])
        link = chain[-1].child
    return tuple(chain)


@lru_cache(maxsize=4)
def load_robot(root: Path | None = None) -> Robot:
    """Laedt den Roboter aus `third_party/doosan_m1013/urdf/m1013.white.urdf`.

    Die Gelenkkette kommt aus der URDF, die Grenzen aus `robots/doosan_m1013.json`
    (`joint_limits_rad`, bereits Steuerungskonvention; der restliche `kinematics`-Block ist
    alte DH-Konvention und wird nicht benutzt).
    """
    root = REPO_ROOT if root is None else Path(root)
    joints = _parse_urdf_chain(root / URDF_PATH)
    if len(joints) != 6:
        raise ValueError(f"URDF-Kette hat {len(joints)} Drehgelenke, erwartet 6")
    data = json.loads((root / ROBOT_JSON_PATH).read_text("utf-8"))
    limits = np.array(data["kinematics"]["joint_limits_rad"], dtype=float)
    return Robot(root / URDF_PATH, joints, limits, JOINT_VEL_LIMITS.copy())


# --- A1.2: Werkzeug und Workstation (Pydantic-Modelle) -----------------------------------------
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402


def _asset_root(root: Path | None) -> Path:
    return Path(root) if root is not None else Path(__file__).resolve().parents[3]


class Frame(BaseModel):
    """Pose in mm und Quaternion (w, x, y, z); Matrix siehe `roboprint.frames`."""

    model_config = ConfigDict(extra="ignore")
    pos_mm: tuple[float, float, float]
    quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)


class Channel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str
    description: str = ""
    default_value: float = 0.0


class Tool(BaseModel):
    """Werkzeug aus `tools/<name>.json`: TCP relativ zum Flansch F, Mesh, Kanaele."""

    model_config = ConfigDict(extra="ignore")
    name: str
    tcp_frame: Frame
    weight_kg: float = 0.0
    channels: dict[str, Channel] = Field(default_factory=dict)
    mesh: str | None = None
    mesh_transform: Frame | None = None


class Workstation(BaseModel):
    """Workstation aus `workstations/<name>.json` (Frames W, B, S siehe SPEC §2)."""

    model_config = ConfigDict(extra="ignore")
    name: str
    mobility: str = "stationary"
    safety_min_distance_mm: float = 50.0
    compatible_robots: list[str] = Field(default_factory=list)
    mesh: str | None = None
    robot_base_frame: Frame
    work_surface_frame: Frame


def load_tool(root: Path | None = None, name: str = "30gut") -> Tool:
    """Laedt das Werkzeug aus `tools/30gut.json`."""
    import json

    return Tool.model_validate(json.loads((_asset_root(root) / "tools" / f"{name}.json").read_text("utf-8")))


def load_workstation(root: Path | None = None, name: str = "doosantisch") -> Workstation:
    """Laedt die Workstation aus `workstations/doosantisch.json`."""
    import json

    path = _asset_root(root) / "workstations" / f"{name}.json"
    return Workstation.model_validate(json.loads(path.read_text("utf-8")))


def tool_mesh_path(tool: Tool, root: Path | None = None) -> Path | None:
    return None if tool.mesh is None else _asset_root(root) / "tools" / tool.mesh


def workstation_mesh_path(ws: Workstation, root: Path | None = None) -> Path | None:
    return None if ws.mesh is None else _asset_root(root) / "workstations" / ws.mesh
