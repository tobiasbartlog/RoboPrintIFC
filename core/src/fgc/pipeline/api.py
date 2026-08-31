"""Lokale Core-API (ADR-014): dünner FastAPI-Wrapper um pipeline.actions.

Jeder Aufruf erzeugt einen regulären Laufordner (ADR-004) — keine
In-Memory-Abkürzung, keine eigene Fachlogik. Die API ist der dritte
Einstiegspunkt neben CLI und Wizard und ruft dieselben Aktionen.

Starten:
    python -m uvicorn fgc.pipeline.api:app --port 8765
    (oder via `fgc start`, das die API zusammen mit dem Viewer hochfährt)
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fgc.ifc_io import walls as ifc_walls

_LOG = logging.getLogger(__name__)

app = FastAPI(title="FGC Core API", version="0.1.0")


# --- Fehlerkontrakt des Seams actions↔api (Issue #118) ------------------------
#
# ADR-014 will einen dünnen Wrapper. Der Fehlerkontrakt der Aktionsaufrufe lag
# vorher ~20-fach kopiert in jedem Endpoint (`FileNotFoundError → 404`,
# `ValueError`/`OSError → 422`). Er lebt jetzt **einmal** in ``action_errors``.
#
# **Scoping (die offene Designfrage der Issue, konservativ gelöst):** kein
# app-weiter Exception-Handler auf rohe ``FileNotFoundError`` — der würde auch
# *interne* Dateifehler (heute ehrliche 500er) als 404 tarnen. Stattdessen ein
# **expliziter Kontextmanager um genau den Aktionsaufruf**: nur Ausnahmen, die
# aus dem umschlossenen ``with``-Block stammen (d. h. aus der Aktion), werden
# gemappt; Fehler im übrigen Endpoint-Code schlagen unverändert als 500 durch.
# ``FileNotFoundError`` ist eine ``OSError``-Unterklasse, deshalb wird sie
# **zuerst** gefangen — die Reihenfolge „Projekt fehlt (404) vor Eingabe
# ungültig (422)" bleibt erhalten.


@contextmanager
def action_errors() -> Iterator[None]:
    """Mappt die Fehler eines ``pipeline.actions``-Aufrufs auf HTTP (Issue #118).

    ``FileNotFoundError`` → 404 (Projekt/Definition fehlt), ``ValueError``/
    ``OSError`` → 422 (ungültige Eingabe/Schema). Der Detailtext ist der
    Klartext der Ausnahme (``str(exc)``) — byte-gleich zum bisherigen, je
    Endpoint kopierten Verhalten. Nur den Aktionsaufruf umschließen, damit
    interne Dateifehler an anderer Stelle ehrliche 500er bleiben (Scoping).
    """
    try:
        yield
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --- Gemeinsamer Projekt-Umschlag (ADR-016, Issue #118) -----------------------
#
# Der 5-Feld-Umschlag eines Projekts (slug/name/model_path/overview_run/
# print_jobs) lag als eigenes Response-Modell in jedem PUT-Setter. Er lebt jetzt
# einmal als ``ProjectResponse``; die Setter-Modelle erben davon und legen nur
# ihr **Befund**-Extra additiv daneben (``payload_ok``, ``compatible``, … —
# Befund, kein Gate, ADR-013). ``_project_envelope`` baut die fünf Felder aus dem
# Artefakt (die eine Stelle), ``_project_response`` daraus die reine Antwort.


class ProjectResponse(BaseModel):
    """Antwort auf POST /projects und GET /projects/{slug}.

    `overview_run` ist der Laufordner-Pfad (absolut); der Viewer baut daraus die
    `/@fs/`-URL und lädt die Modellübersicht (model.glb + candidates.json).

    Basis des Projekt-Umschlags (Issue #118): die PUT-Setter-Antworten erben
    diese fünf Felder und ergänzen ihren Befund.
    """

    slug: str
    name: str
    model_path: str
    overview_run: str
    print_jobs: list[dict]


def _project_envelope(slug: str, artifact: dict) -> dict:
    """Die fünf Umschlag-Felder aus einem Projekt-Artefakt (Issue #118)."""
    return {
        "slug": slug,
        "name": artifact["name"],
        "model_path": artifact["model_path"],
        "overview_run": artifact["overview_run"],
        "print_jobs": artifact["print_jobs"],
    }


def _project_response(slug: str, artifact: dict) -> ProjectResponse:
    return ProjectResponse(**_project_envelope(slug, artifact))

# Der Viewer (Vite) ruft die API cross-origin — ohne diese Header blockt der
# Browser jede Antwort (isApiAvailable/postSlice), obwohl die API läuft.
# Vite weicht ohne strictPort auf 5174+ aus, deshalb jede lokale Origin statt
# festgenageltem Port 5173 (Issue #49); die API bleibt ein Localhost-Dienst.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


class SliceRequest(BaseModel):
    """Parameter für POST /slice — Spiegel der fgc-slice-CLI-Flags.

    Overrides gegen die Prozessfenster-Karte folgen der bestehenden Regel:
    Karte ist Quelle, explizite Overrides (hier: gesetzt ≠ null) gewinnen.
    """

    model_path: str
    global_id: str
    layer_height_mm: float | None = None
    strand_width_mm: float | None = None
    n_shells: int | None = None
    with_context: bool = True


class SliceResponse(BaseModel):
    """Antwort auf POST /slice: Verweis auf den Laufordner + Toolpath-Kennzahlen."""

    run_dir: str
    n_layers: int
    n_targets: int
    n_print: int


def _api_slice_source(model_path: Path, global_id: str, params: object) -> str:
    """Provenienz-Quellstring für API-gesteuerte Läufe.

    Analog zu cli.slice_source, aber ohne argparse-Flag-Namen — die API hat
    kein argparse. Der String ist reproduzierbar und dokumentiert, dass der
    Lauf per API-Aufruf erzeugt wurde (ADR-014).
    """
    return (
        f"POST /slice model={model_path.name} wall={global_id} "
        f"layer_height_mm={params.layer_height_mm} "  # type: ignore[attr-defined]
        f"strand_width_mm={params.strand_width_mm} "  # type: ignore[attr-defined]
        f"n_shells={params.n_shells}"  # type: ignore[attr-defined]
    )


# --- Roboterkatalog (Issue #20): Roboterdefinitionen auflisten ----------------


class RobotInfoModel(BaseModel):
    """Kenndaten einer Roboterdefinition für den Viewer-Dropdown (Issue #20)."""

    name: str
    reach_mm: float
    max_print_height_mm: float
    max_print_length_mm: float
    workspace_provisional: bool
    payload_kg: float | None = None  # Traglast in kg (Issue #21, Payload-Check)


class RobotDefectModel(BaseModel):
    """Eine defekte Roboterdefinition, die GET /robots nicht laden konnte (Issue #73).

    Robuster Katalog: eine kaputte Datei verschwindet nicht mehr still, sondern
    wird sichtbar gemeldet (Log-Warnung *und* Eintrag in der Antwort), damit der
    Nutzer den Defekt sieht statt einen Roboter kommentarlos zu vermissen.
    """

    name: str  # Dateiname ohne Endung (der Roboter, der fehlen würde)
    error: str  # Klartext-Grund (Schema-Verstoß, kaputtes JSON, …)


class RobotListResponse(BaseModel):
    """Antwort auf GET /robots: alle verfügbaren Roboterdefinitionen.

    ``errors`` listet defekte Definitionen (Issue #73) — leer im Normalfall.
    """

    robots: list[RobotInfoModel]
    errors: list[RobotDefectModel] = []


@app.get("/robots", response_model=RobotListResponse)
def get_robots() -> RobotListResponse:
    """Listet alle Roboterdefinitionen aus robots/ (Issue #20).

    v1 enthält nur den Doosan M1013 (bewusste Beschränkung: keine KUKA-Definition
    ohne portierten Spherical-Wrist-Solver, ADR-002/§9.2); die Mechanik ist generisch.

    Eine defekte Definition (Schema-Verstoß, kaputtes JSON) wird nicht mehr still
    übersprungen (Issue #73): sie wird als Warnung geloggt *und* in ``errors``
    gemeldet — der Katalog bleibt trotzdem lieferbar (report-and-continue).
    """
    from fgc.domain.robot import RobotDef
    from fgc.paths import ROBOTS_DIR

    robots: list[RobotInfoModel] = []
    errors: list[RobotDefectModel] = []
    for path in sorted(ROBOTS_DIR.glob("*.json")):
        try:
            rd = RobotDef.load(path.stem)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning(
                "Roboterdefinition %r ist defekt und wird übersprungen: %s", path.name, exc
            )
            errors.append(RobotDefectModel(name=path.stem, error=str(exc)))
            continue
        robots.append(
            RobotInfoModel(
                name=rd.name,
                reach_mm=rd.reach_mm,
                max_print_height_mm=rd.max_print_height_mm,
                max_print_length_mm=rd.max_print_length_mm,
                workspace_provisional=rd.workspace_provisional,
                payload_kg=rd.payload_kg,
            )
        )
    return RobotListResponse(robots=robots, errors=errors)


# --- Endeffektor-Katalog (Issue #21): Endeffektor-Definitionen auflisten ------


class FrameModel(BaseModel):
    """Ein Frame (Lage) in mm/rad (ADR-006): Position + Einheitsquaternion [w,x,y,z]."""

    pos_mm: list[float]
    quat: list[float]


class ChannelDeclModel(BaseModel):
    """Kanaldeklaration eines Endeffektors für GET /tools (Issue #21)."""

    kind: str
    description: str = ""
    default_value: float = 0.0


class EnvelopeModel(BaseModel):
    """Huellkennzahl um die Flanschachse (ADR-026 Punkt 4, PRD #225, Issue #229)."""

    radius_mm: float
    length_mm: float


class ToolInfoModel(BaseModel):
    """Kenndaten einer Endeffektor-Definition für den Viewer-Dropdown (Issue #21).

    Für den Endeffektor-Konfigurator (Issue #28) zusätzlich ``mesh_path`` (absoluter
    Pfad der Mesh-Datei, den der Viewer als ``/@fs/``-URL lädt, um das Mesh im
    Replay am Flansch zu zeigen) und ``mesh_transform`` (Lage des Mesh relativ zum
    Flansch, am Flansch ausgerichtet).
    """

    name: str
    vendor: str = ""
    weight_kg: float
    cog_mm: list[float] | None = None
    mesh: str | None = None
    mesh_path: str | None = None
    mesh_transform: FrameModel | None = None
    #: TCP-Frame relativ Flansch (ADR-006) — der Bibliothek-Editor stellt beim
    #: „Bearbeiten" exakt diesen gespeicherten Zustand wieder her (Issue #56).
    tcp_frame: FrameModel
    channels: dict[str, ChannelDeclModel]
    #: Namen der Roboter, zu denen der Endeffektor passt (Kompatibilitaets-Tags,
    #: Issue #71). Leer = 'unbekannt', nicht 'inkompatibel'; noch keine Filterwirkung (#74).
    compatible_robots: list[str] = []
    #: Huellkennzahl um die Flanschachse (ADR-026 Punkt 4, PRD #225, Issue #229), beim
    #: Upload berechnet. Fehlt bei Tools ohne Mesh oder Altbestand vor #229 = 'unbekannt'.
    envelope_mm: EnvelopeModel | None = None


class ToolListResponse(BaseModel):
    """Antwort auf GET /tools: alle verfügbaren Endeffektor-Definitionen."""

    tools: list[ToolInfoModel]


class SetToolRequest(BaseModel):
    """Parameter für PUT /projects/{slug}/tool — Endeffektor-Wahl persistieren (Issue #21).

    ``tool`` ist der Name der Endeffektor-Definition aus ``tools/``;
    ``job_id`` ist der Druckjob, dessen ``tool``-Feld aktualisiert wird.
    Payload-Befund ist informativ — kein Gate (Befund, kein Gate).
    """

    tool: str
    job_id: str = "default"


class SetToolResponse(ProjectResponse):
    """Antwort auf PUT /projects/{slug}/tool: Projekt-Umschlag + Payload-Befund (Issue #21).

    Erbt den 5-Feld-Umschlag von ``ProjectResponse`` (Issue #118); der
    Payload-Befund ist additiv — Befund, kein Gate (ADR-013).
    """

    payload_ok: bool | None = None
    payload_margin_kg: float | None = None


def _tool_info_model(td: object, tools_dir: Path) -> ToolInfoModel:
    """Baut das ToolInfoModel aus einer ToolDef (Issue #21/#28) — inkl. Mesh-Pfad.

    ``mesh_path`` ist der absolute Pfad der Mesh-Datei (falls vorhanden und real
    abgelegt); der Viewer übersetzt ihn in eine ``/@fs/``-URL und lädt das Mesh
    fürs Replay am Flansch. Fehlt die Datei, bleibt ``mesh_path=None``.
    """
    mesh_path: str | None = None
    if td.mesh:  # type: ignore[attr-defined]
        candidate = tools_dir / td.mesh  # type: ignore[attr-defined]
        if candidate.exists():
            mesh_path = str(candidate.resolve())
    return ToolInfoModel(
        name=td.name,  # type: ignore[attr-defined]
        vendor=td.vendor,  # type: ignore[attr-defined]
        weight_kg=td.weight_kg,  # type: ignore[attr-defined]
        cog_mm=list(td.cog_mm) if td.cog_mm else None,  # type: ignore[attr-defined]
        mesh=td.mesh,  # type: ignore[attr-defined]
        mesh_path=mesh_path,
        mesh_transform=(
            FrameModel(**td.mesh_transform) if td.mesh_transform else None  # type: ignore[attr-defined]
        ),
        tcp_frame=FrameModel(**td.tcp_frame),  # type: ignore[attr-defined]
        channels={
            ch_name: ChannelDeclModel(
                kind=ch.kind,
                description=ch.description,
                default_value=ch.default_value,
            )
            for ch_name, ch in td.channels.items()  # type: ignore[attr-defined]
        },
        compatible_robots=list(td.compatible_robots),  # type: ignore[attr-defined]
        envelope_mm=(
            EnvelopeModel(**td.envelope_mm) if td.envelope_mm else None  # type: ignore[attr-defined]
        ),
    )


@app.get("/tools", response_model=ToolListResponse)
def get_tools() -> ToolListResponse:
    """Listet alle Endeffektor-Definitionen aus tools/ (Issue #21).

    v1 enthält die Zweikomponenten-Düse (``two_component_nozzle``) plus alle im
    Endeffektor-Konfigurator (Issue #28) angelegten Endeffektoren; die Mechanik
    ist generisch — neuer ``tools/``-Eintrag erscheint automatisch.
    """
    from fgc.domain.tool import ToolDef
    from fgc.paths import TOOLS_DIR

    tools: list[ToolInfoModel] = []
    for path in sorted(TOOLS_DIR.glob("*.json")):
        try:
            td = ToolDef.load(path.stem)
        except Exception:  # noqa: BLE001
            continue
        tools.append(_tool_info_model(td, TOOLS_DIR))
    return ToolListResponse(tools=tools)


class CreateToolRequest(BaseModel):
    """Parameter für POST /tools — Endeffektor aus einem Mesh-Upload anlegen (Issue #28).

    Der Endeffektor-Konfigurator (Bibliothek) lädt das Mesh (STL/OBJ/GLB) als
    base64 hoch (``mesh_base64`` + ``mesh_filename`` fürs Format) und reicht die am
    Flansch per Gizmo ausgerichtete Lage (``mesh_transform``), den gesetzten TCP
    (``tcp_frame``) und die Stammdaten (Name, Gewicht, Schwerpunkt, logische
    Kanäle) herein. Der Core validiert (Format/Größe/Ladbarkeit/Schema) und legt
    Mesh + Definition ab — Payload ist ein Befund, kein Gate (ADR-006/013).
    """

    name: str
    vendor: str = ""
    weight_kg: float
    cog_mm: list[float] | None = None
    channels: dict[str, ChannelDeclModel]
    tcp_frame: FrameModel
    mesh_transform: FrameModel | None = None
    compatible_robots: list[str] = []
    mesh_filename: str
    mesh_base64: str


@app.post("/tools", response_model=ToolInfoModel)
def post_tools(req: CreateToolRequest) -> ToolInfoModel:
    """Legt einen Endeffektor aus einem Mesh-Upload an (Issue #28).

    Dünner Aktions-Wrapper (ADR-014): dekodiert das base64-Mesh und ruft
    `create_tool_from_upload`, das Format/Größe/Ladbarkeit/Schema prüft und Mesh +
    ``<name>.json`` im Tools-Verzeichnis ablegt (Stammdaten, ADR-016). Die Antwort
    ist die frische Endeffektor-Kenndaten-Karte — der Viewer fügt sie ohne Neustart
    in den Katalog ein (Reiter Roboter + Konfigurator).

    422 bei ungültiger Eingabe (Name leer, Mesh-Format/-Größe, kaputtes Mesh,
    Schema-Verletzung, kaputtes base64).
    """
    import base64

    from fgc.paths import TOOLS_DIR
    from fgc.pipeline.actions import create_tool_from_upload

    try:
        mesh_bytes = base64.b64decode(req.mesh_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Mesh-Daten nicht dekodierbar: {exc}") from exc

    try:
        result = create_tool_from_upload(
            req.name,
            mesh_bytes,
            req.mesh_filename,
            req.weight_kg,
            {ch: decl.model_dump() for ch, decl in req.channels.items()},
            req.tcp_frame.model_dump(),
            vendor=req.vendor,
            cog_mm=req.cog_mm,
            mesh_transform=req.mesh_transform.model_dump() if req.mesh_transform else None,
            compatible_robots=req.compatible_robots,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _tool_info_model(result.tool, TOOLS_DIR)


class UpdateToolRequest(BaseModel):
    """Parameter für PUT /tools/{name} — Endeffektor bearbeiten (Issue #56).

    Analog zu ``CreateToolRequest``, aber das Mesh ist **optional**: sind
    ``mesh_base64``/``mesh_filename`` leer, bleiben die bestehende Mesh-Datei und
    ihr Dateiname erhalten — nur ``tcp_frame``, ``mesh_transform``, ``weight_kg``,
    ``vendor``, ``cog_mm`` und ``channels`` werden neu geschrieben. Der Name ist
    fix (Pfad-Parameter, Identität = Dateiname); ein ``name``-Feld im Body gäbe es
    nicht (kein Rename, Out of Scope).
    """

    vendor: str = ""
    weight_kg: float
    cog_mm: list[float] | None = None
    channels: dict[str, ChannelDeclModel]
    tcp_frame: FrameModel
    mesh_transform: FrameModel | None = None
    compatible_robots: list[str] = []
    mesh_filename: str = ""
    mesh_base64: str = ""


@app.put("/tools/{name}", response_model=ToolInfoModel)
def put_tools(name: str, req: UpdateToolRequest) -> ToolInfoModel:
    """Aktualisiert einen bestehenden Endeffektor (Bibliothek-Editor, Issue #56).

    Dünner Aktions-Wrapper (ADR-014): ruft `update_tool_from_upload`, das den
    Endeffektor über ``name`` (Identität = Dateiname, kein Rename) auffrischt. Ohne
    neues Mesh bleibt die bestehende Mesh-Datei erhalten; mit neuem Mesh wird sie
    (nach Validierung) ersetzt. Die Antwort ist die aktualisierte Kenndaten-Karte.

    404, wenn der Endeffektor nicht existiert. 422 bei ungültigem Mesh
    (Format/Größe/kaputt), Schema-Verletzung oder kaputtem base64.
    """
    import base64

    from fgc.paths import TOOLS_DIR
    from fgc.pipeline.actions import update_tool_from_upload

    mesh_bytes: bytes | None = None
    if req.mesh_base64:
        try:
            mesh_bytes = base64.b64decode(req.mesh_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=422, detail=f"Mesh-Daten nicht dekodierbar: {exc}"
            ) from exc

    with action_errors():
        result = update_tool_from_upload(
            name,
            req.weight_kg,
            {ch: decl.model_dump() for ch, decl in req.channels.items()},
            req.tcp_frame.model_dump(),
            mesh_bytes=mesh_bytes,
            mesh_filename=req.mesh_filename or None,
            vendor=req.vendor,
            cog_mm=req.cog_mm,
            mesh_transform=req.mesh_transform.model_dump() if req.mesh_transform else None,
            compatible_robots=req.compatible_robots,
        )

    return _tool_info_model(result.tool, TOOLS_DIR)


@app.delete("/tools/{name}")
def delete_tools(name: str) -> dict[str, str]:
    """Löscht einen Endeffektor: ``<name>.json`` UND Mesh-Datei (Issue #56).

    Dünner Aktions-Wrapper (ADR-014): ruft `delete_tool`. Kein
    projektübergreifender „ist-referenziert"-Check (Out of Scope). 404, wenn der
    Endeffektor nicht existiert.
    """
    from fgc.pipeline.actions import delete_tool

    try:
        delete_tool(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"deleted": name}


# --- Workstation-Bibliothek (Issue #72, PRD #69): CRUD auf workstations/ -------


class HeightRangeModel(BaseModel):
    """Stufenlos verstellbarer Hoehenbereich in mm (min < max, Issue #72)."""

    min: float
    max: float


class WorkstationInfoModel(BaseModel):
    """Kenndaten einer Workstation fuer die Bibliothek (Issue #72).

    Eine Entity fuer stationaere Zelle und mobile Workstation (``mobility``); das
    Hoehenmodell haengt an ``height_adjustable`` — ``base_heights_mm`` (fest) oder
    ``height_range_mm`` (verstellbar). Genau eines der Felder ist gesetzt.
    """

    name: str
    mobility: str
    height_adjustable: bool
    base_heights_mm: list[float] = []
    height_range_mm: HeightRangeModel | None = None
    safety_min_distance_mm: float
    vendor: str = ""
    #: Kompatibilitaets-Tags (Issue #71/#72); leer = 'unbekannt', nicht 'inkompatibel'.
    compatible_robots: list[str] = []
    #: Optionales Umgebungs-Mesh (Issue #78): Dateiname + absoluter Pfad (der Viewer
    #: uebersetzt ihn in eine ``/@fs/``-URL). Fehlt das Mesh, bleiben beide None.
    mesh: str | None = None
    mesh_path: str | None = None
    #: Platzierungs-Frames (ADR-006); None = nicht gesetzt.
    robot_base_frame: FrameModel | None = None
    work_surface_frame: FrameModel | None = None
    #: S1-Stammdaten (Issue #136, ADR-022): Kanal-Mapping (ADR-011) + gemessene
    #: Totzeit (ADR-012); None = 'unbestaetigt'. Der Modul-Export generiert daraus
    #: das Setup. Freie Dicts (der Core validiert gegen das Workstation-Schema).
    io_channels: dict | None = None
    deadtime: dict | None = None


class WorkstationListResponse(BaseModel):
    """Antwort auf GET /workstations: alle verfuegbaren Workstation-Definitionen."""

    workstations: list[WorkstationInfoModel]


class WorkstationRequest(BaseModel):
    """Parameter fuer POST/PUT /workstations — Workstation anlegen/bearbeiten (Issue #72/#78).

    Strukturierte Zahlenfelder **plus** optionaler Mesh-Upload (Issue #78, ADR-021):
    ``mesh_base64`` + ``mesh_filename`` (base64-in-JSON wie CreateToolRequest) sowie
    die im Bibliothek-Editor gesetzten Platzierungs-Frames ``robot_base_frame`` und
    ``work_surface_frame`` (ADR-006). Alle vier sind optional — fehlen sie, bleibt die
    Workstation reine Zahlenfelder (bzw. beim Update das bestehende Mesh erhalten).
    Die Hoehen-Branch-Regel (verstellbar → ``height_range_mm`` mit min<max; fest →
    geordnetes ``base_heights_mm`` inkl. 0) prueft der Core (`build_workstation_artifact`);
    ein Verstoss oder ein kaputtes Mesh ergibt 422.
    """

    name: str
    mobility: str
    height_adjustable: bool
    base_heights_mm: list[float] = []
    height_range_mm: HeightRangeModel | None = None
    safety_min_distance_mm: float | None = None
    vendor: str = ""
    compatible_robots: list[str] = []
    #: Optionales Mesh-Upload (Issue #78): base64 + Dateiname fuers Format (wie
    #: CreateToolRequest). Fehlt = kein neues Mesh (beim Update bleibt das alte).
    mesh_filename: str | None = None
    mesh_base64: str | None = None
    #: Platzierungs-Frames (ADR-006); nicht gesendet = geloescht (Request ist der Stand).
    robot_base_frame: FrameModel | None = None
    work_surface_frame: FrameModel | None = None
    #: S1-Stammdaten (Issue #136, ADR-022): Kanal-Mapping (ADR-011) + gemessene
    #: Totzeit (ADR-012); nicht gesendet = geloescht (Request ist der Stand). Freie
    #: Dicts — der Core validiert sie gegen das Workstation-Schema (Verstoss = 422).
    io_channels: dict | None = None
    deadtime: dict | None = None


def _decode_optional_mesh(mesh_base64: str | None) -> bytes | None:
    """Dekodiert ein optionales base64-Mesh aus dem Request (Issue #78).

    ``None``/leer → ``None`` (kein neuer Upload). Kaputtes base64 → 422 (analog
    ``post_tools``), damit die Aktions-Schicht nur saubere Bytes sieht.
    """
    if not mesh_base64:
        return None
    import base64

    try:
        return base64.b64decode(mesh_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422, detail=f"Mesh-Daten nicht dekodierbar: {exc}"
        ) from exc


def _workstation_info_model(
    ws: object, workstations_dir: Path | None = None
) -> WorkstationInfoModel:
    """Baut das WorkstationInfoModel aus einer WorkstationDef (Issue #72/#78).

    Loest den absoluten ``mesh_path`` auf (falls ein Mesh gesetzt und real abgelegt
    ist) — der Viewer uebersetzt ihn in eine ``/@fs/``-URL, analog ``_tool_info_model``.
    """
    from fgc.paths import WORKSTATIONS_DIR

    base = workstations_dir or WORKSTATIONS_DIR
    rng = ws.height_range_mm  # type: ignore[attr-defined]
    mesh_path: str | None = None
    mesh = ws.mesh  # type: ignore[attr-defined]
    if mesh:
        candidate = base / mesh
        if candidate.exists():
            mesh_path = str(candidate.resolve())
    rbf = ws.robot_base_frame  # type: ignore[attr-defined]
    wsf = ws.work_surface_frame  # type: ignore[attr-defined]
    return WorkstationInfoModel(
        name=ws.name,  # type: ignore[attr-defined]
        mobility=ws.mobility,  # type: ignore[attr-defined]
        height_adjustable=ws.height_adjustable,  # type: ignore[attr-defined]
        base_heights_mm=list(ws.base_heights_mm),  # type: ignore[attr-defined]
        height_range_mm=HeightRangeModel(min=rng[0], max=rng[1]) if rng else None,
        safety_min_distance_mm=ws.safety_min_distance_mm,  # type: ignore[attr-defined]
        vendor=ws.vendor,  # type: ignore[attr-defined]
        compatible_robots=list(ws.compatible_robots),  # type: ignore[attr-defined]
        mesh=mesh,
        mesh_path=mesh_path,
        robot_base_frame=FrameModel(**rbf) if rbf else None,
        work_surface_frame=FrameModel(**wsf) if wsf else None,
        io_channels=ws.io_channels,  # type: ignore[attr-defined]
        deadtime=ws.deadtime,  # type: ignore[attr-defined]
    )


@app.get("/workstations", response_model=WorkstationListResponse)
def get_workstations() -> WorkstationListResponse:
    """Listet alle Workstation-Definitionen aus workstations/ (Issue #72).

    Duenner Aktions-Wrapper (ADR-014): ruft `list_workstations`. Kaputte Dateien
    werden still uebersprungen; ein neuer ``workstations/``-Eintrag erscheint ohne
    Neustart.
    """
    from fgc.pipeline.actions import list_workstations

    return WorkstationListResponse(
        workstations=[_workstation_info_model(ws) for ws in list_workstations()]
    )


@app.post("/workstations", response_model=WorkstationInfoModel)
def post_workstations(req: WorkstationRequest) -> WorkstationInfoModel:
    """Legt eine Workstation an (Bibliothek, Issue #72).

    Duenner Aktions-Wrapper (ADR-014): ruft `create_workstation`, das das Artefakt
    schema-valide baut (inkl. Hoehen-Branch-Regel) und **atomar** ablegt (Temp +
    ``os.replace``, ADR-018). Die Antwort ist die frische Kenndaten-Karte.

    422 bei ungueltiger Eingabe (Name leer, Hoehen-Branch-Regel verletzt,
    Schema-Verletzung).
    """
    from fgc.pipeline.actions import create_workstation

    mesh_bytes = _decode_optional_mesh(req.mesh_base64)
    try:
        result = create_workstation(
            req.name,
            req.mobility,
            req.height_adjustable,
            base_heights_mm=req.base_heights_mm,
            height_range_mm=req.height_range_mm.model_dump() if req.height_range_mm else None,
            safety_min_distance_mm=req.safety_min_distance_mm,
            vendor=req.vendor,
            compatible_robots=req.compatible_robots,
            mesh_bytes=mesh_bytes,
            mesh_filename=req.mesh_filename,
            robot_base_frame=req.robot_base_frame.model_dump() if req.robot_base_frame else None,
            work_surface_frame=(
                req.work_surface_frame.model_dump() if req.work_surface_frame else None
            ),
            io_channels=req.io_channels,
            deadtime=req.deadtime,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _workstation_info_model(result.workstation)


@app.put("/workstations/{name}", response_model=WorkstationInfoModel)
def put_workstations(name: str, req: WorkstationRequest) -> WorkstationInfoModel:
    """Aktualisiert eine bestehende Workstation (Bibliothek-Editor, Issue #72).

    Duenner Aktions-Wrapper (ADR-014): ruft `update_workstation`. Der Name ist fix
    (Pfad-Parameter, Identitaet = Dateiname; ``req.name`` wird ignoriert, kein
    Rename). Schreiben ist **atomar** (ADR-018).

    404, wenn die Workstation nicht existiert. 422 bei verletzter Hoehen-Branch-Regel
    oder Schema-Verletzung.
    """
    from fgc.pipeline.actions import update_workstation

    mesh_bytes = _decode_optional_mesh(req.mesh_base64)
    with action_errors():
        result = update_workstation(
            name,
            req.mobility,
            req.height_adjustable,
            base_heights_mm=req.base_heights_mm,
            height_range_mm=req.height_range_mm.model_dump() if req.height_range_mm else None,
            safety_min_distance_mm=req.safety_min_distance_mm,
            vendor=req.vendor,
            compatible_robots=req.compatible_robots,
            mesh_bytes=mesh_bytes,
            mesh_filename=req.mesh_filename,
            robot_base_frame=req.robot_base_frame.model_dump() if req.robot_base_frame else None,
            work_surface_frame=(
                req.work_surface_frame.model_dump() if req.work_surface_frame else None
            ),
            io_channels=req.io_channels,
            deadtime=req.deadtime,
        )

    return _workstation_info_model(result.workstation)


@app.delete("/workstations/{name}")
def delete_workstations(name: str) -> dict[str, str]:
    """Loescht eine Workstation: ``<name>.json`` (Issue #72).

    Duenner Aktions-Wrapper (ADR-014): ruft `delete_workstation`. Kein
    projektuebergreifender „ist-referenziert"-Check (Out of Scope). 404, wenn die
    Workstation nicht existiert.
    """
    from fgc.pipeline.actions import delete_workstation

    try:
        delete_workstation(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"deleted": name}


# --- Basis-Bohrbild-Erkennung (Issue #78, ADR-021): Mesh-Snap der Roboterbasis --


class DetectBaseHolesRequest(BaseModel):
    """Parameter fuer POST /workstations/{name}/detect-base-holes (Issue #78).

    ``robot`` ist der Name der Roboterdefinition aus ``robots/``, deren
    ``base_mount``-Bohrbild im Workstation-Mesh gesucht wird.
    """

    robot: str


class DetectedHoleModel(BaseModel):
    """Eine erkannte Durchgangsbohrung (Welt-mm, ADR-006) fuers Viewer-Overlay."""

    center_mm: list[float]
    radius_mm: float
    normal: list[float]


class DetectBaseHolesResponse(BaseModel):
    """Antwort auf POST /workstations/{name}/detect-base-holes (Issue #78).

    ``matched`` = Basis-Bohrbild im Mesh gefunden; ``robot_base_frame`` der daraus
    abgeleitete Frame (ADR-006, w-first) oder ``None``; ``detected_holes`` **alle**
    erkannten Loecher (unabhaengig vom Abgleich); ``warnings`` traegt bei Nicht-Treffer
    den klaren Befund (kein Gate, ADR-013); ``message`` die Kurzfassung.
    """

    matched: bool
    robot_base_frame: FrameModel | None = None
    detected_holes: list[DetectedHoleModel]
    warnings: list[str]
    message: str


@app.post(
    "/workstations/{name}/detect-base-holes",
    response_model=DetectBaseHolesResponse,
)
def post_detect_base_holes(name: str, req: DetectBaseHolesRequest) -> DetectBaseHolesResponse:
    """Erkennt das Basis-Bohrbild eines Roboters im Workstation-Mesh (Issue #78).

    Duenner Aktions-Wrapper (ADR-014): ruft `detect_workstation_base_holes`. Passt das
    Bohrbild, kommt ein ``robot_base_frame`` zurueck (identisch zum manuellen
    Flaechen-Pick); passt nichts, ist das ein **Befund, kein Fehler** (``matched=False``
    mit Warnung, ADR-013) und liefert weiterhin 200.

    404, wenn Workstation oder Roboter unbekannt sind. 422, wenn die Workstation kein
    Mesh hat, das Mesh unlesbar ist oder der Roboter kein ``base_mount`` fuehrt.
    """
    from fgc.pipeline.actions import detect_workstation_base_holes

    with action_errors():
        result = detect_workstation_base_holes(name, req.robot)

    return DetectBaseHolesResponse(
        matched=result.matched,
        robot_base_frame=(
            FrameModel(**result.robot_base_frame) if result.robot_base_frame else None
        ),
        detected_holes=[DetectedHoleModel(**h) for h in result.detected_holes],
        warnings=result.warnings,
        message=result.message,
    )


@app.put("/projects/{slug}/tool", response_model=SetToolResponse)
def put_tool(slug: str, req: SetToolRequest) -> SetToolResponse:
    """Endeffektor-Wahl für einen Druckjob persistieren (Issue #21).

    Setzt das ``tool``-Feld im Druckjob ``job_id`` und führt den statischen
    Payload-Check durch (Endeffektor-Gewicht vs. Roboter-Traglast).
    Payload-Überschreitung ist ein Befund, kein Gate — die Wahl wird gespeichert,
    die Warnung erscheint in der Antwort (payload_ok=false).
    """
    from fgc.pipeline.actions import set_tool_for_job

    with action_errors():
        result = set_tool_for_job(slug, req.tool, req.job_id)

    return SetToolResponse(
        **_project_envelope(slug, result.artifact),
        payload_ok=result.payload_ok,
        payload_margin_kg=result.payload_margin_kg,
    )


class SetWorkstationRequest(BaseModel):
    """Parameter für PUT /projects/{slug}/workstation — Workstation-Wahl persistieren (Issue #77).

    ``workstation`` ist der Name der Workstation-Definition aus ``workstations/``;
    ``job_id`` ist der Druckjob, dessen ``workstation``-Feld aktualisiert wird.
    Kompatibilitäts-Befund ist informativ — kein Gate (Befund, kein Gate, ADR-013).
    """

    workstation: str
    job_id: str = "default"


class SetWorkstationResponse(ProjectResponse):
    """Antwort auf PUT /projects/{slug}/workstation: Projekt-Umschlag + Kompat-Befund (Issue #77).

    Erbt den 5-Feld-Umschlag von ``ProjectResponse`` (Issue #118); der
    Kompatibilitäts-Befund ist additiv — Befund, kein Gate (ADR-013).
    """

    #: Kompatibilität zum Roboter des Jobs (domain/compat): true/false bzw. null (kein Roboter).
    compatible: bool | None = None


@app.put("/projects/{slug}/workstation", response_model=SetWorkstationResponse)
def put_workstation(slug: str, req: SetWorkstationRequest) -> SetWorkstationResponse:
    """Workstation-Wahl für einen Druckjob persistieren (Issue #77, PRD #69).

    Setzt das ``workstation``-Feld im Druckjob ``job_id`` (einzige Schreibstelle
    ``fgc.project``, ADR-016) und liefert den Kompatibilitäts-Befund gegen den Roboter
    des Jobs zurück. Inkompatibilität ist ein Befund, kein Gate — die Wahl wird
    gespeichert, die Warnung erscheint in der Antwort (compatible=false).

    Anders als PUT .../robot und PUT .../tool veraltet dieser Aufruf **keine** Outputs
    (kein Revisions-Bump): die Workstation-Werte konsumiert erst der Druckplan-
    Automatismus (#70). Das ist der Seam zu PRD B (#70).
    """
    from fgc.pipeline.actions import set_workstation_for_job

    with action_errors():
        result = set_workstation_for_job(slug, req.workstation, req.job_id)

    return SetWorkstationResponse(
        **_project_envelope(slug, result.artifact),
        compatible=result.compatible,
    )


class SetStandModeRequest(BaseModel):
    """Anfrage an PUT /projects/{slug}/stand-mode: Aufstell-Toggle setzen (Issue #81)."""

    #: Aufstell-Zustand: 'floor' (Roboter am Boden) | 'elevated' (darf erhoeht stehen).
    stand_mode: str
    job_id: str = "default"


class SetStandModeResponse(ProjectResponse):
    """Antwort auf PUT /projects/{slug}/stand-mode: Projekt-Umschlag + gesetzter Toggle (Issue #81).

    Erbt den 5-Feld-Umschlag von ``ProjectResponse`` (Issue #118); ``stand_mode``
    ist der gesetzte Wert (additiv).
    """

    stand_mode: str


@app.put("/projects/{slug}/stand-mode", response_model=SetStandModeResponse)
def put_stand_mode(slug: str, req: SetStandModeRequest) -> SetStandModeResponse:
    """Aufstell-Toggle für einen Druckjob persistieren (Issue #81, PRD B/#70).

    Setzt das ``stand_mode``-Feld im Druckjob ``job_id`` (einzige Schreibstelle
    ``fgc.project``, ADR-016). Der Toggle begrenzt den Podesthöhen-Satz, den die
    Abschnittssuche der Workstation nutzen darf (``floor`` = Boden, ``elevated`` =
    reale Podesthöhen). Wie PUT .../workstation veraltet dieser Aufruf **keine**
    Outputs; die Neubewertung stößt der Druckplan über POST .../decomposition an.
    """
    from fgc.pipeline.actions import set_stand_mode_for_job

    with action_errors():
        result = set_stand_mode_for_job(slug, req.stand_mode, req.job_id)

    return SetStandModeResponse(
        **_project_envelope(slug, result.artifact),
        stand_mode=result.stand_mode,
    )


class SetContextCheckRequest(BaseModel):
    """Anfrage an PUT /projects/{slug}/context-check: Gebäudekontext-Schalter (Issue #131)."""

    #: Gebäudekontext-Prüfung der Kollisionskontrolle ein (True) / aus (False).
    check_building_context: bool
    job_id: str = "default"


class SetContextCheckResponse(ProjectResponse):
    """Antwort auf PUT /projects/{slug}/context-check: Projekt-Umschlag + Schalter (Issue #131).

    Erbt den 5-Feld-Umschlag von ``ProjectResponse`` (Issue #118);
    ``check_building_context`` ist der gesetzte Wert (additiv).
    """

    check_building_context: bool


@app.put("/projects/{slug}/context-check", response_model=SetContextCheckResponse)
def put_context_check(slug: str, req: SetContextCheckRequest) -> SetContextCheckResponse:
    """Gebäudekontext-Schalter der Kollisionskontrolle persistieren (Issue #131, ADR-024).

    Spiegel von PUT .../stand-mode: setzt das ``check_building_context``-Feld im
    Druckjob ``job_id`` (einzige Schreibstelle ``fgc.project``, ADR-016). Bei „ein"
    prüft die nächste Simulation den Arm zusätzlich gegen den Gebäudekontext
    (context.json, Issue #17); bei Zerlegungsart Modul gegenstandslos (ADR-022). Wie
    PUT .../stand-mode veraltet dieser Aufruf **keine** Outputs — der Schalter wirkt
    erst bei der nächsten Simulation.
    """
    from fgc.pipeline.actions import set_context_check_for_job

    with action_errors():
        result = set_context_check_for_job(slug, req.check_building_context, req.job_id)

    return SetContextCheckResponse(
        **_project_envelope(slug, result.artifact),
        check_building_context=result.check_building_context,
    )


class SetModuleLimitsRequest(BaseModel):
    """Anfrage an PUT /projects/{slug}/module-limits: Modul-Obergrenzen setzen (Issue #90).

    ``None`` je Grenze = keine Obergrenze; beide ``None`` = Block entfernen
    (nur der Arbeitsraum begrenzt, ADR-022).
    """

    max_length_mm: float | None = None
    max_height_mm: float | None = None
    job_id: str = "default"


class SetModuleLimitsResponse(ProjectResponse):
    """Antwort auf PUT /projects/{slug}/module-limits: Projekt-Umschlag + Grenzen (Issue #90).

    Erbt den 5-Feld-Umschlag von ``ProjectResponse`` (Issue #118);
    ``module_limits`` ist der gesetzte sparse Block (additiv).
    """

    module_limits: dict


@app.put("/projects/{slug}/module-limits", response_model=SetModuleLimitsResponse)
def put_module_limits(slug: str, req: SetModuleLimitsRequest) -> SetModuleLimitsResponse:
    """Optionale Obergrenzen der Modulgroesse fuer einen Druckjob persistieren (Issue #90).

    Setzt den sparse ``module_limits``-Block im Druckjob ``job_id`` (einzige
    Schreibstelle ``fgc.project``, ADR-016). Die Grenzen wirken auf die
    Rasterverfeinerung der Zerlegungsart „modul" (Zelle > Grenze ⇒ weitere
    Teilung); das Modulgewicht bleibt ein Befund je Teil im Zerlegungslauf —
    kein Gate (ADR-022). Wie PUT .../stand-mode veraltet dieser Aufruf **keine**
    Outputs; die Neubewertung stoesst der Druckplan ueber POST .../decomposition an.
    """
    from fgc.pipeline.actions import set_module_limits_for_job

    with action_errors():
        result = set_module_limits_for_job(
            slug, req.max_length_mm, req.max_height_mm, req.job_id
        )

    return SetModuleLimitsResponse(
        **_project_envelope(slug, result.artifact),
        module_limits=result.module_limits,
    )


class SetObjectiveRequest(BaseModel):
    """Anfrage an PUT /projects/{slug}/objective: Zielfunktion der Zerlegungs-Suche (Issue #212).

    Ein Gewichts-Satz, zwei Lesarten (Grill 2026-07-14): ``aufwiegen=False``
    (Default) = die Gewichts-Reihenfolge ist die lexikographische Rangfolge;
    ``True`` = gewichtete Summe. ``weights=None`` = Default-Gewichte.
    """

    aufwiegen: bool = False
    #: Gewicht je Kriterium (umsetzvorgaenge/fugenflaeche/kinematische_marge/volumen_cv);
    #: ``None`` = Default (Rangfolge Umsetzvorgaenge > Fugenflaeche > Marge > c_v).
    weights: dict[str, float] | None = None
    job_id: str = "default"


class SetObjectiveResponse(ProjectResponse):
    """Antwort auf PUT /projects/{slug}/objective: Projekt-Umschlag + wirksame Config (Issue #212).

    Erbt den 5-Feld-Umschlag von ``ProjectResponse`` (Issue #118); ``objective``
    ist die **wirksame** Config (Lesart + Gewichte, immer vollstaendig — auch
    wenn der Druckjob den Default sparse ohne Feld traegt).
    """

    objective: dict


@app.put("/projects/{slug}/objective", response_model=SetObjectiveResponse)
def put_objective(slug: str, req: SetObjectiveRequest) -> SetObjectiveResponse:
    """Zielfunktion der Zerlegungs-Suche fuer einen Druckjob persistieren (Issue #212, PRD #183).

    Setzt den sparse ``objective``-Block im Druckjob ``job_id`` (einzige
    Schreibstelle ``fgc.project``, ADR-016); der Default entfernt das Feld
    (Altprojekte byte-gleich). Anders als PUT .../module-limits veraltet eine
    **tatsaechliche** Aenderung den Zerlegungsplan (Eingabe-Stufe ``cutplan``,
    echo-fest via ``bump_if_changed`` #199): ein unter der alten Zielfunktion
    gesuchter Plan gilt ehrlich als veraltet (ADR-017). Gleichstand zweier
    Gewichte im Aus-Modus (lexikographisch) ist ein 400er — die GUI verhindert
    ihn, der Core weist ihn zusaetzlich zurueck. Die komplette Config (inkl.
    Quantisierungs-Schrittweiten) stempelt der naechste Zerlegungslauf in seine
    Provenienz (ADR-004).
    """
    from fgc.pipeline.actions import set_objective_for_job

    with action_errors():
        result = set_objective_for_job(slug, req.aufwiegen, req.weights, req.job_id)

    return SetObjectiveResponse(
        **_project_envelope(slug, result.artifact),
        objective=result.objective,
    )


class SetPlacementOverrideRequest(BaseModel):
    """Anfrage an PUT /projects/{slug}/placement-override (Issue #94, PRD #88).

    Freie Platzierungswerte eines Teils, sparse: ``None`` je Feld = erbt die
    automatische (bzw. per ``option_id`` referenzierte) Platzierung; alle
    ``None`` = die freien Werte werden entfernt (zurück zur Automatik).
    """

    section_id: str
    lateral_mm: float | None = None
    standoff_mm: float | None = None
    stand_height_mm: float | None = None
    job_id: str = "default"
    #: Issue #173: ``True`` bewahrt zuvor gesetzte freie Override-Felder und legt
    #: nur die uebergebenen Werte feldweise darueber (Anwenden-Pfad einer
    #: Einzelfeld-Option des Kollisions-Advisors). Default ``False`` = Neuaufbau
    #: (manuelles Formular, ``None`` loescht ein Feld).
    merge: bool = False


class SetPlacementOverrideResponse(ProjectResponse):
    """Antwort auf PUT /projects/{slug}/placement-override: Projekt-Umschlag + Eintrag (Issue #94).

    Erbt den 5-Feld-Umschlag von ``ProjectResponse`` (Issue #118). ``override``
    ist der sparse gespeicherte Stand des Teils (leer = Override entfernt,
    automatische Platzierung); beides additiv.
    """

    section_id: str
    override: dict


@app.put("/projects/{slug}/placement-override", response_model=SetPlacementOverrideResponse)
def put_placement_override(
    slug: str, req: SetPlacementOverrideRequest
) -> SetPlacementOverrideResponse:
    """Freien Platzierungs-Override eines Teils persistieren (Issue #94, PRD #88).

    Dünner Aktions-Wrapper (ADR-014, Mirror von PUT .../module-limits): schreibt
    die freien Werte in den ``section_overrides``-Eintrag des Teils (einzige
    Schreibstelle ``fgc.project``, ADR-016) und bumpt bei tatsächlicher Änderung
    NUR den Pro-Abschnitts-Zähler dieses Teils (#83 — nur dieses Teil veraltet).
    Kein Werte-Gate: der Sicherheits-Mindestabstand der Workstation wird beim
    nächsten Zerlegungslauf als Befund gemeldet (``placement_check``), nicht
    erzwungen. Die Neubewertung (Ampel/erreichbar %/Marge) stößt der Druckplan
    über POST .../decomposition an (ADR-007).
    """
    from fgc.pipeline.actions import set_placement_override_for_job

    with action_errors():
        result = set_placement_override_for_job(
            slug,
            req.section_id,
            req.lateral_mm,
            req.standoff_mm,
            req.stand_height_mm,
            req.job_id,
            merge=req.merge,
        )

    return SetPlacementOverrideResponse(
        **_project_envelope(slug, result.artifact),
        section_id=result.section_id,
        override=result.override,
    )


# --- Platzierung (Issue #22): Aufstellmöglichkeiten bewerten + Wahl markieren --


class PlacementOptionModel(BaseModel):
    """Eine reale Aufstellmöglichkeit — die geplante Basis-Lage relativ zur Wand.

    Ein **Plan**, kein Setup (ADR-006): verbindlich wird die Lage erst durch
    das Antast-Verfahren. Einheiten: mm, rad (ADR-006).
    """

    option_id: str
    lateral_mm: float
    standoff_mm: float
    stand_height_mm: float
    yaw_rad: float = 0.0


class EvaluatePlacementsRequest(BaseModel):
    """Parameter für POST /projects/{slug}/placements — Bewertungsmodus (Issue #22).

    Der Nutzer gibt seine realen Aufstellmöglichkeiten vor, der Core bewertet
    sie (erreichbarer Wandanteil + kinematische Marge). Roboter und Endeffektor
    kommen aus dem Druckjob (Issue #20/#21).
    """

    options: list[PlacementOptionModel]
    job_id: str = "default"
    selected: str | None = None


class EvaluatePlacementsResponse(BaseModel):
    """Antwort auf POST /projects/{slug}/placements: Scores + Lauf-Verweis + Projekt.

    ``scored`` enthält je Aufstellmöglichkeit den Score (reachable_fraction,
    kinematic_margin, warnings — Warnungen sind Daten, kein Abbruch); die
    normativen Daten liegen im Bewertungslauf ``run_dir`` (placement.json, ADR-004).
    """

    slug: str
    job_id: str
    run_dir: str
    scored: list[dict]
    selected: str | None
    print_jobs: list[dict]
    #: Gesamt-Befund „(kein) machbarer Kandidat" des Optimalvorschlags (Issue #228,
    #: ADR-026): ``checked``/``feasible``/``n_feasible``. ``None`` im reinen
    #: Bewertungsmodus (dort läuft kein Vorschlags-Grob-Check). Der Core rechnet, der
    #: Viewer zeigt (Ampel/Hinweis sind Folge-Issue) — je ``scored``-Eintrag steht das
    #: Einzelurteil zusätzlich unter ``score.collision``.
    feasibility: dict | None = None


class SelectPlacementRequest(BaseModel):
    """Parameter für PUT /projects/{slug}/placement-selection (Issue #22).

    ``option_id=None`` hebt die Wahl auf. Die Wahl ist ein Plan-Zustand im
    Projekt — kein Setup (ADR-006).
    """

    option_id: str | None
    job_id: str = "default"


class SelectPlacementResponse(BaseModel):
    """Antwort auf PUT /projects/{slug}/placement-selection: aktualisierte Druckjobs."""

    slug: str
    job_id: str
    selected: str | None
    print_jobs: list[dict]


@app.post("/projects/{slug}/placements", response_model=EvaluatePlacementsResponse)
def post_placements(slug: str, req: EvaluatePlacementsRequest) -> EvaluatePlacementsResponse:
    """Bewertet reale Aufstellmöglichkeiten eines Druckjobs (Issue #22).

    Dünner Aktions-Wrapper (ADR-014): ruft `evaluate_placements`, das die
    Bewertung als provenienz-gestempelten Lauf (placement.json) ablegt und im
    Druckjob nur Plan-Eingaben + Wahl + Lauf-Verweis persistiert (ADR-016).
    """
    from fgc.pipeline.actions import evaluate_placements

    source = (
        f"POST /projects/{slug}/placements job_id={req.job_id} "
        f"n_options={len(req.options)}"
    )
    with action_errors():
        result = evaluate_placements(
            slug,
            [o.model_dump() for o in req.options],
            source,
            req.job_id,
            selected=req.selected,
        )

    return EvaluatePlacementsResponse(
        slug=slug,
        job_id=result.job_id,
        run_dir=str(result.run_dir),
        scored=result.scored,
        selected=result.selected,
        print_jobs=result.artifact["print_jobs"],
        feasibility=result.feasibility,
    )


@app.put("/projects/{slug}/placement-selection", response_model=SelectPlacementResponse)
def put_placement_selection(slug: str, req: SelectPlacementRequest) -> SelectPlacementResponse:
    """Markiert eine Aufstellmöglichkeit als gewählt (Issue #22).

    Reiner Plan-Zustand im Druckjob (`selected_placement`) — keine Neubewertung,
    kein Setup (ADR-006): verbindlich wird die Lage erst durchs Antasten.
    """
    from fgc.pipeline.actions import select_placement

    with action_errors():
        result = select_placement(slug, req.option_id, req.job_id)

    return SelectPlacementResponse(
        slug=slug,
        job_id=result.job_id,
        selected=result.selected,
        print_jobs=result.artifact["print_jobs"],
    )


# --- Platzierung, Optimalvorschlag (Issue #23) -----------------------------------


class SuggestPlacementRequest(BaseModel):
    """Parameter fuer POST /projects/{slug}/placement-suggestion (Issue #23).

    ``standoff_mm``: Abstand der Basis vor der Wandfront (mm); Default 700 mm
    (Bedienersicherheitsabstand). ``n_best``: Anzahl der besten Vorschlaege,
    die in die Vergleichsliste kommen. ``job_id``: Druckjob im Projekt.
    """

    job_id: str = "default"
    standoff_mm: float = 700.0
    n_best: int = 3


@app.post("/projects/{slug}/placement-suggestion", response_model=EvaluatePlacementsResponse)
def post_placement_suggestion(
    slug: str, req: SuggestPlacementRequest
) -> EvaluatePlacementsResponse:
    """Optimalvorschlag fuer die Roboterbasis (Platzierung, Issue #23).

    Duenner Aktions-Wrapper (ADR-014): ruft ``suggest_placement``, das ueber ein
    deterministisches 2D-Raster (3 seitliche x 7 Hoehen-Stufen = 21 Kandidaten)
    sucht, bewertet und die ``n_best`` besten Vorschlaege als ``vorschlag-*``-
    Optionen in die Vergleichsliste einfuegt. Bestehende manuelle Optionen
    bleiben erhalten; fruhere Vorschlaege werden ersetzt.

    Rechenzeit: Je nach Hardware 2–10 Sekunden (21 IK-Laeufe ueber je ein festes
    Sampling-Raster). Die GUI zeigt waehrend der Berechnung einen Busy-Zustand.
    Warnungen sind Daten — kein Abbruch, kein Gate.
    """
    from fgc.pipeline.actions import suggest_placement

    source = (
        f"POST /projects/{slug}/placement-suggestion "
        f"job_id={req.job_id} standoff_mm={req.standoff_mm} n_best={req.n_best}"
    )
    with action_errors():
        result = suggest_placement(
            slug,
            source,
            req.job_id,
            standoff_mm=req.standoff_mm,
            n_best=req.n_best,
        )

    return EvaluatePlacementsResponse(
        slug=slug,
        job_id=result.job_id,
        run_dir=str(result.run_dir),
        scored=result.scored,
        selected=result.selected,
        print_jobs=result.artifact["print_jobs"],
        feasibility=result.feasibility,
    )


# --- Singularitäts-Advisor (Issue #65) ----------------------------------------


class SingularityAdviceRequest(BaseModel):
    """Parameter für POST /projects/{slug}/singularity-advice (Issue #65/#134).

    ``section_id`` benennt den **Fokus-Abschnitt** des Zerlegungsplans (Issue
    #134, Muster Kollisions-Advisor #130); ohne ``section_id`` ist die Antwort
    leer (``type=None``, ``advice=None``) — kein Fehler.
    """

    job_id: str = "default"
    section_id: str | None = None


class SingularityAdviceResponse(BaseModel):
    """Antwort auf POST /projects/{slug}/singularity-advice: Typ-Urteil + Vorschlag.

    Rein beratend (ADR-007): der Core urteilt, der Viewer *setzt* danach über die
    bestehenden Routen (``process-params`` = Kipp-Delta, ``placement-override``
    #94 = Platzierung des Abschnitts). ``advice=None`` bedeutet: nichts zu
    beraten (kein Fokus-Abschnitt, unerreichbar oder Marge unkritisch).
    """

    slug: str
    job_id: str
    section_id: str | None
    type: str | None
    near: bool
    measure: float | None
    advice: dict | None


@app.post("/projects/{slug}/singularity-advice", response_model=SingularityAdviceResponse)
def post_singularity_advice(
    slug: str, req: SingularityAdviceRequest
) -> SingularityAdviceResponse:
    """Berät zur Singularitätsnähe der Platzierung des Fokus-Abschnitts (Issue #65/#134).

    Dünner Aktions-Wrapper (ADR-014): ruft ``advise_singularity`` (read-only). Das
    *Anwenden* eines Vorschlags läuft über die bestehenden Schreib-Routen — der
    Viewer rechnet nichts selbst (ADR-007).
    """
    from fgc.pipeline.actions import advise_singularity

    with action_errors():
        result = advise_singularity(slug, req.job_id, req.section_id)

    return SingularityAdviceResponse(
        slug=slug,
        job_id=result.job_id,
        section_id=result.section_id,
        type=result.type,
        near=result.near,
        measure=result.measure,
        advice=result.advice,
    )


# --- Kollisions-Advisor (Issue #130) ------------------------------------------


class CollisionAdviceRequest(BaseModel):
    """Parameter für POST /projects/{slug}/collision-advice (Issue #130).

    ``section_id=None`` wählt den ersten Abschnitt des Zerlegungsplans (die
    Optionsliste ist eine gerankte Menü-Antwort je Abschnitt).
    ``include_options=False`` (Prüf-UX #139/#145) liefert nur den Basis-Befund —
    genau **eine** Neu-Simulation (~20 s) statt Basis + ~17 Hebel-Kandidaten
    (mehrere Minuten). Additiv, Default = bisheriges Verhalten.
    """

    job_id: str = "default"
    section_id: str | None = None
    include_options: bool = True


class CollisionAdviceResponse(BaseModel):
    """Antwort auf POST /projects/{slug}/collision-advice: Basis-Befund + Optionsliste.

    Rein beratend (ADR-007, Muster ADR-020): der Core re-simuliert jeden Hebel-
    Kandidaten mit derselben Maschinerie und liest denselben ``meta.collision``-Befund
    (#127) — keine Parallel-Metrik. ``baseline`` = Vorher-Metrik (min. Abstand/Marge/
    kollisionsfrei) oder ``None`` (keine Kollisionsgeometrie/kein Abschnitt);
    ``options`` = gerankte, gangbare Optionen (nur Verbesserer), jede mit der
    anwendbaren Schreibstellen-Nutzlast (``write``). Das *Anwenden* läuft danach über
    die bestehenden Routen (``process-params`` / ``placement-override``).
    """

    slug: str
    job_id: str
    section_id: str | None
    baseline: dict | None
    options: list[dict]


@app.post("/projects/{slug}/collision-advice", response_model=CollisionAdviceResponse)
def post_collision_advice(slug: str, req: CollisionAdviceRequest) -> CollisionAdviceResponse:
    """Kollisions-Advisor: gerankte Optionsliste auf Knopfdruck (Issue #130).

    Dünner Aktions-Wrapper (ADR-014, Mirror des Singularitäts-Advisors): ruft
    ``advise_collision`` (teuer — re-simuliert je Kandidat). Das *Anwenden* eines
    Menü-Eintrags schreibt der Viewer über die bestehenden Schreib-Routen — der
    Advisor selbst schreibt nichts (ADR-007).
    """
    from fgc.pipeline.actions import advise_collision

    with action_errors():
        result = advise_collision(
            slug, req.job_id, req.section_id, include_options=req.include_options,
        )

    return CollisionAdviceResponse(
        slug=slug,
        job_id=result.job_id,
        section_id=result.section_id,
        baseline=result.baseline,
        options=result.options,
    )


# --- Zerlegung (Issue #24): Zerlegungsvorschlag in Abschnitte ------------------


class CutModel(BaseModel):
    """Eine achsparallele Schnittebene (Plan-Eingabe, Issue #24/#25)."""

    orientation: str
    position_mm: float


class SectionOverrideModel(BaseModel):
    """Platzierungs-Override eines Teils — zwei additive Formen (Issue #25/#94):
    ``option_id`` referenziert eine erfasste Aufstellmöglichkeit aus der
    Platzierungsliste (``job["placements"]``, Issue #22); die freien Felder
    (``lateral_mm``/``standoff_mm``/``stand_height_mm``, Issue #94) übersteuern
    sparse und feldweise die automatische bzw. referenzierte Platzierung."""

    section_id: str
    option_id: str | None = None
    lateral_mm: float | None = None
    standoff_mm: float | None = None
    stand_height_mm: float | None = None


class ProposeDecompositionRequest(BaseModel):
    """Parameter für POST /projects/{slug}/decomposition (Issue #24, erweitert #25).

    ``decomposition_kind``: Zerlegungsart (``"abschnitt"`` = in place;
    ``"modul"`` = an der Workstation vorproduziert, Issue #90/ADR-022 — braucht
    eine Workstation am Druckjob, sonst 422 mit freundlichem Hinweis).
    ``job_id``: Druckjob im Projekt. ``cuts=None`` (Default): der Core schlägt
    die Schnittebenen selbst vor (Issue #24, rückwärtskompatibel). ``cuts``
    gesetzt (Schnittplan-Editing, Issue #25): die Schnittebenen sind
    Plan-Eingaben aus dem Viewer (Drag/Zahlenfeld/Hinzufügen/Entfernen); der
    Core baut daraus die Abschnittsgeometrie und bewertet neu — das ist die
    „Prüfen"-Neubewertung nach jeder Änderung. ``joint_offset_mm`` (nur mit
    ``cuts`` wirksam): Fugen-Versatz zwischen Höhenlagen. ``section_overrides``:
    je Abschnitt eine übersteuerte Platzierung.
    """

    job_id: str = "default"
    decomposition_kind: str = "abschnitt"
    cuts: list[CutModel] | None = None
    joint_offset_mm: float = 0.0
    section_overrides: list[SectionOverrideModel] | None = None


class DecompositionResponse(BaseModel):
    """Antwort auf POST /projects/{slug}/decomposition: Schnittplan + Ampeln + Projekt.

    ``sections`` enthält je Abschnitt Geometrie (x0..x1, z0..z1), die zugeordnete
    Platzierung und den Ampel-Befund (``status.reachable`` + reachable_fraction);
    bei echtem Druckbarkeits-Urteil zusätzlich ``printability`` (Issue #164:
    Freigang + repräsentative Prüf-Tür, additiv). Die normativen Daten liegen im
    Zerlegungslauf ``run_dir`` (decompose.json, ADR-004). ``cuts`` sind die
    Schnittebenen (Plan-Eingaben, ADR-016).
    """

    slug: str
    job_id: str
    run_dir: str
    decomposition_kind: str
    cuts: list[dict]
    joint_offset_mm: float
    sections: list[dict]
    print_jobs: list[dict]
    #: Freigang-Befund der Wand (Issue #163): druckbare Tiefe vs. Wanddicke, wand-weit.
    #: ``None``, wenn die Endeffektor-/Kinematik-Geometrie fehlt (Befund, kein Gate).
    freigang: dict | None = None
    #: Umfangsansage der Stufe-2-Prüf-Tür (Issue #175): ``{"n_representatives",
    #: "n_parts", "est_seconds"}`` — wie viele Höhenreihen eine **globale** Prüfung
    #: rechnen müsste + grobe Dauer, für die bewusste Nutzerwahl „prüft N Abschnitte,
    #: dauert ~…", ohne die teure Prüfung anzustoßen (Fokus-Prüfung bleibt Default).
    pruef_scope: dict | None = None


@app.post("/projects/{slug}/decomposition", response_model=DecompositionResponse)
def post_decomposition(slug: str, req: ProposeDecompositionRequest) -> DecompositionResponse:
    """Schlägt eine Zerlegung der Wand in erreichbare Abschnitte vor (Issue #24) —
    oder wertet einen manuell editierten Schnittplan neu (Issue #25, „Prüfen").

    Dünner Aktions-Wrapper (ADR-014): ruft ``propose_decomposition``, das über das
    deep module `fgc.decompose` die Schnittebenen + Abschnitte + Platzierungen
    berechnet, die Ampeln bewertet und alles als provenienz-gestempelten Lauf
    (decompose.json) ablegt; im Druckjob landen nur Zerlegungsart + Schnittebenen +
    Fugen-Versatz + Overrides + Lauf-Verweis (ADR-016). Ohne ``cuts`` wie bisher
    (Issue #24, read-only-Vorschlag); mit ``cuts`` ist dieser Aufruf selbst die
    Neubewertung des editierten Schnittplans — die UI rechnet nie selbst
    (ADR-007), sie ruft diesen Endpoint über den „Prüfen"-Button (debounced).

    ``decomposition_kind="modul"`` (Issue #90, ADR-022) rechnet mit der **festen
    Platzierung an der Workstation** des Druckjobs (sie ist der Druckort) und
    legt je Teil additiv den Modulgrenzen-Befund (Gewicht + Grenzen) bei; fehlt
    die Workstation am Druckjob, kommt 422 mit freundlichem Hinweis. Ein
    `section_overrides`-Eintrag mit unbekannter `option_id` wird mit 422
    abgelehnt. Warnungen/rote Abschnitte sind Daten — kein Abbruch, kein Gate.
    """
    from fgc.pipeline.actions import propose_decomposition

    source = (
        f"POST /projects/{slug}/decomposition "
        f"job_id={req.job_id} kind={req.decomposition_kind}"
    )
    with action_errors():
        result = propose_decomposition(
            slug,
            source,
            req.job_id,
            kind=req.decomposition_kind,
            cuts=[c.model_dump() for c in req.cuts] if req.cuts is not None else None,
            joint_offset_mm=req.joint_offset_mm,
            section_overrides=(
                # exclude_none: ungesetzte Felder bleiben sparse — sie dürfen weder
                # als null im project.json landen (Schema) noch „erben" übersteuern.
                [o.model_dump(exclude_none=True) for o in req.section_overrides]
                if req.section_overrides is not None
                else None
            ),
        )

    return DecompositionResponse(
        slug=slug,
        job_id=result.job_id,
        run_dir=str(result.run_dir),
        decomposition_kind=result.decomposition_kind,
        cuts=result.cuts,
        joint_offset_mm=result.joint_offset_mm,
        sections=result.sections,
        print_jobs=result.artifact["print_jobs"],
        freigang=result.freigang,
        pruef_scope=result.pruef_scope,
    )


# --- Stufe-2-Prüf-Tür entkoppelt (Issue #175): Anstoß/Fortschritt/Abbruch ---------


class StartDecompositionCheckRequest(BaseModel):
    """Parameter für POST /projects/{slug}/decomposition-check (Issue #175).

    Startet die entkoppelte Stufe-2-Druckbarkeitsprüfung als **Hintergrundlauf** —
    sie verlässt den interaktiven Schnittplan-Loop (Befund B14: ~71 s Freeze) und
    läuft mit Fortschritt + Abbruch. ``focus_section_id`` prüft nur die Höhenreihe des
    Fokus-Teils (Default-Wahl, schnell); ``null`` prüft **global** (alle Reihen — die
    bewusste, teure Wahl, deren Umfang der Viewer aus ``pruef_scope`` ansagt).
    """

    job_id: str = "default"
    focus_section_id: str | None = None


class DecompositionCheckStatusResponse(BaseModel):
    """Zustand/Fortschritt eines Hintergrund-Prüflaufs (Issue #175).

    ``state``: ``running`` | ``done`` | ``cancelled`` | ``superseded`` | ``empty`` |
    ``error``. ``n_done``/``n_total`` speisen die Fortschrittsanzeige; ``scope``/
    ``section_id`` „was wird/wurde geprüft" (global vs. Fokus). Bei ``done`` tragen
    ``sections`` (mit frischer ``printability``) + ``print_jobs`` das Ergebnis, damit
    der Viewer ohne Nachladen aktualisiert. ``superseded`` = die Eingaben änderten sich
    während der Rechnung (paralleler Schreibzugriff war möglich) — verworfen, neu anstoßen.
    """

    check_id: str
    slug: str
    job_id: str
    scope: str
    section_id: str | None = None
    state: str
    n_total: int
    n_done: int
    n_computed: int
    n_cached: int
    error: str | None = None
    sections: list[dict] | None = None
    print_jobs: list[dict] | None = None


@app.post(
    "/projects/{slug}/decomposition-check",
    response_model=DecompositionCheckStatusResponse,
)
def post_decomposition_check(
    slug: str, req: StartDecompositionCheckRequest
) -> DecompositionCheckStatusResponse:
    """Stößt die entkoppelte Stufe-2-Prüf-Tür als Hintergrundlauf an (Issue #175).

    Kehrt **sofort** mit ``state="running"`` + ``check_id`` zurück; der Viewer poll't
    dann GET …/decomposition-check/{check_id} für Fortschritt und Ergebnis und kann
    POST …/{check_id}/cancel zum Abbrechen rufen. Die eigentliche Prüfung hält die
    Projekt-Sperre nicht über die Rechenzeit (ADR-018) — parallele Schreibzugriffe
    (Schnitt verschieben, Slice-Param ändern) bleiben möglich, der Editor friert nicht.
    """
    from fgc.pipeline import checkjobs

    with action_errors():
        job = checkjobs.start(
            slug, req.job_id, focus_section_id=req.focus_section_id
        )
    return DecompositionCheckStatusResponse(**job.to_dict())


@app.get(
    "/projects/{slug}/decomposition-check/{check_id}",
    response_model=DecompositionCheckStatusResponse,
)
def get_decomposition_check(slug: str, check_id: str) -> DecompositionCheckStatusResponse:
    """Fortschritt/Ergebnis eines Hintergrund-Prüflaufs (Issue #175). 404, wenn unbekannt."""
    from fastapi import HTTPException

    from fgc.pipeline import checkjobs

    job = checkjobs.get(check_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Prüflauf {check_id!r} unbekannt.")
    return DecompositionCheckStatusResponse(**job.to_dict())


@app.post(
    "/projects/{slug}/decomposition-check/{check_id}/cancel",
    response_model=DecompositionCheckStatusResponse,
)
def cancel_decomposition_check(
    slug: str, check_id: str
) -> DecompositionCheckStatusResponse:
    """Bricht einen laufenden Hintergrund-Prüflauf ab (Issue #175). 404, wenn unbekannt.

    Setzt nur das Abbruch-Signal; der Thread bricht vor der nächsten teuren Zelle ab und
    **persistiert nichts** (der Stand bleibt „ungeprüft"/„veraltet"). Der Zustand geht
    kurz darauf auf ``cancelled`` über (per GET beobachtbar).
    """
    from fastapi import HTTPException

    from fgc.pipeline import checkjobs

    if not checkjobs.cancel(check_id):
        raise HTTPException(status_code=404, detail=f"Prüflauf {check_id!r} unbekannt.")
    job = checkjobs.get(check_id)
    assert job is not None
    return DecompositionCheckStatusResponse(**job.to_dict())


# --- Beam-Zerlegungslauf auslösbar (Issue #221, Folge #217): Anstoß/Fortschritt/Abbruch ---


class StartBeamProposeRequest(BaseModel):
    """Parameter für POST /projects/{slug}/decomposition-beam (Issue #221).

    Stößt die **Beam-Zerlegung** (#217, PRD #183 Stufe 3) als **Hintergrundlauf** an —
    ``propose_decomposition(beam_search=True)`` mit produktivem Scorer + Kollisions-
    Prüf-Tür. Der Lauf verlässt den Request-Pfad (er kostet Prüf-Tür-Aufrufe) und läuft
    mit Fortschritt + Abbruch, analog zur entkoppelten Stufe-2-Prüf-Tür (#175).
    ``call_budget`` deckelt die erlaubten Prüf-Tür-Aufrufe (``null`` = Core-Default #215).
    """

    job_id: str = "default"
    call_budget: int | None = None


class BeamProposeStatusResponse(BaseModel):
    """Zustand/Fortschritt eines Beam-Zerlegungslaufs (Issue #221) — Spiegel von
    :meth:`fgc.pipeline.checkjobs.BeamProposeJob.to_dict`.

    ``state``: ``running`` | ``done`` | ``cancelled`` | ``error``. ``n_done``/``n_total``
    = verbrauchte / erlaubte **Prüf-Tür-Aufrufe** (das Aufruf-Kontingent #215 — Fortschritt
    in Aufrufen, nicht in Sekunden) und speisen die Fortschrittsanzeige. Bei ``done`` tragen
    ``sections`` (Sieger-Schnittplan mit Ampeln) + ``print_jobs`` + ``run_dir`` das Ergebnis,
    und ``refinement`` den Such-Ausweis verbatim aus dem Lauf (Verworfen-Gründe US 10,
    Relaxationsausweis US 22, Metriken US 20) — der Viewer aktualisiert ohne Nachladen.
    """

    beam_id: str
    slug: str
    job_id: str
    state: str
    n_total: int
    n_done: int
    error: str | None = None
    run_dir: str | None = None
    sections: list[dict] | None = None
    print_jobs: list[dict] | None = None
    refinement: dict | None = None


@app.post(
    "/projects/{slug}/decomposition-beam",
    response_model=BeamProposeStatusResponse,
)
def post_decomposition_beam(
    slug: str, req: StartBeamProposeRequest
) -> BeamProposeStatusResponse:
    """Stößt die Beam-Zerlegung als Hintergrundlauf an (Issue #221, Folge #217).

    Kehrt **sofort** mit ``state="running"`` + ``beam_id`` zurück; der Viewer poll't dann
    GET …/decomposition-beam/{beam_id} für Fortschritt (verbrauchte Prüf-Tür-Aufrufe) und
    Ergebnis und kann POST …/{beam_id}/cancel zum Abbrechen rufen. Der Registry bricht
    einen älteren Lauf desselben (Projekt, Druckjob) automatisch ab (kein Doppel-Schreiben).
    Dünner Aktions-Wrapper (ADR-014): die Rechnung lebt in ``checkjobs.start_beam_propose``.
    """
    from fgc.pipeline import checkjobs

    with action_errors():
        job = checkjobs.start_beam_propose(
            slug, req.job_id, call_budget=req.call_budget
        )
    return BeamProposeStatusResponse(**job.to_dict())


@app.get(
    "/projects/{slug}/decomposition-beam/{beam_id}",
    response_model=BeamProposeStatusResponse,
)
def get_decomposition_beam(slug: str, beam_id: str) -> BeamProposeStatusResponse:
    """Fortschritt/Ergebnis eines Beam-Zerlegungslaufs (Issue #221). 404, wenn unbekannt."""
    from fastapi import HTTPException

    from fgc.pipeline import checkjobs

    job = checkjobs.get_beam_propose(beam_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Beam-Lauf {beam_id!r} unbekannt.")
    return BeamProposeStatusResponse(**job.to_dict())


@app.post(
    "/projects/{slug}/decomposition-beam/{beam_id}/cancel",
    response_model=BeamProposeStatusResponse,
)
def cancel_decomposition_beam(slug: str, beam_id: str) -> BeamProposeStatusResponse:
    """Bricht einen laufenden Beam-Zerlegungslauf ab (Issue #221). 404, wenn unbekannt.

    Setzt nur das Abbruch-Signal; der Thread bricht vor dem nächsten teuren Prüf-Tür-
    Aufruf ab und **persistiert nichts** (der Zerlegungsstand bleibt unverändert). Der
    Zustand geht kurz darauf auf ``cancelled`` über (per GET beobachtbar).
    """
    from fastapi import HTTPException

    from fgc.pipeline import checkjobs

    if not checkjobs.cancel_beam_propose(beam_id):
        raise HTTPException(status_code=404, detail=f"Beam-Lauf {beam_id!r} unbekannt.")
    job = checkjobs.get_beam_propose(beam_id)
    assert job is not None
    return BeamProposeStatusResponse(**job.to_dict())


# --- Abschnitts-Simulation (Issue #26): Slicen + Simulieren je Abschnitt ------


class SimulateSectionRequest(BaseModel):
    """Parameter für POST /projects/{slug}/sections/{section_id}/simulate (Issue #26).

    ``job_id`` = Druckjob im Projekt. Roboter, Endeffektor und Schnittplan kommen
    aus dem Druckjob; die Lage stammt aus der geplanten Platzierung des Abschnitts
    (``pose_source="planned"``), nicht aus einem gemessenen Setup.
    """

    job_id: str = "default"


class SimulateSectionResponse(BaseModel):
    """Antwort auf POST …/sections/{section_id}/simulate: Lauf-Verweis + Kennzahlen.

    ``run_dir`` ist der Abschnitts-Lauf (toolpath.json + trajectory.json, ADR-004);
    der Viewer lädt ihn in den bestehenden Trajektorien-Player. ``pose_source`` ist
    ``"planned"`` (Simulation aus dem Plan). ``duration_s``/``axis_utilization``/
    ``warnings`` speisen die Anzeige je Abschnitt (Druckzeit/Achsauslastung/Warnungen).
    Es ist ein **kinematisches Replay ohne Kollisionsprüfung** (PRD Out of Scope).
    """

    slug: str
    job_id: str
    section_id: str
    run_dir: str
    pose_source: str
    duration_s: float
    n_targets: int
    n_warnings: int
    io_compensated: bool
    axis_utilization: list[float]
    warnings: list[dict]
    print_jobs: list[dict]


@app.post(
    "/projects/{slug}/sections/{section_id}/simulate",
    response_model=SimulateSectionResponse,
)
def post_simulate_section(
    slug: str, section_id: str, req: SimulateSectionRequest
) -> SimulateSectionResponse:
    """Slict + simuliert einen Abschnitt aus der Platzierung heraus (Issue #26).

    Dünner Aktions-Wrapper (ADR-014): ruft `simulate_section`, das aus dem
    Abschnitts-Teil-Mesh einen Toolpath und daraus + der geplanten Platzierung eine
    Trajektorie (``pose_source="planned"``) in **einem** Lauf erzeugt und den
    Druckjob je Abschnitt darauf verweisen lässt (``section_runs``, ADR-016).
    Warnungen/rote Achsauslastung sind Daten — kein Abbruch, kein Gate. Es ist ein
    kinematisches Replay ohne Kollisionsprüfung (PRD Out of Scope).
    """
    from fgc.pipeline.actions import simulate_section

    source = (
        f"POST /projects/{slug}/sections/{section_id}/simulate job_id={req.job_id}"
    )
    with action_errors():
        result = simulate_section(slug, section_id, source, req.job_id)

    return SimulateSectionResponse(
        slug=slug,
        job_id=result.job_id,
        section_id=result.section_id,
        run_dir=str(result.run_dir),
        pose_source=result.pose_source,
        duration_s=result.duration_s,
        n_targets=result.n_targets,
        n_warnings=result.n_warnings,
        io_compensated=result.io_compensated,
        axis_utilization=result.axis_utilization,
        warnings=result.warnings,
        print_jobs=result.artifact["print_jobs"],
    )


# --- Export (Issue #29): DRL je Abschnitt + veraltet-Markierung ---------------


class ExportSectionRequest(BaseModel):
    """Parameter für POST /projects/{slug}/sections/{section_id}/export (Issue #29).

    ``job_id`` = Druckjob im Projekt. Der Abschnitt muss zuvor simuliert sein
    (``section_runs``, Issue #26) — daraus (trajectory.json) und dem im Lauf
    liegenden gemessenen Setup entsteht das DRL. Ohne Setup: Antasten-Hinweis.
    """

    job_id: str = "default"


class ExportSectionResponse(BaseModel):
    """Antwort auf …/sections/{section_id}/export: DRL-Verweis + Vollständigkeit.

    ``run_dir`` ist der Abschnitts-Lauf (die ``program.drl`` liegt darin, ADR-004).
    ``complete`` ist ``True`` bei vollständigem Setup (lauffähiges DRL), sonst
    ``False`` mit ``note`` = Hinweis/Fehlbestand (ADR-006). ``setup_source`` benennt
    die Herkunft ehrlich (Issue #136): ``"measured"``/``"none"`` (Art „abschnitt")
    bzw. ``"generated"``/``"generated_incomplete"`` (Art „modul", aus Stammdaten
    generiert). Kein Gate — die Ausgabe entsteht so oder so.
    """

    slug: str
    job_id: str
    section_id: str
    run_dir: str
    drl_path: str
    complete: bool
    setup_source: str
    note: str
    n_samples: int
    print_jobs: list[dict]


@app.post(
    "/projects/{slug}/sections/{section_id}/export",
    response_model=ExportSectionResponse,
)
def post_export_section(
    slug: str, section_id: str, req: ExportSectionRequest
) -> ExportSectionResponse:
    """Erzeugt das DRL-Programm eines Abschnitts (Reiter Export, Issue #29).

    Dünner Aktions-Wrapper (ADR-014): ruft `export_section_drl`, das die
    bestehende Emit-Aktion (Issue #13) nutzt. Mit gemessenem Setup im Lauf →
    vollständiges DRL; ohne → sichtbar gekennzeichneter Antasten-Hinweis
    (``complete=false``, ``note`` gesetzt) statt eines unmarkiert unvollständigen
    Programms — kein Gate. Frischt zugleich die Export-Revision auf (veraltet-
    Markierung, Issue #29).
    """
    from fgc.pipeline.actions import export_section_drl

    source = f"POST /projects/{slug}/sections/{section_id}/export job_id={req.job_id}"
    with action_errors():
        result = export_section_drl(slug, section_id, source, req.job_id)

    return ExportSectionResponse(
        slug=slug,
        job_id=result.job_id,
        section_id=result.section_id,
        run_dir=str(result.run_dir),
        drl_path=str(result.drl_path),
        complete=result.complete,
        setup_source=result.setup_source,
        note=result.note,
        n_samples=result.n_samples,
        print_jobs=result.artifact["print_jobs"],
    )


# --- Projekte (ADR-016): dünne Wrapper um fgc.project / actions ---------------


class ProjectSummaryModel(BaseModel):
    """Kurzinfo eines Projekts für die Projektliste (GET /projects)."""

    slug: str
    name: str
    model_path: str
    n_print_jobs: int


class ProjectListResponse(BaseModel):
    """Antwort auf GET /projects: alle Projekte unter projects/."""

    projects: list[ProjectSummaryModel]


class CreateProjectRequest(BaseModel):
    """Parameter für POST /projects — Projekt aus einer IFC-Datei anlegen."""

    name: str
    model_path: str
    robot: str = "doosan_m1013"


@app.get("/projects", response_model=ProjectListResponse)
def get_projects() -> ProjectListResponse:
    """Listet alle Projekte (ADR-016): dünner Wrapper um `fgc.project.list_projects`."""
    from fgc.project import list_projects

    return ProjectListResponse(
        projects=[
            ProjectSummaryModel(
                slug=s.slug,
                name=s.name,
                model_path=s.model_path,
                n_print_jobs=s.n_print_jobs,
            )
            for s in list_projects()
        ]
    )


@app.post("/projects", response_model=ProjectResponse)
def post_projects(req: CreateProjectRequest) -> ProjectResponse:
    """Legt ein Projekt aus einer IFC-Datei an (ADR-016): dieselbe Aktion wie CLI/Wizard.

    Erzeugt Projektordner + project.json + Übersichts-Lauf (Eignungsbefunde) und
    verweist auf den Lauf (nie eingebettet). Reiner Aktions-Wrapper — keine
    Fachlogik in der API.
    """
    from fgc.pipeline.actions import create_project_from_ifc

    model_path = Path(req.model_path)
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"IFC-Modell nicht gefunden: {model_path}")

    source = (
        f"POST /projects name={req.name!r} model={model_path.name} robot={req.robot}"
    )
    try:
        creation = create_project_from_ifc(req.name, model_path, req.robot, source)
    except (KeyError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _project_response(creation.project_dir.name, creation.artifact)


class SetPrintJobRequest(BaseModel):
    """Parameter für PUT /projects/{slug}/print-job — Druckjob setzen oder überschreiben.

    ``assessment_run`` verweist auf den Übersichts-Lauf (walls-list), der die
    Eignungsbefunde enthält. Er wird referenziert, nie eingebettet (ADR-016).
    ``wall_name`` ist optional und nur für die UI-Anzeige — keine normativen Daten.
    Eignung ist ein Befund, kein Gate: auch ungeeignete Wände sind übernehmbar.
    """

    wall_global_id: str
    assessment_run: str
    job_id: str = "default"
    wall_name: str | None = None


@app.put("/projects/{slug}/print-job", response_model=ProjectResponse)
def put_print_job(slug: str, req: SetPrintJobRequest) -> ProjectResponse:
    """Setzt oder überschreibt einen Druckjob im Projekt (ADR-016).

    Dünner Aktions-Wrapper: keine Fachlogik in der API. Die Wand wird im
    Druckjob verewigt; der Befund-Lauf (assessment_run) wird referenziert,
    nicht kopiert — Provenienz bleibt im Übersichts-Lauf (ADR-004/016).
    """
    from fgc.pipeline.actions import set_print_job

    # Der frühere Vorab-``load_project`` trug hier die 404-Semantik (die Aktion
    # fing kein ``FileNotFoundError``). Sie liegt jetzt im ``action_errors``-Seam:
    # ``set_print_job`` lädt das Projekt (über ``mutate_print_job``) und wirft bei
    # fehlendem Projekt ``FileNotFoundError`` → 404 (Issue #118, Regressionstest).
    with action_errors():
        result = set_print_job(
            slug,
            req.wall_global_id,
            req.assessment_run,
            req.job_id,
            wall_name=req.wall_name,
        )

    return _project_response(slug, result.artifact)


class SliceParamsModel(BaseModel):
    """Basis-Slice-Parameter des Druckjobs (Scheibe 2, Issue #59; #60).

    Jedes Feld ist optional (``null`` = nicht gesetzt): nur gesetzte Felder
    überschreiben die Prozessfenster-Karte/Code-Defaults beim Slicen. Alle leer →
    der Block wird entfernt (zurück auf Karten-/Code-Defaults).

    ``v_print_mm_s``/``v_travel_mm_s`` (Druck-/Travel-Geschwindigkeit) und
    ``io_print``/``io_travel`` (io-Wert je Zielart, als Skalar über alle Kanäle)
    sind die „Fortgeschritten"-Felder (Scheibe 2b, Issue #60): existierende
    ``SliceParams``-Werte, die bisher nicht konfigurierbar waren.
    """

    layer_height_mm: float | None = None
    strand_width_mm: float | None = None
    n_shells: int | None = None
    v_print_mm_s: float | None = None
    v_travel_mm_s: float | None = None
    io_print: float | None = None
    io_travel: float | None = None


class OrientationParamsModel(BaseModel):
    """Bahn-relativer Anstellwinkel der Düse (Scheibe 3, Issue #61) — in Grad.

    Jedes Feld optional (``null`` = nicht gesetzt): ``lead_deg`` = Lead-/Lag-Winkel
    (in Fahrtrichtung positiv), ``kipp_deg`` = Kipp-Winkel (zur Wand-Außenseite
    positiv). Alle leer → der Orientierungsblock wird entfernt (senkrecht von oben).
    """

    lead_deg: float | None = None
    kipp_deg: float | None = None


class IkConfigModel(BaseModel):
    """Wählbare IK-Konfiguration (Issue #129, ADR-024) — drei Tri-State-Schalter.

    Je Achse ``"a"`` (Zustand A), ``"b"`` (Zustand B) oder ``null`` (auto = kein
    Constraint, Default). Gesetzte Achsen filtern die 8 Lösungszweige in
    ``select_along_path`` **hart** (Bitschema ``opw.py``: Schulter/Ellbogen/
    Handgelenk). Alle ``null`` → der Block wird entfernt (auto/auto/auto).
    """

    shoulder: Literal["a", "b"] | None = None
    elbow: Literal["a", "b"] | None = None
    wrist: Literal["a", "b"] | None = None


class SectionProcessOverrideModel(BaseModel):
    """Abschnitts-Override der Gradierungs-Ebene (Issue #82; ik_config #129) — sparse.

    Dieselben Gruppen wie global (``slice``/``orientation``/``ik_config``); nur
    gesetzte Felder übersteuern, ungesetzte erben global (``resolve_section_params``).
    """

    slice: SliceParamsModel = SliceParamsModel()
    orientation: OrientationParamsModel = OrientationParamsModel()
    ik_config: IkConfigModel = IkConfigModel()


class SetProcessParamsRequest(BaseModel):
    """Parameter für PUT /projects/{slug}/process-params (Scheibe 2/3/S3, #59/#61/#82).

    ``slice`` trägt die Basis-Slice-Parameter, ``orientation`` den bahn-relativen
    Anstellwinkel (Grad); ``job_id`` ist der Druckjob, dessen ``process_params``-
    Gruppen gesetzt werden. ``sections`` bildet ``section_id`` → Abschnitts-Override
    ab (Gradierungs-Ebene, Issue #82; ``None`` = bestehende Abschnitts-Overrides
    unberührt lassen). Die Änderung veraltet Zerlegung/Simulation/Export
    (veraltet-Markierung, ADR-017).
    """

    slice: SliceParamsModel = SliceParamsModel()
    orientation: OrientationParamsModel = OrientationParamsModel()
    ik_config: IkConfigModel = IkConfigModel()
    sections: dict[str, SectionProcessOverrideModel] | None = None
    job_id: str = "default"


@app.put("/projects/{slug}/process-params", response_model=ProjectResponse)
def put_process_params(slug: str, req: SetProcessParamsRequest) -> ProjectResponse:
    """Setzt die Prozessparameter (Slice-Basis) eines Druckjobs (Scheibe 2, Issue #59).

    Dünner Aktions-Wrapper (ADR-014): ruft `set_process_params`, das den
    ``process_params.slice``-Block schema-validiert in den Druckjob schreibt
    (`fgc.project` = einzige Schreibstelle, ADR-016) und die Prozessparameter-
    Revision bumpt → nachgelagerte Stände veralten sichtbar (ADR-017). Danach liest
    `simulate_section` die Slice-Parameter aus dem Job statt nur aus der Karte.
    """
    from fgc.pipeline.actions import set_process_params

    with action_errors():
        result = set_process_params(
            slug,
            req.slice.model_dump(),
            req.job_id,
            orientation=req.orientation.model_dump(),
            ik_config=req.ik_config.model_dump(),
            sections=(
                {sid: ov.model_dump() for sid, ov in req.sections.items()}
                if req.sections is not None
                else None
            ),
        )

    return _project_response(slug, result.artifact)


class SetRobotRequest(BaseModel):
    """Parameter für PUT /projects/{slug}/robot — Roboterwahl + Neubewertung (Issue #20).

    ``robot`` ist der Name der Roboterdefinition aus ``robots/``; ``job_id`` ist
    der Druckjob, dessen ``assessment_run`` und ``robot``-Feld aktualisiert werden.
    Die Neubewertung erzeugt einen regulären Laufordner (ADR-004): provenienzgestempelt,
    schema-validiert, reproduzierbar.
    """

    robot: str
    job_id: str = "default"


@app.put("/projects/{slug}/robot", response_model=ProjectResponse)
def put_robot(slug: str, req: SetRobotRequest) -> ProjectResponse:
    """Roboterwahl + Neubewertung für einen Druckjob (Issue #20).

    Erzeugt einen neuen Befund-Lauf (walls-list) für den gewählten Roboter,
    aktualisiert ``project.overview_run`` (damit die Modellübersicht neu einfärbt)
    und setzt im Druckjob ``assessment_run`` + ``robot``. Dünner Aktions-Wrapper —
    keine Fachlogik in der API (ADR-014).
    """
    from fgc.pipeline.actions import reassess_walls_for_robot

    source = f"PUT /projects/{slug}/robot robot={req.robot} job_id={req.job_id}"
    with action_errors():
        result = reassess_walls_for_robot(slug, req.robot, source, req.job_id)

    return _project_response(slug, result.artifact)


@app.get("/projects/{slug}", response_model=ProjectResponse)
def get_project(slug: str) -> ProjectResponse:
    """Lädt ein Projekt (ADR-016): dünner Wrapper um `fgc.project.load_project`."""
    from fgc.project import load_project, project_dir_for

    try:
        artifact = load_project(project_dir_for(slug))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _project_response(slug, artifact)


@app.post("/slice", response_model=SliceResponse)
def post_slice(req: SliceRequest) -> SliceResponse:
    """Sliced eine Wand (ADR-014): dieselbe Aktion wie `fgc slice`.

    Erzeugt einen regulären Laufordner mit schema-validierten Artefakten inkl.
    Provenienz (ADR-004 bleibt unangetastet). Antwort referenziert den
    Laufordner; der Viewer lädt die Artefakte von dort.
    """
    from fgc.domain.process_params import ProcessWindow, SliceParams
    from fgc.pipeline.actions import slice_to_run

    model_path = Path(req.model_path)
    window = ProcessWindow.load()
    params = SliceParams.from_window(
        window,
        layer_height_mm=req.layer_height_mm,
        strand_width_mm=req.strand_width_mm,
        n_shells=req.n_shells,
    )

    try:
        wall = ifc_walls.load_wall(model_path, req.global_id)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    source = _api_slice_source(model_path, req.global_id, params)
    run = slice_to_run(model_path, wall, params, source, with_context=req.with_context)

    if run is None:
        raise HTTPException(
            status_code=422,
            detail="Slicer lieferte keine Targets (Konturen degeneriert?)",
        )

    return SliceResponse(run_dir=str(run.run_dir), **run.toolpath.summary())
