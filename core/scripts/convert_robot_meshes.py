"""Konvertiert das vendorte Doosan-M1013-URDF-Modell in Viewer-GLBs je Glied.

Quelle der Wahrheit sind die Originale unter ``third_party/doosan_m1013/``
(URDF + DAE-Meshes, gepinnter Upstream-Commit; siehe ``UPSTREAM.md``). Dieses
Skript ist das eine, wiederholbare Derivat-Werkzeug (Design-Log 2026-07-05
„M1013-Meshes"): pro Glied (Basis + link1…6) genau ein GLB unter
``viewer/public/robots/m1013/`` plus ein ``manifest.json``. Kein Blender/assimp,
kein Draco — nur trimesh (+ pycollada für DAE).

**Was ins GLB eingebacken wird** (damit der Viewer schlicht
``mesh.matrix = frames[i]`` setzt, ohne eine zweite Zahlenquelle):

1. **Meter→mm-Skalierung.** Die DAE-Meshes tragen ihre Zahlen in Millimeter,
   das URDF skaliert sie per ``<mesh scale="0.001">`` nach Meter. Der Viewer
   rechnet in Millimeter (ADR-006), also ist der effektive Vertex-Faktor
   ``urdf_scale · 1000`` (= 1 bei scale 0.001) — konsequent aus dem
   URDF-Attribut abgeleitet statt geraten.
2. **Konstanter Link-Offset URDF-Linkframe ↔ DH-Gliedframe.** Beide Frames
   sitzen starr am selben Glied, unterscheiden sich also nur um eine feste
   Transformation. Die muss aber an einem **korrespondierenden Posenpaar**
   berechnet werden — URDF-Null (aufrecht, Doosan-Konvention) und DH-Null
   (seitlich abgeknickt) sind *nicht* dieselbe physische Pose (Issue #53)!
   Numerisch verifiziert gilt ``q_urdf_i = q_dh_i − _START_i`` (alle
   Vorzeichen +1) mit ``_START = (0, π/2, π/2, 0, 0, π)`` und dem
   Basiswechsel ``B = Rz(π)`` (URDF-Basis → DH-Basis). Also:

       offset_i = dhFrame_i(_START)^-1 · Rz(π) · urdfFrame_i(0)

   mit ``dhFrame_i`` = ``OpwKinematics.link_frames`` (DH aus
   ``robots/doosan_m1013.json`` — die *einzige* Kinematik-Wahrheit, spiegelt
   der Viewer per Golden-Orakel) und ``urdfFrame_i`` = Vorwärtskette der
   URDF-Gelenkursprünge. Der GLB-Vertex wird zu
   ``offset_i · visual_origin_i · vertex_mm`` — dann gilt für jede Pose
   ``worldVertex = frames[i] · glbVertex`` (Restfehler ≤ 0.4 mm aus den auf
   drei Dezimalen gerundeten rpy-Werten des Vendor-URDF).

Alles wird in **Millimeter** gerechnet; das Ergebnis wird in die Vertices
gebacken (ein Mesh je GLB, Identitäts-Node), damit die Darstellung nicht davon
abhängt, wie der glTF-Loader Node-Hierarchie/Skalierung behandelt.

Neu erzeugen (vom Repo-Root, venv; pycollada nötig — ``fgc-core[geo]``):

    .venv/Scripts/python.exe core/scripts/convert_robot_meshes.py

Deterministisch: feste Glied-/Datei-Reihenfolge, Vertices gerundet, keine
Zeitstempel im GLB.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh

from fgc.kinematics.opw import _START, OpwKinematics, _quat_to_rot

ROBOT = "doosan_m1013"
UPSTREAM_COMMIT = "ec9242546ec6202835900dbcd8498e2daabfa6a6"
UPSTREAM_REPO = "https://github.com/doosan-robotics/doosan-robot2"
LICENSE_NOTE = "BSD-3-Clause © Doosan Robotics Inc. — siehe third_party/doosan_m1013/LICENSE"

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIR = REPO_ROOT / "third_party" / "doosan_m1013"
URDF_PATH = VENDOR_DIR / "urdf" / "m1013.white.urdf"
# package://dsr_description2/meshes/... im URDF -> vendorte Meshes:
MESH_PACKAGE_PREFIX = "package://dsr_description2/meshes/"
MESH_ROOT = VENDOR_DIR / "meshes"

OUT_DIR = REPO_ROOT / "viewer" / "public" / "robots" / "m1013"

# Reihenfolge der Glieder: Basis + Achse 1…6 (7 Frames wie link_frames()).
LINK_ORDER = ["base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6"]
JOINT_ORDER = ["joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6"]

MM_PER_M = 1000.0


def _rpy_to_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """URDF-RPY (fixed-axis X-Y-Z) -> 3×3-Rotationsmatrix (Rz·Ry·Rx)."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def _origin_matrix_mm(elem: ET.Element | None) -> np.ndarray:
    """<origin xyz rpy> -> homogene 4×4 in mm (xyz aus Metern skaliert)."""
    t = np.eye(4)
    if elem is None:
        return t
    xyz = [float(v) for v in (elem.get("xyz") or "0 0 0").split()]
    rpy = [float(v) for v in (elem.get("rpy") or "0 0 0").split()]
    t[:3, :3] = _rpy_to_matrix(*rpy)
    t[:3, 3] = np.array(xyz) * MM_PER_M
    return t


def _frame_to_matrix_mm(frame) -> np.ndarray:
    """OpwKinematics-Frame (pos_mm, quat) -> homogene 4×4 in mm."""
    t = np.eye(4)
    t[:3, :3] = _quat_to_rot(frame.quat)
    t[:3, 3] = np.array(frame.pos_mm)
    return t


