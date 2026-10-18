/**
 * Zerlegungsart-Weiche Abschnitte↔Module — reiner Zustand (Issue #95, ADR-022):
 * Sichtbarkeitsmatrix (`.hidden`-Werte), Beschriftungen, Workstation-Hinweis
 * und die drei Artwechsel-Regeln (Schnitte bleiben / Slicing-Overrides
 * überleben / Platzierungs-Overrides verfallen).
 */

import { describe, expect, it } from "vitest";

import type { Cut, SectionOverride, SectionProcessOverride } from "../api/projects";
import {
  normalizeZerlegungsart,
  paletteTitle,
  partLabel,
  switchArt,
  visibilityFor,
  workstationHint,
} from "./zerlegungsart-state";

describe("Sichtbarkeitsmatrix — artspezifische Einstellungen (nur .hidden)", () => {
  it("Abschnitt: Aufstell-Toggle sichtbar, max-Maße-Felder versteckt", () => {
    expect(visibilityFor("abschnitt")).toEqual({
      aufstellHidden: false,
      moduleLimitsHidden: true,
    });
  });

  it("Modul: max-Maße-Felder sichtbar, Aufstell-Toggle versteckt", () => {
    expect(visibilityFor("modul")).toEqual({
      aufstellHidden: true,
      moduleLimitsHidden: false,
    });
  });

  it("nie beide Gruppen gleichzeitig sichtbar oder versteckt (Weiche)", () => {
    for (const art of ["abschnitt", "modul"] as const) {
      const vis = visibilityFor(art);
      expect(vis.aufstellHidden).not.toBe(vis.moduleLimitsHidden);
    }
  });
});

describe("Beschriftungen — Palette + Teil-Namen schalten mit der Art", () => {
  it("Palette heißt Abschnitte bzw. Module", () => {
    expect(paletteTitle("abschnitt")).toBe("Abschnitte");
    expect(paletteTitle("modul")).toBe("Module");
  });

  it("Teil-Namen: Abschnitt N / Modul N (Anzeige, nie die section_id)", () => {
    expect(partLabel("abschnitt", 3)).toBe("Abschnitt 3");
    expect(partLabel("modul", 3)).toBe("Modul 3");
  });

  it("normalisiert Altprojekte/unbekannte Werte auf abschnitt", () => {
    expect(normalizeZerlegungsart(undefined)).toBe("abschnitt");
    expect(normalizeZerlegungsart(null)).toBe("abschnitt");
    expect(normalizeZerlegungsart("egal")).toBe("abschnitt");
    expect(normalizeZerlegungsart("modul")).toBe("modul");
  });
});

describe("Workstation-Hinweis — freundlich, kein Gate (ADR-022)", () => {
  it("Art modul ohne Workstation → Hinweistext (Workstation ist der Druckort)", () => {
    const hint = workstationHint("modul", false);
    expect(hint).toContain("Workstation");
    expect(hint).toContain("Druckort");
  });

  it("mit Workstation oder bei Art abschnitt → kein Hinweis", () => {
    expect(workstationHint("modul", true)).toBeNull();
    expect(workstationHint("abschnitt", false)).toBeNull();
    expect(workstationHint("abschnitt", true)).toBeNull();
  });
});

describe("Artwechsel-Regeln (ADR-022 Punkt 5) — drei Regeln, alle getestet", () => {
  const cuts: Cut[] = [
    { orientation: "horizontal", position_mm: 1300 },
    { orientation: "vertical", position_mm: -200 },
  ];
  const placementOverrides: SectionOverride[] = [
    { section_id: "abschnitt-1", option_id: "stellplatz-1" }, // Referenz (#25)
    { section_id: "abschnitt-2", standoff_mm: 900 }, // freie Werte (#94)
  ];
  const slicingSections: Record<string, SectionProcessOverride> = {
    "abschnitt-1": { slice: { layer_height_mm: 8 } },
    "abschnitt-2": { orientation: { kipp_deg: 5 } },
  };

  it("Regel 1: ALLE Schnitte bleiben erhalten (zerlegungsart-neutral), Fugen-Versatz auch", () => {
    const result = switchArt({
      cuts,
      jointOffsetMm: 150,
      sectionOverrides: placementOverrides,
      slicingSections,
    });
    expect(result.cuts).toEqual(cuts);
    expect(result.cuts).not.toBe(cuts); // Kopie, kein geteilter Zustand
    expect(result.jointOffsetMm).toBe(150);
  });

  it("Regel 2: Slicing-Overrides (process_params.sections) überleben unverändert", () => {
    const result = switchArt({
      cuts,
      jointOffsetMm: 0,
      sectionOverrides: placementOverrides,
      slicingSections,
    });
    expect(result.slicingSections).toEqual(slicingSections);
  });

  it("Regel 3: Platzierungs-Overrides verfallen (Referenz UND freie Werte)", () => {
    const result = switchArt({
      cuts,
      jointOffsetMm: 0,
      sectionOverrides: placementOverrides,
      slicingSections,
    });
    expect(result.sectionOverrides).toEqual([]);
  });

  it("der Plan ist nach dem Wechsel ungeprüft (dirty) — Re-Check bewertet mit neuer Art", () => {
    const result = switchArt({ cuts, jointOffsetMm: 0, sectionOverrides: [] });
    expect(result.dirty).toBe(true);
  });

  it("deterministisch und rein: Eingaben bleiben unangetastet", () => {
    const before = JSON.stringify({ cuts, placementOverrides, slicingSections });
    switchArt({
      cuts,
      jointOffsetMm: 42,
      sectionOverrides: placementOverrides,
      slicingSections,
    });
    expect(JSON.stringify({ cuts, placementOverrides, slicingSections })).toBe(before);
  });
});
