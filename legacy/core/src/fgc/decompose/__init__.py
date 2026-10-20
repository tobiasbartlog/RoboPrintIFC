"""fgc.decompose — Zerlegungsvorschlag in Abschnitte mit Platzierungen (Issue #24).

Deep module hinter einer schmalen Tuer: reicht keine einzelne **Platzierung**
fuer 100 % der Wand, schlaegt ``propose`` eine **Zerlegung** in **Abschnitte**
(Zerlegungsart „Abschnitt", in place — `core/CONTEXT.md`) vor: achsparallele
Schnittebenen (horizontal = Hoehenstufen, vertikal = Laengenteilung) und je
Abschnitt eine eigene Platzierung, Druckreihenfolge unten → oben.

- ``propose(wall, robot, tool)`` → :class:`DecompositionPlan`
- ``from_cuts(wall, robot, tool, cuts, ...)`` → :class:`DecompositionPlan` aus
  manuell gesetzten Schnittebenen (Schnittplan-Editing, Issue #25)
- ``apply_overrides(plan, overrides)`` → Plan mit uebersteuerten Platzierungen
  je Abschnitt (Issue #25)
- ``apply(wall_mesh, plan)`` → wasserdichte Abschnitts-Meshes
- ``evaluate(plan, robot, tool)`` → Ampel je Abschnitt (Befund, kein Gate)
- ``check_module`` / ``check_plan`` (`fgc.decompose.limits`, Issue #90) →
  Modulgrenzen-Befund je Teil bei Art „modul": Gewicht (Volumen × Dichte) +
  optionale Obergrenzen max. Laenge/Hoehe — Befund, kein Gate (ADR-022)
- ``check_safety_distance`` (Issue #94) → Sicherheitsabstands-Befund je Teil
  mit freiem Platzierungs-Override: Abstand vor der Wandfront gegen den
  Workstation-Mindestabstand (#77) — Befund, kein Gate
- ``module_pose`` / ``pose_plan`` / ``placement_from_pose``
  (`fgc.decompose.module_pose`, Issue #96) → Lage des Moduls am Druckort aus
  Relativpose + Workstation-Frames (ADR-021/022, Invertierung der
  Leserichtung); Roundtrip Relativpose ↔ Arbeitsflaechen-Lage verlustfrei
- ``assess_plan`` / ``PruefCache`` / ``PruefStats`` / ``count_representatives``
  (`fgc.decompose.pruefung`, Issue #190) → die Urteils-Politik der **Prüf-Tür**
  (Scoping, Reihen-Vererbung, Cache-Politik) mit injizierbarem Stufe-2-Orakel;
  Stufe 1 = derselbe Aufruf ohne Orakel
- ``ObjectiveConfig`` / ``KriterienWerte`` / ``candidate_key`` /
  ``compare_candidates`` (`fgc.decompose.objective`, Issue #212, PRD #183
  Stufe 3) → die Zielfunktion der Zerlegungs-Suche: lexikographischer
  Komparator (Default) oder gewichtete Summe über EINEM Gewichts-Satz,
  Erreichbarkeit als hartes K.-o., Quantisierung stetiger Kriterien;
  Kriterienwerte injiziert (die Lieferanten verdrahtet die Beam-Suche #216/#217)
- ``ZerlegungsStrategie`` / ``GreedyAchsenVerfeinerung`` /
  ``KollisionsGetriebeneVerfeinerung`` / ``RasterAufgabe`` / ``RasterWahl`` /
  ``ZellenOption`` / ``causing_axis`` (`fgc.decompose.strategie`, Issue #216/#165,
  US 19) → das Strategie-Interface der Zerlegungs-Suche, extrahiert aus
  ``propose._refine`` (#203): Greedy und **kollisionsgetriebene Verfeinerung**
  (#165 — Zelle gut = von bester Option frei, Hebel IK/Platzierung → Bandhoehe →
  Breite entlang der verursachenden Achse aus dem Befund) und Beam (#217)
  austauschbar an derselben Naht, Provenienz nennt die Strategie (ADR-004)
- ``band_raster_kandidaten`` / ``BandRasterKandidat``
  (`fgc.decompose.kandidaten`, Issue #216) → deterministischer Kandidaten-
  Generator: achsparallele Band-Raster in stabiler Ordnung (grob vor fein)
- ``BilligerScorer`` / ``KandidatBewertung`` / ``Standplatz``
  (`fgc.decompose.scorer`, Issue #216) → billige Kriterienwerte je Kandidat
  (#212): Erreichbarkeit + Anzahl Standplaetze aus der Reichweitenkarte
  (#210/#214, Min-Aggregation), Fugenflaeche/c_v/Raycast-Inselkarte per
  Masken-/Matrixbewertung (Han/Z-Chunking) — Schaetzung, kein Urteil (ADR-007)

Seit Issue #90 (ADR-022) rechnen ``propose``/``from_cuts`` auch die
Zerlegungsart **Modul**: feste Platzierung an der Workstation (dem Druckort)
statt Platzierungssuche je Zelle; Teile stehend in Einbauorientierung.

Kinematik/Erreichbarkeit laufen ausschliesslich ueber `fgc.placement`
(Optimalvorschlag/Bewertung) — nichts dupliziert (Issue #22/#23). „Segment" ist
vermieden (im Slicer vergeben); hier heisst die Einheit **Abschnitt** bzw.
zerlegungsart-uebergreifend **Teil**.
"""

