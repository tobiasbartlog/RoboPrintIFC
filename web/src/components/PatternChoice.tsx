import { Badge, Button, Group, Paper, SegmentedControl, Select, Stack, Text } from '@mantine/core';
import { useEffect, useMemo } from 'react';
import { usePatternStore, usePatternStoreApi } from '../state/patternContext';
import {
  choiceForSelection,
  choiceSummary,
  isDefaultPattern,
  LAYER_ORDER_OPTIONS,
  patternChanged,
  selectionOf,
  type LayerOrderChoice,
} from '../state/patternChoice';
import { useAppStore } from '../state/storeContext';
import { useSetView } from '../state/viewContext';
import { Reason } from './common';

const NONE = { value: 'none', label: 'Kein Muster (Standard)' };

/**
 * Musterwahl im Ablauf: Muster oder gespeichertes Muster und Schichtfolge für den nächsten Lauf.
 * Der Standard (kein Muster, Schichtfolge „Standard“) schneidet wie bisher. Namen und Rollen kommen
 * aus dem Katalog der API; die Wahl geht als Jobparameter bis in den Lauf (`pattern_preset`,
 * `infill_pattern`, `outfill_pattern`, `layer_order`, `pattern_params`).
 */
export function PatternChoice() {
  const choice = useAppStore((s) => s.patternChoice);
  const replace = useAppStore((s) => s.replacePatternChoice);
  const setChoice = useAppStore((s) => s.setPatternChoice);
  const reset = useAppStore((s) => s.resetPatternChoice);
  const catalog = usePatternStore((s) => s.catalog);
  const catalogError = usePatternStore((s) => s.catalogError);
  const patternStore = usePatternStoreApi();
  const setView = useSetView();

  useEffect(() => {
    if (patternStore.getState().catalog === null) void patternStore.getState().loadCatalog();
  }, [patternStore]);

  const data = useMemo(() => {
    const base = new Set(catalog?.base_patterns ?? ['schalen']);
    const groups = [
      {
        group: 'Gespeicherte Muster',
        items: (catalog?.presets ?? []).map((p) => ({
          value: `preset:${p.id}`,
          // Preset und Muster heißen oft gleich (z. B. „Sinuswelle“); der Zusatz hält die Einträge auseinander.
          label: `${p.preset.name} (${p.source === 'user' ? 'eigenes' : 'Vorlage'})`,
        })),
      },
      {
        group: 'Füllung im Hohlraum (Infill)',
        items: (catalog?.patterns ?? []).filter((p) => p.role === 'infill' && !base.has(p.name)).map((p) => ({ value: `infill:${p.name}`, label: p.label })),
      },
      {
        group: 'Außenhaut (Outfill)',
        items: (catalog?.patterns ?? []).filter((p) => p.role === 'outfill' && !base.has(p.name)).map((p) => ({ value: `outfill:${p.name}`, label: p.label })),
      },
      {
        group: 'Ganze Wand',
        items: (catalog?.patterns ?? []).filter((p) => p.role === 'full' && !base.has(p.name)).map((p) => ({ value: `outfill:${p.name}`, label: p.label })),
      },
    ].filter((g) => g.items.length > 0);
    const all = [NONE, ...groups.flatMap((g) => g.items)];
    // Eine Wahl, die der Katalog nicht kennt (z. B. aus dem Musterersteller), bleibt sichtbar.
    const current = selectionOf(choice);
    const extra = all.some((o) => o.value === current) ? [] : [{ value: current, label: choiceSummary(choice, catalog).split(' · ')[0] ?? current }];
    return [NONE, ...extra, ...groups];
  }, [catalog, choice]);

  const changed = patternChanged(choice);
  const none = selectionOf(choice) === 'none';
  const nParams = (() => {
    try {
      return Object.keys(JSON.parse(choice.pattern_params || '{}') as object).length;
    } catch {
      return 0;
    }
  })();

  return (
    <Paper withBorder p="xs" data-testid="pattern-choice" data-changed={changed > 0}>
      <Stack gap="xs">
        <Group justify="space-between" gap="xs">
          <Group gap="xs" wrap="nowrap">
            <Text fw={600}>Druckmuster</Text>
            {changed ? (
              <Badge variant="light" data-testid="pattern-choice-changed">
                {changed} geändert
              </Badge>
            ) : null}
          </Group>
          {changed ? (
            <Button variant="default" size="compact-xs" onClick={reset} data-testid="pattern-choice-reset">
              Auf Standard
            </Button>
          ) : null}
        </Group>

        <Select
          label="Muster"
          size="xs"
          allowDeselect={false}
          data={data}
          value={selectionOf(choice)}
          onChange={(v) => v && replace(choiceForSelection(v, choice))}
          comboboxProps={{ withinPortal: true }}
          data-testid="pattern-choice-select"
        />
        <Reason text={catalogError && !catalog ? 'Der Musterkatalog ist nicht erreichbar. Ohne ihn lässt sich kein Muster wählen; der Lauf schneidet dann wie bisher.' : null} testid="pattern-choice-reason" />

        <Stack gap={2}>
          <Text size="xs" id="pattern-choice-order-label">
            Schichtfolge
          </Text>
          <SegmentedControl
            fullWidth
            size="xs"
            data={LAYER_ORDER_OPTIONS}
            value={choice.layer_order}
            onChange={(v) => setChoice({ layer_order: v as LayerOrderChoice })}
            aria-labelledby="pattern-choice-order-label"
            data-testid="pattern-choice-order"
          />
          <Text size="xs" c="dimmed">
            {none && !choice.layer_order
              ? 'Standard: wie bisher (jede Schicht in derselben Richtung).'
              : choice.layer_order === 'same'
                ? 'Gleich: jede Schicht in derselben Richtung, der Schichtwechsel läuft schräg.'
                : choice.layer_order === 'alternate'
                  ? 'Wechselnd: jede zweite Schicht läuft rückwärts, der Schichtwechsel ist ein reiner Hub nach oben.'
                  : 'Standard: mit Muster wechselnd, der Schichtwechsel ist ein reiner Hub nach oben.'}
          </Text>
        </Stack>

        <Text size="xs" c="dimmed" data-testid="pattern-choice-summary">
          {choiceSummary(choice, catalog)}
          {nParams ? ' (aus dem Musterersteller)' : ''}
        </Text>
        <Group gap="xs">
          <Button variant="subtle" size="compact-xs" onClick={() => setView('pattern')} data-testid="pattern-choice-open-builder">
            Im Musterersteller gestalten
          </Button>
        </Group>
        {isDefaultPattern(choice) ? null : (
          <Text size="xs" c="dimmed">
            Strangbreite, Schichthöhe, Abtastabstand und Verbinder gelten aus den Druckeinstellungen.
          </Text>
        )}
      </Stack>
    </Paper>
  );
}
