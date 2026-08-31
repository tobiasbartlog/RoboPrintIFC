/**
 * Abschnitts-Quader (Issue #84): Lage/Ausdehnung im Wand-lokalen z-hoch-Frame
 * (Issue #99: die Drehung in den Gruppen-Frame übernimmt die Quader-Gruppe an
 * der PCA-Wand-Pose). `x0..x1` ist Wand-lokal entlang der Längsachse, `z0..z1`
 * ab Wandfuß; die Dicke ist voll. Rein geprüft (kein three.js).
 */

import { describe, expect, it } from "vitest";

import type { DecompositionSection } from "../api/projects";
import { sectionBoxSpec } from "./sections";
import type { WallFrame } from "./wall-frame";

const wall: WallFrame = {
  origin: { x: 999, y: -999 }, // für die Wand-lokale Spec irrelevant (Gruppe verschiebt)
  yaw: 0.7,
  center: { x: 10, y: 20 },
  length_mm: 4000,
  thickness_mm: 260,
  height_mm: 2600,
  zMin: 5,
};

function section(over: Partial<DecompositionSection>): DecompositionSection {
  return {
    section_id: "abschnitt-1",
    order: 1,
    x0_mm: -2000,
    x1_mm: 0,
    z0_mm: 0,
    z1_mm: 1300,
    placement: { option_id: "auto", lateral_mm: 0, standoff_mm: 0, stand_height_mm: 0 },
    status: { reachable: true, reachable_fraction: 1, n_samples: 0 },
    ...over,
  } as DecompositionSection;
}

describe("sectionBoxSpec: Wand-lokale Lage", () => {
  const spec = sectionBoxSpec(section({ x0_mm: -2000, x1_mm: 0, z0_mm: 0, z1_mm: 1300 }), wall);

  it("spannt Länge (x) × volle Dicke (y) × Höhe (z) auf", () => {
    // Länge 2000 + Übermaß, Dicke 260 + Übermaß, Höhe 1300 + Übermaß.
    expect(spec.size[0]).toBeCloseTo(2000 + 30, 6);
    expect(spec.size[1]).toBeCloseTo(260 + 30, 6);
    expect(spec.size[2]).toBeCloseTo(1300 + 30, 6);
  });

  it("sitzt Wand-lokal auf der x-Mitte des Abschnitts, z ab Wandfuß", () => {
    // Mittelpunkt x der Grenzen -2000..0 = -1000 (direkt Wand-lokal, #99);
    // Dicken-Mitte = center.y 20; z-Mitte 650 + zMin 5 = 655.
    expect(spec.origin[0]).toBeCloseTo(-1000, 6);
    expect(spec.origin[1]).toBeCloseTo(20, 6);
    expect(spec.origin[2]).toBeCloseTo(655, 6);
  });
});

describe("sectionBoxSpec: oberer Abschnitt (z-Band)", () => {
  const spec = sectionBoxSpec(section({ x0_mm: 0, x1_mm: 2000, z0_mm: 1300, z1_mm: 2600 }), wall);

  it("folgt Abschnittsmitte und z-Band", () => {
    expect(spec.origin[0]).toBeCloseTo(1000, 6);
    expect(spec.origin[2]).toBeCloseTo(5 + 1950, 6); // zMin 5 + z-Mitte 1950
    expect(spec.size[2]).toBeCloseTo(1300 + 30, 6);
  });
});

describe("sectionBoxSpec: einzelner Abschnitt über die volle Wand", () => {
  const spec = sectionBoxSpec(
    section({ x0_mm: -2000, x1_mm: 2000, z0_mm: 0, z1_mm: 2600 }),
    wall,
  );

  it("umfasst die ganze Wandlänge und -höhe (abwärtskompatibler Einzelfall)", () => {
    expect(spec.size[0]).toBeCloseTo(4000 + 30, 6);
    expect(spec.size[2]).toBeCloseTo(2600 + 30, 6);
    expect(spec.origin[0]).toBeCloseTo(0, 6); // zentriert auf den Wand-Nullpunkt
  });
});
