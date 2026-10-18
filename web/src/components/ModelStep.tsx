import { Badge, Button, FileButton, Group, Loader, Paper, Radio, Stack, Text, Title } from '@mantine/core';
import { useEffect } from 'react';
import type { WallEntry } from '../contracts';
import { useAppStore, useSteps } from '../state/storeContext';
import { ErrorNote, Reason } from './common';

function dims(w: WallEntry): string {
  const n = (v: number) => Math.round(v).toLocaleString('de-DE');
  return `${n(w.length_mm)} × ${n(w.height_mm)} × ${n(w.thickness_mm)} mm`;
}

export function ModelStep() {
  const examples = useAppStore((s) => s.examples);
  const loadExamples = useAppStore((s) => s.loadExamples);
  const openExample = useAppStore((s) => s.openExample);
  const openFile = useAppStore((s) => s.openFile);
  const busy = useAppStore((s) => s.projectBusy);
  const error = useAppStore((s) => s.projectError);
  const detail = useAppStore((s) => s.projectErrorDetail);
  const project = useAppStore((s) => s.project);
  const wallId = useAppStore((s) => s.wallId);
  const selectWall = useAppStore((s) => s.selectWall);
  const setStep = useAppStore((s) => s.setStep);
  const { blocked } = useSteps();

  useEffect(() => {
    void loadExamples();
  }, [loadExamples]);

  const next = blocked('decompose');
  return (
    <Stack gap="md" data-testid="step-model-panel">
      <Title order={3}>Modell</Title>
      <Stack gap="xs">
        <Text size="sm" fw={600}>
          Beispiel öffnen oder IFC-Datei hochladen
        </Text>
        {examples.map((ex) => (
          <Button key={ex.id} variant="default" justify="flex-start" disabled={busy} onClick={() => void openExample(ex.path)} data-testid={`example-${ex.id}`}>
            {ex.name}
            {ex.description ? (
              <Text span size="xs" c="dimmed" ml="xs">
                {ex.description}
              </Text>
            ) : null}
          </Button>
        ))}
        <FileButton accept=".ifc" onChange={(f) => f && void openFile(f)}>
          {(props) => (
            <Button {...props} variant="light" disabled={busy} data-testid="upload-ifc">
              IFC-Datei hochladen
            </Button>
          )}
        </FileButton>
        {busy ? <Loader size="sm" data-testid="project-loading" /> : null}
        {error ? <ErrorNote message={error} detail={detail} testid="project-error" /> : null}
      </Stack>

      {project ? (
        <Stack gap="xs" data-testid="wall-list">
          <Group justify="space-between">
            <Text size="sm" fw={600} data-testid="project-name">
              {project.name}
            </Text>
            <Text size="xs" c="dimmed">
              {project.walls.length} Wände
            </Text>
          </Group>
          <Radio.Group value={wallId ?? ''} onChange={selectWall}>
            <Stack gap="xs">
              {project.walls.map((w) => (
                <Paper key={w.wall_id} withBorder p="xs" data-testid={`wall-row-${w.wall_id}`} data-eligible={w.eligible}>
                  <Radio
                    value={w.wall_id}
                    disabled={!w.eligible}
                    data-testid={`wall-select-${w.wall_id}`}
                    label={
                      <Group gap="xs">
                        <Text size="sm" fw={500}>
                          {w.name}
                        </Text>
                        <Text size="xs" c="dimmed" data-testid={`wall-dims-${w.wall_id}`}>
                          {dims(w)}
                        </Text>
                        <Badge size="sm" color={w.eligible ? 'green' : 'red'} variant="light" data-testid={`wall-eligible-${w.wall_id}`}>
                          {w.eligible ? 'geeignet' : 'ungeeignet'}
                        </Badge>
                      </Group>
                    }
                  />
                  {w.reason ? (
                    <Text size="xs" c="red" mt={4} data-testid={`wall-reason-${w.wall_id}`}>
                      {w.reason}
                    </Text>
                  ) : null}
                </Paper>
              ))}
            </Stack>
          </Radio.Group>
        </Stack>
      ) : null}

      <Stack gap={4}>
        <Button disabled={next !== null} onClick={() => setStep('decompose')} data-testid="to-decompose">
          Weiter zu Zerlegen & prüfen
        </Button>
        <Reason text={next} testid="to-decompose-reason" />
      </Stack>
    </Stack>
  );
}
