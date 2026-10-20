/**
 * Gradierungs-Ebene: Pro-Abschnitts-Overrides + Auflösung (Druckplan S3, Issue #82).
 *
 * Reine, DOM-freie Funktionen zwischen dem Druckjob
 * (`process_params.sections[section_id]`) und dem Panel-Formular je Abschnitt —
 * plus der **Auflösung** „global + Override → effektiv", die den Core-Zwilling
 * `fgc.domain.process_params.resolve_section_params` bit-gleich spiegelt (geteilte
 * Golden-Fälle `section-params.golden.json`, erzeugt von
 * `viewer/scripts/gen_goldens.py`, Paar `section-params`).
 *
 * Wie global (Issue #59/#61): ein leeres Feld heißt „nicht gesetzt" → der Abschnitt
 * erbt den globalen Wert (bzw. fällt weiter auf die Karte/Code-Defaults zurück).
 * Nur gesetzte Felder gehen als Override an die API.
 */

import type { OrientationParams, SectionProcessOverride, SliceParams } from "../api/projects";
import {
  type IkConfigForm,
  emptyIkConfigForm,
  ikConfigFormFromBlock,
  ikConfigRequestFromForm,
} from "./ik-config-state";
import {
  type OrientationForm,
  type SliceForm,
  emptyOrientationForm,
  emptySliceForm,
  orientationFormFromBlock,
  orientationRequestFromForm,
  sliceFormFromBlock,
  sliceRequestFromForm,
} from "./process-params-state";

/**
 * Die Gruppen, die ein Abschnitt übersteuern darf — dieselben wie global
 * (#82 slice/orientation; #129 ik_config). `resolveSectionParams` löst alle drei
 * generisch: numerische Felder (slice/orientation) wie String-Tri-States (ik_config).
 */
const GROUPS = ["slice", "orientation", "ik_config"] as const;

/**
 * Löst globale Prozessparameter + Abschnitts-Override zu den effektiven auf.
 *
 * Bit-gleicher Zwilling von `resolve_section_params` (Core): je Gruppe
 * (`slice`/`orientation`) und Feld gewinnt der Abschnittswert, wenn gesetzt; sonst
 * erbt er global. Weder-noch gesetzte Felder bleiben weg (→ Karte/Code-Default).
 * `null`/nicht-endliche Werte übersteuern nie. Das Ergebnis ist wieder sparse
 * (leere Gruppen entfallen), damit es sich wie ein normaler Block weiterlesen lässt.
 */
export function resolveSectionParams(
  globalParams: SectionProcessOverride,
  sectionOverride: SectionProcessOverride,
): SectionProcessOverride {
  const effective: SectionProcessOverride = {};
  for (const group of GROUPS) {
    const base = (globalParams[group] ?? {}) as Record<string, unknown>;
    const over = (sectionOverride[group] ?? {}) as Record<string, unknown>;
    const merged: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(base)) if (isSet(v)) merged[k] = v;
    for (const [k, v] of Object.entries(over)) if (isSet(v)) merged[k] = v;
    if (Object.keys(merged).length > 0) {
      (effective as Record<string, unknown>)[group] = merged;
    }
  }
  return effective;
}

/** Formularzustand eines Abschnitts-Overrides — dieselben Felder wie global. */
export interface SectionOverrideForm {
  slice: SliceForm;
  orientation: OrientationForm;
  ikConfig: IkConfigForm;
}

/** Leeres Abschnitts-Override-Formular (kein Feld gesetzt → erbt komplett global). */
export function emptySectionOverrideForm(): SectionOverrideForm {
  return {
    slice: emptySliceForm(),
    orientation: emptyOrientationForm(),
    ikConfig: emptyIkConfigForm(),
  };
}

/**
 * Liest den Abschnitts-Override eines Druckjobs (`process_params.sections[id]`) ins
 * Formular. Fehlt der Block/Abschnitt (Altprojekt), bleiben alle Felder `null` —
 * so wird nach dem Neuladen genau der persistierte Stand wiederhergestellt.
 */
export function sectionOverrideForm(
  override: SectionProcessOverride | undefined,
): SectionOverrideForm {
  return {
    slice: sliceFormFromBlock(override?.slice),
    orientation: orientationFormFromBlock(override?.orientation),
    ikConfig: ikConfigFormFromBlock(override?.ik_config),
  };
}

/**
 * Baut aus dem Abschnitts-Formular den sparse Override-Block: nur gesetzte Felder.
 * Ist keine Gruppe belegt, ist das Ergebnis `{}` (der Core lässt den Abschnitt
 * dann komplett global erben).
 */
export function sectionOverrideRequestFromForm(form: SectionOverrideForm): SectionProcessOverride {
  const out: SectionProcessOverride = {};
  const slice = sliceRequestFromForm(form.slice);
  const orientation = orientationRequestFromForm(form.orientation);
  const ikConfig = ikConfigRequestFromForm(form.ikConfig);
  if (Object.keys(slice).length > 0) out.slice = slice;
  if (Object.keys(orientation).length > 0) out.orientation = orientation;
  if (Object.keys(ikConfig).length > 0) out.ik_config = ikConfig;
  return out;
}

/**
 * Baut aus der Abschnitts-ID→Formular-Map den `sections`-Request für die API.
 * Jeder Abschnitt geht mit — auch leer geräumte (→ `{}`), damit der Core sie
 * wieder auf „erbt global" zurücksetzt.
 */
export function sectionsRequestFromForms(
  forms: Record<string, SectionOverrideForm>,
): Record<string, SectionProcessOverride> {
  const out: Record<string, SectionProcessOverride> = {};
  for (const [sectionId, form] of Object.entries(forms)) {
    out[sectionId] = sectionOverrideRequestFromForm(form);
  }
  return out;
}

/** true, wenn im Abschnitts-Formular mindestens ein Feld gesetzt (übersteuert) ist. */
export function sectionOverrideFormHasValues(form: SectionOverrideForm): boolean {
  const req = sectionOverrideRequestFromForm(form);
  return req.slice !== undefined || req.orientation !== undefined || req.ik_config !== undefined;
}

/** Die globalen `slice`/`orientation`/`ik_config`-Blöcke als Auflöse-Eingabe (parity-Format). */
export function globalParamsFrom(
  slice: SliceParams | undefined,
  orientation: OrientationParams | undefined,
  ikConfig?: SectionProcessOverride["ik_config"],
): SectionProcessOverride {
  const out: SectionProcessOverride = {};
  if (slice && Object.keys(slice).length > 0) out.slice = slice;
  if (orientation && Object.keys(orientation).length > 0) out.orientation = orientation;
  if (ikConfig && Object.keys(ikConfig).length > 0) out.ik_config = ikConfig;
  return out;
}

/** „Gesetzt": endliche Zahl (slice/orientation) ODER nicht-leerer String (ik_config). */
function isSet(v: unknown): boolean {
  if (typeof v === "number") return Number.isFinite(v);
  if (typeof v === "string") return v.length > 0;
  return false;
}
