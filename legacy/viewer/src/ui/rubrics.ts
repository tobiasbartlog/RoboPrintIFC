/**
 * Geteiltes Rubriken-Modul — dünne DOM-Klasse (Issue #89, PRD #88). Verheiratet
 * den reinen `RubricsState` mit dem DOM: je Rubrik ein Button und eine Sicht,
 * umgeschaltet wird AUSSCHLIESSLICH über das `.hidden`-Attribut (globales
 * `[hidden]{display:none!important}` schlägt jedes `display:flex`) — nie über
 * `style.display`, sonst kehrt der tote-Reiter-Bug wieder (Lehre aus #56).
 *
 * Generisch über die Rubrik-Ids und die Element-Id-Bildung, damit Bibliothek
 * (`library-rubrics.ts`) und Druckplan-Aside dieselbe Klasse nutzen. Reines
 * Sicht-Toggling ohne Fachzustand (ADR-007): welche Rubrik gerade aktiv ist,
 * meldet der optionale Callback.
 */

import { RubricsState } from "./rubrics-state";

export interface RubricsOptions<Id extends string> {
  /** Die Rubrik-Ids in Reihenfolge. */
  readonly ids: readonly Id[];
  /** Anfangs aktive Rubrik (muss zum initial sichtbaren `.hidden`-Zustand passen). */
  readonly initial: Id;
  /** Element-Id des Umschalt-Buttons je Rubrik. */
  buttonId(id: Id): string;
  /** Element-Id der Sicht je Rubrik. */
  viewId(id: Id): string;
  /** Nach jedem Rubrikwechsel (auch beim erneuten Klick auf die aktive). */
  onRubricChanged?(id: Id): void;
}

export class Rubrics<Id extends string> {
  private readonly state: RubricsState<Id>;
  private readonly buttons = new Map<Id, HTMLButtonElement>();
  private readonly views = new Map<Id, HTMLElement>();

  constructor(private readonly options: RubricsOptions<Id>) {
    this.state = new RubricsState(options.ids, options.initial);
    for (const id of options.ids) {
      const btn = document.getElementById(options.buttonId(id)) as HTMLButtonElement | null;
      const view = document.getElementById(options.viewId(id));
      if (!btn || !view) throw new Error(`Rubrik „${id}" fehlt in index.html`);
      this.buttons.set(id, btn);
      this.views.set(id, view);
      btn.addEventListener("click", () => this.setActive(id));
    }
  }

  /** Die aktuell aktive Rubrik. */
  get active(): Id {
    return this.state.active;
  }

  /** Aktiviert eine Rubrik: genau ihre Sicht sichtbar (`.hidden`), Rest aus. */
  setActive(id: Id): void {
    this.state.setActive(id);
    for (const rid of this.state.ids) {
      const view = this.views.get(rid);
      const btn = this.buttons.get(rid);
      if (view) view.hidden = !this.state.isActive(rid);
      if (btn) btn.classList.toggle("active", this.state.isActive(rid));
    }
    this.options.onRubricChanged?.(id);
  }
}
