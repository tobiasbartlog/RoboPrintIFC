"""Typ-Klassifikation der Singularitätsnähe (Issue #65, Scheibe 6 von PRD #57).

Das reziproke Konditionsmaß (``OpwKinematics.singularity_measure``, Issue #11)
sagt **wie nah** eine Pose an einer Singularität ist — aber nicht **welcher Art**.
Dieses tiefe, reine Modul klassifiziert die Nähe aus den **Gelenkwinkeln** nach
Typ und liefert damit die Grundlage für gezielte Vorschläge (Advisor,
``fgc.placement.advisor``):

- **Handgelenk** (wrist): die Beugeachse J5 (``joints_rad[4]``) steht nahe 0 bzw.
  ±π — die beiden umgebenden Drehachsen (J4∥J6) werden (anti)parallel, der
  Handgelenks-Freiheitsgrad koppelt (derselbe Zweig wie
  ``opw.SINGULARITY_THRESHOLD_RAD``).
- **Ellbogen** (elbow): der Arm ist **gestreckt** (oder ganz gefaltet) — die
  Handwurzel liegt am Rand des 2-Glied-Arbeitsraums (Abstand Schulter→Handwurzel
  ≈ Oberarm+Unterarm bzw. |Oberarm−Unterarm|), J3 nahe seiner Streckung.
- **Schulter** (shoulder): die **Handwurzel** liegt über/nahe der
  Basis-Drehachse z0 — der radiale Abstand von z0 fällt auf den geometrischen
  Mindestabstand (Schulter-Offset ``b``).

Es wird **kein neues Skalarmaß** erfunden: die *Nähe* bleibt
``singularity_measure``; hier kommt nur die *Typ*-Unterscheidung dazu. Die
Klassifikation rechnet dimensionslose Schwere-Werte ∈ [0, 1] je Typ (1 = genau
an der jeweiligen Bedingung) aus rein geometrischen, aus den Gelenkwinkeln per
FK abgeleiteten Indikatoren; der dominante Typ ist der mit der größten Schwere.

Einheiten strikt nach ADR-006 (Gelenkwinkel in Radiant, Längen in Millimeter).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from fgc.kinematics.opw import OpwKinematics
from fgc.kinematics.select import DEFAULT_SINGULARITY_WARN

#: Vokabular der Singularitätstypen.
SingularityType = Literal["wrist", "elbow", "shoulder"]

#: Winkelband (rad) um die Handgelenks-Bedingung (J5 nahe 0/±π), in dem die
#: Handgelenks-Schwere von 1 auf 0 abklingt (~20°). Oberhalb des harten
#: OPW-Zweigs (``opw.SINGULARITY_THRESHOLD_RAD``) mit Marge angesetzt.
WRIST_BAND_RAD = 0.35

#: Radiales Band (Bruchteil der charakteristischen Reichweite) für die
#: Schulter-Schwere: fällt der Abstand der Handwurzel von z0 (abzüglich des
#: Schulter-Offsets ``b``) unter dieses Band, klingt die Schwere von 1 ab.
SHOULDER_BAND_FRACTION = 0.12

#: Längenband (Bruchteil der Reichweite) für die Ellbogen-Schwere: Abstand des
#: Schulter→Handwurzel-Maßes von der Streckung/Faltung, in dem die Schwere abklingt.
ELBOW_BAND_FRACTION = 0.10


@dataclass(frozen=True)
class SingularityAssessment:
    """Typ-Urteil einer Pose — reine Daten (kein Gate).

    ``measure`` ist das reziproke Konditionsmaß (Issue #11, 0 = singulär,
    1 = gut konditioniert); ``near`` sagt, ob es unter der Warnschwelle liegt.
    ``dominant`` ist der Typ mit der größten ``severity`` (auch wenn nicht
    ``near`` — dann der *nächstliegende* Typ). Die drei ``*_severity`` ∈ [0, 1]
    sind die dimensionslosen Nähe-Anteile je Typ; ``*``-Rohindikatoren tragen die
    geometrischen Größen für Anzeige/Diagnose.
    """

    measure: float
    near: bool
    dominant: SingularityType
    wrist_severity: float
    elbow_severity: float
    shoulder_severity: float
    wrist_angle_rad: float
    elbow_gap_mm: float
    wrist_center_radial_mm: float

    @property
    def severities(self) -> dict[str, float]:
        return {
            "wrist": self.wrist_severity,
            "elbow": self.elbow_severity,
            "shoulder": self.shoulder_severity,
        }


def _wrap(angle: float) -> float:
    """Winkel auf (−π, π]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def wrist_center_mm(kin: OpwKinematics, joints_rad) -> np.ndarray:
    """Handgelenkzentrum (Schnittpunkt der letzten drei Achsen) in Basiskoordinaten.

    Der sphärische Handgelenk-Ursprung liegt um ``d6`` entlang der Flansch-z-Achse
    vor dem Flansch — dieselbe Größe, die ``opw.inverse_matrix`` als ``c`` nutzt
    (``origin − c4·normal``). Grundlage der Schulter-/Ellbogen-Indikatoren.
    """
    t = kin.forward_matrix(joints_rad)
    return t[:3, 3] - kin._d[5] * t[:3, 2]


