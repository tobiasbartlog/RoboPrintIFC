import { describe, expect, it } from "vitest";

import type {
  PlacementFeasibility,
  ScoredPlacementOption,
} from "../api/projects";
import {
  placementAmpel,
  placementFeasibilityHint,
  placementSuggestionRows,
} from "./placement-suggestion-state";

function option(overrides: Partial<ScoredPlacementOption> = {}): ScoredPlacementOption {
  return {
    option_id: "vorschlag-1",
    lateral_mm: 0,
    standoff_mm: 700,
    stand_height_mm: 0,
    yaw_rad: 0,
    score: { reachable_fraction: 1, kinematic_margin: 0.5 },
    ...overrides,
  };
}

describe("placementAmpel — Kollisions-Ampel aus dem Core-Urteil (Issue #231)", () => {
  it("status=clear -> grün/frei", () => {
    expect(placementAmpel({ free: true, status: "clear", source: "coarse" })).toEqual({
      tone: "ok",
      label: "frei",
    });
  });

  it("status=colliding -> rot/kollidierend", () => {
    expect(placementAmpel({ free: false, status: "colliding", source: "coarse" })).toEqual({
      tone: "bad",
      label: "kollidierend",
    });
  });

  it("kein Urteil (undefined) -> neutral/nicht geprüft — keine erfundene Ampel", () => {
    expect(placementAmpel(undefined)).toEqual({ tone: "muted", label: "nicht geprüft" });
  });

  it("null -> neutral/nicht geprüft", () => {
    expect(placementAmpel(null)).toEqual({ tone: "muted", label: "nicht geprüft" });
  });

  it("unbekannter status-Wert faellt fail-soft auf neutral zurueck (kein Absturz)", () => {
    expect(
      placementAmpel({ free: false, status: "im_sicherheitsband", source: "exact" }),
    ).toEqual({ tone: "muted", label: "nicht geprüft" });
  });
});

describe("placementSuggestionRows — Vorschlagsliste, je Vorschlag eine Ampel", () => {
  it("bildet leere Liste ohne scored ab", () => {
    expect(placementSuggestionRows(undefined)).toEqual([]);
    expect(placementSuggestionRows(null)).toEqual([]);
    expect(placementSuggestionRows([])).toEqual([]);
  });

  it("bildet je Kandidat eine Zeile mit Ampel aus score.collision, Core-Reihenfolge erhalten", () => {
    const scored = [
      option({
        option_id: "vorschlag-1",
        standoff_mm: 500,
        stand_height_mm: 300,
        score: {
          reachable_fraction: 1,
          kinematic_margin: 0.4,
          collision: { free: true, status: "clear", source: "coarse" },
        },
      }),
      option({
        option_id: "vorschlag-2",
        standoff_mm: 230,
        stand_height_mm: 0,
        score: {
          reachable_fraction: 0.8,
          kinematic_margin: 0.1,
          collision: { free: false, status: "colliding", source: "coarse" },
        },
      }),
    ];
    const rows = placementSuggestionRows(scored);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({
      optionId: "vorschlag-1",
      ampel: { tone: "ok", label: "frei" },
      detail: "erreichbar 100% · Abstand 500 mm / Höhe 300 mm",
    });
    expect(rows[1]).toEqual({
      optionId: "vorschlag-2",
      ampel: { tone: "bad", label: "kollidierend" },
      detail: "erreichbar 80% · Abstand 230 mm / Höhe 0 mm",
    });
  });

  it("Kandidat ohne Grob-Check (kein collision-Feld) -> neutrale Ampel, kein Absturz", () => {
    const rows = placementSuggestionRows([option()]);
    expect(rows[0].ampel).toEqual({ tone: "muted", label: "nicht geprüft" });
  });
});

describe("placementFeasibilityHint — Hinweis + Absprung nur bei 'kein machbarer Kandidat'", () => {
  it("kein Befund (undefined/null) -> kein Hinweis", () => {
    expect(placementFeasibilityHint(undefined)).toEqual({ show: false, text: "" });
    expect(placementFeasibilityHint(null)).toEqual({ show: false, text: "" });
  });

  it("checked=false (Grob-Check nicht gelaufen) -> kein Hinweis, auch wenn feasible gesetzt waere", () => {
    const feasibility: PlacementFeasibility = {
      checked: false,
      feasible: null,
      n_feasible: 0,
      n_total: 0,
      note: "Kollisions-Grob-Check nicht gelaufen (keine Geometrie) — Machbarkeit unbekannt.",
    };
    expect(placementFeasibilityHint(feasibility).show).toBe(false);
  });

  it("mindestens ein machbarer Kandidat -> kein Hinweis", () => {
    const feasibility: PlacementFeasibility = {
      checked: true,
      feasible: true,
      n_feasible: 1,
      n_total: 3,
      note: "Mindestens ein kollisionsfreier Vorschlag vorhanden.",
    };
    expect(placementFeasibilityHint(feasibility)).toEqual({ show: false, text: "" });
  });

  it("kein machbarer Kandidat -> Hinweis sichtbar mit dem Core-Text verbatim", () => {
    const feasibility: PlacementFeasibility = {
      checked: true,
      feasible: false,
      n_feasible: 0,
      n_total: 3,
      note:
        "Kein machbarer Kandidat — alle Vorschläge kollidieren grob " +
        "(Zerlegen statt weiter platzieren, ADR-026 Punkt 2).",
    };
    expect(placementFeasibilityHint(feasibility)).toEqual({
      show: true,
      text:
        "Kein machbarer Kandidat — alle Vorschläge kollidieren grob " +
        "(Zerlegen statt weiter platzieren, ADR-026 Punkt 2).",
    });
  });
});
