"""Platzierungs-Grob-Check: kollidiert eine Aufstellung *grob*? (ADR-024, PRD #124, Issue #131).

Die **Ausbaustufe „Grob-Check"** der Kollisionskontrolle (ADR-024 Konsequenz):
der Optimalvorschlag der Platzierung (:func:`fgc.placement.suggest.suggest`) soll
keine Aufstellungen liefern, die erst in der Simulation durchfallen. Statt der
teuren, exakten Mesh-Distanz je Bahnpunkt (die :mod:`fgc.collision.check`
urteilt) genügt hier ein **billiger** Befund je Kandidat:

- **wenige Stichproben-Posen** — ein grobes Raster über die Wandfläche (Ecken +
  Mitte statt des feinen ``evaluate``-Rasters), IK über die bestehende
  Konfigurationswahl,
- **Breitphasen-Geometrie genügt** — die konvexe Hülle je Glied (#125,
  ``broadphase_hull``), keine VHACD-Urteilsgeometrie, kein python-fcl,
- **AABB-Test gegen das Wandvolumen** — taucht ein **Armglied** (Ellbogen/
  Unterarm) hinter die Druckebene (``y < 0``) in den Wandkörper, ist das der
  Fehler aus dem Auslöser-Foto (M1013-Ellbogen durch die Wand). Basis, Handgelenk
  und Flansch/Endeffektor bleiben außen — sie arbeiten prozessbedingt an der
  Wandfront ``y ≈ 0`` und würden sonst chronisch fehlwarnen (ADR-024 Kontext 2).

**Befund, kein Gate.** Der Grob-Check *sortiert* nur: ein Kandidat, dessen Bahn
grob kollidiert, rutscht im Ranking hinter die kollisionsfreien (siehe
``suggest``); die Platzierungs-Ampel behält ihre Bedeutung. Kollidiert **nichts**,
bleibt die #98-Sortierung bit-identisch (der Grob-Check fügt nur einen konstanten
True-Schlüssel hinzu).

**Reinheit / Modularität.** Der Kern von ``evaluate``/``suggest`` bleibt
unangetastet — dieses Modul ist die additive Erweiterung. Die Geo-Pakete
(``numpy``) werden erst im Aufruf gebraucht; die Breitphasen-Hüllen kommen fertig
aus :func:`fgc.collision.robot_geometry.load_robot_collision_geometry`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fgc.collision.check import corner_box, matrix
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.kinematics import IkConfigFilter, OpwKinematics, select_along_path
from fgc.placement.evaluate import (
    SAMPLE_SPACING_MM,
    PlacementOption,
    WallSurface,
    flange_targets,
    nozzle_rotation,
)

if TYPE_CHECKING:  # nur für Typprüfer — kein Laufzeit-Import (geo-frei startbar)
    from fgc.collision.robot_geometry import RobotCollisionGeometry

#: Armglieder, die hinter die Druckebene tauchen können (Rotator/Oberarm/Ellbogen).
#: Handgelenk (4/5) und Flansch (6)/Endeffektor bleiben außen — sie sitzen
#: prozessbedingt an der Wandfront ``y ≈ 0`` (Nozzle-Nähe) und würden sonst
#: chronisch fehlwarnen (ADR-024 Kontext 2). Die Basis (0) ist montiert.
ARM_LINK_INDICES: tuple[int, ...] = (1, 2, 3)

#: Mindest-Eindringtiefe hinter die Druckebene (mm), ab der ein Glied als
#: Kollision zählt — hält Streifkontakt an der Front (``y ≈ 0``) draußen.
DEFAULT_PENETRATION_MM = 20.0

#: Ersatzdicke (mm), wenn die ``WallSurface`` keine Dicke trägt — der Grob-Check
#: braucht ein Volumen hinter der Front, gegen das er testet.
NOMINAL_THICKNESS_MM = 150.0

#: Grobes Stichproben-Raster als Bruchteil der größeren Wandkante — so fallen
#: nur wenige Posen (Ecken + ggf. Mitte) an, nicht das feine ``evaluate``-Raster.
_COARSE_FRACTION = 0.5


def _wall_box(
    wall: WallSurface, penetration_mm: float
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Wandvolumen hinter der Druckebene als achsenparallele Box (Wandkoordinaten).

    ``x`` entlang der Wandlänge (zentriert), ``z`` über die Höhe — auf der
    **echten Höhenlage** der Fläche (``z_offset_mm .. z_offset_mm + height_mm``,
    Issue #132, wie ``flange_targets``), ``y`` der Wandkörper um die
    PCA-Mittelebene (``y ∈ [−Dicke/2, +Dicke/2]``, Issue #160 — dieselbe
    Konvention wie Slicer/Simulation; vorher lag die Box eine halbe Dicke zu
    tief hinter der Mittelebene). Der vordere Rand (Frontfläche ``+Dicke/2``)
    ist um ``penetration_mm`` zurückgesetzt: nur ein Glied, das **tiefer**
    eintaucht, zählt als Kollision.
    """
    thickness = wall.thickness_mm if wall.thickness_mm > 0 else NOMINAL_THICKNESS_MM
    return (
        (-wall.length_mm / 2.0, wall.length_mm / 2.0),
        (-thickness / 2.0, thickness / 2.0 - penetration_mm),
        (wall.z_offset_mm, wall.z_offset_mm + wall.height_mm),
    )


