/** Reine Stepper- und Veraltet-Logik (kein DOM, kein Store). */
import type { ParamValues } from './params';
import { paramsKey } from './params';
import { DEFAULT_PATTERN, type PatternChoice } from './patternChoice';

export const STEP_IDS = ['model', 'decompose', 'simulation', 'export'] as const;
export type StepId = (typeof STEP_IDS)[number];
export type StepStatus = 'fehlt' | 'veraltet' | 'aktuell';

export const STEP_LABELS: Record<StepId, string> = {
  model: 'Modell',
  decompose: 'Zerlegen & prüfen',
  simulation: 'Simulation',
  export: 'Export',
};

export interface RunBasis {
  projectId: string;
  wallId: string;
  paramsKey: string;
  /** Lauf über den Direkteinstieg geöffnet: gehört zu keinem Projekt und veraltet nicht. */
  direct?: boolean;
}

export interface StepInputs {
  projectId: string | null;
  wallId: string | null;
  params: ParamValues;
  /** Musterwahl (Standard: kein Muster). Sie gehört wie die Parameter zur Basis des Laufs. */
  pattern?: PatternChoice;
  /** Basis des vorhandenen Laufs, falls vorhanden. */
  runBasis: RunBasis | null;
}

/** Fingerabdruck aus Parametern und Musterwahl. */
function basisKey(params: ParamValues, pattern: PatternChoice = DEFAULT_PATTERN): string {
  return paramsKey({ ...params, ...pattern });
}

export function makeBasis(projectId: string, wallId: string, params: ParamValues, pattern: PatternChoice = DEFAULT_PATTERN): RunBasis {
  return { projectId, wallId, paramsKey: basisKey(params, pattern) };
}

export function isRunStale(i: StepInputs): boolean {
  const b = i.runBasis;
  if (!b) return false;
  if (b.direct) return false;
  return b.projectId !== i.projectId || b.wallId !== i.wallId || b.paramsKey !== basisKey(i.params, i.pattern);
}

export function stepStatuses(i: StepInputs): Record<StepId, StepStatus> {
  const model: StepStatus = i.projectId && i.wallId ? 'aktuell' : 'fehlt';
  const run: StepStatus = !i.runBasis ? 'fehlt' : isRunStale(i) ? 'veraltet' : 'aktuell';
  return { model, decompose: run, simulation: run, export: run };
}

/** Grund, warum ein Schritt (noch) nicht betreten werden kann; null = frei. */
export function stepBlockedReason(step: StepId, i: StepInputs): string | null {
  switch (step) {
    case 'model':
      return null;
    case 'decompose':
      // Ein direkt geöffneter Lauf zeigt seine Teile auch ohne Modell; nur neu rechnen braucht eine Wand.
      if (i.runBasis?.direct) return null;
      if (!i.projectId) return 'Erst ein Modell wählen.';
      if (!i.wallId) return 'Erst eine Wand wählen.';
      return null;
    case 'simulation':
    case 'export':
      return i.runBasis ? null : 'Erst zerlegen & prüfen.';
  }
}

export function nextStep(step: StepId): StepId | null {
  return STEP_IDS[STEP_IDS.indexOf(step) + 1] ?? null;
}
