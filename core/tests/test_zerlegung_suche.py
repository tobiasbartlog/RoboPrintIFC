"""Bausteine der Zerlegungs-Suche (Issue #216, PRD #183 Stufe 3, US 19).

Drei Bausteine — noch ohne Beam-Loop, ohne Pruef-Tuer:

- **Strategie-Interface** (`fgc.decompose.strategie`), extrahiert aus
  ``propose._refine`` (#203): der Achsen-Greedy traegt das Interface (der
  #165-Greedy haengt an derselben Naht, kein Umbau hier), eine kandidaten-
  basierte Strategie (Beam-Minimalform, #217-Anschluss) ebenso; ``propose``
  laeuft ueber die Naht und bleibt mit dem Default bit-identisch.
- **Band-Raster-Generator** (`fgc.decompose.kandidaten`): deterministisch,
  stabile Ordnung, Schnittgeometrie identisch zu ``propose``.
- **Billiger Scorer** (`fgc.decompose.scorer`): Kriterienwerte (#212) aus
  Reichweitenkarte (#210/#214, Min-Aggregation) + Masken-/Matrixbewertung
  (Han/Z-Chunking); deterministisch (bit-gleich); die Werte speisen den
  #212-Komparator nachweislich (Rangfolge-Entscheid an echten Kandidaten).
"""

from __future__ import annotations

import pytest

from fgc.decompose.kandidaten import (
    BandRasterKandidat,
    band_raster_kandidat,
    band_raster_kandidaten,
)
from fgc.decompose.objective import ObjectiveConfig, candidate_key, compare_candidates
from fgc.decompose.propose import MAX_DIVISIONS, _build_cuts, propose
from fgc.decompose.scorer import (
    BilligerScorer,
    fugenflaeche_mm2,
    raycast_inselkarte,
    volumen_cv,
    wand_maske,
)
from fgc.decompose.strategie import (
    GreedyAchsenVerfeinerung,
    RasterAufgabe,
    RasterWahl,
    ZerlegungsStrategie,
)
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.kinematics.opw import OpwKinematics
from fgc.kinematics.reachability import ReachabilityMap
from fgc.placement.evaluate import WallSurface

ROBOT = "doosan_m1013"

SMALL_WALL = WallSurface(length_mm=600.0, height_mm=400.0, thickness_mm=200.0)
TALL_WALL = WallSurface(length_mm=600.0, height_mm=3200.0, thickness_mm=200.0)


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


# --- Baustein 1: Strategie-Interface (Extraktion aus propose._refine, #203) ----


def test_greedy_strategie_verfeinert_entlang_der_blockierenden_achse():
    """Der extrahierte Loop teilt nur die blockierende Achse (Hoehe) — wie _refine."""
    def frac_at(_nv: int, nh: int) -> float:
        return 1.0 if nh >= 3 else 0.2 * nh

    wahl = GreedyAchsenVerfeinerung().waehle_raster(
        RasterAufgabe(frac_at=frac_at, start=(1, 1), cap=8)
    )
    # Hoehenteilung hebt den Anteil staerker -> nur horizontal geteilt (1, 3);
    # die nicht-blockierende Laengsachse bleibt ungeteilt (Verhalten aus #203).
    assert wahl == RasterWahl(n_length=1, n_height=3)


def test_greedy_strategie_respektiert_cap_und_gleichstand():
    """Nie gruen: beide Achsen bis cap; Gleichstand bevorzugt die Laengsachse."""
    wahl = GreedyAchsenVerfeinerung().waehle_raster(
        RasterAufgabe(frac_at=lambda _nv, _nh: 0.5, start=(1, 1), cap=2)
    )
    assert (wahl.n_length, wahl.n_height) == (2, 2)


def test_greedy_traegt_das_interface_und_nennt_sich_in_der_provenienz():
    """Greedy-Anschluss am Interface (US 19): der #165-Greedy haengt an derselben Naht."""
    strategie = GreedyAchsenVerfeinerung()
    assert isinstance(strategie, ZerlegungsStrategie)
    # ADR-004: die Provenienz nennt Strategie + Surrogat-Modellstand (falls aktiv).
    assert strategie.provenance() == {
        "strategy": "greedy-achsen-verfeinerung",
        "surrogate_model": None,
    }


class _FixesRaster(ZerlegungsStrategie):
    """Test-Strategie: liefert ein festes Raster und protokolliert die Aufgabe."""

    name = "test-fixes-raster"

    def __init__(self, n_length: int, n_height: int) -> None:
        self.n_length = n_length
        self.n_height = n_height
        self.aufgaben: list[RasterAufgabe] = []

    def waehle_raster(self, aufgabe: RasterAufgabe) -> RasterWahl:
        self.aufgaben.append(aufgabe)
        return RasterWahl(n_length=self.n_length, n_height=self.n_height)


