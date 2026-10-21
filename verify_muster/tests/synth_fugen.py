"""Synthetische Fugenwand nach dem Foto (docs/muster/referenz/fugenwand-foto.jpg, Nutzer-Nachtrag 18:20).

Eine Schicht ist ein einziger geschlossener Zug (Topologie-Vorschlag aus AUFTRAG.md):
Feld A → Fuge J1 → Steg zum Knoten ueber der Feldmitte von A → Gurt zum Knoten ueber B → Steg zurueck
zur Fuge J1 → Feld B → Fuge J2 → … → Endkappe → Rueckseite gespiegelt zurueck → Endkappe.

Konstruktion als "Riemen um Rollen": eine geschlossene Folge von Kreisen (Mittelpunkt, Radius,
Drehsinn), verbunden durch gemeinsame Tangenten. Damit sind Kontakte exakt einstellbar:

- Fuge: Die beiden Besuche sind Kehren vom Radius r mit Mittelpunkten im Abstand contact + 2·r auf der
  Hoehe y_out − r; ihre Scheitel beruehren sich mit Mittellinienabstand `contact_mm`. Die Felder
  (`outfill`) laufen tangential auf y = ∓y_out, die Stege (`web`) schraeg zu den Knoten.
- Knoten ueber den Feldmitten: Rechtskehren unter dem Gurt (`infill`, y = ∓y_girder); innere Knoten
  werden zweimal besucht und beruehren sich wie die Fugen (`node_contact_mm`). Die Gurte von Vorder- und
  Rueckseite liegen 2·y_girder = 29 mm auseinander und beruehren sich ebenfalls.
- Endkappen (`outfill`) mit Eckradius r_end an den Modulenden.
- Die Naht (Start = Ende, senkrechter Schichtwechsel) liegt mitten auf dem ersten Gurt, also innen,
  nicht auf der Sichtflaeche und nicht an der Stossflaeche.
"""

from __future__ import annotations

import numpy as np

from verify_muster.tests.synth import W

TWO_PI = 2.0 * np.pi


def _tangent(p, sp, rp, q, sq, rq):
    """Gemeinsame Tangente vom Kreis (p, Drehsinn sp, Radius rp) zum Kreis (q, sq, rq).

    Ein Bahnpunkt auf einem Kreis mit Fahrtrichtung t ist center − s·r·n(t), n = t um +90° gedreht
    (Linkskehre s = +1: Mittelpunkt links der Fahrtrichtung). Rueckgabe: (Abgangspunkt, Ankunftspunkt).
    """
    d = np.asarray(q, float) - np.asarray(p, float)
    dist = float(np.hypot(*d))
    k = sq * rq - sp * rp
    if dist <= abs(k) + 1e-9:
        raise ValueError("Kreise zu nah fuer eine gemeinsame Tangente")
    theta = np.arctan2(d[1], d[0]) - np.arcsin(k / dist)
    n = np.array([-np.sin(theta), np.cos(theta)])
    return np.asarray(p, float) - sp * rp * n, np.asarray(q, float) - sq * rq * n


def _seg(a, b, step):
    m = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
    return a + (np.arange(m + 1) / m)[:, None] * (b - a)


