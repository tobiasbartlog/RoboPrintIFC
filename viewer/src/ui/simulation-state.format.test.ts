/**
 * formatDuration-Übertrag (Issue #49): Math.round der Restsekunden konnte 60
 * ergeben („1:60 min"); lange Drucke (> 1 h) brauchen das Stundenformat.
 */

import { describe, expect, it } from "vitest";

import { formatDuration } from "./simulation-state";

describe("formatDuration", () => {
  it("formatiert unter einer Minute mit Zehntel", () => {
    expect(formatDuration(5.64)).toBe("5.6 s");
  });

  it("überträgt gerundete 60 Sekunden in die Minute (kein 1:60)", () => {
    expect(formatDuration(119.6)).toBe("2:00 min");
  });

  it("überträgt 59.97 s in das Minutenformat (kein 60.0 s)", () => {
    expect(formatDuration(59.97)).toBe("1:00 min");
  });

  it("formatiert Stunden als h:mm:ss (Druckzeit 7,5 h)", () => {
    expect(formatDuration(26898.68)).toBe("7:28:19 h");
  });

  it("bleibt bei ungültigen Werten beim Gedankenstrich", () => {
    expect(formatDuration(Number.NaN)).toBe("—");
    expect(formatDuration(-3)).toBe("—");
  });
});
