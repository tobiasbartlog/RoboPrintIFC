/**
 * Wand-/Teil-Fokus als **ein Halter** (Issue #196; ersetzt `focus-state.ts`
 * aus #84 plus die 7 gefütterten Kopien in main.ts/scope-switch/process-params/
 * placement-override/simulation/collision-advisor).
 *
 * Ein Teil lässt sich im geteilten 3D-Feld (bzw. der Teile-Palette) als
 * **Fokus** wählen: der Klick nimmt es auf, ein erneuter Klick auf dasselbe
 * Teil gibt es wieder frei (Toggle). Genau ein Teil kann Fokus sein — oder
 * keines (`null`, der abwärtskompatible Ausgangszustand). Der Fokus ist reiner
 * **Sicht-Zustand** (ADR-007): der Store kennt weder Kamera noch Highlight,
 * nur *welche* `section_id` gerade im Fokus steht. Alle Wirkungen (Highlight,
 * Kamera-Einfassung, Panel-Umschaltungen) sind Subscriber — sie lesen den
 * Zustand, sie bestimmen ihn nicht.
 *
 * DOM-frei und ohne three.js (Pure/DOM-Split wie `cutplan-state.ts`), damit
 * Auswahl-Logik und Wirkungs-Vertrag (`FOCUS_EFFECT_ORDER`) ohne Renderer per
 * vitest prüfbar bleiben.
 */

/** Ein Fokus-Abonnent: wird bei jeder ECHTEN Änderung gerufen (nie bei No-ops). */
export type FocusListener = (sectionId: string | null) => void;

/**
 * Lese-/Abonnier-Sicht des Stores — was die Panels bekommen (sie lesen und
 * abonnieren, sie schreiben nicht; schreiben darf nur die Fokus-Quelle:
 * 3D-Klick/Teile-Palette via `toggle`, Neuzerlegung via `reconcile`).
 */
export interface FocusReader {
  /** Die aktuell fokussierte `section_id` oder `null` (kein Fokus). */
  get(): string | null;
  /** Abonniert Änderungen (Aufruf-Reihenfolge = Registrier-Reihenfolge); liefert das Abbestellen. */
  subscribe(listener: FocusListener): () => void;
}

export class FocusStore implements FocusReader {
  private _focused: string | null = null;
  private readonly _listeners: FocusListener[] = [];

  get(): string | null {
    return this._focused;
  }

  /**
   * Klick auf ein Teil: ist es bereits im Fokus, wird der Fokus aufgehoben
   * (Toggle → sauberer „kein Fokus"-Zustand), sonst wird es der neue Fokus.
   * Dies ist die Funktion hinter dem 3D-Klick und der Teile-Palette (#84/#91).
   */
  toggle(sectionId: string): void {
    this._set(this._focused === sectionId ? null : sectionId);
  }

  /**
   * Gleicht den Fokus mit den aktuell vorhandenen Teilen ab: verschwindet das
   * Fokus-Teil durch eine neue Zerlegung (anderer Schnittplan, Neubewertung),
   * fällt der Zustand sauber auf „kein Fokus" zurück. Ein noch vorhandener
   * Fokus bleibt unverändert — auch bei nur einem Teil (#84).
   */
  reconcile(sectionIds: readonly string[]): void {
    if (this._focused !== null && !sectionIds.includes(this._focused)) {
      this._set(null);
    }
  }

  subscribe(listener: FocusListener): () => void {
    this._listeners.push(listener);
    return () => {
      const i = this._listeners.indexOf(listener);
      if (i >= 0) this._listeners.splice(i, 1);
    };
  }

  /** Nur echte Änderungen feuern (No-ops bleiben still — wie die alte Kaskade). */
  private _set(sectionId: string | null): void {
    if (sectionId === this._focused) return;
    this._focused = sectionId;
    for (const listener of [...this._listeners]) listener(sectionId);
  }
}

/**
 * Die Wirkungen eines Fokus-Wechsels als **getesteter Vertrag** (Issue #196):
 * Mitglieder-Menge und Reihenfolge der früheren, handgepflegten
 * `onFocusChanged`-Kaskade in `main.ts` — JEDE Wirkung steht hier, keine darf
 * still fehlen oder wandern (Muster `job-adopt.ts`, #193). `main.ts` liefert
 * nur noch die echten Effekte (Ports) und registriert sie EINMAL über
 * `registerFocusEffects`.
 */
export const FOCUS_EFFECT_ORDER = [
  /** 1. Fokus-Quader im 3D-Feld hervorheben — ganze Wand bleibt sichtbar (#84). */
  "highlightSectionBox",
  /** 2. Marker↔Mesh-Tausch: das Fokus-Teil zeigt den echten Arm statt des Markers (#93). */
  "swapPlacementFocusMesh",
  /** 3. Gilt-für-Umschalter abgleichen — Abwahl fällt auf Global zurück (#92). */
  "reconcileScopeSwitch",
  /** 4. Slicing-Formulare auf den wirksamen Scope stellen + Kopf-Notiz (#92/#107) —
   *  ersetzt den früheren Zwei-Hop-Sonderweg über den Umschalter-Callback. */
  "syncProcessParamsScope",
  /** 5. Platzierungsfelder der Zerlegung: fokus-getrieben bedienbar (#106/#94). */
  "syncPlacementOverrideScope",
  /** 6. Accordion-Titel „Platzierung — <Teil>" (#106). */
  "setPlacementTitle",
  /** 7. Druckort-Ansicht abgleichen: verlassen bzw. am neuen Modul neu aufbauen (#96). */
  "syncDruckort",
  /** 8. Kamera weich einfassen (#84). */
  "frameFocus",
  /** 9. Live-Vorschau „Vorbereiten" am Fokus neu aufbauen (#85). */
  "updatePreparePreview",
  /** 10. Simulations-Dock: Fokus ist das Ziel des „Fokus … simulieren"-Knopfs (#86). */
  "syncSimulationDock",
  /** 11. Kollisions-Advisor: Scope-Chip ehrlich mitführen (#130/#139/#145). */
  "syncCollisionAdvisorScope",
] as const;

export type FocusEffectName = (typeof FOCUS_EFFECT_ORDER)[number];

/** Die echten Effekte, die `main.ts` bereitstellt — je Vertrags-Mitglied einer. */
export type FocusEffects = Record<FocusEffectName, (sectionId: string | null) => void>;

/**
 * Registriert die Wirkungs-Kaskade als EINEN Subscriber: bei jedem Fokus-
 * Wechsel laufen alle Effekte in Vertrags-Reihenfolge (`FOCUS_EFFECT_ORDER`).
 * Liefert das Abbestellen (für Tests; `main.ts` registriert einmal, für immer).
 */
export function registerFocusEffects(store: FocusReader, effects: FocusEffects): () => void {
  return store.subscribe((sectionId) => {
    for (const name of FOCUS_EFFECT_ORDER) effects[name](sectionId);
  });
}
