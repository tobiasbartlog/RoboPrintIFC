/**
 * Aufstell-Toggle-Normalisierung (Issue #81) — reine Logik, ohne Renderer.
 *
 * Kern: Altprojekte ohne `stand_mode`-Feld verhalten sich wie `floor`; nur der
 * exakte String `"elevated"` schaltet den erhöhten Zustand.
 */

import { describe, expect, it } from "vitest";

import { DEFAULT_STAND_MODE, normalizeStandMode } from "./aufstell-state";

describe("normalizeStandMode", () => {
  it("Default ist 'floor'", () => {
    expect(DEFAULT_STAND_MODE).toBe("floor");
  });

  it("fehlendes Feld (Altprojekt) → 'floor'", () => {
    expect(normalizeStandMode(undefined)).toBe("floor");
    expect(normalizeStandMode(null)).toBe("floor");
  });

  it("'elevated' bleibt 'elevated'", () => {
    expect(normalizeStandMode("elevated")).toBe("elevated");
  });

  it("'floor' bleibt 'floor'", () => {
    expect(normalizeStandMode("floor")).toBe("floor");
  });

  it("unbekannter Wert → 'floor' (defensiv)", () => {
    expect(normalizeStandMode("schwebend")).toBe("floor");
    expect(normalizeStandMode("")).toBe("floor");
  });
});
