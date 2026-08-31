"""Trajectory-Bau: Toolpath + Setup + Kinematik → zeitparametrierte Trajectory.

Der eine Ort, an dem Strang C zusammenläuft (Systemarchitektur §5, ADR-012/E3):

1. **Frames** — jede zeitfreie Toolpath-Pose (Düse im Wandsystem) wird über das
   Setup (`wall_to_base ∘ target`, `transform`) zur TCP-Pose in
   Roboterbasis-Koordinaten; ``tcp⁻¹`` verkettet daraus die Flansch-Pose für die IK.
2. **Bewegungsmodell** — `fgc.simulation.motion.build_motion` (Issue #62) bildet die
   reale Bewegung ab: **movel-lineare** TCP-Interpolation entlang der kartesischen
   Geraden für Druck-, **movej-Gelenkinterpolation** für Travel-Bewegungen, jede
   unter einem **Trapez-Geschwindigkeitsprofil** (Rampe/Halt/Bremse). Eine
   `select_along_path` über die ganze dichte Bahn (Issue #11) hält die Konfiguration,
   die die Geraden fahrbar lässt; unfahrbare/singuläre **Zwischen**stellen werden als
   verortete `meta.warnings` gemeldet (kein stiller Rückfall auf Gelenkinterpolation).
   Dieses Modell ersetzt die frühere stückweise-konstante `timeparam`-Logik.
3. **io-Totzeitkompensation** — bei ``compensation == simulation_shift`` wird die
   io-Zeitreihe um −t_tot verschoben (`meta.io_compensated = true`); bei
   ``native_lookahead``/``none`` bleibt sie roh (ADR-012).

Gelenkwinkel werden über die ±π-Naht **entfaltet** gespeichert, damit die
Zeitreihe der Samples ohne Sprünge stetig ist (Δq = kürzeste Winkeldifferenz).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any

from fgc.domain.models import Frame
from fgc.kinematics import IkConfigFilter
from fgc.kinematics.opw import OpwKinematics
from fgc.simulation import transform
from fgc.simulation.motion import MotionParams, build_motion
from fgc.simulation.timeparam import axis_utilization

#: Konservative Fallback-Achslimits, falls die Roboterdefinition keine trägt
#: (rad/s bzw. rad/s²) — bewusst niedrig, damit ohne echte Daten nichts
#: überzogen wird.
FALLBACK_VEL_RAD_S = (3.1415927,) * 6
FALLBACK_ACC_RAD_S2 = (10.0,) * 6

#: ConfigWarning.kind (Issue #11) → Trajectory-Schema meta.warnings.kind.
_WARN_KIND = {
    "unreachable": "reach",
    "joint_limits": "joint_limit",
    "singularity": "singularity",
    # Bahnpunkt unter der IK-Konfigurationsvorgabe unerreichbar (Issue #129, ADR-024).
    "ik_config": "ik_config",
}


@dataclass
class Trajectory:
    """Zeitparametrierte Bewegung als Zeitreihe (Schema trajectory 0.1)."""

    samples: list[dict[str, Any]]
    meta: dict[str, Any]
    #: Geometrische Ankunftszeit je Toolpath-Target (dieselbe Zeitachse wie
    #: ``samples[].t_s``). **Nicht serialisiert** — nur zur Laufzeit weitergereicht,
    #: damit der Kollisions-Befund (Issue #127) die Schicht je Sample aus dem
    #: Toolpath ableiten kann (``druckstand.layer_per_sample``). ``None`` bei
    #: Altaufrufern, die das Feld nicht setzen.
    target_times: list[float] | None = None

    def to_artifact(self, provenance: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "provenance": provenance,
            "samples": self.samples,
            "meta": self.meta,
        }


def _tcp_poses(
    targets: list[dict[str, Any]], setup: dict[str, Any]
) -> tuple[list[Frame], Frame]:
    """TCP-Poses in Basis je Target + das invertierte Werkzeug-Frame (Flansch←TCP).

    ``tcp_in_base = wall_to_base ∘ target``; die movel-Interpolation läuft entlang
    dieser TCP-Poses, die IK bekommt ``tcp_in_base ∘ tcp⁻¹`` (Flansch in Basis).
    """
    wall_to_base = transform.frame_from_dict(setup["wall_to_base"])
    tcp = transform.frame_from_dict(setup["tcp"])
    tcp_inv = transform.invert(tcp)
    poses = [
        transform.compose(wall_to_base, transform.frame_from_dict(t["frame"])) for t in targets
    ]
    return poses, tcp_inv


def build_trajectory(
    targets: list[dict[str, Any]],
    setup: dict[str, Any],
    kin: OpwKinematics,
    *,
    pose_source: str = "measured",
    motion: MotionParams | None = None,
    config_filter: IkConfigFilter | None = None,
) -> Trajectory:
    """Baut die Trajectory aus Toolpath-Targets, Setup und Kinematik.

    ``targets`` = Liste der Toolpath-Target-Dicts (Schlüssel ``frame``,
    ``v_mm_s``, ``io``, ``kind`` …). ``setup`` = geladenes Setup-Artefakt-Dict.

    ``motion`` (Issue #62) steuert das **Bewegungsmodell** (Bewegungstyp + vel/acc,
    aus ``process_params.motion``); ohne Angabe gelten die provisorischen
    :class:`~fgc.simulation.motion.MotionParams`-Defaults (rückwärtskompatibel,
    z. B. der CLI-Pfad ``fgc simulate`` ohne Druckjob).

    ``config_filter`` (Issue #129, ADR-024) reicht die wählbare IK-Konfiguration
    an die :func:`select_along_path` durch: gesetzte Achsen (Schulter/Ellbogen/
    Handgelenk) filtern die Lösungszweige **hart**; unter der Vorgabe unerreichbare
    Bahnpunkte werden als ``ik_config``-Warnung in ``meta.warnings`` gemeldet (kein
    Gate). ``None``/``auto`` ⇒ bit-identische Bahnwahl wie ohne den Parameter.

    ``pose_source`` (Issue #26) vermerkt die **Lagequelle** der Wand↔Basis-
    Transformation in ``meta.pose_source``: ``"measured"`` (Default) für das
    gemessene Setup (Antast-Verfahren, ADR-006) — Voraussetzung des echten
    Drucks; ``"planned"`` für ein aus der geplanten Platzierung gebautes Lage-
    Frame — nur für die Simulation zulässig (Design-Log 2026-07-04). Der Wert
    ändert die Rechnung nicht, nur den Metadaten-Stempel.
    """
    if not targets:
        raise ValueError("Toolpath ohne Targets — keine Trajectory baubar")

    motion = motion or MotionParams()
    v_max = kin.params.joint_velocity_limits_rad_s or FALLBACK_VEL_RAD_S

    # 1) TCP-Poses in Basis, 2)+3) Bewegungsmodell (movel/movej + Trapez, #62).
    tcp_poses, tcp_inv = _tcp_poses(targets, setup)
    kinds = [str(t.get("kind", "print")) for t in targets]
    v_cmd = [float(t["v_mm_s"]) for t in targets]
    result = build_motion(
        tcp_poses, kinds, v_cmd, kin, tcp_inv, motion, config_filter=config_filter
    )

    joints = result.joints
    times = result.times
    target_times = result.target_times

    # 4) io-Zeitreihe (+ Totzeitkompensation, ADR-012). Die io-Werte sind je
    #    ursprünglichem Target definiert (Schrittfunktion über die Target-Zeiten);
    #    jedes dichte Sample erbt den io-Zustand seines Segments.
    channels = sorted({ch for t in targets for ch in t.get("io", {})})
    io_geo = [dict(t.get("io", {})) for t in targets]
    deadtime = setup["deadtime"]
    shift = deadtime.get("compensation") == "simulation_shift"
    t_tot = float(deadtime.get("t_tot_s", 0.0))

    def io_step(tau: float) -> dict[str, float]:
        # Schrittfunktion über die geometrische Target-Zeitachse; nach dem Bahnende
        # (Ausdruck fertig) sind alle Kanäle aus (0.0) — der Vorlauf schaltet
        # so t_tot vor Schluss ab.
        if tau > target_times[-1] + 1e-12:
            return {ch: 0.0 for ch in channels}
        k = max(0, bisect_right(target_times, tau) - 1)
        return {ch: float(io_geo[k].get(ch, 0.0)) for ch in channels}

    samples: list[dict[str, Any]] = []
    for i in range(len(joints)):
        io_i = io_step(times[i] + t_tot) if shift else io_step(times[i])
        samples.append(
            {
                "t_s": round(times[i], 6),
                "joints_rad": [round(q, 9) for q in joints[i]],
                "io": {ch: round(v, 6) for ch, v in io_i.items()},
            }
        )

    # Feste Roboterbasis im Wandsystem (base_in_wall = invert(wall_to_base)) als
    # Replay-Anker (ADR-007-Klarstellung): der Viewer verankert den Arm damit fix
    # an der geplanten Lage, statt die Basis pro Frame ans Ziel zu schleifen. Über
    # alle Targets konstant — deckt beide Produktionspfade (measured/planned) ab.
    base_in_wall = transform.invert(transform.frame_from_dict(setup["wall_to_base"]))

    meta: dict[str, Any] = {
        "duration_s": round(times[-1], 6),
        "io_compensated": bool(shift),
        "pose_source": pose_source,
        "axis_utilization": [round(u, 6) for u in axis_utilization(joints, times, v_max)],
        "base_frame": {
            "pos_mm": [round(v, 6) for v in base_in_wall.pos_mm],
            "quat": [round(v, 9) for v in base_in_wall.quat],
        },
    }
    warnings = [
        {
            "t_s": round(t_s, 6),
            "kind": _WARN_KIND.get(kind, "other"),
            "message": message,
        }
        for (t_s, kind, message) in result.warnings
    ]
    if warnings:
        meta["warnings"] = warnings

    return Trajectory(
        samples=samples, meta=meta, target_times=[round(t, 6) for t in target_times]
    )
