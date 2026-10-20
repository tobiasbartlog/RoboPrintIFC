import { Alert, Badge, Box, Button, Group, Loader, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useEffect, useState } from 'react';
import type { PatternPreview } from '../contracts';
import { ErrorNote } from '../components/common';
import { usePatternStore } from '../state/patternContext';
import { contactStyle, LAYER_CHANGE_LABEL, length, mm, num, RULE_TITLE, seconds, segmentStyle, spacingSummary } from '../state/patterns';
import { PatternSvg } from './PatternSvg';

function Swatch({ color, dashed = false, round = false }: { color: string; dashed?: boolean; round?: boolean }) {
  return (
    <Box
      aria-hidden
      style={{
        width: 18,
        height: round ? 10 : 4,
        borderRadius: round ? 5 : 2,
        background: dashed ? 'transparent' : color,
        borderTop: dashed ? `2px dashed ${color}` : undefined,
        flexShrink: 0,
      }}
    />
  );
}

/** Legende aus dem, was die Vorschau wirklich enthält; neue Segment- und Kontaktarten erscheinen von selbst. */
function Legend({ preview }: { preview: PatternPreview }) {
  const kinds = [...new Set(preview.paths.flatMap((p) => p.segments.map((s) => s.kind)))];
  const contacts = [...new Set(preview.contacts.map((c) => c.kind))];
  return (
    <Group gap="md" wrap="wrap" data-testid="pattern-legend">
      {kinds.map((k) => (
        <Group gap={6} wrap="nowrap" key={k} data-testid={`legend-kind-${k}`}>
          <Swatch color={segmentStyle(k).color} />
          <Text size="xs">{segmentStyle(k).label}</Text>
        </Group>
      ))}
      {contacts.map((k) => (
        <Group gap={6} wrap="nowrap" key={k} data-testid={`legend-contact-${k}`}>
          <Swatch color={contactStyle(k).color} round />
          <Text size="xs">{contactStyle(k).label}</Text>
        </Group>
      ))}
      <Group gap={6} wrap="nowrap">
        <Swatch color="var(--mantine-color-dimmed)" dashed />
        <Text size="xs">nächste Schicht (umgekehrt)</Text>
      </Group>
      <Text size="xs">○ Start</Text>
      <Text size="xs">□ Ende</Text>
      <Text size="xs">→ Druckrichtung</Text>
      <Group gap={6} wrap="nowrap">
        <Box aria-hidden style={{ width: 12, height: 12, borderRadius: 6, border: '2px solid var(--mantine-color-red-6)' }} />
        <Text size="xs">Regelverstoß</Text>
      </Group>
    </Group>
  );
}

function Stat({ id, label, value, hint }: { id: string; label: string; value: string; hint?: string }) {
  return (
    <Paper withBorder p="xs" data-testid={`pat-stat-${id}`}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700} size="md">
        {value}
      </Text>
      {hint ? (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      ) : null}
    </Paper>
  );
}

function Metrics({ preview }: { preview: PatternPreview }) {
  const m = preview.metrics;
  const w = Number(preview.params.bead_width_mm ?? 30);
  const byKind = new Map<string, { count: number; length_mm: number }>();
  for (const p of m.paths)
    for (const [k, v] of Object.entries(p.contacts_by_kind)) {
      const cur = byKind.get(k) ?? { count: 0, length_mm: 0 };
      byKind.set(k, { count: cur.count + v.count, length_mm: cur.length_mm + v.length_mm });
    }
  const cellArea = Math.max(0, ...m.paths.map((p) => p.max_cell_area_mm2 ?? 0));
  const cellSpan = Math.max(0, ...m.paths.map((p) => p.max_cell_span_mm ?? 0));
  const nCells = m.paths.reduce((a, p) => a + p.n_cells, 0);
  const lc = preview.layer_change;
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, xl: 4 }} spacing="xs" data-testid="pattern-metrics">
      <Stat id="length" label="Pfadlänge je Schicht" value={length(m.path_length_mm)} hint={`${m.strands} ${m.strands === 1 ? 'Strang' : 'Stränge'}`} />
      <Stat id="time" label="Druckzeit je Schicht" value={seconds(m.print_time_s)} hint={`bei ${num(m.v_print_mm_s, 0)} mm/s`} />
      <Stat id="material" label="Material je Meter" value={`${num(m.material_l_per_m_layer, 2)} l`} hint={`je m Wand und Schicht, ${num(m.material_l_per_m2, 1)} l/m²`} />
      <Stat
        id="cells"
        label="Zellen"
        value={nCells ? `${nCells} ${nCells === 1 ? 'Zelle' : 'Zellen'}` : 'keine'}
        hint={nCells ? `größte ${num(cellArea / 100, 0)} cm², Spannweite ${num(cellSpan, 0)} mm` : undefined}
      />
      <Stat
        id="contacts"
        label="Kontakte"
        value={`${m.contacts} · ${length(m.contact_length_mm)}`}
        hint={[...byKind.entries()].map(([k, v]) => `${v.count} × ${contactStyle(k).label} (${num(v.length_mm, 0)} mm)`).join(', ') || undefined}
      />
      <Stat id="joints" label="Fugenabstand" value={spacingSummary(m.joint_spacing_mm)} />
      <Stat id="straight" label="Längste gerade Außenstrecke" value={mm(m.longest_straight_outer_mm, 0)} hint="je kürzer, desto weniger Rissneigung" />
      <Stat id="radius" label="Kleinster Radius" value={mm(m.min_radius_mm, 1)} hint={`Ziel ≥ w = ${num(w, 0)} mm`} />
      <Stat id="clearance" label="Kleinster Strangabstand" value={mm(m.min_clearance_mm, 1)} />
      <Stat id="coverage" label="Schalenabdeckung" value={`${num(m.shell_coverage * 100, 1)} %`} hint="Anteil des Schalenbereichs unter Raupen" />
      <Stat
        id="layer-change"
        label="Schichtwechsel"
        value={lc ? (LAYER_CHANGE_LABEL[lc.status] ?? lc.status) : '–'}
        hint={lc ? `waagrecht ${num(lc.distance_mm, 1)} mm` : undefined}
      />
    </SimpleGrid>
  );
}

