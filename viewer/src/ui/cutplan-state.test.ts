import { describe, expect, it } from "vitest";

import {
  addCut,
  applyEvaluation,
  initCutPlanState,
  moveCut,
  overrideFor,
  removeCut,
  replaceSectionOverrides,
  setJointOffset,
  setSectionOverride,
} from "./cutplan-state";
import type { DecompositionSection } from "../api/projects";

function section(id: string, reachable: boolean): DecompositionSection {
  return {
    section_id: id,
    order: 1,
    x0_mm: 0,
    x1_mm: 100,
    z0_mm: 0,
    z1_mm: 100,
    placement: { option_id: "platz-1", lateral_mm: 0, standoff_mm: 700, stand_height_mm: 0 },
    status: {
      reachable,
      reachable_fraction: reachable ? 1 : 0,
      n_samples: 4,
      n_reachable: reachable ? 4 : 0,
      kinematic_margin: null,
      mean_margin: null,
      warnings: [],
    },
  };
}

describe("cutplan-state: moveCut ohne Positionsänderung (Issue #37)", () => {
  it("ist ein No-op und setzt insbesondere kein dirty", () => {
    const s = initCutPlanState({ cuts: [{ orientation: "horizontal", position_mm: 1300 }] });
    const moved = moveCut(s, 0, 1300);
    expect(moved).toBe(s); // identischer Zustand — löst keinen Debounce-Check aus
    expect(moved.dirty).toBe(false);
  });
});

describe("cutplan-state: init", () => {
  it("startet leer und geprüft (dirty=false) ohne Seed", () => {
    const s = initCutPlanState();
    expect(s.cuts).toEqual([]);
    expect(s.jointOffsetMm).toBe(0);
    expect(s.sectionOverrides).toEqual([]);
    expect(s.sections).toEqual([]);
    expect(s.dirty).toBe(false);
  });

  it("übernimmt einen wiederhergestellten Stand (aus dem Druckjob)", () => {
    const s = initCutPlanState({
      cuts: [{ orientation: "horizontal", position_mm: 1300 }],
      jointOffsetMm: 50,
      sectionOverrides: [{ section_id: "abschnitt-1", option_id: "stellplatz-1" }],
      sections: [section("abschnitt-1", true)],
    });
    expect(s.cuts).toEqual([{ orientation: "horizontal", position_mm: 1300 }]);
    expect(s.jointOffsetMm).toBe(50);
    expect(s.dirty).toBe(false);
  });

  it("kopiert Seed-Arrays (keine geteilten Referenzen)", () => {
    const seedCuts = [{ orientation: "horizontal" as const, position_mm: 1300 }];
    const s = initCutPlanState({ cuts: seedCuts });
    s.cuts[0].position_mm = 999;
    expect(seedCuts[0].position_mm).toBe(1300);
  });
});

describe("cutplan-state: Schnitte hinzufügen/verschieben/entfernen", () => {
  it("addCut hängt eine Schnittebene an und markiert dirty", () => {
    const s0 = initCutPlanState();
    const s1 = addCut(s0, "horizontal", 1300);
    expect(s1.cuts).toEqual([{ orientation: "horizontal", position_mm: 1300 }]);
    expect(s1.dirty).toBe(true);
    // Ursprungszustand bleibt unverändert (reine Funktion).
    expect(s0.cuts).toEqual([]);
  });

  it("moveCut ändert dieselbe Schnittebene, egal ob von Drag oder Zahlenfeld aufgerufen", () => {
    let s = initCutPlanState();
    s = addCut(s, "vertical", 0);
    // Drag (three.js) ruft moveCut auf …
    s = moveCut(s, 0, 250);
    expect(s.cuts[0].position_mm).toBe(250);
    // … Zahlenfeld ruft dieselbe Funktion auf demselben Zustand auf.
    s = moveCut(s, 0, 300);
    expect(s.cuts[0].position_mm).toBe(300);
    expect(s.dirty).toBe(true);
  });

  it("moveCut mit ungültigem Index ist ein no-op", () => {
    const s0 = initCutPlanState({ cuts: [{ orientation: "horizontal", position_mm: 1300 }] });
    const s1 = moveCut(s0, 5, 999);
    expect(s1).toEqual(s0);
  });

  it("removeCut entfernt per Index und markiert dirty", () => {
    let s = initCutPlanState();
    s = addCut(s, "horizontal", 1300);
    s = addCut(s, "vertical", 0);
    s = applyEvaluation(s, [section("abschnitt-1", true)]); // simuliert einen geprüften Stand
    expect(s.dirty).toBe(false);

    s = removeCut(s, 0);
    expect(s.cuts).toEqual([{ orientation: "vertical", position_mm: 0 }]);
    expect(s.dirty).toBe(true);
  });

  it("removeCut mit ungültigem Index ist ein no-op", () => {
    const s0 = initCutPlanState({ cuts: [{ orientation: "horizontal", position_mm: 1300 }] });
    const s1 = removeCut(s0, -1);
    expect(s1).toEqual(s0);
    const s2 = removeCut(s0, 3);
    expect(s2).toEqual(s0);
  });
});

