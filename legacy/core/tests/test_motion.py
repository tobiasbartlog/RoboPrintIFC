"""Bewegungsmodell `fgc.simulation.motion` (Issue #62, Scheibe 4 von PRD #57).

Deckt die Acceptance-Kriterien ab:
- reines, isoliert testbares Modul (Trapezprofil, movel-Sampling, select_along_path
  über die dichte Bahn) — hier direkt auf synthetischen Posen geprüft, ohne I/O.
- Trapez-Geschwindigkeits-/-Beschleunigungsgrenzen aus der Bahn nachgerechnet.
- movel-Segmente kartesisch **linear** (Zwischen-TCP auf der Geraden, Toleranz).
- Zeitreihe streng monoton.
- Singularität/Reichweitengrenze **mitten in einer movel-Geraden** ⇒ verortete
  Warnung, KEIN stiller Rückfall auf Gelenkinterpolation.
- Bewegungstyp/vel/acc aus `process_params.motion`; Provisorik markiert.
"""

from __future__ import annotations

import math

import pytest

from fgc.domain.models import Frame
from fgc.domain.orientation import NOZZLE_DOWN_QUAT
from fgc.kinematics import OpwKinematics
from fgc.simulation import build_trajectory, transform
from fgc.simulation.motion import (
    MOTION_PARAM_KEYS,
    MotionParams,
    blend_corner,
    build_motion,
    densify_line,
    motion_from_job,
    slerp,
    trapezoid_times,
)
from fgc.simulation.timeparam import node_accelerations, segment_velocities

RATIO_TOL = 1e-6

PROVENANCE = {"source": "test", "created": "2026-07-06T10:00:00Z", "git_commit": "0000000"}
IDENTITY = {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}


@pytest.fixture(scope="module")
def kin() -> OpwKinematics:
    return OpwKinematics.from_robot("doosan_m1013")


def _setup(compensation: str = "none", t_tot_s: float = 0.0) -> dict:
    return {
        "schema_version": "0.1",
        "provenance": PROVENANCE,
        "robot": "doosan_m1013",
        "wall_to_base": IDENTITY,
        "tcp": IDENTITY,
        "io_channels": {
            "pump_a": {"kind": "analog_voltage", "index": 0, "physical_range": [0, 10]},
        },
        "deadtime": {"t_tot_s": t_tot_s, "compensation": compensation, "provisional": True},
    }


def _print_target(pos, quat=NOZZLE_DOWN_QUAT, v_mm_s=100.0, io_on=False, sid="S"):
    return {
        "frame": {"pos_mm": list(pos), "quat": list(quat)},
        "v_mm_s": v_mm_s,
        "io": {"pump_a": 1.0 if io_on else 0.0},
        "kind": "print",
        "layer": 0,
        "segment_id": sid,
    }


# ---------------------------------------------------------------------------
# Reine Bausteine: Trapezprofil
# ---------------------------------------------------------------------------


def test_trapezoid_rest_to_rest_reaches_cruise():
    """Langes Segment: echtes Trapez — Rampe auf v, Halt bei v, Bremse auf 0."""
    v, a, length = 100.0, 200.0, 1000.0
    arc = [i * length / 50 for i in range(51)]
    t = trapezoid_times(arc, v, a)
    assert t[0] == 0.0
    assert all(b > x for x, b in zip(t, t[1:], strict=False))  # streng monoton
    # Geschwindigkeit aus der Bahn (ds/dt) ueberschreitet nie v (+Toleranz) …
    speeds = [(arc[i + 1] - arc[i]) / (t[i + 1] - t[i]) for i in range(len(t) - 1)]
    assert max(speeds) <= v * (1 + 1e-6)
    # … erreicht sie aber (Halt-Phase existiert) …
    assert max(speeds) == pytest.approx(v, rel=1e-3)
    # … und beginnt/endet in Ruhe (Rampe/Bremse).
    assert speeds[0] < v * 0.5
    assert speeds[-1] < v * 0.5


