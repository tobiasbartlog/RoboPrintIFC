"""API-Tests (SPEC §8) mit TestClient; Jobs laufen in echten Spawn-Prozessen mit Fake-Pipeline."""

import json
import time
from pathlib import Path
from types import SimpleNamespace

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
