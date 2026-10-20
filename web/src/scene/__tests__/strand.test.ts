import { describe, expect, it } from 'vitest';
import { printProgress } from '../progress';
import {
  BEAD_VERTS,
  beadBuffer,
  beadsDone,
  cutStart,
  layerRange,
  linesDone,
  strandCut,
  strandLayout,
  strandLines,
  writeTipBead,
} from '../strand';
import { BEAD, H, buildTrajectory, twoShellToolpath } from './strandFixture';

function setup(layers: number, links: boolean) {
  const tp = twoShellToolpath(layers, links);
  const tr = buildTrajectory(tp, links);
  const progress = printProgress(tr, tp.rings);
  return { tp, tr, progress, layout: strandLayout(tp, progress) };
}

/** z-Werte eines flachen Vertex-Arrays [x, y, z, ...]. */
const zs = (a: Float32Array) => Array.from(a).filter((_, i) => i % 3 === 2);

describe('strandLayout', () => {
  it('ordnet Ringe und Verbinder in Druckreihenfolge; Verbinder vom Ringende zum naechsten Ringstart', () => {
    const { layout, tp } = setup(2, true);
    // Ring 0, Verbinder, Ring 1, Verbinder, Ring 2, Verbinder, Ring 3
    expect(layout.printed).toBe(7);
    expect(layout.paths.map((p) => p.cum.length)).toEqual([5, 2, 5, 2, 5, 2, 5]);
    const link = layout.paths[1]!;
    expect(Array.from(link.points)).toEqual([...tp.rings[0]!.waypoints[4]!.slice(0, 3), ...tp.rings[1]!.waypoints[0]!.slice(0, 3)]);
    // Schichtwechsel: der Verbinder gehoert zur Schicht des folgenden Rings und steigt um h.
    const up = layout.paths[3]!;
    expect(up.layer).toBe(1);
    expect((up.points[5] ?? 0) - (up.points[2] ?? 0)).toBeCloseTo(H, 9);
  });

  it('haengt nie gedruckte Ringe hinten an; ohne Fortschritt ist alles offen', () => {
    const { tp } = setup(2, false);
    const open = strandLayout(tp, null);
    expect(open.printed).toBe(0);
    expect(open.paths).toHaveLength(4);
  });
});

describe('strandCut', () => {
  const { layout } = setup(1, false);

  it('schneidet nach Bogenlaenge: ganze Segmente plus Spitze', () => {
    // Aussenring: 4 Segmente zu 100 mm.
    expect(strandCut(layout, 0)).toEqual({ piece: 0, segments: 0, tip: null });
    expect(strandCut(layout, 0.5)).toEqual({ piece: 0, segments: 2, tip: null });
    const c = strandCut(layout, 0.625);
    expect(c.piece).toBe(0);
    expect(c.segments).toBe(2);
    expect(c.tip![0]).toBeCloseTo(50, 9);
    expect(c.tip![1]).toBeCloseTo(100, 9);
    expect(cutStart(layout, c)).toEqual([100, 100, H]);
  });

  it('klemmt am Ende und bei ungueltigen Werten', () => {
    expect(strandCut(layout, 99)).toEqual({ piece: 2, segments: 0, tip: null });
    expect(strandCut(layout, Number.NaN)).toEqual({ piece: 0, segments: 0, tip: null });
    expect(strandCut(layout, -1)).toEqual({ piece: 0, segments: 0, tip: null });
  });
});

describe('Bahnlinien', () => {
  it('fertige Vertices wachsen mit dem Fortschritt bis zur ganzen Bahn', () => {
    const { layout, tr, progress } = setup(2, true);
    const lines = strandLines(layout);
    const total = lines.positions.length / 3;
    let prev = 0;
    for (let i = 0; i < tr.t_s.length; i++) {
      const done = linesDone(lines.start, strandCut(layout, progress.at(i).pos));
      expect(done).toBeGreaterThanOrEqual(prev);
      expect(done).toBeLessThanOrEqual(total);
      prev = done;
    }
    expect(prev).toBe(total);
  });
});

describe('Raupen der laufenden Schicht', () => {
  it('waehlt die Stuecke der Schicht, Verbinder beim Schichtwechsel inklusive', () => {
    const { layout } = setup(2, true);
    expect(layerRange(layout, 0)).toEqual({ from: 0, to: 3 });
    expect(layerRange(layout, 1)).toEqual({ from: 3, to: 7 });
    expect(layerRange(layout, 2)).toEqual({ from: 7, to: 7 });
  });

  it('haengt um h unter der Bahn, ist strangbreit und an Ecken auf Gehrung', () => {
    const { layout } = setup(1, false);
    const buf = beadBuffer(layout, 0, 1, BEAD, H);
    expect(buf.positions.length / 3).toBe(4 * BEAD_VERTS);
    const z = zs(buf.positions);
    expect(Math.max(...z)).toBeCloseTo(H, 5);
    expect(Math.min(...z)).toBeCloseTo(0, 5);
    // Erstes Segment (0,0) -> (100,0): Flanken bei y = +-15, an den Ecken Gehrung bis +-15.
    const ys = Array.from(buf.positions.subarray(0, BEAD_VERTS * 3)).filter((_, i) => i % 3 === 1);
    expect(Math.max(...ys)).toBeCloseTo(BEAD / 2, 5);
    expect(Math.min(...ys)).toBeCloseTo(-BEAD / 2, 5);
    const xs = Array.from(buf.positions.subarray(0, BEAD_VERTS * 3)).filter((_, i) => i % 3 === 0);
    expect(Math.min(...xs)).toBeCloseTo(-BEAD / 2, 5);
    expect(Math.max(...xs)).toBeCloseTo(100 + BEAD / 2, 5);
    // Oberseite zeigt nach oben.
    const [nx, ny, nz] = Array.from(buf.normals.subarray(0, 3));
    expect([nx, ny, nz].map((v) => Math.abs(v ?? 1) < 1e-9 ? 0 : v)).toEqual([0, 0, 1]);
  });

  it('zaehlt fertige Raupen monoton und setzt die Spitze bis zum Schnitt', () => {
    const { layout, tr, progress } = setup(1, true);
    const { from, to } = layerRange(layout, 0);
    const buf = beadBuffer(layout, from, to, BEAD, H);
    let prev = 0;
    for (let i = 0; i < tr.t_s.length; i++) {
      const done = beadsDone(buf, strandCut(layout, progress.at(i).pos));
      expect(done).toBeGreaterThanOrEqual(prev);
      prev = done;
    }
    expect(prev).toBe(buf.positions.length / 3);

    const cut = strandCut(layout, 0.625);
    const pos = new Float32Array(BEAD_VERTS * 3);
    const nrm = new Float32Array(BEAD_VERTS * 3);
    expect(writeTipBead(pos, nrm, layout, cut, BEAD, H)).toBe(true);
    const xs = Array.from(pos).filter((_, i) => i % 3 === 0);
    expect(Math.min(...xs)).toBeCloseTo(50, 5);
    expect(writeTipBead(pos, nrm, layout, strandCut(layout, 0.5), BEAD, H)).toBe(false);
  });
});
