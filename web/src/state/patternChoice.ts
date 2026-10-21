/**
 * Musterwahl für den Ablauf („Zerlegen & prüfen“). Die fünf Felder heißen wie die Szenario-
 * Parameter des Kerns (docs/muster/ARTEFAKT-FORMAT.md) und gehen unverändert in den Job. Der
 * Standard (kein Muster, Schichtfolge leer) schneidet wie bisher. Der Browser rechnet nichts:
 * Namen, Rollen und Presets kommen aus dem Katalog der API.
 */
import type { PatternCatalog } from '../contracts';

export type LayerOrderChoice = '' | 'same' | 'alternate';

export interface PatternChoice {
  /** leer = nicht gesetzt: ohne Muster wie bisher, mit Muster die Folge des Musters (senkrechter Schichtwechsel) */
  layer_order: LayerOrderChoice;
  infill_pattern: string;
  outfill_pattern: string;
  /** Preset-id (mitgeliefert oder eigen); der Server löst sie in die Datei auf */
  pattern_preset: string;
  /** JSON-Objekt als Text (nur geänderte Regler), leer = keine */
  pattern_params: string;
}

export const DEFAULT_PATTERN: PatternChoice = {
  layer_order: '',
  infill_pattern: 'none',
  outfill_pattern: 'none',
  pattern_preset: '',
  pattern_params: '',
};

/** Kernregler, die der Lauf aus den Druckeinstellungen nimmt; sie gehen nicht in `pattern_params`. */
export const SCENARIO_OWNED = ['bead_width_mm', 'layer_height_mm', 'step_mm', 'link_max_mm'] as const;

export const LAYER_ORDER_OPTIONS: { value: LayerOrderChoice; label: string }[] = [
  { value: '', label: 'Standard' },
  { value: 'same', label: 'gleich' },
  { value: 'alternate', label: 'wechselnd' },
];

export function isDefaultPattern(c: PatternChoice): boolean {
  return (Object.keys(DEFAULT_PATTERN) as (keyof PatternChoice)[]).every((k) => c[k] === DEFAULT_PATTERN[k]);
}

/** Anzahl der Einstellungen, die vom Standard abweichen (für das Kennzeichen „geändert“). */
export function patternChanged(c: PatternChoice): number {
  return (Object.keys(DEFAULT_PATTERN) as (keyof PatternChoice)[]).filter((k) => c[k] !== DEFAULT_PATTERN[k]).length;
}

/** Wert der Auswahl: `none`, `preset:<id>`, `infill:<name>` oder `outfill:<name>`. */
export function selectionOf(c: PatternChoice): string {
  if (c.pattern_preset) return `preset:${c.pattern_preset}`;
  if (c.infill_pattern !== 'none') return `infill:${c.infill_pattern}`;
  if (c.outfill_pattern !== 'none') return `outfill:${c.outfill_pattern}`;
  return 'none';
}

/** Auswahl → Felder. Reglerwerte aus früheren Wahlen entfallen, die Schichtfolge bleibt. */
export function choiceForSelection(selection: string, current: PatternChoice): PatternChoice {
  const base: PatternChoice = { ...DEFAULT_PATTERN, layer_order: current.layer_order };
  const [kind, ...rest] = selection.split(':');
  const name = rest.join(':');
  if (kind === 'preset' && name) return { ...base, pattern_preset: name };
  if (kind === 'infill' && name) return { ...base, infill_pattern: name };
  if (kind === 'outfill' && name) return { ...base, outfill_pattern: name };
  return base;
}

/** Namen der Basismuster, die kein Muster im Sinne des Ablaufs sind (nur Schalen). */
function isBase(catalog: PatternCatalog | null, name: string): boolean {
  return (catalog?.base_patterns ?? ['schalen']).includes(name);
}

/**
 * Übernahme aus dem Musterersteller („Für Lauf verwenden“): gewähltes Muster oder Preset, dazu die
 * geänderten Regler als `pattern_params`. Das Basismuster „Schalen“ ist kein Muster. Die
 * Schichtfolge wandert in ihr eigenes Feld; Strangbreite, Schichthöhe, Abtastabstand und Verbinder
 * gelten aus den Druckeinstellungen.
 */