def test_trapezoid_acceleration_bounded_by_setting():
    """Die Beschleunigung aus der Bahn bleibt unter der eingestellten (mit Toleranz)."""
    v, a, length = 100.0, 200.0, 1000.0
    arc = [i * length / 200 for i in range(201)]
    t = trapezoid_times(arc, v, a)
    speeds = [(arc[i + 1] - arc[i]) / (t[i + 1] - t[i]) for i in range(len(t) - 1)]
    mids = [(t[i + 1] + t[i]) / 2 for i in range(len(t) - 1)]
    accels = [(speeds[i + 1] - speeds[i]) / (mids[i + 1] - mids[i]) for i in range(len(speeds) - 1)]
    assert max(abs(x) for x in accels) <= a * (1 + 1e-3)


def test_trapezoid_triangle_when_too_short():
    """Kurzes Segment: Cruise wird nie erreicht (Spitze √(a·L) < v)."""
    v, a, length = 100.0, 200.0, 10.0  # 2·s_ramp = v²/a = 50 > 10 → Dreieck
    arc = [i * length / 40 for i in range(41)]
    t = trapezoid_times(arc, v, a)
    speeds = [(arc[i + 1] - arc[i]) / (t[i + 1] - t[i]) for i in range(len(t) - 1)]
    assert max(speeds) < v
    assert max(speeds) == pytest.approx(math.sqrt(a * length), rel=5e-2)


def test_trapezoid_zero_length_stays_monotonic():
    """Null-Strecke (identische Ziele) bleibt streng monoton (dt_floor)."""
    t = trapezoid_times([0.0, 0.0, 0.0], 100.0, 200.0)
    assert all(b > x for x, b in zip(t, t[1:], strict=False))


def test_trapezoid_nonfinite_dynamics_yield_no_nan():
    """movej ohne Gelenkbewegung ⇒ `_limit_ratio` = inf ⇒ vel/acc = inf.

    Regression zu #62: inf/inf erzeugte NaN-Zeiten, die als literales `NaN` in die
    trajectory.json geschrieben wurden (ungültiges JSON) — der Viewer scheiterte
    beim Laden. Nicht-endliche Dynamik muss auf endliche, streng monotone Floor-
    Zeiten zurückfallen (Null-Bewegung ~ 0 Zeit), niemals NaN.
    """
    for v, a in ((math.inf, math.inf), (math.inf, 100.0), (100.0, math.inf)):
        t = trapezoid_times([0.0, 1.0], v, a)
        assert all(math.isfinite(x) for x in t), (v, a, t)
        assert t[1] > t[0]


# ---------------------------------------------------------------------------
# Reine Bausteine: slerp / densify_line
# ---------------------------------------------------------------------------


def test_slerp_endpoints_and_midpoint_unit():
    q0 = (1.0, 0.0, 0.0, 0.0)
    q1 = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))  # 90° um z
    assert slerp(q0, q1, 0.0) == pytest.approx(q0)
    mid = slerp(q0, q1, 0.5)
    assert sum(c * c for c in mid) == pytest.approx(1.0)  # Einheitsquaternion
    # 45° um z: w = cos(22.5°)
    assert mid[0] == pytest.approx(math.cos(math.pi / 8))


def test_densify_line_points_on_straight_line():
    p0, p1 = (0.0, 0.0, 0.0), (300.0, 0.0, 0.0)
    dense = densify_line(p0, NOZZLE_DOWN_QUAT, p1, NOZZLE_DOWN_QUAT, 20.0)
    assert len(dense) >= 15  # 300/20 = 15 Teilstuecke → 16 Punkte
    for pos, _quat in dense:
        assert pos[1] == pytest.approx(0.0) and pos[2] == pytest.approx(0.0)
    assert dense[0][0] == pytest.approx(p0)
    assert dense[-1][0] == pytest.approx(p1)


# ---------------------------------------------------------------------------
# Kriterium: v/a-Grenzen aus der (Gelenk-)Bahn + strenge Monotonie
# ---------------------------------------------------------------------------


def _smooth_print_targets(kin: OpwKinematics, n: int = 12) -> list[dict]:
    """Print-Targets aus FK einer glatten, nicht-singulären Gelenkbahn (erreichbar)."""
    q0 = [0.1, -0.5, 0.8, 0.2, 0.9, -0.3]
    step = [0.03, 0.02, -0.02, 0.01, 0.02, 0.015]
    targets = []
    for i in range(n):
        q = [q0[j] + i * step[j] for j in range(6)]
        fr = kin.forward(q)
        targets.append(_print_target(fr.pos_mm, fr.quat, sid=f"S{i:03d}"))
    return targets


