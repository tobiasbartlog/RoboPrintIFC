/**
 * Tests der reinen Auswahl-/Ausdünnungs-/Sichtbarkeitslogik der Punkt-
 * nummerierung (Issue #138). three.js-frei — die Sprite-Erzeugung in
 * `toolpath.ts` bleibt hier bewusst ungetestet (kein WebGL im vitest-Lauf).
 */
import { describe, expect, it } from "vitest";

import {
  MAX_TARGET_LABELS,
  significantTargetIndices,
  targetLabelVisible,
  targetLabels,
  thinIndices,
  type TargetLabel,
} from "./target-labels-state";
import type { Target } from "../artifacts/types";

/** Baut ein minimales Target — nur die für die Auswahl relevanten Felder zählen. */
function target(kind: "print" | "travel", layer: number, segment_id: string, x = 0): Target {
  return {
    frame: { pos_mm: [x, 0, 0], quat: [1, 0, 0, 0] },
    v_mm_s: 50,
    io: {},
    kind,
    layer,
    segment_id,
  };
}

describe("significantTargetIndices", () => {
  it("leere Liste → leere Liste", () => {
    expect(significantTargetIndices([])).toEqual([]);
  });

  it("ein einzelnes Target → nur Index 0", () => {
    expect(significantTargetIndices([target("travel", 0, "L0_R0")])).toEqual([0]);
  });

  it("markiert den ersten Punkt, jeden kind-Wechsel und jeden Ring-/Schichtwechsel", () => {
    const targets = [
      target("travel", 0, "L0_R0_approach"), // 0: Start
      target("print", 0, "L0_R0"), // 1: kind-Wechsel (travel→print), neue segment_id
      target("print", 0, "L0_R0"), // 2: gleiche segment_id, gleicher kind → nicht signifikant
      target("print", 0, "L0_R0"), // 3: dito
      target("travel", 0, "L0_R1_approach"), // 4: kind-Wechsel + neuer Ring
      target("print", 0, "L0_R1"), // 5: kind-Wechsel + neue segment_id
      target("print", 1, "L1_R0"), // 6: gleicher kind, aber neue Schicht → segment_id ändert sich
    ];
    expect(significantTargetIndices(targets)).toEqual([0, 1, 4, 5, 6]);
  });

  it("gleicher kind + gleiche segment_id über viele Targets → nur der erste zählt", () => {
    const targets = Array.from({ length: 20 }, (_, i) => target("print", 0, "L0_R0", i));
    expect(significantTargetIndices(targets)).toEqual([0]);
  });
});

describe("thinIndices", () => {
  it("bleibt unverändert, wenn die Liste die Obergrenze nicht überschreitet", () => {
    expect(thinIndices([0, 5, 9], 10)).toEqual([0, 5, 9]);
    expect(thinIndices([0, 5, 9], 3)).toEqual([0, 5, 9]);
  });

  it("maxCount <= 0 → leer", () => {
    expect(thinIndices([0, 1, 2], 0)).toEqual([]);
    expect(thinIndices([0, 1, 2], -5)).toEqual([]);
  });

  it("dünnt gleichmäßig aus, nie mehr als maxCount Einträge, erster Index bleibt", () => {
    const indices = Array.from({ length: 1000 }, (_, i) => i);
    const thinned = thinIndices(indices, 100);
    expect(thinned.length).toBeLessThanOrEqual(100);
    expect(thinned[0]).toBe(0);
    // Aufsteigend sortiert (keine Cluster/Sprünge rückwärts).
    for (let i = 1; i < thinned.length; i++) expect(thinned[i]).toBeGreaterThan(thinned[i - 1]);
    // Über die ganze Bahn verteilt, nicht nur am Anfang abgeschnitten.
    expect(thinned[thinned.length - 1]).toBeGreaterThan(900);
  });
});

