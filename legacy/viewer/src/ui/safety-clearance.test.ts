import { describe, expect, it } from "vitest";

import { breathAt, clearanceState } from "./safety-clearance";

describe("breathAt: weiches Ein-/Ausatmen über einen vollen Zyklus", () => {
  it("0 → eingeatmet, 0.5 → ausgeatmet, 1 → eingeatmet", () => {
    expect(breathAt(0)).toBeCloseTo(0, 12);
    expect(breathAt(0.5)).toBeCloseTo(1, 12);
    expect(breathAt(1)).toBeCloseTo(0, 12);
  });
});

describe("clearanceState: animierter Sicherheitspuffer (Issue #85)", () => {
  it("Puls-Radius atmet zwischen 0.8·safetyMin und safetyMin", () => {
    const min = clearanceState(700, 50, 0).pulseMm; // breath 0
    const max = clearanceState(700, 50, 0.5).pulseMm; // breath 1
    expect(min).toBeCloseTo(0.8 * 50, 9);
    expect(max).toBeCloseTo(50, 9);
    expect(max).toBeGreaterThan(min);
  });

  it("Marge = standoff − Mindestabstand; reagiert auf die Abstands-Optimierung", () => {
    // Der Optimierer bewegt standoff → die Marge (und damit der Puffer) atmet mit.
    expect(clearanceState(700, 50, 0).marginMm).toBe(650);
    expect(clearanceState(120, 50, 0).marginMm).toBe(70);
    expect(clearanceState(700, 50, 0).safe).toBe(true);
  });

  it("verletzter Mindestabstand ist unsicher (Marge < 0)", () => {
    const s = clearanceState(30, 50, 0.25);
    expect(s.marginMm).toBe(-20);
    expect(s.safe).toBe(false);
  });

  it("negative Eingaben werden auf 0 geklemmt (robust)", () => {
    const s = clearanceState(-10, -5, 0);
    expect(s.standoffMm).toBe(0);
    expect(s.safetyMinMm).toBe(0);
    expect(s.pulseMm).toBe(0);
    expect(s.safe).toBe(true);
  });
});
