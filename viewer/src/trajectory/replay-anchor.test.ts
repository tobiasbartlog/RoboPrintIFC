/**
 * Replay-Anker auf der echten Bandlage (Issue #135): der z-Hub kommt verbatim
 * aus `meta.section_z0_mm` (Abwesenheit = 0, Altläufe bit-identisch), der
 * Podest-Sockel erscheint genau dann, wenn die Basis nach dem Hub über dem
 * Boden steht (absolute Aufstellhöhe > 0).
 */

import { describe, expect, it } from "vitest";

import { PEDESTAL_MIN_MM, replayPedestal, sectionLiftMm } from "./replay-anchor";

describe("sectionLiftMm — echte Bandlage aus meta.section_z0_mm", () => {
  it("liest z0 verbatim (oberer Abschnitt der 4×1-Zerlegung)", () => {
    expect(sectionLiftMm({ section_z0_mm: 1229.4 })).toBe(1229.4);
  });

  it("Altlauf/Modul ohne Feld ⇒ 0 (Replay bit-identisch zu heute)", () => {
    expect(sectionLiftMm({})).toBe(0);
    expect(sectionLiftMm(null)).toBe(0);
    expect(sectionLiftMm(undefined)).toBe(0);
  });

  it("nicht-endliche Werte fallen sicher auf 0", () => {
    expect(sectionLiftMm({ section_z0_mm: Number.NaN })).toBe(0);
  });
});

describe("replayPedestal — Sockel unter der Replay-Basis (Muster #133)", () => {
  const frame = (z: number) => ({
    pos_mm: [120, -700, z] as [number, number, number],
    quat: [1, 0, 0, 0] as [number, number, number, number],
  });

  it("Basis unter dem Abschnittsfuß, aber über dem Boden ⇒ Sockelhöhe = absolute Aufstellhöhe", () => {
    // Naht #132: stand 400 abs bei z0 819.6 ⇒ Basis lokal −419.6; Hub 819.6.
    const ped = replayPedestal(frame(-419.6), 819.6);
    expect(ped).not.toBeNull();
    expect(ped!.heightMm).toBeCloseTo(400.0, 6);
    expect(ped!.topZMm).toBeCloseTo(-419.6, 6);
    expect(ped!.xMm).toBe(120);
    expect(ped!.yMm).toBe(-700);
  });

  it("Basis am Boden (Boden-Modus, obere Reihe: lokal −z0 + Hub z0 = 0) ⇒ kein Sockel", () => {
    expect(replayPedestal(frame(-1300), 1300)).toBeNull();
    expect(replayPedestal(frame(0), 0)).toBeNull();
  });

  it("Altlauf ohne base_frame ⇒ kein Sockel (Legacy-Anker schleift die Basis mit)", () => {
    expect(replayPedestal(null, 800)).toBeNull();
    expect(replayPedestal(undefined, 800)).toBeNull();
  });

  it("Schwellwert: knapp unter PEDESTAL_MIN_MM zählt als am Boden", () => {
    expect(replayPedestal(frame(PEDESTAL_MIN_MM / 2), 0)).toBeNull();
    expect(replayPedestal(frame(PEDESTAL_MIN_MM), 0)).not.toBeNull();
  });
});
