"""Baut die 4D-Reichweitenkarte des M1013 aus der OPW-IK (PRD #183, #210).

Offline-Gegenstück zu ``build_glied_sdf.py`` für das Gratiswissen-Arbeitspaket:
die Karte entsteht **direkt-invers** — jede 4D-Zelle (p_z, alpha, kanonische
Basisposition) wird an ihrem Knoten exakt über die analytische OPW-IK
ausgewertet (:meth:`fgc.kinematics.reachability.ReachabilityMap.build` — reine,
deterministische Funktion; dieses Skript trägt nur Aufruf + Datei-I/O über
:func:`fgc.kinematics.reachability.save_reachability_map`).

Ablage unter ``robots/reachability/<robot>/``: ``values.npy`` (packbits) +
``manifest.json`` mit Provenienz (Roboter, Auflösung, Kinematik-Fingerabdruck
des Katalogs, Formatstand; US 17, ADR-004). Deterministisch: keine Zeitstempel,
sortierte JSON-Keys — zweifacher Lauf → bitgleich.

Neu erzeugen (Repo-Root, venv mit ``fgc-core[geo]``):

    .venv/Scripts/python.exe core/scripts/build_reachability_map.py [--cell-mm 50.0] [--n-alpha 37]

Laden + Katalog-Validierung: ``fgc.kinematics.load_reachability_map`` (US 18).
"""

from __future__ import annotations

import argparse

from fgc.domain.robot import RobotDef
from fgc.kinematics import reachability as rm
from fgc.kinematics.opw import OpwKinematics

ROBOT = "doosan_m1013"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-mm", type=float, default=rm.DEFAULT_CELL_MM)
    parser.add_argument("--n-alpha", type=int, default=rm.DEFAULT_N_ALPHA)
    args = parser.parse_args()

    robot = RobotDef.load(ROBOT)
    assert robot.kinematics is not None
    kin = OpwKinematics(robot.kinematics)
    rmap = rm.ReachabilityMap.build(kin, cell_mm=args.cell_mm, n_alpha=args.n_alpha)
    out_dir = rm.save_reachability_map(rmap, ROBOT, robot.kinematics)

    shape = "x".join(str(s) for s in rmap.values.shape)
    frac = rmap.values.mean()
    print(
        f"{out_dir / rm.RM_MANIFEST_NAME} geschrieben: Gitter {shape} "
        f"(Zelle {args.cell_mm} mm, {args.n_alpha} alpha-Knoten), "
        f"{int(rmap.values.sum())}/{rmap.values.size} Zellen erreichbar ({frac:.1%})."
    )


if __name__ == "__main__":
    main()
