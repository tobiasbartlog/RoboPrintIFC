import { describe, expect, it } from 'vitest';
import type { PatternParamSpec } from '../contracts';
import { buildRequest, contactStyle, effectiveValue, inRange, length, num, outlineOfBox, segmentStyle, seconds, spacingSummary, svgFileName } from './patterns';

const spec: PatternParamSpec = { name: 'a', label: 'A', default: 5, unit: 'mm', minimum: 1, maximum: 9, step: 1, kind: 'float', choices: [], help: '' };

describe('patterns (Darstellungshilfen)', () => {
  it('lässt Zwischenstände beim Tippen nicht durch', () => {
    expect(inRange(2, 160, 300)).toBe(false);
    expect(inRange(240, 160, 300)).toBe(true);
    expect(inRange(400, 160, 300)).toBe(false);
    expect(inRange(5, null, null)).toBe(true);
    expect(inRange(Number.NaN, null, null)).toBe(false);
  });

  it('formatiert deutsch und zeigt fehlende Werte als Strich', () => {
    expect(num(1234.5, 1)).toBe('1.234,5');
    expect(num(null)).toBe('–');
    expect(length(747)).toBe('747 mm');
    expect(length(3310)).toBe('3,31 m');
    expect(seconds(33.14)).toBe('33,1 s');
    expect(seconds(125)).toBe('2 min 05 s');
  });

  it('fasst Fugenabstände zusammen', () => {
    expect(spacingSummary([200, 200.1, 200])).toBe('3 × 200 mm');
    expect(spacingSummary([180, 220])).toBe('2 Abstände, 180 bis 220 mm');
    expect(spacingSummary([])).toBe('–');
  });

  it('kennt neue Segment- und Kontaktarten nur über ihren Namen', () => {
    expect(segmentStyle('web').label).toBe('Steg');
    expect(segmentStyle('zickzack').label).toBe('zickzack');
    expect(contactStyle('joint').label).toContain('Fuge');
    expect(contactStyle('neu').label).toBe('neu');
  });

  it('Wert eines Reglers: Änderung vor Kernwert vor Standard', () => {
    expect(effectiveValue(spec, { a: 7 }, { a: 3 })).toBe(7);
    // Mit Standard gilt der Standard, nicht ein veralteter Wert der letzten Vorschau
    expect(effectiveValue(spec, {}, { a: 3 })).toBe(5);
    expect(effectiveValue(spec, {}, null)).toBe(5);
    // Ohne Standard (vom Kern abgeleitet) gilt der gemeldete Wert
    expect(effectiveValue({ ...spec, default: null }, {}, { a: 3 })).toBe(3);
    expect(effectiveValue({ ...spec, default: null }, {}, null)).toBeNull();
  });

  it('baut die Anfrage nur aus Änderungen und dem Querschnitt', () => {
    const req = buildRequest('fugenwand', { a: 7 }, { length_mm: 900, thickness_mm: 200, source: 'free' }, 2);
    expect(req).toEqual({ pattern: 'fugenwand', preset: null, params: { a: 7 }, outline: { length_mm: 900, thickness_mm: 200 }, layer: 2 });
    expect(svgFileName('fugenwand', { length_mm: 900, thickness_mm: 200, source: 'free' })).toBe('muster-fugenwand-900x200.svg');
    expect(outlineOfBox([-300, -100, 0], [300, 100, 400])).toEqual({ length_mm: 600, thickness_mm: 200 });
  });
});
