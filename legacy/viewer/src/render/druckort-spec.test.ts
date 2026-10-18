/**
 * Druckort-Szenen-Spec (Issue #96, ADR-022): reine Umrechnung der Core-Lage
 * (`module_pose`) + Workstation-Stammdaten (ADR-021) in die Szenen-Beschreibung
 * — Roboter-Anker, Modul-Rechteck, Mesh-Quelle; fehlende Voraussetzungen
 * liefern einen freundlichen Hinweis statt einer kaputten Szene (kein Gate).
 * three.js-frei.
 */

import { describe, expect, it } from "vitest";

import {
  druckortSceneSpec,
  druckortSceneSpecForRun,
  frameToMat4,
  moduleBoxSpec,
  runModuleFrame,
  type DruckortSection,
  type DruckortWorkstation,
} from "./druckort-spec";
import type { Frame } from "../api/projects";
import type { Mat4 } from "../kinematics/fk";

const SECTION: DruckortSection = {
  section_id: "abschnitt-1",
  x0_mm: -400,
  x1_mm: 400,
  z0_mm: 0,
  z1_mm: 1200,
  module_pose: {
    workstation: { pos_mm: [0, -800, 0], quat: [1, 0, 0, 0] },
    on_surface: { pos_mm: [-800, -800, 0], quat: [1, 0, 0, 0] },
  },
};

const WS: DruckortWorkstation = {
  name: "druckort",
  mesh: "druckort.glb",
  mesh_path: "C:\\ws\\druckort.glb",
  robot_base_frame: { pos_mm: [0, 0, 300], quat: [1, 0, 0, 0] },
  work_surface_frame: { pos_mm: [800, 0, 0], quat: [1, 0, 0, 0] },
};

describe("frameToMat4 — Frame [w,x,y,z] → zeilenmajore 4×4 (ADR-006)", () => {
  it("Identität → Einheitsmatrix mit Translation", () => {
    const m = frameToMat4({ pos_mm: [10, 20, 30], quat: [1, 0, 0, 0] });
    expect(m).toEqual([1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1]);
  });

  it("90° um z (w-x-y-z-Konvention): x-Achse → y-Achse", () => {
    const s = Math.SQRT1_2;
    const m = frameToMat4({ pos_mm: [0, 0, 0], quat: [s, 0, 0, s] });
    // Spalte 0 (Bild der x-Achse) = (0, 1, 0).
    expect(m[0]).toBeCloseTo(0, 12);
    expect(m[4]).toBeCloseTo(1, 12);
    expect(m[8]).toBeCloseTo(0, 12);
    // Spalte 1 (Bild der y-Achse) = (−1, 0, 0).
    expect(m[1]).toBeCloseTo(-1, 12);
    expect(m[5]).toBeCloseTo(0, 12);
  });
});

describe("moduleBoxSpec — Modul-Rechteck im Modul-System der Core-Lage", () => {
  it("Maße [Länge, Dicke, Höhe] + Mittelpunkt (y zentriert wie der Toolpath, Fuß z=0)", () => {
    const box = moduleBoxSpec(SECTION, 200);
    expect(box.sizeMm).toEqual([800, 200, 1200]);
    // x zentriert; Wandkörper y-zentriert (y ∈ [−100, +100] — dieselbe
    // PCA-Konvention wie Toolpath/Trajektorie); Fuß bei z=0.
    expect(box.centerLocalMm).toEqual([0, 0, 600]);
  });

  it("robust gegen vertauschte Grenzen und Dicke 0", () => {
    const box = moduleBoxSpec(
      { x0_mm: 400, x1_mm: -400, z0_mm: 1200, z1_mm: 0 },
      0,
    );
    expect(box.sizeMm).toEqual([800, 0, 1200]);
    expect(box.centerLocalMm).toEqual([0, 0, 600]);
  });
});

/** Punkt durch eine zeilenmajore 4×4 schicken (Testhelfer). */
function applyMat(m: Mat4, p: [number, number, number]): [number, number, number] {
  return [
    m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3],
    m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7],
    m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11],
  ];
}

