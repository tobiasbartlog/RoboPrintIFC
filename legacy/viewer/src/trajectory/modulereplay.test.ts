import { describe, expect, it } from "vitest";

import {
  moduleReplayFrame,
  projectModuleMarkers,
  type ModuleLocalMarker,
} from "./modulereplay";
import {
  buildSequencePlan,
  locateSequenceTime,
  type SequenceCursor,
} from "./sequence";

function seg(id: string, order: number, duration_s: number) {
  return { section_id: id, order, duration_s };
}

describe("moduleReplayFrame", () => {
  it("Druckphase: aktives Modul = sectionIndex, Arm + Marker sichtbar, Fraktion = localFraction", () => {
    const cur: SequenceCursor = {
      sectionIndex: 1,
      localTime_s: 5,
      localFraction: 0.5,
      phase: "printing",
      toSectionIndex: 1,
      umbauFraction: 0,
    };
    expect(moduleReplayFrame(cur)).toEqual({
      moduleIndex: 1,
      armVisible: true,
      markerVisible: true,
      markerFraction: 0.5,
      growthFraction: 0.5,
    });
  });

  it("Umbau-Phase: aktives Modul = toSectionIndex, Arm + Marker unsichtbar", () => {
    const cur: SequenceCursor = {
      sectionIndex: 0,
      localTime_s: 10,
      localFraction: 1,
      phase: "umbau",
      toSectionIndex: 1,
      umbauFraction: 0.5,
    };
    const frame = moduleReplayFrame(cur);
    expect(frame.moduleIndex).toBe(1); // nächstes Modul kommt auf die Fläche
    expect(frame.armVisible).toBe(false);
    expect(frame.markerVisible).toBe(false);
    expect(frame.markerFraction).toBe(1);
    // Wachstum ruht im Umbau bei 0 — das ankommende Modul ist noch leer (#152),
    // bewusst anders als markerFraction (dort 1, aber unsichtbar).
    expect(frame.growthFraction).toBe(0);
  });

  it("speist den Marker aus der LOKALEN Modulzeit, nicht der Sequenz-Gesamtzeit", () => {
    // Zeitleiste: a[0..10] · umbau[10..15] · b[15..35], total 35.
    const plan = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 5);
    // Globale Zeit 25 liegt in Modul b bei lokal 10/20 = 0.5 — nicht 25/35.
    const frame = moduleReplayFrame(locateSequenceTime(plan, 25));
    expect(frame.moduleIndex).toBe(1);
    expect(frame.armVisible).toBe(true);
    expect(frame.markerFraction).toBeCloseTo(0.5, 6);
  });

  it("im Umbau zwischen den Modulen ruht der Marker (nächstes Modul steht schon)", () => {
    const plan = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 5);
    const frame = moduleReplayFrame(locateSequenceTime(plan, 12)); // umbau[10..15]
    expect(frame.moduleIndex).toBe(1);
    expect(frame.markerVisible).toBe(false);
    expect(frame.armVisible).toBe(false);
  });

  it("Wachstum (Strang + Druckstand) folgt der lokalen Modulzeit in der Druckphase", () => {
    // Zeitleiste: a[0..10] · umbau[10..15] · b[15..35], total 35.
    const plan = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 5);
    // Modul a bei lokal 2.5/10 = 0.25.
    expect(moduleReplayFrame(locateSequenceTime(plan, 2.5)).growthFraction).toBeCloseTo(0.25, 6);
    // Modul b bei lokal 10/20 = 0.5 (global 25) — nicht 25/35.
    expect(moduleReplayFrame(locateSequenceTime(plan, 25)).growthFraction).toBeCloseTo(0.5, 6);
  });

  it("Modulwechsel setzt das Wachstum zurück: neues Modul startet im Umbau bei 0", () => {
    const plan = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 5);
    // Direkt vor dem Umbau druckt a fast fertig (global 9.9 → lokal 0.99).
    expect(moduleReplayFrame(locateSequenceTime(plan, 9.9)).growthFraction).toBeGreaterThan(0.98);
    // Im Umbau steht b schon auf der Fläche, aber leer (0) — kein Übertrag von a.
    const umbau = moduleReplayFrame(locateSequenceTime(plan, 12));
    expect(umbau.moduleIndex).toBe(1);
    expect(umbau.growthFraction).toBe(0);
    // Beginn von b (global 15) wächst dann sauber ab 0.
    expect(moduleReplayFrame(locateSequenceTime(plan, 15)).growthFraction).toBeCloseTo(0, 6);
  });

  it("am Sequenz-Ende ist das letzte Modul voll gewachsen (Fraktion 1)", () => {
    const plan = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 5);
    const frame = moduleReplayFrame(locateSequenceTime(plan, 35));
    expect(frame.moduleIndex).toBe(1);
    expect(frame.growthFraction).toBeCloseTo(1, 6);
  });
});

