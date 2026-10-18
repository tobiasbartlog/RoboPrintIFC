"""Geometrische Pruefungen fuer check_run: Schnitte, Abdeckung, Teilvolumen, Tisch, IFC-Waende.

Unabhaengig von roboprint: liest part.stl, die Workstation-STL und das IFC selbst.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
import trimesh
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from verify.oracle.collision_oracle import TABLE_STL

EMPTY = Polygon()


def section_P(mesh: trimesh.Trimesh, z: float):
    """Querschnitt eines Solids bei Hoehe z (Frame des Meshes) als shapely-(Multi)Polygon in xy."""
    try:
        sec = mesh.section(plane_origin=[0.0, 0.0, float(z)], plane_normal=[0.0, 0.0, 1.0])
    except Exception:  # noqa: BLE001 - trimesh wirft bei entarteten Schnitten
        sec = None
    if sec is None:
        return EMPTY
    T = np.eye(4)
    T[2, 3] = -float(z)
    planar, _ = sec.to_planar(to_2D=T, check=False)
    polys = [p for p in planar.polygons_full if p is not None and p.area > 0]
    if not polys:
        return EMPTY
    # even-odd ueber alle Polygone, falls verschachtelte Konturen getrennt geliefert werden
    region = EMPTY
    for p in polys:
        region = region.symmetric_difference(p)
    return shapely.make_valid(region)


def shell_region(section, shells: int, bead_w: float):
    if section.is_empty:
        return EMPTY
    return section.difference(section.buffer(-shells * bead_w, join_style="mitre"))


def coverage(section, polylines_xy: list[np.ndarray], shells: int, bead_w: float) -> tuple[float, float]:
    """(Abdeckungsanteil, Flaeche Schalenbereich) einer Schicht."""
    region = shell_region(section, shells, bead_w)
    area = float(region.area)
    if area <= 0:
        return 1.0, 0.0
    beads = [LineString(p).buffer(bead_w / 2.0) for p in polylines_xy if len(p) >= 2]
    if not beads:
        return 0.0, area
    covered = unary_union(beads).intersection(region).area
    return float(covered / area), area


@lru_cache(maxsize=1)
def table_top_outline(z_mm: float = 900.0):
    """Umriss der Tischplatte (W, xy) aus doosantisch.stl, knapp unter der Oberkante geschnitten."""
    table = trimesh.load(str(TABLE_STL), force="mesh")
    table.merge_vertices()
    parts = [b for b in table.split(only_watertight=False)]
    polys = []
    for b in parts:
        s = section_P(b, z_mm)
        if not s.is_empty:
            polys.append(s)
    return unary_union(polys) if polys else EMPTY


def footprint_xy(vertices_xy: np.ndarray):
    """Konvexe Huelle der Grundrissprojektion (Obermenge der Projektion)."""
    return shapely.convex_hull(shapely.MultiPoint(np.asarray(vertices_xy)[:, :2]))


def to_manifold(mesh: trimesh.Trimesh):
    import manifold3d as mf

    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                               tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))


def intersection_volume(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    lo = np.maximum(a.bounds[0], b.bounds[0])
    hi = np.minimum(a.bounds[1], b.bounds[1])
    if np.any(hi <= lo):
        return 0.0
    try:
        return float((to_manifold(a) ^ to_manifold(b)).volume())
    except Exception:  # noqa: BLE001
        return float(np.prod(hi - lo))  # konservativ: Bounding-Box-Ueberlappung


# --------------------------------------------------------------------------- IFC


def ifc_walls(path: Path) -> list[dict]:
    """Unabhaengige Vermessung aller IfcWall: Volumen (mm^3, mit Oeffnungen), Dicke, Hoehe,
    Unterkante, Oberkanten der Oeffnungen relativ zur Wandunterkante."""
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.placement as up

    f = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    out = []
    for w in f.by_type("IfcWall"):
        try:
            sh = ifcopenshell.geom.create_shape(settings, w)
        except Exception:  # noqa: BLE001 - Wand ohne Geometrie
            out.append({"global_id": w.GlobalId, "name": w.Name, "volume_mm3": None})
            continue
        v = np.array(sh.geometry.verts, dtype=float).reshape(-1, 3) * 1000.0
        fa = np.array(sh.geometry.faces, dtype=np.int64).reshape(-1, 3)
        m = trimesh.Trimesh(v, fa, process=True)
        M = np.array(up.get_local_placement(w.ObjectPlacement), dtype=float)
        ax = M[:3, 0].copy()
        ax[2] = 0.0
        ax = ax / np.linalg.norm(ax) if np.linalg.norm(ax) > 1e-9 else np.array([1.0, 0.0, 0.0])
        ay = np.cross([0.0, 0.0, 1.0], ax)
        ext_x = float(np.ptp(v @ ax))
        ext_y = float(np.ptp(v @ ay))
        z0, z1 = float(v[:, 2].min()), float(v[:, 2].max())
        lintels = []
        for rel in getattr(w, "HasOpenings", []) or []:
            op = rel.RelatedOpeningElement
            try:
                osh = ifcopenshell.geom.create_shape(settings, op)
            except Exception:  # noqa: BLE001
                continue
            ov = np.array(osh.geometry.verts, dtype=float).reshape(-1, 3) * 1000.0
            top = float(ov[:, 2].max())
            if top < z1 - 1.0:
                lintels.append(top - z0)
        out.append({
            "global_id": w.GlobalId, "name": w.Name, "volume_mm3": float(abs(m.volume)),
            "watertight": bool(m.is_watertight), "thickness_mm": min(ext_x, ext_y),
            "length_mm": max(ext_x, ext_y), "height_mm": z1 - z0, "lintels_mm": lintels,
        })
    return out
