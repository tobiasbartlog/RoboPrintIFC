"""Kollisions-Befund je Sample gegen den wachsenden Druckstand (ADR-024, Issue #126).

Testet das **externe Verhalten** von :mod:`fgc.collision.check`: „Bahn X gegen
Druckstand Y ⇒ Intervall [t1,t2], min. Abstand d, Verursacher Glied L", die
**Distanz-Goldens** (deterministisch, bitgleich bei Wiederholung), die
**konservative Zweiphasen**-Eigenschaft (Hüllen-Distanz ≤ Urteils-Distanz, kein
Sample fälschlich sicher), Selbstkollision ohne Nachbarpaare mit ausgenommenem
Basis↔Boden und die provisorische Endeffektor-Hülle. Der **Performance-Anker**
(Foto-Trajektorie, 25 217 Samples < 60 s) ist als ``slow`` markiert.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon
from trimesh.collision import CollisionManager

from fgc.collision import check as ck
from fgc.collision import druckstand as ds
from fgc.collision.robot_geometry import load_robot_collision_geometry
from fgc.domain.models import Frame
from fgc.geometry.section import section_at
from fgc.kinematics.opw import OpwKinematics, _quat_to_rot
from fgc.paths import RUNS_DIR, TOOLS_DIR
from fgc.simulation import transform

ROBOT = "doosan_m1013"
GOLDEN = Path(__file__).parent / "goldens" / "collision_check_slice.json"
PERF_RUN = RUNS_DIR / "20260708-161603_slice_Denkmal"

# Sechs Posen aus der frühen Foto-Trajektorie (Ellbogen an der Wand).
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
FOOTPRINT = (Polygon([(-500, -100), (500, -100), (500, 100), (-500, 100)]),)


def _mat(fr: Frame) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = _quat_to_rot(fr.quat)
    t[:3, 3] = fr.pos_mm
    return t


def _floor() -> trimesh.Trimesh:
    f = trimesh.creation.box(extents=[6000, 6000, 200])
    f.apply_translation([0, 0, -100])
    return f


def _scenario():
    """Feste, deterministische Szene: geo + Bahn + Druckstand-Provider (kein Tool)."""
    geo = load_robot_collision_geometry(ROBOT)
    kin = OpwKinematics.from_robot(ROBOT)
    lfs = [kin.link_frames(list(p)) for p in POSES]
    spec = ds.DruckstandSpec(
        footprint=FOOTPRINT, layer_height_mm=10.0, n_layers=82, ground=_floor()
    )
    return geo, lfs, ds.obstacle_provider(spec)


# --- Externes Verhalten: Intervall + min. Abstand + Verursacher --------------


def test_path_against_druckstand_reports_interval_min_and_causer() -> None:
    geo, lfs, prov = _scenario()
    report = ck.find_collisions(geo, BASE, lfs, LAYERS, prov, self_collision=False)

    # Diese Bahn kollidiert (Ellbogen im Druckstand) — roter Befund, kein Gate.
    assert report.min_distance_mm < 0.0
    assert report.n_red >= 1
    # Verdichtete Intervalle decken lückenlos alle Samples ab.
    assert report.intervals[0].start_index == 0
    assert report.intervals[-1].end_index == len(POSES) - 1
    # Verursacher am schlimmsten Sample ist ein Armglied gegen den Druckstand.
    worst = min(report.samples, key=lambda s: s.distance_mm)
    assert worst.link in (2, 3, 4, 5)
    assert worst.against in ("current_part", "ground")
    assert worst.status == "red"


# --- Distanz-Goldens: deterministisch, bitgleich bei Wiederholung ------------


def test_distance_goldens_bit_identical_on_repeat() -> None:
    geo, lfs, prov = _scenario()
    d1 = ck.find_collisions(geo, BASE, lfs, LAYERS, prov, self_collision=False).distances()
    d2 = ck.find_collisions(geo, BASE, lfs, LAYERS, prov, self_collision=False).distances()
    # Wiederholung ist BITGLEICH (python-fcl deterministisch, Spike S0).
    assert [x.hex() for x in d1] == [x.hex() for x in d2]


def test_distance_goldens_match_stored_fixture() -> None:
    geo, lfs, prov = _scenario()
    dists = ck.find_collisions(geo, BASE, lfs, LAYERS, prov, self_collision=False).distances()
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    got = [round(x, 3) for x in dists]
    assert got == golden["distances_mm"], f"Distanz-Golden gebrochen: {got}"


# --- Zweiphasen nachweislich konservativ -------------------------------------


def test_two_phase_hull_distance_is_lower_bound() -> None:
    """Hüllen-Distanz ≤ Urteils-Distanz je Glied/Pose ⇒ kein Sample fälschlich sicher."""
    geo, lfs, _ = _scenario()
    floor = _floor()
    prism = ds.extrude_prism(FOOTPRINT, 0.0, 420.0)
    obst = CollisionManager()
    obst.add_object("ground", floor)
    obst.add_object("current_part", prism)

    worst_gap = np.inf
    for lf in lfs:
        world = [transform.compose(BASE, f) for f in lf]
        for i in range(1, 7):
            m = _mat(world[i])
            hull_mgr = CollisionManager()
            hull_mgr.add_object("h", geo.link(i).broadphase_hull)
            hull_mgr.set_transform("h", m)
            part_mgr = CollisionManager()
            for k, part in enumerate(geo.link(i).judgment_parts):
                part_mgr.add_object(f"j{k}", part)
            for k in range(len(geo.link(i).judgment_parts)):
                part_mgr.set_transform(f"j{k}", m)
            d_hull = hull_mgr.min_distance_other(obst)
            d_judg = part_mgr.min_distance_other(obst)
            worst_gap = min(worst_gap, d_judg - d_hull)
    # Hülle ⊇ Roh-Mesh ⇒ Hüllen-Distanz ist untere Schranke (Toleranz für fcl-Rundung).
    assert worst_gap >= -0.5, f"Hülle nicht konservativ: judg-broad={worst_gap:.3f} mm"


# --- Selbstkollision ohne Nachbarpaare, Basis↔Boden ausgenommen --------------


def test_nonadjacent_pairs_exclude_neighbours() -> None:
    pairs = ck.nonadjacent_pairs((0, 1, 2, 3, 4, 5, 6))
    assert all(abs(i - j) >= 2 for i, j in pairs)
    assert (1, 2) not in pairs and (5, 6) not in pairs  # Nachbarn raus
    assert (0, 2) in pairs and (4, 6) in pairs  # Basis-Paare bleiben
    # Tool (Index 7) prüft nur gegen nicht-benachbarte Glieder (nicht 5/6).
    tp = ck.nonadjacent_pairs((0, 1, 2, 3, 4, 5, 6, ck.TOOL_INDEX))
    assert (5, ck.TOOL_INDEX) in tp and (6, ck.TOOL_INDEX) not in tp


def test_base_floor_contact_is_not_a_collision() -> None:
    """Die Basis (Glied 0) wird nicht gegen den Boden geprüft — erlaubter Dauerkontakt."""
    geo, lfs, _ = _scenario()
    # Boden, der die Basis (bei z≈0) berührt, aber weit unter dem Arm liegt.
    floor = trimesh.creation.box(extents=[6000, 6000, 60])
    floor.apply_translation([0, 0, 0])  # deckt z∈[-30,30] — umschließt die Basis
    spec = ds.DruckstandSpec(footprint=FOOTPRINT, layer_height_mm=10.0, n_layers=82, ground=floor)
    prov = ds.obstacle_provider(spec)
    # Arm aufrecht/gestreckt nach oben, weit weg vom Boden.
    kin = OpwKinematics.from_robot(ROBOT)
    up = kin.link_frames([0.0, -1.4, 0.2, 0.0, 0.5, 0.0])
    base0 = Frame(pos_mm=(0.0, 0.0, 0.0))
    report = ck.find_collisions(geo, base0, [up], [0], prov, self_collision=True)
    # Kein roter Befund allein aus Basis↔Boden (Basis ist von der Hindernisprüfung ausgenommen).
    assert report.samples[0].link != 0


# --- Endeffektor: provisorische Hülle am TCP ---------------------------------


def _tool_hull() -> tuple[trimesh.Trimesh, Frame, Frame]:
    tool = json.loads((TOOLS_DIR / "30gut.json").read_text(encoding="utf-8"))
    mesh = trimesh.load(TOOLS_DIR / tool["mesh"], force="mesh", process=False)
    mt = transform.frame_from_dict(tool["mesh_transform"])
    tcp = transform.frame_from_dict(tool["tcp_frame"])
    return ck.provisional_tool_hull(mesh, mt, tcp), tcp, mesh


def test_tool_hull_is_provisional_and_convex() -> None:
    hull, _tcp, mesh = _tool_hull()
    assert hull.is_convex
    # Die Hülle umschließt das Roh-Tool (untere Distanz-Schranke wie die Glied-Hüllen).
    assert hull.volume >= mesh.convex_hull.volume * 0.99


def test_report_marks_tool_provisional() -> None:
    geo, lfs, prov = _scenario()
    hull, tcp, _ = _tool_hull()
    report = ck.find_collisions(
        geo, BASE, lfs, LAYERS, prov, tcp_frame=tcp, tool_hull=hull, self_collision=False
    )
    assert report.tool_provisional is True
    report_no_tool = ck.find_collisions(geo, BASE, lfs, LAYERS, prov, self_collision=False)
    assert report_no_tool.tool_provisional is False


# --- Freizone: Druckstand um den Druckpunkt nicht bewertet -------------------


def test_freizone_suppresses_current_part_near_print_point() -> None:
    """Mit großer Freizone verschwindet der Nahkontakt zum wachsenden Teil (Düse↔Wulst)."""
    geo, lfs, _ = _scenario()
    hull, tcp, _ = _tool_hull()
    spec_no = ds.DruckstandSpec(
        footprint=FOOTPRINT, layer_height_mm=10.0, n_layers=82, ground=_floor()
    )
    spec_fz = ds.DruckstandSpec(
        footprint=FOOTPRINT, layer_height_mm=10.0, n_layers=82, ground=_floor(),
        freizone_radius_mm=100000.0,  # deckt die ganze Szene → Druckstand nie bewertet
    )
    kw = dict(tcp_frame=tcp, tool_hull=hull, self_collision=False)
    r_no = ck.find_collisions(geo, BASE, lfs, LAYERS, ds.obstacle_provider(spec_no), **kw)
    r_fz = ck.find_collisions(geo, BASE, lfs, LAYERS, ds.obstacle_provider(spec_fz), **kw)
    # Ohne Freizone kollidiert das wachsende Teil; mit alles-deckender Freizone bleibt
    # nur der Boden übrig → der min. Abstand wird nicht schlechter durchs current_part.
    assert all(s.against != "current_part" for s in r_fz.samples)
    assert r_fz.min_distance_mm >= r_no.min_distance_mm


# --- Performance-Anker: Foto-Trajektorie < 60 s ------------------------------


@pytest.mark.slow
def test_perf_anchor_photo_trajectory_under_60s() -> None:
    """25 217 Samples der Foto-Trajektorie < 60 s (Spike-Referenz 44 s)."""
    if not (PERF_RUN / "trajectory.json").exists():
        pytest.skip("Performance-Anker-Lauf nicht vorhanden")

    traj = json.loads((PERF_RUN / "trajectory.json").read_text(encoding="utf-8"))
    wallspec = json.loads((PERF_RUN / "wallspec.json").read_text(encoding="utf-8"))
    toolpath = json.loads((PERF_RUN / "toolpath.json").read_text(encoding="utf-8"))
    layer_h = float(toolpath["params"]["layer_height_mm"])
    n_layers = int(toolpath["summary"]["n_layers"])

    geo = load_robot_collision_geometry(ROBOT)
    kin = OpwKinematics.from_robot(ROBOT)
    base = transform.frame_from_dict(traj["meta"]["base_frame"])
    samples = traj["samples"]
    lfs = [kin.link_frames(s["joints_rad"]) for s in samples]

    # Footprint = echter Slicer-Umriss der Wand nahe der Basis, extrudiert je Schicht.
    wall = trimesh.Trimesh(
        vertices=np.array(wallspec["geometry"]["vertices_mm"], dtype=float),
        faces=np.array(wallspec["geometry"]["faces"], dtype=int),
        process=True,
    )
    footprint = tuple(section_at(wall, 1.0)) or (
        Polygon([(wall.bounds[0][0], wall.bounds[0][1]),
                 (wall.bounds[1][0], wall.bounds[0][1]),
                 (wall.bounds[1][0], wall.bounds[1][1]),
                 (wall.bounds[0][0], wall.bounds[1][1])]),
    )
    spec = ds.DruckstandSpec(
        footprint=footprint, layer_height_mm=layer_h, n_layers=n_layers, ground=_floor()
    )
    prov = ds.obstacle_provider(spec)

    # Schicht je Sample aus der TCP-Höhe in Wandkoordinaten (base_frame = Basis-in-Wand)
    # auf dem Toolpath-Schichtraster (layer_height aus dem Toolpath) — Spike-validiert.
    tcp_hull, tcp, _ = _tool_hull()
    zs = []
    for lf in lfs:
        world_tcp = transform.compose(base, transform.compose(lf[6], tcp))
        zs.append(world_tcp.pos_mm[2])
    sample_layers = [int(np.clip(int(np.floor(z / layer_h)), 0, n_layers)) for z in zs]

    t0 = time.perf_counter()
    report = ck.find_collisions(
        geo, base, lfs, sample_layers, prov,
        tcp_frame=tcp, tool_hull=tcp_hull, self_collision=False,
    )
    dt = time.perf_counter() - t0
    print(f"\nPerf-Anker: {len(samples)} Samples in {dt:.1f} s "
          f"(min {report.min_distance_mm:.1f} mm, rot {report.n_red}, gelb {report.n_yellow})")

    assert len(samples) > 25000
    assert report.min_distance_mm < 0.0  # die Foto-Trajektorie kollidiert wirklich
    assert dt < 60.0, f"Performance-Anker {dt:.1f} s ≥ 60 s"
