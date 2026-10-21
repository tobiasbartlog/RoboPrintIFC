import { Alert, Group, Paper, Stack, Table, Text } from '@mantine/core';
import { useEffect } from 'react';
import type { PartPatternReport } from '../contracts';
import { CHOICE_LABEL, length, mm, num, segmentStyle, seconds } from '../state/patterns';
import { usePatternStore } from '../state/patternContext';
import { useAppStore } from '../state/storeContext';

const pct = (share: number) => `${num(share * 100, 0)} %`;

function strandText(r: PartPatternReport): string {
  if (r.n_strands === 1) return 'ein Strang (kein Absetzen)';
  return `${num(r.n_strands, 0)} Stränge, höchstens ${num(r.max_strands_per_layer, 0)} je Schicht`;
}

function changesText(c: PartPatternReport['layer_changes']): string {
  const parts = [`${num(c.vertical, 0)} senkrecht`];
  if (c.diagonal) parts.push(`${num(c.diagonal, 0)} schräg`);
  if (c.travel) parts.push(`${num(c.travel, 0)} mit Absetzen`);
  return parts.join(', ');
}

/** Kennzahlen des Druckmusters des gewählten Teils. Die API rechnet sie aus `toolpath.json`. */
export function PartPatternStats({ partId }: { partId: string }) {
  const runId = useAppStore((s) => s.run?.runId ?? '');
  const report = useAppStore((s) => s.patternReports[`${runId}|${partId}`] ?? null);
  const error = useAppStore((s) => s.patternReportErrors[`${runId}|${partId}`] ?? null);
  const load = useAppStore((s) => s.loadPatternReport);
  const catalog = usePatternStore((s) => s.catalog);

  useEffect(() => {
    void load(partId);
  }, [load, partId, runId]);

  if (error && !report) {
    return (
      <Text size="xs" c="dimmed" data-testid={`pattern-stats-error-${partId}`}>
        Kennzahlen des Musters sind nicht verfügbar. Lauf neu rechnen oder die Verbindung prüfen.
      </Text>
    );
  }
  if (!report) {
    return (
      <Text size="xs" c="dimmed" data-testid={`pattern-stats-loading-${partId}`}>
        Kennzahlen des Musters werden geladen …
      </Text>
    );
  }
  const label = (name: string | null) => (name && name !== 'none' ? (catalog?.patterns.find((p) => p.name === name)?.label ?? name) : null);
  const names = [label(report.outfill), label(report.infill)].filter(Boolean).join(' + ');
  return (
    <Paper withBorder p="xs" data-testid={`pattern-stats-${partId}`} data-has-pattern={report.has_pattern}>
      <Stack gap={4}>
        <Group justify="space-between" wrap="nowrap" align="baseline">
          <Text size="sm" fw={600}>
            Kennzahlen {report.has_pattern ? 'Muster' : 'Schalen'}
          </Text>
          <Text size="xs" c="dimmed" data-testid={`pattern-stats-name-${partId}`}>
            {report.has_pattern ? `${names || 'Schalen'} · ${CHOICE_LABEL[report.layer_order ?? ''] ?? report.layer_order}` : 'ohne Muster'}
          </Text>
        </Group>
        <Table withRowBorders={false} verticalSpacing={1} fz="xs">
          <Table.Tbody>
            <Table.Tr>
              <Table.Td c="dimmed" w={110}>
                Bahnlänge
              </Table.Td>
              <Table.Td data-testid={`pattern-stats-length-${partId}`}>
                {length(report.total_length_mm)} in {num(report.n_layers, 0)} Schichten
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed">Druckzeit</Table.Td>
              <Table.Td data-testid={`pattern-stats-time-${partId}`}>
                {seconds(report.print_time_s)} bei {num(report.v_print_mm_s, 0)} mm/s
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed">Material</Table.Td>
              <Table.Td>{num(report.volume_l, 1)} l (Strang {mm(report.bead_width_mm, 0)} × {mm(report.layer_height_mm, 0)})</Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed">Stränge</Table.Td>
              <Table.Td data-testid={`pattern-stats-strands-${partId}`}>{strandText(report)}</Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed">Schichtwechsel</Table.Td>
              <Table.Td data-testid={`pattern-stats-changes-${partId}`}>
                {changesText(report.layer_changes)}
                {report.layer_changes.max_offset_mm !== null ? `, größter Versatz ${mm(report.layer_changes.max_offset_mm, 1)}` : ''}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td c="dimmed">Offene Segmente</Table.Td>
              <Table.Td>
                {num(report.n_open_rings, 0)} von {num(report.n_rings, 0)} Ringen
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
        {report.notes.length ? (
          // Hinweise des Plans: z. B. Infill entfällt, Rückfall auf Schalen, Insel ohne Strang
          <Alert color="yellow" p={6} title="Hinweise zum Muster" data-testid={`pattern-stats-notes-${partId}`}>
            <Stack gap={2}>
              {report.notes.map((n, i) => (
                <Text size="xs" key={i}>
                  {n}
                </Text>
              ))}
            </Stack>
          </Alert>
        ) : null}
        <Stack gap={2} data-testid={`pattern-stats-kinds-${partId}`}>
          {report.kinds.map((k) => (
            <Group key={k.kind} gap={6} wrap="nowrap" data-testid={`pattern-stats-kind-${partId}-${k.kind}`}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: segmentStyle(k.kind).color, display: 'inline-block', flexShrink: 0 }} aria-hidden="true" />
              <Text size="xs" style={{ flex: 1 }}>
                {segmentStyle(k.kind).label}
              </Text>
              <Text size="xs" c="dimmed">
                {length(k.length_mm)} · {pct(k.share)}
              </Text>
            </Group>
          ))}
        </Stack>
      </Stack>
    </Paper>
  );
}
