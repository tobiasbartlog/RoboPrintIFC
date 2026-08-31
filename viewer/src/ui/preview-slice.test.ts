import { describe, expect, it } from "vitest";

import { type SectionExtent, sliceSectionPreview } from "./preview-slice";

const SECTION: SectionExtent = {
  x0_mm: -500,
  x1_mm: 500,
  z0_mm: 0,
  z1_mm: 240,
  thickness_mm: 240,
};

describe("sliceSectionPreview: sofortige, IK-freie Vorschau-Bahn (Issue #85)", () => {
  it("stapelt Schichten nach Schichthöhe (mehr Höhe → mehr Schichten)", () => {
    const coarse = sliceSectionPreview(SECTION, { layer_height_mm: 40, strand_width_mm: 30, n_shells: 1 });
    const fine = sliceSectionPreview(SECTION, { layer_height_mm: 8, strand_width_mm: 30, n_shells: 1 });
    expect(coarse.nLayers).toBe(6); // 240 / 40
    expect(fine.nLayers).toBe(30); // 240 / 8
    expect(fine.nLayers).toBeGreaterThan(coarse.nLayers);
  });

  it("Reglerziehen ändert die Bahn sofort (andere Params → andere Punktzahl)", () => {
    const before = sliceSectionPreview(SECTION, { layer_height_mm: 8, strand_width_mm: 30, n_shells: 1 });
    const after = sliceSectionPreview(SECTION, { layer_height_mm: 8, strand_width_mm: 30, n_shells: 3 });
    // 3 Schalen statt 1 → dreifache Ringzahl je Schicht.
    expect(after.path.length).toBe(before.path.length * 3);
  });

  it("jeder Ring ist geschlossen (Start = Ende, 5 Punkte)", () => {
    const { path, pointsPerRing } = sliceSectionPreview(SECTION, {
      layer_height_mm: 60,
      strand_width_mm: 30,
      n_shells: 1,
    });
    expect(pointsPerRing).toBe(5);
    for (let i = 0; i < path.length; i += pointsPerRing) {
      expect(path[i]).toEqual(path[i + pointsPerRing - 1]);
    }
  });

  it("Ringe sind CCW aus Sicht von +z (Konvention für nozzle_quat-Außenseite)", () => {
    const { path } = sliceSectionPreview(SECTION, {
      layer_height_mm: 240,
      strand_width_mm: 30,
      n_shells: 1,
    });
    // Signierte Fläche (Shoelace) des ersten Rings > 0 ⇒ CCW.
    let area = 0;
    for (let i = 0; i < 4; i++) {
      const [x1, y1] = path[i];
      const [x2, y2] = path[i + 1];
      area += x1 * y2 - x2 * y1;
    }
    expect(area).toBeGreaterThan(0);
  });

  it("alle Punkte liegen in der Abschnitts-Box (Länge/Dicke/Höhe)", () => {
    const { path } = sliceSectionPreview(SECTION, { layer_height_mm: 24, strand_width_mm: 30, n_shells: 2 });
    for (const [x, y, z] of path) {
      expect(x).toBeGreaterThanOrEqual(-500);
      expect(x).toBeLessThanOrEqual(500);
      expect(Math.abs(y)).toBeLessThanOrEqual(120);
      expect(z).toBeGreaterThanOrEqual(0);
      expect(z).toBeLessThanOrEqual(240);
    }
  });

  it("fällt bei fehlenden Feldern auf sichtbare Defaults (nie leer)", () => {
    const { path, layerHeightMm, strandWidthMm, nShells } = sliceSectionPreview(SECTION, {});
    expect(layerHeightMm).toBeGreaterThan(0);
    expect(strandWidthMm).toBeGreaterThan(0);
    expect(nShells).toBe(1);
    expect(path.length).toBeGreaterThan(0);
  });

  it("zu große Schalen kollabieren, ohne die Bahn ungültig zu machen", () => {
    const thin: SectionExtent = { x0_mm: 0, x1_mm: 40, z0_mm: 0, z1_mm: 20, thickness_mm: 40 };
    const { path, nLayers } = sliceSectionPreview(thin, { layer_height_mm: 20, strand_width_mm: 30, n_shells: 5 });
    // Nur die äußerste Schale passt; überzählige werden ausgelassen.
    expect(nLayers).toBe(1);
    expect(path.length).toBe(5);
  });
});
