"""Szenario-Format (SPEC §7, spec/scenarios/*.json)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ._types import (
    SCENARIO_SCHEMA_VERSION,
    ContractModel,
    PlannerMode,
    ScenarioParamValue,
    Vec3,
)


class BoxSource(ContractModel):
    kind: Literal["box"]
    size_mm: Vec3  # [Länge, Dicke, Höhe]


class IfcSource(ContractModel):
    kind: Literal["ifc"]
    path: str
    walls: Literal["all"] | list[str]


Source = Annotated[BoxSource | IfcSource, Field(discriminator="kind")]


class PlacementOverride(ContractModel):
    x_mm: float
    y_mm: float
    yaw_deg: float


class ScenarioLimits(ContractModel):
    wall_time_s: float


class Scenario(ContractModel):
    schema_version: Literal["1"] = SCENARIO_SCHEMA_VERSION  # type: ignore[assignment]
    id: str
    beschreibung: str
    mode: str
    source: Source
    decompose: bool
    robot: str
    urdf: str
    tool: str
    workstation: str
    # Prozessparameter (SPEC §10). Opt-in für Druckmuster: `pattern_params` als Objekt
    # (docs/muster/ARTEFAKT-FORMAT.md), alle übrigen Werte skalar
    params: dict[str, ScenarioParamValue]
    planner_mode: PlannerMode
    placement_override: PlacementOverride | None = None
    expect: dict[str, Any]
    limits: ScenarioLimits
