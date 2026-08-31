"""S5-Harness — rekonstruiert die **realen** ``find_collisions``-Eingaben der
Abschnitt-1-Bahn (Denkmal, Modul-Zerlegung) exakt so, wie
``fgc.collision.finding.build_section_finding`` sie im Produktivpfad baut.

Warum so: Der zu profilierende Lauf ist ``runs/20260709-140251_slice_Denkmal``
(Provenienz ``POST /projects/denkmal/sections/abschnitt-1/simulate``); sein
gespeicherter ``meta.collision``-Block trägt genau die Ticket-Zahlen
(8688 rot / 2405 gelb / 8442 grün, min −290.444 mm). Statt die Bahn aus der
6-MB-``trajectory.json`` zurückzurechnen, reproduzieren wir sie deterministisch
über den Produktivpfad ``_slice_and_simulate_section`` und **prüfen**, dass der
Kollisionsbefund byte-genau dieselben Zahlen liefert — so profilieren wir
denselben Code mit denselben Eingaben, nicht eine Nachbildung.

Aufruf (venv, Repo-Root ``C:\\Users\\tbartlog\\Documents\\LokalPython\\RoboPrintIFC``)::

    ./.venv/Scripts/python.exe docs/spikes/s5_scripts/s5_harness.py

Direkt aufgerufen prüft es nur die Reproduktion (Selbsttest). Die Profiling-
Sonden importieren ``build_inputs()``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_JSON = REPO_ROOT / "projects" / "denkmal" / "project.json"
SECTION_ID = "abschnitt-1"

# Erwartete Kennzahlen der reproduzierten Abschnitt-1-Bahn (voller Befund, stride=1,
# self=False). URSPRUNG (S5, 2026-07-09, runs/20260709-140251_slice_Denkmal):
# 8688 rot / 2405 gelb / 8442 gruen, min −290.444 mm bei 19 535 Samples.
# RE-PINNED 2026-07-14 (Issue #206): die Pipeline (Slicer/Decompose/Kinematik) ist
# seit S5 um Dutzende Commits fortgeschritten, der 2026-07-09-Lauf reproduziert nicht
# mehr byte-genau. Diese Werte sind der aktuelle **deterministische** Fingerabdruck
# desselben Produktivpfads (slice_and_simulate_section → find_collisions); die
# AP-1-Baseline (#206) und die Nachher-Messung (#215) fussen auf ihm, nicht auf den
# historischen S5-Zahlen. Determinismus je Lauf ist per S0 gesichert (python-fcl
# bytegleich) und wird von s5_ap1_baseline.py als Gate geprueft.
EXPECT_N_RED = 6187
EXPECT_N_YELLOW = 1938
EXPECT_N_GREEN = 8078
EXPECT_MIN_MM = -147.453


@dataclass
class Inputs:
    """Alle Argumente eines ``find_collisions``-Aufrufs plus Kontext-Kennzahlen."""

    geo: Any
    base: Any
    link_frames: list
    sample_layers: list
    provider_factory: Any  # callable -> frischer obstacle_provider (Cache je Lauf leer)
    tcp_frame: Any
    tool_hull: Any
    safety_distance_mm: float
    # Fuer die SDF-Nachher-Messung (#215): Roboter + Druckstand-Spec, aus denen ein
    # SdfObstacleProvider konfigurationsgleich zur FCL-Referenz gebaut wird.
    robot_name: str
    druckstand_spec: Any
    # Kontext
    n_samples: int
    n_targets: int
    n_layers: int
    layer_height_mm: float
    sample_is_travel: list  # bool je Sample (aus dem Toolpath)
    fk_time_s: float
    slice_sim_time_s: float


def build_inputs() -> Inputs:
    """Baut die realen ``find_collisions``-Eingaben der Abschnitt-1-Bahn."""
    import numpy as np
    import trimesh

    import fgc.pipeline.actions as A
    from fgc.collision import check as C
    from fgc.collision import druckstand as DS
    from fgc.collision.finding import (
        DEFAULT_FREIZONE_RADIUS_MM,
        DEFAULT_SAFETY_DISTANCE_MM,
        _footprint,
        _identity_frame,
        _tools_dir,
        travel_intervals,
    )
    from fgc.collision.robot_geometry import load_robot_collision_geometry
    from fgc.kinematics.opw import OpwKinematics
    from fgc.simulation import transform

    artifact = json.loads(PROJECT_JSON.read_text(encoding="utf-8"))
    job = artifact["print_jobs"][0]

    t0 = time.perf_counter()
    comp = A.slice_and_simulate_section(artifact, job, SECTION_ID)
    slice_sim_time_s = time.perf_counter() - t0

    n_layers = int(comp.toolpath.summary()["n_layers"])
    geo = load_robot_collision_geometry(comp.robot_name)
    kin = OpwKinematics.from_robot(comp.robot_name)
    base = transform.frame_from_dict(comp.trajectory.meta["base_frame"])
    samples = comp.trajectory.samples

    t0 = time.perf_counter()
    link_frames = [kin.link_frames(s["joints_rad"]) for s in samples]
    fk_time_s = time.perf_counter() - t0

    sample_times = [float(s["t_s"]) for s in samples]
    targets = comp.target_dicts
    target_times = comp.trajectory.target_times or []
    target_layers = [int(t.get("layer", 0)) for t in targets]
    target_kinds = [str(t.get("kind", "print")) for t in targets]
    sample_layers = DS.layer_per_sample(sample_times, target_times, target_layers)

    # Travel-Kennzeichnung je Sample (aus dem Toolpath, wie finding.travel_intervals).
    tvis = travel_intervals(sample_times, target_times, target_kinds)
    is_travel = [False] * len(samples)
    for a, b in tvis:
        for i in range(a, b + 1):
            is_travel[i] = True

    footprint = _footprint(comp.verts, comp.part_faces, np, trimesh)
    layer_height_mm = float(comp.params.layer_height_mm)

    druckstand_spec = DS.DruckstandSpec(
        footprint=footprint,
        layer_height_mm=layer_height_mm,
        n_layers=n_layers,
        freizone_radius_mm=DEFAULT_FREIZONE_RADIUS_MM,
        mode="modul",
    )

    def provider_factory():
        return DS.obstacle_provider(druckstand_spec)

    tool = comp.tool
    tcp = transform.frame_from_dict(tool.tcp_frame)
    tool_hull = None
    if getattr(tool, "mesh", None):
        mp = _tools_dir() / tool.mesh
        if mp.exists():
            tm = trimesh.load(mp, force="mesh", process=False)
            mt = transform.frame_from_dict(tool.mesh_transform or _identity_frame())
            tool_hull = C.provisional_tool_hull(tm, mt, tcp)

    return Inputs(
        geo=geo,
        base=base,
        link_frames=link_frames,
        sample_layers=sample_layers,
        provider_factory=provider_factory,
        tcp_frame=tcp,
        tool_hull=tool_hull,
        safety_distance_mm=float(DEFAULT_SAFETY_DISTANCE_MM),
        n_samples=len(samples),
        n_targets=len(targets),
        n_layers=n_layers,
        layer_height_mm=layer_height_mm,
        sample_is_travel=is_travel,
        fk_time_s=fk_time_s,
        slice_sim_time_s=slice_sim_time_s,
        robot_name=comp.robot_name,
        druckstand_spec=druckstand_spec,
    )


def verify_reproduction(inp: Inputs) -> dict:
    """Ruft die *echte* ``find_collisions`` und prüft die Ticket-Zahlen."""
    from fgc.collision import check as C

    rep = C.find_collisions(
        inp.geo,
        inp.base,
        inp.link_frames,
        inp.sample_layers,
        inp.provider_factory(),
        tcp_frame=inp.tcp_frame,
        tool_hull=inp.tool_hull,
        safety_distance_mm=inp.safety_distance_mm,
        self_collision=False,
    )
    ok = (
        rep.n_red == EXPECT_N_RED
        and rep.n_yellow == EXPECT_N_YELLOW
        and rep.n_green == EXPECT_N_GREEN
        and abs(rep.min_distance_mm - EXPECT_MIN_MM) < 1e-3
    )
    return {
        "ok": ok,
        "n_red": rep.n_red,
        "n_yellow": rep.n_yellow,
        "n_green": rep.n_green,
        "min_distance_mm": round(rep.min_distance_mm, 3),
    }


if __name__ == "__main__":
    inp = build_inputs()
    res = verify_reproduction(inp)
    print("Reproduktion der realen Abschnitt-1-Bahn:")
    print(f"  n_samples          = {inp.n_samples}")
    print(f"  n_targets          = {inp.n_targets}")
    print(f"  n_layers           = {inp.n_layers}")
    print(f"  layer_height_mm    = {inp.layer_height_mm}")
    print(f"  tool_hull          = {inp.tool_hull is not None}")
    print(f"  travel-Samples     = {sum(inp.sample_is_travel)}")
    print(f"  slice+sim time s   = {inp.slice_sim_time_s:.2f}")
    print(f"  FK link_frames s   = {inp.fk_time_s:.2f}")
    print(f"  Befund             = {res}")
    print("  MATCH" if res["ok"] else "  MISMATCH — Zahlen weichen ab!")
