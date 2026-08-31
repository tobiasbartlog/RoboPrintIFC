"""Tests fuer Basis-Bohrbild-Erkennung + -Abgleich (Issue #78, ADR-006, ADR-013).

Prueft:
- robot.base_mount: Schema + RobotDef.load (M1013 traegt das provisorische 4-Loch-Bild)
- detect_holes_on_top_face: findet die Bohrungen einer Testplatte (Radius/Zentren)
- match_base_mount: Abgleich gegen das M1013-Template (Translation + Rotation),
  Radius-Toleranz (Workstation-Radius darf leicht abweichen), Nicht-Treffer -> None
- base_mount_to_frame: der Frame reproduziert die erkannten Loecher (w-first Einheitsquat)
- Aktion + API POST /workstations/{name}/detect-base-holes (200/404/422, Befund kein Gate)

Die Testplatte wird als **vertikale Wandbaender** gebaut (aussen Rechteck, innen die
Loch-Zylinder) statt via ``trimesh.creation.extrude_polygon`` — letzteres braucht eine
Triangulations-Engine (mapbox_earcut/manifold3d/triangle), die in dieser Umgebung nicht
installiert ist. Fuers horizontale Sectioning zaehlen nur die vertikalen Waende
(die Deckflaechen schneidet die horizontale Ebene ohnehin nicht), also ist die
Wandbaender-Platte fuer die Erkennung aequivalent und voellig deterministisch.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from fgc.domain.robot import RobotDef
from fgc.geometry.holes import (
    apply_frame,
    base_mount_to_frame,
    detect_holes_on_top_face,
    match_base_mount,
)
from fgc.pipeline.actions import create_workstation, detect_workstation_base_holes
from fgc.pipeline.api import app

# M1013-Template-Werte (aus robots/doosan_m1013.json base_mount).
_TEMPLATE_POSITIONS = [(75.0, 75.0), (-75.0, 75.0), (-75.0, -75.0), (75.0, -75.0)]
_TEMPLATE_RADIUS = 4.5  # hole_diameter_mm 9.0 / 2


# ---------------------------------------------------------------------------
# Testplatten-Bau (vertikale Wandbaender)
# ---------------------------------------------------------------------------


def _band(loop: list[tuple[float, float]], z0: float, z1: float):
    """Vertikales Wandband fuer einen geschlossenen 2D-Ring -> (verts, faces)."""
    n = len(loop)
    verts = []
    for x, y in loop:
        verts.append([x, y, z0])
        verts.append([x, y, z1])
    faces = []
    for i in range(n):
        a, b = 2 * i, 2 * i + 1
        c, d = 2 * ((i + 1) % n), 2 * ((i + 1) % n) + 1
        faces.append([a, b, d])
        faces.append([a, d, c])
    return np.array(verts, dtype=float), np.array(faces, dtype=int)


def _circle(cx: float, cy: float, r: float, n: int = 48) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))
        for k in range(n)
    ]


def _plate_mesh(
    *,
    offset: tuple[float, float] = (0.0, 0.0),
    thickness: float = 20.0,
    half: float = 120.0,
    hole_radius: float = 5.0,
    hole_centers: list[tuple[float, float]] | None = None,
    rotation_deg: float = 0.0,
) -> trimesh.Trimesh:
    """Baut eine Platte (Rechteck) mit runden Bohrungen als vertikale Wandbaender.

    ``hole_centers`` sind relativ zum Plattenmittelpunkt; sie werden um ``rotation_deg``
    (um den Mittelpunkt) gedreht und um ``offset`` verschoben — so testen wir Translation
    **und** Rotation. Ohne Angabe die vier M1013-Template-Positionen (±75, ±75).
    """
    ox, oy = offset
    if hole_centers is None:
        hole_centers = list(_TEMPLATE_POSITIONS)
    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    rect = [
        (-half + ox, -half + oy),
        (half + ox, -half + oy),
        (half + ox, half + oy),
        (-half + ox, half + oy),
    ]
    loops = [rect]
    for hx, hy in hole_centers:
        rx = cos_t * hx - sin_t * hy
        ry = sin_t * hx + cos_t * hy
        loops.append(_circle(rx + ox, ry + oy, hole_radius))

    all_v, all_f, off = [], [], 0
    for loop in loops:
        v, f = _band(loop, 0.0, thickness)
        all_v.append(v)
        all_f.append(f + off)
        off += len(v)
    return trimesh.Trimesh(
        vertices=np.vstack(all_v), faces=np.vstack(all_f), process=False
    )


def _plate_stl_bytes(**kwargs) -> bytes:
    data = _plate_mesh(**kwargs).export(file_type="stl")
    return data if isinstance(data, bytes) else data.encode("utf-8")


# ---------------------------------------------------------------------------
# robot.base_mount: Schema + Laden
# ---------------------------------------------------------------------------


def test_m1013_base_mount_loads() -> None:
    """Der M1013 laedt weiterhin und traegt das provisorische 4-Loch-Basis-Bohrbild."""
    rd = RobotDef.load("doosan_m1013")
    assert rd.base_mount is not None
    assert rd.base_mount["hole_count"] == 4
    assert rd.base_mount["hole_diameter_mm"] == 9.0
    assert rd.base_mount["provisional"] is True
    positions = [tuple(p) for p in rd.base_mount["hole_positions_mm"]]
    assert set(positions) == {(75, 75), (-75, 75), (-75, -75), (75, -75)}
    # Regression: die uebrigen Kennwerte bleiben unveraendert.
    assert rd.reach_mm == 1300
    assert rd.kinematics is not None


# ---------------------------------------------------------------------------
# Detektion
# ---------------------------------------------------------------------------


def test_detect_finds_four_holes_with_offset() -> None:
    """Vier Bohrungen einer verschobenen Platte werden nach Radius + Zentrum erkannt."""
    ox, oy, r = 30.0, -20.0, 5.0
    mesh = _plate_mesh(offset=(ox, oy), hole_radius=r)
    holes = detect_holes_on_top_face(mesh)
    assert len(holes) == 4

    for h in holes:
        assert h.radius_mm == pytest.approx(r, abs=0.15)
        assert h.center_mm[2] == pytest.approx(20.0)  # z_top
        assert h.normal == (0.0, 0.0, 1.0)

    centers = {(round(h.center_mm[0]), round(h.center_mm[1])) for h in holes}
    expected = {(round(ox + hx), round(oy + hy)) for hx, hy in _TEMPLATE_POSITIONS}
    assert centers == expected


def test_detect_empty_on_solid_box() -> None:
    """Eine Platte ohne Bohrungen (nur Aussenwand) liefert keine Loecher."""
    mesh = _plate_mesh(hole_centers=[])
    assert detect_holes_on_top_face(mesh) == []


# ---------------------------------------------------------------------------
# Abgleich (match_base_mount)
# ---------------------------------------------------------------------------


def _m1013_base_mount() -> dict:
    return RobotDef.load("doosan_m1013").base_mount  # type: ignore[return-value]


def test_match_template_translation() -> None:
    """Der M1013-Abgleich findet die Platte, Zentrum ≈ Plattenmittelpunkt, kleiner RMS."""
    ox, oy = 30.0, -20.0
    mesh = _plate_mesh(offset=(ox, oy), hole_radius=5.0)
    holes = detect_holes_on_top_face(mesh)
    match = match_base_mount(holes, _m1013_base_mount())
    assert match is not None
    assert match.center_mm[0] == pytest.approx(ox, abs=0.2)
    assert match.center_mm[1] == pytest.approx(oy, abs=0.2)
    assert match.center_mm[2] == pytest.approx(20.0)
    assert match.rms_mm < 0.5
    assert len(match.matched_holes) == 4


def test_match_radius_tolerance_allows_slightly_larger() -> None:
    """Ein Bohrradius 6.0 (Template 4.5) matcht noch (Radius darf leicht abweichen)."""
    mesh = _plate_mesh(offset=(10.0, 10.0), hole_radius=6.0)
    holes = detect_holes_on_top_face(mesh)
    match = match_base_mount(holes, _m1013_base_mount())
    assert match is not None  # |6.0 - 4.5| = 1.5 <= radius_tol 2.0


def test_match_radius_far_off_does_not_match() -> None:
    """Ein Bohrradius 20 (weit weg von 4.5) matcht nicht (kein Kandidat)."""
    mesh = _plate_mesh(offset=(10.0, 10.0), hole_radius=20.0)
    holes = detect_holes_on_top_face(mesh)
    assert match_base_mount(holes, _m1013_base_mount()) is None


def test_match_three_holes_returns_none() -> None:
    """Nur drei Bohrungen -> kein 4-Loch-Bild -> None (kein Absturz)."""
    mesh = _plate_mesh(hole_centers=[(75, 75), (-75, 75), (-75, -75)], hole_radius=5.0)
    holes = detect_holes_on_top_face(mesh)
    assert len(holes) == 3
    assert match_base_mount(holes, _m1013_base_mount()) is None


def test_match_wrong_arrangement_returns_none() -> None:
    """Vier Bohrungen in nicht passender Anordnung (kleines Quadrat) -> None."""
    mesh = _plate_mesh(
        hole_centers=[(40, 40), (-40, 40), (-40, -40), (40, -40)], hole_radius=5.0
    )
    holes = detect_holes_on_top_face(mesh)
    assert len(holes) == 4
    assert match_base_mount(holes, _m1013_base_mount()) is None


# ---------------------------------------------------------------------------
# base_mount_to_frame (Rotation + Position, Quaternion-Konvention)
# ---------------------------------------------------------------------------


def _assert_frame_reproduces_holes(frame: dict, match, template_positions) -> None:
    """Der Frame, auf die Template-Positionen angewendet, trifft die erkannten Loecher."""
    detected = [np.array(h.center_mm) for h in match.matched_holes]
    for tx, ty in template_positions:
        world = apply_frame(frame, [tx, ty, 0.0])
        assert any(np.linalg.norm(world - d) < 0.5 for d in detected), (
            f"Template ({tx},{ty}) -> {world} traf kein erkanntes Loch"
        )


def test_frame_reproduces_holes_and_is_unit_wfirst() -> None:
    """Der Frame reproduziert die erkannten Loecher; Quat ist Einheits-w-first.

    Der Ursprung liegt im Loch-Zentroid. Die Drehung um die Normale ist bei einem
    4-fach symmetrischen Quadrat nur mod 90 Grad bestimmt (jede 90-Grad-Drehung bildet
    das Bohrbild auf sich ab) — verbindlich ist, dass der Frame die Loecher trifft.
    """
    ox, oy = 30.0, -20.0
    mesh = _plate_mesh(offset=(ox, oy), hole_radius=5.0)
    holes = detect_holes_on_top_face(mesh)
    match = match_base_mount(holes, _m1013_base_mount())
    assert match is not None
    frame = base_mount_to_frame(match)

    # w-first Einheitsquaternion (ADR-006).
    assert len(frame["quat"]) == 4
    assert np.linalg.norm(frame["quat"]) == pytest.approx(1.0, abs=1e-6)
    assert frame["pos_mm"][0] == pytest.approx(ox, abs=0.2)
    assert frame["pos_mm"][1] == pytest.approx(oy, abs=0.2)
    assert frame["pos_mm"][2] == pytest.approx(20.0, abs=0.2)
    _assert_frame_reproduces_holes(frame, match, _TEMPLATE_POSITIONS)


def test_frame_reproduces_rotated_holes() -> None:
    """Bei gedrehtem Bohrbild traegt der Frame die Drehung; Anwenden trifft die Loecher."""
    ox, oy, rot = 15.0, 40.0, 30.0
    mesh = _plate_mesh(offset=(ox, oy), hole_radius=5.0, rotation_deg=rot)
    holes = detect_holes_on_top_face(mesh)
    match = match_base_mount(holes, _m1013_base_mount())
    assert match is not None
    # rotation_deg ist bis auf die 4-fach-Symmetrie des Quadrats bestimmt (mod 90).
    assert match.rotation_deg % 90 == pytest.approx(rot % 90, abs=0.5) or (
        90 - (match.rotation_deg % 90)
    ) == pytest.approx(rot % 90, abs=0.5)

    frame = base_mount_to_frame(match)
    assert np.linalg.norm(frame["quat"]) == pytest.approx(1.0, abs=1e-6)
    _assert_frame_reproduces_holes(frame, match, _TEMPLATE_POSITIONS)


# ---------------------------------------------------------------------------
# Aktion detect_workstation_base_holes
# ---------------------------------------------------------------------------


def test_action_matched(tmp_path: Path) -> None:
    """Aktion gegen eine Workstation mit passender Platte -> matched + robot_base_frame."""
    create_workstation(
        "plate ws",
        "stationary",
        False,
        base_heights_mm=[0.0],
        mesh_bytes=_plate_stl_bytes(offset=(30.0, -20.0), hole_radius=5.0),
        mesh_filename="plate.stl",
        workstations_dir=tmp_path,
    )
    result = detect_workstation_base_holes(
        "plate_ws", "doosan_m1013", workstations_dir=tmp_path
    )
    assert result.matched is True
    assert result.robot_base_frame is not None
    assert len(result.detected_holes) == 4
    assert result.warnings == []


def test_action_no_match_is_finding_not_error(tmp_path: Path) -> None:
    """Keine passende Anordnung -> matched=False mit Warnung (Befund, kein Fehler)."""
    create_workstation(
        "small ws",
        "stationary",
        False,
        base_heights_mm=[0.0],
        mesh_bytes=_plate_stl_bytes(
            hole_centers=[(40, 40), (-40, 40), (-40, -40), (40, -40)], hole_radius=5.0
        ),
        mesh_filename="plate.stl",
        workstations_dir=tmp_path,
    )
    result = detect_workstation_base_holes(
        "small_ws", "doosan_m1013", workstations_dir=tmp_path
    )
    assert result.matched is False
    assert result.robot_base_frame is None
    assert result.warnings and "kein passendes" in result.warnings[0]


def test_action_without_mesh_raises(tmp_path: Path) -> None:
    """Workstation ohne Mesh -> ValueError (Erkennung braucht ein Mesh)."""
    create_workstation(
        "nomesh", "stationary", False, base_heights_mm=[0.0], workstations_dir=tmp_path
    )
    with pytest.raises(ValueError, match="kein Mesh"):
        detect_workstation_base_holes("nomesh", "doosan_m1013", workstations_dir=tmp_path)


def test_action_unknown_workstation_raises(tmp_path: Path) -> None:
    """Unbekannte Workstation -> FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        detect_workstation_base_holes("ghost", "doosan_m1013", workstations_dir=tmp_path)


