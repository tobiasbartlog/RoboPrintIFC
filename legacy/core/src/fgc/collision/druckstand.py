"""Wachsender Druckstand als Hindernissatz je **Schicht** (ADR-024, PRD #124, Issue #126).

Reines Hindernis-Modul der **Kollisionskontrolle**: baut je Druckschicht das
zeitabhängig wachsende Hindernisvolumen, gegen das ``fgc.collision.check`` den
Arm prüft. Kein I/O, kein Schema-/API-Change — Geometrie rein, Hindernissatz
raus.

Der **Druckstand** einer Schicht besteht aus (Druckreihenfolge =
Montagereihenfolge, ADR-022):

- in Druckreihenfolge **frühere Teile voll** (fertige Module/Abschnitte),
- das **aktuelle Teil als Footprint-Prisma** — der echte Slicer-Umriss
  (``geometry/section.py``), extrudiert bis zur **aktuellen Schicht**. Die
  Schicht kommt aus dem **Toolpath** (``layer``-Index je Target), nicht aus einer
  TCP-Höhen-Näherung (Spike-Lehrgeld S0). Die Wand *oberhalb* der aktuellen
  Schicht existiert noch nicht und ist kein Hindernis,
- Boden/Podest/Arbeitsfläche und **zuschaltbar** der Gebäudekontext.

Um den aktuellen Druckpunkt bleibt eine **Freizone** (Radius, in dem der
Druckstand nicht bewertet wird — Düse und frischer Wulst berühren sich
prozessbedingt); das aktuelle, wachsende Teil trägt darum ``freizone_exempt``,
den Radius wertet ``check`` je Sample aus (Rebuild bleibt je Schicht).

Bei Zerlegungsart **Modul** (US 24) ist die Workstation der Druckort: der
Hindernissatz enthält nur das wachsende Modul plus die Arbeitsfläche der
Workstation — kein Boden-Podest, kein Gebäudekontext (ADR-022).

**Reinheit / Modularität.** Die schweren Geo-Pakete (``trimesh``, ``shapely``,
``mapbox_earcut``) werden *lazy* importiert (Muster ``robot_geometry``); der Core
startet ohne ``fgc-core[geo]`` sauber, erst der Aufruf einer Geometrie-Funktion
meldet freundlich den fehlenden Extra.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # nur für Typprüfer — kein Laufzeit-Import (geo-frei startbar)
    import trimesh
    from shapely.geometry import Polygon

GEO_HINT = (
    "Der Druckstand braucht die Geo-Extras (trimesh, shapely, mapbox-earcut). "
    "Installiere sie mit  pip install fgc-core[geo]  (bereits im Projekt-venv)."
)

Mode = Literal["abschnitt", "modul"]


def _require_geo():
    """Lazy-Import der Geo-Pakete mit freundlichem Fehlpfad statt Import-Crash."""
    try:
        import numpy
        import trimesh
        from shapely.geometry import Polygon  # noqa: F401  (nur Verfügbarkeitsprobe)
    except ImportError as exc:  # pragma: no cover - Pfad nur ohne [geo]-Extras
        raise ImportError(GEO_HINT) from exc
    return numpy, trimesh


# ---------------------------------------------------------------------------
# Hindernis-Typen
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Obstacle:
    """Ein benanntes Hindernis des Druckstands (Mesh in Welt-/Wandkoordinaten)."""

    name: str
    mesh: trimesh.Trimesh
    #: Das aktuelle, wachsende Teil ist in der **Freizone** um den Druckpunkt
    #: ausgenommen (Düse↔Wulst-Kontakt) — ``check`` wertet den Radius je Sample.
    freizone_exempt: bool = False


@dataclass(frozen=True)
class ObstacleSet:
    """Der Hindernissatz genau **einer** Schicht (Rebuild je Schicht, nicht je Sample)."""

    layer_index: int
    #: Oberkante des wachsenden Teils (mm) = fertige Schichten unter dem Druckpunkt.
    z_top_mm: float
    obstacles: tuple[Obstacle, ...]
    freizone_radius_mm: float = 0.0

    def merged_mesh(self) -> trimesh.Trimesh:
        """Alle Hindernisse zu einem Mesh vereint (Diagnose/Tests)."""
        _, trimesh = _require_geo()
        return trimesh.util.concatenate([o.mesh for o in self.obstacles])


@dataclass(frozen=True)
class DruckstandSpec:
    """Unveränderliche Bau-Eingaben eines Druckstands (eine Wand/ein Druckjob).

    ``footprint`` ist der echte Slicer-Umriss des aktuellen Teils (Welt-XY-
    Polygone aus :func:`fgc.geometry.section.section_at`); daraus wird je Schicht
    das Footprint-Prisma extrudiert. Längen in mm.
    """

    footprint: tuple[Polygon, ...]
    layer_height_mm: float
    n_layers: int
    z_base_mm: float = 0.0
    #: Fertige frühere Teile (voll), in Druckreihenfolge — Hindernis über alle Schichten.
    earlier_parts: tuple[trimesh.Trimesh, ...] = ()
    #: Boden/Podest (Abschnitt) — entfällt im Modul-Modus.
    ground: trimesh.Trimesh | None = None
    #: Zuschaltbarer Gebäudekontext (Abschnitt) — entfällt im Modul-Modus.
    context: trimesh.Trimesh | None = None
    #: Arbeitsfläche/Workstation-Mesh (nur Modul-Modus, US 24).
    work_surface: trimesh.Trimesh | None = None
    freizone_radius_mm: float = 0.0
    mode: Mode = "abschnitt"


# ---------------------------------------------------------------------------
# Footprint-Prisma
# ---------------------------------------------------------------------------


def extrude_prism(
    footprint: Sequence[Polygon], z_bottom_mm: float, z_top_mm: float
) -> trimesh.Trimesh | None:
    """Extrudiert den Slicer-Umriss zu einem sauber geschlossenen Prisma.

    ``footprint`` = 0..n Umriss-Polygone (Welt-XY, Löcher als interiors), wie
    ``section_at`` sie liefert. Ergibt ein wasserdichtes Prisma von ``z_bottom``
    bis ``z_top``; ``None`` bei leerem Umriss oder nicht-positiver Höhe (die
    Schicht 0 hat noch kein fertiges Volumen unter dem Druckpunkt).
    """
    np, trimesh = _require_geo()
    height = z_top_mm - z_bottom_mm
    if height <= 0.0 or not footprint:
        return None
    parts: list[trimesh.Trimesh] = []
    for poly in footprint:
        if poly is None or poly.is_empty:
            continue
        prism = trimesh.creation.extrude_polygon(poly, float(height))
        if z_bottom_mm:
            prism.apply_translation([0.0, 0.0, float(z_bottom_mm)])
        parts.append(prism)
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)


#: Halbe Kantenlänge (mm) des synthetischen Boden-Slabs — wie das Golden-Fixture
#: (#126): 6 m Kante decken Basis + Podest jeder realistischen Aufstellung ab.
GROUND_HALF_EXTENT_MM = 3000.0

#: Dicke (mm) des synthetischen Boden-Slabs (nach unten — nur die Oberkante urteilt).
GROUND_THICKNESS_MM = 200.0


def ground_slab(
    z_top_mm: float,
    *,
    half_extent_mm: float = GROUND_HALF_EXTENT_MM,
    thickness_mm: float = GROUND_THICKNESS_MM,
) -> trimesh.Trimesh:
    """Der reale Boden als Hindernis-Slab mit **Oberkante** bei ``z_top_mm``.

    Issue #135: Toolpath/Trajektorie liegen abschnitts-lokal (z ab Abschnittsfuß);
    der echte Boden (absolut 0 = Wandfuß) liegt dann bei **lokal ``−z0``**. Der
    Aufrufer übergibt ``z_top_mm = −section_z0_mm``. Deterministische, feste Maße
    (wie das #126-Golden-Fixture) — keine Daten-abhängige Geometrie, damit der
    Befund byte-stabil bleibt.
    """
    _, trimesh = _require_geo()
    slab = trimesh.creation.box(
        extents=[2.0 * half_extent_mm, 2.0 * half_extent_mm, thickness_mm]
    )
    slab.apply_translation([0.0, 0.0, float(z_top_mm) - thickness_mm / 2.0])
    return slab


def layer_top_mm(spec: DruckstandSpec, layer_index: int) -> float:
    """Oberkante des wachsenden Teils bei Schicht ``layer_index`` (mm).

    = fertige Schichten **unter** dem aktuellen Druckpunkt: ``z_base + L·h``. Die
    gerade in Arbeit befindliche Schicht ``L`` zählt noch nicht als Hindernis
    (sie wächst); der Index kommt aus dem Toolpath.
    """
    clamped = max(0, min(int(layer_index), int(spec.n_layers)))
    return spec.z_base_mm + clamped * spec.layer_height_mm


# ---------------------------------------------------------------------------
# Hindernissatz je Schicht
# ---------------------------------------------------------------------------


def build_obstacle_set(spec: DruckstandSpec, layer_index: int) -> ObstacleSet:
    """Baut den Hindernissatz **einer** Schicht (das eine Rebuild-je-Schicht-Tor).

    Abschnitt-Modus: frühere Teile voll + wachsendes Footprint-Prisma
    (freizone-exempt) + Boden + optional Gebäudekontext. Modul-Modus: nur das
    wachsende Modul + Arbeitsfläche (kein Boden/Kontext, ADR-022).
    """
    z_top = layer_top_mm(spec, layer_index)
    obstacles: list[Obstacle] = []

    growing = extrude_prism(spec.footprint, spec.z_base_mm, z_top)

    if spec.mode == "modul":
        if growing is not None:
            obstacles.append(Obstacle("modul", growing, freizone_exempt=True))
        if spec.work_surface is not None:
            obstacles.append(Obstacle("work_surface", spec.work_surface))
    else:
        for i, part in enumerate(spec.earlier_parts):
            obstacles.append(Obstacle(f"part{i}", part))
        if growing is not None:
            obstacles.append(Obstacle("current_part", growing, freizone_exempt=True))
        if spec.ground is not None:
            obstacles.append(Obstacle("ground", spec.ground))
        if spec.context is not None:
            obstacles.append(Obstacle("context", spec.context))

    return ObstacleSet(
        layer_index=max(0, min(int(layer_index), int(spec.n_layers))),
        z_top_mm=z_top,
        obstacles=tuple(obstacles),
        freizone_radius_mm=spec.freizone_radius_mm,
    )


def obstacle_provider(spec: DruckstandSpec):
    """Liefert einen **je Schicht cachenden** Zugriff ``layer_index -> ObstacleSet``.

    Der Rebuild passiert genau einmal je Schicht (nicht je Sample); ``check``
    ruft den Provider je Sample mit dessen Schicht-Index und teilt sich so den
    einmal gebauten Hindernissatz über alle Samples derselben Schicht.
    """
    cache: dict[int, ObstacleSet] = {}

    def provide(layer_index: int) -> ObstacleSet:
        key = max(0, min(int(layer_index), int(spec.n_layers)))
        hit = cache.get(key)
        if hit is None:
            hit = build_obstacle_set(spec, key)
            cache[key] = hit
        return hit

    provide.cache = cache  # type: ignore[attr-defined]  (Tests prüfen die Rebuild-Zahl)
    return provide


# ---------------------------------------------------------------------------
# Schicht je Sample aus dem Toolpath (keine TCP-Näherung)
# ---------------------------------------------------------------------------


def layer_per_sample(
    sample_times_s: Sequence[float],
    target_times_s: Sequence[float],
    target_layers: Sequence[int],
) -> list[int]:
    """Schicht-Index je dichtem Trajektorien-Sample aus der Toolpath-Zeitachse.

    Jedes Sample erbt die ``layer`` seines Toolpath-Segments (Schrittfunktion
    über die Target-Zeiten — dieselbe Bisektion wie die io-Zeitreihe in
    ``simulation.build``). So kommt die Schicht **exakt aus dem Toolpath**, nicht
    aus einer TCP-Höhen-Näherung (Spike-Lehrgeld S0).
    """
    tt = list(target_times_s)
    layers = list(target_layers)
    if not tt:
        return [0] * len(sample_times_s)
    out: list[int] = []
    for t in sample_times_s:
        k = max(0, min(bisect_right(tt, t) - 1, len(layers) - 1))
        out.append(int(layers[k]))
    return out