def _parse_urdf(urdf_path: Path):
    """Liest je Glied die Visual-Meshes (+ scale, origin) und je Gelenk den Ursprung."""
    root = ET.parse(urdf_path).getroot()

    joints = {j.get("name"): j for j in root.findall("joint")}
    joint_origin_mm: dict[str, np.ndarray] = {}
    for name in JOINT_ORDER:
        joint_origin_mm[name] = _origin_matrix_mm(joints[name].find("origin"))

    links = {ln.get("name"): ln for ln in root.findall("link")}
    visuals: dict[str, list[tuple[Path, np.ndarray, float]]] = {}
    for name in LINK_ORDER:
        entries: list[tuple[Path, np.ndarray, float]] = []
        for visual in links[name].findall("visual"):
            origin_mm = _origin_matrix_mm(visual.find("origin"))
            mesh_el = visual.find("geometry/mesh")
            if mesh_el is None:
                continue
            filename = mesh_el.get("filename", "")
            assert filename.startswith(MESH_PACKAGE_PREFIX), filename
            rel = filename[len(MESH_PACKAGE_PREFIX) :]
            scale = 1.0
            if mesh_el.get("scale"):
                sx, sy, sz = (float(v) for v in mesh_el.get("scale").split())
                assert sx == sy == sz, f"Nicht-uniforme Mesh-Skalierung: {mesh_el.get('scale')}"
                scale = sx
            entries.append((MESH_ROOT / rel, origin_mm, scale))
        visuals[name] = entries
    return joint_origin_mm, visuals


def _link_offsets_mm(joint_origin_mm: dict[str, np.ndarray]) -> list[np.ndarray]:
    """offset_i = dhFrame_i(_START)^-1 · Rz(π) · urdfFrame_i(0), je Glied (7 Stück).

    Korrespondierendes Posenpaar (Issue #53): die aufrechte Doosan-Nullstellung
    des URDF entspricht in der DH-Kette den Winkeln ``_START``; die Basen der
    beiden Konventionen sind um 180° um z gegeneinander verdreht.
    """
    kin = OpwKinematics.from_robot(ROBOT)
    dh_frames = [_frame_to_matrix_mm(f) for f in kin.link_frames(list(_START))]

    base_change = np.eye(4)
    base_change[:2, :2] = [[-1.0, 0.0], [0.0, -1.0]]  # Rz(π)

    urdf_frames = [np.eye(4)]
    acc = np.eye(4)
    for name in JOINT_ORDER:
        acc = acc @ joint_origin_mm[name]
        urdf_frames.append(acc.copy())

    return [np.linalg.inv(dh_frames[i]) @ base_change @ urdf_frames[i] for i in range(7)]


def _load_link_mesh(entries: list[tuple[Path, np.ndarray, float]]) -> trimesh.Trimesh:
    """Lädt + fügt die Visual-Meshes eines Glieds im Linkframe zusammen (mm)."""
    parts: list[trimesh.Trimesh] = []
    for mesh_path, origin_mm, scale in entries:
        mesh = trimesh.load(mesh_path, force="mesh", process=False)
        # DAE-Zahlen sind mm; scale·1000 = effektiver mm-Faktor (=1 bei 0.001).
        mesh.apply_scale(scale * MM_PER_M)
        mesh.apply_transform(origin_mm)
        parts.append(mesh)
    merged = trimesh.util.concatenate(parts)
    return merged


def _export_glb(mesh: trimesh.Trimesh, out_path: Path) -> None:
    """Deterministischer GLB-Export: ein Mesh, Identitäts-Node, keine Metadaten."""
    mesh.vertices = np.round(mesh.vertices, 6)
    # Materialien/Farben verwerfen — der Viewer schattiert selbst; hält GLB klein.
    clean = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
    scene = trimesh.Scene(clean)
    scene.metadata.clear()
    glb = trimesh.exchange.gltf.export_glb(scene, include_normals=True)
    out_path.write_bytes(glb)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    joint_origin_mm, visuals = _parse_urdf(URDF_PATH)
    offsets = _link_offsets_mm(joint_origin_mm)

    links_manifest = []
    for i, name in enumerate(LINK_ORDER):
        mesh = _load_link_mesh(visuals[name])
        mesh.apply_transform(offsets[i])
        filename = "base.glb" if i == 0 else f"link{i}.glb"
        _export_glb(mesh, OUT_DIR / filename)
        extents = np.round(mesh.bounds, 3).tolist()
        links_manifest.append(
            {
                "index": i,
                "urdf_link": name,
                "file": filename,
                "bounds_mm": extents,
            }
        )
        print(f"  Glied {i} ({name}) -> {filename}: {len(mesh.vertices)} Vertices")

    manifest = {
        "_comment": "Erzeugt von core/scripts/convert_robot_meshes.py — nicht von Hand editieren.",
        "robot": ROBOT,
        "units": "mm",
        "frame_convention": (
            "Vertices in Basiskoordinaten je Glied vor-transformiert; Viewer setzt "
            "mesh.matrix = frames[i] (DH-FK). Offset dhFrame_i(_START)^-1*Rz(pi)*"
            "urdfFrame_i(0) (korrespondierendes Posenpaar, Issue #53) und "
            "Meter->mm-Skalierung sind eingebacken."
        ),
        "upstream": {
            "repo": UPSTREAM_REPO,
            "commit": UPSTREAM_COMMIT,
            "license": LICENSE_NOTE,
        },
        "links": links_manifest,
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{OUT_DIR / 'manifest.json'} geschrieben: {len(links_manifest)} Glieder.")


if __name__ == "__main__":
    main()
