"""Simulation / Trajectory (Issue #12, Strang C, ADR-012).

Deckt die PRD-Invarianten ab:
- Zeitreihe streng monoton; Achsgeschwindigkeits-/-beschleunigungsgrenzen
  eingehalten (aus der zeitparametrierten Gelenkfolge nachgerechnet).
- io-Shift um −t_tot nachweisbar; bei nativer Vorlauf-Kompensation unterbleibt er;
  `meta.io_compensated` korrekt.
- Druckzeitschätzung + Achsauslastung in `meta`; Kinematik-Warnungen in
  `meta.warnings`.
- Schema-Validität und CLI-Integration (fgc simulate schreibt trajectory.json).

Die Toolpaths werden synthetisch aus FK einer glatten, nicht-singulären
Gelenkbahn gebaut (garantiert erreichbar) — kein IFC/ifcopenshell nötig.
"""

from __future__ import annotations

import json

import pytest

from fgc import domain
from fgc.domain.models import Frame
from fgc.kinematics import OpwKinematics
from fgc.pipeline import cli
from fgc.simulation import build_trajectory, transform
from fgc.simulation.timeparam import node_accelerations, segment_velocities

# Toleranz für die Grenz-Invarianten (numerische Marge über der harten Grenze).
RATIO_TOL = 1e-6

PROVENANCE = {
    "source": "test",
    "created": "2026-07-04T10:00:00Z",
    "git_commit": "0000000",
}
IDENTITY = {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}


@pytest.fixture(scope="module")
def kin() -> OpwKinematics:
    return OpwKinematics.from_robot("doosan_m1013")


def _smooth_joints(n: int = 15) -> list[list[float]]:
    """Glatte, nicht-singuläre Gelenkbahn innerhalb der Achsgrenzen."""
    q0 = [0.1, -0.5, 0.8, 0.2, 0.9, -0.3]
    step = [0.03, 0.02, -0.02, 0.01, 0.02, 0.015]
    return [[q0[j] + i * step[j] for j in range(6)] for i in range(n)]


def _targets_from_joints(
    kin: OpwKinematics,
    joints: list[list[float]],
    *,
    io_on_from: int | None = None,
    v_mm_s: float = 100.0,
) -> list[dict]:
    """Baut Toolpath-Target-Dicts aus FK der Gelenkbahn (Frames = Flansch = Düse)."""
    targets = []
    for i, q in enumerate(joints):
        frame: Frame = kin.forward(q)
        on = io_on_from is not None and i >= io_on_from
        targets.append(
            {
                "frame": frame.to_dict(),
                "v_mm_s": v_mm_s,
                "io": {"pump_a": 1.0 if on else 0.0},
                "kind": "print",
                "layer": 0,
                "segment_id": f"S{i:03d}",
            }
        )
    return targets


def _setup(compensation: str = "none", t_tot_s: float = 0.0) -> dict:
    """Identitäts-Setup (wall_to_base = tcp = Identität) mit gegebener Totzeit."""
    return {
        "schema_version": "0.1",
        "provenance": PROVENANCE,
        "robot": "doosan_m1013",
        "wall_to_base": IDENTITY,
        "tcp": IDENTITY,
        "io_channels": {
            "pump_a": {"kind": "analog_voltage", "index": 0, "physical_range": [0, 10]},
        },
        "deadtime": {"t_tot_s": t_tot_s, "compensation": compensation, "provisional": True},
    }


# ---------------------------------------------------------------------------
# Schema-Validität + Grundstruktur
# ---------------------------------------------------------------------------


def test_trajectory_is_schema_valid(kin):
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin)
    domain.validate(traj.to_artifact(PROVENANCE), "trajectory")
    # Bewegungsmodell (Issue #62) verdichtet movel-Geraden: mind. ein Sample je
    # Target, i. d. R. mehr (Zwischenposen entlang der kartesischen Geraden).
    assert len(traj.samples) >= len(targets)
    assert len(traj.meta["axis_utilization"]) == 6


def test_pose_source_defaults_to_measured(kin):
    """Ohne Angabe stammt die Lage aus dem gemessenen Setup (Issue #26)."""
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin)
    assert traj.meta["pose_source"] == "measured"
    domain.validate(traj.to_artifact(PROVENANCE), "trajectory")


