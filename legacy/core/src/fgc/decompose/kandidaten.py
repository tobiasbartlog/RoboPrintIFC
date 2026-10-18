"""Band-Raster-Kandidaten der Zerlegungs-Suche (Issue #216, PRD #183 Stufe 3).

Der **deterministische Kandidaten-Generator** der Beam-Suche (#217):
Kandidaten-Zerlegungen sind achsparallele **Band-Raster** — ``n_length``
gleiche Laengenbaender × ``n_height`` gleiche Hoehenbaender, exakt dieselbe
Schnittgeometrie wie ``propose._build_cuts`` (nichts dupliziert; ein Sieger-
Kandidat ist damit 1:1 ein ``propose``-Raster). Literatur-Muster: diskrete
Schnitt-Kandidaten + billige Bewertung vorn, teures Urteil hinten (Wu 2019,
Han 2025 — ``docs/recherche/2026-07-10-adaption-chunking-literatur.md``); die
Kandidatenzahl bleibt klein (``cap²``, Z-Chunking-Warnung vor 2^n).

Deterministisch (ADR-004-Geist, US 19/25): gleiche Wand + gleicher Deckel ⇒
bit-gleiche Kandidatenfolge. Die **stabile Ordnung** (aufsteigend nach
Teilanzahl, dann Hoehen-, dann Laengenteilung — grob vor fein) ist Teil des
Byte-Vergleichs-Versprechens: Strategien, die die Folge in Ordnung abarbeiten,
sind ohne weitere Sortierung reproduzierbar.

Einheiten strikt nach ADR-006: Millimeter.
"""

from __future__ import annotations

from dataclasses import dataclass

from fgc.decompose.plan import Cut
from fgc.decompose.propose import MAX_DIVISIONS, _build_cuts
from fgc.placement import WallSurface

__all__ = [
    "BandRasterKandidat",
    "band_raster_kandidat",
    "band_raster_kandidaten",
]


@dataclass(frozen=True)
class BandRasterKandidat:
    """Eine Kandidaten-Zerlegung: achsparalleles Band-Raster ueber der Wandfront.

    ``cuts`` sind die inneren Schnittebenen (``propose._build_cuts``-Geometrie,
    Rundung 3 Nachkommastellen wie die ``propose``-Abschnitte); die Band-Grenzen
    (:meth:`row_bounds_mm`/:meth:`col_bounds_mm`) folgen derselben Konvention
    (Wand-System nach ADR-006: ``x`` zentriert um 0, ``z`` ab Wandfuss 0).
    """

    wall: WallSurface
    n_length: int
    n_height: int
    cuts: tuple[Cut, ...]

    @property
    def key(self) -> str:
        """Stabiler Kandidaten-Schluessel (Provenienz/Verworfen-Gruende, US 10)."""
        return f"band-{self.n_length}x{self.n_height}"

    @property
    def n_parts(self) -> int:
        return self.n_length * self.n_height

    def row_bounds_mm(self) -> tuple[tuple[float, float], ...]:
        """Die Hoehenbaender ``(z0, z1)`` unten → oben (Druckreihenfolge)."""
        h = self.wall.height_mm
        return tuple(
            (round(h * i / self.n_height, 3), round(h * (i + 1) / self.n_height, 3))
            for i in range(self.n_height)
        )

    def col_bounds_mm(self) -> tuple[tuple[float, float], ...]:
        """Die Laengenbaender ``(x0, x1)`` links → rechts (x zentriert um 0)."""
        length = self.wall.length_mm
        half = length / 2.0
        return tuple(
            (round(-half + length * i / self.n_length, 3),
             round(-half + length * (i + 1) / self.n_length, 3))
            for i in range(self.n_length)
        )


def band_raster_kandidat(wall: WallSurface, n_length: int, n_height: int) -> BandRasterKandidat:
    """Ein einzelner Band-Raster-Kandidat — Schnitte aus ``propose._build_cuts``."""
    if n_length < 1 or n_height < 1:
        raise ValueError(
            f"Band-Raster braucht mindestens 1 Teilung je Achse, hat "
            f"({n_length}, {n_height})."
        )
    return BandRasterKandidat(
        wall=wall,
        n_length=n_length,
        n_height=n_height,
        cuts=_build_cuts(wall, n_length, n_height),
    )


def band_raster_kandidaten(
    wall: WallSurface, *, cap: int = MAX_DIVISIONS
) -> tuple[BandRasterKandidat, ...]:
    """Alle Band-Raster-Kandidaten bis zum Teilungs-Deckel ``cap`` je Achse.

    Deterministische, stabile Ordnung (grob vor fein): aufsteigend nach
    Teilanzahl ``n_length·n_height``, bei Gleichstand erst weniger Hoehen-,
    dann weniger Laengenteilungen. Gleicher Input ⇒ bit-gleiche Folge (US 19/25).
    """
    if cap < 1:
        raise ValueError(f"cap muss ≥ 1 sein, ist {cap}.")
    pairs = sorted(
        ((v, h) for v in range(1, cap + 1) for h in range(1, cap + 1)),
        key=lambda p: (p[0] * p[1], p[1], p[0]),
    )
    return tuple(band_raster_kandidat(wall, v, h) for v, h in pairs)
