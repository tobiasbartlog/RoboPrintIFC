"""Fermat-Spirale für kleine Inseln (Familie „Mehrfach“, Rolle `full`).

Vorbild: Connected Fermat Spirals (Zhao et al. 2016, SIGGRAPH; recherche.md §4.1). Eine Fermat-
Spirale füllt ein Gebiet mit **einem** Strang aus zwei verschränkten Armen: einwärts auf jedem
zweiten Ring, innen eine Kehre, auswärts auf den Ringen dazwischen. Start und Ende liegen am Rand
nebeneinander. Bei Zhao werden die Iso-Konturen an einer Bruchstelle aufgeschnitten und so neu
verbunden; genau das macht dieses Modul mit den Ringen der Insel.

Ringe. Ring i ist der Rand von Insel ⊖ (i + 0,5)·w (gerundet wie die Schalen, Eckradius
`corner_radius`), solange sich seine gegenüberliegenden Seiten nicht näher als (1 − ε)·w kommen.
Die Ringe liegen im Abstand w, berühren sich also (Kontakt, kein Doppelmaterial). Was innen übrig
bleibt (< w breit), bleibt als Zelle offen. Gebaut wird für **2 oder 3 Ringe**, also Inseln mit
einer Restbreite unter etwa 3·w nach zwei Schalen (z. B. Pfeiler 300 × 200: Ringe bei 15, 45 und
75 mm, Zelle 20 mm). Breitere Inseln bekommen das Grundmuster `shell_chain` (meta
`fermat_skipped`): Ab 4 Ringen müssten sich zwei Ringwechsel durch dieselben Lücken schieben, die
Lücken würden ≥ 5·w lang, und die Welle füllt solche Inseln ohnehin besser (recherche.md §7).

Bruchstelle. Auf dem längsten geraden Stück des innersten Rings (bevorzugt eines, dessen Außenring
keine Außen- oder Stoßfläche berührt, sonst nahe `seam_corner`). Dort sind alle Ringe parallel;
lokale Koordinaten u entlang der Laufrichtung (gegen den Uhrzeigersinn), v nach innen, Ring i bei
v = i·w.

Drei Ringe (Pfeiler):
1. Ring 0 einwärts: Start bei u_s, einmal herum bis u = −a.
2. Ringwechsel 0 → 2: S-Kurve (Biarc) von Ring 0 bei −a auf Ring 2 bei +a, quer durch die Lücke
   in Ring 1. Bei a = w sind das zwei Viertelbögen mit Radius `link_radius_mm` = w.
3. Ring 2 einwärts: einmal herum bis u_h.
4. Kehre: Halbkreis mit Radius w/2 von Ring 2 auf Ring 1 (Drehsinn kehrt um, wie in der Mitte
   jeder Fermat-Spirale).
5. Ring 1 auswärts (im Uhrzeigersinn) einmal herum bis u_e: Ende neben dem Start, eine Raupe
   weiter innen.
Zwei Ringe: Ring 0 einwärts, Kehre bei u = 0 auf Ring 1, Ring 1 auswärts.

u_s, u_h und u_e werden in 1-mm-Schritten gesucht: der kleinste Abstand zum Ringwechsel bzw. zur
Kehre, bei dem jeder Punkt mit Bogenlängenabstand > 2·w mindestens (1 − ε)·w + 0,3 mm entfernt
bleibt (M2). Das Ergebnis wird mit `metrics.measure_path` geprüft; bei einem `error` gilt das
Grundmuster.

Grenzen (Zahlen bei w = 30): Die Kehre hat Radius w/2 = 15 mm (M6 hart erfüllt, Ziel w verfehlt:
Warnung). Ring 0 hat an der Bruchstelle eine Lücke von a + u_s (Pfeiler: ≈ 47 mm Mittellinie,
außen eine Kerbe von ≈ 20 mm Breite), genau wie die Naht des Grundmusters; die Naht liegt am Rand
(Start auf Ring 0), Zhao legt sie ebenso dorthin. Mit `alternate` druckt die nächste Schicht dieselbe
Bahn rückwärts: Ende L = Anfang L + 1, der Schichtwechsel ist ein reiner Z-Hub (M4).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from roboprint.patterns.geometry import (
    Loop,
    arc_points,
    biarc,
    densify,
    offset_region,
    offset_ring,
    resample_curve,
)
from roboprint.patterns.layout import face_clearance
from roboprint.patterns.metrics import RADIUS_TOL, measure_path
from roboprint.patterns.shells import shell_chain
from roboprint.patterns.types import IslandContext, IslandPlan, LayerPath, ParamSpec, Segment

#: Reserve über (1 − ε)·w bei der Suche (Sehnenfehler der späteren Abtastung)
CLEAR_MARGIN_MM = 1.0
#: Abtastung der Prüfung (mm)
CHECK_MM = 2.0
#: Fein-Abtastung der Bögen (Sehnenfehler)
FINE_TOL_MM = 0.05
#: Ringzahl, für die die Fermat-Spirale gebaut wird
MIN_ROWS, MAX_ROWS = 2, 3

PARAMS = (
    ParamSpec(
        "link_radius_mm",
        "Radius Ringwechsel",
        30.0,
        "mm",
        15.0,
        60.0,
        1.0,
        help="Radius der S-Kurve von Ring 0 auf Ring 2 (größer = sanfter, aber längere Lücke)",
    ),
)


# --------------------------------------------------------------------------- Ringe


def fermat_rows(region: Any, w: float, corner_radius: float, eps: float) -> list[Loop] | str:
    """Ringe der Insel im Abstand w, oder eine Begründung, warum es keine einfachen Ringe gibt."""
    rows: list[Loop] = []
    for i in range(MAX_ROWS + 2):
        off = (i + 0.5) * w
        rings = offset_ring(region, off, corner_radius)
        ext = [r for kd, r in rings if kd == "exterior"]
        if not ext:
            break
        if len(ext) > 1 or any(kd == "hole" for kd, _ in rings):
            return f"Ring {i} zerfällt oder hat Löcher (keine einfache Insel)"
        # Ring braucht innen Platz für Eckbögen mit Radius ≥ w/2 (M6 hart): Seine gegenüberliegenden
        # Seiten liegen dann ≥ w auseinander (Kontakt, kein Doppelmaterial)
        if offset_region(region, off + 0.5 * w + 0.5).is_empty:
            break
        rows.append(Loop(ext[0]))
    return rows


def _break_point(rows: list[Loop], ctx: IslandContext) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Bruchstelle M auf dem innersten Ring und Laufrichtung t dort (siehe Modul-Docstring)."""
    inner = rows[-1].pts
    seg = np.diff(inner, axis=0)
    lens = np.linalg.norm(seg, axis=1)
    p = ctx.params
    x0, y0, x1, y1 = ctx.part_bounds
    corner = np.array([x0 if p.seam_corner[0] < 0 else x1, y0 if p.seam_corner[1] < 0 else y1])
    best, info = None, {}
    for k in np.flatnonzero(lens >= 0.8 * lens.max()):
        mid = inner[k] + 0.5 * seg[k]
        t = seg[k] / lens[k]
        outer_pt = rows[0].point(rows[0].project(mid))
        free = float(face_clearance(outer_pt[None, :], ctx.region, ctx.part_bounds, p.w)[0]) > 0.0
        key = (free, round(float(lens[k]), 0), -float(np.linalg.norm(mid - corner)))
        if best is None or key > best[0]:
            best = (key, mid, t)
            info = {"break_on_face": not free, "break_run_mm": round(float(lens[k]), 2)}
    assert best is not None
    return best[1], best[2], info


