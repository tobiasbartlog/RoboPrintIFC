/**
 * Gilt-für-Umschalter Global↔Teil — dünne DOM-Anbindung (Issue #92, PRD #88).
 *
 * Verheiratet die reine Stellungs-Logik (`scope-state.ts`) mit dem Radio-Paar
 * oben im Druckplan-Aside: sichtbar **nur bei gewähltem Teil** (Fokus, #84/#91),
 * umgeschaltet wird der Geltungsbereich der Slicing-Formulare. Sichtbarkeit
 * AUSSCHLIESSLICH über `.hidden` (Lehre aus #56). Kein Fachzustand (ADR-007):
 * welche Formulare/Gruppen der Wechsel betrifft, entscheiden die Abnehmer
 * (`process-params.ts` Formulare, `druckplan.ts` Ausgrau-Matrix) über den
 * Callback.
 *
 * Seit Issue #196 hält der Umschalter KEINE Fokus-Kopie mehr: das gewählte
 * Teil kommt aus dem einen Halter (`focus-store.ts`, injiziert als Reader);
 * hier lebt nur die **Stellung** des Radio-Paars. Der Fokus-Abgleich
 * (`onFocusChanged`) ist ein Mitglied der in main.ts registrierten
 * Wirkungs-Kaskade (FOCUS_EFFECT_ORDER); `onScopeChanged` feuert nur noch
 * für echte Radio-Klicks — die frühere Zwei-Hop-Weiterleitung des Fokus an
 * die Slicing-Formulare ist ein eigenes Kaskaden-Mitglied.
 */

import type { FocusReader } from "./focus-store";
import {
  type Scope,
  effectiveScope,
  reconcileScopeChoice,
  selectScopeChoice,
  switchVisible,
} from "./scope-state";

export interface ScopeSwitchCallbacks {
  /**
   * Feuert bei einer Radio-Umschaltung mit geändertem **wirksamem**
   * Geltungsbereich (Global↔Teil). Fokus-getriebene Wechsel laufen NICHT mehr
   * hierüber (Issue #196) — sie sind eigene Mitglieder der Fokus-Kaskade.
   */
  onScopeChanged(scope: Scope, sectionId: string | null): void;
}

export class ScopeSwitch {
  private readonly root = byId<HTMLElement>("scope-switch");
  private readonly globalRadio = byId<HTMLInputElement>("scope-global");
  private readonly teilRadio = byId<HTMLInputElement>("scope-teil");
  private readonly teilName = byId<HTMLElement>("scope-teil-name");
  private readonly hint = byId<HTMLElement>("scope-hint");

  /** Die Stellung des Radio-Paars — wirksam nur mit fokussiertem Teil. */
  private _choice: Scope = "global";

  constructor(
    private readonly focus: FocusReader,
    private readonly callbacks: ScopeSwitchCallbacks,
  ) {
    this.globalRadio.addEventListener("change", () => this._select("global"));
    this.teilRadio.addEventListener("change", () => this._select("teil"));
    this._render();
  }

  /**
   * Fokus-Kaskaden-Mitglied `reconcileScopeSwitch` (Issue #196): Umschalter
   * ein-/ausblenden und die Stellung abgleichen — Abwahl fällt auf Global
   * zurück, ein Teil-Wechsel im Teil-Modus zielt (über den Store) auf das neue
   * Teil. `partName` beschriftet die Teil-Option.
   */
  onFocusChanged(partName: string | null): void {
    this._choice = reconcileScopeChoice(this._choice, this.focus.get());
    this.teilName.textContent = partName ?? "Teil";
    this._render();
  }

  /** Der wirksame Geltungsbereich (ohne fokussiertes Teil immer `global`). */
  get scope(): Scope {
    return effectiveScope(this._choice, this.focus.get());
  }

  /** Das gewählte Teil (`null` = keines, Umschalter unsichtbar) — aus dem Store. */
  get sectionId(): string | null {
    return this.focus.get();
  }

  private _select(wanted: Scope): void {
    const before = this.scope;
    this._choice = selectScopeChoice(this._choice, wanted, this.focus.get());
    this._render();
    if (this.scope !== before) this._emit();
  }

  private _emit(): void {
    this.callbacks.onScopeChanged(this.scope, this.focus.get());
  }

  private _render(): void {
    this.root.hidden = !switchVisible(this.focus.get());
    const teil = this.scope === "teil";
    this.globalRadio.checked = !teil;
    this.teilRadio.checked = teil;
    this.hint.hidden = !teil;
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}
