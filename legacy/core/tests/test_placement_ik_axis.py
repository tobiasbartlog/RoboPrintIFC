"""IK-Konfiguration als prior-gefuehrte Suchachse (Issue #233, ADR-026 Punkt 5, PRD #225).

Verhaltenstests an der oeffentlichen Naht ``placement.suggest``: je Kandidat wird der
IK-Konfig-Zweig **mitgesucht** — mit anwendbarem Prior nur die Shortlist (+ ``auto``),
sonst die volle 8er-Achse; findet die Shortlist nichts Machbares, eskaliert die Achse
einmalig auf alle 8. Der gewaehlte Zweig steht **nach aussen** in
``PlacementScore.ik_config`` (a/b-Block), damit Bewertung, Simulation und Druck
dieselbe Konfiguration fahren. Die Konfig ist **nie** hartkodiert — der Sieger kommt
aus Prior/Suche und verschiebt sich mit Wand und Setup (Studienbeleg: ``baa`` bleibt
frei, wo ``auto`` in die Wand taucht ⇒ ``baa`` schlaegt ``auto``).
"""

from __future__ import annotations

from importlib import import_module

from fgc.collision.coarse import path_collides
from fgc.collision.robot_geometry import load_robot_collision_geometry
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.domain.workstation import WorkstationDef
from fgc.placement import (
    NEUTRAL_PRIOR,
    PlacementOption,
    PlacementPrior,
    PlacementScore,
    WallSurface,
    suggest,
)

# ``fgc.placement.__init__`` bindet den Namen ``suggest`` an die Funktion und
# ueberdeckt so das Submodul — ``import_module`` liefert es fuer die Sonden/Konstanten.
suggest_mod = import_module("fgc.placement.suggest")

ROBOT = "doosan_m1013"

#: a/b-Bloecke der Studien-Konfigs.
BAA = {"shoulder": "b", "elbow": "a", "wrist": "a"}
BBB = {"shoulder": "b", "elbow": "b", "wrist": "b"}


def _robot() -> RobotDef:
    return RobotDef.load(ROBOT)


def _ref_tool() -> ToolDef:
    """Das vermessene Referenz-Tool (30gut) — nur so greift der eingecheckte Prior."""
    return ToolDef.load("30gut")


def _null_tool() -> ToolDef:
    return ToolDef(
        name="testduese",
        tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )


def _all_free(_o: PlacementOption) -> bool:
    return True


#: Denkmal-naher Fall (Prior-Zelle 800_250 ⇒ ``baa``): tief/dick genug, dass ``auto``
#: ueber das erreichbare Abstandsband in die Wand taucht — nur ``baa`` bleibt frei.
_DENKMAL_WALL = WallSurface(length_mm=800.0, height_mm=800.0, thickness_mm=250.0)
_DENKMAL_WS = WorkstationDef(
    name="w", mobility="mobile", height_adjustable=False,
    base_heights_mm=(0.0, 300.0), safety_min_distance_mm=600.0,
)


def _filter_of(config_filter) -> tuple:
    return (config_filter.shoulder, config_filter.elbow, config_filter.wrist)


def _judged(robot, tool, wall, opt, geo, name) -> PlacementScore:
    """Score eines Zweigs **wie ``suggest`` ihn faehrt**: Reichweite + konfig-bewusster
    Grob-Check als sichtbares Kollisionsfeld (fuer den ``_config_key``-Vergleich)."""
    import dataclasses

    from fgc.placement import evaluate
    from fgc.placement.suggest import collision_judgment

    cf = suggest_mod._config_filter(name)
    score = evaluate(wall, robot, tool, opt, config_filter=cf)
    free = not path_collides(wall, robot, tool, opt, geo, config_filter=cf)
    return dataclasses.replace(score, collision=collision_judgment(free))


def _record_evaluate(monkeypatch) -> list:
    """Sonde: sammelt die je Aufruf uebergebenen ``config_filter`` (Achsen-Beleg)."""
    seen: list[tuple] = []
    real = suggest_mod.evaluate

    def recording(*args, **kwargs):
        seen.append(_filter_of(kwargs["config_filter"]))
        return real(*args, **kwargs)

    monkeypatch.setattr(suggest_mod, "evaluate", recording)
    return seen