def test_pose_source_planned_is_recorded_in_meta(kin):
    """Simulation aus der Platzierung vermerkt die Lagequelle „geplant" (Issue #26)."""
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin, pose_source="planned")
    assert traj.meta["pose_source"] == "planned"
    domain.validate(traj.to_artifact(PROVENANCE), "trajectory")


def test_base_frame_equals_inverse_wall_to_base(kin):
    """meta.base_frame = Roboterbasis im Wandsystem = invert(wall_to_base) (Issue #66).

    Fester Replay-Anker (ADR-007): der Viewer verankert den Arm damit an der
    geplanten Lage. Über alle Targets konstant (ein Wert im meta-Block).
    """
    import math

    # Nicht-triviales Setup: Basis 900 mm vor der Wand, 200 mm hoch, um 30° gedreht.
    yaw = math.pi / 6
    base_in_wall = Frame(
        pos_mm=(150.0, 900.0, 200.0),
        quat=(math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)),
    )
    wall_to_base = transform.invert(base_in_wall)
    setup = _setup()
    setup["wall_to_base"] = {
        "pos_mm": list(wall_to_base.pos_mm),
        "quat": list(wall_to_base.quat),
    }

    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, setup, kin, pose_source="planned")
    domain.validate(traj.to_artifact(PROVENANCE), "trajectory")

    bf = traj.meta["base_frame"]
    for got, exp in zip(bf["pos_mm"], base_in_wall.pos_mm, strict=True):
        assert got == pytest.approx(exp, abs=1e-6)
    for got, exp in zip(bf["quat"], base_in_wall.quat, strict=True):
        assert got == pytest.approx(exp, abs=1e-9)


def test_base_frame_present_for_identity_setup(kin):
    """Auch das Identitäts-Setup trägt ein base_frame (== Identität) — Altläufe."""
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin)
    bf = traj.meta["base_frame"]
    assert bf["pos_mm"] == [0.0, 0.0, 0.0]
    assert bf["quat"] == pytest.approx([1.0, 0.0, 0.0, 0.0])


def test_duration_equals_last_sample_time(kin):
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin)
    assert traj.meta["duration_s"] == pytest.approx(traj.samples[-1]["t_s"])
    assert traj.meta["duration_s"] > 0.0  # Druckzeitschätzung


# ---------------------------------------------------------------------------
# Zeit-Invarianten: strenge Monotonie, v/a-Grenzen
# ---------------------------------------------------------------------------


def test_time_series_strictly_monotonic(kin):
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin)
    ts = [s["t_s"] for s in traj.samples]
    assert all(b > a for a, b in zip(ts, ts[1:], strict=False))


def test_velocity_limits_respected(kin):
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin)
    joints = [tuple(s["joints_rad"]) for s in traj.samples]
    ts = [s["t_s"] for s in traj.samples]
    dt = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    vel = segment_velocities(joints, dt)
    v_max = kin.params.joint_velocity_limits_rad_s
    for seg in vel:
        for j in range(6):
            assert abs(seg[j]) <= v_max[j] * (1 + RATIO_TOL)


def test_acceleration_limits_respected(kin):
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin)
    joints = [tuple(s["joints_rad"]) for s in traj.samples]
    ts = [s["t_s"] for s in traj.samples]
    dt = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    acc = node_accelerations(segment_velocities(joints, dt), dt)
    a_max = kin.params.joint_acceleration_limits_rad_s2
    for node in acc:
        for j in range(6):
            assert abs(node[j]) <= a_max[j] * (1 + RATIO_TOL)


def test_axis_utilization_bounded(kin):
    targets = _targets_from_joints(kin, _smooth_joints())
    traj = build_trajectory(targets, _setup(), kin)
    for u in traj.meta["axis_utilization"]:
        assert 0.0 <= u <= 1.0


# ---------------------------------------------------------------------------
# io-Totzeitkompensation (ADR-012)
# ---------------------------------------------------------------------------


def _io_onset_time(traj) -> float:
    """Zeitpunkt (t_s) des ersten Samples mit io an — dichteunabhängig (Issue #62)."""
    return next(s["t_s"] for s in traj.samples if s["io"]["pump_a"] > 0)


