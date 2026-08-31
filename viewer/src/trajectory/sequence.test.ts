import { describe, expect, it } from "vitest";

import {
  buildSequencePlan,
  locateSequenceTime,
  sequenceRateAt,
  targetIndexAtProgress,
  type SequenceSegment,
} from "./sequence";

function seg(id: string, order: number, duration_s: number): SequenceSegment {
  return { section_id: id, order, duration_s };
}

describe("buildSequencePlan", () => {
  it("sortiert nach order und summiert Druck- + Umbau-Dauern", () => {
    const plan = buildSequencePlan(
      [seg("b", 2, 20), seg("a", 1, 10), seg("c", 3, 30)],
      5,
    );
    expect(plan.segments.map((s) => s.section_id)).toEqual(["a", "b", "c"]);
    // 10 + 5 + 20 + 5 + 30 = 70
    expect(plan.total_s).toBe(70);
    // Starts: a@0, b@15, c@40
    expect(plan.starts_s).toEqual([0, 15, 40]);
    expect(plan.umbau_s).toBe(5);
  });

  it("einzelner Abschnitt: keine Umbau-Dauer im Total (abwärtskompatibel)", () => {
    const plan = buildSequencePlan([seg("a", 1, 42)], 5);
    expect(plan.total_s).toBe(42);
    expect(plan.starts_s).toEqual([0]);
  });

  it("leere Sequenz: total 0", () => {
    const plan = buildSequencePlan([], 5);
    expect(plan.total_s).toBe(0);
    expect(plan.starts_s).toEqual([]);
  });

  it("klemmt negative Dauern (Umbau + Abschnitt) auf 0", () => {
    const plan = buildSequencePlan([seg("a", 1, -10), seg("b", 2, 20)], -3);
    expect(plan.umbau_s).toBe(0);
    expect(plan.total_s).toBe(20);
    expect(plan.starts_s).toEqual([0, 0]);
  });
});

describe("locateSequenceTime", () => {
  const plan = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 5);
  // Zeitleiste: a[0..10] · umbau[10..15] · b[15..35], total 35.

  it("Mitte des ersten Abschnitts", () => {
    const c = locateSequenceTime(plan, 5);
    expect(c.phase).toBe("printing");
    expect(c.sectionIndex).toBe(0);
    expect(c.localTime_s).toBe(5);
    expect(c.localFraction).toBeCloseTo(0.5);
  });

  it("Ende der ersten Druckphase zählt noch als printing (Umbau folgt erst danach)", () => {
    const c = locateSequenceTime(plan, 10);
    expect(c.phase).toBe("printing");
    expect(c.sectionIndex).toBe(0);
    expect(c.localFraction).toBe(1);
  });

  it("innerhalb des Umbau-Schritts", () => {
    const c = locateSequenceTime(plan, 12.5);
    expect(c.phase).toBe("umbau");
    expect(c.sectionIndex).toBe(0);
    expect(c.toSectionIndex).toBe(1);
    expect(c.umbauFraction).toBeCloseTo(0.5);
    expect(c.localFraction).toBe(1); // erster Abschnitt bleibt voll gedruckt
  });

  it("Mitte des zweiten Abschnitts", () => {
    const c = locateSequenceTime(plan, 25);
    expect(c.phase).toBe("printing");
    expect(c.sectionIndex).toBe(1);
    expect(c.localTime_s).toBe(10);
    expect(c.localFraction).toBeCloseTo(0.5);
  });

  it("klemmt über das Ende hinaus auf den letzten Abschnitt (voll gedruckt)", () => {
    const c = locateSequenceTime(plan, 999);
    expect(c.phase).toBe("printing");
    expect(c.sectionIndex).toBe(1);
    expect(c.localFraction).toBe(1);
  });

  it("klemmt negative Zeit auf den Anfang", () => {
    const c = locateSequenceTime(plan, -5);
    expect(c.sectionIndex).toBe(0);
    expect(c.localTime_s).toBe(0);
    expect(c.localFraction).toBe(0);
  });

  it("einzelner Abschnitt: nie eine Umbau-Phase (abwärtskompatibel)", () => {
    const single = buildSequencePlan([seg("a", 1, 10)], 5);
    expect(locateSequenceTime(single, 0).phase).toBe("printing");
    expect(locateSequenceTime(single, 5).phase).toBe("printing");
    expect(locateSequenceTime(single, 10).phase).toBe("printing");
    expect(locateSequenceTime(single, 10).localFraction).toBe(1);
  });

  it("umbau_s=0: direkter Übergang, keine Umbau-Phase", () => {
    const noUmbau = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 0);
    // a[0..10] · b[10..30]. Bei t=10 endet a (printing), bei t=10+ε ist b aktiv.
    expect(locateSequenceTime(noUmbau, 10).sectionIndex).toBe(0);
    expect(locateSequenceTime(noUmbau, 15).sectionIndex).toBe(1);
    expect(locateSequenceTime(noUmbau, 15).phase).toBe("printing");
  });

  it("Abschnitt mit Dauer 0: Fraktion 0, kein NaN", () => {
    const zero = buildSequencePlan([seg("a", 1, 0), seg("b", 2, 10)], 2);
    const c = locateSequenceTime(zero, 0);
    expect(c.sectionIndex).toBe(0);
    expect(c.localFraction).toBe(0);
    expect(Number.isNaN(c.localFraction)).toBe(false);
  });
});

