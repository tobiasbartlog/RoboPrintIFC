"""API-Tests (SPEC §8) mit TestClient; Jobs laufen in echten Spawn-Prozessen mit Fake-Pipeline."""

import io
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from roboprint.api import create_app

ROOT = Path(__file__).resolve().parents[2]
FAKE = "fake_pipeline"
EXAMPLE = {"example_path": "examples/Building-Architecture.ifc"}


def fake_walls(path):
    return [
        SimpleNamespace(wall_id="W1", name="Wand 1", length_mm=3000.0, thickness_mm=200.0, height_mm=2500.0),
        SimpleNamespace(
            wall_id="W2", name="Duenne Wand", length_mm=1000.0, thickness_mm=24.0, height_mm=2500.0
        ),
    ]


def make_client(tmp_path, monkeypatch, pipeline=f"{FAKE}:fast"):
    from roboprint import ifc

    monkeypatch.setattr(ifc, "read_walls", fake_walls)
    monkeypatch.setattr(ifc, "eligibility", lambda w, p: (w.thickness_mm >= 100, "zu duenn"), raising=False)
    return create_app(tmp_path / "runs", tmp_path / "projects", ROOT, pipeline=pipeline)


@pytest.fixture
def client(tmp_path, monkeypatch):
    with TestClient(make_client(tmp_path, monkeypatch)) as c:
        yield c


def make_project(client):
    r = client.post("/api/projects", json=EXAMPLE)
    assert r.status_code == 200, r.text
    return r.json()["project_id"]


def wait_for(client, job_id, states, timeout=60):
    end = time.time() + timeout
    s = {}
    while time.time() < end:
        s = client.get(f"/api/jobs/{job_id}").json()
        if s["state"] in states:
            return s
        time.sleep(0.1)
    raise AssertionError(f"Timeout, letzter Stand {s}")


def test_health(client):
    j = client.get("/api/health").json()
    assert j["status"] == "ok" and "python" in j["versions"]


def test_examples(client):
    ex = client.get("/api/examples").json()
    paths = {e["path"] for e in ex}
    assert "examples/Building-Architecture.ifc" in paths
    assert "spec/scenarios/S1_modul_referenz.json" in paths
    assert {e["kind"] for e in ex} == {"ifc", "scenario"}


def test_project_from_example(client):
    pid = make_project(client)
    info = client.get(f"/api/projects/{pid}").json()
    assert [w["wall_id"] for w in info["walls"]] == ["W1", "W2"]
    assert info["walls"][0]["eligible"] is True
    assert info["walls"][1]["eligible"] is False and info["walls"][1]["reason"] == "zu duenn"
    assert client.get("/api/projects/nope").status_code == 404


def test_project_example_path_rejected(client):
    for bad in ("../README.md", "/etc/passwd", "README.md", "examples/../README.md"):
        assert client.post("/api/projects", json={"example_path": bad}).status_code == 404


def test_project_upload(client):
    r = client.post("/api/projects", files={"file": ("mein.ifc", b"ISO-10303-21;")})
    assert r.status_code == 200
    info = client.get(f"/api/projects/{r.json()['project_id']}").json()
    assert info["name"] == "mein" and len(info["walls"]) == 2
    bad = client.post("/api/projects", files={"file": ("x.txt", b"x")})
    assert bad.status_code == 422


def test_read_walls_stub_gives_501(tmp_path):
    from roboprint import ifc

    try:
        ifc.read_walls(Path("nicht_vorhanden.ifc"))
        pytest.skip("read_walls ist bereits implementiert")
    except NotImplementedError:
        pass
    except Exception:
        pytest.skip("read_walls ist bereits implementiert")
    with TestClient(create_app(tmp_path / "runs", tmp_path / "p", ROOT)) as c:
        assert c.post("/api/projects", json=EXAMPLE).status_code == 501


