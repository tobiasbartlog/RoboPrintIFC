"""OPW-Kinematik (Ortho-Parallel-Basis + Spherical Wrist) für den Doosan M1013.

Portierung des analytischen Solvers aus visose/Robots (MIT), Klasse
``SphericalWristKinematics`` — der Solver, den Robots laut Quellcode (RobotArm
``RobotDoosan.CreateSolver`` → ``SphericalWristKinematics``) tatsächlich für den
M1013 verwendet. Robots' OPW-Solver ist seinerseits aus
``Jmeyer1292/opw_kinematics`` (Brandstötter u. a.) adaptiert. Der in ADR-002/S3
zunächst vermutete Offset-Wrist-Solver (``OffsetWristKinematics``) wird in Robots
nur für Universal Robots benutzt — Befund im Spike-Protokoll S3. Attribution: NOTICE.

Einheiten strikt nach ADR-006: Position in Millimeter, Winkel in Radiant,
Orientierung als Einheitsquaternion ``[w, x, y, z]`` (`fgc.domain.models.Frame`).

FK und IK sind ein zueinander konsistentes Paar: ``inverse(forward(q))`` enthält
für jede erreichbare Pose eine Lösung, deren ``forward`` die Ausgangspose exakt
reproduziert (1000-Posen-Orakel, ADR-009a).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from fgc.domain.models import Frame
from fgc.domain.robot import Kinematics, RobotDef

# Umrechnung Robots' OPW-Kanonik → Roboter-Gelenkkonvention (hartkodiert im
# Robots-Solver: SphericalWristKinematics._start / ._signs).
_START = (0.0, math.pi / 2.0, math.pi / 2.0, 0.0, 0.0, math.pi)
_SIGNS = (1.0, -1.0, -1.0, 1.0, -1.0, 1.0)

#: Schwelle |j5|→0 für den Handgelenks-Singularitätszweig (Robots: zero_threshold).
SINGULARITY_THRESHOLD_RAD = 1.24e-2

#: Konfigurationsbits (Robots RobotConfigurations, [Flags]).
SHOULDER = 1
ELBOW = 2
WRIST = 4


@dataclass(frozen=True)
class IkSolution:
    """Eine IK-Lösung: 6 Gelenkwinkel (Radiant) + Konfiguration + Fehlerflags.

    ``configuration`` ist das Bitfeld aus SHOULDER/ELBOW/WRIST (wie Robots).
    ``unreachable`` markiert eine Zielpose außerhalb des Arbeitsraums (acos-Domäne
    verlassen), ``singularity`` die Nähe zur Handgelenks-Singularität (|j5|≈0/±π),
    in der j4/j6 gekoppelt sind — dort ist die Lösung nur eine gültige Auswahl aus
    dem redundanten Unterraum. Konfigurationswahl/Grenzprüfung: Issue #11.
    """

    joints_rad: tuple[float, float, float, float, float, float]
    configuration: int
    unreachable: bool
    singularity: bool


def _safe_acos(value: float) -> tuple[float, bool]:
    """acos mit Domänenschutz — gibt (Winkel, war_ausserhalb) zurück.

    Robots liest hier ``double.IsNaN`` ab und setzt den Winkel auf 0 samt
    „unreachable"; das bilden wir 1:1 nach.
    """
    if -1.0 <= value <= 1.0:
        return math.acos(value), False
    return 0.0, True


def _rot_to_quat(r: np.ndarray) -> tuple[float, float, float, float]:
    """Rotationsmatrix (3×3) → Einheitsquaternion [w, x, y, z] (Shepperd)."""
    trace = r[0, 0] + r[1, 1] + r[2, 2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (r[2, 1] - r[1, 2]) / s
        y = (r[0, 2] - r[2, 0]) / s
        z = (r[1, 0] - r[0, 1]) / s
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2.0
        w = (r[2, 1] - r[1, 2]) / s
        x = 0.25 * s
        y = (r[0, 1] + r[1, 0]) / s
        z = (r[0, 2] + r[2, 0]) / s
    elif r[1, 1] > r[2, 2]:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2.0
        w = (r[0, 2] - r[2, 0]) / s
        x = (r[0, 1] + r[1, 0]) / s
        y = 0.25 * s
        z = (r[1, 2] + r[2, 1]) / s
    else:
        s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2.0
        w = (r[1, 0] - r[0, 1]) / s
        x = (r[0, 2] + r[2, 0]) / s
        y = (r[1, 2] + r[2, 1]) / s
        z = 0.25 * s
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if w < 0.0:  # kanonisch: w ≥ 0
        n = -n
    return (w / n, x / n, y / n, z / n)


def _quat_to_rot(quat: tuple[float, float, float, float]) -> np.ndarray:
    """Einheitsquaternion [w, x, y, z] → Rotationsmatrix (3×3)."""
    w, x, y, z = quat
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def frame_distance(a: Frame, b: Frame) -> tuple[float, float]:
    """Abstand zweier Frames als (Positionsfehler mm, Orientierungsfehler rad).

    Der Orientierungsfehler ist der geodätische Winkel zwischen den Quaternionen
    (Vorzeichen-unabhängig). Kern der Toleranzprüfung des 1000-Posen-Orakels.
    """
    pos = math.dist(a.pos_mm, b.pos_mm)
    dot = abs(sum(qa * qb for qa, qb in zip(a.quat, b.quat, strict=True)))
    ori = 2.0 * math.acos(min(1.0, dot))
    return pos, ori


class OpwKinematics:
    """FK/IK-Solver für einen 6R-Arm mit OPW-Geometrie (Doosan M1013)."""

    def __init__(self, params: Kinematics) -> None:
        if params.n_joints != 6:
            raise ValueError(f"OPW-Solver braucht genau 6 Achsen, hat {params.n_joints}")
        self.params = params
        self._a = np.array(params.a_mm, dtype=float)
        self._d = np.array(params.d_mm, dtype=float)
        self._alpha = np.array(params.alpha_rad, dtype=float)
        # Charakteristische Länge (Σ|a|+Σ|d|), um die Translationszeilen der
        # Jacobi-Matrix dimensionslos zu machen (Singularitätsmaß, Issue #11).
        self._reach_mm = float(np.abs(self._a).sum() + np.abs(self._d).sum())

    @classmethod
    def from_robot(cls, name: str, robots_dir=None) -> OpwKinematics:
        robot = RobotDef.load(name, robots_dir)
        if robot.kinematics is None:
            raise ValueError(f"Roboter {name!r} trägt keine Kinematik-Parameter (kinematics-Block)")
        return cls(robot.kinematics)

    # -- Vorwärtskinematik ---------------------------------------------------

    def forward_matrix(self, joints_rad) -> np.ndarray:
        """Homogene 4×4-Flanschtransformation aus 6 Gelenkwinkeln (Standard-DH).

        Entspricht Robots' ``MechanismKinematics.DH`` — der Solver für den M1013
        wendet keine zusätzliche Flanschrotation an (anders als der Offset-Wrist).
        """
        joints = np.asarray(joints_rad, dtype=float)
        if joints.shape != (6,):
            raise ValueError(f"Erwarte 6 Gelenkwinkel, bekam Form {joints.shape}")
        t = np.eye(4)
        for i in range(6):
            c, s = math.cos(joints[i]), math.sin(joints[i])
            ca, sa = math.cos(self._alpha[i]), math.sin(self._alpha[i])
            ti = np.array(
                [
                    [c, -s * ca, s * sa, self._a[i] * c],
                    [s, c * ca, -c * sa, self._a[i] * s],
                    [0.0, sa, ca, self._d[i]],
                    [0.0, 0.0, 0.0, 1.0],
                ]
            )
            t = t @ ti
        return t

    def forward(self, joints_rad) -> Frame:
        """Gelenkwinkel (Radiant) → Flansch-Frame (mm, Quaternion [w, x, y, z])."""
        t = self.forward_matrix(joints_rad)
        pos = (float(t[0, 3]), float(t[1, 3]), float(t[2, 3]))
        return Frame(pos_mm=pos, quat=_rot_to_quat(t[:3, :3]))

    def link_frames(self, joints_rad) -> list[Frame]:
        """Kumulierte Frames aller Glieder (Basis … Flansch) in Basiskoordinaten.

        Liefert 7 Frames: Index 0 = Basis (Identität), Index i = das Frame nach
        Achse ``i-1`` der Standard-DH-Kette (dieselbe wie :meth:`forward_matrix`);
        Index 6 = Flansch (identisch zu :meth:`forward`). Dies ist die Quelle der
        Golden-Werte für die **Präsentations-FK** des Viewers (Arm-Replay): der
        Viewer rechnet dieselbe Kette nur zur Anzeige und wird per Testorakel
        gegen diese Frames validiert (ADR-007-Klarstellung 2026-07-04, ADR-009).
        """
        joints = np.asarray(joints_rad, dtype=float)
        if joints.shape != (6,):
            raise ValueError(f"Erwarte 6 Gelenkwinkel, bekam Form {joints.shape}")
        t = np.eye(4)
        frames = [Frame(pos_mm=(0.0, 0.0, 0.0), quat=(1.0, 0.0, 0.0, 0.0))]
        for i in range(6):
            c, s = math.cos(joints[i]), math.sin(joints[i])
            ca, sa = math.cos(self._alpha[i]), math.sin(self._alpha[i])
            ti = np.array(
                [
                    [c, -s * ca, s * sa, self._a[i] * c],
                    [s, c * ca, -c * sa, self._a[i] * s],
                    [0.0, sa, ca, self._d[i]],
                    [0.0, 0.0, 0.0, 1.0],
                ]
            )
            t = t @ ti
            frames.append(
                Frame(
                    pos_mm=(float(t[0, 3]), float(t[1, 3]), float(t[2, 3])),
                    quat=_rot_to_quat(t[:3, :3]),
                )
            )
        return frames

    # -- Inverskinematik -----------------------------------------------------

    def inverse(self, frame: Frame) -> list[IkSolution]:
        """Flansch-Frame → bis zu 8 IK-Lösungen (Shoulder/Elbow/Wrist)."""
        t = np.eye(4)
        t[:3, :3] = _quat_to_rot(frame.quat)
        t[:3, 3] = frame.pos_mm
        return self.inverse_matrix(t)

    def inverse_matrix(self, t: np.ndarray) -> list[IkSolution]:
        """Wie :meth:`inverse`, aber direkt aus der 4×4-Transformation.

        Zeilenweise Portierung von Robots' ``SphericalWristKinematics``: OPW-
        Parameter (a1, a2, b, c1..c4), acht Konfigurationen, abschließend die
        Abbildung auf die Roboter-Gelenkkonvention (``_signs``/``_start``) mit
        Normierung auf [-π, π].
        """
        a1 = self._a[0]
        a2 = -self._a[2]
        c1 = self._d[0]
        c2 = self._a[1]
        c3 = self._d[3]
        c4 = self._d[5]
        b = -self._d[1]

        # Flansch-Ursprung und -Normale (z-Achse), Handgelenkzentrum c.
        origin = t[:3, 3]
        normal = t[:3, 2]
        cx, cy, cz = (origin - c4 * normal)

        solutions: list[IkSolution] = []
        for config in range(8):
            shoulder = bool(config & SHOULDER)
            elbow = bool(config & ELBOW)
            wrist = bool(config & WRIST)
            unreachable = False

            nx1_sq = cx * cx + cy * cy - b * b
            if nx1_sq < 0.0:
                nx1_sq = 0.0
                unreachable = True
            nx1 = math.sqrt(nx1_sq) - a1

            tmp1 = math.atan2(cy, cx)
            tmp2 = math.atan2(b, nx1 + a1)
            j0 = (tmp1 - tmp2) if not shoulder else (tmp1 + tmp2 - math.pi)

            tmp3 = cz - c1
            kappa_2 = a2 * a2 + c3 * c3
            c2_2 = c2 * c2
            s1_2 = nx1 * nx1 + tmp3 * tmp3
            tmp4 = nx1 + 2.0 * a1
            s2_2 = tmp4 * tmp4 + tmp3 * tmp3

            if not shoulder:
                s1 = math.sqrt(s1_2)
                tmp13, nan13 = _safe_acos((s1_2 + c2_2 - kappa_2) / (2.0 * s1 * c2))
                unreachable = unreachable or nan13
                tmp14 = math.atan2(nx1, cz - c1)
                j1 = (-tmp13 + tmp14) if not elbow else (tmp13 + tmp14)
            else:
                s2 = math.sqrt(s2_2)
                tmp15, nan15 = _safe_acos((s2_2 + c2_2 - kappa_2) / (2.0 * s2 * c2))
                unreachable = unreachable or nan15
                tmp16 = math.atan2(nx1 + 2.0 * a1, cz - c1)
                j1 = (tmp15 - tmp16) if not elbow else (-tmp15 - tmp16)

            tmp9 = 2.0 * c2 * math.sqrt(kappa_2)
            tmp10 = math.atan2(a2, c3)
            if not shoulder:
                tmp11, nan11 = _safe_acos((s1_2 - c2_2 - kappa_2) / tmp9)
                unreachable = unreachable or nan11
                j2 = (tmp11 - tmp10) if not elbow else (-tmp11 - tmp10)
            else:
                tmp12, nan12 = _safe_acos((s2_2 - c2_2 - kappa_2) / tmp9)
                unreachable = unreachable or nan12
                j2 = (-tmp12 - tmp10) if not elbow else (tmp12 - tmp10)

            sin0, cos0 = math.sin(j0), math.cos(j0)
            s23 = math.sin(j1 + j2)
            c23 = math.cos(j1 + j2)

            m = t[0, 2] * s23 * cos0 + t[1, 2] * s23 * sin0 + t[2, 2] * c23
            j4 = math.atan2(math.sqrt(max(0.0, 1.0 - m * m)), m)
            if wrist:
                j4 = -j4

            singularity = abs(j4) < SINGULARITY_THRESHOLD_RAD
            if singularity:
                j3 = 0.0
                xe = t[:3, 0]
                col1 = np.array([-math.sin(j0), math.cos(j0), 0.0])
                col2 = t[:3, 2]
                col0 = np.cross(col1, col2)
                rc = np.vstack([col0, col1, col2])
                xec = rc @ xe
                j5 = math.atan2(xec[1], xec[0])
            else:
                j3 = math.atan2(
                    t[1, 2] * cos0 - t[0, 2] * sin0,
                    t[0, 2] * c23 * cos0 + t[1, 2] * c23 * sin0 - t[2, 2] * s23,
                )
                j5 = math.atan2(
                    t[0, 1] * s23 * cos0 + t[1, 1] * s23 * sin0 + t[2, 1] * c23,
                    -t[0, 0] * s23 * cos0 - t[1, 0] * s23 * sin0 - t[2, 0] * c23,
                )

            if wrist:
                j3 += math.pi
                j5 -= math.pi

            raw = [j0, j1, j2, j3, j4, j5]
            joints = []
            for i in range(6):
                v = _SIGNS[i] * raw[i] + _START[i]
                if math.isnan(v):
                    v = 0.0
                # Normierung auf [-π, π] (Robots).
                while v > math.pi:
                    v -= 2.0 * math.pi
                while v < -math.pi:
                    v += 2.0 * math.pi
                joints.append(v)

            solutions.append(
                IkSolution(
                    joints_rad=tuple(joints),  # type: ignore[arg-type]
                    configuration=config,
                    unreachable=unreachable,
                    singularity=singularity,
                )
            )
        return solutions

    # -- Jacobi-Matrix und Singularitätsnähe ---------------------------------

    def jacobian(self, joints_rad) -> np.ndarray:
        """Geometrische 6×6-Jacobi-Matrix im Basissystem (Issue #11).

        Zeilen 0..2 = Translationsanteil (mm/rad), Zeilen 3..5 = Rotationsanteil
        (dimensionslos). Für die reine Drehgelenkkette (alle 6 Achsen revolut)
        gilt spaltenweise ``J[:3,i] = z_i × (o_e − o_i)`` und ``J[3:,i] = z_i``,
        mit den z-Achsen ``z_i`` und Ursprüngen ``o_i`` der Zwischenframes aus der
        Standard-DH-Kette (dieselbe wie :meth:`forward_matrix`).
        """
        joints = np.asarray(joints_rad, dtype=float)
        if joints.shape != (6,):
            raise ValueError(f"Erwarte 6 Gelenkwinkel, bekam Form {joints.shape}")
        t = np.eye(4)
        origins = [t[:3, 3].copy()]
        zaxes = [t[:3, 2].copy()]
        for i in range(6):
            c, s = math.cos(joints[i]), math.sin(joints[i])
            ca, sa = math.cos(self._alpha[i]), math.sin(self._alpha[i])
            ti = np.array(
                [
                    [c, -s * ca, s * sa, self._a[i] * c],
                    [s, c * ca, -c * sa, self._a[i] * s],
                    [0.0, sa, ca, self._d[i]],
                    [0.0, 0.0, 0.0, 1.0],
                ]
            )
            t = t @ ti
            origins.append(t[:3, 3].copy())
            zaxes.append(t[:3, 2].copy())
        o_e = origins[6]
        jac = np.zeros((6, 6))
        for i in range(6):
            jac[:3, i] = np.cross(zaxes[i], o_e - origins[i])
            jac[3:, i] = zaxes[i]
        return jac

    def singularity_measure(self, joints_rad) -> float:
        """Singularitätsnähe ∈ [0, 1]: 1 = gut konditioniert, 0 = singulär.

        Reziproke Konditionszahl (σ_min/σ_max) der längen-normierten Jacobi-Matrix
        (Translationszeilen durch die charakteristische Länge ``_reach_mm`` geteilt,
        damit Translations- und Rotationsanteil dimensionslos vergleichbar sind).
        Das Maß fällt bei jeder Rangminderung der Kette gegen 0 — Handgelenks-
        (Achse 4∥6), Ellenbogen- und Schultersingularität gleichermaßen — und ist
        so ein robotweit einheitliches, roboterunabhängig schwellbares Nähemaß.
        """
        jac = self.jacobian(joints_rad)
        jac[:3, :] /= self._reach_mm
        sv = np.linalg.svd(jac, compute_uv=False)
        if sv[0] <= 0.0:
            return 0.0
        return float(sv[-1] / sv[0])

    # -- Grenzen -------------------------------------------------------------

    def in_limits(self, joints_rad) -> bool:
        """True, wenn alle Gelenkwinkel innerhalb der Achsgrenzen liegen."""
        return all(
            lo - 1e-10 <= q <= hi + 1e-10
            for q, (lo, hi) in zip(joints_rad, self.params.joint_limits_rad, strict=True)
        )
