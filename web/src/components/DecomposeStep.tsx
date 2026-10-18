import { Badge, Button, Group, Paper, Progress, Stack, Text, Title } from '@mantine/core';
import { isJobRunning } from '../state/store';
import { useAppStore, useSteps } from '../state/storeContext';
import { ErrorNote, Reason, StaleBanner } from './common';
import { ParamsPanel } from './ParamsPanel';

export function DecomposeStep() {
  const wallId = useAppStore((s) => s.wallId);
  const wallName = useAppStore((s) => s.project?.walls.find((w) => w.wall_id === s.wallId)?.name ?? null);
  const running = useAppStore(isJobRunning);
  const job = useAppStore((s) => s.job);
  const run = useAppStore((s) => s.run);
  const start = useAppStore((s) => s.startJob);
  const cancel = useAppStore((s) => s.cancelJob);
  const setStep = useAppStore((s) => s.setStep);
  const { status, blocked } = useSteps();

  const stale = status.decompose === 'veraltet';
  const reason = running ? 'Die Rechnung läuft bereits.' : blocked('decompose');
  const pct = Math.round((job.state?.progress ?? 0) * 100);
  const hasFreshRun = status.decompose === 'aktuell';
  const cancelled = job.state?.state === 'cancelled';

  return (
    <Stack gap="md" data-testid="step-decompose-panel">
      <Title order={3}>Zerlegen & prüfen</Title>
      <Text size="sm" data-testid="decompose-wall">
        Wand: {wallName ?? 'noch keine gewählt'}
      </Text>
      <ParamsPanel />

      <Stack gap={4}>
        <Button
          variant={hasFreshRun ? 'default' : 'filled'}
          disabled={reason !== null || wallId === null}
          onClick={() => void start()}
          data-testid="start-job"
        >
          Zerlegen & prüfen
        </Button>
        <Reason text={reason} testid="start-job-reason" />
      </Stack>

      {job.state && (running || cancelled) ? (
        <Paper withBorder p="sm" data-testid="job-progress" data-state={job.state.state}>
          <Group justify="space-between">
            <Text size="sm" fw={600} data-testid="job-stage">
              {cancelled ? 'Abgebrochen' : (job.state.stage ?? 'Wartet auf Start')}
            </Text>
            <Text size="sm" data-testid="job-percent">
              {pct} %
            </Text>
          </Group>
          <Progress value={pct} my="xs" animated={running} />
          {job.state.message ? (
            <Text size="xs" c="dimmed" data-testid="job-message">
              {job.state.message}
            </Text>
          ) : null}
          {running ? (
            <Button variant="default" size="compact-sm" mt="xs" onClick={() => void cancel()} disabled={!job.jobId} data-testid="job-cancel">
              Abbrechen
            </Button>
          ) : null}
        </Paper>
      ) : null}

      {job.error ? <ErrorNote message={job.error} detail={job.errorDetail} testid="job-error" /> : null}
      <StaleBanner show={stale} />

      {run ? (
        <Stack gap="xs" data-testid="part-list" data-stale={stale}>
          <Group justify="space-between">
            <Text fw={600}>Teile ({run.summary.parts.length})</Text>
            <Text size="xs" c="dimmed" data-testid="samples-count">
              Samples: {Object.values(run.trajectory).reduce((a, t) => a + t.n, 0).toLocaleString('de-DE')}
            </Text>
          </Group>
          {run.summary.parts.map((p) => {
            const art = run.parts[p.part_id];
            const ok = p.status === 'machbar';
            const color = stale ? 'gray' : ok ? 'green' : 'red';
            const tr = run.trajectory[p.part_id];
            return (
              <Paper key={p.part_id} withBorder p="xs" data-testid={`part-row-${p.part_id}`}>
                <Group justify="space-between">
                  <Text size="sm" fw={500}>
                    {p.part_id}
                  </Text>
                  <Badge color={color} variant={stale ? 'outline' : 'filled'} data-testid={`part-status-${p.part_id}`}>
                    {p.status}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed" data-testid={`part-dmin-${p.part_id}`}>
                  kleinster Abstand d_min: {p.d_min_mm === null ? 'unbekannt' : `${p.d_min_mm.toLocaleString('de-DE', { maximumFractionDigits: 1 })} mm`}
                  {art ? ` · ${art.n_layers} Schichten` : ''}
                </Text>
                {tr ? (
                  <Text size="xs" c="dimmed" data-testid={`part-samples-${p.part_id}`}>
                    {tr.n} Samples: {tr.n_ok} ok, {tr.n_warn} Warnung, {tr.n_collision} Kollision, {tr.n_unreachable} unerreichbar
                  </Text>
                ) : null}
                {!ok && art?.cause ? (
                  <Text size="xs" c="red" data-testid={`part-cause-${p.part_id}`}>
                    {art.cause.message}
                  </Text>
                ) : null}
              </Paper>
            );
          })}
          <Stack gap={4}>
            <Button disabled={status.simulation === 'fehlt'} onClick={() => setStep('simulation')} data-testid="to-simulation">
              Weiter zur Simulation
            </Button>
          </Stack>
        </Stack>
      ) : null}
    </Stack>
  );
}