def test_job_lifecycle(client):
    pid = make_project(client)
    r = client.post(f"/api/projects/{pid}/jobs", json={"wall_id": "W1", "params": {"h": 8.0}})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    s = wait_for(client, job_id, {"done", "failed"})
    assert s["state"] == "done" and s["progress"] == 1.0 and s["run_id"]
    scen = json.loads((client.app.state.jobs.job_dir(job_id) / "scenario.json").read_text())
    assert scen["source"]["kind"] == "ifc" and scen["source"]["walls"] == ["W1"]
    assert scen["params"] == {"h": 8.0}
    assert client.get(f"/api/runs/{s['run_id']}/hello.txt").text == "hi"
    summary = client.get(f"/api/runs/{s['run_id']}/summary.json").json()
    assert summary["scenario"].startswith("job_")
    assert client.post("/api/projects/nope/jobs", json={"wall_id": "W1"}).status_code == 404
    assert client.post(f"/api/projects/{pid}/jobs", json={"wall_id": "X"}).status_code == 404
    assert client.get("/api/jobs/unbekannt").status_code == 404


def test_job_rejects_unknown_param(client):
    pid = make_project(client)
    r = client.post(f"/api/projects/{pid}/jobs", json={"wall_id": "W1", "params": {"pump_voltage_v": 5.0}})
    assert r.status_code == 422 and "pump_voltage_v" in r.text


def test_web_default_params_accepted(client):
    """Der Viewer schickt bei jedem Job alle Parameter aus `web/src/state/params.ts` mit."""
    src = (ROOT / "web" / "src" / "state" / "params.ts").read_text(encoding="utf-8")
    params: dict = {k: float(v) for k, v in re.findall(r"key: '(\w+)'[^}]*?default: ([\d.]+)", src)}
    params |= dict(re.findall(r"^\s+(tcp_name|dialect): '([^']*)'", src, flags=re.M))
    assert len(params) == src.count("key: '") + 2
    pid = make_project(client)
    r = client.post(f"/api/projects/{pid}/jobs", json={"wall_id": "W1", "params": params})
    assert r.status_code == 202, r.text


@pytest.mark.parametrize("scenario", ["S1_modul_referenz", "S3_kollision_negativ"])
def test_project_from_box_scenario(client, scenario):
    """Quader-Szenarien öffnen sich wie ein Modell mit einer Wand `box`; der Job übernimmt das Szenario."""
    import trimesh

    path = f"spec/scenarios/{scenario}.json"
    r = client.post("/api/projects", json={"example_path": path})
    assert r.status_code == 200, r.text
    pid = r.json()["project_id"]
    (w,) = client.get(f"/api/projects/{pid}").json()["walls"]
    assert w["wall_id"] == "box" and w["eligible"] is True
    assert (w["length_mm"], w["thickness_mm"], w["height_mm"]) == (600, 200, 400)
    stl = client.get(f"/api/projects/{pid}/walls/box.stl")
    assert stl.status_code == 200
    mesh = trimesh.load(io.BytesIO(stl.content), file_type="stl")
    assert abs(mesh.bounds - [[0, 0, 0], [600, 200, 400]]).max() < 1e-6
    r = client.post(f"/api/projects/{pid}/jobs", json={"wall_id": "box", "params": {"h": 8.0}})
    job_id = r.json()["job_id"]
    assert wait_for(client, job_id, {"done", "failed"})["state"] == "done"
    scen = json.loads((client.app.state.jobs.job_dir(job_id) / "scenario.json").read_text())
    orig = json.loads((ROOT / path).read_text(encoding="utf-8"))
    assert scen["source"] == orig["source"] and scen["params"] == {"h": 8.0}
    assert scen["planner_mode"] == orig["planner_mode"]
    assert scen.get("placement_override") == orig.get("placement_override")


def test_status_file_concurrent_read_write(tmp_path):
    """Die API liest `status.json`, während der Jobprozess sie ersetzt (unter Windows ein Sperrkonflikt)."""
    import threading

    from roboprint.api_jobs import read_status, write_status

    write_status(tmp_path, {"n": 0})
    stop = threading.Event()
    errors: list[BaseException] = []

    def reader():
        while not stop.is_set():
            try:
                assert read_status(tmp_path) is not None
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

    t = threading.Thread(target=reader)
    t.start()
    try:
        for i in range(2000):
            write_status(tmp_path, {"n": i})
    finally:
        stop.set()
        t.join()
    assert not errors, errors[:3]
    assert read_status(tmp_path) == {"n": 1999}


