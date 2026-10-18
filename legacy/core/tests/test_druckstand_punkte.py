"""DruckstandPunkte: wachsender Druckstand als Punktwolke (PRD #183 AP 1, Issue #208).

Prüft das reine Punktwolken-Modul :mod:`fgc.collision.druckstand_punkte`: Anhängen
je Schicht ist bit-identisch zum direkten Vorspulen (Abnahme 1), der
Punktabstand bleibt deutlich unter dem Sicherheitsabstand (Abnahme 2), statische
Hindernisse laufen im selben Vertrag wie das FCL-Backend (Abnahme 3, US 15) und
die Quell-Naht zu ``DruckstandSpec`` (#192) liefert dieselben Eingaben.
"""

from __future__ import annotations

import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon

from fgc.collision import druckstand as ds
from fgc.collision import druckstand_punkte as dp
from fgc.collision.check import DEFAULT_SAFETY_DISTANCE_MM

FOOTPRINT = (Polygon([(-400, -120), (400, -120), (400, 120), (-400, 120)]),)


def _floor() -> trimesh.Trimesh:
    f = trimesh.creation.box(extents=[6000, 6000, 200])
    f.apply_translation([0, 0, -100])
    return f


def _spec(**over) -> dp.DruckstandPunkteSpec:
    base = dict(
        footprint=FOOTPRINT,
        layer_height_mm=10.0,
        n_layers=20,
        z_base_mm=0.0,
        point_spacing_mm=25.0,  # gröber als der Default, hält die Tests schnell
    )
    base.update(over)
    return dp.DruckstandPunkteSpec(**base)


# --- Abnahme 1: Anhängen ist bit-identisch zum frischen Aufbau ---------------


def test_stepwise_advance_matches_direct_jump_bit_identical() -> None:
    """Schicht für Schicht anhängen ergibt exakt dieselbe Punktmenge wie ein
    direkter Sprung auf dieselbe Ziel-Schicht (Issue #208, Abnahme 1)."""
    spec = _spec()

    stepwise = dp.DruckstandPunkte(spec)
    for layer in range(1, 16):
        stepwise.advance_layer(layer)

    direct = dp.DruckstandPunkte(spec)
    direct.advance_layer(15)

    np.testing.assert_array_equal(stepwise.growing_points_mm, direct.growing_points_mm)
    np.testing.assert_array_equal(stepwise.points_mm, direct.points_mm)


def test_advance_out_of_order_calls_are_still_bit_identical() -> None:
    """Auch bei ungünstiger Aufrufreihenfolge (mehrfach dieselbe Schicht, dann
    weiter) bleibt das Ergebnis identisch — Anhängen ist idempotent je Schicht."""
    spec = _spec()

    a = dp.DruckstandPunkte(spec)
    a.advance_layer(5)
    a.advance_layer(5)  # bereits erreicht: No-Op
    a.advance_layer(2)  # rückwärts: No-Op
    a.advance_layer(9)

    b = dp.DruckstandPunkte(spec)
    b.advance_layer(9)

    np.testing.assert_array_equal(a.growing_points_mm, b.growing_points_mm)
    assert a.layer_index == b.layer_index == 9


def test_layer_zero_has_no_growing_points() -> None:
    """Schicht 0: unter dem Druckpunkt ist noch nichts fertig — keine Punkte
    (dieselbe Semantik wie ``druckstand.build_obstacle_set`` ohne ``current_part``)."""
    dpk = dp.DruckstandPunkte(_spec())
    dpk.advance_layer(0)
    assert dpk.layer_index == 0
    assert dpk.growing_points_mm.shape == (0, 3)


def test_layer_index_clamped_to_n_layers() -> None:
    dpk = dp.DruckstandPunkte(_spec(n_layers=5))
    dpk.advance_layer(99)
    assert dpk.layer_index == 5


def test_appending_never_shrinks_the_cloud() -> None:
    """Jede weitere Schicht kann die Punktwolke nur wachsen lassen, nie schrumpfen."""
    dpk = dp.DruckstandPunkte(_spec())
    prev_n = 0
    for layer in range(1, 16):
        dpk.advance_layer(layer)
        n = len(dpk.growing_points_mm)
        assert n > prev_n
        prev_n = n


# --- Abnahme 2: Punktabstand-Invariante --------------------------------------


def test_default_spacing_is_derived_from_safety_margin_and_documented() -> None:
    """Default-Punktabstand = 30 % der 50-mm-Sicherheitsmarge (Design-Log 2026-07-12)."""
    assert dp.DEFAULT_POINT_SPACING_MM == pytest.approx(0.3 * DEFAULT_SAFETY_DISTANCE_MM)
    assert dp.DEFAULT_POINT_SPACING_MM == pytest.approx(15.0)
    # "deutlich unter" — mindestens um den Faktor 3 unter dem Sicherheitsabstand.
    assert dp.DEFAULT_POINT_SPACING_MM * 3.0 <= DEFAULT_SAFETY_DISTANCE_MM


