import { MantineProvider } from '@mantine/core';
import { act, fireEvent, render, screen } from '@testing-library/react';
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
    expect(screen.getByTestId('param-hidden-note')).toHaveTextContent('12 weitere Parameter unter „Alle“');
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
});
