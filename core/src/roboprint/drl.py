"""DRL-Emitter fuer die Dialekte v2 und v3 (Doosan M1013, SPEC §5.6, docs/doosan-drl.md).

Grad gibt es nur hier. Schnittstelle::

    emit(planned_part: PlannedPart, dialect: Literal["v2", "v3"], *, allow_infeasible=False) -> str
    load_planned_part(part_dir) -> PlannedPart       # liest einen Laufordner (SPEC §6)
    write_programs(part_dir) -> [program.v2.drl, program.v3.drl]

`PlannedPart` ist ein schlanker Wrapper um die Vertraege `Trajectory`, `Toolpath`,
`PartArtifact` und `Scene` plus Parameter (`DrlParams`, SPEC §10) und Provenienz.

**Bezug:** Jedes Bewegungsziel ist ein Sample der geplanten Trajektorie (genau der gepruefte
Zweig). Nichts wird per IK neu gerechnet:

- `transfer` -> `movej(posj(q))` mit dem q am Ende jedes gelenklinearen Stuecks (ein
  Zwischenpunkt eines Transfers wird als Knick der Gelenkgeraden erkannt);
- `lift`, `lower`, `approach`, `retract` -> `movel(posx(T_BT))` mit T_BT = FK(q) @ T_FT am
  Ende jedes kartesisch linearen Stuecks;
- `print` -> je Toolpath-Wegpunkt ein `movel` auf das Druck-Sample, das diesem Wegpunkt
  entspricht (monotone Zuordnung entlang des Rings, Toleranz `match_tol_mm`, Position aus
  T_WB @ FK(q) @ T_FT).

Je Ring: Pumpe an (`set_analog_output(ch, V_pump)` + `wait(t_tot)`) direkt vor dem ersten
Druck-`movel`, Druck-`movel` mit `radius = min(r_blend_max, 1/2 der angrenzenden Segmente)` und
`ra=DR_MV_RA_DUPLICATE`, der letzte Druckpunkt mit `radius=0` (Halt, damit die Pumpe am Ringende
schaltet), danach Pumpe aus. Dialekt v3 kann den Druck optional als `movesx`-Bloecke
(<= 100 Punkte, `vel_opt=DR_MVS_VEL_CONST`) ausgeben (`DrlParams.v3_movesx`); Default ist aus,
weil `movesx` zwischen den Bloecken anhaelt und der Spline zwischen den Wegpunkten von den
Geraden abweicht. Der Programmrumpf steht in `try/finally`, das den Analogausgang auf 0 setzt;
zusaetzlich setzt die Abschlusssequenz am Programmende 0 V. Der Text ist reines ASCII.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Literal

import numpy as np

from roboprint import params as speeds
from roboprint.contracts import PartArtifact, Provenance, Scene, Summary, Toolpath, Trajectory, load_json
from roboprint.robot import JOINT_VEL_LIMITS, fk_batch

Dialect = Literal["v2", "v3"]
DIALECTS: tuple[str, ...] = ("v2", "v3")

GIMBAL_EPS = 1e-9  # |sin b| darunter: Gimbal-Fall b = 0 oder b = 180 Grad
MOVESX_MAX_POINTS = 100
AO_CHANNELS = (1, 2)
AO_VOLT_RANGE = (0.0, 10.0)
TCP_SPEED_MAX_MM_S = 1000.0  # Datenblatt M1013: max. TCP-Geschwindigkeit 1 m/s
_JOINT_ACC_FACTOR = speeds.JOINT_ACC_FACTOR  # robots/doosan_m1013.json: ~ 4 x v_max (provisorisch)
_LINEAR_TOL_MM = 0.01  # Abweichung, ab der ein kartesischer Knick ein neues movel ist
_LINEAR_TOL_RAD = 1e-6  # dito fuer gelenklineare Transfers
_SAME_MM = 1e-4
_SAME_RAD = 1e-7

_CARTESIAN_KINDS = ("lift", "lower", "approach", "retract")


# --------------------------------------------------------------------------- ZYZ


def zyz_from_matrix(R: np.ndarray) -> tuple[float, float, float]:  # noqa: N803
    """Rotationsmatrix -> Euler ZYZ (a, b, c) in rad mit R = Rz(a) Ry(b) Rz(c), b in [0, pi].

    Gimbal (|sin b| < GIMBAL_EPS): c = 0 und bei b = 0 a = atan2(r21, r11), bei b = pi
    a = atan2(-r21, -r11) (dort gilt r11 = -cos(a - c), r21 = -sin(a - c)).
    """
    R = np.asarray(R, dtype=float)  # noqa: N806
    sb = math.hypot(R[0, 2], R[1, 2])
    b = math.atan2(sb, R[2, 2])
    if sb >= GIMBAL_EPS:
        a = math.atan2(R[1, 2], R[0, 2])
        c = math.atan2(R[2, 1], -R[2, 0])
    elif R[2, 2] > 0.0:
        b, a, c = 0.0, math.atan2(R[1, 0], R[0, 0]), 0.0
    else:
        b, a, c = math.pi, math.atan2(-R[1, 0], -R[0, 0]), 0.0
    return a, b, c


def matrix_from_zyz(a: float, b: float, c: float) -> np.ndarray:
    """R = Rz(a) Ry(b) Rz(c), Winkel in rad."""
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    rz_a = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    ry_b = np.array([[cb, 0.0, sb], [0.0, 1.0, 0.0], [-sb, 0.0, cb]])
    rz_c = np.array([[cc, -sc, 0.0], [sc, cc, 0.0], [0.0, 0.0, 1.0]])
    return rz_a @ ry_b @ rz_c


def posx_values(T_BT: np.ndarray) -> tuple[float, ...]:  # noqa: N803
    """T_BT (4x4, mm) -> (x, y, z, a, b, c) in mm und Grad (ZYZ)."""
    a, b, c = zyz_from_matrix(T_BT[:3, :3])
    x, y, z = (float(v) for v in T_BT[:3, 3])

    def deg(t: float) -> float:  # -180 und +180 sind gleich; einheitlich +180 ausgeben
        d = math.degrees(t)
        return d + 360.0 if d <= -180.0 + 1e-7 else d

    return x, y, z, deg(a), math.degrees(b), deg(c)


def _f(v: float, nd: int) -> str:
    s = f"{v:.{nd}f}"
    return "0." + "0" * nd if s.lstrip("-").strip("0.") == "" else s  # kein "-0.0000"


def format_posx(T_BT: np.ndarray) -> str:  # noqa: N803
    x, y, z, a, b, c = posx_values(T_BT)
    return "posx(" + ", ".join([_f(x, 4), _f(y, 4), _f(z, 4), _f(a, 6), _f(b, 6), _f(c, 6)]) + ")"


def format_posj(q: np.ndarray) -> str:
    return "posj(" + ", ".join(_f(math.degrees(float(v)), 6) for v in q) + ")"


# --------------------------------------------------------------------------- Parameter


@dataclass(frozen=True)
class DrlParams:
    """Emitter-Parameter (SPEC §10). Felder mit Kommentar "A" sind Annahmen fuer den Programmkopf."""

    v_print_mm_s: float = speeds.V_PRINT_MM_S  # A
    w_print_deg_s: float = 60.0  # A (Orientierung beim Druck)
    a_print_mm_s2: float = speeds.A_PRINT_MM_S2  # A
    aw_print_deg_s2: float = 120.0  # A
    v_travel_mm_s: float = speeds.V_TRAVEL_MM_S  # A
    w_travel_deg_s: float = 90.0  # A
    a_travel_mm_s2: float = speeds.A_TRAVEL_MM_S2  # A
    aw_travel_deg_s2: float = 180.0  # A
    joint_speed_fraction: float = speeds.JOINT_SPEED_FRACTION  # A, Gelenke <= 30 % der Grenzen
    pump_channel: int = 1  # A, AO 1 = pump_a
    v_pump_v: float = 5.0  # A
    t_tot_s: float = 3.0  # A, provisorisch
    r_blend_mm: float = 2.0  # A, r_blend = min(r_blend_mm, 1/2 Segment)
    tcp_name: str = "FGC_30GUT"  # A, muss am Teach Pendant angelegt sein
    match_tol_mm: float = 1.0
    v3_movesx: bool = False
    # nur fuer den Kopfkommentar
    layer_height_mm: float = 10.0  # A
    bead_width_mm: float = 30.0  # A
    z_lift_mm: float = 30.0  # A
    approach_mm: float = 20.0  # A
    d_hard_mm: float = 10.0  # A
    tau_max_deg: float = 0.0  # A

    @classmethod
    def from_params(cls, params: Mapping[str, object] | None) -> DrlParams:
        """Uebernimmt bekannte Schluessel (snake_case wie in summary.params), ignoriert andere."""
        base = cls()
        if not params:
            return base
        updates: dict[str, object] = {}
        for f in fields(cls):
            if f.name in params:
                cur = getattr(base, f.name)
                updates[f.name] = type(cur)(params[f.name])  # type: ignore[call-arg]
        return replace(base, **updates)

    def validate(self) -> None:
        if self.pump_channel not in AO_CHANNELS:
            raise ValueError(f"AO-Kanal {self.pump_channel} ungueltig, erlaubt {AO_CHANNELS}")
        lo, hi = AO_VOLT_RANGE
        if not lo <= self.v_pump_v <= hi:
            raise ValueError(f"V_pump {self.v_pump_v} V ausserhalb {lo}..{hi} V")
        if not 0.0 < self.joint_speed_fraction <= 1.0:
            raise ValueError("joint_speed_fraction muss in (0, 1] liegen")
        for name in ("v_print_mm_s", "v_travel_mm_s"):
            v = getattr(self, name)
            if not 0.0 < v <= TCP_SPEED_MAX_MM_S:
                raise ValueError(f"{name} = {v} ausserhalb (0, {TCP_SPEED_MAX_MM_S}]")
        if self.t_tot_s < 0.0 or self.r_blend_mm < 0.0:
            raise ValueError("t_tot_s und r_blend_mm muessen >= 0 sein")

    def joint_vel_deg_s(self) -> list[float]:
        return [self.joint_speed_fraction * math.degrees(v) for v in JOINT_VEL_LIMITS]

    def joint_acc_deg_s2(self) -> list[float]:
        return [_JOINT_ACC_FACTOR * v for v in self.joint_vel_deg_s()]


@dataclass(frozen=True)
class PlannedPart:
    """Alles, was der Emitter fuer ein Teil braucht (Vertraege aus spec/ARTEFAKTE.md)."""

    trajectory: Trajectory
    toolpath: Toolpath
    part: PartArtifact
    scene: Scene
    params: DrlParams = field(default_factory=DrlParams)
    provenance: Provenance | None = None
    scenario_id: str = "unbekannt"
    run_params: Mapping[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------- Ablaufplan


@dataclass(frozen=True)
class Move:
    cmd: Literal["movej", "movel"]
    sample: int
    kind: str
    ring: int
    radius_mm: float = 0.0


@dataclass(frozen=True)
class Pump:
    on: bool
    ring: int


@dataclass(frozen=True)
class Comment:
    text: str


Step = Move | Pump | Comment


def _linear_breaks(P: np.ndarray, start: np.ndarray, tol: float) -> list[int]:  # noqa: N803
    """Indizes in P, an denen die Bahn start -> P[0] -> ... die Gerade verlaesst (Knick oder
    Umkehr), plus der letzte Index. Jedes Stueck dazwischen ist eine Gerade."""
    out: list[int] = []
    seg0, d, reach = start, None, 0.0
    for k in range(len(P)):
        v = P[k] - seg0
        if d is None:
            n = float(np.linalg.norm(v))
            if n > tol:
                d, reach = v / n, n
            continue
        proj = float(v @ d)
        if np.linalg.norm(v - proj * d) > tol or proj < reach - tol:
            out.append(k - 1)
            seg0 = P[k - 1]
            v = P[k] - seg0
            n = float(np.linalg.norm(v))
            d, reach = (v / n, n) if n > tol else (None, 0.0)
        else:
            reach = max(reach, proj)
    if len(P) and (not out or out[-1] != len(P) - 1):
        out.append(len(P) - 1)
    return out


def _runs(kind: list[str], ring: list[int]) -> list[tuple[int, int]]:
    """Zusammenhaengende Abschnitte gleicher (kind, ring) als (Start, Ende) inklusive."""
    runs, s = [], 0
    for i in range(1, len(kind) + 1):
        if i == len(kind) or kind[i] != kind[s] or ring[i] != ring[s]:
            runs.append((s, i - 1))
            s = i
    return runs


def _match_waypoints(
    cand: list[int],
    P_W: np.ndarray,
    waypoints: np.ndarray,
    tol: float,
    ring: int,  # noqa: N803
) -> list[int]:
    """Monotone Zuordnung Wegpunkt -> Sample (Index in `cand`): das erste Sample innerhalb `tol`,
    dann weiter, solange der Abstand faellt."""
    out: list[int] = []
    j = 0
    prev_wp = None
    for w, wp in enumerate(waypoints):
        if prev_wp is not None and np.linalg.norm(wp - prev_wp) < _SAME_MM:
            continue
        dist = np.linalg.norm(P_W[cand] - wp, axis=1)
        k = j
        while k < len(cand) and dist[k] > tol:
            k += 1
        if k == len(cand):
            raise ValueError(
                f"Ring {ring}: Wegpunkt {w} {np.round(wp, 3).tolist()} liegt auf keinem Druck-Sample "
                f"(Toleranz {tol} mm)"
            )
        while k + 1 < len(cand) and dist[k + 1] < dist[k]:
            k += 1
        out.append(k)
        j = k + 1
        prev_wp = wp
    return out


def build_steps(pp: PlannedPart) -> tuple[list[Step], np.ndarray]:
    """Ablaufplan (Bewegungen, Pumpe) aus der Trajektorie; liefert auch T_BT je Sample."""
    tr, prm = pp.trajectory, pp.params
    n = len(tr.t_s)
    if n == 0:
        raise ValueError("Trajektorie ist leer")
    Q = np.asarray(tr.q, dtype=float)  # noqa: N806
    T_FT = np.asarray(pp.scene.tool.T_FT, dtype=float)  # noqa: N806
    T_WB = np.asarray(pp.scene.workstation.T_WB, dtype=float)  # noqa: N806
    T_BT = fk_batch(Q) @ T_FT  # noqa: N806
    P_B = T_BT[:, :3, 3]  # noqa: N806
    P_W = P_B @ T_WB[:3, :3].T + T_WB[:3, 3]  # noqa: N806

    steps: list[Step] = []
    cur = 0
    printed: set[int] = set()

    def add_move(cmd: Literal["movej", "movel"], i: int, radius: float = 0.0) -> None:
        nonlocal cur
        if tr.status[i] == "unreachable":
            raise ValueError(f"Bewegungsziel Sample {i} ist unreachable")
        same = (
            np.max(np.abs(Q[i] - Q[cur])) < _SAME_RAD
            if cmd == "movej"
            else np.linalg.norm(P_B[i] - P_B[cur]) < _SAME_MM
            and np.allclose(T_BT[i, :3, :3], T_BT[cur, :3, :3], atol=1e-9)
        )
        if same and i != 0:
            cur = i
            return
        steps.append(Move(cmd, i, tr.kind[i], tr.ring[i], radius))
        cur = i

    steps.append(Comment("Start (Home)"))
    steps.append(Move("movej", 0, tr.kind[0], tr.ring[0]))
    last_ring = None
    for s, e in _runs(list(tr.kind), list(tr.ring)):
        idx = [i for i in range(s, e + 1) if i > cur]
        if not idx:
            continue
        kind, ring = tr.kind[s], tr.ring[s]
        if kind == "transfer" and ring != last_ring:
            rp = pp.toolpath.rings[ring] if 0 <= ring < len(pp.toolpath.rings) else None
            label = f"Ring {ring}" + (f": Schicht {rp.layer}, Schale {rp.shell}, {rp.kind}" if rp else "")
            steps.append(Comment(label))
            last_ring = ring
        if kind == "transfer":
            for k in _linear_breaks(Q[idx], Q[cur], _LINEAR_TOL_RAD):
                add_move("movej", idx[k])
        elif kind in _CARTESIAN_KINDS:
            for k in _linear_breaks(P_B[idx], P_B[cur], _LINEAR_TOL_MM):
                add_move("movel", idx[k])
        elif kind == "print":
            if ring in printed:
                raise ValueError(f"Ring {ring}: Druck-Samples nicht zusammenhaengend")
            if not 0 <= ring < len(pp.toolpath.rings):
                raise ValueError(f"Ring {ring} fehlt im Toolpath")
            printed.add(ring)
            cand = [cur, *idx]
            wps = np.asarray(pp.toolpath.rings[ring].waypoints, dtype=float)[:, :3]
            ks = _match_waypoints(cand, P_W, wps, prm.match_tol_mm, ring)
            if np.linalg.norm(P_W[idx[-1]] - wps[-1]) > prm.match_tol_mm:
                raise ValueError(f"Ring {ring}: letztes Druck-Sample liegt nicht auf dem Ringende")
            targets = [cand[k] for k in ks if k > 0]
            pts = [P_B[cur]] + [P_B[i] for i in targets]
            steps.append(Pump(True, ring))
            for m, i in enumerate(targets):
                if m == len(targets) - 1:
                    r = 0.0
                else:
                    seg_in = float(np.linalg.norm(pts[m + 1] - pts[m]))
                    seg_out = float(np.linalg.norm(pts[m + 2] - pts[m + 1]))
                    r = math.floor(min(prm.r_blend_mm, 0.5 * seg_in, 0.5 * seg_out) * 1e4) / 1e4
                steps.append(Move("movel", i, "print", ring, r))
                cur = i
            steps.append(Pump(False, ring))
        else:
            raise ValueError(f"unbekannte Sample-Art {kind!r}")
    missing = sorted(set(range(len(pp.toolpath.rings))) - printed)
    if missing:
        raise ValueError(f"Ringe ohne Druck-Samples: {missing}")
    return steps, T_BT


# --------------------------------------------------------------------------- Text


def _ascii(text: object) -> str:
    s = str(text).replace("\r", " ").replace("\n", " ")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return s.encode("ascii", "replace").decode("ascii")


def _header(pp: PlannedPart, dialect: str, n_moves: int) -> list[str]:
    prm, prov = pp.params, pp.provenance
    jv = ", ".join(_f(v, 1) for v in prm.joint_vel_deg_s())
    lines = [
        "RoboPrintIFC v2 - DRL-Programm fuer Doosan M1013 (Lehm-3D-Druck)",
        f"Dialekt: {dialect}"
        + (" (nur Befehle aus Firmware 2.x)" if dialect == "v2" else " (Befehle ab V3 erlaubt)")
        + (", Druck als movesx" if dialect == "v3" and prm.v3_movesx else ", Druck als movel mit Blending"),
        f"Szenario: {pp.scenario_id}",
        f"Teil: {pp.part.part_id} (Wand {pp.part.wall_id}), Status: {pp.part.status}, "
        f"{len(pp.toolpath.rings)} Ringe, {len(pp.trajectory.t_s)} Samples, {n_moves} Bewegungsbefehle",
        "Provenienz: "
        + (
            f"git {prov.git_commit or 'unbekannt'}, erstellt {prov.created}, Kommando: {prov.command}"
            if prov
            else "unbekannt"
        ),
        "Posen: posx = T_BT (TCP in Roboterbasis B) in mm und Grad, Euler ZYZ, ref=DR_BASE;",
        "       posj in Grad, Doosan-Konvention. Alle Ziele stammen aus trajectory.json.",
        "",
        "ACHTUNG: Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck",
        "         (ohne Material, change_operation_speed 10..20 %).",
        "",
        "Provisorische Werte (SPEC 10, A = Annahme, vom Nutzer zu bestaetigen):",
        f"  A Schichthoehe h            {prm.layer_height_mm} mm",
        f"  A Strangbreite w            {prm.bead_width_mm} mm",
        f"  A v_print                   {prm.v_print_mm_s} mm/s, {prm.w_print_deg_s} deg/s "
        f"(acc {prm.a_print_mm_s2} mm/s2, {prm.aw_print_deg_s2} deg/s2)",
        f"  A v_travel                  {prm.v_travel_mm_s} mm/s, {prm.w_travel_deg_s} deg/s "
        f"(acc {prm.a_travel_mm_s2} mm/s2, {prm.aw_travel_deg_s2} deg/s2)",
        f"  A Gelenke                   {prm.joint_speed_fraction * 100:.0f} % der Grenzen: [{jv}] deg/s, "
        f"acc = {_JOINT_ACC_FACTOR:g} x vel",
        f"  A z_lift                    {prm.z_lift_mm} mm ueber Druckstand-Oberkante",
        f"  A An- und Abfahrt           senkrecht {prm.approach_mm} mm",
        f"  A V_pump                    {prm.v_pump_v} V konstant auf AO {prm.pump_channel} (pump_a)",
        f"  A t_tot                     {prm.t_tot_s} s Verweilzeit am Ringstart (provisorisch)",
        f"  A r_blend                   min({prm.r_blend_mm} mm, 1/2 Segmentlaenge)",
        f"  A d_hard                    {prm.d_hard_mm} mm",
        f"  A tau_max                   {prm.tau_max_deg} deg",
        f"  A tcp_name                  {prm.tcp_name} (am Teach Pendant anlegen: tools/30gut.json,",
        "                              Position (134, 0, 73) mm, 90 deg um Flansch-Y)",
        f"  A Dialekt                   {dialect} (Firmware am Teach Pendant pruefen)",
    ]
    known = {f.name for f in fields(DrlParams)}
    extra = {k: v for k, v in pp.run_params.items() if k not in known}
    if extra:
        lines.append("Weitere Laufparameter: " + ", ".join(f"{k}={v}" for k, v in sorted(extra.items())))
    lines += [
        "",
        "Fehlerfall: Der Rumpf steht in try/finally; finally setzt den Analogausgang auf 0 V.",
        "Ein Stopp am Teach Pendant beendet das Programm ggf. ohne finally: Pumpe dann pruefen.",
    ]
    return ["# " + _ascii(s) if s else "#" for s in lines]


def _render(pp: PlannedPart, dialect: str, steps: list[Step], T_BT: np.ndarray) -> str:  # noqa: N803
    prm = pp.params
    Q = pp.trajectory.q  # noqa: N806
    ch = prm.pump_channel
    vt = f"vel=[{_f(prm.v_travel_mm_s, 1)}, {_f(prm.w_travel_deg_s, 1)}]"
    at = f"acc=[{_f(prm.a_travel_mm_s2, 1)}, {_f(prm.aw_travel_deg_s2, 1)}]"
    n_moves = sum(isinstance(s, Move) for s in steps)
    out = _header(pp, dialect, n_moves)
    out += [
        "",
        f"set_velx({_f(prm.v_print_mm_s, 1)}, {_f(prm.w_print_deg_s, 1)})",
        f"set_accx({_f(prm.a_print_mm_s2, 1)}, {_f(prm.aw_print_deg_s2, 1)})",
        "set_velj([" + ", ".join(_f(v, 3) for v in prm.joint_vel_deg_s()) + "])",
        "set_accj([" + ", ".join(_f(v, 3) for v in prm.joint_acc_deg_s2()) + "])",
        f'set_tcp("{_ascii(prm.tcp_name)}")',
        "set_singularity_handling(DR_VAR_VEL)",
        f"set_mode_analog_output(ch={ch}, mod=DR_ANALOG_VOLTAGE)",
        f"set_analog_output(ch={ch}, val=0.0)",
        "",
        "try:",
    ]
    ind = "    "
    use_movesx = dialect == "v3" and prm.v3_movesx
    block: list[str] = []

    def flush() -> None:
        for s in range(0, len(block), MOVESX_MAX_POINTS):
            chunk = block[s : s + MOVESX_MAX_POINTS]
            out.append(f"{ind}movesx([")
            out.extend(f"{ind}    {p}," for p in chunk)
            out.append(
                f"{ind}], vel=[{_f(prm.v_print_mm_s, 1)}, {_f(prm.w_print_deg_s, 1)}], "
                f"acc=[{_f(prm.a_print_mm_s2, 1)}, {_f(prm.aw_print_deg_s2, 1)}], "
                "ref=DR_BASE, vel_opt=DR_MVS_VEL_CONST)"
            )
        block.clear()

    for st in steps:
        if isinstance(st, Comment):
            out.append(f"{ind}# {_ascii(st.text)}")
        elif isinstance(st, Pump):
            if st.on:
                out.append(f"{ind}set_analog_output(ch={ch}, val={_f(prm.v_pump_v, 3)})")
                out.append(f"{ind}wait({_f(prm.t_tot_s, 3)})")
            else:
                flush()
                out.append(f"{ind}set_analog_output(ch={ch}, val=0.0)")
        elif st.cmd == "movej":
            out.append(f"{ind}movej({format_posj(np.asarray(Q[st.sample]))})  # {st.kind}, s{st.sample}")
        elif st.kind == "print":
            px = format_posx(T_BT[st.sample])
            if use_movesx:
                block.append(px)
            else:
                out.append(
                    f"{ind}movel({px}, radius={_f(st.radius_mm, 4)}, ref=DR_BASE, ra=DR_MV_RA_DUPLICATE)"
                    f"  # s{st.sample}"
                )
        else:
            # Geschwindigkeit je Bewegungsart aus `roboprint.params` (wie die Zeitachse in `timing`):
            # Druckgeschwindigkeit = Vorgabe von set_velx, sonst explizites vel=/acc=.
            px = format_posx(T_BT[st.sample])
            if st.kind in speeds.PRINT_SPEED_KINDS:
                out.append(f"{ind}movel({px}, ref=DR_BASE)  # {st.kind}, s{st.sample}")
            else:
                out.append(f"{ind}movel({px}, {vt}, {at}, ref=DR_BASE)  # {st.kind}, s{st.sample}")
    flush()
    out += [
        f"{ind}# Abschluss",
        f"{ind}set_analog_output(ch={ch}, val=0.0)",
        "finally:",
        f"{ind}set_analog_output(ch={ch}, val=0.0)",
        "",
    ]
    return "\n".join(out)


def emit(planned_part: PlannedPart, dialect: Dialect, *, allow_infeasible: bool = False) -> str:
    """Erzeugt den DRL-Programmtext fuer `dialect` in {"v2", "v3"}.

    Wirft ValueError bei unbekanntem Dialekt, ungueltigen Parametern, nicht machbarem Teil
    (ausser `allow_infeasible`), unerreichbaren Zielen oder Druck-Samples, die nicht auf den
    Toolpath-Wegpunkten liegen.
    """
    if dialect not in DIALECTS:
        raise ValueError(f"Dialekt {dialect!r} unbekannt, erlaubt {DIALECTS}")
    pp = planned_part
    pp.params.validate()
    tr = pp.trajectory
    if not allow_infeasible:
        if pp.part.status != "machbar":
            raise ValueError(f"Teil {pp.part.part_id} ist {pp.part.status}: kein Programm")
        if tr.summary.n_collision or tr.summary.n_unreachable:
            raise ValueError(f"Teil {pp.part.part_id}: Trajektorie hat collision/unreachable-Samples")
    steps, T_BT = build_steps(pp)  # noqa: N806
    return _render(pp, dialect, steps, T_BT)


# --------------------------------------------------------------------------- Laufordner


def load_planned_part(part_dir: str | Path, params: DrlParams | None = None) -> PlannedPart:
    """Liest `parts/<id>/` samt `scene.json` und (falls vorhanden) `summary.json` des Laufs."""
    part_dir = Path(part_dir)
    run_dir = part_dir.parent.parent
    summary = load_json(run_dir / "summary.json", Summary) if (run_dir / "summary.json").exists() else None
    run_params = dict(summary.params) if summary else {}
    return PlannedPart(
        trajectory=load_json(part_dir / "trajectory.json", Trajectory),
        toolpath=load_json(part_dir / "toolpath.json", Toolpath),
        part=load_json(part_dir / "part.json", PartArtifact),
        scene=load_json(run_dir / "scene.json", Scene),
        params=params or DrlParams.from_params(run_params),
        provenance=summary.provenance if summary else None,
        scenario_id=summary.scenario_id if summary else "unbekannt",
        run_params=run_params,
    )


def write_programs(part_dir: str | Path, params: DrlParams | None = None) -> list[Path]:
    """Schreibt `program.v2.drl` und `program.v3.drl` in den Teilordner."""
    pp = load_planned_part(part_dir, params)
    paths = []
    for d in DIALECTS:
        p = Path(part_dir) / f"program.{d}.drl"
        p.write_text(emit(pp, d), encoding="ascii", newline="\n")  # type: ignore[arg-type]
        paths.append(p)
    return paths


__all__ = [
    "DIALECTS",
    "DrlParams",
    "PlannedPart",
    "build_steps",
    "emit",
    "format_posj",
    "format_posx",
    "load_planned_part",
    "matrix_from_zyz",
    "posx_values",
    "write_programs",
    "zyz_from_matrix",
]
