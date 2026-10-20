import type { PatternPath, PatternPreview, PatternViolation } from '../contracts';
import { contactStyle, RULE_TITLE, segmentStyle } from '../state/patterns';

type Pt = readonly [number, number];

/** SVG-Punktliste; die Y-Achse wird gespiegelt, damit Y nach oben zeigt wie im Frame P. */
function pts(points: readonly Pt[], closed = false): string {
  const first = points[0];
  const p = closed && first ? [...points, first] : points;
  return p.map(([x, y]) => `${x},${-y}`).join(' ');
}

const NON_SCALING = { vectorEffect: 'non-scaling-stroke' } as const;

function Arrow({ at, dir, size, color }: { at: Pt; dir: Pt; size: number; color: string }) {
  const [ax, ay] = [at[0], -at[1]];
  const [dx, dy] = [dir[0], -dir[1]];
  const L = size;
  const B = size * 0.5;
  const tip = [ax + (dx * L) / 2, ay + (dy * L) / 2];
  const a = [ax - (dx * L) / 2 - dy * B, ay - (dy * L) / 2 + dx * B];
  const b = [ax - (dx * L) / 2 + dy * B, ay - (dy * L) / 2 - dx * B];
  return <polygon points={`${tip},${a},${b}`} style={{ fill: color }} />;
}

function PathLayer({ path, w, faint }: { path: PatternPath; w: number; faint: boolean }) {
  if (faint) {
    return (
      <g data-testid="pat-next-layer" style={{ opacity: 0.45 }}>
        {path.segments.map((s) => (
          <polyline
            key={s.index}
            points={pts(s.points as Pt[], s.closed)}
            fill="none"
            strokeDasharray="7 5"
            strokeWidth={5}
            {...NON_SCALING}
            style={{ stroke: 'var(--mantine-color-dimmed)' }}
          />
        ))}
      </g>
    );
  }
  const arrow = Math.max(w * 0.4, 7);
  return (
    <g data-testid="pat-path">
      {/* Raupenfläche (Mittellinie ⊕ w/2), blass */}
      {path.segments.map((s) => (
        <polyline
          key={`b${s.index}`}
          points={pts(s.points as Pt[], s.closed)}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={w}
          style={{ stroke: segmentStyle(s.kind).color, opacity: 0.2 }}
        />
      ))}
      {path.connectors
        .filter((c) => c.length_mm > 1e-6)
        .map((c, i) => (
          <polyline
            key={`c${i}`}
            points={pts([c.from as Pt, c.to as Pt])}
            strokeDasharray="3 3"
            strokeWidth={1.5}
            {...NON_SCALING}
            style={{ stroke: 'var(--mantine-color-text)' }}
          />
        ))}
      {path.segments.map((s) => (
        <g key={s.index} data-testid={`pat-segment-${s.kind}`}>
          <polyline
            points={pts(s.points as Pt[], s.closed)}
            fill="none"
            strokeWidth={2.2}
            strokeLinejoin="round"
            {...NON_SCALING}
            style={{ stroke: segmentStyle(s.kind).color }}
          >
            <title>{`${segmentStyle(s.kind).label}${s.label ? ` (${s.label})` : ''}, ${Math.round(s.length_mm)} mm`}</title>
          </polyline>
          {s.arrows.map((a, i) => (
            <Arrow key={i} at={a.at as Pt} dir={a.dir as Pt} size={arrow} color={segmentStyle(s.kind).color} />
          ))}
        </g>
      ))}
      <circle
        cx={path.start[0]}
        cy={-path.start[1]}
        r={w * 0.3}
        fill="none"
        strokeWidth={3}
        {...NON_SCALING}
        style={{ stroke: 'var(--mantine-color-green-7)' }}
        data-testid="pat-start"
      >
        <title>Start</title>
      </circle>
      <rect
        x={path.end[0] - w * 0.25}
        y={-path.end[1] - w * 0.25}
        width={w * 0.5}
        height={w * 0.5}
        fill="none"
        strokeWidth={3}
        {...NON_SCALING}
        style={{ stroke: 'var(--mantine-color-text)' }}
        data-testid="pat-end"
      >
        <title>Ende</title>
      </rect>
    </g>
  );
}

