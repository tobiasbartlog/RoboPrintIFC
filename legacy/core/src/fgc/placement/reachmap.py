"""Reichweitenkarte als **Vorfilter** der Platzierung (PRD #183 AP 2, Issue #214).

Die eine Adapter-Naht zwischen der binären 4D-Karte (:mod:`fgc.kinematics.reachability`,
Issue #210) und den drei Platzierungs-Aufrufern — **ein Parameter (die Karte), drei
Aufrufer** (Bewertungsmodus, Optimalvorschlag, Kollisions-Advisor), analog zum
``config_filter``-Muster (#200/#201). Die Karte liegt fachlich in ``kinematics``
(kennt nur IK), die Wand-Geometrie in ``placement`` (``flange_targets``, #201-Seam) —
dieses Modul verheiratet beide, **ohne** die Wand→Basis-Kette (``t_wall_base``) oder
die ``nozzle_quat``-Konvention zu duplizieren.

**Ehrlichkeitsregel (ADR-007/#164): die Karte filtert, urteilt nie.** Jede Funktion
hier liefert eine *Schätzung* bzw. ein *Vorfilter-Prädikat* — „geprüft frei" entsteht
ausschließlich in der Prüf-Tür. Ohne Karte gibt es diese Funktionen schlicht nicht zu
rufen; die Aufrufer bleiben dann byte-gleich (fail-soft, US 12).

Zwei Abfragerichtungen (beide über denselben #201-Seam):

- **Vorwärts** (Bewertung/Optimalvorschlag): ``flange_targets`` liefert die Ziele in
  **Basiskoordinaten** → :func:`option_reach_estimate` / :func:`option_survives`.
- **Invers** (Standplatz je Höhenreihe, US 5/6): dieselben Ziele über
  :func:`fgc.kinematics.reachability.frames_in_wall` ins **Wandsystem** gebracht →
  :func:`standplatz_fuer_reihe` = punktweises Minimum über die Bahnposen der Reihe.

Einheiten strikt nach ADR-006: Millimeter, Radiant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fgc.domain.models import Frame
from fgc.domain.tool import ToolDef
from fgc.kinematics.reachability import frames_in_wall
from fgc.placement.evaluate import (
    SAMPLE_SPACING_MM,
    PlacementOption,
    WallSurface,
    flange_targets,
    nozzle_rotation,
)

if TYPE_CHECKING:
    import numpy as np

    from fgc.kinematics.reachability import ReachabilityMap


# ---------------------------------------------------------------------------
# Vorwärts: erreichbarer Wandanteil als Karten-Schätzung (US 7) + Vorfilter (US 5)
# ---------------------------------------------------------------------------


def option_reach_estimate(
    reach_map: ReachabilityMap,
    wall: WallSurface,
    tool: ToolDef,
    option: PlacementOption,
    *,
    spacing_mm: float = SAMPLE_SPACING_MM,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
) -> float:
    """Karten-Schätzung des erreichbaren Wandanteils einer Aufstellmöglichkeit.

    Baut dieselben Flansch-Ziele wie :func:`fgc.placement.evaluate.evaluate`
    (geteilter #201-Seam, **kein** IK-Aufruf) und lässt die Karte die Vorwärts-
    abfrage in Mikrosekunden beantworten. Das Ergebnis ist eine **Schätzung**
    (Rasterauflösung der Karte), kein Prüf-Tür-Urteil — genau der Wert, den der
    Bewertungsmodus als gekennzeichnete Schätzung anzeigt (US 7).
    """
    r_nozzle = nozzle_rotation(lead_rad, kipp_rad)
    ft = flange_targets(wall, tool, option, spacing_mm, r_nozzle)
    return float(reach_map.reachable_fraction(ft.frames))


def option_survives(
    reach_map: ReachabilityMap,
    wall: WallSurface,
    tool: ToolDef,
    option: PlacementOption,
    *,
    min_fraction: float = 0.0,
    spacing_mm: float = SAMPLE_SPACING_MM,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
) -> bool:
    """Vorfilter-Prädikat: übersteht die Aufstellmöglichkeit den Kartenfilter?

    True, wenn die Karten-Schätzung über ``min_fraction`` liegt — d. h. die Karte
    hält mindestens einen relevanten Anteil der Wand für erreichbar. Default
    ``min_fraction = 0.0`` filtert **nur** die aussichtslosen Kandidaten (Karte:
    nichts erreichbar) heraus; nichts Erreichbares wird weggefiltert (die Karte
    hat am Raster keine falschen Negative, #210) — der teure ``evaluate`` bleibt so
    der Richter, die Karte spart nur die hoffnungslosen Simulationen (US 5).
    """
    return (
        option_reach_estimate(
            reach_map, wall, tool, option,
            spacing_mm=spacing_mm, lead_rad=lead_rad, kipp_rad=kipp_rad,
        )
        > min_fraction
    )


# ---------------------------------------------------------------------------
# Invers: Standplatz je Höhenreihe = Minimum über die Bahnposen (US 5/6)
# ---------------------------------------------------------------------------


def wall_row_frames(
    wall: WallSurface,
    tool: ToolDef,
    *,
    row_z_mm: float,
    spacing_mm: float = SAMPLE_SPACING_MM,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
) -> list[Frame]:
    """Flansch-Zielposen **einer** Höhenreihe in **Wandkoordinaten** (US 6).

    Die Posen einer Reihe sind basis-unabhängig (wand-feste Druckziele): gebaut über
    ``flange_targets`` (Höhe 0 bei ``row_z_mm``) und mit
    :func:`fgc.kinematics.reachability.frames_in_wall` über die **eine**
    ``t_wall_base``-Kette zurück ins Wandsystem gebracht — dieselben Ziele wie die
    Vorwärtsbewertung, nur basis-frei (kein Duplikat des #201-Seams). Die
    Dummy-Basis fällt bei der Rücktransformation exakt wieder heraus.
    """
    row = WallSurface(
        length_mm=wall.length_mm,
        height_mm=0.0,
        thickness_mm=wall.thickness_mm,
        z_offset_mm=row_z_mm,
    )
    r_nozzle = nozzle_rotation(lead_rad, kipp_rad)
    dummy = PlacementOption(
        option_id="_row", lateral_mm=0.0, standoff_mm=0.0, stand_height_mm=0.0
    )
    ft = flange_targets(row, tool, dummy, spacing_mm, r_nozzle)
    wall_frames = frames_in_wall(ft.frames, ft.t_wall_base)
    # Höhe 0 ⇒ n_height == 2 identische Reihen; genau eine genügt (Minimum ist idempotent).
    return wall_frames[: ft.n_length]


def standplatz_fuer_reihe(
    reach_map: ReachabilityMap,
    wall: WallSurface,
    tool: ToolDef,
    base_xy_mm: Any,
    base_z_mm: float,
    *,
    row_z_mm: float,
    spacing_mm: float = SAMPLE_SPACING_MM,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
) -> np.ndarray:
    """Standplatz-Kandidaten je Höhenreihe: Basen, die **alle** Posen der Reihe erreichen.

    Punktweises **Minimum über die Bahnposen** der Reihe (:meth:`ReachabilityMap.
    min_over_poses`, Vahrenkamp Gl. 3 / RM4D IV-D): Rückgabe ist eine bool-Maske über
    ``base_xy_mm`` (``(N, 2)``, x/y im Wandsystem, ``base_z_mm`` = Aufstellhöhe absolut
    über dem Boden, Issue #132) — True heißt, diese Basis deckt garantiert die ganze
    Reihe (kein Umsetzen mitten in der Reihe, US 6). Rein Karten-schnell (< 1 s),
    vektorisiert; **Schätzung/Vorfilter**, kein Prüf-Tür-Urteil.
    """
    frames = wall_row_frames(
        wall, tool, row_z_mm=row_z_mm,
        spacing_mm=spacing_mm, lead_rad=lead_rad, kipp_rad=kipp_rad,
    )
    return reach_map.min_over_poses(frames, base_xy_mm, base_z_mm)
