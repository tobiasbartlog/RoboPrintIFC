"""fgc.placement — Bewertung von Aufstellmoeglichkeiten (Issue #22).

Deep module hinter einer schmalen Tuer: ``evaluate`` bewertet eine geplante
Basis-Lage (Platzierung) einer Wand fuer einen Roboter + Endeffektor und liefert
einen ``PlacementScore`` (erreichbarer Wandanteil + kinematische Marge). Alles
Kinematische laeuft ueber ``fgc.kinematics`` (OPW FK/IK + Konfigurationswahl);
dieses Paket rechnet keine eigene Kinematik.

Die Platzierung ist ein **Plan**, kein **Setup** (ADR-006, `core/CONTEXT.md`):
verbindlich wird die Lage erst durch das Antast-Verfahren.
"""

from fgc.placement.advisor import (
    AdvisorContext,
    Suggestion,
    advise,
)
from fgc.placement.artifact import placement_artifact
from fgc.placement.evaluate import (
    SAMPLE_SPACING_MM,
    FlangeTargets,
    PlacementOption,
    PlacementScore,
    WallSurface,
    base_position_in_wall,
    evaluate,
    flange_targets,
    nozzle_rotation,
    standoff_from_base_y,
)
from fgc.placement.prior import (
    NEUTRAL_PRIOR,
    PlacementPrior,
    PriorTable,
    load_prior_tables,
    placement_prior,
)
from fgc.placement.suggest import (
    DEFAULT_STANDOFF_MM,
    collision_judgment,
    default_collision_free,
    feasibility_finding,
    suggest,
)

__all__ = [
    "DEFAULT_STANDOFF_MM",
    "NEUTRAL_PRIOR",
    "SAMPLE_SPACING_MM",
    "AdvisorContext",
    "FlangeTargets",
    "PlacementOption",
    "PlacementPrior",
    "PlacementScore",
    "PriorTable",
    "Suggestion",
    "WallSurface",
    "advise",
    "base_position_in_wall",
    "collision_judgment",
    "default_collision_free",
    "evaluate",
    "feasibility_finding",
    "flange_targets",
    "load_prior_tables",
    "nozzle_rotation",
    "placement_artifact",
    "placement_prior",
    "standoff_from_base_y",
    "suggest",
]
