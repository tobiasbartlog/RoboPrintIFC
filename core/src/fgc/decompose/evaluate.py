"""Ampel je Abschnitt: ``evaluate(schnittplan) → Befund je Abschnitt`` (Issue #24).

Rechnet fuer jeden Abschnitt eines Zerlegungsvorschlags den erreichbaren Anteil
von *seiner* Platzierung aus (ueber die bestehende Platzierungs-Bewertung
`fgc.placement.evaluate`) und faerbt ihn gruen (voll erreichbar) oder rot. Ein
**Befund, kein Gate** (`core/CONTEXT.md`): ein roter Abschnitt blockiert den Plan
nicht — er markiert nur, dass die Platzierung dort (noch) nicht 100 % erreicht.

Einheiten strikt nach ADR-006: Millimeter, Radiant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fgc.decompose.plan import DecompositionPlan
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.placement import SAMPLE_SPACING_MM
from fgc.placement import evaluate as evaluate_placement

#: Ab diesem erreichbaren Anteil gilt ein Abschnitt als „gruen".
GREEN_THRESHOLD = 0.999


@dataclass(frozen=True)
class SectionStatus:
    """Ampel-Befund eines Abschnitts — reine Daten (kein Gate).

    ``reachable`` = gruen (voll erreichbar) / rot. ``reachable_fraction`` ∈ [0, 1]
    ist der erreichbare Anteil, ``warnings`` traegt die Konfigurationswahl-
    Warnungen als Daten (unreachable/joint_limits/singularity).
    """

    section_id: str
    order: int
    reachable: bool
    reachable_fraction: float
    n_samples: int
    n_reachable: int
    kinematic_margin: float | None
    mean_margin: float | None
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "reachable_fraction": self.reachable_fraction,
            "n_samples": self.n_samples,
            "n_reachable": self.n_reachable,
            "kinematic_margin": self.kinematic_margin,
            "mean_margin": self.mean_margin,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class PlacementCheck:
    """Sicherheitsabstands-Befund einer frei uebersteuerten Platzierung (Issue #94).

    Vergleicht den geplanten Abstand der Basis vor der Wandfront (``standoff_mm``)
    mit dem Sicherheits-Mindestabstand der Workstation (#77). **Befund, kein Gate**
    (`core/CONTEXT.md`): ein unterschrittener Mindestabstand blockiert den Plan
    nicht — er wird nur gemeldet (der Viewer zeigt, der Core urteilt, ADR-007).
    """

    standoff_mm: float
    safety_min_distance_mm: float
    below_min_distance: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "standoff_mm": self.standoff_mm,
            "safety_min_distance_mm": self.safety_min_distance_mm,
            "below_min_distance": self.below_min_distance,
        }


def check_safety_distance(
    plan: DecompositionPlan,
    section_ids: set[str] | frozenset[str],
    safety_min_distance_mm: float,
) -> dict[str, PlacementCheck]:
    """Sicherheitsabstands-Befund je Teil mit freiem Platzierungs-Override (#94).

    Reine Funktion: fuer jedes Teil aus ``section_ids`` (die frei uebersteuerten)
    wird der Abstand seiner Platzierung gegen den Sicherheits-Mindestabstand der
    Workstation gestellt. Unbekannte ``section_ids`` (stale Overrides) werden
    stillschweigend uebergangen. Befund, kein Gate — nichts wirft.
    """
    checks: dict[str, PlacementCheck] = {}
    for section_plan in plan.sections:
        sid = section_plan.section.section_id
        if sid not in section_ids:
            continue
        standoff = float(section_plan.placement.standoff_mm)
        checks[sid] = PlacementCheck(
            standoff_mm=standoff,
            safety_min_distance_mm=float(safety_min_distance_mm),
            below_min_distance=standoff < float(safety_min_distance_mm),
        )
    return checks


def evaluate(
    plan: DecompositionPlan,
    robot: RobotDef,
    tool: ToolDef,
    *,
    spacing_mm: float = SAMPLE_SPACING_MM,
    threshold: float = GREEN_THRESHOLD,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
) -> list[SectionStatus]:
    """Bewertet jeden Abschnitt eines Zerlegungsvorschlags (Ampel gruen/rot).

    Jeder Abschnitt wird als Wandflaeche (Laenge x Hoehe) an seiner **echten
    Hoehenlage** (``z0..z1`` absolut, Issue #132) von seiner Platzierung aus
    bewertet — die Aufstellhoehe (``stand_height_mm``) ist absolut ueber dem
    Boden (Boden = Wandfuss). Dieselbe Kinematik wie beim Optimalvorschlag
    (`fgc.placement`), nichts dupliziert. Ergebnis ist ein
    :class:`SectionStatus` je Abschnitt (in Plan-Reihenfolge, unten → oben).
    Eine im Boden-Modus unerreichbare obere Reihe wird ehrlich rot — Befund,
    kein Gate. Bei Zerlegungsart „modul" bleibt die Flaeche am Boden
    (``z_offset = 0``): das Teil wird stehend an der Workstation gedruckt, sein
    Fuss liegt auf der Arbeitsflaeche (ADR-022), nicht auf Einbauhoehe.

    ``lead_rad``/``kipp_rad`` (Issue #61) reichen den bahn-relativen Anstellwinkel
    an `fgc.placement.evaluate` durch — ein gesetzter Kipp aendert damit die Ampel.
    Deterministisch: gleiche Eingaben → gleiche Ampeln.
    """
    statuses: list[SectionStatus] = []
    for section_plan in plan.sections:
        section = section_plan.section
        surface = plan.surface_for_evaluation(section, plan.wall.thickness_mm)
        score = evaluate_placement(
            surface,
            robot,
            tool,
            section_plan.placement,
            spacing_mm=spacing_mm,
            lead_rad=lead_rad,
            kipp_rad=kipp_rad,
        )
        statuses.append(
            SectionStatus(
                section_id=section.section_id,
                order=section.order,
                reachable=score.reachable_fraction >= threshold,
                reachable_fraction=score.reachable_fraction,
                n_samples=score.n_samples,
                n_reachable=score.n_reachable,
                kinematic_margin=score.kinematic_margin,
                mean_margin=score.mean_margin,
                warnings=score.warnings,
            )
        )
    return statuses
