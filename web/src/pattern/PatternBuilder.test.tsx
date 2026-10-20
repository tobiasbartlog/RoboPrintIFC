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
});
