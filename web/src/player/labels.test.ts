import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { PUMP_KINDS, TRAVEL_KINDS, type Kind } from './clock';
import { KIND_COLOR, KIND_LABEL } from './labels';

/** Alle Bewegungsarten aus dem Vertrag (JSON-Schema der Trajektorie), nicht aus dem eigenen Code. */
function contractKinds(): Kind[] {
  const schema = JSON.parse(readFileSync(resolve(__dirname, '../contracts/schemas/Trajectory.schema.json'), 'utf-8'));
  return schema.properties.kind.items.enum as Kind[];
}

describe('Bewegungsarten', () => {
  it('hat für jede Art des Vertrags Klartext und Farbe', () => {
    for (const k of contractKinds()) {
      expect(KIND_LABEL[k], k).toBeTruthy();
      expect(KIND_COLOR[k], k).toMatch(/^var\(--mantine-color-/);
    }
  });

  it('nennt den Verbinder und zählt ihn zur Pumpe an, nicht zum Travel', () => {
    expect(KIND_LABEL.link).toBe('Verbinder');
    expect(PUMP_KINDS).toEqual(['print', 'link']);
    expect(TRAVEL_KINDS).not.toContain('link');
    expect([...PUMP_KINDS, ...TRAVEL_KINDS].sort()).toEqual([...contractKinds()].sort());
  });

  it('setzt den Verbinder farblich vom Travel ab', () => {
    for (const k of TRAVEL_KINDS) expect(KIND_COLOR.link).not.toBe(KIND_COLOR[k]);
  });
});
