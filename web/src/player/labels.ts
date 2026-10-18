/** Klartext und Theme-Farben (Mantine-CSS-Variablen, keine Hex-Werte) für den Player. */
import type { Kind, Status } from './clock';

const LINKS: Record<string, string> = {
  base_link: 'Sockel',
  tool_body: 'Werkzeug',
  nozzle_tip: 'Düse',
};

export function linkLabel(name: string): string {
  const m = /^link_(\d)$/.exec(name);
  if (m) return `Glied ${m[1]}`;
  return LINKS[name] ?? name;
}

const OBSTACLES: Record<string, string> = { floor: 'Boden', table: 'Tisch', printed: 'Druckstand' };

export function obstacleLabel(name: string): string {
  return OBSTACLES[name] ?? linkLabel(name);
}

export const KIND_LABEL: Record<Kind, string> = {
  print: 'Druck',
  approach: 'Anfahrt',
  retract: 'Abfahrt',
  lift: 'Anheben',
  transfer: 'Umsetzen',
  lower: 'Absenken',
};

export const STATUS_LABEL: Record<Status, string> = {
  ok: 'frei',
  warn: 'Warnung',
  collision: 'Kollision',
  unreachable: 'unerreichbar',
};

const v = (c: string) => `var(--mantine-color-${c})`;

export const KIND_COLOR: Record<Kind, string> = {
  print: v('blue-6'),
  approach: v('cyan-4'),
  retract: v('cyan-4'),
  lift: v('grape-4'),
  lower: v('grape-4'),
  transfer: v('gray-5'),
};

export const STATUS_COLOR: Record<Status, string> = {
  ok: v('green-6'),
  warn: v('yellow-5'),
  collision: v('red-6'),
  unreachable: `repeating-linear-gradient(45deg, ${v('gray-6')} 0 3px, ${v('gray-3')} 3px 6px)`,
};

export const STATUS_BADGE: Record<Status, string> = { ok: 'green', warn: 'yellow', collision: 'red', unreachable: 'gray' };

export function fmt(x: number, digits = 1): string {
  return x.toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
