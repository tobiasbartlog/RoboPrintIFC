import {
  Accordion,
  ActionIcon,
  Anchor,
  Badge,
  Box,
  Button,
  CloseButton,
  Group,
  NumberInput,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Tooltip,
  VisuallyHidden,
} from '@mantine/core';
import { useState, type CSSProperties } from 'react';
import {
  assumptionText,
  changedKeys,
  groupViews,
  hiddenInfo,
  isChanged,
  layersPerModule,
  normalizeSearch,
  secondaryLine,
  type ParamDef,
  type ParamMode,
  type ParamValues,
} from '../state/params';
import { useAppStore } from '../state/storeContext';
import { GroupIcon, ResetIcon, SearchIcon } from './ParamIcons';

/**
 * Bereich „Druckeinstellungen“ (SPEC §10) wie bei Kunststoff-Slicern: Kategorien als Akkordeon,
 * Modus „Grundlegend | Alle“, Suche über alle Kategorien. Geändert = Primärfarbe, Annahme = „A“.
 */

/** Eingabefeld: rund 120 px; in der schmalen Seitenleiste (340 px unter lg) etwas schmaler, damit Labels Platz haben. */
const INPUT_W = { base: 100, lg: 120 };
const LABEL_FZ = { base: 'xs', lg: 'sm' };
const RESET_W = 22; // ActionIcon size="sm"
const DOT = 6;
const LABEL_INDENT = DOT + 4;

/** Geänderter Wert: Rand und leichte Tönung in der Primärfarbe des Themes. */
const CHANGED_FIELD: CSSProperties = {
  borderColor: 'var(--mantine-primary-color-filled)',
  backgroundColor: 'var(--mantine-primary-color-light)',
};

const ACCORDION_STYLES = {
  control: { paddingInlineEnd: 'var(--mantine-spacing-xs)' },
  chevron: { marginInline: 'var(--mantine-spacing-xs)' },
  label: { paddingBlock: 'var(--mantine-spacing-xs)' },
  content: { padding: 'var(--mantine-spacing-xs)', paddingTop: 0 },
};

/** Kennzeichen „A“ mit Tooltip; der zugängliche Text nennt „Annahme“ bzw. „Annahme, vorläufig“. */
function AssumptionMark({ def, testid }: { def?: ParamDef; testid?: string }) {
  const text = def ? assumptionText(def) : 'Annahme';
  return (
    <Tooltip label={`${text}: vor dem ersten Druck am Gerät bestätigen`} withArrow multiline maw={240}>
      <Badge
        size="xs"
        circle
        color="yellow"
        variant="filled"
        autoContrast
        component="span"
        style={{ display: 'inline-flex', flexShrink: 0, cursor: 'help', verticalAlign: 'middle' }}
        data-testid={testid}
      >
        <span aria-hidden="true">A</span>
        <VisuallyHidden component="span">{text}</VisuallyHidden>
      </Badge>
    </Tooltip>
  );
}

function ChangedDot({ changed, testid }: { changed: boolean; testid: string }) {
  return (
    <Box
      component="span"
      style={{
        display: 'inline-block',
        width: DOT,
        height: DOT,
        borderRadius: '50%',
        flexShrink: 0,
        background: changed ? 'var(--mantine-primary-color-filled)' : 'transparent',
      }}
      data-testid={changed ? testid : undefined}
    >
      {changed ? <VisuallyHidden component="span">geändert</VisuallyHidden> : null}
    </Box>
  );
}

