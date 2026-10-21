import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from './App';
import { createFakeApi } from './state/fakeApi';
import { createAppStore } from './state/store';

describe('App', () => {
  it('zeigt den Titel und den Stepper', async () => {
    render(<App api={createFakeApi()} />);
    await screen.findByTestId('example-demo');
    expect(screen.getByRole('heading', { name: 'RoboPrintIFC' })).toBeInTheDocument();
    expect(screen.getByTestId('step-model')).toHaveAttribute('data-status', 'fehlt');
    expect(screen.getByTestId('step-export-reason')).toHaveTextContent('Erst zerlegen & prüfen.');
  });

  it('führt vom Beispiel bis zur Teileliste', async () => {
    const store = createAppStore(createFakeApi({ mode: 'ok', polls: 2 }), { pollMs: 1 });
    render(<App store={store} />);

    fireEvent.click(await screen.findByTestId('example-demo'));
    expect(await screen.findByTestId('wall-reason-duenn')).toHaveTextContent('24 mm');
    fireEvent.click(screen.getByTestId('wall-select-box'));
    fireEvent.click(screen.getByTestId('to-decompose'));
    fireEvent.click(screen.getByTestId('start-job'));
    await waitFor(() => expect(screen.getByTestId('part-status-P01')).toHaveTextContent('machbar'), { timeout: 10_000 });
    expect(screen.getByTestId('step-decompose')).toHaveAttribute('data-status', 'aktuell');
  });
});
