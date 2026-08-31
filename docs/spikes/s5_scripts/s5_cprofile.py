"""S5-Sonde 1 — cProfile-Grobverteilung der **echten** ``find_collisions``.

Profiliert genau den Produktivcode (``fgc.collision.check.find_collisions``) an
der realen Abschnitt-1-Bahn und schreibt die Top-Funktionen nach Eigenzeit
(``tottime``) und kumulierter Zeit (``cumtime``). So sieht man, wieviel in
fcl-``min_distance_other`` (Urteil), in ``transform.compose``/``_matrix``
(FK-Verkettung), in ``_aabb_gap``/``_corner_box`` (Breitphase) und in
``_obstacle_groups`` (Druckstand-Rebuild je Schicht) steckt — ohne die Zahlen zu
verfälschen (nur ein Profiler-Overhead, kein Instrumentierungs-Wrapper im
Hot-Path).

Aufruf (venv, Repo-Root)::

    ./.venv/Scripts/python.exe docs/spikes/s5_scripts/s5_cprofile.py

Schreibt ``docs/spikes/s5_scripts/last_cprofile.txt`` (voller pstats-Dump) und
gibt eine Zusammenfassung auf stdout.
"""

from __future__ import annotations

import cProfile
import io
import pstats
from pathlib import Path

from s5_harness import build_inputs, verify_reproduction

OUT = Path(__file__).resolve().parent / "last_cprofile.txt"


def main() -> None:
    inp = build_inputs()
    res = verify_reproduction(inp)
    print("Reproduktion:", res, "MATCH" if res["ok"] else "MISMATCH")

    from fgc.collision import check as C

    provider = inp.provider_factory()
    pr = cProfile.Profile()
    pr.enable()
    C.find_collisions(
        inp.geo,
        inp.base,
        inp.link_frames,
        inp.sample_layers,
        provider,
        tcp_frame=inp.tcp_frame,
        tool_hull=inp.tool_hull,
        safety_distance_mm=inp.safety_distance_mm,
        self_collision=False,
    )
    pr.disable()

    st = pstats.Stats(pr)
    total = st.total_tt

    buf = io.StringIO()
    buf.write("# cProfile find_collisions — Abschnitt-1 (Denkmal, Modul)\n")
    buf.write(f"# n_samples={inp.n_samples} n_layers={inp.n_layers} total_tt={total:.3f}s\n\n")
    buf.write("## Top 30 nach tottime (Eigenzeit)\n")
    st2 = pstats.Stats(pr, stream=buf)
    st2.sort_stats("tottime").print_stats(30)
    buf.write("\n## Top 30 nach cumtime (kumuliert)\n")
    st2.sort_stats("cumtime").print_stats(30)
    OUT.write_text(buf.getvalue(), encoding="utf-8")

    # Kompakte stdout-Zusammenfassung: die für die Hebel relevanten Symbole.
    print(f"\ntotal_tt = {total:.3f} s über {inp.n_samples} Samples "
          f"({1000*total/inp.n_samples:.3f} ms/Sample)\n")
    keys = [
        ("min_distance_other", "fcl-Urteil (judgment)"),
        ("min_distance_internal", "fcl intern"),
        ("compose", "transform.compose (FK-Verkettung)"),
        ("_matrix", "_matrix (Frame->4x4)"),
        ("_quat_to_rot", "Quat->Rot"),
        ("_aabb_gap", "AABB-Breitphase"),
        ("_corner_box", "AABB-Ecken"),
        ("_obstacle_groups", "Druckstand-Gruppen-Rebuild"),
        ("set_transform", "fcl set_transform"),
        ("_in_freizone", "Freizonen-Test"),
    ]
    print(f"{'Symbol':40s} {'tottime':>9s} {'cumtime':>9s} {'ncalls':>10s}")
    stats = st.stats  # dict {(file,line,func): (cc,nc,tt,ct,callers)}
    for needle, label in keys:
        tt = ct = 0.0
        nc = 0
        for (fn, ln, func), (cc, ncalls, t, c, callers) in stats.items():
            if needle == func:
                tt += t
                ct += c
                nc += ncalls
        if nc:
            print(f"{label:40s} {tt:9.3f} {ct:9.3f} {nc:10d}")
    print(f"\nVoller Dump: {OUT}")


if __name__ == "__main__":
    main()
