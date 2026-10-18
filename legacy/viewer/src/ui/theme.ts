/**
 * Hell/Dunkel-Theme-Umschalter (UI-Redesign Scheibe 1, Issue #101) — reine,
 * DOM- und localStorage-freie Zustandslogik. Wie die anderen `*-state.ts`
 * (z. B. `collapsible-state.ts`) ist der Zustand ein einzelner Wert und eine
 * Ansicht (`themeView`) leitet daraus die Größen ab, die die Verdrahtung (in
 * `main.ts`) am DOM setzt: das `data-theme`-Attribut am `<html>`, der in
 * localStorage abgelegte Wert und die Beschriftung des ◐-Umschalters.
 *
 * Dunkel ist der Default (entspricht dem `:root`-Block der Token; nur
 * `[data-theme="light"]` überschreibt die Palette). Getrennt von DOM getestet
 * (`theme.test.ts`), damit die Umschalt-/Persistenz-Logik ohne Browser prüfbar
 * bleibt.
 */

/** Die beiden Themes des Viewers. Dunkel = Default. */
export type Theme = "dark" | "light";

/** Default-Theme: dunkel (entspricht dem `:root`-Token-Block ohne data-theme). */
export const DEFAULT_THEME: Theme = "dark";

/** localStorage-Schlüssel, unter dem die Theme-Wahl persistiert wird. */
export const THEME_STORAGE_KEY = "fgc-theme";

/** Der reine Theme-Zustand: welches Theme gerade aktiv ist. */
export interface ThemeState {
  theme: Theme;
}

/** Startzustand (Default: dunkel). */
export function themeState(theme: Theme = DEFAULT_THEME): ThemeState {
  return { theme };
}

/**
 * Normalisiert einen (evtl. `null`/unbekannten) gespeicherten Wert zu einem
 * gültigen Theme — alles außer „light"/„dark" fällt auf den Default zurück.
 */
export function normalizeTheme(value: string | null | undefined): Theme {
  return value === "light" || value === "dark" ? value : DEFAULT_THEME;
}

/** Rehydriert den Zustand aus einem gespeicherten Wert (localStorage). */
export function themeFromStorage(value: string | null | undefined): ThemeState {
  return { theme: normalizeTheme(value) };
}

/** Kippt zwischen hell und dunkel (Klick auf den ◐-Umschalter). */
export function toggleTheme(state: ThemeState): ThemeState {
  return { theme: state.theme === "light" ? "dark" : "light" };
}

/** Setzt das Theme explizit. */
export function setTheme(theme: Theme): ThemeState {
  return { theme };
}

/** Die aus dem Zustand abgeleiteten DOM-/Persistenz-Größen. */
export interface ThemeView {
  /** Wert für das `data-theme`-Attribut am `<html>` (steuert die Token-Palette). */
  themeAttr: Theme;
  /** Wert, der in localStorage abgelegt wird. */
  storageValue: Theme;
  /** true, wenn das helle Theme aktiv ist (z. B. `aria-pressed` des ◐-Toggles). */
  isLight: boolean;
  /** Titel/Tooltip des Umschalters — nennt das Ziel des nächsten Klicks. */
  toggleTitle: string;
}

/**
 * Leitet die DOM-/Persistenz-Größen aus dem Zustand ab. Das `data-theme` wird
 * stets explizit gesetzt (auch „dark"); nur `[data-theme="light"]` trägt eine
 * abweichende Palette, „dark" ist der `:root`-Default.
 */
export function themeView(state: ThemeState): ThemeView {
  const isLight = state.theme === "light";
  return {
    themeAttr: state.theme,
    storageValue: state.theme,
    isLight,
    toggleTitle: isLight ? "Zu dunklem Design wechseln" : "Zu hellem Design wechseln",
  };
}
