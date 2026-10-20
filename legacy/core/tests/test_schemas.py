"""Schema-Verträge: gültige Minimalartefakte passieren, Vertragsverletzungen nicht."""

import jsonschema
import pytest

from fgc import domain

PROVENANCE = {
    "source": "test",
    "created": "2026-07-02T12:00:00Z",
    "git_commit": "0000000",
}

FRAME = {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}


def make_setup() -> dict:
    return {
        "schema_version": "0.1",
        "provenance": PROVENANCE,
        "robot": "doosan_m1013",
        "wall_to_base": {"pos_mm": [1000.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        "tcp": FRAME,
        "io_channels": {
            "pump_a": {"kind": "analog_voltage", "index": 0, "physical_range": [0, 10]},
            "pump_b": {"kind": "analog_voltage", "index": 1, "physical_range": [0, 10]},
            "foam": {"kind": "analog_voltage", "index": 2, "physical_range": [0, 5]},
        },
        "deadtime": {"t_tot_s": 2.5, "compensation": "simulation_shift", "provisional": True},
    }


def make_toolpath() -> dict:
    return {
        "schema_version": "0.2",
        "provenance": PROVENANCE,
        "wall_global_id": "2O2Fr$t4X7Zf8NOew3FLOH",
        "targets": [
            {
                "frame": FRAME,
                "v_mm_s": 100.0,
                "io": {"pump_a": 0.8, "pump_b": 0.2},
                "kind": "print",
                "layer": 0,
                "segment_id": "L0-S0",
            }
        ],
        "summary": {"n_layers": 1, "n_targets": 1, "n_print": 1},
    }


def test_setup_valid():
    domain.validate(make_setup(), "setup")


def test_toolpath_valid():
    domain.validate(make_toolpath(), "toolpath")


def test_trajectory_valid():
    domain.validate(
        {
            "schema_version": "0.1",
            "provenance": PROVENANCE,
            "samples": [{"t_s": 0.0, "joints_rad": [0, 0, 0, 0, 0, 0], "io": {"pump_a": 0.8}}],
            "meta": {"duration_s": 0.0, "io_compensated": True},
        },
        "trajectory",
    )


def test_candidates_valid():
    domain.validate(
        {
            "schema_version": "0.1",
            "provenance": PROVENANCE,
            "model": "examples/wand_ohne_oeffnung.ifc",
            "walls": [
                {
                    "global_id": "2O2Fr$t4X7Zf8NOew3FLOH",
                    "eligible": True,
                    "checks": [
                        {"check": "planarity", "passed": True},
                        {"check": "thickness", "passed": True, "provisional": True},
                    ],
                }
            ],
        },
        "candidates",
    )


def test_wallspec_requires_load_bearing():
    spec = {
        "schema_version": "0.1",
        "provenance": PROVENANCE,
        "global_id": "x",
        "geometry": {"vertices_mm": [[0, 0, 0]], "faces": [[0, 0, 0]]},
        "targets": {},
    }
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(spec, "wallspec")


def test_setup_deadtime_is_mandatory():
    setup = make_setup()
    del setup["deadtime"]
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(setup, "setup")


def test_toolpath_rejects_unknown_fields():
    toolpath = make_toolpath()
    toolpath["targets"][0]["t_s"] = 1.0  # Zeit gehoert nicht in den Toolpath (E3)
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(toolpath, "toolpath")


def test_toolpath_requires_summary():
    toolpath = make_toolpath()
    del toolpath["summary"]  # ab v0.2 Vertragsbestandteil (Kennzahlen einmal im Core)
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(toolpath, "toolpath")


def test_toolpath_rejects_unknown_summary_field():
    toolpath = make_toolpath()
    toolpath["summary"]["n_travel"] = 0  # nicht im Vertrag -> additionalProperties: false
    with pytest.raises(jsonschema.ValidationError):
        domain.validate(toolpath, "toolpath")


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        domain.load_schema("nope")
