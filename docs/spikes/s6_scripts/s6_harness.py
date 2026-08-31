"""S6-Harness — Grob-Check (``fgc.collision.coarse.path_collides``) vs. vollen
Kollisionsbefund (``fgc.collision.finding.build_section_finding``) je **Teil** der
realen Denkmal-Zerlegung (Modul, 16 Teile).

Warum so: Der Grob-Check ist Kandidat fuer den Kollisions-Constraint der
Zerlegung (#141). Diese Datei leitet **beide** Urteile je Teil aus **demselben
Produktivpfad** ab wie die echte GUI — nicht aus handgeschriebenen Konstanten:

- Der **Zerlegungsplan** (16 Module + je feste Workstation-Platzierung) kommt aus
  ``actions.plan_for_job`` — dieselbe Tuer, die ``simulate_section`` nutzt.
- Der **volle Befund** je Teil kommt aus ``actions._slice_and_simulate_section``
  (in-memory, kein Lauf geschrieben) + ``finding.build_section_finding`` — exakt
  die Kette, die ``simulate_section`` persistiert (mode="modul", section_z0=0,
  keine frueheren Teile, kein Boden — ADR-022).
- Das **Grob-Urteil** je Teil kommt aus ``coarse.path_collides`` mit der
  **Teil-Wandflaeche** (``Section.as_surface(thickness, z_offset=0)`` — Modul-
  Konvention, das Teil steht am Druckort) + der Teil-Platzierung + Roboter/Tool/
  Orientierung aus demselben Job (``_placement_context_for_job``/``job_orientation``).

Aufruf (venv, Repo-Root ``C:\\Users\\tbartlog\\Documents\\LokalPython\\RoboPrintIFC``)::

    ./.venv/Scripts/python.exe docs/spikes/s6_scripts/s6_harness.py

Direkt aufgerufen druckt es den Plan-Kontext (Sektionen, Flaeche, Platzierung)
und die gespeicherten ``meta.collision``-Zahlen der beiden vorhandenen Laeufe —
ein Selbsttest der Datenbasis. ``s6_validate.py`` importiert ``build_context`` /
``coarse_verdict`` / ``full_finding``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_JSON = REPO_ROOT / "projects" / "denkmal" / "project.json"


@dataclass
class Context:
    """Alles, was der Produktivpfad je Teil braucht — einmal beschafft."""

    artifact: dict
    job: dict
    robot: Any
    robot_name: str
    tool: Any
    ori: Any
    geo: Any
    plan: Any  # DecompositionPlan
    thickness_mm: float


def build_context() -> Context:
    """Beschafft Roboter/Tool/Orientierung/Geometrie + den realen Zerlegungsplan.

    Rein lesend, ueber die Produktiv-Tueren — kein Lauf, keine Mutation.
    """
    from fgc.collision.robot_geometry import load_robot_collision_geometry
    from fgc.domain.process_params import job_orientation
    from fgc.pipeline import actions as A

    artifact = json.loads(PROJECT_JSON.read_text(encoding="utf-8"))
    job = artifact["print_jobs"][0]

    robot, robot_name, tool, _tool_name, wall = A._placement_context_for_job(job)
    ori = job_orientation(job)
    geo = load_robot_collision_geometry(robot_name)
    plan = A.plan_for_job(job, wall, robot, tool, strict_overrides=False).plan
    return Context(
        artifact=artifact,
        job=job,
        robot=robot,
        robot_name=robot_name,
        tool=tool,
        ori=ori,
        geo=geo,
        plan=plan,
        thickness_mm=float(wall.thickness_mm),
    )


def coarse_verdict(
    ctx: Context,
    section,
    placement,
    *,
    penetration_mm: float = 20.0,
    spacing_mm: float | None = None,
) -> tuple[bool, float, int]:
    """Grob-Urteil eines Teils: (kollidiert?, elapsed_ms, n_posen).

    Baut die **Teil-Wandflaeche** wie das Modul real gedruckt wird: das Teil
    steht am Druckort, Fuss auf der Arbeitsflaeche → ``z_offset=0`` (Modul-
    Konvention, ``as_surface``-Doc). ``spacing_mm``/``penetration_mm`` sind die
    Sensitivitaets-Hebel; Defaults = Produktiv-Defaults (``_COARSE_FRACTION``-
    Raster, ``DEFAULT_PENETRATION_MM``).
    """
    from fgc.collision.coarse import path_collides
    from fgc.placement.evaluate import SAMPLE_SPACING_MM, _flange_targets, _nozzle_rotation

    surface = section.as_surface(ctx.thickness_mm, z_offset_mm=0.0)

    # n_posen des groben Rasters (dieselbe Rechnung wie in path_collides).
    coarse = spacing_mm or (
        max(surface.length_mm, surface.height_mm) * 0.5 or SAMPLE_SPACING_MM
    )
    r_nozzle = _nozzle_rotation(ctx.ori.lead_rad, ctx.ori.kipp_rad)
    frames, _, _ = _flange_targets(surface, ctx.tool, placement, coarse, r_nozzle)
    n_poses = len(frames)

    t0 = time.perf_counter()
    hit = path_collides(
        surface, ctx.robot, ctx.tool, placement, ctx.geo,
        lead_rad=ctx.ori.lead_rad, kipp_rad=ctx.ori.kipp_rad,
        penetration_mm=penetration_mm, spacing_mm=spacing_mm,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return bool(hit), elapsed_ms, n_poses


def full_finding(ctx: Context, section_id: str) -> dict:
    """Voller Befund eines Teils ueber den Produktivpfad (kein Lauf geschrieben).

    ``_slice_and_simulate_section`` (in-memory) → ``build_section_finding`` mit
    exakt den Argumenten, die ``simulate_section`` fuer Art „modul" setzt
    (mode="modul", section_z0=0, keine frueheren Teile). Liefert das
    ``report_to_dict``-Dict (n_red/n_yellow/n_green, min_distance_mm,
    causer_link[], causer_against[], intervals[]).
    """
    from fgc.collision.finding import CollisionConfig, build_section_finding
    from fgc.pipeline import actions as A

    comp = A._slice_and_simulate_section(ctx.artifact, ctx.job, section_id)
    toolpath_targets = [t.to_dict() for t in comp.toolpath.targets]
    finding = build_section_finding(
        comp.robot_name,
        base_frame=comp.trajectory.meta["base_frame"],
        samples=comp.trajectory.samples,
        target_times_s=comp.trajectory.target_times or [],
        targets=toolpath_targets,
        part_vertices_mm=comp.verts,
        part_faces=comp.part_faces,
        layer_height_mm=float(comp.params.layer_height_mm),
        n_layers=int(comp.toolpath.summary()["n_layers"]),
        mode=comp.plan_kind,  # "modul"
        tool=comp.tool,
        config=CollisionConfig(),
        section_z0_mm=0.0,
        earlier_parts=comp.earlier_parts,  # leer bei modul
    )
    return finding


def saved_meta_collision() -> dict[str, dict]:
    """Liest den gespeicherten ``meta.collision``-Block der beiden Section-Laeufe."""
    artifact = json.loads(PROJECT_JSON.read_text(encoding="utf-8"))
    job = artifact["print_jobs"][0]
    out: dict[str, dict] = {}
    for sr in job.get("section_runs", []):
        sid = sr["section_id"]
        traj = Path(sr["run"]) / "trajectory.json"
        if not traj.exists():
            out[sid] = {"error": f"kein trajectory.json: {traj}"}
            continue
        meta = json.loads(traj.read_text(encoding="utf-8")).get("meta", {})
        col = meta.get("collision")
        if col is None:
            out[sid] = {"error": "kein meta.collision"}
            continue
        out[sid] = {
            "run": sr["run"],
            "n_red": col.get("n_red"),
            "n_yellow": col.get("n_yellow"),
            "n_green": col.get("n_green"),
            "min_distance_mm": col.get("min_distance_mm"),
            "mode": (col.get("config") or {}).get("mode"),
        }
    return out


if __name__ == "__main__":
    ctx = build_context()
    print(f"Zerlegungsart : {ctx.plan.kind}")
    print(f"n_length x n_height : {ctx.plan.n_length} x {ctx.plan.n_height}")
    print(f"Teile : {len(ctx.plan.sections)}")
    print(f"Wanddicke_mm : {ctx.thickness_mm}")
    print(f"lead/kipp rad : {ctx.ori.lead_rad} / {ctx.ori.kipp_rad}")
    print()
    print(f"{'section_id':<14}{'len':>8}{'hgt':>8}{'z0':>8}"
          f"{'lat':>8}{'stoff':>8}{'sthgt':>8}")
    for sp in ctx.plan.sections:
        s, p = sp.section, sp.placement
        print(f"{s.section_id:<14}{s.length_mm:>8.1f}{s.height_mm:>8.1f}{s.z0_mm:>8.1f}"
              f"{p.lateral_mm:>8.1f}{p.standoff_mm:>8.1f}{p.stand_height_mm:>8.1f}")
    print()
    print("gespeicherte meta.collision der Section-Laeufe:")
    for sid, m in saved_meta_collision().items():
        print(f"  {sid}: {m}")