def test_propose_laeuft_ueber_die_strategie_naht(robot, tool):
    """propose konsumiert die injizierte Strategie — die Naht traegt jede Implementierung."""
    strategie = _FixesRaster(2, 2)
    plan = propose(SMALL_WALL, robot, tool, strategie=strategie)
    assert (plan.n_length, plan.n_height) == (2, 2)
    assert len(plan.sections) == 4
    assert len(strategie.aufgaben) == 1
    assert strategie.aufgaben[0].cap == MAX_DIVISIONS


def test_propose_default_ist_der_extrahierte_greedy_bitgleich(robot, tool):
    """Default (None) == explizit injizierter Greedy: die Extraktion aendert nichts."""
    a = propose(SMALL_WALL, robot, tool)
    b = propose(SMALL_WALL, robot, tool, strategie=GreedyAchsenVerfeinerung())
    assert a == b


# --- Baustein 2: Band-Raster-Kandidaten-Generator ------------------------------


def test_band_raster_kandidaten_deterministisch_in_stabiler_ordnung():
    """Gleicher Input ⇒ bit-gleiche Kandidatenfolge; Ordnung grob vor fein, stabil."""
    a = band_raster_kandidaten(SMALL_WALL, cap=3)
    b = band_raster_kandidaten(SMALL_WALL, cap=3)
    assert a == b
    assert len(a) == 9
    assert (a[0].n_length, a[0].n_height) == (1, 1)
    teile = [k.n_parts for k in a]
    assert teile == sorted(teile)
    # Bei gleicher Teilanzahl kommt weniger Hoehenteilung zuerst (dokumentierte Ordnung).
    assert [(k.n_length, k.n_height) for k in a[:4]] == [(1, 1), (2, 1), (1, 2), (3, 1)]


def test_band_raster_kandidat_teilt_die_schnittgeometrie_mit_propose():
    """Kein Duplikat: Schnitte kommen aus propose._build_cuts, Grenzen gerundet wie dort."""
    k = band_raster_kandidat(SMALL_WALL, 2, 3)
    assert k.cuts == _build_cuts(SMALL_WALL, 2, 3)
    assert k.key == "band-2x3"
    rows = k.row_bounds_mm()
    cols = k.col_bounds_mm()
    assert rows[0] == (0.0, pytest.approx(400.0 / 3, abs=1e-3))
    assert rows[-1][1] == 400.0
    assert cols == ((-300.0, 0.0), (0.0, 300.0))


def test_band_raster_kandidat_weist_ungueltige_teilungen_ab():
    with pytest.raises(ValueError, match="mindestens 1 Teilung"):
        band_raster_kandidat(SMALL_WALL, 0, 1)


# --- Baustein 3a: Masken-/Matrixbewertung (Han) + Raycast-Inselkarte (Z-Chunking)


def test_fugenflaeche_cv_und_inseln_auf_voller_front():
    """Volle Rechteckfront: Fugenflaeche analytisch, c_v = 0, eine Insel je Teil."""
    maske = wand_maske(SMALL_WALL, raster_mm=10.0)
    k11 = band_raster_kandidat(SMALL_WALL, 1, 1)
    k22 = band_raster_kandidat(SMALL_WALL, 2, 2)

    assert fugenflaeche_mm2(maske, k11) == 0.0
    # 1 vertikaler Schnitt (400 mm Hoehe) + 1 horizontaler (600 mm Laenge), Dicke 200.
    assert fugenflaeche_mm2(maske, k22) == pytest.approx((400.0 + 600.0) * 200.0)

    assert volumen_cv(maske, k11) == 0.0
    assert volumen_cv(maske, k22) == 0.0

    labels, inseln = raycast_inselkarte(maske, k22)
    assert inseln == (1, 1, 1, 1)
    assert int(labels.max()) == 4
    assert bool((labels > 0).all())


def test_oeffnung_senkt_fuge_spaltet_inseln_und_hebt_cv():
    """Injizierte Oeffnungs-Maske: Fuge durch die Oeffnung traegt nichts, Inseln zaehlen."""
    maske = wand_maske(SMALL_WALL, raster_mm=10.0)
    maske[:, 25:35] = False  # durchgehende Oeffnung x ∈ [-50, 50)

    k11 = band_raster_kandidat(SMALL_WALL, 1, 1)
    _labels, inseln = raycast_inselkarte(maske, k11)
    assert inseln == (2,)  # ein Teil, zwei Materialinseln (Fragment-Indiz, US 10)

    k21 = band_raster_kandidat(SMALL_WALL, 2, 1)  # Schnitt bei x=0 mitten in der Oeffnung
    assert fugenflaeche_mm2(maske, k21) == 0.0
    _labels2, inseln2 = raycast_inselkarte(maske, k21)
    assert inseln2 == (1, 1)

    asymmetrisch = wand_maske(SMALL_WALL, raster_mm=10.0)
    asymmetrisch[:, :20] = False  # linkes Drittel fehlt -> ungleiche Teil-Volumina
    assert volumen_cv(asymmetrisch, k21) > 0.0