function FitInfo({ preview }: { preview: PatternPreview }) {
  if (preview.fit.length === 0) return null;
  return (
    <Paper withBorder p="sm" data-testid="pattern-fit">
      <Text size="sm" fw={600}>
        Anpassung an die Modullänge
      </Text>
      <Stack gap={2} mt={4}>
        {preview.fit.map((f, i) => (
          <Text size="sm" key={i} data-testid={`pattern-fit-${i}`}>
            {f.count} {f.count === 1 ? 'Feld' : 'Felder'} à {num(f.length_mm, 1)} mm
            {Math.abs(f.deviation_mm) >= 0.05
              ? ` (Ziel ${num(f.target_mm, 1)} mm, Abweichung ${f.deviation_mm > 0 ? '+' : ''}${num(f.deviation_mm, 1)} mm)`
              : ' (Ziel getroffen)'}{' '}
            <Text span size="xs" c="dimmed">
              {preview.fit.length > 1 ? `Insel ${f.island}, ${f.key}, ` : ''}Länge gesamt {num(f.total_mm, 0)} mm
            </Text>
          </Text>
        ))}
      </Stack>
    </Paper>
  );
}

function Violations({ preview, selected, onSelect, stale }: { preview: PatternPreview; selected: number | null; onSelect: (i: number | null) => void; stale: boolean }) {
  const v = preview.violations;
  const errors = v.filter((x) => x.severity === 'error').length;
  return (
    <Stack gap={4} data-testid="pattern-violations">
      <Group gap="xs">
        <Title order={5}>Musterregeln M1–M7</Title>
        {v.length === 0 ? (
          // Grün nur für den aktuellen Stand: Rechnet der Kern noch oder schlug die Anfrage fehl, gilt das Ergebnis der alten Einstellung.
          <Badge color={stale ? 'gray' : 'green'} variant={stale ? 'light' : 'filled'} data-testid="pattern-rules-ok" data-stale={stale}>
            {stale ? 'alle eingehalten (letzte Vorschau)' : 'alle eingehalten'}
          </Badge>
        ) : (
          <Badge color={errors ? 'red' : 'orange'} variant="filled" data-testid="pattern-rules-bad">
            {`${errors} Fehler, ${v.length - errors} ${v.length - errors === 1 ? 'Warnung' : 'Warnungen'}`}
          </Badge>
        )}
      </Group>
      {v.map((x, i) => (
        <Paper
          key={i}
          withBorder
          p={6}
          component="button"
          type="button"
          onClick={() => onSelect(selected === i ? null : i)}
          aria-pressed={selected === i}
          data-testid={`pattern-violation-${i}`}
          data-severity={x.severity}
          style={{
            textAlign: 'left',
            cursor: 'pointer',
            background: 'transparent',
            color: 'inherit',
            borderColor: x.severity === 'error' ? 'var(--mantine-color-red-6)' : 'var(--mantine-color-orange-6)',
            borderWidth: selected === i ? 2 : 1,
          }}
        >
          <Group gap="xs" wrap="nowrap" align="flex-start">
            <Badge color={x.severity === 'error' ? 'red' : 'orange'} variant="light" style={{ flexShrink: 0 }}>
              {x.rule}
            </Badge>
            <Text size="sm">
              <Text span fw={600}>
                {RULE_TITLE[x.rule] ?? ''}
              </Text>
              {RULE_TITLE[x.rule] ? ': ' : ''}
              {x.message}
              {x.value !== null && x.limit !== null ? (
                <Text span size="xs" c="dimmed">
                  {' '}
                  (Wert {num(x.value, 2)}, Grenze {num(x.limit, 2)})
                </Text>
              ) : null}
            </Text>
          </Group>
        </Paper>
      ))}
    </Stack>
  );
}

