"""S5-Sonde 3 — misst Hypothese „Distanz nur bis Schwelle" direkt (statt zu schätzen).

Für **jedes** nahe (Glied, Hindernis)-Paar des realen Laufs (die 43 469 fcl-
Aufrufe) ruft die Sonde am selben, bereits positionierten fcl-Manager **beide**
Abfragen und misst ihre Zeit getrennt:

  - ``min_distance_other``  — die exakte Nahdistanz (heutiges Urteil),
  - ``in_collision_other``  — der billige Ja/Nein-Durchdringungstest (0 mm).

So ist der Deckel der Hypothese gemessen, nicht geschätzt: Der zweistufige
Befund (rot < 0, gelb < Sicherheitsabstand) braucht für das **gelbe** Band
zwingend eine Distanz; nur die **klar durchdringenden** (roten) Paare könnte ein
in_collision-Kurzschluss früh abfangen. Die Sonde zählt, wie viele Aufrufe
``in_collision`` mit True beantwortet (also potenziell kurzschließbar) und wie
teuer ``in_collision`` gegenüber ``min_distance`` ist. Das ``set_transform``
(Positionieren der ~36 VHACD-Stücke je nahem Glied) fällt für **beide** Wege an
und ist damit nicht einsparbar — die Sonde beziffert genau diesen Rest.

Aufruf (venv, Repo-Root)::

    ./.venv/Scripts/python.exe docs/spikes/s5_scripts/s5_threshold.py

Schreibt ``docs/spikes/s5_scripts/last_threshold.json``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from s5_harness import build_inputs

OUT = Path(__file__).resolve().parent / "last_threshold.json"


def main() -> None:
    import numpy as np
    from trimesh.collision import CollisionManager

    from fgc.collision import check as C
    from fgc.simulation import transform

    inp = build_inputs()
    geo = inp.geo
    base_frame = inp.base
    provider = inp.provider_factory()
    tcp_frame = inp.tcp_frame
    tool_hull = inp.tool_hull
    safety = inp.safety_distance_mm
    perf = time.perf_counter

    check_links = list(range(1, len(geo.links))) + [C.TOOL_INDEX]
    corners, part_of, part_names = {}, {}, {}
    for i in range(len(geo.links)):
        lk = geo.link(i)
        corners[i] = C.corner_box(lk.broadphase_hull, np)
        pm = CollisionManager()
        names = []
        for p, part in enumerate(lk.judgment_parts):
            nm = f"{i}#{p}"
            pm.add_object(nm, part)
            names.append(nm)
        part_of[i], part_names[i] = pm, names
    corners[C.TOOL_INDEX] = C.corner_box(tool_hull, np)
    tm = CollisionManager()
    tm.add_object("tool", tool_hull)
    part_of[C.TOOL_INDEX], part_names[C.TOOL_INDEX] = tm, ["tool"]

    group_cache: dict = {}

    def groups_for(li):
        hit = group_cache.get(li)
        if hit is None:
            oset = provider(li)
            hit = (oset.freizone_radius_mm, C._obstacle_groups(oset, oset.freizone_radius_mm, np))
            group_cache[li] = hit
        return hit

    t_mindist = 0.0
    t_incoll = 0.0
    n_calls = 0
    n_incoll_true = 0     # in_collision == True (durchdringend, rot)
    n_mindist_red = 0     # min_distance < 0
    n_mindist_yellow = 0  # 0 <= d < safety
    n_mindist_green = 0   # d >= safety (nur „grün" — hier wäre Distanz „verschwendet")

    for k, link_frames in enumerate(inp.link_frames):
        world = [transform.compose(base_frame, lf) for lf in link_frames]
        mats = {i: C.matrix(world[i]) for i in range(len(world))}
        world_tcp = transform.compose(world[6], tcp_frame)
        mats[C.TOOL_INDEX] = C.matrix(world_tcp)
        aabb = {}
        for i in check_links:
            wc = (mats[i] @ corners[i])[:3]
            aabb[i] = (wc.min(axis=1), wc.max(axis=1))
        freizone, groups = groups_for(int(inp.sample_layers[k]))
        ready: set = set()
        for i in check_links:
            wlo, whi = aabb[i]
            for gm, exempt, glo, ghi in groups:
                if C._aabb_gap(wlo, whi, glo, ghi, np) > safety:
                    continue
                C._set_parts(part_of[i], part_names[i], mats[i], i, ready)
                t0 = perf()
                dj = part_of[i].min_distance_other(gm)
                t_mindist += perf() - t0
                t0 = perf()
                hit = part_of[i].in_collision_other(gm)
                t_incoll += perf() - t0
                n_calls += 1
                if hit:
                    n_incoll_true += 1
                if dj < 0.0:
                    n_mindist_red += 1
                elif dj < safety:
                    n_mindist_yellow += 1
                else:
                    n_mindist_green += 1

    out = {
        "n_fcl_calls": n_calls,
        "t_min_distance_s": round(t_mindist, 3),
        "t_in_collision_s": round(t_incoll, 3),
        "ms_per_min_distance": round(1000 * t_mindist / max(1, n_calls), 4),
        "ms_per_in_collision": round(1000 * t_incoll / max(1, n_calls), 4),
        "in_collision_vs_min_distance_ratio": round(t_incoll / max(1e-9, t_mindist), 3),
        "n_in_collision_true": n_incoll_true,
        "call_verdict_from_min_distance": {
            "red": n_mindist_red,
            "yellow": n_mindist_yellow,
            "green_over_safety": n_mindist_green,
        },
        "note": (
            "in_collision beantwortet nur rot/nicht-rot (0 mm), nicht das gelbe "
            "Sicherheits-Band. set_transform faellt fuer beide Wege an."
        ),
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\ngeschrieben: {OUT}")


if __name__ == "__main__":
    main()
