"""Pruefungen je Teil fuer check_run (G3): Struktur, FK, Grenzen, Schichtregel, Ablauf je Strang,
Abtastdichte, Bahntreue, Verbinder, Zweige, Abdeckung, Status. Alles unabhaengig von roboprint.
Die Strang-Regeln selbst stehen in strand_rules.py (ohne Roboter- und Kollisionsmodell)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from verify.oracle.robot_oracle import RobotOracle, inv_T, quat_to_R, rot_angle
from verify.oracle.run_geometry import coverage, section_P
from verify.oracle.strand_rules import (
    KINDS,
    LINK_MAX_DEFAULT,
    branch_changes,
    expected_layers,
    link_errors,
    sequence_errors,
    strand_rings,
    strand_runs,
)

STATUSES = ("ok", "warn", "collision", "unreachable")
RANK = {"collision": 0, "warn": 1, "ok": 2}

# Toleranzen (README)
TCP_POS_TOL = 0.05  # mm, eigene FK gegen tcp[i]
TCP_ROT_TOL = 1e-4  # rad
STEP_TCP = 5.0 + 0.05  # mm
STEP_Q = 0.005 + 1e-6  # rad
PATH_TOL = 0.5  # mm
RING_COVER_TOL = 1.0  # mm, jeder Ringpunkt nahe der gefahrenen Druckbahn
AXIS_TOL_DEG = 0.1
G2_TOL_NEG = 12.0  # roboprint darf bis zu 12 mm konservativer sein
G2_TOL_POS = 1.0  # und hoechstens 1 mm optimistischer


@dataclass
class Params:
    h: float = 10.0
    w: float = 30.0
    shells: int = 2
    d_hard: float = 10.0
    d_target: float = 50.0
    d_target_printed: float = 20.0  # Sollabstand gegen den Druckstand (Nutzerentscheidung 19.10.2026)
    r_free: float = 40.0
    tau_max_deg: float = 0.0
    link_max: float = LINK_MAX_DEFAULT  # mm, laengster Verbinder (SPEC §10); 0 = keine Verbinder

    def thresholds(self) -> list[float]:
        """Schwellen fuer d (d_status): Kollision, d_hard, Toleranz."""
        return [0.0, self.d_hard, G2_TOL_NEG]

    def status_thresholds(self) -> list[float]:
        """Schwellen fuer e = min(d_uebrige, d_Druckstand + d_target - d_target_printed): Warnschwelle
        mit den G2-Toleranzen. e < d_target <=> ein zaehlendes Paar liegt unter seinem Sollabstand."""
        return [self.d_target - G2_TOL_POS, self.d_target, self.d_target + G2_TOL_NEG]

    @property
    def printed_shift(self) -> float:
        return self.d_target - self.d_target_printed


@dataclass
class Findings:
    errors: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def capped(self, key: str, msgs: list[str], limit: int = 5) -> None:
        if msgs:
            more = f" (+{len(msgs) - limit} weitere)" if len(msgs) > limit else ""
            self.err(f"{key}: {len(msgs)} Verstoesse, z. B. " + "; ".join(msgs[:limit]) + more)


def status_of(d: float, d_target: float) -> str:
    """Status aus dem auf d_target normierten Abstand e (siehe Params.status_thresholds)."""
    return "collision" if d < 0 else ("warn" if d < d_target else "ok")


def allowed_statuses(d: float, printed: bool, prm: Params) -> set[str]:
    """Status, den ein Sample mit kleinstem zaehlendem Abstand d (Paar am Druckstand: printed)
    haben darf, allein aus den eigenen Artefaktwerten (d_mm, pair). Regel: Druckstand warnt unter
    d_target_printed, jedes andere Paar unter d_target, d_mm ist das Minimum aller zaehlenden Paare."""
    if d < 0:
        return {"collision"}
    if printed:
        if d < prm.d_target_printed:
            return {"warn"}
        return {"ok"} if d >= prm.d_target else {"ok", "warn"}
    return {"warn"} if d < prm.d_target else {"ok"}


def load_json(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _require(obj: dict, keys, where: str, F: Findings) -> bool:
    missing = [k for k in keys if k not in obj]
    if missing:
        F.err(f"{where}: Schluessel fehlen {missing}")
    if obj.get("schema_version") != "2":
        F.err(f"{where}: schema_version ist {obj.get('schema_version')!r}, erwartet '2'")
    return not missing


def T_SP_from(placement: dict) -> np.ndarray:
    th = np.deg2rad(float(placement["yaw_deg"]))
    T = np.eye(4)
    T[:3, :3] = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    T[:3, 3] = [float(placement["x_mm"]), float(placement["y_mm"]), 0.0]
    return T


# --------------------------------------------------------------------------- Laden


@dataclass
class PartData:
    pid: str
    dir: Path
    part: dict
    mesh: trimesh.Trimesh
    T_WP: np.ndarray
    toolpath: dict
    traj_summary: dict  # trajectory.summary; die Roh-Listen werden nach dem Laden verworfen
    N: int
    q: np.ndarray
    tcp: np.ndarray
    layer: np.ndarray
    ring: np.ndarray
    kind: list
    branch: np.ndarray
    status: list
    d_mm: np.ndarray
    reach: np.ndarray  # bool: nicht unreachable
    ring_layer: np.ndarray
    on_printed: np.ndarray | None = None  # bool: Paar des Minimums enthaelt den Druckstand


_INTERN = {s: s for s in (*STATUSES, *KINDS)}


def load_part(pdir: Path, T_WS: np.ndarray, F: Findings) -> PartData | None:
    tag = pdir.name
    files = {n: pdir / n for n in ("part.json", "part.stl", "toolpath.json", "trajectory.json")}
    for n, p in files.items():
        if not p.is_file():
            F.err(f"{tag}: {n} fehlt")
    if any(not p.is_file() for p in files.values()):
        return None
    part = load_json(files["part.json"])
    _require(part, ("part_id", "wall_id", "T_LP", "T_SP", "T_WP", "placement", "bbox_P", "volume_mm3",
                    "n_layers", "status", "cause"), f"{tag}/part.json", F)
    mesh = trimesh.load(str(files["part.stl"]), force="mesh")
    mesh.merge_vertices()
    if not mesh.is_watertight:
        F.err(f"{tag}: part.stl ist kein geschlossenes Solid")
    T_WP = np.array(part.get("T_WP", np.eye(4)), dtype=float)
    try:
        T_SP_pl = T_SP_from(part["placement"])
        if np.abs(np.array(part["T_SP"], dtype=float) - T_SP_pl).max() > 1e-6 * 1000:
            F.err(f"{tag}: T_SP passt nicht zu placement")
        if np.abs(T_WS @ T_SP_pl - T_WP).max() > 1e-3:
            F.err(f"{tag}: T_WP != T_WS * T_SP(placement)")
        lo, hi = mesh.bounds
        bb = part["bbox_P"]
        if np.abs(np.array(bb["min"]) - lo).max() > 0.5 or np.abs(np.array(bb["max"]) - hi).max() > 0.5:
            F.err(f"{tag}: bbox_P {bb} passt nicht zu part.stl {lo.tolist()} {hi.tolist()}")
        if abs(lo[2]) > 0.5:
            F.err(f"{tag}: Teil-Unterkante z_P = {lo[2]:.3f} mm, erwartet 0 (Frame P)")
        if mesh.is_watertight and abs(float(part["volume_mm3"]) - mesh.volume) > 5e-3 * mesh.volume:
            F.err(f"{tag}: volume_mm3 {part['volume_mm3']} != Volumen part.stl {mesh.volume:.0f}")
    except (KeyError, TypeError, ValueError) as exc:
        F.err(f"{tag}: part.json unlesbar: {exc}")
    tp = load_json(files["toolpath.json"])
    _require(tp, ("part_id", "layer_height_mm", "bead_width_mm", "rings"), f"{tag}/toolpath.json", F)
    tr = load_json(files["trajectory.json"])
    try:
        return _from_trajectory(tag, pdir, part, mesh, T_WP, tp, tr, F)
    finally:
        tr.clear()  # Roh-Listen sofort freigeben (nur Arrays bleiben)


def _from_trajectory(tag, pdir, part, mesh, T_WP, tp, tr, F) -> PartData | None:
    arrays = ("t_s", "q", "tcp", "layer", "ring", "kind", "branch", "status", "d_mm", "pair", "witness",
              "psi_rad")
    if not _require(tr, (*arrays, "part_id", "summary"), f"{tag}/trajectory.json", F):
        return None
    N = len(tr["t_s"])
    bad = [a for a in arrays if len(tr[a]) != N]
    if bad or N == 0:
        F.err(f"{tag}: Arrays ungleich lang oder leer: {bad} (N={N})")
        return None
    t = np.array(tr["t_s"], dtype=float)
    if np.any(np.diff(t) <= 0):
        F.err(f"{tag}: t_s nicht streng monoton (erste Stelle {int(np.argmax(np.diff(t) <= 0))})")
    try:
        q = np.array(tr["q"], dtype=float).reshape(N, 6)
        tcp = np.array(tr["tcp"], dtype=float).reshape(N, 7)
        layer = np.array(tr["layer"], dtype=int)
        ring = np.array(tr["ring"], dtype=int)
        branch = np.array(tr["branch"], dtype=int)
    except (TypeError, ValueError) as exc:
        F.err(f"{tag}: Arrays nicht numerisch/formgerecht: {exc}")
        return None
    kind = [_INTERN.get(x, x) for x in tr["kind"]]
    status = [_INTERN.get(x, x) for x in tr["status"]]
    if set(kind) - set(KINDS):
        F.err(f"{tag}: unbekannte kind-Werte {sorted(set(kind) - set(KINDS))}")
    if set(status) - set(STATUSES):
        F.err(f"{tag}: unbekannte status-Werte {sorted(set(status) - set(STATUSES))}")
    if np.any((branch < 0) | (branch > 7)):
        F.err(f"{tag}: branch ausserhalb 0..7")
    reach = np.array([s != "unreachable" for s in status])
    d = np.full(N, np.nan)
    on_printed = np.zeros(N, dtype=bool)
    for i in range(N):
        v, p, w = tr["d_mm"][i], tr["pair"][i], tr["witness"][i]
        on_printed[i] = isinstance(p, list) and "printed" in p
        if reach[i]:
            if v is None or p is None or w is None:
                F.err(f"{tag}: Sample {i} ({status[i]}) ohne d_mm/pair/witness")
                break
            d[i] = float(v)
        elif v is not None or p is not None or w is not None:
            F.err(f"{tag}: Sample {i} unreachable, aber d_mm/pair/witness nicht null")
            break
    rings = tp.get("rings", [])
    ring_layer = np.array([int(r["layer"]) for r in rings], dtype=int) if rings else np.zeros(0, int)
    if np.any((ring < 0) | (ring >= max(len(rings), 1))):
        F.err(f"{tag}: ring-Index ausserhalb toolpath.rings")
        return None
    summary = tr.get("summary")
    return PartData(tag, pdir, part, mesh, T_WP, tp, summary if isinstance(summary, dict) else {}, N, q,
                    tcp, layer, ring, kind, branch, status, d, reach, ring_layer, on_printed)


# --------------------------------------------------------------------------- Kinematik


def check_kinematics(P: PartData, robot: RobotOracle, T_WB: np.ndarray, F: Findings):
    """Eigene FK je erreichbarem Sample. Rueckgabe (TCP-Position W (N,3), R_WT (N,3,3))."""
    pos = np.full((P.N, 3), np.nan)
    rot = np.full((P.N, 3, 3), np.nan)
    bad_fk, bad_lim = [], []
    for i in np.flatnonzero(P.reach):
        T = T_WB @ robot.fk_tcp(P.q[i])
        pos[i], rot[i] = T[:3, 3], T[:3, :3]
        e = float(np.linalg.norm(T[:3, 3] - P.tcp[i, :3]))
        a = rot_angle(T[:3, :3], quat_to_R(P.tcp[i, 3:]))
        if e > TCP_POS_TOL or a > TCP_ROT_TOL:
            bad_fk.append(f"#{i} dp={e:.4f} mm dR={a:.2e} rad")
        if not robot.in_limits(P.q[i]):
            bad_lim.append(f"#{i} q={np.round(P.q[i], 4).tolist()}")
    F.capped(f"{P.pid}: tcp[i] != FK(q[i])", bad_fk)
    F.capped(f"{P.pid}: q ausserhalb der Gelenkgrenzen", bad_lim)
    return pos, rot


def link_next_flags(P: PartData) -> list[bool]:
    """toolpath.rings[r].link_next (Default false, nur JSON true zaehlt)."""
    return [r.get("link_next", False) is True for r in P.toolpath.get("rings", [])]


def check_layer_rule(P: PartData, F: Findings) -> None:
    """Schichtregel und Ablauf je Strang nach ARTEFAKTE (strand_rules)."""
    exp = expected_layers(P.kind, P.ring, P.ring_layer)
    bad = [f"#{i} {P.kind[i]} ring {P.ring[i]}: layer {P.layer[i]} statt {exp[i]}"
           for i in np.flatnonzero(P.layer != exp)]
    F.capped(f"{P.pid}: layer-Regel (ARTEFAKTE)", bad)
    F.capped(f"{P.pid}: Ablauf je Strang",
             sequence_errors(P.kind, P.ring, link_next_flags(P), len(P.ring_layer)))


def check_density(P: PartData, pos: np.ndarray, F: Findings) -> None:
    both = P.reach[:-1] & P.reach[1:]
    dp = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    dq = np.abs(np.diff(P.q, axis=0)).max(axis=1)
    bad_p = np.flatnonzero(both & (dp > STEP_TCP))
    bad_q = np.flatnonzero(both & (dq > STEP_Q))
    F.metrics["max_step_tcp_mm"] = float(np.nanmax(np.where(both, dp, np.nan))) if both.any() else 0.0
    F.metrics["max_step_q_rad"] = float(np.nanmax(np.where(both, dq, np.nan))) if both.any() else 0.0
    F.capped(f"{P.pid}: TCP-Schritt > 5 mm", [f"#{i}->{i + 1} {dp[i]:.3f} mm" for i in bad_p])
    F.capped(f"{P.pid}: Gelenkschritt > 0,005 rad", [f"#{i}->{i + 1} {dq[i]:.5f} rad" for i in bad_q])


def _seg_dist(p: np.ndarray, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Abstand der Punkte p (n,3) zum Polygonzug mit Segmenten A->B (m,3): (n,)."""
    AB = B - A
    L2 = np.maximum((AB * AB).sum(1), 1e-12)
    t = np.clip(((p[:, None, :] - A[None]) * AB[None]).sum(2) / L2[None], 0.0, 1.0)
    proj = A[None] + t[..., None] * AB[None]
    return np.sqrt(((p[:, None, :] - proj) ** 2).sum(2)).min(1)