def test_time_series_strictly_monotonic(kin):
    traj = build_trajectory(_smooth_print_targets(kin), _setup(), kin)
    ts = [s["t_s"] for s in traj.samples]
    assert all(b > a for a, b in zip(ts, ts[1:], strict=False))


def test_joint_velocity_and_acceleration_limits_respected(kin):
    """Nachgerechnet aus der dichten Bahn: kein Gelenk reisst seine v/a-Grenze."""
    traj = build_trajectory(_smooth_print_targets(kin), _setup(), kin)
    joints = [tuple(s["joints_rad"]) for s in traj.samples]
    ts = [s["t_s"] for s in traj.samples]
    dt = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    vel = segment_velocities(joints, dt)
    v_max = kin.params.joint_velocity_limits_rad_s
    a_max = kin.params.joint_acceleration_limits_rad_s2
    for seg in vel:
        for j in range(6):
            assert abs(seg[j]) <= v_max[j] * (1 + RATIO_TOL)
    for node in node_accelerations(vel, dt):
        for j in range(6):
            assert abs(node[j]) <= a_max[j] * (1 + RATIO_TOL)


# ---------------------------------------------------------------------------
# Kriterium: movel-Segmente sind kartesisch linear (Zwischen-TCP auf der Geraden)
# ---------------------------------------------------------------------------


def test_movel_intermediate_tcp_on_straight_line(kin):
    """Zwischen-TCP einer movel-Geraden liegt (FK der Gelenke) auf der Geraden.

    Zwei reichlich getrennte, gut konditionierte Print-Ziele; die verdichteten
    Zwischenposen müssen (über IK→FK) auf der kartesischen Verbindungsgeraden
    liegen — Abweichung unter enger Toleranz (Identitäts-Setup ⇒ Flansch = TCP).
    """
    a = kin.forward([0.2, -0.6, 0.9, 0.1, 0.8, -0.2])
    b = kin.forward([0.5, -0.4, 0.7, 0.1, 0.9, -0.1])
    targets = [_print_target(a.pos_mm, a.quat, sid="A"),
               _print_target(b.pos_mm, b.quat, sid="B")]
    traj = build_trajectory(targets, _setup(), kin,
                            motion=MotionParams(sample_step_mm=15.0))
    # Rekonstruiere die TCP-Position je Sample aus den Gelenken (Setup = Identität).
    p0, p1 = a.pos_mm, b.pos_mm
    seg = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    seg_len = math.dist(p0, p1)
    assert seg_len > 100.0  # echte Gerade, mehrere Zwischenposen
    max_dev = 0.0
    for s in traj.samples:
        pos = kin.forward(s["joints_rad"]).pos_mm
        # senkrechter Abstand Punkt→Gerade
        w = (pos[0] - p0[0], pos[1] - p0[1], pos[2] - p0[2])
        cross = (
            w[1] * seg[2] - w[2] * seg[1],
            w[2] * seg[0] - w[0] * seg[2],
            w[0] * seg[1] - w[1] * seg[0],
        )
        dev = math.sqrt(sum(c * c for c in cross)) / seg_len
        max_dev = max(max_dev, dev)
    assert max_dev < 1e-3  # mm — Zwischen-TCP auf der Geraden


# ---------------------------------------------------------------------------
# Kernkriterium: Singularität/Reichweite MITTEN in der movel-Geraden ⇒ verortete
# Warnung, KEIN stiller Rückfall auf Gelenkinterpolation.
# ---------------------------------------------------------------------------


def test_midline_singularity_is_located_not_masked(kin):
    """Endpunkte fahrbar, Geraden-Mitte über der Schulterachse unfahrbar.

    Die grobe Prüfung (nur Endpunkte) bliebe still; das dichte movel-Modell
    verortet die unfahrbare Zwischenstelle als Warnung *innerhalb* des Segments.
    """
    a = (600.0, 0.0, 800.0)
    b = (-600.0, 0.0, 800.0)  # Verbindungsgerade läuft durch (0,0,800) = Schulterachse

    # Kontrolle: nur die Endpunkte (grobe Prüfung) erzeugen KEINE Warnung.
    coarse = build_trajectory(
        [_print_target(a, sid="A"), _print_target(b, sid="B")],
        _setup(), kin, motion=MotionParams(sample_step_mm=10_000.0),  # keine Verdichtung
    )
    assert "warnings" not in coarse.meta

    # Dichtes movel-Modell: verortete Warnung mitten im Segment.
    fine = build_trajectory(
        [_print_target(a, sid="A"), _print_target(b, sid="B")],
        _setup(), kin, motion=MotionParams(sample_step_mm=30.0),
    )
    assert "warnings" in fine.meta
    duration = fine.meta["duration_s"]
    mid_warns = [w for w in fine.meta["warnings"] if 0.0 < w["t_s"] < duration]
    assert mid_warns, "erwartet: verortete Warnung mitten in der movel-Geraden"
    assert all(w["kind"] in ("reach", "singularity", "joint_limit") for w in fine.meta["warnings"])