def belt(circles: list[tuple], kinds: list[str], step: float = 1.0):
    """Geschlossener Zug um die Kreise [(Mittelpunkt, Radius, Drehsinn)], Segment i von Kreis i zu i + 1
    mit Art kinds[i]. Rueckgabe: Punkte, Art je Punkt (Kehren halb Ankunfts-, halb Abgangsart), Index
    der Mitte jeder Tangente."""
    n = len(circles)
    tang = [_tangent(*circles[i], *circles[(i + 1) % n]) for i in range(n)]
    pts, kd, seg_start = [], [], []
    for i in range(n):
        j = (i + 1) % n
        a, b = tang[i]
        s = _seg(a, b, step)[:-1]
        seg_start.append(len(pts) + len(s) // 2)
        pts.extend(s)
        kd += [kinds[i]] * len(s)
        # Kehre um Kreis j von b bis zum Abgangspunkt der naechsten Tangente
        (cx, cy), r, sj = circles[j]
        e = tang[j][0]
        a0 = np.arctan2(b[1] - cy, b[0] - cx)
        a1 = np.arctan2(e[1] - cy, e[0] - cx)
        sweep = (sj * (a1 - a0)) % TWO_PI
        m = max(2, int(np.ceil(sweep * r / step)))
        ang = a0 + sj * np.linspace(0.0, sweep, m + 1)[:-1]
        arc = np.column_stack([cx + r * np.cos(ang), cy + r * np.sin(ang)])
        pts.extend(arc)
        kd += [kinds[i]] * (len(arc) // 2) + [kinds[j]] * (len(arc) - len(arc) // 2)
    return np.asarray(pts), kd, seg_start


def circles(contact_mm: float = 28.5, node_contact_mm: float | None = None, r: float = 16.0,
            r_end: float = 30.0, n_fields: int = 3, length: float = 600.0, y_out: float = 85.0,
            y_girder: float = 14.5):
    """Kreise und Segmentarten der Fugenwand (Vorderseite in +x, Rueckseite gespiegelt zurueck).
    Rueckgabe: (Kreise, Arten, Index des ersten Gurts, Marken)."""
    node_contact_mm = contact_mm if node_contact_mm is None else node_contact_mm
    cj = 0.5 * (contact_mm + 2.0 * r)
    cn = 0.5 * (node_contact_mm + 2.0 * r)
    pitch = length / n_fields
    joints = [-length / 2 + k * pitch for k in range(1, n_fields)]
    mids = [-length / 2 + (k + 0.5) * pitch for k in range(n_fields)]
    x0, x1 = -length / 2 + W / 2, length / 2 - W / 2
    yo, yc = -y_out + r, -y_girder - r
    front = [((x0 + r_end, -y_out + r_end), r_end, 1, "outfill", "capL")]
    for k, xj in enumerate(joints, start=1):
        a = (mids[k - 1], f"N{k - 1}") if k == 1 else (mids[k - 1] + cn, f"N{k - 1}b")
        b = (mids[k], f"N{k}") if k == n_fields - 1 else (mids[k] - cn, f"N{k}a")
        front += [((xj - cj, yo), r, 1, "web", f"J{k}L"), ((a[0], yc), r, -1, "infill", a[1]),
                  ((b[0], yc), r, -1, "web", b[1]), ((xj + cj, yo), r, 1, "outfill", f"J{k}R")]
    front.append(((x1 - r_end, -y_out + r_end), r_end, 1, "outfill", "capR"))
    rev = list(reversed(front))
    back = []
    for i, (p, rr, s, _, tag) in enumerate(rev):
        kind_out = rev[i + 1][3] if i + 1 < len(rev) else "outfill"
        back.append(((p[0], -p[1]), rr, s, kind_out, tag + "'"))
    allc = front + back
    return ([(c[0], c[1], c[2]) for c in allc], [c[3] for c in allc], 2, [c[4] for c in allc])


def loop(contact_mm: float = 28.5, step: float = 1.0, **kw):
    """Eine Schicht als geschlossener Zug, Start mitten auf dem ersten Gurt der Vorderseite."""
    cs, ks, g_idx, _ = circles(contact_mm, **kw)
    pts, kd, seg_start = belt(cs, ks, step)
    s0 = seg_start[g_idx]
    pts = np.vstack([pts[s0:], pts[:s0], pts[s0:s0 + 1]])
    kd = kd[s0:] + kd[:s0] + kd[s0:s0 + 1]
    return pts, kd


def to_rings(pts: np.ndarray, kinds: list[str]) -> list[dict]:
    """Geschlossenen Zug in offene Ringe gleicher Art zerlegen. Die Ringe stossen aneinander (Ring k + 1
    beginnt am letzten Punkt von Ring k): Verbinder der Laenge 0 (ARTEFAKT-FORMAT, Nachtrag 18:45)."""
    rings, start = [], 0
    n = len(pts)
    for i in range(1, n):
        if kinds[i] != kinds[start] or i == n - 1:
            rings.append({"kind": kinds[start], "shell": 0 if kinds[start] == "outfill" else 1,
                          "xy": pts[start : i + 1]})
            start = i
    return rings


def fugenwand(contact_mm: float = 28.5, **kw) -> list[dict]:
    """Ringe einer Schicht (eine Insel) der Fugenwand."""
    pts, kd = loop(contact_mm, **kw)
    return to_rings(pts, kd)
