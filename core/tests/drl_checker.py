"""Strenger DRL-Pruefer nach SPEC §11 G5 (Ersatz, solange `verify/fake_drcf` fehlt).

Unabhaengig von `roboprint`: liest nur die Artefakte (JSON) und die URDF, rechnet die FK mit
Pinocchio und die ZYZ-Umrechnung selbst (vorwaerts: R = Rz(a) Ry(b) Rz(c)). Das Programm laeuft
in CPython mit Stubs und ohne Builtins; jeder unbekannte Befehl oder Parameter ist ein Fehler.

Geprueft:
- nur Befehle/Signaturen aus docs/doosan-drl.md; `movesx` und `DR_MVS_VEL_CONST` nur in v3,
  `movej` nur mit `posj` (kein `movej(posx)` in v2), `movel` nur mit `posx` und `ref=DR_BASE`;
- AO-Kanal in {1, 2}, Modus vor dem ersten Schreiben gesetzt, 0..10 V, am Ende 0 V;
- vel/acc in den Grenzen (Gelenke <= Datenblatt, acc <= 4 x v_max, TCP <= 1000 mm/s);
- `movesx` <= 100 Punkte; Blending-Radius <= 2 mm und <= 1/2 der angrenzenden Segmente; vor jedem
  AO-Wechsel steht die Bewegung (radius 0);
- jedes `posj` ist ein geplantes q (<= 0,001 Grad), jedes `posx` = FK(geplantes q) (<= 0,1 mm,
  <= 0,05 Grad), in der Reihenfolge der Trajektorie; das letzte Ziel ist das letzte Sample;
- Pumpe ist nur an, waehrend Druck-Samples angefahren werden, und alle Druck-Ziele laufen mit
  Pumpe; jeder Toolpath-Wegpunkt wird mit Pumpe an erreicht.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pinocchio as pin

REPO = Path(__file__).resolve().parents[2]
POSJ_TOL_DEG = 1e-3
POSX_TOL_MM = 0.1
POSX_TOL_DEG = 0.05
WAYPOINT_TOL_MM = 0.5
TCP_SPEED_MAX = 1000.0
VEL_DEG = np.array([120.0, 120.0, 180.0, 225.0, 225.0, 225.0])


class DrlError(Exception):
    pass


@dataclass(frozen=True)
class Posx:
    v: tuple[float, ...]


@dataclass(frozen=True)
class Posj:
    v: tuple[float, ...]


@dataclass
class Motion:
    cmd: str
    target: Posx | Posj
    pump: bool
    radius: float
    line: int


@dataclass
class State:
    motions: list[Motion] = field(default_factory=list)
    ao: dict[int, float] = field(default_factory=dict)
    ao_mode: set[int] = field(default_factory=set)
    ao_log: list[tuple[int, float, int]] = field(default_factory=list)  # (ch, val, n_motions davor)
    tcp: str | None = None
    singularity: str | None = None


def zyz(a: float, b: float, c: float) -> np.ndarray:
    def rz(t: float) -> np.ndarray:
        return np.array([[math.cos(t), -math.sin(t), 0], [math.sin(t), math.cos(t), 0], [0, 0, 1.0]])

    ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1.0, 0], [-math.sin(b), 0, math.cos(b)]])
    return rz(a) @ ry @ rz(c)


def _rot_deg(Ra: np.ndarray, Rb: np.ndarray) -> float:  # noqa: N803
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(Ra.T @ Rb) - 1.0) / 2.0))))


def _env(dialect: str, st: State, fail_at: int | None) -> dict:
    def num(*vals: object) -> tuple[float, ...]:
        out = []
        for v in vals:
            if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
                raise DrlError(f"keine Zahl: {v!r}")
            out.append(float(v))
        return tuple(out)

    def posx(x, y, z, a, b, c):
        return Posx(num(x, y, z, a, b, c))

    def posj(j1, j2, j3, j4, j5, j6):
        return Posj(num(j1, j2, j3, j4, j5, j6))

    def vel_x(vel, acc):
        for val, lim in ((vel, TCP_SPEED_MAX), (acc, 4 * TCP_SPEED_MAX)):
            if val is None:
                continue
            vv = num(*(val if isinstance(val, list) else [val]))
            if len(vv) not in (1, 2) or vv[0] <= 0 or vv[0] > lim or (len(vv) == 2 and vv[1] <= 0):
                raise DrlError(f"vel/acc ungueltig: {val}")

    def motion(cmd, target, radius):
        if fail_at is not None and len(st.motions) == fail_at:
            raise RuntimeError("simulierter Steuerungsfehler")
        r = 0.0 if radius is None else num(radius)[0]
        if r < 0:
            raise DrlError("radius < 0")
        st.motions.append(
            Motion(cmd, target, st.ao.get(1, 0.0) > 0 or st.ao.get(2, 0.0) > 0, r, len(st.motions))
        )

    def movej(pos, vel=None, acc=None, time=None, radius=None, mod=None, ra=None):
        if not isinstance(pos, Posj):
            raise DrlError("movej nur mit posj (kein movej(posx))")
        if vel is not None or acc is not None or time is not None:
            raise DrlError("movej: vel/acc nur global erwartet")
        motion("movej", pos, radius)

    def movel(pos, vel=None, acc=None, time=None, radius=None, ref=None, mod=None, ra=None):
        if not isinstance(pos, Posx):
            raise DrlError("movel nur mit posx")
        if ref != "DR_BASE":
            raise DrlError("movel ohne ref=DR_BASE")
        if ra not in (None, "DR_MV_RA_DUPLICATE"):
            raise DrlError(f"ra {ra}")
        if time is not None or mod is not None:
            raise DrlError("time/mod nicht erwartet")
        vel_x(vel, acc)
        motion("movel", pos, radius)

    def movesx(pos_list, vel=None, acc=None, time=None, ref=None, mod=None, vel_opt=None):
        if not isinstance(pos_list, list) or not 1 <= len(pos_list) <= 100:
            raise DrlError("movesx: 1..100 Punkte")
        if ref != "DR_BASE" or vel_opt != "DR_MVS_VEL_CONST":
            raise DrlError("movesx: ref=DR_BASE und vel_opt=DR_MVS_VEL_CONST erwartet")
        vel_x(vel, acc)
        for k, p in enumerate(pos_list):
            if not isinstance(p, Posx):
                raise DrlError("movesx nur mit posx")
            motion("movesx", p, None)
            st.motions[-1].radius = 0.0 if k == len(pos_list) - 1 else -1.0  # -1: Spline-Stuetzpunkt

    def set_velx(v, w=None):
        vel_x([v] if w is None else [v, w], None)

    def set_accx(a, aw=None):
        vel_x(None, [a] if aw is None else [a, aw])

    def set_velj(v):
        vv = np.array(num(*v))
        if vv.shape != (6,) or np.any(vv <= 0) or np.any(vv > VEL_DEG):
            raise DrlError(f"set_velj ausserhalb der Grenzen: {v}")

    def set_accj(a):
        aa = np.array(num(*a))
        if aa.shape != (6,) or np.any(aa <= 0) or np.any(aa > 4 * VEL_DEG):
            raise DrlError(f"set_accj ausserhalb der Grenzen: {a}")

    def set_tcp(name):
        st.tcp = name

    def set_singularity_handling(mode):
        st.singularity = mode

    def set_mode_analog_output(ch, mod):
        if ch not in (1, 2) or mod != "DR_ANALOG_VOLTAGE":
            raise DrlError(f"set_mode_analog_output(ch={ch}, mod={mod})")
        st.ao_mode.add(ch)

    def set_analog_output(ch, val):
        if ch not in (1, 2):
            raise DrlError(f"AO-Kanal {ch}")
        if ch not in st.ao_mode:
            raise DrlError("AO-Modus nicht gesetzt")
        (v,) = num(val)
        if not 0.0 <= v <= 10.0:
            raise DrlError(f"AO {v} V")
        st.ao[ch] = v
        st.ao_log.append((ch, v, len(st.motions)))

    def wait(t):
        if num(t)[0] < 0:
            raise DrlError("wait < 0")

    env = {
        k: v for k, v in locals().items() if k not in ("num", "vel_x", "motion", "dialect", "st", "fail_at")
    }
    env.update(DR_BASE="DR_BASE", DR_VAR_VEL="DR_VAR_VEL", DR_ANALOG_VOLTAGE="DR_ANALOG_VOLTAGE",
               DR_MV_RA_DUPLICATE="DR_MV_RA_DUPLICATE")  # fmt: skip
    if dialect == "v3":
        env["DR_MVS_VEL_CONST"] = "DR_MVS_VEL_CONST"
    else:
        del env["movesx"]
    return env


def run_program(text: str, dialect: str, fail_at: int | None = None) -> State:
    """Fuehrt das Programm aus; DrlError/NameError/TypeError bei unzulaessigem Inhalt."""
    if dialect not in ("v2", "v3"):
        raise DrlError(dialect)
    text.encode("ascii")
    st = State()
    env = _env(dialect, st, fail_at)
    env["__builtins__"] = {}
    try:
        exec(compile(text, f"program.{dialect}.drl", "exec"), env)  # noqa: S102
    except RuntimeError:
        if fail_at is None:
            raise
    return st


class _Plan:
    def __init__(self, part_dir: Path) -> None:
        run = part_dir.parent.parent
        self.traj = json.loads((part_dir / "trajectory.json").read_text())
        self.tp = json.loads((part_dir / "toolpath.json").read_text())
        scene = json.loads((run / "scene.json").read_text())
        T_FT = np.array(scene["tool"]["T_FT"])  # noqa: N806
        self.T_BW = np.linalg.inv(np.array(scene["workstation"]["T_WB"]))
        model = pin.buildModelFromUrdf(str(REPO / scene["robot"]["urdf"]))
        data = model.createData()
        fid = model.getFrameId("link_6")
        self.Q = np.array(self.traj["q"])
        self.T = np.empty((len(self.Q), 4, 4))
        for i, q in enumerate(self.Q):
            pin.framesForwardKinematics(model, data, q)
            M = data.oMf[fid]  # noqa: N806
            T = np.eye(4)  # noqa: N806
            T[:3, :3], T[:3, 3] = M.rotation, M.translation * 1000.0
            self.T[i] = T @ T_FT
        self.valid = np.array([s != "unreachable" for s in self.traj["status"]])

    def match(self, m: Motion, start: int) -> int:
        """Erstes gueltiges Sample >= start, das dem Ziel entspricht, sonst -1."""
        if isinstance(m.target, Posj):
            err = np.max(np.abs(np.degrees(self.Q[start:]) - np.array(m.target.v)), axis=1)
            ok = err <= POSJ_TOL_DEG
        else:
            x, y, z, a, b, c = m.target.v
            R = zyz(*np.radians([a, b, c]))  # noqa: N806
            dp = np.linalg.norm(self.T[start:, :3, 3] - np.array([x, y, z]), axis=1)
            cosang = (np.einsum("nij,ij->n", self.T[start:, :3, :3], R) - 1.0) / 2.0
            ok = (dp <= POSX_TOL_MM) & (np.degrees(np.arccos(np.clip(cosang, -1, 1))) <= POSX_TOL_DEG)
        ok &= self.valid[start:]
        hit = np.flatnonzero(ok)
        return int(start + hit[0]) if hit.size else -1


def check(text: str, dialect: str, part_dir: Path) -> list[str]:
    """Liste der Verstoesse (leer = bestanden)."""
    try:
        st = run_program(text, dialect)
    except (DrlError, NameError, TypeError, SyntaxError, UnicodeEncodeError) as e:
        return [f"Ausfuehrung: {type(e).__name__}: {e}"]
    errs: list[str] = []
    if st.tcp != "FGC_30GUT":
        errs.append(f"set_tcp fehlt/falsch: {st.tcp}")
    if st.singularity != "DR_VAR_VEL":
        errs.append("set_singularity_handling(DR_VAR_VEL) fehlt")
    if not st.ao_log or any(v != 0.0 for v in st.ao.values()):
        errs.append("AO am Programmende nicht 0")
    plan = _Plan(part_dir)
    kinds = plan.traj["kind"]
    idx, start = [], 0
    for m in st.motions:
        i = plan.match(m, start)
        if i < 0:
            errs.append(
                f"Bewegung {m.line} ({m.cmd} {m.target}) entspricht keinem geplanten Sample ab {start}"
            )
            return errs
        idx.append(i)
        start = i
    if idx and idx[-1] != len(plan.Q) - 1:
        errs.append(f"letztes Ziel ist Sample {idx[-1]}, nicht das Trajektorienende {len(plan.Q) - 1}")
    for m, i in zip(st.motions, idx, strict=True):
        if m.pump != (kinds[i] == "print"):
            errs.append(f"Bewegung {m.line} zu Sample {i} ({kinds[i]}) mit Pumpe {'an' if m.pump else 'aus'}")
    # Blending: Radius <= 2 mm und <= 1/2 der angrenzenden Segmente; vor AO-Wechsel Halt
    pos = [plan.T[i, :3, 3] for i in idx]
    ao_before = {n for _, _, n in st.ao_log}
    for k, m in enumerate(st.motions):
        if m.radius < 0:
            continue
        if (k + 1) in ao_before and m.radius != 0.0:
            errs.append(f"Bewegung {k} vor AO-Wechsel mit radius {m.radius}")
        if m.radius > 0:
            seg_in = np.linalg.norm(pos[k] - pos[k - 1]) if k else 0.0
            seg_out = np.linalg.norm(pos[k + 1] - pos[k]) if k + 1 < len(pos) else 0.0
            if m.cmd != "movel" or m.radius > 2.0 + 1e-9 or m.radius > 0.5 * min(seg_in, seg_out) + 1e-3:
                errs.append(
                    f"Bewegung {k}: radius {m.radius} > min(2, 1/2 Segment {seg_in:.3f}/{seg_out:.3f})"
                )
    # Abdeckung: jeder Wegpunkt mit Pumpe an erreicht
    pumped = np.array([p for p, m in zip(pos, st.motions, strict=True) if m.pump]).reshape(-1, 3)
    T_WB = np.linalg.inv(plan.T_BW)  # noqa: N806
    pumped_W = pumped @ T_WB[:3, :3].T + T_WB[:3, 3]  # noqa: N806
    starts = [i for i in range(1, len(st.motions)) if st.motions[i].pump and not st.motions[i - 1].pump]
    start_W = np.array([pos[i - 1] for i in starts]).reshape(-1, 3) @ T_WB[:3, :3].T + T_WB[:3, 3]  # noqa: N806
    for r, ring in enumerate(plan.tp["rings"]):
        for w, wp in enumerate(ring["waypoints"]):
            p = np.array(wp[:3])
            cands = pumped_W if w else np.vstack([pumped_W, start_W])
            if not len(cands) or np.min(np.linalg.norm(cands - p, axis=1)) > WAYPOINT_TOL_MM:
                errs.append(f"Ring {r}, Wegpunkt {w} nicht mit Pumpe erreicht")
                break
    return errs
