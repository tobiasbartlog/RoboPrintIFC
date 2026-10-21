"""Eingabeprüfung der Mustervorschau für API und CLI (keine Kerndatei).

Der Kern prüft in `PatternParams.validate` nur harte Grenzen (w > 0, shells ≥ 1) und die
Musterparameter über ihre ParamSpecs. Die Bereiche der Kernregler (`CORE_PARAM_SPECS`, z. B.
w ∈ [10, 60] mm, shells ∈ [1, 4]) prüft er nicht, und unbekannte Schlüssel landen still in
`extra`. Ein Tippfehler wie `bead_with_mm` gäbe dann ohne Meldung den Standardwert. Diese
Prüfungen holt `check_spec` mit deutschen Meldungen nach, ebenso die übrigen Kernwerte ohne Regler
(`RULE_PARAM_SPECS`: Abtastung, Toleranzen nur strenger als die Regel, v > 0) und die Regelkonstante ε.
`check_outline` begrenzt auch Größe und Punktzahl eines Polygon-Querschnitts.

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

#: Übrige Kernwerte ohne Regler: Abtastung, Toleranzen der Regeln, Geschwindigkeit. Die Grenzen
#: halten die Vorschau schnell (step_mm < 2 mm: Krümmungsrauschen und quadratischer Aufwand der
#: M2-Paarsuche) und erlauben Toleranzen nur strenger als die Regel (SPEC §10, AUFTRAG M2/M3/M6).
RULE_PARAM_SPECS: tuple[ParamSpec, ...] = (
    ParamSpec("step_mm", "Wegpunktabstand", 20.0, "mm", 2.0, 100.0),
    ParamSpec("chord_tol_mm", "Sehnenfehler", 0.5, "mm", 0.05, 0.5),
    ParamSpec("delta_mm", "Überhangtoleranz δ", 2.0, "mm", 0.0, 2.0),
    ParamSpec("v_print_mm_s", "Druckgeschwindigkeit", 100.0, "mm/s", 1.0, 1000.0),
    ParamSpec("link_max_mm", "Längster Verbinder", 60.0, "mm", 0.0, 60.0),
    ParamSpec("contact_tol_mm", "Kontakttoleranz", 0.5, "mm", 0.0, 0.5),
)
#: Regelkonstanten (AUFTRAG M2/M7: ε = 0,15); jeder andere Wert ist ein Fehler
RULE_CONSTANTS: Mapping[str, float] = {"eps": 0.15}

#: Größe eines Polygon-Querschnitts (wie `PatternOutlineBox.length_mm` ≤ 20000)
OUTLINE_MAX_EXTENT_MM = 20000.0
OUTLINE_MAX_POINTS = 5000


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
    for ps in (*CORE_PARAM_SPECS, *RULE_PARAM_SPECS):
        if raw.get(ps.name) is not None:
            check_value(ps, raw[ps.name])
    for name, value in RULE_CONSTANTS.items():
        v = raw.get(name)
        if v is not None and (
            isinstance(v, bool) or not isinstance(v, int | float) or abs(float(v) - value) > 1e-12
        ):
            raise ValueError(
                f"{name} = {v!r}: ε ist eine Regelkonstante (AUFTRAG M2, M7) und bleibt {value:g}"
            )
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

    if isinstance(outline, Mapping) and "polygon" in outline:
        n = len(outline["polygon"]) + sum(len(h) for h in outline.get("holes") or [])
        if n > OUTLINE_MAX_POINTS:
            raise ValueError(f"Querschnitt hat {n} Punkte, höchstens {OUTLINE_MAX_POINTS} sind erlaubt")
    geom = make_outline(outline)
    if not geom.is_empty:
        x0, y0, x1, y1 = geom.bounds
        if max(x1 - x0, y1 - y0) > OUTLINE_MAX_EXTENT_MM:
            raise ValueError(
                f"Querschnitt zu groß: {max(x1 - x0, y1 - y0):g} mm, höchstens {OUTLINE_MAX_EXTENT_MM:g} mm"
            )
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
    # Der Kern meldet die leeren Inseln selbst (M1 „Insel ohne Strang“, metrics.missing_islands);
    # hier steht stattdessen eine Meldung mit dem Grund
    keep = [
        v for v in data.get("violations", []) if not (v["rule"] == "M1" and "ohne Strang" in v["message"])
    ]
    data["violations"] = [
        *keep,
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
