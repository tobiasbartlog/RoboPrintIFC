"""Konvertiert die URDF-``<collision>``-Meshes des M1013 ins Kollisions-Derivat.

Gegenstück zu ``convert_robot_meshes.py`` (Viewer-GLBs), aber core-only für die
**Kollisionskontrolle** (ADR-024 Nachtrag 2026-07-08, Issue #125): je Glied
(Basis + link1…6) entstehen deterministisch

- die **Breitphasen-Hülle** (konvexe Hülle, untere Distanz-Schranke) und
- die **Urteilsgeometrie** (VHACD-Konvexzerlegung, formtreu ±5,5 mm),

Vertices im DH-Gliedframe (``worldV = frames[i]·v``, **dieselbe Offset-Formel
wie das GLB-Skript — importiert, nicht kopiert**). Ablage als core-eigenes
Derivat unter ``robots/collision/<robot>/`` plus ``manifest.json`` mit Provenienz
(Upstream-Commit, VHACD-Parameter). Referenziert additiv im Roboterkatalog.

Deterministisch: feste Glied-/Datei-Reihenfolge, ``asyncACD=False``, gerundete
Vertices, sortierte JSON-Keys, keine Zeitstempel — zweifacher Lauf → bitgleich.

Neu erzeugen (Repo-Root, venv mit ``fgc-core[geo]``):

    .venv/Scripts/python.exe core/scripts/convert_robot_collision.py
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh

# Offset-Formel + URDF-Parsing des GLB-Skripts wiederverwenden (nicht kopieren).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_robot_meshes as crm  # noqa: E402

from fgc.collision import robot_geometry as rg  # noqa: E402
from fgc.paths import ROBOTS_DIR  # noqa: E402

ROBOT = crm.ROBOT
#: Relativ zu robots/ — genau die Referenz, die im Katalog steht.
COLLISION_REF = f"collision/{ROBOT}"
OUT_DIR = ROBOTS_DIR / COLLISION_REF

LINK_FILES = ["base.json"] + [f"link{i}.json" for i in range(1, 7)]


def _parse_collision_entries(urdf_path: Path):
    """Wie ``crm._parse_urdf``, aber für die ``<collision>``-Meshes je Glied."""
    root = ET.parse(urdf_path).getroot()
    links = {ln.get("name"): ln for ln in root.findall("link")}
    out: dict[str, list[tuple[Path, np.ndarray, float]]] = {}
    for name in crm.LINK_ORDER:
        entries: list[tuple[Path, np.ndarray, float]] = []
        for coll in links[name].findall("collision"):
            origin_mm = crm._origin_matrix_mm(coll.find("origin"))
            mesh_el = coll.find("geometry/mesh")
            if mesh_el is None:
                continue
            filename = mesh_el.get("filename", "")
            assert filename.startswith(crm.MESH_PACKAGE_PREFIX), filename
            rel = filename[len(crm.MESH_PACKAGE_PREFIX) :]
            scale = 1.0
            if mesh_el.get("scale"):
                sx, sy, sz = (float(v) for v in mesh_el.get("scale").split())
                assert sx == sy == sz, f"Nicht-uniforme Skalierung: {mesh_el.get('scale')}"
                scale = sx
            entries.append((crm.MESH_ROOT / rel, origin_mm, scale))
        out[name] = entries
    return out


def _raw_link_mesh(
    entries: list[tuple[Path, np.ndarray, float]], offset_mm: np.ndarray
) -> trimesh.Trimesh:
    """Kollisionsmeshes eines Glieds im DH-Gliedframe zusammenfügen (mm)."""
    parts: list[trimesh.Trimesh] = []
    for mesh_path, origin_mm, scale in entries:
        mesh = trimesh.load(mesh_path, force="mesh", process=False)
        mesh.apply_scale(scale * crm.MM_PER_M)  # DAE-mm · scale·1000 = mm-Faktor
        mesh.apply_transform(origin_mm)
        parts.append(mesh)
    merged = trimesh.util.concatenate(parts)
    merged.apply_transform(offset_mm)
    return merged


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    joint_origin_mm, _ = crm._parse_urdf(crm.URDF_PATH)
    offsets = crm._link_offsets_mm(joint_origin_mm)  # dieselbe Formel wie das GLB-Skript
    coll_entries = _parse_collision_entries(crm.URDF_PATH)

    links_manifest = []
    for i, name in enumerate(crm.LINK_ORDER):
        raw = _raw_link_mesh(coll_entries[name], offsets[i])
        result = rg.decompose_link(raw.vertices, raw.faces)  # reine, deterministische Zerlegung

        payload = {"broadphase": result["broadphase"], "judgment": result["judgment"]}
        (OUT_DIR / LINK_FILES[i]).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        hull_verts = np.asarray(result["broadphase"]["vertices_mm"], dtype=float)
        bounds = np.round(
            np.vstack([hull_verts.min(axis=0), hull_verts.max(axis=0)]), 3
        ).tolist()
        links_manifest.append(
            {
                "index": i,
                "urdf_link": name,
                "file": LINK_FILES[i],
                "broadphase_faces": len(result["broadphase"]["faces"]),
                "judgment_parts": len(result["judgment"]),
                "judgment_faces_total": int(sum(len(p["faces"]) for p in result["judgment"])),
                "bounds_mm": bounds,
            }
        )
        print(
            f"  Glied {i} ({name}) -> {LINK_FILES[i]}: "
            f"Hülle {links_manifest[-1]['broadphase_faces']} Faces, "
            f"{links_manifest[-1]['judgment_parts']} VHACD-Stücke"
        )

    manifest = {
        "_comment": "Erzeugt von core/scripts/convert_robot_collision.py — nicht editieren.",
        "robot": ROBOT,
        "units": "mm",
        "frame_convention": (
            "Vertices je Glied im DH-Gliedframe (worldV = frames[i]·v), dieselbe "
            "Offset-Formel wie convert_robot_meshes.py (Issue #53, importiert)."
        ),
        "geometry_roles": {
            "broadphase": "konvexe Hülle je Glied — untere Distanz-Schranke (Hülle ⊇ Roh-Mesh)",
            "judgment": (
                "VHACD-Konvexzerlegung je Glied — Urteilsgeometrie, formtreu "
                f"±{rg.VHACD_TOLERANCE_MM} mm (Spike S0)"
            ),
        },
        "vhacd_params": rg.VHACD_PARAMS,
        "round_decimals": rg.ROUND_DECIMALS,
        "generator": "core/scripts/convert_robot_collision.py",
        "source_meshes": "third_party/doosan_m1013/meshes/m1013_collision (URDF <collision>)",
        "upstream": {
            "repo": crm.UPSTREAM_REPO,
            "commit": crm.UPSTREAM_COMMIT,
            "license": crm.LICENSE_NOTE,
        },
        "links": links_manifest,
    }
    (OUT_DIR / rg.MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"{OUT_DIR / rg.MANIFEST_NAME} geschrieben: {len(links_manifest)} Glieder.")


if __name__ == "__main__":
    main()
