/**
 * Reine Payload-/Formularlogik des Workstation-Editors (Issue #75). Kein DOM,
 * kein Netzwerk — nur die Umrechnung Formular↔Modell, die Branch-Regel-Prüfung
 * und die Karten-Zusammenfassung.
 */

import { describe, expect, it } from "vitest";

import type { WorkstationDef } from "../api/projects";
import {
  buildWorkstationRequest,
  mobilityLabel,
  podestStackSvg,
  summarizeWorkstation,
  workstationToForm,
  type WorkstationFormInput,
  type WorkstationPlacement,
} from "./workstation-payload";

function ws(overrides: Partial<WorkstationDef> = {}): WorkstationDef {
  return {
    name: "zelle_a",
    mobility: "stationary",
    height_adjustable: false,
    base_heights_mm: [0, 150, 300],
    height_range_mm: null,
    safety_min_distance_mm: 50,
    vendor: "",
    compatible_robots: [],
    ...overrides,
  };
}

function form(overrides: Partial<WorkstationFormInput> = {}): WorkstationFormInput {
  return {
    name: "zelle_a",
    mobility: "stationary",
    heightAdjustable: false,
    baseHeightsMm: [0, 150, 300],
    rangeMinMm: 0,
    rangeMaxMm: 0,
    safetyMinDistanceMm: 50,
    vendor: "",
    compatibleRobots: [],
    ...overrides,
  };
}

describe("mobilityLabel", () => {
  it("übersetzt mobility in deutsche Badges", () => {
    expect(mobilityLabel("stationary")).toBe("stationär");
    expect(mobilityLabel("mobile")).toBe("mobil");
  });
});

describe("summarizeWorkstation", () => {
  it("fasst eine stationäre Podest-Workstation zusammen (N Podeste + Bereich)", () => {
    const s = summarizeWorkstation(ws({ base_heights_mm: [0, 150, 300] }));
    expect(s.typeBadge).toBe("stationär");
    expect(s.heightText).toBe("3 Podeste · 0–300 mm");
    expect(s.safetyText).toBe("Sicherheitsabstand 50 mm");
    expect(s.podestHeights).toEqual([0, 150, 300]);
  });

  it("singularisiert Podest (Singular) bei genau einer Höhe", () => {
    expect(summarizeWorkstation(ws({ base_heights_mm: [0] })).heightText).toBe(
      "1 Podest · 0–0 mm",
    );
  });

  it("fasst eine verstellbare Workstation als min–max zusammen (keine Podeste)", () => {
    const s = summarizeWorkstation(
      ws({
        mobility: "mobile",
        height_adjustable: true,
        base_heights_mm: [],
        height_range_mm: { min: 200, max: 800 },
      }),
    );
    expect(s.typeBadge).toBe("mobil");
    expect(s.heightText).toBe("verstellbar · 200–800 mm");
    expect(s.podestHeights).toEqual([]);
  });
});

describe("podestStackSvg", () => {
  it("rendert je Podest ein Rechteck", () => {
    const svg = podestStackSvg([0, 150, 300]);
    expect(svg.startsWith("<svg")).toBe(true);
    expect(svg.match(/<rect /g)).toHaveLength(3);
  });

  it("rendert bei verstellbar (leere Liste) eine Rampe statt Rechtecke", () => {
    const svg = podestStackSvg([]);
    expect(svg).toContain("ws-podest-ramp");
    expect(svg.match(/<rect /g)).toBeNull();
  });
});

describe("buildWorkstationRequest — feste Podesthöhen", () => {
  it("baut den Request und entdoppelt Roboter-Tags", () => {
    const req = buildWorkstationRequest(
      form({ compatibleRobots: ["m1013", "m1013", " kr30 "] }),
    );
    expect(req.height_adjustable).toBe(false);
    expect(req.base_heights_mm).toEqual([0, 150, 300]);
    expect(req.height_range_mm).toBeNull();
    expect(req.compatible_robots).toEqual(["m1013", "kr30"]);
  });

  it("verlangt einen Namen", () => {
    expect(() => buildWorkstationRequest(form({ name: "   " }))).toThrow(/Name/);
  });

  it("verlangt streng aufsteigende Podesthöhen", () => {
    expect(() => buildWorkstationRequest(form({ baseHeightsMm: [0, 300, 150] }))).toThrow(
      /aufsteigend/,
    );
  });

  it("verlangt die 0 (Bodenhöhe) in den Podesthöhen", () => {
    expect(() => buildWorkstationRequest(form({ baseHeightsMm: [150, 300] }))).toThrow(
      /Bodenhöhe|0/,
    );
  });

  it("verlangt mindestens eine Podesthöhe", () => {
    expect(() => buildWorkstationRequest(form({ baseHeightsMm: [] }))).toThrow(/Podesthöhe/);
  });

  it("lehnt einen negativen Sicherheitsabstand ab", () => {
    expect(() => buildWorkstationRequest(form({ safetyMinDistanceMm: -5 }))).toThrow(
      /Sicherheitsabstand/,
    );
  });
});

