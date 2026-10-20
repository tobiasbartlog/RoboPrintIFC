import type { PatternCatalog } from '../contracts';
import { createFakePatternApi } from './fakePatternApi';
import { createFakeApi } from './fakeApi';
import {
  choiceForSelection,
  choiceFromBuilder,
  choiceLabel,
  choiceSummary,
  DEFAULT_PATTERN,
  isDefaultPattern,
  jobPatternParams,
  patternChanged,
  selectionOf,
} from './patternChoice';
import { createAppStore, selectStatuses } from './store';

/** Katalog der Fake-API, ergänzt um ein Infill-Muster und ein mitgeliefertes Preset. */
async function catalog(): Promise<PatternCatalog> {
  const base = await createFakePatternApi().getCatalog();
  return {
    ...base,
    patterns: [
      ...base.patterns,
      { name: 'sinus', role: 'infill', label: 'Sinuswelle', description: '', family: 'wellen', layer_invariant: true, params: [] },
    ],
    presets: [
      {
        id: 'sinus',
        source: 'builtin',
        preset: {
          schema_version: 1,
          name: 'Sinuswelle',
          pattern: 'sinus',
          params: { bead_width_mm: 30, layer_order: 'alternate', wavelength_mm: 250, shells: 2 },
          outline: { length_mm: 600, thickness_mm: 200 },
          description: '',
        },
      },
    ],
  };
}

async function until(cond: () => boolean, ms = 3000) {
  const t0 = Date.now();
  while (!cond()) {
    if (Date.now() - t0 > ms) throw new Error('Zeitüberschreitung');
    await new Promise((r) => setTimeout(r, 5));
  }
}

describe('Musterwahl: reine Logik', () => {
  it('der Standard ist „kein Muster“ und schickt nichts mit', () => {
    expect(isDefaultPattern(DEFAULT_PATTERN)).toBe(true);
    expect(patternChanged(DEFAULT_PATTERN)).toBe(0);
    expect(selectionOf(DEFAULT_PATTERN)).toBe('none');
    expect(jobPatternParams(DEFAULT_PATTERN)).toEqual({});
  });

  it('Auswahl setzt genau das passende Feld; die Schichtfolge bleibt, Reglerwerte entfallen', () => {
    const cur = { ...DEFAULT_PATTERN, layer_order: 'same' as const, pattern_params: '{"a":1}' };
    expect(choiceForSelection('infill:sinus', cur)).toEqual({ ...DEFAULT_PATTERN, layer_order: 'same', infill_pattern: 'sinus' });
    expect(choiceForSelection('outfill:fugenwand', cur)).toMatchObject({ outfill_pattern: 'fugenwand', infill_pattern: 'none' });
    expect(choiceForSelection('preset:mein-muster', cur)).toMatchObject({ pattern_preset: 'mein-muster', pattern_params: '' });
    expect(choiceForSelection('none', cur)).toEqual({ ...DEFAULT_PATTERN, layer_order: 'same' });
    expect(selectionOf(choiceForSelection('infill:sinus', cur))).toBe('infill:sinus');
  });

  it('Jobparameter: nur Abweichungen, pattern_params als Objekt', () => {
    const c = { ...DEFAULT_PATTERN, layer_order: 'alternate' as const, infill_pattern: 'sinus', pattern_params: '{"wavelength_mm":200}' };
    expect(jobPatternParams(c)).toEqual({ layer_order: 'alternate', infill_pattern: 'sinus', pattern_params: { wavelength_mm: 200 } });
    expect(patternChanged(c)).toBe(3);
    // kaputter Text wird nicht gesendet
    expect(jobPatternParams({ ...DEFAULT_PATTERN, pattern_params: '{kaputt' })).toEqual({});
  });

  it('Übernahme aus dem Musterersteller: Rolle bestimmt den Platz, Basismuster ist kein Muster', async () => {
    const cat = await catalog();
    const infill = cat.patterns.find((p) => p.role === 'infill')!;
    const full = cat.patterns.find((p) => p.role === 'full' && p.name !== 'schalen');
    expect(choiceFromBuilder(cat, infill.name, null, {})).toEqual({ ...DEFAULT_PATTERN, infill_pattern: infill.name });
    if (full) expect(choiceFromBuilder(cat, full.name, null, {})).toMatchObject({ outfill_pattern: full.name, infill_pattern: 'none' });
    expect(choiceFromBuilder(cat, 'schalen', null, { shells: 3 })).toEqual(DEFAULT_PATTERN);
  });

  it('Übernahme: Regler nach pattern_params, Schichtfolge eigenes Feld, Druckeinstellungen bleiben dort', async () => {
    const cat = await catalog();
    const infill = cat.patterns.find((p) => p.role === 'infill')!;
    const c = choiceFromBuilder(cat, infill.name, null, { wavelength_mm: 180, layer_order: 'same', bead_width_mm: 40, step_mm: 10, link_max_mm: 5, layer_height_mm: 8, x: null });
    expect(c.layer_order).toBe('same');
    expect(JSON.parse(c.pattern_params)).toEqual({ wavelength_mm: 180 });
  });

  it('Übernahme eines Presets: nur Abweichungen vom Preset gehen mit', async () => {
    const cat = await catalog();
    const entry = cat.presets[0]!;
    const same = choiceFromBuilder(cat, entry.preset.pattern, entry.id, { ...entry.preset.params });
    expect(same.pattern_preset).toBe(entry.id);
    expect(same.pattern_params).toBe('');
    expect(same.layer_order).toBe('');
    const key = Object.keys(entry.preset.params).find((k) => typeof entry.preset.params[k] === 'number' && !['bead_width_mm', 'layer_height_mm', 'step_mm', 'link_max_mm'].includes(k))!;
    const changed = choiceFromBuilder(cat, entry.preset.pattern, entry.id, { ...entry.preset.params, [key]: (entry.preset.params[key] as number) + 1 });
    expect(JSON.parse(changed.pattern_params)).toEqual({ [key]: (entry.preset.params[key] as number) + 1 });
  });

  it('Beschriftung nennt Preset oder Muster in Klartext', async () => {
    const cat = await catalog();
    const entry = cat.presets[0]!;
    expect(choiceLabel({ ...DEFAULT_PATTERN, pattern_preset: entry.id }, cat)).toContain(entry.preset.name);
    expect(choiceLabel(DEFAULT_PATTERN, cat)).toBe('Kein Muster');
    expect(choiceSummary({ ...DEFAULT_PATTERN, layer_order: 'alternate', pattern_params: '{"a":1,"b":2}' }, cat)).toBe('Kein Muster · Schichtfolge wechselnd · 2 Regler geändert');
  });
});

