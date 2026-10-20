"""fgc.postproc.emitter — Emitter-Protocol und DRL-Emit-Funktion (Strang C, ADR-011).

Der Emitter erzeugt aus dem **Toolpath** (roboterunabhängige Targets) + Setup +
Bewegungsparametern (``process_params.motion``) ein controller-natives
DRL-Programm: **per Toolpath-Target** ein Bewegungsbefehl —
``movel(posx, vel, acc, radius, ref)`` für Druck-, ``movej(posx, …)`` für
Verfahrbewegungen (Issue #64). Der dichte Gelenk-Stream der Simulation
(``trajectory.json``) bleibt für den Viewer-Replay erhalten; die DRL wird kürzer
und dem Controller überlassen (er löst die IK der Cartesian-Ziele).

Logische Kanäle aus den Targets werden über das Kanal-Mapping des Setups auf
physische AO-/DO-Ausgänge gemappt (ADR-011). Grad-Konvertierung (Quaternion →
ZYZ-Euler, Radiant → Grad) ausschließlich hier (ADR-006). Change-on-Delta: nur
bei io-Wertänderung ein Befehl, keine redundanten Schreibzugriffe.

**Provisorik-Stempel** (ADR-006/012/013): die Bewegungsgrenzen (vel/acc/Blending)
stammen aus angenommenen ``process_params.motion``-Werten (Spike S1 markiert),
nicht aus am Gerät gemessenen Grenzen. Der Stempel im DRL-Kopf kennzeichnet das
Programm als vorläufig — **kein Gate**: es entsteht trotzdem.
"""

from __future__ import annotations

import math
from typing import Any

from fgc.domain.models import Frame
from fgc.simulation import transform
from fgc.simulation.motion import MOVEL, MotionParams

_AO_MODE = {
    "analog_voltage": "DR_ANALOG_VOLTAGE",
    "analog_current": "DR_ANALOG_CURRENT",
}

#: Logisches Referenz-Frame (``motion.ref``) → DRL-Bezugssystem-Token.
_REF = {"base": "DR_BASE", "world": "DR_WORLD", "tool": "DR_TOOL"}


