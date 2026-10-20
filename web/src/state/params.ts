/**
 * Parameter nach SPEC §10. `assumption`: vom Nutzer zu bestätigende Annahme.
 * Die Schlüssel sind die Feldnamen von `PlannerParams` im Kern; der Viewer schickt sie bei jedem Job mit.
 *
 * `core/tests/test_api.py::test_web_default_params_accepted` liest diese Datei mit regulären Ausdrücken:
 * Jede Zahlendefinition nennt Schlüssel und Standardwert als Literal im selben Objekt (ohne geschweifte
 * Klammer dazwischen), und die Standardwerte von `tcp_name` und `dialect` stehen je auf einer eigenen Zeile
 * in `STRING_DEFAULTS`. Nur die Zahlendefinitionen tragen die Eigenschaft für den Schlüssel als Literal.
 */
import { describeSpot, type Spot } from './spot';

export type ParamValue = number | string | boolean;
export type ParamValues = Record<string, ParamValue>;

/** Kategorien wie bei Kunststoff-Slicern. Reihenfolge = Reihenfolge im Panel. */
export type ParamGroupId = 'layer' | 'module' | 'speed' | 'pump' | 'motion' | 'clearance' | 'planning' | 'control';

export interface ParamGroup {
  id: ParamGroupId;
  title: string;
  /** Kurzfassung fasst gleiche Einheiten hintereinander zusammen („100 · 250 mm/s“). */
  joinUnits?: boolean;
}

export const PARAM_GROUPS: readonly ParamGroup[] = [
  { id: 'layer', title: 'Schicht & Strang' },
  { id: 'module', title: 'Module' },
  { id: 'speed', title: 'Geschwindigkeit', joinUnits: true },
  { id: 'pump', title: 'Pumpe' },
  { id: 'motion', title: 'Bewegung' },
  { id: 'clearance', title: 'Abstände' },
  { id: 'planning', title: 'Bahnplanung' },
  { id: 'control', title: 'Steuerung & Export' },
];

interface BaseParamDef {
  key: string;
  label: string;
  group: ParamGroupId;
  /** sichtbar im Modus „Grundlegend“ */
  basic: boolean;
  assumption: boolean;
  provisional?: boolean;
  hint?: string;
}

export interface NumParamDef extends BaseParamDef {
  unit: string;
  default: number;
  step: number;
  /** Koordinate des Druckplatzes; das Panel zeigt beide zusammen als Draufsicht (`SpotPicker`). */
  spot?: 'x' | 'y';
}

export interface TextParamDef extends BaseParamDef {
  kind: 'text';
  default: string;
}

export interface ChoiceParamDef extends BaseParamDef {
  kind: 'choice';
  default: string;
  options: { value: string; label: string }[];
  /** Kurzname in der Kurzfassung, z. B. „DRL“ für „DRL v2“ */
  short?: string;
}

export type ParamDef = (NumParamDef & { kind: 'number' }) | TextParamDef | ChoiceParamDef;
export type ParamMode = 'basic' | 'all';