describe('Musterwahl im Store', () => {
  async function ready() {
    const calls: unknown[] = [];
    const api = createFakeApi({ mode: 'ok', polls: 2 });
    const start = api.startJob.bind(api);
    api.startJob = async (projectId, request) => {
      calls.push(request);
      return start(projectId, request);
    };
    const store = createAppStore(api, { pollMs: 1 });
    await store.getState().openExample('fixture/run_demo');
    store.getState().selectWall('box');
    return { store, calls };
  }

  it('Standard: der Job trägt keinen Musterparameter (Verhalten wie heute)', async () => {
    const { store, calls } = await ready();
    await store.getState().startJob();
    const req = calls[0] as { params: Record<string, unknown> };
    for (const k of ['layer_order', 'infill_pattern', 'outfill_pattern', 'pattern_preset', 'pattern_params']) expect(req.params).not.toHaveProperty(k);
  });

  it('gewähltes Muster und Schichtfolge gehen in den Job; die Wahl macht den Lauf veraltet', async () => {
    const { store, calls } = await ready();
    await store.getState().startJob();
    await until(() => store.getState().run !== null);
    expect(selectStatuses(store.getState()).export).toBe('aktuell');
    store.getState().replacePatternChoice({ ...DEFAULT_PATTERN, infill_pattern: 'sinus', layer_order: 'alternate', pattern_params: '{"wavelength_mm":220}' });
    expect(selectStatuses(store.getState()).export).toBe('veraltet');
    store.getState().resetPatternChoice();
    expect(selectStatuses(store.getState()).export).toBe('aktuell');
    store.getState().replacePatternChoice({ ...DEFAULT_PATTERN, pattern_preset: 'fugenwand' });
    await store.getState().startJob();
    const req = calls[1] as { params: Record<string, unknown> };
    expect(req.params).toMatchObject({ pattern_preset: 'fugenwand' });
    expect(req.params).not.toHaveProperty('layer_order');
    await until(() => selectStatuses(store.getState()).export === 'aktuell');
  });

  it('lädt Kennzahlen und Schichten über die API und merkt sie sich je Lauf', async () => {
    const { store } = await ready();
    await store.getState().startJob();
    await until(() => store.getState().run !== null);
    await store.getState().loadPatternReport('P01');
    const key = `${store.getState().run!.runId}|P01`;
    expect(store.getState().patternReports[key]?.n_layers).toBe(5);
    const a = await store.getState().loadPatternLayer('P01', 2);
    const b = await store.getState().loadPatternLayer('P01', 2);
    expect(a).toBe(b);
    expect(a.layer).toBe(2);
  });
});
