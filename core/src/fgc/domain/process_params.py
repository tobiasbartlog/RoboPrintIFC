"""Prozessparameter: eine Quelle für Eignungsprüfung UND Slicer (ADR-013).

Zwei Schichten:
- `ProcessWindow` spiegelt die Prozessparameter-Karte
  (materialcards/process_window.provisional.json). Werte dürfen null sein,
  solange S1/S1b/S4 keine Zahlen geliefert haben — Checks, die davon abhängen,
  laufen dann als provisional.
- `SliceParams` sind die konkreten Zahlen, mit denen der Slicer v0 arbeitet.
  Defaults sind PLATZHALTER (provisional, P4) und per CLI überschreibbar;
  belegte Werte aus der Karte überschreiben die Defaults.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

from fgc.paths import PROCESS_WINDOW_CARD

#: Platzhalter-Defaults des Slicers v0 — durch S1/S4-Zahlen zu ersetzen.
#: `default_shells` ist zugleich das einzige Fallback-Literal für die Schalenzahl
#: (ADR-013: E1 und Slicer teilen sich eine Quelle) — s. ProcessWindow.default_shells
#: und SliceParams.n_shells, die beide hierher verweisen.
PROVISIONAL_DEFAULTS = {
    "strand_width_mm": 30.0,
    "layer_height_mm": 10.0,
    "default_shells": 2,
    # Dichte des Druckguts (kg/m³) fuer die Modulgewichts-Rechnung (Issue #90,
    # ADR-022) — PLATZHALTER (Lehm-typisch), bis S1/Materialversuche messen.
    # Wie default_shells: die Prozessfenster-Karte ist die eine Quelle.
    "density_kg_m3": 1900.0,
    # shapely-mitre_limit der Innen-Offsets (shell_rings()/has_narrow_web(),
    # E1 UND Slicer) — Spike S4 (docs/spikes/S4_offset_robustheit.md, Issue #2):
    # shapely-Default 5.0 zerfaellt an scharfen konkaven Reflex-Kerben (Kerbwinkel
    # <=30°) in ein MultiPolygon, 2.0 bleibt im gesamten Testbereich (15-90°)
    # zerfallsfrei. Kein S1-Bezug (reine Offset-Robustheit, nicht
    # materialabhaengig) — anders als default_shells/density_kg_m3 daher fest,
    # nicht `provisional` im Sinne von „wartet auf Messung".
    "mitre_limit": 2.0,
}


@dataclass(frozen=True)
class ProcessWindow:
    """Prozessfenster aus der Karte; None = noch nicht belastbar gemessen."""

    provisional: bool = True
    strand_width_mm: float | None = None
    layer_height_mm: float | None = None
    wall_thickness_min_mm: float | None = None
    wall_thickness_max_mm: float | None = None
    min_inner_radius_strand_widths: float | None = None
    min_web_width_strand_widths: float | None = None
    min_convex_angle_deg: float | None = None
    #: Für E1 angenommene Schalenzahl (Planungsannahme; der Slicer bekommt sein
    #: n_shells zur Laufzeit/CLI, s. SliceParams.from_window). Kartenwert = eine
    #: Quelle (ADR-013).
    default_shells: int = PROVISIONAL_DEFAULTS["default_shells"]
    phi_target_resolution_mm: float | None = None
    #: Dichte des Druckguts (kg/m³) — Default fuer die Modulgewichts-Rechnung
    #: (Issue #90, ADR-022: Gewicht = Volumen × Dichte, Befund kein Gate).
    #: Kartenwert = eine Quelle (ADR-013), wie default_shells; provisorisch bis
    #: S1/Materialversuche.
    density_kg_m3: float = PROVISIONAL_DEFAULTS["density_kg_m3"]
    #: shapely-``mitre_limit`` der Innen-Offsets, die sowohl E1
    #: (``fgc.eligibility.footprint.has_narrow_web``) als auch der Slicer
    #: (``fgc.slicer.shells.shell_rings``) fahren — Spike S4/Issue #2: Kartenwert
    #: = eine Quelle (ADR-013), wie default_shells. Anders als die S1-abhängigen
    #: Felder oben kein Platzhalter, der auf Messung wartet (reine
    #: Offset-Robustheit, materialunabhängig).
    mitre_limit: float = PROVISIONAL_DEFAULTS["mitre_limit"]

    @classmethod
    def load(cls, path: Path | None = None) -> ProcessWindow:
        raw = json.loads((path or PROCESS_WINDOW_CARD).read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass(frozen=True)
class SliceParams:
    """Konkrete Slicer-Parameter; alles Provisorische ist als solches geflaggt."""

    strand_width_mm: float = PROVISIONAL_DEFAULTS["strand_width_mm"]
    layer_height_mm: float = PROVISIONAL_DEFAULTS["layer_height_mm"]
    n_shells: int = PROVISIONAL_DEFAULTS["default_shells"]
    v_print_mm_s: float = 100.0
    v_travel_mm_s: float = 250.0
    io_print: dict[str, float] = field(default_factory=lambda: {"pump_a": 0.5, "pump_b": 0.5})
    io_travel: dict[str, float] = field(default_factory=lambda: {"pump_a": 0.0, "pump_b": 0.0})
    #: Bahn-relativer Anstellwinkel der Düse (Scheibe 3, Issue #61), Radiant.
    #: 0/0 = senkrecht von oben (heutiges Verhalten); der Slicer reicht sie an
    #: ``fgc.domain.orientation.nozzle_quat`` weiter (die eine Orientierungsquelle).
    lead_rad: float = 0.0
    kipp_rad: float = 0.0
    #: shapely-``mitre_limit`` der Schalen-Offsets (``shells.shell_rings``) —
    #: Kartenwert = eine Quelle mit ``ProcessWindow.mitre_limit`` (ADR-013,
    #: Spike S4/Issue #2).
    mitre_limit: float = PROVISIONAL_DEFAULTS["mitre_limit"]

    @classmethod
    def from_window(cls, window: ProcessWindow, **overrides: object) -> SliceParams:
        """Karte > Default; explizite Overrides (CLI/Druckjob) schlagen beides."""
        params = cls()
        if window.strand_width_mm is not None:
            params = replace(params, strand_width_mm=window.strand_width_mm)
        if window.layer_height_mm is not None:
            params = replace(params, layer_height_mm=window.layer_height_mm)
        params = replace(params, n_shells=window.default_shells)
        params = replace(params, mitre_limit=window.mitre_limit)
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(params, **clean) if clean else params


#: Die skalaren Basis-Slice-Parameter, die der Druckjob im ``process_params.slice``-
#: Block übersteuern darf (Scheibe 2, Issue #59; erweitert um Geschwindigkeiten in
#: Scheibe 2b, Issue #60). Jeder Schlüssel bildet 1:1 auf ein skalares
#: ``SliceParams``-Feld ab — so ist der Job-Block eine dünne, schema-validierte
#: Quelle für dieselben Werte.
SLICE_PARAM_KEYS: tuple[str, ...] = (
    "layer_height_mm",
    "strand_width_mm",
    "n_shells",
    "v_print_mm_s",
    "v_travel_mm_s",
)

#: Die io-Overrides der „Fortgeschritten"-Gruppe (Scheibe 2b, Issue #60). Im Job
#: als **einzelner Skalar** je Zielart gehalten (UI-nah, ein Zahlenfeld); beim
#: Lesen auf einen gleichförmigen Wert über die io-Kanäle der Basis-``SliceParams``
#: ausgedehnt (v0 nutzt für alle Pumpen denselben Wert — per-Kanal-Differenzierung
#: gehört in die Materialphase). Getrennt von ``SLICE_PARAM_KEYS``, weil hier ein
#: Skalar→dict-Übergang stattfindet.
IO_PARAM_KEYS: tuple[str, ...] = ("io_print", "io_travel")


def _slice_overrides_from_block(block: dict) -> dict:
    """Übersetzt einen ``slice``-Block in Slice-Overrides (der geteilte Kern).

    Der eine Ausdehnungs-Schritt, den ``job_slice_overrides`` (globaler Block) und
    ``section_slice_overrides`` (abschnitts-effektiver Block, Issue #188) teilen:
    skalare Felder (``SLICE_PARAM_KEYS``) gehen unverändert durch; die io-Felder
    (``IO_PARAM_KEYS``) sind ein **Skalar** und werden auf einen gleichförmigen Wert
    über die io-Kanäle der Basis-``SliceParams`` ausgedehnt (``io_print`` über die
    Druck-, ``io_travel`` über die Travel-Kanäle). Nur *gesetzte* Felder erscheinen —
    ein leerer Block ergibt leere Overrides (Karten-/Code-Default).
    """
    overrides = {k: block[k] for k in SLICE_PARAM_KEYS if block.get(k) is not None}
    base = SliceParams()
    for key in IO_PARAM_KEYS:
        value = block.get(key)
        if value is not None:
            channels = getattr(base, key)  # {pump_a: …, pump_b: …}
            overrides[key] = {ch: float(value) for ch in channels}
    return overrides


def job_slice_overrides(job: dict) -> dict:
    """Liest die gesetzten Slice-Overrides eines Druckjobs (``process_params.slice``).

    Die Wahrheitsquelle für die *globalen* Slice-Basisparameter (Issue #59/#60): nur
    *gesetzte* Felder werden zurückgegeben, damit
    ``SliceParams.from_window(window, **overrides)`` ungesetzte auf Karte/Code-Default
    fallen lässt. Fehlt der Block ganz (Altprojekt), ist das Ergebnis leer → reines
    Karten-/Default-Verhalten (rückwärtskompatibel). Der abschnitts-effektive Spiegel
    ist ``section_slice_overrides`` (Issue #188).
    """
    block = (job.get("process_params") or {}).get("slice") or {}
    return _slice_overrides_from_block(block)


#: Die Winkel-Felder der Orientierungsgruppe (Scheibe 3, Issue #61) — im Job
#: **in Grad** persistiert (UI-nah), erst hier nach Radiant übersetzt. Ein
#: globales, aber erweiterbar entworfenes Objekt (weitere Felder additiv).
ORIENTATION_PARAM_KEYS: tuple[str, ...] = ("lead_deg", "kipp_deg")


@dataclass(frozen=True)
class OrientationParams:
    """Bahn-relative Düsen-Anstellung eines Druckjobs (Radiant), Default 0/0.

    ``lead_rad`` = Lead-/Lag-Winkel (in Fahrtrichtung positiv), ``kipp_rad`` =
    Kipp-Winkel (zur Wand-Außenseite positiv). 0/0 = senkrecht von oben (heutiges
    Verhalten). Weiche Grenzen: der Wert wird nicht gekappt (Warnung statt Sperre,
    ``core/CONTEXT.md``: Befund, kein Gate).
    """

    lead_rad: float = 0.0
    kipp_rad: float = 0.0


def job_orientation(job: dict) -> OrientationParams:
    """Liest die Orientierungsgruppe eines Druckjobs (``process_params.orientation``).

    Wahrheitsquelle für den Anstellwinkel (Issue #61): die im Job in **Grad**
    gehaltenen Felder werden nach Radiant übersetzt. Fehlt der Block (Altprojekt)
    oder ein Feld, gilt 0 → senkrecht von oben (rückwärtskompatibel, heutiges
    Verhalten). Slicer und ``placement`` verrechnen die Winkel über dieselbe
    Funktion ``fgc.domain.orientation.nozzle_quat``.
    """
    block = (job.get("process_params") or {}).get("orientation") or {}
    return OrientationParams(**_orientation_from_block(block).__dict__)


def _orientation_from_block(block: dict) -> OrientationParams:
    lead = block.get("lead_deg")
    kipp = block.get("kipp_deg")
    return OrientationParams(
        lead_rad=math.radians(float(lead)) if lead is not None else 0.0,
        kipp_rad=math.radians(float(kipp)) if kipp is not None else 0.0,
    )


#: Die drei Tri-State-Achsen der IK-Konfiguration (Issue #129, ADR-024) — je Achse
#: ``"a"`` (Zustand A), ``"b"`` (Zustand B) oder fehlend/``None`` = auto (kein
#: Constraint, heutiges Verhalten). Bitschema ``opw.py``: Schulter=1/Ellbogen=2/
#: Handgelenk=4; die Übersetzung Block→Filter macht ``IkConfigFilter.from_block``.
IK_CONFIG_KEYS: tuple[str, ...] = ("shoulder", "elbow", "wrist")

#: Die Prozessgruppen, die ein Abschnitts-Override je Abschnitt übersteuern darf
#: (Gradierungs-Ebene, Issue #82; erweitert um ``ik_config``, Issue #129): dieselben
#: sparse Blöcke wie global — ``slice`` (Schichthöhe/Strangbreite/Schalen +
#: Geschwindigkeiten/io), ``orientation`` (Lead/Kipp in Grad) und ``ik_config``
#: (die drei Tri-State-IK-Schalter). ``motion`` bleibt bewusst global (kein
#: Abschnitts-Override). ``resolve_section_params`` löst alle drei Gruppen generisch
#: (nur gesetzte Felder übersteuern) — Strings (ik_config) wie Zahlen (slice/orientation).
SECTION_OVERRIDE_GROUPS: tuple[str, ...] = ("slice", "orientation", "ik_config")


def resolve_section_params(global_params: dict, section_override: dict) -> dict:
    """Löst globale Prozessparameter + Abschnitts-Override zu den effektiven auf.

    Die reine Auflösung der Gradierungs-Ebene (Issue #82) — analog zum Muster von
    ``job_slice_overrides``: je Gruppe (``slice``/``orientation``) und Feld
    **übersteuert** der Abschnittswert, wenn gesetzt; sonst **erbt** er den
    globalen. Ein Feld, das weder global noch im Abschnitt gesetzt ist, bleibt weg
    → der Aufrufer lässt es auf Prozessfenster-Karte/Code-Default fallen (heutiges
    Verhalten). Das Ergebnis ist wieder *sparse* (leere Gruppen werden nicht
    ausgegeben), damit es sich wie ein normaler ``process_params``-Block weiterlesen
    lässt (``job_slice_overrides``/``job_orientation`` erwarten genau diese Form).

    Kartenfrei und ohne Job-Struktur, damit der Viewer sie bit-gleich spiegeln kann
    (``viewer/src/ui/section-params-state.ts``, geteilte Golden-Fälle
    ``section-params.golden.json``). ``global_params`` und ``section_override`` sind
    je ein Objekt ``{"slice": {...}, "orientation": {...}}`` mit nur gesetzten
    Feldern; ``None``/fehlende Werte übersteuern nie.
    """
    effective: dict = {}
    for group in SECTION_OVERRIDE_GROUPS:
        base = global_params.get(group) or {}
        over = section_override.get(group) or {}
        merged = {k: v for k, v in base.items() if v is not None}
        for key, value in over.items():
            if value is not None:
                merged[key] = value
        if merged:
            effective[group] = merged
    return effective


def job_global_params(job: dict) -> dict:
    """Die globalen ``slice``/``orientation``-Blöcke eines Druckjobs als sparse Objekt.

    Die eine Eingabe für ``resolve_section_params`` (Issue #82): sammelt genau die
    Gruppen, die ein Abschnitt übersteuern darf, aus ``process_params``. Fehlt der
    Block (Altprojekt), ist das Ergebnis leer → jeder Abschnitt erbt reine
    Karten-/Code-Defaults.
    """
    pp = job.get("process_params") or {}
    return {group: pp[group] for group in SECTION_OVERRIDE_GROUPS if pp.get(group)}


def job_section_override(job: dict, section_id: str) -> dict:
    """Der rohe Abschnitts-Override eines Druckjobs (``process_params.sections[id]``).

    Nur die *gesetzten* Overrides dieses Abschnitts (sparse, je Gruppe); fehlt der
    ``sections``-Block oder der Abschnitt (Altprojekt/ungesetzt), ist das Ergebnis
    leer → der Abschnitt erbt komplett global (Issue #82).
    """
    sections = (job.get("process_params") or {}).get("sections") or {}
    return sections.get(section_id) or {}


def effective_section_params(job: dict, section_id: str) -> dict:
    """Die effektiven ``slice``/``orientation``-Blöcke eines Abschnitts (Issue #82).

    Bequemer Durchstich: global (``job_global_params``) + Abschnitts-Override
    (``job_section_override``) → effektive, wieder als ``process_params``-artiges
    Objekt lesbare Gruppen (``resolve_section_params``). So können Slicer/placement
    einen Abschnitt genau wie den globalen Job behandeln.
    """
    return resolve_section_params(job_global_params(job), job_section_override(job, section_id))


def section_slice_overrides(job: dict, section_id: str) -> dict:
    """Die abschnitts-effektiven Slice-Overrides eines Druckjobs (Issue #188).

    Der Spiegel von ``job_slice_overrides`` auf Abschnittsebene: der effektive
    ``slice``-Block dieses Abschnitts (``effective_section_params`` = global +
    Abschnitts-Override, Issue #82) läuft durch **dieselbe** io-Skalar-Ausdehnung
    (``_slice_overrides_from_block``). Ohne Abschnitts-Override ist das Ergebnis
    byte-gleich zu ``job_slice_overrides(job)`` — Abschnitte ohne Override rechnen
    exakt wie bisher (Regressionsanker #188).
    """
    block = effective_section_params(job, section_id).get("slice") or {}
    return _slice_overrides_from_block(block)


def section_orientation(job: dict, section_id: str) -> OrientationParams:
    """Die abschnitts-effektive Orientierungsgruppe eines Druckjobs (Issue #188).

    Der Spiegel von ``job_orientation`` auf Abschnittsebene: der effektive
    ``orientation``-Block dieses Abschnitts (global + Abschnitts-Override, Issue #82)
    läuft durch **dieselbe** Grad→Radiant-Übersetzung (``_orientation_from_block``).
    Ohne Abschnitts-Override ist das Ergebnis gleich ``job_orientation(job)``; fehlt
    alles, gilt 0/0 → senkrecht von oben (rückwärtskompatibel).
    """
    block = effective_section_params(job, section_id).get("orientation") or {}
    return _orientation_from_block(block)
