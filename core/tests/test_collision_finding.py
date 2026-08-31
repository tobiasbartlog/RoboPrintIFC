"""Additiver Kollisions-Befund im Trajektorien-Artefakt (ADR-024, PRD #124, Issue #127).

Deckt die Akzeptanzkriterien der I/O-/Schema-Scheibe ab:

- **Additive Schema-Erweiterung, Altläufe byte-gleich**: eine Trajektorie ohne
  ``meta.collision`` validiert unter dem erweiterten Schema und bleibt bei einem
  Serialisierungs-Round-Trip byte-stabil.
- **Regressionsanker ohne Kollisionsgeometrie**: ein Roboter ohne
  ``robot_geometry``-Artefakt liefert **keinen** Befund — die Bestands-Felder
  bleiben byte-gleich, der Block fehlt schlicht (kein ``null``-Füllen).
- **Determinismus**: gleicher Lauf ⇒ bitgleicher Befund (python-fcl determin.,
  Rundung stabil).
- **Foto-Trajektorie als Regressions-Fixture** (``runs/20260708-161603_slice_Denkmal``):
  erwartete Intervall-Anzahl + min. Abstand als Golden (``slow``).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon

from fgc import domain
from fgc.collision import check as ck
from fgc.collision import druckstand as ds
from fgc.collision import finding as fd
from fgc.collision.robot_geometry import load_robot_collision_geometry
from fgc.geometry.section import section_at
from fgc.kinematics.opw import OpwKinematics
from fgc.paths import RUNS_DIR
from fgc.simulation import build_trajectory, transform

ROBOT = "doosan_m1013"
FIXTURE = RUNS_DIR / "20260708-161603_slice_Denkmal"
GOLDEN = Path(__file__).parent / "goldens" / "collision_finding_denkmal.json"

IDENTITY = {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}
PROV = {"source": "test", "created": "2026-07-08T10:00:00Z", "git_commit": "0000000"}


def _small_trajectory():
    """Kleine, erreichbare Bahn (FK einer glatten Gelenkbahn) + ihre Targets."""
    kin = OpwKinematics.from_robot(ROBOT)
    q0 = [0.1, -0.5, 0.8, 0.2, 0.9, -0.3]
    step = [0.03, 0.02, -0.02, 0.01, 0.02, 0.015]
    joints = [[q0[j] + i * step[j] for j in range(6)] for i in range(8)]
    targets = [
        {
            "frame": kin.forward(q).to_dict(),
            "v_mm_s": 100.0,
            "io": {"pump_a": 0.0},
            "kind": "print",
            "layer": 0,
            "segment_id": f"S{i:03d}",
        }
        for i, q in enumerate(joints)
    ]
    setup = {
        "schema_version": "0.1",
        "provenance": PROV,
        "robot": ROBOT,
        "wall_to_base": IDENTITY,
        "tcp": IDENTITY,
        "io_channels": {
            "pump_a": {"kind": "analog_voltage", "index": 0, "physical_range": [0, 10]},
        },
        "deadtime": {"t_tot_s": 0.0, "compensation": "none", "provisional": True},
    }
    return build_trajectory(targets, setup, kin, pose_source="planned"), targets


def _part_box() -> trimesh.Trimesh:
    """Teil-lokales Quader-Mesh (x zentriert, z ab Fuß 0) als Footprint-Quelle."""
    box = trimesh.creation.box(extents=[600.0, 200.0, 1000.0])
    box.apply_translation([0.0, 0.0, 500.0])
    return box


def _request_from(traj, targets) -> fd.FindingRequest:
    """FindingRequest (Issue #192) für eine gegebene Bahn + Targets, Teil = Standard-Quader.

    Ersetzt das frühere ``_finding_kwargs``-Splatting: statt eines 18-Schlüssel-Dicts
    ein gruppiertes Wertobjekt. Varianten baut man mit :func:`dataclasses.replace`
    (z. B. ``replace(req, scene=replace(req.scene, mode="modul"))``)."""
    box = _part_box()
    return fd.FindingRequest(
        trajectory=fd.TrajectoryExcerpt(
            base_frame=traj.meta["base_frame"],
            samples=traj.samples,
            target_times_s=traj.target_times or [],
        ),
        toolpath=fd.ToolpathExcerpt(targets=targets, layer_height_mm=10.0, n_layers=100),
        part=fd.PartMesh(vertices_mm=np.asarray(box.vertices), faces=np.asarray(box.faces)),
        scene=fd.SceneInputs(),
        refs=fd.RobotToolRefs(),
    )


def _base_request() -> fd.FindingRequest:
    """FindingRequest aus einer frischen kleinen Bahn (ersetzt ``_finding_kwargs``)."""
    traj, targets = _small_trajectory()
    return _request_from(traj, targets)


# --- Byte-Kompatibilität: Altläufe laden byte-gleich ---------------------------


def test_old_run_without_collision_validates_and_roundtrips():
    """Eine Trajektorie ohne meta.collision validiert unter dem additiven Schema
    und bleibt beim Serialisieren byte-stabil (keine Zusatzfelder)."""
    traj, _ = _small_trajectory()
    art = traj.to_artifact(PROV)
    assert "collision" not in art["meta"]
    domain.validate(art, "trajectory")
    text = json.dumps(art, indent=2, ensure_ascii=False, allow_nan=False)
    assert json.loads(text) == art


def test_real_old_fixture_validates_under_new_schema():
    """Der reale Altlauf (ohne Befund) validiert weiter — additiv, kein Bruch."""
    path = FIXTURE / "trajectory.json"
    if not path.exists():
        pytest.skip("Fixture-Lauf nicht vorhanden")
    art = json.loads(path.read_text(encoding="utf-8"))
    assert "collision" not in art["meta"]
    domain.validate(art, "trajectory")


# --- Regressionsanker: kein Kollisions-Artefakt ⇒ Befund fehlt schlicht --------


def test_missing_collision_geometry_yields_no_finding(tmp_path):
    """Roboter ohne ``collision_geometry``-Referenz: Befund ist ``None``, die
    Bestands-Felder bleiben byte-gleich (kein ``null``-Füllen)."""
    robots_dir = tmp_path / "robots"
    robots_dir.mkdir()
    # Katalog ohne 'collision_geometry' → collision_dir meldet FileNotFoundError.
    (robots_dir / "nogeo.json").write_text(json.dumps({"schema_version": "0.1"}), encoding="utf-8")

    traj, _ = _small_trajectory()
    art_before = traj.to_artifact(PROV)

    finding = fd.build_section_finding(
        "nogeo",
        fd.FindingRequest(
            trajectory=fd.TrajectoryExcerpt(
                base_frame=traj.meta["base_frame"],
                samples=traj.samples,
                target_times_s=traj.target_times or [],
            ),
            toolpath=fd.ToolpathExcerpt(
                targets=[{"layer": 0, "kind": "print"}], layer_height_mm=10.0, n_layers=1
            ),
            part=fd.PartMesh(vertices_mm=[[0.0, 0.0, 0.0]], faces=[[0, 0, 0]]),
            scene=fd.SceneInputs(),
            refs=fd.RobotToolRefs(robots_dir=robots_dir),
        ),
    )
    assert finding is None
    art_after = traj.to_artifact(PROV)
    assert art_after == art_before
    assert "collision" not in art_after["meta"]


# --- Determinismus: gleicher Lauf ⇒ bitgleicher Befund -------------------------


def _finding_small():
    traj, targets = _small_trajectory()
    return fd.build_section_finding(ROBOT, _request_from(traj, targets)), traj


def test_finding_is_deterministic_and_schema_valid():
    f1, traj = _finding_small()
    f2, _ = _finding_small()
    assert f1 is not None
    # Bitgleicher Befund bei Wiederholung (Determinismus-Kriterium).
    assert json.dumps(f1, sort_keys=True) == json.dumps(f2, sort_keys=True)
    # Konfig-Echo mit provisional-Geist + Abstandskurve parallel zu den Samples.
    assert f1["config"]["provisional"] is True
    assert f1["config"]["safety_distance_mm"] == fd.DEFAULT_SAFETY_DISTANCE_MM
    assert len(f1["distances_mm"]) == len(traj.samples)
    assert len(f1["causer_link"]) == len(traj.samples)
    # Der volle additive Block validiert im Trajektorien-Artefakt.
    art = traj.to_artifact(PROV)
    art["meta"]["collision"] = f1
    domain.validate(art, "trajectory")


# --- Gebäudekontext-Schalter (Issue #131): nur bei „ein" geprüft ---------------


def _context_box() -> trimesh.Trimesh:
    """Kontext-Slab neben dem Arm — nah genug, um bei „ein" einen Befund auszulösen."""
    ctx = trimesh.creation.box(extents=[400.0, 400.0, 1600.0])
    ctx.apply_translation([700.0, 300.0, 800.0])
    return ctx


def _small_trajectory_with_travel():
    """Kleine Bahn mit einem Travel-Lauf in der Mitte (Targets 2..5) — so greift
    die Travel-Ausduennung sichtbar (mehr Travel-Samples als der stride)."""
    kin = OpwKinematics.from_robot(ROBOT)
    q0 = [0.1, -0.5, 0.8, 0.2, 0.9, -0.3]
    step = [0.03, 0.02, -0.02, 0.01, 0.02, 0.015]
    joints = [[q0[j] + i * step[j] for j in range(6)] for i in range(8)]
    targets = [
        {
            "frame": kin.forward(q).to_dict(),
            "v_mm_s": 100.0,
            "io": {"pump_a": 0.0},
            "kind": "travel" if 2 <= i < 6 else "print",
            "layer": 0,
            "segment_id": f"S{i:03d}",
        }
        for i, q in enumerate(joints)
    ]
    setup = {
        "schema_version": "0.1",
        "provenance": PROV,
        "robot": ROBOT,
        "wall_to_base": IDENTITY,
        "tcp": IDENTITY,
        "io_channels": {
            "pump_a": {"kind": "analog_voltage", "index": 0, "physical_range": [0, 10]},
        },
        "deadtime": {"t_tot_s": 0.0, "compensation": "none", "provisional": True},
    }
    return build_trajectory(targets, setup, kin, pose_source="planned"), targets


def test_context_checked_only_when_enabled():
    """Der Kontext-Schalter treibt die Prüfung: bei „aus" ist ein mitgegebener
    Kontext byte-gleich zu „kein Kontext"; bei „ein" wird er als Hindernis geprüft
    (Verursacher 'context', kleinerer Mindestabstand) und das Konfig-Echo kippt."""
    ctx = _context_box()
    ctx_v, ctx_f = np.asarray(ctx.vertices), np.asarray(ctx.faces)
    req = _base_request()

    none = fd.build_section_finding(
        ROBOT, replace(req, config=fd.CollisionConfig(context_enabled=False))
    )
    off = fd.build_section_finding(
        ROBOT,
        replace(
            req,
            config=fd.CollisionConfig(context_enabled=False),
            scene=replace(req.scene, context=(ctx_v, ctx_f)),
        ),
    )
    on = fd.build_section_finding(
        ROBOT,
        replace(
            req,
            config=fd.CollisionConfig(context_enabled=True),
            scene=replace(req.scene, context=(ctx_v, ctx_f)),
        ),
    )

    # „aus" + Kontextgeometrie == „kein Kontext" (der Kontext wird nicht geprüft).
    assert json.dumps(off, sort_keys=True) == json.dumps(none, sort_keys=True)
    assert off["config"]["context_enabled"] is False
    # „ein": Konfig-Echo kippt, der Kontext wird zum Verursacher, der Befund ändert sich.
    assert on["config"]["context_enabled"] is True
    assert json.dumps(on, sort_keys=True) != json.dumps(none, sort_keys=True)
    assert "context" in set(on["causer_against"])


def test_context_ignored_for_modul():
    """Bei Zerlegungsart Modul ist der Kontext-Schalter gegenstandslos (ADR-022):
    „ein" + Kontextgeometrie liefert byte-gleich zum kontextlosen Modul-Befund."""
    ctx = _context_box()
    ctx_v, ctx_f = np.asarray(ctx.vertices), np.asarray(ctx.faces)
    req = _base_request()

    none = fd.build_section_finding(
        ROBOT,
        replace(
            req,
            scene=replace(req.scene, mode="modul"),
            config=fd.CollisionConfig(context_enabled=True),
        ),
    )
    on = fd.build_section_finding(
        ROBOT,
        replace(
            req,
            scene=replace(req.scene, mode="modul", context=(ctx_v, ctx_f)),
            config=fd.CollisionConfig(context_enabled=True),
        ),
    )
    assert json.dumps(on, sort_keys=True) == json.dumps(none, sort_keys=True)


"""--- Echte Höhenlage: Boden bei lokal −z0, frühere Teile (Issue #135) ---------"""


def test_z0_zero_finding_bit_identical():
    """Regressionsanker (Issue #135): die unterste Reihe (z0 = 0, keine früheren
    Teile) liefert mit den neuen additiven Parametern einen **bit-identischen**
    Befund zum bisherigen Aufruf — kein Boden am Fuß (v1-Lehrgeld #127)."""
    req = _base_request()
    before = fd.build_section_finding(ROBOT, req)
    after = fd.build_section_finding(
        ROBOT, replace(req, scene=replace(req.scene, section_z0_mm=0.0, earlier_parts=()))
    )
    assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)


