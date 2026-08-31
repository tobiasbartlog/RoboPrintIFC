"""Freigang-Kriterium (Issue #163, Karte #139 / Entscheidung #141, Scheibe 2).

Stufe 1 des Zerlegungs-Constraints: das analytische **Freigang-Kriterium**
(`fgc.decompose.freigang`) leitet aus Wanddicke, freier Länge unter dem Handgelenk
und Handgelenk-/Unterarm-Radius die **druckbare Tiefe von einer Seite** ab und
stellt **ausschließlich Unmöglichkeit** fest — „Wand zu dick für einseitigen Druck".

Der **Kern-Vertrag** ist die *Fehlerrichtung* (S6-Lehre): das Kriterium darf nur
„unmöglich" sagen, wenn es sicher ist. Die Tests sind so gebaut, dass ein falsches
„unmöglich" **auffliegt** — jeder konstruiert druckbare Fall (Dicke ≤ druckbare
Tiefe) muss stumm bleiben (kein Befund). Der Denkmal-Referenzfall (480 mm, `30gut`)
wird als *sicher* zu dick erkannt; die Gegenüberstellung zum vollen Kollisionsbefund
(alle 16 Module real −206…−436 mm) steht im Protokoll (Design-Log 2026-07-10).
"""

from __future__ import annotations

import math

import jsonschema
import pytest

from fgc.decompose import (
    DEFAULT_WRIST_RADIUS_MM,
    DecompositionPlan,
    FreigangCheck,
    Section,
    SectionPlan,
    check_freigang,
    check_teilhoehe,
    decompose_artifact,
    free_length_under_wrist_mm,
    max_printable_height_mm,
    printable_depth_mm,
    sample_angle_rad,
)
from fgc.decompose.evaluate import SectionStatus
from fgc.domain import validate
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.placement import PlacementOption, WallSurface

PROVENANCE = {
    "source": "test",
    "created": "2026-07-10T12:00:00Z",
    "git_commit": "0000000",
}


# --- reine Formel: druckbare Tiefe D = L + R ------------------------------------


def test_printable_depth_is_free_length_plus_radius():
    assert printable_depth_mm(200.0, 60.0) == 260.0
    assert printable_depth_mm(0.0, 0.0) == 0.0


def test_printable_depth_clamps_negative_inputs():
    # Kein negativer Reichweiten-Unsinn; geklemmt auf 0.
    assert printable_depth_mm(-100.0, 60.0) == 60.0
    assert printable_depth_mm(200.0, -10.0) == 200.0


# --- Kern-Vertrag: kein falsches „unmöglich" ------------------------------------


@pytest.mark.parametrize("thickness", [0.0, 50.0, 150.0, 259.999, 260.0])
def test_printable_wall_never_flagged_too_thick(thickness):
    """Jede Wand DÜNNER GLEICH der druckbaren Tiefe bleibt stumm (Fehlerrichtung S6).

    Ein falsches „unmöglich" hier würde einen nachweislich druckbaren Fall sperren —
    genau das darf nicht passieren. D = 200 + 60 = 260.
    """
    check = check_freigang(thickness, free_length_mm=200.0, wrist_radius_mm=60.0)
    assert check.too_thick is False
    assert check.excess_mm == 0.0
    assert check.levers == ()


def test_boundary_exactly_on_depth_is_printable():
    # „too_thick" ist strikt >: exakt auf der druckbaren Tiefe gilt als druckbar.
    check = check_freigang(260.0, free_length_mm=200.0, wrist_radius_mm=60.0)
    assert check.too_thick is False


def test_just_over_depth_is_too_thick():
    check = check_freigang(260.001, free_length_mm=200.0, wrist_radius_mm=60.0)
    assert check.too_thick is True
    assert check.excess_mm == pytest.approx(0.001)
    assert check.levers  # Hebel benannt


# --- Befund-Fall: Hebel + Überschuss --------------------------------------------


def test_too_thick_names_levers_and_excess():
    check = check_freigang(480.0, free_length_mm=273.594, wrist_radius_mm=60.0)
    assert check.too_thick is True
    assert check.printable_depth_mm == pytest.approx(333.594)
    assert check.excess_mm == pytest.approx(480.0 - 333.594)
    # Die benannten Hebel aus Karte #139 / Entscheidung #141.
    joined = " ".join(check.levers).lower()
    assert "tiefenteilung" in joined
    assert "endeffektor" in joined
    assert "aufstellung" in joined