export const NUM_PARAMS: NumParamDef[] = [
  { key: 'layer_height_mm', label: 'Schichthöhe', unit: 'mm', default: 10, step: 1, assumption: true, group: 'layer', basic: true },
  {
    key: 'bead_width_mm',
    label: 'Strangbreite',
    unit: 'mm',
    default: 30,
    step: 1,
    assumption: true,
    hint: 'Düse 30gut',
    group: 'layer',
    basic: true,
  },
  {
    key: 'module_height_max_mm',
    label: 'Modulhöhe höchstens',
    unit: 'mm',
    default: 400,
    step: 50,
    assumption: true,
    hint: 'Lehm unter Eigengewicht; niedriger, wenn der Roboter höher nicht kollisionsfrei druckt',
    group: 'module',
    basic: true,
  },
  {
    key: 'spot_x_mm',
    label: 'Druckplatz seitlich',
    unit: 'mm',
    default: 0,
    step: 50,
    assumption: false,
    group: 'module',
    basic: true,
    spot: 'x',
  },
  {
    key: 'spot_y_mm',
    label: 'Druckplatz Tiefe',
    unit: 'mm',
    default: -50,
    step: 50,
    assumption: false,
    group: 'module',
    basic: true,
    spot: 'y',
  },
  {
    key: 'shells',
    label: 'Schalen',
    unit: '',
    default: 2,
    step: 1,
    assumption: false,
    hint: 'aus Prozesskarte',
    group: 'layer',
    basic: true,
  },
  { key: 'v_print_mm_s', label: 'Druckgeschwindigkeit', unit: 'mm/s', default: 100, step: 5, assumption: true, group: 'speed', basic: true },
  { key: 'v_travel_mm_s', label: 'Fahrgeschwindigkeit', unit: 'mm/s', default: 250, step: 10, assumption: true, group: 'speed', basic: true },
  { key: 'z_lift_mm', label: 'Abhebehöhe', unit: 'mm', default: 30, step: 1, assumption: true, group: 'motion', basic: false },
  { key: 'approach_mm', label: 'An- und Abfahrt', unit: 'mm', default: 20, step: 1, assumption: true, group: 'motion', basic: false },
  { key: 'v_pump_v', label: 'Pumpenspannung', unit: 'V', default: 5, step: 0.1, assumption: true, group: 'pump', basic: true },
  {
    key: 't_tot_s',
    label: 'Verweilzeit am Ringstart',
    unit: 's',
    default: 3,
    step: 0.5,
    assumption: true,
    provisional: true,
    group: 'pump',
    basic: true,
  },
  { key: 'r_blend_mm', label: 'Überschleifradius', unit: 'mm', default: 2, step: 0.5, assumption: true, group: 'motion', basic: false },
  { key: 'd_hard_mm', label: 'Mindestabstand hart', unit: 'mm', default: 10, step: 1, assumption: true, group: 'clearance', basic: false },
  { key: 'd_target_mm', label: 'Sollabstand', unit: 'mm', default: 50, step: 5, assumption: false, group: 'clearance', basic: false },
  {
    key: 'd_target_printed_mm',
    label: 'Sollabstand Druckstand',
    unit: 'mm',
    default: 20,
    step: 5,
    assumption: false,
    group: 'clearance',
    basic: false,
  },
  { key: 'r_free_mm', label: 'Freiraumradius', unit: 'mm', default: 40, step: 5, assumption: false, group: 'clearance', basic: false },
  { key: 'tau_max_deg', label: 'Düsenneigung höchstens', unit: '°', default: 0, step: 1, assumption: true, group: 'motion', basic: false },
  { key: 'psi_step_deg', label: 'Winkelraster ψ', unit: '°', default: 15, step: 1, assumption: false, group: 'planning', basic: false },
  { key: 'step_mm', label: 'Abtastabstand', unit: 'mm', default: 20, step: 1, assumption: false, group: 'planning', basic: false },
  { key: 'dq_max_rad', label: 'Gelenksprung je Kante', unit: 'rad', default: 0.3, step: 0.05, assumption: false, group: 'planning', basic: false },
];

/** Standardwerte der Text- und Auswahlparameter (je eine Zeile, siehe Dateikopf). */
const STRING_DEFAULTS = {
  tcp_name: 'FGC_30GUT',
  dialect: 'v2',
};

type StringKey = keyof typeof STRING_DEFAULTS;
type StringParamDef = TextParamDef | ChoiceParamDef;

/** Text- und Auswahlparameter, nach Feldnamen; `key` und `default` ergänzt `withKey`. */
const STRING_PARAMS: { dialect: Omit<ChoiceParamDef, 'key' | 'default'>; tcp_name: Omit<TextParamDef, 'key' | 'default'> } = {
  dialect: {
    kind: 'choice',
    label: 'DRL-Dialekt',
    group: 'control',
    basic: true,
    assumption: false,
    hint: 'v2 für Firmware 2.x, v3 für Firmware 3.x',
    options: [
      { value: 'v2', label: 'v2' },
      { value: 'v3', label: 'v3' },
    ],
    short: 'DRL',
  },
  tcp_name: {
    kind: 'text',
    label: 'Werkzeugname (TCP)',
    group: 'control',
    basic: false,
    assumption: true,
    hint: 'muss am Teach Pendant angelegt sein',
  },
};

