/**
 * Druckort-View-State (Issue #96, ADR-022): der Umschalter Einbauort↔Druckort
 * existiert NUR am fokussierten Modul (bei Abschnitten entfällt er — Einbauort
 * = Druckort); fällt die Voraussetzung weg, kehrt die Ansicht sauber auf
 * „einbauort" zurück. Reine Logik, DOM-frei.
 */

import { describe, expect, it } from "vitest";

import {
  druckortAvailable,
  initDruckortState,
  isDruckort,
  reconcileDruckortView,
  resolveReplayReturnCamera,
  selectDruckortView,
} from "./druckort-state";

describe("initDruckortState", () => {
  it("startet abwärtskompatibel im Einbauort", () => {
    const s = initDruckortState();
    expect(s.view).toBe("einbauort");
    expect(isDruckort(s)).toBe(false);
  });
});

describe("druckortAvailable — Umschalter nur am fokussierten Modul", () => {
  it("existiert bei Art modul + Fokus", () => {
    expect(druckortAvailable("modul", "abschnitt-1")).toBe(true);
  });

  it("entfällt bei Abschnitten (Einbauort = Druckort), auch mit Fokus", () => {
    expect(druckortAvailable("abschnitt", "abschnitt-1")).toBe(false);
  });

  it("entfällt ohne Fokus, auch bei Art modul", () => {
    expect(druckortAvailable("modul", null)).toBe(false);
  });

  it("entfällt ohne Fokus bei Abschnitten", () => {
    expect(druckortAvailable("abschnitt", null)).toBe(false);
  });
});

describe("selectDruckortView — Nutzerwahl", () => {
  it("schaltet am fokussierten Modul auf Druckort", () => {
    const s = selectDruckortView(initDruckortState(), "druckort", "modul", "abschnitt-1");
    expect(s.view).toBe("druckort");
    expect(isDruckort(s)).toBe(true);
  });

  it("ignoriert Druckort ohne Modul-Fokus (bleibt Einbauort)", () => {
    const s = selectDruckortView(initDruckortState(), "druckort", "modul", null);
    expect(s.view).toBe("einbauort");
  });

  it("ignoriert Druckort bei Art abschnitt", () => {
    const s = selectDruckortView(initDruckortState(), "druckort", "abschnitt", "abschnitt-1");
    expect(s.view).toBe("einbauort");
  });

  it("schaltet immer zurück auf Einbauort (Rückweg)", () => {
    const druckort = selectDruckortView(
      initDruckortState(), "druckort", "modul", "abschnitt-1",
    );
    const back = selectDruckortView(druckort, "einbauort", "modul", "abschnitt-1");
    expect(back.view).toBe("einbauort");
  });

  it("gibt bei unveränderter Ansicht denselben Zustand zurück (Referenz)", () => {
    const s = initDruckortState();
    expect(selectDruckortView(s, "einbauort", "modul", "abschnitt-1")).toBe(s);
    const d = selectDruckortView(s, "druckort", "modul", "abschnitt-1");
    expect(selectDruckortView(d, "druckort", "modul", "abschnitt-1")).toBe(d);
  });
});

describe("reconcileDruckortView — Voraussetzungen fallen weg", () => {
  const druckort = selectDruckortView(
    initDruckortState(), "druckort", "modul", "abschnitt-1",
  );

  it("Fokus gelöst → zurück auf Einbauort", () => {
    expect(reconcileDruckortView(druckort, "modul", null).view).toBe("einbauort");
  });

  it("Artwechsel auf abschnitt → zurück auf Einbauort", () => {
    expect(reconcileDruckortView(druckort, "abschnitt", "abschnitt-1").view).toBe(
      "einbauort",
    );
  });

  it("Voraussetzungen intakt → Ansicht bleibt (derselbe Zustand)", () => {
    expect(reconcileDruckortView(druckort, "modul", "abschnitt-2")).toBe(druckort);
  });

  it("Einbauort bleibt Einbauort — reconcile ändert nie in Richtung Druckort", () => {
    const s = initDruckortState();
    expect(reconcileDruckortView(s, "modul", "abschnitt-1")).toBe(s);
  });
});

describe("resolveReplayReturnCamera — Rückweg trägt die Wand-Ansicht (Issue #137)", () => {
  it("ohne Stash (frisch aus der Wand-Ansicht): hält die aktuelle Kamera fest", () => {
    const current = { view: "wand" };
    let calls = 0;
    const result = resolveReplayReturnCamera(null, () => {
      calls++;
      return current;
    });
    expect(result).toBe(current);
    expect(calls).toBe(1);
  });

  it("mit vorhandenem Stash (schon am Druckort): reicht den Stash durch und snapshottet NICHT die Druckort-Kamera", () => {
    const stashedWall = { view: "wand" };
    let calls = 0;
    const result = resolveReplayReturnCamera(stashedWall, () => {
      calls++;
      return { view: "druckort" }; // die aktuelle (falsche) Kamera
    });
    // Der Kern des Bugfixes: der bestehende Wand-Stash gewinnt, die aktuelle
    // Druckort-Kamera wird gar nicht erst erfasst.
    expect(result).toBe(stashedWall);
    expect(calls).toBe(0);
  });
});
