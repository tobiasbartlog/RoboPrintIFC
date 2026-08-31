/**
 * Teile-Palette am 3D-Feld — reiner Zustand (Issue #91, PRD #88): Ableitung der
 * Einträge (Ampel/erreichbar/Auswahl), ▪-Marker aus `process_params.sections`
 * (#82) und die Auswahl↔Fokus-Synchronität (reuse `focus-store.ts`, #84/#196).
 */

import { describe, expect, it } from "vitest";

import type {
  DecompositionSection,
  SectionOverride,
  SectionProcessOverride,
} from "../api/projects";
import { FocusStore } from "./focus-store";
import {
  type PartsPaletteInput,
  paletteEntries,
  placementDisplayValues,
  placementOverrideSectionIds,
  slicingOverrideSectionIds,
} from "./parts-palette-state";

/** Baut einen Abschnitt mit dem für die Palette relevanten Befund. */
function section(
  id: string,
  order: number,
  reachable: boolean,
  fraction: number,
): DecompositionSection {
  return {
    section_id: id,
    order,
    x0_mm: 0,
    x1_mm: 1000,
    z0_mm: 0,
    z1_mm: 500,
    placement: { option_id: "auto", lateral_mm: 0, standoff_mm: 700, stand_height_mm: 0 },
    status: {
      reachable,
      reachable_fraction: fraction,
      n_samples: 100,
      n_reachable: Math.round(fraction * 100),
      kinematic_margin: reachable ? 0.5 : 0,
      mean_margin: reachable ? 0.5 : 0,
      warnings: [],
    },
  };
}

function input(over: Partial<PartsPaletteInput> = {}): PartsPaletteInput {
  return {
    sections: [section("b", 2, false, 0.4), section("a", 1, true, 1)],
    dirty: false,
    focusedSectionId: null,
    overrideSectionIds: [],
    ...over,
  };
}

describe("paletteEntries — Einträge in Druckreihenfolge", () => {
  it("sortiert nach order und leitet erreichbar + Name ab; ohne Urteil Ampel ungeprüft", () => {
    // Ohne Druckbarkeits-Urteil ist die Ampel „ungeprüft" (Issue #170) — NICHT mehr
    // grün/rot aus der Erreichbarkeit (die bleibt als reachable_fraction sichtbar).
    const entries = paletteEntries(input());
    expect(entries.map((e) => e.section_id)).toEqual(["a", "b"]);
    expect(entries[0]).toMatchObject({
      order: 1,
      name: "Abschnitt 1",
      ampel: "ungeprueft",
      reachable_fraction: 1,
    });
    expect(entries[1]).toMatchObject({
      order: 2,
      name: "Abschnitt 2",
      ampel: "ungeprueft",
      reachable_fraction: 0.4,
    });
  });

  it("schaltet die Teil-Namen mit der Zerlegungsart (Abschnitt/Modul, #95)", () => {
    expect(paletteEntries(input({ kind: "modul" }))[0].name).toBe("Modul 1");
    expect(paletteEntries(input({ kind: "abschnitt" }))[0].name).toBe("Abschnitt 1");
    // Default (Altaufrufer ohne kind) bleibt „Abschnitt".
    expect(paletteEntries(input())[0].name).toBe("Abschnitt 1");
  });

  it("markiert bei dirty jede Ampel als ungeprüft (Schnittplan geändert)", () => {
    const entries = paletteEntries(input({ dirty: true }));
    expect(entries.every((e) => e.ampel === "ungeprueft")).toBe(true);
  });

  it("reicht Platzierungswerte + Marge verbatim aus dem Core-Artefakt durch (#93)", () => {
    // Teil-Detail: keine Viewer-Ableitung — nur Werte aus placement/status (ADR-007).
    const entries = paletteEntries(input());
    const a = entries.find((e) => e.section_id === "a");
    expect(a).toMatchObject({
      lateral_mm: 0,
      standoff_mm: 700,
      stand_height_mm: 0,
      kinematic_margin: 0.5,
    });
    const b = entries.find((e) => e.section_id === "b");
    expect(b?.kinematic_margin).toBe(0); // rote Ampel → Marge aus dem Artefakt
  });
});

