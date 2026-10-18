"""Erzeugt den handgebauten Laufordner ``web/fixtures/run_demo/`` reproduzierbar.

Der Ordner folgt spec/ARTEFAKTE.md und dient dem Viewer (P3), bevor der Planer fertig ist.
Nichts darin ist physikalisch geprüft: q und tcp stammen aus einer groben Näherung um die
Home-Pose, Abstände und Status sind frei gewählt (inkl. warn, collision und unreachable).

Aufruf: ``python web/fixtures/make_fixture.py [ausgabeordner]`` (nur numpy, trimesh, roboprint.contracts).
"""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "core" / "src"))

from roboprint.contracts import (  # noqa: E402
    BBox,
    Cause,
    PartArtifact,
    PartEntry,
    Placement,
    Provenance,
    Ring,
    Scene,
    SceneParams,
    SceneRobot,
    SceneTool,
    SceneWorkstation,
    Summary,
    Toolpath,
    Trajectory,
    TrajectorySummary,
    WallEntry,
    dump_json,
)

PART_ID = "P01"
SIZE = (600.0, 200.0, 40.0)  # Länge, Dicke, Höhe in mm
H = 10.0  # Schichthöhe
W = 30.0  # Strangbreite
N_LAYERS = 4
Z_LIFT = 30.0
APPROACH = 20.0
V_PRINT = 100.0
V_TRAVEL = 250.0
DS_PRINT = 40.0  # Abstand der Druck-Samples entlang des Rings
HOME_Q = np.radians([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])
HOME_TCP = np.array([780.0, 700.0, 1600.0])
T_WB = np.eye(4)
T_WB[:3, 3] = [780.0, 1090.0, 901.0]
T_WS = np.eye(4)
T_WS[:3, 3] = [780.0, 605.0, 901.0]
NOZZLE_DOWN_Q = [0.0, 1.0, 0.0, 0.0]  # Drehung 180° um X: +Z_T zeigt nach -Z_W


def rnd(x: float, nd: int = 4) -> float:
    return round(float(x), nd)


def quat_to_mat(q: tuple[float, float, float, float]) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def pose_mat(pos: list[float], quat: tuple[float, float, float, float]) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = quat_to_mat(quat)
    t[:3, 3] = pos
    return t


def mat_list(m: np.ndarray) -> list[list[float]]:
    return [[rnd(v) for v in row] for row in m]


def ring_polyline(inset: float) -> np.ndarray:
    """Geschlossenes Rechteck in P (Mitte des Quaders im Ursprung), Start an der Ecke (-x, -y)."""
    hx, hy = SIZE[0] / 2 - inset, SIZE[1] / 2 - inset
    corners = np.array([[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy], [-hx, -hy]])
    return corners


def resample(poly: np.ndarray, step: float) -> np.ndarray:
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(int(round(s[-1] / step)), 4)
    targets = np.linspace(0.0, s[-1], n + 1)
    return np.column_stack([np.interp(targets, s, poly[:, k]) for k in range(poly.shape[1])])


def build_toolpath(T_WP: np.ndarray) -> Toolpath:
    rings = []
    for layer in range(N_LAYERS):
        z_p = (layer + 1) * H
        for shell, (kind, inset) in enumerate([("outer", W / 2), ("inner", W / 2 + W)]):
            xy = resample(ring_polyline(inset), 20.0)
            pts_p = np.column_stack([xy, np.full(len(xy), z_p), np.ones(len(xy))])
            pts_w = (T_WP @ pts_p.T).T[:, :3]
            wps = [[rnd(p[0]), rnd(p[1]), rnd(p[2]), *NOZZLE_DOWN_Q] for p in pts_w]
            wps[-1] = list(wps[0])
            rings.append(Ring(layer=layer, shell=shell, kind=kind, closed=True, waypoints=wps))
    return Toolpath(part_id=PART_ID, layer_height_mm=H, bead_width_mm=W, rings=rings)


