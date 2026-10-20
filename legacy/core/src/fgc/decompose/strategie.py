"""Zerlegungs-Strategie-Interface (Issue #216, PRD #183 Stufe 3, US 19).

Die **eine** Naht, an der austauschbare Zerlegungs-Strategien haengen: extrahiert
aus dem Verfeinerungs-Loop ``propose._refine`` (#203) — **Greedy** (die
kollisionsgetriebene Verfeinerung #165 wie der hier extrahierte Achsen-Greedy)
und die **Beam-Suche** (#217) implementieren dieselbe schmale Tuer, damit der
Paper-Vergleich (US 19/27) fair und byte-vergleichbar laeuft: gleiche
:class:`RasterAufgabe` rein, gleiche :class:`RasterWahl` raus.

**Provenienz (ADR-004):** jede Strategie benennt sich selbst
(:meth:`ZerlegungsStrategie.provenance` — Strategiename + Surrogat-Modellstand,
falls aktiv, #219). Der Zerlegungslauf (#217) stempelt diesen Block in die
Lauf-Provenienz; heute (Default :class:`GreedyAchsenVerfeinerung`) ist das
Verhalten bit-identisch zum bisherigen ``_refine``.

Die :class:`RasterAufgabe` traegt beide Sichtweisen der Suche:

- ``frac_at``/``start``/``cap`` — das billige Reichweiten-Orakel je
  Kandidat-Raster, das der Achsen-Greedy (heute) und die #165-Verfeinerung
  (Pruef-Tuer-getrieben) konsumieren;
- ``kandidaten``/``bewerte``/``objective``/``call_budget`` — die
  Kandidatenmenge (Band-Raster-Generator, ``fgc.decompose.kandidaten``), der
  billige Scorer (``fgc.decompose.scorer``) und die Zielfunktion (#212) fuer
  kandidaten-basierte Strategien (Beam #217); ``None``-Defaults halten den
  heutigen ``propose``-Pfad byte-gleich (fail-soft — ohne Karte gibt es keinen
  Scorer, Muster #214). ``call_budget`` ist das Aufruf-Kontingent exakter
  Pruef-Tuer-Aufrufe (``propose.DEFAULT_CALL_BUDGET``, #215) — verdrahtet #217,
  hier nur durchgereicht (deterministisch, byte-vergleichbar, US 25).

Kein Beam-Loop, keine Pruef-Tuer in diesem Modul — nur das Interface und der
extrahierte Greedy. Deterministisch (ADR-004-Geist).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from fgc.decompose.evaluate import GREEN_THRESHOLD

if TYPE_CHECKING:
    from fgc.decompose.kandidaten import BandRasterKandidat
    from fgc.decompose.objective import ObjectiveConfig
    from fgc.decompose.scorer import KandidatBewertung

__all__ = [
    "IK_AXES",
    "IK_VALUES",
    "LATERAL_DELTAS_MM",
    "STANDOFF_DELTAS_MM",
    "STAND_HEIGHT_DELTAS_MM",
    "GreedyAchsenVerfeinerung",
    "KollisionsGetriebeneVerfeinerung",
    "PruefBefund",
    "PruefTuer",
    "RasterAufgabe",
    "RasterWahl",
    "ZellenOption",
    "ZerlegungsStrategie",
    "causing_axis",
    "option_menu",
]

#: Die drei IK-Achsen und ihre beiden konkreten Loesungszweige (Issue #129/#165) —
#: der **prozessneutrale** Hebel 1 der kollisionsgetriebenen Verfeinerung (#141):
#: ein anderer Zweig verlegt den Arm im Raum, ohne Bahn/Prozess zu aendern. Spiegelt
#: bewusst ``fgc.collision.advisor.IK_AXES`` (dieselbe Domaenensprache), bleibt aber
#: **lokal** — ``fgc.decompose`` haengt nicht an ``fgc.collision`` (Modularitaet).
IK_AXES: tuple[str, ...] = ("shoulder", "elbow", "wrist")
IK_VALUES: tuple[str, ...] = ("a", "b")

#: Automatische Platzierungs-Hebel (Hebel 1, #141) als **Deltas** auf die je Zelle
#: gesuchte Basis-Platzierung (Abstand vor der Wandfront, Aufstellhoehe, seitlich).
#: Deltas statt Absolutwerte, weil die Basis-Platzierung je Reihe/Zelle verschieden
#: ist (``propose`` sucht sie je Reihe) — Orakel und ``propose`` wenden **dasselbe**
#: Delta auf **dieselbe** Basis an (byte-vergleichbar). Kipp/Lead fehlen bewusst:
#: prozessrelevant, nie automatisch (#141, bleibt Advisor-Hebel).
STANDOFF_DELTAS_MM: tuple[float, ...] = (50.0, 100.0, 150.0)
STAND_HEIGHT_DELTAS_MM: tuple[float, ...] = (-50.0, 50.0)
LATERAL_DELTAS_MM: tuple[float, ...] = (-100.0, 100.0)


class PruefBefund(Protocol):
    """Das, was die Zerlegungs-Strategie aus **einem** Pruef-Tuer-Urteil braucht (#165).

    Strukturelle Sicht (Duck-Typing) auf :class:`fgc.collision.finding.ClearanceVerdict`:
    ``collides`` (mindestens ein Sample kollidiert) und ``causer_position_mm`` (Position
    des Verursacher-Glieds am schlimmsten Sample im **abschnitts-lokalen** System,
    Issue #181) — der Hebel, entlang dem die verursachende Achse *aus dem Befund*
    (nicht per Heuristik) gelesen wird. ``fgc.decompose`` bleibt so **geo-frei**: die
    schwere Kollisionsrechnung liegt hinter dem injizierten :data:`PruefTuer`-Orakel.
    """

    collides: bool
    causer_position_mm: tuple[float, float, float] | None


@dataclass(frozen=True)
class ZellenOption:
    """Die **automatischen** Hebel einer Zelle (Hebel 1 der #141-Reihenfolge).

    ``ik_block`` = (Teil-)IK-Konfiguration (Tri-State, prozessneutral); ``placement_delta``
    = sparse **Delta** auf die Basis-Platzierung (``standoff_mm``/``stand_height_mm``/
    ``lateral_mm``). Genau einer der beiden Hebel ist je Menue-Eintrag gesetzt; das leere
    ``ZellenOption()`` = **Basis** (nichts aendern). Kipp/Lead sind kein Feld —
    prozessrelevant, nie automatisch (#141).
    """

    ik_block: dict[str, str] | None = None
    placement_delta: dict[str, float] | None = None

    @property
    def is_baseline(self) -> bool:
        return not self.ik_block and not self.placement_delta

    @property
    def label(self) -> str:
        if self.ik_block:
            return "IK " + ",".join(f"{a}={v}" for a, v in sorted(self.ik_block.items()))
        if self.placement_delta:
            return "Platzierung " + ",".join(
                f"{k}{v:+.0f}" for k, v in sorted(self.placement_delta.items())
            )
        return "Basis"

    def to_dict(self) -> dict[str, Any]:
        return {"ik_block": self.ik_block, "placement_delta": self.placement_delta}


#: Das injizierte **Pruef-Tuer-Orakel** der kollisionsgetriebenen Verfeinerung (#165):
#: ``(kandidat, row_index, option) → Befund``. Es urteilt ueber den **Repraesentanten**
#: der Hoehenreihe ``row_index`` des Kandidaten-Rasters ``kandidat`` **von der Option aus**
#: (IK/Platzierung angewandt) und liefert einen :class:`PruefBefund` — oder ``None``
#: (unzustaendig: keine Kollisions-Geometrie, Altprojekt). Produktiv eine Closure ueber
#: die Abschnitts-Simulation (:func:`fgc.pipeline.sectionsim.collision_pruef_tuer`, #189);
#: in Tests ein deterministisches Fake (Muster wie der Advisor). Jeder Aufruf zaehlt gegen
#: das Aufruf-Kontingent (#178/#215).
PruefTuer = Callable[["BandRasterKandidat", int, "ZellenOption"], "PruefBefund | None"]


def option_menu(*, placement_levers: bool = True) -> tuple[ZellenOption, ...]:
    """Das **deterministische** Hebel-1-Menue je Zelle (Basis → IK → Platzierung, #141).

    Feste Reihenfolge (Determinismus, US 25): erst **Basis** (nichts aendern), dann die
    **IK-Konfiguration** (prozessneutral, je Achse beide Zweige), dann die **Platzierung**
    (Abstand/Aufstellhoehe/seitlich). Kipp/Lead kommen nie vor — prozessrelevant, nie
    automatisch (#141). Die Verfeinerung probiert die Eintraege der Reihe nach, bis ein
    Eintrag die Zelle frei meldet; jeder Versuch kostet einen Pruef-Tuer-Aufruf (Kontingent).

    ``placement_levers=False`` (Issue #237, Zerlegungsart „modul"): nur Basis + IK —
    an der **festen** Workstation-Platzierung (ADR-022) gibt es keine automatischen
    Platzierungs-Deltas (die Lage des Moduls am Druckort ist keine freie Suchachse).
    """
    menu: list[ZellenOption] = [ZellenOption()]
    for axis in IK_AXES:
        for value in IK_VALUES:
            menu.append(ZellenOption(ik_block={axis: value}))
    if placement_levers:
        for d in STANDOFF_DELTAS_MM:
            menu.append(ZellenOption(placement_delta={"standoff_mm": d}))
        for d in STAND_HEIGHT_DELTAS_MM:
            menu.append(ZellenOption(placement_delta={"stand_height_mm": d}))
        for d in LATERAL_DELTAS_MM:
            menu.append(ZellenOption(placement_delta={"lateral_mm": d}))
    return tuple(menu)


def causing_axis(
    cell_length_mm: float, cell_height_mm: float, causer_position_mm: tuple | None
) -> str:
    """Die **verursachende Achse** *aus dem Befund* — ``"length"`` oder ``"height"`` (#165).

    Keine Heuristik: liest die Position des Verursacher-Glieds (``causer_position_mm``,
    abschnitts-lokal — ``x`` zentriert um 0, ``z`` ab Zellfuss 0, Issue #181) und
    vergleicht, entlang welcher Achse das Glied — **relativ zur Zellgroesse** — am
    weitesten aus der Zellmitte ragt: ``rel_x = |x| / (Laenge/2)`` gegen
    ``rel_z = |z − Hoehe/2| / (Hoehe/2)``. Die groessere relative Auslenkung benennt die
    Achse, entlang der die Zelle zu gross ist. Gleichstand **und** fehlende Position ⇒
    ``"height"`` — der **Bandhoehe-senken-zuerst**-Vorrang der Hebel-Reihenfolge (#141:
    2. Bandhoehe senken, dann 3. Breite teilen).
    """
    if causer_position_mm is None:
        return "height"
    cx, _cy, cz = causer_position_mm
    half_len = max(1.0, cell_length_mm / 2.0)
    half_h = max(1.0, cell_height_mm / 2.0)
    rel_x = abs(float(cx)) / half_len
    rel_z = abs(float(cz) - cell_height_mm / 2.0) / half_h
    return "length" if rel_x > rel_z else "height"


@dataclass(frozen=True)
class RasterAufgabe:
    """Die eine Aufgabe an eine Zerlegungs-Strategie (US 19): Wahl des Band-Rasters.

    ``frac_at(n_length, n_height)`` ist das billige Reichweiten-Orakel je
    Kandidat-Zellgroesse (bei ``propose`` die Platzierungssuche bzw. die feste
    Workstation-Bewertung, #203); ``start`` der Seed ``(n_length, n_height)``;
    ``cap`` die Teilungs-Obergrenze je Achse (``propose.MAX_DIVISIONS``).

    ``kandidaten``/``bewerte``/``objective``/``call_budget`` sind der Kontext
    kandidaten-basierter Strategien (Beam #217): Kandidatenmenge aus dem
    Generator, billiger Scorer (liefert :class:`~fgc.decompose.scorer.
    KandidatBewertung` mit den #212-Kriterienwerten), Zielfunktions-Config und
    das Aufruf-Kontingent (#215). ``None`` = nicht verdrahtet (heutiger
    ``propose``-Pfad) — Strategien nutzen, was sie brauchen; dieselbe Aufgabe
    fuer alle Strategien ist die Grundlage des byte-vergleichbaren
    Paper-Vergleichs (US 19/27).
    """

    frac_at: Callable[[int, int], float]
    start: tuple[int, int]
    cap: int
    kandidaten: tuple[BandRasterKandidat, ...] | None = None
    bewerte: Callable[[BandRasterKandidat], KandidatBewertung] | None = None
    objective: ObjectiveConfig | None = None
    call_budget: int | None = None
    #: Das injizierte Pruef-Tuer-Orakel der kollisionsgetriebenen Verfeinerung (#165):
    #: ``(kandidat, row_index, option) → Befund``. ``None`` (Default) = kein Kollisions-
    #: Constraint — der reine Achsen-Greedy/Beam-Pfad bleibt byte-gleich. Braucht die
    #: :attr:`kandidaten` (die Verfeinerung schlaegt Raster darin nach).
    pruef_tuer: PruefTuer | None = None
    #: Das Hebel-1-Menue der Pruef-Tuer-Strategien (#165/#217). ``None`` (Default) =
    #: :func:`option_menu` mit allen Hebeln (byte-gleich zum Altverhalten). Die
    #: Zerlegungsart „modul" reicht das platzierungs-freie Menue herein (Issue #237:
    #: feste Workstation-Platzierung, ADR-022 — nur Basis + IK).
    menu: tuple[ZellenOption, ...] | None = None


@dataclass(frozen=True)
class RasterWahl:
    """Das Ergebnis einer Strategie: die gewaehlte Teilungszahl je Achse.

    ``bewertung`` traegt — nur bei kandidaten-basierten Strategien (#217) — die
    Scorer-Bewertung des Siegers (Kriterienwerte + Diagnose, fuer Provenienz und
    Verworfen-Gruende, US 10/20); der Achsen-Greedy laesst sie ``None``.
    """

    n_length: int
    n_height: int
    bewertung: KandidatBewertung | None = None
    #: Die je **Hoehenreihe** (``h_idx`` 0…n_height−1) gewaehlte automatische Option
    #: (IK/Platzierung) der kollisionsgetriebenen Verfeinerung (#165) — Basis, wenn keine
    #: noetig war. ``None`` bei den uebrigen Strategien (Greedy/Beam aendern keine
    #: Zell-Optionen). ``propose`` wendet den Platzierungs-Teil auf die Reihen-Platzierung
    #: an und stempelt IK + Provenienz in ``DecompositionPlan.refinement``.
    zellen_optionen: tuple[ZellenOption, ...] | None = None
    #: Der Provenienz-Block der kollisionsgetriebenen Verfeinerung (#165, ADR-004):
    #: Strategie, Aufruf-Kontingent, verbrauchte Aufrufe, je Reihe gewaehlter Hebel +
    #: Kollisions-Status. ``None`` bei den uebrigen Strategien.
    provenienz: dict[str, Any] | None = None


class ZerlegungsStrategie(ABC):
    """Interface der Zerlegungs-Suche (US 19) — extrahiert aus ``propose._refine`` (#203).

    Implementierungen: :class:`GreedyAchsenVerfeinerung` (der bisherige Loop,
    Default in ``propose``), die kollisionsgetriebene Greedy-Verfeinerung (#165)
    und die Beam-Suche (#217). Eine Strategie ist **deterministisch** (gleiche
    Aufgabe ⇒ gleiche Wahl) und benennt sich in der Provenienz (ADR-004).
    """

    #: Strategiename fuer die Lauf-Provenienz (ADR-004) — je Implementierung eigen.
    name: ClassVar[str] = "unbenannt"

    @abstractmethod
    def waehle_raster(self, aufgabe: RasterAufgabe) -> RasterWahl:
        """Waehlt deterministisch das Band-Raster fuer die Aufgabe."""

    def provenance(self) -> dict[str, Any]:
        """Der Provenienzblock der Strategie (ADR-004): Name + Surrogat-Modellstand.

        ``surrogate_model`` bleibt ``None``, solange kein Surrogat-Vorsortierer
        aktiv ist (#219 ueberschreibt mit dem Modellstand — Datensatz, Seed,
        Merkmalsliste); der Zerlegungslauf (#217) stempelt den Block in die
        Lauf-Provenienz.
        """
        return {"strategy": self.name, "surrogate_model": None}


class GreedyAchsenVerfeinerung(ZerlegungsStrategie):
    """Der bisherige Verfeinerungs-Loop aus ``propose._refine`` (#203) — extrahiert.

    Verfeinert ``(n_length, n_height)`` entlang der jeweils staerker
    blockierenden Achse: getestet wird, ob eine zusaetzliche Laengen- **oder**
    Hoehenteilung den erreichbaren Anteil (``frac_at``) staerker hebt; die
    staerkere gewinnt (Gleichstand: Laenge). Logik zeichenidentisch zum frueheren
    ``_refine`` — der Default in ``propose`` bleibt damit bit-identisch (die
    Goldens in ``test_decompose`` sichern das). Der Guard verhindert
    Endlosverfeinerung, falls ein Abschnitt physikalisch nie gruen wird
    (dann best effort, ``evaluate`` faerbt rot).
    """

    name = "greedy-achsen-verfeinerung"

    def waehle_raster(self, aufgabe: RasterAufgabe) -> RasterWahl:
        frac_at = aufgabe.frac_at
        n_v, n_h = aufgabe.start
        cap = aufgabe.cap
        frac = frac_at(n_v, n_h)
        guard = 0
        while frac < GREEN_THRESHOLD and (n_v < cap or n_h < cap) and guard < 4 * cap:
            guard += 1
            cand_v = frac_at(n_v + 1, n_h) if n_v < cap else -1.0
            cand_h = frac_at(n_v, n_h + 1) if n_h < cap else -1.0
            if cand_v >= cand_h:
                n_v += 1
                frac = cand_v
            else:
                n_h += 1
                frac = cand_h
        return RasterWahl(n_length=n_v, n_height=n_h)


#: Fallback-Aufruf-Kontingent, falls die Aufgabe keins traegt — spiegelt
#: ``propose.DEFAULT_CALL_BUDGET`` (#215), bleibt aber lokal (``propose`` importiert
#: ``strategie``, nicht umgekehrt — kein Zirkelimport). ``propose`` reicht den echten
#: Wert stets herein; dieser Default greift nur bei Direktaufrufen ohne Kontingent.
_FALLBACK_CALL_BUDGET = 20


class KollisionsGetriebeneVerfeinerung(ZerlegungsStrategie):
    """Der **eigentliche Constraint** (#165, Constraint-Serie Scheibe 4): eine Zelle gilt
    erst als gut, wenn sie **von der besten automatischen Option aus** kollisionsfrei ist.

    Haengt an **dieselbe** Naht wie der Achsen-Greedy (:meth:`waehle_raster`) — kein
    zweiter Verfeinerungs-Loop (#216). Statt des billigen Reichweiten-Orakels ``frac_at``
    treibt hier das injizierte **Pruef-Tuer-Orakel** (:data:`RasterAufgabe.pruef_tuer`,
    #162) die Verfeinerung. Hebel-Reihenfolge strikt nach der HITL-Entscheidung #141
    (2026-07-10):

    1. **IK-Konfiguration** (prozessneutral) + **Platzierung** (Abstand/Aufstellhoehe/
       seitlich) je Zelle — automatisch (:func:`option_menu`, feste Reihenfolge).
    2. **Bandhoehe senken** (``n_height += 1``), dann 3. **Breite teilen**
       (``n_length += 1``) — **entlang der verursachenden Achse aus dem Befund**
       (:func:`causing_axis`, keine Heuristik; Gleichstand ⇒ Bandhoehe zuerst).

    **Kipp wird nie automatisch variiert** (prozessrelevant — kein Kipp-Feld im Menue),
    **Tiefenteilung nie automatisch** (die Verfeinerung teilt nur Hoehe/Laenge, #142).
    Der ``MAX_DIVISIONS``-Deckel (``aufgabe.cap``) bleibt; das **Aufruf-Kontingent**
    (``aufgabe.call_budget``, #178/#215) deckelt die exakten Pruef-Tuer-Aufrufe je Lauf —
    **kein Zeitbudget** (Determinismus: gleicher Input ⇒ gleiche Aufruffolge ⇒ gleicher
    Schnitt, maschinenunabhaengig, US 25). Ist das Kontingent erschoepft oder der Deckel
    erreicht, endet die Verfeinerung **best effort** (der Plan wird ehrlich rot bewertet;
    Befund, kein Gate).

    **Fail-soft:** ohne Orakel (``pruef_tuer is None``) oder wenn das Orakel ``None``
    (unzustaendig, keine Kollisions-Geometrie) meldet, faellt die Strategie auf den
    Achsen-Greedy zurueck (byte-gleiche Plaene) — nie ein geratenes „frei" (ADR-013).
    """

    name = "kollisionsgetriebene-verfeinerung"

    def waehle_raster(self, aufgabe: RasterAufgabe) -> RasterWahl:
        if aufgabe.pruef_tuer is None or not aufgabe.kandidaten:
            # Fail-soft: kein Kollisions-Constraint verdrahtet ⇒ Achsen-Greedy (byte-gleich).
            wahl = GreedyAchsenVerfeinerung().waehle_raster(aufgabe)
            return _mit_provenienz(wahl, {"strategy": self.name, "fallback": "kein-orakel"})

        pruef_tuer = aufgabe.pruef_tuer
        cap = aufgabe.cap
        budget = (
            aufgabe.call_budget if aufgabe.call_budget is not None else _FALLBACK_CALL_BUDGET
        )
        menu = aufgabe.menu if aufgabe.menu is not None else option_menu()
        kandidat_by_raster = {(k.n_length, k.n_height): k for k in aufgabe.kandidaten}

        # Die Verfeinerung startet bewusst bei (1, 1) — die Kollisionsfreiheit soll den
        # Schnitt treiben, nicht der roboter-feste Arbeitsraum-Seed (der ``aufgabe.start``
        # aus der Reichweite bleibt fuer den Greedy). Gedeckelt durch ``cap``.
        n_v, n_h = 1, 1
        calls = 0
        capped = False
        budget_exhausted = False
        rows_prov: list[dict[str, Any]] = []
        chosen: list[ZellenOption] = []

        while True:
            kandidat = kandidat_by_raster.get((n_v, n_h))
            if kandidat is None:
                # Kandidat ausserhalb der vorgenerierten Menge (Deckel) ⇒ best effort.
                capped = True
                break
            cell_length = kandidat.wall.length_mm / n_v
            cell_height = kandidat.wall.height_mm / n_h
            rows_prov = []
            chosen = []
            subdivide_axis: str | None = None
            unzustaendig = False

            for h_idx in range(n_h):
                row_choice: ZellenOption | None = None
                last: PruefBefund | None = None
                for opt in menu:
                    if calls >= budget:
                        budget_exhausted = True
                        break
                    befund = pruef_tuer(kandidat, h_idx, opt)
                    calls += 1
                    if befund is None:
                        unzustaendig = True
                        break
                    last = befund
                    if not befund.collides:
                        row_choice = opt
                        break
                if unzustaendig or budget_exhausted:
                    break
                if row_choice is not None:
                    chosen.append(row_choice)
                    rows_prov.append(
                        {
                            "h_idx": h_idx,
                            "collision_free": True,
                            "lever": row_choice.label,
                            "option": row_choice.to_dict(),
                        }
                    )
                else:
                    # Reihe durch Hebel 1 nicht frei ⇒ verursachende Achse aus dem Befund.
                    subdivide_axis = causing_axis(
                        cell_length,
                        cell_height,
                        last.causer_position_mm if last is not None else None,
                    )
                    rows_prov.append(
                        {
                            "h_idx": h_idx,
                            "collision_free": False,
                            "lever": None,
                            "subdivide_axis": subdivide_axis,
                        }
                    )
                    break

            if unzustaendig:
                # Orakel unzustaendig (keine Geometrie) ⇒ Greedy-Fallback (nie geratenes frei).
                wahl = GreedyAchsenVerfeinerung().waehle_raster(aufgabe)
                return _mit_provenienz(
                    wahl,
                    {"strategy": self.name, "fallback": "unzustaendig", "calls_used": calls},
                )

            if subdivide_axis is None:
                # Alle Reihen frei (oder Budget erschoepft mit Teilbelegung) — fertig.
                break

            # Hebel 2/3: entlang der verursachenden Achse teilen (Bandhoehe zuerst bei
            # Gleichstand). Ist die gewaehlte Achse am Deckel, weicht die Verfeinerung auf
            # die andere aus; sind beide am Deckel ⇒ best effort.
            if budget_exhausted:
                break
            if subdivide_axis == "height" and n_h < cap:
                n_h += 1
            elif subdivide_axis == "length" and n_v < cap:
                n_v += 1
            elif n_h < cap:
                n_h += 1
            elif n_v < cap:
                n_v += 1
            else:
                capped = True
                break

        # Reihen ohne eigene Wahl (Budget mitten in der Reihe erschoepft, oder capped)
        # erben die Basis-Option — ehrlich, deterministisch (evaluate faerbt sie ggf. rot).
        while len(chosen) < n_h:
            chosen.append(ZellenOption())

        provenienz = {
            "strategy": self.name,
            "call_budget": budget,
            "calls_used": calls,
            "budget_exhausted": budget_exhausted,
            "capped": capped,
            "rows": rows_prov,
        }
        return RasterWahl(
            n_length=n_v,
            n_height=n_h,
            zellen_optionen=tuple(chosen),
            provenienz=provenienz,
        )


def _mit_provenienz(wahl: RasterWahl, provenienz: dict[str, Any]) -> RasterWahl:
    """Kleiner Helfer: haengt einen Provenienz-Block an eine (Greedy-)Wahl (Fallback-Pfad)."""
    from dataclasses import replace as _replace

    return _replace(wahl, provenienz=provenienz)
