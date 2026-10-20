import { describe, expect, it } from "vitest";

import type { Candidates } from "../artifacts/types";
import {
  formatRelativeGerman,
  wallBalanceFromCandidates,
  wallBalanceLegend,
  wallBalanceSegments,
  wallBalanceTotal,
  type WallBalance,
} from "./wall-balance";

/** Baut ein minimales candidates-Artefakt aus (eligible, provisional?)-Wänden. */
function candidates(walls: Array<{ eligible: boolean; provisional?: boolean }>): Candidates {
  return {
    schema_version: "0.1",
    provenance: { source: "test", created: "2026-07-08T00:00:00Z", git_commit: "0" },
    model: "test.ifc",
    walls: walls.map((w, i) => ({
      global_id: `w${i}`,
      eligible: w.eligible,
      checks: [
        { check: "reach", passed: true, provisional: false },
        // Ein bestandener provisional-Check kennzeichnet „vorläufig".
        ...(w.provisional ? [{ check: "workspace", passed: true, provisional: true }] : []),
      ],
    })),
  };
}

describe("wallBalanceFromCandidates — Regel gespiegelt aus render/model.ts verdict()", () => {
  it("zählt druckbar/vorläufig/ungeeignet aus den Flags (kein Neu-Rechnen)", () => {
    const c = candidates([
      { eligible: true },
      { eligible: true },
      { eligible: true, provisional: true },
      { eligible: false },
    ]);
    expect(wallBalanceFromCandidates(c)).toEqual({ druckbar: 2, vorlaeufig: 1, ungeeignet: 1 });
  });

  it("eligible mit provisional-Pass ist vorläufig, nicht druckbar", () => {
    const c = candidates([{ eligible: true, provisional: true }]);
    expect(wallBalanceFromCandidates(c)).toEqual({ druckbar: 0, vorlaeufig: 1, ungeeignet: 0 });
  });

  it("nicht eligible ist immer ungeeignet (auch mit provisional-Checks)", () => {
    const c = candidates([{ eligible: false, provisional: true }]);
    expect(wallBalanceFromCandidates(c)).toEqual({ druckbar: 0, vorlaeufig: 0, ungeeignet: 1 });
  });

  it("leeres Artefakt ergibt eine Null-Bilanz", () => {
    expect(wallBalanceFromCandidates(candidates([]))).toEqual({
      druckbar: 0,
      vorlaeufig: 0,
      ungeeignet: 0,
    });
  });
});

describe("wallBalanceSegments — Anteile in Prozent, degradiert bei Null", () => {
  it("rechnet Anteile aus den Zählungen (Summe 100)", () => {
    const b: WallBalance = { druckbar: 2, vorlaeufig: 1, ungeeignet: 1 };
    const seg = wallBalanceSegments(b);
    expect(seg).toEqual({ druckbar: 50, vorlaeufig: 25, ungeeignet: 25 });
    expect(seg!.druckbar + seg!.vorlaeufig + seg!.ungeeignet).toBeCloseTo(100);
  });

  it("gibt null zurück, wenn nichts zu bilanzieren ist (kein Balken statt kaputtem Balken)", () => {
    expect(wallBalanceSegments({ druckbar: 0, vorlaeufig: 0, ungeeignet: 0 })).toBeNull();
  });

  it("100 % einer Kategorie füllt den Balken vollständig", () => {
    expect(wallBalanceSegments({ druckbar: 3, vorlaeufig: 0, ungeeignet: 0 })).toEqual({
      druckbar: 100,
      vorlaeufig: 0,
      ungeeignet: 0,
    });
  });
});

describe("wallBalanceTotal / wallBalanceLegend", () => {
  it("summiert alle Kategorien", () => {
    expect(wallBalanceTotal({ druckbar: 9, vorlaeufig: 4, ungeeignet: 7 })).toBe(20);
  });

  it("nennt nur nicht-leere Kategorien, getrennt mit ·", () => {
    expect(wallBalanceLegend({ druckbar: 9, vorlaeufig: 4, ungeeignet: 7 })).toBe(
      "9 druckbar · 4 vorläufig · 7 ungeeignet",
    );
    expect(wallBalanceLegend({ druckbar: 1, vorlaeufig: 0, ungeeignet: 0 })).toBe("1 druckbar");
    expect(wallBalanceLegend({ druckbar: 0, vorlaeufig: 0, ungeeignet: 0 })).toBe("");
  });
});

describe("formatRelativeGerman", () => {
  const base = Date.parse("2026-07-08T12:00:00Z");
  const ago = (ms: number) => formatRelativeGerman(base - ms, base);

  it("staffelt Minuten, Stunden, Tage", () => {
    expect(ago(30 * 1000)).toBe("gerade eben");
    expect(ago(60 * 1000)).toBe("vor 1 Min.");
    expect(ago(45 * 60 * 1000)).toBe("vor 45 Min.");
    expect(ago(2 * 60 * 60 * 1000)).toBe("vor 2 Std.");
    expect(ago(24 * 60 * 60 * 1000)).toBe("gestern");
    expect(ago(3 * 24 * 60 * 60 * 1000)).toBe("vor 3 Tagen");
  });

  it("fällt ab einer Woche auf ein Datum zurück", () => {
    expect(ago(30 * 24 * 60 * 60 * 1000)).toMatch(/\d{2}\.\d{2}\.\d{4}/);
  });

  it("clampt negative Differenzen (Uhr-Schräglauf) auf „gerade eben\"", () => {
    expect(formatRelativeGerman(base + 5000, base)).toBe("gerade eben");
  });
});
