import { describe, expect, it } from "vitest";

import { expectGoldenParity } from "../test/golden-parity";
import golden from "./staleness.golden.json";
import sectionGolden from "./staleness-section.golden.json";
import {
  INPUT_KEYS,
  OUTPUT_DEPS,
  type OutputName,
  type Revisions,
  SECTION_AGGREGATE_OUTPUTS,
  SECTION_OUTPUT_JOB_DEPS,
  type SectionOutputName,
  allSectionStageStatuses,
  allStageStatuses,
  isStale,
  sectionStageStatus,
  stageStatus,
} from "./staleness";

/** Baut Revisionsstände: Eingabe-Zähler + je Output ein Schnappschuss. */
function rev(
  inputs: Revisions["inputs"],
  outputs: Revisions["outputs"] = {},
): Revisions {
  return { inputs, outputs };
}

describe("staleness (veraltet-Markierung, Issue #29)", () => {
  it("Projekt ohne Revisionsfeld gilt als nicht veraltet (rückwärtskompatibel)", () => {
    expect(allStageStatuses(undefined)).toEqual({
      druckplan: "current",
      simulation: "current",
      export: "current",
    });
    expect(stageStatus({}, "export")).toBe("current");
  });

  it("Output ohne Schnappschuss ist 'missing', nach Erzeugung 'current'", () => {
    const inputs = { wall: 1, robot: 1, tool: 0, cutplan: 1 };
    expect(stageStatus(rev(inputs), "druckplan")).toBe("missing");
    const withOutput = rev(inputs, { druckplan: { wall: 1, robot: 1, tool: 0 } });
    expect(stageStatus(withOutput, "druckplan")).toBe("current");
  });

  it("Roboterwechsel markiert Druckplan/Simulation/Export als veraltet", () => {
    // Alle drei bei robot=1 erzeugt, dann robot → 2 (Roboterwechsel).
    const revisions = rev(
      { wall: 1, robot: 2, tool: 0, cutplan: 1 },
      {
        druckplan: { wall: 1, robot: 1, tool: 0 },
        simulation: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
        export: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
      },
    );
    const status = allStageStatuses(revisions);
    expect(status).toEqual({
      druckplan: "stale",
      simulation: "stale",
      export: "stale",
    });
    expect(isStale(status.export)).toBe(true);
  });

  it("Neubewertung hebt die Markierung stufenweise auf", () => {
    const inputs = { wall: 1, robot: 2, tool: 0, cutplan: 1 };
    // Druckplan bei robot=2 neu erzeugt → aktuell; Sim/Export noch veraltet.
    let revisions = rev(inputs, {
      druckplan: { wall: 1, robot: 2, tool: 0 },
      simulation: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
      export: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
    });
    let status = allStageStatuses(revisions);
    expect(status.druckplan).toBe("current");
    expect(status.simulation).toBe("stale");
    expect(status.export).toBe("stale");

    // Dann Simulation neu → aktuell; Export noch veraltet.
    revisions = rev(inputs, {
      druckplan: { wall: 1, robot: 2, tool: 0 },
      simulation: { wall: 1, robot: 2, tool: 0, cutplan: 1 },
      export: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
    });
    status = allStageStatuses(revisions);
    expect(status.simulation).toBe("current");
    expect(status.export).toBe("stale");

    // Zuletzt Export neu → alles aktuell.
    revisions = rev(inputs, {
      druckplan: { wall: 1, robot: 2, tool: 0 },
      simulation: { wall: 1, robot: 2, tool: 0, cutplan: 1 },
      export: { wall: 1, robot: 2, tool: 0, cutplan: 1 },
    });
    expect(allStageStatuses(revisions)).toEqual({
      druckplan: "current",
      simulation: "current",
      export: "current",
    });
  });

  it("Prozessparameter-Änderung veraltet Zerlegung/Simulation/Export (Issue #59)", () => {
    // process 0 → 1; alle drei Outputs beobachten process (Slice-Parameter).
    const revisions = rev(
      { wall: 1, robot: 1, tool: 0, cutplan: 1, process: 1 },
      {
        druckplan: { wall: 1, robot: 1, tool: 0, process: 0 },
        simulation: { wall: 1, robot: 1, tool: 0, cutplan: 1, process: 0 },
        export: { wall: 1, robot: 1, tool: 0, cutplan: 1, process: 0 },
      },
    );
    expect(allStageStatuses(revisions)).toEqual({
      druckplan: "stale",
      simulation: "stale",
      export: "stale",
    });
  });

  it("Schnittplan-Änderung veraltet Simulation/Export, nicht den Druckplan", () => {
    // cutplan 1 → 2; Druckplan hängt nicht am cutplan.
    const revisions = rev(
      { wall: 1, robot: 1, tool: 0, cutplan: 2 },
      {
        druckplan: { wall: 1, robot: 1, tool: 0 },
        simulation: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
        export: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
      },
    );
    const status = allStageStatuses(revisions);
    expect(status.druckplan).toBe("current");
    expect(status.simulation).toBe("stale");
    expect(status.export).toBe("stale");
  });

  it("Workstation-Wechsel veraltet Druckplan/Simulation/Export (Issue #83)", () => {
    // workstation 0 → 1; alle drei Outputs beobachten workstation.
    const revisions = rev(
      { wall: 1, robot: 1, tool: 0, cutplan: 1, workstation: 1 },
      {
        druckplan: { wall: 1, robot: 1, tool: 0, workstation: 0 },
        simulation: { wall: 1, robot: 1, tool: 0, cutplan: 1, workstation: 0 },
        export: { wall: 1, robot: 1, tool: 0, cutplan: 1, workstation: 0 },
      },
    );
    expect(allStageStatuses(revisions)).toEqual({
      druckplan: "stale",
      simulation: "stale",
      export: "stale",
    });
  });
});

