/**
 * Effektive-Platzierung-Selektor (Issue #171): reine-Funktions-Tests für beide
 * Faces (skalare Einbauort-Lage, Frame-Druckort-Lage) über alle Fälle — Lauf
 * da/fehlt, Override gesetzt/nicht, Modul-Lauf — plus ein **struktureller**
 * Einquelligkeits-Wächter (Import-Regel): jeder Platzierungs-Leser MUSS den
 * Selektor importieren und darf die skalaren Platzierungsfelder nicht mehr selbst
 * aus `*.placement.*` lesen. Fügt jemand einen neuen Direktleser hinzu, schlägt
 * dieser Test fehl (Wahl der Absicherung s. Design-Log 2026-07-10).
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import type { Frame, SectionOverride } from "../api/projects";
import {
  type PlacementScalars,
  effectiveModuleFrame,
  effectivePlacement,
} from "./effective-placement";

const BASE: PlacementScalars = {
  lateral_mm: 100,
  standoff_mm: 700,
  stand_height_mm: 0,
  yaw_rad: 0.5,
};

describe("effectivePlacement — skalarer Face (Einbauort)", () => {
  it("ohne Override die Zerlegungs-Platzierung verbatim (yaw defaultet auf 0)", () => {
    expect(effectivePlacement({ lateral_mm: 1, standoff_mm: 2, stand_height_mm: 3 })).toEqual({
      lateral_mm: 1,
      standoff_mm: 2,
      stand_height_mm: 3,
      yaw_rad: 0,
    });
    expect(effectivePlacement(BASE, undefined)).toEqual({ ...BASE });
  });

  it("übersteuert feldweise nur die gesetzten (endlichen) freien Felder", () => {
    const override: SectionOverride = { section_id: "a", standoff_mm: 900 };
    expect(effectivePlacement(BASE, override)).toEqual({
      lateral_mm: 100,
      standoff_mm: 900, // überschrieben
      stand_height_mm: 0,
      yaw_rad: 0.5, // yaw kommt weiter aus der Zerlegung
    });
  });

  it("mehrere freie Felder gleichzeitig, der Rest bleibt Zerlegung", () => {
    const override: SectionOverride = { section_id: "a", lateral_mm: 250, stand_height_mm: 400 };
    expect(effectivePlacement(BASE, override)).toEqual({
      lateral_mm: 250,
      standoff_mm: 700,
      stand_height_mm: 400,
      yaw_rad: 0.5,
    });
  });

  it("eine reine option_id-Referenz (ohne freie Werte) ändert nichts (ADR-007)", () => {
    expect(effectivePlacement(BASE, { section_id: "a", option_id: "west" })).toEqual({ ...BASE });
  });

  it("nicht-endliche Override-Werte übersteuern nie", () => {
    const override = {
      section_id: "a",
      standoff_mm: Number.NaN,
      stand_height_mm: Number.POSITIVE_INFINITY,
    } as unknown as SectionOverride;
    expect(effectivePlacement(BASE, override)).toEqual({ ...BASE });
  });
});

const RUN: Frame = { pos_mm: [100, 800, 300], quat: [1, 0, 0, 0] };
const DECOMP: Frame = { pos_mm: [0, 500, 0], quat: [1, 0, 0, 0] };

describe("effectiveModuleFrame — Frame-Face (Druckort)", () => {
  it("frischer Sim-Lauf gewinnt über die Zerlegungs-Lage (Lauf da)", () => {
    expect(effectiveModuleFrame({ runFrame: RUN, decompositionFrame: DECOMP })).toBe(RUN);
  });

  it("ohne Lauf (Lauf fehlt/Altlauf) gilt die Zerlegungs-Lage", () => {
    expect(effectiveModuleFrame({ runFrame: null, decompositionFrame: DECOMP })).toBe(DECOMP);
    expect(effectiveModuleFrame({ runFrame: undefined, decompositionFrame: DECOMP })).toBe(DECOMP);
  });

  it("weder Lauf noch Zerlegungs-Lage → null (Aufrufer zeigt Hinweis)", () => {
    expect(effectiveModuleFrame({ runFrame: null, decompositionFrame: null })).toBeNull();
    expect(effectiveModuleFrame({ runFrame: undefined, decompositionFrame: undefined })).toBeNull();
  });
});

/** Die reinen Platzierungs-Leser des Viewers (Issue #171): jeder MUSS den Selektor
 *  importieren; keiner darf die skalaren Felder selbst aus `.placement.*` lesen. */
const READERS = [
  "../ui/parts-palette-state.ts",
  "../render/placement-markers.ts",
  "../render/prepare-preview.ts",
  "../render/druckort-spec.ts",
];

describe("Einquelligkeit strukturell (Import-Regel, Issue #171)", () => {
  for (const rel of READERS) {
    const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");
    it(`${rel} bezieht die Platzierung aus dem Selektor`, () => {
      expect(src).toMatch(/from "\.\.?\/(?:ui\/)?effective-placement"/);
    });
    it(`${rel} liest keine skalaren Platzierungsfelder direkt aus .placement.*`, () => {
      // Verbietet Direktzugriffe wie `section.placement.standoff_mm` — sie müssen
      // durch effectivePlacement laufen (dort ist `placement.standoff_mm` erlaubt).
      const direct = src.match(/\.placement\.(?:lateral_mm|standoff_mm|stand_height_mm|yaw_rad)/g);
      expect(direct, `Direktleser in ${rel}: ${direct?.join(", ")}`).toBeNull();
    });
  }
});
