"""Bahnbausteine der Familie „Topologie“ für rechteckige Wandquerschnitte (Hilfsmodul).

Alle Bahnen entstehen in einem *kanonischen* Rechteck [0, W] × [0, T] (u längs der Wand, v quer
dazu, mm) mit einer Schildkröte aus Geraden und Kreisbögen und werden erst am Ende per Spiegelung
und Verschiebung (`Frame`) nach Frame P gebracht. Spur k (k = 0 außen, 1 innen) liegt im Abstand
(k + ½)·w vom Rand, ihre Ecken haben den Radius `rc` (Standard w).

Bausteine (Begründungen im Docstring von `topologie.py` und in docs/muster/topologie.md):

- `fermat_rect`: Vollquerschnitt als Fermat-Doppelring. Spur 0 läuft gegen den Uhrzeigersinn von
  der Mitte des Eckbogens rechts oben bis auf das rechte Stirnbein, eine Wende (Halbkreis r = w/2)
  führt auf Spur 1, die im Uhrzeigersinn umläuft und neben der Wende endet. Wird das Rechteck oben
  schmaler (Abschrägung, Schicht für Schicht), fallen zuerst die oberen Schenkel weg: Spur 0 und
  Spur 1 werden zu U-Formen, die an der Wende hängen bleiben. Jede höhere Schicht nutzt nur Teile
  der Spuren der tieferen (M3 ohne Überhang).
- `pillar_left`: Pfeiler links einer Öffnung (Laibung bei u = a). Start innen auf Spur 1, Spur 1 im
  Uhrzeigersinn bis an die Laibung, Wende auf Spur 0, Spur 0 um den Pfeiler, Ende auf der unteren
  Außenfläche an der Laibungsecke. In den Schichten unter der Brüstung läuft dieselbe Bahn weiter
  ins Brüstungsfeld; die Laibungsschenkel sind dort Querstege (`web`).
- `field_between` / `field_to_end`: Brüstungsfeld zwischen zwei Pfeilern (S-Form aus drei
  Läufen) bzw. bis zum Modulende (Spirale aus Spur 0 und Spur 1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from roboprint.patterns.geometry import arc_points, dedupe

#: feine Abtastung der Bögen (Sehnenfehler mm, Punktabstand mm) vor dem Neu-Abtasten
FINE_TOL_MM = 0.02
FINE_STEP_MM = 2.0


class Turtle:
    """Polylinie aus Geraden (`to`, `fwd`) und tangentialen Kreisbögen (`turn`)."""

    def __init__(self, p: tuple[float, float] | np.ndarray, h: tuple[float, float] | np.ndarray):
        self.p = np.asarray(p, float).copy()
        h = np.asarray(h, float)
        self.h = h / np.linalg.norm(h)
        self.pts = [self.p.copy()]

    def to(self, axis: int, value: float) -> Turtle:
        """Geradeaus, bis Koordinate `axis` (0 = u, 1 = v) den Wert `value` hat."""
        if abs(self.h[axis]) < 1e-12:
            raise ValueError("Richtung parallel zur Achse")
        d = (value - self.p[axis]) / self.h[axis]
        if d < -1e-6:
            raise ValueError(f"Rückwärtsfahrt ({d:.2f} mm) bei {self.p} → {axis}={value}")
        return self.fwd(max(d, 0.0))

    def fwd(self, d: float) -> Turtle:
        if d > 1e-9:
            self.p = self.p + self.h * d
            self.pts.append(self.p.copy())
        return self

    def turn(self, r: float, deg: float) -> Turtle:
        """Kreisbogen mit Radius r; deg > 0 links (gegen den Uhrzeigersinn), < 0 rechts."""
        n = np.array([-self.h[1], self.h[0]]) * (1.0 if deg > 0 else -1.0)
        c = self.p + r * n
        v = self.p - c
        sweep = math.radians(deg)
        arc = arc_points(c, r, math.atan2(v[1], v[0]), sweep, FINE_TOL_MM, FINE_STEP_MM)
        self.pts.extend(arc[1:])
        self.p = arc[-1].copy()
        ca, sa = math.cos(sweep), math.sin(sweep)
        self.h = np.array([ca * self.h[0] - sa * self.h[1], sa * self.h[0] + ca * self.h[1]])
        return self

    def cut(self) -> np.ndarray:
        """Bisherige Punkte als Stück abgeben; die Schildkröte läuft am selben Punkt weiter."""
        out = dedupe(np.array(self.pts))
        self.pts = [self.p.copy()]
        return out


@dataclass(frozen=True)
class Piece:
    """Stück einer Bahn in kanonischen Koordinaten: Segmentart, Schale, Punkte, Beschriftung."""

    kind: str
    shell: int
    pts: np.ndarray
    label: str = ""


@dataclass(frozen=True)
class Frame:
    """Kanonisch (u, v) → Frame P: x = x0 + su·u, y = y0 + sv·v (su, sv ∈ {±1})."""

    x0: float
    y0: float
    su: float = 1.0
    sv: float = 1.0

    def apply(self, pts: np.ndarray) -> np.ndarray:
        return np.column_stack([self.x0 + self.su * pts[:, 0], self.y0 + self.sv * pts[:, 1]])


def reverse_pieces(pieces: list[Piece]) -> list[Piece]:
    return [Piece(q.kind, q.shell, q.pts[::-1].copy(), q.label) for q in reversed(pieces)]


#: Sicherheitszuschlag auf Mindestabstände (mm): Die Prüfung tastet mit 2 mm ab
CLEAR_MARGIN_MM = 1.0


def turn_clearance(w: float, eps: float) -> float:
    """Längsabstand eines Strangendes vom Mittelpunkt einer Wende (r = w/2) auf der Nachbarspur,
    damit beide sich nur berühren: Mittellinienabstand (1 − ε)·w zum Bogen, also (1 − ε)·w + w/2
    zum Mittelpunkt, quer um w/2 versetzt (plus Zuschlag)."""
    return math.sqrt(((1.0 - eps) * w + w / 2.0) ** 2 - (w / 2.0) ** 2) + CLEAR_MARGIN_MM


# --------------------------------------------------------------------------- Fermat-Doppelring


def fermat_yu(T: float, w: float, rc: float, eps: float) -> float:
    """Höchste Lage der Wende im Vollquerschnitt: Spur-1-Ende darüber noch auf dem geraden Schenkel."""
    return (T - 1.5 * w) - rc - turn_clearance(w, eps)


def fermat_min_top(w: float, rc: float) -> float:
    """Kleinste verfügbare Höhe t, bei der die Wende noch auf geraden Schenkeln liegt."""
    return 1.5 * w + rc + w - 1.0


def fermat_rect(W: float, T: float, t: float, w: float, rc: float, eps: float, yu_max: float) -> list[Piece]:
    """Fermat-Doppelring im Rechteck [0, W] × [0, T], oben nur bis t verfügbar (t ≤ T).

    Wende am rechten Stirnende (u = W) auf Höhe yu = min(yu_max, t + 1 − w). Leere Liste, wenn
    nicht einmal der untere Lauf von Spur 0 hineinpasst."""
    o0, o1 = w / 2.0, 1.5 * w
    xa0, xb0, ya0, yb0 = o0, W - o0, o0, T - o0
    xa1, xb1, ya1, yb1 = o1, W - o1, o1, T - o1
    fit0 = yb0 + w / 2.0 <= t + 1.0
    fit1 = yb1 + w / 2.0 <= t + 1.0
    yu = min(yu_max, t + 1.0 - w)
    out: list[Piece] = []
    if yu >= max(ya1 + rc, ya0 + rc) and xb1 - xa1 >= 2 * rc and yb1 - ya1 >= 2 * rc:
        if fit0:
            c = np.array([xb0 - rc, yb0 - rc])
            s0 = c + rc * np.array([math.cos(math.pi / 4), math.sin(math.pi / 4)])
            tt = Turtle(s0, (-1.0, 1.0)).turn(rc, 45).to(0, xa0 + rc).turn(rc, 90)
        else:
            top = min(yb0 - rc, t + 1.0 - w / 2.0)
            tt = Turtle((xa0, top), (0.0, -1.0))
        tt.to(1, ya0 + rc).turn(rc, 90).to(0, xb0 - rc).turn(rc, 90).to(1, yu)
        out.append(Piece("outer", 0, tt.cut(), "Spur 0"))
        tt.turn(w / 2.0, 180)
        out.append(Piece("inner", 1, tt.cut(), "Wende"))
        tt.to(1, ya1 + rc).turn(rc, -90).to(0, xa1 + rc).turn(rc, -90)
        if fit1:
            tt.to(1, yb1 - rc).turn(rc, -90).to(0, xb1 - rc).turn(rc, -90).to(1, yu + turn_clearance(w, eps))
        else:
            tt.to(1, min(yb1 - rc, t + 1.0 - w / 2.0))
        out.append(Piece("inner", 1, tt.cut(), "Spur 1"))
    elif ya0 + rc + w / 2.0 <= t + 1.0:
        top = min(yb0 - rc, t + 1.0 - w / 2.0)
        tt = Turtle((xa0, top), (0.0, -1.0))
        tt.to(1, ya0 + rc).turn(rc, 90).to(0, xb0 - rc).turn(rc, 90).to(1, top)
        out.append(Piece("outer", 0, tt.cut(), "Spur 0 (U)"))
    elif ya0 + w / 2.0 <= t + 1.0 and xb0 - xa0 > 2 * rc:
        tt = Turtle((xa0 + rc, ya0), (1.0, 0.0)).to(0, xb0 - rc)
        out.append(Piece("outer", 0, tt.cut(), "Spur 0 (Lauf)"))
    return out


# --------------------------------------------------------------------------- Pfeiler und Felder


def pillar_min_width(w: float, rc: float, eps: float) -> float:
    """Kleinste Pfeilerbreite: Spur 1 braucht oben zwei Eckbögen, der Start unten liegt um
    w + `turn_clearance` vor der Laibung auf dem geraden Lauf."""
    return max(3.0 * w + 2.0 * rc, w + turn_clearance(w, eps) + 1.5 * w + rc) + 1.0


def pillar_min_thickness(w: float, rc: float) -> float:
    """Kleinste Wanddicke: Spur-1-Schenkel an der Laibung gerade von 2·w bis T − 1,5·w − rc."""
    return 1.5 * w + rc + 2.0 * w + 1.0


def pillar_left(a: float, T: float, w: float, rc: float, eps: float, below: bool) -> list[Piece]:
    """Pfeiler [0, a] × [0, T] links einer Öffnung (Laibung bei u = a), Richtung innen → außen.

    `below`: Schicht unter der Brüstung; dann heißen die Laibungsschenkel `web` (Querstege an der
    künftigen Laibung) und die Bahn endet nicht an der Laibungsecke, sondern läuft (vom Aufrufer)
    weiter. Wendepunkt yw = 1,5·w + w/2 (Spur-1-Schenkel gerade ab dort, Radius w/2 unten rechts)."""
    o0, o1 = w / 2.0, 1.5 * w
    r1 = w / 2.0
    yw = o1 + r1
    uc = turn_clearance(w, eps)
    leg = "web" if below else "inner"
    rev = "web" if below else "outer"
    tt = Turtle((a - w - uc, o1), (-1.0, 0.0))
    tt.to(0, o1 + rc).turn(rc, -90).to(1, T - o1 - rc).turn(rc, -90).to(0, a - o1 - rc).turn(rc, -90)
    out = [Piece("inner", 1, tt.cut(), "Spur 1")]
    tt.to(1, yw)
    out.append(Piece(leg, 1, tt.cut(), "Spur 1 an der Laibung"))
    tt.turn(w / 2.0, 180)
    out.append(Piece(leg, 1, tt.cut(), "Wende an der Laibung"))
    tt.to(1, T - o0 - rc)
    out.append(Piece(rev, 0, tt.cut(), "Laibungsschenkel"))
    tt.turn(rc, 90).to(0, o0 + rc).turn(rc, 90).to(1, o0 + rc).turn(rc, 90).to(0, a - o0)
    out.append(Piece("outer", 0, tt.cut(), "Spur 0"))
    return out


def field_between(a: float, b: float, T: float, w: float, ym: float) -> list[Piece]:
    """Brüstungsfeld zwischen Pfeiler links (Laibung a) und rechts (Laibung b) als S aus drei
    Läufen: unten (+u, Fortsetzung der Pfeiler-Außenspur), Mitte (−u, Höhe ym), oben (+u, geht in
    die Außenspur des rechten Pfeilers über). Die Flanken an den Laibungen sind Querstege (`web`),
    die Raupen berühren dort die Laibungsschenkel der Pfeiler (Fuge)."""
    o0, r = w / 2.0, w / 2.0
    tt = Turtle((a - o0, o0), (1.0, 0.0)).to(0, b - w)
    out = [Piece("outer", 0, tt.cut(), "Brüstung unten")]
    tt.turn(r, 90).to(1, ym - r)
    out.append(Piece("web", 0, tt.cut(), "Flanke rechts"))
    tt.turn(r, 90).to(0, a + w)
    out.append(Piece("inner", 1, tt.cut(), "Brüstung Mitte"))
    tt.turn(r, -90).to(1, T - w)
    out.append(Piece("web", 0, tt.cut(), "Flanke links"))
    tt.turn(r, -90).to(0, b + o0)
    out.append(Piece("outer", 0, tt.cut(), "Brüstung oben"))
    return out


def field_to_end(a: float, X: float, T: float, w: float, rc: float, eps: float) -> list[Piece]:
    """Brüstungsfeld vom Pfeiler links (Laibung a) bis zum Modulende X: Spirale aus Spur 0 (unten
    als Fortsetzung des Pfeilers, Stirn, oben zurück, Flanke an der Laibung hinab) und Spur 1
    (unten, Stirn, oben bis vor die Flanke)."""
    o0, o1, r = w / 2.0, 1.5 * w, w / 2.0
    tt = Turtle((a - o0, o0), (1.0, 0.0)).to(0, X - o0 - rc).turn(rc, 90).to(1, T - o0 - rc).turn(rc, 90)
    tt.to(0, a + w)
    out = [Piece("outer", 0, tt.cut(), "Brüstung Spur 0")]
    tt.turn(r, 90).to(1, o1 + r)
    out.append(Piece("web", 0, tt.cut(), "Flanke an der Laibung"))
    tt.turn(r, 90).to(0, X - o1 - rc).turn(rc, 90).to(1, T - o1 - rc).turn(rc, 90)
    tt.to(0, a + w + turn_clearance(w, eps))
    out.append(Piece("inner", 1, tt.cut(), "Brüstung Spur 1"))
    return out
