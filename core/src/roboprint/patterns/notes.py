"""Hinweise eines Plans für Nutzer und Artefakte: was das gewählte Muster nicht so druckt, wie
gewählt (Infill entfällt, Rückfall auf Schalen, Schalen entfallen, Insel ohne Strang).

Die Musterfamilien schreiben die Gründe in `LayerPath.meta` (z. B. `meta.infill.skipped`,
`pattern_fallback`, `fermat_skipped`, `shells_dropped.hint`, `topology.note`). Ohne diese Hinweise
nennen Toolpath, Teilbericht und Viewer das gewählte Muster, gedruckt würden aber nur Schalen.
`layer_notes` fasst sie je Text mit den betroffenen Schichten zusammen (deutsch, UI-Text).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from roboprint.patterns.geometry import polygons
from roboprint.patterns.types import LayerPath

#: Schlüssel mit Klartext-Grund und ihr Präfix (None: Text steht für sich)
_TEXT_KEYS = {
    "skipped": "entfällt",
    "fermat_skipped": "Fermat-Spirale",
    "pattern_fallback": None,
    "note": None,
}
_SLOT_LABEL = {"infill": "Infill", "outfill": "Outfill"}


def meta_notes(meta: Mapping[str, Any], _parent: str = "") -> list[str]:
    """Klartext-Hinweise aus dem `meta` eines Schichtpfads (rekursiv, Reihenfolge wie im Dict)."""
    out: list[str] = []
    for key, val in meta.items():
        if isinstance(val, Mapping):
            if key == "shells_dropped" and isinstance(val.get("hint"), str):
                out.append(val["hint"])
            else:
                out.extend(meta_notes(val, key))
        elif key in _TEXT_KEYS and isinstance(val, str) and val:
            if key == "skipped":
                out.append(f"{_SLOT_LABEL.get(_parent, 'Muster')} entfällt: {val}")
            elif _TEXT_KEYS[key]:
                out.append(f"{_TEXT_KEYS[key]}: {val}")
            else:
                out.append(val)
    return out


def _layers_text(layers: Sequence[int]) -> str:
    ls = sorted(set(layers))
    if len(ls) == 1:
        return f"Schicht {ls[0]}"
    if ls[-1] - ls[0] + 1 == len(ls):
        return f"Schichten {ls[0]}–{ls[-1]}"
    return f"{len(ls)} Schichten zwischen {ls[0]} und {ls[-1]}"


def layer_notes(paths: Iterable[LayerPath], sections: Mapping[int, Any] | None = None) -> list[str]:
    """Hinweise aller Pfade, je Text einmal mit den betroffenen Schichten. Mit `sections` auch
    Inseln, für die das Muster keinen Strang liefert (M1, Material fehlt)."""
    found: dict[str, list[int]] = {}
    have: dict[int, set[int]] = {}
    for lp in paths:
        have.setdefault(lp.layer, set()).add(lp.island)
        for text in meta_notes(lp.meta):
            found.setdefault(text, []).append(lp.layer)
    for L in sorted(sections or {}):
        for i, region in enumerate(polygons(sections[L])):
            if i not in have.get(L, set()) and region.area > 1.0:
                found.setdefault(
                    f"Insel {i} ohne Strang: Muster liefert keinen Pfad, Material fehlt", []
                ).append(L)
    return [f"{text} ({_layers_text(layers)})" for text, layers in found.items()]


__all__ = ["layer_notes", "meta_notes"]
