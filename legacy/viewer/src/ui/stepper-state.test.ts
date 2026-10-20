import { describe, expect, it } from "vitest";

import type { OutputName, StageStatus } from "./staleness";
import {
  NAV_NOTE,
  PROCESS_STEPS,
  type StepDef,
  stepDotClass,
  stepDotKind,
  stepStatus,
  stepTooltip,
  stepperView,
} from "./stepper-state";

const statuses = (
  s: Partial<Record<OutputName, StageStatus>>,
): Partial<Record<OutputName, StageStatus>> => s;

describe("stepper-state (UI-Redesign Scheibe 2, Issue #102)", () => {
  it("bildet nach dem Druckplan-Split (#106) fünf Schritte ab: Zerlegung eigener Reiter, keine Bibliothek", () => {
    expect(PROCESS_STEPS.map((s) => s.tab)).toEqual([
      "projekt",
      "roboter",
      "zerlegung",
      "druckplan",
      "export",
    ]);
    expect(PROCESS_STEPS.map((s) => s.id)).toEqual([
      "projekt",
      "roboter",
      "zerlegung",
      "slicing",
      "export",
    ]);
    expect(PROCESS_STEPS.some((s) => s.tab === "bibliothek")).toBe(false);
  });

  it("Zerlegung/Slicing/Export binden an Output-Stufen (Projekt/Roboter sind Eingaben)", () => {
    const byId = Object.fromEntries(PROCESS_STEPS.map((s) => [s.id, s.output]));
    expect(byId.projekt).toBeUndefined();
    expect(byId.roboter).toBeUndefined();
    // Zerlegung erbt die frühere „druckplan"-Stufe (Platzierung/Zerlegung, Dirty-Kette).
    expect(byId.zerlegung).toBe("druckplan");
    // Slicing (übergangsweise Reiter druckplan) folgt der Prozessparameter-/Sim-Stufe.
    expect(byId.slicing).toBe("simulation");
    expect(byId.export).toBe("export");
  });

  it("stepStatus: Schritt ohne Output gilt stets als aktuell", () => {
    const step: StepDef = { id: "projekt", label: "Projekt", tab: "projekt" };
    expect(stepStatus(step, statuses({ druckplan: "stale" }))).toBe("current");
  });

  it("stepStatus: Schritt mit Output liest den passenden Zustand (fehlt er → current)", () => {
    const step: StepDef = { id: "export", label: "Export", tab: "export", output: "export" };
    expect(stepStatus(step, statuses({ export: "stale" }))).toBe("stale");
    expect(stepStatus(step, statuses({ export: "missing" }))).toBe("missing");
    expect(stepStatus(step, statuses({}))).toBe("current");
  });

  it("stepDotKind: aktiver Schritt = Akzent, sticht Veraltung aus", () => {
    expect(stepDotKind("stale", true)).toBe("accent");
    expect(stepDotKind("current", true)).toBe("accent");
  });

  it("stepDotKind: inaktiv = amber bei veraltet, sonst grün (missing gilt nicht als veraltet)", () => {
    expect(stepDotKind("stale", false)).toBe("stale");
    expect(stepDotKind("current", false)).toBe("current");
    expect(stepDotKind("missing", false)).toBe("current");
  });

  it("stepDotClass: bildet auf die .dot-Modifikatoren ab (accent/warn/ok)", () => {
    expect(stepDotClass("accent")).toBe("accent");
    expect(stepDotClass("stale")).toBe("warn");
    expect(stepDotClass("current")).toBe("ok");
  });

  it("stepTooltip: nennt immer die freie Navigation, bei Veraltung zusätzlich den Befund", () => {
    const step: StepDef = { id: "export", label: "Export", tab: "export", output: "export" };
    expect(stepTooltip(step, "current")).toBe(NAV_NOTE);
    const stale = stepTooltip(step, "stale");
    expect(stale).toContain("Export veraltet");
    expect(stale).toContain("ADR-017");
    expect(stale).toContain(NAV_NOTE);
  });

  it("stepperView: aktiver Reiter wird zum Akzent-Chip, davor steht ab dem 2. Schritt ein Trenner", () => {
    const views = stepperView(PROCESS_STEPS, statuses({}), "roboter");
    expect(views.map((v) => v.notFirst)).toEqual([false, true, true, true, true]);
    const roboter = views.find((v) => v.tab === "roboter")!;
    expect(roboter.isActive).toBe(true);
    expect(roboter.dotKind).toBe("accent");
    expect(roboter.dotClass).toBe("accent");
    // Inaktive, nicht veraltete Schritte sind grün.
    expect(views.find((v) => v.tab === "projekt")!.dotClass).toBe("ok");
  });

  it("stepperView: veraltete Zerlegung/Slicing/Export färben den Punkt amber (aus der Staleness-Ableitung)", () => {
    const views = stepperView(
      PROCESS_STEPS,
      // druckplan-Stufe → Zerlegungs-Schritt; simulation → Slicing-Schritt; export → Export.
      statuses({ druckplan: "stale", simulation: "stale", export: "stale" }),
      "projekt",
    );
    expect(views.find((v) => v.id === "zerlegung")!.dotClass).toBe("warn");
    expect(views.find((v) => v.id === "slicing")!.dotClass).toBe("warn");
    expect(views.find((v) => v.tab === "export")!.dotClass).toBe("warn");
    // Der aktive Schritt (projekt) ist Akzent; ein inaktiver ohne Output ist grün.
    expect(views.find((v) => v.tab === "projekt")!.dotClass).toBe("accent");
    expect(views.find((v) => v.tab === "roboter")!.dotClass).toBe("ok");
  });

  it("stepperView: bei aktiver Bibliothek (kein Stepper-Schritt) ist kein Schritt aktiv", () => {
    const views = stepperView(PROCESS_STEPS, statuses({ export: "stale" }), "bibliothek");
    expect(views.every((v) => !v.isActive)).toBe(true);
    // Punkte folgen dann rein der Staleness.
    expect(views.find((v) => v.tab === "export")!.dotClass).toBe("warn");
    expect(views.find((v) => v.tab === "roboter")!.dotClass).toBe("ok");
  });

  it("erweiterbar: eine 5-Schritt-Liste (Zerlegung/Slicing) rendert unverändert durch dieselbe Logik", () => {
    const future: StepDef[] = [
      { id: "projekt", label: "Projekt", tab: "projekt" },
      { id: "roboter", label: "Roboter", tab: "roboter" },
      { id: "zerlegung", label: "Zerlegung", tab: "druckplan", output: "druckplan" },
      { id: "slicing", label: "Slicing", tab: "druckplan", output: "simulation" },
      { id: "export", label: "Export", tab: "export", output: "export" },
    ];
    const views = stepperView(future, statuses({ simulation: "stale" }), "export");
    expect(views).toHaveLength(5);
    expect(views.find((v) => v.id === "slicing")!.dotClass).toBe("warn");
    expect(views.find((v) => v.id === "export")!.isActive).toBe(true);
  });
});
