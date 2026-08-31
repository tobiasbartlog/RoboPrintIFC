"""Prior-Tabelle: Generator + Lademodul ``placement.prior`` (ADR-026 Punkt 3, PRD #225, Issue #230).

Dichteste Abdeckung des rein rechnenden Prior-Moduls (PRD-Testentscheidung): Tool-
Aehnlichkeit, konservative Interpolation, ``angenommen-unmachbar`` und **alle**
Fehlfaelle ⇒ neutraler Prior. Plus Generator-Golden-Roundtrip (byte-stabil aus einem
Mini-Fixture) und Deckungsgleichheit des eingecheckten Artefakts mit dem Realgitter.
"""

from __future__ import annotations

import json

from fgc.domain.tool import ToolDef
from fgc.paths import PRIORS_DIR, REPO_ROOT
from fgc.placement.prior import (
    FEAS_FEASIBLE,
    FEAS_INFEASIBLE,
    NEUTRAL_PRIOR,
    PriorTable,
    load_prior_tables,
    placement_prior,
)
from fgc.placement.prior_build import (
    build_prior_artifact,
    dump_artifact,
    tool_reference,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

#: Mini-Gitter-Auszug (2×2 W×T, eine Zelle absichtlich fehlend = abgebrochen).
MINI_META = {
    "widths": [500.0, 800.0],
    "thicks": [100.0, 250.0],
    "standoffs": [200.0, 350.0, 500.0],
    "base_heights": [0.0, 300.0],
    "box_height_mm": 900.0,
    "configs": ["aaa", "baa"],
    "strict_reach": 0.99,
    "safety_mm": 50.0,
    "project": "mini",
    "generated_by": "test-fixture",
    "hmax_by_wt": {
        "500_100": [900.0, 0.0, "aaa", 500.0],
        "500_250": [830.0, 300.0, "baa", 500.0],
        "800_100": [900.0, 300.0, "aaa", 500.0],
        # 800_250 fehlt absichtlich -> angenommen-unmachbar
    },
}

_FIXED_PROV = {"source": "test", "created": "2026-07-22T00:00:00+00:00", "git_commit": "abc1234"}

#: Referenz-Tool (mit Huellmass, damit die Aehnlichkeitsregel greifen kann).
_REF_TOOL = ToolDef(
    name="ref",
    tcp_frame={"pos_mm": [100.0, 0.0, 70.0], "quat": [1.0, 0.0, 0.0, 0.0]},
    weight_kg=2.0,
    envelope_mm={"radius_mm": 60.0, "length_mm": 200.0},
)


def _art(meta=MINI_META, robot="doosan_m1013"):
    return build_prior_artifact(meta, robot, tool_reference(_REF_TOOL), provenance=_FIXED_PROV)


def _mini_table() -> PriorTable:
    return PriorTable.from_artifact(_art())


def _tool(name, *, pos=(100.0, 0.0, 70.0), radius=60.0, length=200.0, envelope=True) -> ToolDef:
    return ToolDef(
        name=name,
        tcp_frame={"pos_mm": list(pos), "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=2.0,
        envelope_mm={"radius_mm": radius, "length_mm": length} if envelope else None,
    )


# --------------------------------------------------------------------------- #
# Generator: Golden-Roundtrip + eingechecktes Artefakt
# --------------------------------------------------------------------------- #


def test_generator_byte_stable_and_order_independent():
    """Byte-stabil (``sort_keys``) und **unabhaengig** von der Eingabe-Zeilenreihenfolge."""
    a = dump_artifact(_art())
    assert a == dump_artifact(_art())  # gleiche Eingaben -> bit-gleich
    # hmax-Reihenfolge permutiert -> weiterhin bit-gleich
    shuffled = dict(MINI_META)
    shuffled["hmax_by_wt"] = dict(reversed(list(MINI_META["hmax_by_wt"].items())))
    assert a == dump_artifact(_art(shuffled))


def test_generator_marks_aborted_cell_assumed_infeasible():
    """Volles W×T-Produkt; die fehlende Zelle traegt ``angenommen-unmachbar`` (nie erfunden)."""
    art = _art()
    assert set(art["cells"]) == {"500_100", "500_250", "800_100", "800_250"}
    aborted = art["cells"]["800_250"]
    assert aborted["status"] == "angenommen-unmachbar"
    assert aborted["h_max_mm"] is None
    assert aborted["best"] is None
    measured = art["cells"]["500_100"]
    assert measured["status"] == "measured"
    assert measured["best"] == {"standoff_mm": 500.0, "base_height_mm": 0.0, "ik_config": "aaa"}


def test_checked_in_artifact_matches_real_grid():
    """Das eingecheckte Artefakt ist der Lauf auf den echten ``data_grid/``-Daten."""
    checked_in = PRIORS_DIR / "placement_prior.doosan_m1013.30gut.json"
    assert checked_in.exists(), "eingechecktes Prior-Artefakt fehlt"
    stored = json.loads(checked_in.read_text(encoding="utf-8"))
    meta_path = (
        REPO_ROOT / "experiments" / "collision_standoff_sweep" / "data_grid" / "meta_wt.json"
    )
    real_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    rebuilt = build_prior_artifact(
        real_meta, "doosan_m1013", tool_reference(ToolDef.load("30gut")),
        provenance=stored["provenance"],
    )
    # Provenienz (Zeitstempel) darf differieren; Kern muss deckungsgleich sein.
    for field in ("kind", "schema_version", "robot", "tool", "grid", "cells"):
        assert rebuilt[field] == stored[field]
    # 3 abgebrochene Zellen ehrlich markiert.
    assumed = {k for k, c in stored["cells"].items() if c["status"] == "angenommen-unmachbar"}
    assert assumed == {"800_550", "1100_400", "1100_550"}


def test_checked_in_artifact_loads_with_valid_provenance():
    """Das eingecheckte Artefakt traegt gueltige ADR-004-Provenienz und laedt sauber."""
    tables = load_prior_tables("doosan_m1013")
    assert len(tables) >= 1
    prov = tables[0].provenance
    assert prov.get("git_commit") and prov.get("grid_meta_path")


# --------------------------------------------------------------------------- #
# Konservative Interpolation
# --------------------------------------------------------------------------- #


def test_exact_support_point_returns_measured_guidance():
    prior = _mini_table().query(500.0, 100.0)
    assert not prior.is_neutral
    assert prior.reason == "measured"
    assert prior.standoff_focus_mm == 500.0
    assert prior.base_height_focus_mm == 0.0
    assert prior.config_shortlist == ("aaa", "auto")
    assert prior.h_max_mm == 900.0


def test_between_support_points_picks_worse_neighbor():
    """(650×180) liegt zwischen Stuetzstellen -> naechste **schlechtere** Zelle (800×250)."""
    prior = _mini_table().query(650.0, 180.0)
    # 800_250 ist die abgebrochene Zelle -> Unmachbarkeits-Erwartung, neutral-breit.
    assert prior.cell_key == "800_250"
    assert prior.feasibility_expectation == FEAS_INFEASIBLE
    assert prior.standoff_focus_mm is None  # breit, keine Verdichtung


def test_between_measured_points_picks_worse_measured_cell():
    """(550×90) -> naechste schlechtere **gemessene** Zelle (800×100), nicht 500×100."""
    prior = _mini_table().query(550.0, 90.0)
    assert prior.cell_key == "800_100"
    assert prior.base_height_focus_mm == 300.0
    assert prior.config_shortlist == ("aaa", "auto")


def test_assumed_infeasible_cell_is_neutral_broad_with_infeasible_expectation():
    prior = _mini_table().query(800.0, 250.0)
    assert not prior.is_neutral  # traegt eine Erwartung
    assert prior.reason == "angenommen-unmachbar"
    assert prior.feasibility_expectation == FEAS_INFEASIBLE
    assert prior.config_shortlist == ()
    assert prior.standoff_focus_mm is None


def test_feasibility_expectation_uses_module_height():
    table = _mini_table()
    assert table.query(500.0, 100.0, height_mm=800.0).feasibility_expectation == FEAS_FEASIBLE
    assert table.query(500.0, 100.0, height_mm=950.0).feasibility_expectation == FEAS_INFEASIBLE


# --------------------------------------------------------------------------- #
# Tool-Aehnlichkeit (ADR-026 Punkt 4)
# --------------------------------------------------------------------------- #


def test_same_name_tool_always_matches():
    assert _mini_table().tool_matches(_tool("ref", envelope=False), safety_distance_mm=1.0)


def test_similar_tool_within_zone_matches():
    close = _tool("other", pos=(120.0, 0.0, 70.0), radius=70.0, length=210.0)
    assert _mini_table().tool_matches(close, safety_distance_mm=50.0)


def test_tool_outside_zone_does_not_match():
    far_tcp = _tool("other", pos=(300.0, 0.0, 70.0))
    assert not _mini_table().tool_matches(far_tcp, safety_distance_mm=50.0)
    far_env = _tool("other", radius=200.0)
    assert not _mini_table().tool_matches(far_env, safety_distance_mm=50.0)


def test_tolerance_follows_configured_zone_narrow_zone_is_stricter():
    """ADR-026 Punkt 4 / #232: die Toleranz folgt der **konfigurierten** Zone —
    dasselbe leicht abweichende Tool ist in einer weiten Zone uebertragbar, in
    einer engen Zone nicht (enge Zone ⇒ strengere Uebertragbarkeit)."""
    close = _tool("other", pos=(120.0, 0.0, 70.0), radius=70.0, length=210.0)
    table = _mini_table()
    assert table.tool_matches(close, safety_distance_mm=50.0)  # weite Zone: uebertragbar
    assert not table.tool_matches(close, safety_distance_mm=5.0)  # enge Zone: nein


def test_tool_without_envelope_does_not_transfer():
    """Fehlendes Huellmass am fremden Tool -> „unbekannt" -> kein Uebertrag."""
    no_env = _tool("other", envelope=False)
    assert not _mini_table().tool_matches(no_env, safety_distance_mm=1000.0)


# --------------------------------------------------------------------------- #
# Fehlfaelle -> neutraler Prior
# --------------------------------------------------------------------------- #


def test_missing_artifact_is_neutral(tmp_path):
    got = placement_prior("doosan_m1013", _REF_TOOL, 500.0, 100.0, 50.0, priors_dir=tmp_path)
    assert got.is_neutral


def test_foreign_robot_is_neutral(tmp_path):
    """Ein Artefakt fuer doosan_m1013 liegt vor, aber die Suche fragt einen fremden
    Roboter -> Load findet nichts -> neutraler Prior."""
    dest = tmp_path / "placement_prior.doosan_m1013.ref.json"
    dest.write_text(dump_artifact(_art()), encoding="utf-8")
    got = placement_prior("kuka_kr16", _REF_TOOL, 500.0, 100.0, 50.0, priors_dir=tmp_path)
    assert got.is_neutral
    # Gegenprobe: derselbe Aufruf mit dem passenden Roboter greift.
    hit = placement_prior("doosan_m1013", _REF_TOOL, 500.0, 100.0, 50.0, priors_dir=tmp_path)
    assert not hit.is_neutral


def test_unknown_tool_is_neutral():
    stranger = _tool("stranger", pos=(400.0, 0.0, 400.0), radius=300.0, envelope=True)
    got = placement_prior("doosan_m1013", stranger, 500.0, 100.0, 20.0, tables=[_mini_table()])
    assert got.is_neutral
    assert got.reason == "unbekanntes-tool"


def test_module_larger_than_grid_is_neutral():
    """Modulmasse groesser als das Gitter -> fehlende Zelle -> neutral (kein Extrapolieren)."""
    got = _mini_table().query(2000.0, 900.0)
    assert got.is_neutral
    assert got.reason == "ausserhalb-gitter"


def test_invalid_provenance_artifact_is_skipped(tmp_path):
    """Provenienz-ungueltiges Artefakt wird uebersprungen -> als abwesend -> neutral."""
    bad = tmp_path / "placement_prior.doosan_m1013.bad.json"
    bad.write_text(json.dumps({"kind": "something-else"}), encoding="utf-8")
    assert load_prior_tables("doosan_m1013", priors_dir=tmp_path) == []
    got = placement_prior("doosan_m1013", _REF_TOOL, 500.0, 100.0, 50.0, priors_dir=tmp_path)
    assert got is NEUTRAL_PRIOR or got.is_neutral


def test_wrong_schema_version_raises_on_from_artifact():
    art = build_prior_artifact(MINI_META, "r", tool_reference(_REF_TOOL), provenance=_FIXED_PROV)
    art["schema_version"] = "999"
    try:
        PriorTable.from_artifact(art)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("erwartete ValueError bei fremder Schema-Version")
