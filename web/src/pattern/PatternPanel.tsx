import { Accordion, ActionIcon, Box, Button, Group, NumberInput, SegmentedControl, Select, Slider, Stack, Switch, Text, TextInput, Tooltip } from '@mantine/core';
import { useMemo, useState } from 'react';
import type { PatternParamSpec } from '../contracts';
import { ErrorNote, Reason } from '../components/common';
import { usePatternStore, usePatternStoreApi } from '../state/patternContext';
import { CHOICE_LABEL, effectiveValue, inRange, num, outlineOfBox, patternInfo, type PatternValue } from '../state/patterns';
import { useAppStore } from '../state/storeContext';

const ROLE_GROUP: Record<string, string> = {
  full: 'Ganze Wand (Schalen, Außen und Innen zusammen)',
  outfill: 'Außenhaut (Outfill)',
  infill: 'Füllung im Hohlraum (Infill)',
};

function unitSuffix(unit: string) {
  return unit ? (
    <Text size="xs" c="dimmed">
      {unit}
    </Text>
  ) : undefined;
}

/** Ein Regler aus einer ParamSpec: Beschriftung mit Einheit, Schieber mit Bereich, Zahlenfeld, Zurücksetzen. */
function ParamControl({ spec }: { spec: PatternParamSpec }) {
  const overrides = usePatternStore((s) => s.params);
  const reported = usePatternStore((s) => s.preview?.params ?? null);
  const setParam = usePatternStore((s) => s.setParam);
  const resetParam = usePatternStore((s) => s.resetParam);
  const value = effectiveValue(spec, overrides, reported as Record<string, PatternValue | undefined> | null);
  const changed = spec.name in overrides;
  const id = `pat-param-${spec.name}`;
  const reset = (
    <Tooltip label="Auf Standard zurücksetzen" disabled={!changed}>
      <ActionIcon
        variant="subtle"
        size="sm"
        aria-label={`${spec.label} zurücksetzen`}
        disabled={!changed}
        onClick={() => resetParam(spec.name)}
        data-testid={`${id}-reset`}
        style={{ visibility: changed ? 'visible' : 'hidden' }}
      >
        ↺
      </ActionIcon>
    </Tooltip>
  );
  // Zahlenfeld: echtes <label for>; Auswahl: Gruppe per aria-labelledby (SegmentedControl hat kein Eingabefeld mit id).
  const labelProps = spec.kind === 'choice' ? ({ component: 'span', id: `${id}-label` } as const) : ({ component: 'label', htmlFor: `${id}-input` } as const);
  const head = (
    <Group justify="space-between" wrap="nowrap" gap={4}>
      <Text {...labelProps} size="sm" fw={changed ? 700 : 400} style={{ minWidth: 0 }}>
        {spec.label}
        {spec.unit ? (
          <Text span c="dimmed" size="xs">
            {' '}
            ({spec.unit})
          </Text>
        ) : null}
      </Text>
      {reset}
    </Group>
  );
  const help = spec.help ? (
    <Text size="xs" c="dimmed">
      {spec.help}
    </Text>
  ) : null;

  if (spec.kind === 'bool') {
    return (
      <Box data-testid={id} data-changed={changed}>
        <Group justify="space-between" wrap="nowrap">
          <Switch id={`${id}-input`} label={spec.label} checked={value === true} onChange={(e) => setParam(spec.name, e.currentTarget.checked)} data-testid={`${id}-input`} />
          {reset}
        </Group>
        {help}
      </Box>
    );
  }
  if (spec.kind === 'choice') {
    return (
      <Box data-testid={id} data-changed={changed}>
        {head}
        <SegmentedControl
          fullWidth
          size="xs"
          data={spec.choices.map((c) => ({ value: String(c), label: CHOICE_LABEL[String(c)] ?? String(c) }))}
          value={String(value)}
          onChange={(v) => setParam(spec.name, typeof spec.choices[0] === 'number' ? Number(v) : v)}
          role="radiogroup"
          aria-labelledby={`${id}-label`}
          data-testid={`${id}-input`}
        />
        {help}
      </Box>
    );
  }
  const n = typeof value === 'number' ? value : Number(spec.default ?? 0);
  const hasRange = spec.minimum !== null && spec.maximum !== null;
  const step = spec.step ?? (spec.kind === 'int' ? 1 : 0.5);
  return (
    <Box data-testid={id} data-changed={changed}>
      {head}
      <Group gap="sm" wrap="nowrap" align="center">
        {hasRange ? (
          <Slider
            style={{ flex: 1 }}
            min={spec.minimum ?? 0}
            max={spec.maximum ?? 100}
            step={step}
            value={Math.min(Math.max(n, spec.minimum ?? n), spec.maximum ?? n)}
            onChange={(v) => setParam(spec.name, v)}
            label={(v) => `${num(v, 1)} ${spec.unit}`}
            aria-label={spec.label}
          />
        ) : (
          <Box style={{ flex: 1 }} />
        )}
        <NumberInput
          id={`${id}-input`}
          size="xs"
          w={86}
          hideControls
          step={step}
          min={spec.minimum ?? undefined}
          max={spec.maximum ?? undefined}
          // „blur“ statt „strict“: strict verwirft jeden Tastendruck außerhalb des Bereichs, bei
          // Minimum 160 ließe sich „240“ nicht eintippen. Zwischenstände gehen nicht an den Kern.
          clampBehavior="blur"
          allowDecimal={spec.kind === 'float'}
          decimalSeparator=","
          value={n}
          onChange={(v) => typeof v === 'number' && inRange(v, spec.minimum, spec.maximum) && setParam(spec.name, v)}
          rightSection={unitSuffix(spec.unit)}
          rightSectionWidth={spec.unit ? 30 : undefined}
          rightSectionPointerEvents="none"
          data-testid={`${id}-input`}
        />
      </Group>
      {help}
    </Box>
  );
}

