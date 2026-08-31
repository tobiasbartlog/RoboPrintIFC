"""S6-Sonde — Falsch-Negativ-Risiko des Grob-Checks konkret ausloesen.

Die reale Denkmal-Zerlegung ist entartet: **alle 16 Module kollidieren** an der
festen, aggressiven Workstation-Platzierung (standoff 485 mm bei 510 mm dickem
Modul) — die Konfusionsmatrix hat keine „free"-Zeile, also kann sie die
gefaehrliche Zelle (Grob-Check sagt „frei", voller Befund rot) nicht pruefen.

Diese Sonde erzwingt sie: sie **variiert nur den standoff** eines realen Moduls
(``abschnitt-1``, echte Clay-Geometrie) und legt Grob-Urteil neben den vollen
Befund. Der Verursacher-Histogramm aus ``s6_validate`` sagt voraus, dass bei
groesserem Abstand Ellbogen/Oberarm (Glieder 1–3) die Wand freigeben, waehrend
Handgelenk (4) / Endeffektor prozessbedingt an der Front bleiben — der Grob-Check
schliesst genau die aus (ARM_LINK_INDICES = 1,2,3) und kippt dann auf „frei",
obwohl der volle Befund noch rot/gelb ist.

KEINE Platzierung wird geschrieben — nur in-memory, ``standoff`` ist der einzige
veraenderte Wert (ADR-024-Constraint-Frage fuer #141). Kein Lauf, keine Mutation.

Aufruf (venv, Repo-Root)::

    ./.venv/Scripts/python.exe docs/spikes/s6_scripts/s6_fn_probe.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s6_harness import build_context, coarse_verdict  # noqa: E402

OUT = Path(__file__).resolve().parent / "last_fn_probe.json"
TOOL_INDEX = 7
SECTION_ID = "abschnitt-1"
STANDOFFS_MM = (485.0, 700.0, 900.0, 1100.0, 1300.0)


def link_label(i) -> str:
    if i is None:
        return "none"
    if i == TOOL_INDEX:
        return "tool(7)"
    return f"link{i}"


def full_finding_at(ctx, section_id, placement) -> dict:
    """Voller Befund eines Teils an einer **uebersteuerten** Platzierung (in-memory).

    Nutzt den Advisor-Hebel „Platzierung" von ``_slice_and_simulate_section``
    (Override), also denselben Produktivpfad wie der Kollisions-Advisor — kein Lauf.
    """
    from fgc.collision.advisor import Override
    from fgc.collision.finding import CollisionConfig, build_section_finding
    from fgc.pipeline import actions as A

    ov = Override(placement={
        "lateral_mm": placement.lateral_mm,
        "standoff_mm": placement.standoff_mm,
        "stand_height_mm": placement.stand_height_mm,
    })
    comp = A._slice_and_simulate_section(ctx.artifact, ctx.job, section_id, override=ov)
    fnd = build_section_finding(
        comp.robot_name,
        base_frame=comp.trajectory.meta["base_frame"],
        samples=comp.trajectory.samples,
        target_times_s=comp.trajectory.target_times or [],
        targets=[t.to_dict() for t in comp.toolpath.targets],
        part_vertices_mm=comp.verts,
        part_faces=comp.part_faces,
        layer_height_mm=float(comp.params.layer_height_mm),
        n_layers=int(comp.toolpath.summary()["n_layers"]),
        mode=comp.plan_kind,
        tool=comp.tool,
        config=CollisionConfig(),
        section_z0_mm=0.0,
        earlier_parts=comp.earlier_parts,
    )
    return fnd


def main() -> None:
    ctx = build_context()
    sp = next(s for s in ctx.plan.sections if s.section.section_id == SECTION_ID)
    rows = []
    print(f"Standoff-Sweep an {SECTION_ID} (echte Geometrie, nur standoff variiert):\n")
    print(f"{'standoff':>9} | {'grob':>6} | {'voll n_red':>10} {'n_yellow':>9} "
          f"{'min_mm':>10} | rote Verursacher / (falls 0 rot) gelbe Verursacher")
    for so in STANDOFFS_MM:
        placement = replace(sp.placement, standoff_mm=so)
        hit, ms, n_poses = coarse_verdict(ctx, sp.section, placement)
        fnd = full_finding_at(ctx, SECTION_ID, placement)
        n_red = int(fnd["n_red"])
        n_yellow = int(fnd["n_yellow"])
        dists = fnd["distances_mm"]
        c_link = fnd["causer_link"]
        # Verursacher der roten (oder, wenn keine roten, der gelben) Samples.
        band = [(d, li) for d, li in zip(dists, c_link) if d is not None and d < 0.0]
        which = "rot"
        if not band:
            band = [(d, li) for d, li in zip(dists, c_link)
                    if d is not None and 0.0 <= d < fnd["config"]["safety_distance_mm"]]
            which = "gelb"
        causer = Counter(link_label(li) for _d, li in band)
        only_excluded = bool(causer) and all(
            kk in ("link4", "link5", "link6", "tool(7)") for kk in causer
        )
        rows.append({
            "standoff_mm": so, "coarse_collides": hit, "coarse_ms": round(ms, 3),
            "n_red": n_red, "n_yellow": n_yellow, "min_distance_mm": fnd["min_distance_mm"],
            "band": which, "causer": dict(causer),
            "false_negative": (not hit) and n_red > 0,
            "front_only_penetrator": only_excluded,
        })
        flag = "  <== FALSCH-NEGATIV" if (not hit and n_red > 0) else ""
        print(f"{so:>9.0f} | {'RED' if hit else 'free':>6} | {n_red:>10d} {n_yellow:>9d} "
              f"{str(fnd['min_distance_mm']):>10} | {which}: {dict(causer)}{flag}")
    OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nJSON: {OUT}")


if __name__ == "__main__":
    main()