# --------------------------------------------------------------------------- Prüfung


def _clear(curve: np.ndarray, thresh: float, exempt: float, near: np.ndarray, reach: float) -> bool:
    """M2 an der Bruchstelle: Punkte im Umkreis `reach` um `near` (fern davon laufen nur Ringe im
    Abstand w nebeneinander; das prüft danach `measure_path`)."""
    dense = densify(curve, CHECK_MM)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
    keep = np.linalg.norm(dense - near, axis=1) <= reach
    pairs = cKDTree(dense[keep]).query_pairs(thresh, output_type="ndarray")
    s = s[keep]
    return not (len(pairs) and np.any(np.abs(s[pairs[:, 0]] - s[pairs[:, 1]]) > exempt))


def _sub(loop: Loop, s0: float, s1: float) -> np.ndarray:
    """Wie `Loop.sub`, aber vektorisiert (die Suche ruft es einige hundert Mal)."""
    L = loop.length
    s0 %= L
    e = s1 % L
    if e <= s0 + 1e-9:
        e += L
    base = loop.cum[:-1]
    inner = np.concatenate([base, base + L, base + 2 * L])
    inner = inner[(inner > s0 + 1e-9) & (inner < e - 1e-9)]
    s = np.concatenate([[s0], inner, [e]]) % L
    k = np.clip(np.searchsorted(loop.cum, s, side="right") - 1, 0, len(loop.pts) - 2)
    seg = loop.cum[k + 1] - loop.cum[k]
    t = np.where(seg > 0, (s - loop.cum[k]) / np.where(seg > 0, seg, 1.0), 0.0)
    return loop.pts[k] + t[:, None] * (loop.pts[k + 1] - loop.pts[k])


