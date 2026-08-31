"""Roboterdefinitionen aus robots/<name>.json (ADR-002, P5).

Für E1-Stufe 1 braucht es nur den groben Arbeitsraum; die Kinematikparameter
(DH/OPW) kommen mit M1 in dieselbe Datei (Spike S3, ADR-002). Einheiten strikt
nach ADR-006: mm, Radiant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fgc.paths import ROBOTS_DIR


@dataclass(frozen=True)
class Kinematics:
    """Geometrieparameter eines 6R-Arms für FK/IK (Spike S3, ADR-002, ADR-006).

    Reine Daten ohne NumPy: Der Kinematik-Kern (`fgc.kinematics`) baut daraus den
    Solver. `solver` benennt die portierte Solverfamilie (`"opw"` = Ortho-Parallel-
    Basis + Spherical Wrist, aus visose/Robots `SphericalWristKinematics`).
    Standard-DH je Achse: `a_mm`, `d_mm` (Millimeter), `alpha_rad` (Radiant);
    `joint_limits_rad` je Achse als (min, max)-Paar in Radiant.

    `joint_velocity_limits_rad_s` / `joint_acceleration_limits_rad_s2` sind die
    kinematischen Achslimits, die die Simulation (`fgc.simulation`, Issue #12) zur
    Zeitparametrierung braucht; optional (None, wenn die Roboterdefinition sie
    nicht trägt) — die Simulation setzt dann konservative Fallbacks.
    """

    solver: str
    a_mm: tuple[float, ...]
    d_mm: tuple[float, ...]
    alpha_rad: tuple[float, ...]
    joint_limits_rad: tuple[tuple[float, float], ...]
    joint_velocity_limits_rad_s: tuple[float, ...] | None = None
    joint_acceleration_limits_rad_s2: tuple[float, ...] | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Kinematics:
        a = tuple(float(x) for x in raw["a_mm"])
        d = tuple(float(x) for x in raw["d_mm"])
        alpha = tuple(float(x) for x in raw["alpha_rad"])
        limits = tuple((float(lo), float(hi)) for lo, hi in raw["joint_limits_rad"])
        n = len(a)
        if not (len(d) == len(alpha) == len(limits) == n):
            raise ValueError(
                "Kinematik-Parameter uneinheitlich lang: "
                f"a={len(a)}, d={len(d)}, alpha={len(alpha)}, limits={len(limits)}"
            )
        vel = raw.get("joint_velocity_limits_rad_s")
        acc = raw.get("joint_acceleration_limits_rad_s2")
        vel_t = tuple(float(x) for x in vel) if vel is not None else None
        acc_t = tuple(float(x) for x in acc) if acc is not None else None
        for label, seq in (("joint_velocity_limits_rad_s", vel_t),
                           ("joint_acceleration_limits_rad_s2", acc_t)):
            if seq is not None and len(seq) != n:
                raise ValueError(
                    f"{label} hat {len(seq)} Einträge, erwartet {n} (je Achse einen)"
                )
        return cls(
            solver=str(raw["solver"]),
            a_mm=a,
            d_mm=d,
            alpha_rad=alpha,
            joint_limits_rad=limits,
            joint_velocity_limits_rad_s=vel_t,
            joint_acceleration_limits_rad_s2=acc_t,
        )

    @property
    def n_joints(self) -> int:
        return len(self.a_mm)


@dataclass(frozen=True)
class RobotDef:
    name: str
    reach_mm: float
    max_print_height_mm: float
    max_print_length_mm: float
    workspace_provisional: bool = True
    kinematics: Kinematics | None = None
    payload_kg: float | None = None  # Traglast in kg (Issue #21, statischer Payload-Check)
    #: Basis-Bohrbild fuer die Montage auf einer Workstation (Issue #78, ADR-006):
    #: {hole_count, hole_diameter_mm, hole_positions_mm, ...} — rohe schema-valide
    #: Daten. None = kein Bohrbild hinterlegt. Read-only (Roboter sind read-only im
    #: #69-Scope); konsumiert von fgc.geometry.holes.match_base_mount.
    base_mount: dict[str, Any] | None = None

    @classmethod
    def load(cls, name: str, robots_dir: Path | None = None) -> RobotDef:
        from fgc.domain import validate  # lokaler Import: kein Zirkel (Issue #73)

        path = (robots_dir or ROBOTS_DIR) / f"{name}.json"
        if not path.exists():
            available = sorted(p.stem for p in (robots_dir or ROBOTS_DIR).glob("*.json"))
            raise FileNotFoundError(
                f"Roboterdefinition {path.name!r} fehlt in robots/ — vorhanden: {available}"
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        validate(raw, "robot")  # Schema-Validierung (Issue #73); wirft jsonschema.ValidationError
        ws = raw["workspace"]
        kin = raw.get("kinematics")
        return cls(
            name=raw["name"],
            reach_mm=raw["reach_mm"],
            max_print_height_mm=ws["max_print_height_mm"],
            max_print_length_mm=ws["max_print_length_mm"],
            workspace_provisional=ws.get("provisional", True),
            kinematics=Kinematics.from_dict(kin) if kin is not None else None,
            payload_kg=float(raw["payload_kg"]) if "payload_kg" in raw else None,
            base_mount=raw.get("base_mount"),
        )