def test_upper_section_ground_no_false_alarm_at_section_foot():
    """Oberer Abschnitt (z0 > 0, Basis am Boden): der Boden liegt bei lokal −z0 —
    weit unter der Bahn am Abschnittsfuß. Kein „unter Boden"-Fehlalarm: kein
    rotes/gelbes Intervall gegen 'ground', Ampelzählung wie ohne Boden."""
    req = _base_request()
    baseline = fd.build_section_finding(ROBOT, req)
    upper = fd.build_section_finding(
        ROBOT, replace(req, scene=replace(req.scene, section_z0_mm=1300.0))
    )
    assert upper is not None
    # Kein Kollisions-/Warn-Intervall gegen den Boden (der liegt 1300 mm tiefer).
    assert not any(
        iv["against"] == "ground" and iv["status"] != "green"
        for iv in upper["intervals"]
    )
    # Die Ampelzählung bleibt die des bodenlosen Befunds — der echte Boden bei
    # −z0 ist für diese Bahn schlicht weit weg (kein Fehlalarm am Abschnittsfuß).
    assert upper["n_red"] == baseline["n_red"]
    assert upper["n_yellow"] == baseline["n_yellow"]
    assert upper["n_green"] == baseline["n_green"]


def test_earlier_part_becomes_obstacle_on_its_band():
    """Ein früheres Teil (bereits ins abschnitts-lokale System verschoben) wird
    volles Hindernis: der Befund ändert sich, Verursacher 'part0' erscheint."""
    part = _context_box()  # Slab neben dem Arm — nah genug für einen Befund
    req = _base_request()
    baseline = fd.build_section_finding(ROBOT, req)
    with_part = fd.build_section_finding(
        ROBOT,
        replace(
            req,
            scene=replace(
                req.scene,
                earlier_parts=((np.asarray(part.vertices), np.asarray(part.faces)),),
            ),
        ),
    )
    assert json.dumps(with_part, sort_keys=True) != json.dumps(baseline, sort_keys=True)
    assert "part0" in set(with_part["causer_against"])


