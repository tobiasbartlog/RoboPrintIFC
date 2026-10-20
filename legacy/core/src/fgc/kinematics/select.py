"""Konfigurationswahl entlang einer Bahn (Issue #11, Strang B).

Baut auf dem FK/IK-Kern (`opw.OpwKinematics`, Issue #7) auf und liefert der
Simulation (Strang C) fahrbare Gelenkfolgen: aus mehrdeutigen IK-Lösungen wird
je Target **deterministisch** und **bahnstetig** eine gewählte Gelenklösung
bestimmt (gleiche Bahn → gleiche Folge, keine Konfigurationssprünge zwischen
benachbarten Targets), gegen die Achsgrenzen der Roboterdefinition geprüft und
mit einem Singularitätsnähe-Maß bewertet.

Schnittstelle bleibt schmal (P3): Frame(s) rein, gewählte Gelenklösung(en) plus
Warnliste raus. Warnungen sind **Daten** (für das spätere
`Trajectory.meta.warnings`, Issue #12), keine Exceptions — *unfahrbar* ist nur
ein Target, für das keine Lösung innerhalb der Achsgrenzen existiert; es kommt
als Target ohne Gelenklösung samt Warnung zurück, nicht als Fehler.

Einheiten strikt nach ADR-006 (Gelenkwinkel in Radiant).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from fgc.domain.models import Frame
from fgc.kinematics.opw import ELBOW, SHOULDER, WRIST, OpwKinematics

#: Warnung ab diesem Singularitätsnähe-Maß (reziproke Konditionszahl, s.
#: ``OpwKinematics.singularity_measure``). Kalibriert oberhalb des harten
#: OPW-Singularitätszweigs: der Solver koppelt Achse 4/6 ab |j5| ≈ 1,24e-2 rad
#: (Maß ≈ 0,004); die Warnung feuert mit Marge davor, damit die frame-inexakte
#: Koppelzone stets angekündigt ist.
DEFAULT_SINGULARITY_WARN = 0.01

#: Art einer Warnung — Vokabular für ``ConfigWarning.kind``.
WarningKind = Literal["unreachable", "joint_limits", "singularity", "ik_config"]


@dataclass(frozen=True)
class IkConfigFilter:
    """Harter Filter über die 8 IK-Konfigurationszweige (Issue #129, ADR-024).

    Je Achse ein **Tri-State**: ``None`` = *auto* (kein Constraint, exakt das
    heutige Verhalten), ``False`` = *Zustand A* (Konfigurationsbit gelöscht),
    ``True`` = *Zustand B* (Konfigurationsbit gesetzt). Ein gesetzter Zustand
    schließt in :func:`select_along_path` **alle** Lösungen aus, deren Bit nicht
    passt — ein **harter Filter**, keine weiche Präferenz (verworfene Alternative
    in ADR-024: „warum hängt der Ellbogen trotz Vorgabe wieder unten?"). Bitschema
    wie ``opw.py``: Schulter=SHOULDER(1), Ellbogen=ELBOW(2), Handgelenk=WRIST(4).

    ``auto/auto/auto`` (alle ``None``) ist der **Regressionsanker**: :func:`allows`
    ist dann für jede Konfiguration wahr, die Bahnwahl bleibt bit-identisch zu
    heute (:meth:`is_auto` short-circuitet den Filter komplett).
    """

    shoulder: bool | None = None
    elbow: bool | None = None
    wrist: bool | None = None

    @property
    def is_auto(self) -> bool:
        """True, wenn keine Achse fixiert ist (kein Filter → heutiges Verhalten)."""
        return self.shoulder is None and self.elbow is None and self.wrist is None

    def allows(self, configuration: int) -> bool:
        """True, wenn ``configuration`` (Bitfeld) alle fixierten Achsen erfüllt."""
        for bit, want in (
            (SHOULDER, self.shoulder),
            (ELBOW, self.elbow),
            (WRIST, self.wrist),
        ):
            if want is not None and bool(configuration & bit) != want:
                return False
        return True

    @classmethod
    def from_block(cls, block: dict | None) -> IkConfigFilter:
        """Baut den Filter aus einem ``ik_config``-Block (``{"shoulder": "a"|"b", …}``).

        Die persistierte Form (process-params, Issue #129): je Achse ``"a"``
        (Zustand A → Bit 0/False), ``"b"`` (Zustand B → Bit 1/True) oder fehlend/
        ``None`` (auto). Ein leerer/fehlender Block ⇒ ``auto/auto/auto``.
        """
        block = block or {}

        def _tri(value: object) -> bool | None:
            if value is None:
                return None
            return str(value) == "b"

        return cls(
            shoulder=_tri(block.get("shoulder")),
            elbow=_tri(block.get("elbow")),
            wrist=_tri(block.get("wrist")),
        )


def config_to_block(configuration: int) -> dict[str, str]:
    """Übersetzt ein opw-Konfigurationsbitfeld in einen a/b-``ik_config``-Block.

    Die **Rückrichtung** zu :meth:`IkConfigFilter.from_block` (die es bislang 0×
    gab, Issue #200): je Achse liefert das *gesetzte* Bit den Zweig ``"b"``
    (Zustand B), das gelöschte ``"a"`` (Zustand A) — exakt die Umkehrung von
    ``from_block`` (dort ``"b"`` → Bit gesetzt/``True``). Bitschema wie ``opw.py``:
    Schulter=SHOULDER(1), Ellbogen=ELBOW(2), Handgelenk=WRIST(4). Das Ergebnis
    benennt **alle drei** Achsen (voller Block); Aufrufer, die nur eine Achse
    fixieren wollen (Config-Flip des Singularitäts-Advisors), picken den
    betreffenden Schlüssel heraus.

    Roundtrip-Garantie: ``IkConfigFilter.from_block(config_to_block(c)).allows(c)``
    ist für jedes ``c`` wahr und schließt jede andere Konfiguration aus (der volle
    Block fixiert alle drei Bits).
    """
    return {
        "shoulder": "b" if configuration & SHOULDER else "a",
        "elbow": "b" if configuration & ELBOW else "a",
        "wrist": "b" if configuration & WRIST else "a",
    }


@dataclass(frozen=True)
class ConfigWarning:
    """Eine Warnung als Datum (nicht als Exception) — Ziel: Trajectory.meta.

    ``target_index`` verweist auf das Target in der Eingabefolge; ``value`` trägt
    das gemessene Maß (Singularitätsnähe), soweit sinnvoll.
    """

    target_index: int
    kind: WarningKind
    detail: str
    value: float | None = None


@dataclass(frozen=True)
class SelectedTarget:
    """Gewählte Gelenklösung für ein Target (oder *unfahrbar*).

    ``joints_rad is None`` markiert ein unfahrbares Target (keine Lösung
    innerhalb der Achsgrenzen); dann sind auch ``configuration`` und
    ``singularity_measure`` None.
    """

    index: int
    joints_rad: tuple[float, float, float, float, float, float] | None
    configuration: int | None
    singularity_measure: float | None

    @property
    def drivable(self) -> bool:
        return self.joints_rad is not None


@dataclass(frozen=True)
class PathSolution:
    """Ergebnis der Konfigurationswahl für eine ganze Bahn.

    ``targets`` in Eingabereihenfolge, ``warnings`` gesammelt über alle Targets.
    """

    targets: list[SelectedTarget]
    warnings: list[ConfigWarning]

    @property
    def drivable(self) -> bool:
        """True, wenn jedes Target eine zulässige Gelenklösung hat."""
        return all(t.drivable for t in self.targets)


def _wrapped_delta(a: float, b: float) -> float:
    """Kürzeste Winkeldifferenz a−b in (−π, π] — robust über die ±π-Naht."""
    return math.atan2(math.sin(a - b), math.cos(a - b))


def joint_distance(q1: Sequence[float], q2: Sequence[float]) -> float:
    """Gelenkraum-Abstand zweier Konfigurationen (L2 über kürzeste Winkeldiffs).

    Über die ±π-Naht gemessen, damit ein rein numerischer Sprung der auf
    [−π, π] normierten IK-Lösung (z. B. 3,13 → −3,13) nicht als weite Bewegung
    zählt — Grundlage der Bahnstetigkeit.
    """
    return math.sqrt(sum(_wrapped_delta(a, b) ** 2 for a, b in zip(q1, q2, strict=True)))


def select_along_path(
    kin: OpwKinematics,
    frames: Iterable[Frame],
    *,
    seed: Sequence[float] | None = None,
    singularity_warn_below: float = DEFAULT_SINGULARITY_WARN,
    config_filter: IkConfigFilter | None = None,
) -> PathSolution:
    """Wählt entlang einer Frame-Folge je Target eine Gelenklösung (P3).

    Deterministisch und bahnstetig: Für jedes Target werden aus den bis zu acht
    IK-Lösungen die **erreichbaren und achsgrenz-konformen** herausgefiltert und
    daraus die dem Vorgänger im Gelenkraum **nächste** gewählt (erstes Target:
    nächste zum ``seed``, Standard = Nullstellung). Gleichstände werden über den
    Konfigurationsindex aufgelöst — dadurch ist die Lösungsfolge über Läufe
    hinweg reproduzierbar. Die Nächste-Nachbar-Wahl hält die Konfiguration
    entlang einer stetigen Bahn konstant (keine Konfigurationssprünge).

    Ein Target ohne zulässige Lösung wird als *unfahrbar* zurückgegeben
    (``joints_rad=None``) und erzeugt eine Warnung ``joint_limits`` (erreichbar,
    aber alle Lösungen außerhalb der Achsgrenzen) bzw. ``unreachable`` (Zielpose
    außerhalb des Arbeitsraums). Der Vorgänger-Bezug für das nächste Target
    bleibt die zuletzt erfolgreich gewählte Lösung, damit die Bahn über eine
    Lücke hinweg stetig bleibt. Liegt das Singularitätsnähe-Maß der gewählten
    Lösung unter ``singularity_warn_below``, kommt zusätzlich eine Warnung
    ``singularity`` mit dem gemessenen Wert.

    ``config_filter`` (Issue #129, ADR-024) beschränkt die zulässigen
    IK-Konfigurationszweige **hart**: fixierte Achsen (Schulter/Ellbogen/
    Handgelenk) schließen alle Lösungen mit falschem Bit aus. Bleibt an einem
    Bahnpunkt keine zulässige Lösung übrig, obwohl er ohne die Vorgabe fahrbar
    wäre, wird er *unter der Vorgabe unerreichbar*: Warnung ``ik_config``, Target
    ohne Gelenklösung (kein Gate — die Bahn bleibt stetig, US 14). ``None`` oder
    ``auto/auto/auto`` ist der **Regressionsanker**: der Filter greift nicht, die
    Bahnwahl bleibt bit-identisch (``IkConfigFilter.is_auto``).
    """
    n = kin.params.n_joints
    if seed is None:
        prev: tuple[float, ...] = (0.0,) * n
    else:
        prev = tuple(float(x) for x in seed)

    filtering = config_filter is not None and not config_filter.is_auto

    targets: list[SelectedTarget] = []
    warnings: list[ConfigWarning] = []

    for i, frame in enumerate(frames):
        solutions = kin.inverse(frame)
        valid = [
            s for s in solutions if not s.unreachable and kin.in_limits(s.joints_rad)
        ]
        if not valid:
            reachable = any(not s.unreachable for s in solutions)
            if reachable:
                warnings.append(
                    ConfigWarning(
                        i,
                        "joint_limits",
                        "keine IK-Lösung innerhalb der Achsgrenzen",
                    )
                )
            else:
                warnings.append(
                    ConfigWarning(
                        i,
                        "unreachable",
                        "Zielpose außerhalb des Arbeitsraums (keine IK-Lösung)",
                    )
                )
            targets.append(SelectedTarget(i, None, None, None))
            continue

        # Harter IK-Konfigurationsfilter (Issue #129, ADR-024): gesetzte Achsen
        # schließen Lösungen mit falschem Bit aus. Bleibt nichts übrig, ist der
        # Bahnpunkt *unter der Vorgabe* unerreichbar → Warnung ``ik_config``,
        # Target ohne Gelenklösung (kein Gate). Der ``auto/auto/auto``-Fall ist
        # oben ausgeschlossen (``filtering``) — dann bleibt ``valid`` unangetastet
        # und die Bahnwahl ist bit-identisch zu heute (Regressionsanker).
        if filtering:
            allowed = [s for s in valid if config_filter.allows(s.configuration)]
            if not allowed:
                warnings.append(
                    ConfigWarning(
                        i,
                        "ik_config",
                        "IK-Konfiguration schließt alle Lösungen dieses Bahnpunkts aus",
                    )
                )
                targets.append(SelectedTarget(i, None, None, None))
                continue
            valid = allowed

        # Deterministische Nächste-Nachbar-Wahl: primär kleinster Gelenkabstand
        # zum Vorgänger, bei (gerundetem) Gleichstand kleinster Konfig-Index.
        chosen = min(
            valid,
            key=lambda s: (round(joint_distance(s.joints_rad, prev), 9), s.configuration),
        )
        measure = kin.singularity_measure(chosen.joints_rad)
        if measure < singularity_warn_below:
            warnings.append(
                ConfigWarning(
                    i,
                    "singularity",
                    f"Nähe zur Singularität (Maß {measure:.4f})",
                    measure,
                )
            )
        targets.append(
            SelectedTarget(i, chosen.joints_rad, chosen.configuration, measure)
        )
        prev = chosen.joints_rad

    return PathSolution(targets=targets, warnings=warnings)
