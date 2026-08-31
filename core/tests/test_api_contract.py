"""Kontrakt-Orakel für ``viewer/src/api/projects.ts`` (Issue #202).

Der breiteste Seam des Systems — ``projects.ts`` (30 Fetch-Wrapper, 52 hand-
gepflegte Typen) als Spiegel der Pydantic-Antwortmodelle in ``fgc.pipeline.api``
— hatte kein Testorakel: der TS-Compiler prüft die Fiktion nur gegen sich
selbst. Feld-Drift in einem Antwortmodell (Umbenennung, Wegfall) blieb grün und
brach erst zur GUI-Laufzeit.

Dieses Modul schließt die Lücke mit **Golden-Responses**: die Core-TestClient-
Erfolgspfade legen je Route eine echte Antwort als ``*.contract.json`` unter
``viewer/src/api/contract/`` ab; der TS-Test ``projects.contract.test.ts`` weist
jede Golden ihrem Spiegel-Typ zu (``tsc``-Strukturprüfung über ``Wire<T>``), so
dass eine Feld-Umbenennung in ``api.py`` den Viewer-Build rot färbt.

**Eigenes Namensschema, bewusst NICHT ``*.golden.json``:** die Endung
``.golden.json`` ist in diesem Repo die erzwungene Invariante der Py↔TS-
Paritäts-Familie („jede Golden-Datei ist im ``fgc.parity``-MANIFEST registriert",
Wächter ``test_parity.py::test_every_golden_registered``). Die Kontrakt-Familie
ist keine Paritäts-Familie (kein TS-Zwilling, siehe unten) und trägt darum
``.contract.json`` — mit eigener zweiseitiger Registratur: :data:`COVERED` ↔
Dateien auf Platte (:func:`test_covered_routes_have_golden_files` und
:func:`test_no_unregistered_contract_files`).

**Eigenständige Familie, nicht ``fgc.parity``** (Design-Log 2026-07-13): das
Paritäts-Harness beweist *Zwillingsfunktions*-Parität (Py ``fn(case)`` gegen einen
TS-Zwilling, beide gegen ein Golden verglichen). Hier gibt es keinen TS-Zwilling,
der etwas nachrechnet — die Golden IST die Core-Antwort, der Beweis ist die
*strukturelle Typ-Konformität* dieser Antwort gegen den handgepflegten Spiegel,
erzwungen von ``tsc``. Ein Zwang ins ``register(pair, fn, cases, compare, …)``-
Skelett würde ``fn``/``compare`` missbrauchen (es gibt keine Python-Neuableitung
zum Vergleichen). Wiederverwendet werden die *Hauskonventionen* (eingecheckte
Golden-JSON, ein Gen-Treiber, ein schneller Leser/Enforcement-Test), nicht die
Mechanik.

Zwei Teile:

- :func:`test_every_response_model_route_has_contract` (schnell, immer): jede
  Route mit ``response_model`` ist entweder abgedeckt (Golden liegt) ODER als
  ``TODO`` mit Grund verzeichnet — kein stilles Loch. Zugleich ist die
  eingecheckte ``contract-manifest.json`` frisch (der TS-Test liest sie).
- :func:`test_regenerate_api_goldens` (nur mit ``FGC_REGEN_API_GOLDENS=1``):
  fährt die Erfolgspfade über den TestClient und schreibt die Golden + das
  Manifest. Pfade werden sanitisiert (reproduzierbar, maschinenunabhängig).

Neu erzeugen (vom Repo-Root, venv):

    FGC_REGEN_API_GOLDENS=1 .venv/Scripts/python.exe -m pytest \
        core/tests/test_api_contract.py -k regenerate -q
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from fgc.paths import REPO_ROOT
from fgc.pipeline import runfolder
from fgc.pipeline.api import app
from fgc.project import store as project_store

CONTRACT_DIR = REPO_ROOT / "viewer" / "src" / "api" / "contract"
MANIFEST_PATH = CONTRACT_DIR / "contract-manifest.json"

ROBOT = "doosan_m1013"
TOOL = "30gut"  # tools/30gut.json (im Repo abgelegter Referenz-Endeffektor)
WORKSTATION = "mobile_hub"  # workstations/mobile_hub.json (mobil, ungetaggt)


# =================================================================================
# Registratur: welche Route trägt welche Golden gegen welchen projects.ts-Typ
# =================================================================================
#
# Schlüssel = "<METHOD> <path>" (der Routen-Schlüssel). ``golden`` = Dateibasis
# unter CONTRACT_DIR; ``ts_type`` = der Spiegel-Typ in projects.ts (rein
# informativ fürs Manifest — die echte tsc-Prüfung steht im TS-Test); ``unwrap``
# = der Umschlag-Schlüssel für Listen-Routen (die TS-Wrapper entpacken ihn).


class Covered:
    def __init__(self, golden: str, ts_type: str, unwrap: str | None = None) -> None:
        self.golden = golden
        self.ts_type = ts_type
        self.unwrap = unwrap


COVERED: dict[str, Covered] = {
    "GET /robots": Covered("robots", "RobotDef[]", unwrap="robots"),
    "GET /tools": Covered("tools", "ToolDef[]", unwrap="tools"),
    "GET /workstations": Covered("workstations", "WorkstationDef[]", unwrap="workstations"),
    "GET /projects": Covered("projects", "ProjectSummary[]", unwrap="projects"),
    "POST /projects": Covered("project-create", "Project"),
    "GET /projects/{slug}": Covered("project-get", "Project"),
    "PUT /projects/{slug}/print-job": Covered("project-print-job", "Project"),
    "PUT /projects/{slug}/robot": Covered("project-robot", "Project"),
    "PUT /projects/{slug}/process-params": Covered("project-process-params", "Project"),
    "PUT /projects/{slug}/tool": Covered("set-tool", "SetToolResult"),
    "PUT /projects/{slug}/workstation": Covered("set-workstation", "SetWorkstationResult"),
    "PUT /projects/{slug}/stand-mode": Covered("set-stand-mode", "SetStandModeResult"),
    "PUT /projects/{slug}/context-check": Covered("set-context-check", "SetContextCheckResult"),
    "PUT /projects/{slug}/module-limits": Covered("set-module-limits", "SetModuleLimitsResult"),
    "PUT /projects/{slug}/objective": Covered("set-objective", "SetObjectiveResult"),
    "PUT /projects/{slug}/placement-override": Covered(
        "set-placement-override", "SetPlacementOverrideResult"
    ),
    "POST /projects/{slug}/decomposition": Covered("decomposition", "DecompositionResult"),
    "POST /projects/{slug}/decomposition-check": Covered(
        "decomposition-check", "DecompositionCheckStatus"
    ),
    "POST /projects/{slug}/decomposition-beam": Covered(
        "decomposition-beam", "BeamProposeStatus"
    ),
    "POST /projects/{slug}/sections/{section_id}/simulate": Covered(
        "simulate-section", "SimulateSectionResult"
    ),
    "POST /projects/{slug}/sections/{section_id}/export": Covered(
        "export-section", "ExportDrlResult"
    ),
}

#: Bewusst (noch) nicht abgedeckte Routen — sichtbar statt still (AC #202).
TODO: dict[str, str] = {
    "POST /tools": (
        "Mesh-Upload-Fixture nötig (base64-STL); ToolDef-Spiegel via GET /tools abgedeckt."
    ),
    "PUT /tools/{name}": (
        "Mesh-Upload-Fixture nötig; ToolDef-Spiegel via GET /tools abgedeckt."
    ),
    "POST /workstations": "WorkstationDef-Spiegel via GET /workstations abgedeckt.",
    "PUT /workstations/{name}": "WorkstationDef-Spiegel via GET /workstations abgedeckt.",
    "POST /workstations/{name}/detect-base-holes": (
        "DetectHolesResult-Spiegel: braucht ein Workstation-Mesh mit passendem "
        "Roboter-Bohrbild (Folgeticket)."
    ),
    "POST /projects/{slug}/singularity-advice": (
        "SingularityAdvice/-Suggestion-Spiegel: Advisor kann leer antworten "
        "(advice=null); repräsentative Golden als Folgeticket."
    ),
    "POST /projects/{slug}/collision-advice": (
        "CollisionAdvice/-Option/-Baseline/-Write-Spiegel: teure Neu-Simulation "
        "(Minuten); Golden als Folgeticket."
    ),
    "POST /projects/{slug}/placements": (
        "Kein projects.ts-Spiegel mehr (Wrapper mit #134 entfallen)."
    ),
    "POST /projects/{slug}/placement-suggestion": (
        "Seit #231 wieder ein lesender Spiegel (PlacementSuggestionResult, "
        "Ampel-Anzeige) — noch keine Golden-Kontraktprüfung; Feld-Drift bleibt "
        "vorerst ungeprüft (Folgeticket)."
    ),
    "PUT /projects/{slug}/placement-selection": (
        "Kein projects.ts-Spiegel mehr (Wrapper mit #134 entfallen)."
    ),
    "GET /projects/{slug}/decomposition-check/{check_id}": (
        "Gleiches Modell (DecompositionCheckStatus) wie POST …/decomposition-check "
        "(dort abgedeckt); done/cancelled-Varianten als Folgeticket."
    ),
    "POST /projects/{slug}/decomposition-check/{check_id}/cancel": (
        "Gleiches Modell (DecompositionCheckStatus) wie POST …/decomposition-check (abgedeckt)."
    ),
    "GET /projects/{slug}/decomposition-beam/{beam_id}": (
        "Gleiches Modell (BeamProposeStatus) wie POST …/decomposition-beam "
        "(dort abgedeckt); done-Variante mit Sieger/refinement als Folgeticket."
    ),
    "POST /projects/{slug}/decomposition-beam/{beam_id}/cancel": (
        "Gleiches Modell (BeamProposeStatus) wie POST …/decomposition-beam (abgedeckt)."
    ),
    "POST /slice": (
        "SliceResponse liegt in client.ts (außerhalb projects.ts); via http.test.ts abgedeckt."
    ),
    "DELETE /tools/{name}": "response_model=dict ({deleted}); kein strukturierter Spiegel.",
    "DELETE /workstations/{name}": "response_model=dict ({deleted}); kein strukturierter Spiegel.",
}


def _route_key(route: object) -> str:
    method = sorted(route.methods)[0]  # type: ignore[attr-defined]
    return f"{method} {route.path}"  # type: ignore[attr-defined]


def response_model_routes() -> list[tuple[str, str]]:
    """(Routen-Schlüssel, Modellname) je Route mit ``response_model`` (sortiert)."""
    out: list[tuple[str, str]] = []
    for route in app.routes:
        model = getattr(route, "response_model", None)
        if model is None:
            continue
        name = getattr(model, "__name__", str(model))
        out.append((_route_key(route), name))
    return sorted(set(out))


def build_manifest() -> dict:
    """Das Manifest, das der TS-Test liest — deterministisch aus Routen + Registratur."""
    routes = []
    for key, model in response_model_routes():
        if key in COVERED:
            c = COVERED[key]
            routes.append(
                {
                    "route": key,
                    "model": model,
                    "status": "covered",
                    "golden": c.golden,
                    "ts_type": c.ts_type,
                    **({"unwrap": c.unwrap} if c.unwrap else {}),
                }
            )
        else:
            routes.append(
                {"route": key, "model": model, "status": "todo", "reason": TODO.get(key, "")}
            )
    return {
        "_comment": (
            "Kontrakt-Manifest der API-Golden-Familie (Issue #202) — erzeugt von "
            "core/tests/test_api_contract.py; nicht von Hand editieren."
        ),
        "routes": routes,
    }


# =================================================================================
# Enforcement (schnell, immer): kein stilles Loch + Manifest frisch
# =================================================================================


def test_every_response_model_route_has_contract():
    """Jede Route mit ``response_model`` ist Golden ODER TODO — nie stillschweigend offen."""
    keys = {key for key, _ in response_model_routes()}
    for key in sorted(keys):
        assert key in COVERED or key in TODO, (
            f"Route {key!r} hat weder eine Golden noch einen TODO-Eintrag — stilles Loch (#202)."
        )
    # Keine Karteileichen: jeder Registratur-Eintrag zeigt auf eine echte Route.
    for key in list(COVERED) + list(TODO):
        assert key in keys, f"Registratur-Eintrag {key!r} zeigt auf keine Route mit response_model."


def test_covered_routes_have_golden_files():
    """Für jede abgedeckte Route liegt die Golden-Datei eingecheckt vor."""
    for key, c in COVERED.items():
        path = CONTRACT_DIR / f"{c.golden}.contract.json"
        assert path.is_file(), (
            f"{key}: Golden {c.golden}.contract.json fehlt — "
            f"FGC_REGEN_API_GOLDENS=1 pytest -k regenerate laufen lassen."
        )
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc, f"{key}: Golden {c.golden}.contract.json ist leer."


def test_no_unregistered_contract_files():
    """Jede ``*.contract.json`` auf Platte gehört zu einem COVERED-Eintrag (Rückrichtung).

    Spiegel des Paritäts-Wächters ``test_every_golden_registered`` für die
    Kontrakt-Familie: eine Golden, die niemand einer Route zuordnet, wird von
    keinem Typ-Check gelesen — sichtbar statt still. Zugleich der Beleg der
    Namens-Abgrenzung: unter ``viewer/src`` liegt KEINE ``*.golden.json`` dieser
    Familie (die Endung gehört exklusiv dem ``fgc.parity``-Manifest).
    """
    on_disk = {p.name for p in CONTRACT_DIR.glob("*.contract.json")}
    registered = {f"{c.golden}.contract.json" for c in COVERED.values()}
    assert on_disk == registered, (
        f"Kontrakt-Dateien und Registratur driften: nur auf Platte "
        f"{sorted(on_disk - registered)}, nur registriert {sorted(registered - on_disk)}."
    )
    # Abgrenzung zur Paritäts-Familie: kein .golden.json im Kontrakt-Verzeichnis.
    assert not list(CONTRACT_DIR.glob("*.golden.json")), (
        "Kontrakt-Goldens heißen *.contract.json — .golden.json ist die Endung der "
        "fgc.parity-Familie (test_parity.py::test_every_golden_registered)."
    )


def test_contract_manifest_is_fresh():
    """Die eingecheckte contract-manifest.json entspricht Routen + Registratur."""
    assert MANIFEST_PATH.is_file(), "contract-manifest.json fehlt (regenerate laufen lassen)."
    on_disk = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert on_disk == build_manifest(), (
        "contract-manifest.json ist veraltet — FGC_REGEN_API_GOLDENS=1 "
        "pytest -k regenerate laufen lassen (oder Registratur/Routen synchronisieren)."
    )


# =================================================================================
# Gen-Treiber (nur mit FGC_REGEN_API_GOLDENS=1): Golden aus Erfolgspfaden schreiben
# =================================================================================


def _sanitize(obj, replacements: list[tuple[str, str]]):
    """Ersetzt maschinen-spezifische Pfad-Präfixe rekursiv durch stabile Platzhalter."""
    if isinstance(obj, str):
        s = obj
        for needle, repl in replacements:
            s = s.replace(needle, repl)
            s = s.replace(needle.replace("\\", "/"), repl)
        return s
    if isinstance(obj, list):
        return [_sanitize(v, replacements) for v in obj]
    if isinstance(obj, dict):
        return {k: _sanitize(v, replacements) for k, v in obj.items()}
    return obj


@pytest.mark.skipif(
    not os.environ.get("FGC_REGEN_API_GOLDENS"),
    reason="Golden-Regen nur mit FGC_REGEN_API_GOLDENS=1 (schreibt Dateien)",
)
def test_regenerate_api_goldens(tmp_path, monkeypatch, install_walls, make_wall):
    """Fährt die Erfolgspfade über den TestClient und schreibt Golden + Manifest."""
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    projects_dir.mkdir()
    runs_dir.mkdir()
    monkeypatch.setattr(project_store, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(runfolder, "RUNS_DIR", runs_dir)
    # Überhohe Wand (2600 mm) → echte Zerlegung mit Höhenstufen (reales trimesh-Mesh).
    install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", length=800.0, height=2600.0)])

    replacements = [
        (str(tmp_path), "<tmp>"),
        (str(tmp_path.resolve()), "<tmp>"),
        (str(REPO_ROOT), "<repo>"),
        (str(REPO_ROOT.resolve()), "<repo>"),
    ]
    written: dict[str, dict] = {}

    def capture(key: str, body: dict) -> dict:
        c = COVERED[key]
        clean = _sanitize(body, replacements)
        path = CONTRACT_DIR / f"{c.golden}.contract.json"
        path.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written[key] = clean
        return body

    client = TestClient(app)
    model = tmp_path / "modell.ifc"
    model.write_text("dummy", encoding="utf-8")

    # Kataloge (reale robots/tools/workstations-Verzeichnisse → reproduzierbar).
    capture("GET /robots", client.get("/robots").json())
    capture("GET /tools", client.get("/tools").json())
    capture("GET /workstations", client.get("/workstations").json())

    # Projekt anlegen + Umschlag-Familie.
    created = capture(
        "POST /projects",
        client.post("/projects", json={"name": "Kontrakthaus", "model_path": str(model)}).json(),
    )
    slug = created["slug"]
    overview_run = created["overview_run"]
    capture("GET /projects", client.get("/projects").json())
    capture("GET /projects/{slug}", client.get(f"/projects/{slug}").json())
    capture(
        "PUT /projects/{slug}/print-job",
        client.put(
            f"/projects/{slug}/print-job",
            json={"wall_global_id": "WALLAAAAAAAAAAAAAAAAAA", "assessment_run": overview_run},
        ).json(),
    )
    capture(
        "PUT /projects/{slug}/robot",
        client.put(f"/projects/{slug}/robot", json={"robot": ROBOT}).json(),
    )
    capture(
        "PUT /projects/{slug}/tool",
        client.put(f"/projects/{slug}/tool", json={"tool": TOOL, "job_id": "default"}).json(),
    )
    capture(
        "PUT /projects/{slug}/workstation",
        client.put(
            f"/projects/{slug}/workstation", json={"workstation": WORKSTATION, "job_id": "default"}
        ).json(),
    )
    capture(
        "PUT /projects/{slug}/stand-mode",
        client.put(f"/projects/{slug}/stand-mode", json={"stand_mode": "elevated"}).json(),
    )
    capture(
        "PUT /projects/{slug}/context-check",
        client.put(f"/projects/{slug}/context-check", json={"check_building_context": True}).json(),
    )
    capture(
        "PUT /projects/{slug}/module-limits",
        client.put(
            f"/projects/{slug}/module-limits", json={"max_length_mm": None, "max_height_mm": 1400.0}
        ).json(),
    )
    capture(
        "PUT /projects/{slug}/objective",
        client.put(
            f"/projects/{slug}/objective",
            json={
                "aufwiegen": False,
                "weights": {
                    "umsetzvorgaenge": 8.0,
                    "fugenflaeche": 3.0,
                    "kinematische_marge": 2.0,
                    "volumen_cv": 1.0,
                },
            },
        ).json(),
    )
    capture(
        "PUT /projects/{slug}/process-params",
        client.put(
            f"/projects/{slug}/process-params",
            json={
                "slice": {"layer_height_mm": 9.0, "n_shells": 3},
                "orientation": {"kipp_deg": 5.0},
            },
        ).json(),
    )

    # Zerlegung (rich!) + davon abhängige Routen.
    decomp = capture(
        "POST /projects/{slug}/decomposition",
        client.post(
            f"/projects/{slug}/decomposition",
            json={"cuts": [{"orientation": "horizontal", "position_mm": 1300.0}]},
        ).json(),
    )
    section_id = decomp["sections"][0]["section_id"]
    capture(
        "PUT /projects/{slug}/placement-override",
        client.put(
            f"/projects/{slug}/placement-override",
            json={"section_id": section_id, "standoff_mm": 750.0},
        ).json(),
    )
    capture(
        "POST /projects/{slug}/decomposition-check",
        client.post(
            f"/projects/{slug}/decomposition-check", json={"focus_section_id": section_id}
        ).json(),
    )
    # Beam-Zerlegungslauf anstoßen (Issue #221): der Start kehrt sofort mit
    # ``state="running"`` zurück (Hintergrundlauf) — ein Running-Snapshot als Golden,
    # wie bei decomposition-check. Sieger/refinement (done-Variante) sind ein
    # Folgeticket (im Manifest als TODO an der GET-Route vermerkt).
    capture(
        "POST /projects/{slug}/decomposition-beam",
        client.post(f"/projects/{slug}/decomposition-beam", json={}).json(),
    )
    capture(
        "POST /projects/{slug}/sections/{section_id}/simulate",
        client.post(f"/projects/{slug}/sections/{section_id}/simulate", json={}).json(),
    )
    capture(
        "POST /projects/{slug}/sections/{section_id}/export",
        client.post(f"/projects/{slug}/sections/{section_id}/export", json={}).json(),
    )

    # Manifest schreiben und Vollständigkeit sicherstellen.
    MANIFEST_PATH.write_text(
        json.dumps(build_manifest(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    missing = set(COVERED) - set(written)
    assert not missing, f"Nicht alle abgedeckten Routen wurden erzeugt: {sorted(missing)}"
