/**
 * Wachsender Druckstand — reine Prisma-Spec (US 10, Issue #128). Prüft die
 * Darstellungsmathematik: Höhe wächst linear mit dem Fortschritt, Länge/Dicke
 * bleiben; der Anteil wird geklemmt; entartete Maße fallen sicher auf 0.
 */

import { describe, expect, it } from "vitest";

import { druckstandPrism } from "./druckstand-spec";

const FULL: [number, number, number] = [800, 120, 1200];

describe("druckstandPrism — wächst entlang der Höhe (US 10)", () => {
  it("Fortschritt 0 → nichts gewachsen (Höhe 0, unsichtbar)", () => {
    const p = druckstandPrism({ fullSizeMm: FULL, grownFraction: 0 });
    expect(p.sizeMm).toEqual([800, 120, 0]);
    expect(p.centerLocalMm).toEqual([0, 0, 0]);
    expect(p.visible).toBe(false);
  });

  it("Fortschritt 1 → volle Box (Höhe voll, Mittelpunkt auf halber Höhe)", () => {
    const p = druckstandPrism({ fullSizeMm: FULL, grownFraction: 1 });
    expect(p.sizeMm).toEqual([800, 120, 1200]);
    expect(p.centerLocalMm).toEqual([0, 0, 600]);
    expect(p.visible).toBe(true);
  });

  it("Fortschritt 0.5 → halbe Höhe, Länge/Dicke unverändert", () => {
    const p = druckstandPrism({ fullSizeMm: FULL, grownFraction: 0.5 });
    expect(p.sizeMm).toEqual([800, 120, 600]);
    expect(p.centerLocalMm).toEqual([0, 0, 300]);
    expect(p.grownFraction).toBe(0.5);
  });

  it("klemmt den Anteil auf [0,1] (kein Über-/Unterwachsen)", () => {
    expect(druckstandPrism({ fullSizeMm: FULL, grownFraction: 1.7 }).grownFraction).toBe(1);
    expect(druckstandPrism({ fullSizeMm: FULL, grownFraction: -0.3 }).grownFraction).toBe(0);
    expect(druckstandPrism({ fullSizeMm: FULL, grownFraction: Number.NaN }).grownFraction).toBe(0);
  });

  it("entartete Maße fallen sicher auf 0 (kein NaN/negativ)", () => {
    const p = druckstandPrism({ fullSizeMm: [-5, Number.NaN, 0], grownFraction: 1 });
    expect(p.sizeMm).toEqual([0, 0, 0]);
    expect(p.visible).toBe(false);
  });
});
