"""Bohrbild-Erkennung + -Abgleich fuer die Roboterbasis (Issue #78, ADR-006, ADR-013).

Erkennt Durchgangsbohrungen auf der oberen Montageflaeche eines Workstation-Meshes
und gleicht sie gegen das (PROVISORISCHE) Basis-Bohrbild eines Roboters
(``robot.base_mount``) ab. Rein geometrisch (trimesh/shapely/numpy) — kennt weder
FastAPI noch die Domaenen-Objekte, analog ``fgc.geometry.section``.

**Befund, kein Gate (ADR-013):** findet sich kein passendes Bild, gibt es einen
klaren Befund (``match_base_mount`` liefert ``None``), keinen Fehler — die Basis
kann weiterhin manuell per Flaechen-Klick gesetzt werden.

**Provisorisch:** das M1013-Bohrbild stammt aus dem Herstellerhandbuch (gegen das
gevendorte Mesh abgeglichen); die Toleranzen sind grosszuegig gewaehlt.

Frame-Konvention (ADR-006, w-first): :func:`base_mount_to_frame` liefert das
``robot_base_frame`` **identisch** zur Viewer-Seite (``mountBaseToSurface``):
Basis-+z-Achse -> Flaechennormale, Ursprung im Loch-Zentroid, Drehung um die
Normale, ``q = spin ∘ align`` (erst ausrichten, dann um die Normale drehen). So
sind ein Mesh-erkannter Snap und ein manueller Flaechen-Pick kompatibel.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np

#: Numerische Schwelle (Grad-Vergleiche, Nullvektoren), analog face-align (Viewer).
_EPS = 1e-9


@dataclass(frozen=True)
class DetectedHole:
    """Eine erkannte Durchgangsbohrung auf der Montageflaeche (Welt-mm, ADR-006).

    ``center_mm`` ist der 3D-Lochmittelpunkt (x, y in Welt, z = Flaechenhoehe),
    ``radius_mm`` der gefittete Radius, ``normal`` die Flaechennormale (v1: ``[0,0,1]``).
    """

    center_mm: tuple[float, float, float]
    radius_mm: float
    normal: tuple[float, float, float]


@dataclass(frozen=True)
class BaseMountMatch:
    """Ergebnis eines erfolgreichen Bohrbild-Abgleichs (:func:`match_base_mount`).

    ``center_mm`` ist der Zentroid der zugeordneten erkannten Loecher (z auf der
    Flaeche), ``normal`` die Flaechennormale, ``rotation_deg`` die Drehung um die
    Normale, die das Template auf die erkannten Loecher abbildet, ``matched_holes``
    die zugeordneten Loecher und ``rms_mm`` der Rest-Abgleichsfehler.
    """

    center_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    rotation_deg: float
    matched_holes: list[DetectedHole]
    rms_mm: float


# ---------------------------------------------------------------------------
# Quaternion-Helfer (numpy, w-first) — identisch zur Viewer-Konvention (face-align.ts)
# ---------------------------------------------------------------------------


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    return v / n if n > _EPS else v


def _quat_axis_angle(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    """Quaternion [w,x,y,z] aus Einheitsachse + Winkel (rad)."""
    a = _normalize(axis)
    h = angle_rad / 2.0
    s = math.sin(h)
    return np.array([math.cos(h), a[0] * s, a[1] * s, a[2] * s], dtype=float)


def quat_about(axis: np.ndarray | list[float], angle_deg: float) -> np.ndarray:
    """Quaternion [w,x,y,z] fuer eine Drehung um ``axis`` um ``angle_deg`` Grad."""
    return _quat_axis_angle(np.asarray(axis, dtype=float), math.radians(angle_deg))


def quat_between(a: np.ndarray | list[float], b: np.ndarray | list[float]) -> np.ndarray:
    """Kuerzeste Rotation, die ``a`` auf ``b`` dreht (Quaternion [w,x,y,z]).

    Behandelt den Antiparallel-Fall (180 Grad) mit einer stabilen senkrechten
    Achse — identisch zu ``quatBetween`` im Viewer (face-align.ts).
    """
    f = _normalize(np.asarray(a, dtype=float))
    t = _normalize(np.asarray(b, dtype=float))
    d = float(np.dot(f, t))
    if d >= 1.0 - _EPS:
        return np.array([1.0, 0.0, 0.0, 0.0])
    if d <= -1.0 + _EPS:
        axis = np.cross(f, [1.0, 0.0, 0.0])
        if float(np.linalg.norm(axis)) < _EPS:
            axis = np.cross(f, [0.0, 1.0, 0.0])
        return _quat_axis_angle(axis, math.pi)
    axis = np.cross(f, t)
    return _quat_axis_angle(axis, math.acos(max(-1.0, min(1.0, d))))


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton-Produkt: ``quat_mul(a, b)`` wendet erst ``b``, dann ``a`` an."""
    aw, ax, ay, az = (float(x) for x in a)
    bw, bx, by, bz = (float(x) for x in b)
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        dtype=float,
    )