def test_io_shift_moves_onset_earlier(kin):
    """simulation_shift: io-Einschalten liegt um ~t_tot vor der Geometrie."""
    joints = _smooth_joints()
    k = len(joints) // 2
    targets = _targets_from_joints(kin, joints, io_on_from=k)

    native = build_trajectory(targets, _setup("none"), kin)
    t_geo = _io_onset_time(native)  # geometrischer Einschaltzeitpunkt
    t_tot = 0.3 * t_geo  # spannt mehrere Samples, bleibt < t_geo

    shifted = build_trajectory(targets, _setup("simulation_shift", t_tot), kin)
    assert shifted.meta["io_compensated"] is True

    onset_t = _io_onset_time(shifted)
    assert onset_t < t_geo                        # zeitlich vorgezogen
    assert onset_t >= t_geo - t_tot - 1e-6        # nicht weiter als t_tot vor


def test_native_lookahead_leaves_io_unshifted(kin):
    """native_lookahead: kein Shift, io_compensated = false, Onset unverändert."""
    joints = _smooth_joints()
    k = len(joints) // 2
    targets = _targets_from_joints(kin, joints, io_on_from=k)

    ref = build_trajectory(targets, _setup("none"), kin)
    traj = build_trajectory(targets, _setup("native_lookahead", 1.0), kin)
    assert traj.meta["io_compensated"] is False
    assert _io_onset_time(traj) == pytest.approx(_io_onset_time(ref))  # nicht vorgezogen


def test_compensation_none_leaves_io_unshifted(kin):
    joints = _smooth_joints()
    k = len(joints) // 2
    targets = _targets_from_joints(kin, joints, io_on_from=k)
    ref = build_trajectory(targets, _setup("none"), kin)
    traj = build_trajectory(targets, _setup("none", 1.0), kin)
    assert traj.meta["io_compensated"] is False
    assert _io_onset_time(traj) == pytest.approx(_io_onset_time(ref))


# ---------------------------------------------------------------------------
# Kinematik-Warnungen landen in meta.warnings
# ---------------------------------------------------------------------------


def test_unreachable_target_lands_in_warnings(kin):
    joints = _smooth_joints(3)
    targets = _targets_from_joints(kin, joints)
    # mittleres Target weit ausserhalb des Arbeitsraums → unreachable
    targets[1]["frame"] = {"pos_mm": [5000.0, 5000.0, 5000.0], "quat": [1.0, 0.0, 0.0, 0.0]}
    traj = build_trajectory(targets, _setup(), kin)
    domain.validate(traj.to_artifact(PROVENANCE), "trajectory")
    assert traj.meta["warnings"]
    assert traj.meta["warnings"][0]["kind"] in ("reach", "joint_limit", "singularity")


# ---------------------------------------------------------------------------
# CLI-Integration: fgc simulate schreibt trajectory.json in den Lauf
# ---------------------------------------------------------------------------


def test_cli_simulate_writes_valid_trajectory(kin, tmp_path):
    run_dir = tmp_path / "20260704-run_slice"
    run_dir.mkdir()
    targets = _targets_from_joints(kin, _smooth_joints(), io_on_from=7)
    toolpath = {
        "schema_version": "0.2",
        "provenance": PROVENANCE,
        "wall_global_id": "TESTWALL0000000000000",
        "targets": targets,
        "summary": {"n_layers": 1, "n_targets": len(targets), "n_print": len(targets)},
    }
    domain.validate(toolpath, "toolpath")
    (run_dir / "toolpath.json").write_text(json.dumps(toolpath), encoding="utf-8")

    setup_path = tmp_path / "setup.json"
    setup = _setup("simulation_shift", 0.5)
    domain.validate(setup, "setup")
    setup_path.write_text(json.dumps(setup), encoding="utf-8")

    rc = cli.main(["simulate", "--run", str(run_dir), "--setup", str(setup_path)])
    assert rc == 0

    traj_path = run_dir / "trajectory.json"
    assert traj_path.exists()
    artifact = json.loads(traj_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "trajectory")
    assert artifact["meta"]["io_compensated"] is True
    assert artifact["meta"]["duration_s"] > 0.0


def test_cli_simulate_missing_toolpath_fails(tmp_path, capsys):
    run_dir = tmp_path / "empty_run"
    run_dir.mkdir()
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(_setup()), encoding="utf-8")
    rc = cli.main(["simulate", "--run", str(run_dir), "--setup", str(setup_path)])
    assert rc == 1


def test_cli_simulate_unknown_run_fails(tmp_path):
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(_setup()), encoding="utf-8")
    rc = cli.main(["simulate", "--run", str(tmp_path / "nope"), "--setup", str(setup_path)])
    assert rc == 1