class _Layout:
    """Ringe, Bruchstelle und lokale Koordinaten (u entlang, v nach innen)."""

    def __init__(self, rows: list[Loop], m: np.ndarray, t: np.ndarray, w: float):
        self.rows, self.t, self.w = rows, t, w
        self.n = np.array([-t[1], t[0]])
        self.b = [lp.project(m) for lp in rows]
        self.o = rows[0].point(self.b[0])
        self.v = [float((lp.point(b) - self.o) @ self.n) for lp, b in zip(rows, self.b, strict=True)]

    def pt(self, i: int, u: float) -> np.ndarray:
        return self.rows[i].point(self.b[i] + u)

    def fwd(self, i: int, u0: float, u1: float) -> np.ndarray:
        """Ring i vorwärts von u0 bis u1 (über den Ringanfang, also fast ein Umlauf)."""
        return _sub(self.rows[i], self.b[i] + u0, self.b[i] + u1)

    def link(self, i: int, j: int, a: float) -> tuple[np.ndarray, float] | None:
        """S-Kurve von Ring i bei −a auf Ring j bei +a (beide vorwärts)."""
        return biarc(self.pt(i, -a), self.t, self.pt(j, a), self.t, FINE_TOL_MM, 1.0)

    def hairpin(self, i: int, j: int, u: float) -> tuple[np.ndarray, float]:
        """Halbkreis von Ring i (vorwärts) bei u auf Ring j (rückwärts) bei u."""
        a, b = self.pt(i, u), self.pt(j, u)
        ctr, r = 0.5 * (a + b), 0.5 * float(np.linalg.norm(b - a))
        va = a - ctr
        # Bogen über die Vorwärtsseite (+t): Drehsinn so, dass die Anfangstangente +t ist
        sweep = math.pi if float(va[0] * self.t[1] - va[1] * self.t[0]) > 0 else -math.pi
        pts = arc_points(ctr, r, math.atan2(va[1], va[0]), sweep, FINE_TOL_MM, 1.0)
        pts[0], pts[-1] = a, b
        return pts, r


