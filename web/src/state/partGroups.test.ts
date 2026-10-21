import { groupOf, groupParts } from './partGroups';

const part = (part_id: string, same_as: string | null = null) => ({ part_id, same_as });

describe('partGroups', () => {
  it('fasst Kopien unter ihrem Repräsentanten zusammen', () => {
    const groups = groupParts([part('a_r0'), part('a_r1', 'a_r0'), part('b_r0'), part('a_r2', 'a_r0'), part('b_r1', 'b_r0')]);
    expect(groups.map((g) => g.rep.part_id)).toEqual(['a_r0', 'b_r0']);
    expect(groups.map((g) => g.members.map((m) => m.part_id))).toEqual([
      ['a_r0', 'a_r1', 'a_r2'],
      ['b_r0', 'b_r1'],
    ]);
  });

  it('ohne Kopien ist jedes Teil eine eigene Gruppe', () => {
    const groups = groupParts([part('P01'), part('P02')]);
    expect(groups.map((g) => g.members.length)).toEqual([1, 1]);
  });

  it('nimmt den Repräsentanten zuerst, auch wenn eine Kopie vor ihm steht', () => {
    const [g] = groupParts([part('c', 'r'), part('r')]);
    expect(g!.rep.part_id).toBe('r');
    expect(g!.members.map((m) => m.part_id)).toEqual(['r', 'c']);
  });

  it('verliert kein Modul, wenn same_as ins Leere zeigt oder fehlt', () => {
    const groups = groupParts([{ part_id: 'alt' }, part('x', 'gibt_es_nicht'), part('y', 'x')]);
    expect(groups.flatMap((g) => g.members.map((m) => m.part_id)).sort()).toEqual(['alt', 'x', 'y']);
    expect(groups.map((g) => g.rep.part_id)).toEqual(['alt', 'x']);
  });

  it('findet die Gruppe eines Teils', () => {
    const groups = groupParts([part('r'), part('c', 'r')]);
    expect(groupOf(groups, 'c')?.rep.part_id).toBe('r');
    expect(groupOf(groups, 'fehlt')).toBeNull();
    expect(groupOf(groups, null)).toBeNull();
  });
});