def test_modul_ignores_z0_and_earlier_parts():
    """Art „modul": Workstation ist der Druckort (ADR-022) — z0/frühere Teile
    sind gegenstandslos, der Befund bleibt byte-gleich."""
    part = _context_box()
    req = _base_request()
    plain = fd.build_section_finding(ROBOT, replace(req, scene=replace(req.scene, mode="modul")))
    decorated = fd.build_section_finding(
        ROBOT,
        replace(
            req,
            scene=replace(
                req.scene,
                mode="modul",
                section_z0_mm=1300.0,
                earlier_parts=((np.asarray(part.vertices), np.asarray(part.faces)),),
            ),
        ),
    )
    assert json.dumps(decorated, sort_keys=True) == json.dumps(plain, sort_keys=True)


def test_travel_intervals_flag_travel_segments():
    """Travel-Segmente werden als 'nicht lückenlos geprüft' verdichtet markiert."""
    # Zwei Targets bei t=0 (print) und t=1 (travel); Samples decken beide.
    ivs = fd.travel_intervals([0.0, 0.5, 1.0, 1.5], [0.0, 1.0], ["print", "travel"])
    assert ivs == [(2, 3)]
    empty = fd.travel_intervals([0.0, 1.0], [0.0, 1.0], ["print", "print"])
    assert empty == []