describe("placementDisplayValues — ehrliche Karten-Zeile (Issue #161)", () => {
  const base = { lateral_mm: 0, standoff_mm: 700, stand_height_mm: 0 };

  it("ohne Override bleiben die Zerlegungs-Werte verbatim", () => {
    expect(placementDisplayValues(base, undefined)).toEqual(base);
  });

  it("gesetzte Felder ersetzen sparse — ungesetzte erben die Zerlegungs-Werte", () => {
    const shown = placementDisplayValues(base, { section_id: "a", standoff_mm: 900 });
    expect(shown).toEqual({ lateral_mm: 0, standoff_mm: 900, stand_height_mm: 0 });
  });

  it("reine option_id-Referenz (#25) ohne freie Werte ändert nichts", () => {
    expect(placementDisplayValues(base, { section_id: "a", option_id: "west" })).toEqual(base);
  });

  it("nicht-endliche Werte übersteuern nie", () => {
    const shown = placementDisplayValues(base, {
      section_id: "a",
      lateral_mm: Number.NaN,
      stand_height_mm: 450,
    });
    expect(shown).toEqual({ lateral_mm: 0, standoff_mm: 700, stand_height_mm: 450 });
  });

  it("paletteEntries: nur das übersteuerte Teil zeigt Override-Werte, Nachbarn verbatim", () => {
    const entries = paletteEntries(
      input({
        placementOverrides: [{ section_id: "a", standoff_mm: 950, lateral_mm: -120 }],
      }),
    );
    const a = entries.find((e) => e.section_id === "a");
    expect(a).toMatchObject({ lateral_mm: -120, standoff_mm: 950, stand_height_mm: 0 });
    const b = entries.find((e) => e.section_id === "b");
    expect(b).toMatchObject({ lateral_mm: 0, standoff_mm: 700, stand_height_mm: 0 });
  });

  it("paletteEntries ohne placementOverrides (Altaufrufer) — Werte verbatim (Bestand)", () => {
    const a = paletteEntries(input()).find((e) => e.section_id === "a");
    expect(a).toMatchObject({ lateral_mm: 0, standoff_mm: 700, stand_height_mm: 0 });
  });
});

describe("Marker-Ableitung — nur Teile mit tatsächlichem Slicing-Override", () => {
  it("kennzeichnet genau die Teile aus overrideSectionIds", () => {
    const entries = paletteEntries(input({ overrideSectionIds: ["a"] }));
    expect(entries.find((e) => e.section_id === "a")?.has_override).toBe(true);
    expect(entries.find((e) => e.section_id === "b")?.has_override).toBe(false);
  });

  it("slicingOverrideSectionIds: gesetzte slice/orientation zählen, leere nicht", () => {
    const sections: Record<string, SectionProcessOverride> = {
      a: { slice: { layer_height_mm: 8 } },
      b: { orientation: { kipp_deg: 5 } },
      c: {}, // leer → kein Marker
      d: { slice: {} }, // leere Gruppe → kein Marker
    };
    expect(slicingOverrideSectionIds(sections)).toEqual(["a", "b"]);
  });

  it("verschwindet, sobald der Override entfernt ist (leerer/kein Block)", () => {
    expect(slicingOverrideSectionIds({ a: {} })).toEqual([]);
    expect(slicingOverrideSectionIds(undefined)).toEqual([]);
  });
});

