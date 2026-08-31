"""ReachabilityMap: 4D-Reichweitenkarte nach RM4D-Muster aus der OPW-IK (PRD #183, #210).

Arbeitspaket 2 („Gratiswissen"): eine **einmalig offline gebaute, binäre
4D-Karte** des M1013 beantwortet „ist diese Flanschpose von dieser Basisposition
erreichbar?" in Mikrosekunden — als **Vorfilter** für Platzierung (#214) und
Zerlegungs-Scorer (#216). Das Urteil bleibt bei der Prüf-Tür (Ehrlichkeitsregel
ADR-007/#164): die Karte kennt weder Hindernisse noch den Druckstand.

**RM4D-Muster** (Rudorfer 2024, arXiv 2410.06968; Verifikation
``docs/recherche/2026-07-10-adaption-chunking-literatur.md``): unter zwei
Annahmen — (1) endlose Basisachse J1, (2) endloses letztes Handgelenk in
Anflugrichtung — kollabiert die 6D-Erreichbarkeitsfrage auf vier Koordinaten:

- ``p_z``  — Höhe der Pose über der Basis (mm),
- ``alpha`` — Anflugwinkel der Flansch-z-Achse zur Vertikalen (rad, 0 = auf,
  π = Düse senkrecht nach unten),
- ``(x_t, y_t)`` — die **kanonische Basisposition**: der horizontale Versatz
  Basis−Pose, gedreht in das Azimut-Frame der Anflugrichtung
  (:func:`canonical_coords`; bei senkrechtem Anflug ist das Azimut entartet und
  die Kanonisierung lässt den Versatz ungedreht — die Karte ist dort
  rotationssymmetrisch, jede Zelle wird exakt ausgewertet).

Der M1013 erfüllt beide Annahmen (J1/J6 = ±360°) und liegt damit näher am
RM4D-Ideal als der im Paper geprüfte Franka. **Eine** Datenstruktur beantwortet
vorwärts (:meth:`ReachabilityMap.is_reachable`) **und** invers
(:meth:`ReachabilityMap.base_positions`) ohne separaten Inversionsschritt; der
Standplatz für eine ganze Höhenreihe entsteht als punktweises **Minimum über die
Posenmenge** (:meth:`ReachabilityMap.min_over_poses`, Vahrenkamp Gl. 3 /
RM4D IV-D — Grundlage von US 6).

**Aufbau direkt-invers über die analytische OPW-IK** (keine
Zufalls-Sampling-Orgie): jede 4D-Zelle wird an ihrem Knoten exakt ausgewertet —
Repräsentant-Pose (:func:`representative_frame`) → OPW-IK → „existiert eine
Lösung innerhalb der Achsgrenzen?". Der Build nutzt dabei eine belegte
Reduktion: beim M1013 sind **alle Achsen außer J3 Vollkreis-Achsen** (Limits
⊇ ±π; auf [−π, π] normierte IK-Lösungen sind dort nie limitiert), Erreichbarkeit
hängt damit nur vom Positionszweig der OPW-IK ab (Handgelenkzentrum, 4
Schulter/Ellbogen-Zweige) — exakt dieselben Formeln wie
:meth:`fgc.kinematics.opw.OpwKinematics.inverse_matrix`, vektorisiert. Die
Voraussetzung wird beim Build **hart geprüft** (klarer Fehler statt stiller
Falschkarte); der Test ``test_reachability.py`` prüft die Karte am Raster gegen
die skalare OPW-IK als Ground Truth (keine falschen Negative im Kartenraster).

**Frame-Quelle** ist der #201-Seam: :func:`fgc.placement.evaluate.flange_targets`
liefert Flansch-Ziele in **Basiskoordinaten** (→ Vorwärtsabfrage) plus
``t_wall_base``; :func:`frames_in_wall` bringt die Ziele damit ins Wandsystem
(→ Inversabfrage). Die Standplatz-Semantik folgt ADR-025: Kandidaten-Basen sind
aufrecht (beliebiger Yaw — J1-Invarianz), ``base_z_mm`` ist die Aufstellhöhe
absolut über dem Boden (Boden = Wandfuß ``z = 0``, Issue #132); die Umrechnung
Abstand-ab-Wandfläche ↔ y-Koordinate lebt weiter allein in
``base_position_in_wall``/``standoff_from_base_y``.

Persistiert wird die Karte als versioniertes Artefakt mit Provenienz (US 17,
ADR-004) unter ``robots/reachability/<robot>/`` (``values.npy`` = packbits +
``manifest.json``; Skript ``core/scripts/build_reachability_map.py``). Laden
validiert gegen den Roboterkatalog: Formatstand, Robotername und der
SHA-256-Fingerabdruck der Katalog-Kinematik (:func:`kinematics_fingerprint`) —
falscher Roboter oder geänderte Kinematik schlagen klar fehl (US 18), kein
stiller Falschfilter.

Einheiten strikt nach ADR-006: mm, Radiant, Quaternionen [w, x, y, z].
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from fgc.domain.models import Frame
from fgc.domain.robot import Kinematics, RobotDef
from fgc.kinematics.opw import OpwKinematics, _quat_to_rot, _rot_to_quat
from fgc.paths import ROBOTS_DIR

#: Default-Zellkante (mm) der p_z/x_t/y_t-Achsen — RM4D-Papierauflösung (5 cm).
DEFAULT_CELL_MM = 50.0

#: Default-Knotenzahl der alpha-Achse: 37 Knoten über [0, π] = 5°-Schritte (RM4D).
DEFAULT_N_ALPHA = 37

#: Formatstand des Artefakts — Erhöhung invalidiert alte Builds beim Laden.
RM_FORMAT_VERSION = 1

#: Ablage: ``robots/reachability/<robot>/`` mit Werten + Provenienz-Manifest.
RM_DIR_NAME = "reachability"
RM_MANIFEST_NAME = "manifest.json"
RM_VALUES_NAME = "values.npy"

BUILD_HINT = "Neu bauen mit  .venv/Scripts/python.exe core/scripts/build_reachability_map.py"

#: Unterhalb dieser Horizontalnorm der Anflugrichtung gilt das Azimut als
#: entartet (senkrechter Anflug) — die Kanonisierung lässt den Versatz ungedreht.
AZIMUTH_EPS = 1e-9

#: Achsen, deren Limits der Reduktions-Build als Vollkreis voraussetzt (alle
#: außer J3): auf [−π, π] normierte Lösungen sind dort nie limitiert.
_FULL_CIRCLE_AXES = (0, 1, 3, 4, 5)

#: Toleranz der Achsgrenzprüfung — identisch zu ``OpwKinematics.in_limits``.
_LIMIT_TOL = 1e-10


class ReachabilityProvenanceError(ValueError):
    """Karten-Provenienz passt nicht zum Roboterkatalog (US 18) — klarer Fehler."""


def kinematics_fingerprint(kin: Kinematics) -> str:
    """SHA-256 über die erreichbarkeitsrelevanten Kinematik-Parameter des Katalogs.

    Der **Buildstand** der Karten-Provenienz: ändert sich die Katalog-Kinematik
    (DH-Parameter oder Achsgrenzen), passt der Fingerabdruck nicht mehr und das
    Laden schlägt klar fehl statt still mit einer Falschkarte zu filtern (US 18).
    Geschwindigkeits-/Beschleunigungslimits bleiben außen vor (reine Zeitdaten).
    """
    payload = {
        "solver": kin.solver,
        "a_mm": list(kin.a_mm),
        "d_mm": list(kin.d_mm),
        "alpha_rad": list(kin.alpha_rad),
        "joint_limits_rad": [list(pair) for pair in kin.joint_limits_rad],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def canonical_coords(frame: Frame) -> tuple[float, float, float, float]:
    """RM4D-Koordinaten ``(p_z, alpha, x_t, y_t)`` einer Flanschpose in Basiskoordinaten.

    ``p_z`` = Posenhöhe über der Basis; ``alpha`` = Winkel der Flansch-z-Achse
    (Anflugrichtung) zur Vertikalen ∈ [0, π]; ``(x_t, y_t)`` = horizontaler
    Versatz **Basis − Pose**, gedreht in das Azimut-Frame der Anflugrichtung.
    Bei senkrechtem Anflug (Horizontalnorm < :data:`AZIMUTH_EPS`) bleibt der
    Versatz ungedreht — die Karte ist dort rotationssymmetrisch (jede Zelle wird
    beim Build exakt ausgewertet, die Wahl kostet keine Korrektheit am Knoten).
    """
    px, py, pz = frame.pos_mm
    rot = _quat_to_rot(frame.quat)
    ax, ay, az = float(rot[0, 2]), float(rot[1, 2]), float(rot[2, 2])
    h = math.hypot(ax, ay)
    alpha = math.atan2(h, az)
    if h > AZIMUTH_EPS:
        cth, sth = ax / h, ay / h
    else:
        cth, sth = 1.0, 0.0
    ox, oy = -px, -py  # Basis (Ursprung) − Pose, horizontal
    x_t = cth * ox + sth * oy
    y_t = -sth * ox + cth * oy
    return pz, alpha, x_t, y_t


def representative_frame(p_z: float, alpha: float, x_t: float, y_t: float) -> Frame:
    """Repräsentant-Pose einer 4D-Zelle in Basiskoordinaten (Azimut = 0).

    Die **eine** Konvention, mit der der Build jede Zelle auswertet: Anflug
    ``a = (sin α, 0, cos α)`` (Rotation um die y-Achse um α), Position aus dem
    kanonischen Versatz (Basis im Ursprung ⇒ Pose bei ``(−x_t, −y_t, p_z)``).
    Roundtrip-Garantie: :func:`canonical_coords` dieser Pose reproduziert die
    Zellkoordinaten (auch im entarteten Fall α ∈ {0, π}).
    """
    c, s = math.cos(alpha), math.sin(alpha)
    rot = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    return Frame(pos_mm=(-x_t, -y_t, p_z), quat=_rot_to_quat(rot))


def frames_in_wall(frames: Iterable[Frame], t_wall_base: Any) -> list[Frame]:
    """Flansch-Ziele aus Basis- in Wandkoordinaten — der #201-Seam zur Inversabfrage.

    ``frames``/``t_wall_base`` kommen direkt aus
    :func:`fgc.placement.evaluate.flange_targets` (``FlangeTargets.frames`` +
    ``FlangeTargets.t_wall_base``): die eine Wand→Basis-Plan-Transformation wird
    hier **konsumiert, nicht dupliziert** — Vorwärtsabfrage (Basisziele) und
    Inversabfrage (Wandziele) sprechen über dieselbe Kette.
    """
    t = np.asarray(t_wall_base, dtype=float)
    result: list[Frame] = []
    for f in frames:
        tb = np.eye(4)
        tb[:3, :3] = _quat_to_rot(f.quat)
        tb[:3, 3] = f.pos_mm
        tw = t @ tb
        result.append(
            Frame(
                pos_mm=(float(tw[0, 3]), float(tw[1, 3]), float(tw[2, 3])),
                quat=_rot_to_quat(tw[:3, :3]),
            )
        )
    return result


def _require_full_circle_axes(params: Kinematics) -> None:
    """Belegt die Reduktions-Voraussetzung des direkt-inversen Builds (hart).

    Alle Achsen außer J3 müssen Vollkreis-Achsen sein (Limits ⊇ [−π, π]): dann
    ist eine auf [−π, π] normierte IK-Lösung dort nie limitiert, Erreichbarkeit
    hängt nur vom Positionszweig der OPW-IK ab — und die RM4D-Annahmen (J1-Yaw-
    und J6-Roll-Invarianz) gelten **exakt** statt näherungsweise. Ein Roboter,
    der das nicht erfüllt, bekommt keine stille Falschkarte, sondern diesen Fehler.
    """
    for axis in _FULL_CIRCLE_AXES:
        lo, hi = params.joint_limits_rad[axis]
        if lo > -math.pi + 1e-9 or hi < math.pi - 1e-9:
            raise ValueError(
                f"ReachabilityMap.build setzt Vollkreis-Limits auf Achse {axis + 1} voraus "
                f"(hat [{lo:.3f}, {hi:.3f}] rad) — RM4D-Annahmen/Reduktion nicht erfüllt; "
                "direkt-inverser Build für diesen Roboter nicht zulässig."
            )


def _acos_domain(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vektorisiertes ``_safe_acos``: (Winkel, war_ausserhalb) wie ``opw._safe_acos``."""
    ok = (values >= -1.0) & (values <= 1.0)  # NaN/±inf fallen wie im Skalar auf False
    clipped = np.clip(np.nan_to_num(values, nan=2.0, posinf=2.0, neginf=-2.0), -1.0, 1.0)
    return np.where(ok, np.arccos(clipped), 0.0), ~ok


