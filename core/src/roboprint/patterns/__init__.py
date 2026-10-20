"""Druckmuster: reines Geometriemodul (shapely/numpy, ohne Roboter und Planer).

Aus den Querschnitten eines Teils und den Musterparametern entstehen je Schicht und Insel ein
**Schichtpfad** (`LayerPath`): eine geordnete Folge von **Segmenten** mit `kind`, offen oder
geschlossen, verbunden durch implizite gerade Verbinder (meist Länge 0). Ein Pfad ist ein Strang:
Pumpe an, kein Halt, kein Travel (M1). Muster sind **parametrische Segmentmuster mit Kontakten**:
Fugen und Knoten, an denen sich Raupen berühren, ohne sich zu kreuzen (Nutzer-Nachtrag 18:20,
docs/muster/AUFTRAG.md; Artefaktformat docs/muster/ARTEFAKT-FORMAT.md).

Alle Koordinaten Frame P, mm, nur XY (SPEC §2). Schicht L druckt auf z_P = (L + 1)·h.

Schnittstelle (stabil, gegen sie bauen die Musterfamilien)
==========================================================

Einstieg::

    plan_pattern(sections: dict[int, Polygon | MultiPolygon], params: PatternParams | None = None)
        -> list[LayerPath]
    measure(paths, sections, params, layers=None) -> PatternReport          # M1–M7 + Kennzahlen
    preview(spec, outline=None, layer=0) -> dict                            # JSON für API/Viewer
    preview_svg(spec=None, outline=None, layer=0, *, width_px=1000, data=None) -> str
    load_preset(path) -> dict;  save_preset(path, name, pattern, params, outline=None, description="")
    preset_params(preset: dict) -> PatternParams;  params_from_dict(d) -> PatternParams
    fit_to_length(total_mm, target_mm, *, min_count=1, max_count=None, min_mm=None, max_mm=None)
        -> FitResult(count, length_mm, total_mm, target_mm, positions_mm)
    catalog() -> list[dict]   # alle Muster mit ParamSpecs (für API/Viewer-Regler)
    CORE_PARAM_SPECS          # Regler der Kernparameter

`sections` sind die Querschnitte des GANZEN Teils (alle Schichten), damit Muster schicht-
übergreifend entscheiden können (M3: Querstege an künftigen Laibungen). Inseln = Polygone einer
Schicht, sortiert nach (x_min, y_min) ihrer Bounding-Box.

Kernobjekte (types.py):

- `PatternParams` (frozen): bead_width_mm=30, layer_height_mm=10, shells=2,
  layer_order='alternate'|'same', infill='none', outfill='none', step_mm=20, chord_tol_mm=0.5,
  eps=0.15, delta_mm=2, corner_radius_mm=None (= w), transition_radius_mm=None (= w),
  seam_corner=(−1, −1), v_print_mm_s=100, link_max_mm=60, contact_tol_mm=0.5,
  extra: dict (musterspezifisch, Namen aus den ParamSpecs). `params.get(k, d)` liest extra.
- `ParamSpec(name, label, default, unit='mm', minimum, maximum, step, kind='float'|'int'|'choice'|'bool',
  choices, help)`: deklariert einen Musterparameter (deutsche Beschriftung, Bereich), `check(v)`.
- `Segment(kind, shell, points (n,2), closed=False, label='')`, kind ∈ {outer, inner, hole, infill,
  web, outfill}. Schale 0 außen; Infill/Stege tragen `shell = params.shells`.
- `Contact(kind, at, length_mm, segments=(i, j), distance_mm)`, kind ∈ {joint, node, shell}.
- `LayerPath(layer, island, segments, contacts, direction='out_in'|'in_out', restart, meta)`:
  Segmente in Druckreihenfolge; Verbinder implizit als Gerade Ende(i) → Anfang(i + 1).
  `reversed()`, `polyline()`, `connectors()`, `start`, `end`, `closed`, `length`.
- `IslandPlan(segments, contacts=[], meta={})`: Rückgabe einer Musterfunktion.
- `IslandContext`: layer, island, region (Polygon der Insel), sections (ganzes Teil), part_bounds
  (x_min, y_min, x_max, y_max; y-Flächen = Außenflächen, x-Flächen = Stoßflächen), params,
  lanes (Schalenringe, gerundet), cavity (Hohlraum innerhalb der innersten Schale), band (Fläche
  für Infill-Mittellinien mit Kontakt zur innersten Schale), spec (ParamSpecs des gerufenen
  Musters), entry/entry_tangent/printed (nur beim Infill-Aufruf). `ctx.param(name)` liefert den
  geprüften Wert oder den Standard aus der ParamSpec. `ctx.w` = Strangbreite.

Eine Familie anlegen (ohne Rückfrage, ohne Merge-Konflikt)
==========================================================

1. Neue Datei `core/src/roboprint/patterns/families/<familie>.py` (z. B. `fugenwand.py`,
   `wellen.py`, `mehrfach.py`, `topologie.py`). Keine andere Datei des Kerns ändern: Die Registry
   findet alle Module in `families/` per pkgutil (alphabetisch, ohne führendes `_`).
2. Muster registrieren, je Muster ein Dekorator::

       from roboprint.patterns import IslandContext, IslandPlan, ParamSpec, Segment, pattern

       @pattern("fugenwand", role="full", label="Fugenwand (Sollbruchstellen)",
                params=[ParamSpec("field_length_mm", "Feldlänge", 300.0, "mm", 150, 800, 5)],
                description="…")
       def build(ctx: IslandContext) -> IslandPlan:
           L = ctx.param("field_length_mm")
           ...
           return IslandPlan(segments, contacts, meta={"fit": fit.to_dict()})

   Rollen:
   - `full`: baut den ganzen Inselpfad (alle Schalen, Stege, Felder). Für die Fugenwand, die
     Fermat-Spirale und Topologie-Muster. Wird im Preset bzw. in `outfill` (Fugenwand) oder
     `infill` gewählt; der andere Platz muss `none` sein.
   - `outfill`: liefert einen geschlossenen Ring (ein Segment mit closed=True oder eine Kette, deren
     Ende den Anfang trifft), der den Außenring der Schale 0 ersetzt (O1 Welle). Naht, Schalen-
     wechsel und innere Schalen macht der Kern (`shell_chain`), Segmentart dann `outfill`.
   - `infill`: Segmente (kind infill/web) im Hohlraum, angehängt nach den Schalen. Beginn am
     besten bei `ctx.entry` (Ende des Schalenpfads, Richtung `ctx.entry_tangent`); ein Verbinder
     ist erlaubt, wenn er kurz (≤ link_max_mm) und über Material ist. Bereits gedruckt:
     `ctx.printed`.
   `layer_invariant=False` setzen, wenn das Ergebnis von `ctx.layer` oder `ctx.sections` abhängt.
3. Vertrag einer Musterfunktion:
   - Richtung **außen → innen**, als gerade Schicht gedacht. Die Umkehrung für ungerade Schichten
     (`alternate`) macht der Kern; das Muster muss nur dafür sorgen, dass die Bahn umkehrbar ist
     (sie ist es immer) und dass jede Schicht dieselbe XY-Geometrie hat (M3).
   - Punkte in Frame P, abgetastet mit `resample_curve(pts, params.step_mm, params.chord_tol_mm)`
     (Abstand ≤ step_mm, Sehnenfehler ≤ 0,5 mm); Bögen vorher fein erzeugen (`arc_points`,
     `tangent_arc`, `biarc`, `fillet_polyline` mit chord_tol 0,05).
   - Stoßen Segmente aneinander, ist der Verbinder Länge 0 (Ende(i) == Anfang(i + 1)).
   - Gewollte Kontakte (Fuge, Knoten, Steg an Schale) liegen bei Mittellinienabstand
     [(1 − ε)·w, w]; deklariere sie als `Contact` (Art und Lage), gemessen werden sie ohnehin.
   - Naht (Anfang/Ende des Pfads) nicht auf Außen- oder Stoßfläche: `layout.choose_seam(loop,
     ctx.region, ctx.part_bounds, ctx.params)` nutzen oder `layout.face_clearance` prüfen.
   - `meta` JSON-fähig halten (z. B. `fit.to_dict()` aus `fit_to_length`, Fugenlagen).
4. Tests in `core/tests/test_patterns_<familie>.py`: `plan_pattern` auf den Querschnitten
   600×200, 600×300, 600×365 (und Öffnung/Inseln, wo sinnvoll), `measure(...).ok` muss True sein
   (keine `error`-Verstöße), dazu `preview` und ein SVG. Ein Preset nach
   `core/src/roboprint/patterns/presets/<muster>.json`.

Helfer für Familien
===================

geometry.py: `polygons`, `offset_region`, `offset_ring`, `cavity`, `centerline_band`, `dedupe`,
`arc_length`, `densify`, `resample_curve`, `curvature_radius`, `chord_error_estimate`, `Loop`
(Ring mit Bogenlänge: point, tangent, project, sub, reversed), `arc_points`, `tangent_arc`, `biarc`,
`fillet_polyline`. layout.py: `fit_to_length`, `choose_seam`, `face_clearance`, `protected_faces`.
shells.py: `shell_lanes`, `shell_chain(ctx, ring0=None, ring0_kind='outer')`, `lane_change`.
types.py: `reverse_layer`, `Segment.reversed`, `LayerPath.reversed`.

Grundmuster und Schichtfolge
============================

Ohne Muster (beide Plätze `none`, Preset `schalen`) gilt das Grundmuster „Schalen ohne Infill“
(shells.py): alle Schalen einer Insel als ein Strang, Schalenwechsel als S-Kurve aus zwei Bögen
mit Radius w ohne Doppelmaterial, Naht in der Mitte eines Eckbogens (layout.py). Mit
`layer_order = 'alternate'` ist Schicht L + 1 die exakte Umkehrung von Schicht L, der Schicht-
wechsel ein reiner Z-Hub (Ende L == Anfang L + 1). Bei geändertem Querschnitt: `restart` (plan.py).

Metriken (metrics.py) messen M1–M7 wie dort beschrieben; Verstöße mit Schweregrad `error` machen
ein Muster ungültig, `warn` sind Zielverfehlungen (z. B. Radius < w, Naht an einer Fläche).
"""

