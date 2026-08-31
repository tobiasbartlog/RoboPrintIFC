"""GLB-Export einer Wandmenge als binäre glTF (ADR-015: neutrale Geometrie).

Baut aus benannten Wand-Meshes eine `trimesh.Scene` — ein Szenenknoten je Wand,
der Knotenname trägt die Zuordnung (die GlobalId setzt der Aufrufer) — und
schreibt sie als GLB. Kein Import anderer fgc-Module: nimmt nur primitive
Vertex-/Face-Arrays entgegen. Genutzt von `pipeline.actions.walls_to_run` für
das Modell-glTF eines walls-list-Laufs (Issue #6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import trimesh


def export_walls_glb(meshes: dict[str, tuple[Any, Any]], out_path: Path) -> Path:
    """Schreibt die benannten Wand-Meshes als binäre glTF (GLB) nach `out_path`.

    `meshes` bildet Knotennamen auf `(vertices, faces)` ab (Sequenzen von
    3er-Tupeln bzw. Index-Tripeln, auch NumPy-Arrays). Jeder Eintrag wird ein
    eigener Szenenknoten mit genau diesem Namen — beim Re-Import (three.js
    GLTFLoader / trimesh) bleiben die Namen erhalten, sodass der Viewer jede
    Wand über die model_map wiederfindet.
    """
    scene = trimesh.Scene(
        {
            node_name: trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            for node_name, (vertices, faces) in meshes.items()
        }
    )
    out_path.write_bytes(scene.export(file_type="glb"))
    return out_path
