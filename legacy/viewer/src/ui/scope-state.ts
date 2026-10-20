/**
 * Gilt-für-Umschalter Global↔Teil — reiner Zustand (Druckplan-Neuordnung II S3,
 * Issue #92, PRD #88). DOM-frei und vitest-getestet (Hausmuster wie
 * `focus-store.ts` / `parts-palette-state.ts` / `rubrics-state.ts`).
 *
 * Der Geltungsbereichs-Schalter (viewer/CONTEXT.md „Gilt-für-Umschalter",
 * OrcaSlicer-Vorbild): sobald in der Teile-Palette ein **Teil** gewählt (=
 * fokussiert, `focus-store.ts` #84) ist, erscheint oben im Aside der Umschalter
 * Global ↔ gewähltes Teil. Auf „Teil" gestellt zeigen **dieselben**
 * Slicing-Formulare die geerbten effektiven Werte dezent (Platzhalter); jede
 * Eingabe wird zum sparsamen, **feldweisen** Override über die bestehende
 * #82-Mechanik (`process_params.sections`, Auflösung `resolveSectionParams` —
 * keine Duplikation). Jedes übersteuerte Feld bekommt ein ↺ „auf global zurück".
 *
 * Hier liegt nur die **Logik**: Geltungsbereich (inkl. Abgleich mit dem Fokus),
 * die Ausgrau-Matrix (strukturelle Gruppen sind im Teil-Modus deaktiviert — sie
 * *erzeugen* die Teile erst), die Vererbungsanzeige je Feld und der
 * Ein-Feld-Reset. Die dünne DOM-Anbindung ist `scope-switch.ts` (Umschalter)
 * bzw. `process-params.ts` (Formulare).
 */

import type {
  OrientationForm,
  SliceForm,
} from "./process-params-state";
import type { SectionOverrideForm } from "./section-params-state";

/** Der Geltungsbereich der Slicing-Formulare. */
export type Scope = "global" | "teil";

// Der Umschalter hält seit Issue #196 KEINE Fokus-Kopie mehr: das gewählte
// Teil liegt allein im `focus-store.ts` (ein Halter). Hier bleibt nur die
// Logik über der **Stellung** (`choice`) des Radio-Paars — jede Funktion
// bekommt den aktuellen Fokus als Parameter (gelesen aus dem Store).

/**
 * Stellt den Umschalter um. Auf „Teil" nur mit fokussiertem Teil möglich —
 * ohne Teil bleibt die Stellung (der Umschalter ist dann ohnehin unsichtbar).
 */
export function selectScopeChoice(
  choice: Scope,
  wanted: Scope,
  focusedSectionId: string | null,
): Scope {
  if (wanted === "teil" && focusedSectionId === null) return choice;
  return wanted;
}

/**
 * Gleicht die Stellung mit der Teile-Auswahl (Fokus, #84) ab: Abwahl (`null`)
 * fällt sauber auf Global zurück; ein Wechsel auf ein anderes Teil behält die
 * Stellung bei (OrcaSlicer-Verhalten: das neue Teil ist jetzt das Ziel).
 */
export function reconcileScopeChoice(
  choice: Scope,
  focusedSectionId: string | null,
): Scope {
  return focusedSectionId === null ? "global" : choice;
}

/** true, wenn der Umschalter sichtbar ist (nur bei fokussiertem Teil). */
export function switchVisible(focusedSectionId: string | null): boolean {
  return focusedSectionId !== null;
}

/** Der wirksame Geltungsbereich: ohne fokussiertes Teil immer `global`. */
export function effectiveScope(choice: Scope, focusedSectionId: string | null): Scope {
  return focusedSectionId === null ? "global" : choice;
}

// --- Ausgrau-Matrix -------------------------------------------------------