def _densify(W: np.ndarray, step: float) -> np.ndarray:
    pts = [W[0]]
    for a, b in zip(W[:-1], W[1:], strict=True):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        pts += [a + (b - a) * (j / n) for j in range(1, n + 1)]
    return np.array(pts)


def print_segments(P: PartData, with_start: bool = False) -> dict[int, np.ndarray]:
    """Ring -> Indizes seiner Druck-Samples (zusammenhaengend vorausgesetzt, s. Ablaufpruefung).
    with_start: das letzte approach- oder link-Sample desselben Rings (Ringstart) wird vorangestellt."""
    out: dict[int, list] = {}
    for i in range(P.N):
        if P.kind[i] == "print":
            r = int(P.ring[i])
            if (with_start and r not in out and i > 0 and P.kind[i - 1] in ("approach", "link")
                    and P.ring[i - 1] == r):
                out[r] = [i - 1]
            out.setdefault(r, []).append(i)
    return {r: np.array(v) for r, v in out.items()}


def check_toolpath(P: PartData, pos, rot, prm: Params, F: Findings) -> None:
    rings = P.toolpath.get("rings", [])
    bad_z, bad_path, bad_axis, bad_cover = [], [], [], []
    max_dev, max_axis = 0.0, 0.0
    invP = inv_T(P.T_WP)
    for r, ring in enumerate(rings):
        W = np.array(ring["waypoints"], dtype=float)
        if W.ndim != 2 or W.shape[1] != 7 or len(W) < 2:
            bad_path.append(f"Ring {r}: Wegpunkte unbrauchbar")
            continue
        zP = W[:, :3] @ invP[2, :3] + invP[2, 3]
        exp = (int(ring["layer"]) + 1) * prm.h
        if np.abs(zP - exp).max() > PATH_TOL:
            bad_z.append(f"Ring {r} (Schicht {ring['layer']}): z_P {zP.min():.2f}..{zP.max():.2f}, "
                         f"erwartet {exp}")
        if ring.get("closed") and np.linalg.norm(W[0, :3] - W[-1, :3]) > 1e-6:
            bad_path.append(f"Ring {r}: closed, aber letzter Wegpunkt != erster")
    segs = print_segments(P, with_start=True)
    for r, idx in segs.items():
        if r >= len(rings):
            continue
        W = np.array(rings[r]["waypoints"], dtype=float)[:, :3]
        idx = idx[P.reach[idx]]
        if len(idx) < 2:
            bad_cover.append(f"Ring {r}: < 2 erreichbare Druck-Samples")
            continue
        dev = _seg_dist(pos[idx], W[:-1], W[1:])
        max_dev = max(max_dev, float(dev.max()))
        for i in idx[dev > PATH_TOL][:3]:
            bad_path.append(f"#{i} Ring {r}: {dev[np.searchsorted(idx, i)]:.3f} mm neben der Bahn")
        axis = rot[idx][:, :, 2]
        ang = np.degrees(np.arccos(np.clip(-axis[:, 2], -1.0, 1.0)))
        max_axis = max(max_axis, float(ang.max()))
        for j in np.flatnonzero(ang > prm.tau_max_deg + AXIS_TOL_DEG)[:3]:
            bad_axis.append(f"#{idx[j]} Ring {r}: Duesenachse {ang[j]:.3f} deg gegen -Z_W")
        dense = _densify(W, 5.0)
        back = _seg_dist(dense, pos[idx[:-1]], pos[idx[1:]])
        if back.max() > RING_COVER_TOL:
            j = int(np.argmax(back))
            bad_cover.append(f"Ring {r}: Bahnpunkt {np.round(dense[j], 1).tolist()} nicht abgefahren "
                             f"({back[j]:.2f} mm)")
    F.metrics["max_path_dev_mm"] = max_dev
    F.metrics["max_axis_dev_deg"] = max_axis
    F.capped(f"{P.pid}: Wegpunkte nicht auf z_P = (L+1)*h", bad_z)
    F.capped(f"{P.pid}: Druck-Sample > 0,5 mm neben dem Druckring", bad_path)
    F.capped(f"{P.pid}: Duesenachse > tau_max + 0,1 deg", bad_axis)
    F.capped(f"{P.pid}: Druckring nicht vollstaendig abgefahren", bad_cover)


