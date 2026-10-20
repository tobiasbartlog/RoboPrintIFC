"""Gegenpruefung A2.4: Liegt das Teil eines Laufs auf der Tischplatte und frei von der Roboterbasis?

Wendet die S2-Pruefung `check_placement` aus verify/check_run.py auch auf S1/S3 an (dort wird sie
nicht aufgerufen) und misst den Abstand des Grundrisses zur Tischkante.

    /opt/fgc-venv/bin/python -m experiments.gegenpruefung.placement_s1 runs/gp/S1
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from verify.check_run import check_placement
from verify.oracle import run_geometry as rg
from verify.oracle.robot_oracle import workstation_frames
from verify.oracle.run_checks import Findings, load_part

run = Path(sys.argv[1])
_, T_WS, _ = workstation_frames()
top = rg.table_top_outline()
for pdir in sorted((run / "parts").glob("*")):
    F = Findings()
    P = load_part(pdir, T_WS, F)
    vW = P.mesh.vertices @ P.T_WP[:3, :3].T + P.T_WP[:3, 3]
    fp = rg.footprint_xy(vW)
    print(f"{pdir.name}: Grundriss W x {vW[:, 0].min():.0f}..{vW[:, 0].max():.0f}, "
          f"y {vW[:, 1].min():.0f}..{vW[:, 1].max():.0f}; Tischplatte bounds {np.round(top.bounds, 1).tolist()}")
    print(f"  Abstand Grundriss -> Tischkante (innen): {top.exterior.distance(fp) if hasattr(top, 'exterior') else 'n/a'}")
    print(f"  Flaeche ausserhalb Tischplatte: {fp.difference(top).area:.1f} mm2")
    check_placement(P, F)
    print(f"  check_placement (S2-Regel): {F.errors or 'bestanden'}")
