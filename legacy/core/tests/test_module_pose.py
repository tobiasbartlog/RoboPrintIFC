"""Modul-Pose: Relativpose ↔ Lage des Moduls am Druckort (Issue #96, ADR-022).

Geprüft wird das reine Modul ``fgc.decompose.module_pose``: der Roundtrip
Relativpose ↔ Arbeitsflächen-Lage ist verlustfrei (auch mit gedrehten
Workstation-Frames), die Vorwärtsrechnung ist deterministisch und folgt der
ADR-006-Konvention (mm, Quaternionen [w, x, y, z]); das decompose-Artefakt
trägt die Lage **additiv** (ohne Posen byte-gleich wie bisher, Schema-valide).
Keine Kinematik, kein I/O — synthetische Frames/Platzierungen genügen.
"""

from __future__ import annotations

import json
import math

import pytest

from fgc import domain
from fgc.decompose import (
    DecompositionPlan,
    ModulePose,
    Section,
    SectionPlan,
    decompose_artifact,
    module_pose,
    placement_frame,
    placement_from_pose,
    pose_plan,
)
from fgc.domain.models import Frame
from fgc.placement import PlacementOption, WallSurface
from fgc.simulation.transform import quat_normalize

PROVENANCE = {
    "source": "test",
    "created": "2026-07-07T12:00:00Z",
    "git_commit": "0000000",
}


def _quat_z(angle_rad: float) -> tuple[float, float, float, float]:
    return (math.cos(angle_rad / 2.0), 0.0, 0.0, math.sin(angle_rad / 2.0))


def _quat_x(angle_rad: float) -> tuple[float, float, float, float]:
    return (math.cos(angle_rad / 2.0), math.sin(angle_rad / 2.0), 0.0, 0.0)


#: Nicht-triviale Workstation-Frames (ADR-021): Basis gedreht + versetzt,
#: Arbeitsfläche mit eigener Lage — der Roundtrip muss frame-unabhängig stimmen.
BASE_FRAME = Frame(pos_mm=(400.0, -250.0, 320.0), quat=_quat_z(math.radians(35.0)))
SURFACE_FRAME = Frame(pos_mm=(1150.0, 90.0, 20.0), quat=_quat_z(math.radians(-10.0)))

PLACEMENT = PlacementOption(
    option_id="platz-1",
    lateral_mm=120.0,
    standoff_mm=800.0,
    stand_height_mm=300.0,
    yaw_rad=0.3,
)

#: Moduldicke der synthetischen Teile — der Abstand misst ab der Modulflaeche
#: (Issue #160), die Naht rechnet +Dicke/2 auf die Modulmitte um.
THICKNESS_MM = 200.0


# --- Roundtrip Relativpose ↔ Arbeitsflächen-Lage (Akzeptanzkriterium) ----------


def test_roundtrip_relativpose_arbeitsflaechen_lage():
    """Vorwärts (Relativpose → Arbeitsflächen-Lage) und zurück ist verlustfrei —
    die Workstation-Frames kürzen sich in der Kette (ADR-022, Invertierung)."""
    pose = module_pose(PLACEMENT, BASE_FRAME, SURFACE_FRAME, thickness_mm=THICKNESS_MM)
    back = placement_from_pose(
        pose.on_surface, BASE_FRAME, SURFACE_FRAME, thickness_mm=THICKNESS_MM
    )
    assert back.lateral_mm == pytest.approx(PLACEMENT.lateral_mm, abs=1e-9)
    assert back.standoff_mm == pytest.approx(PLACEMENT.standoff_mm, abs=1e-9)
    assert back.stand_height_mm == pytest.approx(PLACEMENT.stand_height_mm, abs=1e-9)
    assert back.yaw_rad == pytest.approx(PLACEMENT.yaw_rad, abs=1e-12)


def test_roundtrip_with_tilted_base_frame():
    """Auch mit einer NICHT z-ausgerichteten Basis (gekippte Montagefläche) bleibt
    der Roundtrip exakt: T_modul←basis kürzt die Frames unabhängig von deren Lage."""
    tilted_base = Frame(pos_mm=(50.0, 900.0, 210.0), quat=_quat_x(math.radians(12.0)))
    pose = module_pose(PLACEMENT, tilted_base, SURFACE_FRAME, thickness_mm=THICKNESS_MM)
    back = placement_from_pose(
        pose.on_surface, tilted_base, SURFACE_FRAME, thickness_mm=THICKNESS_MM
    )
    assert back.lateral_mm == pytest.approx(PLACEMENT.lateral_mm, abs=1e-9)
    assert back.standoff_mm == pytest.approx(PLACEMENT.standoff_mm, abs=1e-9)
    assert back.stand_height_mm == pytest.approx(PLACEMENT.stand_height_mm, abs=1e-9)
    assert back.yaw_rad == pytest.approx(PLACEMENT.yaw_rad, abs=1e-12)