def quat_rotate(q: np.ndarray, v: np.ndarray | list[float]) -> np.ndarray:
    """Dreht Vektor ``v`` mit dem Quaternion ``q`` (v' = q · v · q⁻¹)."""
    q = np.asarray(q, dtype=float)
    vv = np.asarray(v, dtype=float)
    u = q[1:]
    t = 2.0 * np.cross(u, vv)
    return vv + q[0] * t + np.cross(u, t)


def apply_frame(frame: dict, point: np.ndarray | list[float]) -> np.ndarray:
    """Wendet einen Frame ``{pos_mm, quat}`` (Rotation + Translation) auf ``point`` an."""
    r = quat_rotate(np.asarray(frame["quat"], dtype=float), point)
    return r + np.asarray(frame["pos_mm"], dtype=float)


# ---------------------------------------------------------------------------
# Detektion: Loecher auf der oberen Montageflaeche
# ---------------------------------------------------------------------------


def _ring_to_world_xy(coords_2d: np.ndarray, to_3d: np.ndarray) -> np.ndarray:
    """Path2D-Ringkoordinaten zurueck in Welt-XY (der Schnitt ist horizontal).

    Spiegelt ``fgc.geometry.section._to_world_xy`` — nutzt die von ``to_2D()``
    gelieferte 4x4-Ruecktransformation.
    """
    pts = np.asarray(coords_2d, dtype=float)
    homogeneous = np.column_stack([pts, np.zeros(len(pts)), np.ones(len(pts))])
    world = (to_3d @ homogeneous.T).T
    return world[:, :2]


def detect_holes_on_top_face(mesh) -> list[DetectedHole]:
    """Erkennt Durchgangsbohrungen auf der obersten horizontalen Flaeche von ``mesh``.

    v1-Annahme: der Roboter montiert auf einer **horizontalen** oberen Flaeche. Die
    Montageebene liegt bei ``z_top = mesh.bounds[1][2]`` mit Normale ``[0,0,1]``. Wir
    schneiden das Mesh mit einer horizontalen Ebene knapp **unter** der Oberkante
    (``z_top - eps``, ``eps = min(2.0, Dicke*0.25)``) — dieselbe Schnitt-/``to_2D()``-
    Mechanik wie ``fgc.geometry.section`` — und lesen aus jedem gefuellten Polygon die
    ``interiors`` (Loecher). Je Loch wird ein Kreis gefittet: Zentrum = Ringmittel
    (Mittel der Koordinaten), Radius = mittlerer Abstand der Ringpunkte zum Zentrum.
    Das 2D-Zentrum wird nach Welt-XY zurueckgerechnet, ``z = z_top``, ``normal = [0,0,1]``.

    LIMITIERUNG: nur horizontale Oberflaechen; eine schraege Montageflaeche wird (noch)
    nicht erkannt — der Viewer kann spaeter eine explizite Flaeche uebergeben. Leerer
    Schnitt / keine ``interiors`` -> leere Liste.
    """
    z_top = float(mesh.bounds[1][2])
    z_bottom = float(mesh.bounds[0][2])
    thickness = z_top - z_bottom
    eps = min(2.0, thickness * 0.25) if thickness > _EPS else 1.0
    center = mesh.bounds.mean(axis=0)

    section = mesh.section(
        plane_origin=[float(center[0]), float(center[1]), z_top - eps],
        plane_normal=[0.0, 0.0, 1.0],
    )
    if section is None:
        return []

    planar, to_3d = section.to_2D()
    holes: list[DetectedHole] = []
    for poly in planar.polygons_full:
        if poly is None or poly.is_empty:
            continue
        for interior in poly.interiors:
            coords = np.asarray(interior.coords, dtype=float)
            if len(coords) >= 2 and np.allclose(coords[0], coords[-1]):
                coords = coords[:-1]  # geschlossenen Ring entdoppeln
            if len(coords) < 3:
                continue
            world = _ring_to_world_xy(coords, to_3d)
            center_xy = world.mean(axis=0)
            radius = float(np.mean(np.linalg.norm(world - center_xy, axis=1)))
            holes.append(
                DetectedHole(
                    center_mm=(float(center_xy[0]), float(center_xy[1]), z_top),
                    radius_mm=radius,
                    normal=(0.0, 0.0, 1.0),
                )
            )
    return holes


# ---------------------------------------------------------------------------
# Abgleich: erkannte Loecher gegen das Roboter-Bohrbild (2D-Starrtransform)
# ---------------------------------------------------------------------------


def _best_rotation_rms(
    template_centered: np.ndarray, detected_centered: np.ndarray
) -> tuple[float, float]:
    """Beste 2D-Rotation (ohne Spiegelung/Skalierung), die Template auf Detektion legt.

    Analytisches Procrustes fuer den planaren Fall: ``theta = atan2(sum p×q, sum p·q)``
    (p = Template, q = Detektion, beide um ihren Zentroid zentriert). Liefert
    ``(theta_rad, rms_mm)`` fuer die gegebene Zuordnung (Reihenfolge = Korrespondenz).
    """
    p = template_centered
    q = detected_centered
    cross = float(np.sum(p[:, 0] * q[:, 1] - p[:, 1] * q[:, 0]))
    dot = float(np.sum(p[:, 0] * q[:, 0] + p[:, 1] * q[:, 1]))
    theta = math.atan2(cross, dot)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rot = np.array([[cos_t, -sin_t], [sin_t, cos_t]])
    residual = (rot @ p.T).T - q
    rms = float(np.sqrt(np.mean(np.sum(residual**2, axis=1))))
    return theta, rms


