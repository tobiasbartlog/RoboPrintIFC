"""Spike S2 — prueft ADR-005: IFC-Tessellation -> trimesh, geschlossene/konsistent orientierte Schnittkonturen?

Wegwerf-Skript, kein Teil der Produktionspipeline. Aufruf:
    python docs/spikes/s2_scripts/tessellate_check.py examples/Building-Architecture.ifc
"""
import sys

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import trimesh


def tessellate_wall(wall, settings):
    shape = ifcopenshell.geom.create_shape(settings, wall)
    verts = np.array(shape.geometry.verts).reshape(-1, 3)
    faces = np.array(shape.geometry.faces).reshape(-1, 3)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def check_wall(wall, settings):
    mesh = tessellate_wall(wall, settings)
    print(f"\n=== {wall.GlobalId}  {wall.Name} ===")
    print(f"  vertices={len(mesh.vertices)} faces={len(mesh.faces)}")
    print(f"  watertight={mesh.is_watertight}  winding_consistent={mesh.is_winding_consistent}")
    print(f"  bounds z: {mesh.bounds[0][2]:.3f} .. {mesh.bounds[1][2]:.3f}")

    z_min, z_max = mesh.bounds[0][2], mesh.bounds[1][2]
    heights = np.linspace(z_min + 0.05 * (z_max - z_min), z_max - 0.05 * (z_max - z_min), 3)

    for h in heights:
        section = mesh.section(plane_origin=[0, 0, h], plane_normal=[0, 0, 1])
        if section is None:
            print(f"  h={h:.3f}: KEIN Schnitt (Ebene trifft Mesh nicht)")
            continue
        planar, _ = section.to_2D()
        polygons = planar.polygons_full
        n_holes = sum(len(p.interiors) for p in polygons)
        closed = all(p.is_valid and p.exterior.is_ring for p in polygons)
        ccw = [p.exterior.is_ccw for p in polygons]
        print(f"  h={h:.3f}: {len(polygons)} Polygon(e), geschlossen={closed}, "
              f"CCW je Polygon={ccw}, Loecher_gesamt={n_holes}")


def main(ifc_path):
    model = ifcopenshell.open(ifc_path)
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    walls = model.by_type("IfcWall")
    print(f"Modell: {ifc_path}  Schema: {model.schema}  Waende: {len(walls)}")

    for wall in walls:
        check_wall(wall, settings)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "examples/Building-Architecture.ifc")
