import { Color } from 'three';
import type { ScenePalette } from './palette';
import type { KindColor } from './strand';

/** Segmentarten des Musters mit eigener Farbe in der 3D-Ansicht; Schalen und Verbinder behalten ihre Farbe. */
export function patternKindColors(p: ScenePalette): Record<string, string> {
  return { infill: p.infill, web: p.web, outfill: p.outfill };
}

/** RGB-Zuordnung (0..1) für Vertexfarben: Musterarten aus `colors`, alles andere `fallback`. */
export function kindColorFn(colors: Record<string, string>, fallback: string): KindColor {
  const cache = new Map<string, readonly [number, number, number]>();
  const rgb = (css: string): readonly [number, number, number] => {
    const c = new Color(css);
    return [c.r, c.g, c.b];
  };
  const base = rgb(fallback);
  return (kind) => {
    const hit = cache.get(kind);
    if (hit) return hit;
    const css = colors[kind];
    const out = css ? rgb(css) : base;
    cache.set(kind, out);
    return out;
  };
}
