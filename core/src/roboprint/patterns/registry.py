"""Registrierung von Infill- und Outfill-Mustern.

Musterfamilien liegen je als eigene Datei in `roboprint/patterns/families/` und registrieren sich
beim Import. `load_families()` importiert alle Module dieses Pakets (alphabetisch) genau einmal;
eine Familie muss deshalb nirgends sonst eingetragen werden (keine Merge-Konflikte).
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

import numpy as np

from roboprint.patterns.types import IslandContext, Segment

#: Infill: fn(ctx) -> Segmente (kind infill/web) in Druckreihenfolge, ab ctx.entry
InfillFn = Callable[[IslandContext], list[Segment]]
#: Outfill: fn(ctx) -> geschlossener Ring (n, 2), der den Außenring der Schale 0 ersetzt, oder None
OutfillFn = Callable[[IslandContext], "np.ndarray | None"]

_INFILL: dict[str, InfillFn] = {}
_OUTFILL: dict[str, OutfillFn] = {}
_loaded = False


def _no_infill(ctx: IslandContext) -> list[Segment]:
    return []


def _no_outfill(ctx: IslandContext) -> np.ndarray | None:
    return None


def register_infill(name: str, fn: InfillFn) -> InfillFn:
    """Infill-Muster unter `name` registrieren. Doppelte Namen sind ein Fehler."""
    if name in _INFILL and _INFILL[name] is not fn:
        raise ValueError(f"Infill-Muster {name!r} ist schon registriert")
    _INFILL[name] = fn
    return fn


def register_outfill(name: str, fn: OutfillFn) -> OutfillFn:
    """Outfill-Muster unter `name` registrieren. Doppelte Namen sind ein Fehler."""
    if name in _OUTFILL and _OUTFILL[name] is not fn:
        raise ValueError(f"Outfill-Muster {name!r} ist schon registriert")
    _OUTFILL[name] = fn
    return fn


def load_families() -> None:
    """Alle Module unter `roboprint.patterns.families` einmal importieren."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    pkg = importlib.import_module("roboprint.patterns.families")
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if not info.name.startswith("_"):
            importlib.import_module(f"{pkg.__name__}.{info.name}")


def infill_names() -> list[str]:
    load_families()
    return sorted(_INFILL)


def outfill_names() -> list[str]:
    load_families()
    return sorted(_OUTFILL)


def get_infill(name: str) -> InfillFn:
    load_families()
    if name not in _INFILL:
        raise KeyError(f"unbekanntes Infill-Muster {name!r}; bekannt: {sorted(_INFILL)}")
    return _INFILL[name]


def get_outfill(name: str) -> OutfillFn:
    load_families()
    if name not in _OUTFILL:
        raise KeyError(f"unbekanntes Outfill-Muster {name!r}; bekannt: {sorted(_OUTFILL)}")
    return _OUTFILL[name]


register_infill("none", _no_infill)
register_outfill("none", _no_outfill)
