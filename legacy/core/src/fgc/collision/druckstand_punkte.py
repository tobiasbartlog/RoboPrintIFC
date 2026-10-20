"""DruckstandPunkte: wachsender Druckstand als Punktwolke (PRD #183 AP 1, Issue #208).

Zweites Standbein der invertierten Kollisions-Vorarbeit neben dem Glied-SDF
(:mod:`fgc.collision.glied_sdf`, Issue #207): dort liegt die teure Vorarbeit auf
dem, was sich **nie ändert** (die Armglieder als statisches Voxel-Feld); hier
bleibt das, was sich **ständig ändert** (der wachsende Druckstand), absichtlich
**billig** — eine Punktwolke, deren Schichtfortschritt reines **Anhängen** ist
(Design-Log 2026-07-12, Shen et al. 2026: „das wachsende Werkstück ist eine
Punktwolke aus den bereits deponierten Materialblöcken, je Wegpunkt
fortgeschrieben").

**Kein Feld-Umbau.** :meth:`DruckstandPunkte.advance_layer` fügt je Schicht nur
den neuen Grundriss-Schnitt (Schnitthöhe = :func:`fgc.collision.druckstand.
layer_top_mm`, dieselbe Semantik wie beim Footprint-Prisma) als deterministisch
gesampelte Punktmenge **hinzu** — bereits angehängte Schichten werden nie neu
berechnet oder entfernt. Das ist bewusst konservativ statt exakt: eine ältere
Schicht-Fläche, die inzwischen von neuem Material überdeckt (also innen liegt)
ist, bleibt in der Wolke; ein Punkt im Innern kann den minimalen Abstand zu
einem Außenpunkt nur **überschätzen**, nie unterschätzen (der kürzeste Weg von
außen zu ihm quert zwangsläufig die tatsächliche Oberfläche) — reines Anhängen
ist darum ohne Risiko für die Kollisionskontrolle. Weil jede Schicht-Punktmenge
eine **reine Funktion** ihrer Schichthöhe ist (Grundriss + z-Höhe +
Punktabstand, keine Abhängigkeit vom Aufrufmuster), ist das Ergebnis
**bit-identisch**, ob man Schicht für Schicht anhängt oder direkt bis Schicht
``n`` vorspult (Abnahmekriterium 1, Issue #208).

**Punktabstand.** :data:`DEFAULT_POINT_SPACING_MM` leitet sich aus der
50-mm-Sicherheitsmarge ab (``check.DEFAULT_SAFETY_DISTANCE_MM``): „deutlich
unter dem Sicherheitsabstand" (Design-Log 2026-07-12) — hier 30 % der Marge
(15 mm). Shen et al. 2026 nutzen 2 mm bei 3 mm Marge (≈ 67 %); unser Verhältnis
ist konservativer, weil unser Sicherheitsabstand selbst schon eine großzügige
Prozessmarge trägt (weicher Lehm), nicht nur einen numerischen Toleranzpuffer.

**Statische Hindernisse im selben Vertrag** (US 15): Workstation-Arbeitsfläche
und Gebäudekontext werden **einmalig** bei Konstruktion zu Punktmengen
gesampelt — sie wachsen nie, anders als der Druckstand. Dieselbe
Sampling-Funktion (:func:`_mesh_surface_points`) bedient beide Fälle; welche
Hindernisse teilnehmen folgt exakt der Modus-Weiche aus
:func:`fgc.collision.druckstand.build_obstacle_set` (Abschnitt: frühere Teile +
Boden + Kontext; Modul: nur Arbeitsfläche).

**Quell-Naht.** :meth:`DruckstandPunkteSpec.from_druckstand_spec` baut die
Punktwolken-Eingaben direkt aus einem bestehenden
:class:`fgc.collision.druckstand.DruckstandSpec` (selbst aus
``SceneInputs``/``FindingRequest``, Issue #192) — derselbe eine Ort, an dem
Szene-Eingaben zu Hindernissen werden, für beide Backends (FCL-Meshes dort,
Punktwolke hier). Konsumiert wird dieses Modul vom kommenden
``SdfObstacleProvider`` (Issue #213), der Glied-SDF (#207) und Punktwolke
(dieses Modul) zum batchweisen Abfrage-Paar verheiratet.

**Reinheit / Modularität.** Wie die Schwestermodule: die Geo-Pakete (numpy,
trimesh, shapely) werden *lazy* importiert — der Core startet ohne
``fgc-core[geo]``. Sampling ist **deterministisch** (feste Gitter, keine
Zufallszahlen) — Voraussetzung für Bit-Gleichheit und künftige Goldens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from fgc.collision import druckstand as _ds
from fgc.collision.check import DEFAULT_SAFETY_DISTANCE_MM

if TYPE_CHECKING:  # nur für Typprüfer — kein Laufzeit-Import (geo-frei startbar)
    import trimesh
    from shapely.geometry import Polygon

    from fgc.collision.druckstand import DruckstandSpec

GEO_HINT = (
    "Die Druckstand-Punktwolke braucht die Geo-Extras (trimesh, shapely). "
    "Installiere sie mit  pip install fgc-core[geo]  (bereits im Projekt-venv)."
)

Mode = Literal["abschnitt", "modul"]

#: Default-Punktabstand (mm) der Druckstand-Punktwolke — „deutlich unter dem
#: Sicherheitsabstand" (Design-Log 2026-07-12), hier 30 % von
#: ``DEFAULT_SAFETY_DISTANCE_MM`` (50 mm ⇒ 15 mm).
DEFAULT_POINT_SPACING_MM = round(0.3 * DEFAULT_SAFETY_DISTANCE_MM, 1)


def _require_geo():
    """Lazy-Import der Geo-Pakete mit freundlichem Fehlpfad statt Import-Crash."""
    try:
        import numpy
        import trimesh
        from shapely.geometry import Point  # noqa: F401  (nur Verfügbarkeitsprobe)
    except ImportError as exc:  # pragma: no cover - Pfad nur ohne [geo]-Extras
        raise ImportError(GEO_HINT) from exc
    return numpy, trimesh


# ---------------------------------------------------------------------------
# Bau-Eingaben
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DruckstandPunkteSpec:
    """Unveränderliche Bau-Eingaben einer Druckstand-Punktwolke (Analog zu ``DruckstandSpec``).

    Dieselben Felder/Semantik wie :class:`fgc.collision.druckstand.DruckstandSpec`
    (``footprint``, ``earlier_parts``, ``ground``, ``context``, ``work_surface``,
    ``mode``) — nur die Konsequenz ist eine Punktwolke statt Solid-Meshes je
    Schicht. ``point_spacing_mm`` steuert sowohl die Gitterweite des wachsenden
    Grundriss-Schnitts als auch die Ziel-Kantenlänge der statischen
    Oberflächen-Samples.
    """

    footprint: tuple[Polygon, ...]
    layer_height_mm: float
    n_layers: int
    z_base_mm: float = 0.0
    #: Fertige frühere Teile (voll), in Druckreihenfolge — wie ``DruckstandSpec``.
    earlier_parts: tuple[trimesh.Trimesh, ...] = ()
    #: Boden/Podest (Abschnitt) — entfällt im Modul-Modus.
    ground: trimesh.Trimesh | None = None
    #: Zuschaltbarer Gebäudekontext (Abschnitt) — entfällt im Modul-Modus.
    context: trimesh.Trimesh | None = None
    #: Arbeitsfläche/Workstation-Mesh (nur Modul-Modus, US 24).
    work_surface: trimesh.Trimesh | None = None
    point_spacing_mm: float = DEFAULT_POINT_SPACING_MM
    mode: Mode = "abschnitt"

    @classmethod
    def from_druckstand_spec(
        cls,
        spec: DruckstandSpec,
        *,
        point_spacing_mm: float = DEFAULT_POINT_SPACING_MM,
    ) -> DruckstandPunkteSpec:
        """Baut die Punktwolken-Eingaben aus einem bestehenden ``DruckstandSpec``.

        Dieselbe Naht wie das FCL-Backend (``SceneInputs`` → ``DruckstandSpec``,
        Issue #192): beide Backends entstehen aus denselben Szene-Eingaben, nur
        die Sampling-Konsequenz unterscheidet sich (Meshes vs. Punktwolke).
        """
        return cls(
            footprint=spec.footprint,
            layer_height_mm=spec.layer_height_mm,
            n_layers=spec.n_layers,
            z_base_mm=spec.z_base_mm,
            earlier_parts=spec.earlier_parts,
            ground=spec.ground,
            context=spec.context,
            work_surface=spec.work_surface,
            point_spacing_mm=point_spacing_mm,
            mode=spec.mode,
        )


# ---------------------------------------------------------------------------
# Deterministisches Sampling
# ---------------------------------------------------------------------------


def _footprint_slice_points(footprint, z_mm: float, spacing_mm: float, np) -> Any:
    """Deterministisches Gitter der Grundriss-Polygone in einer Schnitthöhe ``z_mm``.

    Achsparalleles Gitter mit Schrittweite ``spacing_mm`` über der Bounding-Box
    je Polygon, gefiltert auf Punkte **im** Polygon (``covers`` — schließt den
    Rand ein, damit dünne Wandquerschnitte nicht leer ausgehen). Deterministisch
    (festes Gitter, keine Zufallszahlen) — Voraussetzung für die Bit-Gleichheit
    von :meth:`DruckstandPunkte.advance_layer` (Issue #208, Abnahme 1).
    """
    import shapely

    pts: list[Any] = []
    for poly in footprint:
        if poly is None or poly.is_empty:
            continue
        minx, miny, maxx, maxy = poly.bounds
        nx = max(1, int(np.ceil((maxx - minx) / spacing_mm))) + 1
        ny = max(1, int(np.ceil((maxy - miny) / spacing_mm))) + 1
        xs = np.linspace(minx, maxx, nx)
        ys = np.linspace(miny, maxy, ny)
        # Vektorisiertes ``covers`` (shapely 2) in derselben x-major-Reihenfolge
        # wie die frühere Punkt-Schleife — Ergebnis bleibt bit-identisch (#213).
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        flat = np.column_stack([gx.ravel(), gy.ravel()])
        inside = shapely.covers(poly, shapely.points(flat))
        kept = flat[inside]
        if len(kept):
            pts.append(
                np.column_stack([kept, np.full(len(kept), float(z_mm), dtype=float)])
            )
    if not pts:
        return np.zeros((0, 3), dtype=float)
    return np.concatenate(pts, axis=0)


def _mesh_surface_points(mesh: trimesh.Trimesh, spacing_mm: float, np, trimesh_mod) -> Any:
    """Deterministische Oberflächen-Punktwolke eines **statischen** Meshes (US 15).

    Unterteilt das Mesh, bis keine Kante länger als ``spacing_mm`` ist
    (``trimesh.remesh.subdivide_to_size`` — deterministisch, anders als die
    Zufallsstichprobe von ``trimesh.sample.sample_surface``), und nimmt die
    entstehenden Knoten als Punktwolke. Einmalig aufgerufen (bei Konstruktion),
    nie je Schicht — die statischen Hindernisse wachsen nicht.
    """
    verts, _faces = trimesh_mod.remesh.subdivide_to_size(
        mesh.vertices, mesh.faces, max_edge=spacing_mm
    )
    return np.asarray(verts, dtype=float)


# ---------------------------------------------------------------------------
# Der wachsende Druckstand als Punktwolke
# ---------------------------------------------------------------------------


class DruckstandPunkte:
    """Der wachsende Druckstand als Punktwolke (Issue #208).

    ``advance_layer(layer_index)`` hängt die Grundriss-Schnitte aller noch
    fehlenden Schichten bis einschließlich ``layer_index`` an — nie rückwärts,
    nie neu berechnet (s. Moduldocstring für die Bit-Gleichheits- und
    Konservativitäts-Begründung). Statische Hindernisse (Workstation,
    Gebäudekontext) werden **einmalig** bei Konstruktion gesampelt (US 15).
    """

    def __init__(self, spec: DruckstandPunkteSpec) -> None:
        np, trimesh = _require_geo()
        self.spec = spec
        self._layer_index = 0
        self._growing_layers: list[Any] = []
        self._static_points = self._build_static_points(np, trimesh)

    def _build_static_points(self, np, trimesh) -> Any:
        """Baut die statischen Hindernis-Punkte einmalig — dieselbe Modus-Weiche
        wie :func:`fgc.collision.druckstand.build_obstacle_set` (US 15)."""
        spec = self.spec
        parts: list[Any] = []
        if spec.mode == "modul":
            if spec.work_surface is not None:
                parts.append(
                    _mesh_surface_points(spec.work_surface, spec.point_spacing_mm, np, trimesh)
                )
        else:
            for part in spec.earlier_parts:
                parts.append(_mesh_surface_points(part, spec.point_spacing_mm, np, trimesh))
            if spec.ground is not None:
                parts.append(_mesh_surface_points(spec.ground, spec.point_spacing_mm, np, trimesh))
            if spec.context is not None:
                parts.append(
                    _mesh_surface_points(spec.context, spec.point_spacing_mm, np, trimesh)
                )
        if not parts:
            return np.zeros((0, 3), dtype=float)
        return np.concatenate(parts, axis=0)

    def advance_layer(self, layer_index: int) -> None:
        """Hängt die Grundriss-Schnitte aller noch fehlenden Schichten bis
        ``layer_index`` an — reines Anhängen, kein Feld-Umbau (Issue #208).

        ``layer_index`` wird wie in :func:`fgc.collision.druckstand.layer_top_mm`
        auf ``[0, n_layers]`` geklemmt. Bereits erreichte oder frühere Schichten
        sind ein No-Op (der Druckstand wächst nur vorwärts). Da jede Schicht-
        Punktmenge eine reine Funktion ihrer Schichthöhe ist, liefert das
        Vorspulen in einem Schritt (``advance_layer(n)``) bit-identische Punkte
        zum schrittweisen Anhängen (``advance_layer(1)``, ``advance_layer(2)``,
        …, ``advance_layer(n)``).
        """
        np, _ = _require_geo()
        target = max(0, min(int(layer_index), int(self.spec.n_layers)))
        while self._layer_index < target:
            self._layer_index += 1
            z_top = _ds.layer_top_mm(self.spec, self._layer_index)
            self._growing_layers.append(
                _footprint_slice_points(
                    self.spec.footprint, z_top, self.spec.point_spacing_mm, np
                )
            )

    @property
    def layer_index(self) -> int:
        """Höchste bereits angehängte Schicht (0 = noch nichts gedruckt)."""
        return self._layer_index

    @property
    def growing_points_mm(self) -> Any:
        """Nur die Punkte des wachsenden Teils, ``(N, 3)`` mm (ohne Statik)."""
        np, _ = _require_geo()
        if not self._growing_layers:
            return np.zeros((0, 3), dtype=float)
        return np.concatenate(self._growing_layers, axis=0)

    @property
    def growing_layer_counts(self) -> tuple[int, ...]:
        """Punktzahl je bereits angehängter Schicht (1..``layer_index``), in Schichtreihenfolge.

        Naht für den ``SdfObstacleProvider`` (Issue #213): zusammen mit
        :attr:`growing_points_mm` (Konkatenation in derselben Reihenfolge) ergeben
        sich daraus Präfix-Offsets je Schicht — der Hindernis-Punktsatz einer
        Schicht ``L`` ist dann ein reiner Array-View, kein Rebuild.
        """
        return tuple(len(a) for a in self._growing_layers)

    @property
    def static_points_mm(self) -> Any:
        """Die einmalig gesampelten statischen Hindernis-Punkte, ``(N, 3)`` mm (US 15)."""
        return self._static_points

    @property
    def points_mm(self) -> Any:
        """Der volle Hindernis-Punktsatz: wachsendes Teil + statische Hindernisse."""
        np, _ = _require_geo()
        return np.concatenate([self.growing_points_mm, self._static_points], axis=0)
