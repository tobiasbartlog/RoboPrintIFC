import { describe, expect, it } from "vitest";
import { formatTime, interpolateSample } from "./interpolate";
import type { TrajectorySample } from "../artifacts/types";

function mkSample(t_s: number, io: Record<string, number>): TrajectorySample {
  return { t_s, joints_rad: [0, 0, 0, 0, 0, 0], io };
}

describe("interpolateSample", () => {
  it("returns empty io for empty samples", () => {
    const result = interpolateSample([], 1.0);
    expect(result.io).toEqual({});
  });

  it("returns single sample unchanged", () => {
    const samples = [mkSample(0, { pump: 0.8 })];
    const result = interpolateSample(samples, 5.0);
    expect(result.io.pump).toBeCloseTo(0.8);
  });

  it("returns first sample at t=0", () => {
    const samples = [mkSample(0, { pump: 0.0 }), mkSample(1, { pump: 1.0 })];
    const result = interpolateSample(samples, 0);
    expect(result.io.pump).toBeCloseTo(0.0);
  });

  it("returns last sample at t=duration", () => {
    const samples = [mkSample(0, { pump: 0.0 }), mkSample(2, { pump: 1.0 })];
    const result = interpolateSample(samples, 2);
    expect(result.io.pump).toBeCloseTo(1.0);
  });

  it("interpolates linearly in the middle", () => {
    const samples = [mkSample(0, { pump: 0.0 }), mkSample(2, { pump: 1.0 })];
    const result = interpolateSample(samples, 1);
    expect(result.io.pump).toBeCloseTo(0.5);
  });

  it("clamps t below start to first sample", () => {
    const samples = [mkSample(1, { pump: 0.2 }), mkSample(3, { pump: 0.8 })];
    const result = interpolateSample(samples, -5);
    expect(result.io.pump).toBeCloseTo(0.2);
  });

  it("clamps t above end to last sample", () => {
    const samples = [mkSample(1, { pump: 0.2 }), mkSample(3, { pump: 0.8 })];
    const result = interpolateSample(samples, 99);
    expect(result.io.pump).toBeCloseTo(0.8);
  });

  it("handles multiple samples with binary search", () => {
    const samples = [
      mkSample(0, { pump: 0.0 }),
      mkSample(1, { pump: 0.25 }),
      mkSample(2, { pump: 0.5 }),
      mkSample(3, { pump: 0.75 }),
      mkSample(4, { pump: 1.0 }),
    ];
    expect(interpolateSample(samples, 0.5).io.pump).toBeCloseTo(0.125);
    expect(interpolateSample(samples, 2.0).io.pump).toBeCloseTo(0.5);
    expect(interpolateSample(samples, 3.5).io.pump).toBeCloseTo(0.875);
  });

  it("treats missing channel in one sample as 0", () => {
    const samples = [
      mkSample(0, { pump: 0.0 }),
      mkSample(2, { pump: 1.0, foam: 0.4 }),
    ];
    const result = interpolateSample(samples, 1);
    expect(result.io.pump).toBeCloseTo(0.5);
    // foam: 0 in first sample (missing → 0), 0.4 in second → 0.2 at midpoint
    expect(result.io.foam).toBeCloseTo(0.2);
  });

  it("handles two samples with identical t_s (dt=0)", () => {
    const samples = [mkSample(1, { pump: 0.3 }), mkSample(1, { pump: 0.7 })];
    const result = interpolateSample(samples, 1);
    expect(result.io.pump).toBeCloseTo(0.3);
  });
});

describe("formatTime", () => {
  it("formats sub-minute as seconds", () => {
    expect(formatTime(5.6)).toBe("5.6 s");
  });

  it("formats exactly 60 s as 1 min", () => {
    expect(formatTime(60)).toBe("1:00.0 min");
  });

  it("formats 90 s correctly", () => {
    expect(formatTime(90)).toBe("1:30.0 min");
  });

  // Stunden-Format (Issue #33): 7,5-h-Trajektorien erschienen als "448:18.7 min".
  it("formats >= 1 h as h:mm:ss", () => {
    expect(formatTime(26898.680447)).toBe("7:28:19 h");
  });

  it("formats exactly 3600 s as 1 h", () => {
    expect(formatTime(3600)).toBe("1:00:00 h");
  });

  it("keeps minute format just below 1 h", () => {
    expect(formatTime(3599.9)).toBe("59:59.9 min");
  });

  it("carries rounded seconds into the minute (no :60)", () => {
    expect(formatTime(3659.7)).toBe("1:01:00 h");
  });

  // Übertrag auch unterhalb des Stunden-Zweigs (Issue #49): erst runden, dann verzweigen.
  it("carries 59.97 s into the minute format (no 60.0 s)", () => {
    expect(formatTime(59.97)).toBe("1:00.0 min");
  });

  it("carries 119.96 s to 2:00.0 min (no 1:60.0)", () => {
    expect(formatTime(119.96)).toBe("2:00.0 min");
  });

  it("carries 3599.97 s into the hour format (no 59:60.0 min)", () => {
    expect(formatTime(3599.97)).toBe("1:00:00 h");
  });
});
