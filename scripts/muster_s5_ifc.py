"""Erzeugt das IFC für das Musterszenario S5 (Modul mit Öffnung).

Aufruf: `python scripts/muster_s5_ifc.py [--out docs/muster/szenarien/S5_fensterwand.ifc]`

Warum synthetisch: `examples/Building-Architecture.ifc` (S2) enthält keine Öffnung (kein
`IfcOpeningElement`, `IfcWindow`, `IfcDoor`; `roboprint.ifc.read_walls` liefert für alle vier Wände
`openings = []`). Kein S2-Modul hat deshalb eine Öffnung. S5 nimmt eine Wand wie die S2-Außenwände
(200 mm dick) und setzt ein Fenster hinein:

- Wand 600 × 200 × 400 mm (Länge × Dicke × Höhe), gerade, im Ursprung.
- Fenster x = 180 … 420 mm (240 mm breit), Brüstung z0 = 150 mm, Sturz z1 = 400 mm.

Das ist genau das untere Modul einer höheren Wand mit Sturz bei 400 mm: Die Zerlegung schneidet an
der Sturzlinie (`decompose.mandatory_cuts`), darüber liegt ein prismatisches Modul. Länge ≤ b_max
(600 mm) und Höhe ≤ `module_height_max_mm` (400 mm), also entsteht genau ein Modul: Schichten 0–14
voller Querschnitt (Brüstung), ab Schicht 15 zwei Inseln (Pfeiler 180 mm, ≥ 151 mm für `topologie`).
Die Datei ist deterministisch (feste GlobalIds), damit Läufe vergleichbar bleiben.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import ifcopenshell
import ifcopenshell.api

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "muster" / "szenarien" / "S5_fensterwand.ifc"

LENGTH, THICK, HEIGHT = 0.600, 0.200, 0.400  # m (IFC in Metern)
WIN_X0, WIN_X1, WIN_Z0, WIN_Z1 = 0.180, 0.420, 0.150, 0.400
GUIDS = {
    "project": "0S5MusterProjekt00000a",
    "site": "0S5MusterSite000000000a",
    "building": "0S5MusterGebaeude00000a",
    "storey": "0S5MusterGeschoss00000a",
    "wall": "0S5MusterFensterwand0a",
    "opening": "0S5MusterFenster000000a",
}


def _guid(g: str) -> str:
    # IFC-GlobalId: 22 Zeichen aus dem IFC-Base64-Alphabet
    return (g + "0" * 22)[:22]


def build(out: Path) -> Path:
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="S5 Musterszenario")
    ifcopenshell.api.run("unit.assign_unit", f)  # Meter
    ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context",
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Building")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="EG")
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=building, products=[storey])

    wall = ifcopenshell.api.run(
        "root.create_entity", f, ifc_class="IfcWall", name="S5 Fensterwand (synthetisch, 200 mm wie S2)"
    )
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=wall)
    rep = ifcopenshell.api.run(
        "geometry.add_wall_representation", f, context=body, length=LENGTH, height=HEIGHT, thickness=THICK
    )
    ifcopenshell.api.run("geometry.assign_representation", f, product=wall, representation=rep)
    ifcopenshell.api.run("spatial.assign_container", f, relating_structure=storey, products=[wall])

    opening = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcOpeningElement", name="Fenster")
    import numpy as np

    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = WIN_X0, -0.05, WIN_Z0
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=opening, matrix=m)
    orep = ifcopenshell.api.run(
        "geometry.add_wall_representation",
        f,
        context=body,
        length=WIN_X1 - WIN_X0,
        height=(WIN_Z1 - WIN_Z0) + 0.05,
        thickness=THICK + 0.10,
    )
    ifcopenshell.api.run("geometry.assign_representation", f, product=opening, representation=orep)
    ifcopenshell.api.run("feature.add_feature", f, feature=opening, element=wall)

    for key, ent in (
        ("project", project),
        ("site", site),
        ("building", building),
        ("storey", storey),
        ("wall", wall),
        ("opening", opening),
    ):
        ent.GlobalId = _guid(GUIDS[key])
    out.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(out))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    print(build(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
