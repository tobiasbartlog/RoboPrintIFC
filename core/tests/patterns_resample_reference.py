"""EINGEFRORENE REFERENZ (nicht ändern): `resample_curve` aus `roboprint/patterns/geometry.py` vor der
Wellen-Laufzeitoptimierung (Commit 5dd66ee), Sehnenwahl mit numpy je Kandidat (`_seg_dev`). Der
Gleichheitstest in test_patterns_wellen_perf.py vergleicht die schnelle Fassung damit."""

from __future__ import annotations

import numpy as np

from roboprint.patterns.geometry import _turn_deg, arc_length, dedupe, densify


def _seg_dev(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Größter Abstand der Punkte zur Strecke a-b."""
    if len(pts) == 0:
        return 0.0
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-18:
        return float(np.linalg.norm(pts - a, axis=1).max())
    t = np.clip((pts - a) @ ab / L2, 0.0, 1.0)
    return float(np.linalg.norm(pts - (a + t[:, None] * ab), axis=1).max())


def resample_curve(
    points: np.ndarray,
    step_mm: float = 20.0,
    chord_tol_mm: float = 0.5,
    closed: bool = False,
    keep_angle_deg: float = 20.0,
) -> np.ndarray:
    """Polylinie neu abtasten: Sehnenfehler ≤ `chord_tol_mm` gegen die Eingabe-Polylinie
    (die Sollkurve, fein abgetastet), Wegpunktabstand ≤ `step_mm`.

    Gierig über die Eingabepunkte: Von jedem gewählten Punkt aus der fernste Eingabepunkt, bis zu
    dem alle Zwischenpunkte ≤ chord_tol von der Sehne liegen und die Bogenlänge ≤ step_mm ist.
    Punkte mit einer Richtungsänderung > `keep_angle_deg` (echte Ecken) bleiben erhalten. Danach
    werden zu lange Sehnen gleichmäßig auf ≤ step_mm unterteilt. Alle Ausgabepunkte liegen auf der
    Eingabe-Polylinie. `closed`: Ausgabe endet mit dem Startpunkt."""
    p = dedupe(points)
    if closed and len(p) > 1 and np.linalg.norm(p[0] - p[-1]) > 1e-9:
        p = np.vstack([p, p[:1]])
    if len(p) < 3:
        return densify(p, step_mm) if len(p) == 2 else p
    corner = _turn_deg(p[:-1] if closed else p, closed) > keep_angle_deg
    if closed:
        corner = np.append(corner, True)
    forced = np.flatnonzero(corner)
    s = arc_length(p)
    n = len(p)
    out = [0]
    i = 0
    while i < n - 1:
        jmax = int(np.searchsorted(s, s[i] + step_mm + 1e-9, side="right")) - 1
        jmax = min(max(jmax, i + 1), n - 1)
        f = forced[np.searchsorted(forced, i, side="right") :]
        if len(f):
            jmax = min(jmax, int(f[0]))
        j = jmax
        while j > i + 1 and _seg_dev(p[i + 1 : j], p[i], p[j]) > chord_tol_mm:
            j -= 1
        out.append(j)
        i = j
    res = densify(p[out], step_mm)
    if closed:
        res[-1] = res[0]
    return res
