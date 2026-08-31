"""Beam-Suche end-to-end (Issue #217, PRD #183 Stufe 3, US 9/10/11/20/22/25).

Geprueft wird das externe Verhalten der :class:`fgc.decompose.beam.BeamSuche` an
der #216-Strategie-Naht mit **synthetischen** Lieferanten (Scorer + Pruef-Tuer):
der Scorer ist ein deterministisches Fake ueber ``(n_length, n_height)`` (keine
Karte noetig), die Pruef-Tuer das Advisor-Muster-Fake aus
``test_decompose_kollision``. Ein Integrationsteil fuehrt die Beam-Suche durch
``propose`` mit einem **echten** ``BilligerScorer`` (grobe Reichweitenkarte).

Akzeptanz (#217):
- (US 9) kollidierende Zerlegung wird nicht vorgeschlagen; die Suche findet
  automatisch einen besseren Schnitt.
- (US 25) Kontingent-Determinismus: gleicher Input ⇒ bit-gleicher Schnitt.
- (US 22) leerer Fall zuendet die Leiter Stufe fuer Stufe (Befund + Provenienz);
  Nie-Relaxieren-Invarianten als Negativ-Tests.
- (US 10) Verworfen-Gruende (Reichweite/Fragment/Kollision) nachvollziehbar.
- (US 20) Metriken-Katalog je Lauf vollstaendig.
- Hintergrundlauf mit Fortschritt + Abbruch (Muster #145/#175).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest

from fgc.decompose.beam import (
    GRUND_FRAGMENT,
    GRUND_KOLLISION,
    GRUND_REICHWEITE,
    RELAX_MEHR_STANDPLAETZE,
    RELAX_MEHR_TEILE,
    RELAX_TIEFENTEILUNG,
    BeamSuche,
    beam_breite,
)
from fgc.decompose.kandidaten import BandRasterKandidat, band_raster_kandidaten
from fgc.decompose.objective import KriterienWerte, ObjectiveConfig
from fgc.decompose.scorer import KandidatBewertung
from fgc.decompose.strategie import GreedyAchsenVerfeinerung, RasterAufgabe, option_menu
from fgc.placement import WallSurface

WALL = WallSurface(length_mm=800.0, height_mm=1000.0, thickness_mm=200.0)


# --------------------------------------------------------------------------- #
# Synthetische Lieferanten (deterministisch, ohne Geometrie/Karte)
# --------------------------------------------------------------------------- #


def _bewertung(
    kandidat: BandRasterKandidat,
    *,
    erreichbar: bool = True,
    fragment: bool = False,
) -> KandidatBewertung:
    """Baut eine :class:`KandidatBewertung` mit gesteuerten Kriterienwerten.

    ``umsetzvorgaenge = n_height`` (mehr Hoehenbaender = mehr Standplaetze),
    ``fugenflaeche ∝ innere Schnitte`` — so ordnet der Default-Komparator (#212)
    grob vor fein (weniger Umsetzen zuerst, dann weniger Fugen).
    """
    n = kandidat.n_parts
    werte = KriterienWerte(
        erreichbar=erreichbar,
        umsetzvorgaenge=float(kandidat.n_height),
        fugenflaeche_mm2=float((kandidat.n_length - 1) + (kandidat.n_height - 1)) * 1000.0,
        kinematische_marge_mm=100.0,
        volumen_cv=0.0,
    )
    inseln = tuple(2 if fragment else 1 for _ in range(n))
    gedeckt = tuple(erreichbar for _ in range(kandidat.n_height))
    return KandidatBewertung(
        kandidat=kandidat,
        werte=werte,
        reihen_gedeckt=gedeckt,
        standplaetze=(),
        inseln_je_teil=inseln,
    )


def _bewerte(erreichbar=None, fragment=None):
    """Eine ``bewerte``-Closure ueber Praedikaten auf ``(n_length, n_height)``."""

    def call(kandidat: BandRasterKandidat) -> KandidatBewertung:
        e = True if erreichbar is None else erreichbar(kandidat.n_length, kandidat.n_height)
        f = False if fragment is None else fragment(kandidat.n_length, kandidat.n_height)
        return _bewertung(kandidat, erreichbar=e, fragment=f)

    return call


@dataclass
class FakeBefund:
    collides: bool
    causer_position_mm: tuple | None = None


class FakePruefTuer:
    """Deterministische Pruef-Tuer: ``free_if(n_length, n_height, option) → bool``."""

    def __init__(self, free_if, unzustaendig=False):
        self.free_if = free_if
        self.unzustaendig = unzustaendig
        self.calls: list[tuple] = []

    def __call__(self, kandidat, row_index, option):
        self.calls.append((kandidat.n_length, kandidat.n_height, row_index, option))
        if self.unzustaendig:
            return None
        if self.free_if(kandidat.n_length, kandidat.n_height, option):
            return FakeBefund(collides=False)
        return FakeBefund(collides=True, causer_position_mm=(0.0, 0.0, 0.0))


def _aufgabe(wall, *, bewerte, pruef_tuer=None, call_budget=500, cap=2, objective=None):
    return RasterAufgabe(
        frac_at=lambda _nv, _nh: 0.0,
        start=(1, 1),
        cap=cap,
        kandidaten=band_raster_kandidaten(wall, cap=cap),
        bewerte=bewerte,
        objective=objective or ObjectiveConfig(),
        call_budget=call_budget,
        pruef_tuer=pruef_tuer,
    )


def _strip_zeit(prov: dict) -> dict:
    """Provenienz ohne die rein diagnostische, nicht-deterministische Rechenzeit."""
    p = {k: v for k, v in prov.items() if k != "metriken"}
    m = {k: v for k, v in prov["metriken"].items() if k != "rechenzeit_s"}
    p["metriken"] = m
    return p


# --------------------------------------------------------------------------- #
# Beam-Breite aus dem Kontingent (kein eigener Parameter)
# --------------------------------------------------------------------------- #


def test_beam_breite_aus_kontingent():
    assert beam_breite(20) == 20
    assert beam_breite(1) == 1
    assert beam_breite(None) == 20  # Fallback spiegelt DEFAULT_CALL_BUDGET
    assert beam_breite(0) == 1  # mindestens 1


# --------------------------------------------------------------------------- #
# US 9 — kollidierende Zerlegung wird nicht vorgeschlagen, Suche findet bessere
# --------------------------------------------------------------------------- #


def test_kollidierende_zerlegung_wird_nicht_vorgeschlagen():
    """1×1 kollidiert (bester Score), die Suche waehlt automatisch einen freien Schnitt."""
    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: not (nl == 1 and nh == 1))
    wahl = BeamSuche().waehle_raster(_aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer))

    assert (wahl.n_length, wahl.n_height) != (1, 1)  # nicht der kollidierende Schnitt
    assert wahl.provenienz["geprueft"] is True
    # 1×1 taucht als Verworfen-Grund „Kollision" auf (nachvollziehbar, US 10).
    kollisionen = [v for v in wahl.provenienz["verworfen"] if v["grund"] == GRUND_KOLLISION]
    assert any(v["kandidat"] == "band-1x1" for v in kollisionen)
    assert wahl.provenienz["relaxation"] == []  # im ersten Durchgang gefunden


def test_nur_ueberlebende_durchlaufen_die_prueftuer():
    """Unerreichbare/fragmentierte Kandidaten werden NIE der Pruef-Tuer vorgelegt (US 10/11)."""
    # 2×2 unerreichbar (K.-o.), 2×1 fragmentiert — beide vor der Pruef-Tuer aussortiert.
    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: not (nl == 1 and nh == 1))
    bewerte = _bewerte(
        erreichbar=lambda nl, nh: not (nl == 2 and nh == 2),
        fragment=lambda nl, nh: nl == 2 and nh == 1,
    )
    wahl = BeamSuche().waehle_raster(_aufgabe(WALL, bewerte=bewerte, pruef_tuer=tuer))
    geprueft_raster = {(nl, nh) for nl, nh, _r, _o in tuer.calls}
    assert (2, 2) not in geprueft_raster  # nie geprueft (Reichweite-K.-o.)
    assert (2, 1) not in geprueft_raster  # nie geprueft (Fragment)
    gruende = {v["grund"] for v in wahl.provenienz["verworfen"]}
    assert GRUND_REICHWEITE in gruende and GRUND_FRAGMENT in gruende


# --------------------------------------------------------------------------- #
# US 25 — Kontingent-Determinismus (bit-gleicher Schnitt)
# --------------------------------------------------------------------------- #


def test_kontingent_determinismus_bitgleich():
    """Gleicher Input + gleiches Kontingent ⇒ bit-gleicher Schnitt, Optionen, Provenienz."""
    free_if = lambda nl, nh, opt: nh >= 2  # noqa: E731 — nur bei geteilter Hoehe frei
    a = BeamSuche().waehle_raster(
        _aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=FakePruefTuer(free_if))
    )
    b = BeamSuche().waehle_raster(
        _aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=FakePruefTuer(free_if))
    )
    assert (a.n_length, a.n_height) == (b.n_length, b.n_height)
    assert a.zellen_optionen == b.zellen_optionen
    assert _strip_zeit(a.provenienz) == _strip_zeit(b.provenienz)
    assert a.provenienz["calls_used"] == b.provenienz["calls_used"]  # Aufrufe, keine Zeit


# --------------------------------------------------------------------------- #
# US 22 — Relaxationsleiter Stufe fuer Stufe + Nie-Relaxieren-Invarianten
# --------------------------------------------------------------------------- #


def test_leiter_stufe1_mehr_teile():
    """cap=1 (nur 1×1) kollidiert ⇒ Stufe „mehr Teile" zuendet und findet einen freien Schnitt."""
    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: not (nl == 1 and nh == 1))
    wahl = BeamSuche().waehle_raster(
        _aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer, cap=1)
    )
    assert wahl.provenienz["relaxation"] == [RELAX_MEHR_TEILE]
    assert (wahl.n_length, wahl.n_height) != (1, 1)
    assert wahl.provenienz["geprueft"] is True