def classify(
    kin: OpwKinematics,
    joints_rad,
    *,
    warn_below: float = DEFAULT_SINGULARITY_WARN,
) -> SingularityAssessment:
    """Klassifiziert die Singularitätsnähe einer Pose nach Typ (aus Gelenkwinkeln).

    Baut auf ``kin.singularity_measure`` (Nähe, Issue #11) auf und ergänzt die
    **Typ**-Unterscheidung: drei geometrische, dimensionslose Schwere-Werte
    (Handgelenk/Ellbogen/Schulter); der dominante Typ ist der mit der größten
    Schwere. Rein und deterministisch — Grundlage der Advisor-Vorschläge.
    """
    q = np.asarray(joints_rad, dtype=float)
    if q.shape != (6,):
        raise ValueError(f"Erwarte 6 Gelenkwinkel, bekam Form {q.shape}")

    measure = kin.singularity_measure(q)

    reach = kin._reach_mm
    b = abs(float(kin._d[1]))            # Schulter-Offset (perpendicular)
    upper_arm = abs(float(kin._a[1]))    # Oberarm  (OPW c2)
    forearm = abs(float(kin._d[3]))      # Unterarm (OPW c3)

    wc = wrist_center_mm(kin, q)
    shoulder = np.asarray(kin.link_frames(q)[1].pos_mm, dtype=float)

    # Handgelenk: Beugeachse J5 nahe 0 oder ±π (nächster Abstand zu {0, π}).
    j5 = _wrap(float(q[4]))
    wrist_angle = min(abs(j5), abs(math.pi - abs(j5)))
    wrist_sev = _clamp01(1.0 - wrist_angle / WRIST_BAND_RAD)

    # Schulter: radialer Abstand der Handwurzel von z0, abzüglich Mindestabstand b.
    radial = math.hypot(float(wc[0]), float(wc[1]))
    radial_off = max(0.0, radial - b)
    shoulder_sev = _clamp01(1.0 - radial_off / (SHOULDER_BAND_FRACTION * reach))

    # Ellbogen: Schulter→Handwurzel nahe Streckung (c2+c3) bzw. Faltung |c2−c3|.
    r_sw = float(np.linalg.norm(wc - shoulder))
    elbow_gap = min(abs(r_sw - (upper_arm + forearm)), abs(r_sw - abs(upper_arm - forearm)))
    elbow_sev = _clamp01(1.0 - elbow_gap / (ELBOW_BAND_FRACTION * reach))

    severities: dict[SingularityType, float] = {
        "wrist": wrist_sev,
        "elbow": elbow_sev,
        "shoulder": shoulder_sev,
    }
    # Dominanter Typ = größte Schwere; Gleichstand deterministisch nach fester
    # Reihenfolge (wrist, elbow, shoulder).
    order: tuple[SingularityType, ...] = ("wrist", "elbow", "shoulder")
    dominant = max(order, key=lambda t: (severities[t], -order.index(t)))

    return SingularityAssessment(
        measure=measure,
        near=measure < warn_below,
        dominant=dominant,
        wrist_severity=wrist_sev,
        elbow_severity=elbow_sev,
        shoulder_severity=shoulder_sev,
        wrist_angle_rad=wrist_angle,
        elbow_gap_mm=elbow_gap,
        wrist_center_radial_mm=radial,
    )
