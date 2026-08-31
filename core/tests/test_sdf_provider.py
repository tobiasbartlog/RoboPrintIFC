"""SdfObstacleProvider: SDF-Backend am Hindernis-Provider-Vertrag (PRD #183 AP 1, #213).

Externes Verhalten (Testing Decisions #183, zweistufiger Anker — hier die
CPU-Stufe; die GPU-Stufe mit Toleranzschema lebt in #205):

- **Regressionsanker (US 2):** FCL-Referenz und SDF-Backend liefern auf der
  roten Foto-Szene **identische Befunde** — Status je Sample sowie
  Verursacher-Glied/-Gegner, Eindringtiefe und Distanz **bitgleich** für alle
  nicht-grünen Samples (grün-ferne Zahlen sind beiderseits konservative
  Schranken und dürfen abweichen).
- **Grenzband (US 16):** ein Fall, in dem der FCL-Nachprüfer nachweislich
  greift — die rohe SDF-Schranke läge unter dem Sicherheitsabstand, das
  Urteil kommt exakt (bitgleich, Phase ``judgment``) aus FCL.
- **Selbstkollision im Punkt-Schema:** ein roter Fall (Punkte der Tool-Hülle
  gegen Glied-SDF) und ein gelber Fall (Punkte von Glied 2 gegen Basis-SDF),
  beide bit-identisch zur Referenz.
- **Umschaltung per Konfiguration (US 14)** am App-Ebenen-Backend-Schalter und
  **Fail-soft (US 12)**: ohne SDF-Artefakt fällt die Konstruktion still auf
  die FCL-Referenz zurück; der Default bleibt FCL (Altläufe unverändert).
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon

from fgc.collision import backend as be
from fgc.collision import check as ck
from fgc.collision import druckstand as ds
from fgc.collision import glied_sdf as gs
from fgc.collision.glied_sdf import GliedSdf, load_glied_sdf
from fgc.collision.robot_geometry import (
    RobotCollisionGeometry,
    load_robot_collision_geometry,
)
from fgc.collision.sdf_provider import SdfObstacleProvider
from fgc.domain.models import Frame
from fgc.kinematics.opw import OpwKinematics
from fgc.paths import ROBOTS_DIR
from fgc.simulation import transform

ROBOT = "doosan_m1013"
SDF_DIR = ROBOTS_DIR / "collision" / ROBOT / gs.SDF_DIR_NAME
SAFETY = ck.DEFAULT_SAFETY_DISTANCE_MM

pytestmark = pytest.mark.skipif(not SDF_DIR.exists(), reason="Glied-SDF-Artefakt fehlt")

# Sechs Posen der frühen Foto-Trajektorie (Ellbogen in der Wand) — dieselbe rote
# Szene wie die Distanz-Goldens in test_collision_check.py.
POSES = [
    (-1.961411281, 0.668627027, 0.274207647, -1.406128953, -1.015097337, -1.077559278),
    (-1.941603815, 0.679521265, 0.251597532, -1.40307744, -1.028900007, -1.060921878),
    (-1.921471535, 0.689785081, 0.230296713, -1.399026077, -1.042890054, -1.0451194),
    (-1.901022731, 0.699432812, 0.21027513, -1.394027265, -1.057051871, -1.030102148),
    (-1.88026701, 0.708476448, 0.191507657, -1.388131288, -1.071372012, -1.015824926),
    (-1.859215323, 0.716925978, 0.173973369, -1.381386689, -1.085838922, -1.00224657),
]
LAYERS = [40, 40, 41, 41, 42, 42]
BASE = Frame(pos_mm=(0.0, 615.0, 0.0))
BASE0 = Frame(pos_mm=(0.0, 0.0, 0.0))
FOOTPRINT = (Polygon([(-500, -100), (500, -100), (500, 100), (-500, 100)]),)
EMPTY_SPEC = ds.DruckstandSpec(footprint=(), layer_height_mm=10.0, n_layers=0)


@pytest.fixture(scope="module")
def geo() -> RobotCollisionGeometry:
    return load_robot_collision_geometry(ROBOT)


@pytest.fixture(scope="module")
def glied_sdf() -> GliedSdf:
    return load_glied_sdf(ROBOT)


@pytest.fixture(scope="module")
def kin() -> OpwKinematics:
    return OpwKinematics.from_robot(ROBOT)


def _floor() -> trimesh.Trimesh:
    f = trimesh.creation.box(extents=[6000, 6000, 200])
    f.apply_translation([0, 0, -100])
    return f


def _assert_nongreen_bitidentical(ref: ck.CollisionReport, got: ck.CollisionReport) -> None:
    """Der Identitäts-Kern des CPU-Ankers: Status überall, Werte bitgleich wo es zählt."""
    assert [s.status for s in got.samples] == [s.status for s in ref.samples]
    for g, r in zip(got.samples, ref.samples, strict=True):
        if r.status != "green":
            assert g.distance_mm.hex() == r.distance_mm.hex()
            assert (g.link, g.against, g.phase) == (r.link, r.against, r.phase)
    assert (got.n_red, got.n_yellow, got.n_green) == (ref.n_red, ref.n_yellow, ref.n_green)
    assert got.worst_index == ref.worst_index


# --- Regressionsanker (US 2): Backend-Flip auf der roten Foto-Szene -----------


def test_backend_flip_identical_findings_on_red_scene(geo, glied_sdf, kin) -> None:
    lfs = [kin.link_frames(list(p)) for p in POSES]
    spec = ds.DruckstandSpec(
        footprint=FOOTPRINT, layer_height_mm=10.0, n_layers=82, ground=_floor()
    )
    ref = ck.find_collisions(
        geo, BASE, lfs, LAYERS, ds.obstacle_provider(spec), self_collision=False
    )
    prov = SdfObstacleProvider(spec, glied_sdf, geo)
    got = ck.find_collisions(geo, BASE, lfs, LAYERS, prov, self_collision=False)

    _assert_nongreen_bitidentical(ref, got)
    # Die Szene ist rot — Eindringtiefe (worst) bitgleich, Verursacher identisch.
    assert ref.min_distance_mm < 0.0
    assert got.min_distance_mm.hex() == ref.min_distance_mm.hex()
    # Der Provider erfüllt den Hindernis-Provider-Vertrag: ObstacleSet je Schicht.
    oset = prov(41)
    assert oset.layer_index == 41
    assert any(o.name == "current_part" for o in oset.obstacles)


def test_provider_contract_and_point_growth(geo, glied_sdf) -> None:
    """Punktwolke wächst je Schicht (Präfix-Views), Schicht 0 = nur Statik."""
    spec = ds.DruckstandSpec(
        footprint=FOOTPRINT, layer_height_mm=10.0, n_layers=5, ground=_floor()
    )
    prov = SdfObstacleProvider(spec, glied_sdf, geo)
    prov.prime(5)
    counts = [prov.n_obstacle_points(layer) for layer in range(6)]
    assert counts[0] > 0  # Statik (Boden) zählt ab Schicht 0
    assert all(a < b for a, b in zip(counts, counts[1:], strict=False))  # reines Anhängen


# --- Grenzband (US 16): FCL-Nachprüfer greift nachweislich --------------------


def test_grenzband_fcl_nachpruefer_liefert_exaktes_urteil(geo, glied_sdf, kin) -> None:
    """Boden exakt 40 mm unter dem tiefsten Glied: die rohe SDF-Schranke läge
    weit darunter (Deckung + Interpolationsband), das Urteil kommt bitgleich
    und exakt (Phase ``judgment``) aus dem FCL-Nachprüfer."""
    joints = [0.0, -0.6, -0.6, 0.0, 0.6, 0.0]
    lf = kin.link_frames(joints)
    world = [transform.compose(BASE0, f) for f in lf]
    zmin = min(
        (np.asarray(p.vertices) @ ck.matrix(world[i])[:3, :3].T + ck.matrix(world[i])[:3, 3])[
            :, 2
        ].min()
        for i in range(1, 7)
        for p in geo.link(i).judgment_parts
    )
    slab = trimesh.creation.box(extents=[4000.0, 4000.0, 100.0])
    slab.apply_translation([0.0, 0.0, float(zmin) - 40.0 - 50.0])  # Oberkante bei zmin − 40
    spec = ds.DruckstandSpec(footprint=(), layer_height_mm=10.0, n_layers=0, ground=slab)

    ref = ck.find_collisions(
        geo, BASE0, [lf], [0], ds.obstacle_provider(spec), self_collision=False
    )
    prov = SdfObstacleProvider(spec, glied_sdf, geo)
    got = ck.find_collisions(geo, BASE0, [lf], [0], prov, self_collision=False)

    r, g = ref.samples[0], got.samples[0]
    assert r.status == "yellow" and r.phase == "judgment"
    assert g.status == "yellow" and g.phase == "judgment"
    assert g.distance_mm.hex() == r.distance_mm.hex()
    assert (g.link, g.against) == (r.link, r.against)
    assert prov.n_grenzband >= 1  # die Schranke fiel ins Grenzband — FCL lief

    # Nachweis „der Nachprüfer greift": die rohe SDF-Schranke des Verursachers
    # liegt unter dem exakten Urteil (konservativ) und im Grenzband.
    mats = {i: ck.matrix(world[i]) for i in range(len(world))}
    corners = ck.corner_box(geo.link(g.link).broadphase_hull, np)
    wc = (mats[g.link] @ corners)[:3]
    bound = prov.obstacle_bound(0, g.link, mats[g.link], wc.min(axis=1), wc.max(axis=1), SAFETY)
    assert bound <= SAFETY < 70.0
    assert bound < g.distance_mm  # Schranke unterschätzt, das exakte Urteil kam von FCL


# --- Selbstkollision im Punkt-Schema -------------------------------------------


def test_selbstkollision_rot_im_punkt_schema(geo, glied_sdf, kin) -> None:
    """Tool-Hülle hinter den Flansch in den Unterarm getaucht: rote
    Selbstkollision (Punkte der Tool-Hülle gegen Glied-SDF), bit-identisch."""
    hull = trimesh.creation.box(extents=[200.0, 200.0, 200.0]).convex_hull
    tcp = Frame(pos_mm=(0.0, 0.0, -450.0))
    lf = kin.link_frames([0.0, 0.5, 0.5, 0.0, 0.5, 0.0])
    kw = dict(tcp_frame=tcp, tool_hull=hull, self_collision=True)

    ref = ck.find_collisions(geo, BASE0, [lf], [0], ds.obstacle_provider(EMPTY_SPEC), **kw)
    prov = SdfObstacleProvider(EMPTY_SPEC, glied_sdf, geo)
    got = ck.find_collisions(geo, BASE0, [lf], [0], prov, **kw)

    r, g = ref.samples[0], got.samples[0]
    assert r.status == "red" and str(r.against).startswith("link")
    assert (g.status, g.link, g.against) == (r.status, r.link, r.against)
    assert g.distance_mm.hex() == r.distance_mm.hex()
    assert prov.n_grenzband >= 1  # das Paar fiel ins Grenzband — FCL urteilte exakt


def test_selbstkollision_gelb_glied_gegen_glied(geo, glied_sdf, kin) -> None:
    """Gefaltete Pose ohne Hindernisse: Warnung Basis↔Glied 2 im Punkt-Schema
    (Punkte von Glied 2 gegen das Basis-SDF), bit-identisch zur Referenz."""
    lf = kin.link_frames([0.0, 1.2, 2.7, 0.0, 1.2, 0.0])

    ref = ck.find_collisions(
        geo, BASE0, [lf], [0], ds.obstacle_provider(EMPTY_SPEC), self_collision=True
    )
    prov = SdfObstacleProvider(EMPTY_SPEC, glied_sdf, geo)
    got = ck.find_collisions(geo, BASE0, [lf], [0], prov, self_collision=True)

    r, g = ref.samples[0], got.samples[0]
    assert r.status == "yellow" and str(r.against).startswith("link")
    assert (g.status, g.link, g.against) == (r.status, r.link, r.against)
    assert g.distance_mm.hex() == r.distance_mm.hex()


# --- Umschaltung per Konfiguration (US 14) + Fail-soft (US 12) ------------------


def test_backend_switch_default_env_and_setter(monkeypatch) -> None:
    monkeypatch.delenv(be.BACKEND_ENV, raising=False)
    assert be.collision_backend() == "fcl"  # Default: Altläufe unverändert
    monkeypatch.setenv(be.BACKEND_ENV, "sdf")
    assert be.collision_backend() == "sdf"  # Umgebungs-Konfiguration
    monkeypatch.setenv(be.BACKEND_ENV, "unsinn")
    assert be.collision_backend() == "fcl"  # Tippfehler fällt soft auf die Referenz
    try:
        be.set_collision_backend("sdf")
        assert be.collision_backend() == "sdf"  # expliziter Setzwert gewinnt
    finally:
        be.set_collision_backend(None)
    with pytest.raises(ValueError, match="Unbekanntes Kollisions-Backend"):
        be.set_collision_backend("gpu")


def test_backend_switch_builds_sdf_provider_and_falls_back_soft(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(be.BACKEND_ENV, raising=False)
    spec = ds.DruckstandSpec(footprint=FOOTPRINT, layer_height_mm=10.0, n_layers=5)

    # Default (fcl): schlichter Referenz-Provider ohne SDF-Oberfläche.
    prov = be.obstacle_provider_for(ROBOT, spec)
    assert ck._sdf_surface(prov) is None
    assert prov(3).layer_index == 3

    try:
        be.set_collision_backend("sdf")
        prov = be.obstacle_provider_for(ROBOT, spec)
        assert isinstance(prov, SdfObstacleProvider)
        assert ck._sdf_surface(prov) is prov
        assert prov(3).layer_index == 3  # der Vertrag bleibt erfüllt

        # Fail-soft (US 12): Roboter ohne SDF-Artefakt → FCL-Referenz statt Crash.
        robots = tmp_path
        (robots / "altbot.json").write_text(json.dumps({"name": "altbot"}), encoding="utf-8")
        old = be.obstacle_provider_for("altbot", spec, robots_dir=robots)
        assert ck._sdf_surface(old) is None
        assert old(2).layer_index == 2
    finally:
        be.set_collision_backend(None)
