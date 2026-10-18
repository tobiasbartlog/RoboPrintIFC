"""Modulgrenzen-Pruefung: Teil-Abmessungen + Obergrenzen + Dichte → Befund (Issue #90).

Reines, tiefes Modul (ADR-022, PRD #88): prueft die Abmessungen eines **Teils**
(Zerlegungsart „Modul") gegen die *optionalen* Obergrenzen max. Modullaenge/-hoehe
und rechnet das Modulgewicht aus Volumen × Dichte. Alles ist ein **Befund, kein
Gate** (`core/CONTEXT.md`): verletzte Grenzen und hohe Gewichte werden gemeldet,
blockieren aber nie — der harte Begrenzer der Modulgroesse ist der Arbeitsraum an
der festen Workstation-Platzierung (der wohnt in `propose`, nicht hier).

Der Dichte-Default kommt aus der **Prozessfenster-Karte**
(`materialcards/process_window.*.json`, Feld ``density_kg_m3``) — die eine Quelle
fuer Prozessparameter, wie die Schalenzahl (ADR-013). Dieses Modul selbst liest
keine Datei (kein I/O): der Aufrufer reicht die Dichte herein.

Deterministisch: gleiche Eingaben → gleicher Befund (feste Rundung, stabile
Reihenfolge der Grenzen: Laenge vor Hoehe). Einheiten nach ADR-006: Millimeter;
Gewicht in kg (Dichte in kg/m³).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fgc.decompose.plan import DecompositionPlan

#: Namen der pruefbaren Obergrenzen — stabile Reihenfolge (Laenge vor Hoehe),
#: damit der Befund deterministisch serialisiert.
LIMIT_KINDS = ("max_length", "max_height")


@dataclass(frozen=True)
class ModuleLimits:
    """Optionale globale Obergrenzen der Modulgroesse (Transport/Montage, ADR-022).

    ``None`` = keine Obergrenze fuer diese Achse (dann begrenzt nur der
    Arbeitsraum). Beide gesetzt, eine gesetzt oder keine — alles erlaubt.
    """

    max_length_mm: float | None = None
    max_height_mm: float | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ModuleLimits:
        """Baut die Obergrenzen aus dem sparse Druckjob-Block ``module_limits``.

        Fehlender Block/fehlende Felder (Altprojekt) → keine Obergrenzen.
        """
        raw = raw or {}
        length = raw.get("max_length_mm")
        height = raw.get("max_height_mm")
        return cls(
            max_length_mm=float(length) if length is not None else None,
            max_height_mm=float(height) if height is not None else None,
        )

    def to_dict(self) -> dict[str, float]:
        """Sparse Serialisierung (nur gesetzte Grenzen) — Schema-Vertrag."""
        out: dict[str, float] = {}
        if self.max_length_mm is not None:
            out["max_length_mm"] = self.max_length_mm
        if self.max_height_mm is not None:
            out["max_height_mm"] = self.max_height_mm
        return out


@dataclass(frozen=True)
class LimitFinding:
    """Befund zu genau einer Obergrenze — eingehalten oder verletzt, nie ein Gate.

    ``exceeded`` ist strikt ``actual_mm > limit_mm``: ein Teil *exakt auf* der
    Grenze gilt als eingehalten (Grenzfall-Vertrag, Golden).
    """

    limit: str  # "max_length" | "max_height"
    limit_mm: float
    actual_mm: float
    exceeded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "limit_mm": self.limit_mm,
            "actual_mm": self.actual_mm,
            "exceeded": self.exceeded,
        }


@dataclass(frozen=True)
class ModuleCheck:
    """Der Modulgrenzen-Befund eines Teils: Gewicht + je gesetzter Grenze ein Befund.

    ``weight_kg`` = Volumen (Laenge × Hoehe × Dicke) × Dichte — ein angezeigter
    Befund, kein Gate (ADR-022). ``findings`` enthaelt nur Eintraege fuer
    tatsaechlich gesetzte Obergrenzen (keine Grenzen → leer).
    """

    weight_kg: float
    density_kg_m3: float
    findings: tuple[LimitFinding, ...] = ()

    @property
    def any_exceeded(self) -> bool:
        return any(f.exceeded for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "weight_kg": self.weight_kg,
            "density_kg_m3": self.density_kg_m3,
            "limits": [f.to_dict() for f in self.findings],
        }


def check_module(
    length_mm: float,
    height_mm: float,
    thickness_mm: float,
    *,
    density_kg_m3: float,
    limits: ModuleLimits | None = None,
) -> ModuleCheck:
    """Prueft ein Teil-Rechteck gegen die optionalen Obergrenzen + rechnet das Gewicht.

    Gewicht = Volumen × Dichte (mm³ → m³, Dichte in kg/m³), auf 3 Nachkommastellen
    gerundet (Determinismus). Je *gesetzter* Obergrenze entsteht genau ein
    :class:`LimitFinding` (Reihenfolge ``LIMIT_KINDS``: Laenge vor Hoehe);
    ``exceeded`` strikt ``>`` — exakt auf der Grenze ist eingehalten. Keine
    Obergrenzen → keine Findings, nur das Gewicht. **Befund, kein Gate.**

    Wirft ``ValueError`` bei nicht-positiver Dichte (ohne Dichte kein Gewicht).
    """
    if density_kg_m3 <= 0:
        raise ValueError(
            f"Dichte {density_kg_m3!r} kg/m³ ist nicht positiv — Gewicht nicht rechenbar. "
            "Default liefert die Prozessfenster-Karte (density_kg_m3)."
        )
    limits = limits or ModuleLimits()

    volume_m3 = (length_mm * height_mm * thickness_mm) / 1e9
    weight_kg = round(volume_m3 * density_kg_m3, 3)

    findings: list[LimitFinding] = []
    if limits.max_length_mm is not None:
        findings.append(
            LimitFinding(
                limit="max_length",
                limit_mm=limits.max_length_mm,
                actual_mm=length_mm,
                exceeded=length_mm > limits.max_length_mm,
            )
        )
    if limits.max_height_mm is not None:
        findings.append(
            LimitFinding(
                limit="max_height",
                limit_mm=limits.max_height_mm,
                actual_mm=height_mm,
                exceeded=height_mm > limits.max_height_mm,
            )
        )
    return ModuleCheck(
        weight_kg=weight_kg,
        density_kg_m3=density_kg_m3,
        findings=tuple(findings),
    )


def check_plan(
    plan: DecompositionPlan,
    *,
    density_kg_m3: float,
    limits: ModuleLimits | None = None,
) -> dict[str, ModuleCheck]:
    """Der Modulgrenzen-Befund je Teil eines Zerlegungsplans (``section_id →`` Befund).

    Bequemer Durchstich fuer Art „modul": jedes Teil wird als Rechteck (Laenge ×
    Hoehe × Wanddicke) gegen dieselben Obergrenzen und dieselbe Dichte geprueft —
    rein, deterministisch, Plan-Reihenfolge bleibt erhalten.
    """
    return {
        sp.section.section_id: check_module(
            sp.section.length_mm,
            sp.section.height_mm,
            plan.wall.thickness_mm,
            density_kg_m3=density_kg_m3,
            limits=limits,
        )
        for sp in plan.sections
    }