def test_job_progress_and_cancel(tmp_path, monkeypatch):
    app = make_client(tmp_path, monkeypatch, f"{FAKE}:slow")
    with TestClient(app) as c:
        pid = make_project(c)
        job_id = c.post(f"/api/projects/{pid}/jobs", json={"wall_id": "W1"}).json()["job_id"]
        end = time.time() + 60
        s = {}
        while time.time() < end:
            s = c.get(f"/api/jobs/{job_id}").json()
            if s["stage"] == "plan":
                break
            time.sleep(0.1)
        assert s["state"] == "running" and s["progress"] == pytest.approx(0.3)
        assert s["message"] == "rechne"
        assert c.delete(f"/api/jobs/{job_id}").json()["state"] == "cancelled"
        assert c.get(f"/api/jobs/{job_id}").json()["state"] == "cancelled"


def test_job_failure(tmp_path, monkeypatch):
    app = make_client(tmp_path, monkeypatch, f"{FAKE}:broken")
    with TestClient(app) as c:
        pid = make_project(c)
        job_id = c.post(f"/api/projects/{pid}/jobs", json={"wall_id": "W1"}).json()["job_id"]
        s = wait_for(c, job_id, {"failed", "done"})
        assert s["state"] == "failed" and "kaputt" in s["message"]


@pytest.fixture
def fixture_client(tmp_path):
    app = create_app(ROOT / "web" / "fixtures", tmp_path / "projects", ROOT)
    with TestClient(app) as c:
        yield c


def test_run_artifacts(fixture_client):
    c = fixture_client
    assert c.get("/api/runs").json() == ["run_demo"]
    s = c.get("/api/runs/run_demo/summary.json")
    assert s.status_code == 200 and s.json()["schema_version"] == "2"
    assert c.get("/api/runs/run_demo/scene.json").status_code == 200
    stl = c.get("/api/runs/run_demo/parts/P01/part.stl")
    assert stl.status_code == 200 and len(stl.content) > 80
    drl = c.get("/api/runs/run_demo/parts/P01/program.v2.drl")
    assert drl.status_code == 200 and drl.headers["content-type"].startswith("text/plain")
    assert c.get("/api/runs/run_demo/parts/P01/trajectory.json").status_code == 200
    assert c.get("/api/runs/run_demo/nichts.json").status_code == 404
    assert c.get("/api/runs/unbekannt/summary.json").status_code == 404


def test_nested_run_id(tmp_path):
    run = tmp_path / "runs" / "verify" / "S1"
    run.mkdir(parents=True)
    (run / "summary.json").write_text("{}")
    (run / "a.txt").write_text("x")
    with TestClient(create_app(tmp_path / "runs", tmp_path / "p", ROOT)) as c:
        assert c.get("/api/runs/verify/S1/a.txt").text == "x"
        assert c.get("/api/runs").json() == ["verify/S1"]


@pytest.mark.parametrize(
    "path",
    [
        "run_demo/../../../README.md",
        "run_demo/%2e%2e/%2e%2e/README.md",
        "run_demo/..%2f..%2fREADME.md",
        "%2e%2e/README.md",
        "run_demo//etc/passwd",
    ],
)
def test_traversal_rejected_runs(fixture_client, path):
    assert fixture_client.get(f"/api/runs/{path}").status_code == 404


def test_traversal_symlink(tmp_path):
    run = tmp_path / "runs" / "r"
    run.mkdir(parents=True)
    (run / "summary.json").write_text("{}")
    secret = tmp_path / "secret.txt"
    secret.write_text("geheim")
    (run / "link.txt").symlink_to(secret)
    with TestClient(create_app(tmp_path / "runs", tmp_path / "p", ROOT)) as c:
        assert c.get("/api/runs/r/link.txt").status_code == 404


