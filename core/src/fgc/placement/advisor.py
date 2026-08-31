"""Singularitäts-Advisor: Typ + Kontext → gezielter Vorschlag (Issue #65, Scheibe 6).

Tiefes, isoliert testbares Core-Modul, das über der Typ-Klassifikation
(``fgc.kinematics.singularity``) sitzt und aus **Typ + Platzierungskontext** einen
**gezielten Hebel** ableitet — samt Vorher/Nachher-Marge aus **derselben**
Core-Bewertung (``fgc.placement.evaluate``):

- **Handgelenk → Kipp-Delta** (``lever="kipp"``): ein bahn-relativer Kipp-Winkel
  (``process_params.orientation.kipp_deg``) dreht die Flansch-Ziel-Orientierung aus
  dem Handgelenks-Zweig heraus. Der Advisor sucht das Kipp-Delta, das die
  **kinematische Marge** in der Neubewertung anhebt, ohne den erreichbaren Anteil
  zu senken — nachweisbar (pytest ``test_singularity_advisor``).
- **Reichweite/Ellbogen → Platzierungsoption** (``lever="placement"``): eine
  bessere Basis-Lage (aus ``fgc.placement.suggest``) — der gestreckte Arm braucht
  eine andere Aufstellung, keinen Anstellwinkel.
- **config-abhängig/Schulter → Config-Flip** (``lever="config_flip"``, Issue #200):
  die Schulter auf den **anderen** IK-Zweig (a↔b) fixieren, **bahn-weit** neu bewertet
  (der harte Filter betrifft die ganze Bahn, nicht die schlechteste Pose). Der
  Vorschlag trägt den persistierbaren a/b-Block (``ik_config``) + die ``write``-Nutzlast
  in genau der Form des Kollisions-Advisors — anwendbar über denselben
  ``set_process_params(ik_config=…)``-Seam (#129, ADR-024 Punkt 4 erfüllt den
  ADR-020-Revisionstrigger).

ADR-007/016: Der Advisor **urteilt** (rechnet Vorschlag + Marge); geschrieben wird
ausschließlich über die bestehende Projekt-Schreibstelle (``fgc.project``), und der
Kipp-Hebel landet in genau dem ``process_params.orientation``-Block, den Slicer und
``placement`` über dieselbe ``nozzle_quat`` verrechnen (Issue #61) — kein Drift.

Referenzposen sind **bewusst weggelassen** (nur Start-Seed der Konfigurationswahl):
der Advisor bewertet die real gesampelte Wandbahn, keine hinterlegten Sollposen —
Scope-Grenze wie im Acceptance-Kriterium (Design-Log 2026-07-06, ADR-020).

Einheiten strikt nach ADR-006 (mm, Radiant; ``kipp_delta_deg`` als UI-naher Grad).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.kinematics import (
    IkConfigFilter,
    OpwKinematics,
    classify,
    config_to_block,
    select_along_path,
)
from fgc.kinematics.singularity import SingularityAssessment, SingularityType
from fgc.placement.evaluate import (
    SAMPLE_SPACING_MM,
    PlacementOption,
    PlacementScore,
    WallSurface,
    evaluate,
    flange_targets,
    nozzle_rotation,
)
from fgc.placement.suggest import suggest

#: Vokabular der Vorschlags-Hebel.
SingularityLever = Literal["kipp", "placement", "config_flip"]

#: Kandidaten für das Kipp-Delta (Grad), die der Advisor durchprobiert. Symmetrisch
#: um 0 (beide Kipp-Richtungen), 10°-Raster bis ±40° — grob genug für wenige
#: Neubewertungen, fein genug, um aus dem Handgelenks-Zweig herauszudrehen.
KIPP_CANDIDATES_DEG: tuple[float, ...] = (-40.0, -30.0, -20.0, -10.0, 10.0, 20.0, 30.0, 40.0)

#: Ab dieser kinematischen Marge (reziprokes Konditionsmaß der schlechtesten
#: erreichten Pose) lohnt ein Vorschlag; darüber ist die Platzierung unkritisch.
#: Bewusst großzügiger als die harte Warnschwelle (``DEFAULT_SINGULARITY_WARN``),
#: damit auch „noch nicht rot, aber knapp" beraten wird.
ADVISE_MARGIN_BELOW = 0.03


@dataclass(frozen=True)
class WorstPose:
    """Die schlechtest-konditionierte erreichte Pose einer Platzierungsbewertung.

    ``index`` verweist auf das Sampling-Ziel; ``joints_rad`` ist die gewählte
    Gelenklösung (Grundlage der Typ-Klassifikation), ``configuration`` ihr
    IK-Konfigurationsbit, ``margin`` ihr Singularitätsnähe-Maß.
    """

    index: int
    joints_rad: tuple[float, float, float, float, float, float]
    configuration: int
    margin: float


@dataclass(frozen=True)
class AdvisorContext:
    """Platzierungskontext einer Advisor-Anfrage (Robot/Tool/Platzierung/Kipp).

    Trägt genau, was die Neubewertung (``evaluate``) braucht; ``lead_rad``/
    ``kipp_rad`` sind der **aktuelle** Anstellwinkel (aus
    ``process_params.orientation``), auf den der Kipp-Hebel sein Delta addiert.
    """

    robot: RobotDef
    tool: ToolDef
    wall: WallSurface
    option: PlacementOption
    lead_rad: float = 0.0
    kipp_rad: float = 0.0
    spacing_mm: float = SAMPLE_SPACING_MM

    def kinematics(self) -> OpwKinematics:
        if self.robot.kinematics is None:
            raise ValueError(
                f"Roboter {self.robot.name!r} trägt keine Kinematik-Parameter — "
                "Singularitäts-Advisor nicht rechenbar."
            )
        return OpwKinematics(self.robot.kinematics)

    def score(
        self,
        *,
        kipp_rad: float | None = None,
        option: PlacementOption | None = None,
        config_filter: IkConfigFilter | None = None,
    ) -> PlacementScore:
        """Neubewertung derselben Core-Bewertung (``placement.evaluate``).

        ``config_filter`` (Issue #200) reicht die harte IK-Konfigurationsvorgabe
        des Config-Flips **bahn-weit** durch — dieselbe Bewertung, nur mit
        gesetztem Filter (keine Parallel-Metrik).
        """
        return evaluate(
            self.wall,
            self.robot,
            self.tool,
            option or self.option,
            spacing_mm=self.spacing_mm,
            lead_rad=self.lead_rad,
            kipp_rad=self.kipp_rad if kipp_rad is None else kipp_rad,
            config_filter=config_filter,
        )


@dataclass(frozen=True)
class Suggestion:
    """Ein gezielter Vorschlag samt Vorher/Nachher-Marge — reine Daten (kein Gate).

    ``sing_type`` = klassifizierter Typ; ``lever`` = passender Hebel; ``margin_before``/
    ``margin_after`` = kinematische Marge vor/nach dem Vorschlag aus der Neubewertung
    (``None``, wenn nicht berechenbar). Je Hebel ist genau ein Nutzlast-Feld gesetzt:
    ``kipp_delta_deg`` (Kipp), ``placement`` (Platzierung), ``ik_config`` (Config-Flip,
    Issue #200: der persistierbare a/b-Tri-State-Block statt des früheren rohen
    opw-Bitfelds). Der Config-Flip trägt zusätzlich die ``write``-Nutzlast in genau der
    Form des Kollisions-Advisors (``{"setter": "process-params", "ik_config": block}``,
    ADR-024) — beide Advisor schreiben über **denselben** ``set_process_params(
    ik_config=…)``-Seam (#129).
    """

    sing_type: SingularityType
    lever: SingularityLever
    margin_before: float | None
    margin_after: float | None
    detail: str
    kipp_delta_deg: float | None = None
    placement: PlacementOption | None = None
    ik_config: dict[str, str] | None = None

    @property
    def improves(self) -> bool:
        """True, wenn die Marge nachweisbar steigt (Vorher < Nachher)."""
        return (
            self.margin_before is not None
            and self.margin_after is not None
            and self.margin_after > self.margin_before
        )

    @property
    def write(self) -> dict | None:
        """Schreibstellen-Nutzlast des Config-Flips (sonst ``None``).

        Dieselbe Form wie beim Kollisions-Advisor (``fgc.collision.advisor``): der
        Viewer bildet sie auf die bestehende ``process-params``-Route ab (ADR-016);
        der Advisor selbst schreibt nichts (ADR-007).
        """
        if self.ik_config is None:
            return None
        return {"setter": "process-params", "ik_config": self.ik_config}

    def to_dict(self) -> dict:
        return {
            "type": self.sing_type,
            "lever": self.lever,
            "margin_before": self.margin_before,
            "margin_after": self.margin_after,
            "improves": self.improves,
            "detail": self.detail,
            "kipp_delta_deg": self.kipp_delta_deg,
            "placement": (
                {
                    "option_id": self.placement.option_id,
                    "lateral_mm": self.placement.lateral_mm,
                    "standoff_mm": self.placement.standoff_mm,
                    "stand_height_mm": self.placement.stand_height_mm,
                    "yaw_rad": self.placement.yaw_rad,
                }
                if self.placement is not None
                else None
            ),
            "ik_config": self.ik_config,
            "write": self.write,
        }


def worst_reachable(ctx: AdvisorContext) -> WorstPose | None:
    """Die schlechtest-konditionierte erreichte Pose der aktuellen Platzierung.

    Baut dieselben Flansch-Ziele wie ``placement.evaluate`` (geteilte Helfer, kein
    Duplikat) und lässt die Konfigurationswahl (``select_along_path``, Issue #11)
    die Gelenklösungen bestimmen. ``None``, wenn kein Ziel erreichbar ist.
    """
    kin = ctx.kinematics()
    r_nozzle = nozzle_rotation(ctx.lead_rad, ctx.kipp_rad)
    frames = flange_targets(
        ctx.wall, ctx.tool, ctx.option, ctx.spacing_mm, r_nozzle
    ).frames
    solution = select_along_path(kin, frames)
    worst: WorstPose | None = None
    for t in solution.targets:
        if not t.drivable or t.singularity_measure is None:
            continue
        if worst is None or t.singularity_measure < worst.margin:
            worst = WorstPose(
                index=t.index,
                joints_rad=t.joints_rad,  # type: ignore[arg-type]
                configuration=int(t.configuration),  # type: ignore[arg-type]
                margin=float(t.singularity_measure),
            )
    return worst


def assess(ctx: AdvisorContext) -> tuple[SingularityAssessment, WorstPose] | None:
    """Klassifiziert die schlechteste erreichte Pose der Platzierung nach Typ."""
    worst = worst_reachable(ctx)
    if worst is None:
        return None
    kin = ctx.kinematics()
    return classify(kin, worst.joints_rad), worst


def advise(
    ctx: AdvisorContext, *, advise_below: float = ADVISE_MARGIN_BELOW
) -> Suggestion | None:
    """Leitet aus Typ + Kontext einen gezielten Vorschlag ab (oder ``None``).

    ``None`` bedeutet: kein erreichbares Ziel *oder* die schlechteste erreichte
    Pose ist mit Marge unkritisch (``margin >= advise_below``) — dann gibt es
    nichts zu beraten. Sonst dispatcht der Advisor auf den zum Typ passenden Hebel.
    """
    result = assess(ctx)
    if result is None:
        return None
    assessment, worst = result
    if worst.margin >= advise_below:
        return None
    return suggestion_for(ctx, assessment, worst)


def suggestion_for(
    ctx: AdvisorContext, assessment: SingularityAssessment, worst: WorstPose
) -> Suggestion:
    """Bildet Typ (+ Kontext) auf den erwarteten Hebel ab — der Dispatch-Kern.

    Getrennt von :func:`advise`, damit der Hebel-je-Typ isoliert testbar ist
    (synthetische Assessments/Posen, ohne eine reale Platzierung zu treffen).
    """
    if assessment.dominant == "wrist":
        return _advise_kipp(ctx, assessment, worst)
    if assessment.dominant == "elbow":
        return _advise_placement(ctx, assessment, worst)
    return _advise_config_flip(ctx, assessment, worst)


def _advise_kipp(
    ctx: AdvisorContext, assessment: SingularityAssessment, worst: WorstPose
) -> Suggestion:
    """Handgelenk → Kipp-Delta: sucht das Kipp, das die Marge am meisten anhebt.

    Neubewertet je Kandidat über dieselbe ``placement.evaluate`` und wählt das
    Delta mit der größten kinematischen Marge, das den erreichbaren Anteil **nicht**
    senkt. Findet sich keine Verbesserung, ist ``kipp_delta_deg=0`` und Vorher =
    Nachher (der Advisor beschönigt nicht).
    """
    base = ctx.score()
    before = base.kinematic_margin
    best_delta = 0.0
    best_margin = before if before is not None else -1.0
    for delta in KIPP_CANDIDATES_DEG:
        cand = ctx.score(kipp_rad=ctx.kipp_rad + math.radians(delta))
        if cand.kinematic_margin is None:
            continue
        if cand.reachable_fraction < base.reachable_fraction - 1e-9:
            continue
        if cand.kinematic_margin > best_margin:
            best_margin = cand.kinematic_margin
            best_delta = delta
    after = best_margin if best_delta != 0.0 else before
    detail = (
        f"Handgelenks-Singularität (J5≈0): Düse um {best_delta:+.0f}° kippen — "
        f"Marge {_fmt(before)} → {_fmt(after)}."
        if best_delta != 0.0
        else "Handgelenks-Singularität (J5≈0): kein Kipp-Delta verbessert die Marge hier."
    )
    return Suggestion(
        sing_type="wrist",
        lever="kipp",
        margin_before=before,
        margin_after=after,
        detail=detail,
        kipp_delta_deg=best_delta,
    )


def _advise_placement(
    ctx: AdvisorContext, assessment: SingularityAssessment, worst: WorstPose
) -> Suggestion:
    """Reichweite/Ellbogen → Platzierungsoption: bessere Basis-Lage vorschlagen.

    Nutzt den bestehenden Optimalvorschlag (``placement.suggest``); der gestreckte
    Arm braucht eine andere Aufstellung (Höhe/Abstand), keinen Anstellwinkel.
    Vorher/Nachher = kinematische Marge der aktuellen vs. der vorgeschlagenen Lage.
    """
    before = ctx.score().kinematic_margin
    ranked = suggest(
        ctx.wall,
        ctx.robot,
        ctx.tool,
        n_best=1,
        spacing_mm=ctx.spacing_mm,
        lead_rad=ctx.lead_rad,
        kipp_rad=ctx.kipp_rad,
    )
    if not ranked:
        return Suggestion(
            sing_type="elbow",
            lever="placement",
            margin_before=before,
            margin_after=before,
            detail="Ellbogen gestreckt: keine bessere Platzierung im Raster gefunden.",
        )
    best_option, best_score = ranked[0]
    after = best_score.kinematic_margin
    detail = (
        f"Ellbogen gestreckt (Reichweitenrand): Basis auf Höhe "
        f"{best_option.stand_height_mm:.0f} mm / Abstand {best_option.standoff_mm:.0f} mm "
        f"stellen — erreichbarer Anteil {best_score.reachable_fraction:.0%}, "
        f"Marge {_fmt(before)} → {_fmt(after)}."
    )
    return Suggestion(
        sing_type="elbow",
        lever="placement",
        margin_before=before,
        margin_after=after,
        detail=detail,
        placement=best_option,
    )


def _advise_config_flip(
    ctx: AdvisorContext, assessment: SingularityAssessment, worst: WorstPose
) -> Suggestion:
    """config-abhängig/Schulter → Schulter-Zweig fixieren, **bahn-weit** neu bewertet.

    Der harte IK-Konfigurationsfilter betrifft die **ganze Bahn**, nicht die eine
    schlechteste Pose (Issue #200, ADR-024 Punkt 4): der Advisor fixiert die Schulter
    auf den **anderen** Zweig (a↔b, ``kinematics.config_to_block`` liest den aktuellen
    Zweig aus dem Bitfeld der schlechtesten Pose) und lässt **dieselbe**
    ``placement.evaluate`` die Vorher/Nachher-Marge über die gesampelte Bahn rechnen
    (Neu-Simulations-Muster des Kollisions-Advisors #130, keine Parallel-Metrik).

    ``margin_before`` = bahn-weite kinematische Marge ohne Vorgabe, ``margin_after`` =
    mit gesetztem Filter. Bahnpunkte, die *unter der Vorgabe* unerreichbar werden,
    sinken ehrlich in die Bewertung ein und werden als Befund benannt (kein Gate,
    US 14). Emittiert den a/b-Block + die ``write``-Nutzlast (``Suggestion.write``),
    die der Viewer über die bestehende ``process-params``-Route anwendet (#129).
    """
    current_shoulder = config_to_block(worst.configuration)["shoulder"]
    target = "a" if current_shoulder == "b" else "b"
    block = {"shoulder": target}

    base = ctx.score()
    before = base.kinematic_margin
    flipped = ctx.score(config_filter=IkConfigFilter.from_block(block))
    after = flipped.kinematic_margin

    # Bahnpunkte, die erst unter der Vorgabe unerreichbar werden (Befund, kein Gate).
    lost = max(0, base.n_reachable - flipped.n_reachable)
    lost_note = (
        f" {lost} Bahnpunkt(e) unter der Vorgabe unerreichbar (Befund)." if lost else ""
    )
    detail = (
        f"Schulter/konfig-abhängige Singularität: Schulter auf Zweig {target} "
        f"fixieren — Marge {_fmt(before)} → {_fmt(after)} (bahn-weit).{lost_note}"
    )
    return Suggestion(
        sing_type="shoulder",
        lever="config_flip",
        margin_before=before,
        margin_after=after,
        detail=detail,
        ik_config=block,
    )


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"
