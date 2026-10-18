"""Smoke-Check der vendorten M1013-Viewer-GLBs (Issue #40).

Validiert die *eingecheckten* Artefakte unter ``viewer/public/robots/m1013/``
(nicht neu erzeugt — das Konvertierskript liest 15 MB DAE): Manifest-
Vollständigkeit, mm-Skala je Glied und die Größenordnung des zusammengesetzten
Roboters (Reichweite M1013 ~1300 mm). So fällt auf, wenn eine GLB fehlt, in
Meter statt Millimeter gerät oder der Offset die Kette zerreißt.
"""

from __future__ import annotations

import json

import numpy as np
import trimesh

from fgc.kinematics.opw import _START, OpwKinematics, _quat_to_rot
from fgc.paths import REPO_ROOT, VIEWER_DIR

MESH_DIR = VIEWER_DIR / "public" / "robots" / "m1013"
MANIFEST = MESH_DIR / "manifest.json"
UPSTREAM_COMMIT = "ec9242546ec6202835900dbcd8498e2daabfa6a6"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_complete() -> None:
    """7 Glieder (Basis + link1…6), alle Dateien vorhanden, Provenienz gesetzt."""
    m = _manifest()
    assert m["robot"] == "doosan_m1013"
    assert m["units"] == "mm"
    assert m["upstream"]["commit"] == UPSTREAM_COMMIT
    assert "doosan-robot2" in m["upstream"]["repo"]
    assert m["upstream"]["license"], "Lizenzhinweis fehlt im Manifest"

    links = m["links"]
    assert [ln["index"] for ln in links] == list(range(7)), "Basis + link1…6 erwartet"
    for ln in links:
        f = MESH_DIR / ln["file"]
        assert f.exists() and f.stat().st_size > 0, f"GLB fehlt/leer: {ln['file']}"


def test_glbs_draco_free_and_mm_scale() -> None:
    """Kein Draco-Extension-Marker; jedes Glied liegt in mm-Größenordnung."""
    for ln in _manifest()["links"]:
        data = (MESH_DIR / ln["file"]).read_bytes()
        assert b"KHR_draco_mesh_compression" not in data, f"Draco in {ln['file']}"
        mesh = trimesh.load(MESH_DIR / ln["file"], force="mesh")
        max_extent = float(mesh.extents.max())
        # In mm liegt jedes Glied zwischen ~1 cm und der Roboterhöhe; in Meter
        # wäre der größte Wert < 2 — das fängt eine verlorene Skalierung.
        assert 10.0 < max_extent < 1600.0, f"{ln['file']}: {max_extent} mm unplausibel"


def _dh_frames(joints: list[float]) -> list[np.ndarray]:
    kin = OpwKinematics.from_robot("doosan_m1013")

    def _mat(frame) -> np.ndarray:
        t = np.eye(4)
        t[:3, :3] = _quat_to_rot(frame.quat)
        t[:3, 3] = frame.pos_mm
        return t

    return [_mat(f) for f in kin.link_frames(joints)]


def test_assembled_upright_is_robot_scale() -> None:
    """In der aufrechten Pose (DH-Winkel ``_START``, Issue #53) steht der
    zusammengesetzte Arm ~1450 mm hoch auf dem Boden."""
    frames = _dh_frames(list(_START))
    pts = []
    for ln in _manifest()["links"]:
        mesh = trimesh.load(MESH_DIR / ln["file"], force="mesh")
        v = np.c_[mesh.vertices, np.ones(len(mesh.vertices))] @ frames[ln["index"]].T
        pts.append(v[:, :3])
    allpts = np.vstack(pts)
    zmin, zmax = float(allpts[:, 2].min()), float(allpts[:, 2].max())
    assert -50.0 < zmin < 50.0, f"Basis nicht am Boden: zmin={zmin} mm"
    assert 1300.0 < zmax < 1600.0, f"Aufrechte Höhe {zmax} mm unplausibel (M1013 ~1450)"


def test_flange_link_sits_on_dh_flange_frame() -> None:
    """Regression Issue #53: das link6-GLB muss lokal am Flansch-Ursprung liegen.

    Beim alten Baking (Offset aus URDF-Null ↔ DH-Null, zwei verschiedene
    physische Posen) lag das Flanschglied ~2 m neben seinem DH-Frame — der
    Endeffektor-Konfigurator zeigte Achsenkreuz/TCP/Mesh neben dem Arm.
    """
    mesh = trimesh.load(MESH_DIR / "link6.glb", force="mesh")
    center = np.asarray(mesh.bounds).mean(axis=0)
    dist = float(np.linalg.norm(center))
    assert dist < 150.0, f"link6 lokal {dist:.0f} mm vom Flansch-Ursprung entfernt"


def test_vendored_sources_present() -> None:
    """Die Quelle der Wahrheit (URDF + visual+collision Meshes + LICENSE) liegt im Repo."""
    vendor = REPO_ROOT / "third_party" / "doosan_m1013"
    assert (vendor / "urdf" / "m1013.white.urdf").exists()
    assert (vendor / "LICENSE").exists()
    assert (vendor / "UPSTREAM.md").exists()
    visual = list((vendor / "meshes" / "m1013_white").glob("*.dae"))
    collision = list((vendor / "meshes" / "m1013_collision").glob("*.dae"))
    assert len(visual) == 10, f"visual DAE unvollständig: {len(visual)}"
    assert len(collision) == 10, f"collision DAE unvollständig: {len(collision)}"