function withKey(name: StringKey): StringParamDef {
  return { ...STRING_PARAMS[name], key: name, default: STRING_DEFAULTS[name] };
}

/** Alle Parameter, die das Panel zeigt (Zahlen, dann Dialekt und Werkzeugname). */
export const PARAMS: readonly ParamDef[] = [
  ...NUM_PARAMS.map((d) => ({ ...d, kind: 'number' as const })),
  withKey('dialect'),
  withKey('tcp_name'),
];

export const DEFAULT_PARAMS: ParamValues = Object.fromEntries(PARAMS.map((d) => [d.key, d.default]));

export function changedKeys(values: ParamValues): string[] {
  return Object.keys(DEFAULT_PARAMS).filter((k) => values[k] !== DEFAULT_PARAMS[k]);
}

export function isChanged(def: ParamDef, values: ParamValues): boolean {
  return values[def.key] !== def.default;
}

/** Anzahl geänderter Einstellungen unter `defs`; die beiden Koordinaten des Druckplatzes zählen als eine. */
export function countChanged(defs: readonly ParamDef[], values: ParamValues): number {
  const changed = defs.filter((d) => isChanged(d, values));
  const spots = changed.filter((d) => d.kind === 'number' && d.spot).length;
  return changed.length - Math.max(0, spots - 1);
}

/** Stabiler Fingerabdruck für den Veraltet-Vergleich. */
export function paramsKey(values: ParamValues): string {
  return JSON.stringify(
    Object.keys(values)
      .sort()
      .map((k) => [k, values[k]]),
  );
}

export function groupTitle(id: ParamGroupId): string {
  return PARAM_GROUPS.find((g) => g.id === id)?.title ?? id;
}

// ---------------------------------------------------------------- Suche und Sichtbarkeit

/** Kleinbuchstaben ohne diakritische Zeichen: „Abstand“ findet auch „Abstände“. */
export function normalizeSearch(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();
}

/** Jedes Wort der Suche kommt im Label oder im Gruppentitel vor. Leere Suche passt immer. */
export function matchesSearch(def: ParamDef, query: string): boolean {
  const words = normalizeSearch(query).split(/\s+/).filter(Boolean);
  const text = normalizeSearch(`${def.label} ${groupTitle(def.group)}`);
  return words.every((w) => text.includes(w));
}

/** Eine nichtleere Suche gilt über alle Gruppen und ignoriert den Modus. */
export function visibleParams(mode: ParamMode, query: string): ParamDef[] {
  if (normalizeSearch(query)) return PARAMS.filter((d) => matchesSearch(d, query));
  return mode === 'all' ? [...PARAMS] : PARAMS.filter((d) => d.basic);
}

export interface GroupView {
  group: ParamGroup;
  params: ParamDef[];
  changed: number;
  summary: string;
}

/** Gruppen mit mindestens einem sichtbaren Parameter, in Panel-Reihenfolge. */
export function groupViews(mode: ParamMode, query: string, values: ParamValues): GroupView[] {
  const visible = visibleParams(mode, query);
  return PARAM_GROUPS.flatMap((group) => {
    const params = visible.filter((d) => d.group === group.id);
    if (!params.length) return [];
    return [{ group, params, changed: countChanged(params, values), summary: groupSummary(group, params, values) }];
  });
}

export interface HiddenInfo {
  /** Parameter, die nur unter „Alle“ stehen */
  count: number;
  /** davon gegenüber dem Standard geändert */
  changed: number;
  /** Gruppen mit versteckten Änderungen, zum Aufklappen nach dem Umschalten */
  changedGroups: ParamGroupId[];
}

