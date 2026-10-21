/* eslint-disable */
/**
 * GENERIERT aus schemas/PatternPreview.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

/**
 * Antwort von `POST /api/patterns/preview`: Schicht `layer` und Folgeschicht (blass).
 */
export interface PatternPreview {
  contacts: PatternContact[];
  fit: PatternFit[];
  layer: number;
  layer_change: PatternLayerChange | null;
  metrics: PatternMetrics;
  name: string | null;
  next_layer: PatternNextLayer;
  /**
   * Hinweise: was das Muster nicht wie gewählt druckt (Infill entfällt …)
   */
  notes: string[];
  ok: boolean;
  outline: PatternOutlineOut;
  params: {
    [k: string]: boolean | number | string | number[] | null;
  };
  paths: PatternPath[];
  pattern: PatternSelection;
  schema_version: number;
  timing_ms: PatternTiming;
  violations: PatternViolation[];
}
/**
 * Kontaktzone (Fuge, Knoten, Steg an Schale); `overlap_mm` = w − Mittellinienabstand.
 */
export interface PatternContact {
  /**
   * @minItems 2
   * @maxItems 2
   */
  at: [number, number];
  distance_mm: number | null;
  kind: "joint" | "node" | "shell";
  length_mm: number;
  overlap_mm: number | null;
  segments: number[];
}
/**
 * Ergebnis von `fit_to_length` aus den Musterdaten: tatsächliche Feldzahl und Feldlänge.
 */
export interface PatternFit {
  count: number;
  deviation_mm: number;
  island: number;
  /**
   * Ort in `meta` des Pfads, z. B. `fit` oder `fit_back`
   */
  key: string;
  length_mm: number;
  positions_mm: number[];
  target_mm: number;
  total_mm: number;
}
export interface PatternLayerChange {
  distance_mm: number;
  from: number;
  status: "vertical" | "restart" | "diagonal";
  to: number;
}
/**
 * Kennzahlen der Schicht (Summe über alle Inseln) und je Insel (`paths`).
 */
export interface PatternMetrics {
  cells: PatternCell[];
  contact_length_mm: number;
  contacts: number;
  contacts_per_m: number;
  joint_spacing_mm: (number | null)[];
  longest_straight_outer_mm: number | null;
  material_l_per_m2: number;
  material_l_per_m_layer: number;
  min_clearance_mm: number | null;
  min_radius_mm: number | null;
  path_length_mm: number;
  paths: PatternPathMetrics[];
  print_time_s: number;
  /**
   * kleinste Abdeckung des Schalenbereichs über alle Inseln, 0..1
   */
  shell_coverage: number;
  strands: number;
  v_print_mm_s: number;
}
export interface PatternCell {
  area_mm2: number;
  /**
   * @minItems 2
   * @maxItems 2
   */
  at: [number, number];
  span_mm: number;
}
export interface PatternPathMetrics {
  cells: PatternCell[];
  connectors_mm: (number | null)[];
  contact_length_mm: number | null;
  contact_lengths_mm: (number | null)[];
  contacts: number;
  contacts_by_kind: {
    [k: string]: PatternContactSum;
  };
  contacts_per_m: number | null;
  direction: string;
  /**
   * @minItems 2
   * @maxItems 2
   */
  end: [number, number];
  island: number;
  joint_spacing_mm: (number | null)[];
  joint_x_mm: (number | null)[];
  layer: number;
  longest_straight_outer_at: [number, number] | null;
  longest_straight_outer_mm: number | null;
  material_l_per_m2: number | null;
  material_l_per_m_layer: number | null;
  max_cell_area_mm2: number | null;
  max_cell_span_mm: number | null;
  max_chord_error_mm: number | null;
  min_clearance_mm: number | null;
  min_radius_mm: number | null;
  n_cells: number;
  n_segments: number;
  path_length_mm: number | null;
  print_time_s: number | null;
  /**
   * Abdeckung des Schalenbereichs, 0..1 (Maß wie G3)
   */
  shell_coverage: number;
  /**
   * @minItems 2
   * @maxItems 2
   */
  start: [number, number];
}
export interface PatternContactSum {
  count: number;
  length_mm: number;
}
export interface PatternNextLayer {
  layer: number;
  paths: PatternPath[];
}
/**
 * Ein Strang einer Schicht und Insel, Segmente in Druckreihenfolge.
 */
export interface PatternPath {
  closed: boolean;
  connectors: PatternConnector[];
  declared_contacts: PatternContact[];
  direction: "out_in" | "in_out";
  /**
   * @minItems 2
   * @maxItems 2
   */
  end: [number, number];
  island: number;
  layer: number;
  length_mm: number;
  meta: {
    [k: string]: unknown;
  };
  restart: boolean;
  segments: PatternSegment[];
  /**
   * @minItems 2
   * @maxItems 2
   */
  start: [number, number];
}
/**
 * Gerader Verbinder zwischen zwei Segmenten (Länge 0, wenn sie aneinanderstoßen).
 */
export interface PatternConnector {
  /**
   * @minItems 2
   * @maxItems 2
   */
  from: [number, number];
  length_mm: number;
  /**
   * @minItems 2
   * @maxItems 2
   */
  to: [number, number];
}
export interface PatternSegment {
  arrows: PatternArrow[];
  closed: boolean;
  /**
   * @minItems 2
   * @maxItems 2
   */
  end: [number, number];
  /**
   * @minItems 2
   * @maxItems 2
   */
  end_dir: [number, number];
  index: number;
  kind: "outer" | "inner" | "hole" | "infill" | "web" | "outfill";
  label: string;
  length_mm: number;
  points: [number, number][];
  shell: number;
  /**
   * @minItems 2
   * @maxItems 2
   */
  start: [number, number];
  /**
   * @minItems 2
   * @maxItems 2
   */
  start_dir: [number, number];
}
export interface PatternArrow {
  /**
   * @minItems 2
   * @maxItems 2
   */
  at: [number, number];
  /**
   * @minItems 2
   * @maxItems 2
   */
  dir: [number, number];
}
export interface PatternOutlineOut {
  /**
   * @minItems 4
   * @maxItems 4
   */
  bounds: [number, number, number, number];
  polygons: PatternOutlinePolygonOut[];
}
export interface PatternOutlinePolygonOut {
  exterior: [number, number][];
  holes: [number, number][][];
}
export interface PatternSelection {
  infill: string;
  layer_order: "same" | "alternate";
  outfill: string;
  resolved: PatternResolved;
}
export interface PatternResolved {
  full: string | null;
  infill: string | null;
  outfill: string | null;
}
export interface PatternTiming {
  /**
   * Gesamtzeit der Anfrage im Server (ms)
   */
  api: number | null;
  measure: number;
  plan: number;
  total: number;
}
/**
 * Verstoß gegen M1–M7: `error` macht das Muster ungültig, `warn` ist eine Zielverfehlung.
 */
export interface PatternViolation {
  at: [number, number] | null;
  island: number | null;
  layer: number | null;
  limit: number | null;
  message: string;
  rule: string;
  severity: "error" | "warn";
  value: number | null;
}
