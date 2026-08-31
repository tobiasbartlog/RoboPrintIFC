/**
 * Freie Platzierungs-Overrides je Teil — reiner Zustand (Issue #94, PRD #88):
 * Umrechnung Formular ↔ `section_overrides`-Eintrag (sparse, Rundreise) und die
 * Vererbungsanzeige nach dem S3-Muster (geerbt dezent, Eingabe = Override,
 * ↺ zurück auf Automatik). Der Viewer urteilt nie (ADR-007) — die automatischen
 * Platzhalter-Werte kommen verbatim aus dem Core-Artefakt.
 */

import { describe, expect, it } from "vitest";

import type { SectionOverride } from "../api/projects";
import {
  emptyPlacementOverrideForm,
  placementFieldView,
  placementOverrideForm,
  placementOverrideHasValues,
  placementOverrideRequest,
} from "./placement-override-state";

describe("placementOverrideForm — Eintrag → Formular (Wiederherstellung)", () => {
  it("liest gesetzte freie Felder; fehlende bleiben null (erben)", () => {
    const entry: SectionOverride = { section_id: "abschnitt-1", standoff_mm: 900 };
    expect(placementOverrideForm(entry)).toEqual({
      lateral_mm: null,
      standoff_mm: 900,
      stand_height_mm: null,
    });
  });

  it("fehlender Eintrag oder reine option_id-Referenz (#25) ergibt ein leeres Formular", () => {
    expect(placementOverrideForm(undefined)).toEqual(emptyPlacementOverrideForm());
    expect(
      placementOverrideForm({ section_id: "abschnitt-1", option_id: "stellplatz-1" }),
    ).toEqual(emptyPlacementOverrideForm());
  });

  it("nicht-endliche Werte übersteuern nie", () => {
    const entry = { section_id: "a", lateral_mm: Number.NaN } as SectionOverride;
    expect(placementOverrideForm(entry).lateral_mm).toBeNull();
  });
});

describe("placementOverrideRequest — Formular → sparse API-Werte", () => {
  it("nur gesetzte Felder gehen mit; leeres Formular = Override entfernen", () => {
    const form = { lateral_mm: 120, standoff_mm: null, stand_height_mm: 0 };
    expect(placementOverrideRequest(form)).toEqual({ lateral_mm: 120, stand_height_mm: 0 });
    expect(placementOverrideRequest(emptyPlacementOverrideForm())).toEqual({});
  });

  it("Rundreise: Eintrag → Formular → Request ergibt dieselben freien Felder", () => {
    const entry: SectionOverride = {
      section_id: "abschnitt-2",
      option_id: "stellplatz-1",
      lateral_mm: -50,
      standoff_mm: 850,
    };
    expect(placementOverrideRequest(placementOverrideForm(entry))).toEqual({
      lateral_mm: -50,
      standoff_mm: 850,
    });
  });

  it("placementOverrideHasValues erkennt Overrides (▪-Marker-Zwilling)", () => {
    expect(placementOverrideHasValues(emptyPlacementOverrideForm())).toBe(false);
    expect(
      placementOverrideHasValues({ lateral_mm: null, standoff_mm: 900, stand_height_mm: null }),
    ).toBe(true);
  });
});

describe("placementFieldView — geerbt dezent / Eingabe = Override / ↺ (S3-Muster)", () => {
  it("ohne Override: leeres Feld, automatischer Wert dezent als Platzhalter", () => {
    expect(placementFieldView(712.4, null)).toEqual({
      value: "",
      placeholder: "712 · Auto",
      overridden: false,
    });
  });

  it("mit Override: Wert im Feld, overridden steuert Hervorhebung + ↺", () => {
    expect(placementFieldView(700, 900)).toEqual({
      value: "900",
      placeholder: "700 · Auto",
      overridden: true,
    });
  });

  it("ohne bewertete Zerlegung (kein Artefakt) bleibt der Platzhalter generisch", () => {
    expect(placementFieldView(null, null).placeholder).toBe("Auto");
  });
});
