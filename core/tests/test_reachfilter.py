"""Reichweitenkarte als Vorfilter der Platzierung (PRD #183 AP 2, Issue #214).

Externes Verhalten der drei Aufrufer, die sich **einen** Vorfilter-Parameter teilen
(``config_filter``-Muster #200/#201), plus die Ehrlichkeitsregel (ADR-007/#164: die
Karte filtert, urteilt nie):

- **Optimalvorschlag / Standplatz je Höhenreihe** (US 5/6): der Standplatz je Reihe
  ist das **punktweise Minimum über die Bahnposen** — er deckt garantiert *alle*
  Posen der Reihe (konstruierte Reihe: „deckt alle" vs. „erreicht eine, aber nicht
  die ganze Reihe").
- **Bewertungsmodus** (US 7/11): ``evaluate`` mit Karte trägt den geschätzten
  erreichbaren Anteil **klar als Schätzung gekennzeichnet**; die Ampel-Basis
  (``reachable_fraction``, IK-Urteil) bleibt unverändert.
- **Kollisions-Advisor** (US 8): der Karten-Vorfilter kürzt die Kandidatenliste
  nachweislich (unerreichbare Gegenmaßnahmen gar nicht erst simuliert).
- **Ohne Karte byte-gleich** (US 12): ``evaluate``/``suggest``/``advise`` verhalten
  sich ohne Karte bit-identisch zu Altläufen (fail-soft).
"""

from __future__ import annotations

import numpy as np
import pytest

from fgc.collision.advisor import Override, advise, build_candidates
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.kinematics.opw import OpwKinematics
from fgc.kinematics.reachability import ReachabilityMap
from fgc.placement import reachmap
from fgc.placement.evaluate import PlacementOption, WallSurface, evaluate
from fgc.placement.suggest import suggest

ROBOT = "doosan_m1013"

SMALL_WALL = WallSurface(length_mm=600.0, height_mm=400.0, thickness_mm=200.0)
TALL_WALL = WallSurface(length_mm=600.0, height_mm=4000.0, thickness_mm=200.0)
OPTION = PlacementOption(
    option_id="boden-mitte", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=0.0
)


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


@pytest.fixture(scope="module")
def coarse_map() -> ReachabilityMap:
    """Grobe Karte (150 mm, 15°) — schnell gebaut, dieselbe Build-Logik wie offline."""
    return ReachabilityMap.build(OpwKinematics.from_robot(ROBOT), cell_mm=150.0, n_alpha=13)


# --- US 6: Standplatz je Höhenreihe = Minimum über die Bahn -------------------


def test_standplatz_je_reihe_is_pointwise_and_over_the_row(coarse_map, tool):
    """Der Standplatz deckt garantiert ALLE Posen der Reihe (Minimum = UND über die Bahn)."""
    wall = WallSurface(length_mm=800.0, height_mm=0.0, thickness_mm=200.0)
    row_z = 800.0
    # Konstruierte Kandidaten: zentral-nah (decken alles), lateral versetzt (partiell),
    # fern (nichts).
    cands = np.array(
        [[0.0, 400.0], [0.0, 600.0], [0.0, 800.0], [900.0, 400.0], [0.0, 1400.0]]
    )
    mask = reachmap.standplatz_fuer_reihe(
        coarse_map, wall, tool, cands, 0.0, row_z_mm=row_z
    )

    # Der Standplatz IST das punktweise Minimum (UND) der Einzel-Posen-Inversabfragen.
    frames = reachmap.wall_row_frames(wall, tool, row_z_mm=row_z)
    assert len(frames) > 1
    reference = np.ones(len(cands), dtype=bool)
    for f in frames:
        reference &= coarse_map.base_positions(f, cands, 0.0)
    assert np.array_equal(mask, reference)

    # Jede Standplatz-True-Basis erreicht nachweislich JEDE Pose der Reihe (US 6-Kern).
    true_idx = np.where(mask)[0]
    assert true_idx.size >= 1
    for i in true_idx:
        assert all(
            bool(coarse_map.base_positions(f, cands[i : i + 1], 0.0)[0]) for f in frames
        )

    # Semantischer Teilfall (RM4D IV-D): eine Basis erreicht EINE Pose, aber nicht die
    # ganze Reihe → vom Standplatz ausgeschlossen (kein Umsetzen mitten in der Reihe).
    partial = [
        i
        for i in range(len(cands))
        if not mask[i]
        and any(bool(coarse_map.base_positions(f, cands[i : i + 1], 0.0)[0]) for f in frames)
    ]
    assert partial, "Reihe muss den Fall 'erreicht eine, nicht die ganze Reihe' abdecken"


def test_standplatz_empty_row_is_neutral_true(coarse_map, tool):
    """Leere Posenmenge ⇒ neutrales Element (alles True) — kein stiller Ausschluss."""
    cands = np.array([[0.0, 400.0], [0.0, 5000.0]])
    mask = coarse_map.min_over_poses([], cands, 0.0)
    assert mask.tolist() == [True, True]


# --- US 7/11: Bewertungsmodus — Schätzung gekennzeichnet, Ampel unverändert ----