class Sampler:
    """Sammelt Samples; jedes Segment liefert seine Punkte ohne den Startpunkt."""

    def __init__(self) -> None:
        self.pos: list[np.ndarray] = []
        self.kind: list[str] = []
        self.ring: list[int] = []
        self.layer: list[int] = []
        self.speed: list[float] = []

    def add(self, p: np.ndarray, kind: str, ring: int, layer: int, speed: float) -> None:
        self.pos.append(np.asarray(p, dtype=float))
        self.kind.append(kind)
        self.ring.append(ring)
        self.layer.append(layer)
        self.speed.append(speed)

    def line(self, a: np.ndarray, b: np.ndarray, n: int, kind: str, ring: int, layer: int, v: float) -> None:
        for i in range(1, n + 1):
            self.add(a + (b - a) * (i / n), kind, ring, layer, v)


def build_samples(tp: Toolpath) -> Sampler:
    sm = Sampler()
    sm.add(HOME_TCP, "transfer", 0, 0, V_TRAVEL)  # Startpose, Zeit 0
    cur = HOME_TCP.copy()
    for r, ring in enumerate(tp.rings):
        pts = np.array([w[:3] for w in ring.waypoints])
        start, k_after = pts[0], ring.layer
        if r > 0:
            prev = tp.rings[r - 1]
            k_after = prev.layer + 1
            up = cur + [0, 0, Z_LIFT - APPROACH]
            sm.line(cur, up, 3, "lift", r - 1, k_after, V_TRAVEL)
            cur = up
        z_travel = max(cur[2], start[2] + Z_LIFT)
        above_end = np.array([start[0], start[1], z_travel])
        mid_a = np.array([cur[0], cur[1], z_travel]) if cur[2] < z_travel else cur
        if not np.allclose(mid_a, cur):
            sm.line(cur, mid_a, 2, "transfer", r, k_after if r else 0, V_TRAVEL)
        sm.line(mid_a, above_end, 6, "transfer", r, k_after if r else 0, V_TRAVEL)
        low = start + [0, 0, APPROACH]
        sm.line(above_end, low, 3, "lower", r, k_after if r else 0, V_TRAVEL)
        sm.line(low, start, 3, "approach", r, ring.layer, V_PRINT)
        arc = resample(pts[:, :2], DS_PRINT)
        z = pts[0, 2]
        for xy in arc[1:]:
            sm.add(np.array([xy[0], xy[1], z]), "print", r, ring.layer, V_PRINT)
        end = sm.pos[-1].copy()
        sm.line(end, end + [0, 0, APPROACH], 3, "retract", r, ring.layer, V_PRINT)
        cur = end + [0, 0, APPROACH]
    return sm


def joints_for(p: np.ndarray) -> np.ndarray:
    """Grobe, glatte Näherung: kleine Gelenkwege um die Home-Pose."""
    d = (p - HOME_TCP) / 1000.0
    return HOME_Q + np.array(
        [0.9 * d[0], 0.5 * d[1] - 0.2 * d[2], -0.4 * d[2] + 0.5 * d[1], 0.2 * d[0], 0.3 * d[1], 0.1 * d[0]]
    )


