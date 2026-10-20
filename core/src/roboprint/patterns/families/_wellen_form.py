"""Wellenformen der Familie „Wellen“ (Sinus, gerundete Trapezwelle mit Zickzack und Mäander als
Sonderfällen) und ihre schnellen lokalen Größen für die Einlaufsuche (families/wellen.py).

Die Einlaufsuche probiert je Millimeter Wellenanfang eine neue Welle; gebraucht werden dafür nur
der kleinste Eckradius (Wahl der Halbwellenzahl) und die ersten zwei Punkte der abgetasteten Welle
(Einlauf-Biarc). Beides rechnen `corner_radius` und `wave_start` in reinem Python, ohne die ganze
Welle mit `fillet_polyline` zu erzeugen: dieselben Formeln in derselben Reihenfolge wie
`geometry.fillet_polyline` und `clip_u` (Abweichung höchstens im Rundungsrauschen der
Skalarprodukte, ~1e-13 mm). Wo die Rechnung einen Sonderfall träfe (entartete Ecke), liefert sie
None, und der Aufrufer nimmt die ganze Welle.
"""

from __future__ import annotations

import functools
import math
from typing import Any

import numpy as np

from roboprint.patterns.geometry import dedupe, fillet_polyline
from roboprint.patterns.layout import fit_to_length

#: Abtastung der Sollkurve vor dem Neu-Abtasten (mm)
FINE_MM = 1.0
#: Gleichstand beim Vergleich der Wellenradien (Rundungsrauschen der Eckrundung, mm)
RADIUS_TIE_MM = 1e-9


#: Kleinste Ecke, die gerundet wird (wie `fillet_polyline`, Grad)
MIN_TURN_DEG = 1.0
#: Doppelpunkt-Toleranz (wie `geometry.dedupe`)
DEDUPE_TOL = 1e-9

Verts = list[tuple[float, float]]


def _dedupe(p: Verts) -> Verts:
    if len(p) < 2:
        return list(p)
    out = [p[0]]
    for k in range(1, len(p)):
        if math.hypot(p[k][0] - p[k - 1][0], p[k][1] - p[k - 1][1]) > DEDUPE_TOL:
            out.append(p[k])
    return out


def corner_radius(verts: Verts | None, radius: float) -> float:
    """Kleinster Eckradius wie `fillet_polyline(verts, radius)[1]` (0 ohne Form, inf ohne Ecke)."""
    if verts is None:
        return 0.0
    p = _dedupe(verts)
    rmin = math.inf
    for (ax, ay), (bx, by), (cx, cy) in zip(p, p[1:], p[2:], strict=False):
        ux, uy, vx, vy = bx - ax, by - ay, cx - bx, cy - by
        la, lb = math.sqrt(ux * ux + uy * uy), math.sqrt(vx * vx + vy * vy)
        th = math.acos(min(1.0, max(-1.0, (ux / la) * (vx / lb) + (uy / la) * (vy / lb))))
        if math.degrees(th) < MIN_TURN_DEG:
            continue
        tan_h = math.tan(th / 2.0)
        rmin = min(rmin, min(radius * tan_h, 0.5 * la, 0.5 * lb) / tan_h)
    return rmin


