"""Glied-SDF (PRD #183 AP 1, Issue #207): Konservativität, Provenienz, Laden.

Externes Verhalten, keine Implementierungsdetails (Testing Decisions #183):

- **Ground Truth gegen FCL** an gesampelten Konfigurationen: die SDF-Distanz
  überschätzt die FCL-Distanz zur selben Urteilsgeometrie **nie** (Kernvertrag);
  eine Schranken-Gegenprobe verhindert, dass „konservativ" zu „beliebig klein"
  degeneriert.
- **Provenienz-Fehlpfade (US 18):** falscher Roboter, veraltete Auflösung,
  veralteter Buildstand der Quellgeometrie und fehlendes Artefakt schlagen klar
  fehl.
- Manifest-/Artefakt-Vollständigkeit (US 17), Batch-Form der Abfrage, analytische
  Konservativität am synthetischen Würfel, geo-freier Modul-Import.
"""

from __future__ import annotations

import json
import shutil
import sys

import fcl
import numpy as np
import pytest
import trimesh

from fgc.collision import glied_sdf as gs
from fgc.collision import robot_geometry as rg
from fgc.collision.check import matrix
from fgc.collision.glied_sdf import (
    GliedSdf,
    LinkSdf,
    SdfProvenanceError,
    build_link_field,
    interpolation_band_mm,
    load_glied_sdf,
)
from fgc.kinematics.opw import OpwKinematics
from fgc.paths import ROBOTS_DIR

ROBOT = "doosan_m1013"
SDF_DIR = ROBOTS_DIR / "collision" / ROBOT / gs.SDF_DIR_NAME

#: Toleranz der Konservativitäts-Asserts (mm): Sphären-Radius der FCL-Sonde
#: plus numerisches Epsilon — deutlich unter dem Interpolationsband (~6,9 mm).
SPHERE_R = 0.5
CONS_EPS = 1e-6

pytestmark = pytest.mark.skipif(not SDF_DIR.exists(), reason="Glied-SDF-Artefakt fehlt")


@pytest.fixture(scope="module")
def glied_sdf() -> GliedSdf:
    return load_glied_sdf(ROBOT)


@pytest.fixture(scope="module")
def collision_geo() -> rg.RobotCollisionGeometry:
    return rg.load_robot_collision_geometry(ROBOT)


def _manifest() -> dict:
    return json.loads((SDF_DIR / gs.SDF_MANIFEST_NAME).read_text(encoding="utf-8"))


# --- Manifest + Provenienz vollständig (US 17) --------------------------------


def test_manifest_provenance_complete() -> None:
    m = _manifest()
    assert m["robot"] == ROBOT
    assert m["units"] == "mm"
    assert m["sdf_format_version"] == gs.SDF_FORMAT_VERSION
    assert m["voxel_mm"] == gs.DEFAULT_VOXEL_MM
    assert m["generator"] == "core/scripts/build_glied_sdf.py"
    # Buildstand: Fingerabdruck der Quellgeometrie (#125-Derivat) + Upstream-Kette.
    fp = m["source_files_sha256"]
    assert rg.MANIFEST_NAME in fp and "base.json" in fp and len(fp) == 8
    assert m["source_upstream"]["commit"], "Upstream-Provenienz der Quelle fehlt"
    links = m["links"]
    assert [ln["index"] for ln in links] == list(range(7)), "Basis + link1…6 erwartet"
    for ln in links:
        f = SDF_DIR / ln["file"]
        assert f.exists() and f.stat().st_size > 0, f"SDF fehlt/leer: {ln['file']}"
        assert np.prod(ln["shape"]) > 0


def test_load_returns_seven_link_sdfs(glied_sdf: GliedSdf) -> None:
    assert glied_sdf.robot == ROBOT
    assert [lk.index for lk in glied_sdf.links] == list(range(7))
    for lk in glied_sdf.links:
        assert lk.values.dtype == np.float32
        assert np.isfinite(lk.values).all()
        assert lk.band_mm == pytest.approx(interpolation_band_mm(lk.voxel_mm))
        # Feld enthält Innen- (negativ) und Außenwerte — sonst ist es kein SDF.
        assert lk.values.min() < 0.0 < lk.values.max()