def emit_drl(
    toolpath: dict[str, Any],
    setup: dict[str, Any],
    provenance: dict[str, Any],
    motion: MotionParams | None = None,
) -> str:
    """Erzeugt ein DRL-Programm aus Toolpath + Setup + Bewegungsparametern.

    Je Target ein Bewegungsbefehl: ``movel`` für Druck- (``kind == "print"``),
    ``movej`` für Verfahr-Targets (``kind == "travel"``) — der Bewegungstyp je
    Zielart kommt aus ``motion`` (``print_move``/``travel_move``). Die Ziel-Pose
    wird als kartesische ``posx`` im Bezugssystem ``motion.ref`` emittiert; sie
    entsteht aus ``wall_to_base ∘ frame`` (die eine Transformationsstelle ist das
    Setup, ADR-006). vel/acc/Blending/ref stammen aus ``motion``
    (``process_params.motion``); ist ``motion.tcp_vel_mm_s`` nicht gesetzt, gilt
    das je Target kommandierte ``v_mm_s``.

    Change-on-Delta: AO/DO-Befehle werden nur bei Wertänderung emittiert.
    Kanal-Mapping ausschließlich aus ``setup["io_channels"]`` (ADR-011).
    Grad nur hier (ADR-006).

    Raises:
        ValueError: Unbekannter logischer Kanal (nicht in setup.io_channels).
        ValueError: Logischer Wert außerhalb von logical_range (→ physischer
                    Wert würde physical_range verlassen).
    """
    motion = motion or MotionParams()
    io_channels: dict[str, Any] = setup["io_channels"]
    targets: list[dict[str, Any]] = toolpath["targets"]
    robot: str = setup.get("robot", "doosan_m1013")

    wall_to_base = transform.frame_from_dict(setup["wall_to_base"])

    traj_channels = sorted({ch for t in targets for ch in t.get("io", {})})
    for ch in traj_channels:
        if ch not in io_channels:
            raise ValueError(
                f"Unbekannter logischer Kanal {ch!r} — nicht in setup.io_channels."
                " Kanal-Mapping ausschließlich aus dem Setup (ADR-011)."
            )

    ref_token = _REF.get(str(motion.ref).lower(), str(motion.ref))
    n_print = sum(1 for t in targets if str(t.get("kind", "print")) != "travel")
    n_travel = len(targets) - n_print

    lines: list[str] = []

    # --- Header -----------------------------------------------------------------
    lines += [
        f"# FGC-Planner — DRL-Programm ({robot})",
        f"# Quelle: {provenance['source']}",
        f"# Erstellt: {provenance['created']}",
        f"# Git: {provenance['git_commit']}",
        f"# Toolpath: {len(targets)} Targets ({n_print} Druck, {n_travel} Travel)",
    ]

    # --- Provisorik-Stempel (Spike S1, kein Gate — ADR-006/012/013) -------------
    if motion.provisional:
        vel_desc = (
            f"{motion.tcp_vel_mm_s:.1f} mm/s"
            if motion.tcp_vel_mm_s is not None
            else "je Target (v_mm_s aus Prozessfenster)"
        )
        lines += [
            "#",
            "# ===================== PROVISORISCH (Spike S1) =====================",
            "# Die Bewegungsgrenzen (vel/acc/Blending) sind PROVISORISCH: sie stammen",
            "# aus process_params.motion (angenommene Werte), nicht aus am Gerät",
            "# gemessenen vel/acc-Grenzen. Kein Gate (ADR-006/012/013) — das Programm",
            "# entsteht, ist aber bis zur S1-Messung als vorläufig zu behandeln.",
            f"#   vel     = {vel_desc}",
            f"#   acc     = {motion.tcp_acc_mm_s2:.1f} mm/s^2",
            f"#   blending= {motion.blending_mm:.1f} mm (Verrundung siehe Issue #63)",
            f"#   ref     = {ref_token}",
            "# ===================================================================",
        ]

    # --- Kanal-Modus-Setup ------------------------------------------------------
    analog_chs = [c for c in traj_channels if io_channels[c]["kind"] != "digital"]
    if analog_chs:
        lines.append("")
        lines.append("# --- Kanal-Modus ---")
        for ch in sorted(analog_chs, key=lambda c: io_channels[c]["index"]):
            cfg = io_channels[ch]
            mode = _AO_MODE.get(cfg["kind"], "DR_ANALOG_VOLTAGE")
            ph = cfg["physical_range"]
            lines.append(
                f"set_mode_analog_output(ch={cfg['index']}, mod={mode})"
                f"   # {ch} -> AO{cfg['index']}, {ph[0]}..{ph[1]}"
            )

    # --- Bewegung + IO ----------------------------------------------------------
    lines += ["", "# --- Bewegung + IO ---"]
    last_ph: dict[str, float] = {}

    for t in targets:
        io = t.get("io", {})

        for ch in sorted(traj_channels, key=lambda c: io_channels[c]["index"]):
            cfg = io_channels[ch]
            logical_val = float(io.get(ch, 0.0))
            ph_val = _map_to_physical(ch, logical_val, cfg)
            last = last_ph.get(ch)
            if last is None or ph_val != last:
                if cfg["kind"] == "digital":
                    mid = 0.5 * (cfg["physical_range"][0] + cfg["physical_range"][1])
                    lines.append(f"set_digital_output(ch={cfg['index']}, val={ph_val > mid})")
                else:
                    lines.append(f"set_analog_output(ch={cfg['index']}, val={ph_val:.3f})")
                last_ph[ch] = ph_val

        kind = str(t.get("kind", "print"))
        move = motion.travel_move if kind == "travel" else motion.print_move
        cmd = "movel" if move == MOVEL else "movej"
        posx = _target_posx(wall_to_base, t["frame"])
        vel = motion.tcp_vel_mm_s if motion.tcp_vel_mm_s is not None else float(t["v_mm_s"])
        lines.append(
            f"{cmd}(posx([{posx}]), vel={vel:.3f}, acc={motion.tcp_acc_mm_s2:.3f}, "
            f"radius={motion.blending_mm:.3f}, ref={ref_token})"
            f"   # {kind}, layer {t.get('layer', 0)}, {t.get('segment_id', '')}"
        )

    # --- Abschalten -------------------------------------------------------------
    lines += ["", "# --- Abschalten ---"]
    for ch in sorted(traj_channels, key=lambda c: io_channels[c]["index"]):
        cfg = io_channels[ch]
        if cfg["kind"] == "digital":
            lines.append(f"set_digital_output(ch={cfg['index']}, val=False)")
        else:
            lines.append(f"set_analog_output(ch={cfg['index']}, val=0.000)")

    return "\n".join(lines) + "\n"


