"""API-Modelle (SPEC §8)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._types import ContractModel, ParamValue, PlannerMode
from .artifacts import WallEntry


class Health(ContractModel):
    status: Literal["ok"]
    version: str
    versions: dict[str, str]


class Example(ContractModel):
    id: str
    name: str
    kind: Literal["ifc", "scenario"]
    path: str
    description: str | None = None


class ProjectCreate(ContractModel):
    """Projekt aus Beispiel-Pfad (der Upload läuft als Multipart und hat kein JSON-Modell)."""

    example_path: str


class ProjectCreated(ContractModel):
    project_id: str


class ProjectInfo(ContractModel):
    project_id: str
    name: str
    walls: list[WallEntry]
    building_mm: list[float] | None = Field(
        default=None,
        description="Ausdehnung (x, y, z) der Hausansicht in mm; None ohne IFC-Gebäude (Quader-Beispiel)",
    )


class JobCreate(ContractModel):
    wall_id: str
    params: dict[str, ParamValue] = Field(default_factory=dict)
    planner_mode: PlannerMode = "collision_aware"


class JobCreated(ContractModel):
    job_id: str


class JobState(ContractModel):
    state: Literal["queued", "running", "done", "failed", "cancelled"]
    progress: float = Field(ge=0, le=1)
    stage: str | None
    message: str | None
    run_id: str | None