def test_leiter_stufe2_mehr_standplaetze():
    """Nichts frei ohne mehr Standplaetze; rescore macht ein Raster erreichbar ⇒ Stufe 2 zuendet."""
    # Basis-Scorer: alles unerreichbar (K.-o.) → kein verifizierbarer Kandidat.
    basis = _bewerte(erreichbar=lambda nl, nh: False)

    def rescore(heights):
        # Mehr Standplaetze ⇒ 1×2 wird erreichbar (und die Pruef-Tuer sieht es frei).
        return _bewerte(erreichbar=lambda nl, nh: nh >= 2)

    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: nh >= 2)
    strat = BeamSuche(stand_heights_ladder=[(0.0, 1200.0)], rescore=rescore)
    wahl = strat.waehle_raster(_aufgabe(WALL, bewerte=basis, pruef_tuer=tuer))
    assert wahl.provenienz["relaxation"] == [RELAX_MEHR_TEILE, RELAX_MEHR_STANDPLAETZE]
    assert wahl.n_height >= 2
    assert wahl.provenienz["geprueft"] is True


def test_leiter_stufe3_tiefenteilungsvorschlag_und_best_effort():
    """Nichts hilft ⇒ ganze Leiter zuendet, Tiefenteilungs-Vorschlag, ehrlich ungeprueft (US 22)."""
    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: False)  # nie frei

    def rescore(heights):
        return _bewerte()  # bleibt erreichbar, aber die Pruef-Tuer verweigert alles

    strat = BeamSuche(stand_heights_ladder=[(0.0, 1200.0)], rescore=rescore)
    wahl = strat.waehle_raster(
        _aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer, call_budget=5000)
    )
    assert wahl.provenienz["relaxation"] == [
        RELAX_MEHR_TEILE,
        RELAX_MEHR_STANDPLAETZE,
        RELAX_TIEFENTEILUNG,
    ]
    assert wahl.provenienz["leer"] is True
    # Ehrlichkeitsregel: best effort ist NIE „geprueft frei" (ADR-007).
    assert wahl.provenienz["geprueft"] is False
    tv = wahl.provenienz["tiefenteilung_vorschlag"]
    assert tv["anwendung"] == "manuell"  # nie automatisch (#166/#142)


