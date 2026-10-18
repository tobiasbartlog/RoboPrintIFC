/**
 * Übernahme-Protokoll als getesteter Vertrag (Issue #193): Mitglieder-Menge
 * und Reihenfolge der Nachzieh-Sequenz nach jeder Core-Antwort mit frischen
 * `print_jobs` — Muster `placement-apply.test.ts` (calls-Array-Assertion).
 * Bewusste Varianten (`druckplan: "panel-owns"`, `restore`, `reevaluate`)
 * sind benannte Optionen mit eigenem Testfall, keine stillen Abweichungen.
 */

import { describe, expect, it } from "vitest";

import type { DecompositionSection, PrintJob, SectionOverride } from "../api/projects";
import { adoptJobResponse, findJob, type JobAdoptPorts } from "./job-adopt";

const sections = [
  { section_id: "abschnitt-1", order: 1 },
  { section_id: "abschnitt-2", order: 2 },
] as DecompositionSection[];

const overrides: SectionOverride[] = [{ section_id: "abschnitt-1", standoff_mm: 900 }];
const fresh = { job_id: "default", section_overrides: overrides } as PrintJob;
const other = { job_id: "zweiter" } as PrintJob;

/** Fake-Ports, die jede Wirkung als benannten Eintrag protokollieren. */
function fakePorts(): {
  ports: JobAdoptPorts;
  calls: string[];
  seen: {
    adopted?: PrintJob | undefined;
    fanoutJobs: (PrintJob | undefined)[];
    restored?: PrintJob | undefined;
    revisions?: PrintJob[];
    reevaluated?: SectionOverride[];
  };
} {
  const calls: string[] = [];
  const seen: {
    adopted?: PrintJob | undefined;
    fanoutJobs: (PrintJob | undefined)[];
    restored?: PrintJob | undefined;
    revisions?: PrintJob[];
    reevaluated?: SectionOverride[];
  } = { fanoutJobs: [] };
  const ports: JobAdoptPorts = {
    adoptActiveJob(job) {
      calls.push("adopt");
      seen.adopted = job;
    },
    sectionsFanout: {
      druckplan(s, kind) {
        calls.push(`sections:druckplan:${kind}:${s.length}`);
      },
      simulation(s) {
        calls.push(`sections:simulation:${s.length}`);
      },
      export(s) {
        calls.push(`sections:export:${s.length}`);
      },
      processParams(s, job) {
        calls.push(`sections:processParams:${s.length}`);
        seen.fanoutJobs.push(job);
      },
      placement(s, job) {
        calls.push(`sections:placement:${s.length}`);
        seen.fanoutJobs.push(job);
      },
    },
    restoreProcessParamsPanel(job) {
      calls.push("restore:process-params");
      seen.restored = job;
    },
    restorePlacementPanel(job) {
      calls.push("restore:placement");
      seen.restored = job;
    },
    updateOverrideMarkers() {
      calls.push("markers");
    },
    refreshRevisions(jobs) {
      calls.push("revisions");
      seen.revisions = jobs;
    },
    reevaluateDecomposition(o) {
      calls.push("reevaluate");
      seen.reevaluated = o;
    },
  };
  return { ports, calls, seen };
}

