"""Mesh-Teilung: ``apply(wand_mesh, schnittplan) → Abschnitts-Meshes`` (Issue #24).

Teilt ein Wand-Mesh entlang der Abschnittsgrenzen eines Zerlegungsvorschlags in
wasserdichte Teil-Meshes — je Abschnitt eines. Die Grenzen liegen im selben
Koordinatensystem wie das Mesh (Wand-lokal nach ADR-006: ``x`` entlang der
Laenge, zentriert um 0; ``z`` entlang der Hoehe ab Fuss 0; Millimeter).

Umgesetzt ueber `trimesh.Trimesh.slice_plane(..., cap=False)` je innerer
Abschnittsgrenze und anschliessendes **eigenes Deckeln** der planaren
Schnittflaeche mit shapely (Design-Log 2026-07-05): trimesh cap=True braucht eine
Triangulierungs-Engine (mapbox_earcut/triangle), die in dieser Umgebung nicht
installiert ist — shapely (bereits Abhaengigkeit ueber `geometry/section.py`)
liefert die planare Triangulierung. So bleiben die Teile wasserdicht und die
Volumensumme ergibt das Wandvolumen.

v1-Grenze: die shapely-Deckelung nimmt einfache (loch-freie) Schnittquerschnitte
an — fuer die achsparallelen Schnitte durch quaderfoermige Waende ist der
Querschnitt ein Rechteck. Oeffnungen in der Schnittebene sind eine spaetere
Verfeinerung (read-only v1, das Editieren/Slicen ist #25/#26).
"""

from __future__ import annotations

import numpy as np
import trimesh
from shapely.ops import polygonize, triangulate

from fgc.decompose.plan import DecompositionPlan

#: Toleranz (mm), unterhalb derer eine Grenze als Wandaussenkante gilt und nicht
#: geschnitten wird (unnoetiges Deckeln der ohnehin vorhandenen Aussenflaeche).
_EDGE_EPS_MM = 1e-3

#: Toleranz (mm) fuer „Kante liegt in der Schnittebene" beim Deckeln.
_PLANE_TOL_MM = 1e-3

#: Zu jeder Schnittachse die beiden Ebenen-Koordinatenachsen (fuers 2D-Deckeln).
_PLANE_AXES = {0: (1, 2), 1: (0, 2), 2: (0, 1)}


def _slice_keep(
    mesh: trimesh.Trimesh, origin: tuple[float, float, float], normal: tuple[float, float, float]
) -> trimesh.Trimesh:
    sliced = mesh.slice_plane(plane_origin=list(origin), plane_normal=list(normal), cap=False)
    if sliced is None or len(sliced.vertices) == 0:
        return trimesh.Trimesh()
    sliced.merge_vertices()
    return sliced


def _cap_plane(mesh: trimesh.Trimesh, axis: int, position: float) -> trimesh.Trimesh:
    """Deckelt die offene, in der Ebene ``axis = position`` liegende Schnittflaeche.

    Sammelt die offenen Randkanten (Kanten mit genau einer Nachbarflaeche), die in
    der Schnittebene liegen, baut daraus per shapely die Querschnittspolygone,
    trianguliert sie und haengt die Deckel-Dreiecke an. Ergebnis ist ein Mesh mit
    geschlossener Schnittflaeche (Wickelrichtung richtet `apply` am Ende).
    """
    if len(mesh.faces) == 0:
        return mesh
    edges = mesh.edges_sorted
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = uniq[counts == 1]
    verts = mesh.vertices
    a, b = _PLANE_AXES[axis]

    segments = []
    for e0, e1 in boundary:
        p0, p1 = verts[e0], verts[e1]
        if abs(p0[axis] - position) < _PLANE_TOL_MM and abs(p1[axis] - position) < _PLANE_TOL_MM:
            segments.append([(p0[a], p0[b]), (p1[a], p1[b])])
    if not segments:
        return mesh

    from shapely.geometry import LineString

    new_vertices = [np.asarray(v, dtype=float) for v in verts]
    new_faces = [list(f) for f in mesh.faces]
    for polygon in polygonize([LineString(s) for s in segments]):
        for tri in triangulate(polygon):
            if not polygon.contains(tri.representative_point()):
                continue
            face = []
            for u, v in list(tri.exterior.coords)[:3]:
                point = [0.0, 0.0, 0.0]
                point[axis] = position
                point[a] = u
                point[b] = v
                face.append(len(new_vertices))
                new_vertices.append(np.asarray(point, dtype=float))
            new_faces.append(face)

    capped = trimesh.Trimesh(
        vertices=np.asarray(new_vertices), faces=np.asarray(new_faces), process=True
    )
    return capped


def apply(wall_mesh: trimesh.Trimesh, plan: DecompositionPlan) -> list[trimesh.Trimesh]:
    """Teilt *wall_mesh* in ein wasserdichtes Teil-Mesh je Abschnitt (Issue #24).

    Fuer jeden Abschnitt wird das Mesh auf die Abschnitts-Box
    ``[x0, x1] x [z0, z1]`` (volle Wanddicke) zugeschnitten — aber nur an den
    *inneren* Grenzen (Schnittebenen); die Wandaussenkanten bleiben unberuehrt.
    Reihenfolge der Rueckgabe = Plan-Reihenfolge der Abschnitte.

    Ein einzelner Abschnitt ohne Schnitte liefert eine Kopie des ganzen Meshes
    (Volumensumme = Wandvolumen exakt).
    """
    x_min = -plan.wall.length_mm / 2.0
    x_max = plan.wall.length_mm / 2.0
    z_min = 0.0
    z_max = plan.wall.height_mm

    parts: list[trimesh.Trimesh] = []
    for section_plan in plan.sections:
        s = section_plan.section
        part = wall_mesh.copy()

        # (origin, normal, cap-axis, cap-position) je innerer Grenze.
        planes: list[tuple[tuple, tuple, int, float]] = []
        if s.x0_mm > x_min + _EDGE_EPS_MM:
            planes.append(((s.x0_mm, 0.0, 0.0), (1.0, 0.0, 0.0), 0, s.x0_mm))
        if s.x1_mm < x_max - _EDGE_EPS_MM:
            planes.append(((s.x1_mm, 0.0, 0.0), (-1.0, 0.0, 0.0), 0, s.x1_mm))
        if s.z0_mm > z_min + _EDGE_EPS_MM:
            planes.append(((0.0, 0.0, s.z0_mm), (0.0, 0.0, 1.0), 2, s.z0_mm))
        if s.z1_mm < z_max - _EDGE_EPS_MM:
            planes.append(((0.0, 0.0, s.z1_mm), (0.0, 0.0, -1.0), 2, s.z1_mm))

        for origin, normal, axis, position in planes:
            if len(part.vertices) == 0:
                break
            part = _slice_keep(part, origin, normal)
            part = _cap_plane(part, axis, position)

        if planes and len(part.vertices) > 0:
            trimesh.repair.fix_normals(part)
        parts.append(part)
    return parts


def total_volume(meshes: list[trimesh.Trimesh]) -> float:
    """Summe der (Betrags-)Volumina — fuer die Volumen-Kontrolle in Tests."""
    return float(np.sum([abs(m.volume) for m in meshes if len(m.vertices) > 0]))
