/**
 * Wählbare IK-Konfiguration (Kollisionskontrolle S4, Issue #129, ADR-024) — reiner,
 * DOM-freier Zustand der drei Tri-State-Schalter Schulter/Ellbogen/Handgelenk.
 *
 * Persistiert wie ein Slicing-Parameter (Muster #59/#61/#82): global + je Teil über
 * den Gilt-für-Umschalter (#92). Je Achse drei Stellungen — **auto** (nicht gesetzt →
 * erbt bzw. kein Constraint), **Zustand A** (`"a"`) oder **Zustand B** (`"b"`); gesetzte
 * Achsen filtern die 8 IK-Lösungszweige im Core **hart** (Bitschema `opw.py`).
 *
 * Wie die numerischen Gruppen: „auto" heißt „nicht gesetzt" → im Teil-Modus erbt die
 * Achse den globalen Wert (dezenter Hinweis), jede andere Stellung ist ein sparsamer,
 * feldweiser Override (↺ setzt die Achse auf auto/erbt zurück). Nur gesetzte Achsen
 * gehen als Override an die API (`ikConfigRequestFromForm`). Der Viewer hält keinen
 * Fachzustand (ADR-007) — hier liegt nur die Umrechnung Formular ↔ Block + die
 * Vererbungsanzeige; der harte Filter selbst wird im Core gerechnet.
 */

import type { IkAxisState, IkConfig } from "../api/projects";

/** Die drei IK-Konfigurationsachsen (Bitschema `opw.py`: Schulter/Ellbogen/Handgelenk). */
export const IK_AXES = ["shoulder", "elbow", "wrist"] as const;
export type IkAxis = (typeof IK_AXES)[number];

/**
 * Formularzustand der IK-Konfiguration — je Achse `IkAxisState` oder `null`
 * (auto = nicht gesetzt → erbt bzw. kein Constraint).
 */
export type IkConfigForm = Record<IkAxis, IkAxisState | null>;

/** Leeres Formular: alle Achsen auto (auto/auto/auto = heutiges Verhalten). */
export function emptyIkConfigForm(): IkConfigForm {
  return { shoulder: null, elbow: null, wrist: null };
}

/**
 * Liest einen `ik_config`-Block (global ODER je Abschnitt) ins Formular. Fehlt der
 * Block oder eine Achse, bleibt sie `null` (auto) — so wird nach dem Neuladen genau
 * der persistierte Stand wiederhergestellt.
 */
export function ikConfigFormFromBlock(block: IkConfig | undefined): IkConfigForm {
  return {
    shoulder: axisOrNull(block?.shoulder),
    elbow: axisOrNull(block?.elbow),
    wrist: axisOrNull(block?.wrist),
  };
}

/**
 * Baut aus dem Formular den sparse `ik_config`-Block: nur gesetzte Achsen (nicht
 * `null`). Alle auto → `{}` (der Core entfernt den Block → auto/auto/auto).
 */
export function ikConfigRequestFromForm(form: IkConfigForm): IkConfig {
  const out: IkConfig = {};
  for (const axis of IK_AXES) {
    const v = form[axis];
    if (v !== null) out[axis] = v;
  }
  return out;
}

/** true, wenn mindestens eine Achse fixiert (gesetzt) ist. */
export function ikConfigFormHasValues(form: IkConfigForm): boolean {
  return IK_AXES.some((axis) => form[axis] !== null);
}

/** Liest eine Achse aus dem Formular (`null` = auto). */
export function readIkAxis(form: IkConfigForm, axis: IkAxis): IkAxisState | null {
  return form[axis];
}

/** Setzt genau eine Achse (immutable; `null` = auto/erbt wieder). */
export function setIkAxis(
  form: IkConfigForm,
  axis: IkAxis,
  value: IkAxisState | null,
): IkConfigForm {
  return { ...form, [axis]: value };
}

/**
 * ↺ „auf global zurück": setzt genau eine Achse auf auto/erbt (`null`) zurück; die
 * anderen bleiben unberührt (der sparse Request lässt sie dann wegfallen).
 */
export function resetIkAxis(form: IkConfigForm, axis: IkAxis): IkConfigForm {
  return setIkAxis(form, axis, null);
}

/**
 * Löst globale IK-Konfiguration + Abschnitts-Override zur effektiven auf (Muster
 * `resolveSectionParams`): je Achse gewinnt der Abschnittswert, wenn gesetzt; sonst
 * erbt sie global; auto/auto bleibt auto.
 */
export function resolveIkConfig(globalForm: IkConfigForm, overrideForm: IkConfigForm): IkConfigForm {
  const out = emptyIkConfigForm();
  for (const axis of IK_AXES) {
    out[axis] = overrideForm[axis] ?? globalForm[axis];
  }
  return out;
}

/** Menschlicher Text einer Achsstellung (auto/Zustand A/Zustand B). */
export function axisStateLabel(state: IkAxisState | null): string {
  if (state === "a") return "Zustand A";
  if (state === "b") return "Zustand B";
  return "auto";
}

/**
 * Anzeige einer Achse im Teil-Modus (Gilt-für, #92): der Override steht im Schalter
 * (leer = erbt), der **geerbte** globale Wert dezent als Hinweis, `overridden` steuert
 * Hervorhebung + Sichtbarkeit des ↺.
 */
export interface IkAxisView {
  /** Schalterwert: der Override oder `""` (auto/erbt). */
  value: "" | IkAxisState;
  /** Der geerbte Wert dezent, z. B. „Zustand A · erbt". */
  inheritedLabel: string;
  /** true = Achse übersteuert (hervorheben, ↺ zeigen). */
  overridden: boolean;
}

/** Leitet die Vererbungsanzeige einer Achse ab (Teil-Modus, #92/#129). */
export function ikAxisView(
  inherited: IkAxisState | null,
  override: IkAxisState | null,
): IkAxisView {
  return {
    value: override === null ? "" : override,
    inheritedLabel: `${axisStateLabel(inherited)} · erbt`,
    overridden: override !== null,
  };
}

function axisOrNull(v: IkAxisState | undefined): IkAxisState | null {
  return v === "a" || v === "b" ? v : null;
}
