"""Handgebaute, FK-konsistente Mini-Plaene als Laufordner (fuer test_drl.py).

Rechteckringe auf der Arbeitsflaeche, Duese senkrecht nach unten, um psi gedreht. Alle q per
`robot.ik_nearest` im Zweig des ersten Ziels erzeugt, tcp = T_WB @ fk(q) @ T_FT. Ablauf nach
spec/ARTEFAKTE.md. Braucht kein Pinocchio.

- `build_run`: alter Ablauf (link_max_mm = 0), zwei Schichten mit je einem Ring 200 x 100 mm, jeder
  Ring ein Strang: transfer (Home -> ueber Start) -> lower -> approach -> print -> retract -> lift
  -> transfer (Ring 1 mit Zwischenpunkt) -> ... -> lift.
- `build_strand_run`: Strang mit Verbindern. Schicht 0 und 1 mit je zwei Ringen (Schale 0 outer
  200 x 100, Schale 1 inner 140 x 40), verbunden zu einem Strang 0 -> 1 -> 2 -> 3: Verbinder in der
  Schicht (Ecke aussen -> Ecke innen, 42 mm) und beim Schichtwechsel (1 -> 2, steigt um h). Danach
  ein getrennter Strang aus Ring 4 (Schicht 2) mit Travel retract/lift/transfer (Zwischenpunkt)/
  lower/approach. Ring 3 hat `link_next = true`, der Plan trennt dort trotzdem (SPEC §5.3: die
  Trajektorie ist massgeblich).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from roboprint import frames, robot
from roboprint.assets import load_tool, load_workstation
from roboprint.contracts import (
    BBox,
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

H = 10.0
SIZE = (200.0, 100.0)
SIZE_INNER = (140.0, 40.0)  # Schale 1: 30 mm (Strangbreite) weiter innen
DS = 20.0
STEP_MM = 4.0
STEP_RAD = 0.005
R_DOWN = np.diag([1.0, -1.0, -1.0])  # Z_T = -Z_W, X_T = X_W (psi = 0)
PSI_DEG = (0.0, 37.0)  # Gierwinkel je Ring: Ring 0 im Gimbal-Normalfall a = c-Kopplung, Ring 1 gedreht
UP = np.array([0.0, 0.0, 1.0])


@dataclass(frozen=True)
class RingSpec:
    wps: np.ndarray  # (n, 3) in W, geschlossen (letzter = erster)
    layer: int
    shell: int
    kind: str
    psi_deg: float
    link_next: bool = False


def _rect_waypoints(z: float, T_WP: np.ndarray, size: tuple[float, float] = SIZE) -> np.ndarray:  # noqa: N803
    lx, ly = size[0] / 2, size[1] / 2
    corners = [(-lx, -ly), (lx, -ly), (lx, ly), (-lx, ly), (-lx, -ly)]
    pts = []
    for (x0, y0), (x1, y1) in zip(corners[:-1], corners[1:], strict=True):
        n = int(np.ceil(np.hypot(x1 - x0, y1 - y0) / DS))
        for k in range(n):
            t = k / n
            pts.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0), z))
    pts.append((corners[-1][0], corners[-1][1], z))
    return frames.transform_points(T_WP, np.array(pts))


def _rot(psi_deg: float) -> np.ndarray:
    return R_DOWN @ frames.rot_z(np.radians(psi_deg))[:3, :3]


class _Builder:
    def __init__(self) -> None:
        self.ws, self.tool = load_workstation(), load_tool()
        self.T_WB, self.T_BW = frames.T_WB(self.ws), frames.T_BW(self.ws)
        self.T_FT = frames.T_FT(self.tool)
        self.q: list[np.ndarray] = []
        self.kind: list[str] = []
        self.ring: list[int] = []
        self.layer: list[int] = []
        self.branch: int | None = 2  # wie Home: Lefty/Above/NoFlip
        self.R = R_DOWN

    def add(self, q: np.ndarray, kind: str, ring: int, layer: int) -> None:
        self.q.append(np.asarray(q, dtype=float))
        self.kind.append(kind)
        self.ring.append(ring)
        self.layer.append(layer)

    def ik(self, p_W: np.ndarray) -> np.ndarray:  # noqa: N803
        T_BT = self.T_BW @ frames.make_T(self.R, p_W)  # noqa: N806
        T_BF = T_BT @ frames.invert(self.T_FT)  # noqa: N806
        sol = robot.ik_nearest(T_BF, self.q[-1], self.branch)
        assert sol is not None, f"unerreichbar: {p_W}"
        self.branch = sol[0]
        return sol[1]

    def p_W(self, q: np.ndarray) -> np.ndarray:  # noqa: N802
        return (self.T_WB @ robot.fk(q) @ self.T_FT)[:3, 3]

    def movej(self, q_to: np.ndarray, kind: str, ring: int, layer: int) -> None:
        q0 = self.q[-1]
        n = max(1, int(np.ceil(np.max(np.abs(q_to - q0)) / STEP_RAD)))
        for k in range(1, n + 1):
            self.add(q0 + (q_to - q0) * k / n, kind, ring, layer)

    def movel(self, p_to: np.ndarray, kind: str, ring: int, layer: int) -> None:
        p0 = self.p_W(self.q[-1])
        n = max(1, int(np.ceil(np.linalg.norm(p_to - p0) / STEP_MM)))
        for k in range(1, n + 1):
            self.add(self.ik(p0 + (p_to - p0) * k / n), kind, ring, layer)

    def travel_in(self, start: np.ndarray, ring: int, layer: int, via: bool) -> None:
        """transfer (mit Zwischenpunkt 120 mm hoeher: zwei movej) -> lower -> approach."""
        above = start + 60.0 * UP
        if via:
            self.movej(self.ik(above + 120.0 * UP), "transfer", ring, layer)
        self.movej(self.ik(above), "transfer", ring, layer)
        self.movel(start + 20.0 * UP, "lower", ring, layer)
        self.movel(start, "approach", ring, layer)

    def travel_out(self, end: np.ndarray, ring: int, layer: int) -> None:
        """retract (Schicht des Rings) -> lift (Schicht + 1)."""
        self.movel(end + 20.0 * UP, "retract", ring, layer)
        self.movel(end + 60.0 * UP, "lift", ring, layer + 1)

    def print_ring(self, wps: np.ndarray, ring: int, layer: int) -> None:
        for k in range(1, len(wps)):
            self.movel(wps[k], "print", ring, layer)


def build_run(out: Path, n_layers: int = 2) -> Path:
    """Schreibt den Laufordner `out` (summary, scene, parts/P01/...) und liefert den Teilordner."""
    b = _Builder()
    T_WP = frames.T_WS(b.ws)  # noqa: N806
    specs = [
        RingSpec(_rect_waypoints((L + 1) * H, T_WP), L, 0, "outer", PSI_DEG[L % len(PSI_DEG)])
        for L in range(n_layers)
    ]
    b.add(robot.HOME_Q, "transfer", 0, 0)
    for r, sp in enumerate(specs):
        L = r
        b.R = _rot(sp.psi_deg)
        b.travel_in(sp.wps[0], r, L, via=r > 0)
        b.print_ring(sp.wps, r, L)
        b.travel_out(sp.wps[-1], r, L)
    return _write(out, b, specs, T_WP, "test_mini_rechteck")


def build_strand_run(out: Path) -> Path:
    """Strang 0 -> 1 -> 2 -> 3 ueber Verbinder, dann Travel und Ring 4 als eigener Strang."""
    b = _Builder()
    T_WP = frames.T_WS(b.ws)  # noqa: N806
    specs = []
    for L in range(2):
        z = (L + 1) * H
        specs.append(RingSpec(_rect_waypoints(z, T_WP), L, 0, "outer", 37.0, link_next=True))
        specs.append(RingSpec(_rect_waypoints(z, T_WP, SIZE_INNER), L, 1, "inner", 37.0, link_next=True))
    specs.append(RingSpec(_rect_waypoints(3 * H, T_WP), 2, 0, "outer", 0.0))
    b.add(robot.HOME_Q, "transfer", 0, 0)
    # Strang A: Ringe 0..3, Pumpe laeuft durch, Verbinder auf die Gerade zum naechsten Ringstart
    b.R = _rot(37.0)
    b.travel_in(specs[0].wps[0], 0, 0, via=False)
    for r in range(4):
        sp = specs[r]
        if r > 0:
            b.movel(sp.wps[0], "link", r, sp.layer)  # Schicht des folgenden Rings (ARTEFAKTE)
        b.print_ring(sp.wps, r, sp.layer)
    b.travel_out(specs[3].wps[-1], 3, specs[3].layer)
    # Strang B: Ring 4 nach Travel (Transfer mit Zwischenpunkt)
    sp = specs[4]
    b.R = _rot(sp.psi_deg)
    b.travel_in(sp.wps[0], 4, sp.layer, via=True)
    b.print_ring(sp.wps, 4, sp.layer)
    b.travel_out(sp.wps[-1], 4, sp.layer)
    return _write(out, b, specs, T_WP, "test_mini_strang")


def _write(out: Path, b: _Builder, specs: list[RingSpec], T_WP: np.ndarray, scenario_id: str) -> Path:  # noqa: N803
    n = len(b.q)
    n_layers = max(sp.layer for sp in specs) + 1
    Q = np.array(b.q)  # noqa: N806
    tcp = [frames.pose7(b.T_WB @ robot.fk(q) @ b.T_FT).tolist() for q in Q]
    traj = Trajectory(
        part_id="P01",
        t_s=[0.1 * i for i in range(n)],
        q=Q.tolist(),
        tcp=tcp,
        layer=b.layer,
        ring=b.ring,
        kind=b.kind,  # type: ignore[arg-type]
        branch=[int(robot.branch_of(q)) for q in Q],
        status=["ok"] * n,
        d_mm=[100.0] * n,
        pair=[None] * n,
        witness=[None] * n,
        psi_rad=[float(np.radians(specs[r].psi_deg)) for r in b.ring],
        summary=TrajectorySummary(
            n=n, n_ok=n, n_warn=0, n_collision=0, n_unreachable=0, d_min_mm=100.0,
            dauer_s=0.1 * (n - 1), zweig_wechsel_in_ringen=0,
        ),
    )  # fmt: skip
    tp = Toolpath(
        part_id="P01",
        layer_height_mm=H,
        bead_width_mm=30.0,
        rings=[
            Ring(
                layer=sp.layer, shell=sp.shell, kind=sp.kind, closed=True, link_next=sp.link_next,  # type: ignore[arg-type]
                waypoints=[[*p, *frames.matrix_to_quat(_rot(sp.psi_deg)).tolist()] for p in sp.wps.tolist()],
            )
            for sp in specs
        ],
    )  # fmt: skip
    eye = np.eye(4).tolist()
    part = PartArtifact(
        part_id="P01", wall_id="box", T_LP=eye, T_SP=eye, T_WP=T_WP.tolist(),
        placement=Placement(x_mm=0.0, y_mm=0.0, yaw_deg=0.0),
        bbox_P=BBox(min=[-100.0, -50.0, 0.0], max=[100.0, 50.0, n_layers * H]),
        volume_mm3=SIZE[0] * SIZE[1] * n_layers * H, n_layers=n_layers, status="machbar", cause=None,
    )  # fmt: skip
    scene = Scene(
        robot=SceneRobot(urdf="third_party/doosan_m1013/urdf/m1013.white.urdf"),
        workstation=SceneWorkstation(
            mesh="workstations/doosantisch.stl", T_WB=b.T_WB.tolist(), T_WS=frames.T_WS(b.ws).tolist()
        ),
        tool=SceneTool(
            mesh="tools/30gut.stl", T_FT=b.T_FT.tolist(), mesh_transform=frames.T_F_mesh(b.tool).tolist()
        ),
        params=SceneParams(
            d_hard_mm=10.0, d_target_mm=50.0, d_target_printed_mm=20.0, r_free_mm=40.0, layer_height_mm=H
        ),
    )
    summary = Summary(
        scenario_id=scenario_id, scenario_path="core/tests/drl_plan.py",
        params={"v_print_mm_s": 100.0},
        assumptions=[], walls=[WallEntry(
            wall_id="box", name="box", eligible=True, reason=None, length_mm=SIZE[0], thickness_mm=SIZE[1],
            height_mm=n_layers * H, volume_mm3=part.volume_mm3, part_ids=["P01"])],
        parts=[PartEntry(part_id="P01", wall_id="box", status="machbar", d_min_mm=100.0, n_collision=0,
                         n_unreachable=0)],
        timings_s={},
        provenance=Provenance(git_commit="test", created="2026-10-18T00:00:00Z", command="pytest"),
    )  # fmt: skip
    part_dir = out / "parts" / "P01"
    dump_json(summary, out / "summary.json")
    dump_json(scene, out / "scene.json")
    dump_json(part, part_dir / "part.json")
    dump_json(tp, part_dir / "toolpath.json")
    dump_json(traj, part_dir / "trajectory.json")
    return part_dir
