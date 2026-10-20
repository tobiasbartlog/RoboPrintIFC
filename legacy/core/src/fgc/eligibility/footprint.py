"""Grundriss-Druckbarkeitschecks der E1-Stufe 2 (Geometrie) — reine shapely-Funktionen.

Zahlen aus Spike S4 (docs/spikes/S4_offset_robustheit.md, 2026-07-02), normiert in
Strangbreiten ``w`` (w selbst noch unbekannt, s. S1):

- **Mindest-Innenwinkel konvexer Ecken: 30°.** Darunter schneidet das Innen-Offset
  die Spitze ab (Sliver/Leere ab Schale k=2 bei 15° in der ``wedge``-Familie).
  Der Winkel ist strangbreitenunabhängig.
- **Mindeststegbreite:** ein gerader Steg der Breite ``s`` übersteht Inset ``i``
  nur solange ``s > 2·i``; für ``n`` Schalen ist der tiefste Inset ``(n−0.5)×w``,
  also ``s > (2n−1)×w``. Die Karte trägt in ``min_web_width_strand_widths`` bereits
  den 1-Schalen-Wert **inkl. Sicherheitsmarge** (1.5×w = (2·1−1)+0.5); je weitere
  Schale kommen +2×w hinzu. Der Erosionstest unten nutzt genau diese Breite.
- **Mindestinnenradius 0.5×w:** bewusst NICHT als harter Check umgesetzt — ohne
  Krümmungsanalyse des Grundrisses (Kreisbogen-Fitting je Ecke) wäre jede Zahl
  Pseudogenauigkeit. Dokumentiert offen, s. Design-Log 2026-07-02.
- **mitre_limit = 2.0** (statt shapely-Default 5.0) für den Erosionstest in
  ``has_narrow_web``: der Default zerfällt an scharfen konkaven Reflex-Kerben
  in ein MultiPolygon (Issue #2), materialunabhängig — Default hier nur der
  Fallback ohne Karte, Produktionswert kommt aus ``ProcessWindow.mitre_limit``.

Alle Funktionen sind rein (Polygon rein, Zahl/Urteil raus) und ohne Projekt-Imports,
damit sie einzeln testbar bleiben und keine Modulabhängigkeit erzeugen.
"""

from __future__ import annotations

import math

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient


def min_convex_interior_angle_deg(polygon: Polygon) -> float | None:
    """Kleinster Innenwinkel an einer konvexen Ecke des Außenrings (Grad).

    Reflexecken (Innenwinkel > 180°) werden übergangen — die bindende S4-Grenze
    kommt von der konvexen Spitze, nicht von der konkaven Kerbe. Löcher werden
    ignoriert (v1-Wände sind öffnungslos, ADR-005). ``None``, falls der Ring
    keine konvexe Ecke hat (bei einem einfachen Polygon nicht möglich, defensiv).
    """
    ccw = orient(polygon, sign=1.0)  # Außenring gegen den Uhrzeigersinn
    coords = list(ccw.exterior.coords)
    pts = coords[:-1] if coords and coords[0] == coords[-1] else coords
    n = len(pts)
    if n < 3:
        return None

    smallest: float | None = None
    for i in range(n):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        vin = (x1 - x0, y1 - y0)
        vout = (x2 - x1, y2 - y1)
        cross = vin[0] * vout[1] - vin[1] * vout[0]
        dot = vin[0] * vout[0] + vin[1] * vout[1]
        if cross <= 0:  # bei CCW: konkave Reflexecke (oder gerade) — übergehen
            continue
        interior = math.degrees(math.pi - math.atan2(cross, dot))
        if smallest is None or interior < smallest:
            smallest = interior
    return smallest


def min_web_width_factor(min_web_width_strand_widths: float, n_shells: int) -> float:
    """Vielfaches der Strangbreite für die S4-Stegformel (Faktor von ``min_web_width_mm``).

    ``min_web_width_strand_widths`` ist der 1-Schalen-Wert (1.5×w inkl. +0.5×w
    Sicherheitsmarge); je weitere Schale +2×w. Eigene Funktion, damit
    Begründungstexte (z. B. E1-Dickenprüfung) den Faktor formatieren können, ohne
    den Ausdruck nachzubauen.
    """
    return min_web_width_strand_widths + 2 * (n_shells - 1)


def min_web_width_mm(
    strand_width_mm: float, min_web_width_strand_widths: float, n_shells: int
) -> float:
    """Kleinste druckbare Stegbreite in mm (S4-Formel, inkl. Kartenmarge)."""
    return strand_width_mm * min_web_width_factor(min_web_width_strand_widths, n_shells)


#: Fallback, falls ohne Prozessfenster-Karte aufgerufen (z. B. Tests) — die
#: Produktionsschicht speist ``ProcessWindow.mitre_limit`` durch (ADR-013, eine
#: Quelle mit ``fgc.slicer.shells.shell_rings``), s. ``eligibility.rules``.
DEFAULT_MITRE_LIMIT = 2.0


def has_narrow_web(
    polygon: Polygon,
    strand_width_mm: float,
    min_web_width_strand_widths: float,
    n_shells: int,
    mitre_limit: float = DEFAULT_MITRE_LIMIT,
) -> bool:
    """True, wenn der Grundriss einen Steg schmaler als die druckbare Mindestbreite hat.

    Erosionstest nach S4: Ein Steg der druckbaren Grenzbreite ``smin`` kollabiert
    genau bei Inset ``smin/2``. Wird der Grundriss um ``smin/2`` nach innen
    gepuffert (mit dem Karten-``mitre_limit`` aus S4, Default 2.0) und zerfällt
    dabei in mehrere Teile oder verschwindet, obwohl er vorher zusammenhängend
    war, liegt an dieser Stelle ein zu schmaler Steg vor.
    """
    smin = min_web_width_mm(strand_width_mm, min_web_width_strand_widths, n_shells)
    eroded = polygon.buffer(-smin / 2.0, join_style="mitre", mitre_limit=mitre_limit)
    if eroded.is_empty:
        return True
    return isinstance(eroded, MultiPolygon)
