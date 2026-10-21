"""Fugenwand im Kopfmodul mit Abschrägung (Hilfsmodul, wird nicht als Familie geladen).

Problem (S6, docs/muster/S2-RAUTENKETTE.md): Am Wandkopf nimmt die Dicke ab einer Schicht je Schicht
um 10 mm ab (45°-Schräge, „Schrägseite“ S; die andere Seite G bleibt stehen). Die prismatische
Fugenwand teilte jede Schicht neu ein; ihre Raupen wanderten (M3-Überhang bis 4279 mm², M4 diagonal).

Lösung: Der ganze Teil wird aus seinem Vollquerschnitt geplant (`ctx.sections`), Raupen fallen nach
oben nur weg, und ab der ersten dünneren Schicht übernimmt die Abschrägungslösung der Familie
`topologie` (Fermat-Doppelring, der zu U-Formen abbaut). Die Vollschichten des Teils sind deren
Obermenge:

- **Schrägseite S:** Felder mit Fugen an den Fugenlagen des Vollquerschnitts (dieselben wie in den
  Modulen darunter), an jeder Fuge eine Raute (Haken, Steg, Spitze in Teilmitte, Spitze unten), deren
  untere Spitze die zweite Spur der Gegenseite berührt (Kontakt `shell`).
- **Gegenseite G:** zwei Spuren ohne Fuge (Spur 0 außen, Spur 1 innen), an den Stirnseiten Schenkel,
  eine Wende (Halbkreis r = w/2) verbindet Spur 0 und Spur 1 am rechten Stirnende. Das ist genau der
  U-Teil des Fermat-Doppelrings.

Ein Zug: Start in der Mitte des Eckbogens oben rechts, die Schrägseite entlang (−u), Ecke, linker
Schenkel hinab, Spur 0 entlang G, rechter Schenkel hinauf, Wende, Spur 1 zurück, linker Schenkel
von Spur 1 hinauf bis `v_end` (Ende im Wandinneren).

Warum die Gegenseite keine Fuge hat (Beleg in docs/muster/fugenwand.md, „Abschrägung“): Eine Fuge ist
eine Kerbe von der Außenfläche bis zum Kontakt der Haken. Eine Kerbe kann nach oben nie schließen
(jede Raupe über ihr hinge, M3). Die obersten Schichten (Dicke < 2·w) haben aber nur Platz für einen
Lauf entlang G, der als ein Strang (M1) über jede Fugenlage laufen müsste. Also gibt es in einem
Kopfmodul auf G keine Fuge, von Schicht 0 an. Die Raupen der Schrägseite (Felder, Haken, Rauten)
fallen in der ersten dünneren Schicht alle weg: Die Rauten hängen nur über die Felder von S am Zug,
und die Schräge versetzt die Außenfläche je Schicht um mehr als δ = 2 mm.

Schichten dünner als w (eine Raupe passt nicht in den Querschnitt, M5) bleiben leer; der Hinweis
steht im `meta` der obersten gedruckten Schicht.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import numpy as np
from shapely.geometry import box

from roboprint.patterns.families._fugenwand_geom import (
    Chain,
    GeometryError,
    Pulley,
    arc_between,
    arc_sweep_deg,
    tangent,
)
from roboprint.patterns.families._fugenwand_geom import Piece as PPiece
from roboprint.patterns.families._topologie_bahnen import (
    Frame,
    Piece,
    Turtle,
    fermat_rect,
    reverse_pieces,
)
from roboprint.patterns.families.topologie import (
    _bevel,
    _corner,
    _cut_end,
    _rects,
    _segments,
)
from roboprint.patterns.geometry import polygons
from roboprint.patterns.types import Contact, IslandPlan, PatternParams

#: Sicherheitszuschlag (mm) auf den Mindestabstand (1 − ε)·w beim Suchen von Wende und Strangende
CLEAR_MARGIN_MM = 1.0
#: Schrittweite (mm) der Suche nach Wendenhöhe und Strangende von Spur 1
SEARCH_STEP_MM = 2.5
#: Mindestdicke des Vollquerschnitts in w: zwei Spuren der Gegenseite, Raute und Feld der Schrägseite
MIN_THICKNESS_W = 4.0


def detect(sections: Mapping[int, Any]) -> tuple[Any, str, dict[int, float]] | None:
    """Abschrägung des ganzen Teils: (Vollrechteck, Seite, Dicke je Schicht) oder None.

    Wie `topologie` (eine Insel je Schicht, gleiche Länge, Dicke nimmt von einer Seite ab), aber
    leere Schichten oben (Schnitt über dem Teil) werden übergangen. Seite `top`: y_max weicht
    zurück (G = y_min), `bottom`: y_min weicht zurück."""
    sec = {L: g for L, g in sections.items() if g is not None and not g.is_empty}
    if len(sec) < 2:
        return None
    rects = _rects(sec)
    return None if rects is None else _bevel(rects)


def _frame(base: Any, side: str) -> Frame:
    """Kanonisch: u längs (ab x0), v quer ab der Gegenseite G (v = 0) zur Schrägseite S (v = T)."""
    return Frame(base.x0, base.y0, 1.0, 1.0) if side == "top" else Frame(base.x0, base.y1, 1.0, -1.0)


def _de(x: float) -> str:
    """Zahl mit einer Nachkommastelle, deutsches Komma (UI-Text)."""
    return f"{x:.1f}".replace(".", ",")


def _shell_of(kind: str, p: PatternParams) -> int:
    return {"outfill": 0, "outer": 0, "inner": 1}.get(kind, p.shells)


LABELS = {"outfill": "Außenhaut", "web": "Steg", "inner": "Spur 1", "outer": "Spur 0"}


def open_pieces(pulleys: list[Pulley], links: list[str], start: np.ndarray) -> list[PPiece]:
    """Offener Zug über die Kreise: Bogen auf dem ersten Kreis ab `start` (liegt auf ihm), dann
    Gerade, Bogen, …; der letzte „Kreis“ hat r = 0 (Endpunkt)."""
    n = len(pulleys)
    tans = [tangent(pulleys[i], pulleys[i + 1]) for i in range(n - 1)]
    out: list[PPiece] = []
    prev = np.asarray(start, float)
    for i, pu in enumerate(pulleys[:-1]):
        a, b = tans[i]
        if pu.r > 0:
            out.append(PPiece(pu.kind, arc_between(pu, prev, a), pu, pu.tag))
        out.append(PPiece(links[i], np.vstack([a, b]), None, "line"))
        prev = b
    return out


def check_open(pts: np.ndarray, w: float, eps: float) -> str | None:
    """Wie `fugenwand.check_loop`, aber für einen offenen Zug (kein Umlauf am Ende)."""
    from scipy.spatial import cKDTree
    from shapely.geometry import LineString

    from roboprint.patterns.geometry import densify

    if not LineString(pts).is_simple:
        return "Selbstschnitt"
    d = densify(pts, 2.0)
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(d, axis=0), axis=1))])
    pairs = cKDTree(d).query_pairs((1 - eps) * w + CLEAR_MARGIN_MM - 0.5, output_type="ndarray")
    if len(pairs):
        bad = np.abs(arc[pairs[:, 1]] - arc[pairs[:, 0]]) > 2 * w
        if np.any(bad):
            q = pairs[bad][0]
            return f"Stränge zu nah bei ({d[q[0]][0]:.0f}, {d[q[0]][1]:.0f})"
    return None


class KopfGeometry:
    """Vollschicht des Kopfmoduls im kanonischen Rechteck [0, W] × [0, T] (siehe Modul-Docstring)."""

    def __init__(
        self, W: float, T: float, p: PatternParams, vals: dict[str, Any], joints: list[float], half: float
    ):
        self.W, self.T, self.p, self.vals = W, T, p, vals
        self.joints, self.half = list(joints), half
        self.w = p.w
        self.rc = _corner(p)
        self.o0, self.o1 = p.w / 2.0, 1.5 * p.w

    def face(self, r: float) -> tuple[Chain, Any]:
        """Schrägseite (läuft −u, Haken nach unten). Gebaut als Vorderseite in v' = T − v mit
        `fugenwand.rhomb_face` und dann gespiegelt; die Rautenspitze berührt Spur 1 (v = 1,5·w)."""
        from roboprint.patterns.families.fugenwand import _Geo, rhomb_face

        g = _Geo(SimpleNamespace(region=box(0.0, 0.0, self.W, self.T), params=self.p), self.vals, r)
        g.yb = self.T - self.o1
        g.ym = 0.5 * (g.yf + g.yb)
        return rhomb_face(g, self.joints, self.half).mirrored_reversed(self.T), g

    def build(self, r: float, yu: float, v_end: float) -> tuple[list[PPiece], Any]:
        W, T, rc, o0, o1, w = self.W, self.T, self.rc, self.o0, self.o1, self.w
        face, g = self.face(r)
        tr = Pulley(W - o0 - rc, T - o0 - rc, rc, +1, "outfill", "corner")
        tl = Pulley(o0 + rc, T - o0 - rc, rc, +1, "outfill", "corner")
        bl = Pulley(o0 + rc, o0 + rc, rc, +1, "outfill", "corner")
        br = Pulley(W - o0 - rc, o0 + rc, rc, +1, "outfill", "corner")
        turn = Pulley(W - w, yu, w / 2.0, +1, "inner", "turn")
        br1 = Pulley(W - o1 - rc, o1 + rc, rc, -1, "inner", "corner")
        bl1 = Pulley(o1 + rc, o1 + rc, rc, -1, "inner", "corner")
        end = Pulley(o1, v_end, 0.0, -1, "inner", "end")
        ch = (
            Chain([tr], [])
            .extend(face, "outfill")
            .extend(Chain([tl, bl, br], ["outfill", "outfill"]), "outfill")
        )
        ch = ch.extend(Chain([turn, br1, bl1, end], ["inner", "inner", "inner"]), "outfill")
        start = tr.c + rc * np.array([math.cos(math.pi / 4), math.sin(math.pi / 4)])
        return open_pieces(ch.pulleys, ch.links, start), g

    def check(self, pieces: list[PPiece]) -> str | None:
        if max((arc_sweep_deg(pc) for pc in pieces), default=0.0) > 300.0:
            return "Bogen über 300°: Haken passen nicht zwischen Außenhaut und Spur 1"
        pts = np.vstack([pieces[0].points] + [pc.points[1:] for pc in pieces[1:]])
        return check_open(pts, self.w, self.p.eps)

    def solve(self, radii: list[float]) -> tuple[list[PPiece], Any, float, float, float, str]:
        """Größter Hakenradius, höchste Wende und längster Schenkel von Spur 1, die passen.
        Rückgabe (Stücke, Geo, r, yu, v_end, Grund des ersten Fehlschlags)."""
        lo = self.o1 + self.rc + 0.5  # Wende und Strangende auf geraden Schenkeln
        gap = (1 - self.p.eps) * self.w + CLEAR_MARGIN_MM
        # Startwerte der Suche: Wende unter dem Eckbogen oben rechts, Strangende unter dem oben links
        yu_max = max(lo, self.T - self.o0 - self.rc - gap - self.w)
        ve_max = max(lo, self.T - self.o0 - 2.0 * self.rc - gap)
        reason = ""
        for r in radii:
            try:
                ve = self._search(r, ve_max, lo, lambda v, r=r: (r, lo, v))
                yu = self._search(r, yu_max, lo, lambda y, r=r, ve=ve: (r, y, ve))
            except GeometryError as e:
                reason = reason or str(e)
                continue
            pieces, g = self.build(r, yu, ve)
            why = self.check(pieces)
            if why is None:
                return pieces, g, r, yu, ve, reason
            reason = reason or why
        raise GeometryError(reason or "kein Hakenradius passt")

    def _search(self, r: float, hi: float, lo: float, args) -> float:  # noqa: ANN001
        v = hi
        last = ""
        while v >= lo - 1e-9:
            try:
                pieces, _ = self.build(*args(v))
                why = self.check(pieces)
            except GeometryError as e:
                why = str(e)
            if why is None:
                return v
            last = why
            v -= SEARCH_STEP_MM
        raise GeometryError(last or "keine Lage gefunden")


def _to_pieces(pp: list[PPiece], p: PatternParams) -> list[Piece]:
    out = []
    for pc in pp:
        if len(pc.points) < 2 or np.linalg.norm(np.diff(pc.points, axis=0), axis=1).sum() < 1e-9:
            continue
        out.append(Piece(pc.kind, _shell_of(pc.kind, p), pc.points, LABELS.get(pc.kind, "")))
    return out


def bevel_layer(
    W: float, T: float, t: float, w: float, rc: float, eps: float, yu_max: float, v_end: float, delta: float
) -> list[Piece]:
    """Schrägschicht (Dicke t < T) im kanonischen Rechteck: die U-Formen des Fermat-Doppelrings
    (`_topologie_bahnen.fermat_rect`, Fall „oberer Lauf passt nicht“), aber Spur 1 immer als U ohne
    oberen Lauf und mit dem linken Schenkel höchstens bis `v_end`: In der Vollschicht darunter liegen
    dort die Rauten der Schrägseite. Stufen: Doppel-U mit Wende (Wende unter t + 1 − w), einfaches U
    (Spur 0), Lauf an der Gegenseite, nichts (t < w − 1)."""
    if t + 1.0 >= T:
        raise ValueError("bevel_layer nur für Schrägschichten")
    o0, o1 = w / 2.0, 1.5 * w
    xa0, xb0, ya0 = o0, W - o0, o0
    xa1, xb1, ya1 = o1, W - o1, o1
    yu = min(yu_max, t + 1.0 - w)
    top0 = min(T - o0 - rc, t + 1.0 - w / 2.0)
    if yu >= max(ya1 + rc, ya0 + rc) and xb1 - xa1 >= 2 * rc:
        tt = Turtle((xa0, top0), (0.0, -1.0))
        tt.to(1, ya0 + rc).turn(rc, 90).to(0, xb0 - rc).turn(rc, 90).to(1, yu)
        out = [Piece("outer", 0, tt.cut(), "Spur 0")]
        tt.turn(w / 2.0, 180)
        out.append(Piece("inner", 1, tt.cut(), "Wende"))
        top1 = max(ya1 + rc, min(T - o1 - rc, t + 1.0 - w / 2.0, v_end))
        tt.to(1, ya1 + rc).turn(rc, -90).to(0, xa1 + rc).turn(rc, -90).to(1, top1)
        out.append(Piece("inner", 1, tt.cut(), "Spur 1"))
        return out
    return fermat_rect(W, T, t, w, rc, eps, -math.inf, delta)


def _monotone_right_leg(
    raw: dict[int, list[Piece]],
    layers: list[int],
    W: float,
    o0: float,
    rc: float,
    yu_max: float,
    t: Mapping[int, float],
    w: float,
) -> None:
    """Rechter Schenkel der einfachen U-Form (Spur 1 ist entfallen) höchstens so hoch wie Wende bzw.
    Schenkel der Schicht darunter: Sein Ende muss auf deren Bahn liegen, damit `_align_bevel_ends`
    die tiefere Schicht dort kürzen kann (senkrechter Wechsel, M4). `fermat_rect` lässt ihn um
    `turn_cap_reach` über die Wende ragen (M3 erlaubt das); bei flachen Schritten (60°-Schräge,
    5,8 mm je Schicht) läge sein Ende dann auf dem Wendenbogen statt auf dem Schenkel."""
    cap = None
    for L in layers:
        pcs = raw[L]
        if len(pcs) >= 3:
            cap = min(yu_max, t[L] + 1.0 - w)
            continue
        if len(pcs) != 1 or cap is None:
            cap = None
            continue
        q = pcs[0].pts
        if abs(q[-1, 0] - (W - o0)) > 1e-6:  # Lauf ohne Schenkel
            cap = None
            continue
        lim = max(cap, o0 + rc)
        if q[-1, 1] > lim + 1e-9:
            # vom Ende her: alle Punkte des rechten Schenkels oberhalb von lim fallen weg
            high = (np.abs(q[:, 0] - (W - o0)) < 1e-6) & (q[:, 1] > lim + 1e-9)
            k = len(q)
            while k > 0 and high[k - 1]:
                k -= 1
            q = np.vstack([q[:k], [[W - o0, lim]]])
            raw[L] = [Piece(pcs[0].kind, pcs[0].shell, q, pcs[0].label)]
        cap = float(raw[L][0].pts[-1, 1])


def align_ends(layers: dict[int, list[Piece]], t: Mapping[int, float], order: str) -> dict[int, list[Piece]]:
    """Senkrechter Schichtwechsel (M4, `alternate`) wie `topologie._align_bevel_ends`: Von oben nach
    unten wird Schicht L an der mit L + 1 gemeinsamen Seite (L gerade: Ende, ungerade: Anfang) bis
    auf das Strangende von L + 1 gekürzt; das nimmt nur Raupe weg, über der nichts liegt (M3).
    Zusätzlich: Hat L + 1 denselben Querschnitt (Stufe in der Schräge), wird L auch an der anderen
    Seite wie L + 1 gekürzt, damit L + 1 vollständig bleibt (Orakel M3: bei gleichem Querschnitt
    auch L in L + 1 ⊕ δ)."""
    if order != "alternate":
        return layers
    out = dict(layers)

    def cut(pcs: list[Piece], point: np.ndarray, at_end: bool) -> list[Piece] | None:
        if at_end:
            return _cut_end(pcs, point)
        rev = _cut_end(reverse_pieces(pcs), point)
        return None if rev is None else reverse_pieces(rev)

    for L in sorted(out, reverse=True):
        nxt, cur = out.get(L + 1), out[L]
        if not nxt or not cur:
            continue
        even = L % 2 == 0
        new = cut(cur, nxt[-1].pts[-1] if even else nxt[0].pts[0], even)
        if new:
            cur = new
        if abs(t[L] - t.get(L + 1, -1.0)) < 1e-6:
            new = cut(cur, nxt[0].pts[0] if even else nxt[-1].pts[-1], not even)
            if new:
                cur = new
        out[L] = cur
    return out


def _contacts(kg: KopfGeometry, g: Any, frame: Frame, segs: list[Any]) -> list[Contact]:
    """Deklarierte Kontakte der Vollschicht: Fugen und Rautenspitzen an Spur 1 (kanonisch → P)."""
    T = kg.T
    out = []
    if g.dj <= g.w:
        out += [("joint", (X, T - (g.yf + g.r + g.kj / 2))) for X in kg.joints]
    out += [("shell", (X, T - (g.yb - g.delta / 2))) for X in kg.joints]
    res = []
    for kind, at in out:
        q = frame.apply(np.array([at]))[0]
        dist = [float(np.min(np.linalg.norm(s.points - q, axis=1))) for s in segs]
        i, j = sorted(np.argsort(dist)[:2].tolist()) if len(segs) > 1 else (0, 0)
        res.append(
            Contact(kind, (round(float(q[0]), 3), round(float(q[1]), 3)), 0.0, (int(i), int(j)), g.delta)
        )
    return res


def plan_part(
    sections: Mapping[int, Any],
    p: PatternParams,
    vals: dict[str, Any],
    bevel: tuple[Any, str, dict[int, float]],
    full_meta: dict[str, Any],
) -> tuple[dict[int, IslandPlan], dict[str, Any]]:
    """Schichtpfade (Insel 0) des ganzen Kopfmoduls und Kennzahlen; GeometryError, wenn die
    Vollschicht nicht baubar ist (`_plan_or_fallback` versucht es dann ohne Fugen bzw. mit
    `topologie`).

    `full_meta`: `meta` der prismatischen Fugenwand im Vollquerschnitt (Einteilung, Fugenlagen,
    Hakenradius), damit die Fugen der Schrägseite in denselben Lagen liegen wie in den Modulen
    darunter."""
    from roboprint.patterns.families.fugenwand import RADIUS_STEPS

    base, side, t = bevel
    w = p.w
    W, T = base.width, base.y1 - base.y0
    frame = _frame(base, side)
    F = float(full_meta["field_length_mm"])
    key = "joints_back_x" if side == "top" else "joints_front_x"
    joints = sorted(float(x) - base.x0 for x in full_meta.get(key, []))
    r0 = float(full_meta["hook_radius_mm"])
    radii = sorted({max(r0 * k, w / 2.0) for k in RADIUS_STEPS}, reverse=True)
    kg = KopfGeometry(W, T, p, vals, joints, F / 4.0)
    pp, g, r, yu, v_end, reason = kg.solve(radii)
    full = _to_pieces(pp, p)
    layers = sorted(t)
    full_layers = [L for L in layers if t[L] + 1.0 >= T]
    raw: dict[int, list[Piece]] = {}
    for L in layers:
        if L in full_layers:
            raw[L] = full
        else:
            raw[L] = bevel_layer(W, T, t[L], w, kg.rc, p.eps, yu, v_end, p.delta_mm)
    _monotone_right_leg(raw, layers, W, kg.o0, kg.rc, yu, t, w)
    # M4 (alternate): Am Übergang letzte Vollschicht → erste Schrägschicht muss das gemeinsame Ende
    # das Ende von Spur 1 sein (es bleibt stehen); die Schrägseite liegt am anderen Ende. Ist die
    # letzte Vollschicht ungerade, wird die Bahn aller Schichten umgedreht.
    flip = bool(full_layers) and p.layer_order == "alternate" and max(full_layers) % 2 == 1
    if flip:
        raw = {L: reverse_pieces(v) for L, v in raw.items()}
    aligned = align_ends(raw, t, p.layer_order)
    thin = [L for L in layers if not aligned.get(L)]
    printed = [L for L in layers if aligned.get(L)]
    info = {
        "variant": "kopf",
        "side": side,
        "full_thickness_mm": round(T, 2),
        "joints_x": [round(base.x0 + x, 3) for x in joints],
        "field_length_mm": round(F, 3),
        "hook_radius_mm": round(r, 3),
        "turn_v_mm": round(yu, 2),
        "spur1_end_v_mm": round(v_end, 2),
        "full_layers": [min(full_layers), max(full_layers)] if full_layers else [],
        "flipped": flip,
    }
    if r < r0 - 1e-9:
        info["adjusted"] = f"Hakenradius {r0:g} mm passt im Kopfmodul nicht; {r:g} mm" + (
            f" (Grund: {reason})" if reason else ""
        )
    out: dict[int, IslandPlan] = {}
    cache: dict[tuple, IslandPlan] = {}
    side_name = "y+" if side == "top" else "y−"
    for L in printed:
        pieces = aligned[L]
        zone = "voll" if L in full_layers else "schraege"
        ck = (
            zone,
            round(t[L], 3),
            tuple(round(float(v), 3) for v in (*pieces[0].pts[0], *pieces[-1].pts[-1])),
        )
        if ck not in cache:
            segs = _segments(pieces, frame, p)
            meta: dict[str, Any] = {
                **info,
                "zone": zone,
                "thickness_mm": round(t[L], 2),
                "seam": [round(float(v), 3) for v in segs[0].start],
            }
            if zone == "voll":
                meta["note"] = (
                    f"Kopfmodul (Abschrägung an Seite {side_name}): Fugen und Rauten nur an der "
                    "Schrägseite, Gegenseite zwei Spuren ohne Fuge (eine Kerbe kann nach oben nicht "
                    "schließen, die obersten Schichten brauchen dort einen durchgehenden Lauf)"
                )
                contacts = _contacts(kg, g, frame, segs)
            else:
                meta["note"] = (
                    "Abschrägung: Raupen der Schrägseite entfallen, Doppelring der Gegenseite baut zu "
                    "U-Formen ab (wie Muster topologie)"
                )
                contacts = []
            cache[ck] = IslandPlan(segs, contacts, meta)
        out[L] = cache[ck]
    if thin and printed:
        top = max(printed)
        lo_t, hi_t = min(t[L] for L in thin), max(t[L] for L in thin)
        m = dict(out[top].meta)
        m["thin_layers"] = thin
        m["thin_note"] = (
            f"Schichten {min(thin)}–{max(thin)} ohne Strang: Dicke {_de(hi_t)}…{_de(lo_t)} mm, dünner als "
            f"eine Raupe (w = {w:g} mm passt nicht in den Querschnitt ⊕ 1 mm, M5); darunter liegt "
            "der Lauf der Gegenseite"
        )
        m["note"] = m["thin_note"]
        out[top] = IslandPlan(out[top].segments, out[top].contacts, m)
    info["thin_layers"] = thin
    return out, info


#: Teilpläne (Abschrägung) je Fingerabdruck; `_LAST` hält die Querschnitte des letzten Aufrufs fest
#: (Identität statt Fingerabdruck: `build` wird je Schicht mit demselben `sections` gerufen). Die
#: API plant in einem Threadpool: Zugriff nur unter `_LOCK`.
_PARTS: OrderedDict[tuple, Any] = OrderedDict()
_LAST: list[Any] = [None]
_LOCK = threading.Lock()


def _fingerprint(sections: Mapping[int, Any], p: PatternParams) -> tuple:
    rows = tuple(
        (L, tuple(round(b, 3) for b in g.bounds), round(g.area, 2))
        for L, g in sorted(sections.items())
        if g is not None and not g.is_empty
    )
    return (rows, tuple(sorted((k, repr(v)) for k, v in p.to_dict().items())))


def part_for(ctx: Any, vals: dict[str, Any], full_plan: Callable[[Any], IslandPlan]) -> Any:
    """Plan des ganzen Teils, wenn es eine Abschrägung trägt, sonst None.

    Rückgabe: `(plans je Schicht, info)` oder `("fallback", Grund)`, wenn die Fugenwand im
    Kopfmodul nicht baubar ist. `full_plan(region)` liefert den prismatischen Inselpfad des
    Vollquerschnitts (Einteilung wie in den Modulen darunter)."""
    refs = tuple(ctx.sections.values())
    with _LOCK:
        last = _LAST[0]
        if (
            last is not None
            and len(last[0]) == len(refs)
            and all(a is b for a, b in zip(last[0], refs, strict=True))
            and last[1] == ctx.params
        ):
            return last[2]
        res = None
        bev = detect(ctx.sections)
        if bev is not None:
            key = _fingerprint(ctx.sections, ctx.params)
            if key in _PARTS:
                _PARTS.move_to_end(key)
                res = _PARTS[key]
            else:
                res = _plan_or_fallback(ctx, vals, bev, full_plan)
                _PARTS[key] = res
                while len(_PARTS) > 8:
                    _PARTS.popitem(last=False)
        _LAST[0] = (refs, ctx.params, res)
        return res


def build_island(ctx: Any, vals: dict[str, Any], full_plan: Callable[[Any], IslandPlan]) -> IslandPlan | None:
    """Inselpfad der Schicht `ctx.layer` eines Kopfmoduls; None, wenn das Teil keine Abschrägung
    trägt (dann gilt die prismatische Fugenwand). Schichten dünner als eine Raupe: leerer Plan.
    Rückfall: Abschrägungslösung von `topologie` mit `pattern_fallback`."""
    from roboprint.patterns import registry

    part = part_for(ctx, vals, full_plan)
    if part is None:
        return None
    if part[0] == "fallback":
        topo = registry.get("topologie")
        res = topo.build(replace(ctx, spec=topo.params))
        res = res if isinstance(res, IslandPlan) else IslandPlan(list(res))
        meta = {**res.meta, "pattern_fallback": f"{part[1]}: Abschrägungslösung von topologie"}
        return replace(res, segments=list(res.segments), contacts=list(res.contacts), meta=meta)
    plans, _info = part
    res = plans.get(ctx.layer)
    if res is None:
        return IslandPlan([], [], {"variant": "kopf", "empty": "dünner als eine Raupe"})
    return replace(res, segments=list(res.segments), contacts=list(res.contacts), meta=dict(res.meta))


def _plan_or_fallback(
    ctx: Any, vals: dict[str, Any], bev: Any, full_plan: Callable[[Any], IslandPlan]
) -> Any:
    """Kopfmodul mit Fugen der Schrägseite; geht das nicht, ohne Fugen (Schrägseite als glatter Lauf,
    sonst wie oben); geht auch das nicht: Rückfall (Aufrufer nimmt `topologie`)."""
    base = bev[0]
    first = min(L for L, g in ctx.sections.items() if g is not None and not g.is_empty)
    full = full_plan(polygons(ctx.sections[first])[0])
    if base.y1 - base.y0 < MIN_THICKNESS_W * ctx.params.w:
        return ("fallback", f"Wand {base.y1 - base.y0:.0f} mm zu dünn für Schrägseite und Doppelring")
    reasons = []
    if "pattern_fallback" in full.meta:
        reasons.append(f"Vollquerschnitt ohne Fugenwand ({full.meta['pattern_fallback']})")
    else:
        try:
            return plan_part(ctx.sections, ctx.params, vals, bev, full.meta)
        except (GeometryError, ValueError) as e:
            reasons.append(f"Fugen an der Schrägseite nicht baubar ({e})")
    plain = {
        "field_length_mm": base.width,
        "hook_radius_mm": ctx.params.w,
        "joints_back_x": [],
        "joints_front_x": [],
    }
    try:
        plans, info = plan_part(ctx.sections, ctx.params, vals, bev, plain)
    except (GeometryError, ValueError) as e:
        return ("fallback", "; ".join([*reasons, f"Kopfmodul nicht baubar ({e})"]))
    note = "; ".join(reasons) + ": Schrägseite ohne Fuge"
    info["adjusted"] = note
    for plan in plans.values():
        plan.meta["adjusted"] = note
    return plans, info


__all__ = ["KopfGeometry", "build_island", "check_open", "detect", "open_pieces", "part_for", "plan_part"]
