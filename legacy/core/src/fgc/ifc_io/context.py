"""Gebäudekontext: die übrigen Elemente eines IFC-Modells tessellieren.

Der Viewer soll die ausgewählte Wand im Gesamtgebäude zeigen können — er
rechnet aber nichts (ADR-007), also erzeugt der Core den Kontext als eigenes
Artefakt (context.json). Rein visuell: Öffnungskörper, Räume und abstrakte
Elemente (Raster, Annotationen) bleiben draußen.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import numpy as np

from fgc.ifc_io.walls import M_TO_MM, tessellation_settings

#: Nicht-körperliche bzw. störende Produkttypen (Räume würden alles verdecken).
_SKIP_TYPES = ("IfcOpeningElement", "IfcSpace", "IfcAnnotation", "IfcGrid")

#: IFC-Typen, die als Wände gelten und im Übersichts-Kontext ausgeblendet werden.
_WALL_TYPES = ("IfcWall",)


@dataclass
class ContextElement:
    """Ein Umgebungselement: nur Identität + Mesh, keine Planungsdaten."""

    global_id: str
    ifc_type: str
    name: str | None
    vertices_mm: np.ndarray  # (n, 3)
    faces: np.ndarray  # (m, 3) int

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "global_id": self.global_id,
            "ifc_type": self.ifc_type,
            "geometry": {
                "vertices_mm": [[round(float(x), 1) for x in v] for v in self.vertices_mm],
                "faces": [[int(i) for i in f] for f in self.faces],
            },
        }
        if self.name:
            doc["name"] = self.name
        return doc


def load_context(
    ifc_path: str | Path,
    exclude_global_ids: Iterable[str] = (),
    exclude_ifc_types: Iterable[str] = (),
) -> list[ContextElement]:
    """Tesselliert alle IfcProduct-Instanzen mit Körpergeometrie außer den
    ausgeschlossenen (typisch: die ausgewählte Wand oder bestimmte IFC-Typen).

    `exclude_ifc_types` = IFC-Klassenbezeichnungen (z. B. ``("IfcWall",)``),
    die per `is_a()`-Hierarchie gefiltert werden — also auch Untertypen wie
    ``IfcWallStandardCase``. Wird vom Übersichts-Lauf genutzt, um Wände aus dem
    Kontext auszublenden (sie werden dort bereits als eigene Meshes exportiert).
    """
    model = ifcopenshell.open(str(ifc_path))
    settings = tessellation_settings()
    excluded = set(exclude_global_ids)
    skip_types = tuple(_SKIP_TYPES) + tuple(exclude_ifc_types)

    elements: list[ContextElement] = []
    for product in model.by_type("IfcProduct"):
        if product.GlobalId in excluded:
            continue
        if any(product.is_a(t) for t in skip_types):
            continue
        if getattr(product, "Representation", None) is None:
            continue
        try:
            shape = ifcopenshell.geom.create_shape(settings, product)
        except RuntimeError:
            continue  # z.B. reine Kurvengeometrie — für den Kontext verzichtbar
        faces = np.array(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
        if faces.size == 0:
            continue
        vertices = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3) * M_TO_MM
        elements.append(
            ContextElement(
                global_id=product.GlobalId,
                ifc_type=product.is_a(),
                name=product.Name,
                vertices_mm=vertices,
                faces=faces,
            )
        )
    return elements


def load_context_overview(ifc_path: str | Path) -> list[ContextElement]:
    """Lädt den Gebäudekontext für den Übersichts-Lauf (walls-list).

    Schließt Wände (``IfcWall`` und Untertypen) aus, da sie bereits als
    eigene Meshes in ``model.glb`` exportiert werden.  Alle anderen
    sichtbaren Produkte (Decken, Dächer, Stützen, …) werden tesselliert
    und als Kontextelemente zurückgegeben.
    """
    return load_context(ifc_path, exclude_ifc_types=_WALL_TYPES)


def context_artifact(
    model: str,
    elements: list[ContextElement],
    provenance: dict[str, Any],
    *,
    wall_global_id: str | None = None,
) -> dict[str, Any]:
    """Baut das context-Artefakt.

    ``wall_global_id`` ist optional (``None`` für den Übersichts-Lauf, wo
    keine einzelne Wand ausgeschlossen wird, sondern der gesamte Wandtyp).
    Beim Slice-Lauf wird die GlobalId der ausgewählten Wand übergeben.
    """
    artifact: dict[str, Any] = {
        "schema_version": "0.1",
        "provenance": provenance,
        "model": model,
        "elements": [e.to_dict() for e in elements],
    }
    if wall_global_id is not None:
        artifact["wall_global_id"] = wall_global_id
    return artifact
