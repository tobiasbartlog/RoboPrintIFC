"""Konstruierter Mini-Laufordner fuer die Selbsttests von check_run und fake_drcf.

Erzeugt ohne roboprint, nur mit Pinocchio-FK, numerischer IK und dem Kollisions-Orakel, einen
kleinen Quader (2 Schichten, 2 Schalen) mit Trajektorie und DRL nach spec/ARTEFAKTE.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from verify.oracle.collision_oracle import CollisionOracle, box_part_mesh
from verify.oracle.robot_oracle import (
    HOME_RAD,
    R_to_quat,
    R_to_zyz,
    Rz,
    T_to_pose7,
    default_robot,
    inv_T,
    workstation_frames,
)

SIZE = (200.0, 100.0, 20.0)
CENTER_S = (0.0, -100.0)
PSI = np.pi
H, W_BEAD = 10.0, 30.0
SEED = np.deg2rad([-90.0, 0.0, 90.0, 0.0, 90.0, 0.0])


def _rect(hx: float, hy: float, z: float) -> np.ndarray:
    return np.array([[-hx, -hy, z], [hx, -hy, z], [hx, hy, z], [-hx, hy, z], [-hx, -hy, z]])


class _Builder:
    def __init__(self, center=CENTER_S, step_mm: float = 4.0, dq: float = 0.004):
        self.r = default_robot()
        self.T_WB, self.T_WS, _ = workstation_frames()
        T_SP = np.eye(4)
        T_SP[:3, 3] = [center[0], center[1], 0.0]
        self.T_SP = T_SP
        self.T_WP = self.T_WS @ T_SP
        self.R_WT = Rz(PSI) @ np.diag([1.0, -1.0, -1.0])
        self.step, self.dq = step_mm, dq
        self.q = HOME_RAD.copy()
        self.S: list[dict] = []

    def tcp_W(self, q) -> np.ndarray:
        return self.T_WB @ self.r.fk_tcp(q)

    def ik(self, p_W: np.ndarray, seed) -> np.ndarray:
        T_WT = np.eye(4)
        T_WT[:3, :3] = self.R_WT
        T_WT[:3, 3] = p_W
        T_BF = inv_T(self.T_WB) @ T_WT @ inv_T(self.r.T_FT)
        q, ok = self.r.ik_numeric(T_BF, seed, tol_mm=1e-7)
        if not ok:
            raise RuntimeError(f"IK fuer {p_W} nicht konvergiert")
        # naechste 2pi-Variante zum Seed
        return seed + ((q - seed + np.pi) % (2 * np.pi) - np.pi)

    def add(self, q, kind, ring, layer) -> None:
        self.q = np.array(q, dtype=float)
        self.S.append({"q": self.q.copy(), "kind": kind, "ring": ring, "layer": layer})

    def joint(self, q_to, kind, ring, layer) -> None:
        q0 = self.q.copy()
        n = int(np.ceil(np.abs(q_to - q0).max() / self.dq))
        while True:
            qs = [q0 + (q_to - q0) * (j / n) for j in range(1, n + 1)]
            pts = np.array([self.tcp_W(q)[:3, 3] for q in [q0, *qs]])
            if np.linalg.norm(np.diff(pts, axis=0), axis=1).max() <= self.step:
                break
            n *= 2
        for q in qs:
            self.add(q, kind, ring, layer)

    def line(self, p_from, p_to, kind, ring, layer) -> None:
        p_from, p_to = np.asarray(p_from, float), np.asarray(p_to, float)
        n = max(1, int(np.ceil(np.linalg.norm(p_to - p_from) / self.step)))
        for j in range(1, n + 1):
            p = p_from + (p_to - p_from) * (j / n)
            q = self.ik(p, self.q)
            if np.abs(q - self.q).max() > self.dq:  # feiner unterteilen
                m = int(np.ceil(np.abs(q - self.q).max() / self.dq))
                prev = self.tcp_W(self.q)[:3, 3]
                for k in range(1, m + 1):
                    self.add(self.ik(prev + (p - prev) * (k / m), self.q), kind, ring, layer)
            else:
                self.add(q, kind, ring, layer)


def build(out: Path, part_id: str = "box_0", size=SIZE, center=CENTER_S) -> Path:
    """Schreibt einen bestehenden Mini-Laufordner nach `out` und gibt den Pfad zum Szenario zurueck."""
    b = _Builder(center)
    lx, ly, lz = size
    mesh = box_part_mesh(size)
    n_layers = int(round(lz / H))
    rings = []
    for L in range(n_layers):
        for s in range(2):
            off = (s + 0.5) * W_BEAD
            rings.append({"layer": L, "shell": s, "kind": "outer" if s == 0 else "inner", "closed": True,
                          "P": _rect(lx / 2 - off, ly / 2 - off, (L + 1) * H)})
    quat = R_to_quat(b.R_WT)
    for rg in rings:
        pW = rg["P"] @ b.T_WP[:3, :3].T + b.T_WP[:3, 3]
        rg["W"] = pW
        rg["waypoints"] = [[*p.tolist(), *quat.tolist()] for p in pW]
    up = np.array([0.0, 0.0, 1.0])
    last_L = None
    for r, rg in enumerate(rings):
        start = rg["W"][0]
        k_trav = 0 if last_L is None else last_L + 1
        z_top = b.T_WP[2, 3] + k_trav * H
        travel = start + up * (max(z_top + 30.0, start[2] + 20.0) - start[2] + 20.0)
        if r > 0:
            p = b.tcp_W(b.q)[:3, 3]
            b.line(p, np.array([p[0], p[1], travel[2]]), "lift", r - 1, k_trav)
        q_t = b.ik(travel, SEED if r == 0 else b.q)
        b.joint(q_t, "transfer", r, k_trav)
        b.line(travel, start + 20 * up, "lower", r, k_trav)
        b.line(start + 20 * up, start, "approach", r, rg["layer"])
        for a, c in zip(rg["W"][:-1], rg["W"][1:], strict=True):
            b.line(a, c, "print", r, rg["layer"])
        end = rg["W"][-1]
        b.line(end, end + 20 * up, "retract", r, rg["layer"])
        last_L = rg["layer"]
    p = b.tcp_W(b.q)[:3, 3]
    b.line(p, p + 30 * up, "lift", len(rings) - 1, last_L + 1)

    world = CollisionOracle(mesh, b.T_WP, H, 40.0)
    N = len(b.S)
    traj = {k: [] for k in ("t_s", "q", "tcp", "layer", "ring", "kind", "branch", "status", "d_mm", "pair",
                            "witness", "psi_rad")}
    for i, s in enumerate(b.S):
        st, c = world.status_of_pose(s["q"], s["layer"], 10.0, 50.0, 20.0)  # SPEC §2
        sg = b.r.branch_signs(s["q"])
        traj["t_s"].append(0.01 * i)
        traj["q"].append(s["q"].tolist())
        traj["tcp"].append(T_to_pose7(b.tcp_W(s["q"])).tolist())
        traj["layer"].append(int(s["layer"]))
        traj["ring"].append(int(s["ring"]))
        traj["kind"].append(s["kind"])
        traj["branch"].append(int((sg[0] > 0) * 4 + (sg[1] > 0) * 2 + (sg[2] > 0)))
        traj["status"].append(st)
        traj["d_mm"].append(float(c.d_mm))
        traj["pair"].append(list(c.pair))
        traj["witness"].append([np.asarray(w).tolist() for w in c.witness_W])
        traj["psi_rad"].append(PSI)
    dmin = float(min(traj["d_mm"]))
    counts = {k: traj["status"].count(k) for k in ("ok", "warn", "collision", "unreachable")}
    traj.update(schema_version="2", part_id=part_id, summary={
        "n": N, "n_ok": counts["ok"], "n_warn": counts["warn"], "n_collision": counts["collision"],
        "n_unreachable": counts["unreachable"], "d_min_mm": dmin, "dauer_s": 0.01 * (N - 1),
        "zweig_wechsel_in_ringen": 0})
    pdir = out / "parts" / part_id
    pdir.mkdir(parents=True, exist_ok=True)
    mesh.export(str(pdir / "part.stl"))
    lo, hi = mesh.bounds
    _dump(pdir / "part.json", {
        "schema_version": "2", "part_id": part_id, "wall_id": "box", "T_LP": np.eye(4).tolist(),
        "T_SP": b.T_SP.tolist(), "T_WP": b.T_WP.tolist(),
        "placement": {"x_mm": center[0], "y_mm": center[1], "yaw_deg": 0.0},
        "bbox_P": {"min": lo.tolist(), "max": hi.tolist()}, "volume_mm3": float(mesh.volume),
        "n_layers": n_layers, "status": "machbar", "cause": None})
    _dump(pdir / "toolpath.json", {
        "schema_version": "2", "part_id": part_id, "layer_height_mm": H, "bead_width_mm": W_BEAD,
        "rings": [{k: rg[k] for k in ("layer", "shell", "kind", "closed", "waypoints")} for rg in rings]})
    _dump(pdir / "trajectory.json", traj)
    params = {"layer_height_mm": H, "bead_width_mm": W_BEAD, "d_hard_mm": 10.0, "d_target_mm": 50.0,
              "d_target_printed_mm": 20.0, "r_free_mm": 40.0}
    _dump(out / "summary.json", {
        "schema_version": "2", "scenario_id": "MINI", "scenario_path": "", "params": params,
        "assumptions": [], "walls": [{"wall_id": "box", "name": "box", "eligible": True, "reason": None,
                                      "length_mm": lx, "thickness_mm": ly, "height_mm": lz,
                                      "volume_mm3": float(mesh.volume), "part_ids": [part_id]}],
        "parts": [{"part_id": part_id, "wall_id": "box", "status": "machbar", "d_min_mm": dmin,
                   "n_collision": 0, "n_unreachable": 0}],
        "timings_s": {}, "provenance": {"git_commit": "", "created": "", "command": "minirun"}})
    _dump(out / "scene.json", {
        "schema_version": "2", "robot": {"urdf": "third_party/doosan_m1013/urdf/m1013.white.urdf"},
        "workstation": {"mesh": "workstations/doosantisch.stl", "T_WB": b.T_WB.tolist(),
                        "T_WS": b.T_WS.tolist()},
        "tool": {"mesh": "tools/30gut.stl", "T_FT": b.r.T_FT.tolist(),
                 "mesh_transform": b.r.T_F_toolmesh.tolist()},
        "params": {**{k: params[k] for k in ("d_hard_mm", "d_target_mm", "d_target_printed_mm", "r_free_mm",
                                                "layer_height_mm")}}})
    scen = out / "scenario.json"
    _dump(scen, {"schema_version": "1", "id": "MINI", "mode": "modul",
                 "source": {"kind": "box", "size_mm": list(size)}, "decompose": False, "params": {},
                 "planner_mode": "collision_aware", "expect": {"parts": "all_feasible"}})
    for dialect in ("v2", "v3"):
        (pdir / f"program.{dialect}.drl").write_text(emit_drl(b, traj, rings, dialect), encoding="utf-8")
    return scen


def _dump(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=1), encoding="utf-8")


def _posx(b: _Builder, q) -> str:
    T_BT = b.r.fk_tcp(q)
    a, bb, c = R_to_zyz(T_BT[:3, :3])
    x, y, z = T_BT[:3, 3]
    return f"posx({x:.4f}, {y:.4f}, {z:.4f}, {a:.6f}, {bb:.6f}, {c:.6f})"


def _posj(q) -> str:
    return "posj(" + ", ".join(f"{v:.6f}" for v in np.rad2deg(q)) + ")"


def emit_drl(b: _Builder, traj: dict, rings: list, dialect: str) -> str:
    """Minimaler DRL-Emitter nach SPEC §5.6 (nur fuer Selbsttests)."""
    q = np.array(traj["q"])
    kinds = traj["kind"]
    ring = traj["ring"]
    lines = [
        f"# Selbsttest-Programm, Dialekt {dialect}. Trockenlauf mit reduzierter Geschwindigkeit vor dem "
        "ersten Druck.",
        "set_velx(100, 30)", "set_accx(400, 120)", "set_velj(30)", "set_accj(60)",
        'set_tcp("FGC_30GUT")', "set_singularity_handling(DR_VAR_VEL)",
        "set_mode_analog_output(ch=1, mod=DR_ANALOG_VOLTAGE)",
        f"movej({_posj(HOME_RAD)}, vel=30, acc=60)",
        "try:",
    ]
    ind = "    "
    i, N = 0, len(kinds)
    while i < N:
        j = i
        while j + 1 < N and kinds[j + 1] == kinds[i] and ring[j + 1] == ring[i]:
            j += 1
        k = kinds[i]
        if k == "transfer":
            lines.append(ind + f"movej({_posj(q[j])}, vel=30, acc=60)")
        elif k == "print":
            lines.append(ind + "set_analog_output(ch=1, val=5.0)")
            lines.append(ind + "wait(3.0)")
            W = np.array(rings[ring[i]]["W"])
            idx = [i]
            for p in W[1:]:
                d = np.linalg.norm(np.array([t[:3] for t in traj["tcp"][i:j + 1]]) - p, axis=1)
                idx.append(i + int(np.argmin(d)))
            for n, s in enumerate(idx[1:]):
                last = n == len(idx) - 2
                rad = 0.0 if last else 2.0
                lines.append(ind + f"movel({_posx(b, q[s])}, vel=100, acc=400, radius={rad}, ref=DR_BASE, "
                             "ra=DR_MV_RA_DUPLICATE)")
            lines.append(ind + "set_analog_output(ch=1, val=0)")
        else:
            lines.append(ind + f"movel({_posx(b, q[j])}, vel=100, acc=400, ref=DR_BASE)")
        i = j + 1
    lines += ["except Exception as e:", ind + "set_analog_output(ch=1, val=0)", ind + "raise e",
              "set_analog_output(ch=1, val=0)"]
    return "\n".join(lines) + "\n"
