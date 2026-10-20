import { describe, expect, it } from 'vitest';
import type { Toolpath } from '../../contracts';
import { kindColorFn } from '../kindColors';
import { printProgress } from '../progress';
import { BEAD_VERTS, beadBuffer, hasPatternKinds, strandLayout, strandLines } from '../strand';
import { buildTrajectory, twoShellToolpath } from './strandFixture';

/** Zwei Schalen und ein Infill-Segment (offen) in Schicht 0, Steg in Schicht 1. */
function patternToolpath(): Toolpath {
  const tp = twoShellToolpath(2, true);
  const w = tp.rings[0]!.waypoints;
  tp.rings.splice(
    2,
    0,
    { layer: 0, shell: 2, kind: 'infill', closed: false, link_next: true, waypoints: [w[0]!, w[1]!, w[2]!] },
    { layer: 1, shell: 2, kind: 'web', closed: false, link_next: true, waypoints: [w[2]!, w[3]!] },
  );
  return tp;
}

const COLORS = { infill: 'rgb(255, 0, 0)', web: 'rgb(0, 255, 0)', outfill: 'rgb(0, 0, 255)' };

describe('Segmentarten in der 3D-Ansicht', () => {
  it('jedes Stück trägt die Art seines Rings; Verbinder heißen „link“', () => {
    const tp = patternToolpath();
    const layout = strandLayout(tp, printProgress(buildTrajectory(tp, true), tp.rings));
    const kinds = layout.paths.map((p) => p.kind);
    expect(kinds).toContain('infill');
    expect(kinds).toContain('web');
    expect(kinds).toContain('link');
    expect(hasPatternKinds(layout)).toBe(true);
  });

  it('ohne Musterarten färbt die Ansicht nicht um (Bahn und Raupen wie bisher)', () => {
    const tp = twoShellToolpath(2, true);
    const layout = strandLayout(tp, printProgress(buildTrajectory(tp, true), tp.rings));
    expect(hasPatternKinds(layout)).toBe(false);
    expect(strandLines(layout).colors).toBeNull();
    expect(beadBuffer(layout, 0, layout.printed, 30, 10).colors).toBeNull();
  });

  it('Vertexfarben: Musterarten bekommen ihre Farbe, Schalen und Verbinder die Grundfarbe', () => {
    const tp = patternToolpath();
    const layout = strandLayout(tp, printProgress(buildTrajectory(tp, true), tp.rings));
    const colorOf = kindColorFn(COLORS, 'rgb(0, 0, 0)');
    expect(Array.from(colorOf('infill'))).toEqual([1, 0, 0]);
    expect(Array.from(colorOf('web'))).toEqual([0, 1, 0]);
    expect(Array.from(colorOf('outer'))).toEqual([0, 0, 0]);
    expect(Array.from(colorOf('link'))).toEqual([0, 0, 0]);

    const lines = strandLines(layout, colorOf);
    expect(lines.colors).not.toBeNull();
    expect(lines.colors!.length).toBe(lines.positions.length);
    const k = layout.paths.findIndex((p) => p.kind === 'infill');
    const v = lines.start[k]!;
    expect(Array.from(lines.colors!.slice(3 * v, 3 * v + 3))).toEqual([1, 0, 0]);

    const buf = beadBuffer(layout, 0, layout.printed, 30, 10, colorOf);
    expect(buf.colors!.length).toBe(buf.positions.length);
    const b = buf.start[k]!;
    for (let j = 0; j < BEAD_VERTS; j++) expect(Array.from(buf.colors!.slice(3 * (b + j), 3 * (b + j) + 3))).toEqual([1, 0, 0]);
  });
});
