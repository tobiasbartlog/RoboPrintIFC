"""fgc.simulation — Toolpath + Setup + Kinematik → Trajectory (Strang C, Issue #12).

Siehe docs/architektur.md §5 und ADR-012 (Totzeit-Kompensation, E3):
Die Simulation ist die Stelle, an der **Zeit** entsteht. Sie zeitparametriert die
bahnstetigen Gelenklösungen (`kinematics.select_along_path`, Issue #11), macht die
io-Werte je Bahnposition zur io-Zeitreihe und verschiebt diese — sofern das Setup
``simulation_shift`` deklariert — um −t_tot (Totzeit des Materialsystems).

Das **Bewegungsmodell** (`fgc.simulation.motion`, Issue #62) bildet die reale
Bewegung ab: movel-lineare TCP-Interpolation für Druck, movej-Gelenkinterpolation
für Travel, jede unter einem Trapez-Geschwindigkeitsprofil; unfahrbare/singuläre
Zwischenstellen werden als verortete Warnungen ehrlich gemeldet.

Öffentliche API: :func:`build_trajectory`, :class:`Trajectory`,
:class:`~fgc.simulation.motion.MotionParams`, :func:`~fgc.simulation.motion.motion_from_job`.
"""

from fgc.simulation.build import Trajectory, build_trajectory
from fgc.simulation.motion import MotionParams, motion_from_job

__all__ = ["MotionParams", "Trajectory", "build_trajectory", "motion_from_job"]
