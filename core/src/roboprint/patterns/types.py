"""Datentypen der Druckmuster: Parameter, Parameterbeschreibung, Segmente, Kontakte, Schichtpfade
und der Kontext, den eine Musterfamilie je Insel bekommt.

Alle Koordinaten in Frame P (mm), nur XY. Die Schicht-Z-Lage ergibt sich aus `layer` (SPEC §5.2:
TCP beim Druck auf z_P = (layer + 1)·h); dieses Modul kennt kein Z.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from typing import Any

import numpy as np

#: Erlaubte Segmentarten (ARTEFAKT-FORMAT.md, `kind` in toolpath.json)
SEGMENT_KINDS = ("outer", "inner", "hole", "infill", "web", "outfill")
#: Segmentarten der äußersten Lage (sichtbare Außenhaut, längste gerade Außenstrecke)
OUTER_KINDS = frozenset({"outer", "outfill"})
#: Segmentarten, die zur Schalenhülle zählen
SHELL_KINDS = frozenset({"outer", "inner", "hole", "outfill"})
#: Segmentarten, die Querverbindungen bilden (stützen die Außenhaut, Knoten)
CROSS_KINDS = frozenset({"infill", "web"})
#: Kontaktarten (ARTEFAKT-FORMAT.md, Nachtrag 18:45)
CONTACT_KINDS = ("joint", "node", "shell")
LAYER_ORDERS = ("same", "alternate")
#: Richtung eines Schichtpfads: außen → innen (gerade Schichten) oder innen → außen (Umkehrung)
DIRECTIONS = ("out_in", "in_out")


# --------------------------------------------------------------------------- Parameter


@dataclass(frozen=True)
class PatternParams:
    """Parameter eines Druckmusters (alle Längen in mm).

    - `bead_width_mm` w, `layer_height_mm` h, `shells` Schalen je Seite (≥ 1).
    - `layer_order`: `alternate` (Standard dieses Moduls: gerade Schichten außen → innen, ungerade
      als exakte Umkehrung derselben Bahn) oder `same` (jede Schicht gleich, Schichtwechsel
      diagonal wie heute). Ob `alternate` im Szenario Standard wird, entscheidet der Nutzer (M3).
    - `infill` / `outfill`: Name eines registrierten Musters, `none` = keins (siehe registry).
    - `step_mm`: größter Wegpunktabstand; `chord_tol_mm`: größter Sehnenfehler (M6).
    - `eps`: Kontakt-/Abstandstoleranz ε (M2, M7); `delta_mm`: Überhangtoleranz δ (M3).
    - `corner_radius_mm`: Rundung konvexer Ecken jeder Schalen-Mittellinie; None = w (Ziel M6).
    - `transition_radius_mm`: Radius der S-Kurve beim Schalenwechsel; None = w (Ziel M6).
    - `seam_corner`: Ecke der Teil-Bounding-Box, zu der die Naht bei Gleichstand rückt:
      (−1, −1) = (x_min, y_min), (+1, −1) = (x_max, y_min) usw.
    - `v_print_mm_s`: Druckgeschwindigkeit für die Kennzahl Druckzeit (SPEC §10: 100 mm/s).
    - `link_max_mm`: längster Verbinder zwischen zwei Segmenten (SPEC §10: 60 mm).
    - `contact_tol_mm`: Abstände bis w + contact_tol zählen noch als Kontakt (Sehnenfehler der
      Polylinie, M6); darüber ist es ein Spalt.
    - `extra`: musterspezifische Werte (Namen aus den ParamSpecs der Familie, z. B.
      `field_length_mm`). Lesen mit `params.get(key, default)` bzw. `ctx.param(key)`.
    """

    bead_width_mm: float = 30.0
    layer_height_mm: float = 10.0
    shells: int = 2
    layer_order: str = "alternate"
    infill: str = "none"
    outfill: str = "none"
    step_mm: float = 20.0
    chord_tol_mm: float = 0.5
    eps: float = 0.15
    delta_mm: float = 2.0
    corner_radius_mm: float | None = None
    transition_radius_mm: float | None = None
    seam_corner: tuple[int, int] = (-1, -1)
    v_print_mm_s: float = 100.0
    link_max_mm: float = 60.0
    contact_tol_mm: float = 0.5
    extra: Mapping[str, Any] = field(default_factory=dict, hash=False)

    @property
    def w(self) -> float:
        return float(self.bead_width_mm)

    @property
    def corner_radius(self) -> float:
        return self.w if self.corner_radius_mm is None else float(self.corner_radius_mm)

    @property
    def transition_radius(self) -> float:
        return self.w if self.transition_radius_mm is None else float(self.transition_radius_mm)

    def get(self, key: str, default: Any = None) -> Any:
        """Musterspezifischer Parameter aus `extra`."""
        return self.extra.get(key, default)

    def with_extra(self, **values: Any) -> PatternParams:
        return replace(self, extra={**self.extra, **values})

    def validate(self) -> PatternParams:
        if self.bead_width_mm <= 0 or self.layer_height_mm <= 0:
            raise ValueError("bead_width_mm und layer_height_mm müssen > 0 sein")
        if self.shells < 1:
            raise ValueError("shells muss >= 1 sein")
        if self.layer_order not in LAYER_ORDERS:
            raise ValueError(f"layer_order muss in {LAYER_ORDERS} liegen, nicht {self.layer_order!r}")
        if self.step_mm <= 0 or self.chord_tol_mm <= 0:
            raise ValueError("step_mm und chord_tol_mm müssen > 0 sein")
        if not 0.0 <= self.eps < 1.0:
            raise ValueError("eps muss in [0, 1) liegen")
        if self.corner_radius < 0 or self.transition_radius <= 0:
            raise ValueError("corner_radius_mm >= 0 und transition_radius_mm > 0")
        if tuple(abs(int(c)) for c in self.seam_corner) != (1, 1):
            raise ValueError("seam_corner muss aus ±1 bestehen, z. B. (-1, -1)")
        return self

    def to_dict(self) -> dict[str, Any]:
        """JSON-fähig: alle Kernfelder plus `extra` flach daneben."""
        out: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "extra":
                continue
            v = getattr(self, f.name)
            out[f.name] = list(v) if isinstance(v, tuple) else v
        out.update(dict(self.extra))
        return out


#: Namen der Kernfelder von PatternParams (alles andere landet in `extra`)
CORE_FIELDS = frozenset(f.name for f in fields(PatternParams)) - {"extra"}


def params_from_dict(data: Mapping[str, Any] | None = None, **overrides: Any) -> PatternParams:
    """PatternParams aus einem flachen Dict: Kernfelder direkt, alle übrigen Schlüssel nach `extra`.
    Ein verschachteltes `extra`-Dict wird ebenfalls übernommen."""
    d = {**dict(data or {}), **overrides}
    extra = dict(d.pop("extra", {}) or {})
    core: dict[str, Any] = {}
    for k, v in d.items():
        if k in CORE_FIELDS:
            core[k] = tuple(int(c) for c in v) if k == "seam_corner" else v
        else:
            extra[k] = v
    if "shells" in core:
        core["shells"] = int(core["shells"])
    return PatternParams(**core, extra=extra).validate()


@dataclass(frozen=True)
class ParamSpec:
    """Beschreibung eines Musterparameters, aus der API und Viewer Regler erzeugen.

    `kind`: `float` | `int` | `choice` | `bool`. `minimum`/`maximum` gelten für Zahlen,
    `choices` für `choice`. `label` und `help` sind deutsch (UI-Text). `unit` z. B. "mm", "°", "".
    """

    name: str
    label: str
    default: Any
    unit: str = "mm"
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    kind: str = "float"
    choices: tuple[str, ...] = ()
    help: str = ""

    def check(self, value: Any) -> Any:
        """Wert prüfen und normieren; ValueError bei falschem Typ oder außerhalb des Bereichs."""
        if self.kind == "choice":
            if value not in self.choices:
                raise ValueError(f"{self.name}: {value!r} nicht in {self.choices}")
            return value
        if self.kind == "bool":
            return bool(value)
        v = int(value) if self.kind == "int" else float(value)
        if not math.isfinite(v):
            raise ValueError(f"{self.name}: kein endlicher Wert")
        if self.minimum is not None and v < self.minimum - 1e-9:
            raise ValueError(f"{self.name} = {v} < Minimum {self.minimum}")
        if self.maximum is not None and v > self.maximum + 1e-9:
            raise ValueError(f"{self.name} = {v} > Maximum {self.maximum}")
        return v

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "default": self.default,
            "unit": self.unit,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "kind": self.kind,
            "choices": list(self.choices),
            "help": self.help,
        }


#: Regler für die Kernparameter (gelten für jedes Muster)
CORE_PARAM_SPECS: tuple[ParamSpec, ...] = (
    ParamSpec("bead_width_mm", "Strangbreite w", 30.0, "mm", 10.0, 60.0, 1.0),
    ParamSpec("layer_height_mm", "Schichthöhe h", 10.0, "mm", 2.0, 30.0, 1.0),
    ParamSpec("shells", "Schalen je Seite", 2, "", 1, 4, 1, kind="int"),
    ParamSpec(
        "layer_order",
        "Schichtfolge",
        "alternate",
        "",
        kind="choice",
        choices=LAYER_ORDERS,
        help="alternate: ungerade Schichten als Umkehrung, Schichtwechsel senkrecht",
    ),
    ParamSpec(
        "corner_radius_mm",
        "Eckradius",
        30.0,
        "mm",
        0.0,
        200.0,
        1.0,
        help="Rundung konvexer Ecken der Schalen-Mittellinie (M6: hart ≥ w/2, Ziel ≥ w)",
    ),
    ParamSpec("transition_radius_mm", "Radius Schalenwechsel", 30.0, "mm", 15.0, 200.0, 1.0),
)


# --------------------------------------------------------------------------- Segmente


def as_xy(points: Any) -> np.ndarray:
    """(n, 2)-Array aus Punkten; ValueError bei falscher Form oder NaN."""
    a = np.asarray(points, dtype=float)
    if a.ndim != 2 or a.shape[1] != 2:
        raise ValueError(f"points muss die Form (n, 2) haben, nicht {a.shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError("points enthält NaN/Inf")
    return a


@dataclass
class Segment:
    """Gedrucktes Stück eines Schichtpfads (Mittellinie, Frame P, XY).

    `kind` ∈ SEGMENT_KINDS, `shell` = Schalenindex (Schale 0 außen; Infill/Stege tragen
    `shell = params.shells`). `closed = True` heißt: letzter Punkt == erster Punkt.
    `label` ist optional (z. B. "Feld 2", "Steg J1→N1") und erscheint in der Vorschau.
    """

    kind: str
    shell: int
    points: np.ndarray
    closed: bool = False
    label: str = ""

    def __post_init__(self) -> None:
        if self.kind not in SEGMENT_KINDS:
            raise ValueError(f"kind {self.kind!r} nicht in {SEGMENT_KINDS}")
        if self.shell < 0:
            raise ValueError("shell muss >= 0 sein")
        self.points = as_xy(self.points)
        if len(self.points) < 2:
            raise ValueError("Segment braucht mindestens 2 Punkte")
        if self.closed and (
            len(self.points) < 4 or not np.allclose(self.points[0], self.points[-1], atol=1e-6)
        ):
            raise ValueError("geschlossenes Segment: mindestens 4 Punkte und letzter == erster Punkt")

    @property
    def start(self) -> np.ndarray:
        return self.points[0]

    @property
    def end(self) -> np.ndarray:
        return self.points[-1]

    @property
    def length(self) -> float:
        return float(np.linalg.norm(np.diff(self.points, axis=0), axis=1).sum())

    def reversed(self) -> Segment:
        return Segment(self.kind, self.shell, self.points[::-1].copy(), self.closed, self.label)


@dataclass
class Contact:
    """Gewollter Kontakt zweier Pfadstücke (Raupen berühren sich, Mittellinienabstand
    in [(1 − ε)·w, w], Bogenlängenabstand > 2·w). Keine Kreuzung.

    - `kind`: `joint` (Fuge: zwei Außenfelder stoßen stumpf), `node` (Knoten: Stege/Gurt berühren
      sich), `shell` (Steg oder Infill an einer Schale, oder Schale an Schale).
    - `at`: Lage (Mitte der Kontaktzone), `length_mm`: Länge der Zone entlang des Pfads.
    - `segments`: Indizes der beiden beteiligten Segmente im LayerPath (i ≤ j).
    - `distance_mm`: kleinster Mittellinienabstand (gemessen; bei deklarierten Kontakten Sollwert).
    """

    kind: str
    at: tuple[float, float]
    length_mm: float = 0.0
    segments: tuple[int, int] = (-1, -1)
    distance_mm: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in CONTACT_KINDS:
            raise ValueError(f"Kontaktart {self.kind!r} nicht in {CONTACT_KINDS}")
        self.at = (float(self.at[0]), float(self.at[1]))

    def to_dict(self, w: float | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kind": self.kind,
            "at": [round(self.at[0], 2), round(self.at[1], 2)],
            "length_mm": round(float(self.length_mm), 2),
            "segments": list(self.segments),
            "distance_mm": None if self.distance_mm is None else round(float(self.distance_mm), 2),
        }
        if w is not None and self.distance_mm is not None:
            d["overlap_mm"] = round(max(0.0, w - float(self.distance_mm)), 2)
        return d


@dataclass
class LayerPath:
    """Ein Strang einer Schicht und Insel: Segmente in Druckreihenfolge.

    Zwischen Segment i und i + 1 liegt implizit der Verbinder als Gerade vom letzten Punkt von i
    zum ersten Punkt von i + 1 (Länge 0, wenn sie aneinanderstoßen). `island` ist der Index der
    Insel im Querschnitt der Schicht (Polygone sortiert nach (x_min, y_min) der Bounding-Box).
    `direction`: `out_in` (Schale 0 zuerst) oder `in_out` (Umkehrung). `contacts`: vom Muster
    deklarierte Kontakte (Absicht); gemessen werden sie in `metrics`. `restart`: Der Pfad setzt
    nicht senkrecht an der Vorschicht an (Querschnitt oder Inselzahl geändert, M4-Ausnahme).
    `meta`: Zusatzinfo des Musters (z. B. Nahtlage), JSON-fähig.
    """

    layer: int
    island: int
    segments: list[Segment]
    contacts: list[Contact] = field(default_factory=list)
    direction: str = "out_in"
    restart: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction muss in {DIRECTIONS} liegen")
        if not self.segments:
            raise ValueError("LayerPath braucht mindestens ein Segment")

    @property
    def start(self) -> np.ndarray:
        return self.segments[0].start

    @property
    def end(self) -> np.ndarray:
        return self.segments[-1].end

    def connectors(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """Verbinder (Anfang, Ende) zwischen aufeinanderfolgenden Segmenten."""
        return [(a.end, b.start) for a, b in zip(self.segments[:-1], self.segments[1:], strict=True)]

    def polyline(self) -> np.ndarray:
        """Ganze Mittellinie inkl. Verbinder als (n, 2), ohne doppelte Folgepunkte."""
        pts = np.vstack([s.points for s in self.segments])
        keep = np.ones(len(pts), bool)
        keep[1:] = np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9
        return pts[keep]

    @property
    def length(self) -> float:
        return float(np.linalg.norm(np.diff(self.polyline(), axis=0), axis=1).sum())

    @property
    def closed(self) -> bool:
        """Geschlossener Zug: Ende == Anfang (z. B. Fugenwand als ein Ring)."""
        return bool(np.linalg.norm(self.end - self.start) < 1e-6 and self.length > 0)

    def reversed(self, layer: int | None = None) -> LayerPath:
        """Exakte Umkehrung: Segmente in umgekehrter Folge, jedes Segment umgekehrt.
        Kontakte behalten Lage und Länge, ihre Segmentindizes werden umgerechnet."""
        n = len(self.segments)
        d = "in_out" if self.direction == "out_in" else "out_in"
        cs = [
            Contact(
                c.kind,
                c.at,
                c.length_mm,
                tuple(sorted((n - 1 - c.segments[0], n - 1 - c.segments[1]))),
                c.distance_mm,
            )
            if min(c.segments) >= 0
            else Contact(c.kind, c.at, c.length_mm, c.segments, c.distance_mm)
            for c in self.contacts
        ]
        return LayerPath(
            self.layer if layer is None else layer,
            self.island,
            [s.reversed() for s in reversed(self.segments)],
            cs,
            d,
            self.restart,
            dict(self.meta),
        )


def reverse_layer(paths: list[LayerPath], layer: int | None = None) -> list[LayerPath]:
    """Umkehrung einer ganzen Schicht: Inseln in umgekehrter Folge, jeder Pfad umgekehrt.
    Ende der Schicht == Anfang der Umkehrung (senkrechter Schichtwechsel, M4)."""
    return [p.reversed(layer) for p in reversed(paths)]


# --------------------------------------------------------------------------- Kontext


@dataclass(frozen=True)
class Lane:
    """Geschlossener Schalenring (Mittellinie) vor dem Öffnen an der Naht.

    `kind`: `exterior` (Außenkontur der Insel bzw. ihres Offsets) oder `hole` (Lochkontur);
    `ring` (n, 2) geschlossen, Außenkonturen gegen den Uhrzeigersinn, Löcher im Uhrzeigersinn.
    """

    shell: int
    kind: str
    ring: np.ndarray


@dataclass
class IslandPlan:
    """Ergebnis einer Musterfunktion für eine Insel (Richtung außen → innen, Schicht gerade).

    `segments` in Druckreihenfolge, `contacts` deklarierte Kontakte (Segmentindizes in `segments`),
    `meta` JSON-fähige Zusatzinfo (z. B. `{"seam": [x, y], "fields": 4, "field_length_mm": 297.5}`).
    """

    segments: list[Segment]
    contacts: list[Contact] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IslandContext:
    """Was eine Musterfunktion über die Insel weiß (siehe Docstring von `roboprint.patterns`).

    - `layer`, `island`: Schicht und Inselindex; `region`: Querschnitt der Insel (shapely Polygon).
    - `sections`: Querschnitte des ganzen Teils {Schicht: Geometrie} (für schichtübergreifende
      Entscheidungen, z. B. Stege an künftigen Laibungen, M3).
    - `part_bounds`: (x_min, y_min, x_max, y_max) aller Querschnitte des Teils. y_min/y_max sind
      die Außenflächen, x_min/x_max die Stoßflächen zum Nachbarmodul (M4-Naht).
    - `params`: PatternParams; `spec`: ParamSpecs des gerade gerufenen Musters (für `param`).
    - `lanes`: Standard-Schalenringe (gerundet), Schale 0 zuerst.
    - `cavity`: Hohlraum innerhalb der innersten Schale (Raupenkante), evtl. leer.
    - `band`: Fläche für Infill-Mittellinien, deren Raupe die innerste Schale gerade berührt.
    - `entry`, `entry_tangent`: Ende des bisherigen Pfads und Fahrtrichtung dort (nur beim
      Infill-Aufruf, sonst None). `printed`: bisherige Segmente dieser Insel (nur Infill).
    """

    layer: int
    island: int
    region: Any
    sections: Mapping[int, Any]
    part_bounds: tuple[float, float, float, float]
    params: PatternParams
    lanes: tuple[Lane, ...]
    cavity: Any
    band: Any
    spec: tuple[ParamSpec, ...] = ()
    entry: np.ndarray | None = None
    entry_tangent: np.ndarray | None = None
    printed: tuple[Segment, ...] = ()

    @property
    def w(self) -> float:
        return self.params.w

    def param(self, name: str) -> Any:
        """Musterparameter: Wert aus `params.extra`, sonst Standard aus der ParamSpec.
        Geprüft gegen Bereich bzw. Auswahl der ParamSpec."""
        for s in self.spec:
            if s.name == name:
                return s.check(self.params.extra.get(name, s.default))
        if name in self.params.extra:
            return self.params.extra[name]
        raise KeyError(f"Parameter {name!r} weder gesetzt noch in der ParamSpec des Musters")

    def lanes_of(self, shell: int, kind: str = "exterior") -> list[np.ndarray]:
        return [ln.ring for ln in self.lanes if ln.shell == shell and ln.kind == kind]