from fgc.decompose.apply import apply, total_volume
from fgc.decompose.artifact import cuts_to_dicts, decompose_artifact
from fgc.decompose.beam import (
    RELAXATIONSLEITER,
    BeamSuche,
    beam_breite,
)
from fgc.decompose.benchmark import (
    ARM_BEAM,
    ARM_BEAM_GPU,
    ARM_BEAM_SURROGAT,
    ARM_GREEDY,
    BASE_ARMS,
    ArmRun,
    BenchmarkCase,
    GateDecision,
    SurrogatGateResult,
    benchmark_kennzahlen,
    benchmark_protocol,
    decide_arms,
    evaluate_run,
    mechanical_invariance_check,
    run_arms,
    surrogat_gate,
)
from fgc.decompose.evaluate import (
    GREEN_THRESHOLD,
    PlacementCheck,
    SectionStatus,
    check_safety_distance,
    evaluate,
)
from fgc.decompose.freigang import (
    DEFAULT_WRIST_RADIUS_MM,
    PHI_MAX_CONN_RAD,
    FreigangCheck,
    TeilhoeheCheck,
    check_freigang,
    check_teilhoehe,
    free_length_under_wrist_mm,
    max_printable_height_mm,
    printable_depth_mm,
    sample_angle_rad,
)
from fgc.decompose.kampagne import (
    LABEL_CPU_EXACT,
    LABEL_GPU_CPU_GRENZBAND,
    LABEL_GPU_STICHPROBEN_AUDIT,
    TRAINING_LABEL_SOURCES,
    CampaignCandidate,
    CampaignRun,
    CampaignScope,
    CandidateLabel,
    LabeledSample,
    SamplingPlan,
    campaign_scope,
    dataset_artifact,
    run_campaign,
)
from fgc.decompose.kandidaten import (
    BandRasterKandidat,
    band_raster_kandidat,
    band_raster_kandidaten,
)
from fgc.decompose.limits import (
    LimitFinding,
    ModuleCheck,
    ModuleLimits,
    check_module,
    check_plan,
)
from fgc.decompose.module_pose import (
    ModulePose,
    module_pose,
    placement_frame,
    placement_from_pose,
    pose_plan,
)
from fgc.decompose.objective import (
    CRITERIA,
    DEFAULT_QUANT_STEPS,
    DEFAULT_WEIGHTS,
    KriterienWerte,
    ObjectiveConfig,
    candidate_key,
    compare_candidates,
    objective_from_job,
    quantize,
)
from fgc.decompose.plan import (
    CUT_ORIENTATIONS,
    DECOMPOSITION_KINDS,
    Cut,
    DecompositionPlan,
    Section,
    SectionPlan,
)
from fgc.decompose.printability import (
    REASON_ERROR,
    REASON_NO_GEOMETRY,
    REASON_UNCHECKED,
    REASON_UNREACHABLE,
    VERDICT_TOO_TALL,
    PartPrintability,
)
from fgc.decompose.propose import (
    DEFAULT_CALL_BUDGET,
    MAX_DIVISIONS,
    apply_overrides,
    from_cuts,
    propose,
)
from fgc.decompose.pruefung import (
    FEATURE_SCHEMA_VERSION,
    PRUEF_LABEL_CPU_EXACT,
    PruefCache,
    PruefSample,
    PruefStats,
    assess_plan,
    count_representatives,
    pruef_dataset_block,
)
from fgc.decompose.scorer import (
    INSEL_RASTER_MM,
    BilligerScorer,
    KandidatBewertung,
    Standplatz,
    fugenflaeche_mm2,
    raycast_inselkarte,
    standplatz_gitter,
    volumen_cv,
    wand_maske,
)
from fgc.decompose.strategie import (
    GreedyAchsenVerfeinerung,
    KollisionsGetriebeneVerfeinerung,
    PruefBefund,
    PruefTuer,
    RasterAufgabe,
    RasterWahl,
    ZellenOption,
    ZerlegungsStrategie,
    causing_axis,
    option_menu,
)
from fgc.decompose.surrogat import (
    SURROGATE_FEATURES,
    SURROGATE_MODEL_KIND,
    SURROGATE_SCHEMA_VERSION,
    GradientBoosting,
    SurrogatModell,
    load_surrogat,
    policy_filter,
    save_surrogat,
    train_surrogat,
)