describe("runModuleFrame — Bühne folgt dem Sim-Lauf (Issue #161)", () => {
  it("Identitäts-Basis: Ergebnis = invert(base_in_wall)", () => {
    const f = runModuleFrame(
      { pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] },
      { pos_mm: [0, 800, 300], quat: [1, 0, 0, 0] },
    );
    expect(f.pos_mm).toEqual([0, -800, -300]);
    expect(f.quat).toEqual([1, 0, 0, 0]);
  });

  it("reproduziert bei konsistenten Frames die Zerlegungs-Lage (module_pose)", () => {
    // Basis in Workstation-Koordinaten bei [0,0,300] (= WS.robot_base_frame),
    // Basis im Modul-System bei [0,800,300] ⇒ Modul in WS-Koordinaten bei
    // [0,-800,0] — exakt SECTION.module_pose.workstation.
    const f = runModuleFrame(
      { pos_mm: [0, 0, 300], quat: [1, 0, 0, 0] },
      { pos_mm: [0, 800, 300], quat: [1, 0, 0, 0] },
    );
    expect(f.pos_mm).toEqual([0, -800, 0]);
    expect(f.quat).toEqual([1, 0, 0, 0]);
  });

  it("Algebra-Eigenschaft: (A ∘ B⁻¹)(B(p)) = A(p) — auch mit Drehungen", () => {
    const s = Math.SQRT1_2;
    // A: 90° um z + Translation; B: 90° um x + Translation (beliebig gewählt).
    const a: Frame = { pos_mm: [100, -50, 300], quat: [s, 0, 0, s] };
    const b: Frame = { pos_mm: [30, 800, -20], quat: [s, s, 0, 0] };
    const composed = frameToMat4(runModuleFrame(a, b));
    const p: [number, number, number] = [123, -45, 678];
    const viaB = applyMat(frameToMat4(b), p);
    const got = applyMat(composed, viaB);
    const want = applyMat(frameToMat4(a), p);
    for (let i = 0; i < 3; i++) expect(got[i]).toBeCloseTo(want[i], 9);
  });
});

describe("druckortSceneSpec — Szene oder freundlicher Hinweis (kein Gate)", () => {
  it("vollständige Voraussetzungen → Szene mit Roboter-Anker + Modul-Lage", () => {
    const res = druckortSceneSpec({ workstation: WS, section: SECTION, thicknessMm: 200 });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    // Roboter-Anker = robot_base_frame (Translation in der letzten Spalte).
    expect(res.spec.robotAnchor[3]).toBe(0);
    expect(res.spec.robotAnchor[7]).toBe(0);
    expect(res.spec.robotAnchor[11]).toBe(300);
    // Modul-Frame verbatim aus der Core-Lage (Workstation-Koordinaten).
    expect(res.spec.moduleFrame).toEqual(SECTION.module_pose!.workstation);
    expect(res.spec.moduleBox.sizeMm).toEqual([800, 200, 1200]);
    expect(res.spec.meshFile).toBe("druckort.glb");
    expect(res.spec.meshPath).toBe("C:\\ws\\druckort.glb");
  });

  it("ohne Workstation → Hinweis (Workstation ist der Druckort)", () => {
    const res = druckortSceneSpec({ workstation: null, section: SECTION, thicknessMm: 200 });
    expect(res.ok).toBe(false);
    if (res.ok) return;
    expect(res.hint).toMatch(/Workstation/);
  });

  it("Workstation ohne Frames → Hinweis auf den Bibliothek-Editor (ADR-021)", () => {
    const bare: DruckortWorkstation = { name: "alt", robot_base_frame: null };
    const res = druckortSceneSpec({ workstation: bare, section: SECTION, thicknessMm: 200 });
    expect(res.ok).toBe(false);
    if (res.ok) return;
    expect(res.hint).toMatch(/Frames|Arbeitsfläche/);
    expect(res.hint).toMatch(/alt/);
  });

  it("Teil ohne module_pose (Altlauf) → Hinweis auf Prüfen", () => {
    const { module_pose: _pose, ...rest } = SECTION;
    const res = druckortSceneSpec({
      workstation: WS,
      section: rest as DruckortSection,
      thicknessMm: 200,
    });
    expect(res.ok).toBe(false);
    if (res.ok) return;
    expect(res.hint).toMatch(/Prüfen/);
  });

  it("ohne Mesh bleibt die Szene möglich (Roboter + Modul, Mesh optional)", () => {
    const meshless: DruckortWorkstation = { ...WS, mesh: null, mesh_path: null };
    const res = druckortSceneSpec({
      workstation: meshless,
      section: SECTION,
      thicknessMm: 200,
    });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.spec.meshFile).toBeNull();
  });

  it("ohne fokussiertes Teil → Hinweis", () => {
    const res = druckortSceneSpec({ workstation: WS, section: null, thicknessMm: 200 });
    expect(res.ok).toBe(false);
  });
});