# --- Pruef-Tuer: Travel-Ausduennung + kompaktes Urteil (Issue #162) ------------


def test_travel_flags_inherit_toolpath_kind():
    """Jedes Sample erbt die kind seines Toolpath-Segments (Bisektion), ohne
    Target-Arten sind alle Samples 'nicht Travel'."""
    flags = fd.travel_flags([0.0, 0.5, 1.0, 1.5], [0.0, 1.0], ["print", "travel"])
    assert flags == [False, False, True, True]
    assert fd.travel_flags([0.0, 1.0, 2.0], [], []) == [False, False, False]


def test_thin_travel_indices_keeps_print_and_run_endpoints():
    """Travel-Ausduennung: alle Druck-Samples + jedes stride-te Travel-Sample,
    Anfang UND Ende jedes Travel-Laufs bleiben erhalten (Fehler Richtung 'geprüft')."""
    # Indizes 2..8 sind Travel (ein Lauf der Länge 7), stride 3.
    flags = [False, False, True, True, True, True, True, True, True, False]
    kept = fd.thin_travel_indices(flags, 3)
    # Druck: 0,1,9 immer; Travel-Lauf [2..8]: 2 (Anfang), 5 (stride), 8 (Ende).
    assert kept == [0, 1, 2, 5, 8, 9]


def test_thin_travel_indices_identity_when_stride_le_1():
    """stride <= 1 behält jedes Sample (Identität) — dann prüft die Tür wie voll."""
    flags = [False, True, True, False]
    assert fd.thin_travel_indices(flags, 1) == [0, 1, 2, 3]
    assert fd.thin_travel_indices(flags, 0) == [0, 1, 2, 3]


def test_check_part_clearance_none_without_geometry(tmp_path):
    """Fail-soft wie der volle Befund: Roboter ohne Kollisionsgeometrie ⇒ None."""
    robots_dir = tmp_path / "robots"
    robots_dir.mkdir()
    (robots_dir / "nogeo.json").write_text(json.dumps({"schema_version": "0.1"}), encoding="utf-8")
    traj, _ = _small_trajectory()
    verdict = fd.check_part_clearance(
        "nogeo",
        fd.FindingRequest(
            trajectory=fd.TrajectoryExcerpt(
                base_frame=traj.meta["base_frame"],
                samples=traj.samples,
                target_times_s=traj.target_times or [],
            ),
            toolpath=fd.ToolpathExcerpt(
                targets=[{"layer": 0, "kind": "print"}], layer_height_mm=10.0, n_layers=1
            ),
            part=fd.PartMesh(vertices_mm=[[0.0, 0.0, 0.0]], faces=[[0, 0, 0]]),
            scene=fd.SceneInputs(),
            refs=fd.RobotToolRefs(robots_dir=robots_dir),
        ),
    )
    assert verdict is None


def test_check_part_clearance_matches_full_verdict_print_only():
    """Ohne Travel-Samples (Ausduennung wirkungslos) trifft die Pruef-Tuer das
    frei/kollidiert-Urteil des vollen Befunds bit-genau — dieselbe find_collisions-
    Maschinerie, dieselben Verursacher/Eindringtiefe."""
    traj, targets = _small_trajectory()  # alle Targets 'print' ⇒ keine Travel-Samples
    req = _request_from(traj, targets)
    full = fd.build_section_finding(ROBOT, req)
    assert full is not None
    verdict = fd.check_part_clearance(ROBOT, req, travel_stride=5)
    assert verdict is not None
    # Nichts ausgedünnt (kein Travel) → alle Samples geprüft, Urteil identisch.
    assert verdict.travel_thinned is False
    assert verdict.n_checked == verdict.n_samples == len(traj.samples)
    assert verdict.collides == (full["n_red"] > 0)
    assert verdict.n_red == full["n_red"]
    assert verdict.min_distance_mm == full["min_distance_mm"]
    worst = full["worst_index"]
    assert verdict.causer_link == full["causer_link"][worst]
    assert verdict.causer_against == full["causer_against"][worst]
    # Eindringtiefe = max(0, −min_distance) des schlimmsten Samples.
    expected_pen = max(0.0, -(full["min_distance_mm"] or 0.0))
    assert verdict.penetration_mm == round(expected_pen, fd.ROUND_DECIMALS)


