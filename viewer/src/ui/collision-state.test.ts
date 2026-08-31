/**
 * Kollisionskontrolle S3 — reine Ableitung (US 8/9/11/12/25, Issue #128). Prüft,
 * dass alle Anzeigen **verbatim** aus `meta.collision` entstehen und dass die
 * Abwesenheit des Befunds (Altlauf) sicher der Status quo ist: keine Marker, kein
 * Badge, ehrliche Statuszeile, kein Crash.
 */

import { describe, expect, it } from "vitest";

import type { CollisionMeta } from "../artifacts/types";
import {
  causerLinkAt,
  clearedCollisionFindings,
  collisionBadge,
  collisionCaveats,
  collisionMetaPairs,
  collisionStatusLine,
  distanceAt,
  distanceReadout,
  hasCollisionFinding,
  linkHighlightAt,
  overallCollisionStatus,
  replayStatusLine,
  sampleIndexAtTime,
  statusAtIndex,
  timelineMarkers,
} from "./collision-state";

/** Befund über 5 Samples: grün, gelb, rot, gelb, grün — Verursacher Glied 4/5. */
function finding(over: Partial<CollisionMeta> = {}): CollisionMeta {
  return {
    config: { safety_distance_mm: 50, freizone_radius_mm: 30, provisional: true, mode: "abschnitt" },
    min_distance_mm: -8,
    worst_index: 2,
    n_red: 1,
    n_yellow: 2,
    n_green: 2,
    distances_mm: [120, 40, -8, 45, 200],
    causer_link: [null, 4, 5, 5, null],
    causer_against: [null, "current_part", "current_part", "ground", null],
    intervals: [
      { status: "yellow", start_index: 1, end_index: 1, min_distance_mm: 40, link: 4, against: "current_part" },
      { status: "red", start_index: 2, end_index: 2, min_distance_mm: -8, link: 5, against: "current_part" },
      { status: "yellow", start_index: 3, end_index: 3, min_distance_mm: 45, link: 5, against: "ground" },
    ],
    ...over,
  };
}

const TIMES = [0, 1, 2, 3, 4]; // t_s parallel zu den Samples
const DURATION = 4;

describe("Abwesenheit des Befunds ist sicher (US 25, Regressionsanker)", () => {
  it("hasCollisionFinding erkennt undefined/null als kein Befund", () => {
    expect(hasCollisionFinding(undefined)).toBe(false);
    expect(hasCollisionFinding(null)).toBe(false);
    expect(hasCollisionFinding(finding())).toBe(true);
  });

  it("kein Badge, ehrliche Statuszeile bei fehlendem Befund", () => {
    expect(collisionBadge(undefined)).toBeNull();
    expect(collisionBadge(null)).toBeNull();
    expect(collisionStatusLine(undefined)).toBe("Kinematisches Replay — keine Kollisionsprüfung.");
  });
});

describe("overallCollisionStatus — rot vor gelb vor grün", () => {
  it("rot, sobald n_red > 0", () => {
    expect(overallCollisionStatus(finding())).toBe("red");
  });
  it("gelb, wenn nur Warnungen", () => {
    expect(overallCollisionStatus(finding({ n_red: 0 }))).toBe("yellow");
  });
  it("grün, wenn nichts", () => {
    expect(overallCollisionStatus(finding({ n_red: 0, n_yellow: 0 }))).toBe("green");
  });
});

describe("sampleIndexAtTime — Zeit → Sample-Index (Darstellungsmathematik)", () => {
  it("klemmt an den Rändern und trifft die Stützstellen", () => {
    expect(sampleIndexAtTime(TIMES, -1)).toBe(0);
    expect(sampleIndexAtTime(TIMES, 2)).toBe(2);
    expect(sampleIndexAtTime(TIMES, 99)).toBe(4);
  });
  it("nimmt den größten Index mit t_s <= t", () => {
    expect(sampleIndexAtTime(TIMES, 2.7)).toBe(2);
  });
  it("leere Zeitachse → 0 (kein Crash)", () => {
    expect(sampleIndexAtTime([], 5)).toBe(0);
  });
});

describe("statusAtIndex — Lookup im verbatim-Intervall, kein Neu-Urteil", () => {
  it("liefert den Intervall-Status; ohne Intervall grün", () => {
    expect(statusAtIndex(finding(), 0)).toBe("green");
    expect(statusAtIndex(finding(), 1)).toBe("yellow");
    expect(statusAtIndex(finding(), 2)).toBe("red");
    expect(statusAtIndex(finding(), 4)).toBe("green");
  });
});