# --- Baustein 3b: Scorer — Determinismus + Karte + Komparator-Anschluss --------


def test_scorer_ist_deterministisch_bitgleich(coarse_map, tool):
    """Zwei frische Scorer, gleicher Input ⇒ bit-gleiche Bewertungen (US 19/25)."""
    kandidaten = band_raster_kandidaten(SMALL_WALL, cap=2)
    s1 = BilligerScorer(coarse_map, SMALL_WALL, tool, stand_heights_mm=(0.0, 800.0))
    s2 = BilligerScorer(coarse_map, SMALL_WALL, tool, stand_heights_mm=(0.0, 800.0))
    b1 = [s1.bewerte(k) for k in kandidaten]
    b2 = [s2.bewerte(k) for k in kandidaten]
    assert b1 == b2  # frozen dataclasses: Gleichheit ist Bit-Gleichheit der Werte


def test_scorer_werte_speisen_den_komparator(coarse_map, tool):
    """Integrationstest (#212): Rangfolge-Entscheid an echten Kandidaten.

    K.-o. an der Karte: eine 3,2-m-Wand als EIN Teil hat keine Reihe, deren
    Unter- UND Oberkante ein Standplatz gemeinsam deckt (Min-Aggregation) —
    der Kandidat verliert gegen jeden erreichbaren, egal wie wenig Fugen er
    hat. Unter Erreichbaren mit gleichen Umsetzvorgaengen entscheidet die
    Fugenflaeche (Default-Rangfolge #212).
    """
    config = ObjectiveConfig()
    scorer = BilligerScorer(
        coarse_map, TALL_WALL, tool, stand_heights_mm=(0.0, 1200.0, 2400.0)
    )
    b11 = scorer.bewerte(band_raster_kandidat(TALL_WALL, 1, 1))
    b14 = scorer.bewerte(band_raster_kandidat(TALL_WALL, 1, 4))
    b24 = scorer.bewerte(band_raster_kandidat(TALL_WALL, 2, 4))

    # Karten-K.-o.: ungeteilte 3,2-m-Wand nicht von einem Standplatz deckbar.
    assert not b11.werte.erreichbar
    assert b11.reichweite_anteil < 1.0
    # In Hoehenbaender geteilt ist jede Reihe gedeckt (Podesthoehen-Satz).
    assert b14.werte.erreichbar
    assert all(b14.reihen_gedeckt)
    assert b14.standplaetze  # Standplaetze mit Reihen-Zuordnung + Marge geliefert
    gedeckte_reihen = [r for s in b14.standplaetze for r in s.reihen]
    assert sorted(gedeckte_reihen) == [0, 1, 2, 3]

    # K.-o. schlaegt jeden Score: der erreichbare Kandidat gewinnt.
    assert compare_candidates(b14.werte, b11.werte, config) == -1

    # Gleiche Hoehenreihen ⇒ identische Standplatz-Rechnung (reihenbasiert, laengsneutral).
    assert b24.werte.umsetzvorgaenge == b14.werte.umsetzvorgaenge
    assert b24.werte.kinematische_marge_mm == b14.werte.kinematische_marge_mm
    # ... aber ein zusaetzlicher vertikaler Schnitt = mehr Fugenflaeche ⇒ b14 gewinnt.
    assert b24.werte.fugenflaeche_mm2 > b14.werte.fugenflaeche_mm2
    assert compare_candidates(b14.werte, b24.werte, config) == -1

    # Sortierung ueber candidate_key: erreichbar vor unerreichbar, b14 ganz vorn.
    reihung = sorted([b24, b11, b14], key=lambda b: candidate_key(b.werte, config))
    assert [b.kandidat.key for b in reihung] == ["band-1x4", "band-2x4", "band-1x1"]


# --- Baustein 3c: Scorer im Modul-Modus (#237) — modul-lokale Reihen, feste Basis


