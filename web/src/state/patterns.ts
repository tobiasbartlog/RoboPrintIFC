/**
 * Reine Darstellungshilfen des Mustererstellers: Beschriftungen, Formatierung, Anfrage-Aufbau.
 * Keine Fachlogik (SPEC §9): Geometrie, Regeln und Kennzahlen kommen fertig aus dem Kern.
 */
import type {
  PatternCatalog,
  PatternContactKind,
  PatternInfo,
  PatternOutlineBox,
  PatternParamSpec,
  PatternPreviewRequest,
  PatternSegmentKind,
} from '../contracts';

export type PatternValue = boolean | number | string | number[] | null;
export type PatternValues = Record<string, PatternValue>;

export interface OutlineState {
  length_mm: number;
  thickness_mm: number;
  /** `free`, `module:<part_id>` oder `wall:<wall_id>`: woher die Vorgabe stammt. */
  source: string;
}

export const DEFAULT_OUTLINE: OutlineState = { length_mm: 600, thickness_mm: 200, source: 'free' };

/** Segmentarten: Beschriftung und Theme-Farbe. Neue Arten des Kerns erscheinen mit neutraler Farbe. */
export const SEGMENT_STYLE: Record<string, { label: string; color: string }> = {
  outer: { label: 'Außenschale', color: 'var(--mantine-color-blue-6)' },
  inner: { label: 'Innenschale', color: 'var(--mantine-color-cyan-6)' },
  hole: { label: 'Laibungsschale', color: 'var(--mantine-color-teal-6)' },
  infill: { label: 'Infill / Gurt', color: 'var(--mantine-color-orange-6)' },
  web: { label: 'Steg', color: 'var(--mantine-color-green-6)' },
  outfill: { label: 'Außenfeld / Endkappe', color: 'var(--mantine-color-violet-6)' },
};
const UNKNOWN_COLOR = 'var(--mantine-color-gray-6)';

export const CONTACT_STYLE: Record<string, { label: string; color: string }> = {
  joint: { label: 'Fuge (Sollbruchstelle)', color: 'var(--mantine-color-grape-6)' },
  node: { label: 'Knoten', color: 'var(--mantine-color-yellow-6)' },
  shell: { label: 'Kontakt an Schale', color: 'var(--mantine-color-lime-6)' },
};

export function segmentStyle(kind: PatternSegmentKind | string): { label: string; color: string } {
  return SEGMENT_STYLE[kind] ?? { label: kind, color: UNKNOWN_COLOR };
}
export function contactStyle(kind: PatternContactKind | string): { label: string; color: string } {
  return CONTACT_STYLE[kind] ?? { label: kind, color: UNKNOWN_COLOR };
}

export const RULE_TITLE: Record<string, string> = {
  M1: 'Durchgehend (ein Strang)',
  M2: 'Kreuzungsfrei',
  M3: 'Überhangfrei',
  M4: 'Senkrechter Schichtwechsel',
  M5: 'Im Teil',
  M6: 'Druckbar gekrümmt',
  M7: 'Kontakt',
};

export const LAYER_CHANGE_LABEL: Record<string, string> = {
  vertical: 'senkrecht (reiner Z-Hub)',
  restart: 'Neustart (Querschnitt ändert sich)',
  diagonal: 'diagonal (Regel M4 verletzt)',
};

const nf = (digits: number) => new Intl.NumberFormat('de-DE', { minimumFractionDigits: 0, maximumFractionDigits: digits });
const NF = [nf(0), nf(1), nf(2), nf(3)];

const finite = (v: number | null | undefined): v is number => v !== null && v !== undefined && Number.isFinite(v);

/** Zahl mit deutschem Komma; `null` und nicht endliche Werte als Gedankenstrich. */
export function num(v: number | null | undefined, digits = 1): string {
  return finite(v) ? (NF[Math.min(digits, 3)] ?? NF[1]!).format(v) : '–';
}

export function mm(v: number | null | undefined, digits = 1): string {
  return finite(v) ? `${num(v, digits)} mm` : '–';
}

/** Länge: ab 1 m in m, sonst in mm. */
export function length(v: number | null | undefined): string {
  if (!finite(v)) return '–';
  return v >= 1000 ? `${num(v / 1000, 2)} m` : `${num(v, 0)} mm`;
}

export function seconds(v: number | null | undefined): string {
  if (!finite(v)) return '–';
  if (v < 60) return `${num(v, 1)} s`;
  const m = Math.floor(v / 60);
  return `${m} min ${String(Math.round(v - m * 60)).padStart(2, '0')} s`;
}

/** Fugenabstände kompakt: gleichmäßig → „3 × 200 mm“, sonst Spanne. */
export function spacingSummary(values: readonly (number | null)[]): string {
  const v = values.filter(finite);
  if (v.length === 0) return '–';
  const lo = Math.min(...v);
  const hi = Math.max(...v);
  if (hi - lo < 0.5) return `${v.length} × ${num(lo, 1)} mm`;
  return `${v.length} Abstände, ${num(lo, 1)} bis ${num(hi, 1)} mm`;
}

export function patternInfo(catalog: PatternCatalog | null, name: string): PatternInfo | null {
  return catalog?.patterns.find((p) => p.name === name) ?? null;
}

/** Wert eines Reglers: eigene Änderung, sonst der vom Kern gemeldete wirksame Wert, sonst der Standard. */
export function effectiveValue(spec: PatternParamSpec, overrides: PatternValues, reported: Record<string, PatternValue | undefined> | null): PatternValue {
  const own = overrides[spec.name];
  if (own !== undefined) return own;
  const r = reported?.[spec.name];
  if (r !== undefined && r !== null) return r;
  return spec.default;
}

/** Anfrage an `POST /api/patterns/preview`. Es gehen nur die geänderten Regler mit. */
export function buildRequest(pattern: string, params: PatternValues, outline: OutlineState, layer: number): PatternPreviewRequest {
  const box: PatternOutlineBox = { length_mm: outline.length_mm, thickness_mm: outline.thickness_mm };
  return { pattern, preset: null, params: { ...params }, outline: box, layer };
}

/** Dateiname für den SVG-Export. */
export function svgFileName(pattern: string, outline: OutlineState): string {
  return `muster-${pattern}-${Math.round(outline.length_mm)}x${Math.round(outline.thickness_mm)}.svg`;
}

/** Querschnitt (Länge × Dicke) eines Moduls aus seiner Bounding-Box im Frame P. */
export function outlineOfBox(min: readonly number[], max: readonly number[]): { length_mm: number; thickness_mm: number } {
  return { length_mm: Math.round((max[0] ?? 0) - (min[0] ?? 0)), thickness_mm: Math.round((max[1] ?? 0) - (min[1] ?? 0)) };
}

/** Anzeigename für `PatternParamSpec`-Werte (Auswahl: Rohwert → deutscher Text, soweit bekannt). */
export const CHOICE_LABEL: Record<string, string> = {
  alternate: 'wechselnd',
  same: 'gleich',
  none: 'keins',
};
