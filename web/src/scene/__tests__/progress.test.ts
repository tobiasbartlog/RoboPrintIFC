import { describe, expect, it } from 'vitest';
import type { Trajectory } from '../../contracts';
import { clipHeightMm } from '../math';
import { printProgress, type PrintedState, type PrintProgress } from '../progress';
import { H, buildTrajectory, twoShellToolpath } from './strandFixture';

const states = (p: PrintProgress, n: number): PrintedState[] => Array.from({ length: n }, (_, i) => p.at(i));

/** Index des ersten Samples einer Art (und optional eines Rings). */
function first(tr: Trajectory, kind: Trajectory['kind'][number], ring?: number): number {
  return tr.kind.findIndex((k, i) => k === kind && (ring === undefined || tr.ring[i] === ring));
}

function expectMonotone(seq: PrintedState[]) {
  for (let i = 1; i < seq.length; i++) {
    expect(seq[i]!.layers, `Schichten sinken bei Sample ${i}`).toBeGreaterThanOrEqual(seq[i - 1]!.layers);
    expect(seq[i]!.pos, `Strang schrumpft bei Sample ${i}`).toBeGreaterThanOrEqual(seq[i - 1]!.pos);
  }
}

describe('printProgress: zwei Schalen je Schicht', () => {
  for (const links of [false, true]) {
    const name = links ? 'mit Verbindern' : 'ohne Verbinder';
    const tp = twoShellToolpath(3, links);
    const tr = buildTrajectory(tp, links);
    const p = printProgress(tr, tp.rings);
    const seq = states(p, tr.t_s.length);

    it(`${name}: angezeigte Hoehe und Strang sinken vorwaerts nie`, () => {
      expectMonotone(seq);
      const heights = seq.map((s) => clipHeightMm(s.layers, H, 3));
      for (let i = 1; i < heights.length; i++) expect(heights[i]!).toBeGreaterThanOrEqual(heights[i - 1]!);
    });

    it(`${name}: weicht vom Kollisions-Druckstand k nur an Schalen- und Schichtgrenzen ab`, () => {
      seq.forEach((s, i) => {
        const k = tr.layer[i]!;
        // Ueber k nur am Ende der letzten Schale einer Schicht (letztes Druck-Sample, Abfahrt):
        // gedruckt ist die Schicht, die Pruefung zaehlt sie dort noch nicht.
        if (s.layers > k) {
          expect(s.layers).toBe(k + 1);
          expect(['print', 'retract']).toContain(tr.kind[i]);
        }
        // Unter k nur im Travel, bevor die naechste Schale der Schicht gedruckt ist.
        if (s.layers < k) expect(['lift', 'transfer', 'lower']).toContain(tr.kind[i]);
      });
    });

    it(`${name}: eine Schicht ist erst fertig, wenn ihre Innenschale fertig ist`, () => {
      const lastInner0 = tr.kind.lastIndexOf('print', first(tr, 'print', 2) - 1);
      expect(tr.ring[lastInner0]).toBe(1);
      expect(p.at(lastInner0 - 1).layers).toBe(0);
      expect(p.at(lastInner0).layers).toBe(1);
    });

    it(`${name}: Stuecke in Druckreihenfolge, Verbinder nur im Strang`, () => {
      const rings = p.pieces.filter((x) => x.kind === 'ring').map((x) => x.ring);
      expect(rings).toEqual([0, 1, 2, 3, 4, 5]);
      expect(p.pieces.filter((x) => x.kind === 'link').map((x) => x.ring)).toEqual(links ? [1, 2, 3, 4, 5] : []);
      expect(p.nLayers).toBe(3);
    });
  }

  it('ohne Verbinder springt k beim Wechsel zur Innenschale, der Fortschritt nicht', () => {
    const tp = twoShellToolpath(2, false);
    const tr = buildTrajectory(tp, false);
    const p = printProgress(tr, tp.rings);
    // Das beobachtete Muster: k = 1 im Travel nach Ring 0, danach wieder 0 beim Druck von Ring 1.
    const lift0 = first(tr, 'lift', 0);
    const print1 = first(tr, 'print', 1);
    expect(tr.layer[lift0]).toBe(1);
    expect(tr.layer[print1]).toBe(0);
    expect(p.at(lift0)).toEqual({ layers: 0, pos: 1 });
    expect(p.at(print1).layers).toBe(0);
    expect(p.at(print1).pos).toBeGreaterThan(1);
  });

  it('mit Verbindern zaehlt der Verbinder als eigenes Stueck mit Anteil', () => {
    const tp = twoShellToolpath(1, true);
    const tr = buildTrajectory(tp, true);
    const p = printProgress(tr, tp.rings);
    const link = first(tr, 'link', 1);
    expect(p.at(link - 1)).toEqual({ layers: 0, pos: 1 });
    expect(p.at(link).pos).toBeCloseTo(1.5, 9); // halber Weg des Verbinders
    expect(p.at(link + 1).pos).toBe(2);
  });

  it('teilt den laufenden Ring nach Bogenlaenge', () => {
    const tp = twoShellToolpath(1, false);
    const tr = buildTrajectory(tp, false, 25);
    const p = printProgress(tr, tp.rings);
    const i0 = first(tr, 'print', 0);
    // Aussenring 400 mm, Samples alle 25 mm: Sample i0 + 7 liegt bei 200 mm.
    expect(p.at(i0).pos).toBeCloseTo(25 / 400, 9);
    expect(p.at(i0 + 7).pos).toBeCloseTo(0.5, 9);
  });
});