describe("cutplan-state: Fugen-Versatz", () => {
  it("setJointOffset setzt den Parameter und markiert dirty", () => {
    const s0 = initCutPlanState();
    const s1 = setJointOffset(s0, 150);
    expect(s1.jointOffsetMm).toBe(150);
    expect(s1.dirty).toBe(true);
  });
});

describe("cutplan-state: Platzierungs-Override je Abschnitt", () => {
  it("setSectionOverride weist eine Aufstellmöglichkeit zu und markiert dirty", () => {
    const s0 = applyEvaluation(initCutPlanState(), [section("abschnitt-1", true)]);
    const s1 = setSectionOverride(s0, "abschnitt-1", "stellplatz-2");
    expect(overrideFor(s1, "abschnitt-1")).toBe("stellplatz-2");
    expect(s1.dirty).toBe(true);
  });

  it("setSectionOverride ersetzt eine bestehende Zuweisung desselben Abschnitts", () => {
    let s = setSectionOverride(initCutPlanState(), "abschnitt-1", "stellplatz-1");
    s = setSectionOverride(s, "abschnitt-1", "stellplatz-2");
    expect(s.sectionOverrides).toEqual([{ section_id: "abschnitt-1", option_id: "stellplatz-2" }]);
  });

  it("setSectionOverride mit null hebt die Zuweisung auf", () => {
    let s = setSectionOverride(initCutPlanState(), "abschnitt-1", "stellplatz-1");
    s = setSectionOverride(s, "abschnitt-1", null);
    expect(s.sectionOverrides).toEqual([]);
    expect(overrideFor(s, "abschnitt-1")).toBeNull();
  });

  it("overrideFor liefert null, wenn kein Override gesetzt ist", () => {
    const s = initCutPlanState();
    expect(overrideFor(s, "abschnitt-1")).toBeNull();
  });

  it("setSectionOverride bewahrt freie Platzierungswerte des Eintrags (#94)", () => {
    // Freie Werte (Issue #94) sind eine eigene Ebene über der Referenz: das
    // Zuweisen/Aufheben einer option_id räumt sie nicht mit.
    const s0 = initCutPlanState({
      sectionOverrides: [{ section_id: "abschnitt-1", standoff_mm: 900 }],
    });
    const s1 = setSectionOverride(s0, "abschnitt-1", "stellplatz-1");
    expect(s1.sectionOverrides).toEqual([
      { section_id: "abschnitt-1", standoff_mm: 900, option_id: "stellplatz-1" },
    ]);
    const s2 = setSectionOverride(s1, "abschnitt-1", null);
    expect(s2.sectionOverrides).toEqual([{ section_id: "abschnitt-1", standoff_mm: 900 }]);
  });

  it("replaceSectionOverrides übernimmt den persistierten Stand und markiert dirty (#94)", () => {
    const s0 = applyEvaluation(
      initCutPlanState({ sectionOverrides: [{ section_id: "abschnitt-1", option_id: "x" }] }),
      [section("abschnitt-1", true)],
    );
    expect(s0.dirty).toBe(false);
    const persisted = [{ section_id: "abschnitt-1", option_id: "x", lateral_mm: 120 }];
    const s1 = replaceSectionOverrides(s0, persisted);
    expect(s1.sectionOverrides).toEqual(persisted);
    expect(s1.sectionOverrides[0]).not.toBe(persisted[0]); // Kopie, kein Alias
    expect(s1.dirty).toBe(true); // Bewertung steht aus → Ampel „ungeprüft"
  });
});

describe("cutplan-state: dirty/'ungeprüft' bis zur Neubewertung", () => {
  it("jede Änderung setzt dirty=true, auch nach vorherigem applyEvaluation", () => {
    let s = initCutPlanState();
    s = applyEvaluation(s, [section("abschnitt-1", true)]);
    expect(s.dirty).toBe(false);

    s = addCut(s, "horizontal", 1300);
    expect(s.dirty).toBe(true);
  });

  it("applyEvaluation ist der einzige Weg, dirty wieder auf false zu setzen", () => {
    let s = initCutPlanState();
    s = addCut(s, "horizontal", 1300);
    expect(s.dirty).toBe(true);

    const sections = [section("abschnitt-1", true), section("abschnitt-2", false)];
    s = applyEvaluation(s, sections);
    expect(s.dirty).toBe(false);
    expect(s.sections).toEqual(sections);
  });

  it("Abschnitte aus einer vorherigen Bewertung bleiben erhalten, bis eine neue eintrifft", () => {
    let s = initCutPlanState();
    s = applyEvaluation(s, [section("abschnitt-1", true)]);
    s = moveCut(s, 0, 500); // no-op (kein Cut vorhanden), aber Prinzip: dirty ändert nichts an sections
    expect(s.sections).toEqual([section("abschnitt-1", true)]);
    s = addCut(s, "horizontal", 500);
    expect(s.dirty).toBe(true);
    // Die alten Abschnitte sind weiterhin da (die UI muss sie als "ungeprüft" markieren,
    // nicht löschen) — genau das prüft dieses Modul: dirty=true + alte sections gleichzeitig.
    expect(s.sections).toEqual([section("abschnitt-1", true)]);
  });
});
