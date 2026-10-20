"""Gegenpruefung A2.4: Wie weit kann d zwischen zwei geprueften Samples fallen?

SPEC §5.2/5 und G3 pruefen d >= d_hard nur auf den Samples (TCP <= 5 mm, max|dq| <= 0,005 rad).
Dieses Skript
1. schaetzt je Schritt i -> i+1 die groesste Verschiebung eines Koerperpunkts (Huellkugel-Odometer wie
   verify/oracle/interval_checker._disp) und daraus eine untere Schranke fuer d zwischen den Samples:
   d_zw >= (d_i + d_i+1 - (s_a + s_b)) / 2 (s = Verschiebung der beiden Koerper; hier konservativ
   2 * max ueber alle bewegten Koerper);
2. rechnet fuer die kritischsten Schritte (Schranke < d_hard) mit dem Coal-Orakel auf Roh-Meshes an
   9 Zwischenstellungen nach (gelenklineare Zwischenstellung; bei movel weicht sie bei diesen
   Schrittweiten um << 0,1 mm von der kartesischen Bahn ab, wird mit ausgegeben).
Nur Orakel aus verify/ und Artefakte, kein roboprint-Import.

    /opt/fgc-venv/bin/python -m experiments.gegenpruefung.between_samples runs/gp/S1 [--top 40]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import trimesh

from verify.oracle.collision_oracle import CollisionOracle
from verify.oracle.interval_checker import _disp
from verify.oracle.robot_oracle import default_robot, workstation_frames

MOVING = ("link_2", "link_3", "link_4", "link_5", "link_6", "tool_body", "nozzle_tip")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--d-hard", type=float, default=10.0)
    ap.add_argument("--all", action="store_true", help="alle Schritte mit Schranke < d_hard nachrechnen")
    ap.add_argument("--fractions", type=int, default=11)
    a = ap.parse_args()
    pdir = min((a.run / "parts").glob("*"))
    tr = json.loads((pdir / "trajectory.json").read_text())
    part = json.loads((pdir / "part.json").read_text())
    mesh = trimesh.load(str(pdir / "part.stl"), force="mesh")
    q = np.array(tr["q"])
    d = np.array([np.nan if v is None else v for v in tr["d_mm"]], float)
    layer = np.array(tr["layer"])
    kind = tr["kind"]
    N = len(q)
    o = CollisionOracle(mesh, np.array(part["T_WP"]), 10.0, 40.0)
    T_WB = workstation_frames()[0]
    robot = default_robot()
    # Verschiebung je Schritt
    prev = o.body_poses(q[0])
    step = np.zeros(N - 1)
    for i in range(1, N):
        cur = o.body_poses(q[i])
        step[i - 1] = max(_disp(o._body(n, 0).c, o._body(n, 0).r, prev[n], cur[n]) for n in MOVING)
        prev = cur
    lbz = (d[:-1] + d[1:] - 2 * step) / 2
    print(f"N={N}, max. Punktverschiebung je Schritt: {step.max():.2f} mm (Median {np.median(step):.2f})")
    for k in sorted(set(kind)):
        m = np.array([kind[i] == k for i in range(N - 1)])
        print(f"  {k:9s} max Schritt {step[m].max():6.2f} mm, min Schranke d_zw {np.nanmin(lbz[m]):7.2f} mm")
    order = np.argsort(np.where(np.isfinite(lbz), lbz, np.inf))
    cand = order[: int(np.sum(lbz < a.d_hard))] if a.all else order[: a.top]
    verbose = not a.all
    print(f"Schritte mit Schranke < d_hard: {int(np.sum(lbz < a.d_hard))}")
    worst = (np.inf, None)
    drop = (0.0, None)
    for i in cand:
        fr = np.linspace(0, 1, a.fractions)
        ds = []
        for f in fr:
            qi = (1 - f) * q[i] + f * q[i + 1]
            ds.append(o.distance(qi, int(layer[i + 1] if f > 0.5 else layer[i]), depth=False).d_mm)
        ds = np.array(ds)
        # Abweichung der gelenklinearen Mitte von der kartesischen Geraden (nur Info)
        pa = (T_WB @ robot.fk_tcp(q[i]))[:3, 3]
        pb = (T_WB @ robot.fk_tcp(q[i + 1]))[:3, 3]
        pm = (T_WB @ robot.fk_tcp(0.5 * (q[i] + q[i + 1])))[:3, 3]
        dev = float(np.linalg.norm(pm - 0.5 * (pa + pb)))
        if ds.min() < worst[0]:
            worst = (ds.min(), i)
        if min(ds[0], ds[-1]) - ds.min() > drop[0]:
            drop = (min(ds[0], ds[-1]) - ds.min(), i)
        if verbose:
            print(f"#{i}->{i + 1} {kind[i]}/{kind[i + 1]} k={layer[i]} Schritt {step[i]:.2f} mm, "
                  f"d_rp {d[i]:.2f}/{d[i + 1]:.2f}, Orakel Samples {ds[0]:.2f}/{ds[-1]:.2f}, "
                  f"min zwischen {ds[1:-1].min():.2f} mm, Abfall ggue. min(Enden) "
                  f"{min(ds[0], ds[-1]) - ds[1:-1].min():.3f} mm, gelenklin. Mitte {dev:.3f} mm neben Gerade")
    print(f"nachgerechnete Schritte: {len(cand)}")
    print(f"kleinstes Orakel-d zwischen Samples: {worst[0]:.3f} mm bei Schritt #{worst[1]}")
    print(f"groesster Abfall zwischen Samples ggue. min(Enden): {drop[0]:.3f} mm bei Schritt #{drop[1]}")


if __name__ == "__main__":
    main()