def test_footprint_slice_grid_spacing_is_at_most_spacing_mm() -> None:
    """Je Schnitt sind benachbarte Gitterpunkte höchstens ``point_spacing_mm``
    auseinander (die eigentliche Punktabstand-Invariante)."""
    spacing = 20.0
    pts = dp._footprint_slice_points(FOOTPRINT, 100.0, spacing, np)
    xs = sorted(set(pts[:, 0].round(6)))
    ys = sorted(set(pts[:, 1].round(6)))
    assert max(b - a for a, b in zip(xs, xs[1:], strict=False)) <= spacing + 1e-6
    assert max(b - a for a, b in zip(ys, ys[1:], strict=False)) <= spacing + 1e-6


def test_static_mesh_surface_spacing_bounded_by_spacing_mm() -> None:
    """Die deterministische Mesh-Unterteilung hält jede Kante unter ``spacing_mm``."""
    box = trimesh.creation.box(extents=[500, 500, 500])
    spacing = 40.0
    pts = dp._mesh_surface_points(box, spacing, np, trimesh)
    # Grobe Kontrolle: die Unterteilung erzeugt deutlich mehr Knoten als der
    # rohe Würfel (8 Ecken) — das Gitter wurde tatsächlich verfeinert.
    assert len(pts) > len(box.vertices)


# --- Abnahme 3: statische Hindernisse im selben Vertrag (US 15) --------------


def test_static_obstacles_abschnitt_mode_earlier_parts_ground_context() -> None:
    earlier = trimesh.creation.box(extents=[200, 200, 400])
    ctx = trimesh.creation.box(extents=[500, 500, 500])
    dpk = dp.DruckstandPunkte(
        _spec(earlier_parts=(earlier,), ground=_floor(), context=ctx, mode="abschnitt")
    )
    assert dpk.static_points_mm.shape[0] > 0
    # Ohne Kontext/Boden/frühere Teile bleibt die Statik leer.
    empty = dp.DruckstandPunkte(_spec(mode="abschnitt"))
    assert empty.static_points_mm.shape == (0, 3)


def test_static_obstacles_modul_mode_only_work_surface() -> None:
    """Modul-Modus: nur die Arbeitsfläche zählt als Statik, kein Boden/Kontext/
    frühere Teile — dieselbe Weiche wie ``druckstand.build_obstacle_set``."""
    work = trimesh.creation.box(extents=[2000, 2000, 100])
    earlier = trimesh.creation.box(extents=[200, 200, 400])
    ctx = trimesh.creation.box(extents=[500, 500, 500])
    dpk = dp.DruckstandPunkte(
        _spec(
            mode="modul",
            work_surface=work,
            earlier_parts=(earlier,),
            ground=_floor(),
            context=ctx,
        )
    )
    work_only = dp.DruckstandPunkte(_spec(mode="modul", work_surface=work))
    assert dpk.static_points_mm.shape == work_only.static_points_mm.shape
    np.testing.assert_array_equal(
        sorted(dpk.static_points_mm.tolist()), sorted(work_only.static_points_mm.tolist())
    )


def test_full_points_mm_combines_growing_and_static() -> None:
    dpk = dp.DruckstandPunkte(_spec(ground=_floor()))
    dpk.advance_layer(10)
    assert len(dpk.points_mm) == len(dpk.growing_points_mm) + len(dpk.static_points_mm)


# --- Quell-Naht: DruckstandSpec -> DruckstandPunkteSpec (#192) ---------------


def test_from_druckstand_spec_mirrors_the_fcl_backend_inputs() -> None:
    earlier = trimesh.creation.box(extents=[200, 200, 400])
    floor = _floor()
    fcl_spec = ds.DruckstandSpec(
        footprint=FOOTPRINT,
        layer_height_mm=10.0,
        n_layers=20,
        earlier_parts=(earlier,),
        ground=floor,
        mode="abschnitt",
    )
    punkte_spec = dp.DruckstandPunkteSpec.from_druckstand_spec(fcl_spec, point_spacing_mm=25.0)

    assert punkte_spec.footprint == fcl_spec.footprint
    assert punkte_spec.layer_height_mm == fcl_spec.layer_height_mm
    assert punkte_spec.n_layers == fcl_spec.n_layers
    assert punkte_spec.earlier_parts == fcl_spec.earlier_parts
    assert punkte_spec.ground is floor
    assert punkte_spec.mode == fcl_spec.mode
    assert punkte_spec.point_spacing_mm == 25.0