/** Vorgabe von Länge und Dicke: frei oder aus einem Modul bzw. einer Wand des Projekts. */
function SizeSection() {
  const outline = usePatternStore((s) => s.outline);
  const setOutline = usePatternStore((s) => s.setOutline);
  const layer = usePatternStore((s) => s.layer);
  const setLayer = usePatternStore((s) => s.setLayer);
  const parts = useAppStore((s) => s.run?.parts);
  const walls = useAppStore((s) => s.project?.walls);
  const options = useMemo(() => {
    const out: { group: string; items: { value: string; label: string; length_mm: number; thickness_mm: number }[] }[] = [];
    const modules = Object.values(parts ?? {}).map((p) => {
      const o = outlineOfBox(p.bbox_P.min, p.bbox_P.max);
      return { value: `module:${p.part_id}`, label: `Modul ${p.part_id} (${num(o.length_mm, 0)} × ${num(o.thickness_mm, 0)} mm)`, ...o };
    });
    if (modules.length) out.push({ group: 'Aus dem gewählten Lauf', items: modules });
    const wallItems = (walls ?? [])
      .filter((w) => w.eligible)
      .map((w) => ({ value: `wall:${w.wall_id}`, label: `Wand ${w.name} (${num(w.length_mm, 0)} × ${num(w.thickness_mm, 0)} mm)`, length_mm: Math.round(w.length_mm), thickness_mm: Math.round(w.thickness_mm) }));
    if (wallItems.length) out.push({ group: 'Aus dem Modell', items: wallItems });
    return out;
  }, [parts, walls]);
  const all = options.flatMap((o) => o.items);
  const data = [{ value: 'free', label: 'Frei eingeben' }, ...options.map((o) => ({ group: o.group, items: o.items.map(({ value, label }) => ({ value, label })) }))];
  return (
    <Stack gap="xs" data-testid="pattern-size">
      <Select
        label="Vorgabe"
        description="Länge und Dicke aus einem Modul oder einer Wand übernehmen, oder frei wählen."
        size="xs"
        allowDeselect={false}
        data={data}
        value={all.some((o) => o.value === outline.source) ? outline.source : 'free'}
        onChange={(v) => {
          const hit = all.find((o) => o.value === v);
          if (hit) setOutline({ length_mm: hit.length_mm, thickness_mm: hit.thickness_mm, source: hit.value });
          else setOutline({ source: 'free' });
        }}
        data-testid="pattern-size-source"
      />
      <Group grow gap="xs" align="flex-start">
        <NumberInput
          label="Modullänge (mm)"
          size="xs"
          min={100}
          max={20000}
          step={10}
          hideControls
          clampBehavior="blur"
          value={outline.length_mm}
          onChange={(v) => typeof v === 'number' && inRange(v, 100, 20000) && setOutline({ length_mm: v, source: 'free' })}
          data-testid="pattern-length"
        />
        <NumberInput
          label="Wanddicke (mm)"
          size="xs"
          min={60}
          max={2000}
          step={5}
          hideControls
          clampBehavior="blur"
          value={outline.thickness_mm}
          onChange={(v) => typeof v === 'number' && inRange(v, 60, 2000) && setOutline({ thickness_mm: v, source: 'free' })}
          data-testid="pattern-thickness"
        />
      </Group>
      <NumberInput
        label="Gezeigte Schicht"
        description="Nummer der Schicht; die nächste erscheint blass."
        size="xs"
        w={140}
        min={0}
        max={999}
        step={1}
        clampBehavior="blur"
        value={layer}
        onChange={(v) => typeof v === 'number' && inRange(v, 0, 999) && setLayer(v)}
        data-testid="pattern-layer"
      />
    </Stack>
  );
}

