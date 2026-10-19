import { formatDuration, minDistance, moduleProgress, partRectInWall, stageLabel, tallestModuleMm, totalPrintTimeS } from './moduleView';

type M4 = [[number, number, number, number], [number, number, number, number], [number, number, number, number], [number, number, number, number]];
const shift = (tx: number, ty: number, tz: number): M4 => [
  [1, 0, 0, tx],
  [0, 1, 0, ty],
  [0, 0, 1, tz],
  [0, 0, 0, 1],
];

describe('moduleView', () => {
  it('höchstes Modul aus den Bounding-Boxen', () => {
    const box = (h: number) => ({ bbox_P: { min: [-300, -100, 0] as [number, number, number], max: [300, 100, h] as [number, number, number] } });
    expect(tallestModuleMm({ a: box(370), b: box(725), c: box(500) })).toBe(725);
    expect(tallestModuleMm({})).toBeNull();
  });

  it('projiziert die Teil-BBox mit T_LP in die Wandansicht', () => {
    const r = partRectInWall({ T_LP: shift(300, 100, 0), bbox_P: { min: [-300, -100, 0], max: [300, 100, 400] } });
    expect(r).toEqual({ x0: 0, x1: 600, z0: 0, z1: 400 });
  });

  it('summiert die Druckzeit und formatiert sie', () => {
    expect(totalPrintTimeS({ a: { dauer_s: 100 }, b: { dauer_s: 50.5 } })).toBeCloseTo(150.5);
    expect(formatDuration(45)).toBe('45 s');
    expect(formatDuration(750)).toBe('12 min 30 s');
    expect(formatDuration(3900)).toBe('1 h 05 min');
  });

  it('nimmt den kleinsten bekannten Abstand', () => {
    expect(minDistance([{ d_min_mm: 12 }, { d_min_mm: null }, { d_min_mm: 8 }])).toBe(8);
    expect(minDistance([{ d_min_mm: null }])).toBeNull();
  });

  it('liest den Modulfortschritt aus „Teil i/n“', () => {
    expect(moduleProgress('plan', 'Teil 2/4')).toEqual(['fertig', 'aktiv', 'wartet', 'wartet']);
    expect(moduleProgress('export', 'Teil 4/4')).toEqual(['fertig', 'fertig', 'fertig', 'fertig']);
    expect(moduleProgress('decompose', '3 Teil(e)')).toBeNull();
    expect(stageLabel('plan')).toBe('Planen & prüfen');
    expect(stageLabel(null)).toBe('Wartet auf Start');
  });
});
