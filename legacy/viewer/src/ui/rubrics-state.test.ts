/**
 * Reiner Rubriken-Zustand (Issue #89, PRD #88): welche Rubrik aktiv ist, ohne
 * DOM. Das Ein-/Ausblenden testet `library-rubrics.test.ts` (jsdom); hier nur
 * die Auswahl-Logik.
 */

import { describe, expect, it } from "vitest";

import { RubricsState } from "./rubrics-state";

type Id = "zerlegung" | "slicing";
const IDS: readonly Id[] = ["zerlegung", "slicing"];

describe("RubricsState (Issue #89)", () => {
  it("startet mit der angegebenen Rubrik", () => {
    const state = new RubricsState(IDS, "zerlegung");
    expect(state.active).toBe("zerlegung");
    expect(state.isActive("zerlegung")).toBe(true);
    expect(state.isActive("slicing")).toBe(false);
    expect(state.ids).toEqual(["zerlegung", "slicing"]);
  });

  it("setActive wechselt die aktive Rubrik und meldet die Änderung", () => {
    const state = new RubricsState(IDS, "zerlegung");
    expect(state.setActive("slicing")).toBe(true);
    expect(state.active).toBe("slicing");
    expect(state.isActive("slicing")).toBe(true);
  });

  it("setActive auf die bereits aktive Rubrik meldet keine Änderung", () => {
    const state = new RubricsState(IDS, "slicing");
    expect(state.setActive("slicing")).toBe(false);
    expect(state.active).toBe("slicing");
  });

  it("wirft bei unbekannter Start-Rubrik", () => {
    expect(() => new RubricsState(IDS, "foo" as Id)).toThrow();
  });

  it("wirft bei leerer Rubrik-Liste", () => {
    expect(() => new RubricsState([] as readonly Id[], "zerlegung")).toThrow();
  });

  it("wirft beim Aktivieren einer unbekannten Rubrik", () => {
    const state = new RubricsState(IDS, "zerlegung");
    expect(() => state.setActive("foo" as Id)).toThrow();
    expect(state.active).toBe("zerlegung");
  });

  it("kopiert die Id-Liste defensiv (kein Alias auf das Argument)", () => {
    const src: Id[] = ["zerlegung", "slicing"];
    const state = new RubricsState(src, "zerlegung");
    src.push("x" as Id);
    expect(state.ids).toEqual(["zerlegung", "slicing"]);
  });
});
