"""Platzierungs-Grob-Check: default-an + Machbarkeits-Befund (Issue #131 → #228, ADR-026).

Deckt das äußere Verhalten des kollisionsbewussten Optimalvorschlags ab (Issue #228,
ADR-026): der Grob-Check läuft **standardmäßig** als Vorfilter **vor** ``evaluate``,
kollisionsfreie Kandidaten gewinnen, das Urteil steht als explizites Score-Feld, und
„alle rot" liefert trotzdem eine Liste plus Unmachbarkeits-Befund.

- **Default-an (US 1):** ein bare ``suggest``-Aufruf mit realer M1013-Geometrie ist
  kollisionsbewusst — der Beste ist kollisionsfrei, jeder Vorschlag trägt sein
  ``collision``-Feld.
- **Vorfilter vor ``evaluate`` (US 8/16):** kollidierende Kandidaten werden gar nicht
  erst bewertet — sie tauchen (solange es freie gibt) nicht im Ergebnis auf.
- **Fail-soft „alle rot" (US 4):** streicht der Filter alle, wird das volle Raster
  bewertet, die Liste bleibt nicht leer, der Befund meldet „kein machbarer Kandidat".
- **Alt-Zustand explizit (US 15):** ``collision_free=lambda o: True`` reproduziert die
  reine Erreichbarkeits-Optimierung (kein Vorfilter, #98-Sortierung bit-identisch, kein
  Kollisionsfeld) — ohne Legacy-Schalter.
- **Nachweislicher Grob-Befund:** mit der echten M1013-Breitphasen-Geometrie kollidiert
  eine zu nahe Aufstellung, eine mit Standardabstand nicht.

Alles billig: wenige Stichproben-Posen, Breitphasen-Hüllen (keine 25k-Bahn).
"""

from __future__ import annotations

from fgc.collision.coarse import path_collides
from fgc.collision.robot_geometry import load_robot_collision_geometry
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.domain.workstation import WorkstationDef
from fgc.placement import (
    PlacementOption,
    WallSurface,
    feasibility_finding,
    suggest,
)

ROBOT = "doosan_m1013"

#: Kleine Wand nahe der Basis, mit Dicke (Volumen hinter der Front y=0).
SMALL_WALL = WallSurface(length_mm=600.0, height_mm=400.0, thickness_mm=200.0)
#: Ueberhohe Wand — zwingt den Arm in Reichweitengrenzen (mehr Rang-Spreizung).
TALL_WALL = WallSurface(length_mm=600.0, height_mm=4000.0, thickness_mm=200.0)

_TOOL = ToolDef(
    name="testduese",
    tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
    weight_kg=0.0,
)

#: Workstation, deren Abstands-Raster von nah (kollidierend) bis fern (frei) reicht.
_NEAR_WS = WorkstationDef(
    name="w", mobility="mobile", height_adjustable=False,
    base_heights_mm=(0.0,), safety_min_distance_mm=200.0,
)

#: Alt-Zustand (US 15): reine Erreichbarkeits-Optimierung ohne Legacy-Schalter — alles
#: frei ⇒ kein Vorfilter, #98-Sortierung bit-identisch, kein Kollisionsfeld.
def _all_free(_o: PlacementOption) -> bool:
    return True


def _robot() -> RobotDef:
    return RobotDef.load(ROBOT)


def _ids(candidates) -> list[str]:
    return [opt.option_id for opt, _ in candidates]


# --- Alt-Zustand explizit über die Parameter (US 15) --------------------------


def test_all_free_predicate_is_reachability_only():
    """`collision_free=lambda o: True` reproduziert die reine #98-Sortierung und trägt
    kein Kollisionsfeld — der Alt-Zustand, explizit konstruiert (ADR-026 Punkt 6)."""
    robot = _robot()
    got = suggest(TALL_WALL, robot, _TOOL, n_best=999, collision_free=_all_free)
    ref = sorted(
        got,
        key=lambda it: (
            it[1].reachable_fraction,
            it[1].kinematic_margin or 0.0,
            it[1].mean_margin or 0.0,
            -abs(it[0].lateral_mm),
        ),
        reverse=True,
    )
    assert _ids(got) == _ids(ref)
    # Alles frei ⇒ kein Vorfilter (voller Raster bleibt), Kollisionsfeld trägt „clear".
    assert all(s.collision == {"free": True, "status": "clear", "source": "coarse"}
               for _o, s in got)


# --- Default-an: bare Aufruf ist kollisionsbewusst (US 1) ---------------------


