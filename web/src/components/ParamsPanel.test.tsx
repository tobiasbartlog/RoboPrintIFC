import { MantineProvider } from '@mantine/core';
import { act, createEvent, fireEvent, render, screen } from '@testing-library/react';
import { createFakeApi } from '../state/fakeApi';
import { createAppStore, type AppStore } from '../state/store';
import { StoreProvider } from '../state/storeContext';
import { ParamsPanel } from './ParamsPanel';

function setup(): AppStore {
  const store = createAppStore(createFakeApi());
  render(
    <MantineProvider>
      <StoreProvider store={store}>
        <ParamsPanel />
      </StoreProvider>
    </MantineProvider>,
  );
  return store;
}

const groupOpen = (id: string) => screen.getByTestId(`param-group-${id}`).getAttribute('aria-expanded') === 'true';

describe('ParamsPanel', () => {
  it('startet in „Grundlegend“ mit zugeklappten Gruppen und Kurzfassung', () => {
    setup();
    expect(screen.getByTestId('param-group-layer')).toBeInTheDocument();
    expect(screen.queryByTestId('param-group-clearance')).toBeNull();
    expect(groupOpen('layer')).toBe(false);
    expect(screen.getByTestId('param-summary-layer')).toHaveTextContent('10 mm · 30 mm · 2 Schalen');
    expect(screen.getByTestId('param-summary-control')).toHaveTextContent('DRL v2');
    expect(screen.getByTestId('param-hidden-note')).toHaveTextContent('10 weitere Parameter unter „Alle“');
    expect(screen.queryByTestId('params-reset-all')).toBeNull();
    expect(screen.getByTestId('param-assumption-t_tot_s')).toHaveTextContent('vorläufig');
  });

  it('markiert Änderungen, zählt versteckte und schaltet über den Hinweis auf „Alle“', () => {
    const store = setup();
    act(() => {
      store.getState().setParam('d_hard_mm', 15);
      store.getState().setParam('v_print_mm_s', 80);
    });
    expect(screen.getByTestId('params-changed-count')).toHaveTextContent('2 geändert');
    expect(screen.getByTestId('param-group-changed-speed')).toHaveTextContent('1 geändert');
    expect(screen.getByTestId('param-row-v_print_mm_s')).toHaveAttribute('data-changed', 'true');
    expect(screen.getByTestId('param-note-v_print_mm_s')).toHaveTextContent('Standard 100 mm/s');
    expect(screen.getByTestId('param-hidden-changed')).toHaveTextContent('1 geändert');

    fireEvent.click(screen.getByTestId('param-hidden-note'));
    expect(screen.queryByTestId('param-hidden-note')).toBeNull();
    expect(groupOpen('clearance')).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Mindestabstand hart auf Standard zurücksetzen' }));
    expect(store.getState().params.d_hard_mm).toBe(10);
    fireEvent.click(screen.getByTestId('params-reset-all'));
    expect(store.getState().params.v_print_mm_s).toBe(100);
    expect(screen.queryByTestId('params-changed-count')).toBeNull();
  });

  it('sucht über alle Gruppen, klappt Treffer auf und meldet leere Ergebnisse', () => {
    setup();
    fireEvent.change(screen.getByTestId('param-search'), { target: { value: 'Abstand' } });
    expect(screen.getByTestId('param-search-result')).toHaveTextContent('5 Treffer');
    expect(groupOpen('clearance')).toBe(true);
    expect(groupOpen('planning')).toBe(true);
    expect(screen.queryByTestId('param-group-layer')).toBeNull();
    expect(screen.queryByTestId('param-hidden-note')).toBeNull();

    fireEvent.change(screen.getByTestId('param-search'), { target: { value: 'Quark' } });
    expect(screen.getByTestId('param-search-result')).toHaveTextContent('Kein Parameter passt zu „Quark“.');

    fireEvent.click(screen.getByTestId('param-search-clear'));
    expect(screen.queryByTestId('param-search-result')).toBeNull();
    expect(groupOpen('layer')).toBe(false);
  });

  it('zeigt die Schichten je Modul', () => {
    setup();
    fireEvent.click(screen.getByTestId('param-group-module'));
    expect(screen.getByTestId('param-module-layers')).toHaveTextContent('Ergibt bis zu 40 Schichten je Modul.');
  });

  it('wählt den Druckplatz in der Draufsicht und setzt ihn zurück', () => {
    const store = setup();
    fireEvent.click(screen.getByTestId('param-group-module'));
    const field = screen.getByTestId('spot-field');
    expect(screen.getByTestId('spot-desc')).toHaveTextContent('50 mm vor der Tischmitte, mittig · 535 mm vor der Roboterachse · Standard, empfohlen');
    fireEvent.keyDown(field, { key: 'ArrowRight' });
    fireEvent.keyDown(field, { key: 'ArrowDown' });
    expect([store.getState().params.spot_x_mm, store.getState().params.spot_y_mm]).toEqual([50, -100]);
    expect(screen.getByTestId('spot-desc')).toHaveTextContent('100 mm vor der Tischmitte, 50 mm rechts · 585 mm vor der Roboterachse');
    expect(screen.getByTestId('spot-picker')).toHaveAttribute('data-changed', 'true');
    expect(screen.getByTestId('param-group-changed-module')).toHaveTextContent('1 geändert');
    expect(screen.getByTestId('params-changed-count')).toHaveTextContent('1 geändert');
    // Klick links oben auf das Feld: nächster Rastpunkt ist die linke hintere Ecke (Tischmitte, 200 mm links)
    field.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1680, height: 1330, right: 1680, bottom: 1330, x: 0, y: 0, toJSON: () => ({}) });
    const down = createEvent.pointerDown(field, { pointerId: 1 });
    Object.defineProperties(down, { clientX: { value: 0 }, clientY: { value: 0 } }); // jsdom kennt kein PointerEvent
    fireEvent(field, down);
    expect([store.getState().params.spot_x_mm, store.getState().params.spot_y_mm]).toEqual([-200, 0]);
    fireEvent.click(screen.getByTestId('spot-reset'));
    expect([store.getState().params.spot_x_mm, store.getState().params.spot_y_mm]).toEqual([0, -50]);
    expect(screen.queryByTestId('spot-reset')).toBeNull();
  });

  it('findet den Druckplatz über die Suche und zeigt ihn einmal', () => {
    setup();
    fireEvent.change(screen.getByTestId('param-search'), { target: { value: 'druckplatz' } });
    expect(screen.getByTestId('param-search-result')).toHaveTextContent('2 Treffer');
    expect(screen.getAllByTestId('spot-picker')).toHaveLength(1);
  });
});
