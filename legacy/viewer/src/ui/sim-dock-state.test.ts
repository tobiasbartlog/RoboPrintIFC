/**
 * Modus-Wahl der Player-Leiste (Issue #154): reine Funktion, DOM-frei. Prüft, dass
 * Start- und Replay-Modus einander ausschließen (die Startknöpfe verschwinden im
 * Replay — Ende der Überlagerung, #148) und dass die zwei Hinweise nur im
 * Start-Modus UND bei eigener Bedingung stehen.
 */

import { describe, expect, it } from "vitest";

import { simDockHidden, simDockMode, type SimDockState } from "./sim-dock-state";

const start: SimDockState = { replaying: false, apiAvailable: true, hasPrecondition: false };
const replay: SimDockState = { ...start, replaying: true };

describe("simDockMode", () => {
  it("ist Start-Modus, solange kein Replay läuft", () => {
    expect(simDockMode(start)).toBe("start");
  });

  it("ist Replay-Modus, sobald ein Lauf spielt", () => {
    expect(simDockMode(replay)).toBe("replay");
  });
});

describe("simDockHidden — Start-Modus (kein Replay)", () => {
  it("zeigt die Startknöpfe, versteckt den Player", () => {
    const h = simDockHidden(start);
    expect(h.focusBtn).toBe(false);
    expect(h.sequenceBtn).toBe(false);
    expect(h.player).toBe(true);
  });

  it("versteckt das Geschwindigkeits-Bedienelement (nur im Replay, #155)", () => {
    expect(simDockHidden(start).speed).toBe(true);
  });

  it("versteckt die API-Warnung, solange die API erreichbar ist", () => {
    expect(simDockHidden(start).apiWarning).toBe(true);
  });

  it("zeigt die API-Warnung, wenn die API weg ist", () => {
    expect(simDockHidden({ ...start, apiAvailable: false }).apiWarning).toBe(false);
  });

  it("zeigt die Vorbedingung nur bei anliegendem Hinweis", () => {
    expect(simDockHidden(start).precondition).toBe(true);
    expect(simDockHidden({ ...start, hasPrecondition: true }).precondition).toBe(false);
  });
});

describe("simDockHidden — Replay-Modus (Startknöpfe verschwinden, #154)", () => {
  it("versteckt beide Startknöpfe", () => {
    const h = simDockHidden(replay);
    expect(h.focusBtn).toBe(true);
    expect(h.sequenceBtn).toBe(true);
  });

  it("zeigt den Player", () => {
    expect(simDockHidden(replay).player).toBe(false);
  });

  it("zeigt das Geschwindigkeits-Bedienelement (#155)", () => {
    expect(simDockHidden(replay).speed).toBe(false);
  });

  it("versteckt die Hinweise IMMER — auch wenn API weg / Vorbedingung gesetzt wären", () => {
    const h = simDockHidden({ replaying: true, apiAvailable: false, hasPrecondition: true });
    expect(h.apiWarning).toBe(true);
    expect(h.precondition).toBe(true);
  });
});

describe("simDockHidden — Start und Replay schließen einander aus (keine Überlagerung)", () => {
  it("Player und Startknöpfe sind nie gleichzeitig sichtbar", () => {
    for (const s of [start, replay, { ...start, replaying: true, apiAvailable: false }]) {
      const h = simDockHidden(s);
      const playerVisible = !h.player;
      const focusVisible = !h.focusBtn;
      expect(playerVisible && focusVisible).toBe(false);
    }
  });
});
