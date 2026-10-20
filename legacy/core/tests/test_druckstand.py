"""Wachsender Druckstand als Hindernissatz je Schicht (ADR-024, Issue #126).

Prüft das reine Hindernis-Modul :mod:`fgc.collision.druckstand`: das Footprint-
Prisma wächst je Schicht (Rebuild je Schicht, nicht je Sample), die Freizone-
Kennzeichnung, die Modul-Variante (nur Modul + Arbeitsfläche), der zuschaltbare
Gebäudekontext und die toolpath-exakte Schicht-Zuordnung je Sample.
"""

from __future__ import annotations

import pytest
import trimesh
from shapely.geometry import Polygon

from fgc.collision import druckstand as ds

FOOTPRINT = (Polygon([(-400, -120), (400, -120), (400, 120), (-400, 120)]),)
FOOTPRINT_AREA_MM2 = 800.0 * 240.0


def _floor() -> trimesh.Trimesh:
    f = trimesh.creation.box(extents=[6000, 6000, 200])
    f.apply_translation([0, 0, -100])
    return f


def _spec(**over) -> ds.DruckstandSpec:
    base = dict(
        footprint=FOOTPRINT,
        layer_height_mm=10.0,
        n_layers=82,
        z_base_mm=0.0,
        ground=_floor(),
    )
    base.update(over)
    return ds.DruckstandSpec(**base)


# --- Footprint-Prisma + wachsendes Volumen ----------------------------------


def test_prism_is_real_outline_not_bounding_box() -> None:
    """Ein L-förmiger Umriss ergibt ein L-Prisma (echtes Slicer-Polygon, kein AABB)."""
    ell = Polygon([(0, 0), (300, 0), (300, 100), (100, 100), (100, 300), (0, 300)])
    prism = ds.extrude_prism((ell,), 0.0, 50.0)
    assert prism is not None and prism.is_watertight
    # L-Fläche = 300·100 + 100·200 = 50 000 mm²; ein AABB (300×300) hätte 90 000.
    assert prism.volume == pytest.approx(50000.0 * 50.0, rel=1e-6)


def test_growing_volume_per_layer() -> None:
    """Das aktuelle Teil wächst mit der Schicht; oberhalb existiert nichts."""
    spec = _spec()
    prev_vol = -1.0
    for layer in (1, 10, 40, 82):
        oset = ds.build_obstacle_set(spec, layer)
        assert oset.z_top_mm == pytest.approx(layer * 10.0)
        current = next(o for o in oset.obstacles if o.name == "current_part")
        vol = current.mesh.volume
        assert vol == pytest.approx(FOOTPRINT_AREA_MM2 * layer * 10.0, rel=1e-6)
        assert vol > prev_vol  # streng wachsend
        prev_vol = vol


def test_layer_zero_has_no_growing_part() -> None:
    """Schicht 0: unter dem Druckpunkt ist noch nichts fertig — kein Prisma."""
    oset = ds.build_obstacle_set(_spec(), 0)
    assert oset.z_top_mm == 0.0
    assert all(o.name != "current_part" for o in oset.obstacles)
    assert any(o.name == "ground" for o in oset.obstacles)


def test_layer_index_clamped_to_n_layers() -> None:
    spec = _spec(n_layers=5)
    assert ds.build_obstacle_set(spec, 99).z_top_mm == pytest.approx(5 * 10.0)


# --- Freizone-Kennzeichnung --------------------------------------------------


def test_current_part_is_freizone_exempt() -> None:
    """Nur das wachsende Teil trägt die Freizonen-Ausnahme (Düse↔Wulst)."""
    oset = ds.build_obstacle_set(_spec(freizone_radius_mm=30.0), 20)
    assert oset.freizone_radius_mm == 30.0
    current = next(o for o in oset.obstacles if o.name == "current_part")
    assert current.freizone_exempt is True
    ground = next(o for o in oset.obstacles if o.name == "ground")
    assert ground.freizone_exempt is False


# --- Kontext zuschaltbar -----------------------------------------------------


