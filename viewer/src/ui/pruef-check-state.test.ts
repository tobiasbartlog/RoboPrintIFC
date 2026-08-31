/**
 * Reine Zustandsfunktionen der entkoppelten Stufe-2-Prüf-Tür (Issue #175).
 *
 * Prüft Fortschritts-/ungeprüft-/letzter-Prüfstand-Anzeige + die Veraltungs-Ableitung
 * (Parität zu `fgc.project.revisions.pruef_status`). DOM-frei, deterministisch.
 */

import { describe, expect, it } from "vitest";

import type {
  DecompositionCheckStatus,
  LastPruef,
  PruefScope,
} from "../api/projects";
import { expectGoldenParity } from "../test/golden-parity";
import golden from "./staleness.golden.json";
import type { Revisions } from "./staleness";
import {
  PER_REP_SECONDS,
  PRUEF_DEPS,
  checkProgressView,
  lastCheckView,
  pruefStatus,
  scopeAnnouncement,
} from "./pruef-check-state";

function status(
  over: Partial<DecompositionCheckStatus>,
): DecompositionCheckStatus {
  return {
    check_id: "c1",
    slug: "s",
    job_id: "default",
    scope: "global",
    state: "running",
    n_total: 0,
    n_done: 0,
    n_computed: 0,
    n_cached: 0,
    ...over,
  };
}

describe("pruefStatus — Veraltung des letzten Prüfstands (Issue #175)", () => {
  it("ohne last_pruef ⇒ 'missing' (nie geprüft = ungeprüft)", () => {
    expect(pruefStatus({ inputs: { cutplan: 2 } }, undefined)).toBe("missing");
    expect(pruefStatus(undefined, null)).toBe("missing");
  });

  it("unveränderte Eingaben ⇒ 'current'", () => {
    const revisions: Revisions = { inputs: { wall: 1, cutplan: 3, process: 2 } };
    const last: LastPruef = {
      scope: "global",
      input_snapshot: { wall: 1, cutplan: 3, process: 2, section_total: 0 },
    };
    expect(pruefStatus(revisions, last)).toBe("current");
  });

  it("eine Prüf-Eingabe neuer als der Schnappschuss ⇒ 'stale'", () => {
    const revisions: Revisions = { inputs: { cutplan: 4, process: 2 } };
    const last: LastPruef = {
      scope: "global",
      input_snapshot: { cutplan: 3, process: 2 },
    };
    expect(pruefStatus(revisions, last)).toBe("stale");
  });

  it("ein Platzierungs-/Abschnitts-Override (section_total steigt) ⇒ 'stale'", () => {
    const revisions: Revisions = {
      inputs: { cutplan: 3 },
      section_inputs: { "abschnitt-1": 1, "abschnitt-2": 1 },
    };
    const last: LastPruef = {
      scope: "focus",
      section_id: "abschnitt-1",
      input_snapshot: { cutplan: 3, section_total: 1 },
    };
    expect(pruefStatus(revisions, last)).toBe("stale");
  });

  it("last_pruef OHNE/ mit leerem input_snapshot ⇒ 'missing' (#194, keine stille Aktualität)", () => {
    // Legacy-/Fehl-Datensatz: ohne Schnappschuss ist Aktualität nicht beweisbar.
    expect(pruefStatus({ inputs: { wall: 1 } }, { scope: "global" })).toBe("missing");
    expect(pruefStatus({ inputs: {} }, { scope: "global", input_snapshot: {} })).toBe("missing");
  });
});

describe("Prüf-Parität gegen das geteilte Core-Golden (Issue #194)", () => {
  it("die Prüf-Konstanten sind bit-gleich zum Core (Kommentar-Syncpunkte als Fakt)", () => {
    expect(PRUEF_DEPS).toEqual(golden.constants.PRUEF_DEPS);
    expect(PER_REP_SECONDS).toEqual(golden.constants.PER_REP_SECONDS);
  });

  it("pruefStatus reproduziert jeden pruef_case des Core (inkl. last_pruef-Kante)", () => {
    expectGoldenParity(golden.pruef_cases, (c) =>
      pruefStatus(
        (c.revisions ?? undefined) as Revisions | undefined,
        (c.last_pruef ?? undefined) as LastPruef | undefined,
      ),
    );
  });
});

