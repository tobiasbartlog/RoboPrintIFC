"""Tests für das 3-Punkt-Antastverfahren und fgc setup new (ADR-006, §9.3).

Abdeckung:
- Identitäts-Orientation (keine Rotation)
- Frame-Roundtrip: bekannte Lage → drei Posen → rekonstruierte Lage
- Degenerierte Eingaben: identische Punkte, kollineare Punkte
- Schema-Validierung: setup_artifact + domain.validate
- CLI-Integration: fgc setup new schreibt gültige setup.json
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from fgc import domain
from fgc.pipeline import cli
from fgc.setup import (
    PROVISIONAL_DEADTIME,
    PROVISIONAL_IO_CHANNELS,
    PROVISIONAL_TCP,
    setup_artifact,
    three_point_frame,
)
from fgc.setup.frame3p import _rot_to_quat

# Toleranzen für den Roundtrip-Test
POS_TOL_MM = 1e-9  # floating-point-exakt, kein Messfehler im Test
QUAT_TOL = 1e-9


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _quat_angle_diff(q1: list[float], q2: list[float]) -> float:
    """Winkelabstand zweier Einheitsquaternionen in Radiant.

    Berücksichtigt, dass q und -q dieselbe Rotation darstellen.
    """
    q1 = np.asarray(q1)
    q2 = np.asarray(q2)
    dot = abs(float(np.dot(q1, q2)))
    dot = min(dot, 1.0)  # numerische Absicherung
    return 2.0 * math.acos(dot)


def _frame_from_rotation(R: np.ndarray, p0: np.ndarray, d: float = 300.0):
    """Leitet aus bekannter Rotationsmatrix und Ursprung die drei Antastposen ab."""
    p1 = p0 + d * R[:, 0]  # Punkt auf X-Achse
    p2 = p0 + d * R[:, 1]  # Punkt in XY-Ebene (Y-Richtung)
    return p0, p1, p2


# ---------------------------------------------------------------------------
# Grundlegende Geometrie-Tests
# ---------------------------------------------------------------------------


def test_identity_orientation():
    """Kein-Rotations-Fall: X=Basis-X, Y=Basis-Y → Identitäts-Quaternion."""
    p0 = [1000.0, 500.0, 0.0]
    p1 = [1200.0, 500.0, 0.0]  # +X
    p2 = [1000.0, 700.0, 0.0]  # +Y

    pos_mm, quat = three_point_frame(p0, p1, p2)

    assert pos_mm == pytest.approx(p0, abs=POS_TOL_MM)
    # Identitäts-Quaternion: [1, 0, 0, 0] oder [-1, 0, 0, 0]
    angle = _quat_angle_diff(quat, [1.0, 0.0, 0.0, 0.0])
    assert angle == pytest.approx(0.0, abs=QUAT_TOL)


def test_z_up_orientation():
    """Wandebene in XZ: X=Basis-X, Y=Basis-Z → Z=Basis-Y (Wandnormale)."""
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([100.0, 0.0, 0.0])   # X-Achse = Basis-X
    p2 = np.array([0.0, 0.0, 100.0])   # XY-Ebene in X-Z-Richtung → Y_hat = Basis-Z

    pos_mm, quat = three_point_frame(p0, p1, p2)

    # Rekonstruierte Rotation: Spalten [X, Y, Z] des Rahmens
    # X=[1,0,0], Y=[0,0,1], Z=X×Y=[1,0,0]×[0,0,1]=[0*1-0*0,0*0-1*1,1*0-0*0]=[-1,0,0]
    # Warte — Z = X × Y = [1,0,0] × [0,0,1] = [0·1−0·0, 0·0−1·1, 1·0−0·0] = [0,−1,0]
    # Also R = [[1,0,0],[0,0,-1],[0,1,0]]
    # Quaternion für diese Rotation prüfen wir per Winkelabstand zur erwarteten Matrix
    R_expected = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)
    q_expected = _rot_to_quat(R_expected)
    angle = _quat_angle_diff(quat, q_expected)
    assert angle == pytest.approx(0.0, abs=QUAT_TOL)


# ---------------------------------------------------------------------------
# Frame-Roundtrip-Tests: bekannte Lage → Posen → Rekonstruktion
# ---------------------------------------------------------------------------


def test_roundtrip_90_deg_y_rotation():
    """90° Rotation um Y-Achse: X→−Basis-Z, Y→Basis-Y, Z→Basis-X."""
    angle = math.pi / 2
    c, s = math.cos(angle), math.sin(angle)
    # R_y(90°) = [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]
    R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    p0 = np.array([800.0, 200.0, 500.0])
    expected_quat = _rot_to_quat(R)

    origin, p1, p2 = _frame_from_rotation(R, p0)
    pos_mm, quat = three_point_frame(origin, p1, p2)

    assert list(pos_mm) == pytest.approx(list(p0), abs=POS_TOL_MM)
    angle_err = _quat_angle_diff(quat, expected_quat)
    assert angle_err == pytest.approx(0.0, abs=QUAT_TOL)


def test_roundtrip_45_deg_z_rotation():
    """45° Rotation um Z-Achse: diagonale Wand, häufiger realer Fall."""
    angle = math.pi / 4
    c, s = math.cos(angle), math.sin(angle)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    p0 = np.array([1000.0, 500.0, 0.0])
    expected_quat = _rot_to_quat(R)

    origin, p1, p2 = _frame_from_rotation(R, p0)
    pos_mm, quat = three_point_frame(origin, p1, p2)

    assert list(pos_mm) == pytest.approx(list(p0), abs=POS_TOL_MM)
    angle_err = _quat_angle_diff(quat, expected_quat)
    assert angle_err == pytest.approx(0.0, abs=QUAT_TOL)


def test_roundtrip_arbitrary_rotation():
    """Beliebige Rotation (nicht an Hauptachsen ausgerichtet) — allgemeiner Fall."""
    # Rotation 30° um die Achse [1, 1, 1]/√3
    ax = np.array([1.0, 1.0, 1.0]) / math.sqrt(3)
    a = math.pi / 6  # 30°
    # Rodrigues'sche Formel → Quaternion direkt
    q_expected = [math.cos(a / 2), *(math.sin(a / 2) * ax)]

    # Rotation aus Quaternion
    w, qx, qy, qz = q_expected
    R = np.array([
        [1 - 2*(qy**2 + qz**2), 2*(qx*qy - qz*w), 2*(qx*qz + qy*w)],
        [2*(qx*qy + qz*w), 1 - 2*(qx**2 + qz**2), 2*(qy*qz - qx*w)],
        [2*(qx*qz - qy*w), 2*(qy*qz + qx*w), 1 - 2*(qx**2 + qy**2)],
    ])

    p0 = np.array([500.0, 300.0, 100.0])
    origin, p1, p2 = _frame_from_rotation(R, p0, d=150.0)
    pos_mm, quat = three_point_frame(origin, p1, p2)

    assert list(pos_mm) == pytest.approx(list(p0), abs=POS_TOL_MM)
    angle_err = _quat_angle_diff(quat, q_expected)
    assert angle_err == pytest.approx(0.0, abs=1e-8)


# ---------------------------------------------------------------------------
# Degenerierte Eingaben
# ---------------------------------------------------------------------------


def test_identical_p0_p1_raises():
    """Identische Punkte P0=P1 → ValueError mit verständlicher Meldung."""
    with pytest.raises(ValueError, match="P0 und P1 sind identisch"):
        three_point_frame([0, 0, 0], [0, 0, 0], [0, 100, 0])


def test_identical_p0_p2_raises():
    """Identische Punkte P0=P2 → ValueError mit verständlicher Meldung."""
    with pytest.raises(ValueError, match="P0 und P2 sind identisch"):
        three_point_frame([0, 0, 0], [100, 0, 0], [0, 0, 0])


def test_collinear_points_raise():
    """Kollineare Punkte (P2 auf der X-Achse) → ValueError."""
    # P0, P1, P2 alle auf der X-Achse
    with pytest.raises(ValueError, match="kollinear"):
        three_point_frame([0, 0, 0], [100, 0, 0], [200, 0, 0])


def test_collinear_points_nearly_on_axis_raise():
    """P2 fast auf der X-Achse (sehr kleiner Restabstand) → ValueError."""
    p2 = [200.0, 1e-8, 0.0]  # winzige Y-Abweichung < 1e-6 mm nach Gram-Schmidt
    with pytest.raises(ValueError, match="kollinear"):
        three_point_frame([0, 0, 0], [100, 0, 0], p2)


def test_p1_very_close_to_p0_raises():
    """P1 zu nah an P0 (unter 1e-6 mm) → ValueError."""
    with pytest.raises(ValueError, match="P0 und P1"):
        three_point_frame([0, 0, 0], [1e-7, 0, 0], [0, 100, 0])


# ---------------------------------------------------------------------------
# Schema-Validierung
# ---------------------------------------------------------------------------

PROVENANCE = {
    "source": "test",
    "created": "2026-07-04T10:00:00Z",
    "git_commit": "0000000",
}

FRAME_IDENTITY = {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}


def test_setup_artifact_validates():
    """setup_artifact() liefert ein schema-valides Dict."""
    artifact = setup_artifact(
        robot="doosan_m1013",
        wall_to_base={"pos_mm": [1000.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        tcp=PROVISIONAL_TCP,
        io_channels=PROVISIONAL_IO_CHANNELS,
        deadtime=PROVISIONAL_DEADTIME,
        provenance=PROVENANCE,
    )
    domain.validate(artifact, "setup")  # kein Fehler = Erfolg


def test_setup_artifact_with_computed_frame():
    """setup_artifact mit gerechneten Posen validiert ebenfalls."""
    pos_mm, quat = three_point_frame([1000, 0, 0], [1200, 0, 0], [1000, 0, 200])
    artifact = setup_artifact(
        robot="doosan_m1013",
        wall_to_base={"pos_mm": pos_mm, "quat": quat},
        tcp=PROVISIONAL_TCP,
        io_channels=PROVISIONAL_IO_CHANNELS,
        deadtime=PROVISIONAL_DEADTIME,
        provenance=PROVENANCE,
    )
    domain.validate(artifact, "setup")


# ---------------------------------------------------------------------------
# CLI-Integration
# ---------------------------------------------------------------------------


def test_cli_setup_new_writes_valid_setup(tmp_path):
    """fgc setup new --p0 --p1 --p2 schreibt schema-validiertes setup.json."""
    output = tmp_path / "setup.json"
    rc = cli.main(
        [
            "setup", "new",
            "--p0", "1000,500,0",
            "--p1", "1200,500,0",
            "--p2", "1000,700,0",
            "--robot", "doosan_m1013",
            "--output", str(output),
        ]
    )
    assert rc == 0
    assert output.exists()

    artifact = json.loads(output.read_text(encoding="utf-8"))
    domain.validate(artifact, "setup")

    # wall_to_base: Ursprung korrekt
    assert artifact["wall_to_base"]["pos_mm"] == pytest.approx([1000.0, 500.0, 0.0], abs=1e-6)
    # Keine Rotation (X=Basis-X, Y=Basis-Y) → Identitätsquaternion
    angle = _quat_angle_diff(artifact["wall_to_base"]["quat"], [1.0, 0.0, 0.0, 0.0])
    assert angle == pytest.approx(0.0, abs=1e-9)

    # Provisorische Werte ohne --template
    assert artifact["deadtime"]["provisional"] is True
    assert artifact["robot"] == "doosan_m1013"
    assert "pump_a" in artifact["io_channels"]


def test_cli_setup_new_with_template(tmp_path):
    """--template überträgt TCP/IO/Totzeit aus Vorlage auf neue wall_to_base."""
    tmpl = {
        "schema_version": "0.1",
        "provenance": PROVENANCE,
        "robot": "doosan_m1013",
        "wall_to_base": {"pos_mm": [1000.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "tcp": {"pos_mm": [0.0, 0.0, 150.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "io_channels": {
            "pump_a": {"kind": "analog_voltage", "index": 0, "physical_range": [0, 10]},
            "pump_b": {"kind": "analog_voltage", "index": 1, "physical_range": [0, 10]},
            "foam": {"kind": "analog_voltage", "index": 2, "physical_range": [0, 5]},
        },
        "deadtime": {"t_tot_s": 2.5, "compensation": "simulation_shift", "provisional": True},
    }
    tmpl_path = tmp_path / "template.json"
    # wall_to_base wird aus 3 Posen überschrieben — alle anderen Felder übernommen
    tmpl_path.write_text(json.dumps(tmpl), encoding="utf-8")

    output = tmp_path / "setup_new.json"
    rc = cli.main(
        [
            "setup", "new",
            "--p0", "500,0,0",
            "--p1", "600,0,0",
            "--p2", "500,100,0",
            "--template", str(tmpl_path),
            "--output", str(output),
        ]
    )
    assert rc == 0
    artifact = json.loads(output.read_text(encoding="utf-8"))
    domain.validate(artifact, "setup")

    # wall_to_base aus Posen, nicht aus Vorlage
    assert artifact["wall_to_base"]["pos_mm"] == pytest.approx([500.0, 0.0, 0.0], abs=1e-6)
    # TCP aus Vorlage (make_setup setzt FRAME_IDENTITY als tcp)
    assert artifact["tcp"] == tmpl["tcp"]
    # Totzeit aus Vorlage
    assert artifact["deadtime"]["t_tot_s"] == tmpl["deadtime"]["t_tot_s"]


def test_cli_setup_new_collinear_fails(tmp_path, capsys):
    """Kollineare Posen führen zu Rückgabe 1 und Fehlermeldung auf stderr."""
    output = tmp_path / "setup.json"
    rc = cli.main(
        [
            "setup", "new",
            "--p0", "0,0,0",
            "--p1", "100,0,0",
            "--p2", "200,0,0",   # kollinear
            "--output", str(output),
        ]
    )
    assert rc == 1
    assert not output.exists()
    captured = capsys.readouterr()
    assert "kollinear" in captured.err.lower() or "kollinear" in captured.err


def test_cli_setup_new_identical_p0_p1_fails(tmp_path, capsys):
    """Identische P0/P1 führen zu Rückgabe 1."""
    output = tmp_path / "setup.json"
    rc = cli.main(
        [
            "setup", "new",
            "--p0", "0,0,0",
            "--p1", "0,0,0",
            "--p2", "0,100,0",
            "--output", str(output),
        ]
    )
    assert rc == 1


def test_cli_setup_new_invalid_pose_format_fails(tmp_path, capsys):
    """Ungültiges Pose-Format (kein x,y,z) führt zu Rückgabe 1."""
    output = tmp_path / "setup.json"
    rc = cli.main(
        [
            "setup", "new",
            "--p0", "nicht_eine_pose",
            "--p1", "100,0,0",
            "--p2", "0,100,0",
            "--output", str(output),
        ]
    )
    assert rc == 1
