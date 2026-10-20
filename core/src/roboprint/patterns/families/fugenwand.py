"""Musterfamilie Fugenwand: Außenhaut aus geraden Feldern mit Sollbruchfugen (Outfill O2).

Vorbild ist das Foto `docs/muster/referenz/fugenwand-foto.jpg` (Nutzer-Nachtrag 18:20). Die
Außenhaut besteht aus geraden Feldern (`outfill`). An jeder Feldgrenze stoßen zwei Felder stumpf
aneinander: Ihre Enden biegen als Haken nach innen und berühren sich (Kontakt `joint`), die Raupe
läuft dort aber nicht durch. Das ist die Sollbruchstelle. Von jeder Fuge laufen zwei Schrägstege
(`web`) V-förmig nach innen zu Knoten (Kontakt `node`). Der Modulstoß ist selbst eine Fuge, die
Endkappe (`outfill`) schließt das Modul. Ausführliche Begründung, Skizzen und Kennzahlen:
`docs/muster/fugenwand.md`.

Topologie (je Schicht und Insel ein geschlossener Zug ohne Kreuzung)
====================================================================

Der Zug ist eine einfache geschlossene Kurve, die sich nur berührt. Die Zellen sind deshalb
abwechselnd „innen“ und „außen“: Das Dreieck über einem Feld ist innen (über die Außenhaut an das
Äußere grenzend), der Raum über einer Fuge ist außen (er hängt über den Fugenspalt am Äußeren).
Ein einziger Strang entsteht genau dann, wenn die Innenzellen über Berührstellen einen Baum bilden
und die Außenzellen ebenfalls. Daraus folgen die Varianten:

- `belt = True` (Gurt, Variante a/c): Vorschlag des Nutzers. Je Fuge eine Schleife
  Feld → Haken → Steg zum Knoten über der Feldmitte links → Gurtstück (`infill`) zum Knoten rechts →
  Steg zurück zur Fuge → Haken → nächstes Feld. Jede Fuge und jeder Knoten wird zweimal berührt;
  die beiden Besuche sind spiegelbildliche Haken, die nicht ineinandergreifen. Die Rückseite ist
  gleich gebaut, gespiegelt (`back_offset = gespiegelt`, durchgehende Sollbruchebene) oder um eine
  halbe Teilung versetzt. Vorder- und Rückgurt liegen bei y_m ∓ δ/2 und berühren sich auf ganzer
  Länge (Doppelgurt): Ein einzelner gemeinsamer Gurt ist unmöglich, weil jede Seite ihre
  Gurtstücke für die eigenen Schleifen braucht; zwei Gurte mit Abstand ließen eine Zelle über die
  ganze Modullänge offen.
- `belt = False` (Rautenkette, Variante b): An jeder Fuge hängt eine Raute (Fuge → linke Spitze in
  der Wandmitte → Spitze an der Gegenseite → rechte Spitze → Fuge). Die Rauten berühren sich an den
  Knoten in der Wandmitte („Knoten beider Seiten berühren sich“), ihre Spitze berührt das
  durchlaufende Feld der Gegenseite. Die Fugen der Rückseite liegen dabei **zwangsläufig** um eine
  halbe Teilung versetzt: Gespiegelt ohne Gurt (Fugen beider Seiten gegenüber) ist als ein Strang
  unmöglich. Beweis: Die Raute über einer Fuge ist eine Außenzelle. Hätte sie auf beiden Seiten
  einen Fugenspalt, wäre sie zweimal mit dem Äußeren verbunden (Kreis im Außenbaum) und der Zug
  zerfiele in zwei Stränge. Ohne Gurt hängen die Dreiecke über den Feldern außerdem nur über die
  Knoten zusammen; mit Fugen an allen gespiegelten Stellen bilden je Feld Vorder- und Rückdreieck
  eine eigene Innenkomponente, also n Stränge für n Felder. Wird `gespiegelt` ohne Gurt gewählt,
  entsteht deshalb die Rautenkette, und `meta["note"]` sagt das.

Geometrie
=========

Alle Bögen sind Kreise mit Radius r (`hook_radius_mm`, 0 = Eckradius = w); der Zug ist eine
Riemenfolge über Kreise (`_fugenwand_geom`), tangentenstetig, ohne Ecken. Ein Kontakt ist ein Paar
spiegelbildlicher Bögen, deren Extrempunkte den Mittellinienabstand δ = w − Überlappung haben
(`contact_overlap_mm`, Standard 1 mm, damit der Sehnenfehler ≤ 0,5 mm je Seite den Kontakt nicht
öffnet; erlaubt sind 0 … ε·w = 4,5 mm). Mit `joint_contact_mm`, `node_length_mm`, `apex_length_mm`
werden die Kontakte zu geraden Berührstrecken dieser Länge. `joint_gap_mm` > 0 setzt die
Fugenhaken auf w + Spalt auseinander (offene Fuge, kein Kontakt).

Einteilung: `fit_to_length(Modullänge, Feldlänge)` gibt eine ganze Zahl gleich langer Felder; ist
`web_angle_deg` > 0, folgt die Ziel-Feldlänge aus dem Stegwinkel (Gerade Fuge → Knoten). Ist die
Riemenfolge so nicht baubar oder nicht kreuzungsfrei (Wand zu dünn für die Haken), werden
schrittweise weniger, längere Felder versucht (`meta["fields_requested"]`); geht gar nichts,
liefert das Muster das Grundmuster `shell_chain` und `meta["fallback"]` nennt den Grund.

Naht (M4): Der Zug ist geschlossen, Anfang = Ende. Er beginnt in der Mitte des Gurtstücks bzw.
Stegs mit dem größten Abstand zu Außen- und Stoßflächen (bei Gleichstand nächst der Modulmitte).
Der Materialpunkt des senkrechten Schichtwechsels liegt damit im Wandinneren auf einem Gurt bzw.
Steg, nie auf der Sichtfläche und nie am Modulstoß.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from roboprint.patterns.families._fugenwand_geom import (
    Chain,
    GeometryError,
    Piece,
    Pulley,
    arc_sweep_deg,
    loop_pieces,
    merge_pieces,
    tangent,
)
from roboprint.patterns.geometry import densify
from roboprint.patterns.layout import face_clearance, fit_to_length
from roboprint.patterns.registry import pattern
from roboprint.patterns.shells import shell_chain
from roboprint.patterns.types import Contact, IslandContext, IslandPlan, ParamSpec, Segment

OFFSETS = ("gespiegelt", "versetzt")
END_NODES = ("Endkappe", "Feldmitte")
#: Rechteckprüfung: Fläche der Insel / Fläche der Bounding-Box
RECT_TOL = 0.999
LABELS = {"outfill": "Außenhaut", "web": "Steg", "infill": "Gurt"}

PARAMS = [
    ParamSpec(
        "field_length_mm",
        "Feldlänge (Ziel)",
        400.0,
        "mm",
        120.0,
        2000.0,
        5.0,
        help="Außenstrang zwischen zwei Fugen; ganze Zahl Felder je Modul, Rest gleichmäßig verteilt",
    ),
    ParamSpec(
        "web_angle_deg",
        "Stegwinkel (0 = aus Feldlänge)",
        0.0,
        "°",
        0.0,
        80.0,
        1.0,
        help="Winkel Fuge → Knoten gegen die Wandachse; > 0 bestimmt die Ziel-Feldlänge",
    ),
    ParamSpec("belt", "mit Gurt", True, "", kind="bool", help="ohne Gurt: Rautenkette"),
    ParamSpec(
        "back_offset",
        "Rückseite",
        "gespiegelt",
        "",
        kind="choice",
        choices=OFFSETS,
        help="Fugen der Rückseite gegenüber oder um eine halbe Teilung versetzt",
    ),
    ParamSpec(
        "end_node",
        "Knoten im Endfeld",
        "Endkappe",
        "",
        kind="choice",
        choices=END_NODES,
        help="Gurt: Knoten des Endfelds an der Endkappe (kleinere Endzelle) oder über der Feldmitte",
    ),
    ParamSpec("joint_gap_mm", "Fugenspalt (0 = stumpf)", 0.0, "mm", 0.0, 30.0, 0.5),
    ParamSpec("joint_contact_mm", "Kontaktlänge Fuge", 0.0, "mm", 0.0, 200.0, 5.0),
    ParamSpec("node_length_mm", "Knotenlänge", 0.0, "mm", 0.0, 200.0, 5.0),
    ParamSpec("apex_length_mm", "Kontaktlänge Rautenspitze", 0.0, "mm", 0.0, 200.0, 5.0),
    ParamSpec(
        "hook_radius_mm",
        "Radius an Fuge und Knoten (0 = Eckradius)",
        0.0,
        "mm",
        0.0,
        100.0,
        1.0,
        help="M6: hart ≥ w/2, Ziel ≥ w",
    ),
    ParamSpec(
        "contact_overlap_mm",
        "Sollüberlappung an Kontakten",
        1.0,
        "mm",
        0.0,
        4.5,
        0.1,
        help="Mittellinienabstand an Fuge und Knoten = w − Überlappung (0 … ε·w)",
    ),
]


# --------------------------------------------------------------------------- Bausteine


class _Geo:
    """Maße eines rechteckigen Moduls (Frame P): Vorderseite y0, Rückseite y1."""

    def __init__(self, ctx: IslandContext, vals: dict[str, Any], radius: float | None = None):
        x0, y0, x1, y1 = ctx.region.bounds
        p = ctx.params
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.w = w = p.w
        self.length = x1 - x0
        self.thickness = y1 - y0
        self.yf = y0 + w / 2.0
        self.yb = y1 - w / 2.0
        self.y2 = y0 + y1
        self.ym = self.y2 / 2.0
        self.rc = float(p.corner_radius)
        self.r = float(vals["hook_radius_mm"]) or self.rc
        if self.r <= 0:
            self.r = w
        if radius is not None:
            self.r = float(radius)
        self.delta = w - float(vals["contact_overlap_mm"])
        gap = float(vals["joint_gap_mm"])
        self.dj = self.delta if gap <= 0 else w + gap
        self.kj = float(vals["joint_contact_mm"])
        self.kn = float(vals["node_length_mm"])
        self.ka = float(vals["apex_length_mm"])
        self.y_belt = self.ym - self.delta / 2.0

    def pair(self, x: float, y_lo: float, y_hi: float, sense: int, kind: str, tag: str) -> list[Pulley]:
        """Ein Kreis oder zwei übereinander (gerade Berührstrecke y_lo → y_hi)."""
        a = Pulley(x, y_lo, self.r, sense, kind, tag)
        if y_hi - y_lo < 1e-6:
            return [a]
        return [a, Pulley(x, y_hi, self.r, sense, kind, tag)]

    def joint(self, X: float, side: str) -> Chain:
        """Fugenhaken der Vorderseite: `left` = Ende des linken Felds (Kreis links der Fuge, nach
        oben), `right` = Anfang des rechten Felds (von oben kommend)."""
        y_lo = self.yf + self.r
        if side == "left":
            ps = self.pair(X - self.dj / 2 - self.r, y_lo, y_lo + self.kj, +1, "outfill", "joint")
        else:
            ps = self.pair(X + self.dj / 2 + self.r, y_lo, y_lo + self.kj, +1, "outfill", "joint")[::-1]
        return Chain(ps, ["outfill"] * (len(ps) - 1))

    def belt_node(self, M: float, side: str) -> Chain:
        """Gurtknoten der Vorderseite bei x = M. `right`: rechter Haken (Steg kommt von unten
        rechts, weiter auf dem Gurt nach +x); `left`: linker Haken (Gurt kommt von links, Steg
        geht nach unten links)."""
        y_hi = self.y_belt - self.r
        y_lo = y_hi - self.kn
        if side == "right":
            ps = self.pair(M + self.delta / 2 + self.r, y_lo, y_hi, -1, "web", "node")
        else:
            ps = self.pair(M - self.delta / 2 - self.r, y_lo, y_hi, -1, "web", "node")[::-1]
        return Chain(ps, ["web"] * (len(ps) - 1))

    def end_node_x(self, side: str) -> float:
        """Knoten eines halben Endfelds: berührt die Endkappe (Kontakt `shell`)."""
        if side == "left":
            return self.x0 + self.w / 2 + self.delta / 2
        return self.x1 - self.w / 2 - self.delta / 2

    def rhomb_vertex(self, N: float, side: str) -> Chain:
        """Seitliche Rautenspitze in der Wandmitte am Knoten N (Raute im Uhrzeigersinn)."""
        lo, hi = self.ym - self.kn / 2, self.ym + self.kn / 2
        if side == "left":  # linke Spitze der Raute rechts von N: von unten nach oben
            ps = self.pair(N + self.delta / 2 + self.r, lo, hi, -1, "web", "node")
        else:  # rechte Spitze der Raute links von N: von oben nach unten
            ps = self.pair(N - self.delta / 2 - self.r, lo, hi, -1, "web", "node")[::-1]
        return Chain(ps, ["web"] * (len(ps) - 1))

    def apex(self, X: float) -> Chain:
        """Rautenspitze an der Gegenseite (berührt deren Feld, Kontakt `shell`)."""
        y = self.yb - self.delta - self.r
        ps = [Pulley(X - self.ka / 2, y, self.r, -1, "web", "apex")]
        if self.ka > 1e-6:
            ps.append(Pulley(X + self.ka / 2, y, self.r, -1, "web", "apex"))
        return Chain(ps, ["web"] * (len(ps) - 1))


def _concat(parts: list[tuple[Chain, str]]) -> Chain:
    out = Chain([], [])
    for ch, link in parts:
        out = out.extend(ch, link)
    return out


def belt_face(g: _Geo, joints: list[float], nodes: list[float]) -> Chain:
    """Eine Seite mit Gurt (in Koordinaten der Vorderseite): je Fuge die Schleife
    Haken → Steg → Knoten → Gurt → Knoten → Steg → Haken. `nodes[i]` = Knoten über Feld i."""
    parts: list[tuple[Chain, str]] = []
    for j, X in enumerate(joints):
        loop = _concat(
            [
                (g.joint(X, "left"), ""),
                (g.belt_node(nodes[j], "right"), "web"),
                (g.belt_node(nodes[j + 1], "left"), "infill"),
                (g.joint(X, "right"), "web"),
            ]
        )
        parts.append((loop, "outfill"))
    return _concat(parts)


def rhomb_face(g: _Geo, joints: list[float], half: float) -> Chain:
    """Eine Seite der Rautenkette: an jeder Fuge X eine Raute mit Spitzen bei X ± half."""
    parts: list[tuple[Chain, str]] = []
    for X in joints:
        loop = _concat(
            [
                (g.joint(X, "left"), ""),
                (g.rhomb_vertex(X - half, "left"), "web"),
                (g.apex(X), "web"),
                (g.rhomb_vertex(X + half, "right"), "web"),
                (g.joint(X, "right"), "web"),
            ]
        )
        parts.append((loop, "outfill"))
    return _concat(parts)


def _nodes(g: _Geo, bounds: list[float], full: float, at_cap: bool) -> list[float]:
    """Knoten je Feld: Feldmitte. Endfelder bekommen den Knoten an der Endkappe (der Knotenhaken
    berührt die Kappe, Kontakt `shell`), wenn `at_cap` gilt oder das Endfeld kürzer als 0,75 der
    Teilung ist (versetzte Seite: Ein Knoten über der Mitte eines halben Felds läge links vom
    Fugenhaken)."""
    out = []
    last = len(bounds) - 2
    for i, (a, b) in enumerate(zip(bounds[:-1], bounds[1:], strict=True)):
        cap = at_cap or b - a < 0.75 * full
        if cap and i == 0:
            out.append(g.end_node_x("left"))
        elif cap and i == last:
            out.append(g.end_node_x("right"))
        else:
            out.append(0.5 * (a + b))
    return out


# --------------------------------------------------------------------------- Aufbau


def layout(g: _Geo, vals: dict[str, Any], n: int, F: float) -> tuple[Chain, Chain, dict[str, Any]]:
    """Vorder- und Rückseite (Rückseite schon gespiegelt und rückwärts) für n Felder der Länge F."""
    front_j = [g.x0 + k * F for k in range(1, n)]
    belt = bool(vals["belt"])
    offset = vals["back_offset"] == "versetzt"
    info: dict[str, Any] = {"variant": "gurt" if belt else "raute"}
    if belt:
        back_j = [g.x0 + (k - 0.5) * F for k in range(1, n + 1)] if offset else list(front_j)
        fb = [g.x0, *front_j, g.x1]
        bb = [g.x0, *back_j, g.x1]
        at_cap = vals["end_node"] == "Endkappe"
        nf, nb = _nodes(g, fb, F, at_cap), _nodes(g, bb, F, at_cap)
        front = belt_face(g, front_j, nf)
        back = belt_face(g, back_j, nb)
        info.update(nodes_front_x=nf, nodes_back_x=nb)
        info["variant"] = "gurt_versetzt" if offset else "gurt_gespiegelt"
    else:
        back_j = [g.x0 + (k - 0.5) * F for k in range(1, n + 1)]
        front = rhomb_face(g, front_j, F / 4)
        back = rhomb_face(g, back_j, F / 4)
        if not offset:
            info["note"] = (
                "gespiegelt ohne Gurt ist als ein Strang unmöglich (siehe Docstring); "
                "gebaut wird die Rautenkette mit um F/2 versetzter Rückseite"
            )
        info["nodes_x"] = sorted([X - F / 4 for X in front_j] + [X + F / 4 for X in front_j])
    info.update(joints_front_x=front_j, joints_back_x=back_j)
    return front, back.mirrored_reversed(g.y2), info


def assemble(g: _Geo, front: Chain, back: Chain) -> tuple[list[Pulley], list[str]]:
    """Geschlossene Riemenfolge: Ecke vorn links, Vorderseite, Ecken rechts (Endkappe), Rückseite,
    Ecke hinten links (Endkappe links schließt den Zug)."""
    rc, w = g.rc, g.w
    fl = Pulley(g.x0 + w / 2 + rc, g.yf + rc, rc, +1, "outfill", "corner")
    fr = Pulley(g.x1 - w / 2 - rc, g.yf + rc, rc, +1, "outfill", "corner")
    br = Pulley(g.x1 - w / 2 - rc, g.yb - rc, rc, +1, "outfill", "corner")
    bl = Pulley(g.x0 + w / 2 + rc, g.yb - rc, rc, +1, "outfill", "corner")
    ch = Chain([fl], [])
    ch = ch.extend(front, "outfill")
    ch = ch.extend(Chain([fr, br], ["outfill"]), "outfill")
    ch = ch.extend(back, "outfill")
    ch = ch.extend(Chain([bl], []), "outfill")
    return ch.pulleys, [*ch.links, "outfill"]


def _seam_rotate(pieces: list[Piece], g: _Geo, region: Any, bounds: Any) -> tuple[list[Piece], dict]:
    """Zug so drehen, dass er in der Mitte des Gurtstücks (sonst Stegs) mit dem größten Freiabstand
    zu Außen- und Stoßflächen beginnt (Gleichstand ± 0,5 mm: nächst der Modulmitte)."""
    cand = [
        k
        for k, pc in enumerate(pieces)
        if pc.pulley is None and pc.kind in ("infill", "web") and pc.length > 2 * g.w / 3
    ]
    if not cand:
        cand = [k for k, pc in enumerate(pieces) if pc.length > 1.0]
    mids = np.array([0.5 * (pieces[k].points[0] + pieces[k].points[-1]) for k in cand])
    belt_first = np.array([0 if pieces[k].kind == "infill" else 1 for k in cand])
    clr = face_clearance(mids, region, bounds, g.w)
    xc = 0.5 * (g.x0 + g.x1)
    score = [(belt_first[i], -round(clr[i] * 2) / 2, abs(mids[i][0] - xc)) for i in range(len(cand))]
    best = min(range(len(cand)), key=lambda i: score[i])
    k = cand[best]
    pc = pieces[k]
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pc.points, axis=0), axis=1))])
    half = s[-1] / 2
    m = pc.points[0] + (pc.points[-1] - pc.points[0]) * 0.5
    i = int(np.searchsorted(s, half))
    a = Piece(pc.kind, np.vstack([pc.points[:i], m]), None, pc.tag)
    b = Piece(pc.kind, np.vstack([m, pc.points[i:]]), None, pc.tag)
    rotated = [b, *pieces[k + 1 :], *pieces[:k], a]
    seam = [round(float(m[0]), 3), round(float(m[1]), 3)]
    info = {"seam": seam, "clearance_mm": round(float(clr[best]), 2)}
    return rotated, info


def check_loop(segs: list[tuple[str, np.ndarray]], w: float, eps: float) -> str | None:
    """Schnelle Selbstprüfung des Zugs (vor der Metrik): einfach (kein Selbstschnitt) und kein
    Punktpaar mit Bogenlängenabstand > 2·w näher als (1 − ε)·w. Rückgabe: Fehlertext oder None."""
    pts = np.vstack([segs[0][1]] + [s[1][1:] for s in segs[1:]])
    if not LineString(pts).is_simple:
        return "Selbstschnitt"
    d = densify(pts, 2.0)
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(d, axis=0), axis=1))])
    total = arc[-1]
    pairs = cKDTree(d).query_pairs((1 - eps) * w - 0.5, output_type="ndarray")
    if len(pairs):
        sep = np.abs(arc[pairs[:, 1]] - arc[pairs[:, 0]])
        sep = np.minimum(sep, total - sep)
        bad = sep > 2 * w
        if np.any(bad):
            q = pairs[bad][0]
            return f"Stränge zu nah bei ({d[q[0]][0]:.0f}, {d[q[0]][1]:.0f})"
    return None


def _contacts(g: _Geo, info: dict[str, Any], segs: list[Segment]) -> list[Contact]:
    """Deklarierte Kontakte (Absicht): Fugen, Knoten, Rautenspitzen."""
    out: list[tuple[str, tuple[float, float]]] = []
    yj = g.yf + g.r + g.kj / 2
    if g.dj <= g.w:
        out += [("joint", (X, yj)) for X in info["joints_front_x"]]
        out += [("joint", (X, g.y2 - yj)) for X in info["joints_back_x"]]
    if info["variant"].startswith("gurt"):
        yn = g.y_belt - g.r - g.kn / 2
        for key, mirror in (("nodes_front_x", False), ("nodes_back_x", True)):
            xs = info[key]
            for x in xs[1:-1]:
                out.append(("node", (x, g.y2 - yn if mirror else yn)))
            for x in (xs[0], xs[-1]):
                if abs(x - g.end_node_x("left")) < 1e-6 or abs(x - g.end_node_x("right")) < 1e-6:
                    out.append(("shell", (x, g.y2 - yn if mirror else yn)))
    else:
        out += [("node", (x, g.ym)) for x in info["nodes_x"]]
        ya = g.yb - g.delta / 2
        out += [("shell", (X, ya)) for X in info["joints_front_x"]]
        out += [("shell", (X, g.y2 - ya)) for X in info["joints_back_x"]]
    res = []
    for kind, at in out:
        q = np.array(at)
        dist = [float(np.min(np.linalg.norm(s.points - q, axis=1))) for s in segs]
        i, j = sorted(np.argsort(dist)[:2].tolist()) if len(segs) > 1 else (0, 0)
        res.append(Contact(kind, at, 0.0, (int(i), int(j)), g.delta))
    return res


def _is_rect(region: Any) -> bool:
    return len(region.interiors) == 0 and region.area >= RECT_TOL * region.envelope.area


#: Radiusstufen für Haken an Fuge und Knoten, falls der Zielradius nicht passt (hart ≥ w/2, M6)
RADIUS_STEPS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)


def leg_angle_deg(g: _Geo, belt: bool, F: float) -> float:
    """Tatsächlicher Winkel des Stegs Fuge → Knoten (innere Tangente der beiden Haken) für
    Feldlänge F, ohne Knoten an der Endkappe. NaN, wenn es die Tangente nicht gibt."""
    X = g.x0 + F
    a = g.joint(X, "left").pulleys[-1]
    if belt:
        b = g.belt_node(X - F / 2, "right").pulleys[0]
    else:
        b = g.rhomb_vertex(X - F / 4, "left").pulleys[0]
    try:
        s, e = tangent(a, b)
    except GeometryError:
        return math.nan
    v = e - s
    return math.degrees(math.atan2(abs(v[1]), abs(v[0])))


def field_for_angle(g: _Geo, belt: bool, angle_deg: float) -> tuple[float, float]:
    """Feldlänge, bei der der Steg den Winkel `angle_deg` hat (Bisektion; der Winkel fällt mit
    wachsender Feldlänge). Ist der Winkel mit diesen Haken nicht erreichbar, die Feldlänge des
    steilsten baubaren Stegs. Rückgabe (Feldlänge, erreichter Winkel)."""
    k = 2.0 if belt else 4.0
    lo = k * (g.dj / 2 + g.delta / 2 + 2 * g.r) + 1.0
    hi = max(4.0 * g.length, 4000.0)
    while math.isnan(leg_angle_deg(g, belt, lo)) and lo < hi:
        lo *= 1.05
    if leg_angle_deg(g, belt, lo) <= angle_deg:
        return lo, leg_angle_deg(g, belt, lo)
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if leg_angle_deg(g, belt, mid) > angle_deg:
            lo = mid
        else:
            hi = mid
    return hi, leg_angle_deg(g, belt, hi)


def _attempt(ctx: IslandContext, g: _Geo, vals: dict[str, Any], n: int) -> tuple[Any, str]:
    """Ein Bauversuch mit n Feldern: (IslandPlan-Teile, "") oder (None, Grund)."""
    p = ctx.params
    F = g.length / n
    try:
        front, back, info = layout(g, vals, n, F)
        pulleys, links = assemble(g, front, back)
        pieces = loop_pieces(pulleys, links, p.chord_tol_mm, p.step_mm)
    except GeometryError as e:
        return None, str(e)
    if max((arc_sweep_deg(pc) for pc in pieces), default=0.0) > 300.0:
        return None, "Bogen über 300°: Haken passen nicht zwischen Außenhaut und Knoten"
    pieces, seam = _seam_rotate(pieces, g, ctx.region, ctx.part_bounds)
    merged = merge_pieces(pieces)
    err = check_loop(merged, p.w, p.eps)
    if err:
        return None, err
    return (F, info, pieces, seam, merged), ""


def build_plan(ctx: IslandContext, vals: dict[str, Any]) -> IslandPlan:
    """Inselpfad der Fugenwand (siehe Modul-Docstring) oder Rückfall auf das Grundmuster.

    Reihenfolge der Versuche: gewünschte Felderzahl mit Zielradius, dann mit kleineren Radien
    (RADIUS_STEPS, bis w/2: nur M6-Warnungen), dann weniger Felder. Die Feldlänge ist die
    funktionale Größe (Fugenabstand), der Radius nur ein Druckziel."""
    p = ctx.params
    if not _is_rect(ctx.region):
        plan = shell_chain(ctx)
        plan.meta["fallback"] = "Querschnitt ist kein Rechteck: Grundmuster"
        return plan
    g0 = _Geo(ctx, vals)
    belt = bool(vals["belt"])
    target = float(vals["field_length_mm"])
    ang = float(vals["web_angle_deg"])
    angle_info: dict[str, Any] = {}
    if ang > 0:
        target, reached = field_for_angle(g0, belt, ang)
        angle_info = {"web_angle_target_deg": ang, "web_angle_reached_deg": round(reached, 1)}
    n_min = 2 if belt else 1
    fit = fit_to_length(g0.length, target, min_count=n_min)
    radii = sorted({max(g0.r * k, p.w / 2) for k in RADIUS_STEPS}, reverse=True)
    reason = ""
    for n in range(fit.count, n_min - 1, -1):
        for r in radii:
            g = _Geo(ctx, vals, r)
            res, why = _attempt(ctx, g, vals, n)
            if res is None:
                reason = reason or why
                continue
            return _finish(ctx, g, g0, fit, n, res, angle_info, reason)
    plan = shell_chain(ctx)
    plan.meta["fallback"] = f"Fugenwand nicht baubar: {reason}"
    return plan


def _finish(ctx, g, g0, fit, n, res, angle_info, reason) -> IslandPlan:  # noqa: ANN001
    p = ctx.params
    F, info, pieces, seam, merged = res
    segs = [Segment(k, 0 if k == "outfill" else p.shells, pts, False, LABELS[k]) for k, pts in merged]
    used = fit_to_length(g.length, F, min_count=n, max_count=n)
    legs = [pc for pc in pieces if pc.pulley is None and pc.kind == "web" and pc.length > 1.0]
    angles = [abs(math.degrees(math.atan2(*(pc.points[-1] - pc.points[0])[::-1]))) % 180 for pc in legs]
    meta = {
        **info,
        **angle_info,
        "fit": used.to_dict(),
        "fields_requested": fit.count,
        "field_length_mm": round(F, 3),
        "hook_radius_mm": round(g.r, 3),
        "contact_distance_mm": round(g.delta, 3),
        "joint_distance_mm": round(g.dj, 3),
        "web_angle_deg": sorted({round(min(a, 180 - a), 1) for a in angles}),
        "web_length_mm": sorted({round(pc.length, 1) for pc in legs}),
        "belt_length_mm": sorted(
            {round(pc.length, 1) for pc in pieces if pc.kind == "infill" and pc.pulley is None}
        ),
        **seam,
    }
    notes = []
    if n != fit.count:
        notes.append(f"{fit.count} Felder nicht baubar; {n} Felder")
    if g.r < g0.r - 1e-9:
        notes.append(f"Hakenradius {g0.r:g} mm passt nicht; {g.r:g} mm")
    if notes:
        meta["adjusted"] = "; ".join(notes) + (f" (Grund: {reason})" if reason else "")
    return IslandPlan(segs, _contacts(g, info, segs), meta)


@pattern(
    "fugenwand",
    role="full",
    label="Fugenwand (Sollbruchstellen)",
    params=PARAMS,
    description=(
        "Gerade Außenfelder mit stumpfen Fugen, V-Stege zu Knoten, wahlweise Doppelgurt oder "
        "Rautenkette; ein geschlossener Strang je Schicht, senkrechter Schichtwechsel im Wandinneren."
    ),
)
def build(ctx: IslandContext) -> IslandPlan:
    vals = {s.name: ctx.param(s.name) for s in PARAMS}
    return build_plan(ctx, vals)