__all__ = [
    "ARM_BEAM",
    "ARM_BEAM_GPU",
    "ARM_BEAM_SURROGAT",
    "ARM_GREEDY",
    "BASE_ARMS",
    "ArmRun",
    "BenchmarkCase",
    "GateDecision",
    "SurrogatGateResult",
    "benchmark_kennzahlen",
    "benchmark_protocol",
    "decide_arms",
    "evaluate_run",
    "mechanical_invariance_check",
    "run_arms",
    "surrogat_gate",
    "CRITERIA",
    "CUT_ORIENTATIONS",
    "DECOMPOSITION_KINDS",
    "DEFAULT_CALL_BUDGET",
    "DEFAULT_QUANT_STEPS",
    "DEFAULT_WEIGHTS",
    "DEFAULT_WRIST_RADIUS_MM",
    "FEATURE_SCHEMA_VERSION",
    "PRUEF_LABEL_CPU_EXACT",
    "LABEL_CPU_EXACT",
    "LABEL_GPU_CPU_GRENZBAND",
    "LABEL_GPU_STICHPROBEN_AUDIT",
    "TRAINING_LABEL_SOURCES",
    "CampaignCandidate",
    "CampaignRun",
    "CampaignScope",
    "CandidateLabel",
    "LabeledSample",
    "SamplingPlan",
    "campaign_scope",
    "dataset_artifact",
    "run_campaign",
    "GREEN_THRESHOLD",
    "INSEL_RASTER_MM",
    "MAX_DIVISIONS",
    "PHI_MAX_CONN_RAD",
    "RELAXATIONSLEITER",
    "SURROGATE_FEATURES",
    "SURROGATE_MODEL_KIND",
    "SURROGATE_SCHEMA_VERSION",
    "VERDICT_TOO_TALL",
    "BandRasterKandidat",
    "BeamSuche",
    "BilligerScorer",
    "GradientBoosting",
    "SurrogatModell",
    "load_surrogat",
    "policy_filter",
    "save_surrogat",
    "train_surrogat",
    "Cut",
    "DecompositionPlan",
    "FreigangCheck",
    "GreedyAchsenVerfeinerung",
    "KollisionsGetriebeneVerfeinerung",
    "PruefBefund",
    "PruefTuer",
    "ZellenOption",
    "causing_axis",
    "option_menu",
    "KandidatBewertung",
    "KriterienWerte",
    "TeilhoeheCheck",
    "LimitFinding",
    "ModuleCheck",
    "ModuleLimits",
    "ModulePose",
    "ObjectiveConfig",
    "PartPrintability",
    "PruefCache",
    "PruefSample",
    "PruefStats",
    "RasterAufgabe",
    "RasterWahl",
    "Standplatz",
    "ZerlegungsStrategie",
    "REASON_ERROR",
    "REASON_NO_GEOMETRY",
    "REASON_UNCHECKED",
    "REASON_UNREACHABLE",
    "PlacementCheck",
    "Section",
    "SectionPlan",
    "SectionStatus",
    "apply",
    "apply_overrides",
    "assess_plan",
    "band_raster_kandidat",
    "band_raster_kandidaten",
    "beam_breite",
    "candidate_key",
    "check_freigang",
    "check_module",
    "check_plan",
    "check_safety_distance",
    "check_teilhoehe",
    "compare_candidates",
    "count_representatives",
    "cuts_to_dicts",
    "decompose_artifact",
    "evaluate",
    "pruef_dataset_block",
    "free_length_under_wrist_mm",
    "from_cuts",
    "fugenflaeche_mm2",
    "max_printable_height_mm",
    "printable_depth_mm",
    "raycast_inselkarte",
    "sample_angle_rad",
    "module_pose",
    "objective_from_job",
    "placement_frame",
    "placement_from_pose",
    "pose_plan",
    "propose",
    "quantize",
    "standplatz_gitter",
    "total_volume",
    "volumen_cv",
    "wand_maske",
]
