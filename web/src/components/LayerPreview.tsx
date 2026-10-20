import { ActionIcon, Group, Loader, Paper, Slider, Stack, Text } from '@mantine/core';
import { useEffect, useId, useMemo, useState } from 'react';
import type { PartLayerPath, PartPatternLayer } from '../contracts';
import { num, segmentStyle } from '../state/patterns';
import { useAppStore } from '../state/storeContext';
import { ErrorNote } from './common';

/** Pfeile entlang eines Segments: etwa alle `ARROW_EVERY_MM`, mindestens einer. */
const ARROW_EVERY_MM = 120;

type Pt = readonly [number, number];

const flip = (p: readonly number[]): Pt => [p[0] ?? 0, -(p[1] ?? 0)];

function pointsAttr(points: readonly (readonly number[])[]): string {
  return points.map((p) => flip(p).join(',')).join(' ');
}

/** Pfeilspitzen (Mitte, Richtung) auf der Polylinie, nach Bogenlänge verteilt. Reine Darstellung. */
function arrows(points: readonly (readonly number[])[]): { at: Pt; dir: Pt }[] {
  const out: { at: Pt; dir: Pt }[] = [];
  if (points.length < 2) return out;
  const cum: number[] = [0];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]!;
    const b = points[i]!;
    cum.push((cum[i - 1] ?? 0) + Math.hypot((b[0] ?? 0) - (a[0] ?? 0), (b[1] ?? 0) - (a[1] ?? 0)));
  }
  const total = cum[cum.length - 1] ?? 0;
  if (total <= 0) return out;
  const n = Math.max(1, Math.round(total / ARROW_EVERY_MM));
  for (let k = 0; k < n; k++) {
    const s = ((k + 0.5) / n) * total;
    let i = 1;
    while (i < cum.length - 1 && (cum[i] ?? 0) < s) i++;
    const a = points[i - 1]!;
    const b = points[i]!;
    const seg = (cum[i] ?? 0) - (cum[i - 1] ?? 0);
    const u = seg > 0 ? (s - (cum[i - 1] ?? 0)) / seg : 0;
    const dx = (b[0] ?? 0) - (a[0] ?? 0);
    const dy = (b[1] ?? 0) - (a[1] ?? 0);
    const len = Math.hypot(dx, dy) || 1;
    out.push({ at: flip([(a[0] ?? 0) + u * dx, (a[1] ?? 0) + u * dy]), dir: [dx / len, -dy / len] });
  }
  return out;
}

function Chevron({ at, dir, size, color }: { at: Pt; dir: Pt; size: number; color: string }) {
  const [x, y] = at;
  const [dx, dy] = dir;
  const nx = -dy;
  const ny = dx;
  const tip: Pt = [x + dx * size, y + dy * size];
  const l: Pt = [x - dx * size * 0.6 + nx * size * 0.7, y - dy * size * 0.6 + ny * size * 0.7];
  const r: Pt = [x - dx * size * 0.6 - nx * size * 0.7, y - dy * size * 0.6 - ny * size * 0.7];
  return <polygon points={`${tip.join(',')} ${l.join(',')} ${r.join(',')}`} fill={color} stroke="var(--mantine-color-body)" strokeWidth={size * 0.12} />;
}

function PathLayer({ path, width, pale }: { path: PartLayerPath; width: number; pale: boolean }) {
  return (
    <g data-testid={pale ? 'layer-neighbor' : 'layer-path'} opacity={pale ? 0.3 : 1}>
      {path.segments.map((s) => {
        const color = segmentStyle(s.kind).color;
        return (
          <g key={s.ring} data-kind={s.kind}>
            <polyline points={pointsAttr(s.points)} fill="none" stroke={color} strokeOpacity={pale ? 1 : 0.3} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />
            <polyline
              points={pointsAttr(s.points)}
              fill="none"
              stroke={color}
              strokeWidth={Math.max(2, width * 0.1)}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={pale ? `${width * 0.6} ${width * 0.4}` : undefined}
            />
          </g>
        );
      })}
      {!pale
        ? path.segments.flatMap((s) =>
            arrows(s.points).map((a, k) => <Chevron key={`${s.ring}-${k}`} at={a.at} dir={a.dir} size={width * 0.32} color={segmentStyle(s.kind).color} />),
          )
        : null}
    </g>
  );
}

/** Zeichnung einer Schicht: Raupen nach Segmentart, Richtungspfeile, Start (Kreis) und Ende (Quadrat), Nachbarschicht blass. */
export function LayerSvg({ layer, svgId }: { layer: PartPatternLayer; svgId: string }) {
  const w = layer.bead_width_mm;
  const [lo, hi] = layer.bounds;
  const pad = w * 1.2;
  const x0 = (lo?.[0] ?? 0) - pad;
  const x1 = (hi?.[0] ?? 0) + pad;
  const y0 = -((hi?.[1] ?? 0) + pad);
  const y1 = -((lo?.[1] ?? 0) - pad);
  const start = layer.path.start ? flip(layer.path.start) : null;
  const end = layer.path.end ? flip(layer.path.end) : null;
  const r = w * 0.34;
  return (
    <svg
      id={svgId}
      viewBox={`${x0} ${y0} ${x1 - x0} ${y1 - y0}`}
      width="100%"
      style={{ display: 'block', maxHeight: 260 }}
      role="img"
      aria-label={`Schicht ${layer.layer + 1} von ${layer.n_layers}, Draufsicht`}
      data-testid="layer-preview-svg"
      data-layer={layer.layer}
      data-segments={layer.path.segments.length}
    >
      {layer.neighbor ? <PathLayer path={layer.neighbor} width={w} pale /> : null}
      <PathLayer path={layer.path} width={w} pale={false} />
      {start ? <circle cx={start[0]} cy={start[1]} r={r} fill="var(--mantine-color-body)" stroke="var(--mantine-color-text)" strokeWidth={r * 0.4} data-testid="layer-start" /> : null}
      {end ? <rect x={end[0] - r} y={end[1] - r} width={2 * r} height={2 * r} fill="var(--mantine-color-text)" data-testid="layer-end" /> : null}
    </svg>
  );
}

