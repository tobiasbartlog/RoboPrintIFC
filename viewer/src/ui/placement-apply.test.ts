/**
 * Anwenden-Fluss eines Platzierungs-Overrides (Issue #161, Review-Nacharbeit):
 * die Sequenz PUT → Job übernehmen → Platzierungsfelder → ▪-Marker/Karte →
 * Veraltet-Badges ist Vertrag — sichert den zweiten Fix-Baustein von #161
 * (Anwenden-Parität des Kollisions-Advisors), der vorher nur ungetestete
 * Glue-Zeilen in `main.ts` war.
 */

import { describe, expect, it } from "vitest";

import type { PrintJob, SectionOverride } from "../api/projects";
import { applyPlacementOverride, type PlacementApplyPorts } from "./placement-apply";

/** Fake-Ports, die jede Wirkung als benannten Eintrag protokollieren. */
function fakePorts(printJobs: PrintJob[]): {
  ports: PlacementApplyPorts;
  calls: string[];
  seen: {
    adopted?: PrintJob | undefined;
    restored?: PrintJob | undefined;
    revisions?: PrintJob[];
    reevaluated?: SectionOverride[];
  };
} {
  const calls: string[] = [];
  const seen: {
    adopted?: PrintJob | undefined;
    restored?: PrintJob | undefined;
    revisions?: PrintJob[];
    reevaluated?: SectionOverride[];
  } = {};
  const ports: PlacementApplyPorts = {
    async setPlacementOverride(sectionId, values) {
      calls.push(`put:${sectionId}:${JSON.stringify(values)}`);
      return { print_jobs: printJobs };
    },
    adoptActiveJob(job) {
      calls.push("adopt");
      seen.adopted = job;
    },
    restorePlacementPanel(job) {
      calls.push("restore");
      seen.restored = job;
    },
    updateOverrideMarkers() {
      calls.push("markers");
    },
    refreshRevisions(jobs) {
      calls.push("revisions");
      seen.revisions = jobs;
    },
    reevaluateDecomposition(overrides) {
      calls.push("reevaluate");
      seen.reevaluated = overrides;
    },
  };
  return { ports, calls, seen };
}

describe("applyPlacementOverride — Anwenden-Parität der Advisors (Issue #161)", () => {
  const overrides: SectionOverride[] = [{ section_id: "abschnitt-1", standoff_mm: 900 }];
  const fresh = { job_id: "default", section_overrides: overrides } as PrintJob;
  const other = { job_id: "zweiter" } as PrintJob;

  it("Reihenfolge ist Vertrag: PUT → Job übernehmen → Felder → ▪-Marker → Badges → Neubewertung", async () => {
    const { ports, calls, seen } = fakePorts([other, fresh]);
    const job = await applyPlacementOverride(ports, "abschnitt-1", { standoff_mm: 900 });
    expect(calls).toEqual([
      'put:abschnitt-1:{"standoff_mm":900}',
      "adopt",
      "restore",
      "markers",
      "revisions",
      "reevaluate",
    ]);
    // Der FRISCHE default-Job aus der PUT-Antwort erreicht Panel + aktiven Job —
    // damit `updateOverrideMarkers` (liest den aktiven Job) die neuen
    // section_overrides sieht, muss `adopt` VOR `markers` liegen.
    expect(seen.adopted).toBe(fresh);
    expect(seen.restored).toBe(fresh);
    expect(seen.revisions).toEqual([other, fresh]);
    // Neubewertung (Issue #172): der frische Override-Stand des Jobs entwertet die
    // Ampel/Badges des Teils (gleiche Semantik wie das manuelle Platzierungsfeld).
    expect(seen.reevaluated).toBe(overrides);
    expect(job).toBe(fresh);
  });

  it("unbekannte job_id → Ports bekommen undefined, kein Wurf (Befund, kein Gate)", async () => {
    const { ports, calls, seen } = fakePorts([other]);
    const job = await applyPlacementOverride(ports, "abschnitt-1", {}, "gibt-es-nicht");
    expect(job).toBeUndefined();
    expect(seen.adopted).toBeUndefined();
    expect(seen.restored).toBeUndefined();
    // Ohne Job noch immer Neubewertung mit leerem Override-Stand (kein Wurf).
    expect(seen.reevaluated).toEqual([]);
    expect(calls.slice(1)).toEqual(["adopt", "restore", "markers", "revisions", "reevaluate"]);
  });

  it("PUT schlägt fehl → KEINE UI-Wirkung, der Fehler propagiert zum Panel", async () => {
    const calls: string[] = [];
    const ports: PlacementApplyPorts = {
      setPlacementOverride() {
        return Promise.reject(new Error("Core nicht erreichbar"));
      },
      adoptActiveJob() {
        calls.push("adopt");
      },
      restorePlacementPanel() {
        calls.push("restore");
      },
      updateOverrideMarkers() {
        calls.push("markers");
      },
      refreshRevisions() {
        calls.push("revisions");
      },
      reevaluateDecomposition() {
        calls.push("reevaluate");
      },
    };
    await expect(
      applyPlacementOverride(ports, "abschnitt-1", { lateral_mm: -120 }),
    ).rejects.toThrow(/Core nicht erreichbar/);
    expect(calls).toEqual([]);
  });
});