/** Was im Modus „Grundlegend“ verborgen bleibt; bei Suche oder „Alle“ nichts. */
export function hiddenInfo(mode: ParamMode, query: string, values: ParamValues): HiddenInfo {
  if (mode === 'all' || normalizeSearch(query)) return { count: 0, changed: 0, changedGroups: [] };
  const hidden = PARAMS.filter((d) => !d.basic);
  const changed = hidden.filter((d) => isChanged(d, values));
  const changedGroups = PARAM_GROUPS.map((g) => g.id).filter((id) => changed.some((d) => d.group === id));
  return { count: hidden.length, changed: changed.length, changedGroups };
}

// ---------------------------------------------------------------- Anzeige von Werten

const num = (n: number) => n.toLocaleString('de-DE');

/** Einheit hinter einer Zahl; ohne Einheit das Label („2 Schalen“), Grad ohne Leerzeichen. */
function unitSuffix(def: NumParamDef): string {
  if (!def.unit) return ` ${def.label}`;
  return def.unit === '°' ? '°' : ` ${def.unit}`;
}

/** Wert mit Einheit, wie er hinter „Standard“ steht: „400 mm“, „2 Schalen“, „v2“. */
export function formatValue(def: ParamDef, value: ParamValue): string {
  if (def.kind === 'number') return `${typeof value === 'number' ? num(value) : String(value)}${unitSuffix(def)}`;
  if (def.kind === 'choice') return def.options.find((o) => o.value === value)?.label ?? String(value);
  return String(value) || 'leer';
}

/** Druckplatz aus den Werten (fehlende Koordinate: Standard). */
export function spotOf(values: ParamValues): Spot {
  const x = values.spot_x_mm ?? DEFAULT_PARAMS.spot_x_mm;
  const y = values.spot_y_mm ?? DEFAULT_PARAMS.spot_y_mm;
  return { x: typeof x === 'number' ? x : 0, y: typeof y === 'number' ? y : 0 };
}

/** Kurzfassung einer zugeklappten Gruppe: „10 mm · 30 mm · 2 Schalen“, „100 · 250 mm/s“, „DRL v2“.
 * Die beiden Koordinaten des Druckplatzes stehen zusammen als „Platz 50 mm vor der Tischmitte, mittig“. */
export function groupSummary(group: ParamGroup, defs: ParamDef[], values: ParamValues): string {
  const firstSpot = defs.find((d) => d.kind === 'number' && d.spot);
  const shown = defs.filter((d) => !(d.kind === 'number' && d.spot) || d === firstSpot);
  const pieces = shown.map((d) => {
    if (d === firstSpot) return { value: `Platz ${describeSpot(spotOf(values))}`, suffix: '', unit: '' };
    const v = values[d.key] ?? d.default;
    if (d.kind === 'number') return { value: typeof v === 'number' ? num(v) : String(v), suffix: unitSuffix(d), unit: d.unit };
    if (d.kind === 'choice') return { value: `${d.short ?? d.label} ${formatValue(d, v)}`, suffix: '', unit: '' };
    return { value: formatValue(d, v), suffix: '', unit: '' };
  });
  return pieces
    .map((p, i) => {
      const next = pieces[i + 1];
      const join = group.joinUnits && p.unit && next?.unit === p.unit;
      return join ? p.value : p.value + p.suffix;
    })
    .join(' · ');
}

/** Zweite Zeile unter dem Label: bei Änderung der Standardwert, sonst der Hinweis. */
export function secondaryLine(def: ParamDef, values: ParamValues): string | null {
  if (isChanged(def, values)) return `Standard ${formatValue(def, def.default)}`;
  return def.hint ?? (def.provisional ? 'vorläufig' : null);
}

/** Zugänglicher Text des Kennzeichens „A“. */
export function assumptionText(def: ParamDef): string {
  return def.provisional ? 'Annahme, vorläufig' : 'Annahme';
}

/** ⌊Modulhöhe / Schichthöhe⌋, wenn beide > 0 sind. */
export function layersPerModule(values: ParamValues): number | null {
  const h = values.module_height_max_mm;
  const l = values.layer_height_mm;
  if (typeof h !== 'number' || typeof l !== 'number' || !(h > 0) || !(l > 0)) return null;
  return Math.floor(h / l + 1e-9);
}