function ViolationMark({ v, w, selected }: { v: PatternViolation; w: number; selected: boolean }) {
  if (!v.at) return null;
  const error = v.severity === 'error';
  const color = error ? 'var(--mantine-color-red-6)' : 'var(--mantine-color-orange-6)';
  const r = Math.max(w * 0.55, 9) * (selected ? 1.5 : 1);
  return (
    <g data-testid="pat-violation-mark" data-severity={v.severity}>
      <circle cx={v.at[0]} cy={-v.at[1]} r={r} fill="none" strokeWidth={selected ? 4 : 2.5} strokeDasharray={error ? undefined : '5 3'} {...NON_SCALING} style={{ stroke: color }}>
        <title>{`${v.rule} ${RULE_TITLE[v.rule] ?? ''}: ${v.message}`}</title>
      </circle>
      <text x={v.at[0]} y={-v.at[1] - r - 3} textAnchor="middle" fontSize={Math.max(w * 0.4, 9)} fontWeight={700} style={{ fill: color }}>
        {v.rule}
      </text>
    </g>
  );
}

/**
 * Draufsicht einer Schicht, gezeichnet aus der Antwort des Kerns: Querschnitt, Folgeschicht blass
 * gestrichelt, Strang nach Segmentart, Richtungspfeile, Start/Ende, Kontakte, Verstöße rot.
 */
export function PatternSvg({ preview, selectedViolation }: { preview: PatternPreview; selectedViolation: number | null }) {
  const w = Number(preview.params.bead_width_mm ?? 30);
  const [x0, y0, x1, y1] = preview.outline.bounds;
  const m = Math.max(w, 15);
  const viewBox = `${x0 - m} ${-(y1 + m)} ${x1 - x0 + 2 * m} ${y1 - y0 + 2 * m}`;
  return (
    <svg
      viewBox={viewBox}
      role="img"
      aria-label="Draufsicht einer Schicht des Musters"
      data-testid="pattern-svg"
      data-layer={preview.layer}
      style={{ width: '100%', height: 'auto', maxHeight: '58vh', display: 'block' }}
    >
      {preview.outline.polygons.map((poly, i) => (
        <path
          key={i}
          d={`M ${pts(poly.exterior as Pt[])} Z ${poly.holes.map((h) => `M ${pts(h as Pt[])} Z`).join(' ')}`}
          fillRule="evenodd"
          strokeWidth={1.5}
          {...NON_SCALING}
          style={{ fill: 'var(--mantine-color-gray-light)', stroke: 'var(--mantine-color-gray-5)' }}
        />
      ))}
      {preview.next_layer.paths.map((p, i) => (
        <PathLayer key={`n${i}`} path={p} w={w} faint />
      ))}
      {preview.paths.map((p, i) => (
        <PathLayer key={`p${i}`} path={p} w={w} faint={false} />
      ))}
      {preview.contacts.map((c, i) => (
        <circle
          key={i}
          cx={c.at[0]}
          cy={-c.at[1]}
          r={w * 0.22}
          strokeWidth={1.5}
          {...NON_SCALING}
          style={{ fill: contactStyle(c.kind).color, stroke: 'var(--mantine-color-body)' }}
          data-testid={`pat-contact-${c.kind}`}
        >
          <title>{`${contactStyle(c.kind).label}, Kontaktlänge ${Math.round(c.length_mm)} mm`}</title>
        </circle>
      ))}
      {preview.violations.map((v, i) => (
        <ViolationMark key={i} v={v} w={w} selected={selectedViolation === i} />
      ))}
    </svg>
  );
}
