/**
 * Zustand-Store des Mustererstellers: Auswahl, Regler (nur Änderungen gegenüber dem Standard),
 * Querschnitt, entprellte Vorschau, Speichern. Rechnet nichts: Die Vorschau kommt vom Kern.
 */
import { createStore, type StoreApi } from 'zustand/vanilla';
import type { PatternCatalog, PatternPresetEntry, PatternPreview } from '../contracts';
import type { PatternApi } from './patternApi';
import { buildRequest, DEFAULT_OUTLINE, patternInfo, svgFileName, type OutlineState, type PatternValue, type PatternValues } from './patterns';

export interface PatternState {
  catalog: PatternCatalog | null;
  catalogError: string | null;
  pattern: string;
  /** Gewähltes Preset (Vorlage) oder null. Ändert der Nutzer danach etwas, bleibt die Herkunft stehen. */
  presetId: string | null;
  params: PatternValues;
  outline: OutlineState;
  layer: number;
  preview: PatternPreview | null;
  /** Rechnet gerade (Anfrage unterwegs oder entprellt). */
  busy: boolean;
  previewError: string | null;
  /**
   * HTTP-Status des Vorschaufehlers: 400/422 heißt „Einstellung ungültig“ (Meldung des Kerns ist
   * Klartext), alles andere (null = Netz) heißt „Server nicht erreichbar“.
   */
  previewErrorStatus: number | null;
  saved: PatternPresetEntry | null;
  saveError: string | null;
  loadCatalog: () => Promise<void>;
  selectPattern: (name: string) => void;
  selectPreset: (id: string) => void;
  setParam: (name: string, value: PatternValue) => void;
  resetParam: (name: string) => void;
  resetParams: () => void;
  setOutline: (patch: Partial<OutlineState>) => void;
  setLayer: (layer: number) => void;
  save: (name: string, description: string) => Promise<boolean>;
  /** SVG-Text des Kerns für die aktuelle Einstellung (Export). */
  exportSvg: () => Promise<{ text: string; fileName: string }>;
  /** Vorschau sofort (ohne Entprellung) anfordern. */
  refresh: () => void;
}

export type PatternStore = StoreApi<PatternState>;

export interface PatternStoreOptions {
  /** Entprellzeit der Regler in ms (Standard 120). */
  debounceMs?: number;
  /** Zuerst gewähltes Muster (Standard `schalen`, sonst das erste des Katalogs). */
  initialPattern?: string;
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function errorStatus(e: unknown): number | null {
  const s = (e as { status?: unknown } | null)?.status;
  return typeof s === 'number' ? s : null;
}

export function createPatternStore(api: PatternApi, opts: PatternStoreOptions = {}): PatternStore {
  const debounceMs = opts.debounceMs ?? 120;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;
  let seq = 0;

  const store: PatternStore = createStore<PatternState>((set, get) => {
    const run = () => {
      if (timer) clearTimeout(timer);
      timer = null;
      controller?.abort();
      const ctl = new AbortController();
      controller = ctl;
      const my = ++seq;
      const s = get();
      const req = buildRequest(s.pattern, s.params, s.outline, s.layer);
      set({ busy: true });
      api
        .preview(req, ctl.signal)
        .then((preview) => {
          if (my === seq) set({ preview, previewError: null, previewErrorStatus: null, busy: false });
        })
        .catch((e: unknown) => {
          if (my !== seq || ctl.signal.aborted) return;
          set({ previewError: errorText(e), previewErrorStatus: errorStatus(e), busy: false });
        });
    };
    const schedule = () => {
      if (timer) clearTimeout(timer);
      set({ busy: true, saved: null });
      timer = setTimeout(run, debounceMs);
    };

    return {
      catalog: null,
      catalogError: null,
      pattern: opts.initialPattern ?? 'schalen',
      presetId: null,
      params: {},
      outline: DEFAULT_OUTLINE,
      layer: 0,
      preview: null,
      busy: false,
      previewError: null,
      previewErrorStatus: null,
      saved: null,
      saveError: null,
      refresh: run,
      loadCatalog: async () => {
        set({ catalogError: null });
        try {
          const catalog = await api.getCatalog();
          const known = catalog.patterns.some((p) => p.name === get().pattern);
          set({ catalog, catalogError: null, pattern: known ? get().pattern : (catalog.patterns[0]?.name ?? get().pattern) });
          run();
        } catch (e) {
          set({ catalogError: errorText(e) });
        }
      },
      selectPattern: (name) => {
        // Kernregler bleiben, musterspezifische Regler fallen weg (eigener Satz je Muster).
        const core = new Set(get().catalog?.core_params.map((p) => p.name) ?? []);
        const keep = Object.fromEntries(Object.entries(get().params).filter(([k]) => core.has(k)));
        set({ pattern: name, presetId: null, params: keep });
        schedule();
      },
      selectPreset: (id) => {
        const entry = get().catalog?.presets.find((p) => p.id === id);
        if (!entry) return;
        const { preset } = entry;
        const o = preset.outline;
        const params = Object.fromEntries(Object.entries(preset.params).filter(([, v]) => v !== null)) as PatternValues;
        set({
          pattern: preset.pattern,
          presetId: id,
          params,
          outline: o && 'length_mm' in o ? { length_mm: o.length_mm, thickness_mm: o.thickness_mm, source: 'free' } : get().outline,
        });
        schedule();
      },
      setParam: (name, value) => {
        set({ params: { ...get().params, [name]: value } });
        schedule();
      },
      resetParam: (name) => {
        const { [name]: _drop, ...rest } = get().params;
        void _drop;
        set({ params: rest });
        schedule();
      },
      resetParams: () => {
        set({ params: {} });
        schedule();
      },
      setOutline: (patch) => {
        set({ outline: { ...get().outline, ...patch } });
        schedule();
      },
      setLayer: (layer) => {
        set({ layer: Math.max(0, Math.round(layer)) });
        schedule();
      },
      save: async (name, description) => {
        const s = get();
        const info = patternInfo(s.catalog, s.pattern);
        // Gespeichert werden die Änderungen und die Standardwerte des Musters, damit das Preset
        // auch bei späteren Änderungen der Standards dasselbe Muster beschreibt.
        const params: PatternValues = {};
        for (const spec of info?.params ?? []) if (spec.default !== null) params[spec.name] = spec.default;
        Object.assign(params, s.params);
        try {
          const entry = await api.savePreset({
            id: null,
            name,
            pattern: s.pattern,
            params,
            outline: { length_mm: s.outline.length_mm, thickness_mm: s.outline.thickness_mm },
            description,
          });
          const catalog = get().catalog;
          const presets = catalog ? [...catalog.presets.filter((p) => p.id !== entry.id), entry] : [];
          set({ saved: entry, saveError: null, presetId: entry.id, catalog: catalog ? { ...catalog, presets } : catalog });
          return true;
        } catch (e) {
          set({ saveError: errorText(e), saved: null });
          return false;
        }
      },
      exportSvg: async () => {
        const s = get();
        const text = await api.svg(buildRequest(s.pattern, s.params, s.outline, s.layer));
        return { text, fileName: svgFileName(s.pattern, s.outline) };
      },
    };
  });
  return store;
}
