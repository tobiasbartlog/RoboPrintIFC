import { describe, expect, it } from "vitest";

import type { SectionProcessOverride } from "../api/projects";
import { expectGoldenParity } from "../test/golden-parity";
import golden from "./section-params.golden.json";
import {
  type SectionOverrideForm,
  emptySectionOverrideForm,
  globalParamsFrom,
  resolveSectionParams,
  sectionOverrideForm,
  sectionOverrideFormHasValues,
  sectionOverrideRequestFromForm,
  sectionsRequestFromForms,
} from "./section-params-state";

// --- Py↔TS-Parität: geteilte Golden-Fälle (Core ist die Wahrheit) ---------------
describe("resolveSectionParams gegen geteilte Golden-Fälle (Issue #82)", () => {
  it("reproduziert jeden Core-Golden-Fall bit-gleich", () => {
    expectGoldenParity(golden.cases, (c) =>
      resolveSectionParams(
        c.global as SectionProcessOverride,
        c.override as SectionProcessOverride,
      ),
    );
  });
});

describe("resolveSectionParams Semantik (sparse merge)", () => {
  it("ungesetztes Feld erbt global, gesetztes übersteuert — Slice UND Orientierung", () => {
    const g: SectionProcessOverride = {
      slice: { layer_height_mm: 8, n_shells: 2 },
      orientation: { lead_deg: 10, kipp_deg: 5 },
    };
    const o: SectionProcessOverride = {
      slice: { n_shells: 4 },
      orientation: { kipp_deg: -3 },
    };
    expect(resolveSectionParams(g, o)).toEqual({
      slice: { layer_height_mm: 8, n_shells: 4 },
      orientation: { lead_deg: 10, kipp_deg: -3 },
    });
  });

  it("0 übersteuert (gesetzter Wert), leeres Ergebnis bleibt sparse", () => {
    expect(resolveSectionParams({ orientation: { kipp_deg: 5 } }, { orientation: { kipp_deg: 0 } })).toEqual(
      { orientation: { kipp_deg: 0 } },
    );
    expect(resolveSectionParams({}, {})).toEqual({});
  });
});

// --- Formular ↔ Job (Persistenz, Restore) --------------------------------------
describe("Abschnitts-Formular ↔ Override-Block", () => {
  it("fehlender Override → leeres Formular (rückwärtskompatibel)", () => {
    expect(sectionOverrideForm(undefined)).toEqual(emptySectionOverrideForm());
    expect(sectionOverrideFormHasValues(emptySectionOverrideForm())).toBe(false);
  });

  it("liest slice + orientation eines Abschnitts ins Formular", () => {
    const form = sectionOverrideForm({
      slice: { layer_height_mm: 6, io_travel: 0 },
      orientation: { kipp_deg: 12 },
    });
    expect(form.slice.layerHeightMm).toBe(6);
    expect(form.slice.ioTravel).toBe(0);
    expect(form.orientation.kippDeg).toBe(12);
    expect(sectionOverrideFormHasValues(form)).toBe(true);
  });

  it("baut nur gesetzte Felder in den Override-Request (leer → {})", () => {
    const form: SectionOverrideForm = {
      ...emptySectionOverrideForm(),
      slice: { ...emptySectionOverrideForm().slice, layerHeightMm: 7.5 },
      orientation: { leadDeg: null, kippDeg: 3 },
    };
    expect(sectionOverrideRequestFromForm(form)).toEqual({
      slice: { layer_height_mm: 7.5 },
      orientation: { kipp_deg: 3 },
    });
    expect(sectionOverrideRequestFromForm(emptySectionOverrideForm())).toEqual({});
  });

  it("round-trip: Override-Block → Formular → Request rekonstruiert ihn", () => {
    const override: SectionProcessOverride = {
      slice: { layer_height_mm: 6, n_shells: 4 },
      orientation: { kipp_deg: 20 },
    };
    expect(sectionOverrideRequestFromForm(sectionOverrideForm(override))).toEqual(override);
  });

  it("sectionsRequestFromForms bildet jede Abschnitts-ID ab (leer geräumt = {})", () => {
    const forms: Record<string, SectionOverrideForm> = {
      "abschnitt-1": sectionOverrideForm({ slice: { layer_height_mm: 6 } }),
      "abschnitt-2": emptySectionOverrideForm(),
    };
    expect(sectionsRequestFromForms(forms)).toEqual({
      "abschnitt-1": { slice: { layer_height_mm: 6 } },
      "abschnitt-2": {},
    });
  });
});

describe("globalParamsFrom + Auflösung (effektive Werte fürs Panel)", () => {
  it("mergt globale Blöcke, damit das Panel geerbt vs. übersteuert zeigen kann", () => {
    const global = globalParamsFrom({ layer_height_mm: 8, n_shells: 2 }, { kipp_deg: 5 });
    const effective = resolveSectionParams(global, { slice: { n_shells: 3 } });
    expect(effective).toEqual({ slice: { layer_height_mm: 8, n_shells: 3 }, orientation: { kipp_deg: 5 } });
  });

  it("leere globale Blöcke → leere Eingabe (Abschnitt erbt Karte)", () => {
    expect(globalParamsFrom(undefined, undefined)).toEqual({});
    expect(globalParamsFrom({}, {})).toEqual({});
  });
});