function SaveSection() {
  const api = usePatternStoreApi();
  const pattern = usePatternStore((s) => s.pattern);
  const saved = usePatternStore((s) => s.saved);
  const saveError = usePatternStore((s) => s.saveError);
  const ok = usePatternStore((s) => s.preview?.ok ?? false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const reason = !name.trim() ? 'Zum Speichern einen Namen eingeben.' : null;
  return (
    <Stack gap="xs" data-testid="pattern-save">
      <TextInput label="Name" size="xs" placeholder="z. B. Fugenwand 240" value={name} onChange={(e) => setName(e.currentTarget.value)} data-testid="pattern-save-name" />
      <TextInput label="Notiz (optional)" size="xs" value={description} onChange={(e) => setDescription(e.currentTarget.value)} data-testid="pattern-save-description" />
      <Button
        size="xs"
        disabled={reason !== null || busy}
        loading={busy}
        onClick={async () => {
          setBusy(true);
          await api.getState().save(name.trim(), description.trim());
          setBusy(false);
        }}
        data-testid="pattern-save-button"
      >
        Als Muster speichern
      </Button>
      <Reason text={reason} testid="pattern-save-reason" />
      {!ok && !reason ? (
        <Text size="xs" c="dimmed" data-testid="pattern-save-warn">
          Hinweis: Die aktuelle Einstellung verletzt Musterregeln. Sie lässt sich trotzdem speichern.
        </Text>
      ) : null}
      {saved ? (
        <Text size="sm" c="green" data-testid="pattern-saved">
          Gespeichert als „{saved.preset.name}“ ({saved.id}). Slicer und Szenarien verwenden es unter diesem Namen.
        </Text>
      ) : null}
      {saveError ? <ErrorNote message="Das Muster ließ sich nicht speichern." detail={saveError} testid="pattern-save-error" /> : null}
      <Text size="xs" c="dimmed">
        Muster: {pattern}
      </Text>
    </Stack>
  );
}

function ExportSection() {
  const api = usePatternStoreApi();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Stack gap="xs">
      <Button
        size="xs"
        variant="default"
        loading={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const { text, fileName } = await api.getState().exportSvg();
            const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            a.click();
            // Erst nach dem Start des Downloads freigeben (sofortiges Freigeben bricht ihn in Firefox ab).
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        }}
        data-testid="pattern-export-svg"
      >
        Als SVG exportieren
      </Button>
      {error ? <ErrorNote message="Der SVG-Export hat nicht geklappt." detail={error} testid="pattern-export-error" /> : null}
    </Stack>
  );
}