function ParamField({ def, value, changed, id, labelId }: { def: ParamDef; value: unknown; changed: boolean; id: string; labelId: string }) {
  const setParam = useAppStore((s) => s.setParam);
  const testid = `param-${def.key}`;
  if (def.kind === 'choice') {
    return (
      <SegmentedControl
        size="xs"
        w={INPUT_W}
        data={def.options}
        value={String(value)}
        onChange={(v) => setParam(def.key, v)}
        aria-labelledby={labelId}
        style={{ flexShrink: 0, ...(changed ? { boxShadow: '0 0 0 1px var(--mantine-primary-color-filled)' } : null) }}
        data-testid={testid}
      />
    );
  }
  if (def.kind === 'text') {
    return (
      <TextInput
        id={id}
        size="xs"
        w={INPUT_W}
        style={{ flexShrink: 0 }}
        value={String(value)}
        onChange={(e) => setParam(def.key, e.currentTarget.value)}
        styles={changed ? { input: CHANGED_FIELD } : undefined}
        data-testid={testid}
      />
    );
  }
  return (
    <NumberInput
      id={id}
      size="xs"
      w={INPUT_W}
      style={{ flexShrink: 0 }}
      step={def.step}
      min={0}
      hideControls
      value={value as number}
      onChange={(v) => typeof v === 'number' && setParam(def.key, v)}
      rightSection={def.unit ? <Text size="xs" c="dimmed">{def.unit}</Text> : undefined}
      rightSectionWidth={def.unit ? 40 : undefined}
      rightSectionPointerEvents="none"
      styles={changed ? { input: CHANGED_FIELD } : undefined}
      data-testid={testid}
    />
  );
}

function ParamRow({ def, values }: { def: ParamDef; values: ParamValues }) {
  const resetParam = useAppStore((s) => s.resetParam);
  const changed = isChanged(def, values);
  const second = secondaryLine(def, values);
  const id = `param-input-${def.key}`;
  const labelId = `param-label-${def.key}`;
  return (
    <Box data-testid={`param-row-${def.key}`} data-changed={changed}>
      <Group gap={6} wrap="nowrap" align="center">
        <Group gap={4} wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
          <ChangedDot changed={changed} testid={`param-changed-${def.key}`} />
          {/* Das „A“ fließt im Text mit und bricht bei Platzmangel in die nächste Zeile. */}
          <Text
            component="label"
            htmlFor={def.kind === 'choice' ? undefined : id}
            id={labelId}
            fz={LABEL_FZ}
            fw={changed ? 700 : 400}
            style={{ minWidth: 0, hyphens: 'auto', WebkitHyphens: 'auto' }}
          >
            {def.label}
            {def.assumption ? (
              <>
                {' '}
                <AssumptionMark def={def} testid={`param-assumption-${def.key}`} />
              </>
            ) : null}
          </Text>
        </Group>
        <ParamField def={def} value={values[def.key]} changed={changed} id={id} labelId={labelId} />
        <Box w={RESET_W} style={{ flexShrink: 0 }}>
          {/* Nur bei geändertem Wert: kein deaktivierter Knopf ohne Grund; der Platz bleibt, damit die Zeilen fluchten. */}
          {changed ? (
            <Tooltip label="Auf Standard zurücksetzen" withArrow>
              <ActionIcon
                size="sm"
                variant="subtle"
                aria-label={`${def.label} auf Standard zurücksetzen`}
                onClick={() => resetParam(def.key)}
                data-testid={`param-reset-${def.key}`}
              >
                <ResetIcon />
              </ActionIcon>
            </Tooltip>
          ) : null}
        </Box>
      </Group>
      {second ? (
        <Text size="xs" c="dimmed" pl={LABEL_INDENT} data-testid={`param-note-${def.key}`}>
          {second}
        </Text>
      ) : null}
    </Box>
  );
}