def test_evaluate_estimate_is_labelled_and_leaves_verdict_untouched(coarse_map, robot, tool):
    """Die Karten-Schätzung ist klar gekennzeichnet; das IK-Urteil bleibt unverändert."""
    without = evaluate(SMALL_WALL, robot, tool, OPTION)
    withmap = evaluate(SMALL_WALL, robot, tool, OPTION, reach_map=coarse_map)

    # Ampel-Basis (US 11): reachable_fraction/Marge/Warnungen sind das IK-Urteil,
    # von der Karte unberührt.
    assert withmap.reachable_fraction == without.reachable_fraction
    assert withmap.kinematic_margin == without.kinematic_margin
    assert withmap.warnings == without.warnings

    # US 7: die Schätzung ist da UND als Schätzung markiert.
    est = withmap.reach_estimate
    assert est is not None
    assert est["is_estimate"] is True
    assert est["source"] == "reachability_map"
    assert 0.0 <= est["reachable_fraction"] <= 1.0
    assert "reach_estimate" in withmap.to_dict()


def test_evaluate_without_map_is_byte_identical(robot, tool):
    """Ohne Karte byte-gleich (US 12): kein reach_estimate, identisches to_dict."""
    a = evaluate(TALL_WALL, robot, tool, OPTION)
    b = evaluate(TALL_WALL, robot, tool, OPTION, reach_map=None)
    assert a.reach_estimate is None
    assert a.to_dict() == b.to_dict()
    assert "reach_estimate" not in a.to_dict()


def test_map_estimate_tracks_the_ik_verdict_direction(coarse_map, robot, tool):
    """Die Schätzung folgt der Realität: überhohe Wand < voll erreichbare Wand."""
    small = evaluate(SMALL_WALL, robot, tool, OPTION, reach_map=coarse_map)
    tall = evaluate(TALL_WALL, robot, tool, OPTION, reach_map=coarse_map)
    assert small.reach_estimate["reachable_fraction"] > tall.reach_estimate["reachable_fraction"]


# --- US 5/12: Optimalvorschlag — Vorfilter, ohne Karte byte-gleich -------------


def test_suggest_without_map_is_byte_identical(robot, tool):
    """Ohne Karte liefert suggest die identische Rangliste wie zuvor (US 12)."""
    a = suggest(TALL_WALL, robot, tool, n_best=3)
    b = suggest(TALL_WALL, robot, tool, n_best=3, reach_map=None)
    assert [(o.option_id, s.to_dict()) for o, s in a] == [
        (o.option_id, s.to_dict()) for o, s in b
    ]


def test_suggest_prefilter_keeps_the_top_candidates(coarse_map, robot, tool):
    """Der Vorfilter streicht nur Aussichtsloses — die beste Lage bleibt dieselbe (US 5)."""
    without = suggest(TALL_WALL, robot, tool, n_best=1)
    withmap = suggest(TALL_WALL, robot, tool, n_best=1, reach_map=coarse_map)
    # Der Karten-Vorfilter (lenient) entfernt nur Kandidaten mit Schätzung 0 — die
    # können nie an die Spitze; die beste Lage ist unverändert (Karte filtert, urteilt nie).
    assert withmap[0][0].stand_height_mm == without[0][0].stand_height_mm
    assert withmap[0][0].standoff_mm == without[0][0].standoff_mm
    assert withmap[0][1].reachable_fraction == without[0][1].reachable_fraction


def test_suggest_prefilter_is_failsoft_when_it_would_starve(coarse_map, robot, tool):
    """Würde der Filter ALLE Kandidaten streichen, greift das volle Raster (fail-soft)."""
    # Wand weit außerhalb der Reichweite: die Karte hält jeden Kandidaten für
    # aussichtslos → der Vorfilter darf nicht auf eine leere Liste zusammenfallen.
    far = PlacementOption(
        option_id="fern", lateral_mm=0.0, standoff_mm=5000.0, stand_height_mm=0.0
    )
    ranked = suggest(
        SMALL_WALL, robot, tool, n_best=3, standoff_mm=5000.0, reach_map=coarse_map
    )
    assert ranked  # nicht leer trotz aussichtsloser Karte
    _ = far


# --- US 8: Kollisions-Advisor — Kandidatenliste vorgefiltert (kürzer) ----------


def _finding(min_distance_mm: float, n_red: int) -> dict:
    return {
        "min_distance_mm": min_distance_mm,
        "n_red": n_red,
        "config": {"safety_distance_mm": 0.0},
    }


def test_collision_advisor_prefilter_shortens_the_list():
    """Der Reichweiten-Vorfilter kürzt die Advisor-Liste (unerreichbare gar nicht simuliert)."""
    candidates = build_candidates(section_id="s", standoff_mm=100.0, stand_height_mm=0.0)
    baseline = _finding(-5.0, 3)  # Basis kollidiert

    def simulate(_override: Override) -> dict:
        return _finding(10.0, 0)  # jeder Kandidat beseitigt die Kollision → würde Option

    full = advise(baseline, candidates, simulate)

    # Karten-Vorfilter: verwirft alle Platzierungs-Gegenmaßnahmen (Basis außer Reichweite).
    def reachable(override: Override) -> bool:
        return override.placement is None

    filtered = advise(baseline, candidates, simulate, reachable=reachable)

    assert len(filtered.options) < len(full.options)
    assert all(o.kind != "placement" for o in filtered.options)
    # Nicht-Platzierungs-Hebel überleben unverändert (die Karte urteilt nicht über sie).
    assert any(o.kind == "placement" for o in full.options)


def test_collision_advisor_without_prefilter_is_byte_identical():
    """Ohne Vorfilter (reachable=None) ist das Ranking bit-identisch zu heute (US 12)."""
    candidates = build_candidates(section_id="s", standoff_mm=100.0)
    baseline = _finding(-5.0, 3)

    def simulate(_override: Override) -> dict:
        return _finding(10.0, 0)

    a = advise(baseline, candidates, simulate)
    b = advise(baseline, candidates, simulate, reachable=None)
    assert a.to_dict() == b.to_dict()
