"""Spike S4 — parametrische Testkonturen (normiert in Strangbreiten, w = 1.0).

Wegwerfskript, siehe docs/spikes/s4_scripts/PLAN.md. Jede Funktion liefert
eine Liste von Dicts mit Keys:
    family   -- Konturfamilie (str, z.B. "wedge")
    name     -- eindeutiger Name inkl. Parameter (str)
    params   -- dict der erzeugenden Parameter (in Strangbreiten w=1.0)
    polygon  -- shapely.geometry.Polygon

Alle Maße sind Vielfache der (noch unbekannten) Strangbreite w; w = 1.0
im gesamten Skript, siehe PLAN.md Abschnitt "Einheiten".
"""

from __future__ import annotations

import math

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

W = 1.0  # Strangbreite, normiert


# ---------------------------------------------------------------------------
# 1) Spitze Winkel: Keil-Polygone (Dreiecke) mit variablem Innenwinkel an der
#    Spitze. Schenkellaenge >= 20w, damit der Randeffekt nicht dominiert.
# ---------------------------------------------------------------------------

def wedge(angle_deg: float, leg_length: float = 25.0 * W) -> Polygon:
    """Isoceles Dreieck (Keil), Spitze im Ursprung, Innenwinkel = angle_deg."""
    half = math.radians(angle_deg) / 2.0
    apex = (0.0, 0.0)
    p1 = (leg_length * math.cos(half), leg_length * math.sin(half))
    p2 = (leg_length * math.cos(half), -leg_length * math.sin(half))
    return Polygon([apex, p1, p2])