describe("adoptJobResponse — das Übernahme-Protokoll (Issue #193)", () => {
  it("Zerlegungs-Antwort: Job übernehmen → voller setSections-Fanout → ▪-Marker → Badges", () => {
    const { ports, calls, seen } = fakePorts();
    const job = adoptJobResponse(
      ports,
      { print_jobs: [other, fresh] },
      { sections, druckplan: { kind: "abschnitt" } },
    );
    expect(calls).toEqual([
      "adopt",
      "sections:druckplan:abschnitt:2",
      "sections:simulation:2",
      "sections:export:2",
      "sections:processParams:2",
      "sections:placement:2",
      "markers",
      "revisions",
    ]);
    // Der FRISCHE default-Job erreicht aktiven Job UND die job-lesenden
    // Fanout-Ziele — `adopt` MUSS vor allem Weiteren liegen.
    expect(seen.adopted).toBe(fresh);
    expect(seen.fanoutJobs).toEqual([fresh, fresh]);
    expect(seen.revisions).toEqual([other, fresh]);
    expect(job).toBe(fresh);
  });

  it('benannte Option druckplan: "panel-owns" — die Zerlegungs-Ansicht wendet die Antwort selbst an (Generation-Guard #45), der Rest des Fanouts bleibt vollständig', () => {
    const { ports, calls } = fakePorts();
    adoptJobResponse(ports, { print_jobs: [fresh] }, { sections, druckplan: "panel-owns" });
    expect(calls).toEqual([
      "adopt",
      "sections:simulation:2",
      "sections:export:2",
      "sections:processParams:2",
      "sections:placement:2",
      "markers",
      "revisions",
    ]);
  });

  it("Antwort ohne Teile (bare Persistenz-Schreiben): Job übernehmen → ▪-Marker → Badges", () => {
    const { ports, calls, seen } = fakePorts();
    const job = adoptJobResponse(ports, { print_jobs: [fresh] });
    expect(calls).toEqual(["adopt", "markers", "revisions"]);
    expect(seen.adopted).toBe(fresh);
    expect(job).toBe(fresh);
  });

  it('benannte Option restore: "process-params" — Formulare ziehen die geerbten Werte nach (#82/#92), VOR den ▪-Markern', () => {
    const { ports, calls, seen } = fakePorts();
    adoptJobResponse(ports, { print_jobs: [fresh] }, { restore: "process-params" });
    expect(calls).toEqual(["adopt", "restore:process-params", "markers", "revisions"]);
    expect(seen.restored).toBe(fresh);
  });

  it('benannte Option restore: "placement" + reevaluate — der onSaveOverride-/Advisor-Vertrag (#161/#172): Restore VOR Markern, Neubewertung zuletzt', () => {
    const { ports, calls, seen } = fakePorts();
    adoptJobResponse(
      ports,
      { print_jobs: [other, fresh] },
      { restore: "placement", reevaluate: true },
    );
    // Genau die Reihenfolge des placement-apply-Vertrags (ohne dessen PUT):
    // die vertauschte Hand-Reihenfolge in onSaveOverride (Marker vor Restore)
    // war die Divergenz, die #193 beseitigt.
    expect(calls).toEqual(["adopt", "restore:placement", "markers", "revisions", "reevaluate"]);
    expect(seen.restored).toBe(fresh);
    expect(seen.reevaluated).toBe(overrides);
  });

  it("unbekannte jobId → Ports bekommen undefined, kein Wurf (Befund, kein Gate); Neubewertung mit leerem Override-Stand", () => {
    const { ports, calls, seen } = fakePorts();
    const job = adoptJobResponse(
      ports,
      { print_jobs: [other] },
      { jobId: "gibt-es-nicht", restore: "placement", reevaluate: true },
    );
    expect(job).toBeUndefined();
    expect(seen.adopted).toBeUndefined();
    expect(seen.restored).toBeUndefined();
    expect(seen.reevaluated).toEqual([]);
    expect(calls).toEqual(["adopt", "restore:placement", "markers", "revisions", "reevaluate"]);
  });

  it("sections ohne druckplan-Option → Wurf (explizit statt still), KEINE halbe Wirkung nach dem Fanout-Start", () => {
    const { ports, calls } = fakePorts();
    expect(() => adoptJobResponse(ports, { print_jobs: [fresh] }, { sections })).toThrow(
      /druckplan/,
    );
    // Nur die Übernahme selbst ist gelaufen — kein Marker-/Badge-Schritt auf
    // halbem Weg (der Programmierfehler fällt im ersten Test auf).
    expect(calls).toEqual(["adopt"]);
  });

  it("sections ohne sectionsFanout-Ports → Wurf (Programmierfehler, kein stilles Auslassen)", () => {
    const { ports } = fakePorts();
    delete ports.sectionsFanout;
    expect(() =>
      adoptJobResponse(ports, { print_jobs: [fresh] }, { sections, druckplan: "panel-owns" }),
    ).toThrow(/sectionsFanout/);
  });
});

describe("findJob — der eine default-Job-Selektor (Issue #193)", () => {
  it('findet den Job mit job_id "default" (bzw. der übergebenen jobId)', () => {
    expect(findJob([other, fresh])).toBe(fresh);
    expect(findJob([other, fresh], "zweiter")).toBe(other);
    expect(findJob([other])).toBeUndefined();
    expect(findJob(undefined)).toBeUndefined();
  });
});
