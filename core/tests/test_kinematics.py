"""Kinematik-Kern Doosan M1013: FK/IK und das 1000-Posen-Orakel (ADR-009a).

Der Roundtrip FK→IK→FK ist der dauerhafte Test aus Spike S3: zufällige
Gelenkkonfigurationen → FK → IK → FK, jede erreichbare Lösung muss die
Ausgangspose innerhalb der festgenagelten Toleranzen reproduzieren
(Position < 0,01 mm, Orientierung < 1e-6 rad).

Die automatisierte Stichprobe meidet die Handgelenks-Singularität (Achse 5 nahe
0/±π): dort sind Achse 4 und 6 gekoppelt, der Solver wählt eine gültige, aber
nicht frame-exakte Auslage. Diese Nähe ist bewusst der HITL-/Grasshopper-Punkt
aus S3 bzw. Aufgabe der Konfig-/Singularitätswahl (Issue #11), nicht dieses
Orakels.
"""

import math

import numpy as np
import pytest

from fgc.domain.models import Frame
from fgc.kinematics import OpwKinematics, frame_distance

# Toleranzen aus dem Spike-Protokoll S3 festgenagelt.
POS_TOL_MM = 0.01
ORI_TOL_RAD = 1e-6

# Rand des Handgelenks-Singularitätsbandes (Achse 5): deutlich über der
# Solver-Schwelle 1,24e-2 rad, damit der exakte (nicht-singuläre) IK-Zweig greift.
WRIST_MARGIN_RAD = 0.1


@pytest.fixture(scope="module")
def kin() -> OpwKinematics:
    return OpwKinematics.from_robot("doosan_m1013")


def _sample_joints(rng: np.random.Generator) -> np.ndarray:
    """Zufällige, nicht-singuläre Gelenkkonfiguration innerhalb der Achsgrenzen."""
    q = rng.uniform(-math.pi + 1e-3, math.pi - 1e-3, size=6)
    # Achse 5 aus dem Singularitätsband heraushalten (|q5| ∈ [margin, π-margin]).
    mag = rng.uniform(WRIST_MARGIN_RAD, math.pi - WRIST_MARGIN_RAD)
    q[4] = mag if rng.random() < 0.5 else -mag
    return q


# ---------------------------------------------------------------------------
# Vorwärtskinematik — Grundeigenschaften
# ---------------------------------------------------------------------------


def test_from_robot_loads_kinematics(kin: OpwKinematics):
    """Die Doosan-Definition trägt 6-Achs-OPW-Parameter (ADR-006-Einheiten)."""
    assert kin.params.solver == "opw"
    assert kin.params.n_joints == 6
    assert kin.params.d_mm[0] == pytest.approx(152.5)  # Basishöhe c1


