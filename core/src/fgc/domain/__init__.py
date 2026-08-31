"""fgc.domain — Datenverträge: Schema-Zugriff und Validierung.

Die JSON-Schemas in schemas/ sind die Single Source of Truth (P2, ADR-004).
Dieses Modul lädt und validiert Artefakte gegen sie; Datentypen folgen mit M0.
Einheiten intern: Millimeter, Radiant, Quaternionen (ADR-006).
"""

from __future__ import annotations

import json
from functools import cache
from typing import Any

import jsonschema
from referencing import Registry, Resource

from fgc.paths import SCHEMA_DIR

ARTIFACT_KINDS = (
    "wallspec", "toolpath", "trajectory", "setup", "candidates", "context", "model_map",
    "placement", "decompose",
)

#: Das Projekt (ADR-016) ist kein Lauf-Artefakt, sondern die langlebige
#: Persistenz-Einheit der GUI — aber ebenso ein schema-validierter Datenvertrag.
#: Es teilt Validierung und Registry mit den Artefakten (es referenziert z.B.
#: den provenance-$def aus setup.schema.json), zählt aber nicht zu den Artefakten
#: eines Laufs.
#: ``"tool"`` ist ebenfalls kein Lauf-Artefakt, sondern ein projektunabhängiges
#: Stammdaten-Artefakt analog zu ``robots/<name>.json`` (Issue #21, ADR-011).
#: ``"workstation"`` ist die Aufstell-Umgebung des Roboters als projektunabhängiges
#: Stammdaten-Artefakt (``workstations/<name>.json``, Issue #72, PRD #69).
#: ``"robot"`` ist die Roboterdefinition (``robots/<name>.json``, ADR-002); read-only
#: im #69-Scope, rein additiv validiert (Issue #73).
VALIDATABLE_KINDS = (*ARTIFACT_KINDS, "project", "tool", "workstation", "robot")


@cache
def load_schema(kind: str) -> dict[str, Any]:
    """Lädt das JSON-Schema für eine Artefaktart/Persistenz-Einheit (z.B. 'toolpath', 'project')."""
    if kind not in VALIDATABLE_KINDS:
        raise ValueError(f"Unbekannte Schema-Art {kind!r}, erwartet eine von {VALIDATABLE_KINDS}")
    path = SCHEMA_DIR / f"{kind}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def _registry() -> Registry:
    """Registry aller Schemas, damit schemaübergreifende $refs (z.B. frame,
    provenance aus setup.schema.json) aufgelöst werden."""
    resources = []
    for kind in VALIDATABLE_KINDS:
        schema = load_schema(kind)
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def validate(artifact: dict[str, Any], kind: str) -> None:
    """Validiert ein Artefakt gegen sein Schema; wirft jsonschema.ValidationError."""
    validator = jsonschema.Draft202012Validator(load_schema(kind), registry=_registry())
    validator.validate(artifact)
