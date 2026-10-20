import numpy as np
import pytest

from roboprint import frames
from roboprint.assets import REPO_ROOT, load_tool, load_workstation


@pytest.fixture(scope="module")
def ws():
    return load_workstation()


@pytest.fixture(scope="module")
def tool():
    return load_tool()


def _rand_T(rng):
    q = rng.normal(size=4)
    return frames.T_from_pos_quat(rng.uniform(-1000, 1000, 3), q)


def test_quaternion_roundtrip():
    rng = np.random.default_rng(1)
    for _ in range(200):
        q = frames.quat_normalize(rng.normal(size=4))
        q2 = frames.matrix_to_quat(frames.quat_to_matrix(q))
        assert np.allclose(q2, q if q[0] >= 0 else -q, atol=1e-9)
    # ausgezeichnete Faelle (180 Grad um alle Achsen)
    for q in ([0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]):
        assert np.allclose(frames.matrix_to_quat(frames.quat_to_matrix(q)), q, atol=1e-12)


def test_pose7_roundtrip_and_rotation_properties():
    rng = np.random.default_rng(2)
    for _ in range(50):
        T = _rand_T(rng)
        assert np.allclose(frames.T_from_pose7(frames.pose7(T)), T, atol=1e-9)
        R = T[:3, :3]
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-12)
        assert np.linalg.det(R) == pytest.approx(1.0)
        assert np.allclose(frames.invert(T) @ T, np.eye(4), atol=1e-9)


def test_quat_multiply_matches_matrix_product():
    rng = np.random.default_rng(3)
    a, b = (frames.quat_normalize(rng.normal(size=4)) for _ in range(2))
    assert np.allclose(
        frames.quat_to_matrix(frames.quat_multiply(a, b)),
        frames.quat_to_matrix(a) @ frames.quat_to_matrix(b),
        atol=1e-12,
    )


def test_workstation_known_values(ws):
    assert frames.T_WB(ws)[:3, 3] == pytest.approx([780.0, 1090.0, 901.0])
    assert frames.T_WS(ws)[:3, 3] == pytest.approx([780.0, 605.0, 901.0])  # Tischoberkante z = 901
    assert frames.T_WS(ws)[2, 3] == 901.0
    assert np.allclose(frames.T_WB(ws)[:3, :3], np.diag([-1.0, -1.0, 1.0]))  # 180 Grad um Z
    assert np.allclose(frames.T_BW(ws) @ frames.T_WB(ws), np.eye(4), atol=1e-9)
    # S liegt in B 485 mm vor der Basis (in +Y_B) und 0 mm hoeher
    assert frames.T_BS(ws)[:3, 3] == pytest.approx([0.0, 485.0, 0.0])
    assert frames.T_SW(ws) @ frames.T_WS(ws) == pytest.approx(np.eye(4), abs=1e-9)


def test_cable_hangs_off_the_table(ws):
    """Das Kabel tritt bei -Y_B aus der Basis (base_link-Mesh) und hängt über die nahe hintere
    Tischkante nach unten (Aufbau am Doosantisch), nicht über die Arbeitsfläche."""
    import trimesh

    from roboprint.planner.backend import _urdf_collision_meshes, table_box

    (path,) = _urdf_collision_meshes(REPO_ROOT)["base_link"]
    v = trimesh.load(path, force="mesh").vertices
    cable_end_B = v[np.argmax(np.hypot(v[:, 0], v[:, 1]))]  # noqa: N806
    assert cable_end_B[1] < -300.0
    cable_end_W = frames.transform_points(frames.T_WB(ws), cable_end_B[None])[0]  # noqa: N806
    lo, hi = table_box(REPO_ROOT)
    assert cable_end_W[1] > hi[1], "Kabel liegt auf dem Tisch statt über der Kante"
    assert lo[0] < cable_end_W[0] < hi[0]


