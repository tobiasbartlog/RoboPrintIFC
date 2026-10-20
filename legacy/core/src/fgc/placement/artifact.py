"""Serialisierung des Bewertungslaufs (placement.json, Schema-Vertrag).

Baut das ``placement``-Artefakt aus reinen Platzierungs-Daten — analog
``candidates_artifact`` (domain/models.py). Traegt ``schema_version``, den
Provenienzblock (ADR-004) und die bewerteten Aufstellmoeglichkeiten samt Scores.
Die Bewertung ist reproduzierbar: gleiche Eingaben -> gleiches Artefakt.
"""

from __future__ import annotations

from typing import Any

from fgc.placement.evaluate import PlacementOption, PlacementScore, WallSurface


def placement_artifact(
    robot_name: str,
    tool_name: str,
    wall: WallSurface,
    results: list[tuple[PlacementOption, PlacementScore]],
    provenance: dict[str, Any],
    *,
    wall_global_id: str | None = None,
    selected: str | None = None,
    sampling: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Baut das placement.json-Artefakt (Issue #22, ADR-004)."""
    doc: dict[str, Any] = {
        "schema_version": "0.1",
        "provenance": provenance,
        "robot": robot_name,
        "tool": tool_name,
        "wall": {
            "length_mm": wall.length_mm,
            "height_mm": wall.height_mm,
            "thickness_mm": wall.thickness_mm,
        },
        "options": [
            {
                "option_id": opt.option_id,
                "lateral_mm": opt.lateral_mm,
                "standoff_mm": opt.standoff_mm,
                "stand_height_mm": opt.stand_height_mm,
                "yaw_rad": opt.yaw_rad,
                "score": score.to_dict(),
            }
            for opt, score in results
        ],
    }
    if wall_global_id is not None:
        doc["wall_global_id"] = wall_global_id
    if selected is not None:
        doc["selected"] = selected
    if sampling is not None:
        doc["sampling"] = sampling
    return doc
