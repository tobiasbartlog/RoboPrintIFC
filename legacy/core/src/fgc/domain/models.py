"""Datentypen zu den Schema-Verträgen (schemas/*.schema.json).

Reine Datenklassen ohne Geometrie-Abhängigkeiten — jedes Pipeline-Modul spricht
mit den anderen nur über diese Typen bzw. die daraus serialisierten Artefakte
(ADR-004). Einheiten: Millimeter, Quaternionen [w, x, y, z] (ADR-006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TargetKind = Literal["print", "travel"]

#: Prüfnamen aus candidates.schema.json — Reihenfolge = Auswertereihenfolge E1-Stufe 1.
CHECK_NAMES = ("planarity", "load_bearing", "openings", "workspace", "thickness", "footprint")


@dataclass(frozen=True)
class Frame:
    """Pose: Position in mm + Einheitsquaternion [w, x, y, z] (ADR-006)."""

    pos_mm: tuple[float, float, float]
    quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {"pos_mm": list(self.pos_mm), "quat": list(self.quat)}


@dataclass
class Target:
    """Ein Bahnpunkt des Toolpath: zeitfrei, io als logische Kanäle (ADR-011)."""

    frame: Frame
    v_mm_s: float
    io: dict[str, float]
    kind: TargetKind
    layer: int
    segment_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame.to_dict(),
            "v_mm_s": self.v_mm_s,
            "io": dict(self.io),
            "kind": self.kind,
            "layer": self.layer,
            "segment_id": self.segment_id,
        }


@dataclass
class Toolpath:
    """Geometrische Druckanweisung, roboterunabhängig und zeitfrei."""

    wall_global_id: str
    targets: list[Target] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        """Vorberechnete Kennzahlen (Schicht-/Target-Zahlen) — genau eine Quelle.

        Der Core rechnet diese Zahlen einmal; Artefakt-Summary, CLI-Anzeige
        (report.slice_summary) und Viewer lesen sie nur, statt sie je erneut
        aus der Target-Liste abzuleiten (ADR-007: Viewer rechnet nichts).
        """
        return {
            "n_layers": max((t.layer for t in self.targets), default=-1) + 1,
            "n_targets": len(self.targets),
            "n_print": sum(1 for t in self.targets if t.kind == "print"),
        }

    def to_artifact(
        self,
        provenance: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Serialisiert den Toolpath als Artefakt-Dict.

        `params` = Slice-Parameter-Dict mit den Schlüsseln model_path,
        layer_height_mm, strand_width_mm, n_shells (Issue #9, ADR-014).
        Wird übergeben → schema_version 0.3 mit params-Block;
        ohne params → 0.2 (Rückwärtskompatibilität mit älteren Läufen).
        """
        version = "0.3" if params is not None else "0.2"
        artifact: dict[str, Any] = {
            "schema_version": version,
            "provenance": provenance,
            "wall_global_id": self.wall_global_id,
            "targets": [t.to_dict() for t in self.targets],
            "summary": self.summary(),
        }
        if params is not None:
            artifact["params"] = params
        return artifact


@dataclass
class CheckResult:
    """Ergebnis einer einzelnen Eignungsprüfung (ADR-013)."""

    check: str
    passed: bool
    provisional: bool = False
    reason: str | None = None
    deferred: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"check": self.check, "passed": self.passed}
        if self.provisional:
            doc["provisional"] = True
        if self.reason:
            doc["reason"] = self.reason
        if self.deferred is not None:
            doc["deferred"] = self.deferred
        return doc


@dataclass
class WallCandidate:
    """Eine Wand im candidates.json: Eignungsflags + Ablehnungsgründe."""

    global_id: str
    name: str | None
    eligible: bool
    dimensions_mm: dict[str, float]
    checks: list[CheckResult]

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "global_id": self.global_id,
            "eligible": self.eligible,
            "dimensions_mm": self.dimensions_mm,
            "checks": [c.to_dict() for c in self.checks],
        }
        if self.name:
            doc["name"] = self.name
        return doc

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def candidates_artifact(
    model: str, walls: list[WallCandidate], provenance: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "provenance": provenance,
        "model": model,
        "walls": [w.to_dict() for w in walls],
    }


#: Dateiname der binären Modell-glTF (GLB), die walls_to_run neben dem
#: model_map.json-Artefakt in den Lauf schreibt (Issue #6).
MODEL_GLB_FILE = "model.glb"


def wall_node_name(global_id: str) -> str:
    """Name des Szenenknotens einer Wand in model.glb — trägt die GlobalId.

    Die eine Stelle, die Knoten benennt: der GLB-Export (`geometry.gltf`) und
    das model_map-Artefakt greifen beide hierauf zu, damit Knotenname und
    Mapping garantiert übereinstimmen.
    """
    return f"wall_{global_id}"


def model_map_artifact(
    model: str,
    global_ids: list[str],
    provenance: dict[str, Any],
    *,
    mesh_file: str = MODEL_GLB_FILE,
) -> dict[str, Any]:
    """Baut das model_map-Artefakt: GlobalId-Zuordnung zur binären Modell-glTF.

    Die eigentliche Geometrie liegt binär in `mesh_file` (model.glb, ein
    Szenenknoten je Wand); dieses JSON-Artefakt bleibt schema-/provenienz-konform
    und bindet jeden Knotennamen an die GlobalId seiner IfcWall. Kein
    ifc_io-Import — analog zu wallspec_artifact, nimmt nur die GlobalIds.

    Zusammen mit candidates.json lädt der Viewer die GLB und färbt die Wände
    nach Eignung ein (ADR-007: der Viewer rechnet nichts selbst).
    """
    return {
        "schema_version": "0.1",
        "provenance": provenance,
        "model": model,
        "mesh_file": mesh_file,
        "walls": [
            {"node": wall_node_name(global_id), "global_id": global_id}
            for global_id in global_ids
        ],
    }


def wallspec_artifact(
    global_id: str,
    name: str | None,
    vertices_mm: Any,
    faces: Any,
    load_bearing: bool | None,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Baut das wallspec-Artefakt (Schema-Vertrag) aus reinen Wanddaten.

    Besitzt — analog `candidates_artifact` — `schema_version`, die
    Vertex-Rundung (mm, 3 Nachkommastellen) und den Feldaufbau, damit dieses
    Domänenwissen nicht in der Orchestrierung (`actions.slice_to_run`) liegt.
    `vertices_mm`/`faces` sind Sequenzen von 3er-Tupeln bzw. Index-Tripeln
    (auch NumPy-Arrays); Öffnungen sind ab v0.1 Vertragsbestandteil (OD-3),
    der Slicer behandelt sie in v1 noch nicht → leere Liste.
    """
    doc: dict[str, Any] = {
        "schema_version": "0.1",
        "provenance": provenance,
        "global_id": global_id,
        **({"name": name} if name else {}),
        "geometry": {
            "vertices_mm": [[round(float(x), 3) for x in v] for v in vertices_mm],
            "faces": [[int(i) for i in f] for f in faces],
        },
        "openings": [],
        "targets": {"load_bearing": bool(load_bearing)},
    }
    return doc
