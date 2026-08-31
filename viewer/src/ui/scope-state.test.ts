/**
 * Gilt-für-Umschalter Global↔Teil — reiner Zustand (Issue #92, PRD #88):
 * Geltungsbereich + Fokus-Abgleich, Ausgrau-Matrix, Vererbungsanzeige,
 * feldweise Override-Erzeugung (sparse, #82-Mechanik) und Ein-Feld-Reset ↺.
 * Plus der #83-Anker: ein Teil-Override veraltet nur dieses Teil, eine
 * globale Eingabe veraltet alle (granulare Veraltung bleibt unverändert).
 */

import { describe, expect, it } from "vitest";

import {
  type AsideGroup,
  effectiveScope,
  groupEnabled,
  overrideFieldView,
  readOverrideField,
  reconcileScopeChoice,
  resetOverrideField,
  selectScopeChoice,
  setOverrideField,
  STRUCTURAL_GROUPS,
  switchVisible,
} from "./scope-state";
import {
  emptySectionOverrideForm,
  sectionOverrideRequestFromForm,
} from "./section-params-state";
import { type Revisions, sectionStageStatus } from "./staleness";

describe("Scope-Stellung + Fokus-Abgleich (Issue #92; Fokus-Kopie entfällt mit #196)", () => {
  // Der Fokus lebt seit #196 allein im focus-store; die Stellungs-Logik
  // bekommt ihn als Parameter (gelesen aus dem Store).

  it("Ausgangszustand: Global, kein Teil, Umschalter unsichtbar", () => {
    expect(switchVisible(null)).toBe(false);
    expect(effectiveScope("global", null)).toBe("global");
  });

  it("Teil wählen macht den Umschalter sichtbar; Stellung bleibt Global", () => {
    expect(switchVisible("abschnitt-1")).toBe(true);
    expect(effectiveScope("global", "abschnitt-1")).toBe("global");
  });

  it("auf Teil stellen wirkt nur mit gewähltem Teil", () => {
    // Ohne Teil: bleibt Global (Umschalter wäre ohnehin unsichtbar).
    expect(selectScopeChoice("global", "teil", null)).toBe("global");
    // Mit Teil: Stellung wechselt, wirksamer Geltungsbereich = teil.
    const choice = selectScopeChoice("global", "teil", "a-1");
    expect(choice).toBe("teil");
    expect(effectiveScope(choice, "a-1")).toBe("teil");
  });

  it("Abwahl des Teils fällt sauber auf Global zurück (Umschalter weg)", () => {
    const choice = reconcileScopeChoice("teil", null);
    expect(choice).toBe("global");
    expect(switchVisible(null)).toBe(false);
    expect(effectiveScope(choice, null)).toBe("global");
  });

  it("Wechsel auf ein anderes Teil behält die Stellung (neues Ziel = der Store-Wert)", () => {
    const choice = reconcileScopeChoice("teil", "a-2");
    expect(choice).toBe("teil");
    expect(effectiveScope(choice, "a-2")).toBe("teil");
  });

  it("zurück auf Global zeigt wieder die globalen Werte (Teil bleibt gewählt)", () => {
    const choice = selectScopeChoice("teil", "global", "a-1");
    expect(effectiveScope(choice, "a-1")).toBe("global");
    expect(switchVisible("a-1")).toBe(true); // Umschalter bleibt (Teil weiter gewählt)
  });
});

describe("Ausgrau-Matrix (Issue #92): strukturell gesperrt, Slicing frei, Advisor global", () => {
  const ALL: AsideGroup[] = ["aufstellung", "zerlegung", "schnittplan", "slicing", "advisor"];

  it("Global: alle Gruppen bedienbar", () => {
    for (const g of ALL) expect(groupEnabled(g, "global")).toBe(true);
  });

  it("Teil: strukturelle Gruppen deaktiviert (ausgegraut, nicht ausgeblendet)", () => {
    for (const g of STRUCTURAL_GROUPS) expect(groupEnabled(g, "teil")).toBe(false);
    expect(STRUCTURAL_GROUPS).toEqual(["aufstellung", "zerlegung", "schnittplan"]);
  });

  it("Teil: Slicing voll übersteuerbar, Advisor bleibt (global) bedienbar", () => {
    expect(groupEnabled("slicing", "teil")).toBe(true);
    expect(groupEnabled("advisor", "teil")).toBe(true);
  });
});