def test_no_silent_joint_fallback_keeps_line(kin):
    """Kein Rückfall auf Gelenkinterpolation: die Gerade bleibt bestehen + Warnung.

    Ein Gelenk-Ausweichbogen um die Singularität herum wäre stumm (keine Warnung)
    und würde die TCP-Bahn krümmen. Wir prüfen das Gegenteil: die Warnung ist da
    UND es bleibt eine Einfrier-Stelle (zwei aufeinanderfolgende Samples mit
    identischen Gelenken — die letzte gültige Lösung wird gehalten).
    """
    a = (600.0, 0.0, 800.0)
    b = (-600.0, 0.0, 800.0)
    traj = build_trajectory(
        [_print_target(a, sid="A"), _print_target(b, sid="B")],
        _setup(), kin, motion=MotionParams(sample_step_mm=30.0),
    )
    assert "warnings" in traj.meta  # Befund gemeldet, nicht kaschiert
    joints = [tuple(s["joints_rad"]) for s in traj.samples]
    frozen = any(
        all(abs(joints[i][j] - joints[i + 1][j]) < 1e-9 for j in range(6))
        for i in range(len(joints) - 1)
    )
    assert frozen, "unfahrbare Zwischenstelle friert ein (kein glatter Ausweichbogen)"


# ---------------------------------------------------------------------------
# Kriterium: movej-Travel = Gelenkinterpolation
# ---------------------------------------------------------------------------


def test_travel_uses_joint_interpolation(kin):
    """Ein Travel-Segment interpoliert im Gelenkraum (monotone, dichte Bahn)."""
    qa = [0.2, -0.6, 0.9, 0.1, 0.8, -0.2]
    qb = [0.9, -0.3, 0.6, 0.4, 0.6, 0.3]
    a = kin.forward(qa)
    b = kin.forward(qb)
    targets = [
        _print_target(a.pos_mm, a.quat, sid="start"),
        {**_print_target(b.pos_mm, b.quat, sid="travel"), "kind": "travel",
         "io": {"pump_a": 0.0}, "v_mm_s": 250.0},
    ]
    traj = build_trajectory(targets, _setup(), kin)
    ts = [s["t_s"] for s in traj.samples]
    assert all(y > x for x, y in zip(ts, ts[1:], strict=False))  # streng monoton
    assert len(traj.samples) > 2  # Gelenk-Zwischensamples vorhanden
    # Jedes Gelenk läuft monoton von qa nach qb (lineare Gelenkinterpolation).
    joints = [s["joints_rad"] for s in traj.samples]
    for j in range(6):
        col = [q[j] for q in joints]
        assert col[0] == pytest.approx(qa[j], abs=1e-6)
        assert col[-1] == pytest.approx(qb[j], abs=1e-6)


# ---------------------------------------------------------------------------
# Kriterium: Bewegungstyp/vel/acc aus process_params.motion; Provisorik markiert
# ---------------------------------------------------------------------------


def test_motion_from_job_defaults_when_absent():
    """Fehlt der Block (Altprojekt), gelten die provisorischen Defaults."""
    assert motion_from_job({}) == MotionParams()
    assert motion_from_job({"process_params": {}}) == MotionParams()
    mp = motion_from_job({"process_params": {"motion": {}}})
    assert mp == MotionParams()
    assert mp.provisional is True  # S1-Provisorik markiert