describe("Glied-Einfärbung (US 8) — verursachendes Glied bei rot/gelb", () => {
  it("färbt nur bei rot/gelb und bekanntem Verursacher-Glied", () => {
    expect(linkHighlightAt(finding(), 0)).toBeNull(); // grün
    expect(linkHighlightAt(finding(), 1)).toEqual({ link: 4, status: "yellow" });
    expect(linkHighlightAt(finding(), 2)).toEqual({ link: 5, status: "red" });
  });
  it("kein Glied trotz Status ⇒ null (nichts einfärben)", () => {
    const c = finding({ causer_link: [null, null, null, null, null] });
    expect(linkHighlightAt(c, 2)).toBeNull();
  });
  it("causerLinkAt liest verbatim (auch fehlendes Array sicher)", () => {
    expect(causerLinkAt(finding(), 2)).toBe(5);
    expect(causerLinkAt(finding({ causer_link: undefined }), 2)).toBeNull();
  });
});

describe("Live-Abstandszahl (US 11)", () => {
  it("zeigt gerundete mm; Kollision bei rotem Status", () => {
    expect(distanceReadout(finding(), 1)).toBe("Abstand 40 mm");
    expect(distanceReadout(finding(), 2)).toBe("Kollision (-8 mm)");
  });
  it("außerhalb der Prüfnähe (null) ehrliche Notiz", () => {
    const c = finding({ distances_mm: [null, 40, -8, 45, 200] });
    expect(distanceReadout(c, 0)).toBe("Abstand — (außer Prüfnähe)");
    expect(distanceAt(c, 0)).toBeNull();
  });
});

describe("Timeline-Marker (US 9) — je rot/gelb-Intervall ein anklickbarer Marker", () => {
  it("nur rot/gelb-Intervalle, Fraktion + Sprung-Zeit aus t_s", () => {
    const markers = timelineMarkers(finding(), TIMES, DURATION);
    expect(markers).toHaveLength(3);
    expect(markers.map((m) => m.status)).toEqual(["yellow", "red", "yellow"]);
    // rotes Intervall bei Index 2 (t=2) → Fraktion 0.5, Sprung-Zeit 2 s
    const red = markers[1];
    expect(red.midFraction).toBeCloseTo(0.5);
    expect(red.seekTime_s).toBeCloseTo(2);
    expect(red.title).toContain("Kollision");
  });
  it("ohne Dauer/Samples keine Marker (kein Crash)", () => {
    expect(timelineMarkers(finding(), TIMES, 0)).toEqual([]);
    expect(timelineMarkers(finding(), [], DURATION)).toEqual([]);
  });
  it("grüne Intervalle erzeugen keinen Marker", () => {
    const c = finding({ intervals: [{ status: "green", start_index: 0, end_index: 4 }] });
    expect(timelineMarkers(c, TIMES, DURATION)).toEqual([]);
  });
});

describe("Kollisions-Badge je Teil/Player (US 12)", () => {
  it("Status + Kurztext aus dem Gesamtbefund", () => {
    expect(collisionBadge(finding())).toMatchObject({ status: "red", label: "Kollision" });
    expect(collisionBadge(finding({ n_red: 0 }))).toMatchObject({ status: "yellow", label: "eng" });
    expect(collisionBadge(finding({ n_red: 0, n_yellow: 0 }))).toMatchObject({
      status: "green",
      label: "kollisionsfrei",
    });
  });
  it("Titel nennt min. Abstand + vorläufige Grenzwerte", () => {
    const b = collisionBadge(finding())!;
    expect(b.title).toContain("min. Abstand -8 mm");
    expect(b.title).toContain("vorläufige Grenzwerte");
  });
});

describe("Statuszeile (US 25) — Befund verdrängt die ehrliche Zeile", () => {
  it("fasst rot/gelb + min. Abstand zusammen", () => {
    const line = collisionStatusLine(finding());
    expect(line).toContain("Kollision gefunden");
    expect(line).toContain("1 rot");
    expect(line).toContain("2 gelb");
    expect(line).toContain("min. Abstand -8 mm");
  });
  it("nennt Travel nicht lückenlos geprüft, wenn gesetzt", () => {
    expect(collisionStatusLine(finding({ travel_not_continuously_checked: true }))).toContain(
      "Travel nicht lückenlos geprüft",
    );
  });
});

