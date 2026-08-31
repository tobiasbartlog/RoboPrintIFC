import { describe, expect, it } from "vitest";

import type { ToolDef } from "../api/projects";
import { compatibilityWarning, incompatibleToolNames, isCompatible } from "./compat";

const M1013 = "doosan_m1013";
const KR16 = "kuka_kr16";

/** Minimale ToolDef-Attrappe — nur die fürs Filtern relevanten Felder zählen. */
function tool(name: string, compatible_robots: string[]): ToolDef {
  return {
    name,
    vendor: "",
    weight_kg: 1,
    cog_mm: null,
    mesh: null,
    mesh_path: null,
    mesh_transform: null,
    tcp_frame: { pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] },
    channels: {},
    compatible_robots,
  };
}

describe("isCompatible (Golden-Fälle, deckungsgleich mit test_compat.py)", () => {
  it("getaggt + passend → true", () => {
    expect(isCompatible([M1013, KR16], M1013)).toBe(true);
    expect(isCompatible([M1013], M1013)).toBe(true);
  });
  it("getaggt + fremd → false", () => {
    expect(isCompatible([KR16], M1013)).toBe(false);
    expect(isCompatible([M1013], KR16)).toBe(false);
  });
  it("leere/fehlende Tags → true (unbekannt, Migrationsschutz)", () => {
    expect(isCompatible([], M1013)).toBe(true);
    expect(isCompatible(null, M1013)).toBe(true);
    expect(isCompatible(undefined, M1013)).toBe(true);
  });
  it("kein aktiver Roboter → true (unbekannte Auswahl)", () => {
    expect(isCompatible([M1013], null)).toBe(true);
    expect(isCompatible([], null)).toBe(true);
    expect(isCompatible(null, null)).toBe(true);
  });
});

describe("incompatibleToolNames (Ausgrauen-Menge)", () => {
  const tools = [
    tool("passt", [M1013]),
    tool("fremd", [KR16]),
    tool("ungetaggt", []),
  ];

  it("markiert nur getaggtes fremdes Zubehör", () => {
    const grey = incompatibleToolNames(tools, M1013);
    expect(grey.has("fremd")).toBe(true);
    expect(grey.has("passt")).toBe(false);
    expect(grey.has("ungetaggt")).toBe(false);
  });

  it("graut ohne aktiven Roboter nichts aus (unbekannte Auswahl)", () => {
    expect(incompatibleToolNames(tools, null).size).toBe(0);
  });

  it("ungetaggtes Zubehör bleibt für jeden Roboter wählbar", () => {
    expect(incompatibleToolNames(tools, KR16).has("ungetaggt")).toBe(false);
  });
});

describe("compatibilityWarning (Warnung bei Roboterwechsel)", () => {
  it("warnt, wenn der gewählte Endeffektor durch den Wechsel fremd wird", () => {
    const msg = compatibilityWarning(tool("fremd", [KR16]), M1013);
    expect(msg).toMatch(/Kompatibilitäts-Warnung/);
    expect(msg).toContain("fremd");
    expect(msg).toContain(M1013);
    expect(msg).toMatch(/kein Gate/);
  });

  it("schweigt bei passendem Endeffektor", () => {
    expect(compatibilityWarning(tool("passt", [M1013]), M1013)).toBeNull();
  });

  it("schweigt bei ungetaggtem Endeffektor (unbekannt = wählbar)", () => {
    expect(compatibilityWarning(tool("ungetaggt", []), M1013)).toBeNull();
  });

  it("schweigt ohne aktiven Roboter", () => {
    expect(compatibilityWarning(tool("fremd", [KR16]), null)).toBeNull();
  });

  it("schweigt ohne gewählten Endeffektor", () => {
    expect(compatibilityWarning(null, M1013)).toBeNull();
  });
});
