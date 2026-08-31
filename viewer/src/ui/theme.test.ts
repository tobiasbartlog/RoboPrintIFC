import { describe, expect, it } from "vitest";

import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  type ThemeState,
  normalizeTheme,
  setTheme,
  themeFromStorage,
  themeState,
  themeView,
  toggleTheme,
} from "./theme";

describe("theme-state (UI-Redesign Scheibe 1, Issue #101)", () => {
  it("Default ist dunkel", () => {
    expect(DEFAULT_THEME).toBe("dark");
    expect(themeState()).toEqual({ theme: "dark" });
  });

  it("startet auf Wunsch hell", () => {
    expect(themeState("light")).toEqual({ theme: "light" });
  });

  it("persistiert unter stabilem Schlüssel", () => {
    expect(THEME_STORAGE_KEY).toBe("fgc-theme");
  });

  it("normalizeTheme akzeptiert gültige Werte", () => {
    expect(normalizeTheme("light")).toBe("light");
    expect(normalizeTheme("dark")).toBe("dark");
  });

  it("normalizeTheme fällt bei null/unbekannt auf den Default zurück", () => {
    expect(normalizeTheme(null)).toBe("dark");
    expect(normalizeTheme(undefined)).toBe("dark");
    expect(normalizeTheme("")).toBe("dark");
    expect(normalizeTheme("blau")).toBe("dark");
  });

  it("themeFromStorage rehydriert den Zustand (Reload überlebt)", () => {
    expect(themeFromStorage("light")).toEqual({ theme: "light" });
    expect(themeFromStorage(null)).toEqual({ theme: "dark" });
    expect(themeFromStorage("murks")).toEqual({ theme: "dark" });
  });

  it("toggle kippt hell↔dunkel hin und zurück", () => {
    const dark = themeState();
    const light = toggleTheme(dark);
    expect(light).toEqual({ theme: "light" });
    expect(toggleTheme(light)).toEqual({ theme: "dark" });
  });

  it("toggle mutiert den Eingangszustand nicht (rein)", () => {
    const dark: ThemeState = themeState();
    toggleTheme(dark);
    expect(dark).toEqual({ theme: "dark" });
  });

  it("setTheme setzt explizit", () => {
    expect(setTheme("light")).toEqual({ theme: "light" });
    expect(setTheme("dark")).toEqual({ theme: "dark" });
  });

  it("view (dunkel): data-theme=dark, kein isLight, Titel nennt das helle Ziel", () => {
    const view = themeView(themeState("dark"));
    expect(view.themeAttr).toBe("dark");
    expect(view.storageValue).toBe("dark");
    expect(view.isLight).toBe(false);
    expect(view.toggleTitle).toBe("Zu hellem Design wechseln");
  });

  it("view (hell): data-theme=light, isLight, Titel nennt das dunkle Ziel", () => {
    const view = themeView(themeState("light"));
    expect(view.themeAttr).toBe("light");
    expect(view.storageValue).toBe("light");
    expect(view.isLight).toBe(true);
    expect(view.toggleTitle).toBe("Zu dunklem Design wechseln");
  });
});
