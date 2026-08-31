import { describe, expect, it } from "vitest";

import type { DecompositionSection, PlacementOption } from "../api/projects";
import {
  sectionBaseFrame,
  sectionMarkerPosition,
  sectionPlacementBox,
} from "./placement-markers";
import type { WallFrame } from "./wall-frame";

/** Wand-Pose: Nullpunkt (1000, 200), keine Drehung; Dicke 300, Fuß bei z=500.
 *  Die reinen Pose-Funktionen rechnen Wand-lokal (Issue #99) — origin/yaw
 *  wirken nur in `sectionBaseFrame` (fertig komponierter Gruppen-Frame). */
const wallFrame: WallFrame = {
  origin: { x: 1000, y: 200 },
  yaw: 0,
  center: { x: 0, y: 0 },
  length_mm: 4000,
  thickness_mm: 300,
  height_mm: 2000,
  zMin: 500,
};

function section(
  placement: PlacementOption,
  bounds: Pick<DecompositionSection, "x0_mm" | "x1_mm" | "z0_mm" | "z1_mm">,
): DecompositionSection {
  return {
    section_id: "s1",
    order: 1,
    ...bounds,
    placement,
    status: {
      reachable: true,
      reachable_fraction: 1,
      n_samples: 0,
      n_reachable: 0,
      kinematic_margin: null,
      mean_margin: null,
      warnings: [],
    },
  };
}

const pose: PlacementOption = {
  option_id: "p",
  lateral_mm: 100,
  standoff_mm: 700,
  stand_height_mm: 0,
};

describe("sectionPlacementBox", () => {
  it("Wand-lokal: x0..x1 entlang der Längsachse, volle Dicke, z ab Wandfuß", () => {
    const s = section(pose, { x0_mm: -500, x1_mm: 500, z0_mm: 0, z1_mm: 1300 });
    const box = sectionPlacementBox(s, wallFrame);
    expect(box.min).toEqual([-500, -150, 500]); // x0, center.y-150, zMin+0
    expect(box.max).toEqual([500, 150, 1800]); // x1, center.y+150, zMin+1300
  });
});

describe("sectionMarkerPosition", () => {
  it("setzt lateral entlang der Längsachse (Abschnittsmitte) + standoff vor die Front", () => {
    const s = section(pose, { x0_mm: -400, x1_mm: 400, z0_mm: 0, z1_mm: 1300 });
    const [x, y, z] = sectionMarkerPosition(s, wallFrame);
    // Wand-lokal: lengthMid 0 + lateral 100; Normale 0 + (150+700);
    // z = Boden (wall.zMin 500) + Aufstellhöhe 0 — Regressionsanker #133:
    // unterste Reihe im Boden-Modus steht exakt wie vor der Umstellung.
    expect(x).toBeCloseTo(100);
    expect(y).toBeCloseTo(850);
    expect(z).toBeCloseTo(500);
  });

  it("folgt der Abschnittsmitte, wenn x0..x1 nicht um 0 zentriert ist", () => {
    const s = section(pose, { x0_mm: 600, x1_mm: 1400, z0_mm: 1300, z1_mm: 2600 });
    const [x, , z] = sectionMarkerPosition(s, wallFrame);
    // lengthMid = 1000 + lateral 100 = 1100; z bleibt am Boden (Issue #133:
    // Boden-Modus ⇒ der Marker steht VOR dem oberen Abschnitt auf dem Boden,
    // NICHT mehr schwebend am Abschnittsfuß 500+1300).
    expect(x).toBeCloseTo(1100);
    expect(z).toBeCloseTo(500);
  });

  it("hebt den Marker auf die absolute Aufstellhöhe über dem Boden (Issue #133)", () => {
    const podest: PlacementOption = { ...pose, stand_height_mm: 400 };
    const s = section(podest, { x0_mm: -400, x1_mm: 400, z0_mm: 1300, z1_mm: 2600 });
    const [, , z] = sectionMarkerPosition(s, wallFrame);
    // z = Boden (wall.zMin 500) + absolute Aufstellhöhe 400 — unabhängig vom
    // Abschnittsfuß (z0 1300).
    expect(z).toBeCloseTo(900);
  });

  it("nutzt die Wand-Längsachse, auch wenn der Abschnitt kürzer als die Dicke ist", () => {
    const shortSection = section(pose, { x0_mm: -50, x1_mm: 50, z0_mm: 0, z1_mm: 1300 });
    const [x, y] = sectionMarkerPosition(shortSection, wallFrame);
    // trotz Länge 100 < Dicke 300 bleibt lateral auf x, standoff auf y (#99:
    // die Achse kommt aus der Wand-Pose, nie aus der Box-Ausdehnung).
    expect(x).toBeCloseTo(100);
    expect(y).toBeCloseTo(850);
  });

  it("folgt dem aktiven Platzierungs-Override über den Selektor (Issue #171, B17)", () => {
    const s = section(pose, { x0_mm: -400, x1_mm: 400, z0_mm: 0, z1_mm: 1300 });
    // Override: Abstand 900 (statt 700), Podest 300 (statt 0) — der Marker folgt
    // der effektiven Lage (Zerlegung ⊕ Override), nicht mehr der alten Zerlegung.
    const [x, y, z] = sectionMarkerPosition(s, wallFrame, {
      section_id: "s1",
      standoff_mm: 900,
      stand_height_mm: 300,
    });
    expect(x).toBeCloseTo(100); // lateral unverändert
    expect(y).toBeCloseTo(1050); // 0 + 150 (halbe Dicke) + 900 (Override-Abstand)
    expect(z).toBeCloseTo(800); // Boden 500 + 300 (Override-Podest)
  });
});

