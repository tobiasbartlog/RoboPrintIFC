/**
 * Szenenmodus des geteilten Hauptsichtfelds (Issue #30/#31) — reine Zuordnung
 * Reiter → Inhalt: die Prozess-Reiter zeigen die Modellübersicht (`world`),
 * der Reiter Roboter die Roboter-Vorschau (Kapsel-Arm in Home-Pose), die
 * Bibliothek hat ihre eigene Konfigurator-Szene (`#cfg-viewport`, Issue #28).
 */

import type { TabId } from "./tabs";

export type SceneMode = "world" | "robot-vorschau" | "bibliothek";

export function sceneModeForTab(tab: TabId): SceneMode {
  if (tab === "roboter") return "robot-vorschau";
  if (tab === "bibliothek") return "bibliothek";
  return "world";
}