def _wrap_pi(values: np.ndarray) -> np.ndarray:
    """Normierung auf [−π, π) — vektorisiertes Gegenstück zur Skalar-Schleife."""
    return np.mod(values + math.pi, 2.0 * math.pi) - math.pi


def _reachable_wrist(params: Kinematics, cx: Any, cy: Any, cz: Any) -> np.ndarray:
    """Positionszweig der OPW-IK, vektorisiert: erreichbar je Handgelenkzentrum.

    Zeilengleiche Vektorisierung der Formeln aus
    :meth:`fgc.kinematics.opw.OpwKinematics.inverse_matrix` für die vier
    Schulter/Ellbogen-Zweige (das Wrist-Bit ändert nur j4–j6 — Vollkreis-Achsen,
    s. :func:`_require_full_circle_axes`). Erreichbar ⇔ ein Zweig ohne
    Domänenfehler, dessen Achse-3-Winkel (Signs/Start-Abbildung + Normierung wie
    im Skalar) innerhalb der Achsgrenzen liegt.
    """
    a = params.a_mm
    d = params.d_mm
    a1, a2 = a[0], -a[2]
    c1, c2, c3 = d[0], a[1], d[3]
    b = -d[1]
    lo3, hi3 = params.joint_limits_rad[2]

    cx = np.asarray(cx, dtype=float)
    cy = np.asarray(cy, dtype=float)
    cz = np.asarray(cz, dtype=float)

    nx1_sq = cx * cx + cy * cy - b * b
    u0 = nx1_sq < 0.0
    nx1 = np.sqrt(np.maximum(nx1_sq, 0.0)) - a1

    tmp3 = cz - c1
    kappa_2 = a2 * a2 + c3 * c3
    c2_2 = c2 * c2
    s1_2 = nx1 * nx1 + tmp3 * tmp3
    tmp4 = nx1 + 2.0 * a1
    s2_2 = tmp4 * tmp4 + tmp3 * tmp3
    tmp9 = 2.0 * c2 * math.sqrt(kappa_2)
    tmp10 = math.atan2(a2, c3)

    with np.errstate(divide="ignore", invalid="ignore"):
        _tmp13, nan13 = _acos_domain((s1_2 + c2_2 - kappa_2) / (2.0 * np.sqrt(s1_2) * c2))
        tmp11, nan11 = _acos_domain((s1_2 - c2_2 - kappa_2) / tmp9)
        _tmp15, nan15 = _acos_domain((s2_2 + c2_2 - kappa_2) / (2.0 * np.sqrt(s2_2) * c2))
        tmp12, nan12 = _acos_domain((s2_2 - c2_2 - kappa_2) / tmp9)

    unreachable_s0 = u0 | nan13 | nan11
    unreachable_s1 = u0 | nan15 | nan12

    reachable: np.ndarray | None = None
    for unreachable, j2 in (
        (unreachable_s0, tmp11 - tmp10),  # Schulter A, Ellbogen A
        (unreachable_s0, -tmp11 - tmp10),  # Schulter A, Ellbogen B
        (unreachable_s1, -tmp12 - tmp10),  # Schulter B, Ellbogen A
        (unreachable_s1, tmp12 - tmp10),  # Schulter B, Ellbogen B
    ):
        joint3 = _wrap_pi(-j2 + math.pi / 2.0)  # _SIGNS[2]·j2 + _START[2] (opw)
        ok = ~unreachable & (joint3 >= lo3 - _LIMIT_TOL) & (joint3 <= hi3 + _LIMIT_TOL)
        reachable = ok if reachable is None else reachable | ok
    assert reachable is not None
    return reachable