# ---------------------------------------------------------------------------
# API POST /workstations/{name}/detect-base-holes
# ---------------------------------------------------------------------------


def test_api_detect_happy_path(tmp_path: Path, monkeypatch) -> None:
    """POST detect-base-holes -> 200 matched True mit robot_base_frame (w-first Quat)."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    create_workstation(
        "plate ws",
        "stationary",
        False,
        base_heights_mm=[0.0],
        mesh_bytes=_plate_stl_bytes(offset=(30.0, -20.0), hole_radius=5.0),
        mesh_filename="plate.stl",
        workstations_dir=tmp_path,
    )
    client = TestClient(app)
    resp = client.post(
        "/workstations/plate_ws/detect-base-holes", json={"robot": "doosan_m1013"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["matched"] is True
    assert body["robot_base_frame"] is not None
    quat = body["robot_base_frame"]["quat"]
    assert len(quat) == 4
    assert sum(c * c for c in quat) == pytest.approx(1.0, abs=1e-6)
    assert len(body["detected_holes"]) == 4
    assert body["warnings"] == []


def test_api_detect_no_mesh_422(tmp_path: Path, monkeypatch) -> None:
    """Workstation ohne Mesh -> 422."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    create_workstation(
        "nomesh", "stationary", False, base_heights_mm=[0.0], workstations_dir=tmp_path
    )
    client = TestClient(app)
    resp = client.post(
        "/workstations/nomesh/detect-base-holes", json={"robot": "doosan_m1013"}
    )
    assert resp.status_code == 422


def test_api_detect_unknown_workstation_404(tmp_path: Path, monkeypatch) -> None:
    """Unbekannte Workstation -> 404."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/workstations/ghost/detect-base-holes", json={"robot": "doosan_m1013"}
    )
    assert resp.status_code == 404


def test_api_detect_unknown_robot_404(tmp_path: Path, monkeypatch) -> None:
    """Unbekannter Roboter -> 404 (Mesh ok, aber Roboterdefinition fehlt)."""
    monkeypatch.setattr("fgc.paths.WORKSTATIONS_DIR", tmp_path)
    create_workstation(
        "plate ws",
        "stationary",
        False,
        base_heights_mm=[0.0],
        mesh_bytes=_plate_stl_bytes(offset=(0.0, 0.0), hole_radius=5.0),
        mesh_filename="plate.stl",
        workstations_dir=tmp_path,
    )
    client = TestClient(app)
    resp = client.post(
        "/workstations/plate_ws/detect-base-holes", json={"robot": "ghost_robot"}
    )
    assert resp.status_code == 404
