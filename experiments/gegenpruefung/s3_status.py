"""Gegenpruefung A2.4: Stimmen in S3 auch die NICHT als Kollision gemeldeten Samples?

check_run prueft in S3 nur die von roboprint als `collision` gemeldeten Samples. Dieses Skript rechnet
die Samples an jedem Statuswechsel (+-3) und eine Zufallsstichprobe der uebrigen mit dem Coal-Orakel
nach und vergleicht mit roboprint (G2-Toleranz: roboprint darf hoechstens 1 mm optimistischer sein).

    /opt/fgc-venv/bin/python -m experiments.gegenpruefung.s3_status runs/gp/S3 [--n 300]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import trimesh

from verify.oracle.collision_oracle import CollisionOracle

ap = argparse.ArgumentParser()
ap.add_argument("run", type=Path)
ap.add_argument("--n", type=int, default=300)
a = ap.parse_args()
pdir = min((a.run / "parts").glob("*"))
tr = json.loads((pdir / "trajectory.json").read_text())
part = json.loads((pdir / "part.json").read_text())
mesh = trimesh.load(str(pdir / "part.stl"), force="mesh")
o = CollisionOracle(mesh, np.array(part["T_WP"]), 10.0, 40.0)
st = tr["status"]
N = len(st)
print(f"N={N}, Status {dict(Counter(st))}")
coll = np.array([s == "collision" for s in st])
edges = np.flatnonzero(np.diff(coll.astype(int)) != 0)
sel = set()
for e in edges:
    sel.update(range(max(0, e - 3), min(N, e + 5)))
rng = np.random.default_rng(20261018)
sel.update(rng.choice(np.flatnonzero(~coll), size=min(a.n, int((~coll).sum())), replace=False).tolist())
sel.update(rng.choice(np.flatnonzero(coll), size=min(a.n // 3, int(coll.sum())), replace=False).tolist())
bad = []
for i in sorted(sel):
    if st[i] == "unreachable":
        continue
    c = o.distance(np.array(tr["q"][i]), int(tr["layer"][i]), depth=False)
    d_rp = tr["d_mm"][i]
    if (c.d_mm < 0) != (st[i] == "collision") or d_rp > c.d_mm + 1.0 and c.d_mm >= 0:
        bad.append((i, tr["kind"][i], st[i], d_rp, c.d_mm, c.pair, tr["pair"][i]))
print(f"nachgerechnet: {len(sel)} Samples ({len(edges)} Statuswechsel)")
print(f"Abweichungen (Vorzeichen verschieden oder roboprint > Orakel + 1 mm): {len(bad)}")
for b in bad[:15]:
    print(f"  #{b[0]} {b[1]} roboprint {b[2]} d={b[3]:.2f} {b[6]} | Orakel d={b[4]:.2f} {b[5]}")
