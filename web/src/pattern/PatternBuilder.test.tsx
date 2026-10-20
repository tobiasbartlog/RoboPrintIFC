import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from '../App';
import { createFakeApi } from '../state/fakeApi';
import { createFakePatternApi } from '../state/fakePatternApi';
import { createPatternStore } from '../state/patternStore';

function setup(opts?: Parameters<typeof createFakePatternApi>[0]) {
  const api = createFakePatternApi(opts);
  const patternStore = createPatternStore(api, { debounceMs: 0 });
  render(<App api={createFakeApi()} patternApi={api} patternStore={patternStore} initialView="pattern" />);
  return { api, patternStore };
}

describe('Musterersteller', () => {
  it('ist über den Reiter „Muster“ erreichbar und zeichnet die Vorschau', async () => {
    const { patternStore } = setup();
    expect(screen.getByTestId('view-pattern')).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByTestId('pattern-svg')).toBeInTheDocument();
    expect(patternStore.getState().catalog).not.toBeNull();
    // Strang nach Segmentart, Start/Ende, Kontakte, Legende mit den vorhandenen Arten
    expect(screen.getByTestId('pat-segment-outer')).toBeInTheDocument();
    expect(screen.getByTestId('pat-segment-web')).toBeInTheDocument();
    expect(screen.getByTestId('pat-start')).toBeInTheDocument();
    expect(screen.getByTestId('pat-end')).toBeInTheDocument();
    expect(screen.getByTestId('pat-contact-joint')).toBeInTheDocument();
    expect(screen.getByTestId('pat-next-layer')).toBeInTheDocument();
    expect(screen.getByTestId('legend-kind-web')).toHaveTextContent('Steg');
    expect(screen.getByTestId('legend-contact-joint')).toHaveTextContent('Fuge');
    expect(screen.getByTestId('pattern-rules-ok')).toBeInTheDocument();
    expect(screen.getByTestId('pat-stat-length')).toHaveTextContent('1,08 m');
    expect(screen.getByTestId('pat-stat-joints')).toHaveTextContent('2 × 240 mm');
    expect(screen.getByTestId('pat-stat-coverage')).toHaveTextContent('95 %');
    expect(screen.getByTestId('pattern-fit-0')).toHaveTextContent('3 Felder à 200 mm');
  });

  it('Regler mit Einheit und Bereich aus den ParamSpecs; Änderung erneuert die Vorschau', async () => {
    const { api } = setup();
    await screen.findByTestId('pattern-svg');
    const row = screen.getByTestId('pat-param-bead_width_mm');
    expect(row).toHaveTextContent('Strangbreite w');
    expect(row).toHaveTextContent('(mm)');
    const slider = within(row).getByRole('slider');
    expect(slider).toHaveAttribute('aria-valuemin', '10');
    expect(slider).toHaveAttribute('aria-valuemax', '60');
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    await waitFor(() => expect(api.requests.at(-1)?.params).toEqual({ bead_width_mm: 31 }));
    await waitFor(() => expect(screen.getByTestId('pat-param-bead_width_mm-reset')).toBeVisible());
    // Zurücksetzen nimmt die Änderung zurück
    fireEvent.click(screen.getByTestId('pat-param-bead_width_mm-reset'));
    await waitFor(() => expect(api.requests.at(-1)?.params).toEqual({}));
  });

  it('Verstöße erscheinen rot markiert und in der Liste', async () => {
    const { patternStore } = setup();
    await screen.findByTestId('pattern-svg');
    patternStore.getState().setParam('bead_width_mm', 55);
    const item = await screen.findByTestId('pattern-violation-0');
    expect(item).toHaveTextContent('M6');
    expect(item).toHaveTextContent('Druckbar gekrümmt');
    expect(screen.getByTestId('pat-violation-mark')).toBeInTheDocument();
    expect(screen.getByTestId('pattern-rules-bad')).toHaveTextContent('0 Fehler, 1 Warnung');
  });

  it('Serverfehler in Klartext, letzte Vorschau fehlt dann noch', async () => {
    setup({ previewError: 'Strangbreite darf höchstens 60 sein' });
    expect(await screen.findByTestId('pattern-error')).toHaveTextContent('höchstens 60');
  });

  it('Speichern verlangt einen Namen und nennt den Grund daneben', async () => {
    const { api } = setup();
    await screen.findByTestId('pattern-svg');
    expect(screen.getByTestId('pattern-save-button')).toBeDisabled();
    expect(screen.getByTestId('pattern-save-reason')).toHaveTextContent('Namen');
    fireEvent.change(screen.getByTestId('pattern-save-name'), { target: { value: 'Fugenwand 240' } });
    fireEvent.click(screen.getByTestId('pattern-save-button'));
    expect(await screen.findByTestId('pattern-saved')).toHaveTextContent('Fugenwand 240');
    expect(api.presets).toHaveLength(1);
  });

  it('Serverfehler (kein 422): Klartext mit Handlung, Rohtext nur im Detail, Neu-Anfordern hilft', async () => {
    const { api } = setup();
    await screen.findByTestId('pattern-svg');
    const original = api.preview.bind(api);
    api.preview = async () => {
      throw new TypeError('Failed to fetch');
    };
    fireEvent.keyDown(within(screen.getByTestId('pat-param-bead_width_mm')).getByRole('slider'), { key: 'ArrowRight' });
    const box = await screen.findByTestId('pattern-error');
    expect(box).toHaveAttribute('data-kind', 'server');
    expect(box).toHaveTextContent('Ist er gestartet?');
    // Die letzte gültige Vorschau bleibt stehen, ihr Regelstatus ist nicht mehr grün
    expect(screen.getByTestId('pattern-svg')).toBeInTheDocument();
    expect(screen.getByTestId('pattern-rules-ok')).toHaveAttribute('data-stale', 'true');
    api.preview = original;
    fireEvent.click(screen.getByTestId('pattern-retry'));
    await waitFor(() => expect(screen.queryByTestId('pattern-error')).toBeNull());
    expect(screen.getByTestId('pattern-rules-ok')).toHaveAttribute('data-stale', 'false');
  });

  it('Katalogfehler: Grund an der Musterwahl, Neu-Laden holt den Katalog', async () => {
    const api = createFakePatternApi();
    const getCatalog = api.getCatalog.bind(api);
    api.getCatalog = async () => {
      throw new TypeError('Failed to fetch');
    };
    render(<App api={createFakeApi()} patternApi={api} patternStore={createPatternStore(api, { debounceMs: 0 })} initialView="pattern" />);
    expect(await screen.findByTestId('pattern-catalog-error')).toBeInTheDocument();
    expect(screen.getByTestId('pattern-select-reason')).toHaveTextContent('Katalog');
    api.getCatalog = getCatalog;
    fireEvent.click(screen.getByTestId('pattern-catalog-retry'));
    expect(await screen.findByTestId('pattern-svg')).toBeInTheDocument();
    expect(screen.queryByTestId('pattern-catalog-error')).toBeNull();
    expect(screen.queryByTestId('pattern-select-reason')).toBeNull();
  });

  it('Zwischenstände beim Tippen gehen nicht an den Kern', async () => {
    const { api } = setup();
    await screen.findByTestId('pattern-svg');
    const n = api.requests.length;
    const input = screen.getByTestId('pat-param-bead_width_mm-input');
    // Bereich 10–60: „5“ ist ein Zwischenstand auf dem Weg zu 55
    fireEvent.change(input, { target: { value: '5' } });
    await new Promise((r) => setTimeout(r, 20));
    expect(api.requests.length).toBe(n);
    fireEvent.change(input, { target: { value: '55' } });
    await waitFor(() => expect(api.requests.at(-1)?.params).toEqual({ bead_width_mm: 55 }));
    // Modullänge ebenso (Bereich 100–20000)
    const len = screen.getByTestId('pattern-length');
    const m = api.requests.length;
    fireEvent.change(len, { target: { value: '9' } });
    await new Promise((r) => setTimeout(r, 20));
    expect(api.requests.length).toBe(m);
    fireEvent.change(len, { target: { value: '900' } });
    await waitFor(() => expect(api.requests.at(-1)?.outline).toEqual({ length_mm: 900, thickness_mm: 200 }));
  });

  it('Auswahl eines Verstoßes ist per aria-pressed erkennbar und gilt nur für diese Vorschau', async () => {
    const { patternStore } = setup();
    await screen.findByTestId('pattern-svg');
    patternStore.getState().setParam('bead_width_mm', 55);
    const item = await screen.findByTestId('pattern-violation-0');
    expect(item).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(item);
    expect(screen.getByTestId('pattern-violation-0')).toHaveAttribute('aria-pressed', 'true');
    patternStore.getState().setParam('bead_width_mm', 56);
    await waitFor(() => expect(patternStore.getState().preview?.params.bead_width_mm).toBe(56));
    await waitFor(() => expect(screen.getByTestId('pattern-violation-0')).toHaveAttribute('aria-pressed', 'false'));
  });
});
