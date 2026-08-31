"""Glied-SDF: statisches Voxel-SDF je Armglied im Glied-Koordinatensystem (PRD #183, #207).

Arbeitspaket 1 der SDF-Prüf-Tür (invertiert nach Shen 2026): die teure Vorarbeit
liegt auf dem, was sich nie ändert — **je Armglied ein statisches Voxel-Feld der
signierten Distanz**, einmalig offline gebaut (Skript
``core/scripts/build_glied_sdf.py``; Quelle ist die #125-**Urteilsgeometrie**,
also dieselben VHACD-Konvexstücke, mit denen der FCL-Pfad urteilt — SDF und
FCL-Referenz sprechen über dieselbe Geometrie). Persistiert als versioniertes
Artefakt (``robots/collision/<robot>/sdf/``: ein ``.npy`` je Glied +
``manifest.json`` mit Provenienz), beim Laden gegen den Roboterkatalog und den
Buildstand der Quellgeometrie validiert (US 17/18, ADR-004). **Kein neuronales
Feld** (PRD Out of Scope).

**Kernvertrag: Distanz nie überschätzen.** :meth:`LinkSdf.distance` liefert eine
**untere Schranke** der FCL-Referenzdistanz (min über die VHACD-Stücke, negativ
bei Durchdringung — dieselbe Semantik wie ``CollisionManager.min_distance_*``):

- Die **Knotenwerte** sind exakt: außerhalb der Stück-Vereinigung die Distanz zur
  nächsten Stück-Oberfläche (identisch mit der Solid-Distanz), innerhalb der
  konvex-exakte Wert ``min_i(max_f s_f)`` über die Flächenebenen der Stücke.
- Die **trilineare Interpolation** zwischen Knoten kann um höchstens die halbe
  Zelldiagonale irren (1-Lipschitz-Feld); dieses **Interpolationsband**
  (:func:`interpolation_band_mm`) wird bei jeder Abfrage abgezogen —
  unterschätzen erlaubt, überschätzen ausgeschlossen.
- **Außerhalb des Gitters** gilt die analytische Distanz zur Objekt-AABB
  (AABB ⊇ Geometrie ⇒ untere Schranke), wie im Breitphasen-Filter von
  :mod:`fgc.collision.check`.

Auflösung (``voxel_mm``) und Gitterrand (``padding_mm``) sind Build-Parameter;
ein zusätzliches konservatives Sicherheitsband ist je Abfrage konfigurierbar
(``safety_band_mm``, wird ebenfalls abgezogen). Die Abfrage ist **batchfähig**
(vektorisiertes numpy über ``(N, 3)``-Punktmengen, keine Einzelaufrufe) und
liefert ``(dist, grad)`` — der Gradient (Richtung wachsender Distanz) stammt aus
der analytischen Ableitung der Trilinear-Interpolation und ist Richtungs-, nicht
Urteilsinformation.

**Reinheit / Modularität.** Wie :mod:`fgc.collision.robot_geometry`: die
Geo-Pakete (numpy, trimesh) werden *lazy* importiert — der Core startet ohne
``fgc-core[geo]``. :func:`build_link_field` ist eine **reine** Funktion (Arrays
rein, deterministisches Feld raus, keine Datei-I/O); Schreiben lebt im
Offline-Skript, Lesen + Validieren in :func:`load_glied_sdf`. Konsumiert wird
das Modul von der späteren ``SdfObstacleProvider``-Scheibe (#213) und der
AP-1-Abnahme (#215).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fgc.collision.robot_geometry import GEO_HINT, MANIFEST_NAME, collision_dir

#: Default-Kantenlänge eines Voxels (mm). Bestimmt das Interpolationsband
#: (halbe Zelldiagonale ≈ 6,9 mm) — fein genug, dass der FCL-Nachprüfer im
#: Grenzband (#213) selten anspringt, grob genug für ein kleines Artefakt.
DEFAULT_VOXEL_MM = 8.0

#: Default-Gitterrand um die Objekt-AABB (mm) — größer als der Sicherheitsabstand
#: (50 mm, ``check.DEFAULT_SAFETY_DISTANCE_MM``) plus Interpolationsband, damit
#: alle urteilsrelevanten Abfragen im Gitter landen.
DEFAULT_PADDING_MM = 80.0

#: Reserve für die float32-Ablage der exakten Knotenwerte (mm).
NODE_EPS_MM = 0.01

#: Formatstand des Artefakts — Erhöhung invalidiert alte Builds beim Laden.
SDF_FORMAT_VERSION = 1

#: Unterordner des Kollisions-Derivats, in dem die Glied-SDFs liegen.
SDF_DIR_NAME = "sdf"

SDF_MANIFEST_NAME = "manifest.json"

BUILD_HINT = "Neu bauen mit  .venv/Scripts/python.exe core/scripts/build_glied_sdf.py"


class SdfProvenanceError(ValueError):
    """Glied-SDF-Provenienz passt nicht zu Katalog/Quellgeometrie (US 18) — klarer Fehler."""


def interpolation_band_mm(voxel_mm: float) -> float:
    """Konservatives Band (mm), das jede Abfrage abzieht: halbe Zelldiagonale + Ablage-Reserve.

    Für ein 1-Lipschitz-Distanzfeld ist der Trilinear-Interpolationsfehler durch
    ``√3/2·voxel`` beschränkt (gewichtete Eckpunktabstände, Maximum in Zellmitte);
    Abziehen macht Überschätzen unmöglich.
    """
    return math.sqrt(3.0) / 2.0 * voxel_mm + NODE_EPS_MM


def _require_np():
    """Lazy-Import von numpy mit freundlichem Fehlpfad statt Import-Crash."""
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - Pfad nur ohne [geo]-Extras
        raise ImportError(GEO_HINT) from exc
    return numpy


def _require_geo():
    """Lazy-Import der Geo-Pakete (Build-Pfad) mit freundlichem Fehlpfad."""
    try:
        import numpy
        import trimesh
    except ImportError as exc:  # pragma: no cover - Pfad nur ohne [geo]-Extras
        raise ImportError(GEO_HINT) from exc
    return numpy, trimesh


# ---------------------------------------------------------------------------
# Abfrage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkSdf:
    """Voxel-SDF eines Glieds im DH-Gliedframe (mm, Semantik s. Modul-Docstring)."""

    index: int
    urdf_link: str
    #: Gitterursprung (Knoten [0,0,0]) im Gliedframe, ``(3,)`` mm.
    origin_mm: Any
    voxel_mm: float
    #: Konservatives Band, das jede Abfrage abzieht (:func:`interpolation_band_mm`).
    band_mm: float
    #: Exakte Knotenwerte, ``(nx, ny, nz)`` float32 mm (negativ = innen).
    values: Any
    #: AABB der Quellgeometrie (Urteilsgeometrie) — untere Schranke außerhalb des Gitters.
    object_lo_mm: Any
    object_hi_mm: Any

    def distance(self, points_mm: Any, *, safety_band_mm: float = 0.0):
        """Konservative Distanz + Gradient für Punkte im **Gliedframe**, batchweise.

        ``points_mm``: ``(N, 3)`` in mm. Rückgabe ``(dist, grad)`` mit ``dist``
        ``(N,)`` (mm, **nie über** der FCL-Referenzdistanz zur Urteilsgeometrie)
        und ``grad`` ``(N, 3)`` (Richtung wachsender Distanz, unnormiert).
        ``safety_band_mm`` wird zusätzlich zum Interpolationsband abgezogen.
        """
        np = _require_np()
        pts = np.asarray(points_mm, dtype=float).reshape(-1, 3)
        n_pts = len(pts)
        dist = np.empty(n_pts, dtype=float)
        grad = np.zeros((n_pts, 3), dtype=float)
        if n_pts == 0:
            return dist, grad

        shape = np.asarray(self.values.shape)
        idx_f = (pts - np.asarray(self.origin_mm, dtype=float)) / self.voxel_mm
        in_grid = np.all((idx_f >= 0.0) & (idx_f <= shape - 1), axis=1)

        if in_grid.any():
            val, g = _trilinear_with_grad(self.values, idx_f[in_grid], self.voxel_mm, np)
            dist[in_grid] = val - self.band_mm - safety_band_mm
            grad[in_grid] = g

        outside = ~in_grid
        if outside.any():
            lo = np.asarray(self.object_lo_mm, dtype=float)
            hi = np.asarray(self.object_hi_mm, dtype=float)
            clamped = np.clip(pts[outside], lo, hi)
            delta = pts[outside] - clamped
            gap = np.linalg.norm(delta, axis=1)
            dist[outside] = gap - safety_band_mm
            safe = gap > 0.0
            grad_out = np.zeros_like(delta)
            grad_out[safe] = delta[safe] / gap[safe, None]
            grad[outside] = grad_out

        return dist, grad


@dataclass(frozen=True)
class GliedSdf:
    """Alle Glied-SDFs eines Roboters plus validiertes Provenienz-Manifest."""

    robot: str
    manifest: dict[str, Any]
    links: tuple[LinkSdf, ...]

    def link(self, index: int) -> LinkSdf:
        for lk in self.links:
            if lk.index == index:
                return lk
        raise KeyError(f"Glied {index} nicht im Glied-SDF von {self.robot!r}")

    def distance(self, link_index: int, points_mm: Any, *, safety_band_mm: float = 0.0):
        """Batch-Abfrage gegen ein Glied — Punkte bereits im Gliedframe (mm)."""
        return self.link(link_index).distance(points_mm, safety_band_mm=safety_band_mm)


def _trilinear_with_grad(values: Any, idx_f: Any, voxel_mm: float, np):
    """Trilineare Interpolation + analytischer Gradient auf dem Knotengitter.

    ``idx_f``: kontinuierliche Gitterindizes ``(N, 3)`` innerhalb des Gitters.
    Rückgabe ``(val (N,), grad (N, 3))``; ``grad`` in mm/mm (Feldableitung).
    """
    shape = values.shape
    c0 = np.floor(idx_f).astype(int)
    c0 = np.minimum(np.maximum(c0, 0), np.asarray(shape) - 2)
    t = np.clip(idx_f - c0, 0.0, 1.0)
    ix, iy, iz = c0[:, 0], c0[:, 1], c0[:, 2]
    tx, ty, tz = t[:, 0], t[:, 1], t[:, 2]

    # Erst die 8 Eckwerte gathern, dann nach float64 heben (float32→float64 ist
    # exakt, Ergebnis bit-identisch) — ein astype des ganzen Gitters je Abfrage
    # war der Kostentreiber der Batch-Abfrage (#213).
    def corner(dx_, dy_, dz_):
        return values[ix + dx_, iy + dy_, iz + dz_].astype(float)

    v000 = corner(0, 0, 0)
    v100 = corner(1, 0, 0)
    v010 = corner(0, 1, 0)
    v110 = corner(1, 1, 0)
    v001 = corner(0, 0, 1)
    v101 = corner(1, 0, 1)
    v011 = corner(0, 1, 1)
    v111 = corner(1, 1, 1)

    # Erst x, dann y, dann z zusammenziehen.
    c00 = v000 * (1 - tx) + v100 * tx
    c10 = v010 * (1 - tx) + v110 * tx
    c01 = v001 * (1 - tx) + v101 * tx
    c11 = v011 * (1 - tx) + v111 * tx
    c0_ = c00 * (1 - ty) + c10 * ty
    c1_ = c01 * (1 - ty) + c11 * ty
    val = c0_ * (1 - tz) + c1_ * tz

    dx = (
        ((v100 - v000) * (1 - ty) + (v110 - v010) * ty) * (1 - tz)
        + ((v101 - v001) * (1 - ty) + (v111 - v011) * ty) * tz
    ) / voxel_mm
    dy = ((c10 - c00) * (1 - tz) + (c11 - c01) * tz) / voxel_mm
    dz = (c1_ - c0_) / voxel_mm
    return val, np.stack([dx, dy, dz], axis=1)


# ---------------------------------------------------------------------------
# Build (reine Funktion — Datei-I/O lebt im Offline-Skript)
# ---------------------------------------------------------------------------


def build_link_field(
    parts: Any,
    *,
    voxel_mm: float = DEFAULT_VOXEL_MM,
    padding_mm: float = DEFAULT_PADDING_MM,
) -> dict[str, Any]:
    """Exaktes Knotengitter der signierten Distanz zur Vereinigung konvexer Stücke.

    ``parts``: Sequenz ``(vertices_mm, faces)`` der VHACD-Urteilsstücke eines
    Glieds (Gliedframe, mm). Rückgabe ein deterministisches Dict mit
    ``origin_mm``, ``voxel_mm``, ``padding_mm``, ``object_bounds_mm`` und
    ``values`` (``(nx, ny, nz)`` float32).

    Knotenwerte (exakt, Semantik = ``min_i d_i`` wie der FCL-Manager über die
    Stücke): außerhalb aller Stücke die unsignierte Distanz zur nächsten
    Stück-Oberfläche (= Solid-Distanz); innerhalb eines Stücks der konvex-exakte
    Ebenenwert ``max_f s_f`` (negativ), Minimum über alle enthaltenden Stücke.
    """
    np, trimesh = _require_geo()
    meshes = [
        trimesh.Trimesh(
            vertices=np.asarray(v, dtype=float), faces=np.asarray(f, dtype=int), process=False
        )
        for v, f in parts
    ]
    if not meshes:
        raise ValueError("build_link_field braucht mindestens ein Urteilsstück")

    obj_lo = np.min([m.vertices.min(axis=0) for m in meshes], axis=0)
    obj_hi = np.max([m.vertices.max(axis=0) for m in meshes], axis=0)
    origin = obj_lo - padding_mm
    n = np.ceil((obj_hi + padding_mm - origin) / voxel_mm).astype(int) + 1

    axes = [origin[k] + np.arange(n[k]) * voxel_mm for k in range(3)]
    pts = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)

    # Außen-Distanz: nächste Stück-Oberfläche über alle Stücke (ein BVH, chunked).
    concat = trimesh.util.concatenate(meshes)
    pq = trimesh.proximity.ProximityQuery(concat)
    values = np.empty(len(pts), dtype=float)
    chunk = 65536
    for start in range(0, len(pts), chunk):
        _, d, _ = pq.on_surface(pts[start : start + chunk])
        values[start : start + chunk] = d

    # Innen-Vorzeichen: konvex-exakter Ebenentest je Stück (nur AABB-Kandidaten).
    for mesh in meshes:
        hull = mesh.convex_hull  # garantiert auswärts zeigende Flächennormalen
        lo, hi = mesh.bounds
        cand = np.where(np.all((pts >= lo - 1e-9) & (pts <= hi + 1e-9), axis=1))[0]
        if len(cand) == 0:
            continue
        normals = np.asarray(hull.face_normals, dtype=float)
        offsets = np.einsum("ij,ij->i", normals, np.asarray(hull.triangles[:, 0, :], dtype=float))
        s_max = (pts[cand] @ normals.T - offsets).max(axis=1)
        inside = s_max <= 0.0
        idx = cand[inside]
        values[idx] = np.minimum(values[idx], s_max[inside])

    return {
        "origin_mm": origin,
        "voxel_mm": float(voxel_mm),
        "padding_mm": float(padding_mm),
        "object_bounds_mm": np.vstack([obj_lo, obj_hi]),
        "values": values.reshape(tuple(n)).astype(np.float32),
    }


# ---------------------------------------------------------------------------
# Provenienz + Laden
# ---------------------------------------------------------------------------


def source_fingerprint(collision_directory: Path) -> dict[str, str]:
    """SHA-256 je Quelldatei des Kollisions-Derivats (Manifest + Glied-Geometrien).

    Der **Buildstand** der SDF-Provenienz: ändert sich die #125-Quellgeometrie
    (Neukonvertierung), passt der Fingerabdruck nicht mehr und das Laden schlägt
    klar fehl statt still mit veralteten Feldern zu urteilen (US 18).

    Zeilenenden werden vor dem Hash byte-weise auf ``\\n`` normalisiert
    (``\\r\\n`` → ``\\n``): die Quelldateien sind Text-JSON und werden je nach
    Plattform/``core.autocrlf`` als CRLF (Windows) oder LF (Linux/CI) ausgecheckt
    — ohne Normalisierung wäre der Fingerabdruck plattformabhängig und ein auf
    Windows gebautes Artefakt schlüge in der Linux-CI fälschlich als „veraltet"
    fehl. Die ``.npy``-Gitter bleiben binär (``.gitattributes``) und stehen nicht
    im Fingerabdruck.
    """
    manifest = json.loads((collision_directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    names = [MANIFEST_NAME] + [entry["file"] for entry in manifest["links"]]
    return {
        name: hashlib.sha256(
            (collision_directory / name).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for name in sorted(names)
    }


def glied_sdf_dir(robot_name: str, robots_dir: Path | None = None) -> Path:
    """Ablageordner der Glied-SDFs — Unterordner des katalog-referenzierten Derivats."""
    return collision_dir(robot_name, robots_dir) / SDF_DIR_NAME


def load_glied_sdf(
    robot_name: str,
    robots_dir: Path | None = None,
    *,
    voxel_mm: float = DEFAULT_VOXEL_MM,
) -> GliedSdf:
    """Lädt die Glied-SDFs eines Roboters und validiert die Provenienz (US 17/18).

    Prüft Formatstand, Roboter (Manifest gegen den Katalognamen), Auflösung
    (``voxel_mm`` — abweichender/veralteter Build schlägt fehl) und den
    Buildstand der Quellgeometrie (:func:`source_fingerprint`). Jeder Fehlpfad
    wirft :class:`SdfProvenanceError` mit Bauanleitung — kein stilles Weiterlaufen.
    """
    np = _require_np()
    src_dir = collision_dir(robot_name, robots_dir)
    directory = src_dir / SDF_DIR_NAME
    manifest_path = directory / SDF_MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Kein Glied-SDF-Artefakt für {robot_name!r} unter {directory}. {BUILD_HINT}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    fmt = manifest.get("sdf_format_version")
    if fmt != SDF_FORMAT_VERSION:
        raise SdfProvenanceError(
            f"Glied-SDF-Formatstand {fmt!r} wird nicht unterstützt "
            f"(erwartet {SDF_FORMAT_VERSION}). {BUILD_HINT}"
        )
    if manifest.get("robot") != robot_name:
        raise SdfProvenanceError(
            f"Glied-SDF gehört zu Roboter {manifest.get('robot')!r}, "
            f"erwartet {robot_name!r} — falsche Provenienz. {BUILD_HINT}"
        )
    artifact_voxel = float(manifest.get("voxel_mm", float("nan")))
    if not math.isclose(artifact_voxel, voxel_mm, rel_tol=0.0, abs_tol=1e-9):
        raise SdfProvenanceError(
            f"Glied-SDF hat veraltete Auflösung {artifact_voxel} mm "
            f"(erwartet {voxel_mm} mm). {BUILD_HINT}"
        )
    stored = manifest.get("source_files_sha256") or {}
    current = source_fingerprint(src_dir)
    if stored != current:
        changed = sorted(
            k for k in set(stored) | set(current) if stored.get(k) != current.get(k)
        )
        raise SdfProvenanceError(
            "Glied-SDF-Buildstand veraltet: Quellgeometrie hat sich seit dem Build "
            f"geändert ({', '.join(changed)}). {BUILD_HINT}"
        )

    band = interpolation_band_mm(artifact_voxel)
    links: list[LinkSdf] = []
    for entry in manifest["links"]:
        values = np.load(directory / entry["file"])
        if tuple(values.shape) != tuple(entry["shape"]):
            raise SdfProvenanceError(
                f"Glied-SDF {entry['file']}: Gitterform {tuple(values.shape)} passt nicht "
                f"zum Manifest {tuple(entry['shape'])}. {BUILD_HINT}"
            )
        bounds = np.asarray(entry["object_bounds_mm"], dtype=float)
        links.append(
            LinkSdf(
                index=int(entry["index"]),
                urdf_link=str(entry["urdf_link"]),
                origin_mm=np.asarray(entry["origin_mm"], dtype=float),
                voxel_mm=artifact_voxel,
                band_mm=band,
                values=values,
                object_lo_mm=bounds[0],
                object_hi_mm=bounds[1],
            )
        )
    return GliedSdf(robot=str(manifest["robot"]), manifest=manifest, links=tuple(links))
