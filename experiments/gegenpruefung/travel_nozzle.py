"""Gegenpruefung A2.4: Wo ist die Duesenspitze (TCP) relativ zum Druckstand?

SPEC §5.1 nimmt nozzle_tip <-> printed generell aus (Freizone). Dieses Skript misst je Sample-Art
die Hoehe des TCP ueber der Druckstand-Oberkante k*h, wenn der TCP ueber dem Grundriss des Teils
liegt. Nur Artefakte, kein roboprint-Import.

    /opt/fgc-venv/bin/python experiments/gegenpruefung/travel_nozzle.py runs/gp/S1/parts/box_01
"""

import json
import sys
from pathlib import Path

import numpy as np

d = Path(sys.argv[1])
tr = json.loads((d / "trajectory.json").read_text())
part = json.loads((d / "part.json").read_text())
T_WP = np.array(part["T_WP"])
inv = np.linalg.inv(T_WP)
tcp = np.array(tr["tcp"])[:, :3]
pP = tcp @ inv[:3, :3].T + inv[:3, 3]
lo, hi = np.array(part["bbox_P"]["min"]), np.array(part["bbox_P"]["max"])
kind = np.array(tr["kind"])
layer = np.array(tr["layer"])
h = 10.0
inside = (pP[:, 0] > lo[0]) & (pP[:, 0] < hi[0]) & (pP[:, 1] > lo[1]) & (pP[:, 1] < hi[1])
for k in ("lift", "transfer", "lower", "approach", "retract", "print"):
    m = (kind == k) & inside
    if not m.any():
        continue
    clr = pP[m, 2] - layer[m] * h
    i = np.flatnonzero(m)[np.argmin(clr)]
    print(f"{k:9s} n={m.sum():6d} TCP ueber Druckstand-Oberkante (ueber Grundriss): min {clr.min():7.2f} mm "
          f"bei #{i} (k={layer[i]}, p_P={np.round(pP[i], 1).tolist()})")
