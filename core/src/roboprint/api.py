"""FastAPI: Projekte, Jobs mit Fortschritt und Abbruch, Artefakte ausliefern (SPEC §8).

run_id-Entscheidung: Die run_id ist der **relative Pfad des Laufordners unterhalb von `--runs`
mit `/`** (z. B. `verify/S1`, `jobs/<job_id>/run`, bei `--runs web/fixtures` einfach `run_demo`).
Ein Laufordner ist ein Ordner mit `summary.json`. `GET /api/runs/{run_id}/{pfad}` sucht das
kürzeste Präfix, das ein Laufordner ist; der Rest ist der Artefaktpfad.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

from .contracts.api import (
    Example,
    Health,
    JobCreate,
    JobCreated,
    JobState,
    ProjectCreate,
    ProjectCreated,
    ProjectInfo,
)
from .contracts.artifacts import WallEntry

ASSET_WHITELIST = ("third_party/doosan_m1013", "tools", "workstations")
ROBOT_URDF = "third_party/doosan_m1013/urdf/m1013.white.urdf"
PACKAGE_PREFIX = "package://dsr_description2/"
MESH_BASE = "/api/assets/third_party/doosan_m1013/"
_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_MEDIA = {
    ".stl": "model/stl",
    ".drl": "text/plain; charset=utf-8",
    ".dae": "model/vnd.collada+xml",
    ".json": "application/json",
}


def _err(status: int, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail=msg)


def _safe_join(base: Path, rel: str) -> Path:
    """Löst `rel` unterhalb von `base` auf; alles andere (.., absolut, Symlink-Flucht) ist 404."""
    if not rel or "\x00" in rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        raise _err(404, "Pfad nicht gefunden")
    base_r = base.resolve()
    target = (base_r / rel).resolve()
    if base_r != target and base_r not in target.parents:
        raise _err(404, "Pfad nicht gefunden")
    return target


def _file(path: Path) -> FileResponse:
    if not path.is_file():
        raise _err(404, "Datei nicht gefunden")
    return FileResponse(path, media_type=_MEDIA.get(path.suffix.lower()))


def _wall_attr(wall: Any, *names: str, default: Any = None) -> Any:
    for n in names:
        v = wall.get(n) if isinstance(wall, dict) else getattr(wall, n, None)
        if v is not None:
            return v
    return default


def _eligibility(elig: Any, wall: Any) -> tuple[bool, str | None]:
    """Eignung über `ifc.eligibility(wall, w)`; Ergebnis als (ok, grund), Objekt oder bool."""
    if elig is None:
        return True, None
    try:
        res = elig(wall, None)
    except (NotImplementedError, TypeError):
        return True, None
    if isinstance(res, tuple):
        return bool(res[0]), (res[1] if len(res) > 1 else None)
    if isinstance(res, bool):
        return res, None
    return bool(_wall_attr(res, "eligible", "ok", default=True)), _wall_attr(
        res, "reason", "grund", default=None
    )


def _wall_entries(ifc_path: Path) -> list[WallEntry]:
    """Wände über `roboprint.ifc.read_walls` (lazy); Stub -> 501."""
    from roboprint import ifc

    try:
        walls = ifc.read_walls(ifc_path)
    except NotImplementedError as exc:
        raise _err(501, "IFC-Import ist noch nicht implementiert") from exc
    except Exception as exc:  # defektes IFC
        raise _err(422, f"IFC konnte nicht gelesen werden: {exc}") from exc
    elig = getattr(ifc, "eligibility", None)
    entries: list[WallEntry] = []
    for i, w in enumerate(walls):
        length = float(_wall_attr(w, "length_mm", "length", default=0.0))
        thick = float(_wall_attr(w, "thickness_mm", "thickness", default=0.0))
        height = float(_wall_attr(w, "height_mm", "height", default=0.0))
        eligible, reason = _eligibility(elig, w)
        wid = str(_wall_attr(w, "wall_id", "id", "guid", default=f"W{i + 1:02d}"))
        entries.append(
            WallEntry(
                wall_id=wid,
                name=str(_wall_attr(w, "name", default=wid)),
                eligible=eligible,
                reason=None if eligible else (reason or "ungeeignet"),
                length_mm=length,
                thickness_mm=thick,
                height_mm=height,
                volume_mm3=float(_wall_attr(w, "volume_mm3", default=length * thick * height)),
            )
        )
    return entries


def _parse_multipart(content_type: str, body: bytes) -> dict[str, tuple[str | None, bytes]]:
    """Minimaler multipart/form-data-Parser (stdlib), liefert Name -> (Dateiname, Bytes)."""
    msg = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    out: dict[str, tuple[str | None, bytes]] = {}
    if not msg.is_multipart():
        raise _err(400, "multipart/form-data erwartet")
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name:
            out[str(name)] = (part.get_filename(), part.get_payload(decode=True) or b"")
    return out


def create_app(
    runs_dir: Path = Path("runs"),
    projects_dir: Path | None = None,
    root: Path | None = None,
    *,
    pipeline: str | None = None,
) -> FastAPI:
    """Baut die FastAPI-Anwendung.

    `root` ist die Repo-Wurzel (Beispiele, Szenarien, Assets), Default: Elternordner von
    `core/`. `projects_dir` Default: `<runs_dir>/projects`. Jobläufe landen in
    `<runs_dir>/jobs/<job_id>/run`. `pipeline` ("modul:funktion") ist für Tests austauschbar.
    """
    from roboprint import __version__
    from roboprint.api_jobs import DEFAULT_PIPELINE, JobManager

    root = (root or Path(__file__).resolve().parents[3]).resolve()
    runs_dir = Path(runs_dir)
    projects_dir = Path(projects_dir) if projects_dir is not None else runs_dir / "projects"
    jobs = JobManager(runs_dir / "jobs", root, pipeline or DEFAULT_PIPELINE)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        jobs.shutdown()

    app = FastAPI(title="RoboPrintIFC", version=__version__, lifespan=lifespan)
    app.state.runs_dir = runs_dir
    app.state.projects_dir = projects_dir
    app.state.root = root
    app.state.jobs = jobs

    # ------------------------------------------------------------------ health / examples
    @app.get("/api/health")
    def health() -> Health:
        versions = {"python": platform.python_version()}
        for mod in ("fastapi", "pydantic", "numpy"):
            try:
                versions[mod] = importlib.metadata.version(mod)
            except importlib.metadata.PackageNotFoundError:
                pass
        return Health(status="ok", version=__version__, versions=versions)

    @app.get("/api/examples")
    def examples() -> list[Example]:
        out: list[Example] = []
        for p in sorted((root / "examples").glob("*.ifc")):
            out.append(Example(id=p.stem, name=p.stem, kind="ifc", path=p.relative_to(root).as_posix()))
        for p in sorted((root / "spec" / "scenarios").glob("*.json")):
            try:
                desc = json.loads(p.read_text(encoding="utf-8")).get("beschreibung")
            except (OSError, ValueError):
                desc = None
            out.append(
                Example(
                    id=p.stem,
                    name=p.stem,
                    kind="scenario",
                    path=p.relative_to(root).as_posix(),
                    description=desc,
                )
            )
        return out

    # ------------------------------------------------------------------ projects
    def project_dir(project_id: str) -> Path:
        if not _ID.match(project_id) or not (projects_dir / project_id).is_dir():
            raise _err(404, "Projekt nicht gefunden")
        return projects_dir / project_id

    def store_project(name: str, ifc_path: Path) -> ProjectCreated:
        walls = _wall_entries(ifc_path)
        pid = uuid.uuid4().hex[:12]
        pdir = projects_dir / pid
        pdir.mkdir(parents=True, exist_ok=True)
        info = ProjectInfo(project_id=pid, name=name, walls=walls)
        (pdir / "project.json").write_text(info.model_dump_json(indent=2), encoding="utf-8")
        (pdir / "source.json").write_text(json.dumps({"ifc": str(ifc_path)}), encoding="utf-8")
        return ProjectCreated(project_id=pid)

    @app.post("/api/projects")
    async def create_project(request: Request) -> ProjectCreated:
        ctype = request.headers.get("content-type", "")
        if ctype.startswith("multipart/form-data"):
            fields = _parse_multipart(ctype, await request.body())
            fname, data = fields.get("file", (None, b""))
            if not data:
                raise _err(422, "Feld 'file' fehlt")
            if not (fname or "").lower().endswith(".ifc"):
                raise _err(422, "Nur .ifc-Dateien werden angenommen")
            pid_dir = projects_dir / "_uploads"
            pid_dir.mkdir(parents=True, exist_ok=True)
            dest = pid_dir / f"{uuid.uuid4().hex[:12]}.ifc"
            dest.write_bytes(data)
            return store_project(Path(fname or "upload.ifc").stem, dest)
        try:
            body = ProjectCreate.model_validate(await request.json())
        except Exception as exc:
            raise _err(422, f"Ungültige Anfrage: {exc}") from exc
        rel = body.example_path
        target = _safe_join(root, rel)
        rel_posix = target.relative_to(root).as_posix()
        if not (rel_posix.startswith(("examples/", "spec/scenarios/")) and target.is_file()):
            raise _err(404, "Beispiel nicht gefunden")
        if target.suffix == ".json":
            src = json.loads(target.read_text(encoding="utf-8")).get("source", {})
            if src.get("kind") != "ifc":
                raise _err(422, "Szenario hat keine IFC-Quelle")
            target = _safe_join(root, src["path"])
        if target.suffix.lower() != ".ifc" or not target.is_file():
            raise _err(404, "IFC-Datei nicht gefunden")
        return store_project(target.stem, target)

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> ProjectInfo:
        pdir = project_dir(project_id)
        return ProjectInfo.model_validate_json((pdir / "project.json").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ jobs
    @app.post("/api/projects/{project_id}/jobs", status_code=202)
    def create_job(project_id: str, body: JobCreate) -> JobCreated:
        pdir = project_dir(project_id)
        info = ProjectInfo.model_validate_json((pdir / "project.json").read_text(encoding="utf-8"))
        if body.wall_id not in {w.wall_id for w in info.walls}:
            raise _err(404, "Wand nicht gefunden")
        ifc_path = json.loads((pdir / "source.json").read_text(encoding="utf-8"))["ifc"]
        job_id = uuid.uuid4().hex[:12]
        scenario = {
            "schema_version": "1",
            "id": f"job_{job_id}",
            "beschreibung": f"API-Job fuer Wand {body.wall_id} aus {info.name}",
            "mode": "modul",
            "source": {"kind": "ifc", "path": ifc_path, "walls": [body.wall_id]},
            "decompose": True,
            "robot": "robots/doosan_m1013.json",
            "urdf": ROBOT_URDF,
            "tool": "tools/30gut.json",
            "workstation": "workstations/doosantisch.json",
            "params": dict(body.params),
            "planner_mode": body.planner_mode,
            "expect": {},
            "limits": {"wall_time_s": 3600},
        }
        jobs.start(job_id, scenario)
        return JobCreated(job_id=job_id)

    def job_or_404(job_id: str) -> None:
        if not _ID.match(job_id) or not jobs.exists(job_id):
            raise _err(404, "Job nicht gefunden")

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> JobState:
        job_or_404(job_id)
        return JobState.model_validate(jobs.state(job_id))

    @app.delete("/api/jobs/{job_id}")
    def cancel_job(job_id: str) -> JobState:
        job_or_404(job_id)
        return JobState.model_validate(jobs.cancel(job_id))

    # ------------------------------------------------------------------ runs
    def find_run(run_path: str) -> tuple[Path, str]:
        parts = [p for p in run_path.split("/") if p]
        if not parts or any(p in ("..", ".") or "\\" in p for p in parts):
            raise _err(404, "Pfad nicht gefunden")
        for i in range(1, len(parts) + 1):
            cand = _safe_join(runs_dir, "/".join(parts[:i]))
            if (cand / "summary.json").is_file():
                rest = "/".join(parts[i:])
                if not rest:
                    raise _err(404, "Artefaktpfad fehlt")
                return cand, rest
        raise _err(404, "Lauf nicht gefunden")

    @app.get("/api/runs")
    def list_runs() -> list[str]:
        base = runs_dir.resolve()
        if not base.is_dir():
            return []
        return sorted(
            p.parent.relative_to(base).as_posix()
            for p in base.rglob("summary.json")
            if "projects" not in p.relative_to(base).parts[:1]
        )

    @app.get("/api/runs/{run_path:path}")
    def get_run_file(run_path: str) -> FileResponse:
        run_dir, rest = find_run(run_path)
        return _file(_safe_join(run_dir, rest))

    # ------------------------------------------------------------------ assets
    @app.get("/api/assets/robot.urdf")
    def robot_urdf() -> Response:
        return urdf_response(root / ROBOT_URDF)

    def urdf_response(path: Path) -> Response:
        if not path.is_file():
            raise _err(404, "URDF nicht gefunden")
        text = path.read_text(encoding="utf-8").replace(PACKAGE_PREFIX, MESH_BASE)
        return Response(text, media_type="application/xml")

    @app.get("/api/assets/{asset_path:path}")
    def get_asset(asset_path: str) -> Response:
        target = _safe_join(root, asset_path)
        rel = target.relative_to(root).as_posix()
        if not any(rel == w or rel.startswith(w + "/") for w in ASSET_WHITELIST):
            raise _err(404, "Asset nicht gefunden")
        if target.suffix.lower() == ".urdf":
            return urdf_response(target)
        return _file(target)

    return app