def _corner_samples(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    radius: float,
    tol: float,
    step: float,
    u_skip: float = -math.inf,
) -> list[tuple[float, float]] | None:
    """Bogenpunkte der gerundeten Ecke b (wie `_corner_arcs`), [b] ohne Rundung, None bei Entartung."""
    ux, uy, vx, vy = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
    la, lb = math.sqrt(ux * ux + uy * uy), math.sqrt(vx * vx + vy * vy)
    ux, uy, vx, vy = ux / la, uy / la, vx / lb, vy / lb
    th = math.acos(min(1.0, max(-1.0, ux * vx + uy * vy)))
    if math.degrees(th) < MIN_TURN_DEG:
        return [b]
    tan_h = math.tan(th / 2.0)
    tl = min(radius * tan_h, 0.5 * la, 0.5 * lb)
    ax_, ay_ = b[0] - tl * ux, b[1] - tl * uy
    bx_, by_ = b[0] + tl * vx, b[1] + tl * vy
    cx, cy = bx_ - ax_, by_ - ay_
    nx, ny = -uy, ux
    den = 2.0 * (nx * cx + ny * cy)
    cc = cx * cx + cy * cy
    if abs(den) < 1e-12 * max(1.0, cc):
        return None
    if bx_ <= u_skip:
        # Bogen ganz vor u_s (u wächst längs der Trapezwelle monoton): nur der letzte Punkt zählt
        return [(ax_, ay_), (bx_, by_)]
    rs = cc / den
    ctrx, ctry = ax_ + rs * nx, ay_ + rs * ny
    vax, vay, vbx, vby = ax_ - ctrx, ay_ - ctry, bx_ - ctrx, by_ - ctry
    sweep = math.atan2(vax * vby - vay * vbx, vax * vbx + vay * vby)
    if rs > 0 and sweep < 0:
        sweep += 2 * math.pi
    elif rs < 0 and sweep > 0:
        sweep -= 2 * math.pi
    r = abs(rs)
    dphi = math.pi / 2
    if r > tol:
        dphi = min(dphi, 2.0 * math.acos(1.0 - tol / r))
    if r > 0:
        dphi = min(dphi, 2.0 * math.asin(min(1.0, step / (2.0 * r))))
    a0 = math.atan2(vay, vax)
    cnt = max(1, math.ceil(abs(sweep) / dphi - 1e-9))
    out = [(ax_, ay_)]
    for k in range(1, cnt):
        ang = a0 + sweep * k / cnt
        out.append((ctrx + r * math.cos(ang), ctry + r * math.sin(ang)))
    out.append((bx_, by_))
    return out


