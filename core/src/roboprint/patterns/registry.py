"""Registrierung der Musterfamilien.

Eine Familie liegt als eigene Datei in `roboprint/patterns/families/<familie>.py` und registriert
ihre Muster beim Import mit `register(Pattern(...))` oder dem Dekorator `@pattern(...)`.
`load_families()` importiert alle Module dieses Pakets (alphabetisch, Name ohne führendes `_`)
genau einmal. Eine Familie muss deshalb nirgends sonst eingetragen werden: Es gibt keine
gemeinsame Zeile, die mehrere Agenten ändern müssten. Zusätzlich werden Module direkt unter
`roboprint/patterns/` mit dem Präfix `family_` geladen (Ausweichweg, nicht empfohlen).
"""

from __future__ import annotations

import importlib
import pkgutil
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from roboprint.patterns.types import IslandContext, IslandPlan, ParamSpec, Segment

#: Rollen: `infill` (nach den Schalen, im Hohlraum), `outfill` (ersetzt den Außenring der Schale 0
#: durch einen geschlossenen Ring), `full` (baut den ganzen Inselpfad selbst, z. B. Fugenwand)
ROLES = ("infill", "outfill", "full")

#: Musterfunktion: Kontext → IslandPlan (oder nur die Segmentliste)
BuildFn = Callable[[IslandContext], "IslandPlan | list[Segment]"]


@dataclass(frozen=True)
class Pattern:
    """Ein registriertes Muster.

    - `name`: eindeutig, snake_case (Schlüssel in Preset und Szenario, z. B. `fugenwand`).
    - `role`: siehe ROLES. `label`: deutscher Anzeigename. `description`: deutscher Kurztext.
    - `params`: ParamSpecs der musterspezifischen Parameter (Regler im Viewer).
    - `build(ctx)`: Inselpfad für Schicht `ctx.layer` in Richtung außen → innen (siehe Docstring
      des Pakets). Die Umkehrung für `alternate` macht der Kern.
    - `layer_invariant`: True heißt, das Ergebnis hängt nur von Inselgeometrie und Parametern ab
      (nicht von Schichtnummer oder anderen Schichten). Dann rechnet der Kern es je gleicher Insel
      nur einmal. Muster, die `ctx.sections` oder `ctx.layer` lesen, setzen False.
    - `family`: Name der Familie (Datei), für Katalog und Gruppierung im Viewer.
    """

    name: str
    role: str
    label: str
    build: BuildFn
    params: tuple[ParamSpec, ...] = ()
    description: str = ""
    layer_invariant: bool = True
    family: str = ""

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"role {self.role!r} nicht in {ROLES}")
        if not self.name or not self.name.replace("_", "").isalnum() or self.name != self.name.lower():
            raise ValueError(f"Mustername {self.name!r}: nur Kleinbuchstaben, Ziffern und _")
        names = [p.name for p in self.params]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.name}: doppelte Parameternamen")

    def resolve(self, extra: dict[str, Any]) -> dict[str, Any]:
        """Musterparameter mit Standardwerten auffüllen und prüfen (ValueError bei Bereichsfehler)."""
        return {p.name: p.check(extra.get(p.name, p.default)) for p in self.params}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "label": self.label,
            "description": self.description,
            "family": self.family,
            "layer_invariant": self.layer_invariant,
            "params": [p.to_dict() for p in self.params],
        }


_PATTERNS: dict[str, Pattern] = {}
_loaded = False
# Die API ruft den Katalog aus mehreren Threads gleichzeitig ab: Wer während des ersten Ladens kommt,
# wartet, statt einen halb gefüllten Katalog (nur „schalen“) zu sehen.
_load_lock = threading.RLock()


def register(p: Pattern) -> Pattern:
    """Muster registrieren. Ein anderer Eintrag unter demselben Namen ist ein Fehler; derselbe
    (z. B. nach erneutem Import) wird still ersetzt."""
    old = _PATTERNS.get(p.name)
    if old is not None and (old.family, old.role) != (p.family, p.role):
        raise ValueError(f"Muster {p.name!r} ist schon registriert (Familie {old.family!r})")
    _PATTERNS[p.name] = p
    return p


def unregister(name: str) -> None:
    """Nur für Tests."""
    _PATTERNS.pop(name, None)


def pattern(
    name: str,
    role: str,
    label: str,
    params: Sequence[ParamSpec] = (),
    description: str = "",
    layer_invariant: bool = True,
    family: str = "",
) -> Callable[[BuildFn], BuildFn]:
    """Dekorator: `@pattern("fugenwand", "full", "Fugenwand", params=[...])` über `def build(ctx)`."""

    def deco(fn: BuildFn) -> BuildFn:
        fam = family or fn.__module__.rsplit(".", 1)[-1]
        register(Pattern(name, role, label, fn, tuple(params), description, layer_invariant, fam))
        return fn

    return deco


def load_families() -> None:
    """Alle Familienmodule einmal importieren (siehe Modul-Docstring)."""
    global _loaded
    if _loaded:
        return
    with _load_lock:
        if _loaded:
            return
        pkg = importlib.import_module("roboprint.patterns.families")
        for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
            if not info.name.startswith("_"):
                importlib.import_module(f"{pkg.__name__}.{info.name}")
        base = importlib.import_module("roboprint.patterns")
        for info in sorted(pkgutil.iter_modules(base.__path__), key=lambda m: m.name):
            if info.name.startswith("family_"):
                importlib.import_module(f"roboprint.patterns.{info.name}")
        # erst nach dem letzten Import: Ein zweiter Thread sieht nie einen halb gefüllten Katalog
        _loaded = True


def get(name: str) -> Pattern:
    load_families()
    if name not in _PATTERNS:
        raise KeyError(f"unbekanntes Muster {name!r}; bekannt: {sorted(_PATTERNS)}")
    return _PATTERNS[name]


def names(role: str | None = None) -> list[str]:
    load_families()
    return sorted(n for n, p in _PATTERNS.items() if role is None or p.role == role)


def catalog() -> list[dict[str, Any]]:
    """Alle Muster als JSON-fähige Liste (für API und Viewer)."""
    load_families()
    return [_PATTERNS[n].to_dict() for n in sorted(_PATTERNS)]