def test_roundtrip_zero_yaw_and_negative_values():
    placement = PlacementOption(
        "platz-x", lateral_mm=-75.5, standoff_mm=650.0, stand_height_mm=-40.0, yaw_rad=0.0
    )
    pose = module_pose(placement, BASE_FRAME, SURFACE_FRAME, thickness_mm=THICKNESS_MM)
    back = placement_from_pose(
        pose.on_surface, BASE_FRAME, SURFACE_FRAME, thickness_mm=THICKNESS_MM
    )
    assert back.lateral_mm == pytest.approx(-75.5, abs=1e-9)
    assert back.standoff_mm == pytest.approx(650.0, abs=1e-9)
    assert back.stand_height_mm == pytest.approx(-40.0, abs=1e-9)
    assert back.yaw_rad == pytest.approx(0.0, abs=1e-12)


# --- Konvention (ADR-006/022): mm, [w,x,y,z], Invertierung der Leserichtung ----


def test_identity_frames_simple_numbers():
    """Basis identitätsorientiert bei (0,0,300), Fläche bei (800,0,0) — das Modul
    liegt vor der Basis entlang deren −y-Achse, der Modulfuß auf Flächenhöhe.
    Abstand 800 misst ab der Modulfläche (Issue #160): der Modul-URSPRUNG
    (Modulmitte) liegt 800 + Dicke/2 = 900 mm vor der Basis."""
    base = Frame(pos_mm=(0.0, 0.0, 300.0))
    surface = Frame(pos_mm=(800.0, 0.0, 0.0))
    placement = PlacementOption(
        "platz-1", lateral_mm=0.0, standoff_mm=800.0, stand_height_mm=300.0
    )
    pose = module_pose(placement, base, surface, thickness_mm=THICKNESS_MM)
    # Workstation-Koordinaten: Modulmitte 900 mm vor der Basis (−y), Fuß bei z=0.
    assert pose.workstation.pos_mm == pytest.approx((0.0, -900.0, 0.0), abs=1e-9)
    assert pose.workstation.quat == pytest.approx((1.0, 0.0, 0.0, 0.0), abs=1e-12)
    # Arbeitsflächen-Lage: dieselbe Pose relativ zur Fläche.
    assert pose.on_surface.pos_mm == pytest.approx((-800.0, -900.0, 0.0), abs=1e-9)
    assert pose.on_surface.quat == pytest.approx((1.0, 0.0, 0.0, 0.0), abs=1e-12)


def test_yaw_inverts_reading_direction():
    """yaw dreht die Relativpose um die Hochachse — invertiert gelesen trägt das
    Modul die GEGENdrehung (Quaternion [w,x,y,z], ADR-006)."""
    base = Frame(pos_mm=(0.0, 0.0, 0.0))
    surface = Frame(pos_mm=(0.0, 0.0, 0.0))
    yaw = math.pi / 2.0
    placement = PlacementOption(
        "platz-1", lateral_mm=0.0, standoff_mm=500.0, stand_height_mm=0.0, yaw_rad=yaw
    )
    # Dicke 0 (unbekannt): die Naht degeneriert zu y = standoff — hier bewusst,
    # damit die Rotations-Zahlen einfach bleiben (Issue #160).
    pose = module_pose(placement, base, surface, thickness_mm=0.0)
    expected = _quat_z(-yaw)
    assert quat_normalize(pose.workstation.quat) == pytest.approx(expected, abs=1e-12)
    # Position: −R_z(−yaw)·(0, 500, 0) = (−500, 0, 0).
    assert pose.workstation.pos_mm == pytest.approx((-500.0, 0.0, 0.0), abs=1e-9)


def test_placement_frame_matches_evaluate_convention():
    """placement_frame ist dieselbe Konvention wie fgc.placement.evaluate
    (Basis-Position über die eine Naht base_position_in_wall, Issue #160:
    y = Dicke/2 + Abstand) — nur als Quaternion-Frame."""
    f = placement_frame(PLACEMENT, THICKNESS_MM)
    assert f.pos_mm == (120.0, 900.0, 300.0)
    assert f.quat == pytest.approx(_quat_z(0.3), abs=1e-12)


