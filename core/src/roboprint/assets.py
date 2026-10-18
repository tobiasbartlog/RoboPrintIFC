"""Roboter (URDF), Werkzeug, Workstation und Prozessparameter laden (SPEC §4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_robot(root: Path | None = None) -> Any:
    """Laedt den Roboter aus `third_party/doosan_m1013/urdf/m1013.white.urdf`."""
    raise NotImplementedError


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