def test_nie_relaxieren_erreichbarkeits_ko():
    """Negativ-Invariante: ein unerreichbarer Kandidat wird nie „geprueft frei" (K.-o. bleibt)."""
    # Alles unerreichbar, keine Standplatz-Relaxation ⇒ leer, best effort ungeprueft.
    strat = BeamSuche()
    wahl = strat.waehle_raster(
        _aufgabe(WALL, bewerte=_bewerte(erreichbar=lambda nl, nh: False), pruef_tuer=None)
    )
    assert wahl.provenienz["leer"] is True
    assert wahl.provenienz["geprueft"] is False  # nie geratenes „frei"


def test_nie_relaxieren_kipp_lead_und_tiefe():
    """Negativ-Invariante: kein geprueftes Menue traegt Kipp/Lead; Dicke konstant (keine Tiefe)."""
    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: False)  # zwingt volles Menue je Reihe
    BeamSuche().waehle_raster(_aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer, cap=2))
    for _nl, _nh, _row, opt in tuer.calls:
        pd = opt.placement_delta or {}
        assert not any("kipp" in k or "lead" in k for k in pd)
        assert opt.ik_block is None or "kipp" not in opt.ik_block
    # Alle Kandidaten teilen dieselbe Wanddicke — die Suche teilt nie die Tiefe (#142).
    dicken = {k.wall.thickness_mm for k in band_raster_kandidaten(WALL, cap=16)}
    assert dicken == {WALL.thickness_mm}


