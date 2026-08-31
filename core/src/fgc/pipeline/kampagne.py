"""fgc.pipeline.kampagne — Etikettier-Orakel + Orchestrierung der Datenkampagne (Issue #218).

Die **geometrie-behaftete Hälfte** der Kampagne (PRD #183 Stufe 4, US 24): das
produktive **CPU-exakte Etikettier-Orakel** (:func:`cpu_exact_oracle`) über den
Glied-SDF-Prüf-Tür-Weg (#207/#213/#215) und die Orchestrierung
(:func:`run_data_campaign`), die den reinen Kampagnen-Kern
(:mod:`fgc.decompose.kampagne`) mit Provenienz (ADR-004) zum **Datensatz-Artefakt**
verschnürt und ablegt.

Bevorzugt wird GPU-vorsortiert über #205-G2 — **sofern verfügbar**
(:func:`gpu_available`, aktuell stets ``False``, #205 noch nicht integriert). Der
**CPU-only-Fallback (Glied-SDF) ist der gültige Weg** und wartet **nicht** auf
#205: :func:`select_oracle` fällt geräuschlos auf das CPU-exakte Orakel zurück.

Das CPU-Orakel etikettiert **selbst-enthaltend** über synthetische Quaderwände
(kein IFC/Projekt nötig): dieselbe Kette wie die produktive Prüf-Tür
(``from_cuts`` → ``apply`` → ``slice_wall`` → ``build_trajectory`` →
:func:`fgc.pipeline.sectionsim.section_clearance_check`), nur ohne die IFC-Naht —
so ist die Kampagne ein echtes Batch-Skript.

Einheiten strikt nach ADR-006: Millimeter.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fgc.decompose.kampagne import (
    DEFAULT_SECONDS_PER_LABEL,
    LABEL_CPU_EXACT,
    CampaignCandidate,
    CampaignRun,
    CampaignScope,
    CandidateLabel,
    LabelOracle,
    SamplingPlan,
    campaign_scope,
    dataset_artifact,
    run_campaign,
)
from fgc.pipeline.provenance import make_provenance

if TYPE_CHECKING:
    from collections.abc import Callable

    from fgc.domain.tool import ToolDef

_LOG = logging.getLogger(__name__)

__all__ = [
    "CampaignResult",
    "cpu_exact_oracle",
    "gpu_available",
    "run_data_campaign",
    "select_oracle",
]


def gpu_available() -> bool:
    """Ist der GPU-vorsortierte Etikettierpfad (#205-G2) verfügbar? (aktuell stets ``False``).

    Bewusst konservativ ``False``, solange #205 (cuRoboV2-Backend) nicht integriert
    ist — die Kampagne darf **nicht** auf GPU warten (PRD #183 Stufe 4): der
    CPU-only-Fallback (Glied-SDF) ist der gültige Weg. Sobald #205-G2 steht, wird
    diese Naht das GPU-Orakel (Label-Quelle ``gpu+cpu-grenzband``/``gpu+stichproben-audit``)
    zurückgeben.
    """
    return False


def _wall_box(wall: Any):
    """Quader-Mesh einer Wand im Wand-System (x zentriert, z ab Fuß) — wie ``WallSurface``."""
    import trimesh

    box = trimesh.creation.box(extents=[wall.length_mm, wall.thickness_mm, wall.height_mm])
    box.apply_translation([0.0, 0.0, wall.height_mm / 2.0])
    return box


def _verdict_to_dict(verdict: Any) -> dict[str, Any]:
    """Serialisiert das Prüf-Tür-Urteil (``ClearanceVerdict`` | Grund-String) zum Etikett.

    Ein Grund-String (``error``/``no_geometry``, #170) ist **kein** freies Urteil —
    er wird als ``label="ungeprueft"`` markiert (``collides`` bleibt ``None``), sodass
    das Surrogat-Training (#219) solche Zeilen filtern kann.
    """
    if isinstance(verdict, str):
        return {"label": verdict, "collides": None}
    collides = bool(getattr(verdict, "collides", False))
    return {
        "label": "collision" if collides else "printable",
        "collides": collides,
        "min_distance_mm": getattr(verdict, "min_distance_mm", None),
        "penetration_mm": getattr(verdict, "penetration_mm", None),
        "causer_link": getattr(verdict, "causer_link", None),
        "causer_against": getattr(verdict, "causer_against", None),
    }


def cpu_exact_oracle(
    robot_name: str = "doosan_m1013",
    tool: ToolDef | None = None,
    *,
    robots_dir: Path | None = None,
    travel_stride: int | None = None,
) -> LabelOracle:
    """Das **CPU-exakte** Etikettier-Orakel (Glied-SDF, #215) — der gültige Fallback (US 24).

    Baut je Kandidat die **exakte Prüf-Tür** über eine synthetische Quaderwand: dieselbe
    Kette wie der produktive Weg (``from_cuts`` platziert je Reihe, ``apply`` schneidet,
    ``slice_wall`` slict, ``build_trajectory`` simuliert aus der geplanten Platzierung,
    :func:`fgc.pipeline.sectionsim.section_clearance_check` urteilt travel-verdünnt) —
    nur ohne die IFC-Naht. Das Etikett trägt Label-Quelle :data:`LABEL_CPU_EXACT` und die
    gewählte Platzierung (für die Podest-/Platzierungs-Merkmale, #211). **Fail-soft**
    (ADR-013): ein Fehler wird als ``ungeprueft``-Etikett zurückgegeben, kippt aber nie
    den Nachtlauf (der Kampagnen-Runner überspringt es).
    """
    import numpy as np

    from fgc.collision.finding import DEFAULT_TRAVEL_STRIDE
    from fgc.decompose import apply, from_cuts
    from fgc.domain.process_params import ProcessWindow, SliceParams
    from fgc.domain.robot import RobotDef
    from fgc.domain.tool import ToolDef
    from fgc.kinematics.opw import OpwKinematics
    from fgc.pipeline.sectionsim import (
        SectionComputation,
        planned_setup,
        section_clearance_check,
    )
    from fgc.simulation import build_trajectory
    from fgc.simulation.motion import MotionParams
    from fgc.slicer import slice_wall

    robot = RobotDef.load(robot_name, robots_dir)
    if tool is None:
        tool = ToolDef(
            name="(kein)",
            tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
            weight_kg=0.0,
        )
    window = ProcessWindow.load()
    params = SliceParams.from_window(window)
    kin = OpwKinematics.from_robot(robot_name, robots_dir)
    stride = DEFAULT_TRAVEL_STRIDE if travel_stride is None else int(travel_stride)

    def _oracle(candidate: CampaignCandidate) -> CandidateLabel:
        wall = candidate.wall
        section_id = candidate.section_id
        try:
            plan = from_cuts(wall, robot, tool, list(candidate.kandidat.cuts), kind="abschnitt")
            idx = next(
                i for i, sp in enumerate(plan.sections)
                if sp.section.section_id == section_id
            )
            section = plan.sections[idx].section
            placement = plan.sections[idx].placement

            mesh = _wall_box(wall)
            parts = apply(mesh, plan)
            part = parts[idx]
            if len(part.vertices) == 0:
                raise ValueError(f"Abschnitts-Mesh {section_id!r} leer.")

            verts = np.asarray(part.vertices, dtype=float).copy()
            verts[:, 0] -= section.center_x_mm
            verts[:, 2] -= section.z0_mm

            earlier_parts: list[tuple] = []
            for j in range(idx):  # Druckreihenfolge: alles vor idx ist Druckstand
                pv = np.asarray(parts[j].vertices, dtype=float)
                if len(pv) == 0:
                    continue
                pv = pv.copy()
                pv[:, 0] -= section.center_x_mm
                pv[:, 2] -= section.z0_mm
                earlier_parts.append((pv, parts[j].faces))

            toolpath = slice_wall(verts, np.asarray(part.faces), "campaign-wall", params)
            if not toolpath.targets:
                raise ValueError(f"Slicer lieferte keine Targets für {section_id!r}.")

            setup = planned_setup(
                robot_name, placement, tool,
                thickness_mm=wall.thickness_mm, z_offset_mm=section.z0_mm,
            )
            target_dicts = [t.to_dict() for t in toolpath.targets]
            trajectory = build_trajectory(
                target_dicts, setup, kin, pose_source="planned", motion=MotionParams(),
            )
            comp = SectionComputation(
                robot_name=robot_name,
                tool=tool,
                plan_kind="abschnitt",
                section=section,
                verts=verts,
                part_faces=part.faces,
                params=params,
                toolpath=toolpath,
                trajectory=trajectory,
                target_dicts=target_dicts,
                earlier_parts=earlier_parts,
                section_z0_mm=section.z0_mm,
                building_context_applicable=False,
            )
            verdict = section_clearance_check(comp, config=None, travel_stride=stride)
            return CandidateLabel(
                verdict=_verdict_to_dict(verdict),
                label_source=LABEL_CPU_EXACT,
                placement=placement,
            )
        except Exception:  # noqa: BLE001 — Befund, kein Gate: nie den Nachtlauf kippen (#164)
            _LOG.warning(
                "CPU-exaktes Etikett für %r fehlgeschlagen — ungeprueft.", section_id,
                exc_info=True,
            )
            return CandidateLabel(
                verdict={"label": "error", "collides": None}, label_source=LABEL_CPU_EXACT
            )

    return _oracle


def select_oracle(
    robot_name: str = "doosan_m1013",
    tool: ToolDef | None = None,
    *,
    prefer_gpu: bool = True,
    robots_dir: Path | None = None,
    travel_stride: int | None = None,
) -> LabelOracle:
    """Wählt das Etikettier-Orakel: GPU-vorsortiert (falls verfügbar) sonst CPU-exakt (US 24).

    Bevorzugt GPU über #205-G2, **sofern** :func:`gpu_available` — sonst der gültige
    **CPU-only-Fallback** (Glied-SDF), der nicht auf #205 wartet. Da #205 noch nicht
    integriert ist, liefert diese Naht heute stets das CPU-Orakel; die GPU-Zweigstelle
    bleibt als benannte Naht bestehen.
    """
    if prefer_gpu and gpu_available():
        # #205-G2-Naht: künftig das GPU-Orakel (gpu+cpu-grenzband / gpu+stichproben-audit).
        raise NotImplementedError("GPU-Etikettierung (#205) noch nicht integriert.")
    return cpu_exact_oracle(
        robot_name, tool, robots_dir=robots_dir, travel_stride=travel_stride
    )


@dataclass
class CampaignResult:
    """Ergebnis von :func:`run_data_campaign`: Datensatz-Pfad + Artefakt + Lauf + Umfang."""

    dataset_path: Path
    artifact: dict[str, Any]
    run: CampaignRun
    scope: CampaignScope


def run_data_campaign(
    plan: SamplingPlan,
    out_path: Path,
    source: str,
    *,
    oracle: LabelOracle | None = None,
    robot_name: str = "doosan_m1013",
    tool: ToolDef | None = None,
    seconds_per_label: float = DEFAULT_SECONDS_PER_LABEL,
    on_progress: Callable[[int, int], Any] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    limit: int | None = None,
    robots_dir: Path | None = None,
) -> CampaignResult:
    """Fährt die Datenkampagne end-to-end und legt das **Datensatz-Artefakt** ab (US 24).

    Baut (falls ``oracle`` fehlt) das produktive Orakel über :func:`select_oracle`
    (GPU-bevorzugt, CPU-Fallback), etikettiert den Kandidatenraum
    (:func:`fgc.decompose.kampagne.run_campaign`, abbrechbar/Teilstand) und schnürt den
    Datensatz mit **Provenienz** (ADR-004: ``source``, Zeitstempel, Git-Commit),
    Label-Quelle je Etikett und **Herkunftsverteilung** zusammen
    (:func:`fgc.decompose.kampagne.dataset_artifact`). Schreibt das Artefakt nach
    ``out_path`` (auch ein abgebrochener Teilstand wird geschrieben — verwertbar).
    """
    if oracle is None:
        oracle = select_oracle(robot_name, tool, robots_dir=robots_dir)
    scope = campaign_scope(plan, seconds_per_label=seconds_per_label)
    run = run_campaign(
        plan, oracle, on_progress=on_progress, should_cancel=should_cancel, limit=limit
    )
    provenance = make_provenance(source)
    artifact = dataset_artifact(run, plan, provenance, seconds_per_label=seconds_per_label)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    return CampaignResult(dataset_path=out_path, artifact=artifact, run=run, scope=scope)