@dataclass(frozen=True)
class ReachabilityMap:
    """Binäre 4D-Reichweitenkarte ``(p_z, alpha, x_t, y_t)`` (Semantik s. Modul-Docstring).

    ``values``: bool-Gitter ``(n_side, n_alpha, n_side, n_side)`` über den
    Knoten ``p_z/x_t/y_t ∈ {−extent, …, +extent}`` (Schritt ``cell_mm``) und
    ``alpha ∈ {0, …, π}`` (Schritt ``alpha_step_rad``). Abfragen runden auf den
    nächsten Knoten — **am Knoten selbst ist die Antwort IK-exakt** (direkt-
    inverser Build), dazwischen gilt die Rasterauflösung (Vorfilter, kein Urteil).
    """

    cell_mm: float
    alpha_step_rad: float
    extent_mm: float
    values: Any
    robot: str | None = None
    manifest: dict[str, Any] = field(default_factory=dict)

    # -- Aufbau (direkt-invers über die OPW-IK) -------------------------------

    @classmethod
    def build(
        cls,
        kin: OpwKinematics,
        *,
        cell_mm: float = DEFAULT_CELL_MM,
        n_alpha: int = DEFAULT_N_ALPHA,
    ) -> ReachabilityMap:
        """Baut die Karte, jede Zelle exakt am Knoten über die OPW-IK ausgewertet.

        Das Gitter deckt den vollen Arm ab: ``extent = ⌈(Σ|a|+Σ|d|)/cell⌉·cell``
        ist eine obere Schranke jeder erreichbaren Posendistanz — außerhalb des
        Gitters ist „unerreichbar" exakt, nicht konservativ. Deterministisch:
        gleiche Kinematik + Auflösung → bitgleiche Karte (ADR-004-Geist).
        """
        params = kin.params
        _require_full_circle_axes(params)
        if n_alpha < 2:
            raise ValueError(f"n_alpha muss ≥ 2 sein, ist {n_alpha}")
        reach = sum(abs(x) for x in params.a_mm) + sum(abs(x) for x in params.d_mm)
        extent = math.ceil(reach / cell_mm) * cell_mm
        m = int(round(extent / cell_mm))
        n_side = 2 * m + 1
        alpha_step = math.pi / (n_alpha - 1)

        axis = (np.arange(n_side) - m) * cell_mm
        alphas = np.arange(n_alpha) * alpha_step
        sin_a, cos_a = np.sin(alphas), np.cos(alphas)
        c4 = params.d_mm[5]

        # Handgelenkzentrum je Zelle (Repräsentant, Azimut 0): Pose bei
        # (−x_t, −y_t, p_z), Anflug (sin α, 0, cos α), c = p − c4·a.
        cx = (-axis)[None, :, None] - c4 * sin_a[:, None, None]  # (α, x, 1)
        cy = np.broadcast_to((-axis)[None, None, :], (n_alpha, n_side, n_side))
        values = np.empty((n_side, n_alpha, n_side, n_side), dtype=bool)
        for iz in range(n_side):
            czs = (axis[iz] - c4 * cos_a)[:, None, None]  # (α, 1, 1)
            values[iz] = _reachable_wrist(params, cx, cy, czs)

        return cls(
            cell_mm=float(cell_mm),
            alpha_step_rad=alpha_step,
            extent_mm=float(extent),
            values=values,
        )

    # -- Gitter ----------------------------------------------------------------

    @property
    def _m(self) -> int:
        return int(round(self.extent_mm / self.cell_mm))

    @property
    def n_alpha(self) -> int:
        return int(self.values.shape[1])

    def _side_index(self, coord: float) -> int | None:
        i = int(round(coord / self.cell_mm)) + self._m
        return i if 0 <= i < self.values.shape[0] else None

    def _alpha_index(self, alpha: float) -> int:
        return min(max(int(round(alpha / self.alpha_step_rad)), 0), self.n_alpha - 1)

    # -- Vorwärtsabfrage: Pose erreichbar von der Basis? ------------------------

    def is_reachable(self, frame: Frame) -> bool:
        """Vorwärtsabfrage für eine Flanschpose in **Basiskoordinaten**.

        Genau die Frames, die :func:`fgc.placement.evaluate.flange_targets`
        liefert (#201). Außerhalb des Gitters ⇒ False (exakt: das Gitter deckt
        die volle Armlänge ab).
        """
        p_z, alpha, x_t, y_t = canonical_coords(frame)
        iz = self._side_index(p_z)
        ix = self._side_index(x_t)
        iy = self._side_index(y_t)
        if iz is None or ix is None or iy is None:
            return False
        return bool(self.values[iz, self._alpha_index(alpha), ix, iy])

    def reachable_fraction(self, frames: Iterable[Frame]) -> float:
        """Anteil erreichbarer Posen (Basiskoordinaten) — Kartenschätzer für US 7."""
        total = 0
        hits = 0
        for f in frames:
            total += 1
            hits += self.is_reachable(f)
        return hits / total if total else 0.0

    # -- Inversabfrage: Basispositionen für eine Pose ---------------------------

    def base_positions(
        self, frame: Frame, base_xy_mm: Sequence[Sequence[float]] | Any, base_z_mm: float
    ) -> np.ndarray:
        """Inversabfrage: von welchen Kandidaten-Basispositionen ist die Pose erreichbar?

        ``frame`` in **Wandkoordinaten** (:func:`frames_in_wall`), ``base_xy_mm``
        = ``(N, 2)`` Kandidaten (x, y im Wandsystem — die y-Koordinate kommt aus
        ``base_position_in_wall``, ADR-025), ``base_z_mm`` = Aufstellhöhe absolut
        über dem Boden (Issue #132). Basen gelten als aufrecht mit beliebigem Yaw
        (J1-Invarianz — RM4D-Annahme 1). Rückgabe: bool ``(N,)``; dieselbe
        Struktur wie die Vorwärtsabfrage, kein separater Inversionsschritt.
        """
        xy = np.asarray(base_xy_mm, dtype=float).reshape(-1, 2)
        out = np.zeros(len(xy), dtype=bool)
        px, py, pz = frame.pos_mm
        rot = _quat_to_rot(frame.quat)
        ax, ay, az = float(rot[0, 2]), float(rot[1, 2]), float(rot[2, 2])
        h = math.hypot(ax, ay)
        if h > AZIMUTH_EPS:
            cth, sth = ax / h, ay / h
        else:
            cth, sth = 1.0, 0.0
        iz = self._side_index(pz - base_z_mm)
        if iz is None:
            return out
        ia = self._alpha_index(math.atan2(h, az))

        ox = xy[:, 0] - px
        oy = xy[:, 1] - py
        x_t = cth * ox + sth * oy
        y_t = -sth * ox + cth * oy
        ix = np.rint(x_t / self.cell_mm).astype(int) + self._m
        iy = np.rint(y_t / self.cell_mm).astype(int) + self._m
        n = self.values.shape[0]
        in_grid = (ix >= 0) & (ix < n) & (iy >= 0) & (iy < n)
        out[in_grid] = self.values[iz, ia, ix[in_grid], iy[in_grid]]
        return out

    def min_over_poses(
        self,
        frames: Iterable[Frame],
        base_xy_mm: Sequence[Sequence[float]] | Any,
        base_z_mm: float,
    ) -> np.ndarray:
        """Minimum über die Posenmenge: Basispositionen, die **alle** Posen erreichen.

        Punktweises Minimum (= UND) der binären Inversabfragen über z. B. alle
        Bahnposen einer Höhenreihe (US 6: kein Umsetzen mitten in der Reihe;
        Vahrenkamp Gl. 3 / RM4D IV-D). Leere Posenmenge ⇒ alles True (neutrales
        Element — Aufrufer entscheiden, ob das ein Fehler ist).
        """
        xy = np.asarray(base_xy_mm, dtype=float).reshape(-1, 2)
        out = np.ones(len(xy), dtype=bool)
        for f in frames:
            out &= self.base_positions(f, xy, base_z_mm)
            if not out.any():
                break
        return out


