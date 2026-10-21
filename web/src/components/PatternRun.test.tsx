import { act, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from '../App';
import type { PatternInfo } from '../contracts';
import { createFakeApi } from '../state/fakeApi';
import { createFakePatternApi } from '../state/fakePatternApi';
import { createPatternStore } from '../state/patternStore';
import { createAppStore } from '../state/store';

// Ganze App samt Mantine-Auswahllisten: unter Last (parallele Testdateien) länger als die üblichen 5 s.
vi.setConfig({ testTimeout: 30_000 });
configure({ asyncUtilTimeout: 15_000 });

/** Ablauf mit Musterwahl gegen die Fake-APIs: geprüft wird die Anbindung, nicht die Geometrie. */
function setup(tweak?: (api: ReturnType<typeof createFakeApi>) => void) {
  const api = createFakeApi({ mode: 'ok', polls: 2 });
  tweak?.(api);
  const jobs: { params: Record<string, unknown> }[] = [];
  const start = api.startJob.bind(api);
  api.startJob = async (projectId, request) => {
    jobs.push(request);
    return start(projectId, request);
  };
  const store = createAppStore(api, { pollMs: 1 });
  // Katalog der Fake-API, ergänzt um ein Infill-Muster
  const base = createFakePatternApi();
  const patternApi = {
    ...base,
    async getCatalog() {
      const cat = await base.getCatalog();
      const sinus: PatternInfo = {
        name: 'sinus',
        role: 'infill',
        label: 'Sinuswelle',
        description: 'Sinus zwischen den Innenschalen.',
        family: 'wellen',
        layer_invariant: true,
        params: [{ name: 'wavelength_mm', label: 'Wellenlänge', default: 250, unit: 'mm', minimum: 100, maximum: 500, step: 1, kind: 'float', choices: [], help: '' }],
      };
      return { ...cat, patterns: [...cat.patterns, sinus] };
    },
  };
  const patternStore = createPatternStore(patternApi, { debounceMs: 0 });
  render(<App store={store} patternApi={patternApi} patternStore={patternStore} />);
  return { store, patternStore, jobs };
}

async function toDecompose() {
  fireEvent.click(await screen.findByTestId('example-demo'));
  await screen.findByTestId('wall-reason-duenn');
  fireEvent.click(screen.getByTestId('wall-select-box'));
  fireEvent.click(screen.getByTestId('to-decompose'));
}

async function choose(label: string) {
  fireEvent.click(await screen.findByTestId('pattern-choice-select'));
  fireEvent.click(await screen.findByRole('option', { name: label }));
}

describe('Musterwahl im Ablauf', () => {
  it('Standard: kein Muster, Schichtfolge „Standard“, nichts als geändert markiert', async () => {
    const { store } = setup();
    await toDecompose();
    expect(screen.getByTestId('pattern-choice-select')).toHaveValue('Kein Muster (Standard)');
    expect(screen.queryByTestId('pattern-choice-changed')).toBeNull();
    expect(screen.queryByTestId('pattern-choice-reset')).toBeNull();
    expect(store.getState().patternChoice.infill_pattern).toBe('none');
  });

  it('Muster und Schichtfolge wählen: im Job, Lauf veraltet, Zurücksetzen auf Standard', async () => {
    const { store, jobs } = setup();
    await toDecompose();
    fireEvent.click(screen.getByTestId('start-job'));
    await waitFor(() => expect(screen.getByTestId('part-status-P01')).toHaveTextContent('machbar'));
    expect(screen.getByTestId('step-decompose')).toHaveAttribute('data-status', 'aktuell');

    await choose('Sinuswelle');
    expect(store.getState().patternChoice.infill_pattern).toBe('sinus');
    expect(screen.getByTestId('pattern-choice-changed')).toHaveTextContent('1 geändert');
    expect(screen.getByTestId('step-decompose')).toHaveAttribute('data-status', 'veraltet');
    fireEvent.click(within(screen.getByTestId('pattern-choice-order')).getByLabelText('wechselnd'));
    expect(store.getState().patternChoice.layer_order).toBe('alternate');
    expect(screen.getByTestId('pattern-choice-summary')).toHaveTextContent('Sinuswelle · Schichtfolge wechselnd');

    fireEvent.click(screen.getByTestId('start-job'));
    await waitFor(() => expect(jobs).toHaveLength(2));
    expect(jobs[1]?.params).toMatchObject({ infill_pattern: 'sinus', layer_order: 'alternate' });
    expect(jobs[0]?.params).not.toHaveProperty('infill_pattern');

    fireEvent.click(screen.getByTestId('pattern-choice-reset'));
    expect(store.getState().patternChoice.infill_pattern).toBe('none');
    expect(store.getState().patternChoice.layer_order).toBe('');
  });

  it('zeigt Kennzahlen und die Schichtvorschau des gewählten Teils, Schicht wählbar', async () => {
    setup();
    await toDecompose();
    fireEvent.click(screen.getByTestId('start-job'));
    const stats = await screen.findByTestId('pattern-stats-P01');
    expect(stats).toHaveAttribute('data-has-pattern', 'true');
    expect(screen.getByTestId('pattern-stats-name-P01')).toHaveTextContent('zickzack');
    expect(screen.getByTestId('pattern-stats-strands-P01')).toHaveTextContent('ein Strang (kein Absetzen)');
    expect(screen.getByTestId('pattern-stats-changes-P01')).toHaveTextContent('4 senkrecht');
    expect(screen.getByTestId('pattern-stats-kind-P01-infill')).toHaveTextContent('20 %');
    // Hinweise des Plans (meta) gehen nicht verloren: entfallenes Infill steht beim Teil
    expect(screen.getByTestId('pattern-stats-notes-P01')).toHaveTextContent('Infill entfällt');

    const svg = await screen.findByTestId('layer-preview-svg');
    expect(svg).toHaveAttribute('data-layer', '0');
    expect(screen.getByTestId('layer-label')).toHaveTextContent('Schicht 1 von 5');
    expect(screen.getByTestId('layer-start')).toBeInTheDocument();
    expect(screen.getByTestId('layer-end')).toBeInTheDocument();
    expect(screen.getByTestId('layer-neighbor')).toBeInTheDocument();
    expect(screen.getByTestId('layer-kind-infill')).toHaveTextContent('Infill');
    const first = within(svg).getByTestId('layer-path').querySelector('[data-kind]');
    expect(first?.getAttribute('data-kind')).toBe('outer');

    fireEvent.click(screen.getByTestId('layer-next'));
    await waitFor(() => expect(screen.getByTestId('layer-preview-svg')).toHaveAttribute('data-layer', '1'));
    // jede zweite Schicht läuft rückwärts (alternate): die Reihenfolge der Segmente kehrt sich um
    const second = screen.getByTestId('layer-path').querySelector('[data-kind]');
    expect(second?.getAttribute('data-kind')).toBe('infill');
    expect(screen.getByTestId('layer-prev')).toBeEnabled();
  });
});

describe('Fehlerzustände und Bedienbarkeit', () => {
  it('422 beim Anlegen: Klartext mit Handlung, die Meldung der API liegt im Detail', async () => {
    setup((api) => {
      api.startJob = () => Promise.reject(Object.assign(new Error('Muster-Preset „weg“ nicht gefunden. Anderes Muster wählen.'), { status: 422 }));
    });
    await toDecompose();
    fireEvent.click(screen.getByTestId('start-job'));
    const note = await screen.findByTestId('job-error');
    expect(note).toHaveTextContent('Die Einstellungen wurden abgelehnt. Druckmuster oder Parameter ändern');
    expect(note).not.toHaveTextContent('Verbindung prüfen');
    expect(screen.getByTestId('job-error-detail')).toHaveTextContent('Muster-Preset „weg“ nicht gefunden');
  });

  it('Schichtvorschau: Schieberegler mit Namen, Ladefehler in Nutzersprache mit ausklappbarem Detail', async () => {
    let fail = false;
    setup((api) => {
      const layer = api.patternLayer.bind(api);
      api.patternLayer = (runId, partId, n) => (fail && n > 0 ? Promise.reject(new Error('HTTP 500: Traceback')) : layer(runId, partId, n));
    });
    await toDecompose();
    fireEvent.click(screen.getByTestId('start-job'));
    await screen.findByTestId('layer-preview-svg');
    expect(screen.getByRole('slider', { name: 'Schicht wählen' })).toBeInTheDocument();
    fail = true;
    fireEvent.click(screen.getByTestId('layer-next'));
    const note = await screen.findByTestId('layer-error');
    expect(note).toHaveTextContent('Die Schicht konnte nicht geladen werden. Lauf neu rechnen');
    expect(screen.getByTestId('layer-error-toggle')).toBeInTheDocument();
    expect(screen.getByTestId('layer-error-detail')).toHaveTextContent('HTTP 500: Traceback');
  });

  it('Schichtfolge „Standard“ mit gespeichertem Muster nennt die Folge der Vorlage, nicht pauschal „wechselnd“', async () => {
    const { store } = setup();
    await toDecompose();
    act(() => store.getState().replacePatternChoice({ ...store.getState().patternChoice, pattern_preset: 'mein_muster' }));
    expect(screen.getByTestId('pattern-choice')).toHaveTextContent('Standard: Schichtfolge des gespeicherten Musters.');
  });
});

describe('Für Lauf verwenden', () => {
  it('übernimmt Muster und Regler aus dem Musterersteller und springt in „Zerlegen & prüfen“', async () => {
    const { store, patternStore } = setup();
    await toDecompose();
    fireEvent.click(screen.getByTestId('view-pattern'));
    await waitFor(() => expect(patternStore.getState().catalog).not.toBeNull());
    patternStore.getState().selectPattern('sinus');
    patternStore.getState().setParam('wavelength_mm', 180);
    patternStore.getState().setParam('layer_order', 'alternate');
    fireEvent.click(await screen.findByTestId('pattern-use-for-run'));
    expect(store.getState().patternChoice).toMatchObject({ infill_pattern: 'sinus', layer_order: 'alternate' });
    expect(JSON.parse(store.getState().patternChoice.pattern_params)).toEqual({ wavelength_mm: 180 });
    expect(store.getState().step).toBe('decompose');
    expect(screen.getByTestId('view-flow')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('pattern-choice-summary')).toHaveTextContent('Sinuswelle · Schichtfolge wechselnd · 1 Regler geändert');
  });

  it('ohne Modell führt der Weg in den Schritt „Modell“, die Wahl bleibt gesetzt', async () => {
    const { store, patternStore } = setup();
    fireEvent.click(await screen.findByTestId('view-pattern'));
    await waitFor(() => expect(patternStore.getState().catalog).not.toBeNull());
    expect(screen.getByTestId('pattern-use-hint')).toHaveTextContent('Modell und eine Wand');
    patternStore.getState().selectPattern('fugenwand');
    fireEvent.click(screen.getByTestId('pattern-use-for-run'));
    expect(store.getState().patternChoice.outfill_pattern).toBe('fugenwand');
    expect(store.getState().step).toBe('model');
  });
});
