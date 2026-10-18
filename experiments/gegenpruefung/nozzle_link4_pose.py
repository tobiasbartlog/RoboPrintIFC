"""Gegenpruefung A2.4: Eine Pose, in der die Duesenspitze in link_4 steckt, die aber beide Seiten als
frei (d >= d_hard) bewerten, weil SPEC §5.1 das Paar nozzle_tip <-> link_4 nicht prueft.

    PYTHONPATH=core/src /opt/fgc-venv/bin/python -m experiments.gegenpruefung.nozzle_link4_pose
"""

from __future__ import annotations

import numpy as np

from verify.oracle.collision_oracle import CollisionOracle, box_part_mesh

Q_DEG = [0.0, 0.0, 90.0, 0.0, -145.0, 150.0]


def main() -> None:
    q = np.deg2rad(Q_DEG)
    mesh = box_part_mesh((600.0, 200.0, 400.0))
    T_WP = np.eye(4)
    T_WP[:3, 3] = [280.0, 930.0, 901.0]  # Platzierung aus Lauf S1
    o = CollisionOracle(mesh, T_WP, 10.0, 40.0)
    c = o.distance(q, 0, depth=False)
    print(f"q = {Q_DEG} deg")
    print(f"Orakel, Paare nach SPEC §5.1: d = {c.d_mm:.2f} mm {c.pair}")
    o.pairs = [("nozzle_tip", "link_4")]
    print(f"Orakel, nicht gepruefte Paarung nozzle_tip <-> link_4: d = {o.distance(q, 0).d_mm:.2f} mm")
    try:
        from roboprint.collision import World
    except ImportError:
        print("roboprint nicht importierbar (PYTHONPATH=core/src setzen)")
        return
    w = World(mesh, T_WP, 10.0)
    r = w.distance(q, 0)
    print(f"roboprint World.distance: d = {r.d_mm:.2f} mm {r.pair} -> Status "
          f"{'collision' if r.d_mm < 0 else ('warn' if r.d_mm < 50 else 'ok')}")


if __name__ == "__main__":
    main()
