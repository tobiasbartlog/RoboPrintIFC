"""Kollisions-Geometrie je Roboterglied (ADR-024 Nachtrag 2026-07-08, Issue #125).

Aus den gevendorten URDF-``<collision>``-Meshes eines Arms entsteht **offline**
(Skript ``core/scripts/convert_robot_collision.py``, Muster
``convert_robot_meshes.py``) je Glied (Basis + link1…6) genau zwei Geometrien:

- **Urteilsgeometrie** — die VHACD-Konvexzerlegung der exakten Kollisionsmeshes
  (formtreu ±5,5 mm laut Spike S0), mit der die spätere Simulation den
  minimalen Abstand Arm↔Hindernis *urteilt*.
- **Breitphasen-Hülle** — die konvexe Hülle je Glied als **untere
  Distanz-Schranke** (Hülle ⊇ Roh-Mesh ⇒ Hüllen-Distanz ≤ echte Distanz):
  liegt sie über dem Sicherheitsabstand, ist das Glied sicher grün, und die
  teure VHACD-Abfrage entfällt.

Beide tragen ihre Vertices im **DH-Gliedframe** (``worldV = frames[i]·v``,
dieselbe Offset-Formel wie das GLB-Skript — importiert, nicht kopiert), sodass
die Simulation nur ``mesh.set_transform(frames[i])`` setzen muss.

**Reinheit / Modularität.** Dieses Modul importiert die schweren Geo-Pakete
(``trimesh``, ``vhacdx``) *lazy* — der Core startet ohne ``fgc-core[geo]``
sauber, erst der Aufruf einer Geometrie-Funktion meldet freundlich den fehlenden
Extra (statt Import-Crash). Die Konvexzerlegung :func:`decompose_link` ist eine
**reine** Funktion (Arrays rein, deterministisches Dict raus, keine Datei-I/O);
das URDF-/DAE-Lesen und Schreiben lebt im Offline-Skript, das Lesen des kleinen
Derivats in :func:`load_robot_collision_geometry`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fgc.paths import ROBOTS_DIR

if TYPE_CHECKING:  # nur für Typprüfer — kein Laufzeit-Import (geo-frei startbar)
    import trimesh

GEO_HINT = (
    "Kollisions-Geometrie braucht die Geo-Extras (trimesh, vhacdx). "
    "Installiere sie mit  pip install fgc-core[geo]  (bereits im Projekt-venv)."
)

#: VHACD-Parameter — die *eine* Quelle; landen deterministisch im Manifest.
#: ``asyncACD=False`` erzwingt Determinismus (parallele Zerlegung ist es nicht);
#: die übrigen Werte sind die trimesh-Defaults, mit denen Spike S0 die ±5,5-mm-
#: Formtreue gemessen hat.
VHACD_PARAMS: dict[str, Any] = {
    "maxConvexHulls": 64,
    "resolution": 400000,
    "minimumVolumePercentErrorAllowed": 1.0,
    "maxRecursionDepth": 10,
    "shrinkWrap": True,
    "fillMode": "flood",
    "maxNumVerticesPerCH": 64,
    "asyncACD": False,
    "minEdgeLength": 2,
    "findBestPlane": False,
}

#: Rundung der Vertices (mm) fürs Derivat — Mikrometer-Präzision, weit unter der
#: 5,5-mm-Toleranz, hält die JSON klein und byte-deterministisch.
ROUND_DECIMALS = 3

#: Formtreue-Toleranz der Urteilsgeometrie gegen die Roh-Meshes (Spike S0).
VHACD_TOLERANCE_MM = 5.5

MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class LinkCollisionGeometry:
    """Breitphasen- und Urteilsgeometrie eines Glieds (Vertices im DH-Gliedframe)."""

    index: int
    urdf_link: str
    #: Konvexe Hülle — untere Distanz-Schranke (``trimesh.Trimesh``).
    broadphase_hull: trimesh.Trimesh
    #: VHACD-Konvexstücke — Urteilsgeometrie (``tuple[trimesh.Trimesh, ...]``).
    judgment_parts: tuple[trimesh.Trimesh, ...]


@dataclass(frozen=True)
class RobotCollisionGeometry:
    """Alle Glieder eines Roboters plus Provenienz-Manifest."""

    robot: str
    manifest: dict[str, Any]
    links: tuple[LinkCollisionGeometry, ...]

    def link(self, index: int) -> LinkCollisionGeometry:
        for lk in self.links:
            if lk.index == index:
                return lk
        raise KeyError(f"Glied {index} nicht in der Kollisions-Geometrie von {self.robot!r}")


def _require_geo():
    """Lazy-Import der Geo-Pakete mit freundlichem Fehlpfad statt Import-Crash."""
    try:
        import numpy
        import trimesh
    except ImportError as exc:  # pragma: no cover - Pfad nur ohne [geo]-Extras
        raise ImportError(GEO_HINT) from exc
    return numpy, trimesh


def _mesh_payload(mesh: trimesh.Trimesh, np) -> dict[str, Any]:
    """``trimesh`` → deterministisches, gerundetes ``{vertices_mm, faces}``-Dict."""
    verts = np.round(np.asarray(mesh.vertices, dtype=float), ROUND_DECIMALS)
    faces = np.asarray(mesh.faces, dtype=int)
    return {"vertices_mm": verts.tolist(), "faces": faces.tolist()}


def _payload_to_trimesh(payload: dict[str, Any], trimesh, np) -> trimesh.Trimesh:
    return trimesh.Trimesh(
        vertices=np.asarray(payload["vertices_mm"], dtype=float),
        faces=np.asarray(payload["faces"], dtype=int),
        process=False,
    )


def decompose_link(
    vertices_mm: Any,
    faces: Any,
    vhacd_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reine Zerlegung eines Roh-Glied-Meshes in Hülle + VHACD-Stücke.

    Arrays rein (Vertices in mm im DH-Gliedframe, Dreiecks-``faces``), ein
    deterministisches Dict ``{"broadphase": …, "judgment": [ … ]}`` raus — keine
    Datei-I/O, keine Zeitstempel. Zweifacher Aufruf liefert identische Zahlen
    (``asyncACD=False`` + Rundung), Grundlage der byte-gleichen Ablage.
    """
    np, trimesh = _require_geo()
    params = dict(VHACD_PARAMS if vhacd_params is None else vhacd_params)
    raw = trimesh.Trimesh(
        vertices=np.asarray(vertices_mm, dtype=float),
        faces=np.asarray(faces, dtype=int),
        process=False,
    )
    hull = raw.convex_hull
    parts = raw.convex_decomposition(**params)
    if isinstance(parts, trimesh.Trimesh):  # ältere trimesh-Rückgabe absichern
        parts = [parts]
    return {
        "broadphase": _mesh_payload(hull, np),
        "judgment": [_mesh_payload(p, np) for p in parts],
    }