/** Seitenpanel des Mustererstellers: Musterwahl, Maße, Regler, Speichern, Export. */
export function PatternPanel() {
  const catalog = usePatternStore((s) => s.catalog);
  const pattern = usePatternStore((s) => s.pattern);
  const presetId = usePatternStore((s) => s.presetId);
  const params = usePatternStore((s) => s.params);
  const selectPattern = usePatternStore((s) => s.selectPattern);
  const selectPreset = usePatternStore((s) => s.selectPreset);
  const resetParams = usePatternStore((s) => s.resetParams);
  const catalogError = usePatternStore((s) => s.catalogError);
  const info = patternInfo(catalog, pattern);

  const patternData = useMemo(() => {
    const groups = new Map<string, { value: string; label: string }[]>();
    for (const p of catalog?.patterns ?? []) {
      const g = ROLE_GROUP[p.role] ?? p.role;
      groups.set(g, [...(groups.get(g) ?? []), { value: p.name, label: p.label }]);
    }
    return [...groups.entries()].map(([group, items]) => ({ group, items }));
  }, [catalog]);
  const presetData = useMemo(
    () =>
      (catalog?.presets ?? []).map((p) => ({
        value: p.id,
        label: p.source === 'user' ? `${p.preset.name} (eigenes)` : p.preset.name,
      })),
    [catalog],
  );

  return (
    <Stack gap="md" data-testid="pattern-panel">
      <Select
        label="Muster"
        size="sm"
        allowDeselect={false}
        data={patternData}
        value={catalog ? pattern : null}
        onChange={(v) => v && selectPattern(v)}
        disabled={!catalog}
        placeholder={catalog ? undefined : catalogError ? 'Katalog nicht geladen' : 'Katalog wird geladen …'}
        data-testid="pattern-select"
      />
      <Reason text={!catalog && catalogError ? 'Ohne Musterkatalog ist keine Wahl möglich. Den Katalog über „Katalog neu laden“ in der Mitte erneut anfordern.' : null} testid="pattern-select-reason" />
      {info?.description ? (
        <Text size="xs" c="dimmed" data-testid="pattern-description">
          {info.description}
        </Text>
      ) : null}
      {presetData.length ? (
        <Select
          label="Gespeichertes Muster laden"
          size="xs"
          searchable
          clearable={false}
          data={presetData}
          value={presetId}
          placeholder="Vorlage wählen …"
          onChange={(v) => v && selectPreset(v)}
          data-testid="pattern-preset-select"
        />
      ) : null}
      <Accordion multiple defaultValue={['size', 'pattern', 'core', 'save']} variant="separated" data-testid="pattern-accordion">
        <Accordion.Item value="size">
          <Accordion.Control>Maße</Accordion.Control>
          <Accordion.Panel>
            <SizeSection />
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="pattern">
          <Accordion.Control>Musterparameter{info ? `: ${info.label}` : ''}</Accordion.Control>
          <Accordion.Panel>
            <Stack gap="sm" data-testid="pattern-params">
              {info && info.params.length ? (
                info.params.map((p) => <ParamControl key={p.name} spec={p} />)
              ) : (
                <Text size="xs" c="dimmed">
                  Dieses Muster hat keine eigenen Regler. Strangbreite, Schalen und Radien stehen unter „Strang und Schichten“.
                </Text>
              )}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="core">
          <Accordion.Control>Strang und Schichten</Accordion.Control>
          <Accordion.Panel>
            <Stack gap="sm" data-testid="pattern-core-params">
              {(catalog?.core_params ?? []).map((p) => (
                <ParamControl key={p.name} spec={p} />
              ))}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="save">
          <Accordion.Control>Speichern und exportieren</Accordion.Control>
          <Accordion.Panel>
            <Stack gap="md">
              <SaveSection />
              <ExportSection />
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
      <Button variant="subtle" size="xs" disabled={Object.keys(params).length === 0} onClick={resetParams} data-testid="pattern-reset-all">
        Alle Regler auf Standard
      </Button>
      <Reason text={Object.keys(params).length === 0 ? 'Alle Regler stehen auf Standard.' : null} testid="pattern-reset-reason" />
    </Stack>
  );
}
