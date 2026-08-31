/**
 * Gebäudekontext-Schalter-Normalisierung (Issue #131) — reine Logik, ohne Renderer.
 *
 * Kern: Altprojekte ohne `check_building_context`-Feld verhalten sich wie `false`;
 * nur exakt `true` schaltet die Kontext-Prüfung ein (Persist/Restore-Anker).
 */

import { describe, expect, it } from "vitest";

import { DEFAULT_CONTEXT_CHECK, normalizeContextCheck } from "./kontext-state";

describe("normalizeContextCheck", () => {
  it("Default ist false (aus)", () => {
    expect(DEFAULT_CONTEXT_CHECK).toBe(false);
  });

  it("fehlendes Feld (Altprojekt) → false", () => {
    expect(normalizeContextCheck(undefined)).toBe(false);
    expect(normalizeContextCheck(null)).toBe(false);
  });

  it("true bleibt true (Persist/Restore)", () => {
    expect(normalizeContextCheck(true)).toBe(true);
  });

  it("false bleibt false", () => {
    expect(normalizeContextCheck(false)).toBe(false);
  });
});