function Legend({ layer }: { layer: PartPatternLayer }) {
  const kinds = useMemo(() => [...new Set(layer.path.segments.map((s) => s.kind))], [layer]);
  return (
    <Group gap="sm" wrap="wrap" data-testid="layer-legend">
      {kinds.map((k) => (
        <Group key={k} gap={4} wrap="nowrap" data-testid={`layer-kind-${k}`}>
          <span style={{ width: 14, height: 4, borderRadius: 2, background: segmentStyle(k).color, display: 'inline-block' }} aria-hidden="true" />
          <Text size="xs">{segmentStyle(k).label}</Text>
        </Group>
      ))}
      <Group gap={4} wrap="nowrap">
        <svg width="12" height="12" aria-hidden="true">
          <circle cx="6" cy="6" r="4" fill="var(--mantine-color-body)" stroke="var(--mantine-color-text)" strokeWidth="1.5" />
        </svg>
        <Text size="xs">Start</Text>
      </Group>
      <Group gap={4} wrap="nowrap">
        <svg width="12" height="12" aria-hidden="true">
          <rect x="2" y="2" width="8" height="8" fill="var(--mantine-color-text)" />
        </svg>
        <Text size="xs">Ende</Text>
      </Group>
      {layer.neighbor ? (
        <Text size="xs" c="dimmed">
          blass: {layer.neighbor_relation === 'next' ? 'Folgeschicht' : 'Vorgängerschicht'} {layer.neighbor.layer + 1}
        </Text>
      ) : null}
    </Group>
  );
}

/**
 * 2D-Vorschau einer Schicht des gerechneten Teils. Die Geometrie liefert die API (Frame P aus
 * `toolpath.json`); der Browser zeichnet nur. Die Schicht ist wählbar.
 */
export function LayerPreview({ partId }: { partId: string }) {
  const loadLayer = useAppStore((s) => s.loadPatternLayer);
  const runId = useAppStore((s) => s.run?.runId ?? null);
  const nLayers = useAppStore((s) => s.run?.parts[partId]?.n_layers ?? 0);
  const [layer, setLayer] = useState(0);
  const [data, setData] = useState<PartPatternLayer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const svgId = useId();

  // Anderes Teil oder anderer Lauf: wieder bei Schicht 1 anfangen.
  useEffect(() => setLayer(0), [partId, runId]);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    loadLayer(partId, layer)
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, [loadLayer, partId, layer, runId]);

  const total = data?.n_layers ?? nLayers;
  const last = Math.max(0, total - 1);
  const shown = Math.min(layer, last);

  return (
    <Paper withBorder p="xs" data-testid="layer-preview" data-part={partId}>
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap">
          <Text fw={600} size="sm">
            Schichtvorschau {partId}
          </Text>
          <Group gap={4} wrap="nowrap">
            {busy ? <Loader size="xs" /> : null}
            <Text size="xs" c="dimmed" data-testid="layer-label">
              Schicht {shown + 1} von {total || '–'}
              {data ? ` · z = ${num(data.z_mm, 0)} mm` : ''}
            </Text>
          </Group>
        </Group>
        {total > 1 ? (
          <Group gap="xs" wrap="nowrap">
            <ActionIcon variant="default" size="sm" aria-label="Vorige Schicht" disabled={shown <= 0} onClick={() => setLayer(shown - 1)} data-testid="layer-prev">
              ‹
            </ActionIcon>
            <Slider
              style={{ flex: 1 }}
              min={0}
              max={last}
              step={1}
              value={shown}
              onChange={setLayer}
              label={(v) => `Schicht ${v + 1}`}
              aria-label="Schicht wählen"
              thumbLabel="Schicht wählen"
              data-testid="layer-slider"
            />
            <ActionIcon variant="default" size="sm" aria-label="Nächste Schicht" disabled={shown >= last} onClick={() => setLayer(shown + 1)} data-testid="layer-next">
              ›
            </ActionIcon>
          </Group>
        ) : null}
        {error ? (
          <ErrorNote message="Die Schicht konnte nicht geladen werden. Lauf neu rechnen oder die Verbindung prüfen." detail={error} testid="layer-error" />
        ) : null}
        {data ? (
          <>
            <LayerSvg layer={data} svgId={svgId} />
            <Legend layer={data} />
          </>
        ) : error ? null : (
          <Text size="xs" c="dimmed">
            Schicht wird geladen …
          </Text>
        )}
      </Stack>
    </Paper>
  );
}