def build_trajectory(tp: Toolpath) -> tuple[Trajectory, int | None]:
    sm = build_samples(tp)
    n = len(sm.pos)
    t_s = [0.0]
    for i in range(1, n):
        dist = float(np.linalg.norm(sm.pos[i] - sm.pos[i - 1]))
        t_s.append(t_s[-1] + max(dist / sm.speed[i], 0.05))
    # Statusprofil: Abstand glatt, dann gezielte Auffälligkeiten
    d = [60.0 + 25.0 * math.sin(i / 11.0) for i in range(n)]
    status = ["ok"] * n
    pair: list[list[str] | None] = [["link_2", "table"]] * n
    # Warnstrecke im Druck von Ring 3 (d < d_target = 50, aber > d_hard = 10)
    print_idx = [i for i in range(n) if sm.kind[i] == "print" and sm.ring[i] == 3]
    for j, i in enumerate(print_idx[3:11]):
        d[i] = 42.0 - 3.0 * math.sin(math.pi * j / 7)
        status[i] = "warn"
        pair[i] = ["link_3", "printed"]
    # Kollision im Transfer zu Ring 5: Werkzeugkörper streift den gedruckten Teil
    transfer_idx = [i for i in range(n) if sm.kind[i] == "transfer" and sm.ring[i] == 5]
    for j, i in enumerate(transfer_idx[1:4]):
        d[i] = [14.0, -3.5, -1.2][j]
        status[i] = "warn" if j == 0 else "collision"
        pair[i] = ["tool_body", "printed"]
    # Zwei unerreichbare Samples im Transfer zu Ring 7
    unreach = [i for i in range(n) if sm.kind[i] == "transfer" and sm.ring[i] == 7][2:4]
    for i in unreach:
        status[i] = "unreachable"
    q = []
    last = HOME_Q
    for i in range(n):
        if status[i] != "unreachable":
            last = joints_for(sm.pos[i])
        q.append([rnd(v, 6) for v in last])
    psi = [rnd(0.2 * math.sin(i / 30.0), 6) for i in range(n)]
    d_mm: list[float | None] = []
    witness: list[list[list[float]] | None] = []
    pairs: list[list[str] | None] = []
    for i in range(n):
        if status[i] == "unreachable":
            d_mm.append(None)
            witness.append(None)
            pairs.append(None)
            continue
        p = sm.pos[i]
        d_mm.append(rnd(d[i], 3))
        pairs.append(list(pair[i] or []))
        witness.append([[rnd(p[0]), rnd(p[1]), rnd(p[2])], [rnd(p[0]), rnd(p[1]), rnd(p[2] - d[i])]])
    tcp = [[rnd(p[0]), rnd(p[1]), rnd(p[2]), *NOZZLE_DOWN_Q] for p in sm.pos]
    counts = {s: status.count(s) for s in ("ok", "warn", "collision", "unreachable")}
    valid_d = [v for v in d_mm if v is not None]
    summary = TrajectorySummary(
        n=n,
        n_ok=counts["ok"],
        n_warn=counts["warn"],
        n_collision=counts["collision"],
        n_unreachable=counts["unreachable"],
        d_min_mm=min(valid_d),
        dauer_s=rnd(t_s[-1], 3),
        zweig_wechsel_in_ringen=0,
    )
    traj = Trajectory(
        part_id=PART_ID,
        t_s=[rnd(t, 4) for t in t_s],
        q=q,
        tcp=tcp,
        layer=sm.layer,
        ring=sm.ring,
        kind=sm.kind,
        branch=[2] * n,
        status=status,
        d_mm=d_mm,
        pair=pairs,
        witness=witness,
        psi_rad=psi,
        summary=summary,
    )
    first_coll = next((i for i, s in enumerate(status) if s == "collision"), None)
    return traj, first_coll


DRL = """\
# PLATZHALTER (Fixture, nicht geprueft): kein ausfuehrbares Programm.
# Dialekt v2, TCP FGC_30GUT, Teil P01 (600 x 200 x 40 mm, 4 Schichten)
set_tcp("FGC_30GUT")
movej(posj(0.0, 0.0, 90.0, 0.0, 90.0, 0.0), vel=30, acc=60)
# ... Fixture: die eigentlichen Bewegungsbefehle erzeugt der Planer ...
movej(posj(0.0, 0.0, 90.0, 0.0, 90.0, 0.0), vel=30, acc=60)
"""


