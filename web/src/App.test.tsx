import { render, screen } from '@testing-library/react';
import { App } from './App';

describe('App', () => {
  it('zeigt den Titel', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'RoboPrintIFC' })).toBeInTheDocument();
  });
});