# --- Determinismus + pose_plan --------------------------------------------------


def test_module_pose_is_deterministic():
    a = module_pose(PLACEMENT, BASE_FRAME, SURFACE_FRAME, thickness_mm=THICKNESS_MM)
    b = module_pose(PLACEMENT, BASE_FRAME, SURFACE_FRAME, thickness_mm=THICKNESS_MM)
    assert a == b
    assert json.dumps(a.to_dict()) == json.dumps(b.to_dict())


def _two_section_plan() -> DecompositionPlan:
    wall = WallSurface(length_mm=1600.0, height_mm=1200.0, thickness_mm=200.0)
    p1 = PlacementOption("platz-1", 0.0, 800.0, 300.0)
    p2 = PlacementOption("platz-2", 0.0, 950.0, 300.0)  # Teil mit Override (#94)
    s1 = Section("abschnitt-1", 1, -800.0, 0.0, 0.0, 1200.0)
    s2 = Section("abschnitt-2", 2, 0.0, 800.0, 0.0, 1200.0)
    return DecompositionPlan(
        kind="modul",
        wall=wall,
        cuts=(),
        sections=(SectionPlan(s1, p1), SectionPlan(s2, p2)),
        n_length=2,
        n_height=1,
    )


def test_pose_plan_maps_each_section_from_its_placement():
    plan = _two_section_plan()
    poses = pose_plan(plan, BASE_FRAME, SURFACE_FRAME)
    assert set(poses) == {"abschnitt-1", "abschnitt-2"}
    # Teil 2 hat einen anderen Abstand (Override) → eigene Lage.
    assert poses["abschnitt-1"].workstation != poses["abschnitt-2"].workstation
    for sp in plan.sections:
        expected = module_pose(
            sp.placement, BASE_FRAME, SURFACE_FRAME,
            thickness_mm=plan.wall.thickness_mm,
        )
        assert poses[sp.section.section_id] == expected


# --- Artefakt: additiv + Schema-Vertrag -----------------------------------------


def _statuses(plan: DecompositionPlan):
    from fgc.decompose.evaluate import SectionStatus

    return [
        SectionStatus(
            section_id=sp.section.section_id,
            order=sp.section.order,
            reachable=True,
            reachable_fraction=1.0,
            n_samples=4,
            n_reachable=4,
            kinematic_margin=0.5,
            mean_margin=0.6,
            warnings=[],
        )
        for sp in plan.sections
    ]


def test_artifact_carries_module_pose_additively_and_validates():
    plan = _two_section_plan()
    statuses = _statuses(plan)
    poses = pose_plan(plan, BASE_FRAME, SURFACE_FRAME)
    artifact = decompose_artifact(
        "doosan_m1013", "testduese", plan, statuses, PROVENANCE, module_poses=poses
    )
    domain.validate(artifact, "decompose")
    for section in artifact["sections"]:
        pose = section["module_pose"]
        assert set(pose) == {"workstation", "on_surface"}
        for frame in pose.values():
            assert len(frame["pos_mm"]) == 3
            assert len(frame["quat"]) == 4  # [w, x, y, z] (ADR-006)


def test_artifact_without_poses_stays_byte_identical():
    """Ohne Posen (kein Frame-Paar an der Workstation / Art 'abschnitt') bleibt
    das Artefakt byte-gleich wie vor Issue #96 — kein module_pose-Feld."""
    plan = _two_section_plan()
    statuses = _statuses(plan)
    with_none = decompose_artifact(
        "doosan_m1013", "testduese", plan, statuses, PROVENANCE, module_poses=None
    )
    legacy_signature = decompose_artifact(
        "doosan_m1013", "testduese", plan, statuses, PROVENANCE
    )
    assert json.dumps(with_none, sort_keys=True) == json.dumps(
        legacy_signature, sort_keys=True
    )
    assert all("module_pose" not in s for s in with_none["sections"])
    domain.validate(with_none, "decompose")


def test_module_pose_to_dict_shape():
    pose = ModulePose(
        workstation=Frame(pos_mm=(1.0, 2.0, 3.0)),
        on_surface=Frame(pos_mm=(4.0, 5.0, 6.0)),
    )
    d = pose.to_dict()
    assert d == {
        "workstation": {"pos_mm": [1.0, 2.0, 3.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "on_surface": {"pos_mm": [4.0, 5.0, 6.0], "quat": [1.0, 0.0, 0.0, 0.0]},
    }
