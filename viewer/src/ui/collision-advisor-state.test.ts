import { describe, expect, it } from "vitest";

import type { CollisionAdvice, CollisionOption } from "../api/projects";
import {
  collisionAdvisorView,
  collisionApplyActionFor,
  collisionCheckStatus,
  collisionEmptyListText,
  collisionScopeLabel,
  mmText,
} from "./collision-advisor-state";

const IK_OPTION: CollisionOption = {
  kind: "ik_config",
  label: "IK Handgelenk=b",
  detail: "IK Handgelenk=b: beseitigt Kollision — min. Abstand -10.0 → 5.0 mm, Marge -110.0 → -95.0 mm.",
  collision_free_before: false,
  collision_free_after: true,
  min_distance_before_mm: -10,
  min_distance_after_mm: 5,
  margin_before_mm: -110,
  margin_after_mm: -95,
  write: { setter: "process-params", ik_config: { wrist: "b" } },
};

const KIPP_OPTION: CollisionOption = {
  kind: "kipp_lead",
  label: "Kipp +20°",
  detail: "Kipp +20°: größerer Abstand — min. Abstand 10.0 → 40.0 mm, Marge -90.0 → -60.0 mm.",
  collision_free_before: false,
  collision_free_after: false,
  min_distance_before_mm: 10,
  min_distance_after_mm: 40,
  margin_before_mm: -90,
  margin_after_mm: -60,
  write: { setter: "process-params", orientation: { lead_deg: 0, kipp_deg: 20 } },
};

const PLACEMENT_OPTION: CollisionOption = {
  kind: "placement",
  label: "Abstand 700 mm",
  detail: "Abstand 700 mm: größerer Abstand — min. Abstand 10.0 → 30.0 mm, Marge -90.0 → -70.0 mm.",
  collision_free_before: false,
  collision_free_after: false,
  min_distance_before_mm: 10,
  min_distance_after_mm: 30,
  margin_before_mm: -90,
  margin_after_mm: -70,
  write: {
    setter: "placement-override",
    section_id: "abschnitt-1",
    standoff_mm: 700,
    merge: true,
  },
};

function advice(options: CollisionOption[], baseline: CollisionAdvice["baseline"] = null): CollisionAdvice {
  return {
    slug: "s",
    job_id: "default",
    section_id: "abschnitt-1",
    baseline:
      baseline ??
      { min_distance_mm: -10, margin_mm: -110, collision_free: false, n_red: 4 },
    options,
  };
}

describe("collisionAdvisorView (Issue #130)", () => {
  it("kein Befund (baseline=null) → null", () => {
    const a: CollisionAdvice = { slug: "s", job_id: "default", section_id: null, baseline: null, options: [] };
    expect(collisionAdvisorView(a)).toBeNull();
  });

  it("Basiszeile nennt min. Abstand + Kollisionsstatus", () => {
    const v = collisionAdvisorView(advice([]))!;
    expect(v.baselineText).toContain("min. Abstand -10.0 mm");
    expect(v.baselineText).toContain("4 Kollisions-Samples");
    expect(v.options).toHaveLength(0);
  });

  it("Optionsliste: je Hebel eine Zeile mit Vorher/Nachher + Anwenden-Label", () => {
    const v = collisionAdvisorView(advice([IK_OPTION, KIPP_OPTION, PLACEMENT_OPTION]))!;
    expect(v.options).toHaveLength(3);

    const ik = v.options[0];
    expect(ik.kind).toBe("ik_config");
    expect(ik.leverLabel).toBe("IK-Konfiguration");
    expect(ik.collisionFreeAfter).toBe(true);
    expect(ik.removesCollision).toBe(true); // vorher kollidiert, nachher frei
    expect(ik.minDistanceBeforeText).toBe("-10.0");
    expect(ik.minDistanceAfterText).toBe("5.0");
    expect(ik.applyLabel).toBe("IK Handgelenk=b anwenden");

    expect(v.options[1].leverLabel).toBe("Kipp/Lead");
    expect(v.options[1].removesCollision).toBe(false); // nur Abstandsgewinn
    expect(v.options[2].leverLabel).toBe("Platzierung");
  });
});

describe("collisionApplyActionFor (Anwenden über bestehende Setter, Issue #130)", () => {
  it("IK-Hebel → process-params-ik mit dem Tri-State-Block", () => {
    expect(collisionApplyActionFor(IK_OPTION)).toEqual({
      kind: "process-params-ik",
      ikConfig: { wrist: "b" },
    });
  });

  it("Kipp/Lead-Hebel → process-params-orientation mit Grad-Block", () => {
    expect(collisionApplyActionFor(KIPP_OPTION)).toEqual({
      kind: "process-params-orientation",
      orientation: { lead_deg: 0, kipp_deg: 20 },
    });
  });

  it("Platzierungs-Hebel → placement-override mit section_id + freien Werten (merge, #173)", () => {
    // Einzelfeld-Option: merge bewahrt beim Anwenden bestehende freie Felder,
    // damit der angewandte Zustand dem bewerteten Kandidaten entspricht (B18).
    expect(collisionApplyActionFor(PLACEMENT_OPTION)).toEqual({
      kind: "placement-override",
      sectionId: "abschnitt-1",
      values: { standoff_mm: 700, merge: true },
    });
  });

  it("Platzierungs-Option ohne merge-Flag (Altdaten) → kein merge im values", () => {
    const legacy: CollisionOption = {
      ...PLACEMENT_OPTION,
      write: { setter: "placement-override", section_id: "abschnitt-1", stand_height_mm: 200 },
    };
    expect(collisionApplyActionFor(legacy)).toEqual({
      kind: "placement-override",
      sectionId: "abschnitt-1",
      values: { stand_height_mm: 200 },
    });
  });
});

describe("Prüf-UX: Scope-Beschriftung + zweigeteilte Prüfung (#139/#145)", () => {
  it("Scope nennt das Fokus-Teil (Anzeigename vor roher section_id)", () => {
    expect(collisionScopeLabel("abschnitt-1", "#1 abschnitt-1")).toBe("#1 abschnitt-1");
    expect(collisionScopeLabel("abschnitt-1", null)).toBe("abschnitt-1");
  });

  it("ohne Fokus sagt der Scope ehrlich, dass das erste Teil geprüft wird", () => {
    expect(collisionScopeLabel(null, null)).toBe("erstes Teil (kein Fokus)");
  });

  it("Statuszeile nennt Teil + Kosten je Modus (Befund ≈ 20 s, Menü Minuten)", () => {
    const befund = collisionCheckStatus("befund", "#1 abschnitt-1");
    expect(befund).toContain("#1 abschnitt-1");
    expect(befund).toContain("eine Neu-Simulation");
    const menu = collisionCheckStatus("optionen", "#1 abschnitt-1");
    expect(menu).toContain("#1 abschnitt-1");
    expect(menu).toContain("mehrere Minuten");
  });

  it("leere Optionsliste: nach dem Befund nicht-gesucht, nach dem Menü kein-Hebel", () => {
    expect(collisionEmptyListText("befund")).toContain("nicht gesucht");
    expect(collisionEmptyListText("optionen")).toContain("Kein Hebel");
  });
});

describe("mmText", () => {
  it("formatiert Abstände auf 1 Nachkommastelle, null → ∞", () => {
    expect(mmText(12.34)).toBe("12.3");
    expect(mmText(null)).toBe("∞");
  });
});