def test_motion_from_job_overrides_only_set_fields():
    job = {"process_params": {"motion": {"tcp_acc_mm_s2": 500.0, "print_move": "movej"}}}
    mp = motion_from_job(job)
    assert mp.tcp_acc_mm_s2 == 500.0
    assert mp.print_move == "movej"
    assert mp.sample_step_mm == MotionParams().sample_step_mm  # ungesetzt = Default
    assert mp.provisional is True
    # alle Rail-Schluessel sind bekannte MotionParams-Felder
    for key in MOTION_PARAM_KEYS:
        assert hasattr(mp, key)


def test_motion_acc_setting_changes_duration(kin):
    """Eine kleinere eingestellte Beschleunigung ergibt eine längere Bahn."""
    targets = _smooth_print_targets(kin)
    fast = build_trajectory(targets, _setup(), kin, motion=MotionParams(tcp_acc_mm_s2=800.0))
    slow = build_trajectory(targets, _setup(), kin, motion=MotionParams(tcp_acc_mm_s2=80.0))
    assert slow.meta["duration_s"] > fast.meta["duration_s"]


def test_print_move_as_movej_skips_line_densification(kin):
    """print_move=movej fährt Druck-Ziele im Gelenkraum (Bewegungstyp greift)."""
    a = (600.0, 0.0, 800.0)
    b = (-600.0, 0.0, 800.0)
    targets = [_print_target(a, sid="A"), _print_target(b, sid="B")]
    # movej weicht der Geraden-Mitte im Gelenkraum aus → keine reach-Warnung.
    traj = build_trajectory(targets, _setup(), kin, motion=MotionParams(print_move="movej"))
    assert "warnings" not in traj.meta


# ---------------------------------------------------------------------------
# build_motion direkt (isoliert, ohne setup-Dict)
# ---------------------------------------------------------------------------


def test_build_motion_is_callable_without_io(kin):
    """Das Modul ist isoliert nutzbar: reine Posen + Kinematik rein, Bahn raus."""
    poses = [kin.forward([0.1, -0.5, 0.8, 0.2, 0.9, -0.3 + 0.03 * i]) for i in range(5)]
    tcp_inv = transform.invert(Frame(pos_mm=(0.0, 0.0, 0.0)))
    res = build_motion(poses, ["print"] * 5, [100.0] * 5, kin, tcp_inv, MotionParams())
    assert len(res.joints) == len(res.times) >= 5
    assert res.times[0] == 0.0
    assert all(b > a for a, b in zip(res.times, res.times[1:], strict=False))
    assert len(res.target_times) == 5


# ---------------------------------------------------------------------------
# Scheibe 4b: Blending (Ecken-Verrundung + Geschwindigkeitserhalt, Issue #63)
# ---------------------------------------------------------------------------

# L-Ecke im TCP-Raum: A→P entlang +y, P→B entlang −x (90°), alle erreichbar,
# nozzle-down. Segmentlänge je 150 mm ⇒ Blending-Radius bis 75 mm zulässig.
_CORNER_A = (600.0, -150.0, 700.0)
_CORNER_P = (600.0, 0.0, 700.0)
_CORNER_B = (450.0, 0.0, 700.0)


def _corner_targets() -> list[dict]:
    return [
        _print_target(_CORNER_A, sid="A"),
        _print_target(_CORNER_P, sid="P"),
        _print_target(_CORNER_B, sid="B"),
    ]


def _corner_poses() -> list[Frame]:
    return [Frame(pos_mm=p, quat=NOZZLE_DOWN_QUAT) for p in (_CORNER_A, _CORNER_P, _CORNER_B)]


def test_blend_corner_entry_exit_and_clamp():
    """Pure Geometrie: E liegt r vor, X r nach der Ecke; Radius auf |seg|/2 gedeckelt."""
    e, x, r = blend_corner(_CORNER_A, _CORNER_P, _CORNER_B, 60.0)
    assert r == pytest.approx(60.0)
    assert e == pytest.approx((600.0, -60.0, 700.0))  # 60 mm vor P Richtung A
    assert x == pytest.approx((540.0, 0.0, 700.0))  # 60 mm nach P Richtung B
    # Überradius wird auf die halbe (kürzere) Segmentlänge gedeckelt.
    _e2, _x2, r2 = blend_corner(_CORNER_A, _CORNER_P, _CORNER_B, 500.0)
    assert r2 == pytest.approx(75.0)
    # Kein Radius / entartetes Segment ⇒ keine Verrundung.
    assert blend_corner(_CORNER_A, _CORNER_P, _CORNER_B, 0.0) == (_CORNER_P, _CORNER_P, 0.0)