def test_larger_radius_or_length_never_creates_new_impossible():
    """Großzügigere L/R senken den Befund — sie erzeugen nie ein neues „unmöglich".

    (Monotonie in die sichere Richtung: mehr Reichweite ⇒ höchstens weniger Befund.)
    """
    base = check_freigang(400.0, free_length_mm=273.0, wrist_radius_mm=60.0)
    more = check_freigang(400.0, free_length_mm=273.0, wrist_radius_mm=200.0)
    assert base.too_thick is True
    assert more.too_thick is False  # 273 + 200 = 473 > 400


# --- freie Länge aus dem Endeffektor (Obergrenze) -------------------------------


def test_free_length_is_upper_bound_of_flange_plus_tip():
    tool = ToolDef(
        name="t",
        tcp_frame={"pos_mm": [134.0, 0.0, 73.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )
    # L = d6 + ‖tcp‖ = 121 + sqrt(134²+73²) = 121 + 152.594 = 273.594.
    assert free_length_under_wrist_mm(tool, 121.0) == pytest.approx(273.594, abs=1e-3)


def test_free_length_ignores_flange_sign_direction():
    # Nur der Betrag zählt; negativer Flansch wird geklemmt.
    tool = ToolDef(
        name="t",
        tcp_frame={"pos_mm": [0.0, 0.0, 100.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )
    assert free_length_under_wrist_mm(tool, -50.0) == pytest.approx(100.0)


# --- Denkmal-Referenzfall (480 mm, echter Endeffektor + Roboter) ----------------


def test_denkmal_reference_case_is_surely_too_thick():
    """Denkmal-Wand 480 mm + Referenz-Endeffektor `30gut` am M1013 → sicher zu dick.

    Rein analytisch (keine Kollisionssuche): druckbare Tiefe D ≈ 333,6 mm < 480 mm.
    Der volle Befund zeigt für alle 16 Module real −206…−436 mm Eindringung
    (Protokoll/Design-Log 2026-07-10) — beide zeigen „zu dick", das Kriterium erspart
    dort die teure Suche. Läuft ohne python-fcl/Geometrie (nur Stammdaten).
    """
    tool = ToolDef.load("30gut")
    robot = RobotDef.load("doosan_m1013")
    assert robot.kinematics is not None
    flange = robot.kinematics.d_mm[-1]
    free_length = free_length_under_wrist_mm(tool, flange)
    check = check_freigang(480.0, free_length_mm=free_length)
    assert check.too_thick is True
    assert check.printable_depth_mm < 480.0
    assert check.excess_mm > 100.0  # deutlich, kein Grenzfall


def test_default_wrist_radius_used_when_unspecified():
    a = check_freigang(500.0, free_length_mm=300.0)
    b = check_freigang(500.0, free_length_mm=300.0, wrist_radius_mm=DEFAULT_WRIST_RADIUS_MM)
    assert a.to_dict() == b.to_dict()


# --- Serialisierung + Schema-Vertrag im Zerlegungslauf --------------------------


def _wall_plan(thickness_mm: float) -> DecompositionPlan:
    wall = WallSurface(length_mm=800.0, height_mm=600.0, thickness_mm=thickness_mm)
    section = Section(
        section_id="s1", order=1, x0_mm=-400.0, x1_mm=400.0, z0_mm=0.0, z1_mm=600.0
    )
    placement = PlacementOption(
        option_id="opt", lateral_mm=0.0, standoff_mm=500.0, stand_height_mm=0.0
    )
    return DecompositionPlan(
        kind="abschnitt",
        wall=wall,
        cuts=(),
        sections=(SectionPlan(section=section, placement=placement),),
        n_length=1,
        n_height=1,
    )


def _status() -> list[SectionStatus]:
    return [
        SectionStatus(
            section_id="s1",
            order=1,
            reachable=True,
            reachable_fraction=1.0,
            n_samples=1,
            n_reachable=1,
            kinematic_margin=None,
            mean_margin=None,
        )
    ]


def test_freigang_check_to_dict_shape():
    check = check_freigang(480.0, free_length_mm=273.594, wrist_radius_mm=60.0)
    d = check.to_dict()
    assert set(d) == {
        "wall_thickness_mm",
        "free_length_mm",
        "wrist_radius_mm",
        "printable_depth_mm",
        "too_thick",
        "excess_mm",
        "levers",
    }
    assert isinstance(d["levers"], list)


def test_artifact_with_freigang_validates_against_schema():
    freigang = check_freigang(480.0, free_length_mm=273.594, wrist_radius_mm=60.0)
    doc = decompose_artifact(
        "doosan_m1013", "30gut", _wall_plan(480.0), _status(), PROVENANCE, freigang=freigang
    )
    assert "freigang" in doc
    assert doc["freigang"]["too_thick"] is True
    validate(doc, "decompose")  # wirft nicht


def test_artifact_without_freigang_omits_field_and_validates():
    # Additiv: ohne Freigang bleibt das Artefakt byte-gleich zum Bestand.
    doc = decompose_artifact(
        "doosan_m1013", "30gut", _wall_plan(200.0), _status(), PROVENANCE
    )
    assert "freigang" not in doc
    validate(doc, "decompose")


def test_thin_wall_freigang_not_too_thick_serializes():
    freigang = check_freigang(200.0, free_length_mm=273.594, wrist_radius_mm=60.0)
    doc = decompose_artifact(
        "doosan_m1013", "30gut", _wall_plan(200.0), _status(), PROVENANCE, freigang=freigang
    )
    assert doc["freigang"]["too_thick"] is False
    assert doc["freigang"]["levers"] == []
    validate(doc, "decompose")


# --- Actions-Tie-in: fail-soft (Befund, kein Gate) ------------------------------


def test_action_helper_fail_soft_without_tool_or_thickness():
    from fgc.pipeline.actions import _freigang_finding

    robot = RobotDef.load("doosan_m1013")
    tool = ToolDef.load("30gut")
    # Kein Endeffektor / keine Dicke / Dicke 0 ⇒ kein Befund (nie ein geratenes „zu dick").
    assert _freigang_finding(robot, None, 480.0) is None
    assert _freigang_finding(robot, tool, None) is None
    assert _freigang_finding(robot, tool, 0.0) is None


def test_action_helper_fail_soft_without_kinematics():
    from fgc.pipeline.actions import _freigang_finding

    tool = ToolDef.load("30gut")
    robot = RobotDef(
        name="nokin",
        reach_mm=1000.0,
        max_print_height_mm=1000.0,
        max_print_length_mm=2000.0,
        payload_kg=5.0,
        kinematics=None,
    )
    # Ohne Kinematik (Flanschlänge unbekannt) lieber schweigen als raten.
    assert _freigang_finding(robot, tool, 480.0) is None


def test_action_helper_produces_finding_for_denkmal():
    from fgc.pipeline.actions import _freigang_finding

    robot = RobotDef.load("doosan_m1013")
    tool = ToolDef.load("30gut")
    finding = _freigang_finding(robot, tool, 480.0)
    assert isinstance(finding, FreigangCheck)
    assert finding.too_thick is True
    # 30gut traegt einen realen TCP ⇒ nicht provisorisch (kein Vorlaeufigkeits-Feld).
    assert finding.tcp_provisional is False
    assert "tcp_provisional" not in finding.to_dict()


# --- Vorläufigkeit: provisorischer TCP erzeugt nie ein „sicher unmöglich" (Issue #177) ---


def test_check_freigang_carries_tcp_provisional_flag():
    """``tcp_provisional`` reicht durch, ändert das ``too_thick``-Ergebnis aber nicht —
    es markiert den Befund nur als vorläufig (Issue #177/B9). Nur ``True`` serialisiert."""
    prov = check_freigang(480.0, free_length_mm=273.594, tcp_provisional=True)
    conf = check_freigang(480.0, free_length_mm=273.594, tcp_provisional=False)
    assert prov.too_thick is conf.too_thick is True  # dieselbe Rechnung
    assert prov.tcp_provisional is True
    assert prov.to_dict()["tcp_provisional"] is True
    assert "tcp_provisional" not in conf.to_dict()  # bestätigt ⇒ byte-gleich


def test_action_seam_provisional_tcp_yields_no_certainty_red():
    """Pipeline-Aktions-Naht (Issue #177/B9): ein Endeffektor mit provisorischem TCP
    erzeugt kein „sicher unmöglich" — der Freigang-Befund trägt ``tcp_provisional``,
    und das too_thick-Urteil bleibt ``presumed`` (Vermutung, nie geprüfte Gewissheit)."""
    from fgc.decompose.printability import combine_printability
    from fgc.pipeline.actions import _freigang_finding

    robot = RobotDef.load("doosan_m1013")
    prov_tool = ToolDef(
        name="prov",
        tcp_frame={"pos_mm": [134.0, 0.0, 73.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=1.0,
        tcp_provisional=True,
    )
    finding = _freigang_finding(robot, prov_tool, 480.0)
    assert finding is not None and finding.too_thick is True
    assert finding.tcp_provisional is True  # Vorläufigkeit durchgereicht

    out = combine_printability(_wall_plan(480.0), finding, {}, {})
    (pr,) = out.values()
    assert pr.verdict == "too_thick"
    assert pr.presumed is True  # kein Gewissheits-Rot (höhenblind, #167)
    assert pr.tcp_provisional is True  # sichtbares Vorläufigkeits-Feld
    assert pr.to_dict()["tcp_provisional"] is True


def test_artifact_with_provisional_tcp_freigang_validates():
    freigang = check_freigang(480.0, free_length_mm=273.594, tcp_provisional=True)
    doc = decompose_artifact(
        "doosan_m1013", "30gut", _wall_plan(480.0), _status(), PROVENANCE, freigang=freigang
    )
    assert doc["freigang"]["tcp_provisional"] is True
    validate(doc, "decompose")  # additiv, schema-valide


def test_schema_rejects_unknown_freigang_field():
    freigang = check_freigang(480.0, free_length_mm=273.594).to_dict()
    freigang["bogus"] = 1
    doc = decompose_artifact(
        "doosan_m1013", "30gut", _wall_plan(480.0), _status(), PROVENANCE
    )
    doc["freigang"] = freigang
    # additionalProperties: false ⇒ unbekanntes Feld fällt durch.
    with pytest.raises(jsonschema.ValidationError):
        validate(doc, "decompose")


# ================================================================================
# Zweite Stufe-1-Schranke: „Teil zu hoch für die freie Länge" (Issue #209)
# Winkelschranken-Muster φ_max^sample = π/2 − min(φ_max^conn, φ_max^extr) (Gl. 9).
# ================================================================================


# --- reine Formeln: Gl. 9 (Winkel) + druckbare Höhe -----------------------------


def test_sample_angle_conn_bound_dominates_for_stubby_tool():
    """Bauchiges Handgelenk (R > L): die 45°-Verbindbarkeitsschranke dominiert Gl. 9."""
    # φ_extr = arctan(200/60) = 73,3° > 45° ⇒ min = 45° ⇒ φ_sample = 90° − 45° = 45°.
    assert sample_angle_rad(60.0, 200.0) == pytest.approx(math.pi / 4)


def test_sample_angle_extr_bound_dominates_for_slender_tool():
    """Schlanker Endeffektor (L > R): die Endeffektor-Schranke dominiert Gl. 9."""
    # φ_extr = arctan(60/300) < 45° ⇒ min = φ_extr ⇒ φ_sample = 90° − arctan(60/300).
    assert sample_angle_rad(300.0, 60.0) == pytest.approx(math.pi / 2 - math.atan2(60.0, 300.0))


def test_max_printable_height_closed_form_l2_over_r():
    """H_max = L·tan(φ_sample) fällt geschlossen auf L²/R (schlank) bzw. L (bauchig) zusammen."""
    assert max_printable_height_mm(300.0, 60.0) == pytest.approx(1500.0)  # L ≥ R ⇒ L²/R
    assert max_printable_height_mm(60.0, 200.0) == pytest.approx(60.0)  # L < R ⇒ L
    assert max_printable_height_mm(200.0, 200.0) == pytest.approx(200.0)  # L = R ⇒ L


def test_max_printable_height_generous_for_slender_tool():
    """Ein schlanker Endeffektor ergibt eine großzügige Höhe ≥ L (fängt nur Extremfälle)."""
    assert max_printable_height_mm(300.0, 60.0) >= 300.0


def test_max_printable_height_is_monotone_in_free_length():
    """Großzügigere freie Länge senkt den Befund nie (Fehlerrichtung S6): H_max wächst."""
    base = max_printable_height_mm(300.0, 60.0)
    assert max_printable_height_mm(400.0, 60.0) >= base


def test_max_printable_height_infinite_without_free_length():
    # Fehlt die freie Länge (L ≤ 0), gibt es KEINE endliche Höhen-Schranke (fail-soft).
    assert max_printable_height_mm(0.0, 200.0) == math.inf
    assert max_printable_height_mm(-50.0, 200.0) == math.inf


# --- Kern-Vertrag: kein falsches „zu hoch" (H_max = 300 bei L = R = 300) ---------


@pytest.mark.parametrize("height", [0.0, 100.0, 250.0, 299.999, 300.0])
def test_short_part_never_flagged_too_tall(height):
    """Jedes Teil NIEDRIGER GLEICH der druckbaren Höhe bleibt stumm (S6). H_max = 300."""
    check = check_teilhoehe(height, free_length_mm=300.0, wrist_radius_mm=300.0)
    assert check.too_tall is False
    assert check.excess_mm == 0.0
    assert check.excess_deg == 0.0
    assert check.levers == ()


def test_boundary_exactly_on_height_is_printable():
    # „too_tall" ist strikt >: exakt auf der druckbaren Höhe gilt als druckbar.
    assert check_teilhoehe(300.0, free_length_mm=300.0, wrist_radius_mm=300.0).too_tall is False


def test_just_over_height_is_too_tall_with_excess():
    check = check_teilhoehe(300.001, free_length_mm=300.0, wrist_radius_mm=300.0)
    assert check.too_tall is True
    assert check.excess_mm == pytest.approx(0.001)
    assert check.levers  # Hebel benannt


# --- Überschuss-Ausweis in mm UND Grad (US 4) -----------------------------------


def test_excess_reported_in_mm_and_degrees():
    """Ein zu hohes Teil weist den Überschuss doppelt aus: Höhe (mm) und Neigung (Grad)."""
    check = check_teilhoehe(360.0, free_length_mm=300.0, wrist_radius_mm=300.0)
    assert check.too_tall is True
    assert check.max_printable_height_mm == pytest.approx(300.0)
    assert check.sample_angle_deg == pytest.approx(45.0)
    assert check.excess_mm == pytest.approx(60.0)  # 360 − 300
    # φ_req = arctan(360/300) = 50,19° ; Überschuss = 50,19° − 45° ≈ 5,19° (auf 3 gerundet).
    phi_req = math.degrees(math.atan2(360.0, 300.0))
    assert check.excess_deg == pytest.approx(round(phi_req - 45.0, 3))
    assert check.excess_deg > 0.0


def test_too_tall_names_levers():
    joined = " ".join(
        check_teilhoehe(500.0, free_length_mm=300.0, wrist_radius_mm=300.0).levers
    ).lower()
    assert "höhenteilung" in joined
    assert "endeffektor" in joined
    assert "aufstellung" in joined


# --- fail-soft: fehlende Maße erzeugen nie ein geratenes „zu hoch" --------------


def test_missing_free_length_never_flags_too_tall():
    # L = 0 (kein Endeffektor-Maß) ⇒ keine Schranke, selbst ein sehr hohes Teil bleibt stumm.
    check = check_teilhoehe(2000.0, free_length_mm=0.0, wrist_radius_mm=200.0)
    assert check.too_tall is False
    assert check.excess_mm == 0.0 and check.excess_deg == 0.0
    assert check.max_printable_height_mm == 0.0  # inf wird nie serialisiert


def test_teilhoehe_default_wrist_radius_used_when_unspecified():
    a = check_teilhoehe(500.0, free_length_mm=100.0)
    b = check_teilhoehe(500.0, free_length_mm=100.0, wrist_radius_mm=DEFAULT_WRIST_RADIUS_MM)
    assert a == b
