"""fgc.eligibility — Eignungsprüfung E1 (ADR-013): Wand -> WallCandidate.

Der Grundriss für check_footprint wird über das neutrale Schnittmodul
``fgc.geometry.section`` aus dem Wand-Mesh gewonnen (ADR-015): horizontaler
Schnitt in Wandmitte → erstes Polygon als Grundriss-Polygon. Damit entfällt
die frühere Abhängigkeit auf eine externe Grundriss-Quelle; der Check läuft
jetzt real (nicht mehr provisional wegen fehlendem Polygon), sobald die Karte
die Prüfgrenzen trägt.
"""

from __future__ import annotations

import trimesh

from fgc.domain.models import WallCandidate
from fgc.domain.process_params import ProcessWindow
from fgc.domain.robot import RobotDef
from fgc.eligibility.rules import STAGE1_RULES, EligibilityContext, Rule
from fgc.geometry.section import section_at
from fgc.ifc_io.walls import WallData

__all__ = ["EligibilityContext", "Rule", "STAGE1_RULES", "evaluate_wall"]


def evaluate_wall(
    wall: WallData,
    window: ProcessWindow,
    robot: RobotDef,
    rules: tuple[Rule, ...] = STAGE1_RULES,
) -> WallCandidate:
    """Wendet alle Regeln an; eligible = alle bestanden (provisional zählt als bestanden).

    Der Grundriss wird aus dem Wand-Mesh gewonnen (ADR-015):
    horizontaler Schnitt in Wandmitte → erstes (i. d. R. einziges) Polygon.
    Mehrere disjunkte Teilpolygone (z. B. getrennte Wandabschnitte) sind möglich;
    für die Eignungsprüfung wird das erste (nach Schwerpunkt-x, dann -y sortiert)
    herangezogen — bei getrennten Abschnitten ist dies der am weitesten links
    liegende.
    """
    mesh = trimesh.Trimesh(vertices=wall.vertices_mm, faces=wall.faces, process=False)
    z_min, z_max = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    z_mid = (z_min + z_max) / 2.0
    polys = section_at(mesh, z_mid)
    footprint_poly = polys[0] if polys else None

    ctx = EligibilityContext(wall=wall, window=window, robot=robot, footprint=footprint_poly)
    checks = [rule(ctx) for rule in rules]
    g = wall.geometry
    return WallCandidate(
        global_id=wall.global_id,
        name=wall.name,
        eligible=all(c.passed for c in checks),
        dimensions_mm={
            "length": round(g.length_mm, 1),
            "height": round(g.height_mm, 1),
            "thickness": round(g.thickness_mm, 1),
        },
        checks=checks,
    )
