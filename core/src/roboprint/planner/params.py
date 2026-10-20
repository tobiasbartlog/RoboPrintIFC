"""Planer- und Prozessparameter (SPEC §10) mit Overrides aus dem Szenario."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from typing import Any

import numpy as np

from roboprint import params as speeds


@dataclass(frozen=True)
class PlannerParams:
    # Prozess (SPEC §10)
    layer_height_mm: float = 10.0
    bead_width_mm: float = 30.0
    shells: int = 2
    v_print_mm_s: float = speeds.V_PRINT_MM_S
    v_travel_mm_s: float = speeds.V_TRAVEL_MM_S
    joint_speed_fraction: float = speeds.JOINT_SPEED_FRACTION
    z_lift_mm: float = 30.0
    approach_mm: float = 20.0
    v_pump_v: float = 5.0
    t_tot_s: float = 3.0  # Pumpen-Vorlauf, einmal je Strang am Strangbeginn (SPEC §5.5)
    # Verbinder (SPEC §5.3, Nutzer 20.10.2026): laengste gedruckte Gerade zwischen zwei Ringen eines
    # Strangs; 0 schaltet Verbinder ab (je Ring ein Strang, alter Ablauf)
    link_max_mm: float = 60.0
    r_blend_mm: float = 2.0
    d_hard_mm: float = 10.0
    d_target_mm: float = 50.0
    d_target_printed_mm: float = 20.0  # Sollabstand gegen den Druckstand (SPEC §10)
    r_free_mm: float = 40.0
    tau_max_deg: float = 0.0
    psi_step_deg: float = 15.0
    step_mm: float = 20.0
    dq_max_rad: float = 0.3
    tcp_name: str = "FGC_30GUT"
    dialect: str = "v2"
    # Zerlegung: Nutzergrenze der Modulhoehe (z. B. Lehm unter Eigengewicht, Nutzerentscheidung
    # 19.10.2026). Die Zerlegung schlaegt H* <= diesem Wert vor, kleiner, wenn der Planer hoeher
    # nicht machbar ist.
    module_height_max_mm: float = 400.0
    # Druckplatz in S (Nutzerentscheidung 20.10.2026): Alle Module eines Laufs stehen hier, Gier 0,
    # lange Seite zum Roboter. Standard 50 mm vor der Tischmitte; nur Rastpunkte aus `spot_grid()`.
    spot_x_mm: float = 0.0
    spot_y_mm: float = -50.0
    # Verdichtung (SPEC §5.2/5), mit kleiner Reserve unter den Grenzen 5 mm / 0,005 rad
    dense_tcp_mm: float = 4.9
    dense_dq_rad: float = 0.0049
    # Kosten (SPEC §5.2/3); Gelenkdistanz gewichtet, Abstands- und psi-Strafe
    lambda_d: float = 0.2
    lambda_psi: float = 0.05
    lambda_branch: float = 5.0
    lambda_transfer: float = 0.2
    # Verbinder: Gewicht der Gelenkdistanz vom Ende des vorigen Rings zum Start des naechsten (wie
    # eine Kante im Ring, damit der Verbinder ohne grosse Drehung auskommt)
    lambda_link: float = 1.0
    # Travel: Hoehen des Zwischenpunkts ueber dem Druckstand (SPEC §5.3)
    via_heights_mm: tuple[float, ...] = (150.0, 300.0, 500.0)
    # Druckmuster (opt-in, docs/muster/ARTEFAKT-FORMAT.md). Alle auf dem Standard: Slicer wie bisher
    # (SPEC §5.1). `pattern_params` ist ein JSON-Objekt als Text (sortierte Schluessel), damit die
    # Parameter hashbar bleiben und in summary.params passen; `pattern_preset` ein Pfad zu einem
    # Preset-JSON (roboprint.patterns.load_preset), relativ zum Repo oder absolut.
    layer_order: str = "same"
    infill_pattern: str = "none"
    outfill_pattern: str = "none"
    pattern_params: str = ""
    pattern_preset: str = ""

    def __post_init__(self) -> None:
        check_spot(self.spot_x_mm, self.spot_y_mm)
        if self.layer_order not in LAYER_ORDERS:
            raise ValueError(f"layer_order = {self.layer_order!r}, erlaubt {LAYER_ORDERS}")

    @property
    def uses_pattern(self) -> bool:
        """True, wenn ein Musterparameter vom Standard abweicht (Slicer plant dann mit Muster)."""
        return any(getattr(self, k) != v for k, v in PATTERN_DEFAULTS.items())

    @property
    def psi_grid(self) -> np.ndarray:
        n = int(round(360.0 / self.psi_step_deg))
        return np.radians(np.arange(n) * self.psi_step_deg)

    def as_summary(self) -> dict[str, float | str | bool]:
        out: dict[str, float | str | bool] = {}
        for k, v in asdict(self).items():
            if isinstance(v, tuple):
                continue
            if k in PATTERN_DEFAULTS and v == PATTERN_DEFAULTS[k]:
                continue  # Muster opt-in: ohne Muster bleibt summary.params wie bisher
            out[k] = float(v) if isinstance(v, int) and not isinstance(v, bool) else v
        return out


LAYER_ORDERS = ("same", "alternate")
#: Musterparameter und ihre Standardwerte (= kein Muster, Verhalten wie SPEC §5.1)
PATTERN_DEFAULTS: dict[str, str] = {
    "layer_order": "same",
    "infill_pattern": "none",
    "outfill_pattern": "none",
    "pattern_params": "",
    "pattern_preset": "",
}


def pattern_params_json(value: Any) -> str:
    """`pattern_params` aus Szenario oder API (Objekt oder JSON-Text) als kanonischer JSON-Text."""
    if value is None or value == "":
        return ""
    obj = json.loads(value) if isinstance(value, str) else value
    if not isinstance(obj, dict):
        raise ValueError("pattern_params muss ein Objekt sein")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) if obj else ""


# Rastfeld des Druckplatzes in S (mm): x quer zum Roboter, y zum Roboter hin positiv. Gemessen am
# Quader 600 x 200 (Hoehensuche, 20.10.2026): y = 0 ... -250 ergibt H* 940 ... 850 mm, y = +100 nur
# 250 mm (Glied 4 im Druckstand); x = +-200 bei y = -50 ergibt >= 950 mm, x = -400 nur 810 mm.
SPOT_STEP_MM = 50.0
SPOT_X_RANGE_MM = (-200.0, 200.0)
SPOT_Y_RANGE_MM = (-250.0, 0.0)


def spot_grid() -> list[tuple[float, float]]:
    """Alle Rastpunkte (x, y) des Druckplatzes in S."""
    def axis(lo: float, hi: float) -> list[float]:
        return [lo + i * SPOT_STEP_MM for i in range(int(round((hi - lo) / SPOT_STEP_MM)) + 1)]

    return [(x, y) for y in axis(*SPOT_Y_RANGE_MM) for x in axis(*SPOT_X_RANGE_MM)]


def check_spot(x_mm: float, y_mm: float) -> None:
    """ValueError, wenn (x, y) kein Rastpunkt ist."""
    for v, (lo, hi), name in ((x_mm, SPOT_X_RANGE_MM, "x"), (y_mm, SPOT_Y_RANGE_MM, "y")):
        on_grid = abs(v / SPOT_STEP_MM - round(v / SPOT_STEP_MM)) < 1e-9
        if not (lo - 1e-9 <= v <= hi + 1e-9 and on_grid):
            raise ValueError(
                f"Druckplatz {name} = {v:g} mm ist kein Rastpunkt "
                f"({lo:g} bis {hi:g} mm im {SPOT_STEP_MM:g}-mm-Raster)"
            )


_ALIASES = {
    "h": "layer_height_mm",
    "w": "bead_width_mm",
    "v_print": "v_print_mm_s",
    "v_travel": "v_travel_mm_s",
    "d_hard": "d_hard_mm",
    "d_target": "d_target_mm",
    "d_target_printed": "d_target_printed_mm",
    "r_free": "r_free_mm",
    "z_lift": "z_lift_mm",
}


def from_overrides(overrides: dict[str, Any] | None, d_target_mm: float | None = None) -> PlannerParams:
    """Defaults aus SPEC §10, d_target aus der Workstation, dann Szenario-`params`."""
    p = PlannerParams()
    if d_target_mm is not None:
        p = replace(p, d_target_mm=float(d_target_mm))
    if not overrides:
        return p
    names = {f.name: f.type for f in fields(PlannerParams)}
    upd: dict[str, Any] = {}
    for k, v in overrides.items():
        key = _ALIASES.get(k, k)
        if key not in names:
            raise ValueError(f"Unbekannter Parameter im Szenario: {k}")
        cur = getattr(p, key)
        if key == "pattern_params":
            upd[key] = pattern_params_json(v)
        elif isinstance(v, dict):
            raise ValueError(f"Parameter {k}: Objekt nur bei pattern_params erlaubt")
        else:
            upd[key] = type(cur)(v) if not isinstance(cur, tuple) else tuple(v)
    return replace(p, **upd)
