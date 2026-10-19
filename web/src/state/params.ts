/**
 * Parameter nach SPEC §10. `assumption`: vom Nutzer zu bestätigende Annahme.
 * Die Schlüssel sind die Feldnamen von `PlannerParams` im Kern; der Viewer schickt sie bei jedem Job mit.
 */
export type ParamValue = number | string | boolean;
export type ParamValues = Record<string, ParamValue>;

export interface NumParamDef {
  key: string;
  label: string;
  unit: string;
  default: number;
  step: number;
  assumption: boolean;
  provisional?: boolean;
  hint?: string;
}

export const NUM_PARAMS: NumParamDef[] = [
  { key: 'layer_height_mm', label: 'Schichthöhe', unit: 'mm', default: 10, step: 1, assumption: true },
  { key: 'bead_width_mm', label: 'Strangbreite', unit: 'mm', default: 30, step: 1, assumption: true, hint: 'Düse 30gut' },
  { key: 'shells', label: 'Schalen', unit: '', default: 2, step: 1, assumption: false, hint: 'aus Prozesskarte' },
  { key: 'v_print_mm_s', label: 'Druckgeschwindigkeit', unit: 'mm/s', default: 100, step: 5, assumption: true },
  { key: 'v_travel_mm_s', label: 'Fahrgeschwindigkeit', unit: 'mm/s', default: 250, step: 10, assumption: true },
  { key: 'z_lift_mm', label: 'Abhebehöhe', unit: 'mm', default: 30, step: 1, assumption: true },
  { key: 'approach_mm', label: 'An- und Abfahrt', unit: 'mm', default: 20, step: 1, assumption: true },
  { key: 'v_pump_v', label: 'Pumpenspannung', unit: 'V', default: 5, step: 0.1, assumption: true },
  { key: 't_tot_s', label: 'Verweilzeit am Ringstart', unit: 's', default: 3, step: 0.5, assumption: true, provisional: true },
  { key: 'r_blend_mm', label: 'Überschleifradius', unit: 'mm', default: 2, step: 0.5, assumption: true },
  { key: 'd_hard_mm', label: 'Mindestabstand hart', unit: 'mm', default: 10, step: 1, assumption: true },
  { key: 'd_target_mm', label: 'Sollabstand', unit: 'mm', default: 50, step: 5, assumption: false },
  { key: 'd_target_printed_mm', label: 'Sollabstand Druckstand', unit: 'mm', default: 20, step: 5, assumption: false },
  { key: 'r_free_mm', label: 'Freiraumradius', unit: 'mm', default: 40, step: 5, assumption: false },
  { key: 'tau_max_deg', label: 'Düsenneigung höchstens', unit: '°', default: 0, step: 1, assumption: true },
  { key: 'psi_step_deg', label: 'Winkelraster ψ', unit: '°', default: 15, step: 1, assumption: false },
  { key: 'step_mm', label: 'Abtastabstand', unit: 'mm', default: 20, step: 1, assumption: false },
  { key: 'dq_max_rad', label: 'Gelenksprung je Kante', unit: 'rad', default: 0.3, step: 0.05, assumption: false },
];

export const DEFAULT_PARAMS: ParamValues = {
  ...Object.fromEntries(NUM_PARAMS.map((p) => [p.key, p.default])),
  tcp_name: 'FGC_30GUT',
  dialect: 'v2',
};

export function changedKeys(values: ParamValues): string[] {
  return Object.keys(DEFAULT_PARAMS).filter((k) => values[k] !== DEFAULT_PARAMS[k]);
}

/** Stabiler Fingerabdruck für den Veraltet-Vergleich. */
export function paramsKey(values: ParamValues): string {
  return JSON.stringify(
    Object.keys(values)
      .sort()
      .map((k) => [k, values[k]]),
  );
}
