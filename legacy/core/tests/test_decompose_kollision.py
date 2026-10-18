"""Kollisionsgetriebene Verfeinerung der Zerlegung (Issue #165, Constraint-Serie Scheibe 4).

Geprüft wird das externe Verhalten der :class:`KollisionsGetriebeneVerfeinerung` an der
#216-Strategie-Naht (kein zweiter Verfeinerungs-Loop) mit einem **synthetischen
Prüf-Tür-Orakel** (Muster wie die Advisor-Tests, ``fgc.collision.advisor``): das Orakel
modelliert Kollisionen deterministisch als Funktion der Zellgröße + Option, die Strategie
treibt den Schnitt bis zur Kollisionsfreiheit.

Akzeptanz (#165):
- (a) ein heute kollidierender Fall endet kollisionsfrei — Orakel: voller Befund je
  finalem Teil frei;
- (b) gewählte Optionen (IK/Platzierung) nachvollziehbar in Provenienz + Teil-Platzierungen;
- (c) Determinismus: gleicher Input + Kontingent ⇒ bit-gleicher Schnitt;
- (d) Negativ-Invarianten: Kipp/Tiefenteilung nie automatisch.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from fgc.decompose import (
    KollisionsGetriebeneVerfeinerung,
    RasterAufgabe,
    band_raster_kandidaten,
    causing_axis,
    option_menu,
    propose,
)
from fgc.decompose.strategie import GreedyAchsenVerfeinerung
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.placement import WallSurface

ROBOT = "doosan_m1013"

#: Kollidierende Wand (überhoch): 1×1 kollidiert, Verfeinerung muss teilen.
WALL = WallSurface(length_mm=800.0, height_mm=1000.0, thickness_mm=200.0)


# --------------------------------------------------------------------------- #
# Synthetisches Prüf-Tür-Orakel (deterministisch, zählt Aufrufe)
# --------------------------------------------------------------------------- #


@dataclass
class FakeBefund:
    """Minimaler :class:`fgc.decompose.strategie.PruefBefund` (Duck-Typing)."""

    collides: bool
    causer_position_mm: tuple | None = None


class FakePruefTuer:
    """Deterministisches Fake-Orakel: ``free_if(cell_len, cell_h, option) → bool``.

    Kollidiert eine Zelle, liegt die Verursacher-Position über ``causer`` fest (steuert
    die verursachende Achse). ``calls`` protokolliert jeden Aufruf (Kontingent-/Invarianz-
    Prüfung). ``unzustaendig=True`` liefert stets ``None`` (keine Kollisions-Geometrie).
    """

    def __init__(self, free_if, causer=None, unzustaendig=False):
        self.free_if = free_if
        self._causer = causer or (lambda cl, ch, opt: (0.0, 0.0, ch))  # Default: hohe z ⇒ Höhe
        self.unzustaendig = unzustaendig
        self.calls: list[tuple] = []

    def __call__(self, kandidat, row_index, option):
        self.calls.append((kandidat.n_length, kandidat.n_height, row_index, option))
        if self.unzustaendig:
            return None
        cl = kandidat.wall.length_mm / kandidat.n_length
        ch = kandidat.wall.height_mm / kandidat.n_height
        if self.free_if(cl, ch, option):
            return FakeBefund(collides=False)
        return FakeBefund(collides=True, causer_position_mm=self._causer(cl, ch, option))


def _aufgabe(wall, pruef_tuer, *, call_budget=50, cap=16):
    """Baut die RasterAufgabe wie ``propose`` sie der Strategie reicht (ohne echte Kinematik)."""
    return RasterAufgabe(
        frac_at=lambda nv, nh: 0.0,  # Reichweite hier irrelevant — Kollision treibt.
        start=(1, 1),
        cap=cap,
        kandidaten=band_raster_kandidaten(wall, cap=cap),
        call_budget=call_budget,
        pruef_tuer=pruef_tuer,
    )


def _re_pruef_frei(wall, wahl, free_if, causer=None):
    """Akzeptanz-Orakel (a): ist **jede** finale Zelle unter ihrer gewählten Option frei?"""
    tuer = FakePruefTuer(free_if, causer=causer)
    kand = band_raster_kandidaten(wall, cap=16)
    lookup = {(k.n_length, k.n_height): k for k in kand}
    kandidat = lookup[(wahl.n_length, wahl.n_height)]
    for h_idx in range(wahl.n_height):
        opt = wahl.zellen_optionen[h_idx]
        befund = tuer(kandidat, h_idx, opt)
        assert befund is not None and not befund.collides, (h_idx, opt)


# --------------------------------------------------------------------------- #
# Strategie (Einheit, ohne echte Kinematik)
# --------------------------------------------------------------------------- #


def test_baseline_free_no_subdivision():
    """Alles frei ab Basis ⇒ 1×1, jede Reihe trägt die Basis-Option (kein Hebel)."""
    tuer = FakePruefTuer(free_if=lambda cl, ch, opt: True)
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(_aufgabe(WALL, tuer))
    assert (wahl.n_length, wahl.n_height) == (1, 1)
    assert all(o.is_baseline for o in wahl.zellen_optionen)
    assert wahl.provenienz["calls_used"] == 1


def test_ik_lever_frees_cell_hebel1():
    """Hebel 1: Basis kollidiert, ein IK-Zweig macht frei ⇒ keine Teilung, IK gewählt."""
    def free_if(cl, ch, opt):
        return opt.ik_block == {"wrist": "b"}

    tuer = FakePruefTuer(free_if)
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(_aufgabe(WALL, tuer))
    assert (wahl.n_length, wahl.n_height) == (1, 1)
    assert wahl.zellen_optionen[0].ik_block == {"wrist": "b"}
    assert wahl.zellen_optionen[0].placement_delta is None


def test_placement_lever_frees_cell_hebel1():
    """Hebel 1: Basis + IK kollidieren, ein Platzierungs-Delta macht frei ⇒ keine Teilung."""
    def free_if(cl, ch, opt):
        return opt.placement_delta == {"standoff_mm": 50.0}

    tuer = FakePruefTuer(free_if)
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(_aufgabe(WALL, tuer))
    assert (wahl.n_length, wahl.n_height) == (1, 1)
    assert wahl.zellen_optionen[0].placement_delta == {"standoff_mm": 50.0}


def test_subdivides_height_along_causing_axis():
    """Hebel 2 (Bandhöhe senken) entlang der verursachenden Achse aus dem Befund.

    Zelle frei ⇔ Höhe ≤ 600; kollidierend zeigt der Verursacher nach oben (hohe z) ⇒
    ``causing_axis`` = height ⇒ nur die Höhe wird geteilt (Breite bleibt 1). Akzeptanz (a).
    """
    def free_if(cl, ch, opt):
        return ch <= 600.0

    def causer(cl, ch, opt):
        return (0.0, 0.0, ch)  # oben ⇒ Höhe

    tuer = FakePruefTuer(free_if, causer=causer)
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(_aufgabe(WALL, tuer))
    assert wahl.n_length == 1
    assert wahl.n_height == 2  # 1000/2 = 500 ≤ 600
    _re_pruef_frei(WALL, wahl, free_if, causer)


def test_subdivides_length_along_causing_axis():
    """Hebel 3 (Breite teilen) entlang der verursachenden Achse aus dem Befund.

    Zelle frei ⇔ Länge ≤ 500; kollidierend zeigt der Verursacher seitlich (großes x) ⇒
    ``causing_axis`` = length ⇒ nur die Breite wird geteilt (Höhe bleibt 1). Akzeptanz (a).
    """
    def free_if(cl, ch, opt):
        return cl <= 500.0

    def causer(cl, ch, opt):
        return (cl / 2.0, 0.0, ch / 2.0)  # seitlich ⇒ Länge

    tuer = FakePruefTuer(free_if, causer=causer)
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(_aufgabe(WALL, tuer))
    assert wahl.n_height == 1
    assert wahl.n_length == 2  # 800/2 = 400 ≤ 500
    _re_pruef_frei(WALL, wahl, free_if, causer)


def test_kipp_and_lead_never_automatic():
    """Negativ-Invariante (d): kein Menü-Eintrag trägt Kipp/Lead — nie automatisch (#141)."""
    for opt in option_menu():
        assert opt.placement_delta is None or not (
            {"kipp_mm", "lead_mm", "kipp_deg", "lead_deg", "kipp_rad", "lead_rad"}
            & set(opt.placement_delta)
        )
        assert opt.ik_block is None or "kipp" not in opt.ik_block


def test_kipp_never_in_probed_options():
    """Negativ-Invariante (d): auch im Lauf wird nie eine Kipp/Lead-Option geprüft."""
    def free_if(cl, ch, opt):
        return ch <= 300.0

    tuer = FakePruefTuer(free_if, causer=lambda cl, ch, opt: (0.0, 0.0, ch))
    KollisionsGetriebeneVerfeinerung().waehle_raster(_aufgabe(WALL, tuer))
    for _nv, _nh, _row, opt in tuer.calls:
        pd = opt.placement_delta or {}
        assert not any("kipp" in k or "lead" in k for k in pd)
        assert opt.ik_block is None or "kipp" not in opt.ik_block


def test_depth_split_never_automatic():
    """Negativ-Invariante (d): die Verfeinerung teilt nur Höhe/Länge (Band-Raster) — nie Tiefe.

    Jedes geprüfte Raster ist ein 2D-Band-Raster (n_length × n_height); es gibt keinen
    Tiefen-Freiheitsgrad. Die Wanddicke bleibt über alle Kandidaten konstant (#142).
    """
    def free_if(cl, ch, opt):
        return ch <= 300.0

    tuer = FakePruefTuer(free_if, causer=lambda cl, ch, opt: (0.0, 0.0, ch))
    KollisionsGetriebeneVerfeinerung().waehle_raster(_aufgabe(WALL, tuer))
    thicknesses = {band.wall.thickness_mm for band in band_raster_kandidaten(WALL, cap=16)}
    assert thicknesses == {WALL.thickness_mm}


def test_call_budget_caps_and_is_best_effort():
    """Aufruf-Kontingent (#178): nie mehr als ``call_budget`` Prüf-Tür-Aufrufe; best effort."""
    tuer = FakePruefTuer(free_if=lambda cl, ch, opt: False)  # nie frei
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(
        _aufgabe(WALL, tuer, call_budget=5)
    )
    assert len(tuer.calls) <= 5
    assert wahl.provenienz["budget_exhausted"] is True
    assert len(wahl.zellen_optionen) == wahl.n_height  # jede Reihe trägt eine Option


def test_max_divisions_cap_respected():
    """MAX_DIVISIONS-Deckel bleibt: nie über ``cap`` teilen (auch wenn nie frei)."""
    tuer = FakePruefTuer(
        free_if=lambda cl, ch, opt: False, causer=lambda cl, ch, opt: (0.0, 0.0, ch)
    )
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(
        _aufgabe(WALL, tuer, call_budget=10_000, cap=3)
    )
    assert wahl.n_height <= 3
    assert wahl.n_length <= 3


def test_determinism_same_input_same_cut():
    """Akzeptanz (c): gleicher Input + Kontingent ⇒ bit-gleicher Schnitt + Optionen."""
    def free_if(cl, ch, opt):
        return ch <= 350.0

    def causer(cl, ch, opt):
        return (0.0, 0.0, ch)

    a = KollisionsGetriebeneVerfeinerung().waehle_raster(
        _aufgabe(WALL, FakePruefTuer(free_if, causer=causer))
    )
    b = KollisionsGetriebeneVerfeinerung().waehle_raster(
        _aufgabe(WALL, FakePruefTuer(free_if, causer=causer))
    )
    assert (a.n_length, a.n_height) == (b.n_length, b.n_height)
    assert a.zellen_optionen == b.zellen_optionen


def test_fallback_to_greedy_without_oracle():
    """Fail-soft: ohne Orakel fällt die Strategie auf den Achsen-Greedy zurück (byte-gleich)."""
    aufgabe = RasterAufgabe(frac_at=lambda nv, nh: 1.0, start=(2, 3), cap=16)
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(aufgabe)
    greedy = GreedyAchsenVerfeinerung().waehle_raster(aufgabe)
    assert (wahl.n_length, wahl.n_height) == (greedy.n_length, greedy.n_height)
    assert wahl.provenienz["fallback"] == "kein-orakel"


def test_fallback_when_oracle_unzustaendig():
    """Fail-soft: Orakel meldet ``None`` (keine Geometrie) ⇒ Greedy-Fallback, nie geratenes frei."""
    tuer = FakePruefTuer(free_if=lambda cl, ch, opt: True, unzustaendig=True)
    wahl = KollisionsGetriebeneVerfeinerung().waehle_raster(_aufgabe(WALL, tuer))
    assert wahl.provenienz["fallback"] == "unzustaendig"


def test_causing_axis_reads_from_befund():
    """``causing_axis`` liest die Achse aus der Verursacher-Position (keine Heuristik)."""
    assert causing_axis(800.0, 1000.0, (0.0, 0.0, 950.0)) == "height"  # hohe z
    assert causing_axis(800.0, 1000.0, (390.0, 0.0, 500.0)) == "length"  # großes x
    assert causing_axis(800.0, 1000.0, None) == "height"  # kein Befund ⇒ Bandhöhe zuerst


# --------------------------------------------------------------------------- #
# Integration durch propose (echte Kinematik für die Platzierungssuche je Reihe)
# --------------------------------------------------------------------------- #


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


def test_propose_lands_placement_option_and_provenance(robot, tool):
    """Akzeptanz (b): der gewählte Platzierungs-Hebel landet in der Teil-Platzierung, die
    Provenienz (Strategie/Kontingent/Hebel je Reihe) in ``plan.refinement``."""
    # Basis kollidiert, ein Standoff-Delta macht frei — keine Teilung nötig.
    tuer = FakePruefTuer(free_if=lambda cl, ch, opt: opt.placement_delta == {"standoff_mm": 50.0})
    plan = propose(WALL, robot, tool, pruef_tuer=tuer)
    assert plan.n_length == 1 and plan.n_height == 1
    # (b) Platzierung: der Standoff-Delta ist auf die Reihen-Platzierung addiert.
    baseline = propose(WALL, robot, tool)
    base_standoff = baseline.sections[0].placement.standoff_mm
    assert plan.sections[0].placement.standoff_mm == pytest.approx(base_standoff + 50.0)
    # (b) Provenienz: Strategie benannt, Hebel je Reihe nachvollziehbar.
    assert plan.refinement is not None
    assert plan.refinement["strategy"] == "kollisionsgetriebene-verfeinerung"
    assert plan.refinement["rows"][0]["collision_free"] is True
    assert plan.refinement["rows"][0]["option"]["placement_delta"] == {"standoff_mm": 50.0}


def test_propose_default_path_byte_identical(robot, tool):
    """Ohne ``pruef_tuer`` bleibt ``propose`` byte-gleich (Regressionsanker, kein refinement)."""
    plan = propose(WALL, robot, tool)
    assert plan.refinement is None


def test_refinement_lands_in_artifact(robot, tool):
    """Akzeptanz (b): die Verfeinerungs-Provenienz landet additiv im decompose-Artefakt."""
    from fgc.decompose import decompose_artifact, evaluate

    tuer = FakePruefTuer(free_if=lambda cl, ch, opt: opt.placement_delta == {"standoff_mm": 50.0})
    plan = propose(WALL, robot, tool, pruef_tuer=tuer)
    statuses = evaluate(plan, robot, tool)
    doc = decompose_artifact(
        ROBOT, tool.name, plan, statuses,
        {"source": "test", "created": "2026-07-15T00:00:00Z", "git_commit": "0"},
    )
    assert doc["refinement"]["strategy"] == "kollisionsgetriebene-verfeinerung"
    # Ohne Verfeinerung fehlt der Block ganz (byte-gleich, Altläufe gültig).
    plain_plan = propose(WALL, robot, tool)
    plain = decompose_artifact(
        ROBOT, tool.name, plain_plan, evaluate(plain_plan, robot, tool),
        {"source": "test", "created": "2026-07-15T00:00:00Z", "git_commit": "0"},
    )
    assert "refinement" not in plain


def test_propose_collision_free_end_to_end_determinism(robot, tool):
    """Akzeptanz (a)+(c) durch propose: kollidierender Fall endet frei, deterministisch."""
    def free_if(cl, ch, opt):
        return ch <= 600.0

    def causer(cl, ch, opt):
        return (0.0, 0.0, ch)

    a = propose(WALL, robot, tool, pruef_tuer=FakePruefTuer(free_if, causer=causer))
    b = propose(WALL, robot, tool, pruef_tuer=FakePruefTuer(free_if, causer=causer))
    assert (a.n_length, a.n_height) == (b.n_length, b.n_height) == (1, 2)
    # Determinismus: gleicher Schnitt + gleiche Platzierungen.
    assert [s.placement.standoff_mm for s in a.sections] == [
        s.placement.standoff_mm for s in b.sections
    ]