def check_links(P: PartData, pos: np.ndarray, rot: np.ndarray, prm: Params, F: Findings) -> None:
    """Verbinder (SPEC §5.3, §11 G3): Gerade, Endpunkte, Laenge <= link_max, Schichtsprung 0/1,
    Projektion im Querschnitt aus part.stl (strand_rules.link_errors); Duesenachse wie beim Druck."""
    is_link = np.array([k == "link" for k in P.kind], dtype=bool)
    if not is_link.any():
        F.metrics.update(n_links=0)
        return
    try:
        wps = [np.asarray(r.get("waypoints", []), dtype=float).reshape(-1, 7)
               for r in P.toolpath.get("rings", [])]
    except (TypeError, ValueError):
        wps = []
    if not wps or any(len(w) == 0 for w in wps):
        F.err(f"{P.pid}: Verbinder nicht pruefbar, Wegpunkte fehlen oder sind unbrauchbar")
        return
    sections: dict[int, object] = {}

    def section_of(L: int):
        if L not in sections:
            sections[L] = section_P(P.mesh, (L + 0.5) * prm.h)
        return sections[L]

    errs, metrics = link_errors(P.kind, P.ring, pos, P.reach, wps, P.ring_layer, prm.link_max,
                                inv_T(P.T_WP), section_of)
    F.metrics.update(metrics)
    F.capped(f"{P.pid}: Verbinder (SPEC §5.3)", errs)
    idx = np.flatnonzero(is_link & P.reach)
    ang = np.degrees(np.arccos(np.clip(-rot[idx][:, 2, 2], -1.0, 1.0)))
    F.capped(f"{P.pid}: Verbinder: Duesenachse > tau_max + 0,1 deg",
             [f"#{i} {a:.3f} deg gegen -Z_W" for i, a in zip(idx, ang, strict=True)
              if a > prm.tau_max_deg + AXIS_TOL_DEG])


