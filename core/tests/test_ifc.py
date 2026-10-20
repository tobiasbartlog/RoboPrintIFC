from pathlib import Path

import numpy as np
import pytest

from roboprint import frames
from roboprint.geometry import cut_box, volume
from roboprint.ifc import Wall, eligibility, read_walls

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "Building-Architecture.ifc"


@pytest.fixture(scope="module")
def walls() -> list[Wall]:
    return read_walls(EXAMPLE)


def test_example_wall_count_and_names(walls):
    assert len(walls) == 4
    assert len({w.wall_id for w in walls}) == 4
    assert sum(w.name == "plumbing wall" for w in walls) == 1


def test_walls_lie_in_L_box(walls):
    for w in walls:
        lo, hi = w.mesh.bounds
        assert lo == pytest.approx([0, 0, 0], abs=1e-3)
        assert hi == pytest.approx([w.length_mm, w.thickness_mm, w.height_mm], abs=1e-3)
        assert w.mesh.is_watertight
        assert w.volume_mm3 == pytest.approx(volume(w.mesh))
        assert w.length_mm > w.thickness_mm
        assert np.linalg.det(w.T_GL[:3, :3]) == pytest.approx(1.0)


def test_known_dimensions(walls):
    by = {w.name: w for w in walls}
    left = by["house - outer wall - house left"]
    assert left.length_mm == pytest.approx(6000, abs=0.1)
    assert left.thickness_mm == pytest.approx(200, abs=0.1)
    assert 0 < left.volume_mm3 <= left.length_mm * left.thickness_mm * left.height_mm * (1 + 1e-9)
    assert by["plumbing wall"].thickness_mm == pytest.approx(24, abs=0.1)
    assert by["plumbing wall"].length_mm == pytest.approx(3800, abs=0.1)


def test_global_position_roundtrip(walls):
    # Wand 'left' liegt global bei x ~ 3000..3200 mm (Fallstrick CLAUDE.md)
    left = next(w for w in walls if w.name.endswith("house left"))
    glob = frames.transform_points(left.T_GL, left.mesh.vertices)
    assert glob.min(axis=0)[:2] == pytest.approx([3000, 3000], abs=0.1)
    assert glob.max(axis=0)[:2] == pytest.approx([3200, 9000], abs=0.1)


def test_eligibility(walls):
    by = {w.name: w for w in walls}
    ok, reason = eligibility(by["house - outer wall - house left"], 30.0)
    assert ok and reason is None
    ok, reason = eligibility(by["plumbing wall"], 30.0)
    assert not ok and "24" in reason and "60" in reason
    assert eligibility(by["plumbing wall"], 12.0)[0]  # 24 >= 2 * 12 (Grenzfall)
    assert not eligibility(by["plumbing wall"], 12.5)[0]


def test_raster_blocks_conserve_volume(walls):
    for w in walls:
        if w.name == "plumbing wall":
            continue
        step_x, step_z = 800.0, 700.0
        total = 0.0
        for x0 in np.arange(0, w.length_mm, step_x):
            for z0 in np.arange(0, w.height_mm, step_z):
                hi = (min(x0 + step_x, w.length_mm + 1), w.thickness_mm + 1)
                hi = (*hi, min(z0 + step_z, w.height_mm + 1))
                blk = cut_box(w.mesh, (x0, -1, z0), hi)
                total += volume(blk)
        assert total == pytest.approx(w.volume_mm3, rel=1e-3)


def _make_ifc_with_opening(path: Path) -> None:
    import ifcopenshell
    import ifcopenshell.api

    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="p")
    ifcopenshell.api.run("unit.assign_unit", f)
    ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", f, context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=ctx,
    )  # fmt: skip
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite")
    ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=proj)
    wall = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="mit Fenster")
    ifcopenshell.api.run("spatial.assign_container", f, products=[wall], relating_structure=site)
    rep = ifcopenshell.api.run(
        "geometry.add_wall_representation", f, context=body, length=4.0, height=2.5, thickness=0.2
    )
    ifcopenshell.api.run("geometry.assign_representation", f, product=wall, representation=rep)
    # Wand gedreht um 30 Grad und weit weg vom Ursprung
    c, s = np.cos(np.deg2rad(30)), np.sin(np.deg2rad(30))
    m = np.array([[c, -s, 0, 7.0], [s, c, 0, 3.0], [0, 0, 1, 0.0], [0, 0, 0, 1]])
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=wall, matrix=m, is_si=True)
    op = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcOpeningElement")
    orep = ifcopenshell.api.run(
        "geometry.add_wall_representation", f, context=body, length=1.0, height=1.0, thickness=0.4
    )
    ifcopenshell.api.run("geometry.assign_representation", f, product=op, representation=orep)
    mo = m @ np.array([[1, 0, 0, 1.5], [0, 1, 0, -0.1], [0, 0, 1, 0.9], [0, 0, 0, 1]])
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=op, matrix=mo, is_si=True)
    ifcopenshell.api.run("feature.add_feature", f, feature=op, element=wall)
    f.write(str(path))


def test_wall_with_opening_in_L(tmp_path):
    p = tmp_path / "w.ifc"
    _make_ifc_with_opening(p)
    (w,) = read_walls(p)
    assert w.length_mm == pytest.approx(4000, abs=0.5)
    assert w.thickness_mm == pytest.approx(200, abs=0.5)
    assert w.height_mm == pytest.approx(2500, abs=0.5)
    assert w.mesh.is_watertight
    assert w.volume_mm3 == pytest.approx(4000 * 200 * 2500 - 1000 * 200 * 1000, rel=1e-3)
    (o,) = w.openings
    assert (o.x0, o.x1) == pytest.approx((1500, 2500), abs=1.0)
    assert (o.z0, o.z1) == pytest.approx((900, 1900), abs=1.0)  # z1 = Sturzlinie
    assert w.mesh.bounds[0] == pytest.approx([0, 0, 0], abs=1e-3)