# ---------------------------------------------------------------------------
# Persistenz: Artefakt mit Provenienz (US 17), Laden katalog-validiert (US 18)
# ---------------------------------------------------------------------------


def reachability_dir(robot_name: str, robots_dir: Path | None = None) -> Path:
    """Ablageordner der Reichweitenkarte eines Roboters."""
    return (robots_dir or ROBOTS_DIR) / RM_DIR_NAME / robot_name


def save_reachability_map(
    rmap: ReachabilityMap,
    robot_name: str,
    kinematics: Kinematics,
    robots_dir: Path | None = None,
    *,
    generator: str = "core/scripts/build_reachability_map.py",
) -> Path:
    """Schreibt Karte + Provenienz-Manifest (US 17, ADR-004) — deterministisch.

    ``kinematics`` ist die Katalog-Kinematik, aus der die Karte gebaut wurde —
    ihr Fingerabdruck (:func:`kinematics_fingerprint`) ist der Buildstand, gegen
    den :func:`load_reachability_map` validiert. Keine Zeitstempel, sortierte
    JSON-Keys, packbits-Ablage: zweifacher Lauf → bitgleich.
    """
    directory = reachability_dir(robot_name, robots_dir)
    directory.mkdir(parents=True, exist_ok=True)
    values = np.asarray(rmap.values, dtype=bool)
    np.save(directory / RM_VALUES_NAME, np.packbits(values.astype(np.uint8).ravel()))
    manifest = {
        "_comment": f"Erzeugt von {generator} — nicht editieren.",
        "rm_format_version": RM_FORMAT_VERSION,
        "robot": robot_name,
        "units": "mm/rad (ADR-006)",
        "coords": (
            "RM4D (p_z, alpha, x_t, y_t): Posenhoehe ueber Basis, Anflugwinkel zur "
            "Vertikalen, kanonische Basisposition relativ zur Pose (Azimut-Frame der "
            "Anflugrichtung; senkrechter Anflug ungedreht)."
        ),
        "semantics": (
            "Binaer, direkt-invers ueber die analytische OPW-IK: Zelle wahr = die "
            "Repraesentant-Pose des Zellknotens hat eine IK-Loesung innerhalb der "
            "Achsgrenzen. Vorfilter — das Urteil bleibt bei der Pruef-Tuer."
        ),
        "cell_mm": rmap.cell_mm,
        "alpha_step_rad": rmap.alpha_step_rad,
        "n_alpha": rmap.n_alpha,
        "extent_mm": rmap.extent_mm,
        "shape": list(values.shape),
        "values_file": RM_VALUES_NAME,
        "packing": "numpy packbits (bool, C-Ordnung)",
        "n_cells": int(values.size),
        "n_reachable": int(values.sum()),
        "kinematics_sha256": kinematics_fingerprint(kinematics),
        "generator": generator,
        "source": f"robots/{robot_name}.json (kinematics-Block) via fgc.kinematics.opw",
    }
    (directory / RM_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return directory


def load_reachability_map(robot_name: str, robots_dir: Path | None = None) -> ReachabilityMap:
    """Lädt die Reichweitenkarte und validiert die Provenienz gegen den Katalog.

    Prüft Formatstand, Robotername und den Kinematik-Fingerabdruck des aktuellen
    Roboterkatalogs (``robots/<name>.json``): falscher Roboter oder eine seit dem
    Build geänderte Kinematik schlagen mit :class:`ReachabilityProvenanceError`
    samt Bauanleitung fehl (US 18) — kein stiller Falschfilter.
    """
    directory = reachability_dir(robot_name, robots_dir)
    manifest_path = directory / RM_MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Keine Reichweitenkarte für {robot_name!r} unter {directory}. {BUILD_HINT}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    fmt = manifest.get("rm_format_version")
    if fmt != RM_FORMAT_VERSION:
        raise ReachabilityProvenanceError(
            f"Reichweitenkarten-Formatstand {fmt!r} wird nicht unterstützt "
            f"(erwartet {RM_FORMAT_VERSION}). {BUILD_HINT}"
        )
    if manifest.get("robot") != robot_name:
        raise ReachabilityProvenanceError(
            f"Reichweitenkarte gehört zu Roboter {manifest.get('robot')!r}, "
            f"erwartet {robot_name!r} — falsche Provenienz. {BUILD_HINT}"
        )
    robot = RobotDef.load(robot_name, robots_dir)
    if robot.kinematics is None:
        raise ReachabilityProvenanceError(
            f"Roboter {robot_name!r} trägt keine Kinematik-Parameter — eine "
            f"Reichweitenkarte ist dafür nicht validierbar. {BUILD_HINT}"
        )
    fingerprint = kinematics_fingerprint(robot.kinematics)
    if manifest.get("kinematics_sha256") != fingerprint:
        raise ReachabilityProvenanceError(
            "Reichweitenkarten-Buildstand veraltet: die Katalog-Kinematik von "
            f"{robot_name!r} hat sich seit dem Build geändert. {BUILD_HINT}"
        )

    shape = tuple(int(x) for x in manifest["shape"])
    cell_mm = float(manifest["cell_mm"])
    extent_mm = float(manifest["extent_mm"])
    alpha_step = float(manifest["alpha_step_rad"])
    n_side = 2 * int(round(extent_mm / cell_mm)) + 1
    if (
        len(shape) != 4
        or shape[0] != n_side
        or shape[2] != n_side
        or shape[3] != n_side
        or shape[1] != int(manifest["n_alpha"])
        or abs(alpha_step * (shape[1] - 1) - math.pi) > 1e-9
    ):
        raise ReachabilityProvenanceError(
            f"Reichweitenkarte {robot_name!r}: Gitterform {shape} passt nicht zu den "
            f"Manifest-Parametern (cell {cell_mm} mm, extent {extent_mm} mm, "
            f"n_alpha {manifest.get('n_alpha')}). {BUILD_HINT}"
        )
    packed = np.load(directory / manifest.get("values_file", RM_VALUES_NAME))
    n_cells = int(np.prod(shape))
    if int(packed.size) * 8 < n_cells:
        raise ReachabilityProvenanceError(
            f"Reichweitenkarte {robot_name!r}: Wertedatei zu klein für Form {shape}. "
            f"{BUILD_HINT}"
        )
    values = np.unpackbits(packed, count=n_cells).reshape(shape).astype(bool)
    return ReachabilityMap(
        cell_mm=cell_mm,
        alpha_step_rad=alpha_step,
        extent_mm=extent_mm,
        values=values,
        robot=robot_name,
        manifest=manifest,
    )