/**
 * Die Gruppen des Druckplan-Aside, die der Umschalter regiert. Strukturelle
 * Einstellungen (Aufstellung, Zerlegungsart/Vorschlag, Schnittplan) *erzeugen*
 * die Teile erst und können nicht je Teil gelten — sie werden im Teil-Modus
 * **ausgegraut** (disabled), nie ausgeblendet (das Formular springt nicht).
 * Slicing ist voll übersteuerbar; der Singularitäts-Advisor bleibt bedienbar
 * (er prüft seit Issue #134 die Platzierung des fokussierten Teils).
 */
export type AsideGroup = "aufstellung" | "zerlegung" | "schnittplan" | "slicing" | "advisor";

/** Die im Teil-Modus gesperrten (strukturellen) Gruppen. */
export const STRUCTURAL_GROUPS: readonly AsideGroup[] = [
  "aufstellung",
  "zerlegung",
  "schnittplan",
];

/**
 * Die Ausgrau-Matrix: ist eine Aside-Gruppe im gegebenen Geltungsbereich
 * bedienbar? Global: alles. Teil: strukturelle Gruppen gesperrt, Slicing voll
 * übersteuerbar, Advisor bleibt (global) bedienbar.
 */
export function groupEnabled(group: AsideGroup, scope: Scope): boolean {
  if (scope === "global") return true;
  return !STRUCTURAL_GROUPS.includes(group);
}

// --- Vererbungsanzeige + feldweiser Override/Reset -------------------------

/**
 * Adresse eines Slicing-Feldes im Override-Formular (#82): Gruppe + Feldname —
 * dieselben Gruppen wie `process_params.sections[id]` (slice/orientation).
 */
export type OverrideFieldRef =
  | { group: "slice"; field: keyof SliceForm }
  | { group: "orientation"; field: keyof OrientationForm };

/**
 * Anzeige eines Feldes im Teil-Modus: der Override-Wert steht im Feld (leer =
 * erbt), der **geerbte** globale Wert dezent als Platzhalter, und `overridden`
 * steuert Hervorhebung + Sichtbarkeit des ↺.
 */
export interface OverrideFieldView {
  /** Feldinhalt: der Override-Wert oder leer (erbt). */
  value: string;
  /** Der geerbte Wert dezent („8 · erbt" bzw. „Karten-Default · erbt"). */
  placeholder: string;
  /** true = Feld übersteuert (hervorheben, ↺ zeigen). */
  overridden: boolean;
}

/** Leitet die Vererbungsanzeige eines Feldes ab (Teil-Modus, Issue #92). */
export function overrideFieldView(
  inheritedValue: number | null,
  overrideValue: number | null,
): OverrideFieldView {
  return {
    value: overrideValue === null ? "" : String(overrideValue),
    placeholder:
      inheritedValue === null ? "Karten-Default · erbt" : `${inheritedValue} · erbt`,
    overridden: overrideValue !== null,
  };
}

/** Liest ein Feld aus dem Override-Formular (`null` = nicht gesetzt → erbt). */
export function readOverrideField(
  form: SectionOverrideForm,
  ref: OverrideFieldRef,
): number | null {
  return ref.group === "slice" ? form.slice[ref.field] : form.orientation[ref.field];
}

/** Setzt genau ein Feld im Override-Formular (immutable; `null` = erbt wieder). */
export function setOverrideField(
  form: SectionOverrideForm,
  ref: OverrideFieldRef,
  value: number | null,
): SectionOverrideForm {
  if (ref.group === "slice") {
    return { ...form, slice: { ...form.slice, [ref.field]: value } };
  }
  return { ...form, orientation: { ...form.orientation, [ref.field]: value } };
}

/**
 * ↺ „auf global zurück": setzt **genau ein** Feld auf „erbt" zurück (`null`);
 * alle anderen Overrides bleiben unberührt. Der sparse Request
 * (`sectionOverrideRequestFromForm`, #82) lässt leer geräumte Gruppen dann
 * automatisch wegfallen.
 */
export function resetOverrideField(
  form: SectionOverrideForm,
  ref: OverrideFieldRef,
): SectionOverrideForm {
  return setOverrideField(form, ref, null);
}
