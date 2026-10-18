"""fgc.slicer — planarer Slicer v0: Mesh -> zeitfreier Toolpath (ADR-005).

Drei austauschbare Stufen: sections (Schnitt) -> shells (Offsets) -> build
(Targets). Öffnungen sind außerhalb des v1-Scopes (OD-3), Löcher in
Schnittpolygonen werden aber bereits als eigene Ringe gedruckt.
"""

from __future__ import annotations

import numpy as np
import trimesh

from fgc.domain.models import Toolpath
from fgc.domain.process_params import SliceParams
from fgc.slicer.build import build_toolpath
from fgc.slicer.sections import LayerSection, section_layers
from fgc.slicer.shells import ShellRing, shell_rings

__all__ = [
    "LayerSection",
    "ShellRing",
    "SliceParams",
    "build_toolpath",
    "section_layers",
    "shell_rings",
    "slice_wall",
]


def slice_wall(
    vertices_mm: np.ndarray,
    faces: np.ndarray,
    wall_global_id: str,
    params: SliceParams,
) -> Toolpath:
    """Kompletter Slicer-Durchlauf für eine Wand."""
    mesh = trimesh.Trimesh(vertices=vertices_mm, faces=faces, process=False)
    layers = section_layers(mesh, params.layer_height_mm)
    return build_toolpath(wall_global_id, layers, params)
