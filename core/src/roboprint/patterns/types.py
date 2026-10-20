"""Datentypen der Druckmuster: Parameter, Segmente, Schichtpfade und Kontext für Musterfamilien.

Alle Koordinaten in Frame P (mm), nur XY. Die Schicht-Z-Lage ergibt sich aus `layer` (SPEC §5.2:
TCP beim Druck auf z_P = (layer + 1)·h); dieses Modul kennt kein Z.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: Erlaubte Segmentarten (ARTEFAKT-FORMAT.md, `kind` in toolpath.json)
SEGMENT_KINDS = ("outer", "inner", "hole", "infill", "web", "outfill")
#: Segmentarten, die zur Schalenhülle zählen (Kontakt M7, Außenstrecke)
SHELL_KINDS = frozenset({"outer", "inner", "hole", "outfill"})
#: Segmentarten, die Querverbindungen bilden (Kontaktzonen M7, Stützung der Außenhaut)
CROSS_KINDS = frozenset({"infill", "web"})
LAYER_ORDERS = ("same", "alternate")
#: Richtung eines Schichtpfads: außen → innen oder innen → außen
DIRECTIONS = ("out_in", "in_out")


@dataclass(frozen=True)
class PatternParams:
    """Parameter eines Druckmusters (alle Längen in mm).

    - `bead_width_mm` w, `layer_height_mm` h, `shells` Schalen je Seite (≥ 1).
    - `layer_order`: `alternate` (Standard dieses Moduls: gerade Schichten außen → innen, ungerade
      als exakte Umkehrung) oder `same` (jede Schicht gleich, Schichtwechsel diagonal wie heute).
    - `infill` / `outfill`: Name eines registrierten Musters, `none` = keins.
    - `step_mm`: größter Wegpunktabstand; `chord_tol_mm`: größter Sehnenfehler (M6).
    - `eps`: Kontakt-/Abstandstoleranz ε (M2, M7); `delta_mm`: Überhangtoleranz δ (M3).
    - `corner_radius_mm`: Rundung konvexer Schalenecken (Mittellinie); None = w/2 (harte M6-Grenze).
    - `seam_corner`: Ecke der Insel-Bounding-Box, an die die Naht rückt: (−1, −1) = (x_min, y_min),
      (+1, −1) = (x_max, y_min) usw.
    - `extra`: musterspezifische Werte (z. B. `wavelength_mm`, `amplitude_mm`, `phase`,
      `web_spacing_mm`). Lesen mit `params.get(key, default)`.
    """

    bead_width_mm: float = 30.0
    layer_height_mm: float = 10.0
    shells: int = 2
    layer_order: str = "alternate"
    infill: str = "none"
    outfill: str = "none"
    step_mm: float = 20.0
    chord_tol_mm: float = 0.5
    eps: float = 0.15
    delta_mm: float = 2.0
    corner_radius_mm: float | None = None
    seam_corner: tuple[int, int] = (-1, -1)
    extra: Mapping[str, Any] = field(default_factory=dict, hash=False)

    @property
    def w(self) -> float:
        return float(self.bead_width_mm)

    @property
    def corner_radius(self) -> float:
        return self.w / 2.0 if self.corner_radius_mm is None else float(self.corner_radius_mm)

    def get(self, key: str, default: Any = None) -> Any:
        """Musterspezifischer Parameter aus `extra`."""
        return self.extra.get(key, default)

    def validate(self) -> None:
        if self.bead_width_mm <= 0 or self.layer_height_mm <= 0:
            raise ValueError("bead_width_mm und layer_height_mm müssen > 0 sein")
        if self.shells < 1:
            raise ValueError("shells muss >= 1 sein")
        if self.layer_order not in LAYER_ORDERS:
            raise ValueError(f"layer_order muss in {LAYER_ORDERS} liegen, nicht {self.layer_order!r}")
        if self.step_mm <= 0 or self.chord_tol_mm <= 0:
            raise ValueError("step_mm und chord_tol_mm müssen > 0 sein")
        if not 0.0 <= self.eps < 1.0:
            raise ValueError("eps muss in [0, 1) liegen")
        if self.corner_radius < 0:
            raise ValueError("corner_radius_mm muss >= 0 sein")
        if tuple(abs(int(c)) for c in self.seam_corner) != (1, 1):
            raise ValueError("seam_corner muss aus ±1 bestehen, z. B. (-1, -1)")


def _as_xy(points: Any) -> np.ndarray:
    a = np.asarray(points, dtype=float)
    if a.ndim != 2 or a.shape[1] != 2:
        raise ValueError(f"points muss die Form (n, 2) haben, nicht {a.shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError("points enthält NaN/Inf")
    return a


@dataclass
class Segment:
    """Gedrucktes Stück eines Schichtpfads (Mittellinie, Frame P, XY).

    `kind` ∈ SEGMENT_KINDS, `shell` = Schalenindex (Schale 0 außen; Infill/Stege tragen
    `shell = params.shells`). `closed = True` heißt: letzter Punkt == erster Punkt.
    """

    kind: str
    shell: int
    points: np.ndarray
    closed: bool = False

    def __post_init__(self) -> None:
        if self.kind not in SEGMENT_KINDS:
            raise ValueError(f"kind {self.kind!r} nicht in {SEGMENT_KINDS}")
        if self.shell < 0:
            raise ValueError("shell muss >= 0 sein")
        self.points = _as_xy(self.points)
        if len(self.points) < 2:
            raise ValueError("Segment braucht mindestens 2 Punkte")
        if self.closed and (len(self.points) < 4 or not np.allclose(self.points[0], self.points[-1], atol=1e-6)):
            raise ValueError("geschlossenes Segment: mindestens 4 Punkte und letzter == erster Punkt")

    @property
    def start(self) -> np.ndarray:
        return self.points[0]

    @property
    def end(self) -> np.ndarray:
        return self.points[-1]

    @property
    def length(self) -> float:
        return float(np.linalg.norm(np.diff(self.points, axis=0), axis=1).sum())

    def reversed(self) -> Segment:
        return Segment(self.kind, self.shell, self.points[::-1].copy(), self.closed)


@dataclass
class LayerPath:
    """Ein Strang einer Schicht und Insel: Segmente in Druckreihenfolge.

    Zwischen Segment i und i + 1 liegt implizit der Verbinder als Gerade vom letzten Punkt von i
    zum ersten Punkt von i + 1 (Länge 0, wenn sie aneinanderstoßen). `island` ist der Index der
    Insel im Querschnitt der Schicht (Polygone sortiert nach (x_min, y_min) der Bounding-Box).
    `direction`: `out_in` (Schale 0 zuerst) oder `in_out` (Umkehrung).
    """

    layer: int
    island: int
    segments: list[Segment]
    direction: str = "out_in"

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction muss in {DIRECTIONS} liegen")
        if not self.segments:
            raise ValueError("LayerPath braucht mindestens ein Segment")

    @property
    def start(self) -> np.ndarray:
        return self.segments[0].start

    @property
    def end(self) -> np.ndarray:
        return self.segments[-1].end

    def connectors(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """Verbinder (Anfang, Ende) zwischen aufeinanderfolgenden Segmenten."""
        return [(a.end, b.start) for a, b in zip(self.segments[:-1], self.segments[1:], strict=True)]

    def polyline(self) -> np.ndarray:
        """Ganze Mittellinie inkl. Verbinder als (n, 2), ohne doppelte Folgepunkte."""
        pts = np.vstack([s.points for s in self.segments])
        keep = np.ones(len(pts), bool)
        keep[1:] = np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9
        return pts[keep]

    @property
    def length(self) -> float:
        return float(np.linalg.norm(np.diff(self.polyline(), axis=0), axis=1).sum())

    def reversed(self) -> LayerPath:
        """Exakte Umkehrung: Segmente in umgekehrter Folge, jedes Segment umgekehrt."""
        d = "in_out" if self.direction == "out_in" else "out_in"
        return LayerPath(self.layer, self.island, [s.reversed() for s in reversed(self.segments)], d)


def reverse_layer(paths: list[LayerPath]) -> list[LayerPath]:
    """Umkehrung einer ganzen Schicht: Inseln in umgekehrter Folge, jeder Pfad umgekehrt.
    Ende der Schicht == Anfang der Umkehrung (senkrechter Schichtwechsel, M4)."""
    return [p.reversed() for p in reversed(paths)]


@dataclass(frozen=True)
class Lane:
    """Geschlossener Schalenring (Mittellinie) vor dem Öffnen an der Naht.

    `kind`: outer (Schale 0 außen), inner (Schale > 0 außen) oder hole (Lochkontur);
    `ring` (n, 2) geschlossen, Außenkonturen gegen den Uhrzeigersinn, Löcher im Uhrzeigersinn.
    """

    shell: int
    kind: str
    ring: np.ndarray


@dataclass(frozen=True)
class IslandContext:
    """Was eine Musterfunktion über die Insel weiß (siehe Docstring von `roboprint.patterns`).

    - `layer`, `island`: Schicht und Inselindex; `region`: Querschnitt der Insel (Polygon).
    - `sections`: Querschnitte des ganzen Teils {Schicht: Geometrie} (für schichtübergreifende
      Entscheidungen, z. B. Stege an künftigen Laibungen, M3).
    - `params`: PatternParams.
    - `lanes`: Standard-Schalenringe (vor einem Outfill-Ersatz), Schale 0 zuerst.
    - `cavity`: Hohlraum innerhalb der innersten Schale (Fläche für Infill-Raupen), evtl. leer.
    - `entry`, `entry_tangent`: Ende des bisherigen Pfads und Fahrtrichtung dort (nur Infill;
      beim Outfill-Aufruf None).
    - `printed`: dicht abgetastete Punkte (≤ 2 mm) des bisherigen Pfads dieser Insel in
      Druckreihenfolge, (m, 2); beim Outfill-Aufruf leer.
    """

    layer: int
    island: int
    region: Any
    sections: Mapping[int, Any]
    params: PatternParams
    lanes: tuple[Lane, ...]
    cavity: Any
    entry: np.ndarray | None = None
    entry_tangent: np.ndarray | None = None
    printed: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