describe("Vererbungsanzeige je Feld (Issue #92)", () => {
  it("geerbtes Feld: leer, globaler Wert dezent als Platzhalter", () => {
    expect(overrideFieldView(8, null)).toEqual({
      value: "",
      placeholder: "8 · erbt",
      overridden: false,
    });
  });

  it("übersteuertes Feld: Override-Wert im Feld, ↺ sichtbar (overridden)", () => {
    expect(overrideFieldView(8, 12.5)).toEqual({
      value: "12.5",
      placeholder: "8 · erbt",
      overridden: true,
    });
  });

  it("global ungesetzt: erbt Karte/Default", () => {
    expect(overrideFieldView(null, null).placeholder).toBe("Karten-Default · erbt");
  });
});

describe("feldweise Override-Erzeugung + Ein-Feld-Reset ↺ (Issue #92, #82-Mechanik)", () => {
  it("Eingabe erzeugt einen sparsamen feldweisen Override (nur gesetzte Felder)", () => {
    let form = emptySectionOverrideForm();
    form = setOverrideField(form, { group: "slice", field: "layerHeightMm" }, 12);
    form = setOverrideField(form, { group: "orientation", field: "kippDeg" }, -5);
    // Sparse Request über die BESTEHENDE #82-Umrechnung — keine Duplikation.
    expect(sectionOverrideRequestFromForm(form)).toEqual({
      slice: { layer_height_mm: 12 },
      orientation: { kipp_deg: -5 },
    });
  });

  it("↺ setzt genau ein Feld zurück; andere Overrides bleiben unberührt", () => {
    let form = emptySectionOverrideForm();
    form = setOverrideField(form, { group: "slice", field: "layerHeightMm" }, 12);
    form = setOverrideField(form, { group: "slice", field: "nShells" }, 3);
    form = resetOverrideField(form, { group: "slice", field: "layerHeightMm" });
    expect(readOverrideField(form, { group: "slice", field: "layerHeightMm" })).toBeNull();
    expect(readOverrideField(form, { group: "slice", field: "nShells" })).toBe(3);
    expect(sectionOverrideRequestFromForm(form)).toEqual({ slice: { n_shells: 3 } });
  });

  it("alle Felder zurückgesetzt → leere Gruppen fallen weg (erbt komplett)", () => {
    let form = emptySectionOverrideForm();
    form = setOverrideField(form, { group: "orientation", field: "leadDeg" }, 10);
    form = resetOverrideField(form, { group: "orientation", field: "leadDeg" });
    expect(sectionOverrideRequestFromForm(form)).toEqual({});
  });

  it("setOverrideField ist immutabel (das Eingabe-Formular bleibt unverändert)", () => {
    const before = emptySectionOverrideForm();
    setOverrideField(before, { group: "slice", field: "layerHeightMm" }, 12);
    expect(before.slice.layerHeightMm).toBeNull();
  });
});

describe("granulare Veraltung bleibt in Kraft (Issue #92 sichert #83)", () => {
  /** Schnappschuss beider Abschnitte auf dem Basis-Stand. */
  const SNAP = { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0 };
  function revisions(over: Partial<Revisions>): Revisions {
    return {
      inputs: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0 },
      outputs: {},
      section_inputs: {},
      section_outputs: {
        "a-1": { simulation: { ...SNAP }, export: { ...SNAP } },
        "a-2": { simulation: { ...SNAP }, export: { ...SNAP } },
      },
      ...over,
    };
  }

  it("Teil-Override (Umschalter auf Teil) veraltet NUR dieses Teil", () => {
    // Der Core bumpt beim Teil-Override nur section_inputs[teil] (#83) —
    // der Umschalter ändert daran nichts (dieselbe process-params-Route).
    const rev = revisions({ section_inputs: { "a-1": 1 } });
    expect(sectionStageStatus(rev, "a-1", "simulation")).toBe("stale");
    expect(sectionStageStatus(rev, "a-2", "simulation")).toBe("current");
  });

  it("globale Eingabe (Umschalter auf Global) veraltet wie bisher ALLE Teile", () => {
    const rev = revisions({
      inputs: { wall: 1, robot: 1, cutplan: 1, process: 1, workstation: 0 },
    });
    expect(sectionStageStatus(rev, "a-1", "simulation")).toBe("stale");
    expect(sectionStageStatus(rev, "a-2", "simulation")).toBe("stale");
  });
});
