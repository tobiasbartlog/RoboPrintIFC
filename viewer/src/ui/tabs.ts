/**
 * Reiter des GUI-Prozesses (viewer/CONTEXT.md): vier Prozess-Reiter plus die
 * Bibliothek. Reiter sind *Navigation, kein Zwangspfad* — jeder Reiter ist von
 * jedem aus erreichbar; es gibt kein Gating (ADR-016, Grill-Session 2026-07-04).
 *
 * Seit Issue #86 (PRD B/#70) ist der frühere Reiter **Simulation** in den Reiter
 * **Druckplan** aufgegangen (Modus-Fusion „Vorbereiten↔Simulieren"): Planen und
 * Sehen liegen an einem Ort, der Trajektorien-Abspieler wohnt im Druckplan.
 *
 * Scheibe 4 (#106) spaltet den Druckplan auf: der neue Reiter **Zerlegung**
 * (Platzierung/Zerlegung als Inspector mit Accordions) steht vor dem Reiter
 * **Druckplan**. Scheibe 5 (#107) löst diesen zum eigenständigen Prozess-Schritt
 * **Slicing** (Gilt-für-Kopf + Accordions Prozessparameter/Fortgeschritten/
 * Advisor + Sticky-Footer) auf; die Rubriken-Navigation `druckplan-rubrics` (#89)
 * entfällt. Der interne Reiter-Schlüssel bleibt `druckplan` (data-panel), der
 * Stepper beschriftet den Schritt als „Slicing" (stepper-state.ts).
 *
 * Diese Datei hält die reine, three.js-freie Zustandslogik; das DOM-Verdrahten
 * liegt in ui/shell.ts.
 */

/** Die fünf Prozess-Reiter plus die Bibliothek (Stammdaten außerhalb des Prozesses). */
export const TAB_IDS = [
  "projekt",
  "roboter",
  "zerlegung",
  "druckplan",
  "export",
  "bibliothek",
] as const;

export type TabId = (typeof TAB_IDS)[number];

/** Die fünf Prozess-Reiter (ohne Bibliothek). */
export const PROCESS_TABS: TabId[] = ["projekt", "roboter", "zerlegung", "druckplan", "export"];

/**
 * Ob von `from` nach `to` navigiert werden darf. Immer `true`: Reiter sind
 * Navigation, kein Zwangspfad — Zurückspringen ist stets erlaubt, und kein
 * Reiter sperrt einen anderen (viewer/CONTEXT.md).
 */
export function canNavigate(_from: TabId, _to: TabId): boolean {
  return true;
}

/** Menschliche Beschriftung eines Reiters für die Tab-Leiste. */
export function tabLabel(id: TabId): string {
  switch (id) {
    case "projekt":
      return "Projekt";
    case "roboter":
      return "Roboter";
    case "zerlegung":
      return "Zerlegung";
    case "druckplan":
      return "Druckplan";
    case "export":
      return "Export";
    case "bibliothek":
      return "Bibliothek";
  }
}