def generate_wedges() -> list[dict]:
    out = []
    for angle in (90.0, 60.0, 45.0, 30.0, 15.0):
        poly = wedge(angle)
        out.append(
            {
                "family": "wedge",
                "name": f"wedge_{angle:g}deg",
                "params": {"angle_deg": angle, "leg_length_w": 25.0},
                "polygon": poly,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 1b) Spitze Winkel, Variante Reflex-Kerbe: V-Kerbe in dickem Material
#     (Wandecke von innen), Oeffnungswinkel = angle_deg. Ergaenzung zu
#     wedge() (konvexe Spitze): hier ist die Ecke am Kerbgrund REFLEX
#     (>180 Grad durchs Material gemessen) -- genau der Fall, in dem ein
#     Mitre-Join beim Erodieren einen "Spike" erzeugen kann (bei wedge()
#     hat mitre_limit dagegen keinen Einfluss, s. Protokoll).
# ---------------------------------------------------------------------------

def notch(angle_deg: float, leg_length: float = 25.0 * W, wall_span: float = 15.0 * W) -> Polygon:
    """Grosser Materialblock mit V-Kerbe (Oeffnungswinkel angle_deg) von unten."""
    big = box(-leg_length, -wall_span, leg_length, wall_span)
    half = math.radians(angle_deg) / 2.0
    depth = wall_span * 1.5
    apex = (0.0, 0.0)
    p1 = (-depth * math.sin(half), -depth * math.cos(half))
    p2 = (depth * math.sin(half), -depth * math.cos(half))
    cut_wedge = Polygon([apex, p2, p1])
    return big.difference(cut_wedge)


def generate_notches() -> list[dict]:
    out = []
    for angle in (90.0, 60.0, 45.0, 30.0, 15.0):
        poly = notch(angle)
        out.append(
            {
                "family": "notch",
                "name": f"notch_{angle:g}deg",
                "params": {"angle_deg": angle, "leg_length_w": 25.0, "wall_span_w": 15.0},
                "polygon": poly,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 2) Schmale Stege: Rechteck-Hanteln (zwei Pads, verbunden durch einen
#    schmalen Steg der Breite steg_width).
# ---------------------------------------------------------------------------

def dumbbell(steg_width: float, pad_size: float = 8.0 * W, gap: float = 6.0 * W) -> Polygon:
    """Zwei quadratische Pads, verbunden durch einen Steg der Breite steg_width."""
    half_pad = pad_size / 2.0
    half_steg = steg_width / 2.0
    left_pad = Polygon(
        [
            (-gap / 2.0 - pad_size, -half_pad),
            (-gap / 2.0, -half_pad),
            (-gap / 2.0, half_pad),
            (-gap / 2.0 - pad_size, half_pad),
        ]
    )
    right_pad = Polygon(
        [
            (gap / 2.0, -half_pad),
            (gap / 2.0 + pad_size, -half_pad),
            (gap / 2.0 + pad_size, half_pad),
            (gap / 2.0, half_pad),
        ]
    )
    steg = Polygon(
        [
            (-gap / 2.0, -half_steg),
            (gap / 2.0, -half_steg),
            (gap / 2.0, half_steg),
            (-gap / 2.0, half_steg),
        ]
    )
    merged = unary_union([left_pad, right_pad, steg])
    assert merged.geom_type == "Polygon", "Hantel-Konstruktion ergab keine einfache Flaeche"
    return merged


def generate_dumbbells() -> list[dict]:
    out = []
    for steg_width in (1.0, 1.5, 2.0, 2.5, 3.0):
        poly = dumbbell(steg_width * W)
        out.append(
            {
                "family": "dumbbell",
                "name": f"dumbbell_steg{steg_width:g}w",
                "params": {"steg_width_w": steg_width},
                "polygon": poly,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 3) Enge Innenradien: L-foermige Wandecke mit gerundetem Innen-(Reflex-)eck.
# ---------------------------------------------------------------------------

def rounded_inner_corner(radius: float, arm_len: float = 15.0 * W, thickness: float = 6.0 * W) -> Polygon:
    """L-Winkel (zwei Waende, Dicke `thickness`), Innenecke mit `radius` gerundet.

    Konstruktion: L-Form als Vereinigung zweier Rechtecke, Innenecke wird durch
    Vereinigung mit einer Kreisscheibe am urspruenglichen Eckpunkt gerundet
    (fuellt die Kerbe bis zum Radius auf -- klassische Eckenverrundung).
    """
    horiz = Polygon([(0, 0), (arm_len, 0), (arm_len, thickness), (0, thickness)])
    vert = Polygon([(0, 0), (thickness, 0), (thickness, arm_len), (0, arm_len)])
    parts = [horiz, vert]
    if radius > 0:
        fillet = Point(thickness, thickness).buffer(radius, quad_segs=32)
        parts.append(fillet)
    merged = unary_union(parts)
    assert merged.geom_type == "Polygon", "L-Ecken-Konstruktion ergab keine einfache Flaeche"
    return merged


def generate_rounded_corners() -> list[dict]:
    out = []
    for radius in (0.5, 1.0, 2.0, 3.0):
        poly = rounded_inner_corner(radius * W)
        out.append(
            {
                "family": "rounded_corner",
                "name": f"corner_r{radius:g}w",
                "params": {"radius_w": radius, "thickness_w": 6.0, "arm_len_w": 15.0},
                "polygon": poly,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 4) T-Stoesse: T-foermige Wandkreuzung, Flanschdicke variabel.
# ---------------------------------------------------------------------------

def t_joint(
    flange_thickness: float,
    stem_width: float = 6.0 * W,
    flange_half_len: float = 15.0 * W,
    stem_height: float = 15.0 * W,
) -> Polygon:
    """Flansch (horizontale Wand, Dicke flange_thickness) mit Steg (Stem) mittig."""
    flange = Polygon(
        [
            (-flange_half_len, 0),
            (flange_half_len, 0),
            (flange_half_len, flange_thickness),
            (-flange_half_len, flange_thickness),
        ]
    )
    stem = Polygon(
        [
            (-stem_width / 2.0, flange_thickness),
            (stem_width / 2.0, flange_thickness),
            (stem_width / 2.0, flange_thickness + stem_height),
            (-stem_width / 2.0, flange_thickness + stem_height),
        ]
    )
    merged = unary_union([flange, stem])
    assert merged.geom_type == "Polygon", "T-Stoss-Konstruktion ergab keine einfache Flaeche"
    return merged


def generate_t_joints() -> list[dict]:
    out = []
    for flange_thickness in (2.0, 3.0, 4.0):
        poly = t_joint(flange_thickness * W)
        out.append(
            {
                "family": "t_joint",
                "name": f"tjoint_flansch{flange_thickness:g}w",
                "params": {
                    "flange_thickness_w": flange_thickness,
                    "stem_width_w": 6.0,
                },
                "polygon": poly,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 5) Realitaetsnah: Wandsegment-Rechteck als Kontrollkontur.
# ---------------------------------------------------------------------------

def wall_segment(length: float = 30.0 * W, width: float = 3.0 * W) -> Polygon:
    return Polygon([(0, 0), (length, 0), (length, width), (0, width)])


def generate_wall_segments() -> list[dict]:
    out = []
    for width in (2.0, 3.0, 4.0):
        poly = wall_segment(width=width * W)
        out.append(
            {
                "family": "wall_segment",
                "name": f"wallsegment_w{width:g}w",
                "params": {"length_w": 30.0, "width_w": width},
                "polygon": poly,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def get_all_contours() -> list[dict]:
    contours: list[dict] = []
    contours.extend(generate_wedges())
    contours.extend(generate_notches())
    contours.extend(generate_dumbbells())
    contours.extend(generate_rounded_corners())
    contours.extend(generate_t_joints())
    contours.extend(generate_wall_segments())
    return contours


if __name__ == "__main__":
    cs = get_all_contours()
    print(f"{len(cs)} Testkonturen erzeugt:")
    for c in cs:
        p = c["polygon"]
        print(
            f"  [{c['family']:>14s}] {c['name']:<28s} "
            f"area={p.area:8.2f}  valid={p.is_valid}  simple={p.geom_type == 'Polygon'}"
        )
