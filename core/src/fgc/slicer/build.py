"""Stufe 3 des Slicers: Schalenringe -> Toolpath-Targets.

v0: konstante io-Werte, bahn-relative Orientierung — die Düse zeigt beim Drucken
senkrecht nach unten (``NOZZLE_DOWN_QUAT``, ADR-006), sofern kein Anstellwinkel
gesetzt ist. Bis Issue #51 emittierte der Slicer hier eine Identitäts-
Orientierung, während die Platzierungs-/Erreichbarkeitsbewertung mit
Düse-nach-unten rechnete — dieselbe Wand galt im Druckplan als erreichbar, in der
Simulation nicht. Seit #61 ziehen beide ihre Orientierung aus **einer** Funktion,
``fgc.domain.orientation.nozzle_quat``: der Slicer speist die echte Bahntangente
(aufeinanderfolgende Ringpunkte) ein, ``placement`` seine angenommene Tangente —
so kann Erreichbarkeit nicht von der Simulation abdriften (Regressionsschutz #51).
Der Lead-/Kipp-Winkel (``params.lead_rad``/``params.kipp_rad``) stellt die Düse
bahn-relativ an; 0/0 ⇒ senkrecht von oben (heutiges Verhalten je Ziel).
Jedes Segment beginnt mit einem Travel-Target (io=0, Pumpen aus) zum Ringstart;
die Print-Targets laufen den Ring ab und schließen ihn (letzter Punkt = erster).
Zeit existiert hier nicht — der Toolpath bleibt zeitfrei (E3).
"""

from __future__ import annotations

from fgc.domain.models import Frame, Target, Toolpath
from fgc.domain.orientation import nozzle_quat
from fgc.domain.process_params import SliceParams
from fgc.slicer.sections import LayerSection
from fgc.slicer.shells import shell_rings


def build_toolpath(
    wall_global_id: str, layers: list[LayerSection], params: SliceParams
) -> Toolpath:
    targets: list[Target] = []
    current_xy: tuple[float, float] | None = None
    for section in layers:
        for poly_idx, polygon in enumerate(section.polygons):
            rings = shell_rings(
                polygon, params.strand_width_mm, params.n_shells, params.mitre_limit
            )
            for ring_idx, ring in enumerate(rings):
                segment_id = f"L{section.layer:03d}_C{poly_idx}_S{ring.shell}_R{ring_idx}"
                points_xy = _rotate_to_nearest(ring.points_xy, current_xy)
                targets.extend(_ring_targets(points_xy, section, segment_id, params))
                current_xy = points_xy[0]
    return Toolpath(wall_global_id=wall_global_id, targets=targets)


def _rotate_to_nearest(
    points_xy: list[tuple[float, float]],
    current_xy: tuple[float, float] | None,
) -> list[tuple[float, float]]:
    """Rotiert den geschlossenen Ring so, dass er möglichst nah an `current_xy`
    startet. Ohne das hängt der Startpunkt am Zufall der GEOS-Offset-
    Berechnung (shapely `buffer`): sonst identische Ringe benachbarter
    Schichten können an unterschiedlichen Ecken beginnen, was einen Travel
    quer über die Wand statt eines kurzen Sprungs erzeugt."""
    if current_xy is None or len(points_xy) < 3:
        return points_xy
    ring = points_xy[:-1]  # letzter Punkt == erster (geschlossen) -> nicht doppelt betrachten
    start = min(
        range(len(ring)),
        key=lambda i: (ring[i][0] - current_xy[0]) ** 2 + (ring[i][1] - current_xy[1]) ** 2,
    )
    rotated = ring[start:] + ring[:start]
    return [*rotated, rotated[0]]


def _ring_targets(
    points_xy: list[tuple[float, float]],
    section: LayerSection,
    segment_id: str,
    params: SliceParams,
) -> list[Target]:
    def target(x: float, y: float, quat, kind: str, sid: str) -> Target:
        printing = kind == "print"
        return Target(
            frame=Frame(
                pos_mm=(round(x, 3), round(y, 3), round(section.z_mm, 3)),
                quat=quat,
            ),
            v_mm_s=params.v_print_mm_s if printing else params.v_travel_mm_s,
            io=dict(params.io_print if printing else params.io_travel),
            kind=kind,  # type: ignore[arg-type]
            layer=section.layer,
            segment_id=sid,
        )

    # Bahntangente je Ziel aus aufeinanderfolgenden Ringpunkten; die Düse wird
    # darüber bahn-relativ angestellt (Issue #61 — dieselbe Funktion wie placement).
    def _quat_at(i: int):
        j = i if i > 0 else 1  # Approach nutzt die Tangente des ersten Segments
        prev, cur = points_xy[j - 1], points_xy[j]
        tangent = (cur[0] - prev[0], cur[1] - prev[1])
        return nozzle_quat(tangent, params.lead_rad, params.kipp_rad)

    ax, ay = points_xy[0]
    approach = target(ax, ay, _quat_at(0), kind="travel", sid=f"{segment_id}_approach")
    prints = [
        target(x, y, _quat_at(i + 1), kind="print", sid=segment_id)
        for i, (x, y) in enumerate(points_xy[1:])
    ]
    return [approach, *prints]
