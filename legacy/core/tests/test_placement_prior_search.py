"""Prior lenkt die Vorschlagssuche (Issue #232, ADR-026 Punkt 3-4, PRD #225, Slice 5).

Verhaltenstests **an der oeffentlichen Schnittstelle** ``placement.suggest`` (keine
Implementationsdetails): mit passendem Prior verdichtet sich das Raster um die
gemessenen Best-Stuetzstellen — **messbar weniger** ``evaluate``-Aufrufe bei gleichem
oder besserem Sieger —, die Verdichtung schliesst nie Kandidaten aus, und ohne
anwendbaren Prior ist das Verhalten das von #228 (neutral). Die Tool-Aehnlichkeits-
Regel selbst ist in ``test_placement_prior`` dicht abgedeckt; hier wird sie an der
Vorschlags-Naht (neutral ⇒ #228-Raster) belegt.
"""

from __future__ import annotations

from importlib import import_module

from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.domain.workstation import WorkstationDef
from fgc.placement import (
    NEUTRAL_PRIOR,
    PlacementOption,
    PlacementPrior,
    WallSurface,
    suggest,
)

# ``fgc.placement.__init__`` bindet den Namen ``suggest`` an die Funktion und
# ueberdeckt so das gleichnamige Submodul — ``import_module`` liefert trotzdem das
# echte Modul (fuer die ``evaluate``-Zaehl-Sonde + die Fenster-Konstante).
suggest_mod = import_module("fgc.placement.suggest")

ROBOT = "doosan_m1013"

#: Wand nahe der Basis (voll im Arbeitsraum), mit Dicke.
WALL = WallSurface(length_mm=600.0, height_mm=400.0, thickness_mm=200.0)

_TOOL = ToolDef(
    name="testduese",
    tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
    weight_kg=0.0,
)

#: Workstation mit **weitem** Abstandsbereich (safety_min .. reach) — so dominiert das
#: grobe Raster ausserhalb des Prior-Fensters und der Aufruf-Spar-Effekt ist messbar.
#: Ein einzelnes Bodenpodest isoliert die Abstands-Achse (Hoehe = 1 Kandidat).
_WIDE_WS = WorkstationDef(
    name="w", mobility="mobile", height_adjustable=False,
    base_heights_mm=(0.0,), safety_min_distance_mm=350.0,
)

#: Hoehenverstellbare Workstation fuer die Podesthoehen-Verdichtung.
_ADJ_WS = WorkstationDef(
    name="adj", mobility="mobile", height_adjustable=True,
    base_heights_mm=(), height_range_mm=(0.0, 900.0), safety_min_distance_mm=700.0,
)


def _all_free(_o: PlacementOption) -> bool:
    return True


def _robot() -> RobotDef:
    return RobotDef.load(ROBOT)


def _measured_prior(*, standoff: float | None, base_height: float | None) -> PlacementPrior:
    return PlacementPrior(
        is_neutral=False, reason="measured", feasibility_expectation="feasible",
        standoff_focus_mm=standoff, base_height_focus_mm=base_height,
        config_shortlist=(), h_max_mm=900.0, cell_key="600_200",
    )


def _count_evaluate(monkeypatch) -> dict[str, int]:
    """Zaehlt die ``evaluate``-Aufrufe der Vorschlagssuche (Schnittstellen-Sonde)."""
    calls = {"n": 0}
    real = suggest_mod.evaluate

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(suggest_mod, "evaluate", counting)
    return calls


def _key(score):
    return (
        score.reachable_fraction,
        score.kinematic_margin or 0.0,
        score.mean_margin or 0.0,
    )


def _standoffs(candidates) -> set[float]:
    return {round(opt.standoff_mm, 1) for opt, _ in candidates}


# --- AC 1: weniger evaluate-Aufrufe, gleicher/besserer Sieger -------------------


def test_matching_prior_uses_fewer_evaluate_calls_same_or_better_winner(monkeypatch):
    robot = _robot()
    # Neutraler Referenzlauf (Verhalten #228) — sein Sieger legt den Prior-Fokus fest,
    # damit die Verdichtung nachweislich auf die gute Region zielt.
    calls = _count_evaluate(monkeypatch)
    neutral = suggest(
        WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor",
        n_best=999, collision_free=_all_free, prior=NEUTRAL_PRIOR,
    )
    n_neutral = calls["n"]
    best_neutral = neutral[0][1]
    focus = neutral[0][0].standoff_mm

    calls["n"] = 0
    prior = _measured_prior(standoff=focus, base_height=0.0)
    guided = suggest(
        WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor",
        n_best=999, collision_free=_all_free, prior=prior,
    )
    n_prior = calls["n"]

    assert n_prior < n_neutral, (n_prior, n_neutral)
    # Der Fokus (= neutraler Sieger-Standoff) ist im verdichteten Raster garantiert
    # enthalten ⇒ der Prior-Sieger ist gleich gut oder besser.
    assert _key(guided[0][1]) >= _key(best_neutral)


