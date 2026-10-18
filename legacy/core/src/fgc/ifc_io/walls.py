"""IFC-Import: Wände tessellieren und Metadaten extrahieren.

Tessellations-Settings nach Spike S2: USE_WORLD_COORDS, Default-Toleranzen.
ifcopenshell liefert Geometrie in Metern (SI) — hier ist die eine Stelle, an
der auf interne mm normiert wird (ADR-006).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import numpy as np

from fgc.ifc_io.analysis import WallGeometry, analyze_wall_mesh

M_TO_MM = 1000.0


@dataclass
class WallData:
    """Alles, was Eignungsprüfung und Slicer über eine Wand wissen müssen."""

    global_id: str
    name: str | None
    load_bearing: bool | None  # None = Pset_WallCommon.LoadBearing fehlt im Modell
    is_external: bool | None  # None = Pset_WallCommon.IsExternal fehlt im Modell
    opening_count: int
    vertices_mm: np.ndarray  # (n, 3)
    faces: np.ndarray  # (m, 3) int
    geometry: WallGeometry


def tessellation_settings() -> ifcopenshell.geom.settings:
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    return settings


def load_walls(ifc_path: str | Path) -> list[WallData]:
    """Lädt alle IfcWall-Instanzen (inkl. Subtypen) eines Modells."""
    model = ifcopenshell.open(str(ifc_path))
    settings = tessellation_settings()
    return [_extract(wall, settings) for wall in model.by_type("IfcWall")]


def load_wall(ifc_path: str | Path, global_id: str) -> WallData:
    """Lädt genau eine Wand über ihre GlobalId."""
    model = ifcopenshell.open(str(ifc_path))
    wall = model.by_guid(global_id)
    if wall is None or not wall.is_a("IfcWall"):
        raise KeyError(f"GlobalId {global_id!r} ist keine IfcWall in {ifc_path}")
    return _extract(wall, tessellation_settings())


def _extract(wall, settings) -> WallData:
    shape = ifcopenshell.geom.create_shape(settings, wall)
    vertices = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3) * M_TO_MM
    faces = np.array(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)

    psets = ifcopenshell.util.element.get_psets(wall)
    common = psets.get("Pset_WallCommon", {})
    load_bearing = common.get("LoadBearing")
    is_external = common.get("IsExternal")

    return WallData(
        global_id=wall.GlobalId,
        name=wall.Name,
        load_bearing=None if load_bearing is None else bool(load_bearing),
        is_external=None if is_external is None else bool(is_external),
        opening_count=len(getattr(wall, "HasOpenings", ()) or ()),
        vertices_mm=vertices,
        faces=faces,
        geometry=analyze_wall_mesh(vertices),
    )
