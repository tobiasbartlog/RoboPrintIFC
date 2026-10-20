"""Beam-Suche end-to-end als zweite Zerlegungs-Strategie (Issue #217, PRD #183 Stufe 3).

Die **Beam-Suche** haengt an **derselben** Naht wie der Achsen-Greedy (#203) und
die kollisionsgetriebene Verfeinerung (#165): sie implementiert
:meth:`fgc.decompose.strategie.ZerlegungsStrategie.waehle_raster` — kein
Sonderpfad (US 19, byte-vergleichbarer Paper-Vergleich). Der Ablauf folgt dem
Literatur-Muster „billige Bewertung vorn, teures Urteil hinten" (Wu 2019, Han
2025, `docs/recherche/2026-07-10-adaption-chunking-literatur.md`):

1. **Alle** Band-Raster-Kandidaten (``aufgabe.kandidaten``) werden vom billigen
   Scorer (``aufgabe.bewerte``) bewertet — gratis, ohne Pruef-Tuer.
2. Der :func:`~fgc.decompose.objective.candidate_key`-Komparator (#212) ordnet
   sie; unerreichbare (hartes K.-o.) und fragmentierte Kandidaten fallen als
   **Verworfen-Gruende** (US 10) heraus. Der Beam behaelt die besten **k**.
3. **Nur die Beam-Ueberlebenden** durchlaufen die **Pruef-Tuer**
   (``aufgabe.pruef_tuer``, exaktes Urteil je Hoehenreihe von der besten
   automatischen Option aus) — jeder Aufruf zaehlt gegen das **Aufruf-Kontingent**
   (``aufgabe.call_budget``, #178/#215, kein Zeitbudget). Der erste vollstaendig
   kollisionsfreie Kandidat gewinnt (Ehrlichkeitsregel ADR-007: „geprueft frei"
   entsteht **nur** aus der Pruef-Tuer).

Die **Beam-Breite k** wird aus dem Kontingent abgeleitet
(:func:`beam_breite`) — kein eigener Parameter (Grill 2026-07-14, Entscheidung 4).

**Surrogat-Vorsortierer (Issue #219, optional).** Ist ein ``surrogat`` gesetzt
(duck-typed: ``vorsortiere(bewertungen) -> Liste`` + ``stamp() -> dict``,
produktiv :class:`fgc.decompose.surrogat.SurrogatModell`), reordnet es **nur die
Pruef-Reihenfolge** der Beam-Ueberlebenden — vermutlich frei zuerst. Es
**verwirft nie** und **entscheidet nie**: die Sieger-Auswahl bleibt der
**zielfunktions-beste kollisionsfreie Kandidat** (:meth:`_pruefe` waehlt ihn
unabhaengig von der Pruef-Reihenfolge). Bei gleichem Aufruf-Kontingent liefert
der Beam daher **denselben** besten Kandidaten und dasselbe Urteil — nur
Reihenfolge/Zeit aendern sich (Invarianz-Orakel US 25). Die einzige Spur ist der
**Modellstand** im Provenienz-Feld ``surrogate_model`` (ADR-004), falls aktiv;
ohne Surrogat bleibt alles byte-gleich (``None``, US 12).

**Relaxationsleiter (US 22, Grill 2026-07-14, Entscheidung 5)** bei leerem
Ergebnis, Stufe fuer Stufe und **jede gezuendete Stufe namentlich** in der
Provenienz:

- :data:`RELAX_MEHR_TEILE` — die Kandidaten **jenseits** des Beams (mehr Teile)
  werden noch geprueft;
- :data:`RELAX_MEHR_STANDPLAETZE` — mit einem erweiterten Podesthoehen-Satz
  (``rescore``) neu bewertet: mehr Kandidaten ueberstehen das Erreichbarkeits-K.-o.;
- :data:`RELAX_TIEFENTEILUNG` — zuletzt ein **Tiefenteilungs-Vorschlag**
  (#166-Muster, Anwendung **manuell**, nie automatisch).

**Nie relaxiert** (Grill 2026-07-14): der Sicherheitsabstand, das
Erreichbarkeits-K.-o. (ein unerreichbarer Kandidat wird nie „geprueft frei",
nur — best effort — als ehrlich rot bewerteter Vorschlag zurueckgegeben), die
Ehrlichkeitsregel und die Kipp-/Tiefenteilungs-Automatik (#141/#165): das
Options-Menue traegt kein Kipp/Lead, und die Beam-Suche teilt nie selbst die
Tiefe (Band-Raster sind 2D).

**Determinismus (US 25):** gleiche Eingaben + gleiches Kontingent ⇒ gleiche
Aufruffolge ⇒ bit-gleicher Schnitt. Aufrufe zaehlen, keine Zeit; stabile
Tie-Breaks (``candidate_key`` + Kandidaten-Schluessel). Die optionale
``rechenzeit_s`` im Metriken-Katalog ist rein diagnostisch und geht **nicht** in
die Entscheidung ein.

Kann als **Hintergrundlauf mit Fortschritt + Abbrechen** laufen (Muster #145/#175):
``on_progress(calls_used, call_budget)`` und ``should_cancel()`` sind genau die
Callback-Formen, die ``fgc.pipeline.checkjobs`` in die Pruef-Tuer faedelt.

Einheiten strikt nach ADR-006: Millimeter, Radiant.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fgc.decompose.objective import candidate_key
from fgc.decompose.strategie import (
    GreedyAchsenVerfeinerung,
    RasterAufgabe,
    RasterWahl,
    ZellenOption,
    ZerlegungsStrategie,
    _mit_provenienz,
    option_menu,
)

if TYPE_CHECKING:
    from fgc.decompose.kandidaten import BandRasterKandidat
    from fgc.decompose.objective import ObjectiveConfig
    from fgc.decompose.scorer import KandidatBewertung

__all__ = [
    "GRUND_FRAGMENT",
    "GRUND_KOLLISION",
    "GRUND_REICHWEITE",
    "RELAXATIONSLEITER",
    "RELAX_MEHR_STANDPLAETZE",
    "RELAX_MEHR_TEILE",
    "RELAX_TIEFENTEILUNG",
    "BeamSuche",
    "ScorerFactory",
    "beam_breite",
]

#: Fallback-Aufruf-Kontingent, falls die Aufgabe keins traegt — spiegelt
#: ``propose.DEFAULT_CALL_BUDGET`` (#215), bleibt aber lokal (kein Zirkelimport:
#: ``propose`` importiert ``beam``, nicht umgekehrt). ``propose`` reicht den echten
#: Wert stets herein.
_FALLBACK_CALL_BUDGET = 20

#: Die Verworfen-Gruende der Suche (US 10 — „Reichweite? Fragment? Kollision?").
GRUND_REICHWEITE = "reichweite"
GRUND_FRAGMENT = "fragment"
GRUND_KOLLISION = "kollision"

#: Die Relaxationsleiter in ihrer festen Reihenfolge (US 22, Grill 2026-07-14):
#: mehr Teile → mehr Standplaetze → Tiefenteilungs-Vorschlag.
RELAX_MEHR_TEILE = "mehr_teile"
RELAX_MEHR_STANDPLAETZE = "mehr_standplaetze"
RELAX_TIEFENTEILUNG = "tiefenteilung_vorschlag"
RELAXATIONSLEITER: tuple[str, ...] = (
    RELAX_MEHR_TEILE,
    RELAX_MEHR_STANDPLAETZE,
    RELAX_TIEFENTEILUNG,
)

#: Eine Fabrik, die zu einem erweiterten Aufstellhoehen-Satz einen frischen
#: ``bewerte``-Aufruf liefert (Stufe :data:`RELAX_MEHR_STANDPLAETZE`) — produktiv
#: eine Closure ueber einen neuen :class:`~fgc.decompose.scorer.BilligerScorer`,
#: in Tests ein deterministisches Fake. ``None`` = Stufe uebersprungen (fail-soft).
ScorerFactory = Callable[[Sequence[float]], "Callable[[BandRasterKandidat], KandidatBewertung]"]


def beam_breite(call_budget: int | None) -> int:
    """Die **Beam-Breite k**, abgeleitet aus dem Aufruf-Kontingent (kein eigener Parameter).

    Der Beam behaelt so viele Kandidaten, wie das Kontingent im **guenstigsten
    Fall** (ein Pruef-Tuer-Aufruf je Kandidat) ueberhaupt exakt pruefen koennte —
    mehr Kandidaten vorzuhalten waere Verschwendung, weniger wuerde erreichbare
    Schnitte unnoetig verwerfen. Damit steuert **ein** hartes Kontingent (#215)
    zugleich die Vorauswahl (billig) und die exakte Pruefung (teuer);
    deterministisch und byte-vergleichbar (US 25). Mindestens 1.
    """
    budget = _FALLBACK_CALL_BUDGET if call_budget is None else int(call_budget)
    return max(1, budget)


def _fragmentiert(bewertung: KandidatBewertung) -> bool:
    """Traegt mindestens ein Teil mehr als eine Materialinsel (Fragment-Indiz, US 10)?"""
    return any(int(n) > 1 for n in bewertung.inseln_je_teil)


@dataclass
class _Sieger:
    """Der (vorlaeufige) Sieger der Suche: Kandidat-Bewertung + je Reihe gewaehlte Option."""

    bewertung: KandidatBewertung
    optionen: tuple[ZellenOption, ...]
    geprueft: bool


#: Sentinel: die Pruef-Tuer meldete ``None`` (keine Kollisions-Geometrie) ⇒ Greedy-Fallback.
_UNZUSTAENDIG = object()


@dataclass
class _Lauf:
    """Der veraenderliche Zustand **eines** Beam-Laufs (Aufrufe, Verworfen, Leiter)."""

    budget: int
    calls: int = 0
    budget_exhausted: bool = False
    cancelled: bool = False
    verworfen: list[dict[str, Any]] = field(default_factory=list)
    relaxation: list[str] = field(default_factory=list)
    _seen: set[tuple[str, str]] = field(default_factory=set)

    @property
    def stop(self) -> bool:
        """Ist die Suche zu Ende (Kontingent erschoepft oder abgebrochen)?"""
        return self.cancelled or self.calls >= self.budget

    def verwirf(self, bewertung: KandidatBewertung, grund: str, h_idx: int | None = None) -> None:
        """Haelt einen Verworfen-Grund fest (dedupliziert je Kandidat+Grund, US 10)."""
        kandidat = bewertung.kandidat
        key = (kandidat.key, grund)
        if key in self._seen:
            return
        self._seen.add(key)
        eintrag: dict[str, Any] = {
            "kandidat": kandidat.key,
            "n_length": kandidat.n_length,
            "n_height": kandidat.n_height,
            "teilanzahl": kandidat.n_parts,
            "grund": grund,
        }
        if h_idx is not None:
            eintrag["h_idx"] = h_idx
        self.verworfen.append(eintrag)


class BeamSuche(ZerlegungsStrategie):
    """Die Beam-Suche end-to-end an der #216-Naht (Issue #217, PRD #183 Stufe 3).

    ``stand_heights_ladder`` sind die **erweiterten** Aufstellhoehen-Saetze der
    Relaxationsstufe „mehr Standplaetze" (aufsteigend gedacht); ``rescore`` die
    Fabrik, die zu einem solchen Satz einen frischen ``bewerte``-Aufruf liefert
    (produktiv eine neue :class:`~fgc.decompose.scorer.BilligerScorer`-Closure).
    Ohne beide bleibt die Stufe uebersprungen (fail-soft, US 12). ``on_progress``/
    ``should_cancel`` machen die Suche hintergrundlauffaehig (Muster #145/#175):
    ``on_progress(calls_used, call_budget)`` nach jedem Pruef-Tuer-Aufruf,
    ``should_cancel()`` **vor** jedem (kein halber Aufruf; best effort, der Plan
    wird ehrlich bewertet).
    """

    name = "beam-suche"

    def __init__(
        self,
        *,
        stand_heights_ladder: Sequence[Sequence[float]] = (),
        rescore: ScorerFactory | None = None,
        on_progress: Callable[[int, int], Any] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        surrogat: Any | None = None,
    ) -> None:
        self._ladder = tuple(tuple(float(h) for h in satz) for satz in stand_heights_ladder)
        self._rescore = rescore
        self._on_progress = on_progress
        self._should_cancel = should_cancel
        #: Optionaler Surrogat-Vorsortierer (#219, duck-typed: ``vorsortiere``/``stamp``).
        #: ``None`` ⇒ reine Zielfunktions-Ordnung (byte-gleich, US 12).
        self._surrogat = surrogat

    # -- Die eine Tuer (#216-Naht) ---------------------------------------------

    def waehle_raster(self, aufgabe: RasterAufgabe) -> RasterWahl:
        # Fail-soft: ohne Kandidaten/Scorer/Zielfunktion kein Beam ⇒ Achsen-Greedy
        # (byte-gleich, nie ein geratenes „frei", ADR-013) — wie #165 ohne Orakel.
        if aufgabe.kandidaten is None or aufgabe.bewerte is None or aufgabe.objective is None:
            wahl = GreedyAchsenVerfeinerung().waehle_raster(aufgabe)
            return _mit_provenienz(wahl, {"strategy": self.name, "fallback": "kein-scorer"})

        t0 = time.perf_counter()
        budget = (
            _FALLBACK_CALL_BUDGET if aufgabe.call_budget is None else int(aufgabe.call_budget)
        )
        k = beam_breite(budget)
        menu = aufgabe.menu if aufgabe.menu is not None else option_menu()
        objective = aufgabe.objective
        pruef_tuer = aufgabe.pruef_tuer
        lauf = _Lauf(budget=budget)

        # 1./2.: alle Kandidaten billig bewerten + ordnen; K.-o./Fragment fallen raus.
        base_ranked = self._ordne(list(aufgabe.kandidaten), aufgabe.bewerte, objective)
        verifizierbar = self._filtere(base_ranked, lauf)

        # 3.: nur die besten k (Beam) durch die Pruef-Tuer — das Surrogat (#219) reordnet
        # nur die Pruef-Reihenfolge (``check_order``), nie die Sieger-Auswahl.
        beam = verifizierbar[:k]
        sieger = self._pruefe(beam, pruef_tuer, menu, lauf, check_order=self._check_order(beam))
        if sieger is _UNZUSTAENDIG:
            wahl = GreedyAchsenVerfeinerung().waehle_raster(aufgabe)
            return _mit_provenienz(
                wahl,
                {"strategy": self.name, "fallback": "unzustaendig", "calls_used": lauf.calls},
            )

        # Relaxationsleiter (US 22) — Stufe fuer Stufe, jede gezuendete namentlich in
        # der Provenienz; ein Abbruch (should_cancel) zuendet keine weitere Stufe.
        tiefenteilung: dict[str, Any] | None = None
        if sieger is None and not lauf.stop:
            # Stufe 1: **mehr Teile** — feinere Band-Raster (mehr Teilungen bis zum harten
            # Deckel) zulassen und pruefen. Die Suche teilt damit nie selbst die Tiefe
            # (#142) — nur mehr ebene Schnitte in Laenge/Hoehe (#166 bleibt Vorschlag).
            lauf.relaxation.append(RELAX_MEHR_TEILE)
            feiner = self._mehr_teile_kandidaten(aufgabe)
            if feiner is not None:
                ranked_f = self._ordne(feiner, aufgabe.bewerte, objective)
                verifizierbar_f = self._filtere(ranked_f, lauf)
                sieger = self._pruefe(
                    verifizierbar_f, pruef_tuer, menu, lauf,
                    check_order=self._check_order(verifizierbar_f),
                )
                if sieger is _UNZUSTAENDIG:
                    sieger = None

        if sieger is None and self._rescore is not None and self._ladder and not lauf.stop:
            # Stufe 2: **mehr Standplaetze** — mit erweitertem Podesthoehen-Satz neu
            # bewerten (mehr Kandidaten ueberstehen das Erreichbarkeits-K.-o.).
            lauf.relaxation.append(RELAX_MEHR_STANDPLAETZE)
            for heights in self._ladder:
                if lauf.stop:
                    break
                bewerte2 = self._rescore(heights)
                ranked2 = self._ordne(list(aufgabe.kandidaten), bewerte2, objective)
                verifizierbar2 = self._filtere(ranked2, lauf)
                kandidat = self._pruefe(
                    verifizierbar2, pruef_tuer, menu, lauf,
                    check_order=self._check_order(verifizierbar2),
                )
                if kandidat is _UNZUSTAENDIG:
                    kandidat = None
                if isinstance(kandidat, _Sieger):
                    sieger = kandidat
                    break

        leer = False
        if sieger is None:
            # Best effort: der billig best-bewertete Kandidat (ehrlich ungeprueft,
            # evaluate faerbt ihn). Bei echtem leeren Ergebnis (nicht Abbruch) zuendet
            # zuletzt der **Tiefenteilungs-Vorschlag** (nie automatisch, #166/#142).
            sieger = self._best_effort(base_ranked)
            leer = True
            if not lauf.cancelled:
                lauf.relaxation.append(RELAX_TIEFENTEILUNG)
                tiefenteilung = _tiefenteilung_vorschlag(aufgabe)

        rechenzeit_s = time.perf_counter() - t0
        return self._ergebnis(sieger, lauf, k, rechenzeit_s, tiefenteilung, leer)

    def _mehr_teile_kandidaten(
        self, aufgabe: RasterAufgabe
    ) -> list[BandRasterKandidat] | None:
        """Die **feineren** Band-Raster jenseits des bisherigen Deckels (Stufe „mehr Teile").

        Regeneriert die Kandidatenmenge bis zum **harten** Deckel
        ``propose.MAX_DIVISIONS`` und gibt nur die **neu** hinzugekommenen (mehr
        Teilungen) zurueck — die bereits geprueften werden nicht erneut geprueft
        (Kontingent-schonend, deterministisch). ``None``, wenn der Deckel schon
        erreicht war (die Stufe ist dann gezuendet, kann aber nichts hinzufuegen).
        """
        from fgc.decompose.kandidaten import band_raster_kandidaten
        from fgc.decompose.propose import MAX_DIVISIONS

        if not aufgabe.kandidaten or aufgabe.cap >= MAX_DIVISIONS:
            return None
        bekannt = {(k.n_length, k.n_height) for k in aufgabe.kandidaten}
        wall = aufgabe.kandidaten[0].wall
        voll = band_raster_kandidaten(wall, cap=MAX_DIVISIONS)
        neu = [k for k in voll if (k.n_length, k.n_height) not in bekannt]
        return neu or None

    # -- Bausteine -------------------------------------------------------------

    def _ordne(
        self,
        kandidaten: list[BandRasterKandidat],
        bewerte: Callable[[BandRasterKandidat], KandidatBewertung],
        objective: ObjectiveConfig,
    ) -> list[KandidatBewertung]:
        """Alle Kandidaten billig bewerten und deterministisch ordnen (bester zuerst)."""
        bewertungen = [bewerte(kandidat) for kandidat in kandidaten]
        # Stabiler Tie-Break ueber den Kandidaten-Schluessel: gleiche Kriterienwerte
        # behalten die grob-vor-fein-Ordnung des Generators (bit-vergleichbar, US 25).
        return sorted(
            bewertungen, key=lambda b: (candidate_key(b.werte, objective), b.kandidat.key)
        )

    def _filtere(
        self, ranked: list[KandidatBewertung], lauf: _Lauf
    ) -> list[KandidatBewertung]:
        """Die billigen Verworfen-Gruende (Reichweite/Fragment) ausscheiden (US 10)."""
        verifizierbar: list[KandidatBewertung] = []
        for bewertung in ranked:
            if not bewertung.werte.erreichbar:
                lauf.verwirf(bewertung, GRUND_REICHWEITE)  # hartes K.-o. (#212)
            elif _fragmentiert(bewertung):
                lauf.verwirf(bewertung, GRUND_FRAGMENT)
            else:
                verifizierbar.append(bewertung)
        return verifizierbar

    def _check_order(
        self, kandidaten: list[KandidatBewertung]
    ) -> list[KandidatBewertung] | None:
        """Die Pruef-Reihenfolge des Surrogat-Vorsortierers (#219) — ``None`` = Zielfunktion.

        Ohne Surrogat (``None``) prueft der Beam in **Zielfunktions-Ordnung**
        (byte-gleich, US 12). Mit Surrogat reordnet ``vorsortiere`` die Liste
        (vermutlich frei zuerst) — **nur** die Reihenfolge, nie die Menge (der
        Vorsortierer verwirft nie). Die Sieger-Auswahl in :meth:`_pruefe` bleibt
        zielfunktions-basiert und damit invariant (US 25).
        """
        if self._surrogat is None or not kandidaten:
            return None
        return list(self._surrogat.vorsortiere(kandidaten))

    def _pruefe(
        self,
        kandidaten: list[KandidatBewertung],
        pruef_tuer: Any,
        menu: tuple[ZellenOption, ...],
        lauf: _Lauf,
        *,
        check_order: list[KandidatBewertung] | None = None,
    ) -> _Sieger | None | object:
        """Der **zielfunktions-beste** kollisionsfreie Kandidat — invariant zur Pruef-Reihenfolge.

        ``kandidaten`` ist die zielfunktions-geordnete Liste (beste zuerst) und legt
        die **Sieger-Prioritaet** fest; ``check_order`` (Default = ``kandidaten``) ist
        die tatsaechliche Pruef-**Reihenfolge** — der Surrogat-Vorsortierer (#219)
        reordnet nur diese. Der Sieger ist der Kandidat mit **kleinstem
        Zielfunktions-Rang**, den die Pruef-Tuer frei gesehen hat (nicht der zuerst
        gepruefte): sobald alle zielfunktions-besseren Kandidaten geprueft (und damit
        kollidiert) sind, steht er fest. In **Zielfunktions-Ordnung** ist das
        byte-gleich zum frueheren „erster Kollisionsfreie gewinnt" (der erste freie
        ist dann per Definition der zielfunktions-beste) — die Umordnung aendert nur
        Reihenfolge/Zeit, nie den Sieger (Invarianz-Orakel US 25).

        Ohne Pruef-Tuer (``None``) gibt es kein exaktes Urteil: der beste billig
        erreichbare Kandidat gewinnt **ungeprueft** (Ehrlichkeitsregel — kein
        „geprueft frei"). Meldet die Pruef-Tuer ``None`` (unzustaendig), signalisiert
        :data:`_UNZUSTAENDIG` den Greedy-Fallback.
        """
        if not kandidaten:
            return None
        if pruef_tuer is None:
            bewertung = kandidaten[0]
            optionen = tuple(ZellenOption() for _ in range(bewertung.kandidat.n_height))
            return _Sieger(bewertung=bewertung, optionen=optionen, geprueft=False)

        order = kandidaten if check_order is None else check_order
        rang = {b.kandidat.key: i for i, b in enumerate(kandidaten)}  # Zielfunktions-Prioritaet
        frei: dict[int, _Sieger] = {}  # Rang → Sieger (nur kollisionsfreie)
        geprueft: set[int] = set()
        for bewertung in order:
            if lauf.stop:
                break
            r = rang[bewertung.kandidat.key]
            frei_flag, optionen, info = self._pruefe_kandidat(
                bewertung.kandidat, pruef_tuer, menu, lauf
            )
            if frei_flag is None:
                return _UNZUSTAENDIG
            geprueft.add(r)
            if frei_flag:
                frei[r] = _Sieger(bewertung=bewertung, optionen=optionen, geprueft=True)
                # Fruehstopp: der zielfunktions-beste freie steht fest, sobald **alle**
                # zielfunktions-besseren Kandidaten geprueft (und damit kollidiert) sind.
                best = min(frei)
                if all(i in geprueft for i in range(best)):
                    return frei[best]
            # Nur echte Kollisionen sind Verworfen-Gruende — nicht Kontingent/Abbruch.
            elif info.get("grund") == GRUND_KOLLISION:
                lauf.verwirf(bewertung, GRUND_KOLLISION, info.get("h_idx"))
        # Kontingent/Abbruch/erschoepfte Reihenfolge: der beste bislang frei gesehene
        # Kandidat (best effort, ehrlich geprueft frei), sonst leer.
        if frei:
            return frei[min(frei)]
        return None

    def _pruefe_kandidat(
        self,
        kandidat: BandRasterKandidat,
        pruef_tuer: Any,
        menu: tuple[ZellenOption, ...],
        lauf: _Lauf,
    ) -> tuple[bool | None, tuple[ZellenOption, ...], dict[str, Any]]:
        """Ein Kandidat je Hoehenreihe von der besten automatischen Option aus (Menue #141).

        ``(frei, optionen, info)``: ``frei=True`` alle Reihen kollisionsfrei (mit je
        gewaehlter Option); ``False`` eine Reihe unfrei (``info['grund']`` =
        ``kollision`` / ``budget`` / ``cancelled``); ``None`` unzustaendig. Jeder
        Aufruf zaehlt gegen das Kontingent; **kein** Nachteilen der Zellgroesse
        (Band-Raster fest) — die Beam-Suche teilt nie selbst (das ist der Greedy).
        """
        chosen: list[ZellenOption] = []
        for h_idx in range(kandidat.n_height):
            frei_reihe = False
            for opt in menu:
                if lauf.calls >= lauf.budget:
                    lauf.budget_exhausted = True
                    return False, tuple(chosen), {"grund": "budget", "h_idx": h_idx}
                if self._should_cancel is not None and self._should_cancel():
                    lauf.cancelled = True
                    return False, tuple(chosen), {"grund": "cancelled", "h_idx": h_idx}
                befund = pruef_tuer(kandidat, h_idx, opt)
                lauf.calls += 1
                if self._on_progress is not None:
                    self._on_progress(lauf.calls, lauf.budget)
                if befund is None:
                    return None, tuple(chosen), {"grund": "unzustaendig", "h_idx": h_idx}
                if not befund.collides:
                    chosen.append(opt)
                    frei_reihe = True
                    break
            if not frei_reihe:
                return False, tuple(chosen), {"grund": GRUND_KOLLISION, "h_idx": h_idx}
        return True, tuple(chosen), {}

    def _best_effort(self, base_ranked: list[KandidatBewertung]) -> _Sieger:
        """Der ehrliche Notnagel bei leerem Ergebnis: der billig **best-bewertete** Kandidat.

        Kein „geprueft frei" (``geprueft=False``): ``evaluate`` faerbt den Vorschlag
        ehrlich (Befund, kein Gate) — das Erreichbarkeits-K.-o. wird nie relaxiert,
        nur best effort ein Kompromiss vorgeschlagen (US 22).
        """
        bewertung = base_ranked[0]
        optionen = tuple(ZellenOption() for _ in range(bewertung.kandidat.n_height))
        return _Sieger(bewertung=bewertung, optionen=optionen, geprueft=False)

    def _ergebnis(
        self,
        sieger: _Sieger,
        lauf: _Lauf,
        k: int,
        rechenzeit_s: float,
        tiefenteilung: dict[str, Any] | None,
        leer: bool,
    ) -> RasterWahl:
        """Baut die :class:`RasterWahl` samt Provenienz + Metriken-Katalog (US 20)."""
        kandidat = sieger.bewertung.kandidat
        provenienz: dict[str, Any] = {
            "strategy": self.name,
            "beam_width": k,
            "call_budget": lauf.budget,
            "calls_used": lauf.calls,
            "budget_exhausted": lauf.budget_exhausted,
            "cancelled": lauf.cancelled,
            "geprueft": sieger.geprueft,
            "leer": leer,
            "relaxation": list(lauf.relaxation),
            "verworfen": lauf.verworfen,
            "metriken": _metriken(sieger, rechenzeit_s),
            # Der Modellstand des Surrogat-Vorsortierers (#219), falls aktiv — die
            # einzige Spur des Surrogats (ADR-004). Ohne Surrogat ``None`` (byte-gleich).
            "surrogate_model": self._surrogat.stamp() if self._surrogat is not None else None,
        }
        if tiefenteilung is not None:
            provenienz["tiefenteilung_vorschlag"] = tiefenteilung
        return RasterWahl(
            n_length=kandidat.n_length,
            n_height=kandidat.n_height,
            bewertung=sieger.bewertung,
            zellen_optionen=sieger.optionen,
            provenienz=provenienz,
        )


def _metriken(sieger: _Sieger, rechenzeit_s: float) -> dict[str, Any]:
    """Der Metriken-Katalog **je Lauf** (US 20): Teilanzahl, c_v, Fugenflaeche, …

    Alles aus dem Sieger-Kandidaten + Lauf: ``geprueft_frei_anteil`` ist 1.0, wenn
    die Pruef-Tuer **jede** Reihe frei gesehen hat (Sieger-Definition), sonst
    ``None`` (best-effort-Vorschlag, ungeprueft — nie ein geratenes „frei").
    ``rechenzeit_s`` ist rein diagnostisch (nicht Teil der Entscheidung, US 25).
    """
    bewertung = sieger.bewertung
    werte = bewertung.werte
    return {
        "teilanzahl": bewertung.kandidat.n_parts,
        "volumen_cv": werte.volumen_cv,
        "fugenflaeche_mm2": werte.fugenflaeche_mm2,
        "erreichbarer_anteil": bewertung.reichweite_anteil,
        "geprueft_frei_anteil": 1.0 if sieger.geprueft else None,
        "standplaetze": int(werte.umsetzvorgaenge),
        "rechenzeit_s": rechenzeit_s,
    }


def _tiefenteilung_vorschlag(aufgabe: RasterAufgabe) -> dict[str, Any]:
    """Der **Tiefenteilungs-Vorschlag** der letzten Relaxationsstufe (nie automatisch).

    Ein reiner Hinweis (#166-Muster, ADR-013): die Suche schlaegt vor, die Wand in
    der **Tiefe** zu teilen (beidseitiger Druck) — angewandt wird das **manuell**,
    nie von der Suche selbst (die Band-Raster bleiben 2D, #142). Kein Gate.
    """
    return {
        "hinweis": (
            "Kein erreichbarer, kollisionsfreier Band-Schnitt gefunden — eine "
            "Teilung in der Tiefe (beidseitiger Druck) koennte helfen."
        ),
        "anwendung": "manuell",
        "muster": "#166",
    }
