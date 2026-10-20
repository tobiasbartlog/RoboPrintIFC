import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  DEFAULT_PARAMS,
  PARAMS,
  PARAM_GROUPS,
  changedKeys,
  formatValue,
  groupSummary,
  groupViews,
  hiddenInfo,
  layersPerModule,
  matchesSearch,
  secondaryLine,
  visibleParams,
  type ParamDef,
  type ParamGroupId,
} from './params';

const byKey = (key: string): ParamDef => {
  const d = PARAMS.find((p) => p.key === key);
  if (!d) throw new Error(key);
  return d;
};
const group = (id: ParamGroupId) => PARAM_GROUPS.find((g) => g.id === id)!;
const keysOf = (defs: ParamDef[]) => defs.map((d) => d.key);

describe('Gruppenzuordnung', () => {
  it('ordnet jeden der 23 Parameter genau einer bekannten Gruppe zu', () => {
    expect(PARAMS).toHaveLength(23);
    expect(new Set(keysOf([...PARAMS])).size).toBe(23);
    const ids = new Set(PARAM_GROUPS.map((g) => g.id));
    for (const d of PARAMS) expect(ids.has(d.group)).toBe(true);
    for (const g of PARAM_GROUPS) expect(PARAMS.some((d) => d.group === g.id)).toBe(true);
  });

  it('folgt der freigegebenen Zuordnung', () => {
    const groups = Object.fromEntries(PARAM_GROUPS.map((g) => [g.id, keysOf(PARAMS.filter((d) => d.group === g.id))]));
    expect(groups).toEqual({
      layer: ['layer_height_mm', 'bead_width_mm', 'shells'],
      module: ['module_height_max_mm', 'spot_x_mm', 'spot_y_mm'],
      speed: ['v_print_mm_s', 'v_travel_mm_s'],
      pump: ['v_pump_v', 't_tot_s'],
      motion: ['z_lift_mm', 'approach_mm', 'r_blend_mm', 'tau_max_deg'],
      clearance: ['d_hard_mm', 'd_target_mm', 'd_target_printed_mm', 'r_free_mm'],
      planning: ['psi_step_deg', 'step_mm', 'dq_max_rad'],
      control: ['dialect', 'tcp_name'],
    });
  });

  it('behält Schlüssel und Standardwerte, die der Kern liest', () => {
    expect(DEFAULT_PARAMS.tcp_name).toBe('FGC_30GUT');
    expect(DEFAULT_PARAMS.dialect).toBe('v2');
    expect(DEFAULT_PARAMS.module_height_max_mm).toBe(400);
    expect([DEFAULT_PARAMS.spot_x_mm, DEFAULT_PARAMS.spot_y_mm]).toEqual([0, -50]);
    expect(Object.keys(DEFAULT_PARAMS)).toHaveLength(23);
  });

  it('bleibt für den Kerntest test_web_default_params_accepted lesbar', () => {
    // Gleiche regulären Ausdrücke wie core/tests/test_api.py.
    const src = readFileSync(resolve(__dirname, 'params.ts'), 'utf-8');
    const parsed: Record<string, number | string> = {};
    for (const m of src.matchAll(/key: '(\w+)'[^}]*?default: (-?[\d.]+)/g)) parsed[m[1]!] = Number(m[2]);
    for (const m of src.matchAll(/^\s+(tcp_name|dialect): '([^']*)'/gm)) parsed[m[1]!] = m[2]!;
    expect(Object.keys(parsed)).toHaveLength(src.split("key: '").length - 1 + 2);
    expect(parsed).toEqual(DEFAULT_PARAMS);
  });
});

