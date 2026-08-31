/**
 * Rubriken-Umschaltung der Bibliothek (Issue #75): Roboter / Endeffektor /
 * Workstation. Drei Sichten im selben Reiter-Panel; umgeschaltet wird
 * AUSSCHLIESSLICH über das `.hidden`-Attribut (globales
 * `[hidden]{display:none!important}` schlägt jedes `display:flex`) — nie über
 * `style.display`, sonst kehrt der tote-Reiter-Bug wieder (Lehre aus #56).
 *
 * Seit #89 ein dünner Aufsatz auf das geteilte Rubriken-Modul (`rubrics.ts` +
 * reiner `rubrics-state.ts`); nur die Bibliothek-spezifischen Ids/Startsicht
 * leben hier, das Verhalten bleibt byte-gleich (ADR-007).
 */

import { Rubrics } from "./rubrics";

export type RubricId = "roboter" | "endeffektor" | "workstation";

export const RUBRIC_IDS: readonly RubricId[] = ["roboter", "endeffektor", "workstation"];

export interface LibraryRubricsCallbacks {
  /** Nach jedem Rubrikwechsel — main.ts frischt die gewählte Galerie auf. */
  onRubricChanged?(id: RubricId): void;
}

export class LibraryRubrics {
  private readonly rubrics: Rubrics<RubricId>;

  constructor(callbacks: LibraryRubricsCallbacks = {}) {
    this.rubrics = new Rubrics<RubricId>({
      ids: RUBRIC_IDS,
      initial: "endeffektor",
      buttonId: (id) => `lib-rubric-btn-${id}`,
      viewId: (id) => `lib-rubric-${id}`,
      onRubricChanged: callbacks.onRubricChanged,
    });
  }

  get active(): RubricId {
    return this.rubrics.active;
  }

  /** Aktiviert eine Rubrik: genau ihre Sicht sichtbar (`.hidden`), Rest aus. */
  setActive(id: RubricId): void {
    this.rubrics.setActive(id);
  }
}