def test_check_part_clearance_thins_travel_samples():
    """Mit Travel-Samples prüft die Tür weniger Samples (n_checked < n_samples),
    das kollidiert/frei-Urteil bleibt das des vollen Befunds (S5-Hebel, sicher)."""
    traj, targets = _small_trajectory_with_travel()
    req = _request_from(traj, targets)
    full = fd.build_section_finding(ROBOT, req)
    assert full is not None
    thinned = fd.check_part_clearance(ROBOT, req, travel_stride=5)
    full_stride = fd.check_part_clearance(ROBOT, req, travel_stride=1)
    assert thinned is not None and full_stride is not None
    # stride=1 prüft alles und trifft den vollen Befund; stride=5 dünnt Travel aus.
    assert full_stride.n_checked == len(traj.samples)
    assert thinned.travel_thinned is True
    assert thinned.n_checked < thinned.n_samples == len(traj.samples)
    # Das frei/kollidiert-Urteil bleibt gleich (Travel ist ohnehin 'nicht lückenlos').
    assert thinned.collides == (full["n_red"] > 0) == full_stride.collides


# --- Kollisions-ORT der Pruef-Tuer (Issue #181, Vorarbeit fuer #165) -----------


def test_original_sample_index_maps_back_including_travel_run_edges():
    """Rueckrechnung Ausduennungs-Index → Original-Index (Issue #181), inklusive der
    Randfaelle Anfang/Ende eines Travel-Laufs — genau die Positionen, die
    ``thin_travel_indices`` laut seinem Vertrag IMMER erhaelt (s. dort)."""
    # Ein Travel-Lauf über Indizes 2..8 (Länge 7), stride 3.
    flags = [False, False, True, True, True, True, True, True, True, False]
    kept = fd.thin_travel_indices(flags, 3)
    assert kept == [0, 1, 2, 5, 8, 9]

    # Druck vor dem Lauf: Ausduennungs- und Original-Index sind identisch (0, 1).
    assert fd.original_sample_index(kept, 0) == 0
    assert fd.original_sample_index(kept, 1) == 1
    # Position 2 = ANFANG des Travel-Laufs (Original-Index 2 — bleibt erhalten).
    assert fd.original_sample_index(kept, 2) == 2
    # Position 3 = stride-Sample in der Laufmitte (Original-Index 5).
    assert fd.original_sample_index(kept, 3) == 5
    # Position 4 = ENDE des Travel-Laufs (Original-Index 8, nicht 7 — (8-2)%3 != 0,
    # das Ende bleibt trotzdem erhalten, s. thin_travel_indices).
    assert fd.original_sample_index(kept, 4) == 8
    # Druck nach dem Lauf (Original-Index 9).
    assert fd.original_sample_index(kept, 5) == 9

    # Außerhalb von [0, len(kept)) — z. B. der -1-Sentinel eines Berichts ohne
    # endlichen Abstand — liefert None statt eines IndexError.
    assert fd.original_sample_index(kept, -1) is None
    assert fd.original_sample_index(kept, len(kept)) is None


def test_original_sample_index_identity_without_thinning():
    """stride ≤ 1 (keine Ausdünnung): Original- und Ausdünnungs-Index fallen zusammen."""
    kept = fd.thin_travel_indices([False, True, True, False], 1)
    for i in range(len(kept)):
        assert fd.original_sample_index(kept, i) == i


def _frame(pos: tuple[float, float, float]):
    from fgc.domain.models import Frame

    return Frame(pos_mm=pos, quat=(1.0, 0.0, 0.0, 0.0))


