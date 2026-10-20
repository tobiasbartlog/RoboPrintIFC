"""fgc.kinematics — Vorwärts-/Inverskinematik der Zielroboter.

Siehe docs/architektur.md §5, ADR-002 (Solver aus visose/Robots
selbst portiert, NOTICE) und ADR-006 (Einheiten: mm, Radiant, Quaternionen).
Primärplattform ist der Doosan M1013 mit OPW-Solver (Spike S3).

`opw` liefert FK/IK (Issue #7); `select` die deterministische, bahnstetige
Konfigurationswahl samt Achsgrenz- und Singularitätsprüfung (Issue #11);
`reachability` die offline gebaute 4D-Reichweitenkarte nach RM4D-Muster
(PRD #183, Issue #210).
"""

from fgc.kinematics.opw import (
    IkSolution,
    OpwKinematics,
    frame_distance,
)
from fgc.kinematics.reachability import (
    ReachabilityMap,
    ReachabilityProvenanceError,
    canonical_coords,
    frames_in_wall,
    kinematics_fingerprint,
    load_reachability_map,
    representative_frame,
    save_reachability_map,
)
from fgc.kinematics.select import (
    DEFAULT_SINGULARITY_WARN,
    ConfigWarning,
    IkConfigFilter,
    PathSolution,
    SelectedTarget,
    config_to_block,
    joint_distance,
    select_along_path,
)
from fgc.kinematics.singularity import (
    SingularityAssessment,
    SingularityType,
    classify,
)

__all__ = [
    "DEFAULT_SINGULARITY_WARN",
    "ConfigWarning",
    "IkConfigFilter",
    "IkSolution",
    "OpwKinematics",
    "PathSolution",
    "ReachabilityMap",
    "ReachabilityProvenanceError",
    "SelectedTarget",
    "SingularityAssessment",
    "SingularityType",
    "canonical_coords",
    "classify",
    "config_to_block",
    "frame_distance",
    "frames_in_wall",
    "joint_distance",
    "kinematics_fingerprint",
    "load_reachability_map",
    "representative_frame",
    "save_reachability_map",
    "select_along_path",
]