describe("druckortSceneSpec — Bühne folgt dem Sim-Lauf (runBaseFrame, Issue #161)", () => {
  it("mit runBaseFrame kommt der Modul-Frame aus dem Lauf, nicht aus module_pose", () => {
    // Lauf-Platzierung weicht seitlich um 100 mm von der Zerlegungs-Lage ab
    // (z. B. Placement-Hebel des Kollisions-Advisors angenommen + neu simuliert).
    const res = druckortSceneSpec({
      workstation: WS,
      section: SECTION,
      thicknessMm: 200,
      runBaseFrame: { pos_mm: [100, 800, 300], quat: [1, 0, 0, 0] },
    });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.spec.moduleFrame.pos_mm).toEqual([-100, -800, 0]);
    expect(res.spec.moduleFrame).not.toEqual(SECTION.module_pose!.workstation);
    // Der Roboter-Anker bleibt die Workstation-Basis (unverändert).
    expect(res.spec.robotAnchor[11]).toBe(300);
  });

  it("ohne runBaseFrame (Altlauf/kein Lauf) bleibt die Zerlegungs-Lage (Bestand)", () => {
    const res = druckortSceneSpec({
      workstation: WS,
      section: SECTION,
      thicknessMm: 200,
      runBaseFrame: null,
    });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.spec.moduleFrame).toEqual(SECTION.module_pose!.workstation);
  });

  it("runBaseFrame ersetzt eine fehlende module_pose (der Lauf trägt die Platzierung)", () => {
    const { module_pose: _pose, ...rest } = SECTION;
    const res = druckortSceneSpec({
      workstation: WS,
      section: rest as DruckortSection,
      thicknessMm: 200,
      runBaseFrame: { pos_mm: [0, 800, 300], quat: [1, 0, 0, 0] },
    });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.spec.moduleFrame.pos_mm).toEqual([0, -800, 0]);
  });
});

describe("druckortSceneSpecForRun — Verdrahtung Lauf → Bühne (Issue #161, Review-Nacharbeit)", () => {
  it("zieht trajectory.meta.base_frame SELBST aus dem Lauf — die Bühne folgt dem Sim-Lauf", () => {
    // Der Lauf trägt eine seitlich um 100 mm verschobene Platzierung (z. B.
    // Placement-Hebel angenommen + neu simuliert) — der Modul-Frame muss ihr
    // folgen, NICHT der Zerlegungs-Lage (module_pose). Genau die Regression
    // aus Issue #161: Soll-Kasten/Strang/TCP lagen neben dem Arm.
    const res = druckortSceneSpecForRun({
      workstation: WS,
      section: SECTION,
      thicknessMm: 200,
      run: { trajectory: { meta: { base_frame: { pos_mm: [100, 800, 300], quat: [1, 0, 0, 0] } } } },
    });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.spec.moduleFrame.pos_mm).toEqual([-100, -800, 0]);
    expect(res.spec.moduleFrame).not.toEqual(SECTION.module_pose!.workstation);
  });

  it("Altlauf ohne base_frame → Zerlegungs-Lage (module_pose verbatim, kein Gate)", () => {
    const res = druckortSceneSpecForRun({
      workstation: WS,
      section: SECTION,
      thicknessMm: 200,
      run: { trajectory: { meta: {} } },
    });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.spec.moduleFrame).toEqual(SECTION.module_pose!.workstation);
  });

  it("kein Lauf / Lauf ohne Trajektorie → Zerlegungs-Lage (kein Crash)", () => {
    for (const run of [null, { trajectory: null }]) {
      const res = druckortSceneSpecForRun({
        workstation: WS,
        section: SECTION,
        thicknessMm: 200,
        run,
      });
      expect(res.ok).toBe(true);
      if (!res.ok) return;
      expect(res.spec.moduleFrame).toEqual(SECTION.module_pose!.workstation);
    }
  });
});
