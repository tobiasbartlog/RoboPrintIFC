"""Singularitäts-Advisor: Hebel je Typ + Kipp verbessert die Marge (Issue #65, AC 2).

Prüft das externe Verhalten des deep module ``fgc.placement.advisor``:
- Handgelenks-Platzierung ⇒ Kipp-Hebel, und der angewandte Kipp-Delta hebt die
  kinematische Marge in der **Neubewertung** (dieselbe ``placement.evaluate``)
  nachweisbar an (Kern-Acceptance).
- Gestreckt/Reichweite ⇒ Platzierungs-Hebel; konfig-abhängig/Schulter ⇒ Config-Flip.
- Ist die Platzierung unkritisch, gibt der Advisor keinen Vorschlag.

Synthetische, reproduzierbare Wand-/Platzierungs-Fixtures (wie test_placement).
"""

from __future__ import annotations

import dataclasses

import pytest

from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.kinematics import IkConfigFilter, config_to_block
from fgc.kinematics.opw import ELBOW, SHOULDER, WRIST
from fgc.placement import PlacementOption, WallSurface, advise
from fgc.placement.advisor import (
    AdvisorContext,
    Suggestion,
    assess,
    suggestion_for,
    worst_reachable,
)

ROBOT = "doosan_m1013"

#: Handgelenks-Fixture: kompakte Wand + mäßiger Abstand/Podest — die schlechteste
#: erreichte Pose landet im Handgelenks-Zweig (J5≈0, verifiziert in Scheibe-6-Spike).
WRIST_WALL = WallSurface(length_mm=600.0, height_mm=700.0, thickness_mm=200.0)
WRIST_OPTION = PlacementOption("wrist", lateral_mm=0.0, standoff_mm=500.0, stand_height_mm=300.0)

#: Ellbogen-Fixture: breite, hohe Wand mit tiefer/ferner Basis — der Arm streckt
#: sich am Reichweitenrand (Ellbogen dominiert die schlechteste Pose).
ELBOW_WALL = WallSurface(length_mm=2000.0, height_mm=800.0, thickness_mm=200.0)
ELBOW_OPTION = PlacementOption("elbow", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=900.0)


@pytest.fixture(scope="module")
def robot() -> RobotDef:
    return RobotDef.load(ROBOT)


@pytest.fixture(scope="module")
def tool() -> ToolDef:
    return ToolDef(
        name="testduese",
        tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )


def _ctx(robot, tool, wall, option) -> AdvisorContext:
    return AdvisorContext(robot=robot, tool=tool, wall=wall, option=option)


# --- Kipp-Hebel: Kern-Acceptance (Marge steigt in der Neubewertung) ----------


def test_wrist_placement_yields_kipp_lever(robot, tool):
    ctx = _ctx(robot, tool, WRIST_WALL, WRIST_OPTION)
    result = assess(ctx)
    assert result is not None
    assessment, _worst = result
    assert assessment.dominant == "wrist"

    suggestion = advise(ctx)
    assert suggestion is not None
    assert suggestion.lever == "kipp"
    assert suggestion.kipp_delta_deg is not None and suggestion.kipp_delta_deg != 0.0


def test_applied_kipp_improves_margin_in_reevaluation(robot, tool):
    """AC 2: der vom Advisor vorgeschlagene Kipp-Delta hebt die kinematische Marge
    in der Neubewertung (dieselbe ``placement.evaluate``) nachweisbar an."""
    ctx = _ctx(robot, tool, WRIST_WALL, WRIST_OPTION)
    suggestion = advise(ctx)
    assert suggestion is not None and suggestion.lever == "kipp"
    # Vorher/Nachher aus dem Vorschlag …
    assert suggestion.improves
    assert suggestion.margin_after > suggestion.margin_before

    # … und unabhängig nachgerechnet: dasselbe evaluate mit dem angewandten Kipp
    # liefert eine bessere (min-)Marge, ohne den erreichbaren Anteil zu senken.
    import math

    before = ctx.score()
    after = ctx.score(kipp_rad=ctx.kipp_rad + math.radians(suggestion.kipp_delta_deg))
    assert after.kinematic_margin > before.kinematic_margin
    assert after.reachable_fraction >= before.reachable_fraction - 1e-9
    assert after.kinematic_margin == pytest.approx(suggestion.margin_after, abs=1e-9)


# --- Platzierungs-Hebel (Ellbogen/Reichweite) --------------------------------


def test_elbow_placement_yields_placement_lever(robot, tool):
    ctx = _ctx(robot, tool, ELBOW_WALL, ELBOW_OPTION)
    result = assess(ctx)
    assert result is not None
    assessment, _worst = result
    assert assessment.dominant == "elbow"

    suggestion = advise(ctx)
    assert suggestion is not None
    assert suggestion.lever == "placement"
    assert suggestion.placement is not None


