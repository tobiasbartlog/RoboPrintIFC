"""Modulgrenzen-Pruefung (Issue #90, ADR-022): reines Modul `fgc.decompose.limits`.

Geprueft wird das externe Verhalten: Teil-Abmessungen + optionale Obergrenzen +
Dichte → Befund je Grenze (eingehalten/verletzt) + Gewicht (Volumen × Dichte).
Grenzfaelle per Golden (`fixtures/module_limits.golden.json`, handgerechnet):
keine Obergrenzen, exakt auf der Grenze (= eingehalten), Verletzung,
abweichende Dichte. Der Dichte-Default kommt aus der Prozessfenster-Karte
(eine Quelle, wie die Schalenzahl) — **Befund, kein Gate**: nichts wirft, wenn
eine Grenze verletzt ist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fgc.decompose import (
    Cut,
    DecompositionPlan,
    ModuleLimits,
    Section,
    SectionPlan,
    check_module,
    check_plan,
)
from fgc.domain.process_params import PROVISIONAL_DEFAULTS, ProcessWindow
from fgc.placement import PlacementOption, WallSurface

GOLDEN = Path(__file__).parent / "fixtures" / "module_limits.golden.json"


# --- Golden: handgerechnete Grenzfaelle -----------------------------------------


def test_check_module_matches_golden_cases():
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert doc["cases"], "Golden-Datei ohne Faelle"
    for case in doc["cases"]:
        check = check_module(
            case["length_mm"],
            case["height_mm"],
            case["thickness_mm"],
            density_kg_m3=case["density_kg_m3"],
            limits=ModuleLimits.from_dict(case["limits"]),
        )
        assert check.to_dict() == case["expected"], case["name"]


def test_golden_density_default_matches_process_window_card():
    """Die im Golden dokumentierte Default-Dichte ist exakt der Kartenwert —
    eine Quelle (Prozessfenster-Karte), kein zweites Literal."""
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert doc["density_default_kg_m3"] == ProcessWindow.load().density_kg_m3


# --- Gewicht: Volumen x Dichte ---------------------------------------------------


def test_weight_is_volume_times_density():
    # 2000 x 1000 x 200 mm = 0.4 m^3; bei 1900 kg/m^3 -> 760 kg.
    check = check_module(2000.0, 1000.0, 200.0, density_kg_m3=1900.0)
    assert check.weight_kg == pytest.approx(0.4 * 1900.0)
    assert check.density_kg_m3 == 1900.0


def test_weight_uses_density_default_from_process_window_card():
    """Der Dichte-Default kommt aus der Prozessfenster-Karte (wie default_shells)."""
    window = ProcessWindow.load()
    assert window.density_kg_m3 == PROVISIONAL_DEFAULTS["density_kg_m3"]
    check = check_module(1000.0, 1000.0, 100.0, density_kg_m3=window.density_kg_m3)
    assert check.weight_kg == pytest.approx(0.1 * window.density_kg_m3)


def test_non_positive_density_raises():
    with pytest.raises(ValueError, match="Dichte"):
        check_module(1000.0, 1000.0, 200.0, density_kg_m3=0.0)


# --- Befund, kein Gate ------------------------------------------------------------


def test_no_limits_yields_no_findings():
    check = check_module(9999.0, 9999.0, 500.0, density_kg_m3=1900.0)
    assert check.findings == ()
    assert check.any_exceeded is False


def test_exactly_on_limit_counts_as_kept():
    limits = ModuleLimits(max_length_mm=2000.0, max_height_mm=1000.0)
    check = check_module(2000.0, 1000.0, 200.0, density_kg_m3=1900.0, limits=limits)
    assert [f.exceeded for f in check.findings] == [False, False]
    assert check.any_exceeded is False


def test_exceeded_limit_is_reported_not_raised():
    """Verletzte Grenze = Befund (exceeded=True), kein Fehler/Gate."""
    limits = ModuleLimits(max_height_mm=1000.0)
    check = check_module(2000.0, 2600.0, 200.0, density_kg_m3=1900.0, limits=limits)
    assert len(check.findings) == 1
    finding = check.findings[0]
    assert finding.limit == "max_height"
    assert finding.exceeded is True
    assert check.any_exceeded is True


def test_findings_order_is_length_then_height():
    limits = ModuleLimits(max_length_mm=1.0, max_height_mm=1.0)
    check = check_module(2.0, 2.0, 2.0, density_kg_m3=1900.0, limits=limits)
    assert [f.limit for f in check.findings] == ["max_length", "max_height"]


def test_check_module_is_deterministic():
    limits = ModuleLimits(max_length_mm=1500.0)
    a = check_module(1600.0, 900.0, 240.0, density_kg_m3=1900.0, limits=limits)
    b = check_module(1600.0, 900.0, 240.0, density_kg_m3=1900.0, limits=limits)
    assert a == b


# --- ModuleLimits: sparse Rundreise ------------------------------------------------


def test_module_limits_from_dict_handles_missing_block_and_fields():
    assert ModuleLimits.from_dict(None) == ModuleLimits()
    assert ModuleLimits.from_dict({}) == ModuleLimits()
    only_height = ModuleLimits.from_dict({"max_height_mm": 800.0})
    assert only_height.max_length_mm is None
    assert only_height.max_height_mm == 800.0


def test_module_limits_to_dict_is_sparse():
    assert ModuleLimits().to_dict() == {}
    assert ModuleLimits(max_length_mm=2000.0).to_dict() == {"max_length_mm": 2000.0}
    both = ModuleLimits(max_length_mm=2000.0, max_height_mm=1000.0)
    assert both.to_dict() == {"max_length_mm": 2000.0, "max_height_mm": 1000.0}


# --- check_plan: Befund je Teil ----------------------------------------------------


def _two_part_plan() -> DecompositionPlan:
    wall = WallSurface(length_mm=3000.0, height_mm=1000.0, thickness_mm=200.0)
    placement = PlacementOption("workstation-druckort", 0.0, 700.0, 0.0)
    sections = (
        SectionPlan(Section("abschnitt-1", 1, -1500.0, 0.0, 0.0, 1000.0), placement),
        SectionPlan(Section("abschnitt-2", 2, 0.0, 1500.0, 0.0, 1000.0), placement),
    )
    return DecompositionPlan(
        "modul", wall, (Cut("vertical", 0.0),), sections, n_length=2, n_height=1
    )


def test_check_plan_returns_finding_per_part():
    plan = _two_part_plan()
    checks = check_plan(
        plan, density_kg_m3=1900.0, limits=ModuleLimits(max_length_mm=1200.0)
    )
    assert sorted(checks) == ["abschnitt-1", "abschnitt-2"]
    for check in checks.values():
        # 1500 x 1000 x 200 mm = 0.3 m^3 -> 570 kg; Laenge 1500 > 1200 verletzt.
        assert check.weight_kg == pytest.approx(0.3 * 1900.0)
        assert check.any_exceeded is True
