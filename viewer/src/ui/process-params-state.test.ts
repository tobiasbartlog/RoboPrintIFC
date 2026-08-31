import { describe, expect, it } from "vitest";

import type { PrintJob } from "../api/projects";
import {
  type OrientationForm,
  type SliceForm,
  emptyOrientationForm,
  emptySliceForm,
  orientationFormFromJob,
  orientationFormHasValues,
  orientationRequestFromForm,
  sliceFormFromJob,
  sliceFormHasValues,
  sliceRequestFromForm,
} from "./process-params-state";

function job(process_params?: PrintJob["process_params"]): PrintJob {
  return { job_id: "default", wall_global_id: "W", process_params };
}

describe("process-params serialization (Scheibe 2, Issue #59)", () => {
  it("Job ohne process_params → leeres Formular (rückwärtskompatibel)", () => {
    expect(sliceFormFromJob(job())).toEqual(emptySliceForm());
    expect(sliceFormFromJob(undefined)).toEqual(emptySliceForm());
  });

  it("liest den slice-Block ins Formular", () => {
    const form = sliceFormFromJob(
      job({ slice: { layer_height_mm: 8, strand_width_mm: 25, n_shells: 3 } }),
    );
    expect(form).toEqual({
      ...emptySliceForm(),
      layerHeightMm: 8,
      strandWidthMm: 25,
      nShells: 3,
    });
  });

  it("Teil-Block: ungesetzte Felder bleiben null", () => {
    const form = sliceFormFromJob(job({ slice: { layer_height_mm: 7.5 } }));
    expect(form).toEqual({ ...emptySliceForm(), layerHeightMm: 7.5 });
  });

  it("sliceRequestFromForm lässt leere Felder weg", () => {
    const form: SliceForm = { ...emptySliceForm(), layerHeightMm: 7.5, nShells: 4 };
    expect(sliceRequestFromForm(form)).toEqual({ layer_height_mm: 7.5, n_shells: 4 });
  });

  it("leeres Formular → leerer Request (Block wird entfernt)", () => {
    expect(sliceRequestFromForm(emptySliceForm())).toEqual({});
    expect(sliceFormHasValues(emptySliceForm())).toBe(false);
  });

  it("round-trip: Job → Formular → Request rekonstruiert den slice-Block", () => {
    const slice = { layer_height_mm: 9, strand_width_mm: 30, n_shells: 2 };
    const form = sliceFormFromJob(job({ slice }));
    expect(sliceRequestFromForm(form)).toEqual(slice);
    expect(sliceFormHasValues(form)).toBe(true);
  });
});

describe("Fortgeschritten: Geschwindigkeiten + io (Scheibe 2b, Issue #60)", () => {
  it("liest v_print/v_travel/io_print/io_travel ins Formular", () => {
    const form = sliceFormFromJob(
      job({
        slice: {
          v_print_mm_s: 120,
          v_travel_mm_s: 300,
          io_print: 0.7,
          io_travel: 0,
        },
      }),
    );
    expect(form).toEqual({
      ...emptySliceForm(),
      vPrintMmS: 120,
      vTravelMmS: 300,
      ioPrint: 0.7,
      ioTravel: 0,
    });
  });

  it("io_travel = 0 ist ein gesetzter Wert (nicht null)", () => {
    const form = sliceFormFromJob(job({ slice: { io_travel: 0 } }));
    expect(form.ioTravel).toBe(0);
    expect(sliceRequestFromForm(form)).toEqual({ io_travel: 0 });
    expect(sliceFormHasValues(form)).toBe(true);
  });

  it("sliceRequestFromForm übernimmt nur gesetzte Fortgeschritten-Felder", () => {
    const form: SliceForm = { ...emptySliceForm(), vPrintMmS: 90, ioPrint: 0.5 };
    expect(sliceRequestFromForm(form)).toEqual({ v_print_mm_s: 90, io_print: 0.5 });
  });

  it("round-trip: Basis + Fortgeschritten rekonstruieren den slice-Block", () => {
    const slice = {
      layer_height_mm: 9,
      n_shells: 2,
      v_print_mm_s: 110,
      v_travel_mm_s: 260,
      io_print: 0.6,
      io_travel: 0,
    };
    const form = sliceFormFromJob(job({ slice }));
    expect(sliceRequestFromForm(form)).toEqual(slice);
    expect(sliceFormHasValues(form)).toBe(true);
  });
});

describe("orientation serialization (Scheibe 3, Issue #61)", () => {
  it("Job ohne orientation → leeres Formular (0/0, rückwärtskompatibel)", () => {
    expect(orientationFormFromJob(job())).toEqual(emptyOrientationForm());
    expect(orientationFormFromJob(undefined)).toEqual(emptyOrientationForm());
  });

  it("liest den orientation-Block (Grad) ins Formular", () => {
    const form = orientationFormFromJob(job({ orientation: { lead_deg: 12, kipp_deg: -5 } }));
    expect(form).toEqual({ leadDeg: 12, kippDeg: -5 });
  });

  it("Teil-Block: ungesetztes Feld bleibt null", () => {
    const form = orientationFormFromJob(job({ orientation: { kipp_deg: 8 } }));
    expect(form).toEqual({ leadDeg: null, kippDeg: 8 });
  });

  it("orientationRequestFromForm lässt leere Felder weg", () => {
    const form: OrientationForm = { leadDeg: null, kippDeg: 15 };
    expect(orientationRequestFromForm(form)).toEqual({ kipp_deg: 15 });
  });

  it("leeres Formular → leerer Request (Block wird entfernt)", () => {
    expect(orientationRequestFromForm(emptyOrientationForm())).toEqual({});
    expect(orientationFormHasValues(emptyOrientationForm())).toBe(false);
  });

  it("round-trip: Job → Formular → Request rekonstruiert den orientation-Block", () => {
    const orientation = { lead_deg: 10, kipp_deg: 20 };
    const form = orientationFormFromJob(job({ orientation }));
    expect(orientationRequestFromForm(form)).toEqual(orientation);
    expect(orientationFormHasValues(form)).toBe(true);
  });

  it("0 ist ein gesetzter Wert (nicht null)", () => {
    const form = orientationFormFromJob(job({ orientation: { lead_deg: 0, kipp_deg: 0 } }));
    expect(form).toEqual({ leadDeg: 0, kippDeg: 0 });
    expect(orientationRequestFromForm(form)).toEqual({ lead_deg: 0, kipp_deg: 0 });
  });
});
