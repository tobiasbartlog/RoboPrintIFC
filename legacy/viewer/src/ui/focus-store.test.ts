/**
 * Fokus-Store (Issue #196): der EINE Halter des Wand-/Teil-Fokus. Portiert die
 * Auswahl-Logik-Tests des früheren `focus-state.ts` (#84) auf den Store und
 * fixiert zusätzlich den Wirkungs-Vertrag (`FOCUS_EFFECT_ORDER`): Mitglieder
 * und Reihenfolge der früheren `onFocusChanged`-Kaskade aus `main.ts`.
 */

import { describe, expect, it } from "vitest";

import {
  FOCUS_EFFECT_ORDER,
  FocusStore,
  registerFocusEffects,
  type FocusEffectName,
  type FocusEffects,
} from "./focus-store";

describe("FocusStore: Auswahl-Logik (Toggle + Reconcile, #84)", () => {
  it("Ausgangszustand: kein Fokus", () => {
    const s = new FocusStore();
    expect(s.get()).toBeNull();
  });

  it("toggle wählt einen Abschnitt als Fokus", () => {
    const s = new FocusStore();
    s.toggle("abschnitt-2");
    expect(s.get()).toBe("abschnitt-2");
  });

  it("erneuter toggle auf denselben Abschnitt hebt den Fokus auf", () => {
    const s = new FocusStore();
    s.toggle("abschnitt-2");
    s.toggle("abschnitt-2");
    expect(s.get()).toBeNull();
  });

  it("toggle auf einen anderen Abschnitt übernimmt den Fokus", () => {
    const s = new FocusStore();
    s.toggle("abschnitt-1");
    s.toggle("abschnitt-3");
    expect(s.get()).toBe("abschnitt-3");
  });

  it("reconcile behält einen noch vorhandenen Fokus", () => {
    const s = new FocusStore();
    s.toggle("abschnitt-2");
    s.reconcile(["abschnitt-1", "abschnitt-2", "abschnitt-3"]);
    expect(s.get()).toBe("abschnitt-2");
  });

  it("reconcile verwirft einen Fokus, dessen Abschnitt verschwand (Neuzerlegung)", () => {
    const s = new FocusStore();
    s.toggle("abschnitt-9");
    s.reconcile(["abschnitt-1", "abschnitt-2"]);
    expect(s.get()).toBeNull();
  });

  it("reconcile mit nur einem Abschnitt bleibt sauber", () => {
    const single = ["abschnitt-1"];
    const s = new FocusStore();
    s.toggle("abschnitt-1");
    s.reconcile(single);
    expect(s.get()).toBe("abschnitt-1");
    // Ohne Fokus bleibt reconcile ein No-op.
    const none = new FocusStore();
    none.reconcile(single);
    expect(none.get()).toBeNull();
  });
});

describe("FocusStore: Subscriber (nur echte Änderungen, Registrier-Reihenfolge)", () => {
  it("subscribe feuert bei jeder echten Änderung mit dem neuen Wert", () => {
    const s = new FocusStore();
    const seen: (string | null)[] = [];
    s.subscribe((id) => seen.push(id));
    s.toggle("a");
    s.toggle("b");
    s.toggle("b");
    expect(seen).toEqual(["a", "b", null]);
  });

  it("No-ops bleiben still: reconcile ohne Wegfall feuert nicht", () => {
    const s = new FocusStore();
    s.toggle("a");
    let calls = 0;
    s.subscribe(() => { calls += 1; });
    s.reconcile(["a", "b"]); // Fokus bleibt → keine Wirkung
    s.reconcile([]); // Fokus fällt weg → EINE Wirkung
    expect(calls).toBe(1);
    expect(s.get()).toBeNull();
  });

  it("Subscriber laufen in Registrier-Reihenfolge; abbestellen wirkt", () => {
    const s = new FocusStore();
    const order: string[] = [];
    const off = s.subscribe(() => order.push("erster"));
    s.subscribe(() => order.push("zweiter"));
    s.toggle("a");
    expect(order).toEqual(["erster", "zweiter"]);
    off();
    s.toggle("a"); // → null
    expect(order).toEqual(["erster", "zweiter", "zweiter"]);
  });
});

describe("Wirkungs-Vertrag registerFocusEffects (Issue #196, Muster #193)", () => {
  /** Fake-Ports: protokollieren Name + übergebene section_id. */
  function recordingEffects(log: { name: FocusEffectName; id: string | null }[]): FocusEffects {
    const effects = {} as Record<FocusEffectName, (id: string | null) => void>;
    for (const name of FOCUS_EFFECT_ORDER) {
      effects[name] = (id) => { log.push({ name, id }); };
    }
    return effects;
  }

  it("Mitglieder-Menge und Reihenfolge sind der Vertrag der alten 10-Ziel-Kaskade", () => {
    // Die frühere onFocusChanged-Kaskade (main.ts, #84…#139), als Liste:
    // Highlight → Marker↔Mesh → Gilt-für-Umschalter → Slicing-Scope (ehemals
    // Zwei-Hop) → Platzierungsfelder → Titel → Druckort → Kamera →
    // Live-Vorschau → Sim-Dock → Kollisions-Advisor.
    expect(FOCUS_EFFECT_ORDER).toEqual([
      "highlightSectionBox",
      "swapPlacementFocusMesh",
      "reconcileScopeSwitch",
      "syncProcessParamsScope",
      "syncPlacementOverrideScope",
      "setPlacementTitle",
      "syncDruckort",
      "frameFocus",
      "updatePreparePreview",
      "syncSimulationDock",
      "syncCollisionAdvisorScope",
    ]);
  });

  it("jeder Fokus-Wechsel ruft ALLE Effekte in Vertrags-Reihenfolge mit der section_id", () => {
    const store = new FocusStore();
    const log: { name: FocusEffectName; id: string | null }[] = [];
    registerFocusEffects(store, recordingEffects(log));
    store.toggle("abschnitt-2");
    expect(log.map((e) => e.name)).toEqual([...FOCUS_EFFECT_ORDER]);
    expect(log.every((e) => e.id === "abschnitt-2")).toBe(true);
  });

  it("Abwahl (Toggle auf null) läuft durch dieselbe Kaskade", () => {
    const store = new FocusStore();
    const log: { name: FocusEffectName; id: string | null }[] = [];
    store.toggle("abschnitt-2");
    registerFocusEffects(store, recordingEffects(log));
    store.toggle("abschnitt-2"); // Abwahl
    expect(log.map((e) => e.name)).toEqual([...FOCUS_EFFECT_ORDER]);
    expect(log.every((e) => e.id === null)).toBe(true);
  });

  it("reconcile-Wegfall (Teil verschwindet durch Neuzerlegung) feuert die Kaskade", () => {
    const store = new FocusStore();
    const log: { name: FocusEffectName; id: string | null }[] = [];
    store.toggle("weg");
    registerFocusEffects(store, recordingEffects(log));
    store.reconcile(["abschnitt-1"]);
    expect(log.map((e) => e.name)).toEqual([...FOCUS_EFFECT_ORDER]);
    expect(log.every((e) => e.id === null)).toBe(true);
  });
});
