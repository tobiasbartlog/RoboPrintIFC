"""Planer- und Prozessparameter (SPEC §10) mit Overrides aus dem Szenario."""

from __future__ import annotations

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
    t_tot_s: float = 3.0
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
    # Verdichtung (SPEC §5.2/5), mit kleiner Reserve unter den Grenzen 5 mm / 0,005 rad
    dense_tcp_mm: float = 4.9
    dense_dq_rad: float = 0.0049
    # Kosten (SPEC §5.2/3); Gelenkdistanz gewichtet, Abstands- und psi-Strafe
    lambda_d: float = 0.2
    lambda_psi: float = 0.05
    lambda_branch: float = 5.0
    lambda_transfer: float = 0.2
    # Travel: Hoehen des Zwischenpunkts ueber dem Druckstand (SPEC §5.3)
    via_heights_mm: tuple[float, ...] = (150.0, 300.0, 500.0)

    @property
    def psi_grid(self) -> np.ndarray:
        n = int(round(360.0 / self.psi_step_deg))
        return np.radians(np.arange(n) * self.psi_step_deg)

    def as_summary(self) -> dict[str, float | str | bool]:
        out: dict[str, float | str | bool] = {}
        for k, v in asdict(self).items():
            if isinstance(v, tuple):
                continue
            out[k] = float(v) if isinstance(v, int) and not isinstance(v, bool) else v
        return out


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
        upd[key] = type(cur)(v) if not isinstance(cur, tuple) else tuple(v)
    return replace(p, **upd)
