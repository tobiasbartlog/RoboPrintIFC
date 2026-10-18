/**
 * Geteiltes Rubriken-Modul — reiner Zustand (Issue #89, PRD #88). Aus dem
 * Bibliothek-Muster (`library-rubrics.ts`, #75) herausgezogen, damit sowohl die
 * Bibliothek (Roboter/Endeffektor/Workstation) als auch der Druckplan-Aside
 * (Zerlegung & Platzierung / Slicing) dieselbe Umschalt-Logik teilen.
 *
 * DOM-frei und vitest-getestet (wie `focus-store.ts` / `cutplan-state.ts`): hier
 * liegt nur, *welche* Rubrik aktiv ist; das eigentliche Ein-/Ausblenden erledigt
 * die dünne DOM-Klasse in `rubrics.ts` AUSSCHLIESSLICH über das `.hidden`-Attribut
 * (globales `[hidden]{display:none!important}` schlägt jedes `display:flex` —
 * schützt vor dem toten-Reiter-Bug #56).
 */

export class RubricsState<Id extends string> {
  private readonly _ids: readonly Id[];
  private _active: Id;

  constructor(ids: readonly Id[], initial: Id) {
    if (ids.length === 0) throw new Error("RubricsState braucht mindestens eine Rubrik.");
    if (!ids.includes(initial)) throw new Error(`Unbekannte Start-Rubrik „${initial}".`);
    this._ids = [...ids];
    this._active = initial;
  }

  /** Die konfigurierten Rubriken in Reihenfolge. */
  get ids(): readonly Id[] {
    return this._ids;
  }

  /** Die aktuell aktive Rubrik. */
  get active(): Id {
    return this._active;
  }

  /** true, wenn `id` die aktive Rubrik ist. */
  isActive(id: Id): boolean {
    return id === this._active;
  }

  /**
   * Aktiviert eine Rubrik. Wirft bei unbekannter Id. Liefert `true`, wenn sich
   * die aktive Rubrik dadurch geändert hat (für sparsame Re-Render-Entscheidungen).
   */
  setActive(id: Id): boolean {
    if (!this._ids.includes(id)) throw new Error(`Unbekannte Rubrik „${id}".`);
    const changed = id !== this._active;
    this._active = id;
    return changed;
  }
}
