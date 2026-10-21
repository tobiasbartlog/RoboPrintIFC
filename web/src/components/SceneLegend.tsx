import { Box, Group, Paper, Text } from '@mantine/core';
import { useMemo } from 'react';
import { segmentStyle } from '../state/patterns';
import { useAppStore } from '../state/storeContext';

/** Arten in der Reihenfolge der Legende; `outer`, `inner` und `hole` heißen in 3D gemeinsam „Schalen“. */
const SHELL_KINDS = ['outer', 'inner', 'hole'];
const PATTERN_ORDER = ['infill', 'web', 'outfill'];

/**
 * Legende der 3D-Ansicht: Segmentarten des Musters mit den Farben der Bahn und der Raupen (gleiche
 * Farben wie die 2D-Vorschau). Erscheint nur, wenn das gezeigte Teil Musterarten enthält; ohne
 * Muster bleibt die Ansicht wie bisher einfarbig.
 */
export function SceneLegend() {
  const toolpath = useAppStore((s) => (s.playback && s.playback.partId === s.partId ? (s.playback.loaded.parts[s.playback.partId]?.toolpath ?? null) : null));
  const kinds = useMemo(() => {
    const present = new Set<string>(toolpath?.rings.map((r) => r.kind) ?? []);
    return {
      shells: SHELL_KINDS.some((k) => present.has(k)),
      pattern: PATTERN_ORDER.filter((k) => present.has(k)),
      others: [...present].filter((k) => !SHELL_KINDS.includes(k) && !PATTERN_ORDER.includes(k)),
    };
  }, [toolpath]);
  if (kinds.pattern.length === 0 && kinds.others.length === 0) return null;
  const item = (key: string, label: string, color: string) => (
    <Group key={key} gap={4} wrap="nowrap" data-testid={`scene-legend-${key}`}>
      <Box component="span" style={{ width: 14, height: 5, borderRadius: 2, background: color, display: 'inline-block' }} aria-hidden="true" />
      <Text size="xs">{label}</Text>
    </Group>
  );
  return (
    <Paper withBorder p={6} data-testid="scene-legend" style={{ position: 'absolute', left: 12, top: 12, maxWidth: 'calc(100% - 24px)', pointerEvents: 'none', opacity: 0.95 }}>
      <Group gap="sm" wrap="wrap">
        {kinds.shells ? item('shells', 'Schalen', 'var(--mantine-color-orange-6)') : null}
        {[...kinds.pattern, ...kinds.others].map((k) => item(k, segmentStyle(k).label, segmentStyle(k).color))}
        {item('link', 'Verbinder (Bahn)', 'var(--mantine-color-dark-6)')}
      </Group>
    </Paper>
  );
}