describe("sectionBaseFrame", () => {
  it("legt die Translation auf die Marker-Position im Gruppen-Frame (Basis-Höhe)", () => {
    const podest: PlacementOption = { ...pose, stand_height_mm: 400 };
    const s = section(podest, { x0_mm: -400, x1_mm: 400, z0_mm: 0, z1_mm: 1300 });
    const m = sectionBaseFrame(s, wallFrame);
    // Translation an Zeilen-Index 3,7,11 (zeilenmajor): Wand-lokal (100, 850)
    // + Nullpunkt (1000, 200); z = Boden 500 + absolute Aufstellhöhe 400.
    expect(m[3]).toBeCloseTo(1100);
    expect(m[7]).toBeCloseTo(1050);
    expect(m[11]).toBeCloseTo(900);
    expect(m[15]).toBe(1);
  });

  it("addiert die Aufstellhöhe NICHT doppelt: Frame-z = Marker-z (Issue #133)", () => {
    const podest: PlacementOption = { ...pose, stand_height_mm: 400 };
    const s = section(podest, { x0_mm: -400, x1_mm: 400, z0_mm: 1300, z1_mm: 2600 });
    const m = sectionBaseFrame(s, wallFrame);
    const [, , markerZ] = sectionMarkerPosition(s, wallFrame);
    // Fokus-Roboter steht auf derselben absoluten Höhe wie der Marker
    // (900 = Boden 500 + 400), nicht auf 500 + 400 + 400.
    expect(m[11]).toBeCloseTo(markerZ);
    expect(m[11]).toBeCloseTo(900);
  });

  it("Boden-Modus (stand_height 0): Frame-z liegt auf dem Boden (wall.zMin)", () => {
    const s = section(pose, { x0_mm: -400, x1_mm: 400, z0_mm: 1300, z1_mm: 2600 });
    const m = sectionBaseFrame(s, wallFrame);
    expect(m[11]).toBeCloseTo(500);
  });

  it("kodiert yaw als Rotation um die Hochachse (obere 2×2), sonst Identität", () => {
    const turned: PlacementOption = { ...pose, yaw_rad: Math.PI / 2 };
    const s = section(turned, { x0_mm: -400, x1_mm: 400, z0_mm: 0, z1_mm: 1300 });
    const m = sectionBaseFrame(s, wallFrame);
    expect(m[0]).toBeCloseTo(0); // cos(90°)
    expect(m[1]).toBeCloseTo(-1); // -sin(90°)
    expect(m[4]).toBeCloseTo(1); // sin(90°)
    expect(m[5]).toBeCloseTo(0);
    expect(m[10]).toBe(1); // z-Achse unberührt
  });

  it("komponiert die Wand-Drehung (Issue #99): gedrehte Wand dreht Basis + Position mit", () => {
    const turnedWall: WallFrame = { ...wallFrame, yaw: Math.PI / 2 };
    const s = section(pose, { x0_mm: -400, x1_mm: 400, z0_mm: 0, z1_mm: 1300 });
    const m = sectionBaseFrame(s, turnedWall);
    // Wand-lokal (100, 850) → um 90° gedreht (−850, 100) + Nullpunkt (1000, 200).
    expect(m[3]).toBeCloseTo(150);
    expect(m[7]).toBeCloseTo(300);
    // Rotation = Wand-yaw (90°), Platzierungs-yaw 0.
    expect(m[0]).toBeCloseTo(0);
    expect(m[4]).toBeCloseTo(1);
  });

  it("ohne yaw ist die Rotation die Identität", () => {
    const s = section(pose, { x0_mm: -400, x1_mm: 400, z0_mm: 0, z1_mm: 1300 });
    const m = sectionBaseFrame(s, wallFrame);
    expect(m[0]).toBeCloseTo(1);
    expect(m[1]).toBeCloseTo(0);
    expect(m[4]).toBeCloseTo(0);
    expect(m[5]).toBeCloseTo(1);
  });
});