from roboprint.patterns.geometry import (
    Loop,
    arc_length,
    arc_points,
    biarc,
    cavity,
    centerline_band,
    chord_error_estimate,
    curvature_radius,
    dedupe,
    densify,
    fillet_polyline,
    offset_region,
    offset_ring,
    polygons,
    resample_curve,
    tangent_arc,
)
from roboprint.patterns.layout import FitResult, choose_seam, face_clearance, fit_to_length, protected_faces
from roboprint.patterns.metrics import PathMetrics, PatternReport, Violation, measure
from roboprint.patterns.plan import plan_pattern
from roboprint.patterns.preview import (
    load_preset,
    make_outline,
    preset_params,
    preview,
    preview_svg,
    save_preset,
)
from roboprint.patterns.registry import Pattern, catalog, get, names, pattern, register
from roboprint.patterns.shells import lane_change, shell_chain, shell_lanes
from roboprint.patterns.types import (
    CONTACT_KINDS,
    CORE_PARAM_SPECS,
    CROSS_KINDS,
    OUTER_KINDS,
    SEGMENT_KINDS,
    SHELL_KINDS,
    Contact,
    IslandContext,
    IslandPlan,
    Lane,
    LayerPath,
    ParamSpec,
    PatternParams,
    Segment,
    params_from_dict,
    reverse_layer,
)