# --- AC 1: Sieger-Konfig baa (Studienerwartung) + nur Shortlist bewertet ----------


def test_prior_shortlist_winner_is_baa_and_beats_auto():
    """Mit anwendbarem Prior gewinnt auf dem denkmal-Referenzmodul die ``baa``-Lage:
    ``auto`` kollidiert grob, ``baa`` bleibt frei — der Sieger-Zweig steht nach aussen."""
    robot, tool = _robot(), _ref_tool()
    # Kein ``prior=`` uebergeben ⇒ er wird prior-gefuehrt aus (Roboter, Referenz-Tool,
    # Modulmasse, Sicherheitszone) geladen (Zelle 800_250 ⇒ Shortlist ``baa`` + ``auto``).
    result = suggest(
        _DENKMAL_WALL, robot, tool, workstation=_DENKMAL_WS,
        stand_mode="elevated", n_best=1,
    )
    assert result, "nie leer (Befund, kein Gate)"
    winner_opt, winner_score = result[0]
    assert winner_score.ik_config == BAA, winner_score.ik_config

    # baa schlaegt auto **auf derselben Lage**: mit genau der Bewertung, die ``suggest``
    # je Zweig faehrt (Reichweite + konfig-bewusster Grob-Check), rankt ``baa`` strikt
    # vor ``auto`` — der Grund, warum der Sieger-Zweig nicht ``auto`` ist.
    geo = load_robot_collision_geometry(ROBOT)
    baa = _judged(robot, tool, _DENKMAL_WALL, winner_opt, geo, "baa")
    auto = _judged(robot, tool, _DENKMAL_WALL, winner_opt, geo, "auto")
    assert suggest_mod._config_key(baa) > suggest_mod._config_key(auto)


def test_prior_shortlist_only_evaluates_shortlist_plus_auto(monkeypatch):
    """Mit Prior werden je Kandidat **nur** die Shortlist-Konfig(s) + ``auto`` bewertet
    (gezaehlte Aufrufe) — kein anderer der 8 Zweige, solange die Shortlist traegt."""
    robot, tool = _robot(), _ref_tool()
    seen = _record_evaluate(monkeypatch)
    result = suggest(
        _DENKMAL_WALL, robot, tool, workstation=_DENKMAL_WS,
        stand_mode="elevated", n_best=1,
    )
    assert result[0][1].ik_config == BAA  # Shortlist trug (keine Eskalation)
    baa = _filter_of(suggest_mod._config_filter("baa"))
    auto = _filter_of(suggest_mod._config_filter("auto"))
    assert set(seen) == {baa, auto}, sorted(set(seen))


# --- AC 2: Eskalation auf alle 8, wenn die Shortlist nichts Machbares findet -------


def _stub_only_config(monkeypatch, name: str) -> None:
    """Stub: nur der Zweig ``name`` ist erreichbar (reach 1.0), alle anderen reach 0."""
    target = _filter_of(suggest_mod._config_filter(name))

    def fake_evaluate(wall, robot, tool, opt, *, config_filter=None, **kwargs):
        hit = _filter_of(config_filter) == target
        frac = 1.0 if hit else 0.0
        return PlacementScore(
            reachable_fraction=frac, n_samples=4, n_reachable=int(4 * frac),
            kinematic_margin=(0.5 if hit else None),
            mean_margin=(0.5 if hit else None),
        )

    monkeypatch.setattr(suggest_mod, "evaluate", fake_evaluate)


