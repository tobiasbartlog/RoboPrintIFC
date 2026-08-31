/**
 * Reine Aktions-/Beschriftungslogik des Simulations-Docks (Issue #108, vormals
 * `druckplan-mode.ts`): welches Teil „Fokus simulieren" betrifft und wie die
 * beiden Simulier-Knöpfe je Zerlegungsart beschriftet sind. DOM-/three.js-frei
 * (wie `focus-store.ts` / `cutplan-state.ts`); das Dock in `ui/simulation.ts`
 * weist die Strings 1:1 zu.
 *
 * Der frühere Modus-Umschalter „Vorbereiten↔Simulieren" (#86) ist mit dem
 * Dock-Umbau (#108) ersatzlos entfallen — Schnittplan-Bearbeitung und Simulation
 * koexistieren ohne Modus; den Veraltet-Schutz leistet allein die Veraltet-
 * Markierung (nur veraltete Teile amber, ADR-017). Deshalb wohnen hier nur noch
 * die Ziel-Auswahl und die artabhängige Beschriftung, keine Modus-Prädikate mehr.
 */

import type { Zerlegungsart } from "./zerlegungsart-state";

/**
 * Welches Teil „Fokus simulieren" (Standard) betrifft (Issue #86/#108): das
 * Fokus-Teil, wenn eines gewählt und noch vorhanden ist. Als abwärtskompatible
 * Erleichterung (US 24) genügt bei **genau einem** Teil dieses eine, auch ohne
 * expliziten Fokus. Sonst `null` (kein eindeutiges Ziel → Knopf gesperrt).
 * Reine Auswahllogik.
 */
export function focusTarget(
  focusedSectionId: string | null,
  sectionIds: readonly string[],
): string | null {
  if (focusedSectionId && sectionIds.includes(focusedSectionId)) return focusedSectionId;
  if (sectionIds.length === 1) return sectionIds[0];
  return null;
}

/* ------------------------------------------------------------------------- *
 * Artabhängige Simulieren-Knöpfe (Druckplan-Neuordnung II S9, Issue #97,
 * PRD #88, ADR-022). Die zwei Simulieren-Knöpfe folgen der Zerlegungsart:
 *  - **Abschnitt** (in place, Einbauort = Druckort): „Fokus-Abschnitt
 *    simulieren" + „Ganze Wand (unten → oben)" mit Umbau-Schritt.
 *  - **Modul** (an der Workstation vorproduziert): „Fokus-Modul simulieren"
 *    (spielt in der Druckort-Ansicht, S8) + „Alle Module" statt „Ganze Wand".
 * Reine Beschriftungs-/Sequenzlogik (DOM-frei); die dünne DOM-Anbindung in
 * `simulation.ts` weist die Strings 1:1 zu.
 * ------------------------------------------------------------------------- */

/** Beschriftung des Standard-„Fokus simulieren"-Knopfs je Zerlegungsart (#97). */
export function focusSimLabel(kind: Zerlegungsart): string {
  return kind === "modul" ? "Fokus-Modul simulieren" : "Fokus-Abschnitt simulieren";
}

/** Tooltip des Standard-„Fokus simulieren"-Knopfs je Zerlegungsart (#97). */
export function focusSimTitle(kind: Zerlegungsart): string {
  return kind === "modul"
    ? "Fokus-Modul slicen + als vollen Arm-Lauf am Druckort abspielen (#97)"
    : "Fokus-Abschnitt slicen + als vollen Arm-Lauf abspielen (#26)";
}

/** Beschriftung des Sequenz-Knopfs je Zerlegungsart — „Ganze Wand" ↔ „Alle Module" (#97). */
export function sequenceSimLabel(kind: Zerlegungsart): string {
  return kind === "modul" ? "Alle Module" : "Ganze Wand (unten → oben)";
}

/** Tooltip des Sequenz-Knopfs je Zerlegungsart (#97). */
export function sequenceSimTitle(kind: Zerlegungsart): string {
  return kind === "modul"
    ? "Alle Module in Montagereihenfolge am Druckort abspielen (unten → oben, links → rechts, #97)"
    : "Alle Abschnitte in Druckreihenfolge abspielen (unten → oben, Sequenz #27)";
}

/**
 * Hinweis unter dem „Fokus simulieren"-Knopf je Art und Zielzustand (#86/#97).
 * `focusId` ist das eindeutige Simulier-Ziel (siehe {@link focusTarget}), null
 * heißt „kein eindeutiges Ziel".
 */
export function focusSimHint(
  kind: Zerlegungsart,
  focusId: string | null,
  sectionCount: number,
): string {
  const teil = kind === "modul" ? "Modul" : "Abschnitt";
  if (focusId === null) {
    if (sectionCount === 0) return kind === "modul" ? "Noch keine Module." : "Noch keine Abschnitte.";
    return `Kein ${teil} im Fokus — im 3D-Feld oder in der Liste ${
      kind === "modul" ? "eines" : "einen"
    } wählen.`;
  }
  return kind === "modul"
    ? `Simuliert Modul „${focusId}“ und spielt den vollen Arm-Lauf am Druckort ab.`
    : `Simuliert Abschnitt „${focusId}“ und spielt den vollen Arm-Lauf ab.`;
}

/**
 * Hinweis unter dem Sequenz-Knopf je Art und Bereitschaft (#86/#97). `ready` =
 * jedes Teil hat einen Lauf; `missing` von `total` sind noch nicht simuliert.
 */
export function sequenceSimHint(
  kind: Zerlegungsart,
  ready: boolean,
  total: number,
  missing: number,
): string {
  if (ready) {
    return kind === "modul"
      ? "Spielt alle Module in Montagereihenfolge (unten → oben, links → rechts) am " +
          "Druckort — das Modul auf der Arbeitsfläche wird je Schritt durchgetauscht."
      : "Spielt alle Abschnitte in Druckreihenfolge (unten → oben) — mit " +
          "sichtbarem Umbau-Schritt zwischen den Abschnitten; Gedrucktes bleibt stehen.";
  }
  if (total === 0) return kind === "modul" ? "Noch keine Module." : "Noch keine Abschnitte.";
  const teile = kind === "modul" ? "Modulen" : "Abschnitten";
  return `Noch nicht abspielbar: ${missing} von ${total} ${teile} sind noch nicht simuliert.`;
}

/**
 * true, wenn die Simulation dieser Art **am Druckort** (Workstation-Szene, S8)
 * spielt — nur bei Modulen; Abschnitte werden in place gedruckt (Einbauort =
 * Druckort), sie spielen im geteilten 3D-Feld wie bisher (#26/#27). Reine
 * Weichenlogik; die Venue-Umschaltung erledigt `main.ts`.
 */
export function simPlaysAtDruckort(kind: Zerlegungsart): boolean {
  return kind === "modul";
}
