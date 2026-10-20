"""Einteilung und Nahtlage: `fit_to_length` (ganze Zahl von Feldern) und `choose_seam` (M4).

Naht (M4). Die Naht ist der Punkt auf dem Außenring (Schale 0), an dem der Schichtpfad beginnt
bzw. endet. Bei `alternate` liegt dort jede zweite Schicht der senkrechte Hub um h, und genau dort
sitzt ein kleiner Materialpunkt. Er soll weder auf der sichtbaren Außenfläche (y = y_min/y_max des
Teils in P) noch auf der Stoßfläche zum Nachbarmodul (x = x_min/x_max) liegen.

Regel: Unter allen Punkten des Außenrings wird der mit dem größten Abstand zu den *geschützten
Flächen* gewählt (Teile des Inselrands, die auf diesen vier Ebenen der Teil-Bounding-Box liegen,
Toleranz 1 mm). Maß ist der Freiabstand = Abstand − w/2, also der Abstand der Raupenkante.
- Rechteck mit Eckradius r ≥ w/2: Gewinner ist die Mitte eines Eckbogens. Bei r = w liegt die
  Raupenkante dort 0,29·w (8,8 mm) von beiden Flächen entfernt, im ohnehin gerundeten Eckbereich.
- L-Querschnitt, Insel neben einer Öffnung: Die Naht wandert auf eine Fläche, die keine geschützte
  Ebene ist (Innenecke des L, Laibung).
- Gleichstand (± 0,5 mm, z. B. die vier Ecken eines Rechtecks): Punkt nächst der Ecke
  `params.seam_corner` der Teil-Bounding-Box, Standard (x_min, y_min), wie der Ringstart im Slicer.
- Rückfall: Hat kein Punkt einen Freiabstand > 0 (die Raupe berührt überall eine geschützte Fläche,
  z. B. ein Ring ohne Eckrundung), gilt dieselbe Wahl; `fallback = True` steht dann in der Nahtinfo
  und die Metrik M4 meldet eine Warnung.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from shapely.geometry import box
from shapely.ops import unary_union

from roboprint.patterns.geometry import Loop, densify
from roboprint.patterns.types import PatternParams

#: Toleranz, mit der ein Randstück als „auf der Bounding-Box-Ebene“ gilt (mm)
FACE_TOL_MM = 1.0


@dataclass(frozen=True)
class FitResult:
    """Ergebnis von `fit_to_length`: `count` gleich lange Felder der Länge `length_mm`,
    `positions_mm` die count + 1 Feldgrenzen ab 0 (letzte = total)."""

    count: int
    length_mm: float
    total_mm: float
    target_mm: float
    positions_mm: list[float] = field(default_factory=list)

    @property
    def deviation_mm(self) -> float:
        return self.length_mm - self.target_mm

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "length_mm": round(self.length_mm, 3),
            "total_mm": round(self.total_mm, 3),
            "target_mm": self.target_mm,
            "deviation_mm": round(self.deviation_mm, 3),
            "positions_mm": [round(x, 3) for x in self.positions_mm],
        }


def fit_to_length(
    total_mm: float,
    target_mm: float,
    *,
    min_count: int = 1,
    max_count: int | None = None,
    min_mm: float | None = None,
    max_mm: float | None = None,
) -> FitResult:
    """Ganze Zahl von Feldern auf `total_mm` verteilen, Rest gleichmäßig (alle Felder gleich lang).

    Zahl = round(total / target), dann in [min_count, max_count] gezwungen und so verschoben, dass
    die Feldlänge in [min_mm, max_mm] liegt, sofern möglich (sonst gewinnt min_count bzw. max_count).
    Beispiel: 600 mm mit Ziel 250 mm → 2 Felder à 300 mm; 1000 mm mit Ziel 300 → 3 à 333,3 mm."""
    if total_mm <= 0 or target_mm <= 0:
        raise ValueError("total_mm und target_mm müssen > 0 sein")
    n = max(1, int(round(total_mm / target_mm)))
    if max_mm is not None and total_mm / n > max_mm:
        n = math.ceil(total_mm / max_mm - 1e-9)
    if min_mm is not None and total_mm / n < min_mm:
        n = max(1, math.floor(total_mm / min_mm + 1e-9))
    n = max(n, min_count, 1)
    if max_count is not None:
        n = min(n, max_count)
    length = total_mm / n
    return FitResult(n, length, float(total_mm), float(target_mm), [i * length for i in range(n + 1)])


def protected_faces(
    region: Any, part_bounds: tuple[float, float, float, float], tol_mm: float = FACE_TOL_MM
) -> Any:
    """Randstücke der Insel, die auf einer Ebene x_min, x_max, y_min, y_max des Teils liegen
    (Außen- und Stoßflächen). Leere Geometrie, wenn es keine gibt."""
    x0, y0, x1, y1 = part_bounds
    strips = unary_union(
        [
            box(x0 - tol_mm, y0 - tol_mm, x1 + tol_mm, y0 + tol_mm),
            box(x0 - tol_mm, y1 - tol_mm, x1 + tol_mm, y1 + tol_mm),
            box(x0 - tol_mm, y0 - tol_mm, x0 + tol_mm, y1 + tol_mm),
            box(x1 - tol_mm, y0 - tol_mm, x1 + tol_mm, y1 + tol_mm),
        ]
    )
    return region.boundary.intersection(strips)


def face_clearance(
    points: np.ndarray, region: Any, part_bounds: tuple[float, float, float, float], w: float
) -> np.ndarray:
    """Freiabstand der Raupenkante (Abstand − w/2) zu den geschützten Flächen je Punkt; inf ohne solche."""
    prot = protected_faces(region, part_bounds)
    pts = np.atleast_2d(np.asarray(points, float))
    if prot.is_empty:
        return np.full(len(pts), np.inf)
    return shapely.distance(shapely.points(pts), prot) - w / 2.0


def choose_seam(
    loop: Loop, region: Any, part_bounds: tuple[float, float, float, float], params: PatternParams
) -> tuple[float, dict[str, Any]]:
    """Nahtlage auf dem Außenring nach der Regel im Modul-Docstring.
    Rückgabe (Bogenlänge auf `loop`, Info {seam, clearance_mm, fallback})."""
    cand = densify(loop.pts, 2.0)[:-1]
    clr = face_clearance(cand, region, part_bounds, params.w)
    x0, y0, x1, y1 = part_bounds
    cx = x0 if params.seam_corner[0] < 0 else x1
    cy = y0 if params.seam_corner[1] < 0 else y1
    best = float(np.max(clr))
    if math.isfinite(best):
        tie = np.flatnonzero(clr >= best - 0.5)
    else:
        tie = np.arange(len(cand))
    d = np.linalg.norm(cand[tie] - np.array([cx, cy]), axis=1)
    i = int(tie[int(np.argmin(d))])
    s = loop.project(cand[i])
    info = {
        "seam": [round(float(cand[i][0]), 3), round(float(cand[i][1]), 3)],
        "clearance_mm": None if not math.isfinite(best) else round(float(clr[i]), 3),
        "fallback": bool(math.isfinite(best) and clr[i] <= 0.0),
    }
    return s, info


def seam_on_faces(
    point: np.ndarray, region: Any, part_bounds: tuple[float, float, float, float], w: float
) -> bool:
    """Berührt die Raupe an `point` eine Außen- oder Stoßfläche (Freiabstand ≤ 0)?"""
    return bool(face_clearance(np.asarray(point)[None, :], region, part_bounds, w)[0] <= 0.0)
