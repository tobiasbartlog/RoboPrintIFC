"""Gegenpruefung A2.4: Zeitachse (Gelenk-/TCP-Geschwindigkeit aus t_s) und Gierwinkel im Ring.

    /opt/fgc-venv/bin/python -m experiments.gegenpruefung.timing_psi runs/gp/S1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

VMAX = np.deg2rad([120, 120, 180, 225, 225, 225])

run = Path(sys.argv[1])
pdir = min((run / "parts").glob("*"))
tr = json.loads((pdir / "trajectory.json").read_text())
t = np.array(tr["t_s"])
q = np.array(tr["q"])
tcp = np.array(tr["tcp"])[:, :3]
kind = np.array(tr["kind"])
ring = np.array(tr["ring"])
psi = np.array(tr["psi_rad"])
dt = np.diff(t)
print(f"t_s streng monoton: {bool(np.all(dt > 0))}, min dt {dt.min():.2e} s, Dauer {t[-1]:.1f} s")
qd = np.abs(np.diff(q, axis=0)) / dt[:, None]
v = np.linalg.norm(np.diff(tcp, axis=0), axis=1) / dt
for k in ("print", "approach", "retract", "lift", "transfer", "lower"):
    m = kind[1:] == k
    frac = (qd[m] / VMAX).max(0)
    i = np.flatnonzero(m)[np.argmax((qd[m] / VMAX).max(1))]
    print(f"{k:9s} max TCP {v[m].max():7.1f} mm/s, max Gelenk/Grenze je Achse {np.round(frac, 3).tolist()}"
          f" (Schritt #{i})")
# Gierwinkel innerhalb eines Druckrings
dpsi_max = 0.0
where = None
for r in np.unique(ring):
    m = (kind == "print") & (ring == r)
    if m.sum() < 2:
        continue
    p = np.unwrap(psi[m])
    span = p.max() - p.min()
    if span > dpsi_max:
        dpsi_max, where = span, r
print(f"groesste psi-Spanne in einem Druckring: {np.degrees(dpsi_max):.1f} deg (Ring {where})")
