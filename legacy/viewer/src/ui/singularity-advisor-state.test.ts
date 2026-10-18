import { describe, expect, it } from "vitest";

import type { PrintJob, SingularityAdvice, SingularitySuggestion } from "../api/projects";
import { advisorView, applyActionFor, focusHint, marginText } from "./singularity-advisor-state";

function advice(suggestion: SingularitySuggestion | null): SingularityAdvice {
  return {
    slug: "s",
    job_id: "default",
    section_id: "abschnitt-1",
    type: suggestion?.type ?? null,
    near: true,
    measure: 0.001,
    advice: suggestion,
  };
}

const KIPP: SingularitySuggestion = {
  type: "wrist",
  lever: "kipp",
  margin_before: 0.0004,
  margin_after: 0.1228,
  improves: true,
  detail: "Handgelenks-Singularität (J5≈0): Düse um -40° kippen — Marge 0.000 → 0.123.",
  kipp_delta_deg: -40,
  placement: null,
  ik_config: null,
  write: null,
};

const PLACEMENT: SingularitySuggestion = {
  type: "elbow",
  lever: "placement",
  margin_before: 0.013,
  margin_after: 0.033,
  improves: true,
  detail: "Ellbogen gestreckt …",
  kipp_delta_deg: null,
  placement: { option_id: "vorschlag-1", lateral_mm: 0, standoff_mm: 700, stand_height_mm: 900 },
  ik_config: null,
  write: null,
};

// Config-Flip (#200): a/b-Block + write-Nutzlast in der Form des Kollisions-Advisors.
const CONFIG: SingularitySuggestion = {
  type: "shoulder",
  lever: "config_flip",
  margin_before: 0.002,
  margin_after: 0.05,
  improves: true,
  detail: "Schulter/konfig-abhängige Singularität: Schulter auf Zweig b fixieren — Marge 0.002 → 0.050 (bahn-weit).",
  kipp_delta_deg: null,
  placement: null,
  ik_config: { shoulder: "b" },
  write: { setter: "process-params", ik_config: { shoulder: "b" } },
};

describe("advisorView (Issue #65)", () => {
  it("kein Vorschlag → null", () => {
    expect(advisorView(advice(null))).toBeNull();
  });

  it("Kipp-Vorschlag → Handgelenk-Zeile mit aktivem Anwenden-Knopf", () => {
    const v = advisorView(advice(KIPP))!;
    expect(v.type).toBe("wrist");
    expect(v.lever).toBe("kipp");
    expect(v.typeLabel).toContain("Handgelenk");
    expect(v.marginBeforeText).toBe("0.000");
    expect(v.marginAfterText).toBe("0.123");
    expect(v.improves).toBe(true);
    expect(v.applyLabel).toBe("Kipp -40° anwenden");
    expect(v.applyEnabled).toBe(true);
  });

  it("Platzierungs-Vorschlag → Ellbogen-Zeile, Knopf aktiv", () => {
    const v = advisorView(advice(PLACEMENT))!;
    expect(v.type).toBe("elbow");
    expect(v.applyLabel).toBe("Platzierung übernehmen");
    expect(v.applyEnabled).toBe(true);
  });

  it("Config-Flip → Domänen-Text + aktiver Knopf (Schreibstelle #200)", () => {
    const v = advisorView(advice(CONFIG))!;
    expect(v.type).toBe("shoulder");
    // Domänenbegriff statt „Bitfeld flippen" — nennt Achse + Zweig.
    expect(v.applyLabel).toBe("Schulter auf Zweig b fixieren");
    expect(v.applyEnabled).toBe(true);
  });

  it("Config-Flip ohne Margengewinn → Knopf inaktiv (der Advisor beschönigt nicht)", () => {
    const v = advisorView(advice({ ...CONFIG, improves: false }))!;
    expect(v.applyEnabled).toBe(false);
  });

  it("Kipp-Delta 0 → Knopf inaktiv (keine Verbesserung)", () => {
    const v = advisorView(advice({ ...KIPP, kipp_delta_deg: 0 }))!;
    expect(v.applyEnabled).toBe(false);
  });
});

describe("applyActionFor (Anwenden-Verdrahtung, Issue #65/#134)", () => {
  it("Kipp addiert den Delta auf den aktuellen Kipp und bewahrt den Lead", () => {
    const job: PrintJob = {
      job_id: "default",
      wall_global_id: "W",
      process_params: { orientation: { lead_deg: 5, kipp_deg: 10 } },
    };
    const action = applyActionFor(KIPP, job);
    expect(action).toEqual({
      kind: "process-params",
      orientation: { kipp_deg: -30, lead_deg: 5 }, // 10 + (-40) = -30
    });
  });

  it("Kipp ohne bestehende Orientierung → Delta relativ zu 0, kein Lead", () => {
    const action = applyActionFor(KIPP, { job_id: "default", wall_global_id: "W" });
    expect(action).toEqual({ kind: "process-params", orientation: { kipp_deg: -40 } });
  });

  it("Platzierung wird zu freien Override-Werten des Fokus-Abschnitts (#94/#134)", () => {
    const action = applyActionFor(PLACEMENT, undefined, "abschnitt-2");
    expect(action).toEqual({
      kind: "placement-override",
      sectionId: "abschnitt-2",
      values: { lateral_mm: 0, standoff_mm: 700, stand_height_mm: 900 },
    });
  });

  it("Platzierung ohne Fokus-Abschnitt ist rein beratend (advisory)", () => {
    expect(applyActionFor(PLACEMENT, undefined, null)).toEqual({ kind: "advisory" });
  });

  it("Config-Flip → process-params-ik mit dem a/b-Block (#200, Route wie Kollisions-Advisor)", () => {
    expect(applyActionFor(CONFIG, undefined)).toEqual({
      kind: "process-params-ik",
      ikConfig: { shoulder: "b" },
    });
  });

  it("Config-Flip ohne write-Nutzlast ist rein beratend (advisory)", () => {
    expect(applyActionFor({ ...CONFIG, write: null }, undefined)).toEqual({ kind: "advisory" });
  });
});

describe("focusHint (Fokus-Verankerung, Issue #134)", () => {
  it("ohne Fokus: freundlicher Hinweis auf die Teile-Palette", () => {
    const hint = focusHint(null);
    expect(hint).toContain("Teile-Palette");
    expect(hint).toContain("Fokus-Abschnitt");
  });

  it("mit Fokus: kein Hinweis (null) — der Core-Aufruf läuft", () => {
    expect(focusHint("abschnitt-1")).toBeNull();
  });
});

describe("marginText", () => {
  it("formatiert Zahlen auf 3 Nachkommastellen, null → —", () => {
    expect(marginText(0.12345)).toBe("0.123");
    expect(marginText(null)).toBe("—");
  });
});