# --- AC 2: Verdichtung schliesst nie aus (fail-soft belegt) ---------------------


def test_densification_keeps_candidates_outside_the_window():
    robot = _robot()
    focus = 400.0
    prior = _measured_prior(standoff=focus, base_height=0.0)
    guided = suggest(
        WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor",
        n_best=999, collision_free=_all_free, prior=prior,
    )
    window = suggest_mod.PRIOR_STANDOFF_WINDOW_MM
    outside = [s for s in _standoffs(guided) if abs(s - focus) > window]
    assert outside, "auch ausserhalb des Prior-Fensters muss es Kandidaten geben"


# --- AC 3: Neutral-Fall = Verhalten #228 ----------------------------------------


def test_neutral_prior_matches_228_grid():
    """Ohne anwendbaren Prior ist die Kandidatenmenge die von #228 (verhaltensgleich)."""
    robot = _robot()
    ref = suggest(
        WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor",
        n_best=999, collision_free=_all_free, prior=NEUTRAL_PRIOR,
    )
    # Auto-Laden (default): der Test-Tool ohne passendes Huellmass ⇒ neutraler Prior ⇒
    # identisches Raster wie der explizit neutrale Lauf (Tool-Aehnlichkeit an der Naht).
    auto = suggest(
        WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor",
        n_best=999, collision_free=_all_free,
    )
    assert _standoffs(ref) == _standoffs(auto)


def test_assumed_infeasible_prior_searches_neutral_broad():
    """`angenommen-unmachbar` (kein Fokus) ⇒ neutral-breite Suche; die Erwartung ist
    reine Info, nie ein Gate (die Liste bleibt voll besetzt wie neutral)."""
    robot = _robot()
    assumed = PlacementPrior(
        is_neutral=False, reason="angenommen-unmachbar",
        feasibility_expectation="infeasible",
        standoff_focus_mm=None, base_height_focus_mm=None,
    )
    guided = suggest(
        WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor",
        n_best=999, collision_free=_all_free, prior=assumed,
    )
    neutral = suggest(
        WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor",
        n_best=999, collision_free=_all_free, prior=NEUTRAL_PRIOR,
    )
    assert guided  # nie leer — die Unmachbarkeits-Erwartung gatet nichts
    assert _standoffs(guided) == _standoffs(neutral)


# --- Podesthoehen-Verdichtung (nur hoehenverstellbar) ---------------------------


def test_height_densification_adds_candidate_near_best_height():
    robot = _robot()
    prior = _measured_prior(standoff=None, base_height=300.0)
    guided = suggest(
        WALL, robot, _TOOL, workstation=_ADJ_WS, stand_mode="elevated",
        n_best=999, collision_free=_all_free, prior=prior,
    )
    neutral = suggest(
        WALL, robot, _TOOL, workstation=_ADJ_WS, stand_mode="elevated",
        n_best=999, collision_free=_all_free, prior=NEUTRAL_PRIOR,
    )
    heights_guided = {round(o.stand_height_mm, 1) for o, _ in guided}
    heights_neutral = {round(o.stand_height_mm, 1) for o, _ in neutral}
    # Das neutrale 500-mm-Raster (0, 500, 900) trifft die Besthoehe 300 nicht — die
    # Prior-Verdichtung ergaenzt sie, ohne die groben Stuetzstellen zu verlieren.
    assert 300.0 in heights_guided
    assert 300.0 not in heights_neutral
    assert heights_neutral <= heights_guided


# --- Determinismus --------------------------------------------------------------


def test_prior_guided_search_is_deterministic():
    robot = _robot()
    prior = _measured_prior(standoff=500.0, base_height=0.0)
    a = suggest(WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor", prior=prior)
    b = suggest(WALL, robot, _TOOL, workstation=_WIDE_WS, stand_mode="floor", prior=prior)
    assert [(o.option_id, s.to_dict()) for o, s in a] == [
        (o.option_id, s.to_dict()) for o, s in b
    ]
