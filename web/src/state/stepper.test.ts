import { DEFAULT_PARAMS } from './params';
import { isRunStale, makeBasis, nextStep, stepBlockedReason, stepStatuses, type StepInputs } from './stepper';

const base: StepInputs = { projectId: null, wallId: null, params: { ...DEFAULT_PARAMS }, runBasis: null };

describe('Stepper-Logik', () => {
  it('ohne Projekt fehlt alles, Folgeschritte sind mit Grund gesperrt', () => {
    expect(stepStatuses(base)).toEqual({ model: 'fehlt', decompose: 'fehlt', simulation: 'fehlt', export: 'fehlt' });
    expect(stepBlockedReason('decompose', base)).toMatch(/Modell/);
    expect(stepBlockedReason('simulation', base)).toMatch(/zerlegen/);
  });

  it('Wand gewählt: Modell aktuell, Zerlegen frei', () => {
    const i = { ...base, projectId: 'p', wallId: 'w' };
    expect(stepStatuses(i).model).toBe('aktuell');
    expect(stepBlockedReason('decompose', i)).toBeNull();
  });

  it('Lauf mit passender Basis ist aktuell; Wandwechsel macht ihn veraltet', () => {
    const i: StepInputs = { projectId: 'p', wallId: 'w', params: { ...DEFAULT_PARAMS }, runBasis: makeBasis('p', 'w', DEFAULT_PARAMS) };
    expect(stepStatuses(i)).toMatchObject({ decompose: 'aktuell', simulation: 'aktuell', export: 'aktuell' });
    const stale = { ...i, wallId: 'v' };
    expect(isRunStale(stale)).toBe(true);
    expect(stepStatuses(stale)).toMatchObject({ decompose: 'veraltet', simulation: 'veraltet', export: 'veraltet' });
  });

  it('Parameteränderung macht den Lauf veraltet, Zurücksetzen macht ihn wieder aktuell', () => {
    const i: StepInputs = { projectId: 'p', wallId: 'w', params: { ...DEFAULT_PARAMS }, runBasis: makeBasis('p', 'w', DEFAULT_PARAMS) };
    expect(isRunStale({ ...i, params: { ...DEFAULT_PARAMS, v_print_mm_s: 120 } })).toBe(true);
    expect(isRunStale({ ...i, params: { ...DEFAULT_PARAMS } })).toBe(false);
  });

  it('direkt geöffneter Lauf: Zerlegen ist ohne Modell betretbar (kein Grün auf gesperrtem Schritt)', () => {
    const i: StepInputs = { ...base, runBasis: { projectId: '', wallId: '', paramsKey: '', direct: true } };
    expect(stepStatuses(i)).toMatchObject({ model: 'fehlt', decompose: 'aktuell' });
    expect(stepBlockedReason('decompose', i)).toBeNull();
  });

  it('nextStep', () => {
    expect(nextStep('model')).toBe('decompose');
    expect(nextStep('export')).toBeNull();
  });
});