def test_option_menu_hat_kein_kipp_lead():
    """Negativ-Invariante (statisch, #141): das Hebel-Menue traegt nie Kipp/Lead."""
    for opt in option_menu():
        pd = opt.placement_delta or {}
        assert not any("kipp" in k or "lead" in k for k in pd)


# --------------------------------------------------------------------------- #
# US 20 — Metriken-Katalog vollstaendig
# --------------------------------------------------------------------------- #


def test_metriken_katalog_vollstaendig():
    """Der Metriken-Katalog je Lauf traegt alle US-20-Kennzahlen."""
    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: not (nl == 1 and nh == 1))
    wahl = BeamSuche().waehle_raster(_aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer))
    m = wahl.provenienz["metriken"]
    assert set(m) == {
        "teilanzahl",
        "volumen_cv",
        "fugenflaeche_mm2",
        "erreichbarer_anteil",
        "geprueft_frei_anteil",
        "standplaetze",
        "rechenzeit_s",
    }
    assert m["geprueft_frei_anteil"] == 1.0  # Sieger: jede Reihe geprueft frei
    assert m["teilanzahl"] == wahl.n_length * wahl.n_height


# --------------------------------------------------------------------------- #
# Fail-soft (US 12) — kein Scorer / unzustaendige Pruef-Tuer ⇒ Achsen-Greedy
# --------------------------------------------------------------------------- #


def test_fail_soft_ohne_scorer_faellt_auf_greedy():
    aufgabe = RasterAufgabe(frac_at=lambda nv, nh: 1.0, start=(2, 3), cap=16)
    wahl = BeamSuche().waehle_raster(aufgabe)
    greedy = GreedyAchsenVerfeinerung().waehle_raster(aufgabe)
    assert (wahl.n_length, wahl.n_height) == (greedy.n_length, greedy.n_height)
    assert wahl.provenienz["fallback"] == "kein-scorer"


def test_fail_soft_unzustaendige_prueftuer_faellt_auf_greedy():
    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: True, unzustaendig=True)
    wahl = BeamSuche().waehle_raster(_aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer))
    assert wahl.provenienz["fallback"] == "unzustaendig"


# --------------------------------------------------------------------------- #
# Aufruf-Kontingent — hart, best effort (kein Zeitbudget)
# --------------------------------------------------------------------------- #


def test_kontingent_ist_hart_best_effort():
    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: False)  # nie frei
    wahl = BeamSuche().waehle_raster(
        _aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer, call_budget=5)
    )
    assert len(tuer.calls) <= 5
    assert wahl.provenienz["budget_exhausted"] is True
    assert wahl.provenienz["leer"] is True  # best effort


# --------------------------------------------------------------------------- #
# Hintergrundlauf mit Fortschritt + Abbruch (Muster #145/#175)
# --------------------------------------------------------------------------- #


