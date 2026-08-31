"""Typ-Klassifikation der Singularitätsnähe (Issue #65, Scheibe 6 — AC 1).

Synthetische Posen ⇒ korrekter Typ: eine flache Handgelenksachse (J5≈0) ⇒
Handgelenk, ein gestreckter Arm ⇒ Ellbogen, die Handwurzel über der Basisachse
⇒ Schulter. Rein aus den Gelenkwinkeln, aufbauend auf dem vorhandenen reziproken
Konditionsmaß (Issue #11) — kein neues Skalarmaß.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from fgc.kinematics import OpwKinematics, classify
from fgc.kinematics.singularity import SingularityAssessment

#: Handgelenks-nah: J5 (joints[4]) = 0 ⇒ Achsen J4∥J6 koppeln.
WRIST_POSE = [0.3, -0.5, 0.6, 0.2, 0.0, -0.4]
#: Ellbogen gestreckt: J3 an der Streckung (Schulter→Handwurzel ≈ Oberarm+Unterarm).
ELBOW_POSE = [0.0, 0.0, 1.5, 0.0, 0.8, 0.0]
#: Schulter: Handwurzel über der Basis-Drehachse z0 (radialer Abstand minimal).
SHOULDER_POSE = [0.0, -1.3, 1.0, 0.0, 0.8, 0.0]
#: Gut konditioniert (weit von jeder Singularität).
GENERIC_POSE = [0.3, -0.5, 0.6, 0.2, 0.8, -0.4]


@pytest.fixture(scope="module")
def kin() -> OpwKinematics:
    return OpwKinematics.from_robot("doosan_m1013")


def test_wrist_pose_classified_wrist(kin: OpwKinematics):
    a = classify(kin, WRIST_POSE)
    assert a.dominant == "wrist"
    assert a.near  # J5≈0 ist singularitätsnah
    assert a.wrist_severity == pytest.approx(1.0, abs=1e-6)


def test_elbow_pose_classified_elbow(kin: OpwKinematics):
    a = classify(kin, ELBOW_POSE)
    assert a.dominant == "elbow"
    assert a.near
    assert a.elbow_severity > a.wrist_severity
    assert a.elbow_severity > a.shoulder_severity


def test_shoulder_pose_classified_shoulder(kin: OpwKinematics):
    a = classify(kin, SHOULDER_POSE)
    assert a.dominant == "shoulder"
    assert a.near
    assert a.shoulder_severity > a.elbow_severity
    assert a.shoulder_severity > a.wrist_severity


def test_generic_pose_not_near(kin: OpwKinematics):
    a = classify(kin, GENERIC_POSE)
    assert not a.near
    assert a.measure > 0.01


def test_severities_in_unit_range(kin: OpwKinematics):
    rng = np.random.default_rng(7)
    for _ in range(100):
        q = rng.uniform(-math.pi, math.pi, size=6)
        a = classify(kin, q)
        for s in (a.wrist_severity, a.elbow_severity, a.shoulder_severity):
            assert 0.0 <= s <= 1.0
        assert a.dominant in ("wrist", "elbow", "shoulder")


def test_measure_is_reused_not_reinvented(kin: OpwKinematics):
    """Die Nähe bleibt das Konditionsmaß aus Issue #11 (kein neues Skalar)."""
    for q in (WRIST_POSE, ELBOW_POSE, SHOULDER_POSE, GENERIC_POSE):
        a = classify(kin, q)
        assert a.measure == kin.singularity_measure(q)


def test_classify_returns_assessment_dataclass(kin: OpwKinematics):
    a = classify(kin, GENERIC_POSE)
    assert isinstance(a, SingularityAssessment)
    assert set(a.severities) == {"wrist", "elbow", "shoulder"}


def test_wrong_shape_raises(kin: OpwKinematics):
    with pytest.raises(ValueError, match="6 Gelenkwinkel"):
        classify(kin, [0.0, 0.0, 0.0])