describe("projectModuleMarkers — modul-lokale Intervalle auf die Sequenzachse (#153)", () => {
  // Zeitleiste: a[0..10] · umbau[10..15] · b[15..35], total 35.
  const plan = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 5);

  /** Ein modul-lokaler Marker (Fraktionen über der Modul-Dauer, Sekunden lokal). */
  function local(over: Partial<ModuleLocalMarker> & { extra?: string } = {}) {
    return {
      startFraction: 0.4,
      endFraction: 0.6,
      midFraction: 0.5,
      seekTime_s: 10, // lokale Mitte in Sekunden (bei Modul b: 10/20 = 0.5)
      extra: "unberührt",
      ...over,
    };
  }

  it("verschiebt lokale Sekunden um den Modul-Offset und normiert auf total_s (b)", () => {
    // Modul b: Offset starts_s[1] = 15, Modul-Dauer 20, total 35.
    const [m] = projectModuleMarkers([local()], plan, 1);
    // seekTime_s: 15 + 10 = 25 s (global); midFraction 25/35.
    expect(m.seekTime_s).toBeCloseTo(25, 6);
    expect(m.midFraction).toBeCloseTo(25 / 35, 6);
    // start/end: 15 + 0.4*20 = 23 und 15 + 0.6*20 = 27.
    expect(m.startFraction).toBeCloseTo(23 / 35, 6);
    expect(m.endFraction).toBeCloseTo(27 / 35, 6);
  });

  it("das erste Modul (Offset 0) skaliert nur auf total_s", () => {
    // Modul a: Offset 0, Dauer 10, lokale Mitte 5 s.
    const [m] = projectModuleMarkers([local({ seekTime_s: 5 })], plan, 0);
    expect(m.seekTime_s).toBeCloseTo(5, 6);
    expect(m.midFraction).toBeCloseTo(5 / 35, 6);
  });

  it("(c) Marker am Modul-Ende landen an der Druckphasen-Grenze, nie in der Umbaupause", () => {
    // Lokale Mitte = volle Modul-Dauer (10 s) ⇒ global 10 = Ende der Druckphase a,
    // genau vor der Umbaupause [10..15]. Kein Marker rutscht in den Umbau.
    const [m] = projectModuleMarkers([local({ seekTime_s: 10, endFraction: 1 })], plan, 0);
    expect(m.seekTime_s).toBeCloseTo(10, 6);
    expect(m.endFraction).toBeCloseTo(10 / 35, 6);
    expect(m.seekTime_s).toBeLessThanOrEqual(plan.starts_s[1]); // < Beginn Modul b
  });

  it("lässt Status/Titel-Felder unangetastet (verschiebt nur die Zeitachse)", () => {
    const [m] = projectModuleMarkers([local({ extra: "rot-warnung" })], plan, 1);
    expect(m.extra).toBe("rot-warnung");
  });

  it("unbekannter Modulindex oder leere Zeitleiste ⇒ keine Marker (kein Crash)", () => {
    expect(projectModuleMarkers([local()], plan, 5)).toEqual([]);
    const empty = buildSequencePlan([], 5);
    expect(projectModuleMarkers([local()], empty, 0)).toEqual([]);
  });

  it("leere Marker-Liste ⇒ leere Liste", () => {
    expect(projectModuleMarkers([], plan, 0)).toEqual([]);
  });
});
