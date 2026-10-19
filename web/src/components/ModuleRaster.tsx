import { Group, Paper, Stack, Text } from '@mantine/core';
import { fmt } from '../player/labels';
import type { RunData } from '../state/store';
import { formatDuration, minDistance, moduleProgress, partRectInWall, tallestModuleMm, totalPrintTimeS } from '../state/moduleView';

const v = (c: string) => `var(--mantine-color-${c})`;

function Stat({ label, value, testid }: { label: string; value: string; testid: string }) {
  return (
    <Stack gap={0} data-testid={testid}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text size="sm" fw={600}>
        {value}
      </Text>
    </Stack>
  );
}

/** Kennzahlen des Laufs: Anzahl Module, Druckzeit, kleinster Abstand, höchstes Modul (mit Nutzergrenze). */
export function RunStats({ run }: { run: RunData }) {
  const parts = run.summary.parts;
  const dmin = minDistance(parts);
  const tallest = tallestModuleMm(run.parts);
  const limit = run.summary.params.module_height_max_mm;
  return (
    <Group gap="lg" data-testid="run-stats">
      <Stat label="Module" value={String(parts.length)} testid="stat-count" />
      <Stat label="Druckzeit" value={formatDuration(totalPrintTimeS(run.trajectory))} testid="stat-time" />
      <Stat label="kleinster Abstand" value={dmin === null ? 'unbekannt' : `${fmt(dmin)} mm`} testid="stat-dmin" />
      {tallest !== null ? (
        <Stat
          label={typeof limit === 'number' ? `höchstes Modul (Grenze ${fmt(limit, 0)} mm)` : 'höchstes Modul'}
          value={`${fmt(tallest, 0)} mm`}
          testid="stat-tallest"
        />
      ) : null}
    </Group>
  );
}

interface RasterProps {
  run: RunData;
  stale: boolean;
  partId: string | null;
  onSelect: (partId: string) => void;
}

/** Module in Wandansicht (Ebene x–z von L), gefärbt nach Status; Klick wählt das Modul. */
export function ModuleRaster({ run, stale, partId, onSelect }: RasterProps) {
  const parts = run.summary.parts;
  const wallIds = [...new Set(parts.map((p) => p.wall_id))];
  return (
    <Stack gap="xs" data-testid="module-raster">
      {wallIds.map((wid) => {
        const wall = run.summary.walls.find((w) => w.wall_id === wid);
        const inWall = parts.filter((p) => p.wall_id === wid);
        const rects = inWall.map((p) => ({ p, r: run.parts[p.part_id] ? partRectInWall(run.parts[p.part_id]!) : null }));
        // Ohne Wandmaß (Direkteinstieg) bestimmt die Hülle der Module den Ausschnitt.
        const W = wall?.length_mm ?? Math.max(1, ...rects.map((x) => x.r?.x1 ?? 0));
        const H = wall?.height_mm ?? Math.max(1, ...rects.map((x) => x.r?.z1 ?? 0));
        const pad = Math.max(W, H) * 0.02;
        return (
          <Paper withBorder p="xs" key={wid} data-testid={`module-raster-${wid}`}>
            <Text size="xs" c="dimmed" mb={4}>
              Wandansicht{wall ? `: ${wall.name}` : ''}
            </Text>
            <svg
              viewBox={`${-pad} ${-pad} ${W + 2 * pad} ${H + 2 * pad}`}
              role="img"
              aria-label="Module in Wandansicht"
              style={{ width: '100%', maxHeight: 220, display: 'block' }}
              preserveAspectRatio="xMidYMid meet"
            >
              <rect x={0} y={0} width={W} height={H} style={{ fill: v('gray-1'), stroke: v('gray-6') }} strokeWidth={pad / 3} />
              {rects.map(({ p, r }) => {
                if (!r) return null;
                const ok = p.status === 'machbar';
                const fill = stale ? v('gray-5') : ok ? v('green-6') : v('red-6');
                const selected = p.part_id === partId;
                return (
                  <g key={p.part_id} onClick={() => onSelect(p.part_id)} style={{ cursor: 'pointer' }} data-testid={`module-cell-${p.part_id}`} data-status={p.status} data-selected={selected}>
                    <rect
                      x={r.x0}
                      y={H - r.z1}
                      width={r.x1 - r.x0}
                      height={r.z1 - r.z0}
                      style={{ fill, stroke: selected ? v('blue-6') : v('body'), fillOpacity: 0.8 }}
                      strokeWidth={selected ? pad / 1.5 : pad / 4}
                    />
                    <title>{`${p.part_id}: ${p.status}`}</title>
                  </g>
                );
              })}
            </svg>
          </Paper>
        );
      })}
    </Stack>
  );
}

/** Streifen mit einer Zelle je Modul während der Rechnung (aus „Teil i/n“ der Job-Meldung). */
export function ModuleProgress({ stage, message }: { stage: string | null; message: string | null }) {
  const cells = moduleProgress(stage, message);
  if (!cells) return null;
  const color = { fertig: v('green-6'), aktiv: v('blue-6'), wartet: v('gray-3') } as const;
  const text = { fertig: 'fertig', aktiv: 'wird geprüft', wartet: 'wartet' } as const;
  return (
    <Group gap={4} mt="xs" wrap="wrap" data-testid="module-progress">
      {cells.map((c, k) => (
        <div
          key={k}
          title={`Modul ${k + 1}: ${text[c]}`}
          data-testid={`module-progress-${k + 1}`}
          data-state={c}
          style={{ width: 22, height: 12, borderRadius: 3, background: color[c] }}
        />
      ))}
      <Text size="xs" c="dimmed">
        {cells.filter((c) => c === 'fertig').length} von {cells.length} Modulen fertig
      </Text>
    </Group>
  );
}
