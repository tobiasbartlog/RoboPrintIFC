"""Riemenscheiben-Geometrie für die Fugenwand (Hilfsmodul, wird nicht als Familie geladen).

Ein Schichtpfad der Fugenwand ist ein geschlossener Zug aus Kreisbögen und Geraden. Wir beschreiben
ihn wie einen Riemen über Scheiben: eine zyklische Folge von Kreisen (`Pulley`: Mittelpunkt,
Radius r, Drehsinn s = +1 gegen den Uhrzeigersinn, −1 im Uhrzeigersinn). Zwischen zwei
aufeinanderfolgenden Kreisen läuft der Pfad auf der passenden gemeinsamen Tangente (äußere Tangente
bei gleichem Drehsinn, innere bei verschiedenem), auf jedem Kreis auf dem Bogen vom Ankunfts- zum
Abfahrtspunkt in seinem Drehsinn.

Warum so: Die Kontakte der Fugenwand (Fuge, Knoten, Rautenspitze) sind Stellen, an denen zwei
Bögen bzw. zwei kurze Geraden im Abstand δ = w − Überlappung nebeneinander liegen. Mit Kreisen lässt
sich der Extrempunkt jedes Bogens exakt setzen (Mittelpunkt ± r), der Pfad ist tangentenstetig
(keine Ecken, M6) und jeder Bogen hat genau den gewählten Radius. Eine Polylinie mit scharfen Ecken
und nachträglicher Rundung (`fillet_polyline`) kann das bei spitzen Winkeln nicht: Die Tangenten-
länge r·cot(φ/2) eines 30°-Hakens ist 3,7·r und größer als die halbe Steglänge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from roboprint.patterns.geometry import arc_points, dedupe, densify

#: Feine Abtastung der Sollkurve vor dem Neu-Abtasten (Sehnenfehler, Punktabstand)
FINE_CHORD_MM = 0.05
FINE_STEP_MM = 4.0


class GeometryError(ValueError):
    """Die Riemenfolge ist so nicht baubar (Kreise zu nah für eine innere Tangente u. ä.)."""


@dataclass(frozen=True)
class Pulley:
    """Kreis der Riemenfolge. `kind`: Segmentart des Bogens auf diesem Kreis. `tag`: Rolle für
    Kontakte und Kennzahlen (z. B. "joint", "node", "apex", "corner")."""

    cx: float
    cy: float
    r: float
    sense: int
    kind: str
    tag: str = ""

    @property
    def c(self) -> np.ndarray:
        return np.array([self.cx, self.cy])

    def mirrored(self, y_axis2: float) -> Pulley:
        """Spiegelung an y = y_axis2 / 2 (Drehsinn wechselt)."""
        return Pulley(self.cx, y_axis2 - self.cy, self.r, -self.sense, self.kind, self.tag)

    def flipped(self) -> Pulley:
        """Gleicher Kreis, Durchlauf rückwärts (Drehsinn wechselt)."""
        return Pulley(self.cx, self.cy, self.r, -self.sense, self.kind, self.tag)


@dataclass
class Chain:
    """Offene Riemenfolge: `pulleys` und die Segmentart `links[i]` der Geraden von i nach i + 1."""

    pulleys: list[Pulley]
    links: list[str]

    def __post_init__(self) -> None:
        if self.pulleys and len(self.links) != len(self.pulleys) - 1:
            raise ValueError("Chain: len(links) muss len(pulleys) − 1 sein")

    def extend(self, other: Chain, link: str) -> Chain:
        """Kette anhängen, `link` ist die Gerade vom letzten Kreis zum ersten der anderen."""
        if not self.pulleys:
            return Chain(list(other.pulleys), list(other.links))
        if not other.pulleys:
            return Chain(list(self.pulleys), list(self.links))
        return Chain(self.pulleys + other.pulleys, self.links + [link] + other.links)

    def mirrored_reversed(self, y_axis2: float) -> Chain:
        """Gespiegelt an der Wandmitte und rückwärts durchlaufen (Rückseite aus einer Vorderseite).
        Spiegeln und Umkehren wechseln je den Drehsinn, er bleibt also gleich."""
        ps = [p.mirrored(y_axis2).flipped() for p in reversed(self.pulleys)]
        return Chain(ps, list(reversed(self.links)))


def tangent(p1: Pulley, p2: Pulley) -> tuple[np.ndarray, np.ndarray]:
    """Gemeinsame Tangente von p1 nach p2 im jeweiligen Drehsinn: (Abfahrtspunkt auf p1,
    Ankunftspunkt auf p2).

    Fahrtrichtung u, rechte Normale m = (u_y, −u_x). Auf einem Kreis mit Drehsinn s liegt der Punkt
    mit Fahrtrichtung u bei C + s·r·m. Aus (P2 − P1) ⟂ m folgt D·m = r1·s1 − r2·s2 =: k mit
    D = C2 − C1; dazu (P2 − P1)·u > 0. GeometryError, wenn |k| > |D| (Kreise überlappen für eine
    innere Tangente)."""
    D = p2.c - p1.c
    nd = float(np.linalg.norm(D))
    k = p1.r * p1.sense - p2.r * p2.sense
    if nd < 1e-9 or abs(k) > nd - 1e-9:
        raise GeometryError(
            f"keine Tangente zwischen Kreisen ({p1.tag} bei {p1.cx:.1f}/{p1.cy:.1f}, "
            f"{p2.tag} bei {p2.cx:.1f}/{p2.cy:.1f}): Abstand {nd:.1f} mm < {abs(k):.1f} mm"
        )
    th_d = math.atan2(D[1], D[0])
    beta = math.acos(k / nd)
    for th in (th_d + beta, th_d - beta):
        m = np.array([math.cos(th), math.sin(th)])
        u = np.array([-m[1], m[0]])
        a = p1.c + p1.sense * p1.r * m
        b = p2.c + p2.sense * p2.r * m
        if float((b - a) @ u) > 1e-9:
            return a, b
    # Berührende Kreise (Tangente der Länge 0): beide Punkte fallen zusammen
    m = np.array([math.cos(th_d + beta), math.sin(th_d + beta)])
    a = p1.c + p1.sense * p1.r * m
    return a, a.copy()


def arc_between(
    p: Pulley, a: np.ndarray, b: np.ndarray, chord_mm: float = FINE_CHORD_MM, step_mm: float = FINE_STEP_MM
) -> np.ndarray:
    """Bogen auf p von a nach b im Drehsinn (Sehnenfehler ≤ chord_mm, Punktabstand ≤ step_mm;
    leerer Bogen → nur a, b). Alle Punkte liegen auf dem Kreis."""
    va, vb = a - p.c, b - p.c
    a0 = math.atan2(va[1], va[0])
    a1 = math.atan2(vb[1], vb[0])
    sweep = (a1 - a0) * p.sense % (2 * math.pi)
    if sweep > 2 * math.pi - 1e-7 or sweep < 1e-7:
        return np.vstack([a, b])
    pts = arc_points(p.c, p.r, a0, p.sense * sweep, chord_mm, step_mm)
    pts[0], pts[-1] = a, b
    return pts


@dataclass
class Piece:
    """Stück des geschlossenen Zugs: Bogen (`pulley` gesetzt) oder Gerade."""

    kind: str
    points: np.ndarray
    pulley: Pulley | None = None
    tag: str = ""

    @property
    def length(self) -> float:
        return float(np.linalg.norm(np.diff(self.points, axis=0), axis=1).sum())


def loop_pieces(
    pulleys: list[Pulley], links: list[str], chord_mm: float = FINE_CHORD_MM, step_mm: float = FINE_STEP_MM
) -> list[Piece]:
    """Geschlossener Zug über alle Kreise (zyklisch, `links[i]` = Gerade i → i + 1 mod n).
    Reihenfolge: Bogen 0, Gerade 0→1, Bogen 1, …, Gerade (n−1)→0. Die Punkte liegen exakt auf
    der Sollkurve (Kreise und Geraden); mit chord_mm = 0,5 und step_mm = 20 ist das schon die
    Abtastung nach M6, ein Neu-Abtasten (`resample_curve`) ist nicht nötig."""
    n = len(pulleys)
    if n < 2 or len(links) != n:
        raise ValueError("loop_pieces: mindestens 2 Kreise und genau n Geraden")
    tans = [tangent(pulleys[i], pulleys[(i + 1) % n]) for i in range(n)]
    pieces: list[Piece] = []
    for i, p in enumerate(pulleys):
        arrive = tans[i - 1][1]
        leave = tans[i][0]
        pieces.append(Piece(p.kind, arc_between(p, arrive, leave, chord_mm, step_mm), p, p.tag))
        a, b = tans[i]
        pieces.append(Piece(links[i], densify(np.vstack([a, b]), step_mm), None, "line"))
    return pieces


def arc_sweep_deg(piece: Piece) -> float:
    """Überstrichener Winkel eines Bogenstücks in Grad (Gerade: 0)."""
    if piece.pulley is None or len(piece.points) < 2:
        return 0.0
    v = np.diff(piece.points, axis=0)
    ang = np.unwrap(np.arctan2(v[:, 1], v[:, 0]))
    return float(abs(math.degrees(ang[-1] - ang[0]))) if len(ang) > 1 else 0.0


def merge_pieces(pieces: list[Piece]) -> list[tuple[str, np.ndarray]]:
    """Aufeinanderfolgende Stücke gleicher Art zu einer Punktfolge zusammenfassen (Stücke der
    Länge 0 entfallen)."""
    out: list[tuple[str, list[np.ndarray]]] = []
    for pc in pieces:
        if pc.length < 1e-9:
            continue
        if out and out[-1][0] == pc.kind:
            out[-1][1].append(pc.points[1:])
        else:
            out.append((pc.kind, [pc.points]))
    return [(k, dedupe(np.vstack(parts))) for k, parts in out]
