"""IFC -> `Wall` in L (m -> mm, global -> lokal), Oeffnungen (SPEC §4, §2).

ifcopenshell liefert Meter in globalen Koordinaten. Hier ist die eine Stelle, an der auf mm
normiert und mit `frames.wall_frame_from_ifc` in den Wand-Frame L umgerechnet wird.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import trimesh

from roboprint import frames
from roboprint.geometry import ensure_watertight

M_TO_MM = 1000.0


@dataclass(frozen=True)
class Opening:
    """Oeffnung als Box in L (Wandebene x-z); z1 ist die Sturzlinie (Oberkante)."""

    x0: float
    x1: float
    z0: float
    z1: float


@dataclass
class Wall:
    """Eine IfcWall mit Geometrie in L (mm): x in [0, Laenge], y in [0, Dicke], z in [0, Hoehe]."""

    wall_id: str  # GlobalId
    name: str | None
    mesh: trimesh.Trimesh  # in L, wasserdicht
    length_mm: float
    thickness_mm: float
    height_mm: float
    volume_mm3: float
    T_GL: np.ndarray  # Pose von L im globalen IFC-Frame (mm)
    openings: list[Opening] = field(default_factory=list)


def eligibility(wall: Wall, bead_width_mm: float) -> tuple[bool, str | None]:
    """Eignung (SPEC §5.4/1): Dicke >= 2 * Strangbreite, sonst Begruendung."""
    need = 2.0 * bead_width_mm
    if wall.thickness_mm + 1e-6 >= need:
        return True, None
    return False, (
        f"Wand zu dünn: {wall.thickness_mm:.1f} mm < {need:.1f} mm (2 × Strangbreite {bead_width_mm:g} mm)"
    )


def _settings() -> ifcopenshell.geom.settings:
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    return s


def _shape_mesh_mm(settings, element) -> trimesh.Trimesh | None:
    """Tessellierte Geometrie eines IFC-Produkts in globalen Koordinaten, mm."""
    if getattr(element, "Representation", None) is None:
        return None
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
    except RuntimeError:
        return None
    verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3) * M_TO_MM
    faces = np.array(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
    if len(faces) == 0:
        return None
    return trimesh.Trimesh(verts, faces, process=False)


def _x_hint(element) -> np.ndarray | None:
    """X-Achse der IFC-Platzierung in G (nur fuer das Vorzeichen von X_L)."""
    try:
        import ifcopenshell.util.placement as pl

        return np.asarray(pl.get_local_placement(element.ObjectPlacement))[:3, 0]
    except Exception:  # noqa: BLE001 - Hinweis ist optional
        return None


def _openings_in_L(settings, element, T_LG: np.ndarray, length: float, height: float) -> list[Opening]:  # noqa: N803
    out: list[Opening] = []
    for rel in getattr(element, "HasOpenings", ()) or ():
        m = _shape_mesh_mm(settings, rel.RelatedOpeningElement)
        if m is None:
            continue
        b = frames.transform_points(T_LG, m.vertices)
        lo, hi = b.min(axis=0), b.max(axis=0)
        x0, x1 = max(lo[0], 0.0), min(hi[0], length)
        z0, z1 = max(lo[2], 0.0), min(hi[2], height)
        if x1 - x0 > 1e-3 and z1 - z0 > 1e-3:
            out.append(Opening(float(x0), float(x1), float(z0), float(z1)))
    return sorted(out, key=lambda o: (o.x0, o.z0))


def read_walls(path: Path | str) -> list[Wall]:
    """Liest alle IfcWall (inkl. Subtypen) mit Koerpergeometrie als `Wall` im Wand-Frame L."""
    model = ifcopenshell.open(str(path))
    settings = _settings()
    walls: list[Wall] = []
    for el in model.by_type("IfcWall"):
        g = _shape_mesh_mm(settings, el)
        if g is None:
            continue
        T_GL = frames.wall_frame_from_ifc(g.vertices, _x_hint(el))  # noqa: N806
        T_LG = frames.invert(T_GL)  # noqa: N806
        mesh = trimesh.Trimesh(frames.transform_points(T_LG, g.vertices), g.faces, process=True)
        mesh = ensure_watertight(mesh)
        mesh.vertices[np.abs(mesh.vertices) < 1e-6] = 0.0  # Rundungsrauschen an der min-Ecke
        length, thickness, height = (float(v) for v in mesh.bounds[1] - mesh.bounds[0])
        walls.append(
            Wall(
                wall_id=el.GlobalId,
                name=el.Name,
                mesh=mesh,
                length_mm=length,
                thickness_mm=thickness,
                height_mm=height,
                volume_mm3=float(abs(mesh.volume)),
                T_GL=T_GL,
                openings=_openings_in_L(settings, el, T_LG, length, height),
            )
        )
    return walls