describe("placementOverrideSectionIds — Platzierungs-Overrides zählen mit (#94)", () => {
  it("zählt freie Werte UND option_id-Referenzen als Platzierungs-Override", () => {
    const overrides: SectionOverride[] = [
      { section_id: "a", standoff_mm: 900 }, // freier Wert (#94)
      { section_id: "b", option_id: "stellplatz-1" }, // Referenz (#25)
      { section_id: "c" }, // leer → kein Marker
    ];
    expect(placementOverrideSectionIds(overrides)).toEqual(["a", "b"]);
  });

  it("ignoriert nicht-endliche Werte und dedupliziert/sortiert", () => {
    const overrides: SectionOverride[] = [
      { section_id: "z", lateral_mm: Number.NaN },
      { section_id: "a", lateral_mm: 10, stand_height_mm: 250 },
      { section_id: "a", standoff_mm: 700 },
    ];
    expect(placementOverrideSectionIds(overrides)).toEqual(["a"]);
    expect(placementOverrideSectionIds(undefined)).toEqual([]);
    expect(placementOverrideSectionIds([])).toEqual([]);
  });

  it("Union mit Slicing-Overrides speist den ▪-Marker (has_override)", () => {
    // main.ts bildet die Union — hier der Palettenpfad: ein Teil mit NUR
    // Platzierungs-Override trägt den Marker genauso wie ein Slicing-Override.
    const ids = new Set([
      ...slicingOverrideSectionIds({ b: { slice: { layer_height_mm: 8 } } }),
      ...placementOverrideSectionIds([{ section_id: "a", standoff_mm: 900 }]),
    ]);
    const entries = paletteEntries(input({ overrideSectionIds: [...ids].sort() }));
    expect(entries.find((e) => e.section_id === "a")?.has_override).toBe(true);
    expect(entries.find((e) => e.section_id === "b")?.has_override).toBe(true);
  });
});

describe("Auswahl ↔ Fokus — beidseitig synchron über focus-store (#84/#196)", () => {
  it("markiert genau das fokussierte Teil als gewählt", () => {
    const entries = paletteEntries(input({ focusedSectionId: "b" }));
    expect(entries.find((e) => e.section_id === "b")?.selected).toBe(true);
    expect(entries.find((e) => e.section_id === "a")?.selected).toBe(false);
  });

  it("ein Palette-Klick togglet denselben Fokus wie der 3D-Klick", () => {
    // Auswahl läuft durch store.toggle (kein paralleler Zustand): wählen → lösen.
    const focus = new FocusStore();
    focus.toggle("a");
    expect(paletteEntries(input({ focusedSectionId: focus.get() }))
      .find((e) => e.section_id === "a")?.selected).toBe(true);
    focus.toggle("a"); // erneuter Klick löst
    expect(focus.get()).toBeNull();
    expect(
      paletteEntries(input({ focusedSectionId: focus.get() })).every((e) => !e.selected),
    ).toBe(true);
  });

  it("räumt die Auswahl, wenn der Fokus-Abschnitt wegfällt (leere/neue Zerlegung)", () => {
    // store.reconcile wird in focus-store getestet; hier: ohne Fokus ist nichts gewählt.
    const entries = paletteEntries(input({ sections: [], focusedSectionId: "weg" }));
    expect(entries).toEqual([]);
  });
});

