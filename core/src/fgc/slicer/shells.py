"""Stufe 2 des Slicers: Schichtpolygon -> Schalenringe (shapely-Offsets).

Erste Schale liegt eine halbe Strangbreite innerhalb der Wandfläche (der Strang
hat Breite), jede weitere eine volle Strangbreite tiefer. Offsets können
degenerieren (MultiPolygon-Zerfall, verschwindende Flächen) — genau das
untersucht Spike S4; v0 behandelt beides defensiv: Zerfall wird zu mehreren
Ringen, Leeres bricht die Schalenfolge ab.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient


@dataclass
class ShellRing:
    """Ein geschlossener Druckring: Schalenindex + XY-Punkte (erster == letzter)."""

    shell: int
    points_xy: list[tuple[float, float]]


#: shapely-Default fuer ``join_style="mitre"`` (5.0) fuehrt an scharfen konkaven
#: Reflex-Kerben zu MultiPolygon-Zerfall (Spike S4, Issue #2). 2.0 ist nur der
#: Fallback fuer Aufrufer ohne Prozessfenster-Karte (z. B. Tests); die
#: Produktionsschicht speist den Kartenwert ``ProcessWindow.mitre_limit`` /
#: ``SliceParams.mitre_limit`` durch (ADR-013, eine Quelle mit
#: ``fgc.eligibility.footprint.has_narrow_web``), s. ``build.build_toolpath``.
DEFAULT_MITRE_LIMIT = 2.0


def shell_rings(
    polygon: Polygon,
    strand_width_mm: float,
    n_shells: int,
    mitre_limit: float = DEFAULT_MITRE_LIMIT,
) -> list[ShellRing]:
    rings: list[ShellRing] = []
    for shell in range(n_shells):
        inset = strand_width_mm * (0.5 + shell)
        # mitre_limit=2.0 statt shapely-Default 5.0: Spike S4 hat nachgewiesen,
        # dass der Default an scharfen konkaven Reflex-Kerben (Kerbwinkel <=30°)
        # zu MultiPolygon-Zerfall fuehrt (docs/spikes/S4_offset_robustheit.md).
        shrunk = polygon.buffer(-inset, join_style="mitre", mitre_limit=mitre_limit)
        if shrunk.is_empty:
            break
        for part in _as_polygons(shrunk):
            part = orient(part, sign=1.0)
            rings.append(ShellRing(shell, list(part.exterior.coords)))
            for hole in part.interiors:
                rings.append(ShellRing(shell, list(hole.coords)))
    return rings


def _as_polygons(geom) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if not g.is_empty]
    return []
