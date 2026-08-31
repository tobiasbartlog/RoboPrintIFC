"""Zerlegungsvorschlag: ``propose(wand, roboter, endeffektor)`` (Issue #24/#90).

Reicht keine einzelne Platzierung fuer 100 % der Wand, schlaegt dieses Modul eine
**Zerlegung** in nacheinander druckbare **Teile** vor: ebene, achsparallele
Schnittebenen — horizontal (Hoehenstufen) und/oder vertikal (Laengenteilung).
Zwei Zerlegungsarten (`core/CONTEXT.md`, ADR-022):

- **Abschnitt** (in place): jedes Teil wird an der Endposition gedruckt und von
  *seiner* Platzierung aus zu 100 % erreicht (der Roboter wird umgesetzt);
  Druckreihenfolge unten → oben.
- **Modul** (Issue #90, ADR-022): jedes Teil wird stehend in Einbauorientierung
  an der **Workstation** vorproduziert — der Roboter sitzt fest an
  ``robot_base_frame``, jedes Modul liegt auf der Arbeitsflaeche. Statt einer
  Platzierungssuche je Zelle gilt daher **eine feste Platzierung** fuer alle
  Teile; die Rasterverfeinerung prueft gegen den Arbeitsraum an dieser festen
  Lage (hart) und gegen optionale Obergrenzen max. Modullaenge/-hoehe
  (:class:`fgc.decompose.limits.ModuleLimits`).

Die Reichweite je Teil kommt ausschliesslich aus der bestehenden
Platzierungssuche/-bewertung `fgc.placement` (Issue #23) — nichts dupliziert.
Bei „abschnitt" schaetzt die Startteilung der Roboter-Arbeitsraum
(`max_print_*`), verfeinert wird entlang der *tatsaechlich* blockierenden Achse
(die, deren Verkleinerung den erreichbaren Anteil am staerksten hebt) — so
bleibt der Vorschlag fuer eine ueberhohe Wand horizontal, fuer eine ueberlange
vertikal.

Die Rasterwahl laeuft seit Issue #216 ueber das **Zerlegungs-Strategie-
Interface** (`fgc.decompose.strategie`, PRD #183 US 19): Default ist der aus
``_refine`` (#203) extrahierte Achsen-Greedy (bit-identische Plaene); #165
(kollisionsgetriebene Verfeinerung) und #217 (Beam-Suche) implementieren
dasselbe Interface, die Lauf-Provenienz nennt die Strategie (ADR-004).

Deterministisch (ADR-004-Geist): gleiche Eingaben → gleicher Schnittplan.
Einheiten strikt nach ADR-006: Millimeter, Radiant.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from fgc.decompose.limits import ModuleLimits
from fgc.decompose.plan import (
    DECOMPOSITION_KINDS,
    Cut,
    DecompositionPlan,
    Section,
    SectionPlan,
)
from fgc.decompose.strategie import (
    GreedyAchsenVerfeinerung,
    KollisionsGetriebeneVerfeinerung,
    PruefTuer,
    RasterAufgabe,
    RasterWahl,
    ZerlegungsStrategie,
    option_menu,
)
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.placement import (
    DEFAULT_STANDOFF_MM,
    SAMPLE_SPACING_MM,
    PlacementOption,
    WallSurface,
    suggest,
)
from fgc.placement import evaluate as evaluate_placement

if TYPE_CHECKING:
    from fgc.decompose.objective import ObjectiveConfig
    from fgc.decompose.scorer import BilligerScorer
    from fgc.domain.workstation import WorkstationDef


def _reachability_only(_option: PlacementOption) -> bool:
    """Alt-Zustand des Optimalvorschlags (alles frei ⇒ reine Erreichbarkeits-Optimierung).

    Der Zerlegungsvorschlag urteilt Kollision über die **Prüf-Tür** (#162/#165), nicht
    über den Platzierungs-Grob-Check (#131/#228): Machbarkeit in der Zerlegungs-
    Zielfunktion ist ein eigener Track (ADR-026 / PRD #225 Out of Scope). Deshalb ruft
    ``propose`` ``suggest`` **explizit reachability-only** (kein Grob-Check-Vorfilter) —
    der neue Default-an (Issue #228) bleibt auf den Placement-Optimalvorschlag begrenzt,
    die Zerlegungs-Schnitte bleiben byte-gleich.
    """
    return True


#: Obergrenze der Teilungen je Achse — verhindert Endlosverfeinerung, falls ein
#: Abschnitt physikalisch nie gruen wird (dann best effort, evaluate faerbt rot).
MAX_DIVISIONS = 16

#: Default-Aufruf-Kontingent der Zerlegungs-/Platzierungssuche (Grill-Verfahren
#: 2026-07-14, #178/#183): **ein** Kontingent zaehlt exakte Pruef-Tuer-Aufrufe
#: (find_collisions je Kandidat), nicht Sekunden — deterministisch und
#: byte-vergleichbar (Voraussetzung des Invarianz-Orakels #183-US 25). Der Wert ist
#: die **groesste runde Aufruf-Zahl**, deren Hintergrundlauf ≤ ~5 min (300 s) auf
#: der Referenzmaschine bleibt: gemessen an der AP-1-Nachher-Messung (#215,
#: SDF-Backend, produktiv verduennt) mit ~9,77 s je Aufruf ⇒ 300/9,77 = 30 roh ⇒
#: **20** (≈195 s Vorhersage). Je Druckjob uebersteuerbar (die Provenienz traegt
#: den Wert — langsamere Maschine ⇒ laengerer Lauf, bit-gleicher Schnitt). Die
#: Beam-Breite k leitet die Suche (#217) aus diesem Kontingent ab, kein eigener
#: Parameter. Belege: ``docs/spikes/S5c_ap1_nachher_abnahme.md``, Design-Log
#: 2026-07-14 (#215).
DEFAULT_CALL_BUDGET = 20


def _waehle_raster(
    strategie: ZerlegungsStrategie,
    frac_at: Callable[[int, int], float],
    n_v: int,
    n_h: int,
    cap: int,
) -> tuple[int, int]:
    """Die Strategie-Naht der Rasterwahl (Issue #216, PRD #183 US 19).

    Der fruehere gemeinsame Verfeinerungs-Loop ``_refine`` (#203 — ein Loop fuer
    ``_grid_counts`` [Art „abschnitt", ``frac_at`` sucht je Kandidat-Zellgroesse
    eine neue Platzierung] und ``_module_grid_counts`` [Art „modul", ``frac_at``
    bewertet an der festen Workstation-Platzierung]) ist nach
    ``fgc.decompose.strategie`` extrahiert: die Wahl trifft eine injizierte
    :class:`ZerlegungsStrategie` — Default :class:`GreedyAchsenVerfeinerung`
    (zeichenidentische Logik, bit-gleiche Plaene), austauschbar gegen die
    kollisionsgetriebene Greedy-Verfeinerung (#165) oder die Beam-Suche (#217).
    """
    wahl = strategie.waehle_raster(RasterAufgabe(frac_at=frac_at, start=(n_v, n_h), cap=cap))
    return wahl.n_length, wahl.n_height


def _reachable_fraction(
    length_mm: float,
    height_mm: float,
    thickness_mm: float,
    robot: RobotDef,
    tool: ToolDef,
    spacing_mm: float,
    workstation: WorkstationDef | None = None,
    stand_mode: str = "floor",
) -> float:
    """Bester erreichbarer Anteil eines Abschnitts-Rechtecks (Platzierungssuche).

    Traegt der Druckjob eine Workstation, kommt die Kandidatenmenge aus deren
    Podesthoehen-Satz, begrenzt durch den Aufstell-Toggle ``stand_mode`` (Issue
    #81): ``'floor'`` klemmt die Basis auf Bodenhoehe (weniger vertikale
    Reichweite → kleinere erreichbare Flaeche je Zelle → mehr Hoehenbaender),
    ``'elevated'`` erlaubt die realen Podesthoehen.

    Bewusst am Boden (``z_offset = 0``, Issue #132): diese Funktion ist die
    **Zellgroessen-Heuristik** der Rasterverfeinerung — sie fragt, wie gross
    eine Zelle sein darf, damit der Roboter sie von einer guten Aufstellung aus
    abdeckt. Die ehrliche Bewertung an der echten Hoehenlage macht danach die
    Platzierungssuche je Reihe + ``fgc.decompose.evaluate`` (Befund, kein Gate:
    im Boden-Modus unerreichbare obere Reihen werden trotzdem geschnitten und
    ehrlich rot gemeldet).
    """
    surface = WallSurface(length_mm, height_mm, thickness_mm)
    best = suggest(
        surface, robot, tool, workstation=workstation, stand_mode=stand_mode,
        n_best=1, spacing_mm=spacing_mm, collision_free=_reachability_only,
        config_axis=False,
    )
    return best[0][1].reachable_fraction if best else 0.0


def _grid_counts(
    wall: WallSurface,
    robot: RobotDef,
    tool: ToolDef,
    spacing_mm: float,
    cap: int,
    workstation: WorkstationDef | None = None,
    stand_mode: str = "floor",
    strategie: ZerlegungsStrategie | None = None,
    pruef_tuer: PruefTuer | None = None,
    call_budget: int = DEFAULT_CALL_BUDGET,
    scorer: BilligerScorer | None = None,
    objective: ObjectiveConfig | None = None,
) -> RasterWahl:
    """Bestimmt die Teilungszahl (n_length, n_height), sodass jede Zelle gruen ist.

    Startwert aus dem Roboter-Arbeitsraum (`max_print_length`/`max_print_height`),
    dann Verfeinerung entlang der *blockierenden* Achse: getestet wird, ob eine
    zusaetzliche Laengen- **oder** Hoehenteilung den erreichbaren Anteil staerker
    hebt; die staerkere gewinnt. So werden nicht-blockierende Achsen nicht
    unnoetig geteilt (ueberhoch → nur horizontal, ueberlang → nur vertikal).

    Traegt der Job eine Workstation + Aufstell-Toggle (Issue #81), leitet der
    Toggle den Podesthoehen-Satz je Zelle her: ``'floor'`` (Basis fix am Boden)
    erreicht ueberhohe Zellen schlechter → die Verfeinerung fuegt mehr
    Hoehenteilungen ein als ``'elevated'`` (Basis darf auf ein Podest). Damit der
    Toggle die Hoehenteilung ueberhaupt bestimmen kann, startet die Suche **mit
    Workstation** bewusst bei ``(1, 1)`` (reine, toggle-abhaengige Verfeinerung)
    statt am roboter-festen Arbeitsraum-Startwert ``max_print_height`` — der wuerde
    beide Toggle-Zustaende auf denselben Startwert seeden und den Unterschied
    verschlucken. Ohne Workstation bleibt der bewaehrte Arbeitsraum-Seed (Golden).
    """
    if workstation is not None:
        # Toggle-abhaengige Hoehenteilung: von (1, 1) rein per Reichweite verfeinern.
        n_v = 1
        n_h = 1
    else:
        n_v = 1
        n_h = 1
        if wall.length_mm > 0:
            n_v = min(cap, max(1, math.ceil(wall.length_mm / robot.max_print_length_mm)))
        if wall.height_mm > 0:
            n_h = min(cap, max(1, math.ceil(wall.height_mm / robot.max_print_height_mm)))

    thick = wall.thickness_mm

    def frac_at(nv: int, nh: int) -> float:
        return _reachable_fraction(
            wall.length_mm / nv, wall.height_mm / nh, thick, robot, tool, spacing_mm,
            workstation, stand_mode,
        )

    # Kandidaten-basierte Suche (Band-Raster bis ``cap``, geteilter Generator #216):
    # liegt ein billiger Scorer (Beam #217) **oder** ein Pruef-Tuer-Orakel (kollisions-
    # getriebene Verfeinerung #165) vor, treibt nicht mehr allein die Reichweite den
    # Schnitt. Der Generator wird lazy importiert (``kandidaten`` importiert ``propose``:
    # kein Zirkel beim Modulladen); ``beam`` ebenso (Beam → scorer → kandidaten → propose).
    if pruef_tuer is not None or scorer is not None:
        from fgc.decompose.kandidaten import band_raster_kandidaten

        aufgabe = RasterAufgabe(
            frac_at=frac_at,
            start=(n_v, n_h),
            cap=cap,
            kandidaten=band_raster_kandidaten(wall, cap=cap),
            bewerte=scorer.bewerte if scorer is not None else None,
            objective=objective,
            call_budget=call_budget,
            pruef_tuer=pruef_tuer,
        )
        if strategie is not None:
            strat: ZerlegungsStrategie = strategie
        elif scorer is not None:
            # Beam-Suche (#217): billiger Scorer ordnet, nur Ueberlebende durch die
            # Pruef-Tuer; die Beam-Breite k kommt aus dem Kontingent (kein Parameter).
            from fgc.decompose.beam import BeamSuche

            strat = BeamSuche()
        else:
            strat = KollisionsGetriebeneVerfeinerung()
        return strat.waehle_raster(aufgabe)

    aufgabe = RasterAufgabe(frac_at=frac_at, start=(n_v, n_h), cap=cap)
    return (strategie or GreedyAchsenVerfeinerung()).waehle_raster(aufgabe)


def _check_kind(kind: str, workstation: WorkstationDef | None) -> None:
    """Validiert die Zerlegungsart + den Modul-Druckort (freundlicher Hinweis, #90).

    Unbekannte Art → ``ValueError`` mit den erlaubten Arten. Art „modul" ohne
    Workstation → klarer Hinweispfad (ADR-022: die Workstation *ist* der
    Druckort der Modul-Fertigung — ohne sie gibt es keine feste Platzierung).
    """
    if kind not in DECOMPOSITION_KINDS:
        raise ValueError(
            f"Zerlegungsart {kind!r} unbekannt — erlaubt: {list(DECOMPOSITION_KINDS)} "
            "(core/CONTEXT.md: 'abschnitt' = in place, 'modul' = an der Workstation "
            "vorproduziert)."
        )
    if kind == "modul" and workstation is None:
        raise ValueError(
            "Zerlegungsart 'modul' braucht eine Workstation — sie ist der Druckort "
            "(ADR-022): der Roboter sitzt fest an ihrer Basis, jedes Modul wird auf "
            "der Arbeitsflaeche stehend in Einbauorientierung gedruckt. Bitte zuerst "
            "im Druckjob eine Workstation waehlen (Reiter Roboter, "
            "PUT /projects/{slug}/workstation)."
        )


def _module_placement(
    workstation: WorkstationDef, thickness_mm: float
) -> PlacementOption:
    """Die **feste** Platzierung der Modul-Fertigung an der Workstation (ADR-022).

    Der Roboter sitzt fest an ``robot_base_frame``, das Modul steht vor ihm auf
    der Arbeitsflaeche (``work_surface_frame``) — rechnerisch dieselbe Relativpose
    wie bei „abschnitt", nur invertiert gelesen (das Modul steht, der Roboter
    bleibt). Tragen beide Frames Werte, wird die Relativpose daraus abgeleitet:
    Abstand = horizontale Distanz der Frame-Urspruenge **minus halbe Moduldicke**
    (Issue #160: ``standoff_mm`` ist die Freidistanz vor der Modulflaeche; der
    Arbeitsflaechen-Ursprung traegt die Modulmitte), nie unter dem
    Sicherheits-Mindestabstand; Aufstellhoehe = Basis-Hoehe relativ zur
    Arbeitsflaeche (dem Modulfuss). Ohne Frames (Altbestand, ADR-021 optional)
    gilt der Standard-Abstand — deterministisch, kein Raten.
    """
    half = max(0.0, float(thickness_mm)) / 2.0
    base = workstation.robot_base_frame
    surface = workstation.work_surface_frame
    if base is not None and surface is not None:
        bx, by, bz = (float(v) for v in base["pos_mm"])
        sx, sy, sz = (float(v) for v in surface["pos_mm"])
        standoff = max(
            math.hypot(sx - bx, sy - by) - half, workstation.safety_min_distance_mm
        )
        stand_height = bz - sz
    else:
        standoff = max(DEFAULT_STANDOFF_MM, workstation.safety_min_distance_mm)
        stand_height = 0.0
    return PlacementOption(
        option_id="workstation-druckort",
        lateral_mm=0.0,  # Modul mittig vor der Basis (ADR-022, wie #80 zentral)
        standoff_mm=round(standoff, 1),
        stand_height_mm=round(stand_height, 1),
    )


#: Oeffentliche Tuer zur festen Druckort-Platzierung (Issue #237): der Beam-Aufbau
#: (``fgc.pipeline.actions._beam_search_setup``) braucht dieselbe Platzierung fuer den
#: modul-lokalen Scorer — eine Quelle, keine Duplikation (ADR-022).
modul_druckort_platzierung = _module_placement


def _module_grid_counts(
    wall: WallSurface,
    robot: RobotDef,
    tool: ToolDef,
    spacing_mm: float,
    cap: int,
    placement: PlacementOption,
    limits: ModuleLimits,
    strategie: ZerlegungsStrategie | None = None,
) -> tuple[int, int]:
    """Teilungszahl (n_length, n_height) fuer Art „modul" (Issue #90, ADR-022).

    Anders als bei „abschnitt" gibt es **keine Platzierungssuche je Zelle**: jede
    Zelle wird an der *festen* Workstation-Platzierung bewertet
    (`fgc.placement.evaluate`). Der Startwert kommt aus den optionalen
    Obergrenzen (Zelle > Obergrenze ⇒ weitere Teilung — ``ceil`` garantiert
    Zellen ≤ Grenze); ohne Obergrenzen startet die Suche bei (1, 1). Danach
    verfeinert der Arbeitsraum (hart) entlang der blockierenden Achse wie bei
    „abschnitt" — die Verfeinerung teilt nur weiter, nie groeber, Obergrenzen
    bleiben also immer eingehalten. Deterministisch.
    """
    n_v = 1
    n_h = 1
    if limits.max_length_mm is not None and wall.length_mm > 0:
        n_v = min(cap, max(1, math.ceil(wall.length_mm / limits.max_length_mm)))
    if limits.max_height_mm is not None and wall.height_mm > 0:
        n_h = min(cap, max(1, math.ceil(wall.height_mm / limits.max_height_mm)))

    thick = wall.thickness_mm

    def frac_at(nv: int, nh: int) -> float:
        cell = WallSurface(wall.length_mm / nv, wall.height_mm / nh, thick)
        return evaluate_placement(
            cell, robot, tool, placement, spacing_mm=spacing_mm
        ).reachable_fraction

    return _waehle_raster(strategie or GreedyAchsenVerfeinerung(), frac_at, n_v, n_h, cap)


def _apply_placement_delta(
    option: PlacementOption, delta: dict[str, float] | None
) -> PlacementOption:
    """Wendet ein sparse Platzierungs-**Delta** der Verfeinerung an (Issue #165).

    ``delta`` ist die Nutzlast eines Platzierungs-Hebels der kollisionsgetriebenen
    Verfeinerung (``standoff_mm``/``stand_height_mm``/``lateral_mm``, additiv auf die
    je Reihe gesuchte Basis-Lage) — **dasselbe** Delta, das das Pruef-Tuer-Orakel
    bewertet hat (byte-vergleichbar). ``None``/leer ⇒ die Basis-Lage unveraendert.
    """
    if not delta:
        return option
    return replace(
        option,
        lateral_mm=option.lateral_mm + float(delta.get("lateral_mm", 0.0)),
        standoff_mm=option.standoff_mm + float(delta.get("standoff_mm", 0.0)),
        stand_height_mm=option.stand_height_mm + float(delta.get("stand_height_mm", 0.0)),
    )


def _build_cuts(wall: WallSurface, n_v: int, n_h: int) -> tuple[Cut, ...]:
    """Innere Schnittebenen (Wandaussenkanten sind keine Schnitte)."""
    cuts: list[Cut] = []
    for i in range(1, n_h):  # horizontale Ebenen (Hoehenstufen)
        cuts.append(Cut("horizontal", round(wall.height_mm * i / n_h, 3)))
    for i in range(1, n_v):  # vertikale Ebenen (Laengenteilung)
        cuts.append(Cut("vertical", round(-wall.length_mm / 2.0 + wall.length_mm * i / n_v, 3)))
    return tuple(cuts)


def propose(
    wall: WallSurface,
    robot: RobotDef,
    tool: ToolDef,
    options: list[PlacementOption] | None = None,
    *,
    kind: str = "abschnitt",
    spacing_mm: float = SAMPLE_SPACING_MM,
    cap: int = MAX_DIVISIONS,
    workstation: WorkstationDef | None = None,
    stand_mode: str = "floor",
    limits: ModuleLimits | None = None,
    strategie: ZerlegungsStrategie | None = None,
    pruef_tuer: PruefTuer | None = None,
    call_budget: int = DEFAULT_CALL_BUDGET,
    scorer: BilligerScorer | None = None,
    objective: ObjectiveConfig | None = None,
) -> DecompositionPlan:
    """Schlaegt eine Zerlegung der Wand in erreichbare Teile vor (Issue #24/#81/#90).

    Liefert einen :class:`DecompositionPlan`: achsparallele Schnittebenen und eine
    Liste von Paaren (Abschnitt, Platzierung) in Druckreihenfolge (unten → oben,
    dann links → rechts), jeder Abschnitt von seiner Platzierung aus (angestrebt)
    zu 100 % erreichbar. Reicht bereits eine Platzierung fuer die ganze Wand, ist
    das Ergebnis ein einziger Abschnitt ohne Schnitte.

    ``workstation`` + ``stand_mode`` binden die Abschnittssuche an die reale
    Aufstell-Umgebung + den Aufstell-Toggle (Issue #81): der Toggle begrenzt den
    Podesthoehen-Satz, den jede Zellensuche nutzen darf — ``'floor'`` (Basis fix am
    Boden) leitet **mehr** Hoehenbaender ab als ``'elevated'`` (Basis darf auf ein
    Podest), weil die vertikale Reichweite am Boden begrenzt ist. Ohne Workstation
    (Altprojekt) bleibt es beim bisherigen Fallback-Raster (der Toggle wirkt dann
    nicht — ohne reale Podesthoehen gibt es nichts zu begrenzen).

    **Absolute Aufstellhoehen (Issue #132, Design-Log 2026-07-09):** die
    Platzierungssuche je Abschnitt sieht die echte Hoehenlage der Reihe
    (``z0..z1`` absolut) und liefert ``stand_height_mm`` **absolut ueber dem
    Boden** (Boden = Wandfuss; Boden-Modus ⇒ Hoehensatz ``[0]`` absolut).
    Im Boden-Modus unerreichbare obere Reihen werden trotzdem geschnitten —
    Befund, kein Gate, die Ampel (`evaluate`) sagt die Wahrheit.

    ``kind="modul"`` (Issue #90, ADR-022): statt Platzierungssuche je Zelle gilt
    **eine feste Platzierung an der Workstation** (Roboter an ``robot_base_frame``,
    Modul stehend in Einbauorientierung vor ihm) — dieselbe Pose fuer alle Teile.
    Die Rasterverfeinerung prueft gegen den Arbeitsraum an dieser festen Lage
    (hart) **und** gegen die optionalen Obergrenzen ``limits`` (Zelle > Obergrenze
    ⇒ weitere Teilung; leer = nur Arbeitsraum). Ohne Workstation wird „modul" mit
    einem freundlichen Hinweis abgelehnt (die Workstation ist der Druckort).
    Druckreihenfolge = Montagereihenfolge (unten → oben, links → rechts).

    ``options`` (reale Aufstellmoeglichkeiten) ist fuer die spaetere Bewertungs-
    modus-Variante vorgesehen; v1 sucht je Abschnitt frei (Optimalvorschlag).

    ``strategie`` (Issue #216, PRD #183 US 19) ist die austauschbare
    Zerlegungs-Strategie der Rasterwahl (`fgc.decompose.strategie`): Default
    :class:`GreedyAchsenVerfeinerung` — der bisherige Verfeinerungs-Loop
    (frueher ``_refine``, #203), bit-identische Plaene. Die kollisionsgetriebene
    Greedy-Verfeinerung (#165) und die Beam-Suche (#217) implementieren dasselbe
    Interface; die Lauf-Provenienz nennt die Strategie
    (``strategie.provenance()``, ADR-004 — gestempelt vom Zerlegungslauf #217).

    ``pruef_tuer`` (Issue #165, Art „abschnitt"; seit #237 auch Art „modul" ueber die
    Kandidaten-Naht mit platzierungs-freiem Hebel-Menue) schaltet die **kollisionsgetriebene
    Verfeinerung** ein: das injizierte Pruef-Tuer-Orakel (`fgc.collision.finding`, #162
    — produktiv ueber `fgc.pipeline.sectionsim.collision_pruef_tuer`, #189) urteilt je
    Zelle **von der besten automatischen Option aus** (IK/Platzierung, Reihenfolge #141),
    und die Verfeinerung teilt entlang der **verursachenden Achse aus dem Befund**
    (:func:`fgc.decompose.strategie.causing_axis`) — gedeckelt durch ``cap`` und das
    **Aufruf-Kontingent** ``call_budget`` (#178/#215, kein Zeitbudget). Der gewaehlte
    Platzierungs-Hebel je Reihe landet **in den Teil-Platzierungen**, die Provenienz
    (Strategie/Kontingent/Hebel je Reihe) in ``DecompositionPlan.refinement``. Ohne
    ``pruef_tuer`` (Default ``None``) bleibt der Plan byte-gleich (nur Reichweite).
    Kipp/Tiefenteilung werden **nie** automatisch variiert (#141/#142).

    ``scorer`` (Issue #217, Art „abschnitt"; seit #237 auch Art „modul" — der Scorer
    bewertet dann **modul-lokal** an der festen Druckort-Platzierung,
    ``BilligerScorer(fixe_platzierung=…)``) schaltet die **Beam-Suche** ein: der
    billige Scorer (`fgc.decompose.scorer.BilligerScorer`) bewertet **alle**
    Band-Raster-Kandidaten gratis, der ``objective``-Komparator (#212) ordnet sie,
    der Beam behaelt die besten k (k aus ``call_budget`` abgeleitet, kein Parameter)
    und **nur die Ueberlebenden** durchlaufen die Pruef-Tuer (``pruef_tuer``, exaktes
    Urteil). Der gewaehlte Schnitt + Metriken-Katalog + Verworfen-Gruende +
    Relaxationsausweis landen in ``DecompositionPlan.refinement``
    (`fgc.decompose.beam.BeamSuche`). Ohne ``scorer`` (Default ``None``) bleibt der
    Plan byte-gleich; ist zusaetzlich ``pruef_tuer`` gesetzt, greift die #165-
    Verfeinerung. Eine explizite ``strategie`` gewinnt immer.

    Wirft ``ValueError`` bei unbekannter Zerlegungsart, bei Art „modul" ohne
    Workstation oder wenn der Roboter keine Kinematik traegt (ueber
    `fgc.placement`).
    """
    _check_kind(kind, workstation)

    if kind == "modul":
        assert workstation is not None  # _check_kind garantiert das
        placement = _module_placement(workstation, wall.thickness_mm)
        limits_ = limits or ModuleLimits()
        refinement: dict[str, object] | None = None
        if pruef_tuer is not None or scorer is not None:
            # Zerlegung als Suche auch fuer Art „modul" (Issue #237): dieselbe
            # Kandidaten-Naht wie `_grid_counts` — der Scorer bewertet modul-lokal
            # an der festen Druckort-Platzierung (`BilligerScorer(fixe_platzierung=…)`),
            # die Pruef-Tuer urteilt exakt am Druckort (`collision_pruef_tuer` reicht
            # die Zerlegungsart durch). Das Hebel-Menue ist platzierungs-frei
            # (Basis + IK): die Workstation-Platzierung ist fest (ADR-022), ein
            # automatisches Platzierungs-Delta waere eine stille Lageaenderung.
            from fgc.decompose.beam import BeamSuche
            from fgc.decompose.kandidaten import band_raster_kandidaten

            # Obergrenzen (Transport/Montage, #90) filtern die Kandidatenmenge hart
            # vor — dieselbe ceil-Herleitung wie der Greedy-Startwert garantiert
            # Zellen ≤ Grenze; die Suche waehlt also nie ein grenzverletzendes Raster.
            min_v = 1
            min_h = 1
            if limits_.max_length_mm is not None and wall.length_mm > 0:
                min_v = min(cap, max(1, math.ceil(wall.length_mm / limits_.max_length_mm)))
            if limits_.max_height_mm is not None and wall.height_mm > 0:
                min_h = min(cap, max(1, math.ceil(wall.height_mm / limits_.max_height_mm)))
            kandidaten = tuple(
                k
                for k in band_raster_kandidaten(wall, cap=cap)
                if k.n_length >= min_v and k.n_height >= min_h
            )

            def modul_frac_at(nv: int, nh: int) -> float:
                cell = WallSurface(wall.length_mm / nv, wall.height_mm / nh, wall.thickness_mm)
                return evaluate_placement(
                    cell, robot, tool, placement, spacing_mm=spacing_mm
                ).reachable_fraction

            aufgabe = RasterAufgabe(
                frac_at=modul_frac_at,
                start=(min_v, min_h),
                cap=cap,
                kandidaten=kandidaten,
                bewerte=scorer.bewerte if scorer is not None else None,
                objective=objective,
                call_budget=call_budget,
                pruef_tuer=pruef_tuer,
                menu=option_menu(placement_levers=False),
            )
            if strategie is not None:
                strat: ZerlegungsStrategie = strategie
            elif scorer is not None:
                strat = BeamSuche()
            else:
                strat = KollisionsGetriebeneVerfeinerung()
            wahl = strat.waehle_raster(aufgabe)
            n_v, n_h = wahl.n_length, wahl.n_height
            refinement = wahl.provenienz
        else:
            n_v, n_h = _module_grid_counts(
                wall, robot, tool, spacing_mm, cap, placement, limits_,
                strategie,
            )
        cuts = _build_cuts(wall, n_v, n_h)
        sections: list[SectionPlan] = []
        order = 0
        for h_idx in range(n_h):  # unten → oben (= Montagereihenfolge, ADR-022)
            z0 = round(wall.height_mm * h_idx / n_h, 3)
            z1 = round(wall.height_mm * (h_idx + 1) / n_h, 3)
            for v_idx in range(n_v):  # links → rechts
                x0 = round(-wall.length_mm / 2.0 + wall.length_mm * v_idx / n_v, 3)
                x1 = round(-wall.length_mm / 2.0 + wall.length_mm * (v_idx + 1) / n_v, 3)
                order += 1
                # section_id-Schema bewusst zerlegungsart-neutral ("abschnitt-N"
                # historisch): ein Artwechsel behaelt die Schnittebenen und die
                # Slicing-Overrides je Teil (process_params.sections) — das geht
                # nur mit stabilen IDs (ADR-022 Punkt 5). Anzeige-Namen ("Modul 1")
                # sind Sache des Viewers, nie dieser Schluessel.
                section = Section(f"abschnitt-{order}", order, x0, x1, z0, z1)
                sections.append(
                    SectionPlan(section, replace(placement, option_id=f"platz-{order}"))
                )
        return DecompositionPlan(
            kind=kind,
            wall=wall,
            cuts=cuts,
            sections=tuple(sections),
            n_length=n_v,
            n_height=n_h,
            refinement=refinement,
        )

    wahl = _grid_counts(
        wall, robot, tool, spacing_mm, cap, workstation, stand_mode, strategie,
        pruef_tuer, call_budget, scorer, objective,
    )
    n_v, n_h = wahl.n_length, wahl.n_height

    # Platzierungssuche je **Hoehenreihe** (Issue #132): alle Zellen einer Reihe
    # sind gleich gross und liegen auf derselben echten Hoehenlage (z_offset =
    # z0 der Reihe) — eine Suche je Reihe genuegt (deterministisch); die Spalten
    # einer Reihe teilen die Platzierung, nur die option_id ist je Abschnitt
    # eigen. Die Aufstellhoehe des Ergebnisses ist absolut (Boden = Wandfuss);
    # fuer die unterste Reihe (z0 = 0) ist die Suche bit-identisch zur alten
    # Mini-Wand-Konvention (Regressionsanker). Obere Reihen koennen im
    # Boden-Modus ehrlich unerreichbar bleiben — Befund, kein Gate: geschnitten
    # wird trotzdem, `evaluate` faerbt rot.
    fallback_option = PlacementOption(
        "fallback", lateral_mm=0.0, standoff_mm=DEFAULT_STANDOFF_MM, stand_height_mm=0.0
    )
    row_options: list[PlacementOption] = []
    for h_idx in range(n_h):
        cell = WallSurface(
            wall.length_mm / n_v,
            wall.height_mm / n_h,
            wall.thickness_mm,
            z_offset_mm=round(wall.height_mm * h_idx / n_h, 3),
        )
        best = suggest(
            cell, robot, tool, workstation=workstation, stand_mode=stand_mode,
            n_best=1, spacing_mm=spacing_mm, collision_free=_reachability_only,
            config_axis=False,
        )
        row_option = best[0][0] if best else fallback_option
        # Kollisionsgetriebene Verfeinerung (Issue #165): den je Reihe gewaehlten
        # **Platzierungs-Hebel** (Delta auf die gesuchte Basis-Lage — dasselbe Delta,
        # das das Orakel bewertet hat) auf die Reihen-Platzierung anwenden. Der
        # IK-Hebel steckt in ``wahl.provenienz`` (das Plan-Modell traegt keine IK).
        if wahl.zellen_optionen is not None and h_idx < len(wahl.zellen_optionen):
            row_option = _apply_placement_delta(
                row_option, wahl.zellen_optionen[h_idx].placement_delta
            )
        row_options.append(row_option)

    cuts = _build_cuts(wall, n_v, n_h)

    sections: list[SectionPlan] = []
    order = 0
    for h_idx in range(n_h):  # unten → oben
        z0 = round(wall.height_mm * h_idx / n_h, 3)
        z1 = round(wall.height_mm * (h_idx + 1) / n_h, 3)
        for v_idx in range(n_v):  # links → rechts
            x0 = round(-wall.length_mm / 2.0 + wall.length_mm * v_idx / n_v, 3)
            x1 = round(-wall.length_mm / 2.0 + wall.length_mm * (v_idx + 1) / n_v, 3)
            order += 1
            section = Section(f"abschnitt-{order}", order, x0, x1, z0, z1)
            placement = replace(row_options[h_idx], option_id=f"platz-{order}")
            sections.append(SectionPlan(section, placement))

    return DecompositionPlan(
        kind=kind,
        wall=wall,
        cuts=cuts,
        sections=tuple(sections),
        n_length=n_v,
        n_height=n_h,
        refinement=wahl.provenienz,
    )


def _bounds_from_cuts(wall_extent: tuple[float, float], positions: list[float]) -> list[float]:
    """Baut sortierte Abschnittsgrenzen aus Wandaussenkanten + inneren Schnitten."""
    lo, hi = wall_extent
    inner = sorted({round(p, 3) for p in positions if lo < p < hi})
    return [lo, *inner, hi]


def _stagger_row_bounds(bounds: list[float], offset: float) -> list[float]:
    """Versetzt die *inneren* Grenzen einer Hoehenlage um den Fugen-Versatz.

    Nur die inneren vertikalen Schnitte wandern (die Wandaussenkanten bleiben
    fest); nach dem Versatz zu nah beieinander liegende oder ueber die
    Aussenkanten hinausgeschobene Grenzen werden auf einen Mindestabstand von
    1 mm zur Kante bzw. zueinander geklemmt — v1-Vereinfachung, damit kein
    Abschnitt der Breite 0 entsteht.
    """
    if offset == 0.0 or len(bounds) <= 2:
        return bounds
    lo, hi = bounds[0], bounds[-1]
    margin = 1.0
    shifted = sorted(
        {round(min(max(b + offset, lo + margin), hi - margin), 3) for b in bounds[1:-1]}
    )
    return [lo, *shifted, hi]


def from_cuts(
    wall: WallSurface,
    robot: RobotDef,
    tool: ToolDef,
    cuts: list[Cut],
    *,
    kind: str = "abschnitt",
    joint_offset_mm: float = 0.0,
    spacing_mm: float = SAMPLE_SPACING_MM,
    workstation: WorkstationDef | None = None,
    stand_mode: str = "floor",
) -> DecompositionPlan:
    """Baut einen Zerlegungsplan aus manuell gesetzten Schnittebenen (Issue #25).

    Anders als `propose` (das Raster automatisch aus dem Roboter-Arbeitsraum
    herleitet) uebernimmt diese Funktion die Schnittebenen so, wie der Nutzer
    sie im Viewer gesetzt hat (Drag/Zahlenfeld, Hinzufuegen/Entfernen) — die
    Zerlegung selbst ist damit ein **Plan-Eingang**, keine Berechnung. Fuer
    jeden entstehenden Abschnitt wird trotzdem automatisch eine Platzierung
    gesucht (`fgc.placement.suggest`, dieselbe Kinematik wie `propose`); ein
    per Override zugewiesener Stellplatz (`propose.apply_overrides`) ersetzt
    sie danach — die Ampel-Bewertung (`evaluate`) bleibt unveraendert Sache
    des Cores (ADR-007).

    ``workstation`` + ``stand_mode`` binden — wie bei `propose` — die automatische
    Platzierungssuche je Abschnitt an die reale Aufstell-Umgebung + den Aufstell-
    Toggle (Issue #81); die manuellen Schnittebenen selbst bleiben davon unberuehrt.
    Die Suche sieht jeden Abschnitt an seiner **echten Hoehenlage** und liefert
    die Aufstellhoehe **absolut ueber dem Boden** (Issue #132, wie `propose`).

    ``kind="modul"`` (Issue #90, ADR-022): die Schnittebenen bleiben derselbe
    zerlegungsart-neutrale Plan-Eingang, aber statt einer Platzierungssuche je
    Teil gilt die **eine feste Platzierung an der Workstation** (siehe
    ``propose``) — Obergrenzen verfeinern hier nichts (die Schnitte sind
    Nutzereingabe); ihr Befund entsteht in `fgc.decompose.limits`. Ohne
    Workstation wird „modul" mit einem freundlichen Hinweis abgelehnt.

    ``joint_offset_mm`` versetzt die vertikalen Schnitte jeder zweiten
    Hoehenlage (gestaffelte Stossfugen); 0.0 = kein Versatz. Cuts ausserhalb
    der Wandflaeche werden ignoriert, Duplikate zusammengefasst — deterministisch:
    gleiche Eingaben -> gleicher Plan.

    Wirft ``ValueError`` bei unbekannter Zerlegungsart oder Art „modul" ohne
    Workstation.
    """
    _check_kind(kind, workstation)
    module_placement: PlacementOption | None = None
    if kind == "modul":
        assert workstation is not None  # _check_kind garantiert das
        module_placement = _module_placement(workstation, wall.thickness_mm)

    half_len = wall.length_mm / 2.0
    z_bounds = _bounds_from_cuts(
        (0.0, wall.height_mm), [c.position_mm for c in cuts if c.orientation == "horizontal"]
    )
    x_bounds_base = _bounds_from_cuts(
        (-half_len, half_len), [c.position_mm for c in cuts if c.orientation == "vertical"]
    )

    sections: list[SectionPlan] = []
    order = 0
    for h_idx in range(len(z_bounds) - 1):
        z0, z1 = z_bounds[h_idx], z_bounds[h_idx + 1]
        # Fugen-Versatz: jede zweite Hoehenlage bekommt versetzte vertikale
        # Schnitte (gestaffelte Stossfugen, wie im Mauerwerk).
        row_offset = joint_offset_mm if (h_idx % 2 == 1) else 0.0
        x_bounds = _stagger_row_bounds(x_bounds_base, row_offset)
        for v_idx in range(len(x_bounds) - 1):
            x0, x1 = x_bounds[v_idx], x_bounds[v_idx + 1]
            order += 1
            # section_id-Schema zerlegungsart-neutral (Kommentar in `propose`):
            # stabile IDs halten Slicing-Overrides ueber den Artwechsel (ADR-022).
            section_id = f"abschnitt-{order}"
            section = Section(section_id, order, x0, x1, z0, z1)
            if module_placement is not None:
                # Art „modul": feste Workstation-Platzierung fuer jedes Teil —
                # keine Suche (ADR-022), nur eine eigene option_id je Teil.
                placement = replace(module_placement, option_id=f"platz-{section_id}")
                sections.append(SectionPlan(section, placement))
                continue
            surface = section.as_surface(wall.thickness_mm)
            best = suggest(
                surface, robot, tool, workstation=workstation, stand_mode=stand_mode,
                n_best=1, spacing_mm=spacing_mm, collision_free=_reachability_only,
                config_axis=False,
            )
            if best:
                opt, _score = best[0]
                placement = replace(opt, option_id=f"platz-{section_id}")
            else:
                placement = PlacementOption(
                    f"platz-{section_id}",
                    lateral_mm=0.0,
                    standoff_mm=DEFAULT_STANDOFF_MM,
                    stand_height_mm=0.0,
                )
            sections.append(SectionPlan(section, placement))

    # Effektive (gefilterte, sortierte) Basis-Schnitte vor dem Versatz — das ist
    # der Plan-Eingang, den der Druckjob traegt (ADR-016); der Versatz selbst ist
    # ein separater Parameter (`joint_offset_mm`), keine eigene Schnittebene.
    effective_cuts = tuple(
        [Cut("horizontal", z) for z in z_bounds[1:-1]]
        + [Cut("vertical", x) for x in x_bounds_base[1:-1]]
    )

    return DecompositionPlan(
        kind=kind,
        wall=wall,
        cuts=effective_cuts,
        sections=tuple(sections),
        n_length=len(x_bounds_base) - 1,
        n_height=len(z_bounds) - 1,
        joint_offset_mm=joint_offset_mm,
    )


def apply_overrides(
    plan: DecompositionPlan, overrides: dict[str, PlacementOption]
) -> DecompositionPlan:
    """Ersetzt je Abschnitt die Platzierung durch eine uebersteuerte (Issue #25).

    ``overrides`` bildet ``section_id -> PlacementOption`` ab (typischerweise
    eine bereits erfasste Aufstellmoeglichkeit aus der Platzierungsliste des
    Druckjobs, Issue #22). Abschnitte ohne passenden Eintrag behalten ihre
    automatisch gesuchte Platzierung unveraendert. Stale Referenzen (Abschnitt
    existiert nach einer Schnittplan-Aenderung nicht mehr) werden stillschweigend
    ignoriert — kein Gate, die Ueberpruefung passiert eine Ebene hoeher
    (`fgc.pipeline.actions.propose_decomposition` validiert die option_id gegen
    die bekannte Platzierungsliste).
    """
    if not overrides:
        return plan
    new_sections = tuple(
        SectionPlan(sp.section, overrides[sp.section.section_id])
        if sp.section.section_id in overrides
        else sp
        for sp in plan.sections
    )
    return replace(plan, sections=new_sections)