def test_hintergrundlauf_fortschritt_und_abbruch():
    """Beam laeuft im Thread mit Fortschritt-Callback + Abbruch (wie CheckJob, #145/#175).

    Der Abbruch ist **deterministisch** an den Fortschritt gekoppelt (nach fuenf
    gemeldeten Aufrufen) statt an Thread-Timing — der Thread zeigt nur die
    Hintergrundlauffaehigkeit; das Verhalten bleibt reproduzierbar (US 25).
    """
    fortschritt: list[tuple[int, int]] = []
    cancel_nach = 5

    def on_progress(done: int, total: int) -> None:
        fortschritt.append((done, total))

    def should_cancel() -> bool:
        return len(fortschritt) >= cancel_nach

    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: False)  # laeuft, bis abgebrochen
    strat = BeamSuche(on_progress=on_progress, should_cancel=should_cancel)
    ergebnis: dict = {}

    def lauf():
        ergebnis["wahl"] = strat.waehle_raster(
            _aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer, call_budget=100_000)
        )

    t = threading.Thread(target=lauf)
    t.start()
    t.join(timeout=5.0)
    assert not t.is_alive()

    wahl = ergebnis["wahl"]
    assert len(fortschritt) == cancel_nach  # Fortschritt gemeldet, dann abgebrochen
    assert fortschritt[-1][1] == 100_000  # (done, budget)
    assert wahl.provenienz["cancelled"] is True
    assert wahl.provenienz["leer"] is True  # best effort nach Abbruch
    # Abbruch zuendet KEINE weitere Leiter-Stufe (kein Tiefenteilungs-Vorschlag).
    assert "tiefenteilung_vorschlag" not in wahl.provenienz


# --------------------------------------------------------------------------- #
# Integration durch propose (echter BilligerScorer + Reichweitenkarte)
# --------------------------------------------------------------------------- #

ROBOT = "doosan_m1013"
SMALL_WALL = WallSurface(length_mm=600.0, height_mm=400.0, thickness_mm=200.0)


@pytest.fixture(scope="module")
def robot():
    from fgc.domain.robot import RobotDef

    return RobotDef.load(ROBOT)


@pytest.fixture(scope="module")
def tool():
    from fgc.domain.tool import ToolDef

    return ToolDef(
        name="testduese",
        tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )


@pytest.fixture(scope="module")
def scorer(tool):
    from fgc.decompose.scorer import BilligerScorer
    from fgc.kinematics.opw import OpwKinematics
    from fgc.kinematics.reachability import ReachabilityMap

    reach = ReachabilityMap.build(OpwKinematics.from_robot(ROBOT), cell_mm=150.0, n_alpha=13)
    return BilligerScorer(reach, SMALL_WALL, tool, stand_heights_mm=(0.0, 800.0))


def test_propose_beam_end_to_end_landet_im_artefakt(robot, tool, scorer):
    """propose(scorer=…) fuehrt die Beam-Suche; Schnitt + Metriken landen im decompose-Artefakt."""
    from fgc.decompose import decompose_artifact, evaluate, propose

    tuer = FakePruefTuer(free_if=lambda nl, nh, opt: True)  # alles frei ⇒ groebster Schnitt
    plan = propose(
        SMALL_WALL, robot, tool, scorer=scorer, objective=ObjectiveConfig(), pruef_tuer=tuer
    )
    assert plan.refinement is not None
    assert plan.refinement["strategy"] == "beam-suche"
    assert "metriken" in plan.refinement and "beam_width" in plan.refinement

    # Ampel-Semantik unveraendert (US 11): evaluate liefert je Abschnitt einen Befund.
    statuses = evaluate(plan, robot, tool)
    assert len(statuses) == len(plan.sections)

    doc = decompose_artifact(
        ROBOT, tool.name, plan, statuses,
        {"source": "test", "created": "2026-07-15T00:00:00Z", "git_commit": "0"},
    )
    assert doc["refinement"]["strategy"] == "beam-suche"
    assert doc["refinement"]["metriken"]["teilanzahl"] == plan.n_length * plan.n_height


def test_propose_ohne_scorer_bleibt_byte_gleich(robot, tool):
    """Ohne scorer bleibt propose byte-gleich (kein refinement, Regressionsanker, US 12)."""
    from fgc.decompose import propose

    plan = propose(SMALL_WALL, robot, tool)
    assert plan.refinement is None


# --------------------------------------------------------------------------- #
# Beam-Suche fuer Art „modul" (Issue #237): feste Druckort-Platzierung
# --------------------------------------------------------------------------- #


