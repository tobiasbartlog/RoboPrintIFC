"""S5-Sonde 4 — AP-1-Baseline: FCL-Referenz **produktiv verduennt**, je Aufrufort.

Vorher-Haelfte von US 13 der PRD #183 (Issue #206). Die S5-Basismessung (Sonde 2,
``s5_instrumented.py``) lief **unverduennt** (stride=1, jedes Sample). Der reale
Pruef-Tuer-Pfad (``fgc.collision.finding.check_part_clearance``) duennt Travel aber
mit ``DEFAULT_TRAVEL_STRIDE = 5`` aus, bevor ``find_collisions`` laeuft. Als
Baseline fuer den Paper-Beleg „SDF beschleunigt Y-fach je Posten" (US 13, US 21)
taugt nur eine **konfigurationsgleiche** Messung — also auf **derselben**
verduennten Sample-Auswahl, die auch der Realpfad prueft.

Diese Sonde erweitert die S5-Sonden (sie baut auf ``s5_harness.build_inputs`` und
spiegelt den ``find_collisions``-Loop wie ``s5_instrumented``) und misst die
FCL-Referenz **getrennt nach Aufrufort**:

  * **Arm↔Hindernis**  — ``min_distance_other`` Glied↔Druckstand (Produktiv-Pfad,
    ``self_collision=False``),
  * **Selbstkollision (Arm↔Arm)** — ``min_distance_other`` Glied↔Glied ueber die
    nicht-benachbarten Paare (im Produktiv-Befund AUS, aber Teil der SDF-Abl-
    oesung nach US 13 — daher als eigener Aufrufort mitzumessen).

Determinismus-Gate: ``find_collisions`` auf der verduennten Auswahl wird **zweimal**
gerufen; die rot/gelb/gruen-Zahlen und der Verursacher muessen identisch sein
(python-fcl ist bytegleich, Spike S0). Die instrumentierte Nachbildung muss
dieselben Zahlen liefern wie das echte ``find_collisions`` (sonst misst man etwas
anderes). Absolutzeiten sind Messwerte (maschinenabhaengig), kein Gate — die
belastbare Groesse sind die **Zaehlwerte** und die **Konfiguration**.

Aufruf (venv, Repo-Root)::

    ./.venv/Scripts/python.exe docs/spikes/s5_scripts/s5_ap1_baseline.py

Schreibt ``docs/spikes/s5_scripts/last_ap1_baseline.json``.
"""

from __future__ import annotations

import json
import platform
import statistics
import time
from pathlib import Path

from s5_harness import build_inputs

OUT = Path(__file__).resolve().parent / "last_ap1_baseline.json"

#: Wiederholungen der Wall-Zeit-Messung je Konfiguration (Min/Median berichtet).
N_TIMING_REPEATS = 3


def _thin(inp, stride: int):
    """Verduennte Sample-Auswahl **wie der Realpfad** (``thin_travel_indices``).

    Nutzt dieselbe Produktiv-Funktion und dieselbe Travel-Kennzeichnung je Sample
    wie ``check_part_clearance``; ``stride=1`` behaelt alles (Identitaet, = voller
    Befund). Rueckgabe: (kept-Indizes, link_frames, sample_layers).
    """
    from fgc.collision.finding import thin_travel_indices

    kept = thin_travel_indices(inp.sample_is_travel, int(stride))
    link_frames = [inp.link_frames[i] for i in kept]
    sample_layers = [inp.sample_layers[i] for i in kept]
    return kept, link_frames, sample_layers


def _real_counts(inp, link_frames, sample_layers, *, self_collision: bool):
    """Echtes ``find_collisions`` auf der gegebenen Auswahl → (counts, wall_s)."""
    from fgc.collision import check as C

    t0 = time.perf_counter()
    rep = C.find_collisions(
        inp.geo,
        inp.base,
        link_frames,
        sample_layers,
        inp.provider_factory(),
        tcp_frame=inp.tcp_frame,
        tool_hull=inp.tool_hull,
        safety_distance_mm=inp.safety_distance_mm,
        self_collision=self_collision,
    )
    wall = time.perf_counter() - t0
    counts = {
        "n_samples": len(link_frames),
        "n_red": rep.n_red,
        "n_yellow": rep.n_yellow,
        "n_green": rep.n_green,
        "min_distance_mm": round(rep.min_distance_mm, 3),
        "worst_index": rep.worst_index,
    }
    return counts, wall


