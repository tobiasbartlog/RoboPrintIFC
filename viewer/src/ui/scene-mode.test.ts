/**
 * Szenenmodus je Reiter (Issue #30/#31): das geteilte Hauptsichtfeld zeigt je
 * nach aktivem Reiter die Modellübersicht (world), die Roboter-Vorschau
 * (Reiter Roboter) — die Bibliothek hat ihre eigene Szene (#cfg-viewport).
 */

import { describe, expect, it } from "vitest";

import { sceneModeForTab } from "./scene-mode";

describe("sceneModeForTab", () => {
  it("Reiter Roboter zeigt die Roboter-Vorschau", () => {
    expect(sceneModeForTab("roboter")).toBe("robot-vorschau");
  });

  it("Bibliothek nutzt die eigene Konfigurator-Szene", () => {
    expect(sceneModeForTab("bibliothek")).toBe("bibliothek");
  });

  it.each(["projekt", "druckplan", "export"] as const)(
    "Reiter %s zeigt die Modellübersicht (world)",
    (tab) => {
      expect(sceneModeForTab(tab)).toBe("world");
    },
  );
});