describe("buildWorkstationRequest — verstellbarer Bereich", () => {
  it("baut den Request aus min/max und lässt base_heights leer", () => {
    const req = buildWorkstationRequest(
      form({ heightAdjustable: true, rangeMinMm: 200, rangeMaxMm: 800, baseHeightsMm: [] }),
    );
    expect(req.height_adjustable).toBe(true);
    expect(req.height_range_mm).toEqual({ min: 200, max: 800 });
    expect(req.base_heights_mm).toEqual([]);
  });

  it("verlangt min < max", () => {
    expect(() =>
      buildWorkstationRequest(form({ heightAdjustable: true, rangeMinMm: 800, rangeMaxMm: 200 })),
    ).toThrow(/min < max/);
  });
});

describe("workstationToForm — exakte Vorbefüllung (kein Rename)", () => {
  it("spiegelt eine feste Podest-Workstation ins Formular", () => {
    const f = workstationToForm(
      ws({ name: "zelle_a", base_heights_mm: [0, 150], compatible_robots: ["m1013"] }),
    );
    expect(f.name).toBe("zelle_a");
    expect(f.heightAdjustable).toBe(false);
    expect(f.baseHeightsMm).toEqual([0, 150]);
    expect(f.compatibleRobots).toEqual(["m1013"]);
  });

  it("spiegelt eine verstellbare Workstation (min/max) ins Formular", () => {
    const f = workstationToForm(
      ws({ height_adjustable: true, base_heights_mm: [], height_range_mm: { min: 100, max: 900 } }),
    );
    expect(f.heightAdjustable).toBe(true);
    expect(f.rangeMinMm).toBe(100);
    expect(f.rangeMaxMm).toBe(900);
  });

  it("round-trippt Formular → Request ohne Verlust", () => {
    const original = ws({ base_heights_mm: [0, 200, 400], safety_min_distance_mm: 75 });
    const req = buildWorkstationRequest(workstationToForm(original));
    expect(req.base_heights_mm).toEqual([0, 200, 400]);
    expect(req.safety_min_distance_mm).toBe(75);
  });
});

describe("buildWorkstationRequest — Platzierung (Mesh + Frames, Issue #78)", () => {
  it("ohne Platzierung bleibt der Request byte-gleich (keine Mesh-/Frame-Felder)", () => {
    const req = buildWorkstationRequest(form());
    expect("mesh_base64" in req).toBe(false);
    expect("mesh_filename" in req).toBe(false);
    expect("robot_base_frame" in req).toBe(false);
    expect("work_surface_frame" in req).toBe(false);
  });

  it("übernimmt Mesh (base64 + Dateiname) und beide Frames aus der Szene", () => {
    const placement: WorkstationPlacement = {
      meshBase64: "QUJD",
      meshFilename: "zelle.stl",
      robotBaseFrame: { pos_mm: [1, 2, 3], quat: [1, 0, 0, 0] },
      workSurfaceFrame: { pos_mm: [0, 0, 40], quat: [1, 0, 0, 0] },
    };
    const req = buildWorkstationRequest(form(), placement);
    expect(req.mesh_base64).toBe("QUJD");
    expect(req.mesh_filename).toBe("zelle.stl");
    expect(req.robot_base_frame).toEqual({ pos_mm: [1, 2, 3], quat: [1, 0, 0, 0] });
    expect(req.work_surface_frame).toEqual({ pos_mm: [0, 0, 40], quat: [1, 0, 0, 0] });
  });

  it("sendet ohne Neu-Upload keine Mesh-Felder, aber die aktuellen Frames (auch null)", () => {
    const req = buildWorkstationRequest(form(), {
      robotBaseFrame: null,
      workSurfaceFrame: { pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] },
    });
    expect("mesh_base64" in req).toBe(false);
    // null-Frame ist der Stand „gelöscht" (Request ist die Wahrheit).
    expect(req.robot_base_frame).toBeNull();
    expect(req.work_surface_frame).toEqual({ pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] });
  });

  it("ergänzt Mesh nur, wenn base64 UND Dateiname vorliegen", () => {
    const req = buildWorkstationRequest(form(), { meshBase64: "QUJD" }); // Dateiname fehlt
    expect("mesh_base64" in req).toBe(false);
    expect("mesh_filename" in req).toBe(false);
  });
});