def _assemble(lay: _Layout, n: int, a: float, u_s: float, u_h: float, u_e: float | None):
    """Stücke der Bahn (Ringwechsel und Kehre an die folgenden Ringe gehängt). u_e = None:
    Ring 1 nur 2·w weit (für die Suche)."""
    w = lay.w
    if n == 3:
        lk = lay.link(0, 2, a)
        if lk is None:
            return None
        link, r_link = lk
        r0 = lay.fwd(0, u_s, -a)
        r2 = np.vstack([link, lay.fwd(2, a, u_h)[1:]])
        hp, r_hp = lay.hairpin(2, 1, u_h)
        tail = lay.fwd(1, u_e, u_h)[::-1] if u_e is not None else lay.fwd(1, u_h - 2 * w, u_h)[::-1]
        r1 = np.vstack([hp, tail[1:]])
        return [(0, r0), (2, r2), (1, r1)], r_link, r_hp
    r0 = lay.fwd(0, u_s, u_h)
    hp, r_hp = lay.hairpin(0, 1, u_h)
    tail = lay.fwd(1, u_e, u_h)[::-1] if u_e is not None else lay.fwd(1, u_h - 2 * w, u_h)[::-1]
    return [(0, r0), (1, np.vstack([hp, tail[1:]]))], math.inf, r_hp


def _search(lay: _Layout, n: int, a: float, thresh: float, exempt: float, r_min: float):
    w = lay.w

    def ok(u_s: float, u_h: float, u_e: float | None) -> Any:
        res = _assemble(lay, n, a, u_s, u_h, u_e)
        if res is None or min(res[1], res[2]) < r_min:
            return None
        curve = np.vstack([res[0][0][1]] + [pc[1:] for _, pc in res[0][1:]])
        return res if _clear(curve, thresh, exempt, lay.o, 8.0 * w) else None

    if n == 3:
        # Kehre links vom Ringwechsel (u_h < 0), so nah wie möglich
        u_h = next((float(u) for u in np.arange(-a, -a - 5 * w, -1.0) if ok(a + 2 * w, float(u), None)), None)
        if u_h is None:
            return None
        lo = -a
    else:
        u_h, lo = 0.0, 0.0
    u_s = next((float(u) for u in np.arange(max(lo, 0.0), lo + 4 * w, 1.0) if ok(float(u), u_h, None)), None)
    if u_s is None:
        return None
    for u_e in np.arange(max(lo, 0.0), lo + 4 * w, 1.0):
        res = ok(u_s, u_h, float(u_e))
        if res is not None:
            return res, {"u_start": u_s, "u_turn": u_h, "u_end": float(u_e), "link_half": a}
    return None


# --------------------------------------------------------------------------- Aufbau


def _fallback(ctx: IslandContext, reason: str, extra: dict[str, Any] | None = None) -> IslandPlan:
    plan = shell_chain(ctx)
    plan.meta.update({"fermat_skipped": reason, **(extra or {})})
    return plan


def build(ctx: IslandContext) -> IslandPlan:
    p = ctx.params
    w = p.w
    rows = fermat_rows(ctx.region, w, p.corner_radius, p.eps)
    if isinstance(rows, str):
        return _fallback(ctx, rows)
    n = len(rows)
    if n == 1:
        # Ein Ring: geschlossener Einzelring (Umkehrung je Schicht = senkrechter Wechsel). Nicht
        # shell_chain: Das bricht bei Inseln < 4·w mit zwei Schalen ab (Einwand, Familie Topologie).
        m, _, info = _break_point(rows, ctx)
        lp = rows[0]
        t0 = lp.project(m)
        ring = resample_curve(lp.sub(t0, t0), p.step_mm, p.chord_tol_mm, closed=True)
        return IslandPlan(
            [Segment("outer", 0, ring, closed=True, label="Ring 0")],
            meta={"rows": 1, "fermat_skipped": "1 Ring: zu schmal für zwei Arme, Einzelring", **info},
        )
    if not MIN_ROWS <= n <= MAX_ROWS:
        why = (
            f"{n} Ringe: Insel zu breit für die Fermat-Spirale (gebaut für {MIN_ROWS}–{MAX_ROWS} Ringe, "
            f"Restbreite nach 2 Schalen < 3·w); Welle empfohlen"
            if n > MAX_ROWS
            else "kein Ring: Insel schmaler als w"
        )
        return _fallback(ctx, why, {"rows": n})
    # Drei Ringe; findet sich an der Bruchstelle keine Anordnung (innerster Ring zu kurz, z. B.
    # Pfeiler 200 × 200: Ring 2 ist 50 × 50), zwei Ringe mit größerer Zelle in der Mitte
    reasons: list[str] = []
    for k in range(n, MIN_ROWS - 1, -1):
        res = _attempt(ctx, rows[:k])
        if isinstance(res, IslandPlan):
            if k < n:
                res.meta["rows_dropped"] = n - k
            return res
        reasons.append(f"{k} Ringe: {res}")
    return _fallback(ctx, "; ".join(reasons), {"rows": n})