export function choiceFromBuilder(
  catalog: PatternCatalog | null,
  pattern: string,
  presetId: string | null,
  overrides: Record<string, unknown>,
): PatternChoice {
  const params: Record<string, unknown> = {};
  let layerOrder: LayerOrderChoice = '';
  // Beim Laden eines Presets stehen alle seine Werte als Regler; nur Abweichungen gehören in den Lauf.
  const preset = presetId ? catalog?.presets.find((p) => p.id === presetId)?.preset.params : undefined;
  for (const [k, v] of Object.entries(overrides)) {
    if (v === null || v === undefined || (SCENARIO_OWNED as readonly string[]).includes(k)) continue;
    if (preset && JSON.stringify(preset[k]) === JSON.stringify(v)) continue;
    if (k === 'layer_order') layerOrder = v === 'same' || v === 'alternate' ? v : '';
    else params[k] = v;
  }
  const text = Object.keys(params).length ? JSON.stringify(params, Object.keys(params).sort()) : '';
  const out: PatternChoice = { ...DEFAULT_PATTERN, layer_order: layerOrder, pattern_params: text };
  if (presetId) return { ...out, pattern_preset: presetId };
  const role = catalog?.patterns.find((p) => p.name === pattern)?.role;
  if (isBase(catalog, pattern)) return { ...DEFAULT_PATTERN, layer_order: layerOrder };
  // Infill-Muster gehören nach `infill`, Außenhaut und „ganze Wand“ nach `outfill` (SPEC des Kerns).
  return role === 'infill' ? { ...out, infill_pattern: pattern } : { ...out, outfill_pattern: pattern };
}

/** Geänderte Reglerwerte aus dem Text, für die Anzeige („3 Regler geändert“). */
export function paramsOf(c: PatternChoice): Record<string, unknown> {
  if (!c.pattern_params) return {};
  try {
    const v: unknown = JSON.parse(c.pattern_params);
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

/** Job-Parameter: nur, was vom Standard abweicht; `pattern_params` als Objekt. */
export function jobPatternParams(c: PatternChoice): Record<string, string | Record<string, number | string | boolean | number[]>> {
  const out: Record<string, string | Record<string, number | string | boolean | number[]>> = {};
  if (c.layer_order) out.layer_order = c.layer_order;
  if (c.infill_pattern !== 'none') out.infill_pattern = c.infill_pattern;
  if (c.outfill_pattern !== 'none') out.outfill_pattern = c.outfill_pattern;
  if (c.pattern_preset) out.pattern_preset = c.pattern_preset;
  const p = paramsOf(c);
  if (Object.keys(p).length) out.pattern_params = p as Record<string, number | string | boolean | number[]>;
  return out;
}

/** Name für die Anzeige: Preset-Name, Musterbeschriftung oder die Kennung, solange der Katalog fehlt. */
export function choiceLabel(c: PatternChoice, catalog: PatternCatalog | null): string {
  if (c.pattern_preset) {
    const e = catalog?.presets.find((p) => p.id === c.pattern_preset);
    return e ? `${e.preset.name}${e.source === 'user' ? ' (eigenes)' : ''}` : c.pattern_preset;
  }
  const name = c.infill_pattern !== 'none' ? c.infill_pattern : c.outfill_pattern !== 'none' ? c.outfill_pattern : null;
  if (!name) return 'Kein Muster';
  return catalog?.patterns.find((p) => p.name === name)?.label ?? name;
}

/** Zusammenfassung unter der Auswahl. */
export function choiceSummary(c: PatternChoice, catalog: PatternCatalog | null): string {
  const order = LAYER_ORDER_OPTIONS.find((o) => o.value === c.layer_order)?.label ?? c.layer_order;
  const n = Object.keys(paramsOf(c)).length;
  const parts = [choiceLabel(c, catalog)];
  if (c.layer_order) parts.push(`Schichtfolge ${order}`);
  if (n) parts.push(`${n} Regler geändert`);
  return parts.join(' · ');
}
