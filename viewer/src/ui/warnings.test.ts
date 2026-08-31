/**
 * Warnungs-Deckelung im Trajektorien-Panel (Issue #32): hunderte Warnungen
 * dürfen das DOM nicht fluten — Zusammenfassung je Art + gedeckelte Liste.
 */

import { describe, expect, it } from "vitest";

import { summarizeWarnings } from "./warnings";

function w(t_s: number, kind: string): { t_s: number; kind: string; message: string } {
  return { t_s, kind, message: `${kind} bei ${t_s}` };
}

describe("summarizeWarnings", () => {
  it("zeigt kleine Listen vollständig (keine Deckelung)", () => {
    const list = [w(0, "reach"), w(1, "joint_limit")];
    const s = summarizeWarnings(list, 20);
    expect(s.total).toBe(2);
    expect(s.shown).toHaveLength(2);
    expect(s.hidden).toBe(0);
    expect(s.countsByKind).toEqual({ reach: 1, joint_limit: 1 });
  });

  it("deckelt große Listen und zählt den Rest", () => {
    const list = [
      ...Array.from({ length: 500 }, (_, i) => w(i, "reach")),
      w(999, "joint_limit"),
      w(1000, "joint_limit"),
      w(1001, "joint_limit"),
    ];
    const s = summarizeWarnings(list, 20);
    expect(s.total).toBe(503);
    expect(s.shown).toHaveLength(20);
    expect(s.hidden).toBe(483);
    expect(s.countsByKind).toEqual({ reach: 500, joint_limit: 3 });
    // die ersten (frühesten) Warnungen bleiben sichtbar
    expect(s.shown[0].t_s).toBe(0);
    expect(s.shown[19].t_s).toBe(19);
  });

  it("leere Liste bleibt leer", () => {
    const s = summarizeWarnings([], 20);
    expect(s.total).toBe(0);
    expect(s.shown).toHaveLength(0);
    expect(s.hidden).toBe(0);
  });
});
