import { Button, Group, Progress, Text } from '@mantine/core';
import { isJobRunning } from '../state/store';
import { useAppStore } from '../state/storeContext';

/** Zentrale Job-Leiste: laufende Rechnung mit Fortschritt und Abbrechen. */
export function JobBar() {
  const running = useAppStore(isJobRunning);
  const job = useAppStore((s) => s.job);
  const cancel = useAppStore((s) => s.cancelJob);
  if (!running || !job.state) return null;
  const pct = Math.round(job.state.progress * 100);
  return (
    <Group gap="sm" wrap="nowrap" data-testid="job-bar">
      <Text size="sm">{job.state.stage ?? 'Wartet'}</Text>
      <Progress value={pct} w={140} animated />
      <Text size="sm">{pct} %</Text>
      <Button size="compact-sm" variant="default" onClick={() => void cancel()} disabled={!job.jobId} data-testid="job-bar-cancel">
        Abbrechen
      </Button>
    </Group>
  );
}