def test_scorer_modul_modus_bewertet_reihen_modul_lokal(coarse_map, tool):
    """Der #237-Kernfall: in-situ unerreichbare Hoehenreihen sind am Druckort gedeckt.

    In-situ (Boden, ohne Podest) ist die oberste Reihe der 3,2-m-Wand nicht
    deckbar — genau daran verwarf der Vorfilter im Denkmal-Befund ALLE Kandidaten
    („reichweite", 256/256), obwohl die exakte Modul-Bewertung 100 % Erreichbarkeit
    sah. Im Modul-Modus (feste Druckort-Platzierung) ist jede Reihe ein Modul ab
    ``z = 0`` — der Scorer muss sie modul-lokal bewerten.
    """
    from fgc.placement.evaluate import PlacementOption

    fix = PlacementOption(
        "workstation-druckort", lateral_mm=0.0, standoff_mm=400.0, stand_height_mm=0.0
    )
    in_situ = BilligerScorer(coarse_map, TALL_WALL, tool, stand_heights_mm=(0.0,))
    modul = BilligerScorer(coarse_map, TALL_WALL, tool, fixe_platzierung=fix)
    k14 = band_raster_kandidat(TALL_WALL, 1, 4)

    # In-situ vom Boden: K.-o. (mindestens eine Reihe ungedeckt) — der alte Befund.
    assert not in_situ.bewerte(k14).werte.erreichbar

    # Modul-lokal: jede Reihe ist ein 800-mm-Modul ab z = 0 an der festen Basis.
    b = modul.bewerte(k14)
    assert b.werte.erreichbar
    assert all(b.reihen_gedeckt)
    assert b.werte.umsetzvorgaenge == 1.0  # feste Basis — kein Roboter-Umsetzen
    assert b.werte.kinematische_marge_mm == 0.0  # kein Verschiebe-Spielraum-Proxy
    assert len(b.standplaetze) == 1
    assert b.standplaetze[0].reihen == (0, 1, 2, 3)
    assert b.standplaetze[0].stand_height_mm == 0.0

    # Ein ungeteiltes 3,2-m-Modul bleibt auch am Druckort ehrlich unerreichbar.
    assert not modul.bewerte(band_raster_kandidat(TALL_WALL, 1, 1)).werte.erreichbar


def test_scorer_modul_modus_ist_deterministisch(coarse_map, tool):
    """Modul-Modus wie der Abschnitts-Modus bit-gleich (US 19/25)."""
    from fgc.placement.evaluate import PlacementOption

    fix = PlacementOption(
        "workstation-druckort", lateral_mm=0.0, standoff_mm=400.0, stand_height_mm=0.0
    )
    kandidaten = band_raster_kandidaten(TALL_WALL, cap=3)
    s1 = BilligerScorer(coarse_map, TALL_WALL, tool, fixe_platzierung=fix)
    s2 = BilligerScorer(coarse_map, TALL_WALL, tool, fixe_platzierung=fix)
    assert [s1.bewerte(k) for k in kandidaten] == [s2.bewerte(k) for k in kandidaten]


class _MiniBeam(ZerlegungsStrategie):
    """Kandidaten-basierte Strategie (Beam-Minimalform): belegt den #217-Anschluss.

    Nutzt genau den Kontext der RasterAufgabe, den #217 verdrahtet: Generator-
    Kandidaten + billiger Scorer + Zielfunktion — Wahl per candidate_key (#212).
    """

    name = "mini-beam"

    def waehle_raster(self, aufgabe: RasterAufgabe) -> RasterWahl:
        assert aufgabe.kandidaten is not None
        assert aufgabe.bewerte is not None
        assert aufgabe.objective is not None
        beste = min(
            (aufgabe.bewerte(k) for k in aufgabe.kandidaten),
            key=lambda b: candidate_key(b.werte, aufgabe.objective),
        )
        return RasterWahl(
            n_length=beste.kandidat.n_length,
            n_height=beste.kandidat.n_height,
            bewertung=beste,
        )


def test_interface_traegt_kandidaten_basierte_strategien(coarse_map, tool):
    """Dasselbe Interface traegt Beam (#217): Generator + Scorer + Objective in der Aufgabe."""
    scorer = BilligerScorer(
        coarse_map, TALL_WALL, tool, stand_heights_mm=(0.0, 1200.0, 2400.0)
    )
    aufgabe = RasterAufgabe(
        frac_at=lambda _nv, _nh: 0.0,
        start=(1, 1),
        cap=4,
        kandidaten=band_raster_kandidaten(TALL_WALL, cap=4),
        bewerte=scorer.bewerte,
        objective=ObjectiveConfig(),
        call_budget=20,
    )
    strategie = _MiniBeam()
    assert isinstance(strategie, ZerlegungsStrategie)
    wahl = strategie.waehle_raster(aufgabe)
    assert wahl.bewertung is not None
    assert wahl.bewertung.werte.erreichbar  # der Sieger ueberlebt das Karten-K.-o.
    assert isinstance(wahl.bewertung.kandidat, BandRasterKandidat)
    assert strategie.provenance()["strategy"] == "mini-beam"
