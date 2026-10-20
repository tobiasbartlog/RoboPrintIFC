"""Booleans und Schnitte (manifold3d / trimesh). Alle Laengen in mm, Meshes sind `trimesh.Trimesh`.

Booleans laufen ueber manifold3d und liefern wieder wasserdichte Meshes (Summe der Teilvolumina
beim Zerschneiden = Ausgangsvolumen). Eingaben werden vorher mit `ensure_watertight` repariert.
"""

from __future__ import annotations

from typing import Any

import manifold3d as mf
import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

# --------------------------------------------------------------------------- Aufbau und Reparatur


def make_box(size: Any, origin: Any = (0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    """Quader mit Kantenlaengen `size` (sx, sy, sz); min-Ecke bei `origin`."""
    size = np.asarray(size, dtype=float)
    if np.any(size <= 0):
        raise ValueError(f"Boxmasse muessen positiv sein: {size}")
    box = trimesh.creation.box(extents=size)
    box.apply_translation(np.asarray(origin, dtype=float) + size / 2.0)
    return box


def is_empty(mesh: trimesh.Trimesh) -> bool:
    return mesh is None or len(mesh.faces) == 0


def ensure_watertight(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Liefert eine wasserdichte Kopie (Vertices verschweissen, Entartete entfernen, Normalen,
    Loecher fuellen). Gelingt das nicht, wird die Huelle ueber manifold3d neu aufgebaut; bleibt
    das Mesh dann nicht wasserdicht, gibt es `ValueError`."""
    m = mesh.copy()
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    if not m.is_watertight:
        trimesh.repair.fill_holes(m)
    if m.is_watertight:
        trimesh.repair.fix_normals(m)
        if m.volume < 0:
            m.invert()
        return m
    man = _to_manifold(m)
    if man.status() == mf.Error.NoError and not man.is_empty():
        return _from_manifold(man)
    raise ValueError("Mesh laesst sich nicht wasserdicht machen")


def _to_manifold(mesh: trimesh.Trimesh) -> mf.Manifold:
    m = mf.Mesh(
        vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
        tri_verts=np.asarray(mesh.faces, dtype=np.uint32),
    )
    return mf.Manifold(m)


SIMPLIFY_TOL_MM = 1e-3


def _from_manifold(man: mf.Manifold) -> trimesh.Trimesh:
    # simplify entfernt Slivers und kollineare Vertices, die bei koplanaren Schnitten entstehen
    # (z. B. Schnittebene exakt auf der Fenstersturzlinie) und trimesh sonst als offen meldet.
    out = man.simplify(SIMPLIFY_TOL_MM).to_mesh()
    verts = np.asarray(out.vert_properties, dtype=float)[:, :3]
    return trimesh.Trimesh(verts, np.asarray(out.tri_verts), process=True)


def _manifold_of(mesh: trimesh.Trimesh) -> mf.Manifold:
    man = _to_manifold(mesh)
    if man.status() != mf.Error.NoError:
        man = _to_manifold(ensure_watertight(mesh))
    return man


# --------------------------------------------------------------------------- Booleans


def cut_box(mesh: trimesh.Trimesh, box_min: Any, box_max: Any) -> trimesh.Trimesh:
    """Schnitt von `mesh` mit dem achsparallelen Quader [box_min, box_max]. Leeres Ergebnis ist
    ein Mesh ohne Flaechen (`is_empty`)."""
    lo = np.asarray(box_min, dtype=float)
    hi = np.asarray(box_max, dtype=float)
    if np.any(hi <= lo):
        raise ValueError(f"Leere Box: {lo} .. {hi}")
    cutter = mf.Manifold.cube(tuple(hi - lo)).translate(tuple(lo))
    res = _manifold_of(mesh) ^ cutter
    return trimesh.Trimesh() if res.is_empty() else _from_manifold(res)


def clip_below(mesh: trimesh.Trimesh, z: float) -> trimesh.Trimesh:
    """Teil von `mesh` mit z <= `z` (Druckstand: bereits gedrucktes Material), mit Deckflaeche."""
    res = _manifold_of(mesh).trim_by_plane((0.0, 0.0, -1.0), -float(z))
    return trimesh.Trimesh() if res.is_empty() else _from_manifold(res)


def union(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    res = mf.Manifold.batch_boolean([_manifold_of(m) for m in meshes], mf.OpType.Add)
    return trimesh.Trimesh() if res.is_empty() else _from_manifold(res)


def volume(mesh: trimesh.Trimesh) -> float:
    """Volumen in mm^3 (0 fuer leere Meshes)."""
    return 0.0 if is_empty(mesh) else float(abs(mesh.volume))


def intersection_volume(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    """Volumen der Schnittmenge zweier Meshes in mm^3."""
    if is_empty(a) or is_empty(b):
        return 0.0
    return float((_manifold_of(a) ^ _manifold_of(b)).volume())


def overlaps(a: trimesh.Trimesh, b: trimesh.Trimesh, tol_mm3: float = 1e-3) -> bool:
    """True, wenn sich die Koerper um mehr als `tol_mm3` durchdringen (Beruehren zaehlt nicht)."""
    return intersection_volume(a, b) > tol_mm3


# --------------------------------------------------------------------------- Schnitte


def slice_section(mesh: trimesh.Trimesh, z: float) -> Polygon | MultiPolygon:
    """Horizontaler Schnitt bei Hoehe `z` als shapely-(Multi)Polygon in XY (Loecher inklusive).
    Leerer Schnitt: leeres Polygon. `z` besser nicht exakt auf eine Flaeche legen (Schichtmitte)."""
    if is_empty(mesh):
        return Polygon()
    lo, hi = mesh.bounds[:, 2]
    if z < lo or z > hi:
        return Polygon()
    path = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
    if path is None:
        return Polygon()
    shift = np.eye(4)
    shift[2, 3] = -z  # Ebene nach z = 0, XY bleibt unveraendert
    p2, _ = path.to_2D(to_2D=shift)
    polys = list(p2.polygons_full)
    if not polys:
        return Polygon()
    geom = unary_union(polys)
    if geom.geom_type == "Polygon":
        return geom
    return MultiPolygon([g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"])
