"""Laden, Schreiben und Schema-Export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .api import Example, Health, JobCreate, JobCreated, JobState, ProjectCreate, ProjectCreated, ProjectInfo
from .artifacts import PartArtifact, Scene, Summary, Toolpath, Trajectory
from .scenario import Scenario

M = TypeVar("M", bound=BaseModel)

#: Top-Level-Modelle, für die je ein ``<Name>.schema.json`` exportiert wird.
TOP_LEVEL_MODELS: tuple[type[BaseModel], ...] = (
    Summary, Scene, PartArtifact, Toolpath, Trajectory, Scenario,
    Health, Example, ProjectCreate, ProjectCreated, ProjectInfo, JobCreate, JobCreated, JobState,
)  # fmt: skip


def load_json[M: BaseModel](path: str | Path, model: type[M]) -> M:
    return model.model_validate_json(Path(path).read_bytes())


def dump_json(model: BaseModel, path: str | Path, indent: int | None = None) -> Path:
    """Schreibt das Modell vollständig (inkl. Defaults) als JSON mit Zeilenende ``\\n``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    separators = (",", ":") if indent is None else (",", ": ")
    text = json.dumps(model.model_dump(mode="json"), indent=indent, separators=separators, ensure_ascii=False)
    p.write_text(text + "\n", encoding="utf-8", newline="\n")
    return p


def _strip_property_titles(node: Any) -> None:
    """Entfernt die von pydantic erzeugten Feld-Titel, damit die TS-Generierung keine
    Alias-Typen je Feld erzeugt (nur Modelle behalten ihren ``title``)."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for sub in props.values():
                if isinstance(sub, dict):
                    sub.pop("title", None)
        for value in node.values():
            _strip_property_titles(value)
    elif isinstance(node, list):
        for value in node:
            _strip_property_titles(value)


def schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """JSON-Schema im Serialisierungsmodus: Felder mit Default sind Pflicht (die Ausgabe ist voll)."""
    schema = model.model_json_schema(mode="serialization")
    _strip_property_titles(schema)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    return schema


def export_schemas(out_dir: str | Path) -> list[Path]:
    """Schreibt ``<Name>.schema.json`` je Top-Level-Modell, deterministisch."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for model in TOP_LEVEL_MODELS:
        text = json.dumps(schema_for(model), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        p = out / f"{model.__name__}.schema.json"
        p.write_text(text, encoding="utf-8", newline="\n")
        written.append(p)
    return written
