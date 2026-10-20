"""Konfigurationswahl, Achsgrenzen und Singularitätsnähe (Issue #11, Strang B).

Prüft die Schicht über dem FK/IK-Kern (Issue #7): deterministische, bahnstetige
Auswahl einer Gelenklösung aus mehrdeutigen IK-Lösungen, Erkennung
unfahrbarer Targets (Arbeitsraum / Achsgrenzen) und das Singularitätsnähe-Maß
mit Warnschwelle. Das 1000-Posen-Orakel aus #7 lebt weiter in
``test_kinematics.py`` und bleibt unberührt.
"""

import dataclasses
import math

import numpy as np
import pytest

from fgc.domain.models import Frame
from fgc.kinematics import (
    DEFAULT_SINGULARITY_WARN,
    IkConfigFilter,
    OpwKinematics,
    joint_distance,
    select_along_path,
)
from fgc.kinematics.opw import ELBOW, SHOULDER, WRIST

WRIST_MARGIN_RAD = 0.1


@pytest.fixture(scope="module")
def kin() -> OpwKinematics:
    return OpwKinematics.from_robot("doosan_m1013")


def _sample_joints(rng: np.random.Generator) -> np.ndarray:
    """Zufällige, nicht-singuläre Gelenkkonfiguration (analog Orakel #7)."""
    q = rng.uniform(-math.pi + 1e-3, math.pi - 1e-3, size=6)
    mag = rng.uniform(WRIST_MARGIN_RAD, math.pi - WRIST_MARGIN_RAD)
    q[4] = mag if rng.random() < 0.5 else -mag
    return q


# ---------------------------------------------------------------------------
# Jacobi-Matrix und Singularitätsnähe-Maß
# ---------------------------------------------------------------------------


def test_jacobian_shape(kin: OpwKinematics):
    jac = kin.jacobian([0.2, -0.4, 0.7, 0.1, 0.8, -0.3])
    assert jac.shape == (6, 6)


def test_jacobian_matches_finite_differences(kin: OpwKinematics):
    """Die geometrische Jacobi-Matrix stimmt mit der numerischen FK-Ableitung.

    Translationsanteil gegen zentrale Differenzen der Flanschposition; der
    Rotationsanteil gegen die aus der Rotationsmatrix-Ableitung gewonnene
    Winkelgeschwindigkeit (schiefsymmetrischer Anteil von dR·Rᵀ).
    """
    q = np.array([0.3, -0.5, 0.6, 0.2, 0.7, -0.4])
    jac = kin.jacobian(q)
    eps = 1e-6
    for i in range(6):
        dq = np.zeros(6)
        dq[i] = eps
        tp = kin.forward_matrix(q + dq)
        tm = kin.forward_matrix(q - dq)
        dpos = (tp[:3, 3] - tm[:3, 3]) / (2 * eps)
        assert np.allclose(jac[:3, i], dpos, atol=1e-3)
        dr = (tp[:3, :3] - tm[:3, :3]) / (2 * eps)
        w_hat = dr @ tp[:3, :3].T
        omega = np.array([w_hat[2, 1], w_hat[0, 2], w_hat[1, 0]])
        assert np.allclose(jac[3:, i], omega, atol=1e-3)


def test_singularity_measure_in_unit_range(kin: OpwKinematics):
    rng = np.random.default_rng(3)
    for _ in range(200):
        q = _sample_joints(rng)
        m = kin.singularity_measure(q)
        assert 0.0 <= m <= 1.0 + 1e-9


def test_singularity_measure_drops_towards_wrist_singularity(kin: OpwKinematics):
    """Je näher Achse 5 an 0, desto kleiner das Maß; bei j5=0 praktisch singulär."""
    prev = None
    for j5 in [0.5, 0.2, 0.1, 0.05, 0.02]:
        m = kin.singularity_measure([0.2, -0.4, 0.7, 0.1, j5, -0.3])
        if prev is not None:
            assert m < prev
        prev = m
    assert kin.singularity_measure([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]) < 1e-6