# --- Ground Truth gegen FCL an gesampelten Konfigurationen --------------------


def _sample_configs(kin: OpwKinematics, n: int, rng) -> list[np.ndarray]:
    lo = np.maximum([lim[0] for lim in kin.params.joint_limits_rad], -np.pi)
    hi = np.minimum([lim[1] for lim in kin.params.joint_limits_rad], np.pi)
    return [rng.uniform(lo, hi) for _ in range(n)]


def _hull_planes(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    hull = mesh.convex_hull
    normals = np.asarray(hull.face_normals, dtype=float)
    offsets = np.einsum("ij,ij->i", normals, np.asarray(hull.triangles[:, 0, :], dtype=float))
    return normals, offsets


def _inside_any(parts: list[trimesh.Trimesh], pts_local: np.ndarray) -> np.ndarray:
    """Exakter Innen-Test (konvexe Stücke, Ebenentest) — im Gliedframe."""
    inside = np.zeros(len(pts_local), dtype=bool)
    for part in parts:
        lo, hi = part.bounds
        cand = np.where(np.all((pts_local >= lo - 1e-9) & (pts_local <= hi + 1e-9), axis=1))[0]
        if len(cand) == 0:
            continue
        normals, offsets = _hull_planes(part)
        s_max = (pts_local[cand] @ normals.T - offsets).max(axis=1)
        inside[cand[s_max <= -1e-6]] = True
    return inside


def _fcl_min_distance(
    point_world: np.ndarray,
    part_objs: list[fcl.CollisionObject],
    aabb_lo: np.ndarray,
    aabb_hi: np.ndarray,
) -> float:
    """FCL-Referenz: min. Distanz Punkt↔Stücke (Sonde = Kugel ``SPHERE_R``).

    AABB-Lücken sind untere Schranken je Stück — Stücke, deren Lücke über dem
    bisherigen Minimum liegt, brauchen keinen exakten FCL-Aufruf (dasselbe
    Zweiphasen-Muster wie :mod:`fgc.collision.check`).
    """
    d = np.maximum(np.maximum(aabb_lo - point_world, point_world - aabb_hi), 0.0)
    gaps = np.sqrt((d * d).sum(axis=1))
    sphere = fcl.CollisionObject(fcl.Sphere(SPHERE_R), fcl.Transform(np.eye(3), point_world))
    best = np.inf
    for j in np.argsort(gaps):
        if gaps[j] - SPHERE_R >= best:
            break
        dist = fcl.distance(sphere, part_objs[j], fcl.DistanceRequest(), fcl.DistanceResult())
        best = min(best, dist)
    return float(best) + SPHERE_R  # Sondenradius zurückrechnen → Punkt-Distanz


@pytest.mark.parametrize("link_index", range(7))
def test_sdf_never_overestimates_fcl_distance(
    glied_sdf: GliedSdf, collision_geo: rg.RobotCollisionGeometry, link_index: int
) -> None:
    """Kernvertrag an gesampelten Konfigurationen: SDF-Distanz ≤ FCL-Distanz.

    Punkte werden im Weltsystem erzeugt (Hüllen-Oberfläche ± Normalversatz an
    zufälligen Gelenkstellungen), über die Glied-Pose ins Gliedframe geholt —
    derselbe Weg, den der spätere ``SdfObstacleProvider`` (#213) geht — und
    gegen FCL auf **derselben** Urteilsgeometrie verglichen. Innenpunkte müssen
    ≤ 0 melden (nie „frei" bei Kollision); die Gegenprobe unten verhindert,
    dass Konservativität zu Beliebigkeit degeneriert.
    """
    rng = np.random.default_rng(207 + link_index)
    kin = OpwKinematics.from_robot(ROBOT)
    lk_geo = collision_geo.link(link_index)
    lk_sdf = glied_sdf.link(link_index)
    parts = list(lk_geo.judgment_parts)
    bvhs = [trimesh.collision.mesh_to_BVH(p) for p in parts]
    part_bounds = np.array([p.bounds for p in parts])  # (P, 2, 3), Gliedframe

    for joints in _sample_configs(kin, 2, rng):
        world_mat = matrix(kin.link_frames(joints)[link_index])
        rot, trans = world_mat[:3, :3], world_mat[:3, 3]
        part_objs = [fcl.CollisionObject(b, fcl.Transform(rot, trans)) for b in bvhs]

        # Sample: Hüllen-Oberfläche ± Versatz entlang der Flächennormale
        # (±2 mm Grenzband ausgespart — Innen/Außen bleibt eindeutig). Versatz bis
        # 70 mm bleibt im Gitter (padding 80) → dort gilt auch die Gegenprobe;
        # zusätzlich ferne Punkte (150–400 mm, außerhalb des Gitters), für die nur
        # Konservativität gilt (AABB-Schranke ist bewusst locker).
        seed = int(rng.integers(1 << 31))
        surf, face = trimesh.sample.sample_surface(lk_geo.broadphase_hull, 28, seed=seed)
        normals = lk_geo.broadphase_hull.face_normals[face]
        offs = rng.uniform(-25.0, 70.0, size=len(surf))
        offs = np.where(np.abs(offs) < 2.0, 2.0, offs)
        offs[-4:] = rng.uniform(150.0, 400.0, size=4)
        tight = np.ones(len(surf), dtype=bool)
        tight[-4:] = False
        pts_local = surf + normals * offs[:, None]
        pts_world = pts_local @ rot.T + trans

        # Realpfad: Weltpunkte über die Glied-Pose zurück ins Gliedframe.
        back_local = (pts_world - trans) @ rot
        sdf_dist, grad = lk_sdf.distance(back_local)
        assert sdf_dist.shape == (len(pts_local),) and grad.shape == (len(pts_local), 3)

        # Welt-AABBs der Stücke für den Vorfilter der FCL-Referenz.
        w_lo = np.empty((len(parts), 3))
        w_hi = np.empty((len(parts), 3))
        for j, (b_lo, b_hi) in enumerate(part_bounds):
            corners = np.array(
                [
                    [x, y, z]
                    for x in (b_lo[0], b_hi[0])
                    for y in (b_lo[1], b_hi[1])
                    for z in (b_lo[2], b_hi[2])
                ]
            )
            wc = corners @ rot.T + trans
            w_lo[j], w_hi[j] = wc.min(axis=0), wc.max(axis=0)

        inside = _inside_any(parts, back_local)
        for k, p_world in enumerate(pts_world):
            if inside[k]:
                # Nie „frei" melden, wo FCL Kollision urteilt.
                assert sdf_dist[k] <= CONS_EPS, f"Innenpunkt {k}: SDF {sdf_dist[k]:.3f} > 0"
                continue
            fcl_dist = _fcl_min_distance(p_world, part_objs, w_lo, w_hi)
            assert sdf_dist[k] <= fcl_dist + CONS_EPS, (
                f"Glied {link_index}, Punkt {k}: SDF {sdf_dist[k]:.3f} mm überschätzt "
                f"FCL {fcl_dist:.3f} mm"
            )
            # Gegenprobe (nur im Gitter): höchstens 2 Interpolationsbänder darunter.
            if tight[k]:
                assert sdf_dist[k] >= fcl_dist - 2.0 * lk_sdf.band_mm - 3.0, (
                    f"Glied {link_index}, Punkt {k}: SDF {sdf_dist[k]:.3f} mm zu weit unter "
                    f"FCL {fcl_dist:.3f} mm — Feld defekt?"
                )


def test_safety_band_shifts_distance_conservatively(glied_sdf: GliedSdf) -> None:
    lk = glied_sdf.link(2)
    pts = np.asarray(lk.object_hi_mm, dtype=float) + np.array([[30.0, 0.0, 0.0]])
    d0, _ = lk.distance(pts)
    d1, _ = lk.distance(pts, safety_band_mm=10.0)
    assert d1 == pytest.approx(d0 - 10.0)


# --- Analytische Konservativität am synthetischen Würfel ----------------------


def _box_sdf(pts: np.ndarray, half: float) -> np.ndarray:
    """Exakte signierte Distanz zum achsparallelen Würfel [−half, half]³."""
    q = np.abs(pts) - half
    outside = np.linalg.norm(np.clip(q, 0.0, None), axis=1)
    inside = np.clip(q.max(axis=1), None, 0.0)
    return outside + inside


def test_build_link_field_cube_conservative_and_tight() -> None:
    """Reine Build-Funktion + Abfrage gegen die analytische Würfel-Distanz."""
    box = trimesh.creation.box(extents=[100.0, 100.0, 100.0])
    field = build_link_field([(box.vertices, box.faces)], voxel_mm=10.0, padding_mm=40.0)
    lk = LinkSdf(
        index=0,
        urdf_link="cube",
        origin_mm=field["origin_mm"],
        voxel_mm=field["voxel_mm"],
        band_mm=interpolation_band_mm(field["voxel_mm"]),
        values=field["values"],
        object_lo_mm=field["object_bounds_mm"][0],
        object_hi_mm=field["object_bounds_mm"][1],
    )
    rng = np.random.default_rng(207)
    pts = rng.uniform(-120.0, 120.0, size=(500, 3))  # inkl. Punkte außerhalb des Gitters
    truth = _box_sdf(pts, 50.0)
    dist, grad = lk.distance(pts)
    assert np.all(dist <= truth + 1e-6), "Distanz überschätzt die analytische Wahrheit"
    assert np.all(dist >= truth - 2.0 * lk.band_mm - 0.5), "Distanz degeneriert nach unten"
    # Gradient zeigt vom Würfel weg (klar außerhalb, abseits der Kanten).
    p = np.array([[80.0, 0.0, 0.0]])
    _, g = lk.distance(p)
    assert g[0, 0] > 0.9 * np.linalg.norm(g[0])


def test_distance_batch_shapes_and_empty() -> None:
    box = trimesh.creation.box(extents=[50.0, 50.0, 50.0])
    field = build_link_field([(box.vertices, box.faces)], voxel_mm=10.0, padding_mm=30.0)
    lk = LinkSdf(
        index=0,
        urdf_link="cube",
        origin_mm=field["origin_mm"],
        voxel_mm=field["voxel_mm"],
        band_mm=interpolation_band_mm(field["voxel_mm"]),
        values=field["values"],
        object_lo_mm=field["object_bounds_mm"][0],
        object_hi_mm=field["object_bounds_mm"][1],
    )
    d, g = lk.distance(np.zeros((0, 3)))
    assert d.shape == (0,) and g.shape == (0, 3)
    d, g = lk.distance([0.0, 0.0, 0.0])  # einzelner Punkt, flach übergeben
    assert d.shape == (1,) and d[0] < 0.0


# --- Provenienz-Fehlpfade (US 18) ---------------------------------------------


@pytest.fixture()
def fake_robots_dir(tmp_path):
    """Miniatur-Katalog + Kollisions-Derivat + gültiges SDF-Artefakt für Fehlpfade."""
    robot = "testbot"
    robots = tmp_path / "robots"
    coll = robots / "collision" / robot
    coll.mkdir(parents=True)
    (robots / f"{robot}.json").write_text(
        json.dumps({"name": robot, "collision_geometry": f"collision/{robot}"}),
        encoding="utf-8",
    )
    (coll / "base.json").write_text('{"fake": "geometrie"}', encoding="utf-8")
    (coll / rg.MANIFEST_NAME).write_text(
        json.dumps(
            {"robot": robot, "links": [{"index": 0, "urdf_link": "base", "file": "base.json"}]}
        ),
        encoding="utf-8",
    )

    box = trimesh.creation.box(extents=[50.0, 50.0, 50.0])
    field = build_link_field(
        [(box.vertices, box.faces)], voxel_mm=gs.DEFAULT_VOXEL_MM, padding_mm=30.0
    )
    sdf_dir = coll / gs.SDF_DIR_NAME
    sdf_dir.mkdir()
    np.save(sdf_dir / "base.npy", field["values"])
    manifest = {
        "sdf_format_version": gs.SDF_FORMAT_VERSION,
        "robot": robot,
        "units": "mm",
        "voxel_mm": gs.DEFAULT_VOXEL_MM,
        "padding_mm": 30.0,
        "source_files_sha256": gs.source_fingerprint(coll),
        "links": [
            {
                "index": 0,
                "urdf_link": "base",
                "file": "base.npy",
                "shape": list(field["values"].shape),
                "origin_mm": field["origin_mm"].tolist(),
                "object_bounds_mm": field["object_bounds_mm"].tolist(),
            }
        ],
    }
    (sdf_dir / gs.SDF_MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return robots, robot, sdf_dir


def _patch_manifest(sdf_dir, **overrides) -> None:
    m = json.loads((sdf_dir / gs.SDF_MANIFEST_NAME).read_text(encoding="utf-8"))
    m.update(overrides)
    (sdf_dir / gs.SDF_MANIFEST_NAME).write_text(json.dumps(m), encoding="utf-8")


def test_valid_fake_artifact_loads(fake_robots_dir) -> None:
    robots, robot, _ = fake_robots_dir
    sdf = load_glied_sdf(robot, robots_dir=robots)
    assert sdf.robot == robot and len(sdf.links) == 1
    d, _ = sdf.distance(0, [[0.0, 0.0, 0.0]])
    assert d[0] < 0.0


def test_wrong_robot_provenance_fails(fake_robots_dir) -> None:
    robots, robot, sdf_dir = fake_robots_dir
    _patch_manifest(sdf_dir, robot="anderer_arm")
    with pytest.raises(SdfProvenanceError, match="anderer_arm.*falsche Provenienz"):
        load_glied_sdf(robot, robots_dir=robots)


def test_stale_resolution_fails(fake_robots_dir) -> None:
    robots, robot, sdf_dir = fake_robots_dir
    _patch_manifest(sdf_dir, voxel_mm=16.0)
    with pytest.raises(SdfProvenanceError, match="veraltete Auflösung"):
        load_glied_sdf(robot, robots_dir=robots)


def test_stale_source_build_fails(fake_robots_dir) -> None:
    """Quellgeometrie neu konvertiert → SDF-Buildstand veraltet → klarer Fehler."""
    robots, robot, _ = fake_robots_dir
    src = robots / "collision" / robot / "base.json"
    src.write_text('{"fake": "neu konvertiert"}', encoding="utf-8")
    with pytest.raises(SdfProvenanceError, match="Buildstand veraltet.*base.json"):
        load_glied_sdf(robot, robots_dir=robots)


def test_unsupported_format_version_fails(fake_robots_dir) -> None:
    robots, robot, sdf_dir = fake_robots_dir
    _patch_manifest(sdf_dir, sdf_format_version=gs.SDF_FORMAT_VERSION + 1)
    with pytest.raises(SdfProvenanceError, match="Formatstand"):
        load_glied_sdf(robot, robots_dir=robots)


def test_missing_artifact_is_friendly(fake_robots_dir) -> None:
    robots, robot, sdf_dir = fake_robots_dir
    shutil.rmtree(sdf_dir)
    with pytest.raises(FileNotFoundError, match="build_glied_sdf.py"):
        load_glied_sdf(robot, robots_dir=robots)


# --- Geo-Extras fehlen: freundlicher Fehlpfad statt Import-Crash ---------------


def test_module_imports_without_geo_at_top_level() -> None:
    assert not hasattr(gs, "np") and not hasattr(gs, "numpy")
    assert not hasattr(gs, "trimesh")


def test_require_np_gives_friendly_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "numpy", None)  # simuliert fehlendes Extra
    with pytest.raises(ImportError, match=r"fgc-core\[geo\]"):
        gs._require_np()
