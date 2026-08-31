"""fgc.setup — Kalibrier-Helfer für das Setup-Artefakt (ADR-006, §9.3).

Das Setup-Artefakt ist die eine Stelle, an der Bauteilwelt und Roboterwelt
verheiratet werden (ADR-006): ``wall_to_base``-Frame (aus dem
3-Punkt-Antastverfahren), TCP, Kanal-Mapping und gemessene Totzeit.

Öffentliche API
---------------
``three_point_frame(p0, p1, p2)``
    Berechnet Frame (pos_mm, quat) aus drei Roboterposen.
``PROVISIONAL_TCP`` / ``PROVISIONAL_IO_CHANNELS`` / ``PROVISIONAL_DEADTIME``
    Provisorische Standardwerte (mit ``provisional: true`` markiert), die
    ``fgc setup new`` ohne ``--template`` einsetzt, bis S1/S1b Messwerte
    liefern.
``setup_artifact(...)``
    Baut das schema-konforme Setup-Dict für ``domain.validate``.
"""

from __future__ import annotations

from typing import Any

from fgc.setup.frame3p import three_point_frame

__all__ = [
    "three_point_frame",
    "PROVISIONAL_TCP",
    "PROVISIONAL_IO_CHANNELS",
    "PROVISIONAL_DEADTIME",
    "setup_artifact",
]

# ---------------------------------------------------------------------------
# Provisorische Standardwerte — bis S1/S1b Messwerte liefern (P4, ADR-006)
# ---------------------------------------------------------------------------

#: TCP-Frame: Düse 200 mm entlang Flansch-Z, keine Rotation — provisorisch
#: bis der tatsächliche Werkzeugoffset ausgemessen ist.
PROVISIONAL_TCP: dict[str, Any] = {
    "pos_mm": [0.0, 0.0, 200.0],
    "quat": [1.0, 0.0, 0.0, 0.0],
}

#: Kanal-Mapping: Pump A → AO0 (0–10 V), Pump B → AO1 (0–10 V),
#: Schaum → AO2 (0–5 V) — entspricht dem erwarteten Doosan-M1013-Aufbau,
#: provisorisch bis Verkabelung bestätigt (S1).
PROVISIONAL_IO_CHANNELS: dict[str, Any] = {
    "pump_a": {"kind": "analog_voltage", "index": 0, "physical_range": [0.0, 10.0]},
    "pump_b": {"kind": "analog_voltage", "index": 1, "physical_range": [0.0, 10.0]},
    "foam": {"kind": "analog_voltage", "index": 2, "physical_range": [0.0, 5.0]},
}

#: Totzeit: 3,0 s als Schätzwert (Schlauchlänge ~1 m, Förderrate ~30 ml/s);
#: muss in Spike S1 gemessen werden (→ ADR-012).
PROVISIONAL_DEADTIME: dict[str, Any] = {
    "t_tot_s": 3.0,
    "compensation": "simulation_shift",
    "provisional": True,
}


def setup_artifact(
    robot: str,
    wall_to_base: dict[str, Any],
    tcp: dict[str, Any],
    io_channels: dict[str, Any],
    deadtime: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Baut das schema-konforme Setup-Artefakt-Dict.

    Rein strukturell — keine Validierung hier; der Aufrufer ruft
    ``domain.validate(artifact, 'setup')`` auf.
    """
    return {
        "schema_version": "0.1",
        "provenance": provenance,
        "robot": robot,
        "wall_to_base": wall_to_base,
        "tcp": tcp,
        "io_channels": io_channels,
        "deadtime": deadtime,
    }
