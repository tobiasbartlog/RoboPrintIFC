import { Paper, Text } from '@mantine/core';
import { useAppStore } from '../state/storeContext';

/** Platzhalter für den Player (A3.4: eine Uhr `t`, Timeline, Kollisionsliste, Debug-Schnittstelle). */
export function PlayerPanel() {
  const t = useAppStore((s) => s.t);
  return (
    <Paper withBorder p="sm" data-testid="player-panel">
      <Text fw={600} size="sm">
        Wiedergabe
      </Text>
      <Text size="sm" c="dimmed">
        Zeitleiste und Abspielen folgen. Aktuelle Zeit: {t.toFixed(1)} s
      </Text>
    </Paper>
  );
}
