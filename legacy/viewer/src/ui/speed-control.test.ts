/**
 * Reine Rechnung der Abspielgeschwindigkeit (Issue #155): Faktor → Replay-Dauer +
 * Beschriftung. DOM-frei — die Umbaupausen dürfen NICHT mit dem Faktor schrumpfen.
 */

import { describe, expect, it } from "vitest";

import {
  SPEED_STEPS,
  formatEta,
  formatRate,
  replayEta,
  speedOptionLabel,
} from "./speed-control";

describe("SPEED_STEPS", () => {
  it("ist die vorgesehene Leiter und enthält die Voreinstellung 1×", () => {
    expect(SPEED_STEPS).toEqual([0.25, 0.5, 1, 2, 5, 10, 25, 50, 100, 200]);
    expect(SPEED_STEPS).toContain(1);
  });
});

describe("formatRate", () => {
  it("hängt das ×-Zeichen an, ohne Nachkomma-Aufblähung", () => {
    expect(formatRate(0.25)).toBe("0.25×");
    expect(formatRate(1)).toBe("1×");
    expect(formatRate(200)).toBe("200×");
  });
});

describe("replayEta", () => {
  it("teilt die Druckphasen durch den Faktor", () => {
    expect(replayEta(100, 0, 1)).toBe(100);
    expect(replayEta(100, 0, 2)).toBe(50);
    expect(replayEta(100, 0, 100)).toBe(1);
  });

  it("lässt die Umbaupausen UNGETEILT (Erzählzeit, skaliert nicht mit)", () => {
    // 100 s Druck + 6 s Umbau: bei 100× bleibt der Umbau volle 6 s.
    expect(replayEta(100, 6, 100)).toBeCloseTo(1 + 6);
    expect(replayEta(100, 6, 1)).toBeCloseTo(106);
  });

  it("klemmt rate<=0 auf 1 (keine Division durch 0)", () => {
    expect(replayEta(100, 0, 0)).toBe(100);
    expect(replayEta(100, 0, -5)).toBe(100);
  });
});

describe("formatEta", () => {
  it("gibt ~M:SS unter einer Stunde", () => {
    expect(formatEta(104)).toBe("~1:44");
    expect(formatEta(52)).toBe("~0:52");
    expect(formatEta(0)).toBe("~0:00");
  });

  it("gibt ~H:MM:SS ab einer Stunde", () => {
    expect(formatEta(5212)).toBe("~1:26:52");
  });
});

describe("speedOptionLabel", () => {
  it("nennt Faktor UND resultierende Replay-Dauer", () => {
    // 5212 s Druck, keine Umbaupause → bei 50× ~1:44.
    expect(speedOptionLabel(50, 5212, 0)).toBe("50× · ~1:44");
    expect(speedOptionLabel(1, 5212, 0)).toBe("1× · ~1:26:52");
  });
});
