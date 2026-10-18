"""Tests der Verträge: Roundtrip, Validierung, Szenarien, Fixture und Aktualität von Schema/TS."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from roboprint.contracts import (
    TOP_LEVEL_MODELS,
    JobCreate,
    JobState,
    PartArtifact,
    ProjectInfo,
    Scenario,
    Scene,
    Summary,
    Toolpath,
    Trajectory,
    dump_json,
    export_schemas,
    load_json,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "web" / "fixtures" / "run_demo"
SCHEMAS = REPO / "web" / "src" / "contracts" / "schemas"
CONTRACTS_TS = REPO / "web" / "src" / "contracts"
REGEN = "python -m roboprint export-contracts web/src/contracts/schemas && npm --prefix web run gen:contracts"


def _traj(n: int = 3) -> dict:
    return {
        "schema_version": "2",
        "part_id": "P01",
        "t_s": [0.1 * i for i in range(n)],
        "q": [[0.0] * 6 for _ in range(n)],
        "tcp": [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for _ in range(n)],
        "layer": [0] * n,
        "ring": [0] * n,
        "kind": ["print"] * n,
        "branch": [0] * n,
        "status": ["ok"] * n,
        "d_mm": [50.0] * n,
        "pair": [["link_1", "floor"]] * n,
        "witness": [[[0, 0, 0], [0, 0, 1]]] * n,
        "psi_rad": [0.0] * n,
        "summary": {
            "n": n, "n_ok": n, "n_warn": 0, "n_collision": 0, "n_unreachable": 0,
            "d_min_mm": 50.0, "dauer_s": 0.2, "zweig_wechsel_in_ringen": 0,
        },
    }  # fmt: skip


# ----------------------------------------------------------------- Roundtrip und Fixture


@pytest.mark.parametrize(
    ("rel", "model"),
    [
        ("summary.json", Summary),
        ("scene.json", Scene),
        ("parts/P01/part.json", PartArtifact),
        ("parts/P01/toolpath.json", Toolpath),
        ("parts/P01/trajectory.json", Trajectory),
    ],
)
def test_fixture_validates_and_roundtrips(rel: str, model: type, tmp_path: Path) -> None:
    obj = load_json(FIXTURE / rel, model)
    out = dump_json(obj, tmp_path / "x.json")
    assert load_json(out, model) == obj
    assert out.read_text(encoding="utf-8").endswith("\n")
    # Vollständige Ausgabe: gleicher JSON-Inhalt wie die Fixture-Datei
    assert json.loads(out.read_text()) == json.loads((FIXTURE / rel).read_text())


def test_fixture_content() -> None:
    traj = load_json(FIXTURE / "parts/P01/trajectory.json", Trajectory)
    assert 200 <= len(traj.t_s) <= 2000
    assert {"warn", "collision"} <= set(traj.status)
    i = traj.status.index("collision")
    assert traj.pair[i] is not None and traj.witness[i] is not None and traj.d_mm[i] < 0
    summary = load_json(FIXTURE / "summary.json", Summary)
    assert any("Fixture, nicht geprüft" in a for a in summary.assumptions)
    assert (FIXTURE / "parts/P01/part.stl").stat().st_size > 0
    assert (FIXTURE / "parts/P01/program.v2.drl").read_text().strip()


def test_fixture_is_reproducible(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("make_fixture", REPO / "web/fixtures/make_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_fixture"] = mod
    spec.loader.exec_module(mod)
    mod.make(tmp_path / "run_demo")
    for f in sorted(p for p in FIXTURE.rglob("*") if p.is_file()):
        assert (tmp_path / "run_demo" / f.relative_to(FIXTURE)).read_bytes() == f.read_bytes(), f


# ----------------------------------------------------------------- Validierung


def test_trajectory_valid_minimal() -> None:
    Trajectory.model_validate(_traj())


def test_trajectory_unequal_lengths() -> None:
    d = _traj()
    d["q"].pop()
    with pytest.raises(ValidationError, match="Länge"):
        Trajectory.model_validate(d)


def test_trajectory_t_s_not_monotone() -> None:
    d = _traj()
    d["t_s"][2] = d["t_s"][1]
    with pytest.raises(ValidationError, match="monoton"):
        Trajectory.model_validate(d)


def test_trajectory_unreachable_needs_nulls() -> None:
    d = _traj()
    d["status"][1] = "unreachable"
    d["summary"].update(n_ok=2, n_unreachable=1)
    with pytest.raises(ValidationError, match="unreachable"):
        Trajectory.model_validate(d)
    d["d_mm"][1] = d["pair"][1] = d["witness"][1] = None
    Trajectory.model_validate(d)


def test_trajectory_summary_must_match() -> None:
    d = _traj()
    d["summary"]["n_ok"] = 2
    with pytest.raises(ValidationError, match="summary"):
        Trajectory.model_validate(d)


@pytest.mark.parametrize(
    ("key", "value"),
    [("kind", ["jump"] * 3), ("status", ["fine"] * 3), ("schema_version", "1"), ("q", [[0.0] * 5] * 3),
     ("tcp", [[0.0] * 6] * 3)],
)  # fmt: skip
def test_trajectory_rejects_bad_values(key: str, value: object) -> None:
    d = _traj()
    d[key] = value
    with pytest.raises(ValidationError):
        Trajectory.model_validate(d)


def test_trajectory_rejects_unknown_field_and_nan() -> None:
    d = _traj()
    d["extra"] = 1
    with pytest.raises(ValidationError):
        Trajectory.model_validate(d)
    d = _traj()
    d["psi_rad"][0] = float("nan")
    with pytest.raises(ValidationError):
        Trajectory.model_validate(d)


def test_matrices_must_be_4x4() -> None:
    scene = json.loads((FIXTURE / "scene.json").read_text())
    bad = copy.deepcopy(scene)
    bad["workstation"]["T_WB"] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    with pytest.raises(ValidationError):
        Scene.model_validate(bad)
    bad = copy.deepcopy(scene)
    bad["tool"]["T_FT"][3] = [0, 0, 1]
    with pytest.raises(ValidationError):
        Scene.model_validate(bad)


def test_toolpath_pose_length_and_closed_ring() -> None:
    tp = json.loads((FIXTURE / "parts/P01/toolpath.json").read_text())
    bad = copy.deepcopy(tp)
    bad["rings"][0]["waypoints"][0] = [0, 0, 0, 1, 0, 0]
    with pytest.raises(ValidationError):
        Toolpath.model_validate(bad)
    bad = copy.deepcopy(tp)
    bad["rings"][0]["waypoints"][-1][0] += 5
    with pytest.raises(ValidationError, match="Ring"):
        Toolpath.model_validate(bad)
    bad = copy.deepcopy(tp)
    bad["rings"][0]["kind"] = "middle"
    with pytest.raises(ValidationError):
        Toolpath.model_validate(bad)


def test_part_status_literal() -> None:
    part = json.loads((FIXTURE / "parts/P01/part.json").read_text())
    part["status"] = "feasible"
    with pytest.raises(ValidationError):
        PartArtifact.model_validate(part)


# ----------------------------------------------------------------- Szenarien und API


@pytest.mark.parametrize("path", sorted((REPO / "spec" / "scenarios").glob("*.json")), ids=lambda p: p.stem)
def test_scenarios_load(path: Path) -> None:
    sc = load_json(path, Scenario)
    assert sc.id == path.stem
    assert sc.planner_mode in ("collision_aware", "ignore_collision")


def test_scenario_details() -> None:
    s1 = load_json(REPO / "spec/scenarios/S1_modul_referenz.json", Scenario)
    assert s1.source.kind == "box" and s1.source.size_mm == [600, 200, 400]
    s3 = load_json(REPO / "spec/scenarios/S3_kollision_negativ.json", Scenario)
    assert s3.placement_override is not None and s3.placement_override.y_mm == 330
    s2 = load_json(REPO / "spec/scenarios/S2_beispiel_ifc_modul.json", Scenario)
    assert s2.source.kind == "ifc" and s2.source.walls == "all"


def test_api_models() -> None:
    state = JobState(state="running", progress=0.5, stage="plan", message=None, run_id=None)
    assert state.model_dump()["progress"] == 0.5
    with pytest.raises(ValidationError):
        JobState(state="running", progress=1.5, stage=None, message=None, run_id=None)
    with pytest.raises(ValidationError):
        JobState(state="paused", progress=0.0, stage=None, message=None, run_id=None)
    assert JobCreate(wall_id="w1").planner_mode == "collision_aware"
    walls = load_json(FIXTURE / "summary.json", Summary).walls
    info = ProjectInfo(project_id="p1", name="demo", walls=walls)
    assert ProjectInfo.model_validate_json(info.model_dump_json()) == info


# ----------------------------------------------------------------- Aktualität


def test_export_is_deterministic(tmp_path: Path) -> None:
    a = export_schemas(tmp_path / "a")
    b = export_schemas(tmp_path / "b")
    assert [p.name for p in a] == [f"{m.__name__}.schema.json" for m in TOP_LEVEL_MODELS]
    for pa, pb in zip(a, b, strict=True):
        assert pa.read_bytes() == pb.read_bytes()
        assert b"\r" not in pa.read_bytes() and pa.read_bytes().endswith(b"\n")


def test_committed_schemas_are_current(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    fresh = {p.name: p.read_bytes() for p in tmp_path.glob("*.schema.json")}
    committed = {p.name: p.read_bytes() for p in SCHEMAS.glob("*.schema.json")}
    assert set(fresh) == set(committed), f"Schema-Dateien weichen ab. Neu erzeugen mit: {REGEN}"
    stale = sorted(n for n in fresh if fresh[n] != committed[n])
    assert not stale, f"Veraltete Schemas {stale}. Neu erzeugen mit: {REGEN}"


def test_every_schema_has_typescript() -> None:
    for schema in sorted(SCHEMAS.glob("*.schema.json")):
        name = schema.name.removesuffix(".schema.json")
        ts = CONTRACTS_TS / f"{name}.ts"
        assert ts.is_file(), f"{ts.name} fehlt. Neu erzeugen mit: {REGEN}"
        assert f"export interface {name} " in ts.read_text(encoding="utf-8"), f"{ts.name}: {REGEN}"
        top = json.loads(schema.read_text())
        for prop in top.get("properties", {}):
            assert prop in ts.read_text(encoding="utf-8"), f"{ts.name}: Feld {prop} fehlt. {REGEN}"
    index = (CONTRACTS_TS / "index.ts").read_text(encoding="utf-8")
    for m in TOP_LEVEL_MODELS:
        assert f"'./{m.__name__}'" in index, f"index.ts exportiert {m.__name__} nicht"
