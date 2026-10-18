import { Badge, Button, Group, Stack, Text, Title, UnstyledButton } from '@mantine/core';
import { PlayerPanel } from '../player/PlayerPanel';
import { useAppStore, useSteps } from '../state/storeContext';
import { StaleBanner } from './common';

export function SimulationStep() {
  const run = useAppStore((s) => s.run);
  const partId = useAppStore((s) => s.partId);
  const selectPart = useAppStore((s) => s.selectPart);
  const setStep = useAppStore((s) => s.setStep);
  const { status } = useSteps();
  const stale = status.simulation === 'veraltet';

  return (
    <Stack gap="md" data-testid="step-simulation-panel">
      <Title order={3}>Simulation</Title>
      <StaleBanner show={stale} />
      <Text size="sm" c="dimmed">
        Modul wählen und abspielen. Der Arm steht am Doosantisch, das Modul wächst Schicht für Schicht.
      </Text>
      <Group gap="xs" data-testid="sim-part-select">
        {run?.summary.parts.map((p) => (
          <UnstyledButton key={p.part_id} onClick={() => selectPart(p.part_id)} data-testid={`sim-part-${p.part_id}`} data-selected={partId === p.part_id}>
            <Badge
              size="lg"
              variant={partId === p.part_id ? 'filled' : 'outline'}
              color={stale ? 'gray' : p.status === 'machbar' ? 'green' : 'red'}
            >
              {p.part_id}
            </Badge>
          </UnstyledButton>
        ))}
      </Group>
      <Text size="sm" data-testid="sim-selected">
        Ausgewähltes Teil: {partId ?? 'keines'}
      </Text>
      <PlayerPanel />
      <Button onClick={() => setStep('export')} data-testid="to-export">
        Weiter zum Export
      </Button>
    </Stack>
  );
}