def test_clearance_verdict_from_report_computes_collision_location():
    """Kollisions-ORT direkt am Urteils-Kern (Issue #181): ein synthetischer
    ``CollisionReport`` (kontrollierte Verursacher/Positionen/Schichten) belegt die
    Rückrechnung Original-Index, Schicht, Verursacher-Position und rote Intervalle
    — schnell und isoliert von der (Druckstand-)Kollisionsgeometrie."""
    samples = (
        ck.SampleResult(0, 100.0, "green", None, None, "broad"),
        ck.SampleResult(1, -10.0, "red", 2, "current_part", "judgment"),
        ck.SampleResult(2, -30.0, "red", 2, "current_part", "judgment"),
        ck.SampleResult(3, 40.0, "green", None, None, "broad"),
    )
    intervals = (
        ck.Interval("green", 0, 0, 100.0, 0, None, None),
        ck.Interval("red", 1, 2, -30.0, 2, 2, "current_part"),
        ck.Interval("green", 3, 3, 40.0, 3, None, None),
    )
    report = ck.CollisionReport(
        samples=samples, intervals=intervals, min_distance_mm=-30.0, worst_index=2,
        safety_distance_mm=50.0, n_red=2, n_yellow=0, n_green=2, tool_provisional=False,
    )
    # Ausdünnung: die 4 geprüften Positionen entsprechen den Original-Indizes
    # [0, 3, 5, 7] (z. B. weil 1, 2, 4, 6 ausgedünnte Travel-Samples waren).
    kept = [0, 3, 5, 7]
    sample_layers = [0, 1, 2, 3]  # Schicht je geprüfte (ausgedünnte) Position
    # Glied-Frames je geprüfte Position (7 Glieder je Sample); Glied 2 bei Position 2
    # (Original-Index 5, der schlimmste) an einer eindeutigen Stelle platziert.
    link_frames = [[_frame((0.0, 0.0, float(k) * 1000.0)) for _ in range(7)] for k in range(4)]
    link_frames[2][2] = _frame((111.0, 222.0, 333.0))
    base = _frame((10.0, 20.0, 30.0))

    verdict = fd.ClearanceVerdict.from_report(
        report, n_samples=8, travel_thinned=True,
        kept=kept, link_frames=link_frames, sample_layers=sample_layers,
        base=base, tcp_frame=None,
    )

    assert verdict.worst_original_index == 5  # kept[2]
    assert verdict.worst_layer == 2
    # compose(base, link) mit Identitäts-Quaternion = einfache Positionsaddition.
    assert verdict.causer_position_mm == (121.0, 242.0, 363.0)
    assert len(verdict.red_intervals) == 1
    iv = verdict.red_intervals[0]
    assert iv.start_index == 3  # kept[1]
    assert iv.end_index == 5  # kept[2]
    assert iv.worst_index == 5  # kept[2]
    assert iv.link == 2
    assert iv.against == "current_part"
    assert iv.min_distance_mm == -30.0

    # Additiv: der to_dict()-Roundtrip trägt dieselben Werte in JSON-Form.
    d = verdict.to_dict()
    assert d["worst_original_index"] == 5
    assert d["worst_layer"] == 2
    assert d["causer_position_mm"] == [121.0, 242.0, 363.0]
    assert d["red_intervals"] == [
        {
            "link": 2, "against": "current_part",
            "start_index": 3, "end_index": 5, "worst_index": 5,
            "min_distance_mm": -30.0,
        }
    ]


def test_clearance_verdict_from_report_stays_additive_without_location_args():
    """Additivität (Issue #181): ``from_report`` ohne die neuen Ort-Argumente (wie
    ein Altaufrufer, der von keiner Ausdünnung weiß) liefert weiterhin ein gültiges
    Urteil — die bestehenden Felder bleiben unverändert, ``kept`` fällt fail-soft auf
    Identität zurück (keine bekannte Ausdünnung ⇒ Original-Index = Bericht-Index),
    die Felder, die zusätzliche Frames/Basis brauchen (``worst_layer``,
    ``causer_position_mm``), bleiben ``None`` — kein erfundener Ort ohne Daten."""
    samples = (ck.SampleResult(0, -5.0, "red", 3, "ground", "judgment"),)
    intervals = (ck.Interval("red", 0, 0, -5.0, 0, 3, "ground"),)
    report = ck.CollisionReport(
        samples=samples, intervals=intervals, min_distance_mm=-5.0, worst_index=0,
        safety_distance_mm=50.0, n_red=1, n_yellow=0, n_green=0, tool_provisional=False,
    )
    verdict = fd.ClearanceVerdict.from_report(report, n_samples=1, travel_thinned=False)
    assert verdict.collides is True
    assert verdict.causer_link == 3
    assert verdict.causer_against == "ground"
    # Keine Ausdünnungs-Abbildung übergeben ⇒ Identität (kein IndexError, kein None).
    assert verdict.worst_original_index == 0
    # Schicht/Position brauchen zusätzliche Argumente (Frames/Basis) — ohne sie None.
    assert verdict.worst_layer is None
    assert verdict.causer_position_mm is None
    assert verdict.red_intervals == (
        fd.RedInterval(
            link=3, against="ground", start_index=0, end_index=0, worst_index=0,
            min_distance_mm=-5.0,
        ),
    )


def _flange_teil_pos(kin: OpwKinematics, joints_rad: list[float]) -> np.ndarray:
    """Teil-/Wandsystem-Position des Flanschs (Glied 6) bei Basis = Identität —
    Anker für ein konstruiertes Hindernis genau an diesem Gelenkzustand."""
    lf = kin.link_frames(joints_rad)
    return np.asarray(transform.compose(transform.frame_from_dict(IDENTITY), lf[6]).pos_mm)


def _box(extents: list[float], center) -> tuple[np.ndarray, np.ndarray]:
    box = trimesh.creation.box(extents=extents)
    box.apply_translation(list(center))
    return np.asarray(box.vertices), np.asarray(box.faces)