def test_context_toggle() -> None:
    ctx = trimesh.creation.box(extents=[500, 500, 500])
    assert all(o.name != "context" for o in ds.build_obstacle_set(_spec(), 10).obstacles)
    with_ctx = ds.build_obstacle_set(_spec(context=ctx), 10)
    assert any(o.name == "context" for o in with_ctx.obstacles)


# --- Modul-Variante (US 24) --------------------------------------------------


def test_modul_variant_only_module_and_work_surface() -> None:
    """Modul-Modus: nur wachsendes Modul + Arbeitsfläche, kein Boden/Kontext."""
    work = trimesh.creation.box(extents=[2000, 2000, 100])
    ctx = trimesh.creation.box(extents=[500, 500, 500])
    oset = ds.build_obstacle_set(
        _spec(mode="modul", work_surface=work, context=ctx), 15
    )
    names = {o.name for o in oset.obstacles}
    assert names == {"modul", "work_surface"}
    modul = next(o for o in oset.obstacles if o.name == "modul")
    assert modul.freizone_exempt is True


# --- Frühere Teile voll ------------------------------------------------------


def test_earlier_parts_are_full_obstacles() -> None:
    earlier = trimesh.creation.box(extents=[200, 200, 400])
    oset = ds.build_obstacle_set(_spec(earlier_parts=(earlier,)), 5)
    part = next(o for o in oset.obstacles if o.name == "part0")
    assert part.freizone_exempt is False
    assert part.mesh.volume == pytest.approx(earlier.volume, rel=1e-9)


# --- Boden-Slab an der echten Höhenlage (Issue #135) --------------------------


def test_ground_slab_top_at_minus_z0() -> None:
    """Der reale Boden liegt abschnitts-lokal bei −z0: Oberkante des Slabs exakt
    bei ``z_top_mm``, Dicke nach unten — der obere Abschnitt (z0 = 1300) bekommt
    seinen Boden also bei lokal −1300, nicht am Abschnittsfuß."""
    slab = ds.ground_slab(-1300.0)
    lo, hi = slab.bounds
    assert hi[2] == pytest.approx(-1300.0)
    assert lo[2] == pytest.approx(-1300.0 - ds.GROUND_THICKNESS_MM)
    assert hi[0] == pytest.approx(ds.GROUND_HALF_EXTENT_MM)
    assert lo[1] == pytest.approx(-ds.GROUND_HALF_EXTENT_MM)


def test_ground_slab_at_zero_matches_golden_floor() -> None:
    """``ground_slab(0)`` ist deckungsgleich zum Golden-Boden (#126-Fixture) —
    Oberkante auf 0, 6 m Kante, 200 mm dick."""
    slab = ds.ground_slab(0.0)
    ref = _floor()
    assert slab.bounds == pytest.approx(ref.bounds)


# --- Rebuild je Schicht (nicht je Sample) ------------------------------------


def test_provider_rebuilds_once_per_layer() -> None:
    """Der Provider baut je Schicht genau einmal; viele Samples teilen sich das Set."""
    provide = ds.obstacle_provider(_spec())
    first = provide(12)
    again = provide(12)  # gleiche Schicht → kein Rebuild
    assert again is first
    provide(13)
    provide(12)  # erneut Schicht 12 → weiterhin aus Cache
    assert set(provide.cache) == {12, 13}  # nur zwei Rebuilds trotz vieler Aufrufe


# --- Schicht je Sample aus dem Toolpath --------------------------------------


def test_layer_per_sample_from_toolpath_times() -> None:
    """Jedes Sample erbt die Schicht seines Toolpath-Segments (Bisektion, keine TCP-Näherung)."""
    target_times = [0.0, 1.0, 2.5, 4.0]
    target_layers = [0, 0, 1, 2]
    sample_times = [0.0, 0.5, 1.2, 2.4, 2.6, 3.9, 4.0, 5.0]
    got = ds.layer_per_sample(sample_times, target_times, target_layers)
    assert got == [0, 0, 0, 0, 1, 1, 2, 2]


def test_layer_per_sample_empty_targets() -> None:
    assert ds.layer_per_sample([0.0, 1.0], [], []) == [0, 0]