describe("paletteEntries — Druckbarkeit steuert die Ampel (Issue #164)", () => {
  /** Ein erreichbares Teil mit gesetztem Druckbarkeits-Urteil. */
  function withPrintability(
    verdict: "printable" | "collides" | "too_thick",
    presumed = false,
  ): DecompositionSection {
    const s = section("m", 1, true, 1); // erreichbar (grün nach altem Pfad)
    return {
      ...s,
      printability: {
        verdict,
        presumed,
        causer_link: verdict === "collides" ? 2 : null,
        penetration_mm: verdict === "collides" ? 289 : null,
        excess_mm: verdict === "too_thick" ? 176 : null,
      },
    };
  }

  it("kollidiert-Urteil färbt die Ampel ROT, obwohl das Teil erreichbar ist", () => {
    // Genau der Denkmal-Fall: erreichbar (status.reachable=true), aber kollidiert.
    const entries = paletteEntries(input({ sections: [withPrintability("collides")] }));
    expect(entries[0].ampel).toBe("red");
    expect(entries[0].printability?.severity).toBe("bad");
  });

  it("too_thick färbt rot (das lügende erreichbar-Häkchen fällt)", () => {
    const entries = paletteEntries(input({ sections: [withPrintability("too_thick")] }));
    expect(entries[0].ampel).toBe("red");
    expect(entries[0].printability?.label).toBe("zu dick · 176 mm");
  });

  it("grün NUR aus der Prüf-Tür: printable ⇒ grün", () => {
    const entries = paletteEntries(input({ sections: [withPrintability("printable")] }));
    expect(entries[0].ampel).toBe("green");
    expect(entries[0].printability?.presumed).toBe(false);
  });

  it("geerbtes Reihen-Urteil ist als ,vermutlich' erkennbar", () => {
    const entries = paletteEntries(input({ sections: [withPrintability("collides", true)] }));
    expect(entries[0].printability?.presumed).toBe(true);
    expect(entries[0].printability?.label).toContain("vermutlich");
  });

  it("ohne Druckbarkeits-Urteil (Altlauf) ⇒ Ampel ‚ungeprüft‘, NICHT Erreichbarkeit (Issue #170, B35)", () => {
    // Der Kern von B35: ein Altlauf ohne Urteil darf nicht mehr die alte
    // Erreichbarkeits-Ampel zeigen — beide Teile sind „ungeprüft", unabhängig davon,
    // ob sie erreichbar (a) oder nicht (b) sind. Kein Crash (Befund, kein Gate).
    const entries = paletteEntries(input());
    expect(entries.find((e) => e.section_id === "a")?.ampel).toBe("ungeprueft");
    expect(entries.find((e) => e.section_id === "a")?.printability).toBeNull();
    expect(entries.find((e) => e.section_id === "b")?.ampel).toBe("ungeprueft");
  });

  it("‚ungeprüft‘-Urteil (unknown) ist als eigener Zustand sichtbar (nicht grün/rot)", () => {
    const s = section("m", 1, true, 1); // erreichbar — früher fälschlich grün
    const withUnknown: DecompositionSection = {
      ...s,
      printability: { verdict: "unknown", presumed: false, reason: "error" },
    };
    const entries = paletteEntries(input({ sections: [withUnknown] }));
    expect(entries[0].ampel).toBe("ungeprueft");
    expect(entries[0].printability?.severity).toBe("unknown");
    expect(entries[0].printability?.label).toBe("ungeprüft");
  });

  it("dirty schlägt jedes Urteil: Ampel ungeprüft, keine Druckbarkeit gezeigt", () => {
    const entries = paletteEntries(
      input({ sections: [withPrintability("collides")], dirty: true }),
    );
    expect(entries[0].ampel).toBe("ungeprueft");
    expect(entries[0].printability).toBeNull();
  });
});