def instrumented_by_callsite(inp, link_frames, sample_layers, *, self_collision: bool):
    """``find_collisions``-Nachbildung mit Timern **getrennt nach Aufrufort**.

    Spiegelt ``fgc.collision.check.find_collisions`` (dieselben Helfer, dieselben
    fcl-Manager) und trennt die Posten in **Arm↔Hindernis** und **Selbstkollision**:
    je Aufrufort eigene Timer fuer ``set_transform`` (VHACD-Stuecke positionieren),
    Breitphase (``_aabb_gap``) und das fcl-Urteil (``min_distance_other``) plus
    Zaehler. Gemeinsame Vorarbeit (Compose/Matrix/AABB) liegt in ``t_shared``.
    """
    import numpy as np
    from trimesh.collision import CollisionManager

    from fgc.collision import check as C
    from fgc.simulation import transform

    geo = inp.geo
    base_frame = inp.base
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

    def groups_for(layer_index: int):
        hit = group_cache.get(layer_index)
        if hit is None:
            oset = obstacle_provider(layer_index)
            grp = C._obstacle_groups(oset, oset.freizone_radius_mm, np)
            hit = (oset.freizone_radius_mm, grp)
            group_cache[layer_index] = hit
        return hit

    c = {
        # Aufrufort-neutrale Vorarbeit
        "t_shared": 0.0,
        "t_obstacle_rebuild": 0.0,
        "n_obstacle_rebuild": 0,
        # Aufrufort ARM↔HINDERNIS
        "t_arm_broad": 0.0,
        "t_arm_setparts": 0.0,
        "t_arm_fcl": 0.0,
        "n_arm_broad_eval": 0,
        "n_arm_broad_reject": 0,
        "n_arm_fcl": 0,
        # Aufrufort SELBSTKOLLISION (Arm↔Arm)
        "t_self_broad": 0.0,
        "t_self_setparts": 0.0,
        "t_self_fcl": 0.0,
        "n_self_broad_eval": 0,
        "n_self_broad_reject": 0,
        "n_self_fcl": 0,
    }
    all_check = set(check_links) | set(self_links)
    results = []

    for k, link_frames_k in enumerate(link_frames):
        t0 = perf()
        world = [transform.compose(base_frame, lf) for lf in link_frames_k]
        mats = {i: C.matrix(world[i]) for i in range(len(world))}
        print_point = None
        if tcp_frame is not None:
            world_tcp = transform.compose(world[6], tcp_frame)
            print_point = np.asarray(world_tcp.pos_mm, dtype=float)
            if tool_hull is not None:
                mats[C.TOOL_INDEX] = C.matrix(world_tcp)
        aabb: dict = {}
        for i in all_check:
            wc = (mats[i] @ corners[i])[:3]
            aabb[i] = (wc.min(axis=1), wc.max(axis=1))
        c["t_shared"] += perf() - t0

        li = int(sample_layers[k])
        hit = group_cache.get(li)
        if hit is None:
            oset = obstacle_provider(li)
            t0 = perf()
            grp = C._obstacle_groups(oset, oset.freizone_radius_mm, np)
            c["t_obstacle_rebuild"] += perf() - t0
            c["n_obstacle_rebuild"] += 1
            hit = (oset.freizone_radius_mm, grp)
            group_cache[li] = hit
        freizone, groups = hit

        parts_ready: set = set()
        best = (float("inf"), None, None, "broad")

        # --- Aufrufort ARM↔HINDERNIS ---
        for i in check_links:
            wlo, whi = aabb[i]
            for gm, exempt, glo, ghi in groups:
                t0 = perf()
                gap = C._aabb_gap(wlo, whi, glo, ghi, np)
                c["t_arm_broad"] += perf() - t0
                c["n_arm_broad_eval"] += 1
                if gap > safety:
                    c["n_arm_broad_reject"] += 1
                    if gap < best[0]:
                        best = (float(gap), None, None, "broad")
                    continue
                t0 = perf()
                C._set_parts(part_of[i], part_names[i], mats[i], i, parts_ready)
                c["t_arm_setparts"] += perf() - t0
                t0 = perf()
                dj, jn, jd = part_of[i].min_distance_other(
                    gm, return_names=True, return_data=True
                )
                c["t_arm_fcl"] += perf() - t0
                c["n_arm_fcl"] += 1
                if exempt and C._in_freizone(jd, jn, print_point, freizone, np):
                    continue
                if dj < best[0]:
                    best = (float(dj), i, jn[1], "judgment")

        # --- Aufrufort SELBSTKOLLISION (Arm↔Arm) ---
        if self_collision:
            for i, j in self_pairs:
                t0 = perf()
                gap = C._aabb_gap(*aabb[i], *aabb[j], np)
                c["t_self_broad"] += perf() - t0
                c["n_self_broad_eval"] += 1
                if gap > safety:
                    c["n_self_broad_reject"] += 1
                    continue
                t0 = perf()
                C._set_parts(part_of[i], part_names[i], mats[i], i, parts_ready)
                C._set_parts(part_of[j], part_names[j], mats[j], j, parts_ready)
                c["t_self_setparts"] += perf() - t0
                t0 = perf()
                d = part_of[i].min_distance_other(part_of[j])
                c["t_self_fcl"] += perf() - t0
                c["n_self_fcl"] += 1
                if d < best[0]:
                    best = (float(d), i, f"link{j}", "judgment")

        results.append(best[0])

    n_red = sum(1 for d in results if d < 0.0)
    n_yellow = sum(1 for d in results if 0.0 <= d < safety)
    n_green = len(results) - n_red - n_yellow
    return c, (n_red, n_yellow, n_green, round(min(results), 3))


