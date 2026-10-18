"""Bewertung eines DRL-Programms gegen die geplante Trajektorie (G5, SPEC §5.6/§11)."""

from __future__ import annotations

import json
import traceback
from pathlib import Path

import numpy as np

from verify.fake_drcf.controller import DrlError, InjectedFault, State, make_namespace
from verify.oracle.robot_oracle import HOME_RAD, ROBOT_JSON, default_robot, load_json, rot_angle, zyz_to_R

POSJ_TOL_DEG = 1e-3
POSX_POS_TOL = 0.1  # mm
POSX_ROT_TOL_DEG = 0.05
MOVEL_PATH_TOL = 0.5  # mm, Druck-/Fahrsamples zwischen zwei movel-Zielen liegen auf der Geraden
MOVEJ_PATH_TOL = 1e-4  # rad, Samples zwischen zwei movej-Zielen liegen auf der Gelenkgeraden


def _limits_deg() -> tuple[np.ndarray, np.ndarray]:
    kin = load_json(ROBOT_JSON)["kinematics"]
    return (np.rad2deg(kin["joint_velocity_limits_rad_s"]),
            np.rad2deg(kin["joint_acceleration_limits_rad_s2"]))


def execute(text: str, dialect: str, fault_at_motion: int | None = None) -> tuple[State, str | None]:
    """Fuehrt DRL-Text aus. Rueckgabe (Zustand, Fehlertext oder None)."""
    v, a = _limits_deg()
    st = State(dialect=dialect, joint_v_max=v, joint_a_max=a, fault_at_motion=fault_at_motion)
    ns = make_namespace(st)
    try:
        code = compile(text, "<drl>", "exec")
        exec(code, ns)  # noqa: S102 - eingeschraenkter Namensraum, das ist der Zweck des Fake-Controllers
    except InjectedFault:
        return st, None
    except DrlError as exc:
        return st, f"DRL-Fehler: {exc}"
    except Exception as exc:  # noqa: BLE001 - jeder Python-Fehler ist ein Programmabbruch
        tb = traceback.extract_tb(exc.__traceback__)
        line = next((f.lineno for f in reversed(tb) if f.filename == "<drl>"), "?")
        return st, f"Programmabbruch in Zeile {line}: {type(exc).__name__}: {exc}"
    return st, None


class Trajectory:
    def __init__(self, path: Path):
        tr = json.loads(Path(path).read_text(encoding="utf-8"))
        self.q = np.array(tr["q"], dtype=float)
        self.kind = list(tr["kind"])
        self.ring = np.array(tr["ring"], dtype=int)
        self.reach = np.array([s != "unreachable" for s in tr["status"]])
        self.N = len(self.q)
        r = default_robot()
        self.T_BT = np.array([r.fk_tcp(q) for q in self.q])
        self.qdeg = np.rad2deg(self.q)


def _match(m, traj: Trajectory, start: int) -> int | None:
    """Erstes Sample >= start, dem das Bewegungsziel entspricht (posj: q, posx: FK(q))."""
    tgt = np.asarray(m.target, dtype=float)
    lo = start
    while lo < traj.N:
        hi = min(traj.N, lo + 4000)
        if m.is_joint:
            ok = np.abs(traj.qdeg[lo:hi] - tgt).max(axis=1) <= POSJ_TOL_DEG
        else:
            ok = np.linalg.norm(traj.T_BT[lo:hi, :3, 3] - tgt[:3], axis=1) <= POSX_POS_TOL
        ok &= traj.reach[lo:hi]
        for j in np.flatnonzero(ok):
            i = lo + int(j)
            if m.is_joint:
                return i
            R = zyz_to_R(*tgt[3:6])
            if np.rad2deg(rot_angle(R, traj.T_BT[i, :3, :3])) <= POSX_ROT_TOL_DEG:
                return i
        lo = hi
    return None


