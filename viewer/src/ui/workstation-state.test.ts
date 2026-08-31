import { describe, expect, it } from "vitest";

import type { WorkstationDef } from "../api/projects";
import {
  incompatibleWorkstationNames,
  workstationCompatibilityWarning,
} from "./workstation-state";

const M1013 = "doosan_m1013";
const KR16 = "kuka_kr16";

/** Minimale WorkstationDef-Attrappe — nur name + compatible_robots zählen fürs Filtern. */
function ws(name: string, compatible_robots: string[]): WorkstationDef {
  return {
    name,
    mobility: "stationary",
    height_adjustable: false,
    base_heights_mm: [0, 200],
    height_range_mm: null,
    safety_min_distance_mm: 50,
    vendor: "",
    compatible_robots,
  };
}

describe("incompatibleWorkstationNames (Ausgrauen-Menge, reuse isCompatible/#74)", () => {
  const list = [
    ws("passt", [M1013]),
    ws("fremd", [KR16]),
    ws("ungetaggt", []),
  ];

  it("markiert nur getaggte fremde Workstations", () => {
    const grey = incompatibleWorkstationNames(list, M1013);
    expect(grey.has("fremd")).toBe(true);
    expect(grey.has("passt")).toBe(false);
    expect(grey.has("ungetaggt")).toBe(false);
  });

  it("graut ohne aktiven Roboter nichts aus (unbekannte Auswahl)", () => {
    expect(incompatibleWorkstationNames(list, null).size).toBe(0);
  });

  it("ungetaggte Workstation bleibt für jeden Roboter wählbar (Migrationsschutz)", () => {
    expect(incompatibleWorkstationNames(list, KR16).has("ungetaggt")).toBe(false);
  });
});

describe("workstationCompatibilityWarning (Warnung bei Roboterwechsel)", () => {
  it("warnt, wenn die gewählte Workstation durch den Wechsel fremd wird", () => {
    const msg = workstationCompatibilityWarning(ws("fremd", [KR16]), M1013);
    expect(msg).toMatch(/Kompatibilitäts-Warnung/);
    expect(msg).toContain("fremd");
    expect(msg).toContain(M1013);
    expect(msg).toMatch(/kein Gate/);
    expect(msg).toContain("Workstation"); // Wording spezifisch für Workstation
  });

  it("schweigt bei passender Workstation", () => {
    expect(workstationCompatibilityWarning(ws("passt", [M1013]), M1013)).toBeNull();
  });

  it("schweigt bei ungetaggter Workstation (unbekannt = wählbar)", () => {
    expect(workstationCompatibilityWarning(ws("ungetaggt", []), M1013)).toBeNull();
  });

  it("schweigt ohne aktiven Roboter", () => {
    expect(workstationCompatibilityWarning(ws("fremd", [KR16]), null)).toBeNull();
  });

  it("schweigt ohne gewählte Workstation", () => {
    expect(workstationCompatibilityWarning(null, M1013)).toBeNull();
  });
});