describe('printProgress: Grenzfaelle', () => {
  const tp = twoShellToolpath(2, true);
  const tr = buildTrajectory(tp, true);
  const n = tr.t_s.length;
  const p = printProgress(tr, tp.rings);

  it('am Anfang ist nichts gedruckt', () => {
    expect(p.at(0)).toEqual({ layers: 0, pos: 0 });
    expect(p.at(first(tr, 'approach'))).toEqual({ layers: 0, pos: 0 });
    expect(p.at(-5)).toEqual(p.at(0));
    expect(p.at(Number.NaN)).toEqual(p.at(0));
  });

  it('am Ende ist alles gedruckt', () => {
    expect(p.at(n - 1)).toEqual({ layers: 2, pos: p.pieces.length });
    expect(p.at(1e9)).toEqual(p.at(n - 1));
  });

  it('leere Trajektorie: nichts gedruckt', () => {
    const empty = { ...tr, kind: [], ring: [], layer: [], tcp: [] };
    expect(printProgress(empty, tp.rings).at(0)).toEqual({ layers: 0, pos: 0 });
    expect(printProgress(empty, tp.rings).pieces).toEqual([]);
  });

  it('unerreichbare Samples aendern den Fortschritt nicht', () => {
    // Bei unreachable traegt tcp das Ziel (ARTEFAKTE), der Ablauf bleibt gleich; nur der Status zeigt es.
    const status = tr.status.map((s, i) => (tr.kind[i] === 'print' && tr.ring[i] === 1 ? 'unreachable' : s));
    const bad = { ...tr, status, d_mm: tr.d_mm.map((d, i) => (status[i] === 'unreachable' ? null : d)) };
    const q = printProgress(bad, tp.rings);
    expectMonotone(states(q, n));
    for (let i = 0; i < n; i++) expect(q.at(i)).toEqual(p.at(i));
  });

  it('ein nie gedruckter Ring haelt seine Schicht offen', () => {
    // Ring 3 (Innenschale Schicht 1) fehlt in der Trajektorie, etwa nach einem Abbruch.
    const keep = tr.ring.map((r) => r !== 3);
    const pick = <T,>(a: T[]) => a.filter((_, i) => keep[i]);
    const cut = { ...tr, kind: pick(tr.kind), ring: pick(tr.ring), layer: pick(tr.layer), tcp: pick(tr.tcp) };
    const q = printProgress(cut, tp.rings);
    expectMonotone(states(q, cut.kind.length));
    expect(q.at(cut.kind.length - 1).layers).toBe(1);
  });

  it('ohne Toolpath zaehlen die Ringe der Trajektorie, Schicht aus k', () => {
    const q = printProgress(tr, null);
    expect(q.nLayers).toBe(2);
    for (let i = 0; i < n; i++) expect(q.at(i)).toEqual(p.at(i));
  });
});