def check_branches(P: PartData, robot: RobotOracle, F: Findings) -> None:
    """Kein Zweigwechsel innerhalb eines Strangs (approach, print, link, retract ohne Travel dazwischen;
    roboprint-Bits und eigene Klassifikation) und eineindeutige Zuordnung eigene Klasse <-> branch
    abseits der Singularitaeten."""
    bad, mapping, inverse, conflicts = [], {}, {}, []
    for idx in strand_runs(P.kind):
        idx = idx[P.reach[idx]]
        if len(idx) == 0:
            continue
        where = strand_rings(P.ring, idx)
        if len(set(P.branch[idx].tolist())) > 1:
            j = int(np.flatnonzero(np.diff(P.branch[idx]) != 0)[0]) + 1
            bad.append(f"Strang {where}: branch {sorted(set(P.branch[idx].tolist()))}, erster Wechsel bei "
                       f"#{idx[j]} ({P.kind[idx[j]]})")
        n_rings = len({int(P.ring[i]) for i in idx})
        ref = [0, 0, 0]
        for i in idx[:: max(1, len(idx) // (50 * n_rings))].tolist() + [int(idx[-1])]:
            s = robot.branch_signs(P.q[i], eps=1e-3)
            for c in range(3):
                if s[c] == 0:
                    continue
                if ref[c] and s[c] != ref[c]:
                    name = ("Schulter", "Ellbogen", "Hand")[c]
                    bad.append(f"Strang {where}: eigene Konfiguration wechselt ({name}) bei #{i} "
                               f"({P.kind[i]})")
                ref[c] = s[c]
    for i in np.flatnonzero(P.reach)[:: max(1, P.N // 400)]:
        s = robot.branch_signs(P.q[i], eps=0.05)
        if 0 in s:
            continue
        b = int(P.branch[i])
        if mapping.setdefault(s, b) != b or inverse.setdefault(b, s) != s:
            conflicts.append(f"#{i}: Klasse {s} -> branch {b}, vorher {mapping[s]}/{inverse[b]}")
    F.capped(f"{P.pid}: Zweigwechsel innerhalb eines Strangs", bad)
    F.capped(f"{P.pid}: branch nicht eineindeutig zur Konfiguration", conflicts)


def check_coverage(P: PartData, pos: np.ndarray, prm: Params, F: Findings) -> None:
    invP = inv_T(P.T_WP)
    H = float(P.mesh.bounds[1][2])
    n_layers = int(np.ceil(H / prm.h - 1e-6))
    if int(P.part.get("n_layers", n_layers)) != n_layers:
        F.err(f"{P.pid}: n_layers {P.part.get('n_layers')} != ceil(H/h) = {n_layers}")
    segs = print_segments(P, with_start=True)
    by_layer: dict[int, list] = {}
    for r, idx in segs.items():
        idx = idx[P.reach[idx]]
        if len(idx) >= 2:
            pP = pos[idx] @ invP[:3, :3].T + invP[:3, 3]
            by_layer.setdefault(int(P.ring_layer[r]), []).append(pP[:, :2])
    worst, bad = 1.0, []
    for L in range(n_layers):
        z = (L + 0.5) * prm.h
        if z >= H:
            continue
        sec = section_P(P.mesh, z)
        cov, area = coverage(sec, by_layer.get(L, []), prm.shells, prm.w)
        worst = min(worst, cov)
        if cov < 0.95:
            bad.append(f"Schicht {L}: {100 * cov:.1f} % von {area:.0f} mm2")
    F.metrics["coverage_min"] = worst
    F.capped(f"{P.pid}: Abdeckung < 95 %", bad)


def check_status(P: PartData, lb: np.ndarray, ub: np.ndarray, pairs: list, prm: Params, F: Findings,
                 evaluated: np.ndarray, lbe: np.ndarray | None = None) -> dict:
    """Eigener Status (roboprint) gegen Pruefer-Intervall [lb, ub] fuer d_status und lbe fuer den
    normierten Abstand e (alle Schwellen entschieden). Ohne lbe gilt e = d (ein Sollabstand)."""
    if lbe is None:
        lbe = lb
    own_bad, cmp_bad, hard_bad = [], [], []
    n_chk_coll = 0
    for i in np.flatnonzero(evaluated):
        s = P.status[i]
        d_rp = P.d_mm[i]
        on_p = bool(P.on_printed[i]) if getattr(P, "on_printed", None) is not None else False
        if s not in allowed_statuses(d_rp, on_p, prm):
            own_bad.append(f"#{i} status {s} passt nicht zu d_mm {d_rp:.3f} (Paar am Druckstand: {on_p})")
        if d_rp < prm.d_hard:
            hard_bad.append(f"#{i} roboprint d={d_rp:.2f} mm")
        if ub[i] < 0:
            n_chk_coll += 1
            if s != "collision":
                cmp_bad.append(f"#{i} {P.kind[i]}: Pruefer collision ({pairs[i]}), roboprint {s} "
                               f"d={d_rp:.2f}")
            continue
        dc = lb[i]
        if not np.isfinite(dc) or dc < 0:
            cmp_bad.append(f"#{i}: Pruefer-Intervall unentschieden [{lb[i]}, {ub[i]}]")
            continue
        if dc < prm.d_hard:
            hard_bad.append(f"#{i} Pruefer d in [{lb[i]:.2f}, {ub[i]:.2f}] mm ({pairs[i]})")
        ec = lbe[i]
        lo_s, hi_s = status_of(ec - G2_TOL_NEG, prm.d_target), status_of(ec + G2_TOL_POS, prm.d_target)
        if not RANK[lo_s] <= RANK.get(s, -1) <= RANK[hi_s]:
            cmp_bad.append(f"#{i} {P.kind[i]}: roboprint {s} (d={d_rp:.2f}), Pruefer d in "
                           f"[{lb[i]:.2f}, {ub[i]:.2f}], e = {ec:.2f} ({pairs[i]})")
    F.capped(f"{P.pid}: status passt nicht zu d_mm", own_bad)
    F.capped(f"{P.pid}: eigener Status != Pruefer-Status", cmp_bad)
    F.capped(f"{P.pid}: d < d_hard", hard_bad)
    ev = evaluated & (ub >= 0)
    F.metrics["checker_d_min_lb_mm"] = float(lb[ev].min()) if ev.any() else None
    F.metrics["checker_n_collision"] = n_chk_coll
    return {"n_checker_collision": n_chk_coll}


def check_summary(P: PartData, prm: Params, F: Findings) -> None:
    s = P.traj_summary
    counts = {k: sum(1 for x in P.status if x == k) for k in STATUSES}
    exp = {"n": P.N, "n_ok": counts["ok"], "n_warn": counts["warn"], "n_collision": counts["collision"],
           "n_unreachable": counts["unreachable"]}
    for k, v in exp.items():
        if s.get(k) != v:
            F.err(f"{P.pid}: trajectory.summary.{k} = {s.get(k)}, gezaehlt {v}")
    if P.reach.any():
        dmin = float(np.nanmin(P.d_mm))
        if s.get("d_min_mm") is None or abs(float(s["d_min_mm"]) - dmin) > 1e-3:
            F.err(f"{P.pid}: trajectory.summary.d_min_mm = {s.get('d_min_mm')}, aus d_mm {dmin:.3f}")
    # ARTEFAKTE: Zweigwechsel zwischen aufeinanderfolgenden erreichbaren Samples innerhalb eines Strangs
    n_bw = branch_changes(P.kind, P.branch, P.reach)
    F.metrics["branch_changes_in_strands"] = n_bw
    if s.get("zweig_wechsel_in_ringen") != n_bw:
        F.err(f"{P.pid}: trajectory.summary.zweig_wechsel_in_ringen = {s.get('zweig_wechsel_in_ringen')}, "
              f"gezaehlt {n_bw} (Wechsel innerhalb eines Strangs)")
