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


# Anzeigenamen und Kurzbeschreibungen der mitgelieferten Beispiele (die Kennungen bleiben die ids).
_EXAMPLE_TEXT: dict[str, tuple[str, str]] = {
    "Building-Architecture": ("Gebäudemodell (IFC)", "Mehrere Wände, darunter eine zu dünne"),
    "S1_modul_referenz": ("Referenzmodul 600 × 200 × 400 mm", "Quader am Doosantisch, Referenzfall"),
    "S2_beispiel_ifc_modul": ("Gebäudewände als Module", "Alle Wände des Gebäudemodells"),
    "S3_kollision_negativ": ("Kollisionsbeispiel", "Quader in der Roboterbasis, zeigt die Kollisionsanzeige"),
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


BEAD_WIDTH_MM = 30.0  # SPEC §10, Strangbreite w


def _eligibility(wall: Any, bead_width_mm: float = BEAD_WIDTH_MM) -> tuple[bool, str | None]:
    """Eignung nach SPEC §5.4/1 über `ifc.eligibility(wall, w)`."""
    from roboprint import ifc

    ok, reason = ifc.eligibility(wall, bead_width_mm)
    return bool(ok), reason


def _wall_entries(ifc_path: Path) -> list[WallEntry]:
    """Wände über `roboprint.ifc.read_walls` (lazy); Stub -> 501."""
    from roboprint import ifc

    try:
        walls = ifc.read_walls(ifc_path)
    except NotImplementedError as exc:
        raise _err(501, "IFC-Import ist noch nicht implementiert") from exc
    except Exception as exc:  # defektes IFC
        raise _err(422, f"IFC konnte nicht gelesen werden: {exc}") from exc
    entries: list[WallEntry] = []
    for i, w in enumerate(walls):
        length = float(_wall_attr(w, "length_mm", "length", default=0.0))
        thick = float(_wall_attr(w, "thickness_mm", "thickness", default=0.0))
        height = float(_wall_attr(w, "height_mm", "height", default=0.0))
        eligible, reason = _eligibility(w)
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


def _box_wall(source: dict[str, Any]) -> WallEntry:
    """Quader-Quelle eines Szenarios als einzige Wand `box`, wie in `pipeline._box_job`."""
    length, thick, height = (float(v) for v in source["size_mm"])
    return WallEntry(
        wall_id="box",
        name=f"Quader {length:.0f} × {thick:.0f} × {height:.0f} mm",
        eligible=True,
        reason=None,
        length_mm=length,
        thickness_mm=thick,
        height_mm=height,
        volume_mm3=length * thick * height,
    )


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
            name, desc = _EXAMPLE_TEXT.get(p.stem, (p.stem, None))
            rel = p.relative_to(root).as_posix()
            out.append(Example(id=p.stem, name=name, kind="ifc", path=rel, description=desc))
        for p in sorted((root / "spec" / "scenarios").glob("*.json")):
            try:
                desc = json.loads(p.read_text(encoding="utf-8")).get("beschreibung")
            except (OSError, ValueError):
                desc = None
            name, short = _EXAMPLE_TEXT.get(p.stem, (p.stem, None))
            out.append(
                Example(
                    id=p.stem,
                    name=name,
                    kind="scenario",
                    path=p.relative_to(root).as_posix(),
                    description=short or desc,
                )
            )
        return out

    # ------------------------------------------------------------------ projects
    def project_dir(project_id: str) -> Path:
        if not _ID.match(project_id) or not (projects_dir / project_id).is_dir():
            raise _err(404, "Projekt nicht gefunden")
        return projects_dir / project_id

    def store_project(name: str, walls: list[WallEntry], source: dict[str, str]) -> ProjectCreated:
        """`source` ist `{"ifc": <Pfad>}` oder `{"scenario": <Pfad relativ zu root>}` (Quader-Beispiel)."""
        pid = uuid.uuid4().hex[:12]
        pdir = projects_dir / pid
        pdir.mkdir(parents=True, exist_ok=True)
        info = ProjectInfo(project_id=pid, name=name, walls=walls)
        (pdir / "project.json").write_text(info.model_dump_json(indent=2), encoding="utf-8")
        (pdir / "source.json").write_text(json.dumps(source), encoding="utf-8")
        return ProjectCreated(project_id=pid)

    def project_source(pdir: Path) -> dict[str, str]:
        return json.loads((pdir / "source.json").read_text(encoding="utf-8"))

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
            return store_project(Path(fname or "upload.ifc").stem, _wall_entries(dest), {"ifc": str(dest)})
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
            if src.get("kind") == "box":
                name = _EXAMPLE_TEXT.get(target.stem, (target.stem, ""))[0]
                return store_project(name, [_box_wall(src)], {"scenario": rel_posix})
            if src.get("kind") != "ifc":
                raise _err(422, "Szenario hat weder IFC- noch Quader-Quelle")
            target = _safe_join(root, src["path"])
        if target.suffix.lower() != ".ifc" or not target.is_file():
            raise _err(404, "IFC-Datei nicht gefunden")
        return store_project(target.stem, _wall_entries(target), {"ifc": str(target)})

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> ProjectInfo:
        pdir = project_dir(project_id)
        return ProjectInfo.model_validate_json((pdir / "project.json").read_text(encoding="utf-8"))

    wall_stl_cache: dict[str, dict[str, bytes]] = {}

    @app.get("/api/projects/{project_id}/walls/{wall_file}")
    def get_wall_mesh(project_id: str, wall_file: str) -> Response:
        """Wandmesh als binäres STL im Frame L (mm), `wall_file` = `<wall_id>.stl`."""
        pdir = project_dir(project_id)
        wall_id = wall_file[:-4] if wall_file.lower().endswith(".stl") else ""
        info = ProjectInfo.model_validate_json((pdir / "project.json").read_text(encoding="utf-8"))
        if not wall_id or wall_id not in {w.wall_id for w in info.walls}:
            raise _err(404, "Wand nicht gefunden")
        source = project_source(pdir)
        if project_id not in wall_stl_cache and "scenario" in source:
            from roboprint.geometry import make_box

            # Quader im Frame L mit der min-Ecke im Ursprung, wie der Platzhalter im Viewer
            w = info.walls[0]
            mesh = make_box([w.length_mm, w.thickness_mm, w.height_mm])
            wall_stl_cache[project_id] = {w.wall_id: bytes(mesh.export(file_type="stl"))}
        if project_id not in wall_stl_cache:
            from roboprint import ifc

            ifc_path = source["ifc"]
            try:
                walls = ifc.read_walls(ifc_path)
            except Exception as exc:  # defektes IFC
                raise _err(422, f"IFC konnte nicht gelesen werden: {exc}") from exc
            wall_stl_cache[project_id] = {
                str(_wall_attr(w, "wall_id", "id", "guid", default="")): bytes(w.mesh.export(file_type="stl"))
                for w in walls
            }
        data = wall_stl_cache[project_id].get(wall_id)
        if data is None:
            raise _err(404, "Wandgeometrie nicht verfügbar")
        return Response(data, media_type="model/stl")

    # ------------------------------------------------------------------ jobs
    @app.post("/api/projects/{project_id}/jobs", status_code=202)
    def create_job(project_id: str, body: JobCreate) -> JobCreated:
        pdir = project_dir(project_id)
        info = ProjectInfo.model_validate_json((pdir / "project.json").read_text(encoding="utf-8"))
        if body.wall_id not in {w.wall_id for w in info.walls}:
            raise _err(404, "Wand nicht gefunden")
        from roboprint.planner.params import from_overrides

        try:  # sofort melden statt erst im Jobprozess scheitern
            from_overrides(dict(body.params))
        except ValueError as exc:
            raise _err(422, str(exc)) from exc
        source = project_source(pdir)
        job_id = uuid.uuid4().hex[:12]
        beschreibung = f"API-Job fuer Wand {body.wall_id} aus {info.name}"
        if "scenario" in source:
            # Beispielszenario: Quelle, Planermodus und Platzierung bleiben, sonst zeigt S3 keine Kollision.
            scenario = json.loads(_safe_join(root, source["scenario"]).read_text(encoding="utf-8"))
            scenario.update(
                id=f"job_{job_id}",
                beschreibung=beschreibung,
                params=dict(body.params),
                expect={},
                limits={"wall_time_s": 3600},
            )
        else:
            scenario = {
                "schema_version": "1",
                "id": f"job_{job_id}",
                "beschreibung": beschreibung,
                "mode": "modul",
                "source": {"kind": "ifc", "path": source["ifc"], "walls": [body.wall_id]},
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
