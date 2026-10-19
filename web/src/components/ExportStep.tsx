import { Alert, Badge, Box, Button, Code, Group, List, Paper, Stack, Text, Title } from '@mantine/core';
import { useState } from 'react';
import { useAppStore, useSteps } from '../state/storeContext';
import { ErrorNote, StaleBanner } from './common';

type Dialect = 'v2' | 'v3';

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Lädt die DRL-Datei über den ApiPort des Stores (ein Pfad für Anzeige und Download). */
export function ExportStep() {
  const run = useAppStore((s) => s.run);
  const loadRun = useAppStore((s) => s.loadRunFile);
  const { status } = useSteps();
  const stale = status.export === 'veraltet';
  // Hauptaktion ist der Download im gewählten Dialekt (Parameter, Standard v2).
  const dialect: Dialect = useAppStore((s) => (s.params.dialect === 'v3' ? 'v3' : 'v2'));
  const [preview, setPreview] = useState<{ key: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);

  async function fetchDrl(partId: string, d: Dialect): Promise<string | null> {
    if (!run) return null;
    setError(null);
    try {
      return await loadRun(`parts/${partId}/program.${d}.drl`);
    } catch (e) {
      setError(`Das ${d.toUpperCase()}-Programm für ${partId} konnte nicht geladen werden. Erneut versuchen.`);
      setDetail(e instanceof Error ? e.message : String(e));
      return null;
    }
  }

  async function show(partId: string, d: Dialect) {
    const text = await fetchDrl(partId, d);
    if (text !== null) setPreview({ key: `${partId}-${d}`, text });
  }
  async function save(partId: string, d: Dialect) {
    const text = await fetchDrl(partId, d);
    if (text !== null) download(`${run?.summary.scenario_id ?? 'lauf'}_${partId}.${d}.drl`, text);
  }

  const headerLines = preview?.text.split('\n').filter((l) => l.startsWith('#')) ?? [];

  return (
    <Stack gap="md" data-testid="step-export-panel">
      <Title order={3}>Export</Title>
      <StaleBanner show={stale} />
      <Alert color="orange" title="Vor dem ersten Druck" data-testid="export-dry-run-note">
        Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck.
      </Alert>

      <Text size="sm" c="dimmed">
        Je Modul ein DRL-Programm für den Doosan M1013. Gewählter Dialekt: {dialect} ({dialect === 'v2' ? 'Firmware 2.x' : 'Firmware 3.x'});
        der Dialekt lässt sich unter „Zerlegen & prüfen“ → Druckeinstellungen → Steuerung & Export ändern.
      </Text>
      <Stack gap="xs" data-testid="export-parts">
        {run?.summary.parts.map((p) => {
          const ok = p.status === 'machbar';
          return (
            <Paper key={p.part_id} withBorder p="xs" data-testid={`export-part-${p.part_id}`}>
              <Group justify="space-between" mb={4}>
                <Text size="sm" fw={500}>
                  {p.part_id}
                </Text>
                <Badge color={stale ? 'gray' : ok ? 'green' : 'red'} variant={stale ? 'outline' : 'filled'}>
                  {p.status}
                </Badge>
              </Group>
              {!ok ? (
                <Text size="xs" c="red" data-testid={`export-warning-${p.part_id}`}>
                  Dieses Teil ist nicht machbar. Das Programm nicht drucken, sondern erst die Ursache beheben.
                </Text>
              ) : null}
              <Group gap="xs">
                {(['v2', 'v3'] as const).map((d) => (
                  <Group key={d} gap={4}>
                    <Button
                      size="compact-sm"
                      variant={ok && d === dialect ? 'filled' : 'default'}
                      onClick={() => void save(p.part_id, d)}
                      data-testid={`download-${p.part_id}-${d}`}
                    >
                      DRL {d} herunterladen
                    </Button>
                    <Button size="compact-sm" variant="subtle" onClick={() => void show(p.part_id, d)} data-testid={`view-${p.part_id}-${d}`}>
                      Vorschau
                    </Button>
                  </Group>
                ))}
              </Group>
            </Paper>
          );
        })}
      </Stack>
      {error ? <ErrorNote message={error} detail={detail} testid="export-error" /> : null}

      {preview ? (
        <Stack gap={4}>
          <Text size="sm" fw={600}>
            Vorschau {preview.key.replace(/-(v\d)$/, ' (Dialekt $1)')}
          </Text>
          {/* Eigener Scrollkasten in beide Richtungen; das Seitenpanel läuft nicht seitlich über. */}
          <Box style={{ maxHeight: 240, overflow: 'auto', maxWidth: '100%' }}>
            <Code block data-testid="drl-preview" style={{ whiteSpace: 'pre', width: 'max-content', minWidth: '100%' }}>
              {preview.text}
            </Code>
          </Box>
          <Text size="xs" c="dimmed" data-testid="drl-header-count">
            Kopfkommentar: {headerLines.length} Zeilen
          </Text>
        </Stack>
      ) : null}

      <Stack gap={4} data-testid="export-assumptions">
        <Text size="sm" fw={600}>
          Annahmen in diesem Lauf
        </Text>
        <List size="xs" spacing={2}>
          {run?.summary.assumptions.map((a, i) => (
            <List.Item key={i}>{a}</List.Item>
          ))}
        </List>
      </Stack>
    </Stack>
  );
}
