"""Realistisches Bewegungsmodell (Issue #62, Scheibe 4 von PRD #57).

Dieses Modul löst die frühere, stückweise-konstante Zeitparametrierung
(:mod:`fgc.simulation.timeparam`) ab: statt jedem Toolpath-Segment eine
konstante Gelenkgeschwindigkeit zuzuweisen, bildet es die reale Bewegung so echt
wie möglich ab:

1. **Trapez-Geschwindigkeitsprofile** (Rampe/Halt/Bremse) — jedes Segment fährt
   unter der *eingestellten Beschleunigung* von Ruhe auf die kommandierte
   Geschwindigkeit hoch, hält sie (soweit die Strecke reicht) und bremst wieder
   auf Ruhe ab. Ohne Blending hält der Roboter an jedem Ziel — genau das macht
   dieses Modell *ehrlich* langsam.
1b. **Blending** (Scheibe 4b / Issue #63, PROVISORISCH S1) — ein gesetzter
   ``blending_mm`` verrundet movel↔movel-Ecken: die Bahn kürzt die Ecke als
   quadratische Bézier-Kurve ab (:func:`blend_corner`) und die angrenzenden
   movel-Segmente teilen sich EIN Trapez, sodass die Geschwindigkeit am
   verblendeten Wegpunkt > 0 bleibt (kein Vollstopp) und die Gesamtzeit sinkt.
   ``blending_mm == 0`` ⇒ exakt das Vollstopp-Verhalten aus Scheibe 4.
2. **movel-lineare TCP-Interpolation** für Druckbewegungen — zwischen zwei
   Print-Zielen wird der TCP entlang der **kartesischen Geraden** dicht abgetastet
   (Position linear, Orientierung per Slerp), je Zwischenpose die IK befragt.
   **Gelenkinterpolation** (movej) für Travel-Bewegungen.
3. **Ehrliche Befunde** — die Konfigurationswahl (:func:`select_along_path`) läuft
   über die *ganze* dichte movel-Gerade und hält so eine Konfiguration, die die
   komplette Gerade fahrbar lässt. Eine unfahrbare/singuläre Zwischenstelle wird
   als **verortete Warnung** gemeldet (mit ihrer interpolierten Zeit), **kein**
   stiller Rückfall auf Gelenkinterpolation, der die Stelle kaschieren würde. Der
   Arm friert dort auf der letzten gültigen Gelenklösung ein (sichtbar wie das
   eingefrorene Home aus Issue #66/#56).

Bewegungstyp und die Bewegungsdynamik kommen aus :class:`MotionParams`
(gespeist aus ``process_params.motion``, Issue #59-Rail). Die kartesischen
vel/acc-Grenzen sind **provisorisch** (Spike S1 markiert) — sie werden ersetzt,
sobald am Gerät gemessene Werte vorliegen.

Reines Modul ohne I/O: Eingang sind Poses/Kinematik, Ausgang die dichte,
zeitparametrierte Gelenk-/Zeitreihe (:class:`MotionResult`). :func:`build_motion`
ist die eine Stelle, die :func:`fgc.simulation.build_trajectory` aufruft.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

from fgc.domain.models import Frame
from fgc.kinematics import DEFAULT_SINGULARITY_WARN, IkConfigFilter, select_along_path
from fgc.kinematics.opw import OpwKinematics
from fgc.simulation import transform
from fgc.simulation.timeparam import node_accelerations, segment_velocities

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]

#: Mindest-Segmentschritt (s), damit identische/sehr nahe Posen die Zeitachse
#: streng monoton halten (keine zwei Samples mit gleichem t_s). Wie timeparam.
DT_FLOOR_S = 1e-3

#: Bewegungstypen (Bewegungstyp aus ``process_params.motion``).
MOVEL = "movel"  # kartesisch-lineare TCP-Interpolation (Druck)
MOVEJ = "movej"  # Gelenkinterpolation (Travel)


@dataclass(frozen=True)
class MotionParams:
    """Bewegungstyp + Dynamik eines Druckjobs (Quelle: ``process_params.motion``).

    Die kartesischen Dynamikwerte (``tcp_acc_mm_s2``, ``tcp_vel_mm_s``) und die
    Abtastdichten sind **provisorisch** (``provisional=True``, Spike S1): sie
    stammen aus einer plausiblen Annahme, bis am Gerät gemessene vel/acc-Grenzen
    vorliegen. ``print_move``/``travel_move`` legen den Bewegungstyp je Zielart
    fest (Standard: Druck = movel, Travel = movej).
    """

    #: Bewegungstyp für Druck-Ziele (kind == "print").
    print_move: str = MOVEL
    #: Bewegungstyp für Travel-Ziele (kind == "travel").
    travel_move: str = MOVEJ
    #: PROVISORISCH (S1): kartesische Beschleunigung des Trapezprofils (mm/s²).
    tcp_acc_mm_s2: float = 250.0
    #: Optionaler Deckel für die Reisegeschwindigkeit (mm/s); None ⇒ das je Ziel
    #: kommandierte ``v_mm_s`` gilt als Halt-/Cruise-Geschwindigkeit.
    tcp_vel_mm_s: float | None = None
    #: PROVISORISCH (S1): Abtastschritt entlang der movel-Geraden (mm) — je feiner,
    #: desto genauer wird eine Zwischen-Singularität verortet.
    sample_step_mm: float = 20.0
    #: PROVISORISCH (S1): Abtastschritt der movej-Gelenkinterpolation (rad).
    travel_step_rad: float = 0.1
    #: Anteil der Achs-vel/acc-Grenzen, den movej ausnutzt (∈ (0, 1]).
    travel_speed_frac: float = 1.0
    #: PROVISORISCH (S1): Blending-/Verrundungsradius (mm) — im DRL das
    #: ``radius=``-Argument von ``movel``/``movej`` (Issue #64). In der Simulation
    #: verrundet :func:`build_motion` damit die Bahn an movel↔movel-Ecken
    #: (:func:`blend_corner`, Issue #63) und hält die Geschwindigkeit am
    #: verblendeten Wegpunkt > 0 (kein Vollstopp). ``0.0``/None ⇒ exakt das
    #: Scheibe-4-Verhalten (Vollstopp an jedem Ziel).
    blending_mm: float = 0.0
    #: Bezugssystem für die DRL-Bewegungsbefehle (``ref=``-Argument): ``"base"``/
    #: ``"world"``/``"tool"`` oder ein controller-eigenes Frame-Token. Nur der
    #: Emitter konsumiert es; die Simulation rechnet stets in Roboterbasis.
    ref: str = "base"
    #: Immer True, bis S1 gemessene Werte liefert — markiert die Provisorik.
    provisional: bool = True


#: Die Felder, die ``process_params.motion`` eines Druckjobs übersteuern darf.
#: Analog SLICE_PARAM_KEYS/ORIENTATION_PARAM_KEYS (Issue #59/#61-Rail).
MOTION_PARAM_KEYS: tuple[str, ...] = (
    "print_move",
    "travel_move",
    "tcp_acc_mm_s2",
    "tcp_vel_mm_s",
    "sample_step_mm",
    "travel_step_rad",
    "travel_speed_frac",
    "blending_mm",
    "ref",
)


# ---------------------------------------------------------------------------
# Reine Geometrie: Interpolation
# ---------------------------------------------------------------------------


def _lerp3(a: Vec3, b: Vec3, u: float) -> Vec3:
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)


def slerp(q0: Quat, q1: Quat, u: float) -> Quat:
    """Sphärische lineare Interpolation zweier Einheitsquaternionen [w, x, y, z].

    Wählt das kürzere Bogenstück (Vorzeichen von ``q1`` ggf. gespiegelt); bei
    nahezu parallelen Quaternionen linear + normiert (numerisch stabil).
    """
    dot = q0[0] * q1[0] + q0[1] * q1[1] + q0[2] * q1[2] + q0[3] * q1[3]
    if dot < 0.0:
        q1 = (-q1[0], -q1[1], -q1[2], -q1[3])
        dot = -dot
    if dot > 0.9995:  # fast parallel → LERP + Normierung
        r = (
            q0[0] + (q1[0] - q0[0]) * u,
            q0[1] + (q1[1] - q0[1]) * u,
            q0[2] + (q1[2] - q0[2]) * u,
            q0[3] + (q1[3] - q0[3]) * u,
        )
        n = math.sqrt(sum(c * c for c in r)) or 1.0
        return (r[0] / n, r[1] / n, r[2] / n, r[3] / n)
    theta_0 = math.acos(min(1.0, dot))
    sin_0 = math.sin(theta_0)
    s0 = math.sin((1.0 - u) * theta_0) / sin_0
    s1 = math.sin(u * theta_0) / sin_0
    return (
        q0[0] * s0 + q1[0] * s1,
        q0[1] * s0 + q1[1] * s1,
        q0[2] * s0 + q1[2] * s1,
        q0[3] * s0 + q1[3] * s1,
    )


def densify_line(
    p0: Vec3, q0: Quat, p1: Vec3, q1: Quat, max_step_mm: float
) -> list[tuple[Vec3, Quat]]:
    """Dichte Posen entlang der kartesischen Geraden ``p0→p1`` (Endpunkte inklusive).

    Position linear interpoliert, Orientierung per :func:`slerp`. Die Zahl der
    Teilstücke ist ``max(1, ceil(|p1−p0| / max_step_mm))`` — so liegt kein
    Zwischenpunkt weiter als ``max_step_mm`` vom nächsten entfernt.
    """
    dist = math.dist(p0, p1)
    n_steps = max(1, math.ceil(dist / max_step_mm)) if max_step_mm > 0 else 1
    out: list[tuple[Vec3, Quat]] = []
    for k in range(n_steps + 1):
        u = k / n_steps
        out.append((_lerp3(p0, p1, u), slerp(q0, q1, u)))
    return out


def _bezier3(e: Vec3, p: Vec3, x: Vec3, u: float) -> Vec3:
    """Quadratische Bézier-Kurve mit Stützpunkten E, P (Kontrolle), X bei ``u∈[0,1]``."""
    mu = 1.0 - u
    w0, w1, w2 = mu * mu, 2.0 * mu * u, u * u
    return (
        e[0] * w0 + p[0] * w1 + x[0] * w2,
        e[1] * w0 + p[1] * w1 + x[1] * w2,
        e[2] * w0 + p[2] * w1 + x[2] * w2,
    )


def blend_corner(a: Vec3, p: Vec3, b: Vec3, radius: float) -> tuple[Vec3, Vec3, float]:
    """Ein-/Austrittspunkte + effektiver Radius einer Ecken-Verrundung an ``p``.

    PROVISORISCH (Spike S1): das Blending-Modell verrundet die Ecke ``a→p→b`` als
    **quadratische Bézier-Kurve** — Eintritt ``E`` liegt ``r`` vor der Ecke auf
    ``p→a``, Austritt ``X`` liegt ``r`` nach der Ecke auf ``p→b``, die Ecke ``p``
    selbst ist der Kontrollpunkt. Der Radius wird auf die halbe Länge jedes
    angrenzenden Segments gedeckelt (``r = min(radius, |ap|/2, |pb|/2)``), damit
    sich die Verrundungsfenster benachbarter Ecken nicht überlappen. Die Formel
    ist eine **plausible Annahme** (Bézier statt controller-echtem Kreisbogen/
    Spline), bis S1 das gerätespezifische Blending vermisst. Rückgabe
    ``(E, X, r)``; bei ``r <= 0`` (kein Blending / entartetes Segment) ``(p, p, 0)``.
    """
    len_ap = math.dist(a, p)
    len_pb = math.dist(p, b)
    if radius <= 0.0 or len_ap <= 0.0 or len_pb <= 0.0:
        return p, p, 0.0
    r = min(radius, len_ap / 2.0, len_pb / 2.0)
    return _lerp3(p, a, r / len_ap), _lerp3(p, b, r / len_pb), r


def _wrapped_delta(a: float, b: float) -> float:
    """Kürzeste Winkeldifferenz a−b in (−π, π]."""
    return math.atan2(math.sin(a - b), math.cos(a - b))


def densify_joints(
    q0: tuple[float, ...], q1: tuple[float, ...], max_step_rad: float
) -> list[tuple[float, ...]]:
    """Dichte Gelenkfolge zwischen ``q0`` und ``q1`` (kürzeste Wege, Endpunkte inkl.).

    Jedes Gelenk läuft linear entlang seiner **kürzesten** Winkeldifferenz; die
    Schrittzahl richtet sich nach dem am weitesten fahrenden Gelenk.
    """
    deltas = [_wrapped_delta(q1[j], q0[j]) for j in range(len(q0))]
    dmax = max((abs(d) for d in deltas), default=0.0)
    n_steps = max(1, math.ceil(dmax / max_step_rad)) if max_step_rad > 0 else 1
    return [
        tuple(q0[j] + (k / n_steps) * deltas[j] for j in range(len(q0)))
        for k in range(n_steps + 1)
    ]


# ---------------------------------------------------------------------------
# Trapez-Geschwindigkeitsprofil (Rampe/Halt/Bremse), ruhe-zu-ruhe
# ---------------------------------------------------------------------------


def trapezoid_times(
    arc: list[float], v_cruise: float, a: float, *, dt_floor_s: float = DT_FLOOR_S
) -> list[float]:
    """Zeitpunkte je Wegmarke eines **ruhe-zu-ruhe** Trapezprofils.

    ``arc`` ist die kumulierte Weglänge je Sample (``arc[0] == 0``, monoton
    steigend); ``v_cruise`` die Halt-/Cruise-Geschwindigkeit, ``a`` die
    Beschleunigung (beide > 0, gleiche Einheiten wie ``arc``). Rückgabe: Zeiten
    ``t[k] = t(arc[k])`` ab 0.

    Das Profil beginnt und endet **in Ruhe** (v = 0): Rampe mit ``a`` auf
    ``v_cruise`` (bzw. Dreieck, wenn die Strecke zu kurz ist), Halt bei
    ``v_cruise``, Bremse mit ``a`` auf 0. Reicht die Strecke nicht für die
    Cruise-Phase, wird das Profil dreieckig (Spitzengeschwindigkeit
    √(a·L) < v_cruise). Sehr kurze/Null-Strecken werden über ``dt_floor_s``
    streng monoton gehalten.
    """
    n = len(arc)
    if n <= 1:
        return [0.0] * n
    length = arc[-1]
    # Kein echtes Trapez möglich: Null-/Negativstrecke, nicht-positive Dynamik
    # ODER nicht-endliche Dynamik. Letzteres tritt bei einem movej-Segment **ohne
    # Gelenkbewegung** auf (identische Start/End-Konfiguration ⇒ `_limit_ratio`
    # liefert math.inf) — inf/inf würde sonst NaN-Zeiten erzeugen (Issue #62-Fix:
    # NaN in trajectory.json ist ungültiges JSON und lässt den Viewer beim Laden
    # scheitern). Eine Null-Bewegung darf ~0 Zeit brauchen: Floor-Schritte je Sample.
    if (
        length <= 0.0
        or v_cruise <= 0.0
        or a <= 0.0
        or not math.isfinite(v_cruise)
        or not math.isfinite(a)
    ):
        return [i * dt_floor_s for i in range(n)]

    s_ramp = v_cruise * v_cruise / (2.0 * a)  # Weg bis v_cruise erreicht ist
    if 2.0 * s_ramp <= length:  # echtes Trapez (Rampe/Halt/Bremse)
        t_ramp = v_cruise / a
        v_top = v_cruise
        cruise_len = length - 2.0 * s_ramp
        total = 2.0 * t_ramp + cruise_len / v_cruise
    else:  # Dreieck: Cruise wird nie erreicht
        s_ramp = length / 2.0
        v_top = math.sqrt(a * length)
        t_ramp = v_top / a
        total = 2.0 * t_ramp

    def t_of_s(s: float) -> float:
        if s <= s_ramp:  # Rampe
            return math.sqrt(max(0.0, 2.0 * s / a))
        if s >= length - s_ramp:  # Bremse (symmetrisch von hinten)
            return total - math.sqrt(max(0.0, 2.0 * (length - s) / a))
        return t_ramp + (s - s_ramp) / v_top  # Halt

    times = [t_of_s(s) for s in arc]
    # Strenge Monotonie sichern (Rundung/Numerik).
    for k in range(1, n):
        if times[k] <= times[k - 1]:
            times[k] = times[k - 1] + dt_floor_s
    return times


def _scale_for_limits(
    joints: list[tuple[float, ...]],
    times: list[float],
    v_max: tuple[float, ...],
    a_max: tuple[float, ...],
    *,
    dt_floor_s: float = DT_FLOOR_S,
) -> list[float]:
    """Streckt ein Segment einmal global, bis die Achs-vel/acc-Grenzen halten.

    Eine gleichförmige Zeitstreckung um ``f`` teilt jede Gelenkgeschwindigkeit
    durch ``f`` und jede Beschleunigung durch ``f²`` — die Trapezform bleibt
    erhalten (nur langsamer). ``f = max(1, r_v, √r_a)`` garantiert danach beide
    Grenzen. Nur innerhalb *eines* ruhe-zu-ruhe-Segments angewandt, damit eine
    einzelne (fast) singuläre Stelle nicht die ganze Bahn ausbremst.
    """
    if len(joints) <= 1:
        return times
    dt = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    vel = segment_velocities(joints, dt)
    rv = max(
        (abs(vel[i][j]) / v_max[j]
         for i in range(len(vel)) for j in range(len(v_max)) if v_max[j] > 0),
        default=0.0,
    )
    acc = node_accelerations(vel, dt)
    ra = max(
        (abs(acc[i][j]) / a_max[j]
         for i in range(len(acc)) for j in range(len(a_max)) if a_max[j] > 0),
        default=0.0,
    )
    f = max(1.0, rv, ra**0.5)
    if f <= 1.0:
        return times
    return [t * f for t in times]


# ---------------------------------------------------------------------------
# Ergebnis + Orchestrierung
# ---------------------------------------------------------------------------


@dataclass
class MotionResult:
    """Dichte, zeitparametrierte Bewegung (Ausgang von :func:`build_motion`).

    ``joints`` (entfaltet über die ±π-Naht) und ``times`` (streng monoton, ab 0)
    sind gleich lang — je dichtes Sample ein Eintrag. ``target_times`` gibt je
    ursprünglichem Toolpath-Ziel seinen Zeitpunkt (für die io-Schrittfunktion).
    ``warnings`` sind **verortete** Befunde ``(t_s, kind, message)`` mit dem
    ConfigWarning-``kind`` (unreachable/joint_limits/singularity).
    """

    joints: list[tuple[float, ...]]
    times: list[float]
    target_times: list[float]
    warnings: list[tuple[float, str, str]] = field(default_factory=list)


def _unwrap(raw: list[tuple[float, ...]]) -> list[tuple[float, ...]]:
    """Entfaltet auf [−π, π] normierte Gelenkwinkel zu stetigen (kürzeste Δq)."""
    if not raw:
        return []
    n_j = len(raw[0])
    out = [tuple(raw[0])]
    for i in range(1, len(raw)):
        prev = out[-1]
        out.append(tuple(prev[j] + _wrapped_delta(raw[i][j], prev[j]) for j in range(n_j)))
    return out


def _segment_move(motion: MotionParams, dest_kind: str) -> str:
    """Bewegungstyp des Segments i→i+1 aus der Art des Ziels i+1."""
    return motion.travel_move if dest_kind == "travel" else motion.print_move


def _blended_corner_targets(motion: MotionParams, kinds: list[str], n: int) -> set[int]:
    """Ziel-Indizes, deren Ecke verblendet wird (Issue #63, PROVISORISCH S1).

    Blending greift nur, wenn ein Radius gesetzt ist **und** beide an der Ecke
    angrenzenden Segmente kartesisch-linear (movel) sind — nur dort ist eine
    Verrundung im TCP-Raum wohldefiniert. movej-Travel-Ecken behalten den
    Vollstopp (bewusst außerhalb der provisorischen Scheibe). Segment ``m-1``
    (einlaufend) bestimmt sich aus ``kinds[m]``, Segment ``m`` (auslaufend) aus
    ``kinds[m+1]``.
    """
    if motion.blending_mm <= 0.0:
        return set()
    return {
        m
        for m in range(1, n - 1)
        if _segment_move(motion, kinds[m]) == MOVEL
        and _segment_move(motion, kinds[m + 1]) == MOVEL
    }


def build_motion(
    tcp_poses: list[Frame],
    kinds: list[str],
    v_cmd_mm_s: list[float],
    kin: OpwKinematics,
    tcp_inv: Frame,
    motion: MotionParams,
    *,
    singularity_warn_below: float = DEFAULT_SINGULARITY_WARN,
    config_filter: IkConfigFilter | None = None,
    dt_floor_s: float = DT_FLOOR_S,
) -> MotionResult:
    """Baut die dichte, zeitparametrierte Bewegung aus TCP-Posen + Kinematik.

    ``tcp_poses`` = TCP-in-Basis je Ziel; ``kinds`` = "print"/"travel" je Ziel;
    ``v_cmd_mm_s`` = kommandierte Bahngeschwindigkeit je Ziel; ``tcp_inv`` = Flansch
    ← TCP (invertiertes Werkzeug-Frame), um Zwischen-TCP-Posen in Flansch-Posen
    für die IK zu verketten.

    Ablauf: (1) die zu lösenden Flansch-Posen bilden — je Ziel eine, plus für jedes
    **movel**-Segment die dichten Zwischenposen der kartesischen Geraden; (2) eine
    einzige :func:`select_along_path` über *alle* diese Posen wählt bahnstetig die
    Konfiguration, die die ganzen Geraden fahrbar hält, und meldet unfahrbare/
    singuläre Zwischenstellen als Warnungen; (3) je Segment ein Trapezprofil
    (movel entlang der kartesischen Länge, movej entlang des normierten Gelenkwegs
    unter den Achsgrenzen); (4) Warnungen auf ihre interpolierte Zeit verorten.
    """
    n = len(tcp_poses)
    if n == 0:
        return MotionResult(joints=[], times=[], target_times=[])
    if n == 1:
        return _single(tcp_poses, kin, tcp_inv, singularity_warn_below, config_filter)

    v_max = kin.params.joint_velocity_limits_rad_s
    a_max = kin.params.joint_acceleration_limits_rad_s2

    # --- (1) Löse-Sequenz aus Flansch-Posen + Metadaten -------------------
    # Jeder Eintrag: (flange, tcp_pos, seg, is_target, target_index)
    flanges: list[Frame] = []
    tcp_pos_of: list[Vec3] = []
    tcp_quat_of: list[Quat] = []
    entry_seg: list[int] = []
    entry_is_target: list[bool] = []
    entry_target: list[int | None] = []
    # movel-Segmente sammeln ihre Eintrags-Indizes (für Zeit/Bogenlänge).
    seg_entries: dict[int, list[int]] = {}
    target_entry: dict[int, int] = {}

    def _add(
        flange: Frame, pos: Vec3, quat: Quat, seg: int, is_target: bool, tgt: int | None
    ) -> int:
        idx = len(flanges)
        flanges.append(flange)
        tcp_pos_of.append(pos)
        tcp_quat_of.append(quat)
        entry_seg.append(seg)
        entry_is_target.append(is_target)
        entry_target.append(tgt)
        return idx

    def _flange_of(pose: Frame) -> Frame:
        return transform.compose(pose, tcp_inv)

    # Ziel 0 als Starteintrag.
    target_entry[0] = _add(
        _flange_of(tcp_poses[0]), tcp_poses[0].pos_mm, tcp_poses[0].quat, 0, True, 0
    )

    for i in range(n - 1):
        move = _segment_move(motion, kinds[i + 1])
        seg_entries[i] = []
        if move == MOVEL:
            dense = densify_line(
                tcp_poses[i].pos_mm, tcp_poses[i].quat,
                tcp_poses[i + 1].pos_mm, tcp_poses[i + 1].quat,
                motion.sample_step_mm,
            )
            for k in range(1, len(dense)):  # Startpunkt = Ziel i schon vorhanden
                pos, quat = dense[k]
                is_tgt = k == len(dense) - 1
                idx = _add(_flange_of(Frame(pos_mm=pos, quat=quat)), pos, quat, i, is_tgt,
                           i + 1 if is_tgt else None)
                seg_entries[i].append(idx)
                if is_tgt:
                    target_entry[i + 1] = idx
        else:  # movej: nur der Endpunkt wird per IK gelöst; Zwischen = Interpolation
            idx = _add(_flange_of(tcp_poses[i + 1]), tcp_poses[i + 1].pos_mm,
                       tcp_poses[i + 1].quat, i, True, i + 1)
            seg_entries[i].append(idx)
            target_entry[i + 1] = idx

    # --- (1b) Blending: movel↔movel-Ecken geometrisch verrunden (Issue #63) ---
    # PROVISORISCH (S1): Ecken-Samples innerhalb des Verrundungsradius werden auf
    # eine quadratische Bézier-Kurve (:func:`blend_corner`) umgesetzt — die Bahn
    # kürzt die Ecke ab statt den scharfen Wegpunkt exakt anzufahren. Reine
    # Umpositionierung (Sample-Anzahl/Indizes unverändert ⇒ Warnungs-Verortung und
    # target_times bleiben gültig). ``blending_mm == 0`` überspringt alles ⇒ exakt
    # das Scheibe-4-Verhalten. Aus einem Schnappschuss gelesen, damit sich die
    # Fenster benachbarter Ecken beim Umsetzen nicht gegenseitig stören.
    blended = _blended_corner_targets(motion, kinds, n)
    if blended:
        orig_pos = list(tcp_pos_of)
        for m in blended:
            a_pt, p_pt, b_pt = tcp_poses[m - 1].pos_mm, tcp_poses[m].pos_mm, tcp_poses[m + 1].pos_mm
            e_pt, x_pt, r = blend_corner(a_pt, p_pt, b_pt, motion.blending_mm)
            if r <= 0.0:
                continue
            len_ap, len_pb = math.dist(a_pt, p_pt), math.dist(p_pt, b_pt)
            q_e = slerp(tcp_poses[m - 1].quat, tcp_poses[m].quat, (len_ap - r) / len_ap)
            q_x = slerp(tcp_poses[m].quat, tcp_poses[m + 1].quat, r / len_pb)

            def _reshape(idx: int, u: float, e=e_pt, p=p_pt, x=x_pt, qe=q_e, qx=q_x) -> None:
                pos = _bezier3(e, p, x, u)
                quat = slerp(qe, qx, u)
                tcp_pos_of[idx] = pos
                tcp_quat_of[idx] = quat
                flanges[idx] = _flange_of(Frame(pos_mm=pos, quat=quat))

            for idx in seg_entries[m - 1]:  # einlaufend: Ecke bei u=0.5, E bei u=0
                d = math.dist(orig_pos[idx], p_pt)
                if d <= r + 1e-9:
                    _reshape(idx, (r - d) / (2.0 * r))
            for idx in seg_entries[m]:  # auslaufend: Ecke bei u=0.5, X bei u=1
                d = math.dist(orig_pos[idx], p_pt)
                if d <= r + 1e-9:
                    _reshape(idx, (r + d) / (2.0 * r))

    # --- (2) Eine Konfigurationswahl über die ganze (dichte) Bahn ---------
    solution = select_along_path(
        kin, flanges,
        singularity_warn_below=singularity_warn_below,
        config_filter=config_filter,
    )
    solved: list[tuple[float, ...] | None] = [st.joints_rad for st in solution.targets]

    # Einfrieren: unfahrbare Posen halten die letzte gültige Gelenklösung
    # (sichtbar wie das eingefrorene Home, Issue #66/#56) — KEIN Rückfall auf
    # eine ausweichende Gelenkinterpolation, der die Stelle kaschieren würde.
    filled: list[tuple[float, ...]] = []
    last: tuple[float, ...] = solved[0] if solved[0] is not None else (0.0,) * kin.params.n_joints
    for j in solved:
        if j is not None:
            last = j
        filled.append(last)

    # --- (3) Dichte Gelenk-/Zeitreihe je Segment aufbauen -----------------
    flat_raw: list[tuple[float, ...]] = [filled[target_entry[0]]]
    seq_to_flat: dict[int, int] = {target_entry[0]: 0}
    # Metrik + Dynamik je Segment (für die Zeitachse nach dem Entfalten).
    seg_ranges: list[tuple[int, int, str, list[float], float, float]] = []

    for i in range(n - 1):
        start_idx = len(flat_raw) - 1  # geteiltes Start-Sample (Ziel i)
        move = _segment_move(motion, kinds[i + 1])
        if move == MOVEL:
            positions = [tcp_pos_of[target_entry[i]]] + [tcp_pos_of[e] for e in seg_entries[i]]
            arc = [0.0]
            for a in range(1, len(positions)):
                arc.append(arc[-1] + math.dist(positions[a - 1], positions[a]))
            for e in seg_entries[i]:
                flat_raw.append(filled[e])
                seq_to_flat[e] = len(flat_raw) - 1
            v = v_cmd_mm_s[i + 1]
            if motion.tcp_vel_mm_s is not None:
                v = min(v, motion.tcp_vel_mm_s)
            seg_ranges.append((start_idx, len(flat_raw) - 1, MOVEL, arc, v, motion.tcp_acc_mm_s2))
        else:  # movej: Gelenkinterpolation zwischen den gelösten Endpunkten
            q0 = filled[target_entry[i]]
            q1 = filled[target_entry[i + 1]]
            qs = densify_joints(q0, q1, motion.travel_step_rad)
            for k in range(1, len(qs)):
                flat_raw.append(qs[k])
            seq_to_flat[target_entry[i + 1]] = len(flat_raw) - 1
            metric = [k / (len(qs) - 1) for k in range(len(qs))]  # normiert [0..1]
            # Cruise/Accel im normierten Weg u so, dass kein Gelenk seine Grenze
            # reisst: u' ≤ frac·min_j v_max_j/|Δq_j|, u'' ≤ frac·min_j a_max_j/|Δq_j|.
            deltas = [abs(_wrapped_delta(q1[j], q0[j])) for j in range(len(q0))]
            u_v = _limit_ratio(v_max, deltas) * motion.travel_speed_frac
            u_a = _limit_ratio(a_max, deltas) * motion.travel_speed_frac
            seg_ranges.append((start_idx, len(flat_raw) - 1, MOVEJ, metric, u_v, u_a))

    flat = _unwrap(flat_raw)

    # --- (3b) Blending-Zeit: movel-Segmente über eine verblendete Ecke zu EINEM
    # Trapez zusammenfassen (Issue #63) — statt an der Ecke auf Ruhe zu bremsen,
    # läuft ein einziges ruhe-zu-ruhe-Profil über die verkettete Bogenlänge; die
    # Ecke liegt im Inneren ⇒ ihre Geschwindigkeit ist > 0 (kein Vollstopp), und
    # die Gesamtzeit sinkt (keine Zwischen-Bremse/-Rampe). ``blended`` leer ⇒
    # unveränderte Scheibe-4-Zeitachse.
    if blended:
        merged: list[tuple[int, int, str, list[float], float, float]] = []
        for i, rng in enumerate(seg_ranges):  # i == Segment-Index; Start = Ziel i
            prev = merged[-1] if merged else None
            if (
                prev is not None
                and i in blended
                and prev[2] == MOVEL
                and rng[2] == MOVEL
                and prev[1] == rng[0]  # geteiltes Ecken-Sample
            ):
                base = prev[3][-1]
                new_arc = prev[3] + [base + (s - rng[3][0]) for s in rng[3][1:]]
                merged[-1] = (prev[0], rng[1], MOVEL, new_arc,
                              min(prev[4], rng[4]), min(prev[5], rng[5]))
            else:
                merged.append(rng)
        seg_ranges = merged

    # --- Zeitachse: je Segment ein Trapez, Ruhe an jedem Ziel -------------
    times = [0.0] * len(flat)
    for start_idx, end_idx, _move, metric, v, a in seg_ranges:
        cum = times[start_idx]
        local = trapezoid_times(metric, v, a, dt_floor_s=dt_floor_s)
        local = _scale_for_limits(flat[start_idx : end_idx + 1], local, v_max, a_max,
                                  dt_floor_s=dt_floor_s)
        for k in range(1, len(local)):
            times[start_idx + k] = cum + local[k]

    target_times = [times[seq_to_flat[target_entry[t]]] for t in range(n)]

    # --- (4) Warnungen verorten -------------------------------------------
    warnings: list[tuple[float, str, str]] = []
    for w in solution.warnings:
        flat_idx = seq_to_flat.get(w.target_index)
        t_s = times[flat_idx] if flat_idx is not None else 0.0
        warnings.append((t_s, w.kind, w.detail))

    return MotionResult(joints=flat, times=times, target_times=target_times, warnings=warnings)


def _limit_ratio(limits: tuple[float, ...], deltas: list[float]) -> float:
    """min_j limit_j/|Δq_j| über die tatsächlich fahrenden Gelenke (∞ wenn keins)."""
    ratios = [
        limits[j] / deltas[j]
        for j in range(len(deltas))
        if deltas[j] > 1e-12 and limits[j] > 0
    ]
    return min(ratios) if ratios else math.inf


def _single(
    tcp_poses: list[Frame], kin: OpwKinematics, tcp_inv: Frame, singularity_warn_below: float,
    config_filter: IkConfigFilter | None = None,
) -> MotionResult:
    """Ein-Ziel-Sonderfall: eine Pose, Zeit 0, ggf. eine Warnung."""
    flange = transform.compose(tcp_poses[0], tcp_inv)
    sol = select_along_path(
        kin, [flange],
        singularity_warn_below=singularity_warn_below,
        config_filter=config_filter,
    )
    j = sol.targets[0].joints_rad or (0.0,) * kin.params.n_joints
    warnings = [(0.0, w.kind, w.detail) for w in sol.warnings]
    return MotionResult(joints=[j], times=[0.0], target_times=[0.0], warnings=warnings)


def motion_from_job(job: dict[str, Any]) -> MotionParams:
    """Liest die Bewegungsgruppe eines Druckjobs (``process_params.motion``).

    Wahrheitsquelle für Bewegungstyp + Dynamik (Issue #62). Nur *gesetzte* Felder
    übersteuern die :class:`MotionParams`-Defaults; fehlt der Block (Altprojekt),
    gelten die (provisorischen) Defaults → rückwärtskompatibel. Sobald der Nutzer
    einen Wert setzt, bleibt er dennoch als provisorisch markiert, bis S1 misst.
    """
    block = (job.get("process_params") or {}).get("motion") or {}
    overrides = {k: block[k] for k in MOTION_PARAM_KEYS if block.get(k) is not None}
    return replace(MotionParams(), **overrides) if overrides else MotionParams()
