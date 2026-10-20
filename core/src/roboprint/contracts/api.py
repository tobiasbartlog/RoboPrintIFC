"""API-Modelle (SPEC §8)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field

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


# --------------------------------------------------------------------------- Druckmuster (2D-Vorschau)
# Verträge des Mustererstellers (docs/muster/AUFTRAG.md, Nachtrag 18:20). Die Geometrie rechnet
# `roboprint.patterns`; die Modelle spiegeln `patterns.preview` und `patterns.catalog` 1:1 (ein Test
# prüft, dass die Vorschau jedes registrierten Musters validiert). Koordinaten Frame P, mm, nur XY.

Point2 = Annotated[list[float], Field(min_length=2, max_length=2)]
PatternParamValue = bool | int | float | str | list[int] | list[float]
SegmentKind = Literal["outer", "inner", "hole", "infill", "web", "outfill"]
ContactKind = Literal["joint", "node", "shell"]


class PatternOutlineBox(ContractModel):
    """Rechteckiger Querschnitt, Ursprung in der Mitte (x ∈ [−L/2, L/2], y ∈ [−d/2, d/2])."""

    length_mm: float = Field(gt=0, le=20000)
    thickness_mm: float = Field(gt=0, le=2000)


class PatternOutlinePolygon(ContractModel):
    """Beliebiger Querschnitt als Polygon (Frame P, mm) mit optionalen Löchern."""

    polygon: list[Point2] = Field(min_length=3)
    holes: list[list[Point2]] = Field(default_factory=list)


class PatternPreviewRequest(ContractModel):
    """Body von `POST /api/patterns/preview`.

    `pattern`: registrierter Mustername oder `schalen`/`none`; ist es keins von beiden, gilt es als
    Preset-id. `preset`: Preset-id als Grundlage (Muster, Parameter, Querschnitt); `pattern`,
    `params` und `outline` überschreiben es. `params` ist flach: Kern- und Musterparameter
    nebeneinander. Ohne `outline` gilt das Preset-`outline`, sonst 600 × 200 mm."""

    pattern: str | None = None
    preset: str | None = None
    params: dict[str, PatternParamValue | None] = Field(default_factory=dict)
    outline: PatternOutlineBox | PatternOutlinePolygon | None = None
    layer: int = Field(default=0, ge=0, le=10000)


class PatternArrow(ContractModel):
    at: Point2
    dir: Point2


class PatternSegment(ContractModel):
    index: int
    kind: SegmentKind
    shell: int
    label: str
    closed: bool
    points: list[Point2]
    start: Point2
    end: Point2
    start_dir: Point2
    end_dir: Point2
    length_mm: float
    arrows: list[PatternArrow]


class PatternConnector(ContractModel):
    """Gerader Verbinder zwischen zwei Segmenten (Länge 0, wenn sie aneinanderstoßen)."""

    model_config = ConfigDict(populate_by_name=True)

    from_: Point2 = Field(alias="from")
    to: Point2
    length_mm: float


class PatternContact(ContractModel):
    """Kontaktzone (Fuge, Knoten, Steg an Schale); `overlap_mm` = w − Mittellinienabstand."""

    kind: ContactKind
    at: Point2
    length_mm: float
    segments: list[int]
    distance_mm: float | None
    overlap_mm: float | None = None


class PatternPath(ContractModel):
    """Ein Strang einer Schicht und Insel, Segmente in Druckreihenfolge."""

    layer: int
    island: int
    direction: Literal["out_in", "in_out"]
    restart: bool
    closed: bool
    start: Point2
    end: Point2
    segments: list[PatternSegment]
    connectors: list[PatternConnector]
    length_mm: float
    meta: dict[str, Any]
    declared_contacts: list[PatternContact]


class PatternNextLayer(ContractModel):
    layer: int
    paths: list[PatternPath]


class PatternLayerChange(ContractModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: int = Field(alias="from")
    to: int
    distance_mm: float
    status: Literal["vertical", "restart", "diagonal"]


class PatternViolation(ContractModel):
    """Verstoß gegen M1–M7: `error` macht das Muster ungültig, `warn` ist eine Zielverfehlung."""

    rule: str
    severity: Literal["error", "warn"]
    layer: int | None
    island: int | None
    at: Point2 | None
    value: float | None
    limit: float | None
    message: str


class PatternCell(ContractModel):
    area_mm2: float
    span_mm: float
    at: Point2


class PatternContactSum(ContractModel):
    count: int
    length_mm: float


class PatternPathMetrics(ContractModel):
    layer: int
    island: int
    direction: str
    path_length_mm: float | None
    print_time_s: float | None
    n_segments: int
    connectors_mm: list[float | None]
    min_clearance_mm: float | None
    min_radius_mm: float | None
    max_chord_error_mm: float | None
    shell_coverage: float = Field(description="Abdeckung des Schalenbereichs, 0..1 (Maß wie G3)")
    contacts: int
    contacts_by_kind: dict[str, PatternContactSum]
    contact_length_mm: float | None
    contacts_per_m: float | None
    contact_lengths_mm: list[float | None]
    longest_straight_outer_mm: float | None
    longest_straight_outer_at: Point2 | None
    joint_x_mm: list[float | None]
    joint_spacing_mm: list[float | None]
    cells: list[PatternCell]
    n_cells: int
    max_cell_area_mm2: float | None
    max_cell_span_mm: float | None
    material_l_per_m_layer: float | None
    material_l_per_m2: float | None
    start: Point2
    end: Point2


class PatternMetrics(ContractModel):
    """Kennzahlen der Schicht (Summe über alle Inseln) und je Insel (`paths`)."""

    path_length_mm: float
    print_time_s: float
    v_print_mm_s: float
    strands: int
    material_l_per_m_layer: float
    material_l_per_m2: float
    contacts: int
    contact_length_mm: float
    contacts_per_m: float
    joint_spacing_mm: list[float | None]
    longest_straight_outer_mm: float | None
    min_radius_mm: float | None
    min_clearance_mm: float | None
    shell_coverage: float = Field(description="kleinste Abdeckung des Schalenbereichs über alle Inseln, 0..1")
    cells: list[PatternCell]
    paths: list[PatternPathMetrics]


class PatternFit(ContractModel):
    """Ergebnis von `fit_to_length` aus den Musterdaten: tatsächliche Feldzahl und Feldlänge."""

    island: int
    key: str = Field(description="Ort in `meta` des Pfads, z. B. `fit` oder `fit_back`")
    count: int
    length_mm: float
    total_mm: float
    target_mm: float
    deviation_mm: float
    positions_mm: list[float]


class PatternResolved(ContractModel):
    full: str | None
    outfill: str | None
    infill: str | None


class PatternSelection(ContractModel):
    infill: str
    outfill: str
    layer_order: Literal["same", "alternate"]
    resolved: PatternResolved


class PatternOutlinePolygonOut(ContractModel):
    exterior: list[Point2]
    holes: list[list[Point2]]


class PatternOutlineOut(ContractModel):
    polygons: list[PatternOutlinePolygonOut]
    bounds: Annotated[list[float], Field(min_length=4, max_length=4)]


class PatternTiming(ContractModel):
    plan: float
    measure: float
    total: float
    api: float | None = Field(default=None, description="Gesamtzeit der Anfrage im Server (ms)")


class PatternPreview(ContractModel):
    """Antwort von `POST /api/patterns/preview`: Schicht `layer` und Folgeschicht (blass)."""

    schema_version: int
    name: str | None
    layer: int
    pattern: PatternSelection
    params: dict[str, PatternParamValue | None]
    outline: PatternOutlineOut
    paths: list[PatternPath]
    next_layer: PatternNextLayer
    layer_change: PatternLayerChange | None
    contacts: list[PatternContact]
    violations: list[PatternViolation]
    ok: bool
    metrics: PatternMetrics
    fit: list[PatternFit] = Field(default_factory=list)
    timing_ms: PatternTiming


class PatternParamSpec(ContractModel):
    """Regler eines Parameters (deutsche Beschriftung, Bereich, Art)."""

    name: str
    label: str
    default: PatternParamValue | None
    unit: str
    minimum: float | None
    maximum: float | None
    step: float | None
    kind: Literal["float", "int", "choice", "bool"]
    choices: list[str | int | float]
    help: str


class PatternInfo(ContractModel):
    name: str
    role: Literal["full", "outfill", "infill"]
    label: str
    description: str
    family: str
    layer_invariant: bool
    params: list[PatternParamSpec]


class PatternPreset(ContractModel):
    """Benanntes Muster (Preset-Datei, Schema siehe `roboprint.patterns.preview`)."""

    schema_version: int = 1
    name: str = Field(min_length=1, max_length=120)
    pattern: str
    params: dict[str, PatternParamValue | None] = Field(default_factory=dict)
    outline: PatternOutlineBox | PatternOutlinePolygon | None = None
    description: str = ""


class PatternPresetCreate(ContractModel):
    """Body von `POST /api/patterns/presets`. Ohne `id` wird sie aus dem Namen gebildet. Eine
    eigene Vorlage mit derselben id wird überschrieben, eine mitgelieferte nie (409)."""

    id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=120)
    pattern: str
    params: dict[str, PatternParamValue | None] = Field(default_factory=dict)
    outline: PatternOutlineBox | PatternOutlinePolygon | None = None
    description: str = ""


class PatternPresetEntry(ContractModel):
    id: str
    source: Literal["builtin", "user"]
    preset: PatternPreset


class PatternCatalog(ContractModel):
    """Antwort von `GET /api/patterns`: Kernregler, alle Muster mit Reglern, gespeicherte Presets."""

    core_params: list[PatternParamSpec]
    base_patterns: list[str]
    patterns: list[PatternInfo]
    presets: list[PatternPresetEntry]