def _seg_dev(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def check_program(path: Path, dialect: str, traj: Trajectory, tcp_name: str = "FGC_30GUT") -> list[str]:
    tag = f"{path.parent.name}/{path.name}"
    text = path.read_text(encoding="utf-8")
    st, err = execute(text, dialect)
    errs: list[str] = []
    if err:
        return [f"{tag}: {err}"]
    if st.tcp != tcp_name:
        errs.append(f"{tag}: set_tcp({st.tcp!r}), erwartet {tcp_name!r}")
    if 1 not in st.ao_mode or st.ao_mode[1] != "DR_ANALOG_VOLTAGE":
        errs.append(f"{tag}: set_mode_analog_output(ch=1, mod=DR_ANALOG_VOLTAGE) fehlt")
    M = st.motions
    if not M:
        return errs + [f"{tag}: keine Bewegung"]
    first = M[0]
    if not first.is_joint or np.abs(np.asarray(first.target) - np.rad2deg(HOME_RAD)).max() > POSJ_TOL_DEG:
        errs.append(f"{tag}: erste Bewegung ist nicht movej(posj(home)) (Zeile {first.line})")
    # Zuordnung zu Samples (monotone Teilfolge)
    idx: list[int | None] = [None] * len(M)
    ptr = 0
    if first.is_joint:
        i0 = _match(first, traj, 0)
        idx[0] = i0
        ptr = i0 if i0 is not None else 0
    for k in range(1, len(M)):
        i = _match(M[k], traj, ptr)
        if i is None:
            what = "posj" if M[k].is_joint else "posx"
            errs.append(f"{tag}: {M[k].cmd}-Ziel {what} {np.round(M[k].target, 4).tolist()} "
                        f"(Zeile {M[k].line}) entspricht keinem geplanten Sample ab #{ptr}")
            return errs
        idx[k] = i
        ptr = i
    if idx[-1] != traj.N - 1:
        errs.append(f"{tag}: Programm endet bei Sample #{idx[-1]}, Trajektorie hat {traj.N}")
    # Bahn zwischen den Zielen entspricht der geprueften Interpolation
    pos = traj.T_BT[:, :3, 3]
    for k in range(1, len(M)):
        a, b = idx[k - 1], idx[k]
        if a is None or b - a < 2:
            continue
        mid = np.arange(a + 1, b)
        mid = mid[traj.reach[mid]]
        if not len(mid):
            continue
        if M[k].cmd in ("movesx", "amovesx"):
            continue
        if M[k].is_joint:
            qa, qb = traj.q[a], traj.q[b]
            d = qb - qa
            t = np.clip(((traj.q[mid] - qa) @ d) / max(float(d @ d), 1e-12), 0, 1)
            dev = np.abs(traj.q[mid] - (qa + t[:, None] * d)).max()
            if dev > MOVEJ_PATH_TOL:
                errs.append(f"{tag}: Samples #{a}..#{b} liegen nicht auf der Gelenkgeraden von movej "
                            f"(Zeile {M[k].line}, {dev:.2e} rad)")
        else:
            dev = _seg_dev(pos[mid], pos[a], pos[b]).max()
            if dev > MOVEL_PATH_TOL:
                errs.append(f"{tag}: Samples #{a}..#{b} liegen nicht auf der Geraden von {M[k].cmd} "
                            f"(Zeile {M[k].line}, {dev:.2f} mm)")
    # Blending-Radius <= halbe Nachbarsegmente
    for k, m in enumerate(M):
        if m.radius <= 0:
            continue
        l_prev = np.linalg.norm(pos[idx[k]] - pos[idx[k - 1]]) if k > 0 and idx[k - 1] is not None else 0.0
        l_next = np.linalg.norm(pos[idx[k + 1]] - pos[idx[k]]) if k + 1 < len(M) else 0.0
        if m.radius > 0.5 * min(l_prev, l_next) + 1e-6:
            errs.append(f"{tag}: radius {m.radius} > halbe Segmentlaenge ({l_prev:.2f}/{l_next:.2f} mm), "
                        f"Zeile {m.line}")
    # Pumpe: nur in Druckringen an, beim Einschalten steht der Roboter am Ringstart
    pump_on = np.array([m.pump_on for m in M])
    on = False
    for ev in st.events:
        if ev[0] != "ao":
            continue
        n = ev[3]
        now = ev[2] > 0
        if now and not on:
            if n == 0 or idx[n - 1] is None:
                errs.append(f"{tag}: Pumpe an ohne vorherige Bewegung")
            else:
                i = idx[n - 1]
                nxt = traj.kind[i + 1] if i + 1 < traj.N else None
                if not (traj.kind[i] == "approach" and nxt == "print"):
                    errs.append(f"{tag}: Pumpe an bei Sample #{i} ({traj.kind[i]}), nicht am Ringstart")
                if M[n - 1].radius > 0 or not M[n - 1].sync:
                    errs.append(f"{tag}: vor 'Pumpe an' steht der Roboter nicht (radius/asynchron, "
                                f"Zeile {M[n - 1].line})")
        on = now
    for k in range(1, len(M)):
        a, b = idx[k - 1], idx[k]
        if a is None or b is None:
            continue
        kinds = {traj.kind[i] for i in range(a + 1, b + 1)}
        if pump_on[k] and kinds - {"print"}:
            errs.append(f"{tag}: Pumpe an waehrend {sorted(kinds - {'print'})} (Zeile {M[k].line})")
        if not pump_on[k] and "print" in kinds:
            errs.append(f"{tag}: Druckbewegung ohne Pumpe (Zeile {M[k].line})")
    final = [ev for ev in st.events if ev[0] == "ao" and ev[3] == len(M)]
    for ch in st.ao_mode:
        if st.ao.get(ch, 0.0) != 0.0 or not any(ev[1] == ch and ev[2] == 0.0 for ev in final):
            errs.append(f"{tag}: Programmende setzt AO {ch} nicht auf 0")
    # Fehlerfall: Fehler waehrend der ersten Druckbewegung ausloesen
    k_fault = int(np.argmax(pump_on)) if pump_on.any() else min(1, len(M) - 1)
    st2, err2 = execute(text, dialect, fault_at_motion=k_fault)
    if err2:
        errs.append(f"{tag}: Fehlerfall: {err2}")
    elif any(v != 0.0 for v in st2.ao.values()):
        errs.append(f"{tag}: Fehlerfall (Abbruch bei Bewegung {k_fault}) laesst AO an: {st2.ao}")
    return [e for e in errs[:30]]


def check_rundir(run_dir: Path) -> tuple[list[str], dict]:
    errs: list[str] = []
    stats: dict = {}
    run_dir = Path(run_dir)
    parts = sorted(p for p in (run_dir / "parts").glob("*") if p.is_dir())
    if not parts:
        return [f"{run_dir}: keine Teile"], stats
    tcp_name = "FGC_30GUT"
    if (run_dir / "summary.json").is_file():
        tcp_name = load_json(run_dir / "summary.json").get("params", {}).get("tcp_name", tcp_name)
    for pdir in parts:
        tj = pdir / "trajectory.json"
        if not tj.is_file():
            errs.append(f"{pdir.name}: trajectory.json fehlt")
            continue
        traj = Trajectory(tj)
        for dialect in ("v2", "v3"):
            prog = pdir / f"program.{dialect}.drl"
            if not prog.is_file():
                errs.append(f"{pdir.name}: program.{dialect}.drl fehlt")
                continue
            e = check_program(prog, dialect, traj, tcp_name)
            stats[f"{pdir.name}/{prog.name}"] = "ok" if not e else f"{len(e)} Fehler"
            errs += e
    return errs, stats
