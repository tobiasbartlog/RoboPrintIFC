import { describe, expect, it } from "vitest";

import { canNavigate, PROCESS_TABS, TAB_IDS, tabLabel } from "./tabs";

describe("Reiter-Navigation", () => {
  it("kennt die fünf Prozess-Reiter plus Bibliothek (Druckplan-Split #106: Zerlegung eigener Reiter)", () => {
    expect(TAB_IDS).toEqual([
      "projekt",
      "roboter",
      "zerlegung",
      "druckplan",
      "export",
      "bibliothek",
    ]);
    expect(PROCESS_TABS).toHaveLength(5);
    expect(PROCESS_TABS).toContain("zerlegung");
    expect(PROCESS_TABS).not.toContain("bibliothek");
    expect(TAB_IDS).not.toContain("simulation");
  });

  it("erlaubt jede Navigation — kein Zwangspfad (viewer/CONTEXT.md)", () => {
    for (const from of TAB_IDS) {
      for (const to of TAB_IDS) {
        expect(canNavigate(from, to)).toBe(true);
      }
    }
  });

  it("beschriftet jeden Reiter", () => {
    for (const id of TAB_IDS) {
      expect(tabLabel(id).length).toBeGreaterThan(0);
    }
    expect(tabLabel("projekt")).toBe("Projekt");
    expect(tabLabel("zerlegung")).toBe("Zerlegung");
    expect(tabLabel("bibliothek")).toBe("Bibliothek");
  });
});
