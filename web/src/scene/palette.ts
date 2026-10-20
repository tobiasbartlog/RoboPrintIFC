import { useEffect, useState } from 'react';

/**
 * Farben der Szene kommen aus den Mantine-CSS-Variablen (Theme, hell/dunkel). Die Rueckfallwerte
 * greifen nur, wenn kein MantineProvider laeuft (Testseite, Vitest).
 */
export interface ScenePalette {
  background: string;
  floor: string;
  table: string;
  part: string;
  ghost: string;
  danger: string;
  warn: string;
  toolpathDone: string;
  toolpathTodo: string;
  accent: string;
  /** Segmentarten des Druckmusters (gleiche Farben wie die 2D-Vorschau und die Legende) */
  infill: string;
  web: string;
  outfill: string;
}

const VARS: Record<keyof ScenePalette, [string, string]> = {
  background: ['--mantine-color-body', '#f1f3f5'],
  floor: ['--mantine-color-gray-4', '#ced4da'],
  table: ['--mantine-color-gray-6', '#868e96'],
  part: ['--mantine-color-orange-6', '#f76707'],
  ghost: ['--mantine-color-blue-3', '#74c0fc'],
  danger: ['--mantine-color-red-6', '#fa5252'],
  warn: ['--mantine-color-yellow-5', '#fcc419'],
  toolpathDone: ['--mantine-color-dark-6', '#373a40'],
  toolpathTodo: ['--mantine-color-gray-5', '#adb5bd'],
  accent: ['--mantine-color-blue-6', '#228be6'],
  infill: ['--mantine-color-pink-6', '#e64980'],
  web: ['--mantine-color-green-6', '#40c057'],
  outfill: ['--mantine-color-violet-6', '#7950f2'],
};

export function readPalette(root: HTMLElement = document.documentElement): ScenePalette {
  const cs = getComputedStyle(root);
  const out = {} as ScenePalette;
  for (const key of Object.keys(VARS) as (keyof ScenePalette)[]) {
    const [name, fallback] = VARS[key];
    out[key] = cs.getPropertyValue(name).trim() || fallback;
  }
  return out;
}

/** Palette, die dem Farbschema (hell/dunkel) folgt. */
export function useScenePalette(): ScenePalette {
  const [palette, setPalette] = useState<ScenePalette>(() => readPalette());
  useEffect(() => {
    const update = () => setPalette(readPalette());
    update();
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-mantine-color-scheme'] });
    return () => obs.disconnect();
  }, []);
  return palette;
}
