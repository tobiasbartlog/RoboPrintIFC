import type { Trajectory } from '../contracts';
import { printProgress } from '../scene/progress';
import { buildTrajectory, twoShellToolpath } from '../scene/__tests__/strandFixture';
import { collisionRanges, debugSnapshot, kindSegments, layerSegments, sampleAt, sceneSample, segments, statusSegments } from './clock';

type Tr = Pick<Trajectory, 't_s' | 'status' | 'd_mm' | 'pair' | 'witness' | 'layer' | 'kind' | 'tcp'>;

/** Kleine Trajektorie: 8 Samples, ein Kollisionsbereich mit zwei Samples, eine Warnung, unerreichbar. */
function mini(): Tr {
  return {
    t_s: [0, 1, 2, 3, 4, 5, 6, 7],
    status: ['ok', 'warn', 'collision', 'collision', 'ok', 'unreachable', 'collision', 'ok'],
    d_mm: [80, 30, -2, -5, 70, null, -1, 90],
    pair: [
      ['link_2', 'table'],
      ['link_3', 'printed'],
      ['link_3', 'printed'],
      ['tool_body', 'printed'],
      ['link_2', 'table'],
      null,
      ['link_1', 'floor'],
      ['link_2', 'table'],
    ],
    witness: [
      null,
      null,
      [
        [0, 0, 0],
        [2, 2, 2],
      ],
      [
        [10, 20, 30],
        [12, 22, 32],
      ],
      null,
      null,
      [
        [0, 0, 0],
        [0, 0, 2],
      ],
      null,
    ],
    layer: [0, 0, 1, 1, 2, 2, 2, 3],
    kind: ['transfer', 'lower', 'approach', 'print', 'print', 'print', 'retract', 'lift'],
    tcp: Array.from({ length: 8 }, (_, i) => [i, 10 * i, 100 * i, 1, 0, 0, 0] as [number, number, number, number, number, number, number]),
  };
}

describe('sampleAt (eine Uhr)', () => {
  const tS = [0, 0.5, 1.25, 2, 10];
  it('liefert das letzte Sample mit t_s ≤ t', () => {
    expect(sampleAt(tS, 0)).toBe(0);
    expect(sampleAt(tS, 0.49)).toBe(0);
    expect(sampleAt(tS, 0.5)).toBe(1);
    expect(sampleAt(tS, 1.9999)).toBe(2);
    expect(sampleAt(tS, 2)).toBe(3);
    expect(sampleAt(tS, 9.9)).toBe(3);
    expect(sampleAt(tS, 10)).toBe(4);
  });
  it('klemmt an den Rändern und behandelt Leere', () => {
    expect(sampleAt(tS, -3)).toBe(0);
    expect(sampleAt(tS, 1e9)).toBe(4);
    expect(sampleAt(tS, Number.NaN)).toBe(0);
    expect(sampleAt([], 1)).toBe(-1);
  });
  it('stimmt mit linearer Suche überein', () => {
    const ts: number[] = [];
    let x = 0;
    for (let i = 0; i < 500; i++) ts.push((x += 0.01 + ((i * 7919) % 13) / 100));
    for (let k = 0; k < 300; k++) {
      const t = (k / 300) * (ts[ts.length - 1] ?? 0) * 1.1 - 0.5;
      let lin = 0;
      for (let i = 0; i < ts.length; i++) if ((ts[i] ?? 0) <= t) lin = i;
      expect(sampleAt(ts, t)).toBe(lin);
    }
  });
});

describe('Timeline-Segmente', () => {
  it('fasst gleiche Werte zusammen, Sample i gilt bis t_s[i+1]', () => {
    const s = segments([0, 1, 2, 3], ['a', 'a', 'b', 'b']);
    expect(s).toEqual([
      { value: 'a', i0: 0, i1: 1, t0: 0, t1: 2 },
      { value: 'b', i0: 2, i1: 3, t0: 2, t1: 3 },
    ]);
  });
  it('Status-Bereiche nur für warn, collision, unreachable', () => {
    const s = statusSegments(mini());
    expect(s.map((x) => [x.value, x.i0, x.i1])).toEqual([
      ['warn', 1, 1],
      ['collision', 2, 3],
      ['unreachable', 5, 5],
      ['collision', 6, 6],
    ]);
  });
  it('Arten und Schichten', () => {
    expect(kindSegments(mini()).map((x) => x.value)).toEqual(['transfer', 'lower', 'approach', 'print', 'retract', 'lift']);
    expect(layerSegments(mini()).map((x) => [x.value, x.t0, x.t1])).toEqual([
      [0, 0, 2],
      [1, 2, 4],
      [2, 4, 7],
      [3, 7, 7],
    ]);
  });
});