def test_tool_frames(tool):
    T = frames.T_FT(tool)
    assert T[:3, 3] == pytest.approx([134.0, 0.0, 73.0])
    # Duesenachse +Z_T ist Flansch-X (CLAUDE.md)
    assert T[:3, 2] == pytest.approx([1.0, 0.0, 0.0], abs=1e-9)
    assert np.linalg.det(T[:3, :3]) == pytest.approx(1.0)
    M = frames.T_F_mesh(tool)
    assert M[:3, 3] == pytest.approx([80.1474, 0.00065, 72.9942], abs=1e-3)
    assert np.linalg.det(M[:3, :3]) == pytest.approx(1.0)


def test_bt_bf_roundtrip(tool):
    rng = np.random.default_rng(4)
    T_BF = _rand_T(rng)
    assert np.allclose(frames.T_BF_from_T_BT(frames.T_BT(T_BF, tool), tool), T_BF, atol=1e-9)


def test_placement_chain(ws):
    pl = frames.Placement(100.0, -50.0, np.pi / 2)
    T_SP = frames.T_SP(pl)
    assert T_SP[:3, 3] == pytest.approx([100.0, -50.0, 0.0])
    # +90 Grad um Z_S: X_P zeigt nach +Y_S
    assert T_SP[:3, 0] == pytest.approx([0.0, 1.0, 0.0], abs=1e-12)
    T_WP = frames.T_WP(ws, pl)
    assert np.allclose(T_WP, frames.T_WS(ws) @ T_SP)
    assert T_WP[2, 3] == 901.0  # Modul steht auf der Arbeitsflaeche
    assert np.allclose(frames.T_BP(ws, pl), frames.T_BW(ws) @ T_WP)
    # Punkt (1,0,0) in P -> W
    p = frames.transform_points(T_WP, [[10.0, 0.0, 5.0]])[0]
    assert p == pytest.approx([780.0 + 100.0, 605.0 - 50.0 + 10.0, 906.0])


def test_T_LP_is_bottom_center():
    T = frames.T_LP([100, 20, 300], [500, 220, 900])
    assert T[:3, 3] == pytest.approx([300, 120, 300])
    assert np.allclose(T[:3, :3], np.eye(3))


def _box_vertices(R, origin, size):
    corners = np.array([[x, y, z] for x in (0, size[0]) for y in (0, size[1]) for z in (0, size[2])])
    return corners @ R.T + origin


@pytest.mark.parametrize("angle_deg", [0, 30, 90, 135, 180, 270, -45])
def test_wall_frame_right_handed_and_min_corner(angle_deg):
    a = np.deg2rad(angle_deg)
    R = frames.rot_z(a)
    v = _box_vertices(R, np.array([7000.0, 3000.0, -250.0]), (1800.0, 200.0, 3000.0))
    T_GL = frames.wall_frame_from_ifc(v)
    R_L = T_GL[:3, :3]
    assert np.linalg.det(R_L) == pytest.approx(1.0)
    assert np.allclose(np.cross(R_L[:, 2], R_L[:, 0]), R_L[:, 1])  # Y = Z x X
    assert np.allclose(R_L[:, 2], [0, 0, 1])
    local = frames.transform_points(frames.invert(T_GL), v)
    assert local.min(axis=0) == pytest.approx([0, 0, 0], abs=1e-6)
    assert local.max(axis=0) == pytest.approx([1800, 200, 3000], abs=1e-6)


def test_wall_frame_axis_hint_sets_sign():
    v = _box_vertices(np.eye(3), np.zeros(3), (1000.0, 100.0, 500.0))
    assert frames.wall_frame_from_ifc(v)[:3, 0] == pytest.approx([1, 0, 0])
    T = frames.wall_frame_from_ifc(v, axis_hint=[-1, 0, 0])
    assert T[:3, 0] == pytest.approx([-1, 0, 0])
    assert T[:3, 1] == pytest.approx([0, -1, 0])
    local = frames.transform_points(frames.invert(T), v)
    assert local.min(axis=0) == pytest.approx([0, 0, 0], abs=1e-9)