def _clearance_request_with_collision_at(
    target_sample: int, n: int = 14
) -> tuple[fd.FindingRequest, list, list]:
    """Konstruierte Bahn mit einer Kollision an GENAU ``target_sample``: alle übrigen
    Samples in einer freien Ruhepose, nur dieses eine taucht in ein dort platziertes
    Hindernis (dieselbe, geprüft isolierende Konstruktion wie
    ``test_prueftuer_gefahrrichtung``, inkl. ``layer=0`` konstant — nur so bleibt der
    wachsende Druckstand über die Bahn minimal und die Ruhepose kollidiert nirgends
    außer am konstruierten Sample). Ein Travel-Lauf über die Original-Indizes 2..11
    (Länge 10) erlaubt, ``target_sample`` gezielt auf einen Innen- oder Rand-Fall
    (Anfang/Ende) der Travel-Ausdünnung zu legen."""
    kin = OpwKinematics.from_robot(ROBOT)
    kinds = ["travel" if 2 <= i < 12 else "print" for i in range(n)]
    times = [float(i) for i in range(n)]
    targets = [{"layer": 0, "kind": kinds[i]} for i in range(n)]

    q_safe = [0.0, -1.3, 0.3, 0.0, 0.8, 0.0]
    q_spike = [0.2, -0.2, 0.55, 0.0, 1.1, 0.0]
    joints = [list(q_safe) for _ in range(n)]
    joints[target_sample] = list(q_spike)
    samples = [{"joints_rad": joints[i], "t_s": times[i]} for i in range(n)]

    part_v, part_f = _box([600.0, 200.0, 1000.0], [0.0, 0.0, 500.0])
    obstacle = _box([120.0, 120.0, 120.0], _flange_teil_pos(kin, q_spike))

    req = fd.FindingRequest(
        trajectory=fd.TrajectoryExcerpt(
            base_frame=IDENTITY, samples=samples, target_times_s=times
        ),
        toolpath=fd.ToolpathExcerpt(targets=targets, layer_height_mm=10.0, n_layers=100),
        part=fd.PartMesh(vertices_mm=part_v, faces=part_f),
        scene=fd.SceneInputs(mode="abschnitt", earlier_parts=(obstacle,)),
        refs=fd.RobotToolRefs(),
    )
    return req, kinds, times


def test_check_part_clearance_reports_collision_location_full_stride():
    """Kollisions-ORT (Issue #181) an der echten Pruef-Tuer: konstruierte Kollision
    an einem Druck-Sample, ``travel_stride=1`` (keine Ausdünnung) —
    ``worst_original_index``/``worst_layer``/``causer_position_mm``/``red_intervals``
    sind plausibel und stimmen mit ``causer_link``/``causer_against`` des kompakten
    Urteils überein."""
    target_sample = 6  # liegt im Travel-Lauf (2..11), stride=1 dünnt hier nichts aus
    req, _kinds, _times = _clearance_request_with_collision_at(target_sample)
    verdict = fd.check_part_clearance(ROBOT, req, travel_stride=1)
    assert verdict is not None and verdict.collides is True
    assert verdict.travel_thinned is False
    assert verdict.n_red == 1, "Testaufbau: genau EIN Sample (das konstruierte) kollidiert"

    assert verdict.worst_original_index == target_sample
    assert verdict.worst_layer == 0  # alle Targets tragen layer=0 (Testaufbau)
    assert verdict.causer_position_mm is not None
    assert len(verdict.causer_position_mm) == 3
    assert verdict.red_intervals, "eine konstruierte Kollision muss mind. ein rotes Intervall haben"
    iv = verdict.red_intervals[0]
    assert iv.start_index <= target_sample <= iv.end_index
    assert iv.worst_index == target_sample
    assert iv.link == verdict.causer_link
    assert iv.against == verdict.causer_against
    assert iv.min_distance_mm == verdict.min_distance_mm

    # Additiv: der to_dict()-Roundtrip trägt dieselben Werte in JSON-Form.
    d = verdict.to_dict()
    assert d["worst_original_index"] == target_sample
    assert d["causer_position_mm"] == list(verdict.causer_position_mm)
    assert d["red_intervals"][0]["worst_index"] == target_sample


def test_check_part_clearance_reports_collision_location_at_travel_run_end():
    """Randfall ENDE eines Travel-Laufs (Issue #181, Akzeptanzkriterium 'Randfälle
    Anfang/Ende'): die konstruierte Kollision liegt am letzten Sample eines
    Travel-Laufs (Original-Index 11) — ``thin_travel_indices`` erhält Enden IMMER,
    die ausgedünnte Pruef-Tuer (stride=5) sieht das Sample also trotzdem und muss
    seinen Original-Index korrekt zurückrechnen (nicht den internen, ausgedünnten
    Index — der wäre hier eine andere Zahl, s. Testaufbau-Assertion unten)."""
    target_sample = 11
    req, kinds, times = _clearance_request_with_collision_at(target_sample)
    kept = fd.thin_travel_indices(fd.travel_flags(times, times, kinds), 5)
    assert target_sample in kept, "Testaufbau: das Ende eines Travel-Laufs bleibt erhalten"
    thinned_position = kept.index(target_sample)
    assert thinned_position != target_sample, (
        "Testaufbau: der Ausdünnungs-Index muss vom Original-Index abweichen — "
        "sonst wäre die Rückrechnung tautologisch (Identität statt echter Test)"
    )

    verdict = fd.check_part_clearance(ROBOT, req, travel_stride=5)
    assert verdict is not None and verdict.collides is True
    assert verdict.travel_thinned is True

    # Der schlimmste Sample-Index ist auf Original-Indizierung zurückgerechnet —
    # NICHT die interne, ausgedünnte Position (die wäre hier != target_sample).
    assert verdict.worst_original_index == target_sample
    assert verdict.red_intervals
    assert verdict.red_intervals[0].worst_index == target_sample
    assert verdict.red_intervals[0].end_index == target_sample


