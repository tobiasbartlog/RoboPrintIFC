"""Kollisions-Geometrie je Glied (ADR-024 Nachtrag, Issue #125).

Validiert das eingecheckte Derivat unter ``robots/collision/doosan_m1013/``
(Manifest + Provenienz), die additive Katalog-Referenz, die Ladefunktion und die
beiden geometrischen Eigenschaften aus dem Spike: Urteilsgeometrie (VHACD)
formtreu ±5,5 mm zum Roh-Mesh und Breitphasen-Hülle ⊇ Roh-Mesh (untere
Distanz-Schranke). Vergleichsposen kommen aus der DH-FK (``link_frames``).
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pytest
import trimesh

from fgc.collision import robot_geometry as rg
from fgc.collision.robot_geometry import load_robot_collision_geometry
from fgc.domain import validate
from fgc.domain.robot import RobotDef
from fgc.kinematics.opw import _START, OpwKinematics, _quat_to_rot
from fgc.paths import REPO_ROOT, ROBOTS_DIR

ROBOT = "doosan_m1013"
COLLISION_DIR = ROBOTS_DIR / "collision" / ROBOT
CATALOG = ROBOTS_DIR / f"{ROBOT}.json"
UPSTREAM_COMMIT = "ec9242546ec6202835900dbcd8498e2daabfa6a6"

# Das Konvertierskript (core/scripts) trägt die eine Roh-Mesh-Quelle (URDF-<collision>).
sys.path.insert(0, str(REPO_ROOT / "core" / "scripts"))
import convert_robot_collision as conv  # noqa: E402


def _manifest() -> dict:
    return json.loads((COLLISION_DIR / rg.MANIFEST_NAME).read_text(encoding="utf-8"))


def _frame_mat(frame) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = _quat_to_rot(frame.quat)
    t[:3, 3] = frame.pos_mm
    return t


def _dh_frame(index: int) -> np.ndarray:
    """DH-Gliedframe in der bekannten Pose ``_START`` (aufrecht, Issue #53)."""
    kin = OpwKinematics.from_robot(ROBOT)
    return _frame_mat(kin.link_frames(list(_START))[index])


def _raw_link_meshes() -> dict[int, trimesh.Trimesh]:
    """Roh-Kollisionsmeshes je Glied aus dem URDF (im DH-Gliedframe, mm)."""
    joint_origin_mm, _ = conv.crm._parse_urdf(conv.crm.URDF_PATH)
    offsets = conv.crm._link_offsets_mm(joint_origin_mm)
    entries = conv._parse_collision_entries(conv.crm.URDF_PATH)
    return {
        i: conv._raw_link_mesh(entries[name], offsets[i])
        for i, name in enumerate(conv.crm.LINK_ORDER)
    }


# --- Manifest + Provenienz ---------------------------------------------------


def test_manifest_complete_and_provenance() -> None:
    m = _manifest()
    assert m["robot"] == ROBOT
    assert m["units"] == "mm"
    assert m["upstream"]["commit"] == UPSTREAM_COMMIT
    assert "doosan-robot2" in m["upstream"]["repo"]
    assert m["upstream"]["license"], "Lizenzhinweis fehlt"
    # VHACD-Parameter als Provenienz mitgeschrieben, Determinismus erzwungen:
    assert m["vhacd_params"]["asyncACD"] is False
    assert m["vhacd_params"] == rg.VHACD_PARAMS

    links = m["links"]
    assert [ln["index"] for ln in links] == list(range(7)), "Basis + link1…6 erwartet"
    for ln in links:
        f = COLLISION_DIR / ln["file"]
        assert f.exists() and f.stat().st_size > 0, f"Geometrie fehlt/leer: {ln['file']}"
        assert ln["broadphase_faces"] > 0 and ln["judgment_parts"] > 0


# --- Additive Katalog-Referenz ----------------------------------------------


def test_catalog_reference_is_additive() -> None:
    """Katalog referenziert das Artefakt; Bestand ohne Referenz lädt unverändert."""
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert raw["collision_geometry"] == f"collision/{ROBOT}"
    validate(raw, "robot")  # mit Referenz schema-valide

    without = dict(raw)
    del without["collision_geometry"]
    validate(without, "robot")  # ohne Referenz weiterhin schema-valide (additiv)

    # RobotDef ignoriert das Feld: Bestand lädt byte-gleich (unveränderte Semantik).
    r = RobotDef.load(ROBOT)
    assert r.name == ROBOT and r.reach_mm == raw["reach_mm"]


def test_collision_dir_resolves_from_catalog() -> None:
    assert rg.collision_dir(ROBOT) == COLLISION_DIR


def test_missing_reference_is_friendly(tmp_path) -> None:
    (tmp_path / f"{ROBOT}.json").write_text(json.dumps({"name": ROBOT}), encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="collision_geometry"):
        rg.collision_dir(ROBOT, robots_dir=tmp_path)


# --- Ladefunktion ------------------------------------------------------------


def test_load_returns_broadphase_and_judgment_per_link() -> None:
    geo = load_robot_collision_geometry(ROBOT)
    assert geo.robot == ROBOT
    assert [lk.index for lk in geo.links] == list(range(7))
    for lk in geo.links:
        assert isinstance(lk.broadphase_hull, trimesh.Trimesh)
        assert len(lk.broadphase_hull.faces) > 0
        assert len(lk.judgment_parts) >= 1
        for part in lk.judgment_parts:
            assert isinstance(part, trimesh.Trimesh) and len(part.faces) > 0


# --- Eigenschaft: Hülle ⊇ Roh-Mesh (untere Distanz-Schranke) -----------------


def test_broadphase_hull_contains_raw_mesh() -> None:
    """Jeder Roh-Vertex liegt in der Breitphasen-Hülle → Hüllen-Distanz ≤ echte."""
    geo = load_robot_collision_geometry(ROBOT)
    raws = _raw_link_meshes()
    for lk in geo.links:
        raw = raws[lk.index]
        sd = trimesh.proximity.ProximityQuery(lk.broadphase_hull).signed_distance(raw.vertices)
        # +inside/−außen; nur Rundung (3 Dezimalen) darf minimal nach außen ragen.
        assert sd.min() >= -0.1, f"Glied {lk.index}: Roh-Vertex {sd.min():.3f} mm außerhalb"


# --- Eigenschaft: VHACD formtreu ±5,5 mm an bekannten Posen ------------------


@pytest.mark.parametrize("index", [2, 5])
def test_vhacd_shape_fidelity_at_known_pose(index: int) -> None:
    """VHACD-Union deckt das Roh-Mesh in der Pose ``_START`` bis auf ±5,5 mm ab."""
    geo = load_robot_collision_geometry(ROBOT)
    raw = _raw_link_meshes()[index].copy()
    pose = _dh_frame(index)
    raw.apply_transform(pose)

    pieces = []
    for part in geo.link(index).judgment_parts:
        p = part.copy()
        p.apply_transform(pose)
        pieces.append(trimesh.proximity.ProximityQuery(p))

    pts, _ = trimesh.sample.sample_surface(raw, 2000, seed=0)
    best = np.full(len(pts), -1e9)
    for pq in pieces:
        best = np.maximum(best, pq.signed_distance(pts))  # +inside eines Stücks
    outside = np.clip(-best, 0.0, None)  # Abstand nach außen, 0 wenn abgedeckt

    p99 = float(np.percentile(outside, 99))
    assert p99 <= rg.VHACD_TOLERANCE_MM, f"Glied {index}: p99 {p99:.2f} mm > Toleranz"
    # Vereinzelte scharfe Ecken dürfen knapp darüber; harter Deckel gegen Ausreißer.
    assert float(outside.max()) <= 8.0, f"Glied {index}: max {outside.max():.2f} mm zu groß"


# --- Determinismus der reinen Zerlegung -------------------------------------


@pytest.mark.skipif(
    sys.platform != "win32",
    reason=(
        "VHACD-Bytes sind plattformabhängig; das eingecheckte base.json ist ein "
        "Windows-Artefakt. Determinismus wird AUF einer Plattform garantiert (byte-"
        "gleich), plattformübergreifend bewusst nicht behauptet — daher nur dort "
        "geprüft, wo das Artefakt erzeugt wurde. S. Design-Log 2026-07-10."
    ),
)
def test_decompose_link_is_deterministic_matches_artifact() -> None:
    """Frische Zerlegung der Basis == eingecheckte Datei (rein + deterministisch).

    Byte-Gleichheit gilt nur auf der Herkunftsplattform des Artefakts (Windows);
    die VHACD-Konvexzerlegung ist über Plattformen hinweg nicht reproduzierbar.
    """
    raw = _raw_link_meshes()[0]
    fresh = rg.decompose_link(raw.vertices, raw.faces)
    stored = json.loads((COLLISION_DIR / "base.json").read_text(encoding="utf-8"))
    assert fresh["broadphase"]["faces"] == stored["broadphase"]["faces"]
    assert fresh["broadphase"]["vertices_mm"] == stored["broadphase"]["vertices_mm"]
    assert len(fresh["judgment"]) == len(stored["judgment"])
    for a, b in zip(fresh["judgment"], stored["judgment"], strict=True):
        assert a["vertices_mm"] == b["vertices_mm"] and a["faces"] == b["faces"]


# --- Geo-Extras fehlen: freundlicher Fehlpfad statt Import-Crash -------------


def test_module_imports_without_geo_at_top_level() -> None:
    # trimesh/vhacdx werden lazy geladen — nicht auf Modulebene (Core startet geo-frei).
    assert not hasattr(rg, "trimesh")
    assert not hasattr(rg, "vhacdx")


def test_require_geo_gives_friendly_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "trimesh", None)  # simuliert fehlendes Extra
    with pytest.raises(ImportError, match=r"fgc-core\[geo\]"):
        rg._require_geo()