def make(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    part_dir = out / "parts" / PART_ID
    part_dir.mkdir(parents=True)

    T_SP = np.eye(4)
    T_WP = T_WS @ T_SP
    tool_T_FT = pose_mat([134.0, 0.0, 73.0], (math.sqrt(0.5), 0.0, math.sqrt(0.5), 0.0))
    mesh_T = pose_mat([80.1474, 0.0006, 72.9942], (0.5, 0.5, -0.5, 0.5))

    mesh = trimesh.creation.box(extents=SIZE)
    mesh.apply_translation([0.0, 0.0, SIZE[2] / 2])
    mesh.export(part_dir / "part.stl")

    tp = build_toolpath(T_WP)
    traj, first_coll = build_trajectory(tp)
    n_coll = traj.summary.n_collision
    volume = SIZE[0] * SIZE[1] * SIZE[2]

    scene = Scene(
        robot=SceneRobot(urdf="third_party/doosan_m1013/urdf/m1013.white.urdf"),
        workstation=SceneWorkstation(
            mesh="workstations/doosantisch.stl", T_WB=mat_list(T_WB), T_WS=mat_list(T_WS)
        ),
        tool=SceneTool(mesh="tools/30gut.stl", T_FT=mat_list(tool_T_FT), mesh_transform=mat_list(mesh_T)),
        params=SceneParams(d_hard_mm=10.0, d_target_mm=50.0, r_free_mm=40.0, layer_height_mm=H),
    )
    part = PartArtifact(
        part_id=PART_ID,
        wall_id="box",
        T_LP=mat_list(np.eye(4)),
        T_SP=mat_list(T_SP),
        T_WP=mat_list(T_WP),
        placement=Placement(x_mm=0.0, y_mm=0.0, yaw_deg=0.0),
        bbox_P=BBox(min=[-SIZE[0] / 2, -SIZE[1] / 2, 0.0], max=[SIZE[0] / 2, SIZE[1] / 2, SIZE[2]]),
        volume_mm3=volume,
        n_layers=N_LAYERS,
        status="nicht machbar",
        cause=Cause(
            sample=first_coll if first_coll is not None else 0,
            t_s=traj.t_s[first_coll or 0],
            link="tool_body",
            obstacle="printed",
            message="Fixture: Werkzeugkoerper durchdringt den gedruckten Teil (3,5 mm), nicht geprueft.",
        ),
    )
    summary = Summary(
        scenario_id="fixture_run_demo",
        scenario_path="web/fixtures/make_fixture.py",
        params={
            "layer_height_mm": H,
            "bead_width_mm": W,
            "shells": 2,
            "v_print_mm_s": V_PRINT,
            "v_travel_mm_s": V_TRAVEL,
            "z_lift_mm": Z_LIFT,
            "approach_mm": APPROACH,
            "pump_voltage_v": 5.0,
            "t_tot_s": 3.0,
            "r_blend_mm": 2.0,
            "d_hard_mm": 10.0,
            "d_target_mm": 50.0,
            "r_free_mm": 40.0,
            "tau_max_deg": 0.0,
            "psi_step_deg": 15.0,
            "ds_mm": 20.0,
            "dq_max_rad": 0.3,
            "tcp_name": "FGC_30GUT",
            "dialect": "v2",
        },
        assumptions=[
            "Fixture, nicht geprüft: handgebauter Laufordner für den Viewer, nicht vom Planer erzeugt.",
            "Fixture, nicht geprüft: q und tcp stammen aus einer groben Näherung um die Home-Pose.",
            "Fixture, nicht geprüft: Abstände, Status, Paare und Zeugenpunkte sind frei gewählt.",
            "Schichthöhe 10 mm, Strangbreite 30 mm, 2 Schalen (Annahmen aus SPEC §10).",
        ],
        walls=[
            WallEntry(
                wall_id="box",
                name="box",
                eligible=True,
                reason=None,
                length_mm=SIZE[0],
                thickness_mm=SIZE[1],
                height_mm=SIZE[2],
                volume_mm3=volume,
                part_ids=[PART_ID],
            )
        ],
        parts=[
            PartEntry(
                part_id=PART_ID,
                wall_id="box",
                status="nicht machbar",
                d_min_mm=traj.summary.d_min_mm,
                n_collision=n_coll,
                n_unreachable=traj.summary.n_unreachable,
            )
        ],
        timings_s={"fixture": 0.0},
        provenance=Provenance(
            git_commit=None, created="2026-10-18T00:00:00Z", command="python web/fixtures/make_fixture.py"
        ),
    )
    dump_json(summary, out / "summary.json", indent=2)
    dump_json(scene, out / "scene.json", indent=2)
    dump_json(part, part_dir / "part.json", indent=2)
    dump_json(tp, part_dir / "toolpath.json")
    dump_json(traj, part_dir / "trajectory.json")
    (part_dir / "program.v2.drl").write_text(DRL, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "run_demo"
    make(target)
    print(f"geschrieben: {target}")
