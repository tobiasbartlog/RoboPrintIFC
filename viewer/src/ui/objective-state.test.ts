/**
 * Zielfunktions-Einstellungen (Issue #212, PRD #183 Stufe 3): reine Logik des
 * Einstellungs-Fensters — Default vorbelegt, Laden aus dem Druckjob (speichert/
 * lädt), Rangfolge aus den Gewichten, Gleichstands-Sperre NUR im Aus-Modus
 * (UI-seitige Verhinderung, Grill 2026-07-14). Dazu der DOM-Vertrag: jede vom
 * Fenster (`ui/objective.ts`) verdrahtete Element-ID existiert in index.html
 * (Lehre der ⌘K-Palette: grüne Unit-Tests trotz toter Verdrahtung).
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import type { ObjectiveWeights, PrintJob } from "../api/projects";
import {
  DEFAULT_OBJECTIVE_WEIGHTS,
  OBJECTIVE_CRITERIA,
  defaultObjective,
  objectiveFromJob,
  objectiveRanking,
  objectiveReadingText,
  objectiveSaveBlocked,
  tiedCriteria,
} from "./objective-state";

const job = (objective?: PrintJob["objective"]): PrintJob => ({
  job_id: "default",
  wall_global_id: "WALL",
  ...(objective ? { objective } : {}),
});

describe("objectiveFromJob: Default vorbelegt, speichert/lädt", () => {
  it("ohne Druckjob / ohne objective-Feld gilt die gepinnte Default-Config", () => {
    expect(objectiveFromJob(undefined)).toEqual(defaultObjective());
    expect(objectiveFromJob(null)).toEqual(defaultObjective());
    expect(objectiveFromJob(job())).toEqual(defaultObjective());
    // Default: Aufwiegen AUS, Gewichte absteigend entlang der Grill-Rangfolge.
    expect(defaultObjective().aufwiegen).toBe(false);
    expect(objectiveRanking(defaultObjective().weights)).toEqual(
      OBJECTIVE_CRITERIA.map((c) => c.key),
    );
  });

  it("lädt einen gespeicherten Stand verlustfrei (Roundtrip Fenster → Job → Fenster)", () => {
    const stored = {
      aufwiegen: true,
      weights: { umsetzvorgaenge: 8, fugenflaeche: 3, kinematische_marge: 2, volumen_cv: 1 },
    };
    expect(objectiveFromJob(job(stored))).toEqual(stored);
  });

  it("teilbelegte Gewichte erben fehlende Kriterien aus den Defaults (fail-soft)", () => {
    const partial = { umsetzvorgaenge: 9 } as ObjectiveWeights;
    const loaded = objectiveFromJob(job({ aufwiegen: false, weights: partial }));
    expect(loaded.weights.umsetzvorgaenge).toBe(9);
    expect(loaded.weights.volumen_cv).toBe(DEFAULT_OBJECTIVE_WEIGHTS.volumen_cv);
  });
});

describe("objectiveRanking: Gewichts-Reihenfolge = Rangfolge (Aus-Lesart)", () => {
  it("sortiert absteigend nach Gewicht", () => {
    expect(
      objectiveRanking({
        umsetzvorgaenge: 1,
        fugenflaeche: 2,
        kinematische_marge: 3,
        volumen_cv: 4,
      }),
    ).toEqual(["volumen_cv", "kinematische_marge", "fugenflaeche", "umsetzvorgaenge"]);
  });

  it("Gleichstand behält die Kriterien-Registry-Reihenfolge (deterministisch)", () => {
    const ranking = objectiveRanking({
      umsetzvorgaenge: 2,
      fugenflaeche: 2,
      kinematische_marge: 2,
      volumen_cv: 2,
    });
    expect(ranking).toEqual(OBJECTIVE_CRITERIA.map((c) => c.key));
  });
});

describe("Gleichstand im Aus-Modus wird verhindert (Grill 2026-07-14)", () => {
  const tiedWeights = {
    umsetzvorgaenge: 4,
    fugenflaeche: 4,
    kinematische_marge: 2,
    volumen_cv: 1,
  };

  it("tiedCriteria benennt die gleichauf liegenden Kriterien", () => {
    expect(tiedCriteria(tiedWeights)).toEqual([["umsetzvorgaenge", "fugenflaeche"]]);
    expect(tiedCriteria(DEFAULT_OBJECTIVE_WEIGHTS)).toEqual([]);
  });

  it("Aus-Modus: Gleichstand sperrt das Speichern mit benannten Kriterien", () => {
    const blocked = objectiveSaveBlocked({ aufwiegen: false, weights: tiedWeights });
    expect(blocked).toMatch(/Gleichstand/);
    expect(blocked).toMatch(/Umsetzvorgänge/);
    expect(blocked).toMatch(/Fugenfläche/);
  });

  it("An-Modus (Aufwiegen): derselbe Gleichstand ist zulässig", () => {
    expect(objectiveSaveBlocked({ aufwiegen: true, weights: tiedWeights })).toBeNull();
  });

  it("der Default ist speicherbar (kein Gleichstand)", () => {
    expect(objectiveSaveBlocked(defaultObjective())).toBeNull();
  });

  it("nicht-positive/nicht-endliche Gewichte sperren in beiden Lesarten", () => {
    for (const aufwiegen of [false, true]) {
      for (const bad of [0, -1, Number.NaN]) {
        const settings = {
          aufwiegen,
          weights: { ...DEFAULT_OBJECTIVE_WEIGHTS, fugenflaeche: bad },
        };
        expect(objectiveSaveBlocked(settings)).toMatch(/positive Zahl/);
      }
    }
  });
});

describe("objectiveReadingText: die Lesart ist benannt, nie still", () => {
  it("Aus-Modus nennt die Rangfolge und das harte K.-o.", () => {
    const text = objectiveReadingText(defaultObjective());
    expect(text).toMatch(/Rangfolge/);
    expect(text).toMatch(/kein Aufwiegen/);
    expect(text).toMatch(/K\.-o\./);
    expect(text).toMatch(
      /Umsetzvorgänge > Fugenfläche > kinematische Marge > Volumen-Gleichmäßigkeit/,
    );
  });

  it("An-Modus nennt die gewichtete Summe", () => {
    const text = objectiveReadingText({ ...defaultObjective(), aufwiegen: true });
    expect(text).toMatch(/Gewichtete Summe/);
    expect(text).toMatch(/K\.-o\./);
  });
});

describe("index.html: DOM-Vertrag des Einstellungs-Fensters (Issue #212)", () => {
  const html = readFileSync(
    fileURLToPath(new URL("../../index.html", import.meta.url)),
    "utf-8",
  );

  it.each([
    "objective-fenster",
    "objective-open-btn",
    "objective-aufwiegen",
    "objective-weights",
    "objective-reading",
    "objective-status",
    "objective-save-btn",
    "objective-cancel-btn",
    "objective-reset-btn",
  ])("Element #%s existiert", (id) => {
    expect(html).toContain(`id="${id}"`);
  });

  it("das Fenster startet versteckt (Sichtbarkeit nur über `hidden`)", () => {
    const root = html.slice(html.indexOf('id="objective-fenster"'));
    expect(root.slice(0, root.indexOf(">"))).toContain("hidden");
  });
});