describe("Zerlegung des Befunds (Issue #156) — Zahlen → Meta-Paare, Vorbehalte → Warnungspunkte", () => {
  it("collisionMetaPairs trägt Status-Kopf + alle Zahlen (n_red/n_yellow/n_green/min/mode)", () => {
    const pairs = collisionMetaPairs(finding());
    const byLabel = new Map(pairs.map((p) => [p.label, p.value]));
    expect(byLabel.get("Kollisionskontrolle")).toBe("Kollision gefunden");
    expect(byLabel.get("Kollisions-Samples (rot)")).toBe("1");
    expect(byLabel.get("Warn-Samples (gelb)")).toBe("2");
    expect(byLabel.get("Freie Samples (grün)")).toBe("2");
    expect(byLabel.get("Min. Abstand")).toBe("-8 mm");
    expect(byLabel.get("Prüf-Modus")).toBe("Abschnitt (in place)");
  });

  it("collisionMetaPairs enthält KEINEN 160-Zeichen-Satz — jedes Value ist knapp", () => {
    for (const p of collisionMetaPairs(finding())) {
      expect(p.value.length).toBeLessThan(40);
    }
  });

  it("collisionMetaPairs lässt Min. Abstand weg, wenn null; Modul-Modus spricht am Druckort", () => {
    const pairs = collisionMetaPairs(
      finding({
        min_distance_mm: null,
        config: { safety_distance_mm: 50, freizone_radius_mm: 30, provisional: false, mode: "modul" },
      }),
    );
    const labels = pairs.map((p) => p.label);
    expect(labels).not.toContain("Min. Abstand");
    expect(pairs.find((p) => p.label === "Prüf-Modus")?.value).toBe("Modul (am Druckort)");
  });

  it("collisionCaveats bringt die Vorbehalte als Warnungspunkte (verbatim)", () => {
    expect(collisionCaveats(finding())).toEqual(["Kollisionsbefund: vorläufige Grenzwerte"]);
    expect(
      collisionCaveats(finding({ travel_not_continuously_checked: true })),
    ).toEqual([
      "Kollisionsbefund: vorläufige Grenzwerte",
      "Kollisionsbefund: Travel nicht lückenlos geprüft",
    ]);
  });

  it("collisionCaveats ist leer ohne Vorbehalte (kein Warnungspunkt)", () => {
    const c = finding({
      config: { safety_distance_mm: 50, freizone_radius_mm: 30, provisional: false, mode: "abschnitt" },
    });
    expect(collisionCaveats(c)).toEqual([]);
  });
});

describe("replayStatusLine (Issue #135, Symptom 3) — kein Widerspruch zum Badge", () => {
  it("mit Befund: nennt die Befund-Zusammenfassung statt der ehrlichen Zeile", () => {
    const line = replayStatusLine("Abschnitt s1", finding());
    expect(line).toContain("Abschnitt s1 simuliert — Replay läuft.");
    expect(line).toContain("Kollisionskontrolle: Kollision gefunden");
    expect(line).not.toContain("keine Kollisionsprüfung");
  });
  it("kollisionsfreier Befund liest sich grün", () => {
    const line = replayStatusLine("Abschnitt s1", finding({ n_red: 0, n_yellow: 0 }));
    expect(line).toContain("kollisionsfrei");
    expect(line).not.toContain("keine Kollisionsprüfung");
  });
  it("Altlauf ohne Befund behält die ehrliche Zeile (US 25)", () => {
    expect(replayStatusLine("Abschnitt s1", null)).toBe(
      "Abschnitt s1 simuliert — Replay läuft (keine Kollisionsprüfung).",
    );
  });
});

describe("clearedCollisionFindings — Leeren bei Neu-Zerlegung (Issue #182)", () => {
  it("liefert immer ein leeres Objekt (section_ids können wiederkehren)", () => {
    expect(clearedCollisionFindings()).toEqual({});
  });

  it("ist ein neues Objekt bei jedem Aufruf (kein geteilter, mutierbarer Zustand)", () => {
    const a = clearedCollisionFindings();
    const b = clearedCollisionFindings();
    expect(a).not.toBe(b);
  });
});
