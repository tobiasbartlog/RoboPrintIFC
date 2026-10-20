"""fgc.decompose.objective — die Zielfunktion der Zerlegungs-Suche (Issue #212, PRD #183 Stufe 3).

Der **Komparator** der kommenden Beam-Suche (#217): entscheidet, welcher
Kandidaten-Zerlegung der Vorzug gebührt. Zwei Lesarten über **einem**
Gewichts-Satz (Grill 2026-07-14, ein Zustand statt zweier, die auseinanderlaufen):

- **Aufwiegen AUS (Default): lexikographisch.** Die Gewichts-*Reihenfolge* ist die
  Rangfolge — Default Umsetzvorgänge > Fugenfläche > kinematische Marge > c_v
  (Einmessen ist der teuerste manuelle Schritt, c_v ist Komfort; kein c_v
  kompensiert ein Einmessen). Gleichstand zweier Gewichte ist in dieser Lesart
  ein Fehler (die Rangfolge wäre mehrdeutig) — die GUI verhindert ihn, der Core
  weist ihn zusätzlich zurück.
- **Aufwiegen AN: gewichtete Summe** derselben Zahlen über den quantisierten
  Kriterienwerten (kleiner = besser).

Davor steht die Erreichbarkeit als **hartes K.-o.** (kein Gewicht): ein
Kandidat mit unerreichbarem Teil verliert gegen jeden erreichbaren, egal wie
gut seine Scores sind.

**Quantisierung:** stetige Kriterien werden in Bins geschnappt, damit echte
Gleichstände entstehen und die Entscheidung ans nachrangige Kriterium
durchgereicht wird. Die Schrittweiten sind **benannte Verfahrens-Parameter**
(:data:`QUANT_FUGENFLAECHE_MM2` …), PROVISORISCH bis zur Eichung an echten
Kandidaten nach AP 2 (PRD #183).

**Kriterienwerte werden injiziert** (:class:`KriterienWerte`): dieses Modul
rechnet keine Erreichbarkeit, Fugenfläche oder Marge selbst — die echten
Lieferanten (ReachabilityMap #210, Raycast-Scorer) verdrahtet erst die
Beam-Suche (#216/#217). Dadurch ist der Komparator deterministisch und ohne
Geometrie-Stack testbar.

Die komplette Config (:meth:`ObjectiveConfig.to_dict`, inkl. Schrittweiten)
wandert in die **Lauf-Provenienz** jedes Zerlegungslaufs (ADR-004) — der
Paper-Benchmark pinnt den Default. Persistiert wird sie als Druckjob-Parameter
über das Setter-Muster (ADR-016, ``set_objective_for_job``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CRITERIA",
    "DEFAULT_WEIGHTS",
    "DEFAULT_QUANT_STEPS",
    "QUANT_UMSETZVORGAENGE",
    "QUANT_FUGENFLAECHE_MM2",
    "QUANT_MARGE_MM",
    "QUANT_VOLUMEN_CV",
    "KriterienWerte",
    "ObjectiveConfig",
    "candidate_key",
    "compare_candidates",
    "objective_from_job",
    "quantize",
]

#: Die vier Kriterien der Zielfunktion (Grill 2026-07-14, Entscheidung 1) — die
#: Tupel-Reihenfolge IST die Default-Rangfolge: Umsetzvorgänge > Fugenfläche >
#: kinematische Marge > c_v. Erreichbarkeit ist bewusst KEIN Kriterium — sie ist
#: das harte K.-o. davor (ein unerreichbares Teil macht den Kandidaten wertlos).
CRITERIA: tuple[str, ...] = (
    "umsetzvorgaenge",
    "fugenflaeche",
    "kinematische_marge",
    "volumen_cv",
)

#: Default-Gewichte (ein Satz, zwei Lesarten): absteigend entlang der
#: Default-Rangfolge — im Aus-Modus liest sich die Reihenfolge als Rangfolge,
#: im An-Modus sind es die Summanden-Gewichte. Paarweise verschieden, damit der
#: Default im Aus-Modus keine mehrdeutige Rangfolge trägt.
DEFAULT_WEIGHTS: dict[str, float] = {
    "umsetzvorgaenge": 4.0,
    "fugenflaeche": 3.0,
    "kinematische_marge": 2.0,
    "volumen_cv": 1.0,
}

#: Schrittweite Umsetzvorgänge: 1 = identisch auf der Zählung (das Kriterium ist
#: diskret; der Eintrag hält den Schrittweiten-Satz vollständig und provenienzfähig).
QUANT_UMSETZVORGAENGE: float = 1.0
#: PROVISORISCH (Eichung nach AP 2 an echten Kandidaten, PRD #183): Fugenflächen
#: im selben 0,05-m²-Bin gelten als Gleichstand.
QUANT_FUGENFLAECHE_MM2: float = 50_000.0
#: PROVISORISCH (Eichung nach AP 2): kinematische Margen im selben 25-mm-Bin
#: gelten als Gleichstand.
QUANT_MARGE_MM: float = 25.0
#: PROVISORISCH (Eichung nach AP 2): Volumen-Variationskoeffizienten (c_v) im
#: selben 0,05-Bin gelten als Gleichstand.
QUANT_VOLUMEN_CV: float = 0.05

#: Der vollständige Schrittweiten-Satz je Kriterium — benannte
#: Verfahrens-Parameter, Teil der Lauf-Provenienz (ADR-004).
DEFAULT_QUANT_STEPS: dict[str, float] = {
    "umsetzvorgaenge": QUANT_UMSETZVORGAENGE,
    "fugenflaeche": QUANT_FUGENFLAECHE_MM2,
    "kinematische_marge": QUANT_MARGE_MM,
    "volumen_cv": QUANT_VOLUMEN_CV,
}


@dataclass(frozen=True)
class KriterienWerte:
    """Die **injizierten** Kriterienwerte eines Zerlegungs-Kandidaten (Issue #212).

    Das Interface zwischen Zielfunktion und Lieferanten: die Beam-Suche
    (#216/#217) füllt diese Werte aus Karte + Scorer; dieses Modul rechnet
    nichts davon selbst. Richtungen: ``umsetzvorgaenge``/``fugenflaeche_mm2``/
    ``volumen_cv`` kleiner = besser, ``kinematische_marge_mm`` größer = besser
    (der Komparator dreht sie intern um). ``erreichbar`` ist das harte K.-o.
    davor — kein Kriterium, kein Gewicht.
    """

    erreichbar: bool
    umsetzvorgaenge: float
    fugenflaeche_mm2: float
    kinematische_marge_mm: float
    volumen_cv: float


def _default_weights() -> dict[str, float]:
    return dict(DEFAULT_WEIGHTS)


def _default_quant_steps() -> dict[str, float]:
    return dict(DEFAULT_QUANT_STEPS)


@dataclass(frozen=True)
class ObjectiveConfig:
    """Die vollständige Zielfunktions-Config (Issue #212): ein Gewichts-Satz, zwei Lesarten.

    ``aufwiegen=False`` (Default) liest die Gewichte als **Rangfolge**
    (lexikographisch, absteigend); ``aufwiegen=True`` als Summanden einer
    **gewichteten Summe**. ``quant_steps`` sind die Schrittweiten der
    Quantisierung (benannte Verfahrens-Parameter, PROVISORISCH bis AP 2).

    Validiert bei Konstruktion: jedes Kriterium braucht genau ein positives,
    endliches Gewicht und eine positive Schrittweite; im Aus-Modus sind gleiche
    Gewichte ein Fehler (mehrdeutige Rangfolge — die GUI verhindert den
    Gleichstand, der Core weist ihn zusätzlich zurück).
    """

    aufwiegen: bool = False
    weights: dict[str, float] = field(default_factory=_default_weights)
    quant_steps: dict[str, float] = field(default_factory=_default_quant_steps)

    def __post_init__(self) -> None:
        for label, mapping in (("weights", self.weights), ("quant_steps", self.quant_steps)):
            unknown = set(mapping) - set(CRITERIA)
            if unknown:
                raise ValueError(
                    f"Unbekannte Kriterien in {label}: {sorted(unknown)} — "
                    f"erlaubt: {list(CRITERIA)}."
                )
            missing = set(CRITERIA) - set(mapping)
            if missing:
                raise ValueError(
                    f"Fehlende Kriterien in {label}: {sorted(missing)} — "
                    "jedes Kriterium braucht genau einen Wert."
                )
            for crit, value in mapping.items():
                v = float(value)
                if not math.isfinite(v) or v <= 0:
                    raise ValueError(
                        f"{label}[{crit!r}]={value!r} ist nicht positiv/endlich — "
                        "Gewichte und Schrittweiten sind positive Zahlen."
                    )
        if not self.aufwiegen:
            by_weight: dict[float, list[str]] = {}
            for crit in CRITERIA:
                by_weight.setdefault(float(self.weights[crit]), []).append(crit)
            tied = [crits for crits in by_weight.values() if len(crits) > 1]
            if tied:
                raise ValueError(
                    f"Gleichstand der Gewichte im Aus-Modus (Rangfolge mehrdeutig): {tied}. "
                    "Entweder Gewichte paarweise verschieden wählen oder Aufwiegen einschalten."
                )

    def ranking(self) -> tuple[str, ...]:
        """Die Rangfolge der Kriterien: absteigend nach Gewicht (Aus-Lesart).

        Deterministisch auch bei (nur im An-Modus zulässigem) Gleichstand:
        gleiche Gewichte behalten die :data:`CRITERIA`-Reihenfolge.
        """
        return tuple(
            sorted(CRITERIA, key=lambda c: (-float(self.weights[c]), CRITERIA.index(c)))
        )

    def to_dict(self) -> dict[str, Any]:
        """Die **komplette** Config fürs Lauf-Provenienz-Feld (ADR-004): Lesart,
        Gewichte und Schrittweiten — nichts implizit, der Benchmark pinnt den Default."""
        return {
            "aufwiegen": self.aufwiegen,
            "weights": {c: float(self.weights[c]) for c in CRITERIA},
            "quant_steps": {c: float(self.quant_steps[c]) for c in CRITERIA},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ObjectiveConfig:
        """Config aus dem persistierten Druckjob-Block — fail-soft additiv.

        ``None``/leer (Altprojekt) ⇒ Default-Config. Teilbelegte ``weights``/
        ``quant_steps`` werden über die Defaults gemischt (fehlende Kriterien
        erben); unbekannte Kriterien oder unzulässige Werte schlagen klar fehl
        (Validierung der Konstruktion — kein stiller Falschkomparator).
        """
        if not data:
            return cls()
        weights = {**DEFAULT_WEIGHTS, **(data.get("weights") or {})}
        quant_steps = {**DEFAULT_QUANT_STEPS, **(data.get("quant_steps") or {})}
        return cls(
            aufwiegen=bool(data.get("aufwiegen", False)),
            weights=weights,
            quant_steps=quant_steps,
        )


def quantize(value: float, step: float) -> int:
    """Bin-Index eines stetigen Kriterienwerts (Schrittweite = Verfahrens-Parameter).

    Rundet deterministisch zum nächsten Bin (``floor(value/step + 0.5)``): Werte
    im selben Bin sind ein **echter Gleichstand** und reichen die Entscheidung
    ans nachrangige Kriterium durch (Grill 2026-07-14).
    """
    if not math.isfinite(step) or step <= 0:
        raise ValueError(f"Schrittweite {step!r} ist nicht positiv/endlich.")
    return math.floor(float(value) / float(step) + 0.5)


def _directed_value(criterion: str, werte: KriterienWerte) -> float:
    """Der Kriterienwert in Minimierungs-Richtung (Marge wird negiert: mehr = besser)."""
    if criterion == "umsetzvorgaenge":
        return float(werte.umsetzvorgaenge)
    if criterion == "fugenflaeche":
        return float(werte.fugenflaeche_mm2)
    if criterion == "kinematische_marge":
        return -float(werte.kinematische_marge_mm)
    if criterion == "volumen_cv":
        return float(werte.volumen_cv)
    raise ValueError(f"Unbekanntes Kriterium {criterion!r} — erlaubt: {list(CRITERIA)}.")


def candidate_key(werte: KriterienWerte, config: ObjectiveConfig) -> tuple:
    """Der Sortier-Schlüssel eines Kandidaten — kleiner = besser (für ``min``/``sorted``).

    Erste Komponente ist das **K.-o.** (0 = erreichbar, 1 = nicht): ein
    unerreichbarer Kandidat verliert gegen jeden erreichbaren, unabhängig von
    jedem Score. Danach je Lesart:

    - lexikographisch (``aufwiegen=False``): die quantisierten, gerichteten
      Kriterienwerte in Rangfolge (:meth:`ObjectiveConfig.ranking`);
    - gewichtete Summe (``aufwiegen=True``): ein Skalar über denselben
      quantisierten Werten (die Quantisierung normiert die Einheiten auf
      Bin-Zählungen — dieselben Schrittweiten wie im Aus-Modus, eine Config).
    """
    ko = 0 if werte.erreichbar else 1
    quants = {
        c: quantize(_directed_value(c, werte), config.quant_steps[c]) for c in CRITERIA
    }
    if config.aufwiegen:
        score = sum(float(config.weights[c]) * quants[c] for c in CRITERIA)
        return (ko, score)
    return (ko, *(quants[c] for c in config.ranking()))


def compare_candidates(a: KriterienWerte, b: KriterienWerte, config: ObjectiveConfig) -> int:
    """Der Komparator: -1 wenn ``a`` besser, +1 wenn ``b`` besser, 0 bei Gleichstand.

    Dünner Vergleich über :func:`candidate_key` — die Beam-Suche (#217) sortiert
    direkt über den Schlüssel; der Komparator ist die testbare Zwei-Kandidaten-Sicht.
    """
    ka, kb = candidate_key(a, config), candidate_key(b, config)
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0


def objective_from_job(job: dict[str, Any] | None) -> ObjectiveConfig:
    """Die wirksame Zielfunktions-Config eines Druckjobs (Default, wenn Feld fehlt).

    Liest den sparse ``objective``-Block (Setter ``set_objective_for_job``,
    ADR-016); Altprojekte ohne Block bekommen den gepinnten Default — genau die
    Config, die der Zerlegungslauf in seine Provenienz stempelt (ADR-004).
    """
    return ObjectiveConfig.from_dict((job or {}).get("objective"))