# --- Config-Flip-Hebel (Schulter/konfig-abhängig): Dispatch-je-Typ ------------


def test_shoulder_type_yields_config_flip_lever(robot, tool):
    """``suggestion_for`` bildet den Schulter-Typ auf den Config-Flip-Hebel ab
    (Hebel-je-Typ isoliert, mit einem synthetischen Schulter-Assessment).

    Issue #200: der Vorschlag trägt den persistierbaren a/b-Block (kein opw-Bitfeld
    mehr) und fixiert die Schulter auf den **anderen** Zweig als die schlechteste Pose.
    """
    ctx = _ctx(robot, tool, WRIST_WALL, WRIST_OPTION)
    worst = worst_reachable(ctx)
    assert worst is not None
    base = assess(ctx)[0]
    shoulder_assessment = dataclasses.replace(base, dominant="shoulder")

    suggestion = suggestion_for(ctx, shoulder_assessment, worst)
    assert isinstance(suggestion, Suggestion)
    assert suggestion.lever == "config_flip"
    assert suggestion.sing_type == "shoulder"

    # a/b-Block statt rohem opw-Bitfeld: nur die Schulter fixiert, Zweig in {a, b}.
    assert suggestion.ik_config is not None
    assert set(suggestion.ik_config) == {"shoulder"}
    target = suggestion.ik_config["shoulder"]
    assert target in ("a", "b")
    # … und zwar der *andere* Zweig als der der schlechtesten Pose (echter Flip).
    current = config_to_block(worst.configuration)["shoulder"]
    assert target != current

    # Vorher/Nachher-Marge ist bahn-weit (dieselbe evaluate über die Bahn), nicht
    # der Ein-Pose-Wert der schlechtesten Pose.
    assert suggestion.margin_before is not None
    assert suggestion.margin_after is not None


def test_config_flip_payload_form_matches_collision_advisor(robot, tool):
    """AC #200: a/b-Block + write-Nutzlast in genau der Form des Kollisions-Advisors
    (`{"setter": "process-params", "ik_config": block}`); kein opw-Bitfeld mehr."""
    ctx = _ctx(robot, tool, WRIST_WALL, WRIST_OPTION)
    worst = worst_reachable(ctx)
    base = assess(ctx)[0]
    suggestion = suggestion_for(
        ctx, dataclasses.replace(base, dominant="shoulder"), worst
    )
    block = suggestion.ik_config

    assert suggestion.write == {"setter": "process-params", "ik_config": block}
    d = suggestion.to_dict()
    assert d["ik_config"] == block
    assert d["write"] == {"setter": "process-params", "ik_config": block}
    assert "config" not in d  # das rohe opw-Bitfeld ist entfallen


def test_config_to_block_roundtrips_with_from_block():
    """Übersetzung beide Richtungen (Issue #200): `config_to_block` ist die
    Gegenrichtung zu `IkConfigFilter.from_block` und schließt sauber."""
    for c in range(8):  # alle 3 Bits (Schulter/Ellbogen/Handgelenk)
        block = config_to_block(c)
        assert set(block) == {"shoulder", "elbow", "wrist"}
        assert all(v in ("a", "b") for v in block.values())
        filt = IkConfigFilter.from_block(block)
        # Der volle Block fixiert alle drei Bits → nur genau diese Konfiguration.
        assert filt.allows(c)
        for other in range(8):
            if other != c:
                assert not filt.allows(other)
    # Bit-Zuordnung explizit: gesetztes Bit → "b", gelöschtes → "a".
    assert config_to_block(0) == {"shoulder": "a", "elbow": "a", "wrist": "a"}
    assert config_to_block(SHOULDER) == {"shoulder": "b", "elbow": "a", "wrist": "a"}
    assert config_to_block(SHOULDER | ELBOW | WRIST) == {
        "shoulder": "b", "elbow": "b", "wrist": "b",
    }


# --- Kein Vorschlag, wenn unkritisch -----------------------------------------


def test_no_suggestion_when_margin_above_threshold(robot, tool):
    """advise_below=0 ⇒ nie unter der Schwelle ⇒ kein Vorschlag (Gating-Test)."""
    ctx = _ctx(robot, tool, WRIST_WALL, WRIST_OPTION)
    assert advise(ctx, advise_below=0.0) is None


def test_no_suggestion_when_unreachable(robot, tool):
    far = PlacementOption("weit", lateral_mm=0.0, standoff_mm=10_000.0, stand_height_mm=0.0)
    ctx = _ctx(robot, tool, WRIST_WALL, far)
    assert worst_reachable(ctx) is None
    assert advise(ctx) is None