/** Hauptfläche des Mustererstellers: Draufsicht, Legende, Kennzahlen, Regelverstöße. */
export function PatternWorkspace() {
  const preview = usePatternStore((s) => s.preview);
  const busy = usePatternStore((s) => s.busy);
  const error = usePatternStore((s) => s.previewError);
  const errorStatus = usePatternStore((s) => s.previewErrorStatus);
  const catalogError = usePatternStore((s) => s.catalogError);
  const loadCatalog = usePatternStore((s) => s.loadCatalog);
  const refresh = usePatternStore((s) => s.refresh);
  const [selected, setSelected] = useState<number | null>(null);
  // Die Auswahl ist ein Index in die Verstoßliste; mit jeder neuen Vorschau zeigt er auf etwas anderes.
  useEffect(() => setSelected(null), [preview]);
  const inputError = errorStatus === 400 || errorStatus === 422;
  return (
    <Box h="100%" style={{ overflowY: 'auto', overflowX: 'hidden', minWidth: 0 }} data-testid="pattern-workspace" aria-busy={busy}>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <Title order={3}>Muster</Title>
          {busy ? (
            <Group gap={6} data-testid="pattern-busy">
              <Loader size="xs" />
              <Text size="xs" c="dimmed">
                rechnet …
              </Text>
            </Group>
          ) : preview ? (
            <Text size="xs" c="dimmed" data-testid="pattern-timing">
              Vorschau in {num(preview.timing_ms.api ?? preview.timing_ms.total, 0)} ms
            </Text>
          ) : null}
        </Group>
        {catalogError ? (
          <Stack gap={4}>
            <ErrorNote message="Der Musterkatalog konnte nicht geladen werden. Ist der Server gestartet? Danach „Katalog neu laden“." detail={catalogError} testid="pattern-catalog-error" />
            <Button size="xs" variant="default" w="fit-content" onClick={() => void loadCatalog()} data-testid="pattern-catalog-retry">
              Katalog neu laden
            </Button>
          </Stack>
        ) : null}
        {error && inputError ? (
          // 400/422: Die Meldung des Kerns ist deutscher Klartext zur Einstellung.
          <Alert color="red" title="Diese Einstellung ergibt keine Vorschau" data-testid="pattern-error" data-kind="input">
            <Text size="sm">{error}</Text>
            <Text size="xs" c="dimmed">
              {preview ? 'Angezeigt bleibt die letzte gültige Vorschau. ' : ''}Regler zurücksetzen oder anders einstellen.
            </Text>
          </Alert>
        ) : null}
        {error && !inputError ? (
          // Netz- oder Serverfehler: Klartext mit Handlung, die rohe Meldung nur ausklappbar.
          <Stack gap={4} data-testid="pattern-error" data-kind="server">
            <ErrorNote
              message={`Der Server hat keine Vorschau geliefert. Ist er gestartet?${preview ? ' Angezeigt bleibt die letzte gültige Vorschau.' : ''}`}
              detail={error}
              testid="pattern-server-error"
            />
            <Button size="xs" variant="default" w="fit-content" onClick={refresh} data-testid="pattern-retry">
              Vorschau neu anfordern
            </Button>
          </Stack>
        ) : null}
        {preview ? (
          <>
            {!preview.ok ? (
              <Alert color="red" title="Das Muster verletzt Regeln" data-testid="pattern-invalid">
                <Text size="sm">So ließe es sich nicht ohne Absetzen oder Kreuzung drucken. Die Stellen sind rot markiert.</Text>
              </Alert>
            ) : null}
            <Paper withBorder p="xs" style={{ opacity: busy || error ? 0.7 : 1 }}>
              <PatternSvg preview={preview} selectedViolation={selected} />
            </Paper>
            <Legend preview={preview} />
            <FitInfo preview={preview} />
            <Metrics preview={preview} />
            <Violations preview={preview} selected={selected} onSelect={setSelected} stale={busy || error !== null} />
          </>
        ) : !error && !catalogError ? (
          <Text c="dimmed" data-testid="pattern-loading">
            Vorschau wird berechnet …
          </Text>
        ) : null}
      </Stack>
    </Box>
  );
}
