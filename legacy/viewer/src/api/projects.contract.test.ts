/**
 * Kontrakt-Orakel für die projects.ts-Spiegel-Typen (Issue #202).
 *
 * `projects.ts` pflegt 52 Typen von Hand als Spiegel der Pydantic-Antwortmodelle
 * in `core/src/fgc/pipeline/api.py`. Bis hierhin prüfte der TS-Compiler die Fiktion
 * nur gegen sich selbst — eine Feld-Umbenennung in einem Antwortmodell blieb grün und
 * brach erst zur GUI-Laufzeit. Dieses Orakel schließt die Lücke:
 *
 * Der Core legt je Route eine **echte** Golden-Response ab
 * (`contract/*.contract.json`, erzeugt von `core/tests/test_api_contract.py` —
 * bewusst NICHT `*.golden.json`: die Endung gehört exklusiv der Py↔TS-Paritäts-
 * Familie und ihrem Wächter `test_parity.py::test_every_golden_registered`); hier
 * wird jede Golden ihrem Spiegel-Typ **strukturell zugewiesen**. Läuft `tsc --noEmit`
 * (`npm run build`), erzwingt es damit, dass jedes Pflichtfeld des Spiegels in der
 * Core-Antwort vorkommt — fehlt/verschiebt sich eines (Drift in api.py), wird der
 * Viewer-Build rot.
 *
 * `Wire<T>` weitet String-/Zahl-**Literal-Unions** (`"a" | "b"`, `"floor" | …`) auf
 * ihren Basistyp: JSON-Importe tragen keine Literaltypen (`"floor"` ist `string`),
 * würden also gegen die engen Unions falsch-positiv anschlagen. Feldname, Präsenz und
 * Basistyp (string↔number↔boolean) bleiben scharf geprüft — genau die Drift, die zählt.
 *
 * Grenze (bewusst, v1): ein **zusätzliches** Feld in api.py ohne Spiegel-Feld bleibt
 * unbemerkt (strukturelle Zuweisung erlaubt Extra-Felder auf Werten). Umbenennung,
 * Wegfall und Typwechsel eines Pflichtfelds werden erkannt — das ist die Drift-Klasse
 * der Akzeptanz (#202).
 */
import { describe, expect, it } from "vitest";

import type {
  BeamProposeStatus,
  DecompositionCheckStatus,
  DecompositionResult,
  ExportDrlResult,
  PlacementOverrideValues,
  Project,
  ProjectSummary,
  RobotDef,
  SetContextCheckResult,
  SetModuleLimitsResult,
  SetObjectiveResult,
  SetPlacementOverrideResult,
  SetStandModeResult,
  SetToolResult,
  SetWorkstationResult,
  SimulateSectionResult,
  ToolDef,
  WorkstationDef,
} from "./projects";

import manifest from "./contract/contract-manifest.json";
import robotsGolden from "./contract/robots.contract.json";
import toolsGolden from "./contract/tools.contract.json";
import workstationsGolden from "./contract/workstations.contract.json";
import projectsGolden from "./contract/projects.contract.json";
import projectCreateGolden from "./contract/project-create.contract.json";
import projectGetGolden from "./contract/project-get.contract.json";
import projectPrintJobGolden from "./contract/project-print-job.contract.json";
import projectRobotGolden from "./contract/project-robot.contract.json";
import projectProcessParamsGolden from "./contract/project-process-params.contract.json";
import setToolGolden from "./contract/set-tool.contract.json";
import setWorkstationGolden from "./contract/set-workstation.contract.json";
import setStandModeGolden from "./contract/set-stand-mode.contract.json";
import setContextCheckGolden from "./contract/set-context-check.contract.json";
import setModuleLimitsGolden from "./contract/set-module-limits.contract.json";
import setObjectiveGolden from "./contract/set-objective.contract.json";
import setPlacementOverrideGolden from "./contract/set-placement-override.contract.json";
import decompositionGolden from "./contract/decomposition.contract.json";
import decompositionCheckGolden from "./contract/decomposition-check.contract.json";
import decompositionBeamGolden from "./contract/decomposition-beam.contract.json";
import simulateSectionGolden from "./contract/simulate-section.contract.json";
import exportSectionGolden from "./contract/export-section.contract.json";

/**
 * Weitet Literal-Unions auf ihren Basistyp, erhält aber Feldnamen, Präsenz
 * (`?`), Verschachtelung und die string/number/boolean-Unterscheidung.
 */
type Wire<T> = T extends (infer U)[]
  ? Wire<U>[]
  : T extends object
    ? { [K in keyof T]: Wire<T[K]> }
    : T extends string
      ? string
      : T extends number
        ? number
        : T extends boolean
          ? boolean
          : T;