class _FakeScorer:
    """Traeger des ``bewerte``-Aufrufs — ``propose`` greift auf ``scorer.bewerte`` zu."""

    def __init__(self, bewerte):
        self.bewerte = bewerte


def _druckort_ws():
    from fgc.domain.workstation import WorkstationDef

    return WorkstationDef(
        name="druckort", mobility="stationary", height_adjustable=False,
        base_heights_mm=(0.0,),
    )


def test_propose_modul_beam_suche_findet_schnitt_am_druckort(robot, tool):
    """#237-Kernverhalten: die Beam-Suche laeuft auch fuer Art „modul" — der erste
    geprueft-freie Kandidat gewinnt, alle Teile tragen die feste Druckort-Platzierung."""
    from fgc.decompose import propose

    wall = WallSurface(length_mm=800.0, height_mm=3200.0, thickness_mm=200.0)
    tuer = FakePruefTuer(free_if=lambda _nl, nh, _opt: nh >= 4)
    plan = propose(
        wall, robot, tool, kind="modul", workstation=_druckort_ws(),
        scorer=_FakeScorer(_bewerte()), objective=ObjectiveConfig(),
        pruef_tuer=tuer, call_budget=500,
    )
    assert plan.kind == "modul"
    assert plan.refinement is not None
    assert plan.refinement["strategy"] == "beam-suche"
    assert plan.refinement["geprueft"] is True
    # Die Suche findet die noetige Hoehenteilung (frei erst ab nh >= 4) — nie feiner
    # als noetig in der Hoehe. (Kein exakter Raster-Anker: bei den Fake-Werten fallen
    # die Fugenflaechen in denselben Quantisierungs-Schritt der Zielfunktion #212,
    # der stabile Schluessel-Tie-Break entscheidet dann die Laengsteilung.)
    assert plan.n_height == 4
    # Feste Workstation-Platzierung fuer ALLE Teile (ADR-022) — keine Suche je Zelle.
    lagen = {
        (sp.placement.lateral_mm, sp.placement.standoff_mm, sp.placement.stand_height_mm)
        for sp in plan.sections
    }
    assert len(lagen) == 1


def test_propose_modul_beam_menue_ist_platzierungs_frei(robot, tool):
    """Art „modul" probiert nur Basis + IK (ADR-022: die Platzierung ist fest —
    ein automatisches Platzierungs-Delta waere eine stille Lageaenderung)."""
    from fgc.decompose import propose

    wall = WallSurface(length_mm=800.0, height_mm=3200.0, thickness_mm=200.0)
    tuer = FakePruefTuer(free_if=lambda _nl, _nh, _opt: False)  # alles kollidiert
    propose(
        wall, robot, tool, kind="modul", workstation=_druckort_ws(),
        scorer=_FakeScorer(_bewerte()), objective=ObjectiveConfig(),
        pruef_tuer=tuer, call_budget=50,
    )
    assert tuer.calls  # die Pruef-Tuer lief (vorher: 0 Aufrufe, Befund #237)
    assert all(opt.placement_delta is None for (_nl, _nh, _row, opt) in tuer.calls)


def test_propose_modul_beam_respektiert_obergrenzen(robot, tool):
    """Modul-Obergrenzen (#90) filtern die Kandidatenmenge hart vor: kein geprueft-
    freier Sieger verletzt ``max_height_mm`` (ceil-Herleitung wie der Greedy-Start)."""
    from fgc.decompose import ModuleLimits, propose

    wall = WallSurface(length_mm=800.0, height_mm=3200.0, thickness_mm=200.0)
    tuer = FakePruefTuer(free_if=lambda _nl, _nh, _opt: True)  # alles frei
    plan = propose(
        wall, robot, tool, kind="modul", workstation=_druckort_ws(),
        limits=ModuleLimits(max_height_mm=900.0),
        scorer=_FakeScorer(_bewerte()), objective=ObjectiveConfig(),
        pruef_tuer=tuer, call_budget=500,
    )
    # 3200 / 900 ⇒ mindestens 4 Hoehenbaender; grobere Kandidaten existieren nicht.
    assert plan.n_height == 4
    assert all(nh >= 4 for (_nl, nh, _row, _opt) in tuer.calls)