describe('Kollisionsliste', () => {
  it('ein Eintrag je zusammenhängendem Bereich, mit kritischstem Sample', () => {
    const r = collisionRanges(mini());
    expect(r).toHaveLength(2);
    expect(r[0]).toMatchObject({ i0: 2, i1: 3, iMin: 3, tMin: 3, dMin: -5, link: 'tool_body', obstacle: 'printed', layer: 1, focus: [11, 21, 31] });
    expect(r[1]).toMatchObject({ i0: 6, i1: 6, iMin: 6, link: 'link_1', obstacle: 'floor', focus: [0, 0, 1] });
  });
  it('leer ohne Kollision', () => {
    const tr = mini();
    tr.status = tr.status.map((s) => (s === 'collision' ? 'warn' : s));
    expect(collisionRanges(tr)).toEqual([]);
  });
});

describe('Debug-Objekt', () => {
  it('hat genau die Felder aus SPEC §9 und kommt aus demselben Index', () => {
    const tr = mini();
    const d = debugSnapshot({ t: 3.4, trajectory: tr, tcpRendered: [3.1, 30, 300, 1, 0, 0, 0], highlightedLinks: ['tool_body'], showObstacle: true });
    expect(Object.keys(d).sort()).toEqual(['highlightedLinks', 'obstacleVisible', 'sampleIndex', 'status', 't', 'tcpArtifact', 'tcpRendered'].sort());
    expect(d).toEqual({
      t: 3.4,
      sampleIndex: 3,
      tcpRendered: [3.1, 30, 300],
      tcpArtifact: [3, 30, 300],
      status: 'collision',
      highlightedLinks: ['tool_body'],
      obstacleVisible: true,
    });
  });
  it('Hindernis nur bei warn/collision und eingeschalteter Anzeige', () => {
    const tr = mini();
    const at = (t: number, show = true) => debugSnapshot({ t, trajectory: tr, tcpRendered: null, highlightedLinks: [], showObstacle: show }).obstacleVisible;
    expect(at(0)).toBe(false);
    expect(at(1)).toBe(true);
    expect(at(2, false)).toBe(false);
    expect(at(5)).toBe(false);
  });
  it('ohne Trajektorie', () => {
    expect(debugSnapshot({ t: 1, trajectory: null, tcpRendered: null, highlightedLinks: [], showObstacle: true })).toMatchObject({
      sampleIndex: -1,
      tcpArtifact: null,
      status: null,
      obstacleVisible: false,
    });
  });
});

describe('sceneSample', () => {
  it('übernimmt alle Felder des Index', () => {
    const tr = { ...mini(), q: Array.from({ length: 8 }, (_, i) => [i, 0, 0, 0, 0, 0]) } as unknown as Trajectory;
    const s = sceneSample(tr, 3);
    expect(s).toMatchObject({ q: [3, 0, 0, 0, 0, 0], layer: 1, status: 'collision', pair: ['tool_body', 'printed'], d_mm: -5 });
    expect(sceneSample(tr, 99)).toBeNull();
    expect(s?.printed).toBeNull();
  });

  it('trägt mit Fortschritt den Druckstand der Anzeige, getrennt vom Kollisions-k', () => {
    const tp = twoShellToolpath(1, false);
    const tr = buildTrajectory(tp, false);
    const progress = printProgress(tr, tp.rings);
    // Travel nach der Aussenschale: k = 1 (Pruefung), gedruckt ist erst ein Ring der Schicht 0.
    const i = tr.kind.indexOf('lift');
    expect(sceneSample(tr, i, progress)).toMatchObject({ layer: 1, printed: { layers: 0, pos: 1 } });
  });
});

describe('Verbinder', () => {
  it('erscheint als eigene Bewegungsart zwischen zwei Druckbereichen', () => {
    const tp = twoShellToolpath(1, true);
    const tr = buildTrajectory(tp, true);
    expect(kindSegments(tr).map((x) => x.value)).toEqual(['transfer', 'lower', 'approach', 'print', 'link', 'print', 'retract', 'lift']);
  });
});
