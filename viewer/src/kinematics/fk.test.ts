import { describe, expect, it } from "vitest";
import golden from "./fk.golden.json";
import { expectGoldenParity } from "../test/golden-parity";
import {
  anchorFlangeToTarget,
  dhMatrix,
  forwardChain,
  frameToMat,
  identity,
  invertRigid,
  multiply,
  orientationAngle,
  positionOf,
  quaternionOf,
  type DhParams,
} from "./fk";
import { M1013_DH } from "./robot";

// Toleranzen des FK-Testorakels (ADR-009-Muster). Die Viewer-FK ist dieselbe
// analytische Standard-DH-Kette wie die Core-FK, daher rein numerisch (double)
// begrenzt. Position: euklidischer Abstand in mm. Orientierung: maximale
// vorzeichenangeglichene Komponentendifferenz der Quaternionen — direkter und
// numerisch stabiler als der geodätische Winkel, dessen acos nahe dot=1
// künstlich verstärkt. Beobachtet ~1e-9; Schranken mit Reserve gesetzt.
const POS_TOL_MM = 1e-6;
const QUAT_TOL = 1e-8;

/** Maximale Komponentendifferenz zweier Quaternionen nach Vorzeichenangleich. */
function quatCompDiff(
  a: readonly number[],
  b: readonly number[],
): number {
  const dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  const s = dot < 0 ? -1 : 1; // q und −q sind dieselbe Rotation
  let m = 0;
  for (let i = 0; i < 4; i++) m = Math.max(m, Math.abs(a[i] - s * b[i]));
  return m;
}

const dh = golden.dh as DhParams;

describe("forwardChain gegen Core-Golden (Testorakel, ADR-009)", () => {
  it("liefert 7 Glied-Frames; Basis ist die Identität", () => {
    const frames = forwardChain(dh, golden.cases[0].joints_rad);
    expect(frames).toHaveLength(7);
    expect(positionOf(frames[0])).toEqual([0, 0, 0]);
    expect(orientationAngle(quaternionOf(frames[0]), [1, 0, 0, 0])).toBeCloseTo(0, 12);
  });

  it("reproduziert jede Gliedpose des Core innerhalb Toleranz", () => {
    expectGoldenParity(
      golden.cases,
      (c) => forwardChain(dh, c.joints_rad),
      (got, c, label) => {
        const frames = got as ReturnType<typeof forwardChain>;
        expect(frames).toHaveLength(c.links.length);
        c.links.forEach((link, i) => {
          const gp = link.pos_mm as [number, number, number];
          const gq = link.quat as [number, number, number, number];
          const p = positionOf(frames[i]);
          const pos = Math.hypot(p[0] - gp[0], p[1] - gp[1], p[2] - gp[2]);
          expect(pos, `${label} pos[${i}]`).toBeLessThan(POS_TOL_MM);
          expect(quatCompDiff(quaternionOf(frames[i]), gq), `${label} quat[${i}]`).toBeLessThan(
            QUAT_TOL,
          );
        });
      },
    );
  });
});

describe("Viewer-DH gegen Golden-DH (Driftschutz)", () => {
  it("M1013_DH entspricht der DH, aus der die Golden-Werte stammen", () => {
    expect(M1013_DH).toEqual(golden.dh);
  });
});

describe("Matrix-Bausteine", () => {
  it("dhMatrix mit theta=0, a=d=alpha=0 ist die Identität", () => {
    const m = dhMatrix(0, 0, 0, 0);
    const id = identity();
    for (let i = 0; i < 16; i++) expect(m[i]).toBeCloseTo(id[i], 12);
  });

  it("multiply(M, I) == M", () => {
    const m = dhMatrix(620, 34.5, Math.PI / 2, 0.3);
    const prod = multiply(m, identity());
    for (let i = 0; i < 16; i++) expect(prod[i]).toBeCloseTo(m[i], 12);
  });

  it("invertRigid(M)·M == I für eine starre Transformation", () => {
    const m = forwardChain(dh, golden.cases[5].joints_rad)[6];
    const prod = multiply(invertRigid(m), m);
    for (let i = 0; i < 16; i++) {
      expect(prod[i]).toBeCloseTo(identity()[i], 9);
    }
  });

  it("frameToMat/quaternionOf sind zueinander konsistent", () => {
    const q: [number, number, number, number] = [0.5, 0.5, 0.5, 0.5];
    const m = frameToMat([10, 20, 30], q);
    expect(positionOf(m)).toEqual([10, 20, 30]);
    expect(orientationAngle(quaternionOf(m), q)).toBeLessThan(1e-9);
  });
});

describe("anchorFlangeToTarget", () => {
  it("legt den Flansch exakt auf das Ziel-Frame (anchor·flange == target)", () => {
    const flange = forwardChain(dh, golden.cases[6].joints_rad)[6];
    const target = frameToMat([1500, -300, 900], [1, 0, 0, 0]);
    const anchor = anchorFlangeToTarget(flange, target);
    const placed = multiply(anchor, flange);
    // Position trifft
    const tp = positionOf(target);
    const pp = positionOf(placed);
    expect(Math.hypot(pp[0] - tp[0], pp[1] - tp[1], pp[2] - tp[2])).toBeLessThan(1e-6);
    // Orientierung trifft
    expect(orientationAngle(quaternionOf(placed), quaternionOf(target))).toBeLessThan(1e-9);
  });
});