export function ParamsPanel() {
  const params = useAppStore((s) => s.params);
  const resetParams = useAppStore((s) => s.resetParams);
  const [mode, setMode] = useState<ParamMode>('basic');
  const [query, setQuery] = useState('');
  const [opened, setOpened] = useState<string[]>([]);
  // Während einer Suche klappen die Gruppen mit Treffern auf; danach gilt wieder `opened`.
  const [searchOpened, setSearchOpened] = useState<string[] | null>(null);

  const searching = normalizeSearch(query) !== '';
  const views = groupViews(mode, query, params);
  const hits = views.reduce((n, v) => n + v.params.length, 0);
  const hidden = hiddenInfo(mode, query, params);
  const nChanged = changedKeys(params).length;
  const layers = layersPerModule(params);

  function changeQuery(q: string) {
    setQuery(q);
    setSearchOpened(normalizeSearch(q) ? groupViews(mode, q, params).map((v) => v.group.id) : null);
  }

  function showAll() {
    setMode('all');
    setOpened((o) => [...new Set([...o, ...hidden.changedGroups])]);
  }

  return (
    <Stack gap="xs" data-testid="params">
      <Group justify="space-between" gap="xs" style={{ rowGap: 4 }}>
        <Group gap="xs" wrap="nowrap">
          <Text fw={600}>Druckeinstellungen</Text>
          {nChanged ? (
            <Badge variant="light" data-testid="params-changed-count">
              {nChanged} geändert
            </Badge>
          ) : null}
        </Group>
        {nChanged ? (
          <Button variant="default" size="compact-xs" onClick={resetParams} data-testid="params-reset-all">
            Alle zurücksetzen
          </Button>
        ) : null}
      </Group>

      <SegmentedControl
        fullWidth
        size="xs"
        value={mode}
        onChange={(v) => setMode(v === 'all' ? 'all' : 'basic')}
        data={[
          { value: 'basic', label: 'Grundlegend' },
          { value: 'all', label: 'Alle' },
        ]}
        aria-label="Umfang der Druckeinstellungen"
        data-testid="param-mode"
      />

      <Stack gap={4}>
        <TextInput
          size="xs"
          placeholder="Parameter suchen, z. B. Abstand"
          aria-label="Parameter suchen"
          leftSection={<SearchIcon />}
          rightSection={query ? <CloseButton size="sm" aria-label="Suche leeren" onClick={() => changeQuery('')} data-testid="param-search-clear" /> : null}
          value={query}
          onChange={(e) => changeQuery(e.currentTarget.value)}
          onKeyDown={(e) => e.key === 'Escape' && changeQuery('')}
          data-testid="param-search"
        />
        {searching ? (
          <Text size="xs" c="dimmed" data-testid="param-search-result">
            {hits ? `${hits} Treffer` : `Kein Parameter passt zu „${query.trim()}“.`}
          </Text>
        ) : null}
      </Stack>

      {views.length ? (
        <Accordion
          multiple
          variant="contained"
          chevronPosition="left"
          value={searchOpened ?? opened}
          onChange={searchOpened ? setSearchOpened : setOpened}
          styles={ACCORDION_STYLES}
        >
          {views.map((v) => {
            const isOpen = (searchOpened ?? opened).includes(v.group.id);
            return (
              <Accordion.Item key={v.group.id} value={v.group.id}>
                <Accordion.Control data-testid={`param-group-${v.group.id}`}>
                  <Box component="span" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <GroupIcon id={v.group.id} />
                    <Box component="span" style={{ display: 'block', flex: 1, minWidth: 0 }}>
                      <Text component="span" display="block" size="sm" fw={500}>
                        {v.group.title}
                      </Text>
                      {!isOpen ? (
                        <Text component="span" display="block" size="xs" c="dimmed" truncate="end" data-testid={`param-summary-${v.group.id}`}>
                          {v.summary}
                        </Text>
                      ) : null}
                    </Box>
                    {v.changed ? (
                      <Badge component="span" variant="light" size="sm" style={{ flexShrink: 0 }} data-testid={`param-group-changed-${v.group.id}`}>
                        {v.changed} geändert
                      </Badge>
                    ) : null}
                  </Box>
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="xs">
                    {v.params.map((d) => (
                      <ParamRow key={d.key} def={d} values={params} />
                    ))}
                    {v.group.id === 'module' && layers !== null ? (
                      <Text size="xs" c="dimmed" pl={LABEL_INDENT} data-testid="param-module-layers">
                        Ergibt bis zu {layers.toLocaleString('de-DE')} Schichten je Modul.
                      </Text>
                    ) : null}
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            );
          })}
        </Accordion>
      ) : null}

      {hidden.count ? (
        <Anchor component="button" type="button" size="sm" ta="left" onClick={showAll} data-testid="param-hidden-note">
          {hidden.count} weitere Parameter unter „Alle“
          {hidden.changed ? (
            <Badge
              component="span"
              variant="light"
              size="sm"
              ml={6}
              style={{ display: 'inline-flex', verticalAlign: 'middle' }}
              data-testid="param-hidden-changed"
            >
              {hidden.changed} geändert
            </Badge>
          ) : null}
        </Anchor>
      ) : null}

      <Group gap={6} wrap="nowrap" align="flex-start" data-testid="params-legend">
        <AssumptionMark />
        <Text size="xs" c="dimmed">
          Annahme. Vor dem ersten Druck am Gerät bestätigen; steht im Kopf jedes DRL-Programms.
        </Text>
      </Group>
    </Stack>
  );
}
