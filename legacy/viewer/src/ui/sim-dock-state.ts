/**
 * Player-Leiste des Simulations-Docks — reine Modus-Wahl (Issue #154, Wayfinder-
 * Karte #139, Entscheidung #148). DOM-frei und vitest-getestet (Hausmuster wie
 * `druckort-state.ts` / `scope-state.ts` / `focus-store.ts`): hier liegt nur die
 * Logik, WELCHE Dock-Elemente `hidden` sind; das Zuweisen des `.hidden`-Attributs
 * (ausschließlich `.hidden`, Lehre aus #56 — kein `style.display`, keine
 * CSS-Gymnastik) macht dünn `ui/simulation.ts`.
 *
 * Das `#sim-dock` zeigte bisher **zwei Zustände gleichzeitig**: die Startknöpfe
 * blieben sichtbar, auch wenn der Player lief — die Ursache der Überlagerung
 * (nicht die Textlängen). Jetzt hat die Leiste genau zwei Modi:
 *
 * - **Start-Modus** (kein Replay): die zwei Startknöpfe (`#sim-focus-btn`,
 *   `#sim-sequence-btn`) und die kompakten Hinweise (`#sim-api-warning`,
 *   `#sim-precondition`) sind sichtbar, der Player ist versteckt.
 * - **Replay-Modus** (ein Lauf spielt — Wand-Replay, Gesamtablauf ODER Modul-
 *   Replay am Druckort): der Player (`#sim-player`) ist sichtbar, die Startknöpfe
 *   und ihre Hinweise sind versteckt. `← Übersicht` (bzw. das Ende eines Laufs)
 *   schaltet zurück in den Start-Modus.
 *
 * Eine Zeile bleibt eine Zeile: nur der jeweils passende Satz Elemente steht in der
 * `#sim-dock`-Leiste — kein Umbruch, kein Popover, keine zweite Zeile (vertikale
 * Bildfläche ist knapp).
 */

/** Die zwei Zustände der Dock-Leiste. */
export type SimDockMode = "start" | "replay";

/**
 * Eingang der Modus-Wahl: läuft ein Replay? ist die Core-API erreichbar? liegt ein
 * Voraussetzungs-Hinweis an? Die letzten beiden steuern nur, ob ihr Hinweis IM
 * Start-Modus erscheint — im Replay-Modus sind sie ohnehin versteckt.
 */
export interface SimDockState {
  /** Ein Lauf spielt im Dock-Player (Wand-Replay, Gesamtablauf oder Modul-Replay). */
  replaying: boolean;
  /** Core-API erreichbar (sonst zeigt der Start-Modus die API-Warnung). */
  apiAvailable: boolean;
  /** Ein Voraussetzungs-Hinweis liegt an (zeigt der Start-Modus die Vorbedingung). */
  hasPrecondition: boolean;
}

/**
 * Welche Dock-Elemente sind `hidden` (true = versteckt)? — direkt auf `.hidden`
 * zuweisbar. Der Status-Text (`#sim-status`) ist NICHT dabei: er ist ein eigener
 * Kanal (Fortschritt/Fehler) und lebt in beiden Modi.
 */
export interface SimDockHidden {
  focusBtn: boolean;
  sequenceBtn: boolean;
  apiWarning: boolean;
  precondition: boolean;
  player: boolean;
  /** Abspielgeschwindigkeit (Issue #155): lebt wie der Player NUR im Replay-Modus. */
  speed: boolean;
}

/** Der Modus folgt allein daraus, ob ein Replay läuft. */
export function simDockMode(state: SimDockState): SimDockMode {
  return state.replaying ? "replay" : "start";
}

/**
 * Die `hidden`-Matrix der Dock-Leiste. Im Start-Modus stehen die Startknöpfe und
 * die anliegenden Hinweise, der Player ist weg; im Replay-Modus genau umgekehrt.
 * Die zwei Hinweise erscheinen im Start-Modus nur, wenn sie etwas zu sagen haben
 * (API weg / Vorbedingung gesetzt) — ihre eigene Bedingung UND der Modus.
 */
export function simDockHidden(state: SimDockState): SimDockHidden {
  const start = simDockMode(state) === "start";
  return {
    focusBtn: !start,
    sequenceBtn: !start,
    apiWarning: !start || state.apiAvailable,
    precondition: !start || !state.hasPrecondition,
    player: start,
    // Das Geschwindigkeits-Bedienelement erscheint mit dem Player (Replay-Modus),
    // verschwindet mit den Startknöpfen (#155 im Replay-Modus von #154).
    speed: start,
  };
}
