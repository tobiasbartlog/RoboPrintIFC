/**
 * Status-Ableitung des Zerlegungs-Inspectors (UI-Redesign Scheibe 4, Issue #106)
 * — reine, DOM-freie Funktionen (wie `cutplan-state.ts` / `parts-palette-state.ts`,
 * vitest-getestet).
 *
 * Zwei Anzeigen leiten sich aus DEMSELBEN Fachzustand ab (der Viewer rechnet
 * nichts Eigenes, ADR-007): der **Kopf-/Fußzeilen-Status** des Schnittplans
 * (ungeprüft ↔ geprüft, aus dem `dirty`-Flag des `cutplan-state`) und der
 * **Zähler der Teile-Palette** („2/3 ✓" ↔ „ungeprüft"). Sobald der Schnittplan
 * geändert wurde (dirty), sind beide amber („ungeprüft") — die Ampeln werden
 * erst nach einer erfolgreichen Neubewertung durch den Core wieder scharf
 * (dieselbe Dirty-Kette wie der Stepper-Punkt, `staleness.ts`).
 */

import type { PartAmpel } from "./parts-palette-state";

/** Eine abgeleitete Badge-Anzeige: Text plus CSS-Modifikatorklasse (`.badge-*`). */
export interface StatusBadge {
  /** Anzeigetext (leer = kein Badge zeigen). */
  label: string;
  /** CSS-Klasse aus den Redesign-Bausteinen (#101): amber vs. grün. */
  cssClass: "badge-warn" | "badge-ok";
  /** true, wenn das Badge überhaupt gezeigt werden soll (sonst versteckt). */
  show: boolean;
}

/**
 * Kopf-/Fußzeilen-Status des Schnittplans (Issue #106, Punkt 3/5). „ungeprüft"
 * (amber, 600) sobald der Plan geändert wurde (dirty); sonst „geprüft ✓" (grün),
 * sofern es überhaupt einen bewerteten Stand gibt. Ohne Schnitte UND ohne
 * Abschnitte (leerer Plan) bleibt das Badge aus — es gibt nichts zu prüfen.
 */
export function headStatus(dirty: boolean, sectionCount: number): StatusBadge {
  if (dirty) {
    return { label: "ungeprüft", cssClass: "badge-warn", show: true };
  }
  if (sectionCount === 0) {
    return { label: "", cssClass: "badge-ok", show: false };
  }
  return { label: "geprüft ✓", cssClass: "badge-ok", show: true };
}

/**
 * Zähler der Teile-Palette (Issue #106): „N/M ✓" (grüne / alle Teile) wenn
 * bewertet, sonst „ungeprüft" (amber), sobald ein Teil ungeprüft ist. Ohne
 * Teile (leere Palette) bleibt der Zähler aus.
 */
export function paletteCounter(ampeln: readonly PartAmpel[]): StatusBadge {
  const total = ampeln.length;
  if (total === 0) {
    return { label: "", cssClass: "badge-ok", show: false };
  }
  if (ampeln.some((a) => a === "ungeprueft")) {
    return { label: "ungeprüft", cssClass: "badge-warn", show: true };
  }
  const green = ampeln.filter((a) => a === "green").length;
  return {
    label: `${green}/${total} ✓`,
    cssClass: green === total ? "badge-ok" : "badge-warn",
    show: true,
  };
}
