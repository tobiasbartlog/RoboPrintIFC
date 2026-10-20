/**
 * Freie Platzierungs-Overrides je Teil — reiner Zustand (Druckplan-Neuordnung II
 * S5, Issue #94, PRD #88). DOM-frei und vitest-getestet (Hausmuster wie
 * `scope-state.ts` / `section-params-state.ts`).
 *
 * Der Platzierungs-Override eines Teils kann freie Werte tragen (seitliche
 * Position, Abstand, Aufstellhöhe) statt nur die Referenz auf eine erfasste
 * Aufstellmöglichkeit (`option_id`, Issue #25). Die Felder erscheinen im
 * Teil-Scope des Gilt-für-Umschalters (S3-Muster, Issue #92): leer = das Feld
 * erbt die **automatische** Platzierung (dezent als Platzhalter), Eingabe =
 * feldweiser Override, ↺ = zurück auf Automatik. Hier liegt nur die Umrechnung
 * Formular ↔ `section_overrides`-Eintrag und die Vererbungsanzeige; die dünne
 * DOM-Anbindung ist `placement-override.ts`. Der Viewer urteilt nie (ADR-007):
 * bewertet wird der Override vom Core (Ampel/erreichbar %/Marge), auch der
 * Sicherheits-Mindestabstand der Workstation ist ein Core-Befund, kein Gate.
 */

import type { PlacementOverrideValues, SectionOverride } from "../api/projects";

/** Die freien Platzierungsfelder (dieselben Achsen wie eine Aufstellmöglichkeit). */
export type PlacementField = "lateral_mm" | "standoff_mm" | "stand_height_mm";

/** Reihenfolge + Beschriftung der Felder (seitlich / Abstand / Aufstellhöhe). */
export const PLACEMENT_FIELDS: readonly PlacementField[] = [
  "lateral_mm",
  "standoff_mm",
  "stand_height_mm",
];

/** Formularzustand der freien Platzierungswerte eines Teils (`null` = erbt). */
export interface PlacementOverrideForm {
  lateral_mm: number | null;
  standoff_mm: number | null;
  stand_height_mm: number | null;
}

/** Leeres Formular: kein Feld gesetzt → das Teil wird automatisch platziert. */
export function emptyPlacementOverrideForm(): PlacementOverrideForm {
  return { lateral_mm: null, standoff_mm: null, stand_height_mm: null };
}

/**
 * Liest den `section_overrides`-Eintrag eines Teils ins Formular. Fehlt der
 * Eintrag oder trägt er nur eine `option_id`-Referenz (Issue #25), bleiben alle
 * Felder `null` — so wird nach dem Neuladen genau der persistierte Stand
 * wiederhergestellt. Nicht-endliche Werte übersteuern nie.
 */
export function placementOverrideForm(
  entry: SectionOverride | undefined,
): PlacementOverrideForm {
  const form = emptyPlacementOverrideForm();
  if (!entry) return form;
  for (const field of PLACEMENT_FIELDS) {
    const v = entry[field];
    if (typeof v === "number" && Number.isFinite(v)) form[field] = v;
  }
  return form;
}

/**
 * Baut aus dem Formular die sparse API-Werte (nur gesetzte Felder) — die
 * Eingabe für `setPlacementOverride`. Leeres Ergebnis = Override entfernen
 * (zurück zur automatischen Platzierung).
 */
export function placementOverrideRequest(
  form: PlacementOverrideForm,
): PlacementOverrideValues {
  const out: PlacementOverrideValues = {};
  for (const field of PLACEMENT_FIELDS) {
    const v = form[field];
    if (v !== null && Number.isFinite(v)) out[field] = v;
  }
  return out;
}

/** true, wenn mindestens ein Feld gesetzt (übersteuert) ist. */
export function placementOverrideHasValues(form: PlacementOverrideForm): boolean {
  return PLACEMENT_FIELDS.some((f) => form[f] !== null);
}

/**
 * Anzeige eines Platzierungsfeldes im Teil-Scope (S3-Muster, Issue #92/#94):
 * der Override-Wert steht im Feld (leer = automatisch), der **automatische**
 * Wert aus dem Core-Artefakt dezent als Platzhalter, `overridden` steuert
 * Hervorhebung + Sichtbarkeit des ↺.
 */
export interface PlacementFieldView {
  value: string;
  placeholder: string;
  overridden: boolean;
}

/**
 * Leitet die Vererbungsanzeige eines Feldes ab. `automaticValue` ist der
 * aktuell wirksame Wert aus dem Core-Artefakt (`DecompositionSection.placement`)
 * — reine Anzeige, keine Viewer-Ableitung (ADR-007); `null` = noch keine
 * Zerlegung bewertet.
 */
export function placementFieldView(
  automaticValue: number | null,
  overrideValue: number | null,
): PlacementFieldView {
  return {
    value: overrideValue === null ? "" : String(overrideValue),
    placeholder:
      automaticValue === null ? "Auto" : `${Math.round(automaticValue)} · Auto`,
    overridden: overrideValue !== null,
  };
}
