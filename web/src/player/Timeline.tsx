import { Box, Group, Stack, Text } from '@mantine/core';
import { useMemo, type MouseEvent } from 'react';
import type { Trajectory } from '../contracts';
import { duration, kindSegments, layerSegments, statusSegments, type Segment } from './clock';
import { KIND_COLOR, KIND_LABEL, STATUS_COLOR, STATUS_LABEL } from './labels';

interface TimelineProps {
  trajectory: Trajectory;
  t: number;
  onSeek: (t: number) => void;
}

const TRACK_H = 12;

function Track<V>({
  label,
  testid,
  segs,
  end,
  color,
  title,
}: {
  label: string;
  testid: string;
  segs: Segment<V>[];
  end: number;
  color: (v: V, idx: number) => string;
  title: (s: Segment<V>) => string;
}) {
  return (
    <Group gap={6} wrap="nowrap" align="center">
      <Text size="xs" c="dimmed" w={52} style={{ flexShrink: 0 }}>
        {label}
      </Text>
      <Box
        data-testid={testid}
        style={{ position: 'relative', flex: 1, height: TRACK_H, background: 'var(--mantine-color-default-border)', borderRadius: 2, overflow: 'hidden' }}
      >
        {segs.map((s, k) => (
          <div
            key={k}
            title={title(s)}
            data-value={String(s.value)}
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: `${(s.t0 / end) * 100}%`,
              // Mindestbreite, damit kurze Bereiche (einzelne Samples) sichtbar bleiben.
              width: `max(3px, ${((s.t1 - s.t0) / end) * 100}%)`,
              background: color(s.value, k),
            }}
          />
        ))}
      </Box>
    </Group>
  );
}

/**
 * Timeline mit Bereichs-Balken: Bewegungsart, auffällige Status-Bereiche (warn, collision,
 * unreachable) und eine Spur je Schicht. Ein Klick setzt die Uhr.
 */
export function Timeline({ trajectory, t, onSeek }: TimelineProps) {
  const end = Math.max(duration(trajectory), 1e-9);
  const kinds = useMemo(() => kindSegments(trajectory), [trajectory]);
  const status = useMemo(() => statusSegments(trajectory), [trajectory]);
  const layers = useMemo(() => layerSegments(trajectory), [trajectory]);
  const range = (s: { t0: number; t1: number }) => `${s.t0.toFixed(1)}–${s.t1.toFixed(1)} s`;

  function click(e: MouseEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const labelW = 58;
    const x = (e.clientX - r.left - labelW) / Math.max(1, r.width - labelW);
    if (x >= 0 && x <= 1) onSeek(x * end);
  }

  return (
    <Stack gap={6} data-testid="timeline">
      <Stack gap={4} onClick={click} style={{ position: 'relative', cursor: 'pointer' }}>
      <Track label="Art" testid="timeline-kind" segs={kinds} end={end} color={(v) => KIND_COLOR[v]} title={(s) => `${KIND_LABEL[s.value]} ${range(s)}`} />
      <Track
        label="Status"
        testid="timeline-status"
        segs={status}
        end={end}
        color={(v) => STATUS_COLOR[v]}
        title={(s) => `${STATUS_LABEL[s.value]} ${range(s)}`}
      />
      <Track
        label="Schicht"
        testid="timeline-layer"
        segs={layers}
        end={end}
        color={(v) => (v % 2 === 0 ? 'var(--mantine-color-gray-4)' : 'var(--mantine-color-gray-6)')}
        title={(s) => `Schicht ${s.value} fertig ${range(s)}`}
      />
      <div
        aria-hidden
        data-testid="timeline-cursor"
        style={{
          position: 'absolute',
          top: -2,
          bottom: -2,
          left: `calc(58px + (100% - 58px) * ${Math.min(1, Math.max(0, t / end))})`,
          width: 2,
          background: 'var(--mantine-color-text)',
          pointerEvents: 'none',
        }}
      />
      </Stack>
      <Group gap="sm" wrap="wrap">
        {(['print', 'approach', 'lift', 'transfer'] as const).map((k) => (
          <Group key={k} gap={4} wrap="nowrap">
            <Box w={10} h={10} style={{ background: KIND_COLOR[k], borderRadius: 2 }} />
            <Text size="xs">{k === 'approach' ? 'An-/Abfahrt' : k === 'lift' ? 'Heben/Senken' : KIND_LABEL[k]}</Text>
          </Group>
        ))}
        {(['warn', 'collision', 'unreachable'] as const).map((k) => (
          <Group key={k} gap={4} wrap="nowrap">
            <Box w={10} h={10} style={{ background: STATUS_COLOR[k], borderRadius: 2 }} />
            <Text size="xs">{STATUS_LABEL[k]}</Text>
          </Group>
        ))}
      </Group>
    </Stack>
  );
}
