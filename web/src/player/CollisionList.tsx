import { Paper, Stack, Text, UnstyledButton } from '@mantine/core';
import { useMemo } from 'react';
import type { Trajectory } from '../contracts';
import { collisionRanges, statusSegments, type CollisionRange } from './clock';
import { fmt, linkLabel, obstacleLabel } from './labels';

interface CollisionListProps {
  trajectory: Trajectory;
  onSelect: (c: CollisionRange) => void;
  activeT: number;
}

/** Liste „Kollisionen (n)“: ein Eintrag je zusammenhängendem Kollisionsbereich. */
export function CollisionList({ trajectory, onSelect, activeT }: CollisionListProps) {
  const ranges = useMemo(() => collisionRanges(trajectory), [trajectory]);
  const other = useMemo(() => {
    const segs = statusSegments(trajectory);
    const warn = segs.filter((s) => s.value === 'warn');
    const unr = segs.filter((s) => s.value === 'unreachable');
    const n = trajectory.t_s.length || 1;
    const share = (xs: typeof segs) => xs.reduce((a, s) => a + s.i1 - s.i0 + 1, 0) / n;
    return { warn: warn.length, unr: unr.length, unrShare: share(unr) };
  }, [trajectory]);

  return (
    <Stack gap={4} data-testid="collision-list" data-count={ranges.length}>
      <Text fw={600} size="sm" data-testid="collision-title">
        Kollisionen ({ranges.length})
      </Text>
      {ranges.length === 0 ? (
        <Text size="xs" c="dimmed">
          Keine Kollision in diesem Teil.
        </Text>
      ) : (
        ranges.map((c, k) => {
          const active = activeT >= c.t0 && activeT < c.t1;
          return (
            <UnstyledButton key={k} onClick={() => onSelect(c)} data-testid={`collision-item-${k}`} data-link={c.link} data-obstacle={c.obstacle} data-t={c.tMin}>
              <Paper withBorder p={6} style={{ borderColor: active ? 'var(--mantine-color-red-6)' : undefined }}>
                <Text size="sm" fw={500}>
                  {linkLabel(c.link)} ↔ {obstacleLabel(c.obstacle)}
                </Text>
                <Text size="xs" c="dimmed">
                  {c.layer} Schichten fertig · min d {Number.isNaN(c.dMin) ? 'unbekannt' : `${fmt(c.dMin)} mm`} · {fmt(c.t0)}–{fmt(c.t1)} s
                </Text>
              </Paper>
            </UnstyledButton>
          );
        })
      )}
      {other.warn > 0 || other.unr > 0 ? (
        <Text size="xs" c="dimmed" data-testid="status-digest">
          {other.warn > 0 ? `${other.warn} Bereiche mit Warnung (unter Zielabstand)` : ''}
          {other.warn > 0 && other.unr > 0 ? ' · ' : ''}
          {other.unr > 0 ? `${fmt(other.unrShare * 100, other.unrShare < 0.1 ? 1 : 0)} % der Bahn unerreichbar (${other.unr} Bereiche)` : ''}
        </Text>
      ) : null}
    </Stack>
  );
}