def test_blending_rounds_corner_geometry(kin):
    """Kriterium (a): verblendete Ecke ist geometrisch verrundet (Ecke abgekürzt).

    Ohne Blending fährt die Bahn den scharfen Wegpunkt P exakt an; mit Blending
    kürzt sie die Ecke ab — kein Sample erreicht P (Bézier-Verrundung, Issue #63).
    """
    sharp = build_trajectory(_corner_targets(), _setup(), kin,
                             motion=MotionParams(sample_step_mm=10.0))
    rounded = build_trajectory(_corner_targets(), _setup(), kin,
                               motion=MotionParams(sample_step_mm=10.0, blending_mm=60.0))

    def min_dist_to_corner(traj) -> float:
        return min(math.dist(kin.forward(s["joints_rad"]).pos_mm, _CORNER_P)
                   for s in traj.samples)

    assert min_dist_to_corner(sharp) < 1.0  # scharfe Ecke wird exakt erreicht
    assert min_dist_to_corner(rounded) > 10.0  # verblendet: Ecke deutlich abgekürzt


def test_blending_keeps_corner_velocity_and_shortens_time(kin):
    """Kriterium (b): am verblendeten Wegpunkt bleibt v > 0 (kein Vollstopp), Zeit sinkt."""
    tcp_inv = transform.invert(Frame(pos_mm=(0.0, 0.0, 0.0)))
    poses, kinds, v = _corner_poses(), ["print"] * 3, [100.0] * 3
    sharp = build_motion(poses, kinds, v, kin, tcp_inv, MotionParams(sample_step_mm=10.0))
    blend = build_motion(poses, kinds, v, kin, tcp_inv,
                         MotionParams(sample_step_mm=10.0, blending_mm=60.0))

    def corner_speed(res) -> float:
        t = res.target_times[1]  # mittlere Ecke (Ziel 1)
        i = min(range(len(res.times)), key=lambda k: abs(res.times[k] - t))
        i0, i1 = max(0, i - 1), min(len(res.times) - 1, i + 1)
        p0 = kin.forward(res.joints[i0]).pos_mm
        p1 = kin.forward(res.joints[i1]).pos_mm
        return math.dist(p0, p1) / (res.times[i1] - res.times[i0])

    v_blend, v_sharp = corner_speed(blend), corner_speed(sharp)
    assert v_blend > 90.0  # ~Cruise gehalten → kein Vollstopp
    assert v_sharp < 0.5 * v_blend  # Scheibe 4 bremst an der Ecke deutlich ab
    assert blend.times[-1] < sharp.times[-1]  # Gesamtzeit sinkt durch Blending


def test_blending_zero_matches_full_stop_scheibe4(kin):
    """Rückwärtskompatibilität: blending_mm==0 ⇒ exakt das Scheibe-4-Verhalten.

    Bit-genau identische Gelenk-/Zeitreihe wie ohne Blending-Feld, und die Ecke
    ist ein echter Vollstopp (Geschwindigkeit dort ~0).
    """
    base = build_trajectory(_corner_targets(), _setup(), kin,
                            motion=MotionParams(sample_step_mm=10.0))
    zero = build_trajectory(_corner_targets(), _setup(), kin,
                            motion=MotionParams(sample_step_mm=10.0, blending_mm=0.0))
    assert [s["joints_rad"] for s in base.samples] == [s["joints_rad"] for s in zero.samples]
    assert [s["t_s"] for s in base.samples] == [s["t_s"] for s in zero.samples]
    # Vollstopp an der Ecke: das Sample bei Ziel P hält kurz an (einseitige v ~0).
    tcp_inv = transform.invert(Frame(pos_mm=(0.0, 0.0, 0.0)))
    res = build_motion(_corner_poses(), ["print"] * 3, [100.0] * 3, kin, tcp_inv,
                       MotionParams(sample_step_mm=10.0))
    t = res.target_times[1]
    i = min(range(len(res.times)), key=lambda k: abs(res.times[k] - t))
    lead = math.dist(kin.forward(res.joints[i]).pos_mm, kin.forward(res.joints[i - 1]).pos_mm)
    v_in = lead / (res.times[i] - res.times[i - 1])
    assert v_in < 40.0  # an der scharfen Ecke ist die Anfahrt gebremst (kein Cruise)
