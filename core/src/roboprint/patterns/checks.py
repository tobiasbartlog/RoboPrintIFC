"""Eingabeprüfung der Mustervorschau für API und CLI (keine Kerndatei).

Der Kern prüft in `PatternParams.validate` nur harte Grenzen (w > 0, shells ≥ 1) und die
Musterparameter über ihre ParamSpecs. Die Bereiche der Kernregler (`CORE_PARAM_SPECS`, z. B.
w ∈ [10, 60] mm, shells ∈ [1, 4]) prüft er nicht, und unbekannte Schlüssel landen still in
`extra`. Ein Tippfehler wie `bead_with_mm` gäbe dann ohne Meldung den Standardwert. Diese
Prüfungen holt `check_spec` mit deutschen Meldungen nach.

`flag_empty` markiert eine Vorschau ohne Pfad als Regelfehler: Ist der Querschnitt zu schmal
für Strangbreite und Schalenzahl, liefert der Kern keine Pfade und keine Verstöße, also `ok`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from roboprint.patterns import registry
from roboprint.patterns.plan import resolve_patterns
from roboprint.patterns.preview import make_outline, preset_params
from roboprint.patterns.types import CORE_FIELDS, CORE_PARAM_SPECS, ParamSpec

#: Schlüssel, die `preset_params` selbst auswertet
STRUCTURE_KEYS = frozenset({"extra"})


def _fmt(v: float, unit: str) -> str:
    s = f"{v:g}"
    return f"{s} {unit}" if unit else s


def check_value(spec: ParamSpec, value: Any) -> Any:
    """Einen Reglerwert gegen seine ParamSpec prüfen; ValueError mit deutscher Meldung."""
    who = f"{spec.label} ({spec.name})"
    if spec.kind == "choice":
        if value not in spec.choices:
            allowed = ", ".join(str(c) for c in spec.choices)
            raise ValueError(f"{who}: {value!r} ist nicht erlaubt, möglich sind {allowed}")
        return value
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{who}: {value!r} ist kein Wahrheitswert (true/false)")
        return value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{who}: {value!r} ist keine Zahl")
    if not math.isfinite(value):
        raise ValueError(f"{who}: {value!r} ist kein endlicher Wert")
    if spec.kind == "int" and float(value) != int(value):
        raise ValueError(f"{who}: {value!r} ist keine ganze Zahl")
    v = int(value) if spec.kind == "int" else float(value)
    if spec.minimum is not None and v < spec.minimum - 1e-9:
        raise ValueError(
            f"{who} = {_fmt(v, spec.unit)} liegt unter dem Minimum {_fmt(spec.minimum, spec.unit)}"
        )
    if spec.maximum is not None and v > spec.maximum + 1e-9:
        raise ValueError(
            f"{who} = {_fmt(v, spec.unit)} liegt über dem Maximum {_fmt(spec.maximum, spec.unit)}"
        )
    return v


def check_spec(spec: Mapping[str, Any]) -> None:
    """Preset-Dict `{pattern, params}` prüfen: Kernregler gegen `CORE_PARAM_SPECS`, Musterregler
    gegen die ParamSpecs der aufgelösten Muster, keine unbekannten Schlüssel.

    ValueError mit deutscher Meldung bei falschem Wert, KeyError bei unbekanntem Muster."""
    raw = dict(spec.get("params") or {})
    for ps in CORE_PARAM_SPECS:
        if raw.get(ps.name) is not None:
            check_value(ps, raw[ps.name])
    try:
        params = preset_params(spec)
    except TypeError as exc:
        raise ValueError(f"Ungültiger Parameterwert: {exc}") from exc
    pats = [registry.get(n) for n in (params.outfill, params.infill) if n != "none"]
    known = set(CORE_FIELDS) | STRUCTURE_KEYS
    for pat in pats:
        for ps in pat.params:
            known.add(ps.name)
            if raw.get(ps.name) is not None:
                check_value(ps, raw[ps.name])
    unknown = sorted(set(raw) - known)
    if unknown:
        names = ", ".join(p.name for p in pats) or "schalen"
        own = sorted({ps.name for pat in pats for ps in pat.params})
        hint = (
            f"; Musterparameter von {names}: {', '.join(own)}"
            if own
            else f"; {names} hat keine Musterparameter"
        )
        raise ValueError(f"Unbekannte Parameter: {', '.join(unknown)}{hint}")
    resolve_patterns(params)  # Rollenkonflikte (beide Plätze belegt, Infill im Outfill-Platz)


def check_outline(outline: Any) -> None:
    """Querschnitt prüfen: gültiges Polygon (keine Selbstüberschneidung, Löcher innen) mit Fläche > 0.
    ValueError mit deutscher Meldung; `None` (Standard 600 × 200) ist immer gültig."""
    if outline is None:
        return
    from shapely.validation import explain_validity

    geom = make_outline(outline)
    if geom.is_empty or geom.area <= 0:
        raise ValueError("Querschnitt ohne Fläche (Punkte auf einer Linie oder Selbstüberschneidung?)")
    if not geom.is_valid:
        why = explain_validity(geom)  # englisch, z. B. "Self-intersection[300 100]"
        at = why[why.find("[") :] if "[" in why else ""
        reasons = {
            "Self-intersection": "Umriss überschneidet sich selbst",
            "Ring Self-intersection": "Umriss überschneidet sich selbst",
            "Hole lies outside shell": "Loch liegt außerhalb des Umrisses",
            "Holes are nested": "Löcher liegen ineinander",
            "Interior is disconnected": "Löcher zerteilen die Fläche",
            "Nested shells": "Umrisse liegen ineinander",
            "Too few points": "zu wenige Punkte",
        }
        text = next((de for en, de in reasons.items() if why.startswith(en)), "ungültige Geometrie")
        raise ValueError(f"Querschnitt ungültig: {text} {at}".strip())


def flag_empty(data: dict[str, Any]) -> dict[str, Any]:
    """Vorschau ohne Pfad in der gezeigten Schicht als Regelfehler M1 markieren (in place)."""
    if data.get("paths"):
        return data
    p = data.get("params") or {}
    w, shells = p.get("bead_width_mm"), p.get("shells")
    data["violations"] = [
        *data.get("violations", []),
        {
            "rule": "M1",
            "severity": "error",
            "layer": data.get("layer"),
            "island": None,
            "at": None,
            "value": None,
            "limit": None,
            "message": (
                f"Kein druckbarer Pfad: Der Querschnitt ist zu schmal für {shells} Schale(n) "
                f"mit Strangbreite {w} mm"
            ),
        },
    ]
    data["ok"] = False
    return data
