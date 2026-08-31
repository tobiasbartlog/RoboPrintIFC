"""Gradierungs-Ebene: Pro-Abschnitts-Overrides + Auflösung (Issue #82).

Zwei Ebenen:
- ``resolve_section_params`` — die reine Auflösung „global + Override → effektiv".
  Die Py↔TS-Parität (geteilte Golden-Fälle ``section-params.golden.json``) prüft
  das Paritäts-Manifest: ``test_parity.py::test_golden[section-params]``.
- ``set_process_params(sections=…)`` — die Persistenz des ``sections``-Blocks
  (additiv, schema-valide, nach Neuladen wiederhergestellt).
"""

from __future__ import annotations

import math

import pytest

from fgc.domain.process_params import (
    effective_section_params,
    job_global_params,
    job_orientation,
    job_section_override,
    job_slice_overrides,
    resolve_section_params,
    section_orientation,
    section_slice_overrides,
)


def test_unset_field_inherits_global() -> None:
    """Ungesetztes Feld erbt global, gesetztes übersteuert — für Slice UND Orientierung."""
    g = {
        "slice": {"layer_height_mm": 8.0, "n_shells": 2},
        "orientation": {"lead_deg": 10.0, "kipp_deg": 5.0},
    }
    o = {"slice": {"n_shells": 4}, "orientation": {"kipp_deg": -3.0}}
    assert resolve_section_params(g, o) == {
        "slice": {"layer_height_mm": 8.0, "n_shells": 4},
        "orientation": {"lead_deg": 10.0, "kipp_deg": -3.0},
    }


def test_none_override_does_not_win() -> None:
    """None im Override übersteuert nicht (erbt global) — wie job_slice_overrides."""
    assert resolve_section_params(
        {"slice": {"layer_height_mm": 8.0}}, {"slice": {"layer_height_mm": None}}
    ) == {"slice": {"layer_height_mm": 8.0}}


def test_zero_override_wins() -> None:
    """0 ist ein gesetzter Wert (übersteuert), nicht „ungesetzt"."""
    assert resolve_section_params(
        {"orientation": {"kipp_deg": 5.0}}, {"orientation": {"kipp_deg": 0.0}}
    ) == {"orientation": {"kipp_deg": 0.0}}


def test_empty_result_is_sparse() -> None:
    """Weder global noch je Abschnitt gesetzt → leeres Ergebnis (fällt auf Karte)."""
    assert resolve_section_params({}, {}) == {}
    assert resolve_section_params({"slice": {}}, {"orientation": {}}) == {}


def test_job_helpers_read_blocks() -> None:
    """job_global_params/job_section_override/effective_section_params lesen den Job."""
    job = {
        "process_params": {
            "slice": {"layer_height_mm": 8.0},
            "orientation": {"lead_deg": 10.0},
            "sections": {"abschnitt-1": {"slice": {"layer_height_mm": 6.0}}},
        }
    }
    assert job_global_params(job) == {
        "slice": {"layer_height_mm": 8.0},
        "orientation": {"lead_deg": 10.0},
    }
    assert job_section_override(job, "abschnitt-1") == {"slice": {"layer_height_mm": 6.0}}
    assert job_section_override(job, "abschnitt-2") == {}
    # Abschnitt 1 übersteuert layer, erbt Orientierung; Abschnitt 2 erbt komplett.
    assert effective_section_params(job, "abschnitt-1") == {
        "slice": {"layer_height_mm": 6.0},
        "orientation": {"lead_deg": 10.0},
    }
    assert effective_section_params(job, "abschnitt-2") == {
        "slice": {"layer_height_mm": 8.0},
        "orientation": {"lead_deg": 10.0},
    }


def test_old_job_without_sections_inherits_global() -> None:
    """Altjob ohne sections-Block: jeder Abschnitt erbt komplett global."""
    job = {"process_params": {"slice": {"n_shells": 3}}}
    assert job_section_override(job, "abschnitt-1") == {}
    assert effective_section_params(job, "abschnitt-1") == {"slice": {"n_shells": 3}}


# --- Abschnitts-effektive Leser: Spiegel von job_slice_overrides/job_orientation
# --- (Issue #188 — die Kern-Tür slict/orientiert je Abschnitt) -------------------


def test_section_slice_overrides_override_wins_and_expands_io() -> None:
    """Abschnitts-Override übersteuert; io-Skalar wird wie global auf Kanäle gedehnt."""
    job = {
        "process_params": {
            "slice": {"layer_height_mm": 8.0, "io_print": 0.7},
            "sections": {"abschnitt-1": {"slice": {"layer_height_mm": 6.0}}},
        }
    }
    assert section_slice_overrides(job, "abschnitt-1") == {
        "layer_height_mm": 6.0,
        "io_print": {"pump_a": 0.7, "pump_b": 0.7},
    }


def test_section_slice_overrides_without_override_mirror_job() -> None:
    """Ohne Abschnitts-Override: byte-gleich zu job_slice_overrides (Regressionsanker)."""
    job = {
        "process_params": {
            "slice": {"layer_height_mm": 8.0, "n_shells": 4, "io_travel": 0.0},
            "sections": {"abschnitt-1": {"slice": {"layer_height_mm": 6.0}}},
        }
    }
    assert section_slice_overrides(job, "abschnitt-2") == job_slice_overrides(job)
    # Altjob ganz ohne process_params: leer → Karten-/Code-Default (wie global).
    assert section_slice_overrides({}, "abschnitt-1") == {} == job_slice_overrides({})


def test_section_orientation_override_wins_inherits_rest() -> None:
    """Kipp-Override wirkt nur im Abschnitt, Lead erbt global; Grad→Radiant wie global."""
    job = {
        "process_params": {
            "orientation": {"lead_deg": 10.0},
            "sections": {"abschnitt-1": {"orientation": {"kipp_deg": 25.0}}},
        }
    }
    ori = section_orientation(job, "abschnitt-1")
    assert ori.lead_rad == pytest.approx(math.radians(10.0))
    assert ori.kipp_rad == pytest.approx(math.radians(25.0))


def test_section_orientation_without_override_mirror_job() -> None:
    """Ohne Abschnitts-Override gleich job_orientation; ohne alles 0/0 (senkrecht)."""
    job = {
        "process_params": {
            "orientation": {"lead_deg": 10.0, "kipp_deg": 5.0},
            "sections": {"abschnitt-1": {"orientation": {"kipp_deg": 25.0}}},
        }
    }
    assert section_orientation(job, "abschnitt-2") == job_orientation(job)
    ori = section_orientation({}, "abschnitt-1")
    assert (ori.lead_rad, ori.kipp_rad) == (0.0, 0.0)