def test_forward_returns_unit_quaternion(kin: OpwKinematics):
    frame = kin.forward([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    norm = math.sqrt(sum(v * v for v in frame.quat))
    assert norm == pytest.approx(1.0, abs=1e-12)


def test_forward_within_reach(kin: OpwKinematics):
    """Der Flansch liegt für beliebige Winkel innerhalb der Kettenlänge (Σ a+d)."""
    reach = sum(kin.params.a_mm) + sum(kin.params.d_mm)
    rng = np.random.default_rng(0)
    for _ in range(50):
        q = rng.uniform(-math.pi, math.pi, size=6)
        frame = kin.forward(q)
        assert math.dist(frame.pos_mm, (0.0, 0.0, 0.0)) < reach + 1e-6


# ---------------------------------------------------------------------------
# Inverskinematik — Struktur
# ---------------------------------------------------------------------------


def test_link_frames_length_and_base(kin: OpwKinematics):
    """link_frames liefert 7 Frames; Basis ist die Identität."""
    frames = kin.link_frames([0.2, -0.4, 0.7, 0.1, 0.8, -0.3])
    assert len(frames) == 7
    assert frames[0].pos_mm == (0.0, 0.0, 0.0)
    assert frames[0].quat == (1.0, 0.0, 0.0, 0.0)


def test_link_frames_flange_matches_forward(kin: OpwKinematics):
    """Das letzte Glied-Frame ist exakt der Flansch aus forward() (Konsistenz)."""
    rng = np.random.default_rng(7)
    for _ in range(50):
        q = rng.uniform(-math.pi, math.pi, size=6)
        flange = kin.forward(q)
        last = kin.link_frames(q)[-1]
        pos, ori = frame_distance(flange, last)
        assert pos < 1e-9
        # ori = 2·acos(dot): nahe dot=1 ist der kleinste darstellbare Wert ≠ 0
        # bereits ~4·10⁻⁸ (float64-Auflösung der Formel). 1e-12 war unterhalb
        # dieser Grenze und bestand nur, wenn dot zufällig exakt 1.0 traf
        # (Windows-BLAS) — auf Linux 1 ulp daneben ⇒ 2,98·10⁻⁸. 1e-6 fängt jede
        # echte Orientierungsabweichung, ist aber plattformrobust. Design-Log 2026-07-10.
        assert ori < 1e-6


def test_inverse_returns_eight_configurations(kin: OpwKinematics):
    frame = kin.forward([0.2, -0.4, 0.7, 0.1, 0.8, -0.3])
    sols = kin.inverse(frame)
    assert len(sols) == 8
    assert {s.configuration for s in sols} == set(range(8))


def test_inverse_recovers_original_joints(kin: OpwKinematics):
    """Mindestens eine Lösung reproduziert die Ausgangswinkel (mod Konfiguration)."""
    q = [0.2, -0.4, 0.7, 0.1, 0.8, -0.3]
    frame = kin.forward(q)
    sols = kin.inverse(frame)
    best = min(
        max(abs(a - b) for a, b in zip(s.joints_rad, q, strict=True))
        for s in sols
        if not s.unreachable
    )
    assert best < 1e-6


# ---------------------------------------------------------------------------
# Das 1000-Posen-Orakel (ADR-009a) — dauerhafter Roundtrip FK→IK→FK
# ---------------------------------------------------------------------------


def test_roundtrip_1000_poses(kin: OpwKinematics):
    """FK→IK→FK für 1000 Zufallsposen: jede erreichbare Lösung frame-exakt."""
    rng = np.random.default_rng(20260704)
    n = 1000
    max_pos = 0.0
    max_ori = 0.0
    for i in range(n):
        q = _sample_joints(rng)
        target = kin.forward(q)

        sols = kin.inverse(target)
        valid = [s for s in sols if not s.unreachable]
        assert valid, f"Pose {i}: keine erreichbare IK-Lösung"

        matched = False
        for s in valid:
            pos, ori = frame_distance(target, kin.forward(s.joints_rad))
            if pos < POS_TOL_MM and ori < ORI_TOL_RAD:
                matched = True
            max_pos = max(max_pos, pos)
            max_ori = max(max_ori, ori)
        # Der Roundtrip verlangt, dass jede zurückgegebene erreichbare Lösung
        # die Zielpose reproduziert (nicht-singuläre Stichprobe → exakter Zweig).
        assert matched, f"Pose {i}: keine Lösung innerhalb Toleranz"

    # Toleranzen aus S3 mit großem Abstand eingehalten (analytisch ~1e-9).
    assert max_pos < POS_TOL_MM
    assert max_ori < ORI_TOL_RAD


def test_roundtrip_all_valid_solutions_exact(kin: OpwKinematics):
    """Schärfer: bei nicht-singulären Posen sind ALLE erreichbaren Lösungen exakt."""
    rng = np.random.default_rng(1)
    for _ in range(100):
        q = _sample_joints(rng)
        target = kin.forward(q)
        for s in kin.inverse(target):
            if s.unreachable:
                continue
            pos, ori = frame_distance(target, kin.forward(s.joints_rad))
            assert pos < POS_TOL_MM
            assert ori < ORI_TOL_RAD


def test_frame_distance_zero_for_equal_frames():
    f = Frame(pos_mm=(10.0, 20.0, 30.0), quat=(1.0, 0.0, 0.0, 0.0))
    pos, ori = frame_distance(f, f)
    assert pos == pytest.approx(0.0)
    assert ori == pytest.approx(0.0)
