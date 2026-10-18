"""Fake-Controller: DRL-Stubs nach docs/doosan-drl.md, ausgefuehrt in CPython (G5).

Erlaubt sind genau die dort belegten Befehle (je Dialekt), harmlose Builtins und die DR_-Konstanten.
Alles andere fuehrt zu einem Fehler. Der Controller zeichnet Bewegungsziele, Analogausgaenge und
Einstellungen auf; die Bewertung gegen die Trajektorie macht `verify.fake_drcf.check`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


class DrlError(Exception):
    """Verstoss gegen Dialekt, Signatur oder Wertebereich: bricht das Programm ab."""


class InjectedFault(Exception):  # noqa: N818 - Name ist Teil der Selbstbeschreibung
    """Vom Fake-Controller ausgeloester Fehler (Pruefung der Fehlerbehandlung)."""


SAFE_BUILTINS = ("range", "len", "float", "int", "abs", "min", "max", "list", "tuple", "enumerate", "zip",
                 "print", "round", "sum", "str", "bool", "dict", "isinstance", "Exception", "ValueError",
                 "RuntimeError")

CONSTS_COMMON = {
    "DR_BASE": "DR_BASE", "DR_TOOL": "DR_TOOL", "DR_WORLD": "DR_WORLD",
    "DR_MV_MOD_ABS": "DR_MV_MOD_ABS", "DR_MV_MOD_REL": "DR_MV_MOD_REL",
    "DR_MV_RA_DUPLICATE": "DR_MV_RA_DUPLICATE", "DR_MV_RA_OVERRIDE": "DR_MV_RA_OVERRIDE",
    "DR_MVS_VEL_CONST": "DR_MVS_VEL_CONST", "DR_MVS_VEL_NONE": "DR_MVS_VEL_NONE",
    "DR_VAR_VEL": "DR_VAR_VEL", "DR_AVOID": "DR_AVOID", "DR_TASK_STOP": "DR_TASK_STOP",
    "DR_ANALOG_VOLTAGE": "DR_ANALOG_VOLTAGE", "DR_ANALOG_CURRENT": "DR_ANALOG_CURRENT",
}
CONSTS_V3 = {"DR_QUAT": "DR_QUAT", "DR_HERMITE": "DR_HERMITE"}

CART_V_MAX = 1000.0  # mm/s, M1013-Datenblatt (TCP-Geschwindigkeit)


class PosJ(list):
    pass


class PosX(list):
    pass


@dataclass
class Motion:
    cmd: str  # movej | movel | movesx-Punkt
    target: list  # Grad / mm+Grad
    is_joint: bool
    radius: float
    sync: bool
    line: int
    pump_on: bool
    vel: object = None


@dataclass
class State:
    dialect: str
    joint_v_max: np.ndarray  # deg/s
    joint_a_max: np.ndarray  # deg/s^2
    motions: list = field(default_factory=list)
    calls: list = field(default_factory=list)  # (name, args, kwargs)
    ao_mode: dict = field(default_factory=dict)
    ao: dict = field(default_factory=lambda: {1: 0.0, 2: 0.0})
    tcp: str | None = None
    singularity: object = None
    velx: object = None
    accx: object = None
    velj: object = None
    accj: object = None
    events: list = field(default_factory=list)  # ("ao", ch, val, n_motions) / ("wait", t, n_motions)
    fault_at_motion: int | None = None


def _line() -> int:
    import sys

    f = sys._getframe(2)
    while f is not None and f.f_code.co_filename != "<drl>":
        f = f.f_back
    return f.f_lineno if f is not None else -1


def _num(x, what: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError) as exc:
        raise DrlError(f"{what}: keine Zahl ({x!r})") from exc
    if not np.isfinite(v):
        raise DrlError(f"{what}: nicht endlich ({x!r})")
    return v


def _vals(args, n: int, what: str) -> list[float]:
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        args = tuple(args[0])
    if len(args) != n:
        raise DrlError(f"{what}: {n} Werte erwartet, {len(args)} erhalten")
    return [_num(a, what) for a in args]


def make_namespace(st: State) -> dict:
    """DRL-Namensraum fuer einen Dialekt."""
    v3 = st.dialect == "v3"

    def need_prolog(name: str) -> None:
        if st.tcp is None:
            raise DrlError(f"{name} vor set_tcp (Prolog SPEC §5.6)")
        if st.singularity != "DR_VAR_VEL":
            raise DrlError(f"{name} vor set_singularity_handling(DR_VAR_VEL)")
        for k in ("velx", "accx", "velj", "accj"):
            if getattr(st, k) is None:
                raise DrlError(f"{name} vor set_{k} (Prolog SPEC §5.6)")

    def check_joint_v(v, what: str) -> None:
        vs = np.atleast_1d(np.array(v if isinstance(v, (list, tuple)) else [v], dtype=float))
        if vs.size not in (1, 6) or np.any(vs <= 0):
            raise DrlError(f"{what}: ungueltige Gelenkgeschwindigkeit {v!r}")
        lim = st.joint_v_max if vs.size == 6 else st.joint_v_max.min()
        if np.any(vs > lim + 1e-9):
            raise DrlError(f"{what}: Gelenkgeschwindigkeit {v!r} deg/s > Grenze {np.round(lim, 1).tolist()}")

    def check_joint_a(a, what: str) -> None:
        as_ = np.atleast_1d(np.array(a if isinstance(a, (list, tuple)) else [a], dtype=float))
        if as_.size not in (1, 6) or np.any(as_ <= 0):
            raise DrlError(f"{what}: ungueltige Gelenkbeschleunigung {a!r}")
        lim = st.joint_a_max if as_.size == 6 else st.joint_a_max.min()
        if np.any(as_ > lim + 1e-9):
            raise DrlError(f"{what}: Gelenkbeschleunigung {a!r} deg/s2 > Grenze {np.round(lim, 1).tolist()}")

    def check_cart(v, what: str) -> None:
        vs = list(v) if isinstance(v, (list, tuple)) else [v]
        if len(vs) not in (1, 2):
            raise DrlError(f"{what}: [linear, rotatorisch] oder Skalar erwartet, {v!r}")
        vals = [_num(x, what) for x in vs]
        if any(x <= 0 for x in vals):
            raise DrlError(f"{what}: muss > 0 sein ({v!r})")
        if what.startswith("vel") and vals[0] > CART_V_MAX:
            raise DrlError(f"{what}: {vals[0]} mm/s > {CART_V_MAX} mm/s")

    def posj(*args):
        return PosJ(_vals(args, 6, "posj"))

    def posx(*args, ori_type=None):
        if ori_type is not None:
            if not v3:
                raise DrlError("posx(..., ori_type=...) gibt es erst ab V3 (Dialekt v2)")
            raise DrlError("posx mit ori_type: SPEC §5.6 verlangt Euler ZYZ")
        return PosX(_vals(args, 6, "posx"))

    def _motion(cmd, pos, is_joint, radius, sync, vel):
        if st.fault_at_motion is not None and len(st.motions) >= st.fault_at_motion:
            st.fault_at_motion = None
            raise InjectedFault("vom Fake-Controller ausgeloest")
        r = 0.0 if radius is None else _num(radius, f"{cmd} radius")
        if r < 0:
            raise DrlError(f"{cmd}: radius < 0")
        st.motions.append(Motion(cmd, list(pos), is_joint, r, sync, _line(), st.ao.get(1, 0.0) > 0
                                 or st.ao.get(2, 0.0) > 0, vel))

    def _common(name, vel, acc, time, mod, ra, ref, extra):
        if extra:
            raise DrlError(f"{name}: unbekannte Parameter {sorted(extra)}")
        if mod not in (None, "DR_MV_MOD_ABS"):
            raise DrlError(f"{name}: nur absolute Bewegungen (mod=DR_MV_MOD_ABS)")
        if ra not in (None, "DR_MV_RA_DUPLICATE", "DR_MV_RA_OVERRIDE"):
            raise DrlError(f"{name}: ungueltiges ra {ra!r}")
        if ref not in (None, "DR_BASE"):
            raise DrlError(f"{name}: Posen muessen in DR_BASE stehen (ref={ref!r})")
        if time is not None and _num(time, f"{name} time") <= 0:
            raise DrlError(f"{name}: time <= 0")

    def _movej(name, sync, pos, vel=None, acc=None, time=None, radius=None, mod=None, ra=None,
               v=None, a=None, t=None, r=None, **extra):
        need_prolog(name)
        vel, acc, time, radius = (vel if vel is not None else v, acc if acc is not None else a,
                                  time if time is not None else t, radius if radius is not None else r)
        if isinstance(pos, PosX):
            raise DrlError(f"{name}(posx): ohne sol waehlt der Controller den Zweig (SPEC §5.6, nur posj)")
        if not isinstance(pos, PosJ):
            pos = PosJ(_vals((pos,), 6, f"{name} Ziel"))
        _common(name, vel, acc, time, mod, ra, None, extra)
        if vel is not None:
            check_joint_v(vel, f"{name} vel")
        if acc is not None:
            check_joint_a(acc, f"{name} acc")
        _motion(name, pos, True, radius, sync, vel)

    def _movel(name, sync, pos, vel=None, acc=None, time=None, radius=None, ref=None, mod=None, ra=None,
               v=None, a=None, t=None, r=None, app_type=None, **extra):
        need_prolog(name)
        vel, acc, time, radius = (vel if vel is not None else v, acc if acc is not None else a,
                                  time if time is not None else t, radius if radius is not None else r)
        if not isinstance(pos, PosX):
            raise DrlError(f"{name}: Ziel muss posx sein")
        if app_type is not None:
            raise DrlError(f"{name}: app_type nicht belegt")
        _common(name, vel, acc, time, mod, ra, ref, extra)
        if vel is not None:
            check_cart(vel, f"vel {name}")
        if acc is not None:
            check_cart(acc, f"acc {name}")
        _motion(name, pos, False, radius, sync, vel)

    def movej(pos, *a, **k):
        if a:
            raise DrlError("movej: nur das Ziel positional")
        _movej("movej", True, pos, **k)

    def amovej(pos, *a, **k):
        if a:
            raise DrlError("amovej: nur das Ziel positional")
        _movej("amovej", False, pos, **k)

    def movel(pos, *a, **k):
        if a:
            raise DrlError("movel: nur das Ziel positional")
        _movel("movel", True, pos, **k)

    def amovel(pos, *a, **k):
        if a:
            raise DrlError("amovel: nur das Ziel positional")
        _movel("amovel", False, pos, **k)

    def _movesx(name, sync, pos_list, vel=None, acc=None, time=None, ref=None, mod=None, vel_opt=None,
                v=None, a=None, t=None, spline_type=None, **extra):
        if not v3:
            raise DrlError(f"{name}: im Dialekt v2 nicht erlaubt (SPEC §5.6: movesx nur im Dialekt v3)")
        need_prolog(name)
        if spline_type not in (None, "DR_HERMITE"):
            raise DrlError(f"{name}: spline_type {spline_type!r}")
        vel, acc, time = (vel if vel is not None else v, acc if acc is not None else a,
                          time if time is not None else t)
        _common(name, vel, acc, time, mod, None, ref, extra)
        if vel_opt != "DR_MVS_VEL_CONST":
            raise DrlError(f"{name}: vel_opt=DR_MVS_VEL_CONST verlangt (SPEC §5.6)")
        pts = list(pos_list)
        if not 1 <= len(pts) <= 100:
            raise DrlError(f"{name}: {len(pts)} Punkte (1..100 erlaubt)")
        if vel is not None:
            check_cart(vel, f"vel {name}")
        for p in pts:
            if not isinstance(p, PosX):
                raise DrlError(f"{name}: alle Punkte muessen posx sein")
            _motion(name, p, False, 0.0, sync, vel)

    def movesx(pos_list, *a, **k):
        if a:
            raise DrlError("movesx: nur die Punktliste positional")
        _movesx("movesx", True, pos_list, **k)

    def amovesx(pos_list, *a, **k):
        if a:
            raise DrlError("amovesx: nur die Punktliste positional")
        _movesx("amovesx", False, pos_list, **k)

    def not_allowed(name: str, why: str):
        def f(*_a, **_k):
            raise DrlError(f"{name}: {why}")

        return f

    def set_velx(v1, v2=None, **extra):
        if extra:
            raise DrlError(f"set_velx: unbekannte Parameter {sorted(extra)}")
        check_cart([v1] if v2 is None else [v1, v2], "vel set_velx")
        st.velx = (v1, v2)

    def set_accx(a1, a2=None, **extra):
        if extra:
            raise DrlError(f"set_accx: unbekannte Parameter {sorted(extra)}")
        check_cart([a1] if a2 is None else [a1, a2], "acc set_accx")
        st.accx = (a1, a2)

    def set_velj(vj, **extra):
        if extra:
            raise DrlError(f"set_velj: unbekannte Parameter {sorted(extra)}")
        check_joint_v(vj, "set_velj")
        st.velj = vj

    def set_accj(aj, **extra):
        if extra:
            raise DrlError(f"set_accj: unbekannte Parameter {sorted(extra)}")
        check_joint_a(aj, "set_accj")
        st.accj = aj

    def set_tcp(name, **extra):
        if extra or not isinstance(name, str) or not name:
            raise DrlError(f"set_tcp: Name als Zeichenkette erwartet ({name!r})")
        st.tcp = name

    def set_singularity_handling(mode=None, **extra):
        if extra or mode not in ("DR_VAR_VEL", "DR_AVOID", "DR_TASK_STOP"):
            raise DrlError(f"set_singularity_handling: ungueltiger Modus {mode!r}")
        st.singularity = mode

    def _ch(ch) -> int:
        if isinstance(ch, bool) or not isinstance(ch, int) or ch not in (1, 2):
            raise DrlError(f"Analogausgang: Kanal {ch!r} (nur 1 und 2)")
        return ch

    def set_mode_analog_output(ch=None, mod=None, **extra):
        if extra:
            raise DrlError(f"set_mode_analog_output: unbekannte Parameter {sorted(extra)}")
        c = _ch(ch)
        if mod not in ("DR_ANALOG_VOLTAGE", "DR_ANALOG_CURRENT"):
            raise DrlError(f"set_mode_analog_output: mod {mod!r}")
        st.ao_mode[c] = mod

    def set_analog_output(ch=None, val=None, **extra):
        if extra:
            raise DrlError(f"set_analog_output: unbekannte Parameter {sorted(extra)}")
        c = _ch(ch)
        if c not in st.ao_mode:
            raise DrlError(f"set_analog_output(ch={c}) vor set_mode_analog_output")
        v = _num(val, "set_analog_output val")
        lo, hi = (0.0, 10.0) if st.ao_mode[c] == "DR_ANALOG_VOLTAGE" else (4.0, 20.0)
        if not (lo <= v <= hi or (v == 0.0 and st.ao_mode[c] == "DR_ANALOG_VOLTAGE")):
            raise DrlError(f"set_analog_output: {v} ausserhalb {lo}..{hi}")
        st.ao[c] = v
        st.events.append(("ao", c, v, len(st.motions)))

    def wait(t, **extra):
        if extra or _num(t, "wait") < 0:
            raise DrlError(f"wait: ungueltige Zeit {t!r}")
        st.events.append(("wait", float(t), len(st.motions)))

    def mwait(t=0, **extra):
        if extra:
            raise DrlError("mwait: unbekannte Parameter")
        st.events.append(("mwait", float(t), len(st.motions)))

    def check_motion():
        return 0

    def change_operation_speed(speed, **extra):
        if extra or not 1 <= _num(speed, "change_operation_speed") <= 100:
            raise DrlError("change_operation_speed: 1..100")

    builtins_src = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
    ns = {"__builtins__": {k: builtins_src[k] for k in SAFE_BUILTINS}}
    ns.update(CONSTS_COMMON)
    if v3:
        ns.update(CONSTS_V3)
    else:
        ns["DR_QUAT"] = "DR_QUAT"  # Verwendung wird in posx abgelehnt
        ns["DR_HERMITE"] = "DR_HERMITE"  # movesx/amovesx sind in v2 ohnehin abgelehnt
    ns.update(posj=posj, posx=posx, movej=movej, amovej=amovej, movel=movel, amovel=amovel, movesx=movesx,
              set_velx=set_velx, set_accx=set_accx, set_velj=set_velj, set_accj=set_accj, set_tcp=set_tcp,
              set_singularity_handling=set_singularity_handling,
              set_mode_analog_output=set_mode_analog_output, set_analog_output=set_analog_output, wait=wait,
              mwait=mwait, check_motion=check_motion, change_operation_speed=change_operation_speed)
    ns["amovesx"] = amovesx
    ns["moveb"] = not_allowed("moveb", "Verfuegbarkeit offen (docs/doosan-drl.md), SPEC §5.6 nutzt es nicht")
    ns["movejx"] = not_allowed("movejx", "nicht in docs/doosan-drl.md belegt")
    return ns