# ---------------------------------------------------------------------------
# Konfigurationswahl — Determinismus und Bahnstetigkeit
# ---------------------------------------------------------------------------


def test_selection_is_deterministic(kin: OpwKinematics):
    """Gleiche Bahn → identische Lösungsfolge über Läufe hinweg."""
    rng = np.random.default_rng(7)
    frames = [kin.forward(_sample_joints(rng)) for _ in range(20)]
    a = select_along_path(kin, frames)
    b = select_along_path(kin, frames)
    assert [t.joints_rad for t in a.targets] == [t.joints_rad for t in b.targets]
    assert [t.configuration for t in a.targets] == [t.configuration for t in b.targets]


def test_selection_is_path_continuous(kin: OpwKinematics):
    """Stetige Bahn → konstante Konfiguration, keine Sprünge; Winkel recovern.

    Erzeugt eine glatte Gelenktrajektorie (fernab der Singularität), rechnet die
    zugehörigen Frames und lässt die Auswahl daraus zurückschließen. Erwartet:
    dieselbe Konfiguration an allen Targets und die Original-Gelenkwinkel zurück.
    """
    q0 = np.array([0.1, -0.3, 0.5, 0.2, 0.8, -0.2])
    q1 = np.array([0.6, -0.1, 0.9, 0.5, 1.1, 0.3])
    n = 40
    traj = [q0 + (q1 - q0) * (k / (n - 1)) for k in range(n)]
    frames = [kin.forward(q) for q in traj]

    sol = select_along_path(kin, frames, seed=q0)
    assert sol.drivable
    configs = {t.configuration for t in sol.targets}
    assert len(configs) == 1  # keine Konfigurationssprünge
    for t, q in zip(sol.targets, traj, strict=True):
        assert joint_distance(t.joints_rad, q) < 1e-6
    # Benachbarte Targets liegen im Gelenkraum eng beieinander.
    for prev, cur in zip(sol.targets, sol.targets[1:], strict=False):
        assert joint_distance(prev.joints_rad, cur.joints_rad) < 0.2
    assert sol.warnings == []


def test_seed_steers_first_configuration(kin: OpwKinematics):
    """Unterschiedliche Seeds können am Startpunkt verschiedene Konfigs wählen,
    bleiben aber jeweils in sich stetig — hier über die Recovery-Eigenschaft
    geprüft: mit dem erzeugenden q als Seed kommt genau dieses q zurück."""
    q = np.array([0.4, -0.6, 0.8, -1.2, 0.9, 2.0])
    frame = kin.forward(q)
    sol = select_along_path(kin, [frame], seed=q)
    assert sol.targets[0].drivable
    assert joint_distance(sol.targets[0].joints_rad, q) < 1e-6


# ---------------------------------------------------------------------------
# Achsgrenzen und Arbeitsraum — unfahrbare Targets
# ---------------------------------------------------------------------------


def test_target_outside_workspace_is_unreachable(kin: OpwKinematics):
    frame = Frame(pos_mm=(5000.0, 5000.0, 5000.0), quat=(1.0, 0.0, 0.0, 0.0))
    sol = select_along_path(kin, [frame])
    assert not sol.drivable
    assert sol.targets[0].joints_rad is None
    assert [w.kind for w in sol.warnings] == ["unreachable"]


def test_joint_limit_violation_makes_target_undrivable(kin: OpwKinematics):
    """Erreichbare Pose, aber alle Lösungen außerhalb künstlich enger Grenzen."""
    tight = dataclasses.replace(
        kin.params,
        joint_limits_rad=tuple((-0.05, 0.05) for _ in range(6)),
    )
    kin_tight = OpwKinematics(tight)
    frame = kin.forward([0.2, -0.4, 0.7, 0.1, 0.8, -0.3])
    sol = select_along_path(kin_tight, [frame])
    assert not sol.drivable
    assert sol.targets[0].joints_rad is None
    assert [w.kind for w in sol.warnings] == ["joint_limits"]