def test_assets(fixture_client):
    c = fixture_client
    urdf = c.get("/api/assets/robot.urdf")
    assert urdf.status_code == 200
    assert "package://" not in urdf.text
    mesh = "/api/assets/third_party/doosan_m1013/meshes/m1013_white/MF1013_0_0.dae"
    assert mesh in urdf.text
    same = c.get("/api/assets/third_party/doosan_m1013/urdf/m1013.white.urdf")
    assert same.text == urdf.text
    assert c.get(mesh).status_code == 200
    assert c.get("/api/assets/tools/30gut.stl").status_code == 200
    assert c.get("/api/assets/workstations/doosantisch.stl").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "core/pyproject.toml",
        "tools/../README.md",
        "tools/%2e%2e/README.md",
        "robots/doosan_m1013.json",
        "third_party/doosan_m1013/../../README.md",
        "tools",
    ],
)
def test_assets_whitelist(fixture_client, path):
    assert fixture_client.get(f"/api/assets/{path}").status_code == 404


def test_building_view_real_ifc(tmp_path):
    """Hausansicht: Wände in Gebäudelage und Kontext (Boden, Dach) teilen einen Ursprung nahe 0."""
    import trimesh

    with TestClient(create_app(tmp_path / "runs", tmp_path / "projects", ROOT)) as c:
        pid = c.post("/api/projects", json=EXAMPLE).json()["project_id"]
        info = c.get(f"/api/projects/{pid}").json()
        size = info["building_mm"]
        assert size is not None and 5000 < size[0] < 7000 and 5000 < size[1] < 7000
        boxes = []
        for w in info["walls"]:
            r = c.get(f"/api/projects/{pid}/walls/{w['wall_id']}.stl", params={"frame": "building"})
            assert r.status_code == 200
            boxes.append(trimesh.load(io.BytesIO(r.content), file_type="stl").bounds)
        lo = np.min([b[0] for b in boxes], axis=0)
        assert np.allclose(lo, 0.0, atol=1e-3)  # Ursprung = min-Ecke der Wände
        # Die Wände stehen nebeneinander im Haus, nicht übereinander im Ursprung
        assert len({round(b[0][0]) for b in boxes}) == len(boxes)
        ctx = c.get(f"/api/projects/{pid}/context.stl")
        assert ctx.status_code == 200
        cb = trimesh.load(io.BytesIO(ctx.content), file_type="stl").bounds
        assert cb[1][2] > max(b[1][2] for b in boxes)  # Dach über den Wänden
        assert np.all(cb[1] <= np.asarray(size) + 1e-3)
        wid = info["walls"][0]["wall_id"]
        assert c.get(f"/api/projects/{pid}/walls/{wid}.stl", params={"frame": "G"}).status_code == 422


def test_building_view_absent_for_box(client):
    r = client.post("/api/projects", json={"example_path": "spec/scenarios/S1_modul_referenz.json"})
    pid = r.json()["project_id"]
    assert client.get(f"/api/projects/{pid}").json()["building_mm"] is None
    assert client.get(f"/api/projects/{pid}/context.stl").status_code == 404
    assert client.get(f"/api/projects/{pid}/walls/box.stl", params={"frame": "building"}).status_code == 404


def test_wall_mesh_stl_real_ifc(tmp_path):
    """Wandmesh im Frame L (mm): STL passt zu den Maßen der Wandliste; Fehlerpfade geben 404."""
    import trimesh

    app = create_app(tmp_path / "runs", tmp_path / "projects", ROOT)
    with TestClient(app) as c:
        pid = c.post("/api/projects", json=EXAMPLE).json()["project_id"]
        walls = c.get(f"/api/projects/{pid}").json()["walls"]
        w = walls[0]
        r = c.get(f"/api/projects/{pid}/walls/{w['wall_id']}.stl")
        assert r.status_code == 200 and r.headers["content-type"].startswith("model/stl")
        mesh = trimesh.load(io.BytesIO(r.content), file_type="stl")
        ext = mesh.bounds[1] - mesh.bounds[0]
        assert abs(ext[0] - w["length_mm"]) < 1.0 and abs(ext[2] - w["height_mm"]) < 1.0
        assert c.get(f"/api/projects/{pid}/walls/nope.stl").status_code == 404
        assert c.get(f"/api/projects/{pid}/walls/{w['wall_id']}").status_code == 404
        assert c.get("/api/projects/nope/walls/x.stl").status_code == 404
        assert "dünn" in "".join(x["reason"] or "" for x in walls)
