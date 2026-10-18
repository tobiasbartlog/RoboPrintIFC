import { Badge, Button, Collapse, Group, NumberInput, SegmentedControl, Stack, Text, TextInput } from '@mantine/core';
import { useState } from 'react';
import { DEFAULT_PARAMS, NUM_PARAMS, changedKeys } from '../state/params';
import { useAppStore } from '../state/storeContext';

/** Bereich "Parameter": Einheiten, Defaults, Markierung gegenüber dem Default, Zurücksetzen. */
export function ParamsPanel() {
  const [open, setOpen] = useState(false);
  const params = useAppStore((s) => s.params);
  const setParam = useAppStore((s) => s.setParam);
  const resetParam = useAppStore((s) => s.resetParam);
  const resetParams = useAppStore((s) => s.resetParams);
  const changed = changedKeys(params);

  return (
    <Stack gap="xs" data-testid="params">
      <Group justify="space-between">
        <Button variant="subtle" size="compact-sm" onClick={() => setOpen((o) => !o)} data-testid="params-toggle">
          {open ? 'Parameter ausblenden' : 'Parameter anzeigen'}
          {changed.length ? ` (${changed.length} geändert)` : ''}
        </Button>
        {changed.length ? (
          <Button variant="default" size="compact-sm" onClick={resetParams} data-testid="params-reset-all">
            Alle zurücksetzen
          </Button>
        ) : null}
      </Group>
      <Collapse in={open}>
        <Stack gap="xs">
          {NUM_PARAMS.map((d) => {
            const isChanged = params[d.key] !== d.default;
            return (
              <Group key={d.key} gap="xs" wrap="nowrap" align="flex-end" data-testid={`param-row-${d.key}`} data-changed={isChanged}>
                <NumberInput
                  style={{ flex: 1 }}
                  size="xs"
                  label={
                    <Group gap={4}>
                      <span>{d.label}</span>
                      {d.assumption ? (
                        <Badge size="xs" color="yellow" variant="light" data-testid={`param-assumption-${d.key}`}>
                          {d.provisional ? 'Annahme, provisorisch' : 'Annahme'}
                        </Badge>
                      ) : null}
                    </Group>
                  }
                  description={`Standard ${d.default}${d.unit ? ' ' + d.unit : ''}${d.hint ? ' · ' + d.hint : ''}`}
                  rightSection={<Text size="xs" c="dimmed">{d.unit}</Text>}
                  rightSectionWidth={44}
                  step={d.step}
                  min={0}
                  value={params[d.key] as number}
                  onChange={(v) => typeof v === 'number' && setParam(d.key, v)}
                  styles={isChanged ? { input: { borderColor: 'var(--mantine-color-yellow-6)' } } : undefined}
                  data-testid={`param-${d.key}`}
                />
                <Button variant="subtle" size="compact-xs" disabled={!isChanged} onClick={() => resetParam(d.key)} data-testid={`param-reset-${d.key}`}>
                  Zurücksetzen
                </Button>
              </Group>
            );
          })}
          <TextInput
            size="xs"
            label={
              <Group gap={4}>
                <span>Werkzeugname am Teach Pendant (TCP)</span>
                <Badge size="xs" color="yellow" variant="light">
                  Annahme
                </Badge>
              </Group>
            }
            description={`Standard ${String(DEFAULT_PARAMS.tcp_name)}`}
            value={String(params.tcp_name)}
            onChange={(e) => setParam('tcp_name', e.currentTarget.value)}
            data-testid="param-tcp_name"
          />
          <Stack gap={2}>
            <Text size="xs" fw={500}>
              DRL-Dialekt
            </Text>
            <SegmentedControl
              size="xs"
              data={[
                { value: 'v2', label: 'v2' },
                { value: 'v3', label: 'v3' },
              ]}
              value={String(params.dialect)}
              onChange={(v) => setParam('dialect', v)}
              data-testid="param-dialect"
            />
          </Stack>
        </Stack>
      </Collapse>
    </Stack>
  );
}
