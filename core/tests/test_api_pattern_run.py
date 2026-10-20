"""Musterwahl im Ablauf (M4): Durchreichen bis in den Lauf, Kennzahlen und Schichtvorschau eines Teils.

Die Kennzahlen werden gegen die Geometrie des Slicers geprüft (unabhängig vom Viewer): Länge je
Segmentart aus den Ringen, Stränge aus `link_next`, Schichtwechsel aus den Endpunkten."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from roboprint import pattern_report
from roboprint.contracts import PartPatternLayer, PartPatternReport, dump_json
from roboprint.geometry import make_box
from roboprint.slicer import SliceParams, slice_part, to_toolpath
from test_api import EXAMPLE, make_client, make_project, wait_for

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path, monkeypatch):
    with TestClient(make_client(tmp_path, monkeypatch)) as c:
        yield c


def _toolpath(**kw):
    box = make_box([600.0, 200.0, 60.0], origin=[-300.0, -100.0, 0.0])
    T = np.eye(4)
    T[:3, 3] = [1000.0, 500.0, 20.0]  # Teil P in W verschoben: die Vorschau muss nach P zurückrechnen
    return to_toolpath(slice_part(box, SliceParams(**kw)), T, "box_01"), T


def _write_run(run: Path, tp, T) -> None:
    pdir = run / "parts" / "box_01"
    pdir.mkdir(parents=True)
    dump_json(tp, pdir / "toolpath.json")
    (pdir / "part.json").write_text(json.dumps({"T_WP": T.tolist()}), encoding="utf-8")
    (run / "summary.json").write_text(json.dumps({"params": {"v_print_mm_s": 100.0}}), encoding="utf-8")


def test_metrics_match_slicer_geometry():
    tp, _ = _toolpath(infill_pattern="sinus", layer_order="alternate")
    rep = PartPatternReport.model_validate(pattern_report.metrics(tp.model_dump(mode="json"), 100.0))
    assert rep.has_pattern and rep.infill == "sinus" and rep.layer_order == "alternate"
    assert rep.n_layers == 6 and rep.n_rings == len(tp.rings)
    total = sum(
        float(np.linalg.norm(np.diff(np.asarray(r.waypoints)[:, :2], axis=0), axis=1).sum()) for r in tp.rings
    )
    assert rep.total_length_mm == pytest.approx(total, abs=0.01)
    assert sum(k.length_mm for k in rep.kinds) == pytest.approx(total, abs=0.01)
    assert sum(k.share for k in rep.kinds) == pytest.approx(1.0, abs=1e-4)
    assert {k.kind for k in rep.kinds} >= {"infill"}
    assert rep.print_time_s == pytest.approx(total / 100.0, abs=0.01)
    # ein Strang, senkrechte Schichtwechsel (M1, M4)
    assert rep.n_strands == 1 and rep.max_strands_per_layer == 1
    assert (
        rep.layer_changes.vertical == 5 and rep.layer_changes.diagonal == 0 and rep.layer_changes.travel == 0
    )
    assert rep.layer_changes.max_offset_mm is not None and rep.layer_changes.max_offset_mm <= 0.5


def test_metrics_without_pattern_have_no_pattern_label():
    tp, _ = _toolpath()
    rep = PartPatternReport.model_validate(pattern_report.metrics(tp.model_dump(mode="json")))
    assert not rep.has_pattern and rep.infill is None and rep.layer_order is None
    assert {k.kind for k in rep.kinds} <= {"outer", "inner", "hole"}


def test_layer_view_is_in_part_frame_with_neighbor():
    tp, T = _toolpath(infill_pattern="sinus", layer_order="alternate")
    view = PartPatternLayer.model_validate(
        pattern_report.layer_view(tp.model_dump(mode="json"), {"T_WP": T.tolist()}, 2)
    )
    assert view.n_layers == 6 and view.neighbor_relation == "next" and view.neighbor is not None
    assert view.neighbor.layer == 3
    (lo, hi) = view.bounds
    # Rechteck 600 x 200 um den Ursprung von P (Raupenmitte 15 mm innen), unabhängig von der Verschiebung in W
    assert lo[0] == pytest.approx(-285.0, abs=1.0) and hi[0] == pytest.approx(285.0, abs=1.0)
    assert lo[1] == pytest.approx(-85.0, abs=1.0) and hi[1] == pytest.approx(85.0, abs=1.0)
    assert view.z_mm == pytest.approx(30.0, abs=0.01)
    assert view.path.start == view.path.segments[0].points[0]
    # alternate: Ende der Schicht 2 liegt über dem Anfang der Schicht 3
    assert np.allclose(view.path.end, view.neighbor.start, atol=0.5)
    last = pattern_report.layer_view(tp.model_dump(mode="json"), {"T_WP": T.tolist()}, 5)
    assert last["neighbor_relation"] == "previous" and last["neighbor"]["layer"] == 4
    with pytest.raises(IndexError):
        pattern_report.layer_view(tp.model_dump(mode="json"), {"T_WP": T.tolist()}, 6)


def test_report_endpoints(client, tmp_path):
    tp, T = _toolpath(infill_pattern="zickzack", layer_order="alternate")
    _write_run(tmp_path / "runs" / "muster" / "r1", tp, T)
    q = {"run_id": "muster/r1", "part_id": "box_01"}
    m = client.get("/api/pattern-report/metrics", params=q)
    assert m.status_code == 200, m.text
    assert PartPatternReport.model_validate(m.json()).infill == "zickzack"
    layer = client.get("/api/pattern-report/layer", params={**q, "layer": 1})
    assert layer.status_code == 200 and layer.json()["layer"] == 1
    assert client.get("/api/pattern-report/layer", params={**q, "layer": 99}).status_code == 404
    assert client.get("/api/pattern-report/metrics", params={**q, "part_id": "nope"}).status_code == 404
    assert client.get("/api/pattern-report/metrics", params={**q, "part_id": "../x"}).status_code == 404
    assert (
        client.get("/api/pattern-report/metrics", params={**q, "run_id": "gibt/es/nicht"}).status_code == 404
    )


def _scenario_of(client, job_id) -> dict:
    return json.loads((client.app.state.jobs.job_dir(job_id) / "scenario.json").read_text())


def test_job_passes_pattern_params_into_scenario(client):
    pid = make_project(client)
    params = {
        "layer_order": "alternate",
        "infill_pattern": "sinus",
        "outfill_pattern": "none",
        "pattern_params": {"wavelength_mm": 200.0},
    }
    r = client.post(f"/api/projects/{pid}/jobs", json={"wall_id": "W1", "params": params})
    assert r.status_code == 202, r.text
    scen = _scenario_of(client, r.json()["job_id"])
    assert scen["params"] == params
    wait_for(client, r.json()["job_id"], {"done", "failed"})


@pytest.mark.parametrize("preset_id", ["fugenwand", "sinus"])
def test_job_resolves_preset_id_to_a_file(client, preset_id):
    pid = make_project(client)
    r = client.post(
        f"/api/projects/{pid}/jobs", json={"wall_id": "W1", "params": {"pattern_preset": preset_id}}
    )
    assert r.status_code == 202, r.text
    path = _scenario_of(client, r.json()["job_id"])["params"]["pattern_preset"]
    assert path.endswith(f"{preset_id}.json") and (ROOT / path).is_file()
    wait_for(client, r.json()["job_id"], {"done", "failed"})


def test_job_resolves_user_preset(client):
    body = {"name": "Mein Muster", "pattern": "sinus", "params": {"wavelength_mm": 220.0}, "outline": None}
    saved = client.post("/api/patterns/presets", json=body)
    assert saved.status_code == 201, saved.text
    pid = make_project(client)
    r = client.post(
        f"/api/projects/{pid}/jobs", json={"wall_id": "W1", "params": {"pattern_preset": saved.json()["id"]}}
    )
    assert r.status_code == 202, r.text
    path = Path(_scenario_of(client, r.json()["job_id"])["params"]["pattern_preset"])
    assert path.is_absolute() and path.is_file()
    wait_for(client, r.json()["job_id"], {"done", "failed"})


@pytest.mark.parametrize(
    "params",
    [
        {"pattern_preset": "gibt_es_nicht"},
        {"infill_pattern": "gibt_es_nicht"},
        {"layer_order": "kreuz"},
        {"infill_pattern": "sinus", "pattern_params": {"wavelength_mm": -5.0}},
    ],
)
def test_job_rejects_invalid_pattern_choice_with_422(client, params):
    pid = make_project(client)
    r = client.post(f"/api/projects/{pid}/jobs", json={"wall_id": "W1", "params": params})
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]


def test_default_job_keeps_empty_pattern_choice(client):
    """Standard bleibt wie heute: Der Viewer-Standard (kein Muster, layer_order leer) startet ohne Muster."""
    pid = make_project(client)
    params = {"layer_order": "", "infill_pattern": "none", "outfill_pattern": "none", "pattern_preset": ""}
    r = client.post(f"/api/projects/{pid}/jobs", json={"wall_id": "W1", "params": params})
    assert r.status_code == 202, r.text
    wait_for(client, r.json()["job_id"], {"done", "failed"})


def test_example_payload_unchanged(client):
    assert client.post("/api/projects", json=EXAMPLE).status_code == 200
