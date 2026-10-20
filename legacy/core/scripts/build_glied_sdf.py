"""Baut die Glied-SDF-Artefakte des M1013 aus der #125-Urteilsgeometrie (PRD #183, #207).

Gegenstück zu ``convert_robot_collision.py`` für die SDF-Prüf-Tür: je Glied
(Basis + link1…6) entsteht **offline** ein statisches Voxel-SDF im
DH-Gliedframe (:func:`fgc.collision.glied_sdf.build_link_field` — reine,
deterministische Funktion; dieses Skript trägt nur die Datei-I/O). Quelle ist
die **Urteilsgeometrie** (VHACD-Konvexstücke) des katalog-referenzierten
Kollisions-Derivats — SDF und FCL-Referenz urteilen über dieselbe Geometrie.

Ablage unter ``robots/collision/<robot>/sdf/``: ein ``<glied>.npy`` (float32,
exakte Knotenwerte, mm) je Glied plus ``manifest.json`` mit Provenienz
(Roboter, Auflösung, Buildstand = SHA-256 der Quelldateien, Formatstand,
Upstream-Kette der Quelle; US 17, ADR-004). Deterministisch: feste
Glied-/Datei-Reihenfolge, keine Zeitstempel, sortierte JSON-Keys — zweifacher
Lauf → bitgleich (auf derselben Plattform, s. Design-Log 2026-07-10 zur
VHACD-Quelle).

Neu erzeugen (Repo-Root, venv mit ``fgc-core[geo]``):

    .venv/Scripts/python.exe core/scripts/build_glied_sdf.py [--voxel-mm 8.0] [--padding-mm 80.0]

Achtung: eine abweichende ``--voxel-mm`` weicht vom Lade-Default
(``DEFAULT_VOXEL_MM``) ab — ``load_glied_sdf`` verlangt dann denselben Wert
explizit (Schutz vor veralteter Auflösung, US 18).
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from fgc.collision import glied_sdf as gs
from fgc.collision import robot_geometry as rg

ROBOT = "doosan_m1013"

#: Feste Dateireihenfolge — gleiche Konvention wie das Kollisions-Derivat.
LINK_FILES = ["base.npy"] + [f"link{i}.npy" for i in range(1, 7)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voxel-mm", type=float, default=gs.DEFAULT_VOXEL_MM)
    parser.add_argument("--padding-mm", type=float, default=gs.DEFAULT_PADDING_MM)
    args = parser.parse_args()

    geo = rg.load_robot_collision_geometry(ROBOT)
    src_dir = rg.collision_dir(ROBOT)
    out_dir = src_dir / gs.SDF_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    links_manifest = []
    for lk in geo.links:
        parts = [(p.vertices, p.faces) for p in lk.judgment_parts]
        field = gs.build_link_field(parts, voxel_mm=args.voxel_mm, padding_mm=args.padding_mm)
        fname = LINK_FILES[lk.index]
        np.save(out_dir / fname, field["values"])
        links_manifest.append(
            {
                "index": lk.index,
                "urdf_link": lk.urdf_link,
                "file": fname,
                "shape": list(field["values"].shape),
                "origin_mm": np.round(field["origin_mm"], 6).tolist(),
                "object_bounds_mm": np.round(field["object_bounds_mm"], 6).tolist(),
                "value_range_mm": [
                    round(float(field["values"].min()), 3),
                    round(float(field["values"].max()), 3),
                ],
            }
        )
        print(
            f"  Glied {lk.index} ({lk.urdf_link}) -> {fname}: "
            f"Gitter {'x'.join(str(s) for s in field['values'].shape)}, "
            f"Werte [{links_manifest[-1]['value_range_mm'][0]}, "
            f"{links_manifest[-1]['value_range_mm'][1]}] mm"
        )

    coll_manifest = json.loads((src_dir / rg.MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest = {
        "_comment": "Erzeugt von core/scripts/build_glied_sdf.py — nicht editieren.",
        "sdf_format_version": gs.SDF_FORMAT_VERSION,
        "robot": ROBOT,
        "units": "mm",
        "frame_convention": (
            "Knotenwerte je Glied im DH-Gliedframe (worldV = frames[i]·v), dieselbe "
            "Konvention wie das Kollisions-Derivat (Issue #125)."
        ),
        "semantics": (
            "Signierte Distanz (negativ = innen) zur Vereinigung der VHACD-"
            "Urteilsstücke — dieselbe Referenzgeometrie wie der FCL-Pfad. Abfragen "
            "ziehen das Interpolationsband ab: Distanz wird nie überschätzt."
        ),
        "voxel_mm": float(args.voxel_mm),
        "padding_mm": float(args.padding_mm),
        "interpolation_band_mm": round(gs.interpolation_band_mm(args.voxel_mm), 6),
        "generator": "core/scripts/build_glied_sdf.py",
        "source": (
            "robots/" + str(src_dir.relative_to(src_dir.parent.parent)).replace("\\", "/")
            + " (Urteilsgeometrie/VHACD, Issue #125)"
        ),
        "source_files_sha256": gs.source_fingerprint(src_dir),
        "source_upstream": coll_manifest.get("upstream"),
        "links": links_manifest,
    }
    (out_dir / gs.SDF_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"{out_dir / gs.SDF_MANIFEST_NAME} geschrieben: {len(links_manifest)} Glieder.")


if __name__ == "__main__":
    main()