def main() -> None:
    inp = build_inputs()

    from fgc.collision.finding import DEFAULT_TRAVEL_STRIDE

    stride = int(DEFAULT_TRAVEL_STRIDE)

    kept, tf, tl = _thin(inp, stride)
    _, ff, fl = _thin(inp, 1)  # voller Befund (Kontext)

    # --- Determinismus-Gate: verduennte Auswahl zweimal, Zahlen muessen gleich sein.
    d1, _ = _real_counts(inp, tf, tl, self_collision=False)
    d2, _ = _real_counts(inp, tf, tl, self_collision=False)
    deterministic = d1 == d2
    print(f"Determinismus-Gate (verduennt, self=False): "
          f"{'OK' if deterministic else 'FEHLGESCHLAGEN'}  {d1}")

    # --- Kontext: voller Befund (stride=1) vs. verduennt (stride=5), self=False.
    full_counts, _ = _real_counts(inp, ff, fl, self_collision=False)

    # --- Wall-Zeit-Messung (Min/Median ueber Wiederholungen), verduennt, self=False.
    walls_arm = []
    for _ in range(N_TIMING_REPEATS):
        _, w = _real_counts(inp, tf, tl, self_collision=False)
        walls_arm.append(w)

    # --- Selbstkollision als eigener Aufrufort (verduennt, self=True): Zahlen + Wall.
    # Nur EIN Lauf — Selbstkollision ist ~15x teurer (S5); die Zahl ist ein Messwert,
    # kein Gate, und die Determinismus-/Nachbildungs-Gates greifen ueber die Zaehlwerte.
    self_counts, w_self = _real_counts(inp, tf, tl, self_collision=True)
    self_walls = [w_self]

    # --- Instrumentierte Aufteilung nach Aufrufort (verduennt).
    c_arm, mirror_arm = instrumented_by_callsite(inp, tf, tl, self_collision=False)
    match_arm = (mirror_arm[0], mirror_arm[1], mirror_arm[2]) == (
        d1["n_red"], d1["n_yellow"], d1["n_green"]
    )
    c_self, mirror_self = instrumented_by_callsite(inp, tf, tl, self_collision=True)
    match_self = (mirror_self[0], mirror_self[1], mirror_self[2]) == (
        self_counts["n_red"], self_counts["n_yellow"], self_counts["n_green"]
    )

    def ms_per(t, n):
        return round(1000.0 * t / max(1, n), 4)

    out = {
        "config": {
            "spike": "S5/AP-1-Baseline (Issue #206)",
            "run_origin": "runs/20260709-140251_slice_Denkmal (Denkmal, Abschnitt-1, Modul)",
            "reproduction": "slice_and_simulate_section('denkmal','abschnitt-1') → find_collisions",
            "travel_stride": stride,
            "safety_distance_mm": inp.safety_distance_mm,
            "freizone_radius_mm": 40.0,
            "decomposition_kind": "modul",
            "self_collision_produktiv": False,
            "n_samples_full": inp.n_samples,
            "n_travel_samples_full": int(sum(inp.sample_is_travel)),
            "n_samples_thinned": len(kept),
            "n_layers": inp.n_layers,
            "tool_hull": inp.tool_hull is not None,
            "n_timing_repeats": N_TIMING_REPEATS,
            "machine": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "processor": platform.processor(),
            },
        },
        "determinism_gate": {
            "thinned_self_false_run1": d1,
            "thinned_self_false_run2": d2,
            "identical": deterministic,
        },
        "counts_full_vs_thinned_self_false": {
            "full_stride1": full_counts,
            "thinned_stride5": d1,
        },
        "wall_seconds": {
            "thinned_self_false": {
                "runs": [round(w, 3) for w in walls_arm],
                "min": round(min(walls_arm), 3),
                "median": round(statistics.median(walls_arm), 3),
            },
            "thinned_self_true": {
                "runs": [round(w, 3) for w in self_walls],
                "min": round(min(self_walls), 3),
                "median": round(statistics.median(self_walls), 3),
            },
            "slice_sim_s": round(inp.slice_sim_time_s, 3),
            "fk_link_frames_s": round(inp.fk_time_s, 3),
        },
        "callsite_arm_obstacle": {
            "instrumented_match": match_arm,
            "n_fcl": c_arm["n_arm_fcl"],
            "t_fcl_s": round(c_arm["t_arm_fcl"], 3),
            "ms_per_fcl": ms_per(c_arm["t_arm_fcl"], c_arm["n_arm_fcl"]),
            "t_setparts_s": round(c_arm["t_arm_setparts"], 3),
            "t_broad_s": round(c_arm["t_arm_broad"], 3),
            "n_broad_eval": c_arm["n_arm_broad_eval"],
            "n_broad_reject": c_arm["n_arm_broad_reject"],
            "pct_broad_reject": round(
                100 * c_arm["n_arm_broad_reject"] / max(1, c_arm["n_arm_broad_eval"]), 1
            ),
        },
        "callsite_self_collision": {
            "instrumented_match": match_self,
            "note": "Im Produktiv-Befund AUS; hier als eigener Aufrufort fuer die "
                    "SDF-Abloesung (US 13) auf derselben verduennten Auswahl gemessen.",
            "n_fcl": c_self["n_self_fcl"],
            "t_fcl_s": round(c_self["t_self_fcl"], 3),
            "ms_per_fcl": ms_per(c_self["t_self_fcl"], c_self["n_self_fcl"]),
            "t_setparts_s": round(c_self["t_self_setparts"], 3),
            "t_broad_s": round(c_self["t_self_broad"], 3),
            "n_broad_eval": c_self["n_self_broad_eval"],
            "n_broad_reject": c_self["n_self_broad_reject"],
            "pct_broad_reject": round(
                100 * c_self["n_self_broad_reject"] / max(1, c_self["n_self_broad_eval"]), 1
            ),
        },
        "obstacle_rebuild": {
            "n_rebuild": c_arm["n_obstacle_rebuild"],
            "t_total_s": round(c_arm["t_obstacle_rebuild"], 3),
        },
    }

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    # Konsole ascii-sicher (Windows-cp1252-stdout kann '→' nicht) — Datei bleibt utf-8.
    print(json.dumps(out, indent=2, ensure_ascii=True))
    print(f"\ngeschrieben: {OUT}")
    if not (deterministic and match_arm and match_self):
        raise SystemExit("Gate fehlgeschlagen (Determinismus oder Nachbildung).")


if __name__ == "__main__":
    main()