describe("sequenceRateAt (Abspiel-Rate + Phasengrenze, #155)", () => {
  const plan = buildSequencePlan([seg("a", 1, 10), seg("b", 2, 20)], 5);
  // Zeitleiste: a[0..10] · umbau[10..15] · b[15..35], total 35.

  it("in einer Druckphase gilt der Faktor, Grenze = Ende der Druckphase", () => {
    expect(sequenceRateAt(plan, 5, 200)).toEqual({ rate: 200, until_s: 10 });
    expect(sequenceRateAt(plan, 25, 200)).toEqual({ rate: 200, until_s: 35 });
  });

  it("in der Umbaupause gilt 1× (skaliert nicht mit), Grenze = Ende der Pause", () => {
    expect(sequenceRateAt(plan, 12, 200)).toEqual({ rate: 1, until_s: 15 });
  });

  it("VORWÄRTS gerichtet: genau auf der Druck-Ende-Grenze gilt schon die Umbau-Rate", () => {
    // Anders als locateSequenceTime (t=10 = printing) blickt die Rate nach vorn:
    // ab t=10 beginnt die Pause → Rate 1, sonst gäbe es ein Null-Intervall.
    expect(sequenceRateAt(plan, 10, 200)).toEqual({ rate: 1, until_s: 15 });
    // Am Ende der Pause beginnt die nächste Druckphase.
    expect(sequenceRateAt(plan, 15, 200)).toEqual({ rate: 200, until_s: 35 });
  });

  it("die until_s ist strikt größer als t (kein Null-Intervall → kein Stillstand)", () => {
    for (const t of [0, 10, 12, 15, 25, 34.999]) {
      expect(sequenceRateAt(plan, t, 50).until_s).toBeGreaterThan(t);
    }
  });

  it("am/über dem Ende: Faktor + until Infinity (Player stoppt ohnehin an duration)", () => {
    expect(sequenceRateAt(plan, 35, 200)).toEqual({
      rate: 200,
      until_s: Number.POSITIVE_INFINITY,
    });
    expect(sequenceRateAt(plan, 999, 200).until_s).toBe(Number.POSITIVE_INFINITY);
  });

  it("einzelner Abschnitt: konstant der Faktor, keine Pause-Grenze", () => {
    const single = buildSequencePlan([seg("a", 1, 10)], 5);
    expect(sequenceRateAt(single, 0, 25)).toEqual({ rate: 25, until_s: 10 });
    expect(sequenceRateAt(single, 5, 25)).toEqual({ rate: 25, until_s: 10 });
  });
});

describe("targetIndexAtProgress", () => {
  it("bildet f ∈ [0,1] auf den Fraktions-Index [0, n-1] ab", () => {
    expect(targetIndexAtProgress(11, 0)).toBe(0);
    expect(targetIndexAtProgress(11, 1)).toBe(10);
    expect(targetIndexAtProgress(11, 0.5)).toBe(5);
  });

  it("klemmt und behandelt Randfälle (0/1 Target)", () => {
    expect(targetIndexAtProgress(1, 0.7)).toBe(0);
    expect(targetIndexAtProgress(0, 0.7)).toBe(0);
    expect(targetIndexAtProgress(5, 2)).toBe(4);
    expect(targetIndexAtProgress(5, -1)).toBe(0);
  });
});
