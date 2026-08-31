"""S5-Sonde 2 — instrumentierte Nachbildung des ``find_collisions``-Loops.

Spiegelt den Produktiv-Loop (``fgc.collision.check.find_collisions``) Zeile für
Zeile, ruft **dieselben** Produktiv-Helfer (``_corner_box``, ``_aabb_gap``,
``_obstacle_groups``, ``_matrix``, ``_set_parts``, ``_in_freizone``,
``transform.compose``) und die **echten** fcl-Manager — fügt nur Zähler und
``perf_counter``-Messpunkte je Posten hinzu. Ein Korrektheits-Gate prüft, dass
die Nachbildung byte-genau dieselben rot/gelb/grün-Zahlen liefert wie die echte
``find_collisions`` (sonst misst man etwas anderes).

Gemessen je Posten (Summe ≈ Gesamtzeit):
  - FK-Verkettung  ``transform.compose``  (Welt-Frames der Glieder je Sample)
  - ``_matrix``    (Frame → homogene 4×4, opw-Quat→Rot)
  - Breitphase     (AABB-Ecken transformieren + ``_aabb_gap``)
  - fcl-Urteil     (``min_distance_other``) — Zahl + Zeit + ms/Aufruf
  - Freizonen-Test (``_in_freizone``)
  - Druckstand-Rebuild je Schicht (``_obstacle_groups`` via ``groups_for``)

Zusätzlich die Hypothesen-Kennzahlen:
  - Breitphase: Anteil verworfen (gap > Sicherheit) vs. durchgelassen (→ fcl).
  - Travel-Ausdünnung: Zeitanteil der Travel-Samples.
  - fcl-„nur bis Schwelle": Anteil der fcl-Aufrufe, deren Ergebnis > Sicherheit
    (also nur „grün" entscheidet) vs. ≤ Sicherheit (echtes gelb/rot).
  - Selbstkollision: separater Volllauf mit ``self_collision=True`` (eigener
    Posten, im Produktiv-Befund AUS).

Aufruf (venv, Repo-Root)::

    ./.venv/Scripts/python.exe docs/spikes/s5_scripts/s5_instrumented.py

Schreibt ``docs/spikes/s5_scripts/last_instrumented.json``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from s5_harness import build_inputs, verify_reproduction

OUT = Path(__file__).resolve().parent / "last_instrumented.json"


def instrumented_find_collisions(inp, *, self_collision: bool):
    """Nachbildung des find_collisions-Loops mit Posten-Timern und Zählern."""
    import numpy as np
    from trimesh.collision import CollisionManager

    from fgc.collision import check as C
    from fgc.simulation import transform

    geo = inp.geo
    base_frame = inp.base
    link_frames_per_sample = inp.link_frames
    sample_layers = inp.sample_layers
    obstacle_provider = inp.provider_factory()
    tcp_frame = inp.tcp_frame
    tool_hull = inp.tool_hull
    safety = inp.safety_distance_mm

    perf = time.perf_counter

    check_links = list(range(1, len(geo.links))) + (
        [C.TOOL_INDEX] if tool_hull is not None else []
    )
    self_links = tuple(range(len(geo.links))) + (
        (C.TOOL_INDEX,) if tool_hull is not None else ()
    )
    self_pairs = C.nonadjacent_pairs(self_links) if self_collision else []

    corners: dict = {}
    part_of: dict = {}
    part_names: dict = {}
    for i in range(len(geo.links)):
        lk = geo.link(i)
        corners[i] = C.corner_box(lk.broadphase_hull, np)
        pm = CollisionManager()
        names = []
        for p, part in enumerate(lk.judgment_parts):
            nm = f"{i}#{p}"
            pm.add_object(nm, part)
            names.append(nm)
        part_of[i] = pm
        part_names[i] = names
    if tool_hull is not None:
        corners[C.TOOL_INDEX] = C.corner_box(tool_hull, np)
        tm = CollisionManager()
        tm.add_object("tool", tool_hull)
        part_of[C.TOOL_INDEX] = tm
        part_names[C.TOOL_INDEX] = ["tool"]

    group_cache: dict = {}
    # Zähler
    c = {
        "t_compose": 0.0,
        "t_matrix": 0.0,
        "t_aabb": 0.0,      # Ecken transformieren + min/max
        "t_gap": 0.0,       # _aabb_gap (Arm + self)
        "t_fcl": 0.0,       # min_distance_other
        "t_freizone": 0.0,
        "t_obstacle_rebuild": 0.0,
        "t_setparts": 0.0,
        "n_obstacle_rebuild": 0,
        "n_broad_eval": 0,       # Arm↔Hindernis AABB-Auswertungen
        "n_broad_reject": 0,     # gap > safety (fcl entfällt)
        "n_fcl_arm": 0,          # min_distance_other (Arm)
        "n_fcl_self": 0,         # min_distance_other (Selbstkollision)
        "n_fcl_over_safety": 0,  # fcl-Ergebnis > safety (nur „grün")
        "n_fcl_within_safety": 0,
        "n_self_eval": 0,
        "n_self_reject": 0,
    }
    t_sample = np.zeros(len(link_frames_per_sample))

    def groups_for(layer_index: int):
        hit = group_cache.get(layer_index)
        if hit is None:
            oset = obstacle_provider(layer_index)
            t0 = perf()
            grp = C._obstacle_groups(oset, oset.freizone_radius_mm, np)
            c["t_obstacle_rebuild"] += perf() - t0
            c["n_obstacle_rebuild"] += 1
            hit = (oset.freizone_radius_mm, grp)
            group_cache[layer_index] = hit
        return hit

    results = []
    all_check = set(check_links) | set(self_links)

    for k, link_frames in enumerate(link_frames_per_sample):
        s_start = perf()

        t0 = perf()
        world = [transform.compose(base_frame, lf) for lf in link_frames]
        c["t_compose"] += perf() - t0

        t0 = perf()
        mats = {i: C.matrix(world[i]) for i in range(len(world))}
        c["t_matrix"] += perf() - t0

        print_point = None
        if tcp_frame is not None:
            t0 = perf()
            world_tcp = transform.compose(world[6], tcp_frame)
            c["t_compose"] += perf() - t0
            print_point = np.asarray(world_tcp.pos_mm, dtype=float)
            if tool_hull is not None:
                t0 = perf()
                mats[C.TOOL_INDEX] = C.matrix(world_tcp)
                c["t_matrix"] += perf() - t0

        t0 = perf()
        aabb: dict = {}
        for i in all_check:
            wc = (mats[i] @ corners[i])[:3]
            aabb[i] = (wc.min(axis=1), wc.max(axis=1))
        c["t_aabb"] += perf() - t0

        freizone, groups = groups_for(int(sample_layers[k]))
        parts_ready: set = set()
        best = (float("inf"), None, None, "broad")

        for i in check_links:
            wlo, whi = aabb[i]
            for gm, exempt, glo, ghi in groups:
                t0 = perf()
                gap = C._aabb_gap(wlo, whi, glo, ghi, np)
                c["t_gap"] += perf() - t0
                c["n_broad_eval"] += 1
                if gap > safety:
                    c["n_broad_reject"] += 1
                    if gap < best[0]:
                        best = (float(gap), None, None, "broad")
                    continue
                t0 = perf()
                C._set_parts(part_of[i], part_names[i], mats[i], i, parts_ready)
                c["t_setparts"] += perf() - t0
                t0 = perf()
                dj, jn, jd = part_of[i].min_distance_other(
                    gm, return_names=True, return_data=True
                )
                c["t_fcl"] += perf() - t0
                c["n_fcl_arm"] += 1
                if dj > safety:
                    c["n_fcl_over_safety"] += 1
                else:
                    c["n_fcl_within_safety"] += 1
                t0 = perf()
                skip = exempt and C._in_freizone(jd, jn, print_point, freizone, np)
                c["t_freizone"] += perf() - t0
                if skip:
                    continue
                if dj < best[0]:
                    best = (float(dj), i, jn[1], "judgment")

        if self_collision:
            for i, j in self_pairs:
                t0 = perf()
                gap = C._aabb_gap(*aabb[i], *aabb[j], np)
                c["t_gap"] += perf() - t0
                c["n_self_eval"] += 1
                if gap > safety:
                    c["n_self_reject"] += 1
                    continue
                t0 = perf()
                C._set_parts(part_of[i], part_names[i], mats[i], i, parts_ready)
                C._set_parts(part_of[j], part_names[j], mats[j], j, parts_ready)
                c["t_setparts"] += perf() - t0
                t0 = perf()
                d = part_of[i].min_distance_other(part_of[j])
                c["t_fcl"] += perf() - t0
                c["n_fcl_self"] += 1
                if d < best[0]:
                    best = (float(d), i, f"link{j}", "judgment")

        dist = best[0]
        results.append(dist)
        t_sample[k] = perf() - s_start

    # Klassifikation zur Korrektheitsprüfung
    n_red = sum(1 for d in results if d < 0.0)
    n_yellow = sum(1 for d in results if 0.0 <= d < safety)
    n_green = len(results) - n_red - n_yellow
    return c, t_sample, (n_red, n_yellow, n_green, min(results))


def main() -> None:
    import numpy as np

    inp = build_inputs()
    ref = verify_reproduction(inp)
    print("Echte find_collisions:", ref, "MATCH" if ref["ok"] else "MISMATCH")

    # Volllauf ohne Selbstkollision (= Produktiv-Befund)
    t0 = time.perf_counter()
    c, t_sample, (nr, ny, ng, mn) = instrumented_find_collisions(inp, self_collision=False)
    wall = time.perf_counter() - t0
    match = (nr == ref["n_red"] and ny == ref["n_yellow"] and ng == ref["n_green"])
    print(f"Nachbildung: red/yel/grn {nr}/{ny}/{ng} min {mn:.3f} "
          f"-> {'MATCH' if match else 'MISMATCH'}  (instrumentierte Wall {wall:.2f}s)")

    is_travel = np.asarray(inp.sample_is_travel)
    travel_time = float(t_sample[is_travel].sum())
    print_time = float(t_sample[~is_travel].sum())

    posten = {kk: vv for kk, vv in c.items() if kk.startswith("t_")}
    posten_sum = sum(posten.values())

    ms_per_fcl_arm = 1000.0 * c["t_fcl"] / max(1, c["n_fcl_arm"])

    out = {
        "context": {
            "n_samples": inp.n_samples,
            "n_targets": inp.n_targets,
            "n_layers": inp.n_layers,
            "n_travel_samples": int(is_travel.sum()),
            "tool_hull": inp.tool_hull is not None,
            "slice_sim_time_s": round(inp.slice_sim_time_s, 3),
            "fk_link_frames_time_s": round(inp.fk_time_s, 3),
        },
        "reference_counts": ref,
        "instrumented_match": match,
        "instrumented_wall_s": round(wall, 3),
        "posten_sum_s": round(posten_sum, 3),
        "posten_s": {kk: round(vv, 3) for kk, vv in posten.items()},
        "posten_pct": {kk: round(100 * vv / posten_sum, 1) for kk, vv in posten.items()},
        "counts": {kk: vv for kk, vv in c.items() if kk.startswith("n_")},
        "fcl": {
            "n_fcl_arm": c["n_fcl_arm"],
            "t_fcl_s": round(c["t_fcl"], 3),
            "ms_per_fcl_arm": round(ms_per_fcl_arm, 4),
            "n_fcl_over_safety": c["n_fcl_over_safety"],
            "n_fcl_within_safety": c["n_fcl_within_safety"],
            "pct_fcl_over_safety": round(
                100 * c["n_fcl_over_safety"] / max(1, c["n_fcl_arm"]), 1
            ),
        },
        "broadphase": {
            "n_broad_eval": c["n_broad_eval"],
            "n_broad_reject": c["n_broad_reject"],
            "pct_reject": round(100 * c["n_broad_reject"] / max(1, c["n_broad_eval"]), 1),
        },
        "obstacle_rebuild": {
            "n_rebuild": c["n_obstacle_rebuild"],
            "t_total_s": round(c["t_obstacle_rebuild"], 3),
            "ms_per_rebuild": round(
                1000.0 * c["t_obstacle_rebuild"] / max(1, c["n_obstacle_rebuild"]), 3
            ),
        },
        "travel": {
            "travel_time_s": round(travel_time, 3),
            "print_time_s": round(print_time, 3),
            "pct_travel_time": round(100 * travel_time / (travel_time + print_time), 1),
        },
    }

    # Selbstkollision als eigener Posten (Produktiv AUS)
    t0 = time.perf_counter()
    cS, _, (srn, syn, sgn, smn) = instrumented_find_collisions(inp, self_collision=True)
    wallS = time.perf_counter() - t0
    out["self_collision_posten"] = {
        "instrumented_wall_s": round(wallS, 3),
        "n_fcl_self": cS["n_fcl_self"],
        "t_fcl_self_extra_s": round(cS["t_fcl"] - c["t_fcl"], 3),
        "n_self_eval": cS["n_self_eval"],
        "n_self_reject": cS["n_self_reject"],
        "red_yel_grn": [srn, syn, sgn],
    }

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\ngeschrieben: {OUT}")


if __name__ == "__main__":
    main()