def test_check_part_clearance_reports_collision_location_at_travel_run_start():
    """Randfall ANFANG eines Travel-Laufs (Issue #181, Akzeptanzkriterium 'Randfälle
    Anfang/Ende') — spiegelbildlich zum Ende-Test oben."""
    target_sample = 2
    req, kinds, times = _clearance_request_with_collision_at(target_sample)
    kept = fd.thin_travel_indices(fd.travel_flags(times, times, kinds), 5)
    assert target_sample in kept, "Testaufbau: der Anfang eines Travel-Laufs bleibt erhalten"

    verdict = fd.check_part_clearance(ROBOT, req, travel_stride=5)
    assert verdict is not None and verdict.collides is True
    assert verdict.worst_original_index == target_sample
    assert verdict.red_intervals[0].start_index == target_sample


def test_check_part_clearance_no_collision_has_no_location():
    """Ohne Kollision (frei) bleiben die neuen Ort-Felder None/leer — additiv, kein
    erfundener Ort ohne Verursacher (Issue #181)."""
    traj, targets = _small_trajectory()  # alle Targets 'print', erreichbare Ruhebahn
    req = _request_from(traj, targets)
    verdict = fd.check_part_clearance(ROBOT, req, travel_stride=5)
    assert verdict is not None and verdict.collides is False
    assert verdict.worst_original_index is None
    assert verdict.worst_layer is None
    assert verdict.causer_position_mm is None
    assert verdict.red_intervals == ()
    d = verdict.to_dict()
    assert d["causer_position_mm"] is None
    assert d["red_intervals"] == []


# --- Foto-Trajektorie als Regressions-Fixture (Golden, slow) -------------------


def _floor() -> trimesh.Trimesh:
    f = trimesh.creation.box(extents=[6000.0, 6000.0, 200.0])
    f.apply_translation([0.0, 0.0, -100.0])
    return f


def _fixture_report() -> ck.CollisionReport:
    """Befund der Foto-Trajektorie aus den Artefakten (artefakt-eigene Rekonstruktion).

    Die Schicht je Sample kommt hier aus der Flansch-Höhe auf dem Toolpath-
    Schichtraster (Spike-validiertes, artefakt-eigenes Verfahren — die Target-
    Zeitachse wird beim Lauf nicht persistiert); dieselbe ``find_collisions``-
    Maschinerie wie in der Simulation. Deterministisch (python-fcl, Spike S0).
    """
    traj = json.loads((FIXTURE / "trajectory.json").read_text(encoding="utf-8"))
    wallspec = json.loads((FIXTURE / "wallspec.json").read_text(encoding="utf-8"))
    toolpath = json.loads((FIXTURE / "toolpath.json").read_text(encoding="utf-8"))
    layer_h = float(toolpath["params"]["layer_height_mm"])
    n_layers = int(toolpath["summary"]["n_layers"])

    geo = load_robot_collision_geometry(ROBOT)
    kin = OpwKinematics.from_robot(ROBOT)
    base = transform.frame_from_dict(traj["meta"]["base_frame"])
    samples = traj["samples"]
    lfs = [kin.link_frames(s["joints_rad"]) for s in samples]

    wall = trimesh.Trimesh(
        vertices=np.array(wallspec["geometry"]["vertices_mm"], dtype=float),
        faces=np.array(wallspec["geometry"]["faces"], dtype=int),
        process=True,
    )
    footprint = tuple(section_at(wall, 1.0)) or (
        Polygon(
            [
                (wall.bounds[0][0], wall.bounds[0][1]),
                (wall.bounds[1][0], wall.bounds[0][1]),
                (wall.bounds[1][0], wall.bounds[1][1]),
                (wall.bounds[0][0], wall.bounds[1][1]),
            ]
        ),
    )
    spec = ds.DruckstandSpec(
        footprint=footprint, layer_height_mm=layer_h, n_layers=n_layers, ground=_floor()
    )
    prov = ds.obstacle_provider(spec)
    zs = [transform.compose(base, lf[6]).pos_mm[2] for lf in lfs]
    sample_layers = [int(np.clip(int(np.floor(z / layer_h)), 0, n_layers)) for z in zs]

    return ck.find_collisions(geo, base, lfs, sample_layers, prov, self_collision=False)


@pytest.mark.slow
def test_fixture_finding_matches_golden():
    if not (FIXTURE / "trajectory.json").exists():
        pytest.skip("Fixture-Lauf nicht vorhanden")
    block = fd.report_to_dict(
        _fixture_report(), config=fd.CollisionConfig(), mode="abschnitt", travel_intervals=[]
    )
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(block["intervals"]) == golden["n_intervals"]
    assert block["min_distance_mm"] == golden["min_distance_mm"]


@pytest.mark.slow
def test_fixture_finding_bit_identical_on_repeat():
    if not (FIXTURE / "trajectory.json").exists():
        pytest.skip("Fixture-Lauf nicht vorhanden")
    b1 = fd.report_to_dict(
        _fixture_report(), config=fd.CollisionConfig(), mode="abschnitt", travel_intervals=[]
    )
    b2 = fd.report_to_dict(
        _fixture_report(), config=fd.CollisionConfig(), mode="abschnitt", travel_intervals=[]
    )
    assert json.dumps(b1, sort_keys=True) == json.dumps(b2, sort_keys=True)