/**
 * Die eine tsc-Prüftür: `conforms<T>(golden)` verlangt, dass `golden` strukturell
 * `Wire<T>` erfüllt. Der Aufruf wird von `tsc` (npm run build) geprüft; zur
 * Laufzeit reicht die Golden unverändert durch (vitest belegt zusätzlich, dass sie
 * geladen und nicht leer ist).
 */
function conforms<T>(golden: Wire<T>): Wire<T> {
  return golden;
}

/** Jede Golden gegen ihren projects.ts-Spiegel — die eigentliche Kontraktprüfung. */
const CHECKS: Record<string, () => unknown> = {
  "GET /robots": () => conforms<RobotDef[]>(robotsGolden.robots),
  "GET /tools": () => conforms<ToolDef[]>(toolsGolden.tools),
  "GET /workstations": () => conforms<WorkstationDef[]>(workstationsGolden.workstations),
  "GET /projects": () => conforms<ProjectSummary[]>(projectsGolden.projects),
  "POST /projects": () => conforms<Project>(projectCreateGolden),
  "GET /projects/{slug}": () => conforms<Project>(projectGetGolden),
  "PUT /projects/{slug}/print-job": () => conforms<Project>(projectPrintJobGolden),
  "PUT /projects/{slug}/robot": () => conforms<Project>(projectRobotGolden),
  "PUT /projects/{slug}/process-params": () => conforms<Project>(projectProcessParamsGolden),
  "PUT /projects/{slug}/tool": () => conforms<SetToolResult>(setToolGolden),
  "PUT /projects/{slug}/workstation": () => conforms<SetWorkstationResult>(setWorkstationGolden),
  "PUT /projects/{slug}/stand-mode": () => conforms<SetStandModeResult>(setStandModeGolden),
  "PUT /projects/{slug}/context-check": () =>
    conforms<SetContextCheckResult>(setContextCheckGolden),
  "PUT /projects/{slug}/module-limits": () =>
    conforms<SetModuleLimitsResult>(setModuleLimitsGolden),
  "PUT /projects/{slug}/objective": () => conforms<SetObjectiveResult>(setObjectiveGolden),
  // Befund des Orakels (#202, Design-Log 2026-07-13): der Spiegel typt `override`
  // als `SectionOverride | Record<string,never>`, aber `SectionOverride.section_id`
  // ist Pflicht — die echte Antwort trägt im `override`-Feld NUR die sparse freien
  // Werte (`{standoff_mm}`, ohne `section_id`; das steht separat als Geschwisterfeld).
  // Der akkurate Kontrakt ist `PlacementOverrideValues` (bestehender projects.ts-Typ).
  // Die 52 Typen bleiben unberührt (AC); die Imprecision ist ein Folgeticket wert.
  "PUT /projects/{slug}/placement-override": () =>
    conforms<Omit<SetPlacementOverrideResult, "override"> & { override: PlacementOverrideValues }>(
      setPlacementOverrideGolden,
    ),
  "POST /projects/{slug}/decomposition": () => conforms<DecompositionResult>(decompositionGolden),
  "POST /projects/{slug}/decomposition-check": () =>
    conforms<DecompositionCheckStatus>(decompositionCheckGolden),
  "POST /projects/{slug}/decomposition-beam": () =>
    conforms<BeamProposeStatus>(decompositionBeamGolden),
  "POST /projects/{slug}/sections/{section_id}/simulate": () =>
    conforms<SimulateSectionResult>(simulateSectionGolden),
  "POST /projects/{slug}/sections/{section_id}/export": () =>
    conforms<ExportDrlResult>(exportSectionGolden),
};

describe("API-Kontrakt: Golden-Responses gegen die projects.ts-Spiegel", () => {
  it("deckt jede abgedeckte Manifest-Route mit genau einer Kontraktprüfung ab", () => {
    const covered = manifest.routes
      .filter((r) => r.status === "covered")
      .map((r) => r.route)
      .sort();
    expect(Object.keys(CHECKS).sort()).toEqual(covered);
  });

  for (const [route, check] of Object.entries(CHECKS)) {
    it(`${route}: Golden lädt und erfüllt ihren Spiegel-Typ (tsc)`, () => {
      const golden = check();
      expect(golden).toBeTruthy();
    });
  }
});

describe("API-Kontrakt: kein stilles Loch (Manifest-Spiegel)", () => {
  it("jede Route im Manifest ist covered oder todo — nie stillschweigend offen", () => {
    for (const r of manifest.routes) {
      expect(["covered", "todo"], `${r.route}: unbekannter Status`).toContain(r.status);
      if (r.status === "todo") {
        expect(r.reason, `${r.route}: TODO ohne Begründung`).toBeTruthy();
      }
    }
  });

  it("führt mindestens die 21 abgedeckten Routen und die bekannten TODOs", () => {
    const covered = manifest.routes.filter((r) => r.status === "covered");
    const todo = manifest.routes.filter((r) => r.status === "todo");
    expect(covered.length).toBe(21);
    expect(todo.length).toBeGreaterThanOrEqual(10);
  });
});
