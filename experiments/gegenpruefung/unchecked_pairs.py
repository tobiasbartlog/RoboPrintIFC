"""Gegenpruefung A2.4: Paare, die SPEC §5.1 NICHT prueft.

SPEC §5.1 prueft nozzle_tip nur gegen Boden und Tisch und tool_body nur gegen base_link..link_4.
Dieses Skript misst mit dem Coal-Orakel (Roh-Meshes) die Abstaende der ausgelassenen Paare
- nozzle_tip <-> base_link..link_5, tool_body <-> link_5
1. auf den Samples eines Laufs (jedes `--every`-te) und
2. als Gitter ueber (q5, q6) im gesamten Grenzbereich (die Paare haengen nur von q5/q6 bzw. q4..q6 ab).

    /opt/fgc-venv/bin/python -m experiments.gegenpruefung.unchecked_pairs runs/gp/S1 [--every 20]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from verify.oracle.collision_oracle import CollisionOracle, checked_pairs

PAIRS = [("nozzle_tip", n) for n in ("base_link", "link_1", "link_2", "link_3", "link_4", "link_5")]
PAIRS.append(("tool_body", "link_5"))


def per_pair(o: CollisionOracle, q) -> dict:
    out = {}
    for p in PAIRS:
        o.pairs = [p]
        out[p] = o.distance(q, 0, depth=False).d_mm
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--every", type=int, default=20)
    a = ap.parse_args()
    pdir = min((a.run / "parts").glob("*"))
    tr = json.loads((pdir / "trajectory.json").read_text())
    o = CollisionOracle(None, None, 10.0, 40.0)
    q = np.array(tr["q"])
    best = {p: (np.inf, None) for p in PAIRS}
    for i in range(0, len(q), a.every):
        for p, d in per_pair(o, q[i]).items():
            if d < best[p][0]:
                best[p] = (d, i)
    print(f"Lauf {a.run} (jedes {a.every}. Sample):")
    for p, (d, i) in best.items():
        print(f"  {p[0]:10s} <-> {p[1]:9s}: min d = {d:8.2f} mm bei #{i}")
    # Gitter ueber q5, q6 (q1..q4 = Home-Werte; die Paare zu link_4/link_5 haengen nur von q5, q6 ab)
    grid_best = {p: (np.inf, None) for p in PAIRS if p[1] in ("link_4", "link_5")}
    for q5 in np.deg2rad(np.arange(-180, 181, 5)):
        for q6 in np.deg2rad(np.arange(-180, 181, 10)):
            qq = np.array([0.0, 0.0, np.pi / 2, 0.0, q5, q6])
            for p in grid_best:
                o.pairs = [p]
                d = o.distance(qq, 0, depth=False).d_mm
                if d < grid_best[p][0]:
                    grid_best[p] = (d, (round(np.degrees(q5)), round(np.degrees(q6))))
    print("Gitter q5 in [-180, 180] (5 deg), q6 in [-180, 180] (10 deg):")
    for p, (d, w) in grid_best.items():
        print(f"  {p[0]:10s} <-> {p[1]:9s}: min d = {d:8.2f} mm bei (q5, q6) = {w} deg")
    # Faengt eines der geprueften Selbstkollisionspaare diese Posen ab?
    self_pairs = [p for p in checked_pairs() if p[1] not in ("floor", "table", "printed")]
    # Gesucht: nozzle_tip<->link_4 < 0, waehrend das kleinste GEPRUEFTE Selbstkollisions-d gross ist.
    worst = (-np.inf, None, None)
    n_coll = n_hidden = 0
    for q5 in range(-180, 181, 5):
        for q6 in range(-180, 181, 10):
            qq = np.deg2rad([0.0, 0.0, 90.0, 0.0, q5, q6])
            o.pairs = [("nozzle_tip", "link_4")]
            if o.distance(qq, 0, depth=False).d_mm >= 0:
                continue
            n_coll += 1
            o.pairs = self_pairs
            c = o.distance(qq, 0, depth=False)
            n_hidden += c.d_mm >= 10.0
            if c.d_mm > worst[0]:
                worst = (c.d_mm, (q5, q6), c.pair)
    print(f"Gitterposen mit nozzle_tip<->link_4 < 0: {n_coll}; davon mit geprueftem d_self >= d_hard: {n_hidden}")
    print(f"  groesstes geprueftes d_self bei Duesenkollision: {worst[0]:.2f} mm {worst[2]} bei (q5, q6) = "
          f"{worst[1]} deg")


if __name__ == "__main__":
    main()