__all__ = [
    "CONTACT_KINDS",
    "CORE_PARAM_SPECS",
    "CROSS_KINDS",
    "OUTER_KINDS",
    "SEGMENT_KINDS",
    "SHELL_KINDS",
    "Contact",
    "FitResult",
    "IslandContext",
    "IslandPlan",
    "Lane",
    "LayerPath",
    "Loop",
    "ParamSpec",
    "PathMetrics",
    "Pattern",
    "PatternParams",
    "PatternReport",
    "Segment",
    "Violation",
    "arc_length",
    "arc_points",
    "biarc",
    "catalog",
    "cavity",
    "centerline_band",
    "choose_seam",
    "chord_error_estimate",
    "curvature_radius",
    "dedupe",
    "densify",
    "face_clearance",
    "fillet_polyline",
    "fit_to_length",
    "get",
    "lane_change",
    "load_preset",
    "make_outline",
    "measure",
    "names",
    "offset_region",
    "offset_ring",
    "params_from_dict",
    "pattern",
    "plan_pattern",
    "polygons",
    "preset_params",
    "preview",
    "preview_svg",
    "protected_faces",
    "register",
    "resample_curve",
    "reverse_layer",
    "save_preset",
    "shell_chain",
    "shell_lanes",
    "tangent_arc",
]
