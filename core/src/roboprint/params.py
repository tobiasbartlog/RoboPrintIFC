"""Eine Quelle fuer die Bewegungsgeschwindigkeiten (SPEC §10), genutzt von `timing` und `drl`.

Die Zeitachse in `trajectory.json` soll dieselben Geschwindigkeiten abbilden, die das DRL-Programm
kommandiert. Deshalb stehen die Standardwerte und die Zuordnung Bewegungsart -> (v, a) nur hier:

- `print`, `approach`, `retract`: v_print / a_print (im DRL die Vorgaben von `set_velx`/`set_accx`).
- `lift`, `lower`: v_travel / a_travel (im DRL als explizites `vel=`/`acc=` am `movel`).
- `transfer` (`movej`): gelenklinear mit `joint_speed_fraction` der Achsgrenzen
  (`roboprint.robot.JOINT_VEL_LIMITS`), Gelenkbeschleunigung = `JOINT_ACC_FACTOR` x Gelenkgeschwindigkeit.
"""

from __future__ import annotations

V_PRINT_MM_S = 100.0  # A
A_PRINT_MM_S2 = 500.0  # A
V_TRAVEL_MM_S = 250.0  # A
A_TRAVEL_MM_S2 = 1000.0  # A
JOINT_SPEED_FRACTION = 0.30  # A, Gelenke <= 30 % der Grenzen
JOINT_ACC_FACTOR = 4.0  # Gelenkbeschleunigung = Faktor x Gelenkgeschwindigkeit (1/s)

# Bewegungsarten mit der Druckgeschwindigkeit bzw. der Travel-Geschwindigkeit (kartesisch, `movel`).
PRINT_SPEED_KINDS = ("print", "approach", "retract")
TRAVEL_SPEED_KINDS = ("lift", "lower")
CARTESIAN_KINDS = PRINT_SPEED_KINDS + TRAVEL_SPEED_KINDS


def cartesian_speed(
    kind: str,
    v_print_mm_s: float = V_PRINT_MM_S,
    a_print_mm_s2: float = A_PRINT_MM_S2,
    v_travel_mm_s: float = V_TRAVEL_MM_S,
    a_travel_mm_s2: float = A_TRAVEL_MM_S2,
) -> tuple[float, float]:
    """(v, a) in mm/s und mm/s^2 fuer eine kartesische Bewegungsart."""
    if kind in PRINT_SPEED_KINDS:
        return v_print_mm_s, a_print_mm_s2
    if kind in TRAVEL_SPEED_KINDS:
        return v_travel_mm_s, a_travel_mm_s2
    raise ValueError(f"Keine kartesische Bewegungsart: {kind}")