def test_j3_limit_rejects_out_of_range_solution(kin: OpwKinematics):
    """Die echte J3-Grenze (±160°) verwirft Lösungen jenseits ±2,79 rad."""
    # Eine Pose, deren erzeugende Konfiguration J3 innerhalb der Grenze hält,
    # bleibt fahrbar; die Grenzprüfung selbst ist über in_limits abgedeckt.
    assert kin.in_limits([0.0, 0.0, 2.7, 0.0, 0.5, 0.0])
    assert not kin.in_limits([0.0, 0.0, 3.0, 0.0, 0.5, 0.0])


def test_undrivable_target_midpath_keeps_continuity(kin: OpwKinematics):
    """Ein unfahrbares Target in der Mitte bricht die Bahn nicht ab."""
    q0 = np.array([0.1, -0.3, 0.5, 0.2, 0.8, -0.2])
    q1 = np.array([0.3, -0.2, 0.6, 0.3, 0.9, 0.0])
    reachable = [kin.forward(q0), kin.forward(q1)]
    bad = Frame(pos_mm=(6000.0, 0.0, 0.0), quat=(1.0, 0.0, 0.0, 0.0))
    frames = [reachable[0], bad, reachable[1]]
    sol = select_along_path(kin, frames, seed=q0)
    assert [t.drivable for t in sol.targets] == [True, False, True]
    # Der Vorgängerbezug überlebt die Lücke: dieselbe Konfiguration vor und nach
    # dem unfahrbaren Target, und beide Endwinkel werden exakt zurückgewonnen.
    assert sol.targets[0].configuration == sol.targets[2].configuration
    assert joint_distance(sol.targets[0].joints_rad, q0) < 1e-6
    assert joint_distance(sol.targets[2].joints_rad, q1) < 1e-6


# ---------------------------------------------------------------------------
# Singularitätswarnung
# ---------------------------------------------------------------------------


def test_singularity_near_pose_warns(kin: OpwKinematics):
    q = [0.2, -0.4, 0.7, 0.1, 0.02, -0.3]  # Achse 5 im Singularitätsband
    frame = kin.forward(q)
    sol = select_along_path(kin, [frame], seed=q)
    assert sol.targets[0].singularity_measure < DEFAULT_SINGULARITY_WARN
    assert "singularity" in [w.kind for w in sol.warnings]
    warn = next(w for w in sol.warnings if w.kind == "singularity")
    assert warn.value is not None and warn.value < DEFAULT_SINGULARITY_WARN


def test_non_singular_pose_does_not_warn(kin: OpwKinematics):
    q = [0.3, -0.5, 0.6, 0.2, 0.9, -0.4]
    frame = kin.forward(q)
    sol = select_along_path(kin, [frame], seed=q)
    assert sol.targets[0].singularity_measure > DEFAULT_SINGULARITY_WARN
    assert sol.warnings == []


# ---------------------------------------------------------------------------
# Wählbare IK-Konfiguration — harter Filter (Issue #129, ADR-024)
# ---------------------------------------------------------------------------


def test_auto_filter_is_bit_identical_regression(kin: OpwKinematics):
    """REGRESSIONSANKER: auto/auto/auto (=None) wählt bit-identisch wie ohne Filter.

    Der kritische Nicht-Regressions-Beweis (Acceptance): eine gemischte Bahn ohne
    Filter, mit ``None`` und mit einem all-auto ``IkConfigFilter`` liefert Ziel für
    Ziel dieselben Gelenkwinkel, Konfigurationen und Warnungen.
    """
    rng = np.random.default_rng(11)
    frames = [kin.forward(_sample_joints(rng)) for _ in range(25)]

    base = select_along_path(kin, frames)
    none = select_along_path(kin, frames, config_filter=None)
    auto = select_along_path(kin, frames, config_filter=IkConfigFilter())

    for other in (none, auto):
        assert [t.joints_rad for t in other.targets] == [t.joints_rad for t in base.targets]
        assert [t.configuration for t in other.targets] == [t.configuration for t in base.targets]
        assert other.warnings == base.warnings