def wave_start(
    verts: Verts | None, radius: float, u_s: float, tol: float, step: float
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Die ersten zwei Punkte von `clip_u(fillet_polyline(verts, radius, …)[0], u_s, …)`: der
    Schnittpunkt bei u_s und der nächste Abtastpunkt. None ohne Form oder bei einem Sonderfall."""
    if verts is None:
        return None
    p = _dedupe(verts)
    if len(p) < 3:
        return None
    prev: tuple[float, float] | None = None
    hit: tuple[float, float] | None = None
    seq = [p[0]]
    for i in range(1, len(p) + 1):
        if i < len(p) - 1:
            arc = _corner_samples(p[i - 1], p[i], p[i + 1], radius, tol, step, u_s)
            if arc is None:
                return None
            seq.extend(arc)
        elif i == len(p) - 1:
            seq.append(p[-1])
        for q in seq:
            if prev is not None and math.hypot(q[0] - prev[0], q[1] - prev[1]) <= DEDUPE_TOL:
                continue  # dedupe am Ende von fillet_polyline
            if hit is None:
                if q[0] > u_s:
                    if prev is None:
                        return None  # Welle beginnt hinter u_s
                    a, b = prev, q
                    s = u_s - a[0]
                    d = b[0] - a[0]
                    hit = (a[0] + (b[0] - a[0]) * s / d, a[1] + (b[1] - a[1]) * s / d)
                    if math.hypot(q[0] - hit[0], q[1] - hit[1]) > DEDUPE_TOL:
                        return hit, q
            elif math.hypot(q[0] - prev[0], q[1] - prev[1]) > DEDUPE_TOL:
                return hit, q
            prev = q
        seq = []
    return None


# --------------------------------------------------------------------------- Wellenformen


def sine_uv(
    u_s: float, u_e: float, lam: float, amp: float, phase: float, sigma: float, u_cut: float | None = None
) -> np.ndarray:
    """Sinus von u_s bis u_e. `u_cut`: nur der Anfang bis zum ersten Punkt hinter u_cut (bitgleich
    zum Anfang der ganzen Welle; für die Einlaufsuche, die nur die ersten Wellenlängen prüft)."""
    # Stücke ≤ FINE_MM auch an steilen Flanken (resample_pieces hält längere Stücke für Geraden)
    du = FINE_MM / math.sqrt(1.0 + (2 * math.pi * amp / lam) ** 2)
    n = max(2, math.ceil((u_e - u_s) / du) + 1)
    u = np.linspace(u_s, u_e, n)
    if u_cut is not None and u_cut < u_e:
        u = u[: int(np.searchsorted(u, u_cut, side="right")) + 1]
    return np.column_stack([u, sigma * amp * np.cos(2 * math.pi * (u - u_s) / lam + phase)])


@functools.lru_cache(maxsize=4096)
def zigzag_height(lam: float, amp: float, radius: float) -> float:
    """Höhe H der Zickzack-Scheitelpunkte, bei der der Bogenscheitel (Radius r) genau A erreicht:
    H − r·(√(1 + (4H/λ)²) − 1) = A. Lösbar nur für λ > 4·r (sonst wächst der Abzug schneller als
    H: zwei Bögen mit r füllen die Halbwelle allein); dann inf."""
    if lam <= 4.0 * radius:
        return math.inf
    f = lambda h: h - radius * (math.sqrt(1.0 + (4.0 * h / lam) ** 2) - 1.0) - amp  # noqa: E731
    lo, hi = amp, amp + 1.0
    while f(hi) < 0:
        hi *= 2.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return hi


def _trapezoid_verts(
    u_s: float,
    u_e: float,
    lam: float,
    amp: float,
    phase: float,
    sigma: float,
    plateau: float,
    radius: float,
    n_crests: int | None = None,
) -> list[tuple[float, float]] | None:
    """Eckpunkte der ungerundeten Trapezwelle (None, wenn die Form nicht passt). `n_crests`: nur
    die ersten Scheitel (dieselben Zahlen wie am Anfang der ganzen Liste)."""
    half = lam / 2.0
    P = min(max(plateau, 0.0), half)
    shift = phase / (2 * math.pi) * lam
    height = amp if P > 1e-9 else zigzag_height(lam, amp, radius)
    if not math.isfinite(height):
        return None
    j0 = math.floor(shift / half) - 2
    j1 = math.ceil((u_e - u_s + shift) / half) + 3
    if n_crests is not None:
        j1 = min(j1, j0 + n_crests)
    verts: list[tuple[float, float]] = []
    for j in range(j0, j1):
        cu = u_s - shift + j * half
        sv = sigma * (1 if j % 2 == 0 else -1) * height
        verts += [(cu - P / 2, sv), (cu + P / 2, sv)] if P > 1e-9 else [(cu, sv)]
    return verts


def trapezoid_uv(
    u_s: float,
    u_e: float,
    lam: float,
    amp: float,
    phase: float,
    sigma: float,
    plateau: float,
    radius: float,
    u_cut: float | None = None,
) -> tuple[np.ndarray, float, float]:
    """Gerundete Trapezwelle (plateau = 0: Zickzack, plateau = λ/2: Mäander), Plateaumitte des
    ersten Scheitels bei u_s − phase/(2π)·λ. Rückgabe (uv, kleinster Eckradius, erreichte
    Amplitude); uv ist leer, wenn die Form mit diesem r nicht in die Halbwelle passt.

    `u_cut` (≥ u_s + λ): nur der Anfang bis u_cut. Die Eckrundung ist lokal, der Anfang ist deshalb
    bitgleich zur ganzen Welle; Radius und Amplitude sind dieselben (alle Scheitel sind gleich,
    im Anfang liegen mindestens zwei ganze)."""
    if u_cut is not None and u_cut < u_e:
        u_e = u_cut
    verts = _trapezoid_verts(u_s, u_e, lam, amp, phase, sigma, plateau, radius)
    if verts is None:
        return np.zeros((0, 2)), 0.0, 0.0
    # Mäander: senkrechte Flanken, Nachbarecken mit gleichem u (gewollt)
    uv, rmin = fillet_polyline(np.array(verts), radius, chord_tol_mm=0.05, step_mm=FINE_MM)
    uv = clip_u(uv, u_s, u_e)
    peak = float(np.max(np.abs(uv[:, 1]))) if len(uv) else 0.0
    return uv, rmin, peak


def trapezoid_radius(
    lam: float, amp: float, phase: float, sigma: float, plateau: float, radius: float
) -> float:
    """Kleinster Eckradius der gerundeten Trapezwelle, ohne die Welle zu erzeugen: dieselbe Rechnung
    wie `fillet_polyline` an den inneren Ecken der ersten Scheitel: mit Plateau zwei (Plateauende
    und -anfang), ohne drei (eine Spitze). Alle Ecken einer Art sind gleich (Verschiebung bzw.
    Spiegelung), also derselbe Wert wie für die ganze Welle bis auf Rundungsrauschen; 0, wenn die
    Form nicht passt."""
    crests = 2 if min(max(plateau, 0.0), lam / 2.0) > 1e-9 else 3
    return corner_radius(
        _trapezoid_verts(0.0, 0.0, lam, amp, phase, sigma, plateau, radius, n_crests=crests), radius
    )


def clip_u(uv: np.ndarray, u_s: float, u_e: float) -> np.ndarray:
    """Polylinie (u nicht fallend, deckt [u_s, u_e] ab) auf [u_s, u_e] schneiden, mit exakten
    Endpunkten."""
    u = uv[:, 0]
    i0 = int(np.searchsorted(u, u_s, side="right"))
    i1 = int(np.searchsorted(u, u_e, side="left"))
    if i0 == 0 or i1 >= len(u) or i0 > i1:
        raise ValueError("Welle deckt den Bereich nicht ab")
    a, b = uv[i0 - 1], uv[i0]
    c, d = uv[i1 - 1], uv[i1]
    p = a + (b - a) * (u_s - a[0]) / (b[0] - a[0])
    q = c + (d - c) * (u_e - c[0]) / (d[0] - c[0]) if d[0] > c[0] else d
    return dedupe(np.vstack([p, uv[i0:i1], q]))


def wave_uv(
    shape: str,
    u_s: float,
    u_e: float,
    amp: float,
    opts: dict[str, Any],
    sigma: float,
    n_fixed: int | None = None,
    cut: tuple[float, float] | None = None,
    start_only: bool = False,
):
    """Welle von u_s bis u_e: (uv, Wellenlänge, Halbwellen, kleinster Radius der Sollkurve).
    `n_fixed`: Zahl der Halbwellen vorgeben (Einlaufsuche, spart das erneute Anpassen).
    `cut` = (k, a): nur den Anfang bis u_s + k·λ + a erzeugen, k ≥ 1 (bitgleich zum Anfang der
    ganzen Welle; Wellenlänge, Halbwellen und Radius wie für die ganze Welle).
    `start_only`: uv sind nur die ersten zwei Punkte (Einlauf-Biarc), ohne die Welle zu erzeugen
    (`wave_start`); die Scheitelprüfung entfällt dann (siehe unten)."""
    total = u_e - u_s
    lam_t = float(opts["wavelength_mm"])
    w = float(opts["w"])
    phase = math.radians(float(opts["phase_deg"]))
    radius = float(opts.get("round_radius_mm", 0.0))
    n0 = fit_to_length(total, lam_t / 2.0).count
    target = w if shape == "sinus" else min(w, radius)
    best = None
    # Halbwellen verringern, bis der Radius das Ziel erreicht; begrenzt das Band den Radius
    # (Mäander im 50-mm-Band: r ≤ A), bleibt die angepasste Zahl mit dem größten Radius.
    # Die Welle selbst wird nur erzeugt, wenn ihr Radius (`trapezoid_radius`, ohne Welle) über
    # Abbruch oder Bestwert entscheiden kann; sonst wäre sie verworfen worden (Laufzeit).
    # Entschieden wird mit diesem Radius (für alle Ausschnitte der Welle derselbe) und einer
    # Gleichstandsschwelle RADIUS_TIE_MM: Begrenzt das Band den Radius (Mäander: r = A für mehrere
    # n), war der Vergleich „r > Bestwert + 0,05“ bisher ein Gleichstand im Rundungsrauschen.
    # Die Scheitelprüfung (Scheitel unter A − 0,5 mm) greift bei Plateaus nie (Plateau = A genau)
    # und beim Zickzack nie (Bogenscheitel = A, Abtastung ≤ 0,05 mm darunter, ein verkleinerter
    # Eckradius hebt den Scheitel); sie bleibt als Sicherung, wo die Welle ohnehin erzeugt wird.
    for n in range(n_fixed or n0, 0, -1):
        lam = 2.0 * total / n
        u_cut = None if cut is None else u_s + cut[0] * lam + cut[1]
        pl = 0.0
        if shape == "sinus":
            r = lam * lam / (4 * math.pi**2 * amp) if amp > 1e-9 else math.inf
            uv = None
        else:
            plateau = (
                lam / 2.0 if shape == "maeander" else (0.0 if shape == "zickzack" else opts["plateau_mm"])
            )
            # Trapez: zu langes Plateau lässt keinen Platz für die Eckbögen → Plateau kürzen
            pls = list(dict.fromkeys([plateau, plateau / 2.0, 0.0] if shape == "trapez" else [plateau]))
            uv = None
            for i_pl, pl in enumerate(pls):
                r = trapezoid_radius(lam, amp, phase, sigma, pl, radius)
                last = i_pl == len(pls) - 1
                # Ohne Welle verworfen: r (≥ r nach der Scheitelprüfung) erreicht weder das Ziel
                # noch (als letzte Plateaulänge) den Bestwert
                if r < target - 1e-6 and not (last and (best is None or r > best[3] + 0.05 + RADIUS_TIE_MM)):
                    uv = None
                    continue
                if start_only:
                    uv = _START
                else:
                    uv, r_full, peak = trapezoid_uv(u_s, u_e, lam, amp, phase, sigma, pl, radius, u_cut)
                    if peak < amp - 0.5 and total >= lam / 2.0:  # Scheitel erreichen die Schale nicht
                        r = 0.0
                if r >= target - 1e-6:
                    break
            if uv is None:  # nur Kandidaten, die weder Ziel noch Bestwert erreichen
                continue
        if best is None or r > best[3] + 0.05 + RADIUS_TIE_MM:
            # berichtet wird der Radius der erzeugten Welle (wie bisher), entschieden mit r
            best = (uv, lam, n, r, pl, r_full if (uv is not None and uv is not _START and r > 0) else r)
        if r >= target - 1e-6:
            break
    uv, lam, n, _, pl, r = best
    if uv is None:
        u_c = u_s + FINE_MM if start_only else (None if cut is None else u_s + cut[0] * lam + cut[1])
        uv = sine_uv(u_s, u_e, lam, amp, phase, sigma, u_c)
        if start_only:
            uv = uv[:2]
    elif uv is _START:
        verts = _trapezoid_verts(u_s, min(u_e, u_s + lam), lam, amp, phase, sigma, pl, radius)
        st = wave_start(verts, radius, u_s, 0.05, FINE_MM)
        if st is None:  # Sonderfall: ganze Welle
            uv = trapezoid_uv(u_s, u_e, lam, amp, phase, sigma, pl, radius, u_s + lam)[0][:2]
        else:
            uv = np.array(st)
    return uv, lam, n, r


#: Platzhalter in `wave_uv`: Welle nur am Anfang gebraucht
_START = np.zeros((0, 2))
