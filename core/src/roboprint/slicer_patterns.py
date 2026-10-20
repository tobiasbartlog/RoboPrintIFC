"""Slicer mit Druckmuster (opt-in): Schichtpfade aus `roboprint.patterns` als Ringe im Toolpath.

Format nach docs/muster/ARTEFAKT-FORMAT.md (Nachtrag M3). Nur aktiv, wenn ein Musterparameter vom
Standard abweicht (`layer_order = alternate`, `infill_pattern`, `outfill_pattern`, `pattern_params`
oder `pattern_preset`); sonst schneidet `roboprint.slicer` wie bisher (SPEC §5.1). `layer_order = same`
allein ist kein Muster (das ist die heutige Schichtfolge).

Festlegungen
- Die Querschnitte des **ganzen Teils** (alle Schichten, Frame P, bei (L + 0,5)·h) gehen an
  `patterns.plan_pattern`; Muster entscheiden damit schichtübergreifend (M3).
- Je Schichtpfad (Schicht, Insel) werden die Segmente in Druckreihenfolge zu Ringen: Stößt ein
  Segment mit einem Verbinder der Länge 0 (≤ JOIN_TOL_MM) an ein Segment derselben `kind`, werden
  beide ein Ring. Stoßende Segmente verschiedener `kind` bleiben eigene Ringe; zwischen ihnen liegt
  ein Verbinder der Länge 0 (`link_next`). Den lässt der unabhängige Prüfer `verify.check_run` zu
  (Schichtsprung 0, Punkt im Querschnitt), solange die Trajektorie dafür mindestens ein
  `link`-Sample enthält (Ablaufregel ARTEFAKTE); das ist Sache des Planers (M3.2).
- `closed`: Ein Ring ist geschlossen, wenn sein letzter Punkt den ersten trifft (≤ JOIN_TOL_MM);
  der letzte Punkt wird dann exakt auf den ersten gesetzt. Sonst offenes Segment (`closed = false`).
- Wegpunkte: Die Musterpunkte sind schon dicht (Sehnenfehler ≤ chord_tol_mm, Abstand ≤ step_mm).
  Sie bleiben alle erhalten; Stücke länger als step_mm werden wie bisher gleichmäßig unterteilt,
  doppelte Punkte entfallen.
- Verbinder: `link_next` zwischen allen aufeinanderfolgenden Ringen nach derselben Regel wie ohne
  Muster (`slicer.link_allowed`, SPEC §5.3). Innerhalb eines Schichtpfads sind es die Verbinder
  des Musters (meist Länge 0); beim Schichtwechsel mit `alternate` liegen Ende von L und Anfang von
  L + 1 waagrecht übereinander (Fall `Point`, reiner Z-Hub um h).
- Präzedenz der Parameter: Preset → Szenariowerte, die vom Standard abweichen → `pattern_params`.
  w, h, step_mm und link_max_mm kommen immer aus dem Szenario (die Planung nutzt dieselben).
- Schichtfolge: `layer_order` leer (Standard) heißt „nicht gesetzt“: mit Muster gilt dann die des
  Presets bzw. des Kerns (`alternate`, senkrechter Schichtwechsel nach M4). Ein ausdrücklich
  gesetztes `same` oder `alternate` gilt immer, auch gegen das Preset.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from roboprint.patterns import LayerPath, PatternParams
    from roboprint.slicer import SlicedRing, SliceParams

#: Endpunkte gelten als stoßend bzw. Ring als geschlossen bis zu diesem Abstand (mm)
JOIN_TOL_MM = 1e-6
#: Doppelte Wegpunkte (mm)
DUP_TOL_MM = 1e-9
#: Standardwerte der Musterparameter in SliceParams (= kein Muster)
PATTERN_FIELDS: dict[str, Any] = {
    "layer_order": "",
    "infill_pattern": "none",
    "outfill_pattern": "none",
    "pattern_params": "",
    "pattern_preset": "",
}
#: Standard der Schalenzahl (SPEC §10); weicht das Szenario ab, gilt sein Wert vor dem Preset
SHELLS_DEFAULT = 2


#: Schichtfolgen; "" = nicht gesetzt (ohne Muster wie `same`, mit Muster Preset bzw. Kern)
LAYER_ORDERS = ("", "same", "alternate")


def uses_pattern(p: Any) -> bool:
    """True, wenn ein Musterparameter vom Standard abweicht (SliceParams oder PlannerParams).
    `layer_order = same` allein ist die heutige Schichtfolge und kein Muster."""
    if p.layer_order not in LAYER_ORDERS:
        raise ValueError(f"layer_order = {p.layer_order!r}, erlaubt {LAYER_ORDERS[1:]}")
    return p.layer_order == "alternate" or any(
        getattr(p, k) != v for k, v in PATTERN_FIELDS.items() if k != "layer_order"
    )


def resolve_preset_path(path: str) -> Path:
    """Preset-Pfad: wie angegeben, sonst relativ zum Repo."""
    from roboprint.assets import REPO_ROOT

    p = Path(path)
    if p.exists() or p.is_absolute():
        return p
    alt = REPO_ROOT / p
    return alt if alt.exists() else p


def pattern_params(p: SliceParams) -> PatternParams | None:
    """PatternParams aus den Slicer-Parametern (Präzedenz siehe Modul-Docstring); None ohne Muster.
    ValueError bei unbekanntem Muster, falschem Parameter oder widersprüchlicher Kombination."""
    if not uses_pattern(p):
        return None
    from roboprint.patterns import load_preset, params_from_dict, preset_params
    from roboprint.patterns.plan import resolve_patterns

    data: dict[str, Any] = {}
    if p.pattern_preset:
        data = preset_params(load_preset(resolve_preset_path(p.pattern_preset))).to_dict()
    if p.layer_order:  # ausdrücklich gesetzt; sonst Preset bzw. Kern (alternate)
        data["layer_order"] = p.layer_order
    if p.infill_pattern != "none":
        data["infill"] = p.infill_pattern
    if p.outfill_pattern != "none":
        data["outfill"] = p.outfill_pattern
    if p.shells != SHELLS_DEFAULT or "shells" not in data:
        data["shells"] = p.shells
    if p.pattern_params:
        extra = json.loads(p.pattern_params)
        if not isinstance(extra, dict):
            raise ValueError("pattern_params muss ein Objekt sein")
        data.update(extra)
    data.update(
        bead_width_mm=p.bead_width_mm,
        layer_height_mm=p.layer_height_mm,
        step_mm=p.step_mm,
        link_max_mm=p.link_max_mm,
    )
    pp = params_from_dict(data)
    try:
        resolve_patterns(pp)  # prüft Musternamen, Rollen und Parameter früh
        if p.pattern_params:
            # Wie die Vorschau (checks.check_spec): unbekannte Schlüssel (Tippfehler) und Kernregler
            # außerhalb ihres Bereichs sind ein Fehler, statt still den Standardwert zu ergeben
            from roboprint.patterns.checks import check_spec

            check_spec({"pattern": "none", "params": {"infill": pp.infill, "outfill": pp.outfill, **extra}})
    except KeyError as e:  # unbekanntes Muster: wie jeder andere Parameterfehler
        raise ValueError(str(e.args[0]) if e.args else str(e)) from e
    return pp


def pattern_info(pp: PatternParams) -> dict[str, Any]:
    """Objekt `Toolpath.pattern`: Schichtfolge, Muster und alle Parameter, die vom Standard der
    Kernparameter abweichen, plus die musterspezifischen (ohne None)."""
    from roboprint.patterns import PatternParams as _PP

    std = _PP().to_dict()
    params: dict[str, Any] = {}
    for k, v in pp.to_dict().items():
        if k in ("layer_order", "infill", "outfill") or v is None:
            continue
        if k in std and std[k] == v:
            continue
        params[k] = [float(x) for x in v] if isinstance(v, (list, tuple)) else v
    return {"layer_order": pp.layer_order, "infill": pp.infill, "outfill": pp.outfill, "params": params}


def _dedupe(pts: np.ndarray) -> np.ndarray:
    keep = np.ones(len(pts), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(pts, axis=0), axis=1) > DUP_TOL_MM
    return pts[keep]


def path_groups(path: LayerPath) -> list[tuple[str, int, np.ndarray, bool]]:
    """Segmente eines Schichtpfads als Ringe: (kind, shell, Punkte (n, 2), closed).

    Stoßende Segmente gleicher `kind` (Verbinder ≤ JOIN_TOL_MM) werden zusammengefasst."""
    groups: list[list[Any]] = []
    for seg in path.segments:
        pts = np.asarray(seg.points, dtype=float)
        if groups and groups[-1][0] == seg.kind and np.linalg.norm(groups[-1][2][-1] - pts[0]) <= JOIN_TOL_MM:
            groups[-1][2] = np.vstack([groups[-1][2], pts[1:]])
        else:
            groups.append([seg.kind, int(seg.shell), pts.copy()])
    out = []
    for kind, shell, pts in groups:
        pts = _dedupe(pts)
        closed = len(pts) >= 4 and float(np.linalg.norm(pts[-1] - pts[0])) <= JOIN_TOL_MM
        if closed:
            pts[-1] = pts[0]
        out.append((kind, shell, pts, closed))
    return out


def pattern_rings(sections: Mapping[int, Any], pp: PatternParams, p: SliceParams) -> list[SlicedRing]:
    """Ringe aller Schichtpfade in Druckreihenfolge (Frame P, z = (L + 1)·h), ohne `link_next`."""
    from roboprint.patterns import plan_pattern
    from roboprint.slicer import SlicedRing, _resample

    up = np.array([0.0, 0.0, p.approach_mm])
    rings: list[SlicedRing] = []
    for path in plan_pattern(sections, pp):
        z = (path.layer + 1) * p.layer_height_mm
        for kind, shell, xy, closed in path_groups(path):
            xy = _dedupe(_resample(xy, p.step_mm))
            if len(xy) < 2:
                continue
            pts = np.column_stack([xy, np.full(len(xy), z)])
            rings.append(SlicedRing(path.layer, shell, kind, pts, pts[0] + up, pts[-1] + up, closed=closed))
    return rings
