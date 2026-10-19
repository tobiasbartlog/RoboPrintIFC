import { ActionIcon, Badge, Group, Loader, Paper, Select, Slider, Stack, Table, Text } from '@mantine/core';
import { ErrorNote } from '../components/common';
import { useAppStore } from '../state/storeContext';
import { duration, sampleAt } from './clock';
import { CollisionList } from './CollisionList';
import { KIND_LABEL, STATUS_BADGE, STATUS_LABEL, clock, fmt, linkLabel, obstacleLabel } from './labels';
import { Timeline } from './Timeline';

const SPEEDS = ['0.25', '0.5', '1', '2', '5', '10', '25'];

/**
 * Player: Abspielen, Scrubber, Timeline, Kollisionsliste und die Werte zum aktuellen `t`.
 * Alle Anzeigen kommen aus `sampleAt(t_s, t)`; es gibt keine zweite Zeitabbildung.
 */
export function PlayerPanel() {
  const t = useAppStore((s) => s.t);
  const pb = useAppStore((s) => s.playback);
  const loading = useAppStore((s) => s.playbackLoading);
  const error = useAppStore((s) => s.playbackError);
  const errorDetail = useAppStore((s) => s.playbackErrorDetail);
  const playing = useAppStore((s) => s.playing);
  const speed = useAppStore((s) => s.speed);
  const play = useAppStore((s) => s.play);
  const pause = useAppStore((s) => s.pause);
  const setSpeed = useAppStore((s) => s.setSpeed);
  const scrub = useAppStore((s) => s.scrub);
  const selectCollision = useAppStore((s) => s.selectCollision);
  const partId = useAppStore((s) => s.partId);

  const tr = pb && pb.partId === partId ? pb.trajectory : null;

  if (!tr) {
    return (
      <Paper withBorder p="sm" data-testid="player-panel" data-ready={false}>
        <Text fw={600} size="sm">
          Wiedergabe
        </Text>
        {error ? (
          <ErrorNote message={error} detail={errorDetail} testid="player-error" />
        ) : (
          <Group gap="xs">
            {loading ? <Loader size="xs" /> : null}
            <Text size="sm" c="dimmed">
              {loading ? 'Bahn wird geladen …' : 'Erst ein Teil wählen.'}
            </Text>
          </Group>
        )}
      </Paper>
    );
  }

  const end = duration(tr);
  const i = sampleAt(tr.t_s, t);
  const status = tr.status[i] ?? 'ok';
  const d = tr.d_mm[i];
  const pair = tr.pair[i];

  return (
    <Paper withBorder p="sm" data-testid="player-panel" data-ready>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <Text fw={600} size="sm">
            Wiedergabe
          </Text>
          <Text size="sm" ff="monospace" data-testid="player-time">
            {clock(t)} / {clock(end)} min
          </Text>
        </Group>
        <Group gap="xs" wrap="nowrap">
          <ActionIcon variant="default" aria-label="Zum Anfang" onClick={() => scrub(0)} data-testid="player-start">
            ⏮
          </ActionIcon>
          {playing ? (
            <ActionIcon variant="filled" aria-label="Pause" onClick={pause} data-testid="player-pause">
              ⏸
            </ActionIcon>
          ) : (
            <ActionIcon variant="filled" aria-label="Abspielen" onClick={play} data-testid="player-play">
              ▶
            </ActionIcon>
          )}
          <ActionIcon variant="default" aria-label="Zum Ende" onClick={() => scrub(end)} data-testid="player-end">
            ⏭
          </ActionIcon>
          <Select
            aria-label="Geschwindigkeit"
            size="xs"
            w={90}
            data={SPEEDS.map((v) => ({ value: v, label: `${v.replace('.', ',')}×` }))}
            value={String(speed)}
            onChange={(v) => v && setSpeed(Number(v))}
            allowDeselect={false}
            data-testid="player-speed"
          />
        </Group>
        <Slider
          min={0}
          max={end}
          step={Math.max(end / 2000, 0.001)}
          value={Math.min(t, end)}
          onChange={scrub}
          label={(v) => `${clock(v)} min`}
          aria-label="Zeit"
          data-testid="player-scrubber"
        />
        <Timeline trajectory={tr} t={t} onSeek={scrub} />

        <Table withRowBorders={false} verticalSpacing={2} fz="sm" data-testid="player-readout" data-index={i} data-status={status}>
          <Table.Tbody>
            <Table.Tr>
              <Table.Td c="dimmed" w={100}>Status</Table.Td>
              <Table.Td>
                <Badge color={STATUS_BADGE[status]} variant="filled" data-testid="player-status">
                  {STATUS_LABEL[status]}
                </Badge>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed" w={100}>Abstand</Table.Td>
              <Table.Td data-testid="player-distance">
                {typeof d === 'number' ? `${fmt(d)} mm` : 'keiner (unerreichbar)'}
                {pair ? ` · ${linkLabel(pair[0])} ↔ ${obstacleLabel(pair[1])}` : ''}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed" w={100}>Schicht</Table.Td>
              <Table.Td data-testid="player-layer">{tr.layer[i] ?? 0} fertig</Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed" w={100}>Ring</Table.Td>
              <Table.Td data-testid="player-ring">
                {tr.ring[i] ?? 0} · {KIND_LABEL[tr.kind[i] ?? 'print']}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed" w={100}>Armstellung</Table.Td>
              <Table.Td data-testid="player-branch">{tr.branch[i] ?? '–'}</Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed" w={100}>Bahnpunkt</Table.Td>
              <Table.Td data-testid="player-index">
                {(i + 1).toLocaleString('de-DE')} von {tr.t_s.length.toLocaleString('de-DE')}
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>

        <CollisionList trajectory={tr} onSelect={selectCollision} activeT={t} />
      </Stack>
    </Paper>
  );
}
