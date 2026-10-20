/**
 * Reine Aktions-/Beschriftungslogik des Simulations-Docks (Issue #108, vormals
 * `druckplan-mode.test.ts`): das Simulier-Ziel (Fokus-Teil, abwärtskompatibel bei
 * genau einem Teil) und die artabhängige Beschriftung der beiden Simulier-Knöpfe.
 * Die Modus-Prädikate der Fusion #86 sind mit dem Dock-Umbau entfallen.
 */

import { describe, expect, it } from "vitest";

import {
  focusSimHint,
  focusSimLabel,
  focusSimTitle,
  focusTarget,
  sequenceSimHint,
  sequenceSimLabel,
  sequenceSimTitle,
  simPlaysAtDruckort,
} from "./sim-actions";

describe("focusTarget", () => {
  it("nimmt das Fokus-Teil, wenn es (noch) existiert", () => {
    expect(focusTarget("s2", ["s1", "s2", "s3"])).toBe("s2");
  });

  it("gibt bei genau einem Teil dieses — auch ohne Fokus (US 24)", () => {
    expect(focusTarget(null, ["nur-einer"])).toBe("nur-einer");
  });

  it("gibt null ohne eindeutiges Ziel (kein Fokus, mehrere Teile)", () => {
    expect(focusTarget(null, ["s1", "s2"])).toBeNull();
  });

  it("verwirft einen weggefallenen Fokus", () => {
    expect(focusTarget("weg", ["s1", "s2"])).toBeNull();
  });

  it("gibt null bei leerer Teileliste", () => {
    expect(focusTarget(null, [])).toBeNull();
    expect(focusTarget("s1", [])).toBeNull();
  });
});

// Artabhängige Simulieren-Knöpfe (Issue #97). Der Abschnitt-Zweig MUSS
// bit-identisch zu vor der Scheibe bleiben (Regressionstest); der Modul-Zweig
// beschriftet auf „Fokus-Modul simulieren" + „Alle Module" und spielt am Druckort.
describe("artabhängige Simulieren-Knöpfe (#97)", () => {
  describe("Beschriftung folgt der Zerlegungsart", () => {
    it("Modul-Beschriftung: Fokus-Modul simulieren + Alle Module", () => {
      expect(focusSimLabel("modul")).toBe("Fokus-Modul simulieren");
      expect(sequenceSimLabel("modul")).toBe("Alle Module");
    });

    it("simuliert am Druckort nur bei Modulen (Abschnitt: in place)", () => {
      expect(simPlaysAtDruckort("modul")).toBe(true);
      expect(simPlaysAtDruckort("abschnitt")).toBe(false);
    });

    it("Modul-Tooltips nennen Druckort + Montagereihenfolge", () => {
      expect(focusSimTitle("modul")).toContain("Druckort");
      expect(sequenceSimTitle("modul")).toContain("Montagereihenfolge");
    });
  });

  // Regression: Abschnitt-Modus verhält sich bit-identisch wie vor #97 — die
  // Strings sind wörtlich die aus index.html / simulation.ts festgeschriebenen.
  describe("Abschnitt-Modus bleibt bit-identisch (Regression)", () => {
    it("Knopf-Beschriftungen unverändert", () => {
      expect(focusSimLabel("abschnitt")).toBe("Fokus-Abschnitt simulieren");
      expect(sequenceSimLabel("abschnitt")).toBe("Ganze Wand (unten → oben)");
    });

    it("Tooltips unverändert", () => {
      expect(focusSimTitle("abschnitt")).toBe(
        "Fokus-Abschnitt slicen + als vollen Arm-Lauf abspielen (#26)",
      );
      expect(sequenceSimTitle("abschnitt")).toBe(
        "Alle Abschnitte in Druckreihenfolge abspielen (unten → oben, Sequenz #27)",
      );
    });

    it("Fokus-Hinweis unverändert (alle drei Zustände)", () => {
      expect(focusSimHint("abschnitt", null, 0)).toBe("Noch keine Abschnitte.");
      expect(focusSimHint("abschnitt", null, 3)).toBe(
        "Kein Abschnitt im Fokus — im 3D-Feld oder in der Liste einen wählen.",
      );
      expect(focusSimHint("abschnitt", "s2", 3)).toBe(
        "Simuliert Abschnitt „s2“ und spielt den vollen Arm-Lauf ab.",
      );
    });

    it("Sequenz-Hinweis unverändert (bereit / leer / unvollständig)", () => {
      expect(sequenceSimHint("abschnitt", true, 3, 0)).toBe(
        "Spielt alle Abschnitte in Druckreihenfolge (unten → oben) — mit " +
          "sichtbarem Umbau-Schritt zwischen den Abschnitten; Gedrucktes bleibt stehen.",
      );
      expect(sequenceSimHint("abschnitt", false, 0, 0)).toBe("Noch keine Abschnitte.");
      expect(sequenceSimHint("abschnitt", false, 3, 2)).toBe(
        "Noch nicht abspielbar: 2 von 3 Abschnitten sind noch nicht simuliert.",
      );
    });
  });

  describe("Modul-Hinweise nennen Modul + Druckort", () => {
    it("Fokus-Hinweis je Zustand", () => {
      expect(focusSimHint("modul", null, 0)).toBe("Noch keine Module.");
      expect(focusSimHint("modul", null, 3)).toBe(
        "Kein Modul im Fokus — im 3D-Feld oder in der Liste eines wählen.",
      );
      expect(focusSimHint("modul", "m2", 3)).toBe(
        "Simuliert Modul „m2“ und spielt den vollen Arm-Lauf am Druckort ab.",
      );
    });

    it("Sequenz-Hinweis nennt Montagereihenfolge + Durchtauschen", () => {
      const ready = sequenceSimHint("modul", true, 3, 0);
      expect(ready).toContain("Montagereihenfolge");
      expect(ready).toContain("durchgetauscht");
      expect(sequenceSimHint("modul", false, 0, 0)).toBe("Noch keine Module.");
      expect(sequenceSimHint("modul", false, 3, 2)).toBe(
        "Noch nicht abspielbar: 2 von 3 Modulen sind noch nicht simuliert.",
      );
    });
  });
});
