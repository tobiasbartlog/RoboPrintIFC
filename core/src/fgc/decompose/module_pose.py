"""Modul-Pose: Relativpose ↔ Lage des Moduls am Druckort (Issue #96, ADR-022).

Reines, tiefes Modul (kein I/O, keine Kinematik): aus der Platzierungs-
**Relativpose** eines Teils (``PlacementOption`` — seitlich/Abstand/
Aufstellhoehe/yaw, ADR-006) und den Workstation-Frames ``robot_base_frame`` +
``work_surface_frame`` (ADR-021, Stammdaten seit Issue #78) wird die **Lage des
Moduls auf der Arbeitsflaeche** berechnet. Das ist die *Invertierung der
Leserichtung* aus ADR-022 Punkt 2: bei Zerlegungsart „modul" steht der Roboter
(fest an ``robot_base_frame``), das Modul liegt vor ihm — rechnerisch dieselbe
Relativpose wie bei „abschnitt", nur umgekehrt gelesen:

    T_ws←modul = T_ws←basis ∘ (T_modul←basis)⁻¹

mit ``T_modul←basis`` = Platzierungs-Frame (die Basis-Lage im Modul-/Wand-
Koordinatensystem des Teils: x entlang der Teil-Laenge, zentriert; y = Abstand
vor der Modul-**Mittelebene** — das Wandsystem ist PCA-zentriert, der
Wandkoerper liegt bei y ∈ [−Dicke/2, +Dicke/2]; z = Aufstellhoehe ueber dem
Modulfuss; Drehung ``yaw`` um die Hochachse). Das Modul liegt damit **vor der
Basis entlang deren −y-Achse** — dieselbe Leserichtung wie bei „abschnitt",
wo die Basis bei +y vor der Wand steht. Die „Arbeitsflaechen-Lage" ist dieselbe Pose relativ zur
Arbeitsflaeche: ``T_flaeche←modul = (T_ws←flaeche)⁻¹ ∘ T_ws←modul``.

Der Rueckweg (:func:`placement_from_pose`) rekonstruiert die Relativpose exakt
aus der Arbeitsflaechen-Lage — der Roundtrip Relativpose ↔ Arbeitsflaechen-Lage
ist verlustfrei (pytest-Orakel), weil die Frames sich in der Kette kuerzen.

Damit bekommen die ADR-021-Frames ihren **ersten Konsumenten** (Schluss der
Naht aus #77/#79). Frame-Algebra ausschliesslich aus
:mod:`fgc.simulation.transform` (ADR-006: eine Transformationsstelle, keine
zweite Quaternion-Konvention). Einheiten strikt nach ADR-006: Millimeter,
Radiant, Einheitsquaternionen ``[w, x, y, z]``. Deterministisch: gleiche
Eingaben → gleiche Pose (ADR-004-Geist).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fgc.domain.models import Frame
from fgc.simulation.transform import compose, invert, quat_normalize

if TYPE_CHECKING:
    from fgc.decompose.plan import DecompositionPlan
    from fgc.placement import PlacementOption


def placement_frame(placement: PlacementOption, thickness_mm: float) -> Frame:
    """Die Platzierungs-Relativpose als Frame ``T_modul←basis`` (ADR-006/022).

    Position = Basis-Lage im Modul-/Wand-System des Teils über die eine Naht
    :func:`fgc.placement.base_position_in_wall` (Issue #160: ``standoff_mm``
    misst ab der Modulfläche, das Modul-System ist um die Dicke zentriert —
    darum ist ``thickness_mm`` Pflicht), Rotation = ``yaw`` um die Hochachse —
    exakt die Konvention von ``fgc.placement.evaluate``, nur als
    Quaternion-Frame statt 4×4-Matrix.
    """
    from fgc.placement import base_position_in_wall

    half = placement.yaw_rad / 2.0
    return Frame(
        pos_mm=base_position_in_wall(placement, thickness_mm),
        quat=(math.cos(half), 0.0, 0.0, math.sin(half)),
    )


@dataclass(frozen=True)
class ModulePose:
    """Die Lage eines Moduls am Druckort — zwei Sichten derselben Pose.

    ``workstation`` = Modul-Frame in Workstation-(Mesh-)Koordinaten (dort leben
    Mesh, ``robot_base_frame`` und ``work_surface_frame`` — direkt fuer die
    Druckort-Szene des Viewers konsumierbar). ``on_surface`` = dieselbe Pose
    relativ zur Arbeitsflaeche (die „Arbeitsflaechen-Lage" des Roundtrips).
    Der Modul-Ursprung ist der Ursprung des Teil-Wandsystems: x zentriert
    entlang der Teil-Laenge, y zentriert ueber die Wanddicke (PCA-Mittelebene
    bei y = 0, Koerper y ∈ [−Dicke/2, +Dicke/2]), Modulfuss bei z = 0.
    """

    workstation: Frame
    on_surface: Frame

    def to_dict(self) -> dict[str, Any]:
        return {
            "workstation": self.workstation.to_dict(),
            "on_surface": self.on_surface.to_dict(),
        }


def module_pose(
    placement: PlacementOption,
    robot_base_frame: Frame,
    work_surface_frame: Frame,
    *,
    thickness_mm: float,
) -> ModulePose:
    """Rechnet die Modul-Lage aus Relativpose + Workstation-Frames (ADR-022).

    Invertierung der Leserichtung: ``T_ws←modul = robot_base_frame ∘
    placement_frame(placement)⁻¹`` — der Roboter steht, das Modul liegt vor ihm.
    ``on_surface`` ist dieselbe Pose relativ zur Arbeitsflaeche.
    ``thickness_mm`` = Moduldicke (Wanddicke des Teils) fuer die
    Abstand-ab-Flaeche-Naht (Issue #160). Rein und deterministisch;
    Einheiten mm / Quaternionen [w, x, y, z] (ADR-006).
    """
    in_workstation = compose(
        robot_base_frame, invert(placement_frame(placement, thickness_mm))
    )
    on_surface = compose(invert(work_surface_frame), in_workstation)
    return ModulePose(workstation=in_workstation, on_surface=on_surface)


def placement_from_pose(
    on_surface: Frame,
    robot_base_frame: Frame,
    work_surface_frame: Frame,
    *,
    thickness_mm: float,
    option_id: str = "roundtrip",
) -> PlacementOption:
    """Der Rueckweg: Arbeitsflaechen-Lage → Relativpose (Roundtrip-Orakel).

    Kette: ``T_modul←basis = (work_surface_frame ∘ on_surface)⁻¹ ∘
    robot_base_frame`` — die Workstation-Frames kuerzen sich, uebrig bleibt
    exakt der Platzierungs-Frame; daraus werden seitlich/Abstand/Aufstellhoehe
    (Position) und ``yaw`` (Drehung um die Hochachse) gelesen. Der Abstand
    laeuft durch die inverse Naht (:func:`fgc.placement.standoff_from_base_y`,
    Issue #160) — Roundtrip mit :func:`placement_frame` bleibt verlustfrei bis
    auf Gleitkomma-Rauschen.
    """
    from fgc.placement import PlacementOption, standoff_from_base_y

    in_workstation = compose(work_surface_frame, on_surface)
    t_module_base = compose(invert(in_workstation), robot_base_frame)
    w, x, y, z = quat_normalize(t_module_base.quat)
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    lateral, base_y, stand_height = t_module_base.pos_mm
    return PlacementOption(
        option_id=option_id,
        lateral_mm=lateral,
        standoff_mm=standoff_from_base_y(base_y, thickness_mm),
        stand_height_mm=stand_height,
        yaw_rad=yaw,
    )


def pose_plan(
    plan: DecompositionPlan,
    robot_base_frame: Frame,
    work_surface_frame: Frame,
) -> dict[str, ModulePose]:
    """Die Modul-Lage je Teil eines Zerlegungsplans (``section_id →`` Pose).

    Bequemer Durchstich fuer Art „modul" (analog ``limits.check_plan``): jedes
    Teil wird aus *seiner* Platzierung gerechnet — Teile mit Platzierungs-
    Override (Issue #94) bekommen so ihre eigene Lage. Rein, deterministisch,
    Plan-Reihenfolge bleibt erhalten.
    """
    return {
        sp.section.section_id: module_pose(
            sp.placement, robot_base_frame, work_surface_frame,
            thickness_mm=plan.wall.thickness_mm,
        )
        for sp in plan.sections
    }
