/* eslint-disable */
/**
 * GENERIERT aus schemas/PartPatternReport.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

/**
 * Kennzahlen des Druckmusters eines Teils (ohne Muster: nur Schalen).
 */
export interface PartPatternReport {
  bead_width_mm: number;
  has_pattern: boolean;
  infill: string | null;
  kinds: PartKindStat[];
  layer_changes: PartLayerChanges;
  layer_height_mm: number;
  layer_order: ("same" | "alternate") | null;
  layers: PartLayerStat[];
  max_strands_per_layer: number;
  n_layers: number;
  n_open_rings: number;
  n_rings: number;
  /**
   * Stränge im ganzen Teil (Pumpe an, kein Halt)
   */
  n_strands: number;
  outfill: string | null;
  part_id: string;
  print_time_s: number;
  total_length_mm: number;
  v_print_mm_s: number;
  volume_l: number;
}
export interface PartKindStat {
  kind: "outer" | "inner" | "hole" | "infill" | "web" | "outfill";
  length_mm: number;
  rings: number;
  /**
   * Anteil an der gesamten Druckbahnlänge
   */
  share: number;
}
export interface PartLayerChanges {
  /**
   * Verbinder mit größerem waagrechtem Versatz
   */
  diagonal: number;
  /**
   * größter waagrechter Versatz eines Verbinders, None ohne Verbinder
   */
  max_offset_mm: number | null;
  /**
   * Schichtwechsel mit Absetzen
   */
  travel: number;
  /**
   * Verbinder mit waagrechtem Versatz ≤ 0,5 mm (reiner Z-Hub)
   */
  vertical: number;
}
export interface PartLayerStat {
  layer: number;
  length_mm: number;
  rings: number;
  /**
   * Zusammenhängende Stränge innerhalb der Schicht (ohne Absetzen)
   */
  strands: number;
}