def match_base_mount(
    holes: list[DetectedHole],
    base_mount: dict,
    *,
    radius_tol_mm: float = 2.0,
    position_tol_mm: float = 6.0,
) -> BaseMountMatch | None:
    """Sucht im erkannten Bohrbild die Roboter-Basis (``base_mount``) — 2D-Starrtransform.

    ``base_mount`` ist das rohe Roboter-Dict (``hole_count``, ``hole_diameter_mm``,
    ``hole_positions_mm``). Vorgehen:

    1. Loecher nach Radius filtern: nur solche im Fenster ``|r - template_r| <=
       radius_tol_mm`` (der Workstation-Radius darf leicht abweichen — daher
       grosszuegige Default-Toleranz 2.0 mm).
    2. Eine Teilmenge von ``hole_count`` gefilterten Loechern suchen, deren planare
       (x,y)-Anordnung dem Template bis auf eine **2D-Starrtransform** (Translation +
       Drehung um die Normale; **keine** Skalierung, **keine** Spiegelung) innerhalb
       ``position_tol_mm`` gleicht. Korrespondenzen werden per Brute-Force durchprobiert
       (fuer Anzahl 4 winzig: 4! = 24) und je Zuordnung das analytische 2D-Procrustes
       gerechnet; die Kombination mit minimalem RMS ``<= position_tol_mm`` gewinnt.

    Erfolg -> :class:`BaseMountMatch`. Kein passendes Bild -> ``None`` (Befund, kein
    Gate, ADR-013).
    """
    template = np.array([[float(x), float(y)] for x, y in base_mount["hole_positions_mm"]])
    hole_count = int(base_mount["hole_count"])
    template_radius = float(base_mount["hole_diameter_mm"]) / 2.0

    # Template darf mehr/weniger Positionen fuehren als hole_count nennt — hole_count
    # ist die Wahrheit fuer die zu findende Loecher-Zahl; wir nutzen die gefuehrten
    # Positionen (in der Regel genau hole_count Stueck).
    if len(template) < hole_count:
        hole_count = len(template)
    if hole_count < 1:
        return None

    candidates = [h for h in holes if abs(h.radius_mm - template_radius) <= radius_tol_mm]
    if len(candidates) < hole_count:
        return None

    template_centroid = template.mean(axis=0)
    template_centered = template - template_centroid

    best: tuple[float, np.ndarray, float, list[DetectedHole]] | None = None
    perms = list(itertools.permutations(range(hole_count)))
    for combo in itertools.combinations(candidates, hole_count):
        detected = np.array([[h.center_mm[0], h.center_mm[1]] for h in combo])
        detected_centroid = detected.mean(axis=0)
        detected_centered = detected - detected_centroid
        for perm in perms:
            reordered = template_centered[list(perm)]
            theta, rms = _best_rotation_rms(reordered, detected_centered)
            if rms <= position_tol_mm and (best is None or rms < best[0]):
                best = (rms, detected_centroid, math.degrees(theta), list(combo))

    if best is None:
        return None

    rms, detected_centroid, rotation_deg, matched = best
    z_top = float(matched[0].center_mm[2])
    return BaseMountMatch(
        center_mm=(float(detected_centroid[0]), float(detected_centroid[1]), z_top),
        normal=(0.0, 0.0, 1.0),
        rotation_deg=rotation_deg,
        matched_holes=matched,
        rms_mm=rms,
    )


def base_mount_to_frame(match: BaseMountMatch) -> dict:
    """Baut aus einem :class:`BaseMountMatch` das ``robot_base_frame`` (ADR-006, w-first).

    Die Roboterbasis sitzt **auf** der Flaeche: die Basis-+z-Achse zeigt entlang der
    Normale (nach oben), der Ursprung liegt im Loch-Zentroid, gedreht um
    ``rotation_deg`` um die Normale. Quaternion: ``align = quat_between([0,0,1], normal)``,
    ``spin = quat_about(normal, rotation_deg)``, ``q = spin ∘ align`` (Drehung in der
    Welt-/Ebenen-Ebene). Rueckgabe: w-first Einheitsquaternion — **identisch** zur
    Viewer-Konvention (``mountBaseToSurface``), damit Mesh-Snap und Flaechen-Pick
    kompatible Frames erzeugen.
    """
    normal = np.asarray(match.normal, dtype=float)
    align = quat_between([0.0, 0.0, 1.0], normal)
    spin = quat_about(normal, match.rotation_deg)
    q = _normalize(quat_mul(spin, align))
    return {
        "pos_mm": [float(c) for c in match.center_mm],
        "quat": [float(x) for x in q],
    }