describe("scopeAnnouncement — Umfangsansage (Issue #175)", () => {
  it("nennt N Abschnitte + grobe Dauer für den globalen Knopf", () => {
    const scope: PruefScope = { n_representatives: 4, n_parts: 12, est_seconds: 40 };
    const a = scopeAnnouncement(scope);
    expect(a.globalEmpty).toBe(false);
    expect(a.globalLabel).toContain("4 Abschnitte");
    expect(a.globalLabel).toContain("~40 s");
    expect(a.focusLabel).toContain("Fokus");
  });

  it("Singular bei genau einem Abschnitt", () => {
    expect(scopeAnnouncement({ n_representatives: 1, n_parts: 3, est_seconds: 10 }).globalLabel).toContain(
      "1 Abschnitt,",
    );
  });

  it("nichts zu prüfen (0 Reihen) ⇒ globalEmpty, kein N", () => {
    const a = scopeAnnouncement({ n_representatives: 0, n_parts: 6, est_seconds: 0 });
    expect(a.globalEmpty).toBe(true);
    expect(a.globalLabel).toContain("nichts zu prüfen");
  });

  it("unbekannter Umfang (null) ⇒ generischer Knopf, NICHT deaktiviert", () => {
    const a = scopeAnnouncement(null);
    expect(a.globalEmpty).toBe(false);
    expect(a.globalLabel).toBe("Ganze Wand prüfen");
  });
});

describe("checkProgressView — Fortschritt/Ergebnis (Issue #175)", () => {
  it("null ⇒ inaktiv (nichts anzeigen)", () => {
    expect(checkProgressView(null).active).toBe(false);
  });

  it("running ⇒ Fortschrittsbalken + abbrechbar, Zähler im Text", () => {
    const v = checkProgressView(status({ state: "running", n_total: 8, n_done: 3 }));
    expect(v.running).toBe(true);
    expect(v.cancellable).toBe(true);
    expect(v.fraction).toBeCloseTo(3 / 8);
    expect(v.label).toContain("3/8 Höhenreihen");
  });

  it("done ⇒ nicht mehr abbrechbar, Cache-Statistik sichtbar, Ton ok", () => {
    const v = checkProgressView(
      status({ state: "done", n_total: 4, n_done: 4, n_computed: 1, n_cached: 3, scope: "focus" }),
    );
    expect(v.running).toBe(false);
    expect(v.cancellable).toBe(false);
    expect(v.tone).toBe("ok");
    expect(v.label).toContain("1 gerechnet");
    expect(v.label).toContain("3 aus Cache");
    expect(v.label).toContain("Fokus");
  });

  it("cancelled ⇒ ehrlicher Abbruch-Text, kein Grün", () => {
    const v = checkProgressView(status({ state: "cancelled" }));
    expect(v.tone).toBe("warn");
    expect(v.label).toContain("abgebrochen");
    expect(v.label).toContain("ungeprüft");
  });

  it("superseded ⇒ 'verworfen, neu anstoßen'", () => {
    const v = checkProgressView(status({ state: "superseded" }));
    expect(v.tone).toBe("warn");
    expect(v.label).toContain("verworfen");
  });

  it("error ⇒ roter Ton mit Meldung", () => {
    const v = checkProgressView(status({ state: "error", error: "boom" }));
    expect(v.tone).toBe("bad");
    expect(v.label).toContain("boom");
  });
});

describe("lastCheckView — letzter Prüfstand (Issue #175)", () => {
  it("nie geprüft ⇒ 'noch nicht geprüft'", () => {
    const v = lastCheckView({ inputs: { cutplan: 1 } }, undefined);
    expect(v.known).toBe(false);
    expect(v.label).toContain("noch nicht geprüft");
    expect(v.tone).toBe("warn");
  });

  it("global geprüft + aktuell ⇒ 'ganze Wand', Ton ok", () => {
    const revisions: Revisions = { inputs: { cutplan: 3 } };
    const last: LastPruef = { scope: "global", input_snapshot: { cutplan: 3 } };
    const v = lastCheckView(revisions, last);
    expect(v.known).toBe(true);
    expect(v.stale).toBe(false);
    expect(v.label).toContain("ganze Wand");
    expect(v.tone).toBe("ok");
  });

  it("Fokus geprüft + veraltet ⇒ nennt Teil + '(veraltet)'", () => {
    const revisions: Revisions = { inputs: { cutplan: 5 } };
    const last: LastPruef = {
      scope: "focus",
      section_id: "abschnitt-2",
      input_snapshot: { cutplan: 3 },
    };
    const v = lastCheckView(revisions, last);
    expect(v.stale).toBe(true);
    expect(v.label).toContain("abschnitt-2");
    expect(v.label).toContain("veraltet");
    expect(v.tone).toBe("warn");
  });
});
