/**
 * Fake-Implementierung von `PatternApi` für Komponententests. Sie rechnet keine Muster: Die Antwort
 * ist ein fester Zug aus zwei Segmenten, dessen Länge nur vom Querschnitt abhängt, damit Tests
 * sehen, dass eine Änderung ankommt. Fachlich geprüft wird gegen den echten Kern (Playwright).
 */
import type { PatternCatalog, PatternParamSpec, PatternPresetEntry, PatternPreview, PatternPreviewRequest } from '../contracts';
import type { PatternApi } from './patternApi';

const spec = (name: string, label: string, def: number, min: number, max: number, unit = 'mm'): PatternParamSpec => ({
  name,
  label,
  default: def,
  unit,
  minimum: min,
  maximum: max,
  step: 1,
  kind: 'float',
  choices: [],
  help: '',
});

export const FAKE_CATALOG: PatternCatalog = {
  base_patterns: ['none', 'schalen'],
  core_params: [spec('bead_width_mm', 'Strangbreite w', 30, 10, 60)],
  patterns: [
    { name: 'schalen', role: 'full', label: 'Schalen ohne Infill', description: 'Grundmuster.', family: 'schalen', layer_invariant: true, params: [] },
    {
      name: 'fugenwand',
      role: 'full',
      label: 'Fugenwand (Sollbruchstellen)',
      description: 'Gerade Felder mit Fugen.',
      family: 'fugenwand',
      layer_invariant: true,
      params: [spec('field_length_mm', 'Feldlänge', 240, 160, 300)],
    },
  ],
  presets: [],
};

export interface FakePatternOptions {
  /** Fehlertext für jede Vorschau (422 des Servers). */
  previewError?: string;
  /** Hinweise jeder Vorschau (z. B. „Infill entfällt: …“). */
  notes?: string[];
}

export function createFakePatternApi(opts: FakePatternOptions = {}): PatternApi & { requests: PatternPreviewRequest[]; presets: PatternPresetEntry[] } {
  const requests: PatternPreviewRequest[] = [];
  const presets: PatternPresetEntry[] = [];
  return {
    requests,
    presets,
    async getCatalog() {
      return { ...FAKE_CATALOG, presets: [...presets] };
    },
    async preview(req) {
      requests.push(req);
      if (opts.previewError) throw Object.assign(new Error(opts.previewError), { status: 422 });
      const o = req.outline && 'length_mm' in req.outline ? req.outline : { length_mm: 600, thickness_mm: 200 };
      const w = Number(req.params.bead_width_mm ?? 30);
      const L = o.length_mm;
      const T = o.thickness_mm;
      const pts: [number, number][] = [
        [-L / 2 + w, -T / 2 + w / 2],
        [L / 2 - w, -T / 2 + w / 2],
        [L / 2 - w, T / 2 - w / 2],
        [-L / 2 + w, T / 2 - w / 2],
      ];
      const field = Number(req.params.field_length_mm ?? 240);
      const seg = (index: number, kind: 'outer' | 'web') => ({
        index,
        kind,
        shell: 0,
        label: '',
        closed: false,
        points: index === 0 ? pts.slice(0, 2) : pts.slice(2),
        start: index === 0 ? pts[0]! : pts[2]!,
        end: index === 0 ? pts[1]! : pts[3]!,
        start_dir: [1, 0] as [number, number],
        end_dir: [1, 0] as [number, number],
        length_mm: L - 2 * w,
        arrows: [{ at: index === 0 ? ([0, -T / 2 + w / 2] as [number, number]) : ([0, T / 2 - w / 2] as [number, number]), dir: [1, 0] as [number, number] }],
      });
      const path = {
        layer: req.layer,
        island: 0,
        direction: 'out_in' as const,
        restart: false,
        closed: false,
        start: pts[0]!,
        end: pts[3]!,
        segments: [seg(0, 'outer'), seg(1, 'web')],
        connectors: [],
        length_mm: 2 * (L - 2 * w),
        meta: {},
        declared_contacts: [],
      };
      const length = path.length_mm;
      return {
        schema_version: 1,
        name: null,
        layer: req.layer,
        pattern: { infill: 'none', outfill: 'none', layer_order: 'alternate', resolved: { full: req.pattern, outfill: null, infill: null } },
        params: { bead_width_mm: w, ...req.params },
        outline: { polygons: [{ exterior: [[-L / 2, -T / 2], [L / 2, -T / 2], [L / 2, T / 2], [-L / 2, T / 2], [-L / 2, -T / 2]], holes: [] }], bounds: [-L / 2, -T / 2, L / 2, T / 2] },
        paths: [path],
        next_layer: { layer: req.layer + 1, paths: [path] },
        layer_change: { from: req.layer, to: req.layer + 1, distance_mm: 0, status: 'vertical' },
        contacts: [{ kind: 'joint', at: [0, 0], length_mm: 12, segments: [0, 1], distance_mm: w, overlap_mm: 0 }],
        violations: w > 50 ? [{ rule: 'M6', severity: 'warn', layer: req.layer, island: 0, at: [0, 0], value: 20, limit: w, message: 'Radius kleiner als die Strangbreite' }] : [],
        ok: true,
        notes: opts.notes ?? [],
        metrics: {
          path_length_mm: length,
          print_time_s: length / 100,
          v_print_mm_s: 100,
          strands: 1,
          material_l_per_m_layer: 1.5,
          material_l_per_m2: 150,
          contacts: 1,
          contact_length_mm: 12,
          contacts_per_m: 2,
          joint_spacing_mm: [field, field],
          longest_straight_outer_mm: field,
          min_radius_mm: 30,
          min_clearance_mm: 30,
          shell_coverage: 0.95,
          cells: [],
          paths: [],
        },
        fit: [{ island: 0, key: 'fit', count: 3, length_mm: L / 3, total_mm: L, target_mm: field, deviation_mm: L / 3 - field, positions_mm: [0, L / 3, (2 * L) / 3] }],
        timing_ms: { plan: 1, measure: 1, total: 2, api: 3 },
      } satisfies PatternPreview;
    },
    async savePreset(body) {
      const entry: PatternPresetEntry = {
        id: body.id ?? body.name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
        source: 'user',
        preset: { schema_version: 1, name: body.name, pattern: body.pattern, params: body.params, outline: body.outline ?? null, description: body.description ?? '' },
      };
      presets.push(entry);
      return entry;
    },
    async svg() {
      return '<svg xmlns="http://www.w3.org/2000/svg"></svg>';
    },
  };
}
