/**
 * Aufklapp-Zustand eines einklappbaren Bereichs (Scheibe 2b, Issue #60) — reine,
 * DOM-freie Funktionen. Ein schlichtes, wiederverwendbares Muster für die im
 * Viewer bewusst vermiedene `<details>`-Elementfamilie: der Zustand ist ein
 * einzelnes Boolean (`expanded`), die Ansicht (`collapsibleView`) leitet daraus
 * die drei DOM-Eigenschaften ab, die ein Aufklapp-Bereich braucht — ob der Körper
 * versteckt ist, der `aria-expanded`-Wert der Schaltfläche und deren Beschriftung.
 *
 * Getrennt von three.js/DOM getestet (`collapsible-state.test.ts`), damit die
 * reine Aufklapp-Logik ohne Browser prüfbar bleibt (wie die anderen `*-state.ts`).
 */

/** Der reine Zustand eines einklappbaren Bereichs: auf- oder zugeklappt. */
export interface CollapsibleState {
  expanded: boolean;
}

/** Startzustand (Default: zugeklappt — „Fortgeschritten" ist optional). */
export function collapsibleState(expanded = false): CollapsibleState {
  return { expanded };
}

/** Kippt den Aufklapp-Zustand (Klick auf die Kopfzeile/Schaltfläche). */
export function toggleCollapsible(state: CollapsibleState): CollapsibleState {
  return { expanded: !state.expanded };
}

/** Setzt den Aufklapp-Zustand explizit (z. B. beim Wiederherstellen). */
export function setCollapsible(expanded: boolean): CollapsibleState {
  return { expanded };
}

/** Die aus dem Zustand abgeleiteten DOM-Eigenschaften eines Aufklapp-Bereichs. */
export interface CollapsibleView {
  /** true, wenn der Inhalt (Körper) versteckt ist (zugeklappt). */
  bodyHidden: boolean;
  /** Wert des `aria-expanded`-Attributs der Schaltfläche. */
  ariaExpanded: "true" | "false";
  /** Beschriftung der Schaltfläche inkl. Aufklapp-Marker (▸ zu / ▾ auf). */
  toggleLabel: string;
}

/**
 * Leitet die DOM-Eigenschaften aus dem Zustand ab. ``label`` ist der Klartext des
 * Bereichs (z. B. „Fortgeschritten"); der Marker (▸/▾) macht den Zustand ohne
 * zusätzliches Icon sichtbar.
 */
export function collapsibleView(state: CollapsibleState, label: string): CollapsibleView {
  return {
    bodyHidden: !state.expanded,
    ariaExpanded: state.expanded ? "true" : "false",
    toggleLabel: `${state.expanded ? "▾" : "▸"} ${label}`,
  };
}