def test_shortlist_without_feasible_escalates_to_all_eight(monkeypatch):
    """Konstruierter Fall: nur ``bbb`` ist machbar, die Shortlist (``aaa`` + ``auto``)
    findet nichts ⇒ die Achse eskaliert **einmalig** auf alle 8 und findet ``bbb``."""
    _stub_only_config(monkeypatch, "bbb")  # nur bbb erreichbar (ersetzt evaluate)
    seen = _record_evaluate(monkeypatch)  # Sonde ueber den Stub — zaehlt die Zweige

    prior = PlacementPrior(
        is_neutral=False, reason="measured", feasibility_expectation="feasible",
        config_shortlist=("aaa", "auto"),
    )
    result = suggest(
        WallSurface(600.0, 400.0, 200.0), _robot(), _null_tool(),
        n_best=1, collision_free=_all_free, prior=prior,
    )
    assert result[0][1].ik_config == BBB  # aus der Eskalation, nicht der Shortlist
    # Beleg der Eskalation: alle 8 festen Zweige wurden bewertet.
    fixed = {_filter_of(suggest_mod._config_filter(c)) for c in suggest_mod.ALL_IK_CONFIGS}
    assert fixed <= set(seen)


def test_shortlist_with_feasible_does_not_escalate(monkeypatch):
    """Findet die Shortlist etwas Machbares (``bbb`` in der Shortlist), bleibt es dabei —
    keine Eskalation: ``aaa`` (nur in der vollen Achse) wird nie bewertet."""
    _stub_only_config(monkeypatch, "bbb")
    seen = _record_evaluate(monkeypatch)

    prior = PlacementPrior(
        is_neutral=False, reason="measured", feasibility_expectation="feasible",
        config_shortlist=("bbb", "auto"),
    )
    result = suggest(
        WallSurface(600.0, 400.0, 200.0), _robot(), _null_tool(),
        n_best=1, collision_free=_all_free, prior=prior,
    )
    assert result[0][1].ik_config == BBB
    aaa = _filter_of(suggest_mod._config_filter("aaa"))
    assert aaa not in set(seen)  # keine Eskalation ⇒ Nicht-Shortlist-Zweig ungeprueft


def test_no_prior_runs_the_full_axis(monkeypatch):
    """Ohne anwendbaren Prior (neutral) laeuft **direkt** die volle Achse: alle 8 festen
    Zweige werden je Kandidat bewertet (keine Shortlist, keine Eskalation noetig)."""
    _stub_only_config(monkeypatch, "bbb")
    seen = _record_evaluate(monkeypatch)
    suggest(
        WallSurface(600.0, 400.0, 200.0), _robot(), _null_tool(),
        n_best=1, collision_free=_all_free, prior=NEUTRAL_PRIOR,
    )
    fixed = {_filter_of(suggest_mod._config_filter(c)) for c in suggest_mod.ALL_IK_CONFIGS}
    assert fixed <= set(seen)


# --- AC 4/5: keine Hartkodierung + Determinismus ---------------------------------


def test_winner_config_shifts_with_the_prior(monkeypatch):
    """Keine Hartkodierung: derselbe Wand/Setup liefert je nach Prior-Shortlist einen
    **anderen** Sieger-Zweig — die Wahl kommt aus dem Prior, nicht aus dem Code."""
    _stub_only_config(monkeypatch, "abb")  # nur abb erreichbar
    wall = WallSurface(600.0, 400.0, 200.0)
    for shortlist, expect in [(("abb", "auto"), {"shoulder": "a", "elbow": "b", "wrist": "b"})]:
        prior = PlacementPrior(
            is_neutral=False, reason="measured", config_shortlist=shortlist,
        )
        res = suggest(wall, _robot(), _null_tool(), n_best=1,
                      collision_free=_all_free, prior=prior)
        assert res[0][1].ik_config == expect


def test_prior_guided_config_search_is_deterministic():
    """Determinismus (ADR-004): gleiche Eingaben ⇒ identische Vorschlaege inkl. Zweig."""
    robot, tool = _robot(), _ref_tool()
    a = suggest(_DENKMAL_WALL, robot, tool, workstation=_DENKMAL_WS,
                stand_mode="elevated", n_best=3)
    b = suggest(_DENKMAL_WALL, robot, tool, workstation=_DENKMAL_WS,
                stand_mode="elevated", n_best=3)
    assert [(o.option_id, s.to_dict()) for o, s in a] == [
        (o.option_id, s.to_dict()) for o, s in b
    ]
    assert all(s.to_dict().get("ik_config") is not None for _o, s in a)
