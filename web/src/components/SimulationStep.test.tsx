import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { PartEntry, Summary } from '../contracts';
import { createFakeApi } from '../state/fakeApi';
import { createAppStore, type AppStore } from '../state/store';
import { StoreProvider } from '../state/storeContext';
import { SimulationStep } from './SimulationStep';

const entry = (part_id: string, same_as: string | null = null): PartEntry => ({
  part_id,
  same_as,
  wall_id: 'w',
  status: 'machbar',
  d_min_mm: 12,
  n_collision: 0,
  n_unreachable: 0,
});

function setup(parts: PartEntry[], partId: string | null = null): AppStore {
  const store = createAppStore(createFakeApi());
  const summary = { parts, walls: [], scenario_id: 'test', assumptions: [], params: {} } as unknown as Summary;
  store.setState({
    run: { runId: 'r1', basis: { projectId: '', wallId: '', paramsKey: '', direct: true }, summary, parts: {}, trajectory: {} },
    partId,
    step: 'simulation',
  });
  render(
    <MantineProvider>
      <StoreProvider store={store}>
        <SimulationStep />
      </StoreProvider>
    </MantineProvider>,
  );
  return store;
}

describe('SimulationStep: Module gleicher Geometrie', () => {
  const parts = [entry('a_r0'), entry('a_r1', 'a_r0'), entry('b_r0'), entry('a_r2', 'a_r0'), entry('b_r1', 'b_r0')];

  it('zeigt je Geometrie ein Modul, die Kopien erst unter „Details anzeigen“', () => {
    setup(parts);
    expect(screen.getByTestId('sim-group-note')).toHaveTextContent('5 Module, 2 verschiedene Geometrien');
    expect(screen.getByTestId('sim-part-a_r0')).toBeInTheDocument();
    expect(screen.getByTestId('sim-part-b_r0')).toBeInTheDocument();
    expect(screen.queryByTestId('sim-part-a_r1')).toBeNull();
    expect(screen.getByTestId('sim-group-a_r0-count')).toHaveTextContent('3 Module gleicher Geometrie');
    expect(screen.queryByTestId('sim-group-a_r0-members')).toBeNull();

    fireEvent.click(screen.getByTestId('sim-group-a_r0-toggle'));
    const members = screen.getByTestId('sim-group-a_r0-members');
    expect([...members.querySelectorAll('[data-testid^="sim-group-a_r0-member-"]')].map((e) => e.textContent)).toEqual(['a_r0', 'a_r1', 'a_r2']);
    expect(screen.queryByTestId('sim-group-b_r0-members')).toBeNull();
  });

  it('ein Klick auf eine Kopie wählt sie, die Gruppe bleibt markiert', async () => {
    const store = setup(parts);
    fireEvent.click(screen.getByTestId('sim-group-a_r0-toggle'));
    fireEvent.click(screen.getByTestId('sim-group-a_r0-member-a_r2'));
    expect(store.getState().partId).toBe('a_r2');
    expect(screen.getByTestId('sim-part-a_r0')).toHaveAttribute('data-selected', 'true');
    expect(screen.getByTestId('sim-group-a_r0-member-a_r2')).toHaveAttribute('data-selected', 'true');
    expect(screen.getByTestId('sim-selected')).toHaveTextContent('Ausgewähltes Teil: a_r2 (gleiche Geometrie wie a_r0)');

    fireEvent.click(screen.getByTestId('sim-part-b_r0'));
    expect(store.getState().partId).toBe('b_r0');
    expect(screen.getByTestId('sim-selected')).toHaveTextContent(/^Ausgewähltes Teil: b_r0$/);
    await waitFor(() => expect(store.getState().playbackLoading).toBe(false));
  });

  it('ohne Kopien bleibt es bei einem Knopf je Modul ohne Details', () => {
    setup([entry('P01'), entry('P02')]);
    expect(screen.queryByTestId('sim-group-note')).toBeNull();
    expect(screen.getByTestId('sim-part-P01')).toBeInTheDocument();
    expect(screen.getByTestId('sim-part-P02')).toBeInTheDocument();
    expect(screen.queryByTestId('sim-group-P01-toggle')).toBeNull();
  });
});
