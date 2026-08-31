"""Abschnitts-Simulations-Kern — die geteilte Rechenkette der Prüf- und Sim-Türen.

Das benannte Modul für den Weg **Zerlegungsplan-Kontext → Teil-Mesh schneiden →
slicen → Trajektorie → Kollisionskontrolle gegen den Druckstand →
Clearance-Urteil** (Issue #189, Grill 2026-07-13). Vorher lebte diese Kette als
private Helfer-Familie in ``pipeline/actions.py`` — tief im Verhalten, ohne
Interface. Reiner Move + Typisierung: die Semantik ist unangetastet, die
Türen (``simulate_section``, ``advise_collision``, ``check_section_clearance``,
``propose_decomposition``, ``check_decomposition``, ``export_section_drl``)
bleiben in ``actions.py`` und rufen diesen Kern; Persistenz bleibt dort.

Öffentliches Interface: :class:`PlacementContext` (statt des 5er-Tupels),
:class:`SectionSimContext` / :class:`SectionComputation` (konkret typisiert),
:func:`placement_context_for_job`, :func:`section_sim_context`,
:func:`slice_and_simulate_section`, :func:`clearance_verdict` sowie die
fail-soften Befund-Aufrufe :func:`section_collision_finding`,
:func:`section_clearance_check`, :func:`section_context_geometry` und die
Setup-Komposition :func:`planned_setup`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from fgc.collision.finding import ClearanceVerdict, CollisionConfig
    from fgc.decompose import DecompositionPlan, Section
    from fgc.domain.models import Toolpath
    from fgc.domain.process_params import SliceParams
    from fgc.domain.tool import ToolDef
    from fgc.kinematics.opw import OpwKinematics
    from fgc.placement import PlacementOption, WallSurface
    from fgc.simulation import Trajectory

from fgc.domain.robot import RobotDef
from fgc.ifc_io import walls as ifc_walls

_LOG = logging.getLogger(__name__)

__all__ = [
    "PlacementContext",
    "SectionComputation",
    "SectionSimContext",
    "clearance_verdict",
    "collision_pruef_tuer",
    "placement_context_for_job",
    "planned_setup",
    "section_clearance_check",
    "section_collision_finding",
    "section_context_geometry",
    "section_sim_context",
    "slice_and_simulate_section",
]


def _wall_local_basis(vertices_mm):
    """Die Wand-lokale Basis (Länge/Normale/Mittelpunkt/Fuß) aus den Wand-Vertices.

    ``x`` = 2D-PCA-Hauptachse im Grundriss (Wandlänge), ``y`` = Nebenachse
    (Wanddicke), ``z`` = Welt-z ab Wandfuß 0. Vorzeichen deterministisch fixiert
    (Summe ≥ 0). Die eine Quelle der Transformation, damit Wand-Mesh **und**
    Gebäudekontext (Issue #131) mit **derselben** starren Abbildung ins Wandsystem
    landen (gemeinsamer Welt-Ursprung → relative Lage erhalten).
    """
    import numpy as np

    v = np.asarray(vertices_mm, dtype=float)
    z0 = float(v[:, 2].min())
    mean_xy = v[:, :2].mean(axis=0)
    xy = v[:, :2] - mean_xy
    cov = np.cov(xy.T)
    _eigval, eigvec = np.linalg.eigh(cov)  # aufsteigend: [:,0]=Normale, [:,1]=Länge
    normal = eigvec[:, 0]
    along = eigvec[:, 1]
    if along.sum() < 0:
        along = -along
    if normal.sum() < 0:
        normal = -normal
    return along, normal, mean_xy, z0


def _to_wall_local(vertices_mm, basis):
    """Welt-Vertices (mm) über eine :func:`_wall_local_basis` ins Wandsystem bringen."""
    import numpy as np

    along, normal, mean_xy, z0 = basis
    v = np.asarray(vertices_mm, dtype=float)
    xy = v[:, :2] - mean_xy
    return np.column_stack([xy @ along, xy @ normal, v[:, 2] - z0])


def _wall_local_mesh(vertices_mm, faces):
    """Baut aus einer IFC-Wand ein Mesh im Wand-lokalen System (Issue #26).

    Dieselbe Konvention wie `analyze_wall_mesh`/`WallSurface`/`fgc.decompose`
    (ADR-006), Transformation über :func:`_wall_local_basis`. So passt das Mesh zu
    den Schnittebenen des Zerlegungsplans, den `fgc.decompose.apply` schneidet (der
    Plan lebt im selben Wand-lokalen System).
    """
    import numpy as np
    import trimesh

    basis = _wall_local_basis(vertices_mm)
    local = _to_wall_local(vertices_mm, basis)
    return trimesh.Trimesh(vertices=local, faces=np.asarray(faces), process=False)


def planned_setup(
    robot_name: str, placement, tool, *, thickness_mm: float, z_offset_mm: float = 0.0
) -> dict:
    """Baut aus einer geplanten Platzierung + Endeffektor-TCP ein Setup-Dict (Issue #26).

    Die Simulation braucht die Lage Wand↔Roboterbasis. Statt eines gemessenen
    Setups (Antast-Verfahren, ADR-006) wird hier die **geplante** Basis-Lage der
    Platzierung zum Lage-Frame ``wall_to_base`` (base←wand) verrechnet — dieselbe
    Konvention wie `fgc.placement.evaluate`: die Basis-Position kommt aus der
    einen Naht :func:`fgc.placement.base_position_in_wall` (Issue #160 —
    ``standoff_mm`` misst ab der Wandfläche, die Naht rechnet ``+ Dicke/2`` auf
    die Mittelebenen-Koordinate um; ``thickness_mm`` ist darum Pflicht). Der
    Endeffektor-TCP (Flansch→Düse) kommt aus der ToolDef. ``deadtime`` ohne
    Kompensation (t_tot=0): ein Plan trägt keine gemessene Totzeit — die kommt
    erst mit dem echten Setup (Design-Log 2026-07-04).

    ``z_offset_mm`` (Issue #132, Design-Log 2026-07-09) ist die **eine**
    Umrechnungsnaht zwischen der absoluten Aufstellhöhe des Plans
    (``stand_height_mm`` absolut über dem Boden, Boden = Wandfuß) und dem
    abschnitts-lokalen Sim-Frame (Toolpath/Mesh mit z ab Abschnittsfuß):
    ``stand_height_local = stand_height_abs − z_offset`` — negativ erlaubt
    (Basis steht unterhalb des Abschnittsfußes, z. B. am Boden vor Reihe 2).
    Aufrufer übergeben ``section.z0_mm`` (Art „abschnitt"); ``0.0`` (Default)
    für die ganze Wand, die unterste Reihe und Art „modul" (Workstation-relative
    Höhe, ADR-022) — dort byte-gleich zum bisherigen Verhalten.
    """
    import math

    from fgc.domain.models import Frame
    from fgc.placement import base_position_in_wall
    from fgc.simulation import transform

    yaw = float(placement.yaw_rad)
    lateral, base_y, stand_height = base_position_in_wall(placement, thickness_mm)
    base_in_wall = Frame(
        pos_mm=(lateral, base_y, stand_height - float(z_offset_mm)),
        quat=(math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)),
    )
    wall_to_base = transform.invert(base_in_wall)
    return {
        "robot": robot_name,
        "wall_to_base": {"pos_mm": list(wall_to_base.pos_mm), "quat": list(wall_to_base.quat)},
        "tcp": {
            "pos_mm": [float(x) for x in tool.tcp_frame["pos_mm"]],
            "quat": [float(x) for x in tool.tcp_frame["quat"]],
        },
        "deadtime": {"t_tot_s": 0.0, "compensation": "none"},
    }


def section_collision_finding(
    comp: SectionComputation, *, config: CollisionConfig | None, context=None
) -> dict | None:
    """Fail-softer Aufruf der Kollisions-Befund-Tür (Issue #127): Befund, kein Gate.

    Kapselt :func:`fgc.collision.finding.build_section_finding` so, dass **jeder**
    Fehler (fehlende Geo-Extras, fehlendes Kollisions-Artefakt, ein Check-Fehler)
    zu ``None`` wird — die Simulation liefert dann trotzdem ihre Trajektorie, der
    ``meta.collision``-Block fehlt schlicht (Altläufe/Roboter ohne Geometrie laden
    byte-gleich). Kein stiller Sonderpfad: die reine Rechnung lebt in ``finding``.

    Baut das :class:`FindingRequest` aus ``comp``
    (:meth:`SectionComputation.finding_request`); ``config`` und der optionale
    Gebäudekontext ``context`` (Issue #131, ``(vertices_mm, faces)`` im abschnitts-
    lokalen System) reicht der Aufrufer durch.
    """
    try:
        from fgc.collision.finding import build_section_finding

        return build_section_finding(
            comp.robot_name, comp.finding_request(config=config, context=context)
        )
    except Exception:  # noqa: BLE001 — Befund, kein Gate: nie die Simulation kippen
        return None


def section_context_geometry(artifact: dict, job: dict, section):
    """Gebäudekontext (context.json) ins abschnitts-lokale System (Issue #131) — oder None.

    Lädt den Gebäudekontext des Übersichts-Laufs (context.json, Issue #17),
    transformiert ihn über die **Wand-lokale Basis** (dieselbe starre Abbildung wie
    das Teil-Mesh) und verschiebt ihn ins abschnitts-lokale System (x um die
    Abschnittsmitte, z ab Abschnittsfuß) — so liegt er im selben Frame wie der
    Druckstand. Liefert (verts, faces) eines vereinten Meshes oder ``None`` (kein
    context.json / kein Element / Fehler). **Befund, kein Gate**: ein Fehler kippt
    die Simulation nie.
    """
    import numpy as np

    try:
        run_ref = job.get("assessment_run") or artifact.get("overview_run")
        if not run_ref:
            return None
        ctx_path = Path(run_ref) / "context.json"
        if not ctx_path.exists():
            return None
        elements = json.loads(ctx_path.read_text(encoding="utf-8")).get("elements") or []
        if not elements:
            return None

        wall_data = ifc_walls.load_wall(Path(artifact["model_path"]), job["wall_global_id"])
        basis = _wall_local_basis(wall_data.vertices_mm)

        all_v: list = []
        all_f: list = []
        offset = 0
        for el in elements:
            geom = el.get("geometry") or {}
            verts = geom.get("vertices_mm")
            faces = geom.get("faces")
            if not verts or not faces:
                continue
            local = _to_wall_local(verts, basis)
            local[:, 0] -= section.center_x_mm
            local[:, 2] -= section.z0_mm
            all_v.append(local)
            all_f.append(np.asarray(faces, dtype=int) + offset)
            offset += len(local)
        if not all_v:
            return None
        return np.vstack(all_v), np.vstack(all_f)
    except Exception:  # noqa: BLE001 — Befund, kein Gate
        return None


@dataclass
class SectionComputation:
    """Reines Ergebnis der Slice+Trajektorien-Kette eines Abschnitts (ohne Persistenz).

    Die gemeinsame Rechen-Tür von :func:`fgc.pipeline.actions.simulate_section`
    (persistiert einen Lauf) und :func:`fgc.pipeline.actions.advise_collision`
    (liest nur den Kollisions-Befund je Kandidat, #130) — so laufen echte
    Simulation und Advisor-Neubewertung über **dieselbe** Maschinerie (keine
    Parallel-Metrik, ADR-024). ``target_dicts`` sind byte-gleich zu den
    Toolpath-Artefakt-Targets (``Target.to_dict``).
    """

    robot_name: str
    tool: ToolDef
    plan_kind: str
    section: Section
    verts: np.ndarray
    part_faces: np.ndarray
    params: SliceParams
    toolpath: Toolpath
    trajectory: Trajectory
    target_dicts: list[dict]
    #: Fruehere Teile in Druckreihenfolge (Issue #135), je Teil ``(vertices_mm,
    #: faces)`` bereits ins abschnitts-lokale System DIESES Abschnitts verschoben
    #: (x um dessen Mitte, z um dessen Fuss — echte Baender relativ zum Abschnitt).
    #: Leer bei Art „modul" (Workstation ist der Druckort, ADR-022).
    earlier_parts: list[tuple[np.ndarray, np.ndarray]]
    #: Vorgerechnete Leserichtungs-z0 (Issue #191): ``z0`` bei „abschnitt", ``None``
    #: bei „modul" (:meth:`DecompositionPlan.sim_z0_mm`). ``None`` kodiert zugleich,
    #: dass ``meta.section_z0_mm`` im Trajektorien-Artefakt entfällt.
    section_z0_mm: float | None
    #: Gilt der Gebäudekontext als Hindernis (Issue #191,
    #: :attr:`DecompositionPlan.building_context_applicable`)? Falsch bei „modul".
    building_context_applicable: bool

    def finding_request(self, *, config, context=None):
        """Baut das :class:`fgc.collision.finding.FindingRequest` dieser Rechnung (Issue #192).

        Die **eine** Marshaling-Naht Simulation → Kollisionskontrolle: mappt die
        vorgerechneten Felder dieser ``SectionComputation`` auf die gruppierten
        Eingaben der Kollisions-Türen (:func:`build_section_finding`,
        :func:`check_part_clearance`). Die Invarianten je Gruppe stehen an den
        Gruppen-Definitionen im ``finding``-Modul.

        ``config`` = Kollisions-Konfiguration (Gebäudekontext-Schalter,
        Sicherheitsabstand, Freizone); ``context`` = optionaler Gebäudekontext
        ``(vertices_mm, faces)`` im abschnitts-lokalen System (Issue #131). Die
        Höhenlage kommt aus der vorgerechneten Leserichtungs-z0 (#191, ``None`` →
        0.0), die früheren Teile aus :attr:`earlier_parts`.
        """
        from fgc.collision.finding import (
            FindingRequest,
            PartMesh,
            RobotToolRefs,
            SceneInputs,
            ToolpathExcerpt,
            TrajectoryExcerpt,
        )

        return FindingRequest(
            trajectory=TrajectoryExcerpt(
                base_frame=self.trajectory.meta["base_frame"],
                samples=self.trajectory.samples,
                target_times_s=self.trajectory.target_times or [],
            ),
            toolpath=ToolpathExcerpt(
                targets=self.target_dicts,
                layer_height_mm=self.params.layer_height_mm,
                n_layers=int(self.toolpath.summary()["n_layers"]),
            ),
            part=PartMesh(vertices_mm=self.verts, faces=self.part_faces),
            scene=SceneInputs(
                mode=self.plan_kind,
                section_z0_mm=self.section_z0_mm or 0.0,
                earlier_parts=self.earlier_parts,
                context=context,
            ),
            refs=RobotToolRefs(tool=self.tool),
            config=config,
        )


@dataclass
class SectionSimContext:
    """Loop-invarianter Unterbau der Slice+Sim-Kette **eines** Abschnitts.

    Alles, was ein ``fgc.collision.advisor.Override`` *nicht* verändert: Plan,
    IFC-Wand laden, Zerlegung (``apply`` schneidet die ganze Wand!), die
    Verschiebung ins abschnitts-lokale System, frühere Teile und die Basis-
    Sliceparameter (ohne Orientierung). Der Kollisions-Advisor baut den Kontext
    **einmal** und reicht ihn an alle Kandidaten-Simulationen — vorher lief
    dieser Unterbau je Kandidat neu (~18× je Beratung, Issue #150-Befund).
    ``toolpath_cache`` teilt den geslicten Toolpath je Orientierung
    ``(lead_rad, kipp_rad)``: IK- und Platzierungs-Kandidaten ändern den
    Toolpath nicht und slicen daher nicht erneut.
    """

    robot_name: str
    tool: ToolDef
    plan: DecompositionPlan
    section: Section
    #: Geplante Platzierung des Teils (vor einem etwaigen Advisor-Override).
    placement: PlacementOption
    verts: np.ndarray
    part_faces: np.ndarray
    earlier_parts: list[tuple[np.ndarray, np.ndarray]]
    #: Vorgerechnete Leserichtungs-z0 (Issue #191, Muster wie ``earlier_parts``):
    #: echte Höhenlage ``z0`` bei Art „abschnitt", ``None`` bei „modul``
    #: (:meth:`DecompositionPlan.sim_z0_mm`). Die eine z0-Wahrheit für Setup- und
    #: Befund-Naht — kein inline ``kind``-Vergleich mehr in der Kern-Tür.
    section_z0_mm: float | None
    #: SliceParams aus Fenster + Job-Overrides, Orientierung noch ungesetzt.
    base_params: SliceParams
    kin: OpwKinematics
    toolpath_cache: dict[tuple[float, float], Toolpath] = field(default_factory=dict)


def section_sim_context(
    artifact: dict,
    job: dict,
    section_id: str,
    *,
    workstations_dir: Path | None = None,
    plan: DecompositionPlan | None = None,
) -> SectionSimContext:
    """Baut den loop-invarianten Unterbau für :func:`slice_and_simulate_section`.

    ``plan`` kann vorgereicht werden (der Advisor hat ihn schon rekonstruiert) —
    sonst wird er wie bisher über :func:`fgc.pipeline.actions.plan_for_job`
    gebaut. Wirft ``ValueError`` bei unbekanntem Abschnitt oder leerem Teil-Mesh.
    """
    import numpy as np

    from fgc.decompose import apply
    from fgc.domain.process_params import ProcessWindow, SliceParams, section_slice_overrides
    from fgc.kinematics.opw import OpwKinematics

    pc = placement_context_for_job(job)
    if plan is None:
        from fgc.pipeline.actions import plan_for_job

        plan = plan_for_job(
            job, pc.wall, pc.robot, pc.tool,
            strict_overrides=False, workstations_dir=workstations_dir,
        ).plan

    idx = next(
        (i for i, sp in enumerate(plan.sections) if sp.section.section_id == section_id),
        None,
    )
    if idx is None:
        known = [sp.section.section_id for sp in plan.sections]
        raise ValueError(
            f"Abschnitt {section_id!r} nicht im Zerlegungsplan des Druckjobs — "
            f"vorhanden: {known}. Zuerst den Schnittplan erzeugen (Reiter Druckplan)."
        )
    section = plan.sections[idx].section
    placement = plan.sections[idx].placement

    # Abschnitts-Teil-Mesh aus dem Wand-lokalen Mesh schneiden (decompose.apply).
    wall_data = ifc_walls.load_wall(Path(artifact["model_path"]), job["wall_global_id"])
    mesh = _wall_local_mesh(wall_data.vertices_mm, wall_data.faces)
    parts = apply(mesh, plan)
    part = parts[idx]
    if len(part.vertices) == 0:
        raise ValueError(f"Abschnitts-Mesh {section_id!r} leer — Schnittplan prüfen.")

    # Ins abschnitts-lokale System verschieben (x um Mitte, z ab Fuß).
    verts = np.asarray(part.vertices, dtype=float).copy()
    verts[:, 0] -= section.center_x_mm
    verts[:, 2] -= section.z0_mm

    # Frühere Teile in Druckreihenfolge (Issue #135) — für den Kollisions-Befund
    # als volle Hindernisse auf ihren echten Bändern: dieselbe Verschiebung ins
    # abschnitts-lokale System DIESES Abschnitts (x um dessen Mitte, z um dessen
    # Fuß). plan.sections liegt in Druckreihenfolge (unten → oben, links → rechts),
    # also sind genau die Teile vor `idx` schon gedruckt. Bei Art „modul" leer
    # (die Workstation ist der Druckort — dort steht kein früheres Teil, ADR-022):
    # `plan.prints_in_place` ist der gemeinsame Member mit `_obstacle_load` (#191).
    earlier_parts: list[tuple] = []
    if plan.prints_in_place:
        for j in range(idx):
            pv = np.asarray(parts[j].vertices, dtype=float)
            if len(pv) == 0:
                continue
            pv = pv.copy()
            pv[:, 0] -= section.center_x_mm
            pv[:, 2] -= section.z0_mm
            earlier_parts.append((pv, parts[j].faces))

    # Abschnitts-effektive Slice-Basisparameter (Issue #188): global + Abschnitts-
    # Override über die eine Auflösung (effective_section_params) — Abschnitte ohne
    # Override rechnen byte-gleich wie mit job_slice_overrides (Regressionsanker).
    window = ProcessWindow.load()
    base_params = SliceParams.from_window(window, **section_slice_overrides(job, section_id))

    return SectionSimContext(
        robot_name=pc.robot_name,
        tool=pc.tool,
        plan=plan,
        section=section,
        placement=placement,
        verts=verts,
        part_faces=part.faces,
        earlier_parts=earlier_parts,
        section_z0_mm=plan.sim_z0_mm(section),
        base_params=base_params,
        kin=OpwKinematics.from_robot(pc.robot_name),
    )


def slice_and_simulate_section(
    artifact: dict,
    job: dict,
    section_id: str,
    *,
    override=None,
    workstations_dir: Path | None = None,
    ctx: SectionSimContext | None = None,
) -> SectionComputation:
    """Slict + simuliert **einen** Abschnitt in-memory (kein Lauf) — die geteilte Kern-Tür.

    Baut aus dem Zerlegungsplan das Abschnitts-Teil-Mesh, slict es und simuliert die
    Trajektorie aus der geplanten Platzierung (``pose_source="planned"``) — exakt die
    Kette, die ``simulate_section`` persistiert. Ein optionaler ``fgc.collision.advisor.
    Override`` verlegt für **diesen** Aufruf einen der drei Hebel (Platzierung,
    Kipp/Lead-Orientierung, IK-Konfiguration), ohne etwas zu schreiben — so probiert
    der Kollisions-Advisor jeden Kandidaten mit derselben Simulation durch.

    ``ctx`` (Advisor-Schleife): ein vorgebauter :class:`SectionSimContext` desselben
    Abschnitts überspringt den loop-invarianten Unterbau (IFC laden, Zerlegung,
    Basis-Parameter) — Ergebnis bit-identisch, nur schneller. Ohne ``ctx`` entsteht
    er hier (Einzelaufruf: Verhalten unverändert).

    Wirft ``ValueError`` bei unbekanntem Abschnitt, leerem Teil-Mesh oder leerem Toolpath.
    """
    import math
    from dataclasses import replace as _replace

    import numpy as np

    from fgc.domain.process_params import effective_section_params, section_orientation
    from fgc.kinematics import IkConfigFilter
    from fgc.simulation import build_trajectory
    from fgc.simulation.motion import motion_from_job
    from fgc.slicer import slice_wall

    if ctx is None:
        ctx = section_sim_context(
            artifact, job, section_id, workstations_dir=workstations_dir,
        )

    # Advisor-Hebel „Platzierung": die geplante Lage feldweise übersteuern (nur für
    # diesen Kandidaten; das Anwenden schreibt später über placement-override).
    placement = ctx.placement
    if override is not None and override.placement:
        placement = _replace(placement, **{k: float(v) for k, v in override.placement.items()})

    # Bahn-relativer Anstellwinkel (Issue #61); Advisor-Hebel „Kipp/Lead" übersteuert
    # ihn versuchsweise (absolute Grad), sonst gilt die **abschnitts-effektive**
    # Orientierung (Issue #188: global + Abschnitts-Override, dieselbe Auflösung
    # wie ik_config unten — kein Drift mehr zwischen Persistenz und Kern-Tür).
    if override is not None and override.orientation:
        lead_rad = math.radians(float(override.orientation.get("lead_deg", 0.0)))
        kipp_rad = math.radians(float(override.orientation.get("kipp_deg", 0.0)))
    else:
        _ori = section_orientation(job, section_id)
        lead_rad, kipp_rad = _ori.lead_rad, _ori.kipp_rad
    params = _replace(ctx.base_params, lead_rad=lead_rad, kipp_rad=kipp_rad)

    # Nur die Orientierung formt den Toolpath — IK-/Platzierungs-Kandidaten teilen
    # den geslicten Stand über den Kontext-Cache (Einzelaufruf: ein Eintrag).
    toolpath = ctx.toolpath_cache.get((lead_rad, kipp_rad))
    if toolpath is None:
        toolpath = slice_wall(
            ctx.verts, np.asarray(ctx.part_faces), job["wall_global_id"], params,
        )
        if not toolpath.targets:
            raise ValueError(
                f"Slicer lieferte keine Targets für Abschnitt {section_id!r} "
                "(Konturen degeneriert?)."
            )
        ctx.toolpath_cache[(lead_rad, kipp_rad)] = toolpath

    # Umrechnungsnaht #132: die absolute Aufstellhöhe des Plans ins abschnitts-
    # lokale Sim-Frame (z ab Abschnittsfuß) — nur bei Art „abschnitt"; „modul"
    # trägt eine Workstation-relative Höhe (ADR-022) und bleibt unangetastet.
    # `section_z0_mm` ist die vorgerechnete Leserichtungs-z0 (#191, None → 0.0).
    setup = planned_setup(
        ctx.robot_name, placement, ctx.tool,
        thickness_mm=ctx.plan.wall.thickness_mm,
        z_offset_mm=ctx.section_z0_mm or 0.0,
    )
    # Wählbare IK-Konfiguration (Issue #129): der effektive Block dieses Abschnitts,
    # bzw. der Advisor-Hebel „IK-Konfiguration" versuchsweise (absoluter Block).
    if override is not None and override.ik_config is not None:
        ik_block = override.ik_config
    else:
        ik_block = effective_section_params(job, section_id).get("ik_config")
    config_filter = IkConfigFilter.from_block(ik_block)
    target_dicts = [t.to_dict() for t in toolpath.targets]
    trajectory = build_trajectory(
        target_dicts, setup, ctx.kin, pose_source="planned",
        motion=motion_from_job(job), config_filter=config_filter,
    )

    return SectionComputation(
        robot_name=ctx.robot_name,
        tool=ctx.tool,
        plan_kind=ctx.plan.kind,
        section=ctx.section,
        verts=ctx.verts,
        part_faces=ctx.part_faces,
        params=params,
        toolpath=toolpath,
        trajectory=trajectory,
        target_dicts=target_dicts,
        earlier_parts=ctx.earlier_parts,
        section_z0_mm=ctx.section_z0_mm,
        building_context_applicable=ctx.plan.building_context_applicable,
    )


def _wall_surface_from_assessment(assessment_run: str, wall_global_id: str) -> WallSurface:
    """Liest die Wandmaße (Länge/Höhe/Dicke) aus candidates.json des Befund-Laufs.

    Baut daraus die `WallSurface`, die das placement-Modul zur Erreichbarkeits-
    Bewertung braucht (nur die abzufahrende Fläche zählt, nicht die volle
    Mesh-Geometrie). Wirft `ValueError`, wenn der Lauf, das Artefakt oder die
    Wand fehlt.
    """
    from fgc.placement import WallSurface

    candidates_path = Path(assessment_run) / "candidates.json"
    if not candidates_path.exists():
        raise ValueError(
            f"Befund-Lauf ohne candidates.json: {candidates_path} — Wand nicht bewertbar."
        )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    wall = next(
        (w for w in candidates["walls"] if w["global_id"] == wall_global_id), None
    )
    if wall is None:
        raise ValueError(
            f"Wand {wall_global_id!r} nicht im Befund-Lauf {assessment_run} gefunden."
        )
    dims = wall.get("dimensions_mm", {})
    return WallSurface(
        length_mm=float(dims.get("length", 0.0)),
        height_mm=float(dims.get("height", 0.0)),
        thickness_mm=float(dims.get("thickness", 0.0)),
    )


@dataclass(frozen=True)
class PlacementContext:
    """Kinematik-Umgebung eines Druckjobs: Roboter, Endeffektor, Wandfläche (Issue #189).

    Ersetzt das frühere 5er-Tupel von ``_placement_context_for_job`` (15
    positionsabhängige Entpack-Stellen) durch benannte Felder. ``tool_name`` ist
    nie ``None`` (Fallback ``"(kein)"`` bei fehlendem Endeffektor).
    """

    robot: RobotDef
    robot_name: str
    tool: ToolDef
    tool_name: str
    wall: WallSurface


def placement_context_for_job(job: dict) -> PlacementContext:
    """Lädt Roboter, Endeffektor und Wandfläche aus dem Druckjob (Issue #22/#23).

    Gemeinsame Grundlage für `evaluate_placements` (Bewertungsmodus) und
    `suggest_placement` (Optimalvorschlag) — beide brauchen dieselbe
    Kinematik-Umgebung, nur die Aufstellmöglichkeiten unterscheiden sich.
    Liefert einen :class:`PlacementContext`.

    Wirft `ValueError` bei fehlendem Roboter oder fehlendem Befund-Lauf.
    """
    from fgc.domain.tool import ToolDef

    robot_name = job.get("robot")
    if not robot_name:
        raise ValueError(
            "Kein Roboter im Druckjob gesetzt — Platzierung braucht die Kinematik "
            "(zuerst im Reiter Roboter bewerten, Issue #20)."
        )
    robot = RobotDef.load(robot_name)

    tool_name = job.get("tool")
    if tool_name:
        tool = ToolDef.load(tool_name)
    else:
        # Kein Endeffektor gewählt: Düse am Flansch (Null-TCP) — Platzierung
        # bleibt bewertbar, der TCP-Versatz verschiebt die Ziele nur.
        tool = ToolDef(
            name="(kein)",
            tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
            weight_kg=0.0,
        )

    assessment_run = job.get("assessment_run")
    if not assessment_run:
        raise ValueError(
            "Kein Befund-Lauf im Druckjob (assessment_run) — Wandmaße unbekannt."
        )
    wall = _wall_surface_from_assessment(assessment_run, job["wall_global_id"])
    return PlacementContext(
        robot=robot,
        robot_name=robot_name,
        tool=tool,
        tool_name=(tool_name or "(kein)"),
        wall=wall,
    )


def section_clearance_check(
    comp: SectionComputation, *, config, travel_stride
) -> ClearanceVerdict | str:
    """Fail-softer Aufruf der Pruef-Tuer (:func:`fgc.collision.finding.check_part_clearance`).

    **Befund, kein Gate** — kippt nie den Aufrufer, unterscheidet aber die zwei
    Ausgaenge (Issue #170): die Pruef-Tuer liefert ihr :class:`ClearanceVerdict`,
    ODER — sie war **unzuständig** (kein Kollisions-Geometrie-Artefakt, Altprojekt) —
    :data:`REASON_NO_GEOMETRY`, ODER — die Pruefung ist **fehlgeschlagen** (Ausnahme:
    Regression, fehlende Bibliothek) — :data:`REASON_ERROR`, **mit Log-Eintrag**. So
    ist ein totes Pruefsystem nicht mehr von einem unzustaendigen zu unterscheiden
    (B5/B12). Baut aus einer bereits simulierten Abschnitts-Rechnung (``comp``) das
    verduennte Urteil, mit **derselben** Hindernis-Wahrheit wie die echte Simulation.
    """
    from fgc.decompose.printability import REASON_ERROR, REASON_NO_GEOMETRY

    try:
        from fgc.collision.finding import check_part_clearance

        verdict = check_part_clearance(
            comp.robot_name,
            comp.finding_request(config=config),
            travel_stride=travel_stride,
        )
    except Exception:  # noqa: BLE001 — Befund, kein Gate: nie den Aufrufer kippen
        _LOG.warning(
            "Pruef-Tuer der Zerlegung fehlgeschlagen (Roboter %r) — Teil-Zustand "
            "'ungeprueft' (error), kein 'frei'.",
            getattr(comp, "robot_name", "?"),
            exc_info=True,
        )
        return REASON_ERROR
    # None = die Pruef-Tuer lief, war aber unzustaendig (kein Kollisions-Geometrie-
    # Artefakt). Das ist NICHT dasselbe wie ein Absturz (Issue #170).
    return REASON_NO_GEOMETRY if verdict is None else verdict


def _override_for_option(option, base_placement):
    """Uebersetzt eine :class:`fgc.decompose.strategie.ZellenOption` in einen Advisor-Override.

    Der Platzierungs-Hebel ist ein **Delta** auf die je Zelle gesuchte Basis-Lage
    (Issue #165), der Advisor-Override erwartet **absolute** Werte (bit-identische
    Neu-Simulation, #130) — die Uebersetzung addiert das Delta auf ``base_placement``
    (die geplante Section-Platzierung). Der IK-Hebel geht als Tri-State-Block durch.
    ``None`` (Basis) ⇒ kein Override.
    """
    from fgc.collision.advisor import Override

    if option.ik_block:
        return Override(ik_config=dict(option.ik_block))
    if option.placement_delta:
        d = option.placement_delta
        abs_pl: dict[str, float] = {}
        if "standoff_mm" in d:
            abs_pl["standoff_mm"] = base_placement.standoff_mm + float(d["standoff_mm"])
        if "stand_height_mm" in d:
            abs_pl["stand_height_mm"] = base_placement.stand_height_mm + float(
                d["stand_height_mm"]
            )
        if "lateral_mm" in d:
            abs_pl["lateral_mm"] = base_placement.lateral_mm + float(d["lateral_mm"])
        return Override(placement=abs_pl)
    return None


def collision_pruef_tuer(
    artifact: dict,
    job: dict,
    *,
    workstations_dir: Path | None = None,
    travel_stride: int | None = None,
):
    """Das **produktive** Pruef-Tuer-Orakel der kollisionsgetriebenen Verfeinerung (#165).

    Baut die Closure ``(BandRasterKandidat, row_index, ZellenOption) → ClearanceVerdict |
    None``, die :class:`fgc.decompose.strategie.KollisionsGetriebeneVerfeinerung` (an der
    #216-Naht) treibt. Fuer **ein** Kandidaten-Raster + eine Hoehenreihe urteilt sie ueber
    den **Repraesentanten** dieser Reihe (die unguenstigste Zelle — die letzte in
    Druckreihenfolge, mit den meisten frueheren Teilen als Druckstand) **von der Option aus**:

    - die Kandidaten-Schnitte werden als temporaere Plan-Eingaben in eine Job-Kopie gelegt
      und durch **dieselbe** Kern-Tuer (:func:`section_sim_context` → :func:`plan_for_job`,
      #112/#189) geschickt — die **SectionSimContext-Wiederverwendung** (#189), nichts
      dupliziert;
    - die Zell-Option (IK/Platzierung) wird als Advisor-Override (:func:`_override_for_option`)
      versuchsweise angewandt (kein Schreiben) und die Bahn neu simuliert
      (:func:`slice_and_simulate_section`);
    - das Urteil kommt aus derselben Travel-verduennten Pruef-Tuer wie Stufe 2
      (:func:`section_clearance_check`, #162) — **keine** Parallel-Metrik.

    **Befund, kein Gate / fail-soft** (ADR-013): jeder Fehler und jedes „unzustaendig/
    fehlgeschlagen"-Urteil (kein Kollisions-Geometrie-Artefakt, Regression) liefert
    ``None`` — die Strategie faellt dann ehrlich auf den Achsen-Greedy zurueck, nie ein
    geratenes „frei". Read-only: es wird nichts persistiert.

    Kosten: **je Aufruf** eine Abschnitts-Simulation (~Sekunden, #215/AP-1) — deshalb
    zaehlt die Strategie die Aufrufe hart gegen das Kontingent (#178). Der Aufrufer
    (``propose_decomposition``) faehrt sie als Hintergrundlauf (#145-Muster).
    """
    from fgc.collision.finding import DEFAULT_TRAVEL_STRIDE

    stride = DEFAULT_TRAVEL_STRIDE if travel_stride is None else int(travel_stride)

    def _tuer(kandidat, row_index: int, option):
        try:
            n_v = kandidat.n_length
            # Repraesentant der Reihe: letzte Spalte (Druckreihenfolge unten→oben,
            # links→rechts) — die unguenstigste Zelle (meiste fruehere Teile).
            order = row_index * n_v + n_v
            section_id = f"abschnitt-{order}"
            # Zerlegungsart des (Kandidaten-)Jobs durchreichen (Issue #237): fuer
            # Art „modul" urteilt die Tuer damit am Druckort (feste Workstation-
            # Platzierung, ADR-022) statt faelschlich in-place an der Wand.
            temp_job = {
                **job,
                "decomposition_kind": job.get("decomposition_kind", "abschnitt"),
                "cuts": [
                    {"orientation": c.orientation, "position_mm": c.position_mm}
                    for c in kandidat.cuts
                ],
                "joint_offset_mm": 0.0,
                "section_overrides": [],
            }
            ctx = section_sim_context(
                artifact, temp_job, section_id, workstations_dir=workstations_dir
            )
            override = _override_for_option(option, ctx.placement)
            comp = slice_and_simulate_section(
                artifact, temp_job, section_id,
                override=override, ctx=ctx, workstations_dir=workstations_dir,
            )
            verdict = section_clearance_check(comp, config=None, travel_stride=stride)
        except Exception:  # noqa: BLE001 — Befund, kein Gate: nie den Zerlegungslauf kippen
            _LOG.warning(
                "Kollisions-Pruef-Tuer der Verfeinerung fehlgeschlagen (Reihe %s) — "
                "Zelle 'unzustaendig' (Greedy-Fallback), kein 'frei'.",
                row_index, exc_info=True,
            )
            return None
        # Grund-String (no_geometry/error, #170) ⇒ unzustaendig ⇒ None (Strategie faellt zurueck).
        return None if isinstance(verdict, str) else verdict

    return _tuer


def clearance_verdict(
    artifact: dict,
    job: dict,
    plan: DecompositionPlan | None,
    section_id: str,
    *,
    workstations_dir: Path | None = None,
    travel_stride: int | None = None,
) -> ClearanceVerdict | str:
    """Fail-softes Prüf-Tür-Urteil **eines** Teils (Issue #164, Stufe 2).

    Baut den loop-invarianten Unterbau (:class:`SectionSimContext`, Reuse aus #162)
    **einmal** für dieses Teil, slict + simuliert es und urteilt mit der Travel-
    verdünnten :func:`fgc.collision.finding.check_part_clearance`. **Befund, kein
    Gate** (ADR-013) — kippt nie den Zerlegungslauf, unterscheidet aber (Issue #170)
    das Ergebnis: das :class:`ClearanceVerdict`, :data:`REASON_NO_GEOMETRY` (unzustaendig)
    oder :data:`REASON_ERROR` (Aufbau/Simulation der Pruef-Tür fehlgeschlagen — **mit
    Log-Eintrag**). Read-only: es wird nichts geschrieben.
    """
    from fgc.collision.finding import DEFAULT_TRAVEL_STRIDE
    from fgc.decompose.printability import REASON_ERROR

    stride = DEFAULT_TRAVEL_STRIDE if travel_stride is None else int(travel_stride)
    try:
        ctx = section_sim_context(
            artifact, job, section_id, workstations_dir=workstations_dir, plan=plan
        )
        comp = slice_and_simulate_section(
            artifact, job, section_id, workstations_dir=workstations_dir, ctx=ctx
        )
    except Exception:  # noqa: BLE001 — Befund, kein Gate: nie den Zerlegungslauf kippen
        _LOG.warning(
            "Aufbau/Simulation der Pruef-Tuer fuer Teil %r fehlgeschlagen — "
            "Teil-Zustand 'ungeprueft' (error), kein 'frei'.",
            section_id,
            exc_info=True,
        )
        return REASON_ERROR
    return section_clearance_check(comp, config=None, travel_stride=stride)