describe('Sichtbarkeit je Modus', () => {
  it('zeigt unter „Grundlegend“ 11 von 23 Parametern', () => {
    expect(keysOf(visibleParams('basic', ''))).toEqual([
      'layer_height_mm',
      'bead_width_mm',
      'module_height_max_mm',
      'spot_x_mm',
      'spot_y_mm',
      'shells',
      'v_print_mm_s',
      'v_travel_mm_s',
      'v_pump_v',
      't_tot_s',
      'dialect',
    ]);
    expect(visibleParams('all', '')).toHaveLength(23);
  });

  it('blendet Gruppen ohne grundlegende Parameter aus', () => {
    expect(groupViews('basic', '', DEFAULT_PARAMS).map((v) => v.group.id)).toEqual(['layer', 'module', 'speed', 'pump', 'control']);
    expect(groupViews('all', '', DEFAULT_PARAMS).map((v) => v.group.id)).toEqual(PARAM_GROUPS.map((g) => g.id));
    const control = groupViews('basic', '', DEFAULT_PARAMS).find((v) => v.group.id === 'control')!;
    expect(keysOf(control.params)).toEqual(['dialect']);
  });

  it('zählt Änderungen je Gruppe nur über die gezeigten Parameter', () => {
    const values = { ...DEFAULT_PARAMS, v_print_mm_s: 80, tcp_name: 'X' };
    const views = groupViews('basic', '', values);
    expect(views.find((v) => v.group.id === 'speed')!.changed).toBe(1);
    expect(views.find((v) => v.group.id === 'control')!.changed).toBe(0);
    expect(groupViews('all', '', values).find((v) => v.group.id === 'control')!.changed).toBe(1);
  });
});

describe('versteckte Änderungen', () => {
  it('zählt die Parameter, die nur unter „Alle“ stehen', () => {
    expect(hiddenInfo('basic', '', DEFAULT_PARAMS)).toEqual({ count: 12, changed: 0, changedGroups: [] });
  });

  it('zählt geänderte versteckte Parameter und nennt ihre Gruppen', () => {
    const values = { ...DEFAULT_PARAMS, d_hard_mm: 15, r_free_mm: 50, tcp_name: 'X', v_print_mm_s: 80 };
    expect(hiddenInfo('basic', '', values)).toEqual({ count: 12, changed: 3, changedGroups: ['clearance', 'control'] });
    expect(changedKeys(values)).toHaveLength(4);
  });

  it('verbirgt nichts unter „Alle“ oder bei einer Suche', () => {
    const values = { ...DEFAULT_PARAMS, d_hard_mm: 15 };
    expect(hiddenInfo('all', '', values).count).toBe(0);
    expect(hiddenInfo('basic', 'abstand', values)).toEqual({ count: 0, changed: 0, changedGroups: [] });
  });
});

describe('Suche', () => {
  it('findet über Label und Gruppentitel, ohne Groß- und Kleinschreibung und Umlaute', () => {
    // „Abstand“ trifft Labels mit „abstand“ und die Gruppe „Abstände“ (Freiraumradius).
    expect(keysOf(visibleParams('basic', 'Abstand'))).toEqual([
      'd_hard_mm',
      'd_target_mm',
      'd_target_printed_mm',
      'r_free_mm',
      'step_mm',
    ]);
    expect(keysOf(visibleParams('basic', 'pumpe'))).toEqual(['v_pump_v', 't_tot_s']);
    expect(keysOf(visibleParams('basic', 'DUSE'))).toEqual(['tau_max_deg']);
  });

  it('ignoriert den Modus und verlangt jedes Wort', () => {
    expect(keysOf(visibleParams('basic', 'soll druckstand'))).toEqual(['d_target_printed_mm']);
    expect(visibleParams('all', 'gibt es nicht')).toEqual([]);
    expect(visibleParams('basic', '   ')).toHaveLength(11);
    expect(matchesSearch(byKey('tcp_name'), 'steuerung')).toBe(true);
  });

  it('liefert nur Gruppen mit Treffern', () => {
    expect(groupViews('basic', 'geschwindigkeit', DEFAULT_PARAMS).map((v) => v.group.id)).toEqual(['speed']);
    expect(groupViews('basic', 'xyz', DEFAULT_PARAMS)).toEqual([]);
  });
});