describe("paletteEntries — Kollisions-Badge je Teil (US 12, Issue #128)", () => {
  it("kein Befund ⇒ collision_badge null (Status quo, Altlauf)", () => {
    const entries = paletteEntries(input());
    expect(entries.every((e) => e.collision_badge === null)).toBe(true);
  });

  it("setzt das Badge verbatim aus meta.collision des Teil-Laufs", () => {
    const entries = paletteEntries(
      input({
        collisionBySectionId: {
          a: {
            config: { safety_distance_mm: 50, freizone_radius_mm: 30, provisional: false },
            min_distance_mm: -3,
            n_red: 2,
            n_yellow: 0,
            n_green: 8,
            distances_mm: [],
            intervals: [],
          },
        },
      }),
    );
    const a = entries.find((e) => e.section_id === "a")!;
    const b = entries.find((e) => e.section_id === "b")!;
    expect(a.collision_badge).toMatchObject({ status: "red", label: "Kollision" });
    expect(b.collision_badge).toBeNull(); // kein Lauf für b ⇒ kein Badge
  });

  it("dirty entwertet auch das Kollisions-Badge (Advisor-Anwenden, Issue #172, B20)", () => {
    // Nach „Anwenden" eines Advisor-Hebels (Platzierungs-Override) ist der Plan
    // dirty; das Kollisions-Badge gilt der ALTEN Platzierung und wird — wie Ampel
    // und Druckbarkeit — auf „ungeprüft" (null) entwertet, statt unmarkiert neben
    // den neuen Override-Werten stehen zu bleiben (B11/B20/B32).
    const collision = {
      config: { safety_distance_mm: 50, freizone_radius_mm: 30, provisional: false },
      min_distance_mm: -3,
      n_red: 2,
      n_yellow: 0,
      n_green: 8,
      distances_mm: [],
      intervals: [],
    };
    const clean = paletteEntries(input({ collisionBySectionId: { a: collision } }));
    expect(clean.find((e) => e.section_id === "a")!.collision_badge?.status).toBe("red");
    const dirty = paletteEntries(
      input({ collisionBySectionId: { a: collision }, dirty: true }),
    );
    const a = dirty.find((e) => e.section_id === "a")!;
    expect(a.collision_badge).toBeNull();
    expect(a.ampel).toBe("ungeprueft");
    expect(a.printability).toBeNull();
  });

  it("veraltet über dieselbe Ableitung wie die übrigen Badges (Issue #182)", () => {
    const collision = {
      config: { safety_distance_mm: 50, freizone_radius_mm: 30, provisional: false },
      min_distance_mm: -3,
      n_red: 2,
      n_yellow: 0,
      n_green: 8,
      distances_mm: [],
      intervals: [],
    };
    // Ohne revisions (Altaufrufer) gilt nichts als veraltet — Status quo.
    const noRevisions = paletteEntries(
      input({ collisionBySectionId: { a: collision } }),
    );
    expect(noRevisions.find((e) => e.section_id === "a")!.collision_badge).toMatchObject({
      status: "red",
      stale: false,
    });

    // Ein Parameter-Bump (process) nach der letzten Simulation von "a" macht das
    // Badge veraltet — dieselbe Ableitung wie Druckplan-/Simulation-/Export-Badge
    // (sectionStageStatus, Stufe "simulation").
    const staleRevisions = paletteEntries(
      input({
        collisionBySectionId: { a: collision },
        revisions: {
          inputs: { wall: 1, robot: 1, cutplan: 1, process: 1, workstation: 0 },
          outputs: {},
          section_outputs: {
            a: {
              simulation: {
                wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0,
              },
            },
          },
        },
      }),
    );
    const staleEntry = staleRevisions.find((e) => e.section_id === "a")!;
    // Bleibt sichtbar (Status/Label unverändert) — nur zusätzlich markiert.
    expect(staleEntry.collision_badge).toMatchObject({ status: "red", stale: true });

    // Ein aktueller Schnappschuss (kein Bump seit der Simulation) bleibt nicht-veraltet.
    const currentRevisions = paletteEntries(
      input({
        collisionBySectionId: { a: collision },
        revisions: {
          inputs: { wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0 },
          outputs: {},
          section_outputs: {
            a: {
              simulation: {
                wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0,
              },
            },
          },
        },
      }),
    );
    expect(
      currentRevisions.find((e) => e.section_id === "a")!.collision_badge,
    ).toMatchObject({ status: "red", stale: false });
  });

  it("dirty entwertet weiterhin hart auf null, auch mit stale-Revisionen (#172/B20 bleibt Vorrang)", () => {
    const collision = {
      config: { safety_distance_mm: 50, freizone_radius_mm: 30, provisional: false },
      min_distance_mm: -3,
      n_red: 1,
      n_yellow: 0,
      n_green: 9,
      distances_mm: [],
      intervals: [],
    };
    const entries = paletteEntries(
      input({
        collisionBySectionId: { a: collision },
        dirty: true,
        revisions: {
          inputs: { wall: 1, robot: 1, cutplan: 1, process: 1, workstation: 0 },
          outputs: {},
          section_outputs: {
            a: {
              simulation: {
                wall: 1, robot: 1, cutplan: 1, process: 0, workstation: 0, section: 0,
              },
            },
          },
        },
      }),
    );
    expect(entries.find((e) => e.section_id === "a")!.collision_badge).toBeNull();
  });

  it("lässt die Platzierungs-Ampel unangetastet (getrennter Kanal, Regressionsanker)", () => {
    const entries = paletteEntries(
      input({
        collisionBySectionId: {
          a: {
            config: { safety_distance_mm: 50, freizone_radius_mm: 30, provisional: false },
            min_distance_mm: -3,
            n_red: 1,
            n_yellow: 0,
            n_green: 9,
            distances_mm: [],
            intervals: [],
          },
        },
      }),
    );
    const a = entries.find((e) => e.section_id === "a")!;
    // a trägt kein Druckbarkeits-Urteil ⇒ Ampel „ungeprüft" (Issue #170); das
    // Kollisions-Badge ist ein getrennter Kanal und bleibt „red" — die zwei Kanäle
    // beeinflussen sich nicht (Regressionsanker).
    expect(a.ampel).toBe("ungeprueft");
    expect(a.collision_badge?.status).toBe("red");
  });
});
