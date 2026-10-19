"""Export gleicher Teile (A6.3): Kopien sind bis auf part_id/Kopf identisch zur Einzelausgabe."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from roboprint import export, frames
from roboprint.assets import REPO_ROOT, load_tool, load_workstation
from roboprint.contracts import Scenario, Trajectory, dump_json, load_json
from roboprint.geometry import make_box
from roboprint.pipeline import PartJob, _scene
from roboprint.planner import from_overrides, plan_part
from roboprint.planner.kin import Kin

P = from_overrides({}, 10.0)
SCN = Scenario.model_validate(
    {
        "schema_version": "1",
        "id": "export_test",
        "beschreibung": "Test",
        "mode": "modul",
        "source": {"kind": "ifc", "path": "x.ifc", "walls": "all"},
        "decompose": True,
        "robot": "robots/doosan_m1013.json",
        "urdf": "third_party/doosan_m1013/urdf/m1013.white.urdf",
        "tool": "tools/30gut.json",
        "workstation": "workstations/doosantisch.json",
        "params": {},
        "planner_mode": "collision_aware",
        "expect": {"parts": "all_feasible"},
        "limits": {"wall_time_s": 180},
    }
)


@pytest.fixture(scope="module")
def plan():
    mesh = make_box([200, 100, 40], origin=[-100, -50, 0.0])
    pp = plan_part(mesh, "decompose", P, placement=frames.Placement(-500.0, -325.0, 0.0))
    return mesh, pp


def _ctx(out: Path, jobs: list[PartJob], plans: list) -> export.ExportContext:
    from roboprint.contracts import Provenance

    return export.ExportContext(
        out=out,
        part_jobs=jobs,
        plans=plans,
        kin=Kin(load_workstation(), load_tool()),
        params=P,
        scn=SCN,
        scene=_scene(P, REPO_ROOT),
        provenance=Provenance(git_commit="abc", created="2026-10-19T00:00:00+00:00", command="test"),
        run_params=dict(P.as_summary()),
    )


def _job(mesh, pid: str, wall: str, x: float) -> PartJob:
    T_LP = frames.T_LP([x, 0.0, 0.0], [x + 200.0, 100.0, 40.0])  # noqa: N806
    return PartJob(pid, wall, mesh, T_LP, None, None, (200.0, 100.0, 40.0), 200.0 * 100 * 40)


def test_kopien_gleich_wie_einzeln(plan, tmp_path: Path) -> None:
    mesh, pp = plan
    jobs = [_job(mesh, "w_r0_c0", "W1", 0.0), _job(mesh, "w_r0_c1", "W2", 200.0)]
    plans = [dataclasses.replace(pp, part_id=j.part_id) for j in jobs]
    assert export.group_parts(jobs, plans) == [[0, 1]]
    entries = export.export_parts(_ctx(tmp_path / "a", jobs, plans))
    assert [e.same_as for e in entries] == [None, "w_r0_c0"]
    assert entries[0].status == entries[1].status == "machbar"
    # Referenz: die Kopie allein (eigene Gruppe) ausgegeben
    single = export.export_parts(_ctx(tmp_path / "b", [jobs[1]], [plans[1]]))
    assert single[0].same_as is None
    a, b = tmp_path / "a" / "parts" / "w_r0_c1", tmp_path / "b" / "parts" / "w_r0_c1"
    for f in ("toolpath.json", "trajectory.json", "part.json", "program.v2.drl", "program.v3.drl"):
        assert (a / f).read_bytes() == (b / f).read_bytes(), f
    assert "Teil: w_r0_c1 (Wand W2)" in (a / "program.v2.drl").read_text(encoding="ascii")
    tr = load_json(a / "trajectory.json", Trajectory)
    assert tr.part_id == "w_r0_c1"
    # schnelle Serialisierung: gleicher Inhalt wie dump_json
    dump_json(tr, tmp_path / "ref.json")
    assert json.loads(export.to_json_bytes(tr)) == json.loads((tmp_path / "ref.json").read_text())


def test_verschiedene_plaene_eigene_gruppen(plan) -> None:
    mesh, pp = plan
    jobs = [_job(mesh, "a", "W", 0.0), _job(mesh, "b", "W", 200.0)]
    other = dataclasses.replace(pp, path=dataclasses.replace(pp.path))
    assert export.group_parts(jobs, [pp, other]) == [[0], [1]]
    jobs[1].expected_size_mm = (200.0, 100.0, 30.0)
    assert export.group_parts(jobs, [pp, pp]) == [[0], [1]]


def test_retag() -> None:
    data = b'{"schema_version":"2","part_id":"a_r0","x":["a_r0"]}\n'
    want = b'{"schema_version":"2","part_id":"b_r1","x":["a_r0"]}\n'
    assert export.retag_part_id(data, "a_r0", "b_r1") == want
    with pytest.raises(ValueError):
        export.retag_part_id(data, "zz", "b")
    text = "# Teil: a_r0 (Wand W1)\n#\nmovej(x)  # a_r0\n"
    out = export.retag_program(text, ("a_r0", "W1"), ("b_r1", "W2"))
    assert out == "# Teil: b_r1 (Wand W2)\n#\nmovej(x)  # a_r0\n"
