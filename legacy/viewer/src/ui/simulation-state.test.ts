import { describe, expect, it } from "vitest";

import {
  formatDuration,
  maxAxisUtilization,
  sequenceReady,
  summaryFromMeta,
  summaryLine,
} from "./simulation-state";

describe("maxAxisUtilization", () => {
  it("returns the largest axis load", () => {
    expect(maxAxisUtilization([0.1, 0.7, 0.3, 0.2, 0.5, 0.4])).toBeCloseTo(0.7);
  });
  it("returns 0 for an empty list", () => {
    expect(maxAxisUtilization([])).toBe(0);
  });
});

describe("formatDuration", () => {
  it("formats sub-minute durations in seconds", () => {
    expect(formatDuration(12.34)).toBe("12.3 s");
  });
  it("formats longer durations as minutes:seconds", () => {
    expect(formatDuration(95)).toBe("1:35 min");
  });
  it("guards against invalid input", () => {
    expect(formatDuration(-1)).toBe("—");
    expect(formatDuration(Number.NaN)).toBe("—");
  });
});

describe("summaryLine", () => {
  it("summarizes duration, max axis load and warning count", () => {
    const line = summaryLine({
      duration_s: 42,
      n_warnings: 0,
      axis_utilization: [0.2, 0.6, 0.1, 0.1, 0.1, 0.1],
      pose_source: "planned",
    });
    expect(line).toContain("Druckzeit 42.0 s");
    expect(line).toContain("max. Achse 60 %");
    expect(line).toContain("keine Warnungen");
  });

  it("pluralizes warnings correctly", () => {
    expect(
      summaryLine({ duration_s: 1, n_warnings: 1, axis_utilization: [], pose_source: "planned" }),
    ).toContain("1 Warnung");
    expect(
      summaryLine({ duration_s: 1, n_warnings: 3, axis_utilization: [], pose_source: "planned" }),
    ).toContain("3 Warnungen");
  });
});

describe("summaryFromMeta", () => {
  it("liest Kennzahlen aus dem trajectory.meta-Block (Issue #48, Befund 3)", () => {
    const summary = summaryFromMeta({
      duration_s: 42,
      axis_utilization: [0.2, 0.6, 0.1, 0.1, 0.1, 0.1],
      warnings: [{ kind: "reach" }, { kind: "singularity" }],
      pose_source: "planned",
    });
    expect(summary).toEqual({
      duration_s: 42,
      n_warnings: 2,
      axis_utilization: [0.2, 0.6, 0.1, 0.1, 0.1, 0.1],
      pose_source: "planned",
    });
  });

  it("verträgt fehlende Felder (Altläufe): 0 Warnungen, leere Auslastung, pose_source=planned", () => {
    const summary = summaryFromMeta({ duration_s: 7 });
    expect(summary).toEqual({
      duration_s: 7,
      n_warnings: 0,
      axis_utilization: [],
      pose_source: "planned",
    });
  });

  it("ergibt eine anzeigbare Zusammenfassung (Rundschlag mit summaryLine)", () => {
    const line = summaryLine(summaryFromMeta({ duration_s: 95, warnings: [{ kind: "reach" }] }));
    expect(line).toContain("Druckzeit 1:35 min");
    expect(line).toContain("1 Warnung");
  });
});

describe("sequenceReady", () => {
  it("ist true, wenn jeder Abschnitt einen Lauf hat", () => {
    expect(sequenceReady(["a", "b", "c"], ["a", "b", "c"])).toBe(true);
  });
  it("ist false, wenn ein Abschnitt keinen Lauf hat", () => {
    expect(sequenceReady(["a", "b", "c"], ["a", "c"])).toBe(false);
  });
  it("ist false ohne Abschnitte", () => {
    expect(sequenceReady([], ["a"])).toBe(false);
  });
  it("einzelner Abschnitt mit Lauf genügt (abwärtskompatibel)", () => {
    expect(sequenceReady(["a"], ["a"])).toBe(true);
  });
});
