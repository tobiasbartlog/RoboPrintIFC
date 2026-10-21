import { Badge, Button, Group, Paper, Progress, Stack, Text, Title } from '@mantine/core';
import { clock, linkLabel, obstacleLabel } from '../player/labels';
import { isJobRunning } from '../state/store';
import { useAppStore, useSteps } from '../state/storeContext';
import { ErrorNote, Reason, StaleBanner } from './common';
import { ModuleProgress, ModuleRaster, RunStats } from './ModuleRaster';
import { LayerPreview } from './LayerPreview';
import { ParamsPanel } from './ParamsPanel';
import { PartPatternStats } from './PartPatternStats';
import { PatternChoice } from './PatternChoice';
import { stageLabel } from '../state/moduleView';

const num = (n: number) => n.toLocaleString('de-DE');

export function DecomposeStep() {
  const wallId = useAppStore((s) => s.wallId);
  const wallName = useAppStore((s) => s.project?.walls.find((w) => w.wall_id === s.wallId)?.name ?? null);
  const running = useAppStore(isJobRunning);
  const job = useAppStore((s) => s.job);
  const run = useAppStore((s) => s.run);
  const start = useAppStore((s) => s.startJob);
  const cancel = useAppStore((s) => s.cancelJob);
  const setStep = useAppStore((s) => s.setStep);
  const partId = useAppStore((s) => s.partId);
  const selectPart = useAppStore((s) => s.selectPart);
  const { status, blocked } = useSteps();

  const stale = status.decompose === 'veraltet';
  const reason = running
    ? 'Die Rechnung läuft bereits.'
    : (blocked('decompose') ?? (wallId === null ? 'Erst im Schritt Modell eine Wand wählen.' : null));
  const pct = Math.round((job.state?.progress ?? 0) * 100);
  const hasFreshRun = status.decompose === 'aktuell';
  const cancelled = job.state?.state === 'cancelled';

  return (
    <Stack gap="md" data-testid="step-decompose-panel">
      <Title order={3}>Zerlegen & prüfen</Title>
      <Text size="sm" data-testid="decompose-wall">
        Wand: {wallName ?? (run?.basis.direct ? 'keine (Lauf direkt geöffnet)' : 'noch keine gewählt')}
      </Text>
      <PatternChoice />
      <ParamsPanel />

      {/* Bleibt am unteren Rand der Seitenleiste sichtbar, auch wenn die Druckeinstellungen aufgeklappt sind. */}
      <Stack
        gap={4}
        py="xs"
        data-testid="start-job-bar"
        style={{
          position: 'sticky',
          bottom: 0,
          zIndex: 3,
          background: 'var(--mantine-color-body)',
          borderTop: '1px solid var(--mantine-color-default-border)',
        }}
      >
        <Button
          variant={hasFreshRun ? 'default' : 'filled'}
          disabled={reason !== null}
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
              {cancelled ? 'Abgebrochen' : stageLabel(job.state.stage)}
            </Text>
            <Text size="sm" data-testid="job-percent">
              {pct} %
            </Text>
          </Group>
          <Progress value={pct} my="xs" animated={running} />
          {running ? <ModuleProgress stage={job.state.stage} message={job.state.message} /> : null}
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
              {num(Object.values(run.trajectory).reduce((a, t) => a + t.n, 0))} Bahnpunkte geprüft
            </Text>
          </Group>
          <RunStats run={run} />
          <ModuleRaster run={run} stale={stale} partId={partId} onSelect={selectPart} />
          {run.summary.parts.map((p) => {
            const art = run.parts[p.part_id];
            const ok = p.status === 'machbar';
            const color = stale ? 'gray' : ok ? 'green' : 'red';
            const tr = run.trajectory[p.part_id];
            return (
              <Paper key={p.part_id} withBorder p="xs" data-testid={`part-row-${p.part_id}`}>
                <Group justify="space-between">
                  <Group gap="xs">
                    <Text size="sm" fw={500}>
                      {p.part_id}
                    </Text>
                    <Button
                      size="compact-xs"
                      variant={partId === p.part_id ? 'light' : 'subtle'}
                      onClick={() => selectPart(p.part_id)}
                      data-testid={`part-view-${p.part_id}`}
                    >
                      {partId === p.part_id ? 'in 3D gezeigt' : 'in 3D zeigen'}
                    </Button>
                  </Group>
                  <Badge color={color} variant={stale ? 'outline' : 'filled'} data-testid={`part-status-${p.part_id}`}>
                    {p.status}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed" data-testid={`part-dmin-${p.part_id}`}>
                  kleinster Abstand: {p.d_min_mm === null ? 'unbekannt' : `${p.d_min_mm.toLocaleString('de-DE', { maximumFractionDigits: 1 })} mm`}
                  {art ? ` · ${art.n_layers} Schichten` : ''}
                </Text>
                {tr ? (
                  <Text size="xs" c="dimmed" data-testid={`part-samples-${p.part_id}`}>
                    {num(tr.n)} Bahnpunkte: {num(tr.n_ok)} frei, {num(tr.n_warn)} unter Sollabstand, {num(tr.n_collision)} Kollision,{' '}
                    {num(tr.n_unreachable)} unerreichbar
                  </Text>
                ) : null}
                {partId === p.part_id ? (
                  <Stack gap="xs" mt={4} data-testid={`part-pattern-${p.part_id}`}>
                    <PartPatternStats partId={p.part_id} />
                    <LayerPreview partId={p.part_id} />
                  </Stack>
                ) : null}
                {!ok && art?.cause ? (
                  <Stack gap={0} data-testid={`part-cause-${p.part_id}`}>
                    <Text size="xs" c="red">
                      {art.cause.link && art.cause.obstacle
                        ? `Erstes Problem bei ${clock(art.cause.t_s)} min: ${linkLabel(art.cause.link)} ↔ ${obstacleLabel(art.cause.obstacle)} zu nah. In der Simulation ansehen, dann Parameter oder Wand ändern.`
                        : art.cause.message}
                    </Text>
                    <details>
                      <summary style={{ cursor: 'pointer' }}>
                        <Text span size="xs" c="dimmed">
                          Details
                        </Text>
                      </summary>
                      <Text size="xs" c="dimmed" ff="monospace">
                        {art.cause.message}
                      </Text>
                    </details>
                  </Stack>
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
