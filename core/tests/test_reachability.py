"""ReachabilityMap (PRD #183 AP 2, Issue #210): IK-Ground-Truth, Min-Aggregation, Provenienz.

Externes Verhalten, keine Implementierungsdetails (Testing Decisions #183):

- **Ground Truth gegen die skalare OPW-IK am Kartenraster:** an gesampelten
  4D-Knoten stimmt die Karte mit „existiert eine IK-Lösung innerhalb der
  Achsgrenzen?" überein — insbesondere **keine falschen Negative** (Kernvertrag
  des Vorfilters: er darf nie Erreichbares wegfiltern, das die Prüf-Tür nie
  mehr sieht).
- **Minimum über Posenmengen** (US 6): punktweises UND über eine konstruierte
  Höhenreihe, plus der semantische Fall „Basis erreicht Pose A, aber nicht die
  ganze Reihe".
- **Provenienz (US 17/18):** Artefakt-Manifest vollständig; falscher Roboter,
  geänderte Katalog-Kinematik, falscher Formatstand und fehlendes Artefakt
  schlagen klar fehl.
- Vorwärts-/Inversabfrage sind dieselbe Struktur (Konsistenz-Invariante) über
  den #201-Seam (``flange_targets`` → ``frames_in_wall``).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from fgc.domain.models import Frame
from fgc.domain.robot import Kinematics, RobotDef
from fgc.domain.tool import ToolDef
from fgc.kinematics import reachability as rm
from fgc.kinematics.opw import OpwKinematics
from fgc.kinematics.reachability import (
    ReachabilityMap,
    ReachabilityProvenanceError,
    canonical_coords,
    frames_in_wall,
    kinematics_fingerprint,
    load_reachability_map,
    representative_frame,
    save_reachability_map,
)
from fgc.paths import ROBOTS_DIR
from fgc.placement.evaluate import (
    PlacementOption,
    WallSurface,
    base_position_in_wall,
    flange_targets,
    nozzle_rotation,
)

ROBOT = "doosan_m1013"
RM_DIR = ROBOTS_DIR / rm.RM_DIR_NAME / ROBOT

#: Quaternion „Anflug senkrecht nach unten" (Rotation um y um π: z-Achse → −z).
DOWN_QUAT = (0.0, 0.0, 1.0, 0.0)


@pytest.fixture(scope="module")
def kin() -> OpwKinematics:
    return OpwKinematics.from_robot(ROBOT)


@pytest.fixture(scope="module")
def coarse_map(kin: OpwKinematics) -> ReachabilityMap:
    """Grobe Karte (150 mm, 15°) — schnell gebaut, dieselbe Build-Logik wie offline."""
    return ReachabilityMap.build(kin, cell_mm=150.0, n_alpha=13)


def _ik_reachable(kin: OpwKinematics, frame: Frame) -> bool:
    """Skalare OPW-IK als Ground Truth: irgendeine Lösung innerhalb der Achsgrenzen?"""
    return any(
        not s.unreachable and kin.in_limits(s.joints_rad) for s in kin.inverse(frame)
    )


def _node_coords(rmap: ReachabilityMap, iz: int, ia: int, ix: int, iy: int):
    m = int(round(rmap.extent_mm / rmap.cell_mm))
    return (
        (iz - m) * rmap.cell_mm,
        ia * rmap.alpha_step_rad,
        (ix - m) * rmap.cell_mm,
        (iy - m) * rmap.cell_mm,
    )


# --- Kanonisierung: Repräsentant-Pose ↔ Zellkoordinaten ------------------------


def test_canonical_roundtrip_at_nodes(coarse_map: ReachabilityMap) -> None:
    """canonical_coords(representative_frame(·)) reproduziert die Zellkoordinaten.

    Auch in den entarteten alpha-Fällen (0 und π, senkrechter Anflug): dort lässt
    die Kanonisierung den Versatz ungedreht — der Knoten trifft seine eigene Zelle.
    """
    rng = np.random.default_rng(210)
    shape = coarse_map.values.shape
    samples = [tuple(rng.integers(0, s) for s in shape) for _ in range(50)]
    samples += [(10, 0, 3, 7), (10, shape[1] - 1, 3, 7)]  # alpha = 0 und π explizit
    for iz, ia, ix, iy in samples:
        p_z, alpha, x_t, y_t = _node_coords(coarse_map, iz, ia, ix, iy)
        back = canonical_coords(representative_frame(p_z, alpha, x_t, y_t))
        assert back[0] == pytest.approx(p_z, abs=1e-9)
        assert back[1] == pytest.approx(alpha, abs=1e-7)
        assert back[2] == pytest.approx(x_t, abs=1e-6)
        assert back[3] == pytest.approx(y_t, abs=1e-6)


# --- Ground Truth: keine falschen Negative im Kartenraster ---------------------


def test_map_matches_scalar_opw_ik_at_raster_nodes(
    kin: OpwKinematics, coarse_map: ReachabilityMap
) -> None:
    """Stichproben-Gegenprüfung gegen die skalare OPW-IK als Ground Truth.

    An 400 gesampelten 4D-Knoten (deterministisch, Seed 210) muss die Karte der
    IK exakt entsprechen — **keine falschen Negative** (Vorfilter-Vertrag) und,
    weil der Build direkt-invers am Knoten auswertet, auch keine falschen
    Positive. Die Stichprobe muss beide Klassen enthalten, sonst prüft sie nichts.
    """
    rng = np.random.default_rng(210)
    shape = coarse_map.values.shape
    n_reachable = 0
    for _ in range(400):
        iz, ia, ix, iy = (int(rng.integers(0, s)) for s in shape)
        frame = representative_frame(*_node_coords(coarse_map, iz, ia, ix, iy))
        truth = _ik_reachable(kin, frame)
        mapped = coarse_map.is_reachable(frame)
        assert not (truth and not mapped), (
            f"Falsches Negativ am Knoten ({iz},{ia},{ix},{iy}): "
            "IK erreichbar, Karte sagt nein"
        )
        assert mapped == truth, (
            f"Falsches Positiv am Knoten ({iz},{ia},{ix},{iy}): "
            "Karte sagt erreichbar, IK nicht"
        )
        n_reachable += truth
    assert 0 < n_reachable < 400, "Stichprobe muss erreichbare UND unerreichbare Knoten enthalten"


def test_full_circle_precondition_is_enforced(kin: OpwKinematics) -> None:
    """Reduktions-Voraussetzung (Vollkreis-Limits außer J3) wird hart geprüft."""
    p = kin.params
    limits = list(p.joint_limits_rad)
    limits[0] = (-2.0, 2.0)  # J1 beschnitten → RM4D-Annahme 1 verletzt
    clamped = Kinematics(
        solver=p.solver,
        a_mm=p.a_mm,
        d_mm=p.d_mm,
        alpha_rad=p.alpha_rad,
        joint_limits_rad=tuple(limits),
    )
    with pytest.raises(ValueError, match="Vollkreis-Limits"):
        ReachabilityMap.build(OpwKinematics(clamped), cell_mm=300.0, n_alpha=5)


# --- Vorwärts ↔ invers: eine Struktur, zwei Leserichtungen ---------------------


def test_forward_and_inverse_query_are_consistent(coarse_map: ReachabilityMap) -> None:
    """Inversabfrage (Wandsystem) == Vorwärtsabfrage (Basissystem), Yaw 0.

    Der #201-Weg: ``flange_targets`` liefert Basis-Ziele + ``t_wall_base``;
    ``frames_in_wall`` hebt die Ziele ins Wandsystem, die Basisposition kommt aus
    der ADR-025-Naht ``base_position_in_wall``. Beide Leserichtungen der einen
    Karte müssen dasselbe sagen.
    """
    tool = ToolDef(
        name="testduese",
        tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )
    wall = WallSurface(length_mm=1200.0, height_mm=2400.0, thickness_mm=200.0)
    option = PlacementOption(
        option_id="test", lateral_mm=150.0, standoff_mm=600.0, stand_height_mm=0.0
    )
    targets = flange_targets(wall, tool, option, 400.0, nozzle_rotation(0.0, 0.0))
    wall_frames = frames_in_wall(targets.frames, targets.t_wall_base)
    bx, by, bz = base_position_in_wall(option, wall.thickness_mm)

    forward = [coarse_map.is_reachable(f) for f in targets.frames]
    inverse = [
        bool(coarse_map.base_positions(f, [(bx, by)], bz)[0]) for f in wall_frames
    ]
    assert forward == inverse
    assert any(forward) and not all(forward), "Fixture soll beide Klassen enthalten"
    assert coarse_map.reachable_fraction(targets.frames) == pytest.approx(
        sum(forward) / len(forward)
    )


# --- Minimum über Posenmengen (US 6) -------------------------------------------


def test_min_aggregation_over_pose_row(coarse_map: ReachabilityMap) -> None:
    """Min-Aggregation über eine konstruierte Höhenreihe (Düse senkrecht nach unten).

    Drei Posen auf einer Reihe (z = 1050 mm, x ∈ {−300, 0, 300}), Kandidaten-Basen
    auf y = 450 mm: das Aggregat ist das punktweise UND der Einzelabfragen; eine
    mittige Basis erreicht die ganze Reihe, eine seitliche Basis erreicht Pose A,
    fällt aber aus dem Aggregat (sonst hieße „erreichbar" mitten in der Reihe umsetzen).
    """
    row = [
        Frame(pos_mm=(x, 0.0, 1050.0), quat=DOWN_QUAT) for x in (-300.0, 0.0, 300.0)
    ]
    base_xy = np.array([(x, 450.0) for x in np.arange(-1200.0, 1201.0, 150.0)])
    agg = coarse_map.min_over_poses(row, base_xy, 0.0)
    singles = [coarse_map.base_positions(f, base_xy, 0.0) for f in row]

    expected = singles[0] & singles[1] & singles[2]
    assert np.array_equal(agg, expected)

    i_mid = int(np.where(base_xy[:, 0] == 0.0)[0][0])
    i_side = int(np.where(base_xy[:, 0] == -600.0)[0][0])
    assert agg[i_mid], "mittige Basis muss die ganze Reihe erreichen"
    assert singles[0][i_side], "seitliche Basis erreicht Pose A"
    assert not agg[i_side], "… fällt aber aus dem Reihen-Minimum"


def test_min_over_empty_pose_set_is_neutral(coarse_map: ReachabilityMap) -> None:
    assert coarse_map.min_over_poses([], [(0.0, 500.0)], 0.0).all()


# --- Artefakt + Provenienz (US 17) ---------------------------------------------


needs_artifact = pytest.mark.skipif(
    not (RM_DIR / rm.RM_MANIFEST_NAME).exists(), reason="Reichweitenkarten-Artefakt fehlt"
)


@needs_artifact
def test_committed_artifact_manifest_is_complete() -> None:
    m = json.loads((RM_DIR / rm.RM_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert m["robot"] == ROBOT
    assert m["rm_format_version"] == rm.RM_FORMAT_VERSION
    assert m["cell_mm"] == rm.DEFAULT_CELL_MM
    assert m["n_alpha"] == rm.DEFAULT_N_ALPHA
    assert m["generator"] == "core/scripts/build_reachability_map.py"
    robot = RobotDef.load(ROBOT)
    assert robot.kinematics is not None
    assert m["kinematics_sha256"] == kinematics_fingerprint(robot.kinematics)
    assert 0 < m["n_reachable"] < m["n_cells"]
    assert (RM_DIR / m["values_file"]).stat().st_size > 0


@needs_artifact
def test_committed_artifact_matches_ik_at_full_resolution_nodes(kin: OpwKinematics) -> None:
    """Mini-Abnahme am echten Artefakt: gesampelte Knoten der vollen Auflösung."""
    rmap = load_reachability_map(ROBOT)
    assert rmap.robot == ROBOT
    rng = np.random.default_rng(2100)
    shape = rmap.values.shape
    classes = set()
    for _ in range(40):
        iz, ia, ix, iy = (int(rng.integers(0, s)) for s in shape)
        frame = representative_frame(*_node_coords(rmap, iz, ia, ix, iy))
        truth = _ik_reachable(kin, frame)
        assert rmap.is_reachable(frame) == truth
        classes.add(truth)
    # Handverlesene Knoten-Posen, damit beide Klassen sicher vorkommen:
    near = Frame(pos_mm=(700.0, 0.0, 800.0), quat=DOWN_QUAT)  # vor der Basis
    far = Frame(pos_mm=(2000.0, 0.0, 800.0), quat=DOWN_QUAT)  # jenseits der Reichweite
    assert rmap.is_reachable(near) is True
    assert rmap.is_reachable(far) is False


# --- Provenienz-Fehlpfade (US 18) ------------------------------------------------


@pytest.fixture()
def fake_robots_dir(tmp_path, kin: OpwKinematics):
    """Miniatur-Katalog (schema-valide) + gültiges Karten-Artefakt für Fehlpfade."""
    robot = "testbot"
    robots = tmp_path / "robots"
    robots.mkdir()
    catalog = {
        "schema_version": "0.2",
        "name": robot,
        "reach_mm": 1300,
        "workspace": {"max_print_height_mm": 1000, "max_print_length_mm": 2000},
        "kinematics": {
            "solver": kin.params.solver,
            "a_mm": list(kin.params.a_mm),
            "d_mm": list(kin.params.d_mm),
            "alpha_rad": list(kin.params.alpha_rad),
            "joint_limits_rad": [list(p) for p in kin.params.joint_limits_rad],
        },
    }
    (robots / f"{robot}.json").write_text(json.dumps(catalog), encoding="utf-8")

    rmap = ReachabilityMap.build(kin, cell_mm=300.0, n_alpha=5)
    save_reachability_map(rmap, robot, kin.params, robots_dir=robots)
    return robots, robot, rm.reachability_dir(robot, robots)


def _patch_manifest(directory, **overrides) -> None:
    m = json.loads((directory / rm.RM_MANIFEST_NAME).read_text(encoding="utf-8"))
    m.update(overrides)
    (directory / rm.RM_MANIFEST_NAME).write_text(json.dumps(m), encoding="utf-8")


def test_valid_fake_artifact_loads_and_answers(fake_robots_dir) -> None:
    robots, robot, _ = fake_robots_dir
    rmap = load_reachability_map(robot, robots_dir=robots)
    assert rmap.robot == robot
    assert rmap.is_reachable(Frame(pos_mm=(600.0, 0.0, 600.0), quat=DOWN_QUAT))


def test_wrong_robot_provenance_fails(fake_robots_dir) -> None:
    robots, robot, directory = fake_robots_dir
    _patch_manifest(directory, robot="anderer_arm")
    with pytest.raises(ReachabilityProvenanceError, match="anderer_arm.*falsche Provenienz"):
        load_reachability_map(robot, robots_dir=robots)


def test_changed_catalog_kinematics_fails(fake_robots_dir) -> None:
    """Katalog-Kinematik seit dem Build geändert → Buildstand veraltet → klarer Fehler."""
    robots, robot, _ = fake_robots_dir
    path = robots / f"{robot}.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    catalog["kinematics"]["d_mm"][3] += 25.0  # anderer Arm — Karte wäre ein Falschfilter
    path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(ReachabilityProvenanceError, match="Kinematik.*geändert"):
        load_reachability_map(robot, robots_dir=robots)


def test_unsupported_format_version_fails(fake_robots_dir) -> None:
    robots, robot, directory = fake_robots_dir
    _patch_manifest(directory, rm_format_version=rm.RM_FORMAT_VERSION + 1)
    with pytest.raises(ReachabilityProvenanceError, match="Formatstand"):
        load_reachability_map(robot, robots_dir=robots)


def test_inconsistent_grid_shape_fails(fake_robots_dir) -> None:
    robots, robot, directory = fake_robots_dir
    _patch_manifest(directory, extent_mm=900.0)  # passt nicht mehr zur Gitterform
    with pytest.raises(ReachabilityProvenanceError, match="Gitterform"):
        load_reachability_map(robot, robots_dir=robots)


def test_missing_artifact_is_friendly(fake_robots_dir) -> None:
    robots, robot, directory = fake_robots_dir
    (directory / rm.RM_MANIFEST_NAME).unlink()
    with pytest.raises(FileNotFoundError, match="build_reachability_map.py"):
        load_reachability_map(robot, robots_dir=robots)