def _attempt(ctx: IslandContext, rows: list[Loop]) -> IslandPlan | str:
    """Fermat-Bahn über genau diese Ringe, oder die Begründung, warum es nicht geht."""
    p = ctx.params
    w = p.w
    n = len(rows)
    m, t, info = _break_point(rows, ctx)
    lay = _Layout(rows, m, t, w)
    thresh = (1.0 - p.eps) * w + CLEAR_MARGIN_MM
    r_min = (1.0 - RADIUS_TOL) * w / 2.0 + 0.2
    R = float(ctx.param("link_radius_mm"))
    # Längsversatz der S-Kurve zwischen parallelen Ringen im Abstand 2·w mit Radius R: 2·sqrt(R² − (R − w)²)
    a0 = math.sqrt(max(R * R - (R - w) ** 2, 0.0)) if R > w / 2 else w / 2
    found = None
    for a in (a0, a0 + 0.25 * w, a0 + 0.5 * w) if n == 3 else (0.0,):
        found = _search(lay, n, a, thresh, 2.0 * w, r_min)
        if found is not None:
            break
    if found is None:
        return "keine kreuzungsfreie Anordnung an der Bruchstelle gefunden"
    (pieces, r_link, r_turn), lay_info = found
    labels = {0: "Ring 0 einwärts", 1: "Ring 1 auswärts", 2: "Ring 2 einwärts"}
    segs: list[Segment] = []
    for i, pts in pieces:
        fine = resample_curve(pts, p.step_mm, p.chord_tol_mm)
        if segs:
            fine[0] = segs[-1].points[-1]
        segs.append(Segment("outer" if i == 0 else "inner", i, fine, label=labels[i]))
    path = LayerPath(ctx.layer, ctx.island, segs, [], "out_in")
    _, viol = measure_path(path, ctx.region, p, ctx.part_bounds)
    errors = [v for v in viol if v.severity == "error"]
    if errors:
        return "Prüfung der Fermat-Bahn: " + "; ".join(f"{v.rule} {v.message}" for v in errors[:3])
    gap0 = lay_info["u_start"] + lay_info["link_half"] if n == 3 else lay_info["u_start"] - lay_info["u_turn"]
    meta = {
        "rows": n,
        "row_offsets_mm": [round((i + 0.5) * w, 2) for i in range(n)],
        "turn_radius_mm": round(r_turn, 2),
        **({"link_radius_mm": round(r_link, 2)} if math.isfinite(r_link) else {}),
        "outer_gap_mm": round(gap0, 2),
        "outer_ring_mm": round(lay.rows[0].length, 2),
        "start": [round(float(x), 2) for x in segs[0].points[0]],
        "end": [round(float(x), 2) for x in segs[-1].points[-1]],
        **{k: round(v, 2) for k, v in lay_info.items()},
        **info,
    }
    return IslandPlan(segs, [], meta)
