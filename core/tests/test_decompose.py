"""Zerlegungsvorschlag in Abschnitte mit Platzierungen (Issue #24).

Geprüft wird das externe Verhalten der Modul-Schnittstelle mit synthetischen
Wand-Fixtures (überhoch/überlang/beides): ``propose`` liefert für eine überhohe
Wand horizontale, für eine überlange vertikale Schnitte; alle Abschnitte grün.
``apply`` erzeugt je Abschnitt ein wasserdichtes Teil-Mesh (Volumensumme ≈
Wandvolumen). ``evaluate`` färbt einen absichtlich unerreichbaren Abschnitt rot,
ohne den Plan zu blockieren. Aktion + API-Endpoint folgen dem Prior-Art-Muster
aus test_placement (Stub-Wände + Verzeichnis-Seams).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient

from fgc import domain
from fgc.decompose import (
    Cut,
    DecompositionPlan,
    ModuleLimits,
    Section,
    SectionPlan,
    apply,
    apply_overrides,
    check_plan,
    decompose_artifact,
    evaluate,
    from_cuts,
    propose,
    total_volume,
)
from fgc.domain.robot import RobotDef
from fgc.domain.tool import ToolDef
from fgc.domain.workstation import WorkstationDef
from fgc.pipeline import runfolder
from fgc.pipeline.actions import (
    create_project_from_ifc,
    propose_decomposition,
    reassess_walls_for_robot,
    set_context_check_for_job,
    set_module_limits_for_job,
    set_placement_override_for_job,
    set_print_job,
    set_stand_mode_for_job,
)
from fgc.pipeline.api import app
from fgc.placement import PlacementOption, WallSurface
from fgc.project import store as project_store

ROBOT = "doosan_m1013"

PROVENANCE = {
    "source": "test",
    "created": "2026-07-05T12:00:00Z",
    "git_commit": "0000000",
}

#: Überhohe Wand: braucht Höhenstufen (horizontale Schnitte).
TALL_WALL = WallSurface(length_mm=800.0, height_mm=2600.0, thickness_mm=200.0)
#: Überlange Wand: braucht Längenteilung (vertikale Schnitte).
LONG_WALL = WallSurface(length_mm=3600.0, height_mm=700.0, thickness_mm=200.0)
#: Überhoch UND überlang: beide Schnittrichtungen.
BOTH_WALL = WallSurface(length_mm=3600.0, height_mm=2600.0, thickness_mm=200.0)


@pytest.fixture(scope="module")
def robot() -> RobotDef:
    return RobotDef.load(ROBOT)


@pytest.fixture(scope="module")
def tool() -> ToolDef:
    """Null-TCP-Werkzeug (Düse am Flansch) — hält die Fixtures synthetisch."""
    return ToolDef(
        name="testduese",
        tcp_frame={"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        weight_kg=0.0,
    )


# --- propose: Schnittrichtung + alle Abschnitte grün ---------------------------


def test_tall_wall_gets_horizontal_cuts_all_green(robot, tool):
    # Erhoeht-Modus: seit #132 sieht die Bewertung jede Reihe an ihrer echten
    # Hoehenlage — nur mit erlaubtem Podest kann eine ueberhohe Wand voll gruen sein.
    plan = propose(TALL_WALL, robot, tool, stand_mode="elevated")
    orientations = {c.orientation for c in plan.cuts}
    assert "horizontal" in orientations
    assert "vertical" not in orientations
    assert plan.n_height > 1
    assert plan.n_length == 1
    statuses = evaluate(plan, robot, tool)
    assert all(s.reachable for s in statuses), [s.reachable_fraction for s in statuses]


def test_long_wall_gets_vertical_cuts_all_green(robot, tool):
    plan = propose(LONG_WALL, robot, tool)
    orientations = {c.orientation for c in plan.cuts}
    assert "vertical" in orientations
    assert "horizontal" not in orientations
    assert plan.n_length > 1
    assert plan.n_height == 1
    statuses = evaluate(plan, robot, tool)
    assert all(s.reachable for s in statuses), [s.reachable_fraction for s in statuses]


def test_both_wall_gets_both_directions_all_green(robot, tool):
    # Erhoeht-Modus (wie oben): obere Reihen brauchen seit #132 ein echtes Podest.
    plan = propose(BOTH_WALL, robot, tool, stand_mode="elevated")
    orientations = {c.orientation for c in plan.cuts}
    assert orientations == {"horizontal", "vertical"}
    statuses = evaluate(plan, robot, tool)
    # Ehrliche Abstand-Semantik (Issue #160): der Fallback-Abstand 700 misst jetzt
    # ab der Wandflaeche — die Basis steht real 100 mm (halbe Dicke) weiter weg
    # als unter der alten Mittelebenen-Lesart. Damit verlieren die Rand-Zellen
    # dieser 3.6 m x 2.6 m-Wand ein paar Eck-Stichproben (0.968 statt 1.0); das
    # frühere „alles gruen" war ein Artefakt der optimistischen Semantik.
    fractions = [s.reachable_fraction for s in statuses]
    assert all(f >= 0.95 for f in fractions), fractions
    assert any(s.reachable for s in statuses), fractions


def test_propose_print_order_is_bottom_up(robot, tool):
    plan = propose(TALL_WALL, robot, tool)
    orders = [sp.section.order for sp in plan.sections]
    assert orders == sorted(orders) == list(range(1, len(plan.sections) + 1))
    # Reihenfolge unten → oben: die z-Untergrenze steigt (schwach) monoton.
    z0s = [sp.section.z0_mm for sp in plan.sections]
    assert z0s == sorted(z0s)


def test_propose_is_deterministic(robot, tool):
    a = propose(TALL_WALL, robot, tool)
    b = propose(TALL_WALL, robot, tool)
    assert a.n_length == b.n_length and a.n_height == b.n_height
    assert a.cuts == b.cuts
    assert [sp.section for sp in a.sections] == [sp.section for sp in b.sections]


def test_propose_module_without_workstation_raises_friendly_hint(robot, tool):
    """Art 'modul' ohne Workstation: klarer Hinweispfad (die Workstation ist der
    Druckort, ADR-022) — kein stiller Fallback."""
    with pytest.raises(ValueError, match="Workstation"):
        propose(TALL_WALL, robot, tool, kind="modul")


def test_propose_unknown_kind_raises(robot, tool):
    with pytest.raises(ValueError, match="unbekannt"):
        propose(TALL_WALL, robot, tool, kind="segment")


# --- Aufstell-Toggle: floor vs. elevated (Issue #81) --------------------------


def _pedestal_ws() -> WorkstationDef:
    """Stationaere Workstation mit realem Podeststapel (inkl. Bodenhoehe 0)."""
    return WorkstationDef(
        name="teststation",
        mobility="stationary",
        height_adjustable=False,
        base_heights_mm=(0.0, 500.0, 1000.0, 1500.0),
    )


def test_propose_floor_yields_more_height_bands_than_elevated(robot, tool):
    """Kern-Verhalten (#81): bei gleicher Wand + Workstation leitet der Toggle
    ``floor`` (Basis fix am Boden, begrenzte vertikale Reichweite) **mehr**
    Hoehenbaender ab als ``elevated`` (Basis darf auf ein Podest)."""
    ws = _pedestal_ws()
    floor = propose(TALL_WALL, robot, tool, workstation=ws, stand_mode="floor")
    elevated = propose(TALL_WALL, robot, tool, workstation=ws, stand_mode="elevated")

    assert floor.n_height > elevated.n_height
    # Nur die Hoehenteilung reagiert auf den Toggle — die Laengenteilung bleibt gleich.
    assert floor.n_length == elevated.n_length
    # Mehr Baender = mehr Abschnitte insgesamt (ueberhohe Wand, keine Laengenteilung).
    assert len(floor.sections) > len(elevated.sections)


def test_propose_toggle_is_deterministic(robot, tool):
    """Determinismus (#81): gleiche Eingaben (inkl. Toggle) → gleicher Plan."""
    ws = _pedestal_ws()
    a = propose(TALL_WALL, robot, tool, workstation=ws, stand_mode="floor")
    b = propose(TALL_WALL, robot, tool, workstation=ws, stand_mode="floor")
    assert a.n_height == b.n_height and a.n_length == b.n_length
    assert a.cuts == b.cuts


# --- Absolute Aufstellhoehen (Issue #132, Design-Log 2026-07-09) ---------------


def test_propose_floor_marks_upper_rows_honestly_red(robot, tool):
    """Boden-Modus: obere Reihen liegen jenseits der Reichweite (M1013, 1300 mm)
    vom Boden — die Ampel sagt die Wahrheit (nicht gruen), geschnitten wird
    trotzdem (Befund, kein Gate); die Basis bleibt absolut auf 0 (kein
    Phantom-Podest am Abschnittsfuss mehr)."""
    plan = propose(TALL_WALL, robot, tool, stand_mode="floor")
    assert plan.n_height > 1  # unerreichbar schneidet trotzdem
    # Boden-Modus = Hoehensatz [0] absolut, fuer ALLE Reihen.
    assert all(sp.placement.stand_height_mm == 0.0 for sp in plan.sections)
    statuses = sorted(evaluate(plan, robot, tool), key=lambda s: s.order)
    assert statuses[0].reachable is True  # unterste Reihe vom Boden erreichbar
    assert statuses[-1].reachable is False
    assert statuses[-1].reachable_fraction < 1.0


def test_from_cuts_row_at_1646_from_floor_not_green(robot, tool):
    """Spezifikations-Anker (#132): eine Reihe auf z0 ≈ 1646 mm ist mit
    Reichweite 1300 mm vom Boden nicht voll erreichbar — Ampel nicht gruen."""
    wall = WallSurface(length_mm=800.0, height_mm=2469.6, thickness_mm=200.0)
    cuts = [Cut("horizontal", 823.2), Cut("horizontal", 1646.4)]
    plan = from_cuts(wall, robot, tool, cuts, stand_mode="floor")
    top_plan = max(plan.sections, key=lambda sp: sp.section.order)
    assert top_plan.section.z0_mm == 1646.4
    statuses = evaluate(plan, robot, tool)
    top = next(s for s in statuses if s.section_id == top_plan.section.section_id)
    assert top.reachable is False
    assert top.reachable_fraction < 1.0


def test_propose_elevated_with_mobile_hub_uses_only_real_heights(robot, tool):
    """Erhoeht-Modus mit hoehenverstellbarer Workstation (Hub 0–600 mm): alle
    Aufstellhoehen kommen aus dem realen Geraetebereich [0, 600] — absolut ueber
    dem Boden, kein Phantomwert jenseits des Hubs (#132)."""
    ws = WorkstationDef(
        name="mobile_hub",
        mobility="mobile",
        height_adjustable=True,
        height_range_mm=(0.0, 600.0),
    )
    plan = propose(TALL_WALL, robot, tool, workstation=ws, stand_mode="elevated")
    for sp in plan.sections:
        assert 0.0 <= sp.placement.stand_height_mm <= 600.0, sp.placement


def test_bottom_row_placement_bitidentical_to_old_miniwall_search(robot, tool):
    """Regressionsanker (#132): fuer die unterste Reihe (z0 = 0) ist absolut ≡
    abschnitts-lokal — Platzierungssuche und Bewertung sind bit-identisch zur
    alten Mini-Wand-Konvention (WallSurface ohne z-Offset)."""
    from dataclasses import replace

    from fgc.placement import suggest

    plan = from_cuts(
        TALL_WALL, robot, tool, [Cut("horizontal", 1300.0)], stand_mode="elevated"
    )
    bottom = next(sp for sp in plan.sections if sp.section.z0_mm == 0.0)

    # Alte Konvention: der Abschnitt als Mini-Wand ab z = 0 (kein z-Offset).
    # Der Zerlegungsvorschlag ruft ``suggest`` reachability-only **und ohne die
    # IK-Konfig-Suchachse** (Grob-Check + Konfig-Achse bleiben dem Placement-
    # Optimalvorschlag vorbehalten, #228/#233/ADR-026 Out of Scope) — der Referenz-
    # aufruf muss denselben Modus fahren (``config_axis=False``), sonst driftet er ab.
    legacy_surface = WallSurface(
        bottom.section.length_mm, bottom.section.height_mm, TALL_WALL.thickness_mm
    )
    legacy_opt, legacy_score = suggest(
        legacy_surface, robot, tool, stand_mode="elevated", n_best=1,
        collision_free=lambda _o: True, config_axis=False,
    )[0]
    assert replace(bottom.placement, option_id=legacy_opt.option_id) == legacy_opt

    statuses = evaluate(plan, robot, tool)
    status = next(s for s in statuses if s.section_id == bottom.section.section_id)
    assert status.reachable_fraction == legacy_score.reachable_fraction
    assert status.kinematic_margin == legacy_score.kinematic_margin
    assert status.mean_margin == legacy_score.mean_margin


def test_from_cuts_still_works_with_workstation_and_toggle(robot, tool):
    """`from_cuts` (manuelle Schnitte) bleibt funktionsfaehig, auch mit Workstation +
    Toggle — die manuellen Schnittebenen bestimmen die Abschnitte, der Toggle nur
    die automatische Platzierungssuche je Abschnitt (#81)."""
    ws = _pedestal_ws()
    cuts = [Cut("horizontal", 1300.0)]
    plan = from_cuts(
        TALL_WALL, robot, tool, cuts, workstation=ws, stand_mode="elevated"
    )
    # Schnitte bleiben Plan-Eingang: 1 Höhenschnitt → 2 Abschnitte (unveraendert).
    assert plan.n_height == 2
    assert plan.n_length == 1
    assert len(plan.sections) == 2
    # Jeder Abschnitt bekommt eine automatisch gesuchte Platzierung.
    assert all(sp.placement is not None for sp in plan.sections)


# --- Zerlegungsart Modul (Issue #90, ADR-022) --------------------------------


def _module_ws() -> WorkstationDef:
    """Stationaere Workstation als Modul-Druckort (ADR-022) — mit Frames, damit
    die feste Platzierung aus robot_base_frame/work_surface_frame abgeleitet wird."""
    return WorkstationDef(
        name="druckort",
        mobility="stationary",
        height_adjustable=False,
        base_heights_mm=(0.0,),
        safety_min_distance_mm=50.0,
        robot_base_frame={"pos_mm": [0.0, 0.0, 300.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        work_surface_frame={"pos_mm": [800.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
    )


def test_propose_module_kind_yields_fixed_workstation_placement(robot, tool):
    """Art 'modul': eine feste Platzierung an der Workstation fuer ALLE Teile —
    keine Suche je Zelle (ADR-022); der bisherige ValueError entfaellt."""
    ws = _module_ws()
    plan = propose(TALL_WALL, robot, tool, workstation=ws, kind="modul")
    assert plan.kind == "modul"
    placements = [sp.placement for sp in plan.sections]
    # Alle Teile teilen dieselbe Relativpose (nur die option_id unterscheidet sich).
    assert len({(p.lateral_mm, p.standoff_mm, p.stand_height_mm) for p in placements}) == 1
    p0 = placements[0]
    assert p0.lateral_mm == 0.0  # Modul mittig vor der Basis
    # Freier Abstand vor der Modulflaeche (Issue #160): horizontale Frame-Distanz
    # 800 minus halbe Moduldicke (200/2) — die Flaeche liegt der Basis naeher als
    # der Arbeitsflaechen-Ursprung (Modulmitte).
    assert p0.standoff_mm == 700.0
    assert p0.stand_height_mm == 300.0  # Basis relativ zur Arbeitsflaeche


def test_propose_module_is_deterministic(robot, tool):
    ws = _module_ws()
    a = propose(TALL_WALL, robot, tool, workstation=ws, kind="modul")
    b = propose(TALL_WALL, robot, tool, workstation=ws, kind="modul")
    assert a.n_length == b.n_length and a.n_height == b.n_height
    assert a.cuts == b.cuts
    assert [sp.section for sp in a.sections] == [sp.section for sp in b.sections]
    assert [sp.placement for sp in a.sections] == [sp.placement for sp in b.sections]


def test_propose_module_print_order_is_bottom_up(robot, tool):
    ws = _module_ws()
    plan = propose(TALL_WALL, robot, tool, workstation=ws, kind="modul")
    orders = [sp.section.order for sp in plan.sections]
    assert orders == list(range(1, len(plan.sections) + 1))
    z0s = [sp.section.z0_mm for sp in plan.sections]
    assert z0s == sorted(z0s)  # Montagereihenfolge unten -> oben


def test_propose_module_max_limits_refine_the_grid(robot, tool):
    """Optionale Obergrenzen wirken auf die Verfeinerung: eine max. Hoehe kleiner
    als die Wand erzwingt zusaetzliche Hoehenteilungen (Zelle > Grenze => teilen)."""
    ws = _module_ws()
    wall = WallSurface(length_mm=1000.0, height_mm=2400.0, thickness_mm=200.0)
    unlimited = propose(wall, robot, tool, workstation=ws, kind="modul")
    limited = propose(
        wall, robot, tool, workstation=ws, kind="modul",
        limits=ModuleLimits(max_height_mm=600.0),
    )
    # 2400 / 600 = 4 Hoehenbaender mindestens; jede Zelle bleibt <= Grenze.
    assert limited.n_height >= 4
    assert limited.n_height > unlimited.n_height
    for sp in limited.sections:
        assert sp.section.height_mm <= 600.0 + 1e-6


def test_propose_module_empty_limits_only_workspace(robot, tool):
    """Leere Obergrenzen = nur der Arbeitsraum begrenzt (kein zusaetzliches Teilen)."""
    ws = _module_ws()
    wall = WallSurface(length_mm=800.0, height_mm=800.0, thickness_mm=200.0)
    a = propose(wall, robot, tool, workstation=ws, kind="modul")
    b = propose(
        wall, robot, tool, workstation=ws, kind="modul", limits=ModuleLimits()
    )
    assert (a.n_length, a.n_height) == (b.n_length, b.n_height)


def test_from_cuts_module_kind_uses_fixed_placement(robot, tool):
    """from_cuts mit 'modul': manuelle Schnitte bleiben Plan-Eingang, jedes Teil
    bekommt die feste Workstation-Platzierung (keine Suche)."""
    ws = _module_ws()
    cuts = [Cut("horizontal", 1300.0)]
    plan = from_cuts(TALL_WALL, robot, tool, cuts, workstation=ws, kind="modul")
    assert plan.kind == "modul"
    assert plan.n_height == 2
    placements = [sp.placement for sp in plan.sections]
    assert len({(p.lateral_mm, p.standoff_mm, p.stand_height_mm) for p in placements}) == 1
    # Frame-Distanz 800 minus halbe Moduldicke (Issue #160, wie oben).
    assert placements[0].standoff_mm == 700.0


def test_check_plan_over_module_plan_reports_weight_and_limits(robot, tool):
    """check_plan liefert je Teil Gewicht + Grenzen-Befund (Befund, kein Gate)."""
    ws = _module_ws()
    plan = propose(TALL_WALL, robot, tool, workstation=ws, kind="modul")
    checks = check_plan(
        plan, density_kg_m3=1900.0, limits=ModuleLimits(max_height_mm=600.0)
    )
    assert set(checks) == {sp.section.section_id for sp in plan.sections}
    assert all(c.weight_kg > 0 for c in checks.values())


# --- from_cuts / apply_overrides: Schnittplan-Editing (Issue #25) -------------


def test_from_cuts_builds_sections_from_manual_cut_positions(robot, tool):
    cuts = [Cut("horizontal", 1300.0)]
    plan = from_cuts(TALL_WALL, robot, tool, cuts)
    assert plan.n_height == 2
    assert plan.n_length == 1
    assert len(plan.sections) == 2
    z0s = sorted(sp.section.z0_mm for sp in plan.sections)
    assert z0s == [0.0, 1300.0]


def test_from_cuts_two_directions_grid(robot, tool):
    cuts = [Cut("horizontal", 1300.0), Cut("vertical", -600.0), Cut("vertical", 600.0)]
    plan = from_cuts(BOTH_WALL, robot, tool, cuts)
    assert plan.n_height == 2
    assert plan.n_length == 3
    assert len(plan.sections) == 6
    # Reihenfolge unten -> oben, dann links -> rechts (wie propose()).
    orders = [sp.section.order for sp in plan.sections]
    assert orders == list(range(1, 7))


def test_from_cuts_ignores_out_of_bounds_and_duplicate_cuts(robot, tool):
    cuts = [
        Cut("horizontal", 1300.0),
        Cut("horizontal", 1300.0001),  # Duplikat (Rundung auf 3 Nachkommastellen)
        Cut("horizontal", -50.0),  # ausserhalb der Wandflaeche -> ignoriert
        Cut("horizontal", 99999.0),  # ausserhalb -> ignoriert
    ]
    plan = from_cuts(TALL_WALL, robot, tool, cuts)
    assert plan.n_height == 2
    assert len(plan.cuts) == 1


def test_from_cuts_is_deterministic(robot, tool):
    cuts = [Cut("horizontal", 1300.0), Cut("vertical", 0.0)]
    a = from_cuts(BOTH_WALL, robot, tool, cuts)
    b = from_cuts(BOTH_WALL, robot, tool, cuts)
    assert [sp.section for sp in a.sections] == [sp.section for sp in b.sections]
    assert [sp.placement for sp in a.sections] == [sp.placement for sp in b.sections]


def test_from_cuts_module_without_workstation_raises_friendly_hint(robot, tool):
    with pytest.raises(ValueError, match="Workstation"):
        from_cuts(TALL_WALL, robot, tool, [], kind="modul")


def test_from_cuts_joint_offset_staggers_vertical_cuts_between_height_rows(robot, tool):
    """Fugen-Versatz: jede zweite Hoehenlage bekommt versetzte vertikale Schnitte."""
    cuts = [Cut("horizontal", 1300.0), Cut("vertical", -600.0), Cut("vertical", 600.0)]
    plan = from_cuts(BOTH_WALL, robot, tool, cuts, joint_offset_mm=150.0)
    rows: dict[float, list[float]] = {}
    for sp in plan.sections:
        rows.setdefault(sp.section.z0_mm, []).append(sp.section.x0_mm)
    bottom_row = sorted(rows[0.0])
    top_row = sorted(rows[1300.0])
    assert bottom_row != top_row  # Versatz wirkt
    assert [round(x - 150.0, 3) for x in top_row[1:]] == bottom_row[1:]
    # Die "effektiven" Basis-Schnitte im Plan bleiben die unversetzten Eingaben.
    vertical_positions = sorted(c.position_mm for c in plan.cuts if c.orientation == "vertical")
    assert vertical_positions == [-600.0, 600.0]


def test_from_cuts_zero_joint_offset_keeps_uniform_grid(robot, tool):
    cuts = [Cut("horizontal", 1300.0), Cut("vertical", 0.0)]
    plan = from_cuts(BOTH_WALL, robot, tool, cuts, joint_offset_mm=0.0)
    rows: dict[float, list[float]] = {}
    for sp in plan.sections:
        rows.setdefault(sp.section.z0_mm, []).append(sp.section.x0_mm)
    assert sorted(rows[0.0]) == sorted(rows[1300.0])


def test_apply_overrides_replaces_matching_section_placement():
    wall = WallSurface(1000.0, 800.0, 200.0)
    plan = _grid_plan(wall, n_v=2, n_h=1)
    override = PlacementOption(
        "vorschlag-1", lateral_mm=42.0, standoff_mm=900.0, stand_height_mm=300.0
    )
    updated = apply_overrides(plan, {"abschnitt-1": override})
    by_id = {sp.section.section_id: sp.placement for sp in updated.sections}
    assert by_id["abschnitt-1"] == override
    assert by_id["abschnitt-2"] == plan.sections[1].placement  # unveraendert


def test_apply_overrides_ignores_stale_section_ids():
    wall = WallSurface(1000.0, 800.0, 200.0)
    plan = _grid_plan(wall, n_v=1, n_h=1)
    override = PlacementOption(
        "vorschlag-1", lateral_mm=0.0, standoff_mm=700.0, stand_height_mm=0.0
    )
    updated = apply_overrides(plan, {"abschnitt-existiert-nicht": override})
    assert updated == plan


def test_apply_overrides_empty_dict_is_noop():
    wall = WallSurface(1000.0, 800.0, 200.0)
    plan = _grid_plan(wall, n_v=1, n_h=1)
    assert apply_overrides(plan, {}) is plan


# --- apply: wasserdichte Teil-Meshes, Volumensumme ≈ Wandvolumen ---------------


def _wall_box(length: float, height: float, thickness: float) -> trimesh.Trimesh:
    """Quader im Wand-System: x zentriert, z ab 0 (wie WallSurface)."""
    box = trimesh.creation.box(extents=[length, thickness, height])
    box.apply_translation([0.0, 0.0, height / 2.0])  # z: -H/2..H/2 → 0..H
    return box


def _grid_plan(wall: WallSurface, n_v: int, n_h: int) -> DecompositionPlan:
    """Baut einen Schnittplan mit gleichmäßigem n_v×n_h-Raster (Dummy-Platzierung)."""
    cuts = []
    for i in range(1, n_h):
        cuts.append(Cut("horizontal", wall.height_mm * i / n_h))
    for i in range(1, n_v):
        cuts.append(Cut("vertical", -wall.length_mm / 2.0 + wall.length_mm * i / n_v))
    sections = []
    order = 0
    for hi in range(n_h):
        z0 = wall.height_mm * hi / n_h
        z1 = wall.height_mm * (hi + 1) / n_h
        for vi in range(n_v):
            x0 = -wall.length_mm / 2.0 + wall.length_mm * vi / n_v
            x1 = -wall.length_mm / 2.0 + wall.length_mm * (vi + 1) / n_v
            order += 1
            sections.append(
                SectionPlan(
                    Section(f"abschnitt-{order}", order, x0, x1, z0, z1),
                    PlacementOption(f"platz-{order}", 0.0, 700.0, 0.0),
                )
            )
    return DecompositionPlan("abschnitt", wall, tuple(cuts), tuple(sections), n_v, n_h)


def test_apply_produces_watertight_parts_conserving_volume():
    wall = WallSurface(1000.0, 800.0, 200.0)
    mesh = _wall_box(1000.0, 800.0, 200.0)
    plan = _grid_plan(wall, n_v=2, n_h=2)

    parts = apply(mesh, plan)
    assert len(parts) == 4
    for part in parts:
        assert len(part.vertices) > 0
        assert part.is_watertight
    assert total_volume(parts) == pytest.approx(abs(mesh.volume), rel=1e-3)


def test_apply_single_section_returns_full_mesh():
    wall = WallSurface(1000.0, 800.0, 200.0)
    mesh = _wall_box(1000.0, 800.0, 200.0)
    plan = _grid_plan(wall, n_v=1, n_h=1)
    parts = apply(mesh, plan)
    assert len(parts) == 1
    assert parts[0].is_watertight
    assert abs(parts[0].volume) == pytest.approx(abs(mesh.volume), rel=1e-9)


# --- evaluate: roter Abschnitt ohne Blockade -----------------------------------


def test_evaluate_marks_unreachable_section_red_without_blocking(robot, tool):
    """Ein absichtlich unerreichbarer Abschnitt (Basis weit weg) wird rot — kein Abbruch."""
    wall = WallSurface(600.0, 400.0, 200.0)
    reachable = SectionPlan(
        Section("abschnitt-1", 1, -300.0, 300.0, 0.0, 400.0),
        PlacementOption("platz-1", 0.0, 700.0, 0.0),
    )
    unreachable = SectionPlan(
        Section("abschnitt-2", 2, -300.0, 300.0, 400.0, 800.0),
        PlacementOption("platz-2", 0.0, 10_000.0, 0.0),  # Basis 10 m weg
    )
    plan = DecompositionPlan("abschnitt", wall, (), (reachable, unreachable), 1, 2)

    statuses = evaluate(plan, robot, tool)  # wirft nicht
    by_id = {s.section_id: s for s in statuses}
    assert by_id["abschnitt-1"].reachable is True
    assert by_id["abschnitt-2"].reachable is False
    assert by_id["abschnitt-2"].reachable_fraction == 0.0
    assert all(w["kind"] == "unreachable" for w in by_id["abschnitt-2"].warnings)


# --- decompose_artifact: Schema-Vertrag ----------------------------------------


def test_decompose_artifact_validates_against_schema(robot, tool):
    plan = propose(TALL_WALL, robot, tool)
    statuses = evaluate(plan, robot, tool)
    artifact = decompose_artifact(
        ROBOT, tool.name, plan, statuses, PROVENANCE,
        wall_global_id="WALLAAAAAAAAAAAAAAAAAA",
    )
    domain.validate(artifact, "decompose")
    assert artifact["decomposition_kind"] == "abschnitt"
    assert len(artifact["sections"]) == len(plan.sections)
    assert all("status" in s and "placement" in s for s in artifact["sections"])


def test_decompose_artifact_writes_printability_including_ungeprueft(robot, tool):
    """Druckbarkeit je Teil (Issue #164/#170) ist additiv + schema-valide; auch
    „ungeprüft" (``unknown``) wird geschrieben — MIT ``reason`` (no_geometry/error),
    damit ein Lauf mit fehlgeschlagener Prüfung nicht wie „alles geprüft" aussieht
    (B12/B35). Nur OHNE das ``printability``-Argument (Altlauf) fehlt das Feld."""
    from fgc.decompose import PartPrintability
    from fgc.decompose.printability import (
        REASON_ERROR,
        REASON_NO_GEOMETRY,
        VERDICT_COLLIDES,
        VERDICT_UNKNOWN,
    )

    plan = propose(TALL_WALL, robot, tool)
    statuses = evaluate(plan, robot, tool)
    sids = [sp.section.section_id for sp in plan.sections]
    printability = {
        sids[0]: PartPrintability(
            sids[0], VERDICT_COLLIDES, presumed=False, representative_id=sids[0],
            causer_link=2, causer_against="modul", penetration_mm=289.2, min_distance_mm=-289.2,
        ),
    }
    # Die uebrigen Teile ungeprueft — die Haelfte unzustaendig, die Haelfte Fehler.
    for i, sid in enumerate(sids[1:]):
        reason = REASON_NO_GEOMETRY if i % 2 == 0 else REASON_ERROR
        printability[sid] = PartPrintability(sid, VERDICT_UNKNOWN, presumed=False, reason=reason)

    artifact = decompose_artifact(
        ROBOT, tool.name, plan, statuses, PROVENANCE,
        wall_global_id="WALLAAAAAAAAAAAAAAAAAA", printability=printability,
    )
    domain.validate(artifact, "decompose")
    by_id = {s["section_id"]: s for s in artifact["sections"]}
    assert by_id[sids[0]]["printability"]["verdict"] == "collides"
    assert by_id[sids[0]]["printability"]["causer_link"] == 2
    # Ehrliches Urteil (Kern des Issues): kein „collides" hat keine reason, die
    # geprueft-freie/kollidierte Zeile bleibt byte-gleich (reason erscheint gar nicht).
    assert "reason" not in by_id[sids[0]]["printability"]
    # „ungeprüft"-Teile tragen JETZT das Feld — mit der Fehlerklasse (B34/B35).
    for i, sid in enumerate(sids[1:]):
        pr = by_id[sid]["printability"]
        assert pr["verdict"] == "unknown"
        assert pr["reason"] == (REASON_NO_GEOMETRY if i % 2 == 0 else REASON_ERROR)

    # Ohne printability (Altlauf): kein Feld irgendwo (Golden, byte-gleich).
    plain = decompose_artifact(ROBOT, tool.name, plan, statuses, PROVENANCE)
    assert all("printability" not in s for s in plain["sections"])


def test_decompose_artifact_writes_collision_location_schema_valid(robot, tool):
    """Kollisions-ORT (Issue #181, Schema-Erweiterung): ``worst_original_index`` /
    ``worst_layer`` / ``causer_position_mm`` / ``red_intervals`` je Teil validieren
    additiv unter ``decompose.schema.json`` — ein Altlauf ohne die Felder bleibt
    weiterhin gültig (die vorige Assertion oben belegt das bereits, hier zusätzlich
    fürs collides-Teil mit real gesetztem Ort)."""
    from fgc.decompose import PartPrintability
    from fgc.decompose.printability import VERDICT_COLLIDES

    plan = propose(TALL_WALL, robot, tool)
    statuses = evaluate(plan, robot, tool)
    sids = [sp.section.section_id for sp in plan.sections]
    printability = {
        sids[0]: PartPrintability(
            sids[0], VERDICT_COLLIDES, presumed=False, representative_id=sids[0],
            causer_link=2, causer_against="modul", penetration_mm=289.2, min_distance_mm=-289.2,
            worst_original_index=137, worst_layer=14, causer_position_mm=(12.5, -30.0, 640.0),
            red_intervals=(
                {"link": 2, "against": "modul", "start_index": 100, "end_index": 150,
                 "worst_index": 137, "min_distance_mm": -289.2},
            ),
        ),
    }
    artifact = decompose_artifact(
        ROBOT, tool.name, plan, statuses, PROVENANCE,
        wall_global_id="WALLAAAAAAAAAAAAAAAAAA", printability=printability,
    )
    domain.validate(artifact, "decompose")
    by_id = {s["section_id"]: s for s in artifact["sections"]}
    pr = by_id[sids[0]]["printability"]
    assert pr["worst_original_index"] == 137
    assert pr["worst_layer"] == 14
    assert pr["causer_position_mm"] == [12.5, -30.0, 640.0]
    assert pr["red_intervals"] == [
        {"link": 2, "against": "modul", "start_index": 100, "end_index": 150,
         "worst_index": 137, "min_distance_mm": -289.2},
    ]


# --- Pruef-Tuer: Fehlerklasse + Log + ungeprueft-Zustand (Issue #170) ----------


def _fake_comp():
    """Minimales `comp`-Double fuer `section_clearance_check` (nur die von der Naht
    genutzte Methode; die Pruef-Tuer selbst wird gemockt).

    Seit Issue #192 baut `section_clearance_check` die Eingaben ueber
    `comp.finding_request(...)` (das gruppierte `FindingRequest`), darum traegt das
    Double genau diese Methode — kein 18-Attribut-Sack mehr."""
    from types import SimpleNamespace

    from fgc.collision.finding import (
        FindingRequest,
        PartMesh,
        RobotToolRefs,
        SceneInputs,
        ToolpathExcerpt,
        TrajectoryExcerpt,
    )

    def _request(*, config=None, context=None):
        return FindingRequest(
            trajectory=TrajectoryExcerpt(base_frame={}, samples=[], target_times_s=[]),
            toolpath=ToolpathExcerpt(targets=[], layer_height_mm=10.0, n_layers=1),
            part=PartMesh(vertices_mm=[], faces=[]),
            scene=SceneInputs(
                mode="abschnitt", section_z0_mm=0.0, earlier_parts=[], context=context
            ),
            refs=RobotToolRefs(tool=None),
            config=config,
        )

    return SimpleNamespace(robot_name=ROBOT, finding_request=_request)


def test_section_clearance_check_logs_and_returns_error_on_exception(monkeypatch, caplog):
    """Jede in der Pruef-Tuer verschluckte Ausnahme erzeugt einen Log-Eintrag und
    fuehrt zu :data:`REASON_ERROR` — NIE zu „frei" (Akzeptanzkriterium #170, B5/B12)."""
    import logging

    from fgc.collision import finding
    from fgc.decompose.printability import REASON_ERROR
    from fgc.pipeline.sectionsim import section_clearance_check

    def _boom(*_a, **_k):
        raise RuntimeError("Pruef-Tuer kaputt (Regression)")

    monkeypatch.setattr(finding, "check_part_clearance", _boom)
    with caplog.at_level(logging.WARNING):
        outcome = section_clearance_check(_fake_comp(), config=None, travel_stride=5)
    assert outcome == REASON_ERROR
    assert any("fehlgeschlagen" in r.message.lower() for r in caplog.records)


def test_section_clearance_check_returns_no_geometry_when_pruef_tuer_none(monkeypatch):
    """Liefert die Pruef-Tuer ``None`` (kein Kollisions-Geometrie-Artefakt), ist der
    Zustand ``no_geometry`` — unzustaendig, unterscheidbar vom Absturz (B5)."""
    from fgc.collision import finding
    from fgc.decompose.printability import REASON_NO_GEOMETRY
    from fgc.pipeline.sectionsim import section_clearance_check

    monkeypatch.setattr(finding, "check_part_clearance", lambda *_a, **_k: None)
    outcome = section_clearance_check(_fake_comp(), config=None, travel_stride=5)
    assert outcome == REASON_NO_GEOMETRY


def test_clearance_verdict_logs_and_returns_error_on_sim_failure(
    monkeypatch, caplog
):
    """Scheitert schon der Aufbau/die Simulation der Pruef-Tuer, wird das mit
    Log-Eintrag zu :data:`REASON_ERROR` (die zweite schluckende Stelle, #170/B5)."""
    import logging

    from fgc.decompose.printability import REASON_ERROR
    from fgc.pipeline import sectionsim

    def _boom(*_a, **_k):
        raise RuntimeError("Simulation der Pruef-Tuer kaputt")

    monkeypatch.setattr(sectionsim, "section_sim_context", _boom)
    with caplog.at_level(logging.WARNING):
        outcome = sectionsim.clearance_verdict(
            {"print_jobs": []}, {}, None, "abschnitt-1"
        )
    assert outcome == REASON_ERROR
    assert any("abschnitt-1" in r.message or "abschnitt-1" in str(r.args) for r in caplog.records)


# --- Ampel-Konjunktion: Erreichbarkeit UND Druckbarkeit (Issue #180, B33) ------


def test_decompose_printability_partial_reachability_never_green():
    """Politik-Tür ``assess_plan`` (Issue #180/#190): ein Teil, das die Prüf-Tür **frei**
    sieht, aber nur **teilweise erreichbar** ist (vor #164 rot), wird **nicht** grün — die
    Druckbarkeit überstimmt den härteren roten Erreichbarkeits-Befund nicht mehr (B33).
    Der erreichbare Nachbar wird bei freiem Urteil grün. Orakel injiziert (schnell)."""
    from types import SimpleNamespace

    from fgc.decompose.evaluate import SectionStatus
    from fgc.decompose.printability import VERDICT_PRINTABLE
    from fgc.decompose.pruefung import PruefCache, assess_plan

    # Zwei Teile in getrennten Höhenreihen ⇒ jedes ist sein eigener Repräsentant.
    wall = WallSurface(length_mm=800.0, height_mm=1600.0, thickness_mm=200.0)
    low = SectionPlan(
        Section("abschnitt-1", 1, -400.0, 400.0, 0.0, 800.0),
        PlacementOption("platz-1", 0.0, 700.0, 0.0),
    )
    high = SectionPlan(
        Section("abschnitt-2", 2, -400.0, 400.0, 800.0, 1600.0),
        PlacementOption("platz-2", 0.0, 700.0, 0.0),
    )
    plan = DecompositionPlan("abschnitt", wall, (), (low, high), 1, 2)

    def _status(sid: str, order: int, *, reachable: bool, frac: float) -> SectionStatus:
        return SectionStatus(
            section_id=sid, order=order, reachable=reachable, reachable_fraction=frac,
            n_samples=100, n_reachable=int(frac * 100), kinematic_margin=0.2, mean_margin=0.2,
        )

    statuses = [
        _status("abschnitt-1", 1, reachable=True, frac=1.0),
        _status("abschnitt-2", 2, reachable=False, frac=0.5),  # vor #164 rot
    ]

    # Prüf-Tür-Orakel sieht JEDES Teil frei — allein die Erreichbarkeit unterscheidet.
    def _free_oracle(_section_id: str):
        return SimpleNamespace(
            collides=False, causer_link=None, causer_against=None,
            penetration_mm=None, min_distance_mm=None,
        )

    out, _stats, _samples = assess_plan(
        plan, statuses, None, frozenset(), _free_oracle,
        signature=("test",), cache=PruefCache(),
    )

    # Erreichbares Teil: geprüft-frei ⇒ grün.
    assert out["abschnitt-1"].verdict == VERDICT_PRINTABLE
    assert out["abschnitt-1"].printable is True
    # Teilweise unerreichbares Teil: Prüf-Tür-Kanal bleibt ehrlich („printable"),
    # aber die Konjunktion macht es NICHT grün — beide Kanäle ablesbar.
    assert out["abschnitt-2"].verdict == VERDICT_PRINTABLE  # Prüf-Tür-Kanal ehrlich
    assert out["abschnitt-2"].printable is False            # aber nicht grün (#180)
    assert out["abschnitt-2"].reachable is False
    assert out["abschnitt-2"].reachable_fraction == pytest.approx(0.5)
    # Der Erreichbarkeits-Kanal steht auch im Artefakt (nur wenn nicht erreichbar).
    assert out["abschnitt-2"].to_dict()["reachable"] is False
    assert "reachable" not in out["abschnitt-1"].to_dict()  # voll erreichbar ⇒ byte-gleich


# --- Repraesentanten-Wahl kollisionsehrlich (Issue #174, B10/B13/B26/B36) ------


def _seam_grid_plan(kind: str = "abschnitt") -> DecompositionPlan:
    """2x3-Raster (2 Reihen, 3 Zellen je Reihe, Zellen 800x800) — Druckreihenfolge
    unten->oben, links->rechts (abschnitt-1..6)."""
    wall = WallSurface(length_mm=2400.0, height_mm=1600.0, thickness_mm=200.0)
    sections: list[SectionPlan] = []
    order = 0
    for hi in range(2):
        z0, z1 = 800.0 * hi, 800.0 * (hi + 1)
        for vi in range(3):
            x0 = -1200.0 + 800.0 * vi
            order += 1
            sections.append(
                SectionPlan(
                    Section(f"abschnitt-{order}", order, x0, x0 + 800.0, z0, z1),
                    PlacementOption(f"platz-{order}", 0.0, 700.0, 0.0),
                )
            )
    return DecompositionPlan(kind, wall, (), tuple(sections), 3, 2)


def _seam_status(sid: str, order: int, *, margin, frac=1.0):
    from fgc.decompose.evaluate import SectionStatus

    return SectionStatus(
        section_id=sid, order=order, reachable=frac >= 0.999, reachable_fraction=frac,
        n_samples=100, n_reachable=int(frac * 100), kinematic_margin=margin, mean_margin=margin,
    )


def _record_oracle(*, collides_for=frozenset()):
    """Injizierbares Pruef-Tuer-Orakel (Issue #190), das protokolliert, WELCHE Zellen
    als Repraesentant geprueft wurden (der Beweis der Auswahlregel)."""
    from types import SimpleNamespace

    checked: list[str] = []

    def _check(section_id: str):
        checked.append(section_id)
        hit = section_id in collides_for
        return SimpleNamespace(
            collides=hit, causer_link=2 if hit else None, causer_against="modul",
            penetration_mm=289.2 if hit else None, min_distance_mm=None,
        )

    return checked, _check


def _assess(plan, statuses, *, check, override_ids=frozenset(), freigang=None):
    """``assess_plan`` mit frischem Cache/Dummy-Signatur (die Politik-Tests hier
    exerzieren die Auswahl-/Vererbungsregeln, nicht die Cache-Politik)."""
    from fgc.decompose.pruefung import PruefCache, assess_plan

    printability, _stats, _samples = assess_plan(
        plan, statuses, freigang, override_ids, check,
        signature=("test",), cache=PruefCache(),
    )
    return printability


def test_decompose_printability_representative_is_last_printed_max_obstacle_load():
    """Regel 1 (B10): je Reihe wird die Zelle mit MAXIMALER Hindernislast geprueft —
    bei „abschnitt" die zuletzt gedruckte (abschnitt-3 / abschnitt-6); die uebrigen
    erben ``presumed`` von IHR (nicht von der hindernisaermsten ersten Zelle)."""
    plan = _seam_grid_plan()
    statuses = [_seam_status(f"abschnitt-{i}", i, margin=0.4) for i in range(1, 7)]
    checked, check = _record_oracle(collides_for={"abschnitt-3", "abschnitt-6"})

    out = _assess(plan, statuses, check=check)

    # Nur die zuletzt gedruckte Zelle je Reihe wird geprueft.
    assert sorted(checked) == ["abschnitt-3", "abschnitt-6"]
    assert out["abschnitt-3"].presumed is False and out["abschnitt-6"].presumed is False
    for sid in ("abschnitt-1", "abschnitt-2"):
        assert out[sid].presumed is True and out[sid].representative_id == "abschnitt-3"
    for sid in ("abschnitt-4", "abschnitt-5"):
        assert out[sid].presumed is True and out[sid].representative_id == "abschnitt-6"
    # Alle rot (der Repraesentant kollidiert), keiner gruen.
    assert all(p.verdict == "collides" for p in out.values())


def test_decompose_printability_module_tiebreak_picks_last_printed():
    """Regel 1 bei Art „modul": Hindernislast 0 fuer alle (kein frueheres Teil am
    Druckort, ADR-022) ⇒ der Stich faellt auf die ZULETZT gedruckte Zelle (abschnitt-3),
    nicht die hindernisaermste erste (der Kern von B10 auf Reihenebene)."""
    plan = _seam_grid_plan(kind="modul")
    # Nur die untere Reihe zum Fokus (3 Zellen); obere ebenso.
    statuses = [_seam_status(f"abschnitt-{i}", i, margin=0.06) for i in range(1, 7)]
    checked, check = _record_oracle()

    _assess(plan, statuses, check=check)
    assert sorted(checked) == ["abschnitt-3", "abschnitt-6"]  # zuletzt gedruckt je Reihe


def test_decompose_printability_unreachable_cell_never_representative():
    """Regel 2 (B13): die (sonst gewaehlte) letzte Zelle ist unerreichbar (Marge None)
    ⇒ sie wird NIE Repraesentant; die naechste erreichbare Zelle (abschnitt-2) vertritt
    die Reihe. Kein Urteil von einer eingefrorenen Trajektorie."""
    plan = _seam_grid_plan()
    statuses = [
        _seam_status("abschnitt-1", 1, margin=0.4),
        _seam_status("abschnitt-2", 2, margin=0.4),
        _seam_status("abschnitt-3", 3, margin=None, frac=0.0),  # unerreichbar
        _seam_status("abschnitt-4", 4, margin=0.4),
        _seam_status("abschnitt-5", 5, margin=0.4),
        _seam_status("abschnitt-6", 6, margin=0.4),
    ]
    checked, check = _record_oracle()

    out = _assess(plan, statuses, check=check)
    # Untere Reihe von abschnitt-2 vertreten (nicht der unerreichbaren abschnitt-3).
    assert "abschnitt-2" in checked and "abschnitt-3" not in checked
    assert out["abschnitt-1"].representative_id == "abschnitt-2"
    # Die unerreichbare Zelle erbt zwar das Reihen-Urteil, ist aber via Konjunktion (#180)
    # nie gruen — der Erreichbarkeits-Kanal bleibt ehrlich.
    assert out["abschnitt-3"].reachable is False and out["abschnitt-3"].printable is False


def test_decompose_printability_unreachable_row_is_unknown_not_free():
    """Regel 2, harter Fall (B13): ist KEINE Zelle der Reihe erreichbar, erbt die Reihe
    kein „frei", sondern ``unknown`` mit Grund ``unreachable`` — und die teure Pruef-Tuer
    wird fuer diese Reihe gar nicht erst aufgerufen."""
    from fgc.decompose.printability import REASON_UNREACHABLE

    plan = _seam_grid_plan()
    statuses = [
        # Untere Reihe komplett unerreichbar.
        _seam_status("abschnitt-1", 1, margin=None, frac=0.0),
        _seam_status("abschnitt-2", 2, margin=None, frac=0.0),
        _seam_status("abschnitt-3", 3, margin=None, frac=0.0),
        # Obere Reihe erreichbar.
        _seam_status("abschnitt-4", 4, margin=0.4),
        _seam_status("abschnitt-5", 5, margin=0.4),
        _seam_status("abschnitt-6", 6, margin=0.4),
    ]
    checked, check = _record_oracle()

    out = _assess(plan, statuses, check=check)
    # Untere Reihe: keine Pruef-Tuer, ehrlich ungeprueft (nie „frei").
    for sid in ("abschnitt-1", "abschnitt-2", "abschnitt-3"):
        assert sid not in checked
        assert out[sid].verdict == "unknown" and out[sid].reason == REASON_UNREACHABLE
        assert out[sid].printable is False
    # Obere Reihe unberuehrt: normal ueber ihren Repraesentanten geprueft.
    assert "abschnitt-6" in checked


def test_decompose_printability_override_cell_excluded_from_inheritance():
    """Regel 4 (B36): eine Zelle mit eigenem Platzierungs-Override (``override_ids``,
    im Produktivpfad aus dem Job gelesen) erbt kein Reihen-Urteil und wird nie
    Repraesentant fuer die Nachbarn — sie wird selbst geprueft; die uebrigen erben von
    einer ANDEREN, gleich-platzierten Zelle."""
    plan = _seam_grid_plan()
    statuses = [_seam_status(f"abschnitt-{i}", i, margin=0.4) for i in range(1, 7)]
    checked, check = _record_oracle()

    # abschnitt-3 (sonst Repraesentant der unteren Reihe) traegt einen freien Override.
    out = _assess(plan, statuses, check=check, override_ids=frozenset({"abschnitt-3"}))
    # Override-Zelle selbst geprueft (nicht erbend); Reihen-Repraesentant ist abschnitt-2.
    assert "abschnitt-3" in checked and "abschnitt-2" in checked
    assert out["abschnitt-3"].presumed is False  # selbst geprueft
    assert out["abschnitt-1"].representative_id == "abschnitt-2"
    assert out["abschnitt-2"].representative_id == "abschnitt-2"
    # Die Override-Zelle vertritt NIEMANDEN sonst.
    assert out["abschnitt-1"].representative_id != "abschnitt-3"
    assert out["abschnitt-2"].representative_id != "abschnitt-3"


# --- Aktion propose_decomposition ----------------------------------------------


@pytest.fixture
def stub_walls(install_walls, make_wall):
    # Überhohe Quaderwand (2600 mm) — erzwingt eine Zerlegung mit Höhenstufen.
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", height=2600.0)])


def _project_with_job(tmp_path, *, with_robot: bool = True):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  projects_dir=projects_dir)
    if with_robot:
        reassess_walls_for_robot(slug, ROBOT, "src",
                                 projects_dir=projects_dir, runs_dir=runs_dir)
    return slug, projects_dir, runs_dir


def test_propose_decomposition_writes_run_and_updates_job(tmp_path, stub_walls):
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    result = propose_decomposition(
        slug, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )

    # Zerlegungslauf: decompose.json vorhanden und schema-valide (ADR-004).
    decompose_path = result.run_dir / "decompose.json"
    assert decompose_path.exists()
    artifact = json.loads(decompose_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")
    assert artifact["robot"] == ROBOT
    assert artifact["wall_global_id"] == "WALLAAAAAAAAAAAAAAAAAA"
    assert len(artifact["sections"]) >= 2  # überhohe Wand → mehrere Höhenstufen

    # Druckjob: nur Zerlegungsart + Schnittebenen + Lauf-Verweis, keine Ampeln (ADR-016).
    job = result.artifact["print_jobs"][0]
    assert job["decomposition_kind"] == "abschnitt"
    assert len(job["cuts"]) >= 1
    assert any(c["orientation"] == "horizontal" for c in job["cuts"])
    assert Path(job["decompose_run"]) == result.run_dir.resolve()
    assert str(result.run_dir.resolve()) in job["runs"]
    assert "status" not in job.get("cuts", [{}])[0]
    domain.validate(result.artifact, "project")

    # API-Antwortdaten: je Abschnitt Geometrie + Platzierung + Ampel.
    assert len(result.sections) == len(artifact["sections"])
    for s in result.sections:
        assert "status" in s and "placement" in s
        assert 0.0 <= s["status"]["reachable_fraction"] <= 1.0


# --- Aufstell-Toggle Setter + Persistenz (Issue #81) --------------------------


def test_set_stand_mode_persists_field_without_staleness(tmp_path, stub_walls):
    """Der Setter schreibt ``stand_mode`` schema-valide in den Druckjob und veraltet
    bewusst KEINE Outputs (kein Revisions-Bump, Seam zu #70 wie beim Workstation-Setter)."""
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)

    from fgc.project import load_project, project_dir_for

    pdir = project_dir_for(slug, projects_dir=projects_dir)
    before_rev = load_project(pdir)["print_jobs"][0].get("revisions")

    result = set_stand_mode_for_job(slug, "elevated", projects_dir=projects_dir)

    assert result.stand_mode == "elevated"
    job = result.artifact["print_jobs"][0]
    assert job["stand_mode"] == "elevated"
    domain.validate(result.artifact, "project")
    # Kein bump_input: der Toggle-Setter aendert keine Revisionsstaende (Seam #70).
    assert job.get("revisions") == before_rev


def test_set_stand_mode_rejects_unknown_mode(tmp_path, stub_walls):
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)
    with pytest.raises(ValueError, match="floor|elevated|unbekannt"):
        set_stand_mode_for_job(slug, "schwebend", projects_dir=projects_dir)


# --- Gebäudekontext-Schalter Setter + additiv/byte-gleich (Issue #131) ---------


def test_set_context_check_additive_and_byte_compatible(tmp_path, stub_walls):
    """Der Schalter ist additiv/sparse: Altprojekt trägt kein Feld (byte-gleich),
    „ein" setzt es schema-valide, „aus" entfernt es wieder auf den Altzustand — ohne
    Revisions-Bump (wie der Aufstell-Toggle, der Schalter wirkt erst bei der Sim)."""
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)

    from fgc.project import load_project, project_dir_for

    pdir = project_dir_for(slug, projects_dir=projects_dir)
    baseline_job = load_project(pdir)["print_jobs"][0]
    assert "check_building_context" not in baseline_job  # Altprojekt: Feld fehlt

    on = set_context_check_for_job(slug, True, projects_dir=projects_dir)
    assert on.check_building_context is True
    on_job = on.artifact["print_jobs"][0]
    assert on_job["check_building_context"] is True
    domain.validate(on.artifact, "project")
    # Kein Revisions-Bump (Seam wie #81): der Schalter veraltet keine Outputs.
    assert on_job.get("revisions") == baseline_job.get("revisions")

    off = set_context_check_for_job(slug, False, projects_dir=projects_dir)
    assert off.check_building_context is False
    off_job = off.artifact["print_jobs"][0]
    # „aus" entfernt das Feld → byte-gleich zum Altprojekt (sparse/additiv).
    assert "check_building_context" not in off_job
    assert off_job == baseline_job


def test_propose_decomposition_consumes_persisted_stand_mode(tmp_path, stub_walls):
    """End-to-end (#81): der persistierte Toggle steuert die Hoehenteilung des
    Zerlegungslaufs — floor leitet >= so viele Abschnitte ab wie elevated."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    # Workstation anlegen + im Job waehlen, damit der Toggle einen Podesthoehen-Satz
    # begrenzt (das Workstation-Feld direkt setzen — die Kompat-Route ist hier egal).
    ws_dir = tmp_path / "workstations"
    ws_dir.mkdir(parents=True, exist_ok=True)
    from fgc.domain.workstation import build_workstation_artifact, write_workstation_artifact
    from fgc.project import load_project, project_dir_for, write_project

    write_workstation_artifact(
        ws_dir / "teststation.json",
        build_workstation_artifact(
            "teststation", "stationary", False,
            base_heights_mm=[0.0, 500.0, 1000.0, 1500.0],
        ),
    )
    pdir = project_dir_for(slug, projects_dir=projects_dir)
    art = load_project(pdir)
    art["print_jobs"][0]["workstation"] = "teststation"
    write_project(pdir, art)

    set_stand_mode_for_job(slug, "floor", projects_dir=projects_dir)
    floor = propose_decomposition(
        slug, "src", projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    set_stand_mode_for_job(slug, "elevated", projects_dir=projects_dir)
    elevated = propose_decomposition(
        slug, "src", projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    assert len(floor.sections) >= len(elevated.sections)


def test_propose_decomposition_without_robot_raises(tmp_path, stub_walls):
    slug, projects_dir, runs_dir = _project_with_job(tmp_path, with_robot=False)
    with pytest.raises(ValueError, match="Roboter"):
        propose_decomposition(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)


def test_propose_decomposition_module_without_workstation_raises(tmp_path, stub_walls):
    """Art 'modul' ohne Workstation am Druckjob: freundlicher Hinweispfad
    (die Workstation ist der Druckort, ADR-022)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    with pytest.raises(ValueError, match="Workstation"):
        propose_decomposition(slug, "src", kind="modul",
                              projects_dir=projects_dir, runs_dir=runs_dir)


def _project_with_module_workstation(tmp_path):
    """Projekt mit Druckjob + gewaehlter Workstation (Modul-Druckort, ADR-022)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    ws_dir = tmp_path / "workstations"
    ws_dir.mkdir(parents=True, exist_ok=True)
    from fgc.domain.workstation import build_workstation_artifact, write_workstation_artifact
    from fgc.project import load_project, project_dir_for, write_project

    write_workstation_artifact(
        ws_dir / "druckort.json",
        build_workstation_artifact(
            "druckort", "stationary", False, base_heights_mm=[0.0],
        ),
    )
    pdir = project_dir_for(slug, projects_dir=projects_dir)
    art = load_project(pdir)
    art["print_jobs"][0]["workstation"] = "druckort"
    write_project(pdir, art)
    return slug, projects_dir, runs_dir, ws_dir


def test_propose_decomposition_module_kind_writes_weight_and_limit_findings(
    tmp_path, stub_walls
):
    """End-to-end (#90): Art 'modul' mit Workstation + Obergrenzen legt je Teil
    additiv Gewicht + Grenzen-Befund in Lauf und Antwort — Befund, kein Gate."""
    slug, projects_dir, runs_dir, ws_dir = _project_with_module_workstation(tmp_path)
    set_module_limits_for_job(slug, max_height_mm=600.0, projects_dir=projects_dir)

    result = propose_decomposition(
        slug, "src", kind="modul",
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    assert result.decomposition_kind == "modul"
    # API-Antwort: je Teil ein module_check mit Gewicht + Grenzen.
    for s in result.sections:
        assert "module_check" in s
        assert s["module_check"]["weight_kg"] > 0
        assert s["module_check"]["density_kg_m3"] > 0

    # Lauf-Artefakt schema-valide inkl. module_limits-Echo + module_check je Teil.
    artifact = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")
    assert artifact["decomposition_kind"] == "modul"
    assert artifact["module_limits"] == {"max_height_mm": 600.0}
    assert all("module_check" in s for s in artifact["sections"])

    job = result.artifact["print_jobs"][0]
    assert job["decomposition_kind"] == "modul"
    assert job["module_limits"] == {"max_height_mm": 600.0}
    domain.validate(result.artifact, "project")

    # Ohne Workstation-Frames (ADR-021 optional) gibt es KEINE Modul-Lage —
    # additiv, der Viewer zeigt statt der Druckort-Ansicht einen Hinweis (#96).
    assert all("module_pose" not in s for s in result.sections)
    assert all("module_pose" not in s for s in artifact["sections"])


def test_propose_decomposition_module_kind_writes_module_pose_with_frames(
    tmp_path, stub_walls
):
    """End-to-end (#96, ADR-022): traegt die Workstation Platzierungs-Frames
    (robot_base_frame + work_surface_frame, ADR-021), legt Art 'modul' je Teil
    additiv die Modul-Lage am Druckort (module_pose) in Lauf und Antwort —
    die Frames bekommen damit ihren ersten Konsumenten (Naht #77/#79)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    ws_dir = tmp_path / "workstations"
    ws_dir.mkdir(parents=True, exist_ok=True)
    from fgc.domain.workstation import build_workstation_artifact, write_workstation_artifact
    from fgc.project import load_project, project_dir_for, write_project

    write_workstation_artifact(
        ws_dir / "druckort.json",
        build_workstation_artifact(
            "druckort", "stationary", False, base_heights_mm=[0.0],
            robot_base_frame={"pos_mm": [0.0, 0.0, 300.0], "quat": [1.0, 0.0, 0.0, 0.0]},
            work_surface_frame={"pos_mm": [800.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        ),
    )
    pdir = project_dir_for(slug, projects_dir=projects_dir)
    art = load_project(pdir)
    art["print_jobs"][0]["workstation"] = "druckort"
    write_project(pdir, art)

    result = propose_decomposition(
        slug, "src", kind="modul",
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    assert result.decomposition_kind == "modul"
    # API-Antwort + Lauf: je Teil eine Modul-Lage (workstation + on_surface,
    # Frames nach ADR-006), Artefakt Schema-valide.
    artifact = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")
    for sections in (result.sections, artifact["sections"]):
        for s in sections:
            pose = s["module_pose"]
            assert set(pose) == {"workstation", "on_surface"}
            assert len(pose["workstation"]["quat"]) == 4
            # Modulfuss auf Arbeitsflaechenhoehe: Basis z=300, Aufstellhoehe 300.
            assert pose["workstation"]["pos_mm"][2] == pytest.approx(0.0, abs=1e-9)

    # Art 'abschnitt' bleibt unveraendert: kein module_pose (additiv, Golden).
    plain = propose_decomposition(
        slug, "src", kind="abschnitt",
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    assert all("module_pose" not in s for s in plain.sections)
    plain_artifact = json.loads(
        (plain.run_dir / "decompose.json").read_text(encoding="utf-8")
    )
    assert all("module_pose" not in s for s in plain_artifact["sections"])


def test_art_switch_keeps_cuts_survives_slicing_verfaellt_placement(tmp_path, stub_walls):
    """Zerlegungsart-Weiche end-to-end (Issue #95, ADR-022 Punkt 5): der Wechsel
    Abschnitt→Modul über die eine Schreibstelle (propose_decomposition) behält ALLE
    Schnitte, laesst die Slicing-Overrides (process_params.sections) UEBERLEBEN und
    laesst die Platzierungs-Overrides VERFALLEN — genau so, wie es die Viewer-Weiche
    (switchArt: Schnitte behalten, Overrides raeumen, Re-Check) an den Core sendet."""
    slug, projects_dir, runs_dir, ws_dir = _project_with_module_workstation(tmp_path)

    from fgc.pipeline.actions import evaluate_placements, set_process_params
    from fgc.project import load_project, project_dir_for

    # Stellplatz erfassen (fuer die Platzierungs-Override-Referenz).
    evaluate_placements(
        slug,
        [{"option_id": "stellplatz-1", "lateral_mm": 0.0, "standoff_mm": 900.0,
          "stand_height_mm": 500.0}],
        "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    # Zerlegung Art „abschnitt" mit manuellen Schnitten + Platzierungs-Override je Teil.
    cuts = [{"orientation": "horizontal", "position_mm": 1300.0}]
    propose_decomposition(
        slug, "src", kind="abschnitt", cuts=cuts,
        section_overrides=[{"section_id": "abschnitt-1", "option_id": "stellplatz-1"}],
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    # Slicing-Override je Teil (process_params.sections, #82) — muss den Wechsel ueberleben.
    set_process_params(
        slug, {}, sections={"abschnitt-1": {"slice": {"layer_height_mm": 8.0}}},
        projects_dir=projects_dir,
    )

    pdir = project_dir_for(slug, projects_dir=projects_dir)
    before = load_project(pdir)["print_jobs"][0]
    assert before["decomposition_kind"] == "abschnitt"
    assert before["section_overrides"]  # Platzierungs-Override liegt vor
    slicing_before = before["process_params"]["sections"]

    # Artwechsel wie die Viewer-Weiche: dieselben Schnitte, GERAEUMTE
    # Platzierungs-Overrides, Art „modul" (der Re-Check mit der neuen Art).
    result = propose_decomposition(
        slug, "src", kind="modul", cuts=cuts, section_overrides=[],
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    job = result.artifact["print_jobs"][0]

    # Regel 1: ALLE Schnitte bleiben erhalten (zerlegungsart-neutral).
    assert job["cuts"] == before["cuts"]
    assert result.decomposition_kind == "modul"
    # Regel 3: Platzierungs-Overrides sind danach weg.
    assert job["section_overrides"] == []
    # Regel 2: Slicing-Overrides (process_params.sections) ueberleben unveraendert.
    assert job["process_params"]["sections"] == slicing_before
    # Und die neue Art rechnet: je Teil ein Modulgrenzen-Befund (Gewicht, kein Gate).
    assert all("module_check" in s for s in result.sections)
    domain.validate(result.artifact, "project")


def test_set_module_limits_persists_sparse_without_staleness(tmp_path, stub_walls):
    """Der Setter schreibt module_limits sparse und veraltet KEINE Outputs
    (kein Revisions-Bump, Muster #81)."""
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)

    from fgc.project import load_project, project_dir_for

    pdir = project_dir_for(slug, projects_dir=projects_dir)
    before_rev = load_project(pdir)["print_jobs"][0].get("revisions")

    result = set_module_limits_for_job(
        slug, max_length_mm=2000.0, projects_dir=projects_dir
    )
    assert result.module_limits == {"max_length_mm": 2000.0}
    job = result.artifact["print_jobs"][0]
    assert job["module_limits"] == {"max_length_mm": 2000.0}
    domain.validate(result.artifact, "project")
    assert job.get("revisions") == before_rev

    # Beide None -> Block entfernt (Altzustand, nur Arbeitsraum begrenzt).
    cleared = set_module_limits_for_job(slug, projects_dir=projects_dir)
    assert cleared.module_limits == {}
    assert "module_limits" not in cleared.artifact["print_jobs"][0]


def test_set_module_limits_rejects_non_positive(tmp_path, stub_walls):
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)
    with pytest.raises(ValueError, match="nicht positiv"):
        set_module_limits_for_job(slug, max_length_mm=-5.0, projects_dir=projects_dir)


# --- propose_decomposition mit manuellem Schnittplan (Schnittplan-Editing #25) --


def test_propose_decomposition_with_manual_cuts_updates_job(tmp_path, stub_walls):
    """Manuell gesetzte Schnitte (statt Auto-Vorschlag) ergeben den geplanten Schnittplan."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    result = propose_decomposition(
        slug, "src",
        cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
        joint_offset_mm=50.0,
        projects_dir=projects_dir, runs_dir=runs_dir,
    )

    assert len(result.sections) == 2
    assert result.cuts == [{"orientation": "horizontal", "position_mm": 1300.0}]
    assert result.joint_offset_mm == 50.0

    job = result.artifact["print_jobs"][0]
    assert job["cuts"] == [{"orientation": "horizontal", "position_mm": 1300.0}]
    assert job["joint_offset_mm"] == 50.0
    assert job["section_overrides"] == []
    domain.validate(result.artifact, "project")

    decompose_path = result.run_dir / "decompose.json"
    artifact = json.loads(decompose_path.read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")
    assert artifact["joint_offset_mm"] == 50.0


def test_propose_decomposition_re_evaluates_after_moving_a_cut(tmp_path, stub_walls):
    """Neubewertung (,Prüfen') nach Änderung liefert frische Ampeln — kein Cache."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    first = propose_decomposition(
        slug, "src", cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    second = propose_decomposition(
        slug, "src", cuts=[{"orientation": "horizontal", "position_mm": 900.0}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert first.run_dir != second.run_dir  # eigener Lauf je Neubewertung (ADR-004)
    z0s_first = sorted(s["z0_mm"] for s in first.sections)
    z0s_second = sorted(s["z0_mm"] for s in second.sections)
    assert z0s_first != z0s_second


def test_propose_decomposition_with_section_override(tmp_path, stub_walls):
    """Platzierungs-Override je Abschnitt: weist eine erfasste Aufstellmöglichkeit zu."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    from fgc.pipeline.actions import evaluate_placements

    evaluate_placements(
        slug,
        [{"option_id": "stellplatz-1", "lateral_mm": 0.0, "standoff_mm": 900.0,
          "stand_height_mm": 500.0}],
        "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )

    result = propose_decomposition(
        slug, "src",
        cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
        section_overrides=[{"section_id": "abschnitt-1", "option_id": "stellplatz-1"}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )

    by_id = {s["section_id"]: s for s in result.sections}
    assert by_id["abschnitt-1"]["placement"]["option_id"] == "stellplatz-1"
    assert by_id["abschnitt-1"]["placement"]["stand_height_mm"] == 500.0
    # Abschnitt 2 bleibt automatisch gesucht (kein Override).
    assert by_id["abschnitt-2"]["placement"]["option_id"] != "stellplatz-1"

    job = result.artifact["print_jobs"][0]
    assert job["section_overrides"] == [
        {"section_id": "abschnitt-1", "option_id": "stellplatz-1"}
    ]


def test_propose_decomposition_unknown_override_option_raises(tmp_path, stub_walls):
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    with pytest.raises(ValueError, match="unbekannte Aufstellm"):
        propose_decomposition(
            slug, "src",
            cuts=[{"orientation": "horizontal", "position_mm": 1300.0}],
            section_overrides=[{"section_id": "abschnitt-1", "option_id": "gibt-es-nicht"}],
            projects_dir=projects_dir, runs_dir=runs_dir,
        )


# --- Freie Platzierungs-Overrides je Teil (Issue #94, PRD #88) -------------------

CUTS_1300 = [{"orientation": "horizontal", "position_mm": 1300.0}]


def test_set_placement_override_persists_and_restores(tmp_path, stub_walls):
    """Der Setter schreibt die freien Werte sparse in section_overrides und der
    Stand ueberlebt das Neuladen; alles-None entfernt den Eintrag (Automatik)."""
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)

    result = set_placement_override_for_job(
        slug, "abschnitt-1", lateral_mm=120.0, stand_height_mm=300.0,
        projects_dir=projects_dir,
    )
    assert result.override == {"lateral_mm": 120.0, "stand_height_mm": 300.0}
    job = result.artifact["print_jobs"][0]
    assert job["section_overrides"] == [
        {"section_id": "abschnitt-1", "lateral_mm": 120.0, "stand_height_mm": 300.0}
    ]
    domain.validate(result.artifact, "project")

    # Wiederherstellung nach Neuladen: der Stand steht im project.json.
    from fgc.project import load_project, project_dir_for

    reloaded = load_project(project_dir_for(slug, projects_dir=projects_dir))
    assert reloaded["print_jobs"][0]["section_overrides"] == job["section_overrides"]

    # Alle None → Eintrag entfernt (zurueck zur automatischen Platzierung).
    cleared = set_placement_override_for_job(slug, "abschnitt-1", projects_dir=projects_dir)
    assert cleared.override == {}
    assert cleared.artifact["print_jobs"][0]["section_overrides"] == []


def test_placement_override_stales_druckplan_output_at_source(tmp_path, stub_walls):
    """Issue #172 (Wurzel-Fix #161, Befunde B16/B32): über die Pipeline-Aktions-Naht
    veraltet ein Platzierungs-Override den Druckplan-Output in den Core-Revisionen —
    ein erneuter Zerlegungslauf hebt es auf. Verankert an der QUELLE (Revisionen),
    nicht pro Leser."""
    from fgc.project import load_project, output_status, project_dir_for

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    # Erster Zerlegungslauf erzeugt den Druckplan-Output → aktuell.
    propose_decomposition(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    assert output_status(job)["druckplan"] == "current"

    # Platzierungs-Override eines Teils → der gespeicherte Zerlegungslauf trägt jetzt
    # eine überholte Platzierung → der ganze Druckplan ist veraltet.
    result = set_placement_override_for_job(
        slug, "abschnitt-1", standoff_mm=850.0, projects_dir=projects_dir
    )
    job = result.artifact["print_jobs"][0]
    assert output_status(job)["druckplan"] == "stale"
    overrides = job["section_overrides"]

    # Neubewertung (erneute Zerlegung mit dem Override) → wieder aktuell.
    propose_decomposition(
        slug, "src", section_overrides=overrides,
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    assert output_status(job)["druckplan"] == "current"


def test_set_placement_override_bumps_only_that_section(tmp_path, stub_walls):
    """#83-Mechanik: der Setter bumpt NUR den Pro-Abschnitts-Zaehler des Teils;
    Job-Eingaben bleiben unangetastet, eine unveraenderte Wiederholung bumpt nicht."""
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)

    from fgc.project import load_project, project_dir_for

    before = load_project(project_dir_for(slug, projects_dir=projects_dir))
    inputs_before = before["print_jobs"][0]["revisions"]["inputs"]

    result = set_placement_override_for_job(
        slug, "abschnitt-1", standoff_mm=800.0, projects_dir=projects_dir
    )
    rev = result.artifact["print_jobs"][0]["revisions"]
    assert rev["section_inputs"] == {"abschnitt-1": 1}
    assert rev["inputs"] == inputs_before  # keine Job-Eingabe gebumpt

    # Unveraendertes Wiederholen: kein weiterer Bump (kein Fake-Veralten).
    again = set_placement_override_for_job(
        slug, "abschnitt-1", standoff_mm=800.0, projects_dir=projects_dir
    )
    assert again.artifact["print_jobs"][0]["revisions"]["section_inputs"] == {"abschnitt-1": 1}


def test_set_placement_override_rejects_non_finite(tmp_path, stub_walls):
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)
    with pytest.raises(ValueError, match="endliche"):
        set_placement_override_for_job(
            slug, "abschnitt-1", lateral_mm=float("nan"), projects_dir=projects_dir
        )


def test_set_placement_override_preserves_option_reference(tmp_path, stub_walls):
    """Referenz-Override (Issue #25) + freie Werte (Issue #94) koexistieren: der
    Setter bewahrt die option_id; alles-None raeumt nur die freien Felder."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    from fgc.pipeline.actions import evaluate_placements

    evaluate_placements(
        slug,
        [{"option_id": "stellplatz-1", "lateral_mm": 0.0, "standoff_mm": 900.0,
          "stand_height_mm": 500.0}],
        "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    propose_decomposition(
        slug, "src", cuts=CUTS_1300,
        section_overrides=[{"section_id": "abschnitt-1", "option_id": "stellplatz-1"}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )

    result = set_placement_override_for_job(
        slug, "abschnitt-1", standoff_mm=777.0, projects_dir=projects_dir
    )
    assert result.override == {"option_id": "stellplatz-1", "standoff_mm": 777.0}

    cleared = set_placement_override_for_job(slug, "abschnitt-1", projects_dir=projects_dir)
    assert cleared.override == {"option_id": "stellplatz-1"}
    domain.validate(cleared.artifact, "project")


def test_set_placement_override_merge_preserves_other_free_fields(tmp_path, stub_walls):
    """Issue #173 (Befund B18) an der Pipeline-Aktions-Naht: das Anwenden einer
    Einzelfeld-Option (``merge=True``) bewahrt zuvor gesetzte freie Felder — der
    Effekt ist symmetrisch (Abstand<->Aufstellhoehe). Ohne ``merge`` (Default,
    manuelles Formular) baut der Setter den Eintrag weiter neu auf (Replace)."""
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)

    # A) Abstand als freier Override (Replace-Default) …
    set_placement_override_for_job(
        slug, "abschnitt-1", standoff_mm=600.0, projects_dir=projects_dir
    )
    # … dann Einzelfeld-Option „Aufstellhoehe" mergen: A bleibt, B kommt hinzu.
    merged = set_placement_override_for_job(
        slug, "abschnitt-1", stand_height_mm=200.0, merge=True, projects_dir=projects_dir
    )
    assert merged.override == {"standoff_mm": 600.0, "stand_height_mm": 200.0}

    # Symmetrie (Aufstellhoehe zuerst gesetzt, dann Abstand gemergt) am Nachbarn.
    set_placement_override_for_job(
        slug, "abschnitt-2", stand_height_mm=250.0, projects_dir=projects_dir
    )
    merged2 = set_placement_override_for_job(
        slug, "abschnitt-2", standoff_mm=650.0, merge=True, projects_dir=projects_dir
    )
    assert merged2.override == {"stand_height_mm": 250.0, "standoff_mm": 650.0}
    domain.validate(merged2.artifact, "project")

    # Kontrast: ohne merge raeumt ein Einzelfeld-Schreiben den Nachbarfeld-Wert ab
    # (Replace — das manuelle Formular loescht ein weggelassenes Feld weiterhin).
    replaced = set_placement_override_for_job(
        slug, "abschnitt-1", stand_height_mm=200.0, projects_dir=projects_dir
    )
    assert replaced.override == {"stand_height_mm": 200.0}


def test_propose_decomposition_effective_placement_has_both_merged_fields(
    tmp_path, stub_walls
):
    """Issue #173 end-to-end: Override A setzen, Einzelfeld-Option B mergen ⇒ die
    vom Zerlegungslauf abgeleitete **effektive Platzierung** traegt A UND B (der
    angewandte Zustand entspricht dem bewerteten Kandidaten)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    base = propose_decomposition(
        slug, "src", cuts=CUTS_1300, projects_dir=projects_dir, runs_dir=runs_dir
    )
    auto = {s["section_id"]: s["placement"] for s in base.sections}

    a_standoff = auto["abschnitt-1"]["standoff_mm"] + 400.0  # Override A (Abstand)
    b_height = auto["abschnitt-1"]["stand_height_mm"] + 150.0  # Option B (Aufstellhoehe)

    set_placement_override_for_job(
        slug, "abschnitt-1", standoff_mm=a_standoff, projects_dir=projects_dir
    )
    set_placement_override_for_job(
        slug, "abschnitt-1", stand_height_mm=b_height, merge=True, projects_dir=projects_dir
    )

    from fgc.project import load_project, project_dir_for

    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    result = propose_decomposition(
        slug, "src", cuts=CUTS_1300, section_overrides=job["section_overrides"],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    placement = {s["section_id"]: s for s in result.sections}["abschnitt-1"]["placement"]
    assert placement["standoff_mm"] == a_standoff  # A ueberlebt das Anwenden von B
    assert placement["stand_height_mm"] == b_height  # B ist angewandt
    assert placement["lateral_mm"] == auto["abschnitt-1"]["lateral_mm"]  # ungesetzt erbt


def test_propose_decomposition_applies_free_override_and_returns_to_auto(
    tmp_path, stub_walls
):
    """End-to-end (#94): freie Werte uebersteuern feldweise die automatische
    Platzierung, bewertet mit der bestehenden evaluate-Maschinerie; Entfernen
    kehrt zur automatischen Platzierung zurueck."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    base = propose_decomposition(
        slug, "src", cuts=CUTS_1300, projects_dir=projects_dir, runs_dir=runs_dir
    )
    auto = {s["section_id"]: s["placement"] for s in base.sections}

    set_placement_override_for_job(
        slug, "abschnitt-1",
        standoff_mm=auto["abschnitt-1"]["standoff_mm"] + 400.0,
        projects_dir=projects_dir,
    )

    from fgc.project import load_project, project_dir_for

    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    result = propose_decomposition(
        slug, "src", cuts=CUTS_1300, section_overrides=job["section_overrides"],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    by_id = {s["section_id"]: s for s in result.sections}
    placement = by_id["abschnitt-1"]["placement"]
    assert placement["option_id"] == "frei-abschnitt-1"
    assert placement["standoff_mm"] == auto["abschnitt-1"]["standoff_mm"] + 400.0
    # Ungesetzte Felder erben die automatisch gesuchte Platzierung (sparse).
    assert placement["lateral_mm"] == auto["abschnitt-1"]["lateral_mm"]
    assert placement["stand_height_mm"] == auto["abschnitt-1"]["stand_height_mm"]
    # Bewertet mit derselben Maschinerie: Ampel/erreichbar %/Marge liegen vor.
    assert 0.0 <= by_id["abschnitt-1"]["status"]["reachable_fraction"] <= 1.0
    # Nachbar bleibt automatisch platziert.
    assert by_id["abschnitt-2"]["placement"] == auto["abschnitt-2"]
    artifact = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")

    # Entfernen des Overrides → zurueck zur automatischen Platzierung.
    set_placement_override_for_job(slug, "abschnitt-1", projects_dir=projects_dir)
    back = propose_decomposition(
        slug, "src", cuts=CUTS_1300, section_overrides=[],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert {s["section_id"]: s["placement"] for s in back.sections} == auto


def test_propose_decomposition_reports_safety_distance_befund(tmp_path, stub_walls):
    """#94: ein Abstand unter dem Workstation-Mindestabstand wird als
    placement_check-Befund gemeldet — kein Gate, nichts wirft."""
    slug, projects_dir, runs_dir, ws_dir = _project_with_module_workstation(tmp_path)

    ws = WorkstationDef.load("druckort", workstations_dir=ws_dir)
    set_placement_override_for_job(
        slug, "abschnitt-1",
        standoff_mm=ws.safety_min_distance_mm - 100.0,
        projects_dir=projects_dir,
    )

    from fgc.project import load_project, project_dir_for

    job = load_project(project_dir_for(slug, projects_dir=projects_dir))["print_jobs"][0]
    result = propose_decomposition(
        slug, "src", cuts=CUTS_1300, section_overrides=job["section_overrides"],
        projects_dir=projects_dir, runs_dir=runs_dir, workstations_dir=ws_dir,
    )
    by_id = {s["section_id"]: s for s in result.sections}
    check = by_id["abschnitt-1"]["placement_check"]
    assert check["below_min_distance"] is True
    assert check["safety_min_distance_mm"] == ws.safety_min_distance_mm
    assert check["standoff_mm"] == ws.safety_min_distance_mm - 100.0
    # Nachbar ohne freien Override: kein placement_check (Artefakt additiv).
    assert "placement_check" not in by_id["abschnitt-2"]
    artifact = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")


# --- API: dünner Wrapper --------------------------------------------------------


@pytest.fixture
def api_dirs(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    projects_dir.mkdir()
    runs_dir.mkdir()
    monkeypatch.setattr(project_store, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(runfolder, "RUNS_DIR", runs_dir)
    return projects_dir, runs_dir


@pytest.fixture
def client():
    return TestClient(app)


def _api_project_with_job(client, tmp_path) -> str:
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post(
        "/projects", json={"name": "Testhaus", "model_path": str(model)}
    ).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA",
                     "assessment_run": overview_run})
    client.put(f"/projects/{slug}/robot", json={"robot": ROBOT})
    return slug


def test_api_post_decomposition_returns_sections(client, api_dirs, stub_walls, tmp_path):
    slug = _api_project_with_job(client, tmp_path)

    resp = client.post(f"/projects/{slug}/decomposition", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["decomposition_kind"] == "abschnitt"
    assert Path(data["run_dir"]).exists()
    assert len(data["sections"]) >= 2
    assert any(c["orientation"] == "horizontal" for c in data["cuts"])
    # Druckjob trägt Plan-Eingaben + Verweis (keine Ampeln).
    job = data["print_jobs"][0]
    assert job["decompose_run"] == data["run_dir"]
    assert job["decomposition_kind"] == "abschnitt"


def test_api_post_decomposition_returns_freigang(client, api_dirs, stub_walls, tmp_path):
    """Freigang-Befund (Issue #163) reist end-to-end durch die API (Actions → Antwort).

    Mit gesetztem Endeffektor `30gut` trägt die Antwort einen `freigang`-Block; die
    Stub-Wand ist 200 mm dick (druckbare Tiefe ~333 mm > 200) ⇒ **nicht** zu dick
    (Fehlerrichtung S6: kein falsches „unmöglich" bei der dünnen Wand).
    """
    slug = _api_project_with_job(client, tmp_path)
    client.put(f"/projects/{slug}/tool", json={"tool": "30gut"})

    resp = client.post(f"/projects/{slug}/decomposition", json={})
    assert resp.status_code == 200, resp.text
    fg = resp.json()["freigang"]
    assert fg is not None
    assert fg["too_thick"] is False  # 200-mm-Wand ist druckbar
    assert fg["wall_thickness_mm"] == 200.0
    assert fg["printable_depth_mm"] > 200.0
    assert fg["levers"] == []


def test_api_post_decomposition_unknown_slug_returns_404(client, api_dirs):
    resp = client.post("/projects/gibt-es-nicht/decomposition", json={})
    assert resp.status_code == 404


def test_api_post_decomposition_with_manual_cuts_and_joint_offset(
    client, api_dirs, stub_walls, tmp_path
):
    """Schnittplan-Editing (Issue #25) über die API: cuts + joint_offset_mm wirken."""
    slug = _api_project_with_job(client, tmp_path)

    resp = client.post(
        f"/projects/{slug}/decomposition",
        json={
            "cuts": [{"orientation": "horizontal", "position_mm": 1300.0}],
            "joint_offset_mm": 75.0,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cuts"] == [{"orientation": "horizontal", "position_mm": 1300.0}]
    assert data["joint_offset_mm"] == 75.0
    job = data["print_jobs"][0]
    assert job["joint_offset_mm"] == 75.0


def test_api_post_decomposition_with_unknown_override_returns_422(
    client, api_dirs, stub_walls, tmp_path
):
    slug = _api_project_with_job(client, tmp_path)
    resp = client.post(
        f"/projects/{slug}/decomposition",
        json={
            "cuts": [{"orientation": "horizontal", "position_mm": 1300.0}],
            "section_overrides": [{"section_id": "abschnitt-1", "option_id": "gibt-es-nicht"}],
        },
    )
    assert resp.status_code == 422


def test_api_post_decomposition_module_without_workstation_returns_422(
    client, api_dirs, stub_walls, tmp_path
):
    """Art 'modul' ohne Workstation am Druckjob: 422 mit freundlichem Hinweis
    (die Workstation ist der Druckort, ADR-022)."""
    slug = _api_project_with_job(client, tmp_path)
    resp = client.post(f"/projects/{slug}/decomposition",
                       json={"decomposition_kind": "modul"})
    assert resp.status_code == 422
    assert "Workstation" in resp.text


def test_api_put_module_limits_persists_and_clears(client, api_dirs, stub_walls, tmp_path):
    """PUT /projects/{slug}/module-limits persistiert die Obergrenzen sparse;
    None/None entfernt den Block (Altzustand)."""
    slug = _api_project_with_job(client, tmp_path)

    before = client.get(f"/projects/{slug}").json()["print_jobs"][0]
    assert "module_limits" not in before

    resp = client.put(f"/projects/{slug}/module-limits", json={"max_length_mm": 2000.0})
    assert resp.status_code == 200, resp.text
    assert resp.json()["module_limits"] == {"max_length_mm": 2000.0}
    assert resp.json()["print_jobs"][0]["module_limits"] == {"max_length_mm": 2000.0}

    reloaded = client.get(f"/projects/{slug}").json()["print_jobs"][0]
    assert reloaded["module_limits"] == {"max_length_mm": 2000.0}

    # Leer -> Block entfernt.
    cleared = client.put(f"/projects/{slug}/module-limits", json={})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["module_limits"] == {}
    assert "module_limits" not in cleared.json()["print_jobs"][0]


def test_api_put_module_limits_rejects_non_positive(client, api_dirs, stub_walls, tmp_path):
    slug = _api_project_with_job(client, tmp_path)
    resp = client.put(f"/projects/{slug}/module-limits", json={"max_height_mm": 0})
    assert resp.status_code == 422


def test_api_put_module_limits_unknown_slug_returns_404(client, api_dirs):
    resp = client.put("/projects/gibt-es-nicht/module-limits", json={"max_length_mm": 1000.0})
    assert resp.status_code == 404


def test_api_put_placement_override_persists_and_clears(client, api_dirs, stub_walls, tmp_path):
    """PUT /projects/{slug}/placement-override persistiert die freien Werte sparse;
    alles-None entfernt den Eintrag (zurueck zur automatischen Platzierung)."""
    slug = _api_project_with_job(client, tmp_path)

    resp = client.put(
        f"/projects/{slug}/placement-override",
        json={"section_id": "abschnitt-1", "standoff_mm": 900.0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["override"] == {"standoff_mm": 900.0}
    assert resp.json()["print_jobs"][0]["section_overrides"] == [
        {"section_id": "abschnitt-1", "standoff_mm": 900.0}
    ]

    # Persistenz + Wiederherstellung nach Neuladen.
    reloaded = client.get(f"/projects/{slug}").json()["print_jobs"][0]
    assert reloaded["section_overrides"] == [
        {"section_id": "abschnitt-1", "standoff_mm": 900.0}
    ]

    # Leer → Eintrag entfernt (automatische Platzierung).
    cleared = client.put(
        f"/projects/{slug}/placement-override", json={"section_id": "abschnitt-1"}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["override"] == {}
    assert cleared.json()["print_jobs"][0]["section_overrides"] == []


def test_api_put_placement_override_merge_preserves_existing(
    client, api_dirs, stub_walls, tmp_path
):
    """Issue #173: ``merge=True`` ueber die Route bewahrt zuvor gesetzte freie
    Felder (Anwenden-Pfad einer Einzelfeld-Option); ohne Flag gilt Replace."""
    slug = _api_project_with_job(client, tmp_path)

    client.put(
        f"/projects/{slug}/placement-override",
        json={"section_id": "abschnitt-1", "standoff_mm": 600.0},
    )
    merged = client.put(
        f"/projects/{slug}/placement-override",
        json={"section_id": "abschnitt-1", "stand_height_mm": 200.0, "merge": True},
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["override"] == {"standoff_mm": 600.0, "stand_height_mm": 200.0}

    # Ohne merge (Default): Replace raeumt das Nachbarfeld ab (manuelles Formular).
    replaced = client.put(
        f"/projects/{slug}/placement-override",
        json={"section_id": "abschnitt-1", "stand_height_mm": 200.0},
    )
    assert replaced.json()["override"] == {"stand_height_mm": 200.0}


def test_api_put_placement_override_unknown_slug_returns_404(client, api_dirs):
    resp = client.put(
        "/projects/gibt-es-nicht/placement-override", json={"section_id": "abschnitt-1"}
    )
    assert resp.status_code == 404


def test_api_post_decomposition_with_free_override_applies_values(
    client, api_dirs, stub_walls, tmp_path
):
    """Freier Platzierungs-Override ueber die Zerlegungs-Route (Issue #94): der Core
    bewertet ihn mit der bestehenden evaluate-Maschinerie; sparse persistiert."""
    slug = _api_project_with_job(client, tmp_path)

    resp = client.post(
        f"/projects/{slug}/decomposition",
        json={
            "cuts": [{"orientation": "horizontal", "position_mm": 1300.0}],
            "section_overrides": [{"section_id": "abschnitt-1", "stand_height_mm": 444.0}],
        },
    )
    assert resp.status_code == 200, resp.text
    by_id = {s["section_id"]: s for s in resp.json()["sections"]}
    assert by_id["abschnitt-1"]["placement"]["stand_height_mm"] == 444.0
    assert by_id["abschnitt-1"]["placement"]["option_id"] == "frei-abschnitt-1"
    assert "status" in by_id["abschnitt-1"]  # Ampel/erreichbar %/Marge liegen vor
    # Sparse persistiert: keine null-Felder im Druckjob (Schema additiv).
    job = resp.json()["print_jobs"][0]
    assert job["section_overrides"] == [
        {"section_id": "abschnitt-1", "stand_height_mm": 444.0}
    ]


def test_api_put_stand_mode_persists_and_restores(client, api_dirs, stub_walls, tmp_path):
    """PUT /projects/{slug}/stand-mode persistiert den Toggle; er ueberlebt das
    Neuladen (Altprojekt-Default 'floor' vor dem ersten Setzen)."""
    slug = _api_project_with_job(client, tmp_path)

    # Vor dem ersten Setzen fehlt das Feld → Default-Verhalten 'floor' (nicht im JSON).
    before = client.get(f"/projects/{slug}").json()["print_jobs"][0]
    assert "stand_mode" not in before

    resp = client.put(f"/projects/{slug}/stand-mode", json={"stand_mode": "elevated"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["stand_mode"] == "elevated"
    assert resp.json()["print_jobs"][0]["stand_mode"] == "elevated"

    # Nach Neuladen wiederhergestellt (persistiert im project.json).
    reloaded = client.get(f"/projects/{slug}").json()["print_jobs"][0]
    assert reloaded["stand_mode"] == "elevated"


def test_api_put_stand_mode_rejects_unknown_mode(client, api_dirs, stub_walls, tmp_path):
    slug = _api_project_with_job(client, tmp_path)
    resp = client.put(f"/projects/{slug}/stand-mode", json={"stand_mode": "schwebend"})
    assert resp.status_code == 422


def test_api_put_stand_mode_unknown_slug_returns_404(client, api_dirs):
    resp = client.put("/projects/gibt-es-nicht/stand-mode", json={"stand_mode": "floor"})
    assert resp.status_code == 404


def test_api_put_context_check_persists_and_restores(client, api_dirs, stub_walls, tmp_path):
    """PUT /projects/{slug}/context-check persistiert den Gebäudekontext-Schalter
    (Issue #131); er überlebt das Neuladen (Altprojekt-Default 'aus', Feld fehlt)."""
    slug = _api_project_with_job(client, tmp_path)

    before = client.get(f"/projects/{slug}").json()["print_jobs"][0]
    assert "check_building_context" not in before  # Default aus

    resp = client.put(f"/projects/{slug}/context-check", json={"check_building_context": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["check_building_context"] is True
    assert resp.json()["print_jobs"][0]["check_building_context"] is True

    reloaded = client.get(f"/projects/{slug}").json()["print_jobs"][0]
    assert reloaded["check_building_context"] is True

    # „aus" entfernt das Feld wieder (sparse/additiv, byte-gleich zum Altprojekt).
    off = client.put(f"/projects/{slug}/context-check", json={"check_building_context": False})
    assert off.status_code == 200, off.text
    assert off.json()["check_building_context"] is False
    assert "check_building_context" not in off.json()["print_jobs"][0]


def test_api_put_context_check_unknown_slug_returns_404(client, api_dirs):
    resp = client.put(
        "/projects/gibt-es-nicht/context-check", json={"check_building_context": True}
    )
    assert resp.status_code == 404


def test_api_post_decomposition_without_robot_returns_422(client, api_dirs, stub_walls, tmp_path):
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")
    slug = client.post(
        "/projects", json={"name": "H", "model_path": str(model)}
    ).json()["slug"]
    overview_run = client.get(f"/projects/{slug}").json()["overview_run"]
    client.put(f"/projects/{slug}/print-job",
               json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA",
                     "assessment_run": overview_run})

    resp = client.post(f"/projects/{slug}/decomposition", json={})
    assert resp.status_code == 422