describe('Kurzfassung und Werte', () => {
  it('fasst zugeklappte Gruppen zusammen', () => {
    const v = { ...DEFAULT_PARAMS, v_print_mm_s: 80 };
    const sum = (id: ParamGroupId) => groupSummary(group(id), PARAMS.filter((d) => d.group === id), v);
    expect(sum('layer')).toBe('10 mm · 30 mm · 2 Schalen');
    expect(sum('speed')).toBe('80 · 250 mm/s');
    expect(sum('pump')).toBe('5 V · 3 s');
    expect(sum('motion')).toBe('30 mm · 20 mm · 2 mm · 0°');
    expect(sum('planning')).toBe('15° · 20 mm · 0,3 rad');
    expect(groupSummary(group('control'), [byKey('dialect')], v)).toBe('DRL v2');
    expect(sum('control')).toBe('DRL v2 · FGC_30GUT');
  });

  it('fasst den Druckplatz als eine Angabe zusammen', () => {
    const sum = (v: typeof DEFAULT_PARAMS) => groupSummary(group('module'), PARAMS.filter((d) => d.group === 'module'), v);
    expect(sum(DEFAULT_PARAMS)).toBe('400 mm · Platz 50 mm vor der Tischmitte, mittig');
    expect(sum({ ...DEFAULT_PARAMS, spot_x_mm: 200, spot_y_mm: 0 })).toBe('400 mm · Platz Tischmitte, 200 mm rechts');
    expect(groupSummary(group('module'), [byKey('spot_y_mm')], DEFAULT_PARAMS)).toBe('Platz 50 mm vor der Tischmitte, mittig');
  });

  it('setzt die Kurzfassung in groupViews aus den gezeigten Parametern', () => {
    expect(groupViews('basic', '', DEFAULT_PARAMS).find((g) => g.group.id === 'control')!.summary).toBe('DRL v2');
  });

  it('formatiert Werte deutsch mit Einheit', () => {
    expect(formatValue(byKey('module_height_max_mm'), 400)).toBe('400 mm');
    expect(formatValue(byKey('v_pump_v'), 5.5)).toBe('5,5 V');
    expect(formatValue(byKey('psi_step_deg'), 15)).toBe('15°');
    expect(formatValue(byKey('dialect'), 'v3')).toBe('v3');
    expect(formatValue(byKey('tcp_name'), '')).toBe('leer');
  });

  it('zeigt bei Änderung den Standard, sonst den Hinweis', () => {
    expect(secondaryLine(byKey('module_height_max_mm'), { ...DEFAULT_PARAMS, module_height_max_mm: 600 })).toBe('Standard 400 mm');
    expect(secondaryLine(byKey('bead_width_mm'), DEFAULT_PARAMS)).toBe('Düse 30gut');
    expect(secondaryLine(byKey('t_tot_s'), DEFAULT_PARAMS)).toBe('vorläufig');
    expect(secondaryLine(byKey('t_tot_s'), { ...DEFAULT_PARAMS, t_tot_s: 4 })).toBe('Standard 3 s');
    expect(secondaryLine(byKey('step_mm'), DEFAULT_PARAMS)).toBeNull();
  });

  it('rechnet Schichten je Modul nur mit positiven Werten', () => {
    expect(layersPerModule(DEFAULT_PARAMS)).toBe(40);
    expect(layersPerModule({ ...DEFAULT_PARAMS, module_height_max_mm: 395 })).toBe(39);
    expect(layersPerModule({ ...DEFAULT_PARAMS, module_height_max_mm: 0.3, layer_height_mm: 0.1 })).toBe(3);
    expect(layersPerModule({ ...DEFAULT_PARAMS, layer_height_mm: 0 })).toBeNull();
    expect(layersPerModule({ ...DEFAULT_PARAMS, module_height_max_mm: -1 })).toBeNull();
  });
});