def _overlaps(aabb_lo, aabb_hi, box) -> bool:
    """Überlappt eine (Welt-)AABB die achsenparallele Wandbox in allen drei Achsen?"""
    (xlo, xhi), (ylo, yhi), (zlo, zhi) = box
    return (
        aabb_lo[0] <= xhi
        and xlo <= aabb_hi[0]
        and aabb_lo[1] <= yhi
        and ylo <= aabb_hi[1]
        and aabb_lo[2] <= zhi
        and zlo <= aabb_hi[2]
    )


def path_collides(
    wall: WallSurface,
    robot: RobotDef,
    tool: ToolDef,
    option: PlacementOption,
    geo: RobotCollisionGeometry,
    *,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
    penetration_mm: float = DEFAULT_PENETRATION_MM,
    spacing_mm: float | None = None,
    config_filter: IkConfigFilter | None = None,
) -> bool:
    """Kollidiert die Bahn dieser Aufstellung *grob* mit dem Wandvolumen?

    Baut ein **grobes** Stichproben-Raster (wenige Posen), lässt die bestehende
    Konfigurationswahl (:func:`fgc.kinematics.select_along_path`) die IK je Pose
    lösen und prüft, ob ein **Armglied** (Ellbogen/Unterarm, :data:`ARM_LINK_INDICES`)
    mit seiner Breitphasen-Hülle (#125) tiefer als ``penetration_mm`` hinter die
    Druckebene in den Wandkörper taucht. Reine untere Schranke der echten Distanz
    (Hülle ⊇ Mesh) — ein Treffer ist ein **nachweislicher** Grob-Befund, kein
    Fehlalarm durch dicke Kapseln.

    ``config_filter`` (Issue #200/#201) beschränkt die zulässigen IK-Konfigurations-
    zweige **hart** — derselbe Filter, den auch ``placement.evaluate``/``advisor``
    durchreichen, sodass Ranking (Erreichbarkeit) und Grob-Kollision **denselben**
    Konfigurationszweig bewerten (kein gespaltenes Ranking). ``None``/all-auto =
    Regressionsanker (bit-identisch zu heute).

    Deterministisch (festes Raster, deterministische IK-Wahl). ``False``, wenn der
    Roboter keine Kinematik trägt (ohne IK kein Befund) — der Aufrufer kapselt
    fehlende Geometrie/Extras fail-soft (Befund, kein Gate).
    """
    import numpy as np

    if robot.kinematics is None:
        return False

    kin = OpwKinematics(robot.kinematics)
    r_nozzle = nozzle_rotation(lead_rad, kipp_rad)
    coarse = spacing_mm or (
        max(wall.length_mm, wall.height_mm) * _COARSE_FRACTION or SAMPLE_SPACING_MM
    )
    # Ein Seam für Ziele UND Plan-Lage: ``flange_targets`` liefert die Flansch-Ziele
    # (Basiskoordinaten) und die **eine** Wand→Basis-Transformation (Issue #201) —
    # der Grob-Check baut die t_wall_base-Kette nicht mehr selbst (Abstand ab
    # Wandfläche/Issue #160 lebt nur noch dort). ``t_wall_base`` bringt hier die
    # Glied-Frames ins Wandsystem und testet sie gegen die Wandbox.
    frames, _, _, t_wall_base = flange_targets(wall, tool, option, coarse, r_nozzle)
    solution = select_along_path(kin, frames, config_filter=config_filter)

    box = _wall_box(wall, penetration_mm)

    corners: dict[int, object] = {}
    for i in ARM_LINK_INDICES:
        try:
            corners[i] = corner_box(geo.link(i).broadphase_hull, np)
        except KeyError:
            continue  # Glied nicht in der Geometrie — überspringen (defensiv)

    for target in solution.targets:
        if not target.drivable:
            continue
        link_frames = kin.link_frames(target.joints_rad)
        for i, box_corners in corners.items():
            m = t_wall_base @ matrix(link_frames[i])
            wc = (m @ box_corners)[:3]
            if _overlaps(wc.min(axis=1), wc.max(axis=1), box):
                return True
    return False