describe("Ganzjob-Parität gegen das geteilte Core-Golden (Issue #194)", () => {
  it("die Ganzjob-Konstanten sind bit-gleich zum Core (Kommentar-Syncpunkte als Fakt)", () => {
    expect([...INPUT_KEYS]).toEqual(golden.constants.INPUT_KEYS);
    expect(OUTPUT_DEPS).toEqual(golden.constants.OUTPUT_DEPS);
    expect(SECTION_OUTPUT_JOB_DEPS).toEqual(golden.constants.SECTION_OUTPUT_JOB_DEPS);
    expect(SECTION_AGGREGATE_OUTPUTS).toEqual(golden.constants.SECTION_AGGREGATE_OUTPUTS);
  });

  it("allStageStatuses reproduziert jeden output_case des Core (inkl. section_total-Kante)", () => {
    expectGoldenParity(
      golden.output_cases,
      (c) => allStageStatuses((c.revisions ?? undefined) as Revisions | undefined),
      (got, c, label) => {
        const statuses = got as Record<OutputName, string>;
        for (const stage of Object.keys(c.expected) as OutputName[]) {
          expect(statuses[stage], `${label} / ${stage}`).toBe(c.expected[stage]);
        }
      },
    );
  });
});

describe("sectionStageStatus (feingranulare Pro-Abschnitts-Veraltung, Issue #83)", () => {
  it("Abschnitts-Override veraltet nur diesen Abschnitt; Nachbar bleibt aktuell", () => {
    const revisions: Revisions = {
      inputs: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0 },
      outputs: {},
      section_inputs: { "abschnitt-1": 1 },
      section_outputs: {
        "abschnitt-1": {
          simulation: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0 },
          export: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0 },
        },
        "abschnitt-2": {
          simulation: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0 },
          export: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0 },
        },
      },
    };
    expect(allSectionStageStatuses(revisions, "abschnitt-1")).toEqual({
      simulation: "stale",
      export: "stale",
    });
    expect(allSectionStageStatuses(revisions, "abschnitt-2")).toEqual({
      simulation: "current",
      export: "current",
    });
  });

  it("globaler/struktureller Bump (process) veraltet alle Abschnitte", () => {
    const revisions: Revisions = {
      inputs: { wall: 1, robot: 1, cutplan: 1, process: 1, workstation: 0 },
      outputs: {},
      section_inputs: {},
      section_outputs: {
        "abschnitt-1": {
          simulation: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0 },
        },
        "abschnitt-2": {
          simulation: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0 },
        },
      },
    };
    expect(sectionStageStatus(revisions, "abschnitt-1", "simulation")).toBe("stale");
    expect(sectionStageStatus(revisions, "abschnitt-2", "simulation")).toBe("stale");
  });

  it("Altprojekt ohne Pro-Abschnitts-Ebene: Ganzjob-Veraltung wie bisher", () => {
    // section_outputs fehlt → folgt stageStatus (Ganzjob). robot 1→2 = stale.
    const revisions = rev(
      { wall: 1, robot: 2, tool: 0, cutplan: 1 },
      {
        simulation: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
        export: { wall: 1, robot: 1, tool: 0, cutplan: 1 },
      },
    );
    expect(allSectionStageStatuses(revisions, "abschnitt-1")).toEqual({
      simulation: "stale",
      export: "stale",
    });
    // Kein Revisionsfeld → nichts veraltet.
    expect(allSectionStageStatuses(undefined, "abschnitt-1")).toEqual({
      simulation: "current",
      export: "current",
    });
  });

  it("Abschnitt ohne eigenen Schnappschuss ist 'missing'", () => {
    const revisions: Revisions = {
      inputs: { wall: 1, robot: 1, cutplan: 1 },
      outputs: {},
      section_outputs: {
        "abschnitt-1": {
          simulation: { wall: 1, robot: 1, cutplan: 1, section: 0 },
        },
      },
    };
    expect(sectionStageStatus(revisions, "abschnitt-2", "simulation")).toBe("missing");
    expect(sectionStageStatus(revisions, "abschnitt-1", "simulation")).toBe("current");
  });

  it("stimmt auf den geteilten Golden-Fällen mit dem Core überein (Py↔TS-Parität)", () => {
    expectGoldenParity(
      sectionGolden.cases,
      (c) =>
        allSectionStageStatuses((c.revisions ?? undefined) as Revisions | undefined, c.section_id),
      (got, c, label) => {
        // Golden-Reihenfolge egal — je Stufe vergleichen.
        const statuses = got as Record<SectionOutputName, string>;
        for (const stage of Object.keys(c.expected) as SectionOutputName[]) {
          expect(statuses[stage], `${label} / ${stage}`).toBe(c.expected[stage]);
        }
      },
    );
  });
});
