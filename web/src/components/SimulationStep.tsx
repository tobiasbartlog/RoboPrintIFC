import { Badge, Button, Stack, Text, Title, UnstyledButton } from '@mantine/core';
import { useMemo } from 'react';
import { PlayerPanel } from '../player/PlayerPanel';
import { groupOf, groupParts } from '../state/partGroups';
import { useAppStore, useSteps } from '../state/storeContext';
import { ErrorNote, StaleBanner } from './common';
import { GroupMembers } from './GroupMembers';

export function SimulationStep() {
  const run = useAppStore((s) => s.run);
  const partId = useAppStore((s) => s.partId);
  const selectPart = useAppStore((s) => s.selectPart);
  const setStep = useAppStore((s) => s.setStep);
  const runError = useAppStore((s) => s.runError);
  const runErrorDetail = useAppStore((s) => s.runErrorDetail);
  const direct = useAppStore((s) => s.run?.basis.direct === true);
  const { status } = useSteps();
  const stale = status.simulation === 'veraltet';
  const parts = run?.summary.parts;
  const groups = useMemo(() => groupParts(parts ?? []), [parts]);
  const rep = groupOf(groups, partId)?.rep.part_id ?? null;

  return (
    <Stack gap="md" data-testid="step-simulation-panel">
      <Title order={3}>Simulation</Title>
      <StaleBanner show={stale} />
      {runError ? <ErrorNote message={runError} detail={runErrorDetail} testid="run-error" /> : null}
      {direct ? (
        <Text size="sm" data-testid="direct-run">
          Gespeicherter Lauf {run?.runId} ({run?.summary.scenario_id}), direkt geöffnet.
        </Text>
      ) : null}
      <Text size="sm" c="dimmed">
        Modul wählen und abspielen. Der Arm steht am Doosantisch, das Modul wächst Schicht für Schicht. Rot heißt
        Kollision, Gelb Abstand unter dem Sollwert.
      </Text>
      {parts && groups.length < parts.length ? (
        <Text size="sm" c="dimmed" data-testid="sim-group-note">
          {parts.length} Module, {groups.length} verschiedene Geometrien. Module gleicher Geometrie haben dieselbe Bahn
          und dasselbe Prüfergebnis und sind hier zusammengefasst.
        </Text>
      ) : null}
      <Stack gap="xs" data-testid="sim-part-select">
        {groups.map((g) => {
          const id = g.rep.part_id;
          const selected = rep === id;
          return (
            <GroupMembers key={id} group={g} partId={partId} onSelect={selectPart} testid={`sim-group-${id}`}>
              <UnstyledButton onClick={() => selectPart(id)} data-testid={`sim-part-${id}`} data-selected={selected}>
                <Badge
                  size="lg"
                  tt="none"
                  variant={selected ? 'filled' : 'outline'}
                  color={stale ? 'gray' : g.rep.status === 'machbar' ? 'green' : 'red'}
                >
                  {id}
                </Badge>
              </UnstyledButton>
            </GroupMembers>
          );
        })}
      </Stack>
      <Text size="sm" data-testid="sim-selected">
        Ausgewähltes Teil: {partId ?? 'keines'}
        {partId !== null && rep !== null && rep !== partId ? ` (gleiche Geometrie wie ${rep})` : ''}
      </Text>
      <PlayerPanel />
      <Button onClick={() => setStep('export')} data-testid="to-export">
        Weiter zum Export
      </Button>
    </Stack>
  );
}
