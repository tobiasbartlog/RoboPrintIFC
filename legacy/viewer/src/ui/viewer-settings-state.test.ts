import { describe, expect, it } from "vitest";

import {
  FOCUS_TABS,
  isFocusTab,
  viewerSettingsMenuVisible,
  viewerSettingsSections,
  viewerSettingsState,
  wallFocusVisibility,
} from "./viewer-settings-state";

describe("viewer-settings-state — Wand-Fokus ab Zerlegung", () => {
  it("Default: Kontext aus (nur die gewählte Wand)", () => {
    expect(viewerSettingsState()).toEqual({ contextVisible: false });
    expect(viewerSettingsState(true)).toEqual({ contextVisible: true });
  });

  it("Fokus-Reiter sind Zerlegung, Druckplan (Slicing) und Export", () => {
    expect([...FOCUS_TABS]).toEqual(["zerlegung", "druckplan", "export"]);
    expect(isFocusTab("zerlegung")).toBe(true);
    expect(isFocusTab("druckplan")).toBe(true);
    expect(isFocusTab("export")).toBe(true);
    expect(isFocusTab("projekt")).toBe(false);
    expect(isFocusTab("roboter")).toBe(false);
    expect(isFocusTab("bibliothek")).toBe(false);
  });

  it("Fokus-Reiter + gewählte Wand + Kontext aus → nur die Wand", () => {
    expect(wallFocusVisibility("zerlegung", true, false)).toEqual({
      isolateWall: true,
      showOtherWalls: false,
      showContextGhost: false,
    });
  });

  it("Fokus-Reiter + gewählte Wand + Kontext an → Gebäude + Kontext-Geist blass dazu", () => {
    expect(wallFocusVisibility("druckplan", true, true)).toEqual({
      isolateWall: false,
      showOtherWalls: true,
      showContextGhost: true,
    });
  });

  it("Fokus-Reiter ohne gewählte Wand → Gesamtansicht (kein Isolieren)", () => {
    expect(wallFocusVisibility("zerlegung", false, false)).toEqual({
      isolateWall: false,
      showOtherWalls: true,
      showContextGhost: false,
    });
  });

  it("Nicht-Fokus-Reiter (Modellübersicht) → alle Wände, Kontext folgt dem Schalter", () => {
    expect(wallFocusVisibility("projekt", true, false)).toEqual({
      isolateWall: false,
      showOtherWalls: true,
      showContextGhost: false,
    });
    expect(wallFocusVisibility("projekt", true, true).showContextGhost).toBe(true);
  });
});

describe("viewer-settings-state — zwei ⚙-Sektionen je Reiter × Lauf-offen (Issue #159)", () => {
  it("Fokus-Reiter (Zerlegung/Slicing/Export): beide Sektionen sichtbar, egal ob Lauf offen", () => {
    for (const tab of ["zerlegung", "druckplan", "export"] as const) {
      expect(viewerSettingsSections(tab, false)).toEqual({ modelView: true, replayStage: true });
      expect(viewerSettingsSections(tab, true)).toEqual({ modelView: true, replayStage: true });
    }
  });

  it("Reiter Projekt MIT offenem Lauf: nur die Replay-Bühne (Modellansicht bleibt aus)", () => {
    expect(viewerSettingsSections("projekt", true)).toEqual({
      modelView: false,
      replayStage: true,
    });
  });

  it("Reiter Projekt OHNE Lauf: beide Sektionen aus (Menü verborgen)", () => {
    const s = viewerSettingsSections("projekt", false);
    expect(s).toEqual({ modelView: false, replayStage: false });
    expect(viewerSettingsMenuVisible(s)).toBe(false);
  });

  it("Reiter Roboter/Bibliothek: beide aus, auch wenn (irgendwo) ein Lauf offen wäre", () => {
    for (const tab of ["roboter", "bibliothek"] as const) {
      expect(viewerSettingsSections(tab, true)).toEqual({
        modelView: false,
        replayStage: false,
      });
      expect(viewerSettingsMenuVisible(viewerSettingsSections(tab, true))).toBe(false);
    }
  });

  it("Menü sichtbar ⇔ mindestens eine Sektion sichtbar", () => {
    expect(viewerSettingsMenuVisible({ modelView: false, replayStage: false })).toBe(false);
    expect(viewerSettingsMenuVisible({ modelView: true, replayStage: false })).toBe(true);
    expect(viewerSettingsMenuVisible({ modelView: false, replayStage: true })).toBe(true);
    expect(viewerSettingsMenuVisible({ modelView: true, replayStage: true })).toBe(true);
  });
});
