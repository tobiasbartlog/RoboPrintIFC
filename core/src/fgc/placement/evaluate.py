"""Bewertung einer Aufstellmoeglichkeit (Platzierung, Bewertungsmodus — Issue #22).

Deep module (isoliert testbar): ``evaluate(wand, roboter, endeffektor, option)``
liefert einen :class:`PlacementScore` — den **erreichbaren Wandanteil** (IK ueber
ein festes Sampling-Raster der Wandflaeche/Bahnhoehen) und die **kinematische
Marge** (Singularitaetsnaehe der erreichten Punkte). Die Metrik folgt der
Grill-Entscheidung 2026-07-04 (`core/CONTEXT.md`, Begriff *Platzierung*).

Ein Plan, keine Messung: die Platzierung ist die *geplante* Lage der Roboterbasis
relativ zur Wand (ADR-006). Verbindlich wird die Lage erst ueber das
Antast-Verfahren als **Setup** — dieses Modul rechnet nur eine reproduzierbare
Bewertung.

Kinematik/Erreichbarkeit laufen ausschliesslich ueber die bestehende
:class:`fgc.kinematics.OpwKinematics` + :func:`fgc.kinematics.select_along_path`
(nichts dupliziert, Issue #7/#11). Warnungen sind **Daten**, kein Abbruch — sie
kommen aus der Konfigurationswahl als Liste heraus.

Einheiten strikt nach ADR-006: Millimeter, Radiant, Quaternionen [w, x, y, z].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np

from fgc.domain.models import Frame
from fgc.domain.orientation import NOZZLE_DOWN_QUAT, nozzle_quat
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.kinematics import IkConfigFilter, OpwKinematics, select_along_path
from fgc.kinematics.opw import _quat_to_rot, _rot_to_quat

if TYPE_CHECKING:
    from fgc.kinematics.reachability import ReachabilityMap

#: Festes Sampling-Raster (mm) ueber Wandlaenge und -hoehe. Deterministisch:
#: gleiche Wand + gleiche Aufloesung -> gleiche Stichprobe (ADR-004-Geist).
#: 150 mm haelt die Bewertung schnell (Dutzende IK-Aufrufe) und dennoch dicht
#: genug, um Reichweitengrenzen in der Hoehe sicher zu erfassen.
SAMPLE_SPACING_MM = 150.0

#: Duesen-Anfluggeometrie im Nullpunkt (Lead 0 / Kipp 0): die Duese zeigt
#: senkrecht nach unten (TCP-z auf -z der Wandwelt). Aus derselben kanonischen
#: Konstante wie die Slicer-Ziele abgeleitet (ADR-006, Issue #51) — sonst driften
#: Feasibility (placement) und Simulation auseinander. Ergibt ``diag(1, -1, -1)``.
_R_NOZZLE_DOWN = _quat_to_rot(NOZZLE_DOWN_QUAT)

#: Die von ``placement`` angenommene Bahntangente (Issue #61): horizontal entlang
#: der Wandlaenge (+x). Dieselbe Funktion ``nozzle_quat`` fuellt im Slicer die
#: echte Ringtangente — mit gleicher Tangente ergibt sich dieselbe Rotation, also
#: kein Auseinanderdriften von Erreichbarkeit und Simulation (Regressionsschutz #51).
_PLACEMENT_TANGENT: tuple[float, float, float] = (1.0, 0.0, 0.0)


def nozzle_rotation(lead_rad: float, kipp_rad: float) -> np.ndarray:
    """Anflug-Rotationsmatrix fuer die angenommene Tangente + Anstellung (Issue #61).

    Genau der Pfad, den auch der Slicer geht (``nozzle_quat``) — nur mit der von
    ``placement`` angenommenen horizontalen Tangente. Kipp/Lead != 0 aendern damit
    die Flansch-Ziel-Orientierung und dadurch **nachweisbar** die Erreichbarkeit
    (Ampel), ohne die Rotationskonvention zu duplizieren.

    Öffentlicher Seam (Issue #201): die geteilte ``nozzle_quat``-Konvention ist die
    **eine** Orientierungsquelle für ``placement`` (Bewertung, Advisor, Grob-Check)
    und den Slicer — externe Konsumenten (``advisor``, ``collision.coarse``,
    ``test_slicer``) treffen sie über genau diesen Namen, nicht über ein Duplikat.
    """
    return _quat_to_rot(nozzle_quat(_PLACEMENT_TANGENT, lead_rad, kipp_rad))


@dataclass(frozen=True)
class WallSurface:
    """Die zu bedruckende Wandflaeche als Rechteck im Wand-Koordinatensystem.

    ``x`` laeuft entlang der Wandlaenge (zentriert um 0), ``z`` entlang der Hoehe
    (``z_offset_mm .. z_offset_mm + height_mm``), gedruckt wird auf der Front
    ``y = 0``. Eine bewusst schlanke Repraesentation: fuer die
    Erreichbarkeitsbewertung zaehlt die abzufahrende Flaeche, nicht die volle
    Mesh-Geometrie — so bleibt das Modul mit synthetischen Fixtures (klein/hoch)
    testbar.

    ``z_offset_mm`` (Issue #132, Design-Log 2026-07-09) ist die **echte
    Hoehenlage** der Flaeche ueber dem Boden (Boden = Wandfuss ``z = 0``): ein
    Wand-**Abschnitt** der Reihe 2 traegt hier sein ``z0`` und wird dadurch an
    seiner tatsaechlichen Hoehe bewertet — die Aufstellhoehe der Basis
    (``PlacementOption.stand_height_mm``) ist im selben System **absolut**.
    Default ``0.0`` = Flaeche beginnt am Boden (ganze Wand, unterste Reihe):
    exakt die bisherige Konvention, Bewertung bit-identisch.
    """

    length_mm: float
    height_mm: float
    thickness_mm: float = 0.0
    z_offset_mm: float = 0.0


@dataclass(frozen=True)
class PlacementOption:
    """Eine reale Aufstellmoeglichkeit: die geplante Basis-Lage relativ zur Wand.

    ``lateral_mm`` = seitliche Position der Basis entlang der Wandlaenge (x);
    ``standoff_mm`` = **freier Abstand** der Basis vor der Wandfront (Issue #160:
    gemessen ab der naechstliegenden Wand-/Modulflaeche, NICHT ab der
    Mittelebene — die y-Koordinate im PCA-Wandsystem liefert
    :func:`base_position_in_wall`); ``stand_height_mm`` = Aufstellhoehe der
    Basis (z, z. B. Podest) — **absolut ueber dem Boden** (Boden = Wandfuss
    ``z = 0``, Issue #132), auch wenn die bewertete Flaeche ein hoeher
    liegender Abschnitt ist (``WallSurface.z_offset_mm``); ``yaw_rad`` =
    optionale Drehung der Basis um die Hochachse. Ein **Plan**, kein Setup.
    """

    option_id: str
    lateral_mm: float
    standoff_mm: float
    stand_height_mm: float
    yaw_rad: float = 0.0


def base_position_in_wall(
    option: PlacementOption, thickness_mm: float
) -> tuple[float, float, float]:
    """Basis-Position im PCA-Wandsystem (Mittelebene ``y = 0``, Issue #160).

    Die **eine** Umrechnungsnaht zwischen den Platzierungs-Skalaren (Abstand ab
    Wandflaeche — so misst der Aufsteller am Tisch) und der y-Koordinate des
    Wandsystems: ``y = Dicke/2 + standoff``. Alle Frame-Bauer (Bewertung,
    Grobkollision, Simulations-Setup, Modul-Pose) beziehen die Basis-Lage
    ausschliesslich hierueber — Anzeige und Rechnung koennen nicht mehr
    auseinanderlaufen (Regression: Denkmal-Kollision 2026-07-12).

    ``thickness_mm <= 0`` (unbekannte Dicke) degeneriert ehrlich zu
    ``y = standoff`` (Flaeche = Mittelebene) — kein Raten einer Ersatzdicke.
    """
    half = max(0.0, float(thickness_mm)) / 2.0
    return (option.lateral_mm, half + option.standoff_mm, option.stand_height_mm)


def standoff_from_base_y(y_mm: float, thickness_mm: float) -> float:
    """Rueckweg der Naht: y-Koordinate im Wandsystem → freier Abstand ab Flaeche."""
    return float(y_mm) - max(0.0, float(thickness_mm)) / 2.0


@dataclass(frozen=True)
class PlacementScore:
    """Bewertung einer Aufstellmoeglichkeit — reine Daten (kein Gate).

    ``reachable_fraction`` ∈ [0, 1] = Anteil der Stichprobenpunkte mit gueltiger
    IK-Loesung innerhalb der Achsgrenzen. ``kinematic_margin`` = kleinstes
    Singularitaetsnaehe-Mass ueber die erreichten Punkte (0 = singulaer, 1 = gut
    konditioniert), ``mean_margin`` der Mittelwert; beide ``None``, wenn kein
    Punkt erreichbar ist. ``warnings`` traegt die Konfigurationswahl-Warnungen
    als Daten (unreachable/joint_limits/singularity).

    ``reach_estimate`` (Issue #214) traegt — **nur wenn eine Reichweitenkarte
    gerufen wurde** — die als Schaetzung gekennzeichnete Karten-Vorwegnahme des
    erreichbaren Anteils (``is_estimate=True``, US 7). Die Karte **filtert, urteilt
    nie** (ADR-007): ``reachable_fraction`` (die Ampel-Basis) bleibt das IK-Urteil,
    die Schaetzung steht als getrenntes Feld daneben. Ohne Karte ``None`` — dann
    fehlt der Schluessel im ``to_dict`` und Altlaeufe bleiben byte-gleich (US 12).

    ``collision`` (Issue #228, ADR-026 Punkt 1) traegt — **nur wenn der
    Platzierungs-Grob-Check gelaufen ist** — das explizite Machbarkeits-Urteil des
    Kandidaten (``{"free": bool, "status": "clear"|"colliding", "source": "coarse"}``).
    Ein **Befund, kein Gate**: die Sortierung fuehrt ``free`` als vordersten
    Schluessel, das Feld macht das Urteil fuer Pipeline/Viewer sichtbar, ohne die
    Reihenfolge deuten zu muessen (US 17/21). ``None`` = nicht geprueft (keine
    Kollisionsgeometrie / Altlauf) — dann fehlt der Schluessel im ``to_dict`` und
    das Dict bleibt byte-gleich zum Reichweiten-Zustand.

    ``ik_config`` (Issue #233, ADR-026 Punkt 5) traegt — **nur wenn die IK-Konfig-
    Suchachse gelaufen ist** (Optimalvorschlag) — den **gewaehlten** IK-Konfig-Zweig
    dieses Kandidaten als persistierbaren a/b-Block (``{"shoulder": "a"|"b", …}``;
    leeres/fehlendes Feld = auto). So faehrt die Simulation nachweislich **dieselbe**
    Konfiguration wie die Bewertung (``IkConfigFilter.from_block``). ``None`` = keine
    Achse gelaufen (Bewertungsmodus / Altlauf) — Schluessel fehlt im ``to_dict``.
    """

    reachable_fraction: float
    n_samples: int
    n_reachable: int
    kinematic_margin: float | None
    mean_margin: float | None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    sampling: dict[str, Any] = field(default_factory=dict)
    reach_estimate: dict[str, Any] | None = None
    collision: dict[str, Any] | None = None
    ik_config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "reachable_fraction": self.reachable_fraction,
            "n_samples": self.n_samples,
            "n_reachable": self.n_reachable,
            "kinematic_margin": self.kinematic_margin,
            "mean_margin": self.mean_margin,
            "warnings": self.warnings,
            "sampling": self.sampling,
        }
        # Karten-Schätzung nur mitgeben, wenn eine Karte gerufen wurde — ohne Karte
        # bleibt das Dict byte-gleich zu Altläufen (fail-soft, US 12).
        if self.reach_estimate is not None:
            d["reach_estimate"] = self.reach_estimate
        # Kollisionsurteil nur mitgeben, wenn der Grob-Check lief (Issue #228) —
        # ungeprüft bleibt das Dict byte-gleich zum reinen Reichweiten-Zustand.
        if self.collision is not None:
            d["collision"] = self.collision
        # Gewählte IK-Konfiguration nur mitgeben, wenn die Suchachse lief (Issue #233) —
        # ohne Achse (Bewertungsmodus) bleibt das Dict byte-gleich zum Altzustand.
        if self.ik_config is not None:
            d["ik_config"] = self.ik_config
        return d


def _homogeneous(rot: np.ndarray, pos: tuple[float, float, float]) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = rot
    t[:3, 3] = pos
    return t


def _invert_rigid(t: np.ndarray) -> np.ndarray:
    """Inverse einer starren 4x4-Transformation (R^T, -R^T t)."""
    rot_t = t[:3, :3].T
    inv = np.eye(4)
    inv[:3, :3] = rot_t
    inv[:3, 3] = -rot_t @ t[:3, 3]
    return inv


def _rot_z(yaw_rad: float) -> np.ndarray:
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _sample_counts(length_mm: float, height_mm: float, spacing_mm: float) -> tuple[int, int]:
    n_length = max(2, math.ceil(max(0.0, length_mm) / spacing_mm) + 1)
    n_height = max(2, math.ceil(max(0.0, height_mm) / spacing_mm) + 1)
    return n_length, n_height


class FlangeTargets(NamedTuple):
    """Das Flansch-Ziel-Raster einer Platzierung — der öffentliche Seam (Issue #201).

    ``frames`` = die Flansch-Ziel-Frames in **Roboterbasis-Koordinaten** (Reihenfolge:
    Höhe außen/Schichten unten→oben, Länge innen); ``n_length``/``n_height`` = die
    Rastermaße; ``t_wall_base`` = die **eine** Wand→Basis-Plan-Transformation (4×4,
    homogen, mm), aus der die Frames abgeleitet sind. Sie wird **einmal** hier
    gebildet (die t_wall_base-Kette lebt genau an dieser Stelle) und mitgegeben, damit
    der Grob-Check (:mod:`fgc.collision.coarse`) die Glied-Frames ins Wandsystem
    zurückbringen kann, **ohne** die Invariante zu duplizieren.
    """

    frames: list[Frame]
    n_length: int
    n_height: int
    t_wall_base: np.ndarray


def flange_targets(
    wall: WallSurface,
    tool: ToolDef,
    option: PlacementOption,
    spacing_mm: float,
    r_nozzle: np.ndarray,
) -> FlangeTargets:
    """Baut das Flansch-Ziel-Raster (Roboterbasis-System) fuer alle Rasterpunkte.

    Öffentlicher Seam (Issue #201) mit dokumentierten Invarianten:

    - **Basiskoordinaten:** ``frames`` liegen im Roboterbasis-System (Ziel der IK,
      ``select_along_path``); ``t_wall_base`` ist die zugehörige Wand→Basis-Plan-
      Transformation.
    - **Höhe-außen-Ordnung:** äußere Schleife über die Höhe (Schichten unten→oben),
      innere über die Länge — je Schicht eine natürlich stetige Punktfolge für die
      Konfigurationswahl.
    - **geteilte ``nozzle_quat``-Konvention:** ``r_nozzle`` ist die Anflug-Rotation
      (Düse nach unten, ggf. angestellt) aus derselben ``nozzle_quat`` wie der Slicer
      (:func:`nozzle_rotation`, Issue #61) — kein Auseinanderdriften von
      Erreichbarkeit und Simulation.

    Die z-Stichproben liegen auf der **echten Hoehenlage** der Flaeche
    (``z_offset_mm .. z_offset_mm + height_mm``, Issue #132) — Basis
    (``stand_height_mm``) und Ziele teilen so dasselbe absolute Hoehensystem
    (Boden = Wandfuss). Der Abstand misst ab der Wandflaeche (Issue #160): die eine
    Naht :func:`base_position_in_wall` rechnet ihn auf die y-Koordinate des
    Wandsystems um. ``t_wall_base`` wird als Teil der :class:`FlangeTargets`
    zurueckgegeben (die Kette existiert genau einmal).
    """
    n_length, n_height = _sample_counts(wall.length_mm, wall.height_mm, spacing_mm)
    xs = np.linspace(-wall.length_mm / 2.0, wall.length_mm / 2.0, n_length)
    zs = np.linspace(wall.z_offset_mm, wall.z_offset_mm + wall.height_mm, n_height)

    # Werkzeug: TCP relativ Flansch (ADR-006/-011).
    tcp = tool.tcp_frame
    r_tool = _quat_to_rot(tuple(tcp["quat"]))
    t_flange_tcp = _homogeneous(r_tool, tuple(tcp["pos_mm"]))
    t_flange_tcp_inv = _invert_rigid(t_flange_tcp)

    # Basis-Lage relativ zur Wand (Plan) -> Wand->Basis-Transformation. Der
    # Abstand misst ab der Wandflaeche (Issue #160) — die Naht rechnet ihn auf
    # die y-Koordinate des Wandsystems um.
    t_wall_base = _homogeneous(
        _rot_z(option.yaw_rad),
        base_position_in_wall(option, wall.thickness_mm),
    )
    t_base_wall = _invert_rigid(t_wall_base)

    frames: list[Frame] = []
    for z in zs:
        for x in xs:
            t_wall_tcp = _homogeneous(r_nozzle, (float(x), 0.0, float(z)))
            t_wall_flange = t_wall_tcp @ t_flange_tcp_inv
            t_base_flange = t_base_wall @ t_wall_flange
            pos = (
                float(t_base_flange[0, 3]),
                float(t_base_flange[1, 3]),
                float(t_base_flange[2, 3]),
            )
            frames.append(Frame(pos_mm=pos, quat=_rot_to_quat(t_base_flange[:3, :3])))
    return FlangeTargets(frames, n_length, n_height, t_wall_base)


def evaluate(
    wall: WallSurface,
    robot: RobotDef,
    tool: ToolDef,
    option: PlacementOption,
    *,
    spacing_mm: float = SAMPLE_SPACING_MM,
    lead_rad: float = 0.0,
    kipp_rad: float = 0.0,
    config_filter: IkConfigFilter | None = None,
    reach_map: ReachabilityMap | None = None,
) -> PlacementScore:
    """Bewertet eine Aufstellmoeglichkeit: erreichbarer Wandanteil + kin. Marge.

    Legt ein festes Raster (``spacing_mm``) ueber die Wandflaeche, rechnet je
    Punkt das Flansch-Ziel (Duese senkrecht nach unten, ggf. bahn-relativ
    angestellt) im Roboterbasis-System und laesst die bestehende
    Konfigurationswahl (:func:`select_along_path`) Erreichbarkeit und
    Singularitaetsnaehe bestimmen. Deterministisch: gleiche Eingaben -> gleicher
    Score.

    ``lead_rad``/``kipp_rad`` (Issue #61) stellen die Duese ueber die geteilte
    :func:`fgc.domain.orientation.nozzle_quat` an — mit der von ``placement``
    angenommenen horizontalen Tangente. Ein gesetzter Kipp aendert damit
    nachweisbar die Erreichbarkeit (Ampel), ohne die Rotation zu duplizieren
    (Regressionsschutz #51). 0/0 = senkrecht von oben (heutiges Verhalten).

    ``config_filter`` (Issue #129/#200) beschränkt die zulässigen IK-Konfigurations-
    zweige **hart** (Schulter/Ellbogen/Handgelenk je ``a``/``b``/auto) — dieselbe
    Neu-Bewertung wie ohne Filter, nur mit gesetzter Vorgabe. Unter der Vorgabe
    unerreichbare Bahnpunkte sinken so ehrlich in ``reachable_fraction`` ein und
    tauchen als ``ik_config``-Warnung auf (Befund, kein Gate). ``None``/all-auto =
    Regressionsanker (bit-identisch zu heute).

    ``reach_map`` (Issue #214) ist der **Vorfilter** — die binaere Reichweitenkarte
    (#210). Gesetzt, fuellt sie ``reach_estimate`` mit dem geschaetzten erreichbaren
    Anteil (Karten-Vorwegnahme, klar als Schaetzung gekennzeichnet, US 7). Die Karte
    **filtert, urteilt nie** (ADR-007/#164): ``reachable_fraction`` und die Warnungen
    bleiben das unveraenderte IK-Urteil (Ampel-Semantik unberuehrt, US 11). ``None``
    (Default) = byte-gleich zu Altlaeufen (fail-soft, US 12).

    Wirft ``ValueError``, wenn die Roboterdefinition keine Kinematik-Parameter
    traegt (ohne FK/IK ist keine Erreichbarkeit rechenbar).
    """
    if robot.kinematics is None:
        raise ValueError(
            f"Roboter {robot.name!r} traegt keine Kinematik-Parameter — "
            "Erreichbarkeit nicht rechenbar (kinematics-Block fehlt)."
        )
    kin = OpwKinematics(robot.kinematics)
    r_nozzle = nozzle_rotation(lead_rad, kipp_rad)
    frames, n_length, n_height, _t_wall_base = flange_targets(
        wall, tool, option, spacing_mm, r_nozzle
    )

    # Vorfilter-Schaetzung (US 7): die Karte antwortet vorwaerts in Mikrosekunden,
    # bevor die IK laeuft — reine Daten neben dem Urteil, kein Ersatz dafuer.
    reach_estimate: dict[str, Any] | None = None
    if reach_map is not None:
        reach_estimate = {
            "reachable_fraction": float(reach_map.reachable_fraction(frames)),
            "is_estimate": True,
            "source": "reachability_map",
            "note": "Karten-Schaetzung (Vorfilter) — kein Prueftuer-Urteil (ADR-007).",
        }

    solution = select_along_path(kin, frames, config_filter=config_filter)
    drivable = [t for t in solution.targets if t.drivable]
    n_samples = len(solution.targets)
    n_reachable = len(drivable)
    margins = [t.singularity_measure for t in drivable if t.singularity_measure is not None]

    warnings = [
        {
            "kind": w.kind,
            "target_index": w.target_index,
            "detail": w.detail,
            "value": w.value,
        }
        for w in solution.warnings
    ]

    return PlacementScore(
        reachable_fraction=(n_reachable / n_samples) if n_samples else 0.0,
        n_samples=n_samples,
        n_reachable=n_reachable,
        kinematic_margin=min(margins) if margins else None,
        mean_margin=(sum(margins) / len(margins)) if margins else None,
        warnings=warnings,
        sampling={
            "spacing_mm": spacing_mm,
            "n_length": n_length,
            "n_height": n_height,
        },
        reach_estimate=reach_estimate,
    )
