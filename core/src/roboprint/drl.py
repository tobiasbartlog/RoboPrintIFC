"""DRL-Emitter fuer die Dialekte v2 und v3 (Doosan M1013, SPEC §5.6, docs/doosan-drl.md).

Grad gibt es nur hier. Schnittstelle::

    emit(planned_part: PlannedPart, dialect: Literal["v2", "v3"], *, allow_infeasible=False) -> str
    load_planned_part(part_dir) -> PlannedPart       # liest einen Laufordner (SPEC §6)
    write_programs(part_dir) -> [program.v2.drl, program.v3.drl]

`PlannedPart` ist ein schlanker Wrapper um die Vertraege `Trajectory`, `Toolpath`,
`PartArtifact` und `Scene` plus Parameter (`DrlParams`, SPEC §10) und Provenienz. Den
dialektunabhaengigen Ablaufplan baut `roboprint.drl_steps`; hier entsteht der Text.

**Bezug:** Jedes Bewegungsziel ist ein Sample der geplanten Trajektorie (genau der gepruefte
Zweig). Nichts wird per IK neu gerechnet:

- `transfer` -> `movej(posj(q))` mit dem q am Ende jedes gelenklinearen Stuecks (ein
  Zwischenpunkt eines Transfers wird als Knick der Gelenkgeraden erkannt);
- `lift`, `lower`, `approach`, `retract` -> `movel(posx(T_BT))` mit T_BT = FK(q) @ T_FT am
  Ende jedes kartesisch linearen Stuecks;
- `print` -> je Toolpath-Wegpunkt ein `movel` auf das Druck-Sample, das diesem Wegpunkt
  entspricht (monotone Zuordnung entlang des Rings, Toleranz `match_tol_mm`, Position aus
  T_WB @ FK(q) @ T_FT);
- `link` (Verbinder) -> ein `movel` auf sein letztes Sample (= erster Wegpunkt des naechsten Rings).

**Je Strang** (SPEC §5.3, Nutzerentscheidung 20.10.2026: Ringe ueber gedruckte Verbinder ohne
Halt, Pumpe laeuft durch): Pumpe an (`set_analog_output(ch, V_pump)` + `wait(t_tot)`) einmal am
Strangbeginn im Stillstand nach der Anfahrt; Druck- und Verbinder-`movel` mit
`radius = min(r_blend_max, 1/2 der angrenzenden Segmente)` und `ra=DR_MV_RA_DUPLICATE`, auch an
Ringende und Verbinder-Ecken; nur das letzte `movel` des Strangs mit `radius=0` (Halt, damit die
Pumpe am Strangende schaltet), danach Pumpe aus. Ein Ring ohne Verbinder ist ein Strang aus einem
Ring (alter Ablauf je Ring).

Dialekt v3 kann den Druck optional als einen `movesx`-Block (`vel_opt=DR_MVS_VEL_CONST`) je Strang
ausgeben (`DrlParams.v3_movesx`), aber nur fuer Straenge aus **einem** Ring mit hoechstens 100
Zielen. Straenge mit Verbindern oder mehr Zielen bleiben auch in v3 `movel` mit Blending: `movesx`
haelt am Blockende an (kein Online-Blending zum naechsten Befehl, docs/doosan-drl.md), mehrere
Bloecke wuerden den Strang also mit laufender Pumpe anhalten, und der Spline durch die Ziele faehrt
einen Verbinder nicht als Gerade (SPEC §5.3, G3: <= 0,5 mm neben der Geraden). Default ist aus,
weil der Spline auch zwischen den Druck-Wegpunkten von den Geraden abweicht. Der Programmrumpf
steht in `try/finally`, das den Analogausgang auf 0 setzt; zusaetzlich setzt die
Abschlusssequenz am Programmende 0 V. Der Text ist reines ASCII.
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
from roboprint.drl_steps import STRAND_KINDS, Comment, Move, Pump, Step, plan_steps
from roboprint.robot import JOINT_VEL_LIMITS, fk_batch

Dialect = Literal["v2", "v3"]
DIALECTS: tuple[str, ...] = ("v2", "v3")

GIMBAL_EPS = 1e-9  # |sin b| darunter: Gimbal-Fall b = 0 oder b = 180 Grad
MOVESX_MAX_POINTS = 100
AO_CHANNELS = (1, 2)
AO_VOLT_RANGE = (0.0, 10.0)
TCP_SPEED_MAX_MM_S = 1000.0  # Datenblatt M1013: max. TCP-Geschwindigkeit 1 m/s
_JOINT_ACC_FACTOR = speeds.JOINT_ACC_FACTOR  # robots/doosan_m1013.json: ~ 4 x v_max (provisorisch)


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
    t_tot_s: float = 3.0  # A, provisorisch: Pumpen-Vorlauf einmal am Strangbeginn
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
    link_max_mm: float = 60.0  # Nutzer 20.10.2026, laengster Verbinder, 0 = aus (setzt der Slicer um)

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
        if self.t_tot_s < 0.0 or self.r_blend_mm < 0.0 or self.link_max_mm < 0.0:
            raise ValueError("t_tot_s, r_blend_mm und link_max_mm muessen >= 0 sein")

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


def build_steps(pp: PlannedPart) -> tuple[list[Step], np.ndarray]:
    """Ablaufplan (Bewegungen, Pumpe je Strang) aus der Trajektorie (`roboprint.drl_steps`);
    liefert auch T_BT je Sample."""
    tr, prm = pp.trajectory, pp.params
    if len(tr.t_s) == 0:
        raise ValueError("Trajektorie ist leer")
    T_FT = np.asarray(pp.scene.tool.T_FT, dtype=float)  # noqa: N806
    T_WB = np.asarray(pp.scene.workstation.T_WB, dtype=float)  # noqa: N806
    T_BT = fk_batch(np.asarray(tr.q, dtype=float)) @ T_FT  # noqa: N806
    steps = plan_steps(tr, pp.toolpath, T_BT, T_WB, prm.r_blend_mm, prm.match_tol_mm)
    return steps, T_BT


# --------------------------------------------------------------------------- Text


def _ascii(text: object) -> str:
    s = str(text).replace("\r", " ").replace("\n", " ")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return s.encode("ascii", "replace").decode("ascii")


def _header(pp: PlannedPart, dialect: str, steps: list[Step]) -> list[str]:
    prm, prov = pp.params, pp.provenance
    jv = ", ".join(_f(v, 1) for v in prm.joint_vel_deg_s())
    n_moves = sum(isinstance(s, Move) for s in steps)
    starts = [s for s in steps if isinstance(s, Pump) and s.on]
    n_links = sum(s.links for s in starts)
    lines = [
        "RoboPrintIFC v2 - DRL-Programm fuer Doosan M1013 (Lehm-3D-Druck)",
        f"Dialekt: {dialect}"
        + (" (nur Befehle aus Firmware 2.x)" if dialect == "v2" else " (Befehle ab V3 erlaubt)")
        + (
            ", Druck als movesx (Straenge aus einem Ring mit <= 100 Zielen, sonst movel mit Blending)"
            if dialect == "v3" and prm.v3_movesx
            else ", Druck als movel mit Blending"
        ),
        f"Szenario: {pp.scenario_id}",
        f"Teil: {pp.part.part_id} (Wand {pp.part.wall_id}), Status: {pp.part.status}, "
        f"{len(pp.toolpath.rings)} Ringe in {len(starts)} Straengen ({n_links} Verbinder), "
        f"{len(pp.trajectory.t_s)} Samples, {n_moves} Bewegungsbefehle",
        "Provenienz: "
        + (
            f"git {prov.git_commit or 'unbekannt'}, erstellt {prov.created}, Kommando: {prov.command}"
            if prov
            else "unbekannt"
        ),
        "Posen: posx = T_BT (TCP in Roboterbasis B) in mm und Grad, Euler ZYZ, ref=DR_BASE;",
        "       posj in Grad, Doosan-Konvention. Alle Ziele stammen aus trajectory.json.",
        "Strang: Ringe und Verbinder ohne Halt, die Pumpe laeuft durch. Pumpe an + wait(t_tot) nur am",
        "        Strangbeginn, Pumpe aus nur am Strangende (letztes movel mit radius=0).",
        "",
        "ACHTUNG: Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck",
        "         (ohne Material, change_operation_speed 10..20 %).",
        "",
        "Provisorische Werte (SPEC 10, A = Annahme, vom Nutzer zu bestaetigen; N = Nutzervorgabe):",
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
        f"  A t_tot                     {prm.t_tot_s} s Pumpen-Vorlauf am Strangbeginn (provisorisch)",
        f"  N link_max_mm               {prm.link_max_mm} mm, laengster Verbinder (0 = aus)"
        if prm.link_max_mm > 0
        else "  N link_max_mm               0 (Verbinder aus: je Ring ein Strang)",
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
    out = _header(pp, dialect, steps)
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
    strand_movesx = False  # laufender Strang als ein movesx-Block (Bedingungen im Modul-Docstring)
    block: list[str] = []

    def flush() -> None:
        if not block:
            return
        assert len(block) <= MOVESX_MAX_POINTS
        out.append(f"{ind}movesx([")
        out.extend(f"{ind}    {p}," for p in block)
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
                strand_movesx = use_movesx and st.links == 0 and st.moves <= MOVESX_MAX_POINTS
                out.append(f"{ind}set_analog_output(ch={ch}, val={_f(prm.v_pump_v, 3)})")
                out.append(f"{ind}wait({_f(prm.t_tot_s, 3)})")
            else:
                flush()
                strand_movesx = False
                out.append(f"{ind}set_analog_output(ch={ch}, val=0.0)")
        elif st.cmd == "movej":
            out.append(f"{ind}movej({format_posj(np.asarray(Q[st.sample]))})  # {st.kind}, s{st.sample}")
        elif st.kind in STRAND_KINDS:
            # Druck und Verbinder: Geschwindigkeit aus set_velx, Blending im ganzen Strang
            px = format_posx(T_BT[st.sample])
            if strand_movesx:
                block.append(px)
            else:
                tag = "" if st.kind == "print" else f"{st.kind}, "
                out.append(
                    f"{ind}movel({px}, radius={_f(st.radius_mm, 4)}, ref=DR_BASE, ra=DR_MV_RA_DUPLICATE)"
                    f"  # {tag}s{st.sample}"
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
    steps, T_BT = _checked_steps(planned_part, allow_infeasible)  # noqa: N806
    return _render(planned_part, dialect, steps, T_BT)


def _checked_steps(pp: PlannedPart, allow_infeasible: bool) -> tuple[list[Step], np.ndarray]:
    """Parameter und Machbarkeit pruefen, dann den (dialektunabhaengigen) Ablaufplan bauen."""
    pp.params.validate()
    tr = pp.trajectory
    if not allow_infeasible:
        if pp.part.status != "machbar":
            raise ValueError(f"Teil {pp.part.part_id} ist {pp.part.status}: kein Programm")
        if tr.summary.n_collision or tr.summary.n_unreachable:
            raise ValueError(f"Teil {pp.part.part_id}: Trajektorie hat collision/unreachable-Samples")
    return build_steps(pp)


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
    steps, T_BT = _checked_steps(pp, allow_infeasible=False)  # noqa: N806 - einmal fuer beide Dialekte
    paths = []
    for d in DIALECTS:
        p = Path(part_dir) / f"program.{d}.drl"
        p.write_text(_render(pp, d, steps, T_BT), encoding="ascii", newline="\n")
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
