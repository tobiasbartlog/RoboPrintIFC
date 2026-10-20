"""Kollisions-Advisor: gerankte Optionsliste per Neu-Simulation (Issue #130, ADR-024 Punkt 5).

Das Gegenstück zum Singularitäts-Advisor (ADR-020, ``fgc.placement.advisor``) für
**Kollisionsbefunde** — mit dem einen prägenden Unterschied: der Advisor liefert
eine **gerankte Liste** gangbarer Optionen (das gewünschte „Menü"), nicht einen
Einzelvorschlag. Er läuft **auf Knopfdruck** (teuer: je Kandidat eine
Neu-Simulation) und probiert drei Hebel mit **derselben** Simulations-/Bewertungs-
Maschinerie — *keine* Parallel-Metrik (ADR-024): er liest denselben
``meta.collision``-Befund (Issue #127), den jede Simulation ohnehin erzeugt.

Die drei Hebel:

- **IK-Konfiguration** (S4-Schalter, Issue #129): ein anderer Lösungszweig
  (Schulter/Ellbogen/Handgelenk je ``a``/``b``) verlegt den Arm im Raum, ohne
  Bahn oder Platzierung zu ändern. Schreibstelle: ``process_params.ik_config``.
- **Kipp/Lead-Sweep**: ein bahn-relativer Anstellwinkel dreht Flansch/Arm aus dem
  Hindernis. Schreibstelle: ``process_params.orientation``.
- **Platzierung**: eine andere Basis-Lage (Abstand/Aufstellhöhe) schafft
  Freiraum. Schreibstelle: ``placement-override`` des Teils.

**Reinheit / Modularität.** Dieses Modul ist DOM-/IO-/Geo-frei und von der realen
Simulation über ein ``simulate``-Callable *entkoppelt*: es bekommt einen
Basis-Befund und eine Funktion ``Override → Befund`` gereicht und rankt. So ist es
schnell und isoliert testbar (synthetisches ``simulate``); in der Produktion füttert
die Aktion (``fgc.pipeline.actions.advise_collision``) die *echte* Slice+Trajektorien+
Befund-Kette hinein. Der Advisor **urteilt** nur; geschrieben wird ausschließlich
über die bestehenden Setter (ADR-016) — jede Option trägt die dazu passende
**Schreibstellen-Nutzlast** (``write``).

**Determinismus.** Gleiche Eingaben ⇒ gleiche Reihenfolge: nur Optionen, die die
Kollision nachweislich beseitigen oder den minimalen Abstand vergrößern (US 19),
erscheinen; sortiert nach (kollisionsfrei zuerst, dann Marge absteigend, dann feste
Kandidatenreihenfolge als stabiler Tiebreak).

Einheiten strikt nach ADR-006 (Abstände/Längen in Millimeter, Winkel als UI-naher Grad).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

#: Vokabular der Hebel (welche Schreibstelle die Option anwendet).
LeverKind = Literal["ik_config", "kipp_lead", "placement"]

#: Kipp-Deltas (Grad), die der Sweep um den aktuellen Kipp probiert.
KIPP_DELTAS_DEG: tuple[float, ...] = (-20.0, -10.0, 10.0, 20.0)

#: Lead-Deltas (Grad) — grober als Kipp (Kipp dreht stärker aus der Wand heraus).
LEAD_DELTAS_DEG: tuple[float, ...] = (-20.0, 20.0)

#: Abstands-Deltas (mm): die Basis vor der Wandfront zurücksetzen schafft Freiraum.
STANDOFF_DELTAS_MM: tuple[float, ...] = (50.0, 100.0, 150.0)

#: Aufstellhöhen-Deltas (mm): den Roboter höher/tiefer stellen.
STAND_HEIGHT_DELTAS_MM: tuple[float, ...] = (-50.0, 50.0)

#: Die drei IK-Achsen und ihre beiden konkreten Zweige (auto = fehlend).
IK_AXES: tuple[str, ...] = ("shoulder", "elbow", "wrist")
IK_VALUES: tuple[str, ...] = ("a", "b")

#: Mindest-Zugewinn am minimalen Abstand (mm), ab dem eine Option als „verbessert"
#: gilt. Größer als die Befund-Rundung (``finding.ROUND_DECIMALS`` = 3), damit
#: Rundungsrauschen keine Scheinverbesserung erzeugt.
MIN_DISTANCE_IMPROVEMENT_MM = 1.0


# ---------------------------------------------------------------------------
# Metrik: was der Advisor aus dem meta.collision-Befund liest (keine Parallel-Metrik)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollisionMetric:
    """Die vom Advisor bewerteten Kennzahlen aus **einem** ``meta.collision``-Befund.

    ``min_distance_mm`` ist der minimale Abstand aller Armglieder zu den Hindernissen
    (``None``, wenn kein Nahpaar in der Breitphase — dann „unendlich weit weg");
    ``n_red`` die Zahl der Kollisions-Samples (Abstand < 0). ``safety_distance_mm``
    stammt aus dem Konfig-Echo des Befunds und definiert die **Marge**.
    """

    min_distance_mm: float | None
    safety_distance_mm: float
    n_red: int

    @classmethod
    def from_finding(cls, finding: dict[str, Any] | None) -> CollisionMetric | None:
        """Zieht die Kennzahlen aus einem Befund-Dict — ``None``, wenn kein Befund."""
        if finding is None:
            return None
        config = finding.get("config") or {}
        return cls(
            min_distance_mm=finding.get("min_distance_mm"),
            safety_distance_mm=float(config.get("safety_distance_mm", 0.0)),
            n_red=int(finding.get("n_red", 0)),
        )

    @property
    def collision_free(self) -> bool:
        """True, wenn kein Sample kollidiert (Abstand ≥ 0 überall)."""
        return self.n_red == 0

    @property
    def margin_mm(self) -> float | None:
        """Marge = minimaler Abstand − Sicherheitsabstand (``None``, wenn kein Nahpaar)."""
        if self.min_distance_mm is None:
            return None
        return self.min_distance_mm - self.safety_distance_mm

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_distance_mm": self.min_distance_mm,
            "margin_mm": self.margin_mm,
            "collision_free": self.collision_free,
            "n_red": self.n_red,
        }


def improves(before: CollisionMetric | None, after: CollisionMetric | None) -> bool:
    """True, wenn ``after`` die Kollision nachweislich beseitigt **oder** verbessert.

    Regel (US 19, „beseitigen oder verbessern"): nie schlechter werden
    (``after.n_red > before.n_red`` ⇒ raus); weniger Kollisions-Samples zählt als
    Verbesserung; bei gleicher Kollisionszahl muss der minimale Abstand um mehr als
    :data:`MIN_DISTANCE_IMPROVEMENT_MM` wachsen (Rundungsrauschen zählt nicht).
    """
    if before is None or after is None:
        return False
    if after.n_red > before.n_red:
        return False
    if after.n_red < before.n_red:
        return True
    # Gleich viele Kollisionen: nur ein echter Abstandsgewinn zählt.
    if before.min_distance_mm is None or after.min_distance_mm is None:
        return False
    return after.min_distance_mm > before.min_distance_mm + MIN_DISTANCE_IMPROVEMENT_MM


# ---------------------------------------------------------------------------
# Hebel-Kandidaten: Override (für die Neu-Simulation) + Schreibstellen-Nutzlast
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Override:
    """Die *versuchsweise* Änderung eines Hebels für **eine** Neu-Simulation.

    Genau ein Feld ist gesetzt (je Hebel einer). ``ik_config`` = vollständiger
    Tri-State-Block; ``orientation`` = absolute ``{lead_deg, kipp_deg}``;
    ``placement`` = sparse absolute freie Platzierungswerte (nur gesetzte Felder
    übersteuern die geplante Lage). Ein leeres ``Override()`` = Basis (nichts ändern).
    """

    ik_config: dict[str, str] | None = None
    orientation: dict[str, float] | None = None
    placement: dict[str, float] | None = None


@dataclass(frozen=True)
class LeverCandidate:
    """Ein zu probierender Hebelzug: Neu-Sim-Override + Anzeige + Schreibstellen-Nutzlast.

    ``write`` ist die serialisierbare Nutzlast, mit der die Option später über eine
    **bestehende** Route angewandt wird (ADR-016): ``setter`` = ``"process-params"``
    (mit ``ik_config`` bzw. ``orientation``) oder ``"placement-override"`` (mit
    ``section_id`` + freien Feldern). Der Advisor selbst schreibt nichts.
    """

    kind: LeverKind
    label: str
    override: Override
    write: dict[str, Any]


def build_candidates(
    *,
    section_id: str,
    lead_deg: float = 0.0,
    kipp_deg: float = 0.0,
    ik_config: dict[str, str] | None = None,
    lateral_mm: float = 0.0,
    standoff_mm: float = 0.0,
    stand_height_mm: float = 0.0,
) -> list[LeverCandidate]:
    """Baut das deterministische Kandidaten-Menü der drei Hebel um den aktuellen Stand.

    Alle Overrides/Nutzlasten sind **absolut** (aktueller Wert ± Delta), damit
    Neu-Simulation und Anwenden bit-identisch dieselbe Änderung meinen. Reihenfolge
    ist fix (IK → Kipp → Lead → Platzierung) und trägt den stabilen Tiebreak des
    Rankings.
    """
    current_ik = dict(ik_config or {})
    out: list[LeverCandidate] = []

    # 1) IK-Konfiguration: je Achse den (vom aktuellen Stand abweichenden) Zweig.
    for axis in IK_AXES:
        for value in IK_VALUES:
            if current_ik.get(axis) == value:
                continue
            block = {**current_ik, axis: value}
            out.append(
                LeverCandidate(
                    kind="ik_config",
                    label=f"IK {_AXIS_LABEL[axis]}={value}",
                    override=Override(ik_config=block),
                    write={"setter": "process-params", "ik_config": block},
                )
            )

    # 2) Kipp-Sweep (um den aktuellen Kipp), Lead bleibt.
    for delta in KIPP_DELTAS_DEG:
        ori = {"lead_deg": lead_deg, "kipp_deg": kipp_deg + delta}
        out.append(
            LeverCandidate(
                kind="kipp_lead",
                label=f"Kipp {delta:+.0f}°",
                override=Override(orientation=ori),
                write={"setter": "process-params", "orientation": ori},
            )
        )

    # 3) Lead-Sweep (um den aktuellen Lead), Kipp bleibt.
    for delta in LEAD_DELTAS_DEG:
        ori = {"lead_deg": lead_deg + delta, "kipp_deg": kipp_deg}
        out.append(
            LeverCandidate(
                kind="kipp_lead",
                label=f"Lead {delta:+.0f}°",
                override=Override(orientation=ori),
                write={"setter": "process-params", "orientation": ori},
            )
        )

    # 4) Platzierung: Abstand zurücksetzen bzw. Höhe verstellen (sparse Overrides).
    for delta in STANDOFF_DELTAS_MM:
        value = standoff_mm + delta
        out.append(
            LeverCandidate(
                kind="placement",
                label=f"Abstand {value:.0f} mm",
                override=Override(placement={"standoff_mm": value}),
                write={
                    "setter": "placement-override",
                    "section_id": section_id,
                    "standoff_mm": value,
                    # Issue #173: Einzelfeld-Option mergen — der Kandidat wurde MIT
                    # dem bestehenden Override simuliert; das Anwenden bewahrt es.
                    "merge": True,
                },
            )
        )
    for delta in STAND_HEIGHT_DELTAS_MM:
        value = stand_height_mm + delta
        out.append(
            LeverCandidate(
                kind="placement",
                label=f"Aufstellhöhe {value:.0f} mm",
                override=Override(placement={"stand_height_mm": value}),
                write={
                    "setter": "placement-override",
                    "section_id": section_id,
                    "stand_height_mm": value,
                    # Issue #173: Einzelfeld-Option mergen (s. Abstand-Hebel oben).
                    "merge": True,
                },
            )
        )

    return out


_AXIS_LABEL: dict[str, str] = {"shoulder": "Schulter", "elbow": "Ellbogen", "wrist": "Handgelenk"}


# ---------------------------------------------------------------------------
# Ranking: Neu-Simulation je Kandidat, nur Verbesserer, deterministische Ordnung
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollisionOption:
    """Eine gangbare Option der gerankten Liste — reine Daten (kein Gate).

    Trägt den Vorher/Nachher-Nachweis (min. Abstand + Marge, kollisionsfrei ja/nein)
    aus der **Neu-Simulation** und die anwendbare Schreibstellen-Nutzlast (``write``).
    Erscheint nur, wenn :func:`improves` wahr ist.
    """

    kind: LeverKind
    label: str
    write: dict[str, Any]
    before: CollisionMetric
    after: CollisionMetric

    @property
    def detail(self) -> str:
        removed = self.before.n_red > 0 and self.after.collision_free
        head = "beseitigt Kollision" if removed else (
            "weniger Kollisions-Samples" if self.after.n_red < self.before.n_red
            else "größerer Abstand"
        )
        return (
            f"{self.label}: {head} — min. Abstand "
            f"{_fmt_mm(self.before.min_distance_mm)} → {_fmt_mm(self.after.min_distance_mm)} mm, "
            f"Marge {_fmt_mm(self.before.margin_mm)} → {_fmt_mm(self.after.margin_mm)} mm."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "detail": self.detail,
            "collision_free_before": self.before.collision_free,
            "collision_free_after": self.after.collision_free,
            "min_distance_before_mm": self.before.min_distance_mm,
            "min_distance_after_mm": self.after.min_distance_mm,
            "margin_before_mm": self.before.margin_mm,
            "margin_after_mm": self.after.margin_mm,
            "write": self.write,
        }


@dataclass(frozen=True)
class AdvisorResult:
    """Ergebnis des Kollisions-Advisors: Basis-Metrik + gerankte Optionsliste."""

    baseline: CollisionMetric | None
    options: list[CollisionOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline.to_dict() if self.baseline is not None else None,
            "options": [o.to_dict() for o in self.options],
        }


def _sort_key(option: CollisionOption) -> tuple:
    # Kollisionsfrei zuerst, dann größte Marge (None = ganz nach hinten).
    margin = option.after.margin_mm
    return (
        0 if option.after.collision_free else 1,
        -(margin if margin is not None else float("-inf")),
    )


def rank_options(
    baseline: CollisionMetric | None,
    candidates: Iterable[LeverCandidate],
    simulate: Callable[[Override], dict[str, Any] | None],
    reachable: Callable[[Override], bool] | None = None,
) -> list[CollisionOption]:
    """Simuliert jeden Kandidaten neu und rankt die *verbessernden* Optionen.

    ``simulate(override)`` liefert den ``meta.collision``-Befund der Neu-Simulation
    (oder ``None``). Nur Kandidaten, deren Befund :func:`improves` erfüllt, werden zu
    Optionen; sortiert wird stabil nach :func:`_sort_key` (die Kandidatenreihenfolge
    bleibt als Tiebreak erhalten).

    ``reachable`` (Issue #214) ist der **Reichweitenkarten-Vorfilter**: liefert es für
    einen Kandidaten ``False``, ist die Gegenmaßnahme (typisch eine Platzierung außer
    Reichweite) laut Karte aussichtslos und wird **gar nicht erst simuliert** — eine
    kürzere Antwort ohne teure Neu-Simulation (US 8). Die Karte **filtert, urteilt
    nie** (ADR-007): sie entfernt nur Kandidaten, die Simulation bleibt der Richter.
    ``None`` (Default) = kein Vorfilter, byte-gleich zu heute (US 12).
    """
    if baseline is None:
        return []
    options: list[CollisionOption] = []
    for cand in candidates:
        if reachable is not None and not reachable(cand.override):
            continue
        after = CollisionMetric.from_finding(simulate(cand.override))
        if after is None or not improves(baseline, after):
            continue
        options.append(
            CollisionOption(
                kind=cand.kind,
                label=cand.label,
                write=cand.write,
                before=baseline,
                after=after,
            )
        )
    options.sort(key=_sort_key)
    return options


def advise(
    baseline_finding: dict[str, Any] | None,
    candidates: Sequence[LeverCandidate],
    simulate: Callable[[Override], dict[str, Any] | None],
    reachable: Callable[[Override], bool] | None = None,
) -> AdvisorResult:
    """Orchestriert den Advisor: Basis-Befund lesen → Kandidaten ranken.

    Reine Funktion — die *echte* Neu-Simulation lebt im übergebenen ``simulate``.
    Fehlt der Basis-Befund (kein Kollisions-Geometrie, ``None``), gibt es nichts zu
    beraten (leere Liste). ``reachable`` (Issue #214) verwirft laut Reichweitenkarte
    unerreichbare Gegenmaßnahmen-Kandidaten **vor** der Neu-Simulation (US 8) — die
    Karte filtert, urteilt nie (ADR-007). ``None`` = kein Vorfilter (byte-gleich).
    """
    baseline = CollisionMetric.from_finding(baseline_finding)
    return AdvisorResult(
        baseline=baseline,
        options=rank_options(baseline, candidates, simulate, reachable),
    )


def _fmt_mm(value: float | None) -> str:
    return "∞" if value is None else f"{value:.1f}"
