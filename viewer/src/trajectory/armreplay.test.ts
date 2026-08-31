import { describe, expect, it } from "vitest";
import { computeArmPose, interpJoints, interpTargetFrame } from "./armreplay";
import { forwardChain, frameToMat, multiply, positionOf, type DhParams } from "../kinematics/fk";
import type { Frame, Target, TrajectorySample } from "../artifacts/types";
import { M1013_DH } from "../kinematics/robot";

const dh: DhParams = M1013_DH;

function sample(t: number, q: [number, number, number, number, number, number]): TrajectorySample {
  return { t_s: t, joints_rad: q, io: {} };
}

function target(pos: [number, number, number]): Target {
  return {
    frame: { pos_mm: pos, quat: [1, 0, 0, 0] },
    v_mm_s: 10,
    io: {},
    kind: "print",
    layer: 0,
    segment_id: "s",
  };
}

describe("interpJoints", () => {
  it("liefert Nullwinkel bei leeren Samples", () => {
    expect(interpJoints([], 0.5)).toEqual([0, 0, 0, 0, 0, 0]);
  });

  it("gibt das einzige Sample unverändert zurück", () => {
    expect(interpJoints([sample(0, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])], 0.7)).toEqual([
      0.1, 0.2, 0.3, 0.4, 0.5, 0.6,
    ]);
  });

  it("interpoliert in der Mitte linear", () => {
    const s = [sample(0, [0, 0, 0, 0, 0, 0]), sample(1, [1, 2, 3, 4, 5, 6])];
    expect(interpJoints(s, 0.5)).toEqual([0.5, 1, 1.5, 2, 2.5, 3]);
  });
});

describe("interpTargetFrame", () => {
  it("interpoliert die Position linear", () => {
    const ts = [target([0, 0, 0]), target([10, 20, 30])];
    expect(interpTargetFrame(ts, 0.5).pos_mm).toEqual([5, 10, 15]);
  });
});

describe("computeArmPose — Flansch trifft TCP", () => {
  it("legt den FK-Flansch exakt auf die interpolierte TCP-Position", () => {
    const samples = [
      sample(0, [0.2, -0.4, 0.7, 0.1, 0.8, -0.3]),
      sample(1, [-0.3, 0.5, -0.6, 0.9, -0.2, 1.1]),
    ];
    const targets = [target([1200, -400, 300]), target([1250, -350, 800])];
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      const { joints_rad, anchor } = computeArmPose(dh, samples, targets, f);
      const flange = forwardChain(dh, joints_rad)[6];
      const placed = positionOf(multiply(anchor, flange));
      const expected = interpTargetFrame(targets, f).pos_mm;
      const d = Math.hypot(
        placed[0] - expected[0],
        placed[1] - expected[1],
        placed[2] - expected[2],
      );
      expect(d).toBeLessThan(1e-6);
    }
  });

  it("ohne Targets ist der Anker die Identität (Arm in Basiskoordinaten)", () => {
    const samples = [sample(0, [0, 0, 0, 0, 0, 0])];
    const { anchor } = computeArmPose(dh, samples, null, 0);
    // Anker·flange == flange  ⇒  Anker ≈ Identität
    expect(anchor[0]).toBeCloseTo(1, 9);
    expect(anchor[5]).toBeCloseTo(1, 9);
    expect(anchor[10]).toBeCloseTo(1, 9);
    expect(anchor[3]).toBeCloseTo(0, 6);
  });
});

describe("computeArmPose — feste Basis (base_frame, Issue #66)", () => {
  // base_in_wall: Basis 900 mm vor der Wand, 200 mm hoch, um 30° gedreht.
  const yaw = Math.PI / 6;
  const baseFrame: Frame = {
    pos_mm: [150, 900, 200],
    quat: [Math.cos(yaw / 2), 0, 0, Math.sin(yaw / 2)],
  };

  it("verankert die Basis fix — Anker über die Zeit konstant und == frameToMat(base_frame)", () => {
    const samples = [
      sample(0, [0.2, -0.4, 0.7, 0.1, 0.8, -0.3]),
      sample(1, [-0.3, 0.5, -0.6, 0.9, -0.2, 1.1]),
    ];
    const targets = [target([1200, -400, 300]), target([1250, -350, 800])];
    const expected = frameToMat(baseFrame.pos_mm, baseFrame.quat);
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      const { anchor } = computeArmPose(dh, samples, targets, f, baseFrame);
      for (let k = 0; k < 16; k++) expect(anchor[k]).toBeCloseTo(expected[k], 9);
    }
  });

  it("mit base_frame + TCP-Offset landet der TCP genau auf dem Ziel (Core-Kette)", () => {
    // Kern-Identität der Simulation: anchor · flange · tcp = target, sofern die
    // Gelenke die echte IK-Lösung sind. Konstruiere das Ziel core-konsistent
    // (target = base_in_wall · FK · tcp) und prüfe, dass die Viewer-Kette es trifft.
    const joints: [number, number, number, number, number, number] = [
      0.3, -0.5, 0.8, -0.2, 0.6, 0.1,
    ];
    const tcp = frameToMat([0, 0, 250], [1, 0, 0, 0]); // Düse 250 mm vor dem Flansch
    const anchor = frameToMat(baseFrame.pos_mm, baseFrame.quat);
    const flange = forwardChain(dh, joints)[6];
    const target = multiply(multiply(anchor, flange), tcp);

    const pose = computeArmPose(dh, [sample(0, joints)], null, 0, baseFrame);
    const tcpPlaced = positionOf(multiply(multiply(pose.anchor, flange), tcp));
    const goal = positionOf(target);
    const d = Math.hypot(tcpPlaced[0] - goal[0], tcpPlaced[1] - goal[1], tcpPlaced[2] - goal[2]);
    expect(d).toBeLessThan(1e-6);
  });

  it("null base_frame fällt auf den Legacy-Anker zurück (Flansch aufs Ziel)", () => {
    const samples = [sample(0, [0.2, -0.4, 0.7, 0.1, 0.8, -0.3])];
    const targets = [target([1200, -400, 300])];
    const { anchor } = computeArmPose(dh, samples, targets, 0, null);
    const flange = forwardChain(dh, samples[0].joints_rad)[6];
    const placed = positionOf(multiply(anchor, flange));
    expect(Math.hypot(placed[0] - 1200, placed[1] + 400, placed[2] - 300)).toBeLessThan(1e-6);
  });
});
