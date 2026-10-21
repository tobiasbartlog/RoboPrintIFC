"""Pydantic-Modelle der Laufordner-Artefakte (SPEC §6, spec/ARTEFAKTE.md)."""

from __future__ import annotations

import math
from typing import Annotated

from pydantic import Field, model_validator

from ._types import (
    ArtifactModel,
    ContractModel,
    Joints6,
    Kind,
    LayerOrder,
    Mat4,
    ParamValue,
    PartStatus,
    PatternParamValue,
    Pose7,
    RingKind,
    Status,
    Vec3,
)

# --------------------------------------------------------------------------- summary


class WallEntry(ContractModel):
    wall_id: str
    name: str
    eligible: bool
    reason: str | None
    length_mm: float
    thickness_mm: float
    height_mm: float
    volume_mm3: float
    part_ids: list[str] = Field(default_factory=list)


class PartEntry(ContractModel):
    part_id: str
    wall_id: str
    status: PartStatus
    d_min_mm: float | None
    n_collision: int = Field(ge=0)
    n_unreachable: int = Field(ge=0)
    # Kopie eines gleichen Teils (gleiche Geometrie und Platzierung): part_id des Repraesentanten,
    # dessen Planung und dichte Pruefung fuer diese Kopie gilt (SPEC §5.4/5); sonst null.
    same_as: str | None = None


class Provenance(ContractModel):
    git_commit: str | None
    created: str
    command: str


class Summary(ArtifactModel):
    scenario_id: str
    scenario_path: str
    params: dict[str, ParamValue]
    assumptions: list[str]
    walls: list[WallEntry]
    parts: list[PartEntry]
    timings_s: dict[str, float]
    provenance: Provenance


# --------------------------------------------------------------------------- scene


class SceneRobot(ContractModel):
    urdf: str


class SceneWorkstation(ContractModel):
    mesh: str
    T_WB: Mat4
    T_WS: Mat4


class SceneTool(ContractModel):
    mesh: str
    T_FT: Mat4
    mesh_transform: Mat4


class SceneParams(ContractModel):
    d_hard_mm: float
    d_target_mm: float
    d_target_printed_mm: float
    r_free_mm: float
    layer_height_mm: float


class Scene(ArtifactModel):
    robot: SceneRobot
    workstation: SceneWorkstation
    tool: SceneTool
    params: SceneParams


# --------------------------------------------------------------------------- part


class Placement(ContractModel):
    x_mm: float
    y_mm: float
    yaw_deg: float


class BBox(ContractModel):
    min: Vec3
    max: Vec3


class Cause(ContractModel):
    sample: int = Field(ge=0)
    t_s: float
    link: str
    obstacle: str
    message: str


class PartArtifact(ArtifactModel):
    part_id: str
    wall_id: str
    T_LP: Mat4
    T_SP: Mat4
    T_WP: Mat4
    placement: Placement
    bbox_P: BBox
    volume_mm3: float
    n_layers: int = Field(ge=0)
    status: PartStatus
    cause: Cause | None


# --------------------------------------------------------------------------- toolpath


class Ring(ContractModel):
    layer: int = Field(ge=0)
    shell: int = Field(ge=0)
    kind: RingKind
    # true: geschlossener Ring (letzter Wegpunkt == erster); false: offenes Segment eines Musters
    # (docs/muster/ARTEFAKT-FORMAT.md), Anfang und Ende beliebig
    closed: bool
    # Verbinder zum Ring mit dem naechsthoeheren Index erlaubt (SPEC §5.3)
    link_next: bool = False
    waypoints: list[Pose7]

    @model_validator(mode="after")
    def _closed_ring(self) -> Ring:
        if not self.closed and len(self.waypoints) < 2:
            raise ValueError("offenes Segment braucht mindestens 2 Wegpunkte")
        if self.closed:
            if len(self.waypoints) < 2:
                raise ValueError("geschlossener Ring braucht mindestens 2 Wegpunkte")
            first, last = self.waypoints[0], self.waypoints[-1]
            if any(not math.isclose(a, b, abs_tol=1e-6) for a, b in zip(first, last, strict=True)):
                raise ValueError("geschlossener Ring: letzter Wegpunkt muss dem ersten gleichen")
        return self


class ToolpathPattern(ContractModel):
    """Druckmuster eines Teils (opt-in, docs/muster/ARTEFAKT-FORMAT.md); nur zur Beschriftung."""

    layer_order: LayerOrder
    infill: str
    outfill: str
    params: dict[str, PatternParamValue] = Field(default_factory=dict)
    # Hinweise des Plans (Infill entfällt, Rückfall auf Schalen, Insel ohne Strang …); fehlt ohne Hinweis
    notes: list[str] = Field(default_factory=list, exclude_if=lambda v: not v)


class Toolpath(ArtifactModel):
    part_id: str
    layer_height_mm: float
    bead_width_mm: float
    rings: list[Ring]
    # Nur bei Teilen mit Muster; fehlt sonst ganz in der Datei (ohne Muster bitgleich zu vorher)
    pattern: ToolpathPattern | None = Field(default=None, exclude_if=lambda v: v is None)


# --------------------------------------------------------------------------- trajectory


class TrajectorySummary(ContractModel):
    n: int = Field(ge=0)
    n_ok: int = Field(ge=0)
    n_warn: int = Field(ge=0)
    n_collision: int = Field(ge=0)
    n_unreachable: int = Field(ge=0)
    d_min_mm: float | None
    dauer_s: float
    zweig_wechsel_in_ringen: int = Field(ge=0)


Pair = Annotated[list[str], Field(min_length=2, max_length=2)]
Witness = Annotated[list[Vec3], Field(min_length=2, max_length=2)]

_PARALLEL = ("q", "tcp", "layer", "ring", "kind", "branch", "status", "d_mm", "pair", "witness", "psi_rad")


class Trajectory(ArtifactModel):
    part_id: str
    t_s: list[float]
    q: list[Joints6]
    tcp: list[Pose7]
    layer: list[int]
    ring: list[int]
    kind: list[Kind]
    branch: list[int]
    status: list[Status]
    d_mm: list[float | None]
    pair: list[Pair | None]
    witness: list[Witness | None]
    psi_rad: list[float]
    summary: TrajectorySummary

    @model_validator(mode="after")
    def _consistent(self) -> Trajectory:
        n = len(self.t_s)
        bad = {k: len(getattr(self, k)) for k in _PARALLEL if len(getattr(self, k)) != n}
        if bad:
            raise ValueError(f"Arrays müssen die Länge N={n} von t_s haben, abweichend: {bad}")
        for i in range(1, n):
            if not self.t_s[i] > self.t_s[i - 1]:
                raise ValueError(f"t_s nicht streng monoton bei Index {i}")
        for i, st in enumerate(self.status):
            unreachable = st == "unreachable"
            nulls = self.d_mm[i] is None and self.pair[i] is None and self.witness[i] is None
            if unreachable and not nulls:
                raise ValueError(f"Sample {i}: unreachable braucht d_mm, pair, witness = null")
            if not unreachable and self.d_mm[i] is None:
                raise ValueError(f"Sample {i}: d_mm fehlt bei Status {st}")
        s = self.summary
        c = {k: self.status.count(k) for k in ("ok", "warn", "collision", "unreachable")}
        expected = (n, c["ok"], c["warn"], c["collision"], c["unreachable"])
        got = (s.n, s.n_ok, s.n_warn, s.n_collision, s.n_unreachable)
        if got != expected:
            raise ValueError(f"summary (n, ok, warn, collision, unreachable) {got} != Arrays {expected}")
        return self
