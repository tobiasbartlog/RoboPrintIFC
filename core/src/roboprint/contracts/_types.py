"""Gemeinsame Typen und Basisklasse der Verträge."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

SCHEMA_VERSION = "2"
SCENARIO_SCHEMA_VERSION = "1"

Status = Literal["ok", "warn", "collision", "unreachable"]
Kind = Literal["print", "approach", "retract", "lift", "transfer", "lower"]
PartStatus = Literal["machbar", "nicht machbar"]
RingKind = Literal["outer", "inner", "hole"]
PlannerMode = Literal["collision_aware", "ignore_collision"]

Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Pose7 = Annotated[list[float], Field(min_length=7, max_length=7)]
Joints6 = Annotated[list[float], Field(min_length=6, max_length=6)]
ParamValue = float | str | bool


def _check_mat4(m: list[list[float]]) -> list[list[float]]:
    if len(m) != 4 or any(len(row) != 4 for row in m):
        raise ValueError("Matrix muss 4x4 sein")
    return m


Mat4 = Annotated[
    list[Annotated[list[float], Field(min_length=4, max_length=4)]],
    Field(min_length=4, max_length=4),
    AfterValidator(_check_mat4),
]


class ContractModel(BaseModel):
    """Basis: unbekannte Felder sind Fehler, NaN/Inf sind verboten."""

    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, json_schema_serialization_defaults_required=True
    )


class ArtifactModel(ContractModel):
    """Basis der Laufordner-Artefakte mit ``schema_version == "2"``."""

    schema_version: Literal["2"] = SCHEMA_VERSION  # type: ignore[assignment]