def collision_dir(robot_name: str, robots_dir: Path | None = None) -> Path:
    """Ablageordner des Kollisions-Derivats laut Roboterkatalog-Referenz.

    Liest die ``collision_geometry``-Referenz *additiv* aus ``robots/<name>.json``
    (Bestand ohne Referenz lädt unverändert). Fehlt sie, freundlicher Hinweis
    aufs Konvertierskript.
    """
    root = robots_dir or ROBOTS_DIR
    catalog = json.loads((root / f"{robot_name}.json").read_text(encoding="utf-8"))
    ref = catalog.get("collision_geometry")
    if not ref:
        raise FileNotFoundError(
            f"Roboter {robot_name!r} referenziert keine Kollisions-Geometrie "
            "(Feld 'collision_geometry'). Erzeuge sie mit "
            "core/scripts/convert_robot_collision.py."
        )
    return root / ref


def load_robot_collision_geometry(
    robot_name: str, robots_dir: Path | None = None
) -> RobotCollisionGeometry:
    """Lädt je Glied Urteils- (VHACD) + Breitphasen-Geometrie (Hülle) aus dem Derivat."""
    np, trimesh = _require_geo()
    directory = collision_dir(robot_name, robots_dir)
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))

    links: list[LinkCollisionGeometry] = []
    for entry in manifest["links"]:
        payload = json.loads((directory / entry["file"]).read_text(encoding="utf-8"))
        hull = _payload_to_trimesh(payload["broadphase"], trimesh, np)
        parts = tuple(_payload_to_trimesh(p, trimesh, np) for p in payload["judgment"])
        links.append(
            LinkCollisionGeometry(
                index=int(entry["index"]),
                urdf_link=str(entry["urdf_link"]),
                broadphase_hull=hull,
                judgment_parts=parts,
            )
        )
    return RobotCollisionGeometry(
        robot=str(manifest["robot"]),
        manifest=manifest,
        links=tuple(links),
    )
