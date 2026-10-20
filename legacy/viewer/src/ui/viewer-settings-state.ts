/**
 * Viewer-Einstellungen am 3D-Feld — reine, DOM-/three.js-freie Ableitung.
 *
 * Ab dem Reiter **Zerlegung** fokussiert das geteilte 3D-Feld die gewählte Wand:
 * die übrigen Wände der Modellübersicht und der Gebäudekontext (context.json)
 * treten zurück, damit Schnitte/Abschnitte/Platzierung ungestört lesbar sind.
 * Ein schwebendes Einstellungs-Menü (⚙) blendet das restliche Gebäude bei Bedarf
 * wieder als **Kontext** ein.
 *
 * Diese Datei hält nur die reine Logik (welche Reiter fokussieren, was der
 * Kontext-Schalter sichtbar macht) — getrennt getestet wie die übrigen
 * `*-state.ts`. Das DOM-Verdrahten liegt in `ui/viewer-settings.ts`, die
 * three.js-Wirkung in `main.ts`/`render/model.ts`.
 */

import type { TabId } from "./tabs";

/**
 * Reiter, in denen der Viewer auf die gewählte Wand fokussiert („ab Zerlegung"):
 * Zerlegung, Slicing (interner Schlüssel `druckplan`) und Export. In Projekt
 * (Modellübersicht mit Wandauswahl) und Roboter bleibt die Gesamtansicht.
 */
export const FOCUS_TABS: readonly TabId[] = ["zerlegung", "druckplan", "export"];

/** Ob dieser Reiter die gewählte Wand fokussiert (ab Zerlegung). */
export function isFocusTab(tab: TabId): boolean {
  return FOCUS_TABS.includes(tab);
}

/** Der reine Zustand des Einstellungs-Menüs. */
export interface ViewerSettingsState {
  /**
   * „Gebäude/Kontext einblenden" — Standard aus: im Fokus-Modus zeigt das Feld
   * nur die gewählte Wand. Eingeschaltet kommen die übrigen Wände (gedimmt) und
   * der Gebäudekontext-Geist zurück.
   */
  contextVisible: boolean;
}

/** Startzustand (Default: Kontext aus — nur die gewählte Wand). */
export function viewerSettingsState(contextVisible = false): ViewerSettingsState {
  return { contextVisible };
}

/** Was das geteilte 3D-Feld je nach Reiter/Wahl/Schalter zeigen soll. */
export interface WallFocusVisibility {
  /** true → nur die gewählte Wand; die übrigen Wände werden ausgeblendet. */
  isolateWall: boolean;
  /** true → die übrigen Wände der Modellübersicht sind sichtbar (als Kontext). */
  showOtherWalls: boolean;
  /** true → der Gebäudekontext-Geist (context.json) ist sichtbar. */
  showContextGhost: boolean;
}

/**
 * Leitet ab, was das geteilte 3D-Feld zeigen soll.
 *
 * - Ohne Fokus-Reiter **oder** ohne gewählte Wand: Gesamtansicht — alle Wände
 *   sichtbar; der Gebäudekontext folgt dem übergebenen `contextVisible`
 *   (in der Modellübersicht steuert ihn weiterhin das Projekt-Panel).
 * - Fokus-Reiter **mit** gewählter Wand: standardmäßig nur diese Wand
 *   (`isolateWall`); erst der Kontext-Schalter blendet die übrigen Wände und den
 *   Gebäudekontext-Geist wieder ein.
 */
export function wallFocusVisibility(
  tab: TabId,
  hasSelectedWall: boolean,
  contextVisible: boolean,
): WallFocusVisibility {
  const focus = isFocusTab(tab) && hasSelectedWall;
  if (!focus) {
    return {
      isolateWall: false,
      showOtherWalls: true,
      showContextGhost: contextVisible,
    };
  }
  return {
    isolateWall: !contextVisible,
    showOtherWalls: contextVisible,
    showContextGhost: contextVisible,
  };
}

/**
 * Sichtbarkeit der beiden benannten ⚙-Sektionen (Issue #159).
 *
 * Das ⚙-Menü führt zwei Sektionen mit getrennter Sichtbarkeit:
 * - **Modellansicht** (`context`/`basis`/`bemassung`) — an den Wand-Fokus
 *   gebunden: sichtbar nur in den Fokus-Reitern (`isFocusTab`).
 * - **Replay-Bühne** (`show-arm`/`grow-strand`/`druckstand`/`abstandszahl`) —
 *   sichtbar, **wo eine Bühne läuft**: in den Fokus-Reitern immer, im Reiter
 *   Projekt zusätzlich, sobald dort ein Lauf offen ist. `isFocusTab` ist hier
 *   der falsche Türsteher (fragt „Wand-Fokus", nicht „läuft ein Replay").
 *
 * In Roboter/Bibliothek (kein Fokus, kein Projekt-Lauf) bleiben beide verborgen.
 */
export interface ViewerSettingsSectionVisibility {
  /** „Modellansicht" — context/basis/bemassung. */
  modelView: boolean;
  /** „Replay-Bühne" — show-arm/grow-strand/druckstand/abstandszahl. */
  replayStage: boolean;
}

/** Leitet die Sichtbarkeit der zwei ⚙-Sektionen aus Reiter × Lauf-offen ab. */
export function viewerSettingsSections(
  tab: TabId,
  replayOpen: boolean,
): ViewerSettingsSectionVisibility {
  const focus = isFocusTab(tab);
  return {
    modelView: focus,
    replayStage: focus || (tab === "projekt" && replayOpen),
  };
}

/** Ob das ⚙-Menü überhaupt sichtbar ist — sichtbar ⇔ mindestens eine Sektion. */
export function viewerSettingsMenuVisible(s: ViewerSettingsSectionVisibility): boolean {
  return s.modelView || s.replayStage;
}