describe("targetLabels", () => {
  it("kombiniert Auswahl + Deckelung und trägt Position/Layer/Art mit", () => {
    const targets = [
      target("travel", 0, "L0_R0_approach", 10),
      target("print", 0, "L0_R0", 20),
      target("print", 0, "L0_R0", 30),
    ];
    const labels = targetLabels(targets, 10);
    expect(labels).toEqual([
      { index: 0, layer: 0, kind: "travel", pos_mm: [10, 0, 0] },
      { index: 1, layer: 0, kind: "print", pos_mm: [20, 0, 0] },
    ]);
  });

  it("respektiert die Standard-Obergrenze MAX_TARGET_LABELS bei riesigen Bahnen", () => {
    // 5000 Targets, jedes ein eigener Ring (worst case: jeder Punkt signifikant).
    const targets = Array.from({ length: 5000 }, (_, i) =>
      target(i % 2 === 0 ? "travel" : "print", Math.floor(i / 100), `L${i}`, i),
    );
    const labels = targetLabels(targets);
    expect(labels.length).toBeLessThanOrEqual(MAX_TARGET_LABELS);
  });

  it("wenige Targets bleiben alle sichtbar (kein Ausdünnen nötig)", () => {
    const targets = [
      target("travel", 0, "L0_R0_approach"),
      target("print", 0, "L0_R0"),
      target("travel", 1, "L1_R0_approach"),
      target("print", 1, "L1_R0"),
    ];
    expect(targetLabels(targets).map((l) => l.index)).toEqual([0, 1, 2, 3]);
  });
});

describe("targetLabelVisible", () => {
  const base: TargetLabel = { index: 5, layer: 2, kind: "print", pos_mm: [0, 0, 0] };

  it("ausgeschalteter Schalter → nie sichtbar, unabhängig vom Zustand", () => {
    expect(
      targetLabelVisible(base, false, {
        growthMode: false,
        growthIndex: 0,
        visibleUpTo: 2,
        onlyCurrent: false,
        travelVisible: true,
      }),
    ).toBe(false);
  });

  it("Layer-Modus: sichtbar bis zum Layer-Slider (visibleUpTo), sonst nicht", () => {
    const state = {
      growthMode: false,
      growthIndex: 0,
      visibleUpTo: 2,
      onlyCurrent: false,
      travelVisible: true,
    };
    expect(targetLabelVisible(base, true, state)).toBe(true); // layer 2 <= 2
    expect(targetLabelVisible({ ...base, layer: 3 }, true, state)).toBe(false); // 3 > 2
  });

  it("Layer-Modus mit onlyCurrent: nur exakt der aktuelle Layer", () => {
    const state = {
      growthMode: false,
      growthIndex: 0,
      visibleUpTo: 2,
      onlyCurrent: true,
      travelVisible: true,
    };
    expect(targetLabelVisible({ ...base, layer: 1 }, true, state)).toBe(false);
    expect(targetLabelVisible({ ...base, layer: 2 }, true, state)).toBe(true);
  });

  it("Wachs-Modus: sichtbar, sobald der Fortschritt den Target-Index erreicht hat", () => {
    const state = {
      growthMode: true,
      growthIndex: 5,
      visibleUpTo: 999,
      onlyCurrent: false,
      travelVisible: true,
    };
    expect(targetLabelVisible(base, true, state)).toBe(true); // 5 <= 5
    expect(targetLabelVisible({ ...base, index: 6 }, true, state)).toBe(false); // 6 > 5
  });

  it("Travel-Schalter aus blendet Travel-Labels aus, Print-Labels bleiben unberührt", () => {
    const state = {
      growthMode: false,
      growthIndex: 0,
      visibleUpTo: 2,
      onlyCurrent: false,
      travelVisible: false,
    };
    expect(targetLabelVisible({ ...base, kind: "travel" }, true, state)).toBe(false);
    expect(targetLabelVisible({ ...base, kind: "print" }, true, state)).toBe(true);
  });
});
