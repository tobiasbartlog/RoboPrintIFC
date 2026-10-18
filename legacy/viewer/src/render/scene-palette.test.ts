import { describe, expect, it } from "vitest";

import { clayBrightness, hashSeed, ndcToPx, readScenePalette } from "./scene-palette";

describe("scene-palette — Bühnen-Farben aus CSS-Tokens (Clay-Studio, Issue #113)", () => {
  it("liest --vp1/--vp2 aus den Tokens und wählt die Theme-Gitterdeckkraft", () => {
    const tokens: Record<string, string> = {
      "--vp1": " #2a2f36 ",
      "--vp2": "#23272d",
    };
    const dark = readScenePalette((n) => tokens[n] ?? "", "dark");
    expect(dark.bgInner).toBe("#2a2f36");
    expect(dark.bgOuter).toBe("#23272d");
    expect(dark.gridOpacity).toBeCloseTo(0.06);
    // Fog folgt dem Verlaufsrand.
    expect(dark.grid).toMatch(/^#/);

    const light = readScenePalette((n) => tokens[n] ?? "", "light");
    expect(light.gridOpacity).toBeCloseTo(0.09);
  });

  it("fällt bei fehlenden Tokens auf die Scheibe-9-Vorgaben zurück (kein leerer Verlauf)", () => {
    const dark = readScenePalette(() => "", "dark");
    expect(dark.bgInner).toBe("#2a2f36");
    expect(dark.bgOuter).toBe("#23272d");
    const light = readScenePalette(() => "", "light");
    expect(light.bgInner).toBe("#eceae5");
    expect(light.bgOuter).toBe("#dedbd4");
  });
});

describe("clayBrightness — deterministische ±8-%-Varianz je Wand", () => {
  it("bleibt innerhalb ±8 % um 1.0", () => {
    for (const seed of [0, 1, 7, 42, 100, 999999]) {
      const b = clayBrightness(seed);
      expect(b).toBeGreaterThanOrEqual(0.92 - 1e-9);
      expect(b).toBeLessThanOrEqual(1.08 + 1e-9);
    }
  });

  it("ist reproduzierbar (gleicher Seed → gleicher Wert) und variiert über Seeds", () => {
    expect(clayBrightness(42)).toBe(clayBrightness(42));
    expect(clayBrightness(1)).not.toBe(clayBrightness(2));
  });
});

describe("hashSeed — stabiler String-Hash", () => {
  it("ist deterministisch und unterscheidet Strings", () => {
    expect(hashSeed("wall-a")).toBe(hashSeed("wall-a"));
    expect(hashSeed("wall-a")).not.toBe(hashSeed("wall-b"));
    expect(Number.isInteger(hashSeed("x"))).toBe(true);
  });
});

describe("ndcToPx — NDC → Overlay-Pixel fürs Maß-Label", () => {
  it("bildet Mitte, Ecken und y-Spiegelung korrekt ab", () => {
    expect(ndcToPx(0, 0, 800, 600)).toEqual({ x: 400, y: 300 });
    // NDC (-1,+1) = links oben → (0, 0); (+1,-1) = rechts unten → (w, h).
    expect(ndcToPx(-1, 1, 800, 600)).toEqual({ x: 0, y: 0 });
    expect(ndcToPx(1, -1, 800, 600)).toEqual({ x: 800, y: 600 });
  });
});