def _target_posx(wall_to_base: Frame, frame_dict: dict[str, Any]) -> str:
    """TCP-Ziel als DRL-``posx``-Liste ``x, y, z, a, b, c`` (mm, ZYZ-Euler in Grad).

    Die Wand-lokale Ziel-Pose wird über das Setup (``wall_to_base``) in
    Roboterbasis-Koordinaten gebracht — die eine Transformationsstelle (ADR-006).
    Grad entstehen ausschließlich hier.
    """
    tcp_in_base = transform.compose(wall_to_base, transform.frame_from_dict(frame_dict))
    x, y, z = tcp_in_base.pos_mm
    a, b, c = _quat_to_zyz_deg(tcp_in_base.quat)
    return f"{x:.3f}, {y:.3f}, {z:.3f}, {a:.3f}, {b:.3f}, {c:.3f}"


def _quat_to_zyz_deg(quat: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Einheitsquaternion ``[w, x, y, z]`` → ZYZ-Euler ``(a, b, c)`` in Grad.

    Doosan-``posx`` erwartet die Orientierung als ZYZ-Euler (``R = Rz(a)·Ry(b)·
    Rz(c)``). Bei b≈0/π (Gimbal) wird ``c=0`` gesetzt und der frei bleibende
    Winkel ``a`` allein bestimmt.
    """
    w, x, y, z = transform.quat_normalize(quat)
    r13 = 2.0 * (x * z + w * y)
    r23 = 2.0 * (y * z - w * x)
    r33 = 1.0 - 2.0 * (x * x + y * y)
    r31 = 2.0 * (x * z - w * y)
    r32 = 2.0 * (y * z + w * x)
    r11 = 1.0 - 2.0 * (y * y + z * z)
    r21 = 2.0 * (x * y + w * z)

    sy = math.hypot(r13, r23)
    b = math.atan2(sy, r33)
    if sy > 1e-9:
        a = math.atan2(r23, r13)
        c = math.atan2(r32, -r31)
    else:  # Gimbal (b≈0 oder b≈π): nur a+c bzw. a−c bestimmt → c=0
        a = math.atan2(r21, r11)
        c = 0.0
    return math.degrees(a), math.degrees(b), math.degrees(c)


def _map_to_physical(ch: str, logical_val: float, cfg: dict[str, Any]) -> float:
    lo_min, lo_max = cfg.get("logical_range", [0.0, 1.0])
    ph_min, ph_max = cfg["physical_range"]
    if logical_val < lo_min - 1e-9 or logical_val > lo_max + 1e-9:
        raise ValueError(
            f"Kanal {ch!r}: Logischer Wert {logical_val} außerhalb des erlaubten"
            f" Bereichs [{lo_min}, {lo_max}]"
            f" (physischer Bereich: [{ph_min}, {ph_max}])."
        )
    if abs(lo_max - lo_min) < 1e-12:
        return float(ph_min)
    return ph_min + (logical_val - lo_min) / (lo_max - lo_min) * (ph_max - ph_min)
