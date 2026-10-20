/**
 * Schnittebenen-Orientierung (Issue #34): die Ebenen leben im Wand-lokalen
 * z-hoch-Frame (Issue #99: die Drehung in den Gruppen-Frame übernimmt die
 * Ebenen-Gruppe an der PCA-Wand-Pose). Ein Höhenschnitt muss die Normale
 * entlang z haben (Länge × Dicke aufspannen), ein Längsschnitt die Normale
 * entlang der Wand-Längsachse x (Dicke × Höhe aufspannen). Der Ur-Bug:
 * y-hoch-Rotationen im z-hoch-Frame.
 */

import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { CUT_PLANE_OVERHANG_MM, cutPlaneSpec } from "./cutplanes";
import type { WallFrame } from "./wall-frame";

const O2 = 2 * CUT_PLANE_OVERHANG_MM;

/** Bild der PlaneGeometry-Achsen (Breite=x, Höhe=y, Normale=z) unter der Euler-Rotation. */
function dirs(rotation: [number, number, number]) {
  const e = new THREE.Euler(rotation[0], rotation[1], rotation[2], "XYZ");
  return {
    width: new THREE.Vector3(1, 0, 0).applyEuler(e),
    height: new THREE.Vector3(0, 1, 0).applyEuler(e),
    normal: new THREE.Vector3(0, 0, 1).applyEuler(e),
  };
}

function expectParallel(v: THREE.Vector3, axis: [number, number, number]): void {
  const dot = Math.abs(v.dot(new THREE.Vector3(...axis)));
  expect(dot).toBeCloseTo(1, 6);
}

/** Wand-Pose: der yaw ist für die Wand-lokale Spec irrelevant (Gruppe dreht). */
const wall: WallFrame = {
  origin: { x: 1234, y: -567 },
  yaw: 0.5,
  center: { x: 10, y: 20 },
  length_mm: 4000,
  thickness_mm: 260,
  height_mm: 2600,
  zMin: 0,
};

describe("cutPlaneSpec: Höhenschnitt (horizontal)", () => {
  const spec = cutPlaneSpec({ orientation: "horizontal", position_mm: 1300 }, wall);

  it("spannt Länge (x) × Dicke (y) auf, Normale entlang z", () => {
    const d = dirs(spec.rotation);
    expectParallel(d.width, [1, 0, 0]);
    expectParallel(d.height, [0, 1, 0]);
    expectParallel(d.normal, [0, 0, 1]);
  });

  it("liegt bei z = Wandfuß + position, mittig über der Wand, und überragt sie", () => {
    expect(spec.origin).toEqual([10, 20, 1300]);
    expect(spec.size).toEqual([4000 + O2, 260 + O2]);
  });

  it("Drag-Achse ist z", () => {
    expect(spec.axisLocal).toEqual([0, 0, 1]);
  });
});

describe("cutPlaneSpec: Längsschnitt (vertical)", () => {
  const spec = cutPlaneSpec({ orientation: "vertical", position_mm: 500 }, wall);

  it("spannt Dicke (y) × Höhe (z) auf, Normale entlang der Wand-Längsachse x", () => {
    const d = dirs(spec.rotation);
    expectParallel(d.width, [0, 1, 0]);
    expectParallel(d.height, [0, 0, 1]);
    expectParallel(d.normal, [1, 0, 0]);
  });

  it("liegt Wand-lokal direkt bei x = position (Core-Schnittframe), mittig in der Höhe", () => {
    // Issue #99: die Schnittposition lebt im Wand-lokalen Nullpunkt des Core
    // (decompose.apply) — kein Extent-Mitten-Versatz auf der Längsachse.
    expect(spec.origin).toEqual([500, 20, 1300]);
    expect(spec.size).toEqual([260 + O2, 2600 + O2]);
  });

  it("Drag-Achse ist die Wand-Längsachse x", () => {
    expect(spec.axisLocal).toEqual([1, 0, 0]);
  });
});