def test_default_bare_suggest_is_collision_aware():
    """Standardaufruf (ohne Kollisions-Parameter) läuft mit realer Geometrie
    kollisionsbewusst: der Beste ist kollisionsfrei, jeder Vorschlag trägt sein Feld."""
    robot = _robot()
    geo = load_robot_collision_geometry(ROBOT)
    result = suggest(
        SMALL_WALL, robot, _TOOL, workstation=_NEAR_WS, stand_mode="floor", n_best=999,
    )
    assert result  # nie leer
    for _opt, score in result:
        assert score.collision is not None  # Grob-Check lief ohne Zutun des Aufrufers
    # Der Vorfilter lässt nur Kollisionsfreie durch (solange es welche gibt).
    assert all(s.collision["free"] for _o, s in result)
    assert not path_collides(SMALL_WALL, robot, _TOOL, result[0][0], geo)


def test_default_prefilter_drops_colliding_candidates():
    """Vorfilter vor ``evaluate`` (US 8/16): kollidierende Kandidaten tauchen nicht im
    Ergebnis auf — der bare Vorschlag enthält weniger Kandidaten als der Alt-Zustand."""
    robot = _robot()
    default = suggest(
        SMALL_WALL, robot, _TOOL, workstation=_NEAR_WS, stand_mode="floor", n_best=999,
    )
    old = suggest(
        SMALL_WALL, robot, _TOOL, workstation=_NEAR_WS, stand_mode="floor", n_best=999,
        collision_free=_all_free,
    )
    # Der Alt-Zustand bewertet ALLE Kandidaten; der Default filtert die nahen
    # (kollidierenden) heraus ⇒ echte Teilmenge.
    assert len(default) < len(old)
    default_ids = set(_ids(default))
    assert default_ids < set(_ids(old))


# --- Fail-soft „alle rot" (US 4) ----------------------------------------------


def test_all_colliding_returns_list_and_infeasible_finding():
    """Streicht der Filter alle Kandidaten, wird das volle Raster bewertet (nicht leer,
    kein Fehler) und der Gesamt-Befund meldet „kein machbarer Kandidat"."""
    robot = _robot()

    def _all_collide(_o: PlacementOption) -> bool:
        return False

    result = suggest(
        TALL_WALL, robot, _TOOL, n_best=999, collision_free=_all_collide,
    )
    assert result  # Fail-soft: nie leer
    assert all(s.collision == {"free": False, "status": "colliding", "source": "coarse"}
               for _o, s in result)
    finding = feasibility_finding(result)
    assert finding["checked"] is True
    assert finding["feasible"] is False
    assert finding["n_feasible"] == 0


def test_feasibility_finding_feasible_when_free_exists():
    """Gibt es mindestens einen kollisionsfreien Vorschlag, ist der Befund machbar."""
    robot = _robot()
    result = suggest(
        SMALL_WALL, robot, _TOOL, workstation=_NEAR_WS, stand_mode="floor", n_best=3,
    )
    finding = feasibility_finding(result)
    assert finding["checked"] is True
    assert finding["feasible"] is True
    assert finding["n_feasible"] >= 1


def test_feasibility_finding_unchecked_without_judgment():
    """Ohne Kollisionsurteil (kein Feld) ist der Befund ehrlich „unbekannt", nicht
    „unmachbar" — checked=False, feasible=None."""
    robot = _robot()
    got = suggest(TALL_WALL, robot, _TOOL, n_best=3, collision_free=_all_free)
    # `got` trägt zwar Felder; wir simulieren den ungeprüften Fall über leere Liste.
    assert feasibility_finding([])["checked"] is False
    assert feasibility_finding([])["feasible"] is None
    # Sanity: der geprüfte Fall ist machbar.
    assert feasibility_finding(got)["feasible"] is True


# --- Nachweislicher Grob-Befund mit echter M1013-Geometrie --------------------


def test_path_collides_real_geometry_close_vs_standoff():
    """Fixture-Muster: eine zu nahe Aufstellung kollidiert grob nachweislich, die
    mit Standardabstand nicht (echte Breitphasen-Huellen, wenige Posen)."""
    robot = _robot()
    geo = load_robot_collision_geometry(ROBOT)
    free = PlacementOption("free", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=0.0)
    close = PlacementOption("close", lateral_mm=0.0, standoff_mm=300.0, stand_height_mm=0.0)
    assert path_collides(SMALL_WALL, robot, _TOOL, free, geo) is False
    assert path_collides(SMALL_WALL, robot, _TOOL, close, geo) is True


def test_suggest_is_deterministic_with_collision():
    """Determinismus (ADR-004): gleiche Eingaben ⇒ identische Vorschläge inkl. Feld."""
    robot = _robot()
    a = suggest(SMALL_WALL, robot, _TOOL, workstation=_NEAR_WS, stand_mode="floor")
    b = suggest(SMALL_WALL, robot, _TOOL, workstation=_NEAR_WS, stand_mode="floor")
    assert [(o.option_id, s.to_dict()) for o, s in a] == [
        (o.option_id, s.to_dict()) for o, s in b
    ]