def test_filter_hard_excludes_non_matching_configs(kin: OpwKinematics):
    """Gesetzte Bits filtern HART: die gewählte Konfiguration erfüllt jede Vorgabe."""
    rng = np.random.default_rng(4)
    frames = [kin.forward(_sample_joints(rng)) for _ in range(15)]
    # Ellbogen auf Zustand B (Bit gesetzt) fixieren.
    sol = select_along_path(kin, frames, config_filter=IkConfigFilter(elbow=True))
    for t in sol.targets:
        if t.drivable:
            assert t.configuration & ELBOW  # Bit gesetzt = Zustand B
    # Umgekehrt Zustand A (Bit gelöscht).
    sol_a = select_along_path(kin, frames, config_filter=IkConfigFilter(elbow=False))
    for t in sol_a.targets:
        if t.drivable:
            assert not (t.configuration & ELBOW)


def test_filter_unreachable_config_warns_not_gates(kin: OpwKinematics):
    """Eine fahrbare Pose, deren erzeugende Konfig die Vorgabe verletzt ⇒ Warnung.

    Erzeugt eine Pose aus einer bekannten Konfiguration und verlangt bei allen drei
    Achsen das jeweils GEGENTEILIGE Bit. Wenn kein anderer Zweig dieselbe Pose unter
    der Vorgabe erreicht, ist der Punkt *unter der Vorgabe unerreichbar*: Warnung
    ``ik_config`` + Target ohne Gelenklösung (kein Gate, US 14).
    """
    q = [0.4, -0.6, 0.8, -1.2, 0.9, 2.0]
    frame = kin.forward(q)
    # Die erzeugende Konfiguration ermitteln.
    sol_auto = select_along_path(kin, [frame], seed=q)
    cfg = sol_auto.targets[0].configuration
    assert cfg is not None
    # Alle drei Achsen auf das Gegenteil zwingen ⇒ genau diese Konfig ist verboten;
    # ist keine Alternativ-Lösung zulässig, wird der Punkt unter der Vorgabe unerreichbar.
    opposite = IkConfigFilter(
        shoulder=not (cfg & SHOULDER),
        elbow=not (cfg & ELBOW),
        wrist=not (cfg & WRIST),
    )
    sol = select_along_path(kin, [frame], seed=q, config_filter=opposite)
    kinds = [w.kind for w in sol.warnings]
    if not sol.targets[0].drivable:
        assert "ik_config" in kinds
        assert sol.targets[0].joints_rad is None
    else:
        # Falls doch ein anderer Zweig die Pose erfüllt, muss er die Vorgabe halten.
        assert opposite.allows(sol.targets[0].configuration)


def test_filter_allows_predicate_matches_bit_scheme():
    """``allows`` prüft genau das opw-Bitschema (Schulter/Ellbogen/Handgelenk)."""
    assert IkConfigFilter().is_auto
    assert IkConfigFilter().allows(7)  # auto lässt alles zu
    only_wrist_b = IkConfigFilter(wrist=True)
    assert not only_wrist_b.is_auto
    assert only_wrist_b.allows(WRIST)  # Bit gesetzt
    assert not only_wrist_b.allows(0)  # Bit fehlt
    # from_block: "a" → Bit gelöscht (False), "b" → Bit gesetzt (True), fehlend → auto.
    f = IkConfigFilter.from_block({"shoulder": "b", "elbow": "a"})
    assert f.shoulder is True and f.elbow is False and f.wrist is None
    assert f.allows(SHOULDER) and not f.allows(SHOULDER | ELBOW)
    assert IkConfigFilter.from_block(None).is_auto
    assert IkConfigFilter.from_block({}).is_auto
