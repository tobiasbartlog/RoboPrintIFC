"""EINGEFRORENE REFERENZ (nicht ändern): `fillet_polyline` aus `roboprint/patterns/geometry.py` vor
der Laufzeitoptimierung (Commit b505214), Ecke für Ecke. Der Gleichheitstest in
test_patterns_perf.py vergleicht die vektorisierte Fassung damit."""

from __future__ import annotations

import math

import numpy as np

from roboprint.patterns.geometry import dedupe, tangent_arc


def fillet_polyline(
    points: np.ndarray,
    radius_mm: float,
    closed: bool = False,
    chord_tol_mm: float = 0.5,
    step_mm: float = 20.0,
    min_turn_deg: float = 1.0,
) -> tuple[np.ndarray, float]:
    """Ecken einer Polylinie mit Radius `radius_mm` runden (Kreisbogen tangential an beide Stücke).

    Reicht ein Stück nicht für die Tangentenlänge r·tan(θ/2), wird der Radius an dieser Ecke so
    verkleinert, dass höchstens die halbe Stücklänge verbraucht wird. Rückgabe (Punkte, kleinster
    tatsächlich verwendeter Radius; inf ohne Ecken). Geschlossen: Ein- und Ausgabe enden am Start."""
    p = dedupe(points)
    if closed and np.linalg.norm(p[0] - p[-1]) < 1e-9:
        p = p[:-1]
    n = len(p)
    if n < 3 or radius_mm <= 0:
        out = np.vstack([p, p[:1]]) if closed else p
        return out, math.inf
    idx = range(n) if closed else range(1, n - 1)
    pieces: dict[int, np.ndarray] = {}
    rmin = math.inf
    for i in idx:
        a, b, c = p[i - 1], p[i], p[(i + 1) % n]
        u, v = b - a, c - b
        la, lb = float(np.linalg.norm(u)), float(np.linalg.norm(v))
        u, v = u / la, v / lb
        th = math.acos(float(np.clip(u @ v, -1.0, 1.0)))
        if math.degrees(th) < min_turn_deg:
            continue
        tan_h = math.tan(th / 2.0)
        tl = min(radius_mm * tan_h, 0.5 * la, 0.5 * lb)
        r = tl / tan_h
        rmin = min(rmin, r)
        arc, _ = tangent_arc(b - tl * u, u, b + tl * v, chord_tol_mm, step_mm)
        pieces[i] = arc
    out: list[np.ndarray] = []
    for i in range(n):
        out.append(pieces.get(i, p[i : i + 1]))
    res = np.vstack(out)
    if closed:
        res = np.vstack([res, res[:1]])
    return dedupe(res), rmin
