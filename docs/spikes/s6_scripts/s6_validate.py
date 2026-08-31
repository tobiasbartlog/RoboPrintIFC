"""S6-Sonde — Konfusionsmatrix Grob-Check x voller Befund, Verursacher, Kosten,
Sensitivitaet, ueber alle 16 Module der realen Denkmal-Zerlegung.

Nutzt ``s6_harness`` (build_context / coarse_verdict / full_finding), also den
Produktivpfad. Schreibt ``last_validate.json`` (alle Rohzahlen) und druckt eine
Zusammenfassung.

Aufruf (venv, Repo-Root)::

    ./.venv/Scripts/python.exe docs/spikes/s6_scripts/s6_validate.py

Laufzeit: ~5 min (16x slice+sim+find_collisions ueber den echten Code).
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s6_harness import build_context, coarse_verdict, full_finding  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "last_validate.json"

TOOL_INDEX = 7  # fgc.collision.check.TOOL_INDEX (Endeffektor)
ARM_LINKS = (1, 2, 3)  # fgc.collision.coarse.ARM_LINK_INDICES


def link_label(i) -> str:
    if i is None:
        return "none"
    if i == TOOL_INDEX:
        return "tool(7)"
    return f"link{i}"


def main() -> None:
    ctx = build_context()
    print(f"Kontext: {ctx.plan.kind}, {len(ctx.plan.sections)} Teile, "
          f"dicke={ctx.thickness_mm} mm, lead/kipp={ctx.ori.lead_rad}/{ctx.ori.kipp_rad}")

    per_part = []
    coarse_times_ms: list[float] = []

    for k, sp in enumerate(ctx.plan.sections, 1):
        sid = sp.section.section_id
        t_wall = time.perf_counter()

        # Grob-Urteil (Default-Parameter) + mehrere Wiederholungen fuer die Kosten.
        hit, ms, n_poses = coarse_verdict(ctx, sp.section, sp.placement)
        reps = [coarse_verdict(ctx, sp.section, sp.placement)[1] for _ in range(4)]
        coarse_times_ms.extend([ms, *reps])

        # Voller Befund (Produktivpfad).
        fnd = full_finding(ctx, sid)
        n_red = int(fnd["n_red"])
        n_yellow = int(fnd["n_yellow"])
        n_green = int(fnd["n_green"])
        n_samples = n_red + n_yellow + n_green
        min_mm = fnd["min_distance_mm"]

        # Verursacher nur der ROTEN Samples (die gefaehrlichen).
        c_link = fnd["causer_link"]
        c_against = fnd["causer_against"]
        dists = fnd["distances_mm"]
        red_link = Counter()
        red_against = Counter()
        for d, li, ag in zip(dists, c_link, c_against):
            if d is not None and d < 0.0:
                red_link[link_label(li)] += 1
                red_against[str(ag)] += 1

        part = {
            "section_id": sid,
            "coarse_collides": hit,
            "coarse_ms": round(ms, 3),
            "coarse_n_poses": n_poses,
            "n_samples": n_samples,
            "n_red": n_red,
            "n_yellow": n_yellow,
            "n_green": n_green,
            "min_distance_mm": min_mm,
            "full_red": n_red > 0,
            "red_causer_link": dict(red_link),
            "red_causer_against": dict(red_against),
        }
        per_part.append(part)
        dt = time.perf_counter() - t_wall
        print(f"  [{k:2d}/16] {sid:<13} coarse={'RED ' if hit else 'free'} "
              f"({ms:6.2f} ms, {n_poses} Posen) | full n_red={n_red:5d} "
              f"min={min_mm} | {dt:4.1f}s")

    # --- Konfusionsmatrix -----------------------------------------------------
    tp = sum(1 for p in per_part if p["coarse_collides"] and p["full_red"])
    fp = sum(1 for p in per_part if p["coarse_collides"] and not p["full_red"])
    fn = sum(1 for p in per_part if not p["coarse_collides"] and p["full_red"])
    tn = sum(1 for p in per_part if not p["coarse_collides"] and not p["full_red"])

    # --- Verursacher aggregiert ----------------------------------------------
    agg_link = Counter()
    agg_against = Counter()
    for p in per_part:
        for kk, vv in p["red_causer_link"].items():
            agg_link[kk] += vv
        for kk, vv in p["red_causer_against"].items():
            agg_against[kk] += vv
    total_red = sum(agg_link.values())
    covered = sum(v for kk, v in agg_link.items()
                  if kk in (f"link{i}" for i in ARM_LINKS))
    missed = total_red - covered

    # --- Kosten ---------------------------------------------------------------
    cost = {
        "n_calls": len(coarse_times_ms),
        "median_ms": round(statistics.median(coarse_times_ms), 3),
        "p95_ms": round(sorted(coarse_times_ms)[int(0.95 * (len(coarse_times_ms) - 1))], 3),
        "max_ms": round(max(coarse_times_ms), 3),
        "min_ms": round(min(coarse_times_ms), 3),
    }

    # --- Sensitivitaet (Teil-Flaeche ist fuer alle 16 identisch → einmal) -----
    sp0 = ctx.plan.sections[0]
    base_spacing = max(sp0.section.length_mm, sp0.section.height_mm) * 0.5
    sensitivity = []
    for pen in (5.0, 20.0, 50.0):
        for label, sp_mm in (("raster_default", None),
                             ("raster_fein_0.25x", base_spacing * 0.25),
                             ("raster_grob_2x", base_spacing * 2.0)):
            hit, ms, n_poses = coarse_verdict(
                ctx, sp0.section, sp0.placement,
                penetration_mm=pen, spacing_mm=sp_mm,
            )
            sensitivity.append({
                "penetration_mm": pen,
                "raster": label,
                "spacing_mm": round(sp_mm, 1) if sp_mm else "default",
                "n_poses": n_poses,
                "collides": hit,
                "ms": round(ms, 3),
            })

    result = {
        "context": {
            "kind": ctx.plan.kind,
            "n_parts": len(ctx.plan.sections),
            "thickness_mm": ctx.thickness_mm,
            "lead_rad": ctx.ori.lead_rad,
            "kipp_rad": ctx.ori.kipp_rad,
            "section_len_mm": sp0.section.length_mm,
            "section_hgt_mm": sp0.section.height_mm,
            "placement": {
                "lateral_mm": sp0.placement.lateral_mm,
                "standoff_mm": sp0.placement.standoff_mm,
                "stand_height_mm": sp0.placement.stand_height_mm,
            },
        },
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "causer": {
            "red_total": total_red,
            "by_link": dict(agg_link),
            "covered_by_arm_links_123": covered,
            "missed_by_arm_links": missed,
            "by_against": dict(agg_against),
        },
        "cost": cost,
        "sensitivity": sensitivity,
        "per_part": per_part,
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("\n=== Konfusionsmatrix (Grob-Check x voller Befund) ===")
    print(f"  TP (grob RED, voll rot)   = {tp}")
    print(f"  FP (grob RED, voll gruen) = {fp}")
    print(f"  FN (grob free, voll rot)  = {fn}   <-- GEFAEHRLICH")
    print(f"  TN (grob free, voll gruen)= {tn}")
    print("\n=== Verursacher der roten Samples (aggregiert) ===")
    print(f"  rot gesamt = {total_red}")
    for kk, vv in agg_link.most_common():
        print(f"    {kk:<10} {vv:8d}  ({100*vv/total_red:5.1f} %)")
    print(f"  von (1,2,3) abgedeckt = {covered} ({100*covered/max(total_red,1):.1f} %), "
          f"verloren = {missed} ({100*missed/max(total_red,1):.1f} %)")
    print("  Gegenspieler:")
    for kk, vv in agg_against.most_common():
        print(f"    {kk:<14} {vv:8d}  ({100*vv/total_red:5.1f} %)")
    print(f"\n=== Kosten path_collides ===  {cost}")
    print("\n=== Sensitivitaet (Teil-Flaeche identisch fuer alle 16) ===")
    for s in sensitivity:
        print(f"  pen={s['penetration_mm']:>4} mm  {s['raster']:<18} "
              f"posen={s['n_poses']:>3}  collides={s['collides']}  ({s['ms']:.2f} ms)")
    print(f"\nJSON: {OUT}")


if __name__ == "__main__":
    main()
