import { describe, expect, it } from "vitest";

import type { FreigangFinding } from "../api/projects";
import { freigangBannerView, freigangNotice } from "./freigang-state";

function finding(over: Partial<FreigangFinding> = {}): FreigangFinding {
  return {
    wall_thickness_mm: 480,
    free_length_mm: 273.594,
    wrist_radius_mm: 60,
    printable_depth_mm: 333.594,
    too_thick: true,
    excess_mm: 146.406,
    levers: [
      "Tiefenteilung (in der Dicke schneiden, Slicing-Option #142)",
      "längerer Endeffektor (größere freie Länge unter dem Handgelenk)",
      "höhere Aufstellung / beidseitiger Druck",
    ],
    ...over,
  };
}

describe("freigangNotice", () => {
  it("stays silent when no finding (kein falsches „druckbar“)", () => {
    expect(freigangNotice(null)).toBeNull();
    expect(freigangNotice(undefined)).toBeNull();
  });

  it("stays silent when the wall is not too thick (Fehlerrichtung S6)", () => {
    // Ein nachweislich druckbarer Fall darf NIE eine Meldung erzeugen.
    const ok = finding({ too_thick: false, wall_thickness_mm: 200, excess_mm: 0, levers: [] });
    expect(freigangNotice(ok)).toBeNull();
  });

  it("reports „Wand zu dick“ with thickness, depth and excess", () => {
    const text = freigangNotice(finding())!;
    expect(text).toContain("Wand zu dick für einseitigen Druck");
    expect(text).toContain("480 mm");
    expect(text).toContain("334 mm"); // druckbare Tiefe gerundet
    expect(text).toContain("146 mm"); // Überschuss gerundet
    expect(text).toContain("Befund, kein Gate");
  });

  it("names the levers", () => {
    const text = freigangNotice(finding())!;
    expect(text).toContain("Tiefenteilung");
    expect(text).toContain("längerer Endeffektor");
    expect(text).toContain("höhere Aufstellung");
  });

  it("omits the lever clause when levers are empty", () => {
    const text = freigangNotice(finding({ levers: [] }))!;
    expect(text).not.toContain("Hebel:");
  });
});

describe("freigangBannerView", () => {
  it("hidden with empty text when nothing to report", () => {
    expect(freigangBannerView(null)).toEqual({ hidden: true, text: "" });
    expect(freigangBannerView(finding({ too_thick: false, levers: [] }))).toEqual({
      hidden: true,
      text: "",
    });
  });

  it("visible with the notice when too thick", () => {
    const view = freigangBannerView(finding());
    expect(view.hidden).toBe(false);
    expect(view.text).toContain("Wand zu dick");
  });
});
