"""Optimalvorschlag fuer die Roboterbasis (Platzierung, Modus 1 — Issue #23/#80).

``suggest(wand, roboter, endeffektor, workstation=…)`` erzeugt ein
deterministisches Raster von Basis-Positionen, bewertet jede Lage mit dem
bestehenden ``evaluate`` und liefert die besten Platzierungen (beste zuerst).

Seit Issue #80 (PRD B, Druckplan-Redesign) ist die Kandidatenmenge an die reale
Workstation gebunden:

- **Seitlich = fest die Abschnittsmitte** (``lateral_mm = 0``). Der Roboter steht
  zentral vor der Wand — keine seitliche Rasterung mehr.
- **Hoehe = aus dem realen Podesthoehen-Satz der Workstation** — der geordnete
  ``base_heights_mm`` (nicht hoehenverstellbar, inkl. 0) bzw. ein Raster ueber das
  ``height_range_mm``-Intervall (hoehenverstellbar). Die beste Hoehe gewinnt.
- **Abstand = optimierte Achse.** Raster ab ``safety_min_distance_mm`` (Workstation,
  Default 50) bis zur Reichweitengrenze (``robot.reach_mm``); Ziel ist die **beste
  Marge unter voller Erreichbarkeit** — so werden Singularitaets-
  warnungen aktiv wegoptimiert. Der Abstand faellt **nie unter** den
  Sicherheits-Mindestabstand.

Ohne Workstation (Altprojekt) faellt ``suggest`` sauber auf das bisherige
2D-Raster (seitlich × Hoehe bei fixem 700-mm-Abstand) zurueck — bestehende
placement-Routen/-UI bleiben unveraendert. Der Aufstell-Toggle (``stand_mode``,
Issue #81) gilt auch hier (Issue #100): ``'floor'`` klemmt das Hoehenraster auf
die Bodenhoehe ``[0]``.

Alle Hoehen-Kandidaten sind **absolute** Aufstellhoehen ueber dem Boden
(Boden = Wandfuss, Issue #132) — die realen Geraetehoehen der Workstation
(``base_heights_mm``/``height_range_mm``) sind genau solche absoluten Werte.
Traegt die bewertete Flaeche eine echte Hoehenlage (``WallSurface.z_offset_mm``,
z. B. ein Abschnitt der Reihe 2), rechnet ``evaluate`` Basis und IK-Ziele im
selben absoluten Hoehensystem.

``placement.evaluate`` bleibt die Bewertung — nur die Kandidatenmenge und das
Auswahlkriterium aendern sich. Sortierung (Issue #98): voller erreichbarer
Anteil, dann beste **Min-Marge** (``kinematic_margin`` — die schlechteste Stelle
entscheidet, nicht der Durchschnitt), dann beste ``mean_margin``, bei
Gleichstand die **zentrale Lage** (kleinstes ``|lateral|``). Vorher entschied
allein die Mean-Marge — die waehlte seitliche Lagen, deren ferne Ecke praktisch
an der Reichweitengrenze lag. Deterministisch: gleiche Eingaben → gleiche
Ausgabe (feste Raster, stabile Sortierung, ADR-004-Geist). Die Suche operiert
nur auf der schlanken ``WallSurface`` — kein IFC, keine Kollisionspruefung
(bewusste v1-Luecke, #23).

Einheiten strikt nach ADR-006: Millimeter, Radiant.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.kinematics import IkConfigFilter
from fgc.placement.evaluate import (
    SAMPLE_SPACING_MM,
    PlacementOption,
    PlacementScore,
    WallSurface,
    evaluate,
)
from fgc.placement.prior import PlacementPrior, placement_prior
from fgc.placement.reachmap import option_survives

if TYPE_CHECKING:
    from fgc.domain.workstation import WorkstationDef
    from fgc.kinematics.reachability import ReachabilityMap

#: Schrittweite des Hoehengitters (mm) — Fallback-Raster und Intervall-Rasterung
#: (``height_range_mm``) einer hoehenverstellbaren Workstation.
HEIGHT_STEP_MM = 500.0
#: Maximale Aufstellhoehe (mm) im Fallback-Raster — jenseits wird nicht gesucht.
MAX_STAND_HEIGHT_MM = 3000.0
#: Seitliche Rasterpositionen relativ zur Wandmitte (Bruchteile der Wandlaenge).
#: Nur noch Fallback (ohne Workstation): linkes Viertel, Mitte, rechtes Viertel.
_LATERAL_FRACS: tuple[float, ...] = (-0.25, 0.0, 0.25)
#: Standard-Abstand der Basis vor der Wandfront (mm) — Bedienersicherheitsabstand.
DEFAULT_STANDOFF_MM = 700.0
#: Schrittweite der optimierten Abstands-Achse (mm, Issue #80): fein genug, um das
#: Marge-Optimum zu treffen, grob genug, um die IK-Aufrufe beherrschbar zu halten.
DISTANCE_STEP_MM = 150.0
#: Aufstell-Zustaende (Issue #81): 'floor' klemmt die Podesthoehe auf 0 (Boden),
#: 'elevated' erlaubt den realen Podesthoehen-Satz der Workstation.
STAND_MODES: tuple[str, ...] = ("floor", "elevated")

#: Default-Sicherheitszone (GUI, mm) fuer die Prior-Tool-Aehnlichkeit (ADR-026
#: Punkt 4) — entspricht ``fgc.collision.check.DEFAULT_SAFETY_DISTANCE_MM`` (50 mm).
#: Keine eigene Prior-Konstante: die Tool-Toleranz haengt an genau dieser Zone.
DEFAULT_SAFETY_ZONE_MM = 50.0

# --- Prior-Lenkung (Issue #232, ADR-026 Punkt 3-4): Raster-Verdichtung ----------
#: Grobes Abstands-Raster **ausserhalb** des Prior-Fensters (mm) — groeber als das
#: neutrale ``DISTANCE_STEP_MM``, damit der Prior messbar weniger Kandidaten (und
#: damit ``evaluate``-Aufrufe) erzeugt. Innerhalb des Fensters bleibt ``DISTANCE_STEP_MM``
#: (fein). **Nie** kategorischer Ausschluss: das grobe Raster deckt den ganzen
#: Reichweitenbereich ab.
PRIOR_COARSE_DISTANCE_STEP_MM = 300.0
#: Halbe Fensterbreite (mm) um die gemessene Best-Standoff-Stuetzstelle, in der das
#: Abstands-Raster verdichtet wird.
PRIOR_STANDOFF_WINDOW_MM = 150.0
#: Feines Podesthoehen-Raster (mm) im Prior-Fenster einer **hoehenverstellbaren**
#: Workstation (verdichtet um die belegte Besthoehe ~300 mm); ausserhalb bleibt
#: ``HEIGHT_STEP_MM``. Diskrete ``base_heights_mm`` werden nie erfunden.
PRIOR_HEIGHT_FINE_STEP_MM = 150.0
#: Halbe Fensterbreite (mm) um die gemessene Best-Podesthoehe.
PRIOR_HEIGHT_WINDOW_MM = 200.0

#: Prädikat je Kandidat: kollisionsfrei? Der Optimalvorschlag baut es standardmäßig
#: (Issue #228) — als Default oder explizit übergeben (Alt-Zustand: ``lambda o: True``).
#: Extern übergeben ist es **konfig-agnostisch** (ein Argument, für alle Zweige gleich).
CollisionPredicate = Callable[[PlacementOption], bool]
#: Konfig-**bewusstes** Grob-Prädikat (Issue #233): ``(option, config_filter) ->
#: bool``. Der interne Default (:func:`default_collision_free`) prüft je IK-Zweig,
#: sodass die Kollision Teil der Konfig-Suchachse wird. ``config_filter=None`` = auto.
ConfigCollisionPredicate = Callable[..., bool]

# --- IK-Konfiguration als prior-gefuehrte Suchachse (Issue #233, ADR-026 Punkt 5) ---
#: Die 8 festen IK-Konfigurationszweige (Schulter/Ellbogen/Handgelenk je ``a``/``b``)
#: als 3-Buchstaben-Namen — die **volle Suchachse**. Reihenfolge wie im Prior-Gitter
#: (deterministischer Tie-Break: bei gleichem Score gewinnt der fruehere Name).
ALL_IK_CONFIGS: tuple[str, ...] = (
    "aaa", "aab", "aba", "abb", "baa", "bab", "bba", "bbb",
)
#: ``auto`` = die gelenkraum-naechste Wahl (kein Filter) — Teil jeder Prior-Shortlist.
AUTO_CONFIG = "auto"


def _config_filter(name: str) -> IkConfigFilter:
    """Buchstaben-Name (``"baa"`` / ``"auto"``) → harter IK-Konfig-Filter (Issue #233).

    ``"auto"`` ⇒ leerer Filter (kein Constraint, gelenkraum-naechste Wahl); sonst je
    Achse ``a``/``b`` (Bitschema ``opw.py`` ueber :meth:`IkConfigFilter.from_block`).
    """
    if name == AUTO_CONFIG:
        return IkConfigFilter()
    return IkConfigFilter.from_block(
        {"shoulder": name[0], "elbow": name[1], "wrist": name[2]}
    )


def _config_block(name: str) -> dict[str, str]:
    """Der persistierbare a/b-Block des gewaehlten Zweigs (``"auto"`` ⇒ leer)."""
    if name == AUTO_CONFIG:
        return {}
    return {"shoulder": name[0], "elbow": name[1], "wrist": name[2]}


def _config_axis(prior: PlacementPrior | None) -> tuple[tuple[str, ...], bool]:
    """Die IK-Konfig-Suchachse je Kandidat + ob Eskalation auf alle 8 moeglich ist.

    Prior **mit** Shortlist (gemessene Zelle) ⇒ nur ``(Prior-Konfig(s) + "auto")``,
    Eskalation moeglich (Issue #233, ADR-026 Punkt 5). Sonst — neutraler Prior oder
    Zelle ohne Best-Konfig (``angenommen-unmachbar``) — läuft **direkt** die volle
    Achse (alle 8), keine Eskalation noetig. Die Shortlist des Priors traegt ``auto``
    bereits selbst (:mod:`fgc.placement.prior`).
    """
    if prior is not None and prior.config_shortlist:
        return tuple(prior.config_shortlist), True
    return ALL_IK_CONFIGS, False


def _reach_key(score: PlacementScore) -> tuple[float, float, float]:
    """Reichweiten-Rang eines Scores: voller Anteil → Min-Marge → Mean-Marge."""
    return (
        score.reachable_fraction,
        score.kinematic_margin or 0.0,
        score.mean_margin or 0.0,
    )


def _config_key(score: PlacementScore) -> tuple[bool, float, float, float]:
    """Kandidaten-Rang **innerhalb** eines Kandidaten (Konfig-Wahl, Issue #233).

    Kollisionsfrei zuerst (die Studie: ``baa`` ist frei, wo ``auto`` in die Wand
    taucht), dann der Reichweiten-Rang. So gewinnt die Konfig, die den Kandidaten
    **machbar** macht — nicht die, die nur am meisten erreicht (ADR-026 Punkt 5).
    """
    free = True if score.collision is None else bool(score.collision["free"])
    return (free, *_reach_key(score))


def _is_feasible(score: PlacementScore) -> bool:
    """Machbar = etwas erreichbar **und** (falls geprueft) kollisionsfrei (Issue #233)."""
    if score.reachable_fraction <= 0.0:
        return False
    return score.collision is None or bool(score.collision["free"])


def collision_judgment(free: bool) -> dict[str, Any]:
    """Das explizite Machbarkeits-Feld eines Kandidaten (Issue #228, ADR-026 Punkt 1).

    ``free=True`` → ``status="clear"`` (grün), ``free=False`` → ``status="colliding"``
    (rot). Der Grob-Check (:func:`fgc.collision.coarse.path_collides`) urteilt binär —
    das gelbe Sicherheitsband der exakten Kollisionskontrolle (ADR-024) kennt er nicht.
    Ein **Befund, kein Gate**: das Urteil ordnet die Sortierung und wird sichtbares
    Score-Feld, gatet aber nichts (keine leeren Listen).
    """
    return {
        "free": bool(free),
        "status": "clear" if free else "colliding",
        "source": "coarse",
    }


def feasibility_finding(
    results: Iterable[tuple[PlacementOption, PlacementScore]],
) -> dict[str, Any]:
    """Gesamt-Befund „(kein) machbarer Kandidat" über eine Vorschlagsliste (Issue #228).

    Verdichtet die Einzel-Kollisionsurteile zum einen Befund, den die Vorschlags-API
    weiterreicht (US 3/17): ``checked`` (lief der Grob-Check überhaupt?), ``feasible``
    (gibt es mindestens einen kollisionsfreien Kandidaten?), plus die Zählung.
    ``checked=False`` (kein Urteil, z. B. fehlende Kollisionsgeometrie) ⇒
    ``feasible=None`` — ehrlich „unbekannt", nicht „unmachbar".
    """
    materialized = list(results)
    judged = [s.collision for _o, s in materialized if s.collision is not None]
    if not judged:
        return {
            "checked": False,
            "feasible": None,
            "n_feasible": 0,
            "n_total": len(materialized),
            "note": "Kollisions-Grob-Check nicht gelaufen (keine Geometrie) — "
            "Machbarkeit unbekannt.",
        }
    n_feasible = sum(1 for c in judged if c["free"])
    feasible = n_feasible > 0
    return {
        "checked": True,
        "feasible": feasible,
        "n_feasible": n_feasible,
        "n_total": len(judged),
        "note": (
            "Mindestens ein kollisionsfreier Vorschlag vorhanden."
            if feasible
            else "Kein machbarer Kandidat — alle Vorschläge kollidieren grob "
            "(Zerlegen statt weiter platzieren, ADR-026 Punkt 2)."
        ),
    }


def default_collision_free(
    robot: RobotDef,
    tool: ToolDef,
    wall: WallSurface,
    *,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
    robots_dir: Any = None,
) -> ConfigCollisionPredicate | None:
    """Baut das standardmäßige Grob-Kollisions-Prädikat des Vorschlags (Issue #228/#233).

    Lädt die Breitphasen-Geometrie des Roboters (#125) **fail-soft** und liefert ein
    ``(option, config_filter=None) -> bool`` (kollisionsfrei?), das der Grob-Check
    (:func:`fgc.collision.coarse.path_collides`) je Kandidat auswertet. Der optionale
    ``config_filter`` (Issue #233, ADR-026 Punkt 5) prueft die Kollision **je
    IK-Konfig-Zweig** — so wird der Grob-Befund Teil der Konfig-Suchachse (die Studie:
    ``baa`` bleibt frei, wo ``auto`` in die Wand taucht). ``None`` (Default) = auto,
    verhaltensgleich zum Aufruf ``predicate(opt)`` (#228).

    Fehlt die Geometrie (Altprojekt / Roboter ohne Artefakt) oder die Geo-Extras, gibt
    es ``None`` — dann läuft die Suche **ungeprüft** (byte-gleich zum reinen
    Reichweiten-Zustand). Ein Fehler je Kandidat wird ebenfalls fail-soft zu „frei"
    (nie zu Unrecht abwerten — Befund, kein Gate).

    Die Geo-Abhängigkeit ist bewusst lazy: ``suggest`` bleibt ohne Geo-Stack startbar,
    der Import fällt erst hier an.
    """
    try:
        from fgc.collision.coarse import path_collides
        from fgc.collision.robot_geometry import load_robot_collision_geometry

        geo = load_robot_collision_geometry(robot.name, robots_dir)
    except Exception:
        return None

    def free(option: PlacementOption, config_filter: IkConfigFilter | None = None) -> bool:
        try:
            return not path_collides(
                wall, robot, tool, option, geo,
                lead_rad=lead_rad, kipp_rad=kipp_rad, config_filter=config_filter,
            )
        except Exception:
            return True

    return free


def _fallback_grid(
    wall_length_mm: float, standoff_mm: float, stand_mode: str = "elevated"
) -> list[PlacementOption]:
    """Bisheriges 2D-Raster (seitlich × Hoehe bei fixem Abstand) — Altprojekt-Fallback.

    Der Aufstell-Toggle (Issue #81) gilt auch ohne Workstation (Issue #100):
    ``stand_mode == 'floor'`` klemmt das Hoehenraster auf die Bodenhoehe ``[0]``
    — vorher suchte der Fallback stets 0 … MAX_STAND_HEIGHT_MM und stellte den
    Roboter trotz Boden-Modus aufs Podest.

    Reihenfolge: Hoehe aussen, seitlich innen (links → mitte → rechts) — damit
    option_id deterministisch den Raster-Index kodiert und bei gleichen
    Eingaben gleich bleibt.
    """
    if stand_mode == "floor":
        heights = [0.0]
    else:
        n_heights = int(MAX_STAND_HEIGHT_MM / HEIGHT_STEP_MM) + 1
        heights = [i * HEIGHT_STEP_MM for i in range(n_heights)]
    counter = 0
    options: list[PlacementOption] = []
    for h in heights:
        for frac in _LATERAL_FRACS:
            counter += 1
            options.append(
                PlacementOption(
                    option_id=f"vorschlag-grid-{counter}",
                    lateral_mm=round(frac * wall_length_mm, 1),
                    standoff_mm=standoff_mm,
                    stand_height_mm=h,
                )
            )
    return options


def _raster(lo: float, hi: float, step: float) -> list[float]:
    """Deterministisches, aufsteigendes Raster [lo, hi] mit Schrittweite ``step``.

    Startet strikt bei ``lo`` und enthaelt immer den Endpunkt ``hi`` (auch wenn der
    letzte Schritt kuerzer ist). Bei ``hi <= lo`` genau ``[lo]``.
    """
    if hi <= lo:
        return [round(lo, 1)]
    values: list[float] = []
    v = lo
    while v < hi:
        values.append(round(v, 1))
        v += step
    values.append(round(hi, 1))
    return values


def _densified_raster(
    lo: float,
    hi: float,
    focus: float,
    window: float,
    coarse_step: float,
    fine_step: float,
) -> list[float]:
    """Prior-verdichtetes Raster [lo, hi] (Issue #232, ADR-026 Punkt 3-4).

    **Fein** (``fine_step``) im Fenster ``[focus-window, focus+window]`` (geklemmt),
    **grob** (``coarse_step``) ueber den ganzen Bereich — der Prior lenkt, schliesst
    aber **nie** kategorisch aus: das grobe Grundraster deckt [lo, hi] lueckenlos ab,
    auch weit ausserhalb des Fensters bleiben Kandidaten (fail-soft). Endpunkte und
    die Fokus-Stuetzstelle selbst sind immer enthalten; Ergebnis aufsteigend, dedupt.
    """
    if hi <= lo:
        return [round(lo, 1)]
    values: set[float] = set()
    v = lo
    while v < hi:
        values.add(round(v, 1))
        v += coarse_step
    values.add(round(hi, 1))
    w_lo = max(lo, focus - window)
    w_hi = min(hi, focus + window)
    if w_hi >= w_lo:
        v = w_lo
        while v < w_hi:
            values.add(round(v, 1))
            v += fine_step
        values.add(round(w_hi, 1))
    values.add(round(min(max(focus, lo), hi), 1))  # die Best-Stuetzstelle selbst
    return sorted(values)


def _standoff_axis(
    lo: float, hi: float, prior: PlacementPrior | None
) -> list[float]:
    """Abstands-Achse: prior-verdichtet um ``standoff_focus_mm``, sonst neutral (#228).

    Neutral (kein/​``angenommen-unmachbar``-Prior ohne Fokus) ⇒ das unveraenderte
    gleichmaessige ``DISTANCE_STEP_MM``-Raster (verhaltensgleich zu #228).
    """
    if prior is not None and not prior.is_neutral and prior.standoff_focus_mm is not None:
        return _densified_raster(
            lo, hi, prior.standoff_focus_mm, PRIOR_STANDOFF_WINDOW_MM,
            PRIOR_COARSE_DISTANCE_STEP_MM, DISTANCE_STEP_MM,
        )
    return _raster(lo, hi, DISTANCE_STEP_MM)


def _workstation_heights(
    workstation: WorkstationDef,
    stand_mode: str = "elevated",
    prior: PlacementPrior | None = None,
) -> list[float]:
    """Podesthoehen-Satz der Workstation als Hoehen-Kandidaten (Issue #80/#81).

    Der Aufstell-Toggle (Issue #81) begrenzt den Satz: ``stand_mode == 'floor'``
    klemmt die Kandidatenmenge auf die Bodenhoehe ``[0.0]`` — der Roboter steht auf
    dem Boden, die vertikale Reichweite ist entsprechend begrenzt. ``'elevated'``
    erlaubt die realen Podesthoehen:

    - Hoehenverstellbar → Raster ueber das ``height_range_mm``-Intervall (Schrittweite
      ``HEIGHT_STEP_MM``, Endpunkte inklusive).
    - Sonst → der geordnete diskrete ``base_heights_mm``-Satz (inkl. Bodenhoehe 0).

    Die Domaene garantiert je nach ``height_adjustable`` genau eines der beiden
    Felder (Branch-Regel, #72).
    """
    if stand_mode == "floor":
        return [0.0]
    if workstation.height_adjustable:
        lo, hi = workstation.height_range_mm  # type: ignore[misc]
        # Prior-Verdichtung um die belegte Besthoehe (~300 mm), sofern die
        # Workstation den Bereich hergibt (Issue #232, ADR-026 Punkt 3). Diskrete
        # ``base_heights_mm`` unten werden nie erfunden — der Satz bleibt neutral.
        if (
            prior is not None
            and not prior.is_neutral
            and prior.base_height_focus_mm is not None
        ):
            return _densified_raster(
                float(lo), float(hi), prior.base_height_focus_mm,
                PRIOR_HEIGHT_WINDOW_MM, HEIGHT_STEP_MM, PRIOR_HEIGHT_FINE_STEP_MM,
            )
        return _raster(float(lo), float(hi), HEIGHT_STEP_MM)
    return [round(float(h), 1) for h in workstation.base_heights_mm]


def _workstation_grid(
    workstation: WorkstationDef,
    robot: RobotDef,
    stand_mode: str = "elevated",
    prior: PlacementPrior | None = None,
) -> list[PlacementOption]:
    """Kandidatenmenge fuer eine gewaehlte Workstation (Issue #80/#81/#232).

    Seitlich fest zentral (``lateral_mm = 0``), Hoehe aus dem — vom Aufstell-Toggle
    (``stand_mode``, #81) begrenzten — Podesthoehen-Satz, Abstand als optimierte Achse
    ab ``safety_min_distance_mm`` (nie darunter) bis zur Reichweitengrenze
    ``robot.reach_mm``. Reihenfolge: Hoehe aussen, Abstand innen — deterministisch,
    damit die option_id den Raster-Index stabil kodiert.

    Ein anwendbarer ``prior`` (Issue #232, ADR-026 Punkt 3) **verdichtet** Abstands-
    und (bei hoehenverstellbarer Workstation) Podesthoehen-Raster um die gemessenen
    Best-Stuetzstellen — grober ausserhalb, aber nie kategorischer Ausschluss. Ohne
    anwendbaren Prior bleibt die Kandidatenmenge verhaltensgleich zu #228.
    """
    heights = _workstation_heights(workstation, stand_mode, prior)
    distances = _standoff_axis(
        workstation.safety_min_distance_mm, float(robot.reach_mm), prior
    )
    counter = 0
    options: list[PlacementOption] = []
    for h in heights:
        for d in distances:
            counter += 1
            options.append(
                PlacementOption(
                    option_id=f"vorschlag-grid-{counter}",
                    lateral_mm=0.0,  # zentral = Abschnittsmitte (Issue #80)
                    standoff_mm=d,
                    stand_height_mm=h,
                )
            )
    return options


def suggest(
    wall: WallSurface,
    robot: RobotDef,
    tool: ToolDef,
    *,
    workstation: WorkstationDef | None = None,
    stand_mode: str = "elevated",
    standoff_mm: float = DEFAULT_STANDOFF_MM,
    n_best: int = 3,
    spacing_mm: float = SAMPLE_SPACING_MM,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
    collision_free: CollisionPredicate | None = None,
    reach_map: ReachabilityMap | None = None,
    prior: PlacementPrior | None = None,
    safety_distance_mm: float = DEFAULT_SAFETY_ZONE_MM,
    config_axis: bool = True,
    robots_dir: Any = None,
) -> list[tuple[PlacementOption, PlacementScore]]:
    """Sucht die besten Basis-Lagen fuer eine Wand (Optimalvorschlag, Modus 1).

    **Mit Workstation** (Issue #80): seitlich fest zentral (Abschnittsmitte), Hoehe
    aus dem realen Podesthoehen-Satz (``base_heights_mm`` bzw. ``height_range_mm``),
    begrenzt durch den Aufstell-Toggle ``stand_mode`` (Issue #81: ``'floor'`` klemmt
    die Hoehe auf 0, ``'elevated'`` erlaubt den vollen Satz), Abstand als optimierte
    Achse ab ``safety_min_distance_mm`` (nie darunter) bis zur Reichweitengrenze.
    **Ohne Workstation** (Altprojekt): das bisherige 2D-Raster (seitlich × Hoehe
    bei fixem ``standoff_mm``) — bestehende placement-Routen/-UI bleiben
    unveraendert; ``stand_mode`` gilt auch hier (Issue #100: ``'floor'`` → nur
    Bodenhoehe).

    Jede Lage wird mit ``evaluate`` bewertet (erreichbarer Wandanteil + kinematische
    Marge). Auswahlkriterium/Sortierung (Issue #98): ``reachable_fraction``
    (primaer), dann ``kinematic_margin`` (Min-Marge — die schlechteste Stelle
    entscheidet), dann ``mean_margin``, bei Gleichstand die zentrale Lage
    (kleinstes ``|lateral_mm|``). Der beste Vorschlag hat also den vollen
    erreichbaren Anteil bei maximal robuster Worst-Case-Marge (Singularitaeten
    und Reichweiten-Grenzfaelle aktiv wegoptimiert). Deterministisch: feste
    Raster + stabile Sortierung → gleiche Eingaben liefern gleiche Ausgabe.
    Einheiten: mm, rad (ADR-006).

    **Machbarkeit statt Erreichbarkeit — Grob-Check default-an (Issue #228, ADR-026).**
    Der Kollisions-Grob-Check (#131, :func:`fgc.collision.coarse.path_collides`) läuft
    **standardmäßig** als zweiter **Vorfilter vor** der teuren ``evaluate``-Schleife
    (Muster Reichweitenkarte #214): kollidierende Kandidaten werden gar nicht erst
    bewertet, nur die kollisionsfreien Überlebenden. **Fail-soft** wie #214: streicht
    der Filter *alle* Kandidaten, wird das volle Raster bewertet und der
    Unmachbarkeits-Befund gemeldet (nie leere Liste, nie Fehler). Das Kollisionsurteil
    bleibt **vorderster Sortierschlüssel** *und* wird explizites Feld
    (``PlacementScore.collision``, „Befund, kein Gate").

    ``collision_free`` steuert das Prädikat je Kandidat: ``None`` (Default) baut es
    intern aus der Roboter-Geometrie (:func:`default_collision_free`, fail-soft — ohne
    Geometrie läuft die Suche ungeprüft, byte-gleich zum reinen Reichweiten-Zustand).
    Ein explizit übergebenes Prädikat gewinnt (Test-Injektion, Vorbau in der Pipeline).
    Der **Alt-Zustand** (reine Erreichbarkeits-Optimierung, ADR-026 Punkt 6 / US 15)
    ist ohne Legacy-Schalter explizit konstruierbar: ``collision_free=lambda o: True``
    (alles frei ⇒ kein Vorfilter, konstanter Schlüssel, #98-Sortierung bit-identisch).

    **Reichweitenkarte als Vorfilter (Issue #214, ADR-007/#164).** ``reach_map`` ist
    die binaere Karte (#210): gesetzt, streicht sie **vor** der teuren ``evaluate``-
    Schleife die laut Karte aussichtslosen Kandidaten (nichts erreichbar) aus dem
    Raster — nur die Ueberlebenden werden simuliert (US 5). Die Karte **filtert,
    urteilt nie**: das Ranking bleibt das IK-Urteil der ``evaluate``-Bewertung.
    Lenient und fail-soft: nur Kandidaten mit Karten-Schaetzung 0 fallen weg (nichts
    Erreichbares wird weggefiltert — die Karte hat am Raster keine falschen
    Negative); wuerde der Filter **alle** streichen, greift das volle Raster (kein
    Verhungern). ``None`` (Default) = kein Filter, byte-gleich zu heute (US 12).

    **Prior lenkt die Suche (Issue #232, ADR-026 Punkt 3-4).** ``prior`` (default
    ``None`` ⇒ aus ``(robot, tool, Modulmasse, safety_distance_mm)`` geladen,
    fail-soft) **verdichtet** — bei gewaehlter Workstation — das Abstands- und (nur
    hoehenverstellbar) das Podesthoehen-Raster um die gemessenen Best-Stuetzstellen:
    feiner im Prior-Fenster, groeber ausserhalb, aber **nie** kategorischer
    Ausschluss (auch weit ausserhalb bleiben Kandidaten). So braucht ein passender
    Prior **messbar weniger** ``evaluate``-Aufrufe bei gleichem oder besserem Sieger.
    Der Prior gilt nur fuer ein hinreichend aehnliches Tool (‖Δ TCP‖ **und** Δ Huellmass
    ≤ ``safety_distance_mm`` = GUI-Sicherheitszone); fremder Roboter, unaehnliches oder
    huellmass-loses Tool, fehlende Zelle ⇒ neutraler Prior ⇒ Suchverhalten wie #228.
    Eine ``angenommen-unmachbar``-Zelle liefert eine neutral-breite Suche (die
    Unmachbarkeits-Erwartung ist reine Info, **nie** ein Gate). Der Prior **lenkt,
    urteilt nie** — ein falscher Prior kostet Suchzeit, nie Korrektheit.

    **IK-Konfiguration als prior-gefuehrte Suchachse (Issue #233, ADR-026 Punkt 5).**
    Je Kandidat wird der IK-Konfig-Zweig (Schulter/Ellbogen/Handgelenk, 8 Zweige +
    ``auto``) **mitgesucht**: mit anwendbarem Prior nur die Shortlist der passenden
    W×T-Zelle plus ``auto`` (``config_shortlist``, ueber ``evaluate``-``config_filter``,
    #129/#200), sonst direkt die volle Achse (alle 8). Gewaehlt wird der **machbar
    machende** Zweig (kollisionsfrei zuerst, dann Reichweite — der Grob-Check laeuft
    beim Default konfig-bewusst je Zweig, sodass ``baa`` gewinnt, wo ``auto`` in die
    Wand taucht). Findet die Shortlist **keinen** machbaren Kandidaten, eskaliert die
    Achse **einmalig** auf alle 8. Der gewaehlte Zweig steht als a/b-Block in
    ``PlacementScore.ik_config`` — nach aussen sichtbar, damit Bewertung, Simulation
    und Druck **dieselbe** Konfiguration fahren. Nie hartkodiert: der Sieger kommt aus
    Prior/Suche und verschiebt sich mit Wand und Setup. ``config_axis=False`` schaltet
    die Achse ab (nur ``auto``, kein ``ik_config``-Feld) — der Regressionsanker fuer
    Aufrufer, die die Konfig **nicht** mitsuchen (Zerlegungs-Platzierungssuche
    ``fgc.decompose.propose``): Verhalten und Score bit-gleich zu vor #233.

    Wirft ``ValueError``, wenn die Roboterdefinition keine Kinematik-Parameter
    traegt (ohne FK/IK keine Erreichbarkeit rechenbar).
    """
    # Prior-Lenkung (Issue #232, ADR-026 Punkt 3-4): default-an, fail-soft. ``None``
    # ⇒ aus (Roboter, Tool, Modulmasse, GUI-Sicherheitszone) laden — jeder Fehlfall
    # (kein Artefakt, fremder Roboter, unaehnliches/fehlendes Huellmass-Tool) liefert
    # den neutralen Prior (Suche verhaltensgleich zu #228). Der Prior **lenkt** nur
    # das Raster (verdichtet um die Best-Stuetzstellen), **urteilt nie** — geurteilt
    # wird weiter vom Grob-Check + ``evaluate`` auf der echten Geometrie. Ein explizit
    # uebergebener Prior (Test-Injektion) gewinnt und umgeht das Laden.
    if prior is None:
        prior = placement_prior(
            robot.name, tool, wall.length_mm, wall.thickness_mm, safety_distance_mm,
            module_height_mm=wall.height_mm,
        )
    if workstation is None:
        grid = _fallback_grid(wall.length_mm, standoff_mm, stand_mode)
    else:
        grid = _workstation_grid(workstation, robot, stand_mode, prior)
    # Vorfilter 1 (Issue #214): laut Reichweitenkarte aussichtslose Kandidaten gar
    # nicht erst simulieren. Fail-soft — ein leerer Filter darf nicht alle
    # Kandidaten verhungern lassen.
    if reach_map is not None:
        survivors = [
            opt for opt in grid
            if option_survives(
                reach_map, wall, tool, opt,
                spacing_mm=spacing_mm, lead_rad=lead_rad, kipp_rad=kipp_rad,
            )
        ]
        if survivors:
            grid = survivors

    # Grob-Check je Kandidat (Issue #228/#233): ein extern uebergebenes ``collision_free``
    # ist **konfig-agnostisch** (ein Argument, fuer alle Zweige gleich — Alt-Zustand /
    # Test-Injektion). Ohne Uebergabe baut ``suggest`` das **konfig-bewusste** Prädikat
    # aus der Roboter-Geometrie (fail-soft): so wird der Kollisions-Befund Teil der
    # IK-Konfig-Suchachse (ADR-026 Punkt 5). Bleibt es ``None`` (keine Geometrie), läuft
    # die Suche ungeprüft (kein Kollisionsfeld, byte-gleich zu #214).
    external = collision_free
    config_judge: ConfigCollisionPredicate | None = None
    if external is None:
        config_judge = default_collision_free(
            robot, tool, wall, lead_rad=lead_rad, kipp_rad=kipp_rad,
            robots_dir=robots_dir,
        )

    def _judge(opt: PlacementOption, name: str) -> bool | None:
        """Kollisionsfrei-Urteil je (Kandidat, IK-Konfig) — ``None`` = nicht geprueft."""
        if external is not None:
            return bool(external(opt))  # konfig-agnostisch (extern/Test)
        if config_judge is not None:
            return bool(config_judge(opt, _config_filter(name)))
        return None

    # IK-Konfiguration als prior-gefuehrte Suchachse (Issue #233, ADR-026 Punkt 5): je
    # Kandidat nur die Shortlist-Konfigs (+auto) bewerten und den **machbar machenden**
    # Zweig waehlen (kollisionsfrei zuerst, dann Reichweite — die Studie: ``baa`` schlaegt
    # ``auto``). Findet die Shortlist nichts Machbares, eskaliert die Achse **einmalig**
    # auf alle 8; ohne anwendbaren Prior laeuft die volle Achse direkt. ``config_axis=False``
    # schaltet die Achse ab (nur ``auto``, kein ``ik_config``-Feld) — der Regressionsanker
    # fuer Aufrufer, die die Konfig nicht mitsuchen wollen (Zerlegungs-Platzierungssuche).
    if config_axis:
        axis, can_escalate = _config_axis(prior)
    else:
        axis, can_escalate = (AUTO_CONFIG,), False

    def _evaluate_axis(
        config_names: tuple[str, ...],
    ) -> list[tuple[PlacementOption, PlacementScore]]:
        out: list[tuple[PlacementOption, PlacementScore]] = []
        for opt in grid:
            best: tuple[PlacementOption, PlacementScore] | None = None
            for name in config_names:
                score = evaluate(
                    wall, robot, tool, opt, spacing_mm=spacing_mm,
                    lead_rad=lead_rad, kipp_rad=kipp_rad,
                    config_filter=_config_filter(name),
                )
                # Ohne Achse (nur ``auto``) kein ``ik_config``-Feld — byte-gleich zu vor #233.
                if config_axis:
                    score = dataclasses.replace(score, ik_config=_config_block(name))
                free = _judge(opt, name)
                if free is not None:
                    score = dataclasses.replace(score, collision=collision_judgment(free))
                if best is None or _config_key(score) > _config_key(best[1]):
                    best = (opt, score)
            if best is not None:
                out.append(best)
        return out

    candidates = _evaluate_axis(axis)
    # Eskalation (Issue #233): findet die Shortlist keinen machbaren Kandidaten,
    # einmal die volle Achse. Ohne Prior (can_escalate=False) lief sie schon.
    if can_escalate and not any(_is_feasible(s) for _o, s in candidates):
        candidates = _evaluate_axis(ALL_IK_CONFIGS)

    # Vorfilter (Issue #228, ADR-026 Punkt 1) nach der Achse: ein Kandidat, dessen
    # **bester** Zweig immer noch kollidiert (kein Zweig rettet ihn), faellt aus der
    # Liste — kollisionsfreie zuerst. Fail-soft: kollidieren **alle** Kandidaten in
    # jedem Zweig, bleibt das volle Feld (Unmachbarkeits-Befund, nie leere Liste).
    def _free_of(score: PlacementScore) -> bool:
        return True if score.collision is None else bool(score.collision["free"])

    free_candidates = [c for c in candidates if _free_of(c[1])]
    if free_candidates:
        candidates = free_candidates

    # Sortierung (Issue #98 + #131 + #228): kollisionsfrei (vorderster Schlüssel) →
    # voller Anteil → beste Min-Marge (Worst-Case zaehlt) → beste Mean-Marge → zentrale
    # Lage. Nach dem Vorfilter ist der Kollisionsschlüssel unter den Überlebenden
    # konstant (alle frei bzw., im Fail-soft-Fall, alle kollidierend).
    candidates.sort(
        key=lambda item: (
            _free_of(item[1]),
            item[1].reachable_fraction,
            item[1].kinematic_margin or 0.0,
            item[1].mean_margin or 0.0,
            -abs(item[0].lateral_mm),
        ),
        reverse=True,
    )
    return candidates[:n_best]
