/* eslint-disable */
/**
 * GENERIERT aus schemas/PartPatternLayer.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

/**
 * Eine Schicht des gerechneten Teils im Teil-Frame P (mm, XY) samt Nachbarschicht.
 */
export interface PartPatternLayer {
  bead_width_mm: number;
  /**
   * Ecken [min, max] aller Punkte der gezeigten Schichten
   *
   * @minItems 2
   * @maxItems 2
   */
  bounds: [[number, number], [number, number]];
  layer: number;
  n_layers: number;
  /**
   * Folgeschicht (letzte Schicht: Vorgängerschicht)
   */
  neighbor: PartLayerPath | null;
  neighbor_relation: ("next" | "previous") | null;
  part_id: string;
  path: PartLayerPath;
  z_mm: number;
}
export interface PartLayerPath {
  end: [number, number] | null;
  layer: number;
  length_mm: number;
  segments: PartLayerSegment[];
  start: [number, number] | null;
}
export interface PartLayerSegment {
  closed: boolean;
  kind: "outer" | "inner" | "hole" | "infill" | "web" | "outfill";
  link_next: boolean;
  points: [number, number][];
  ring: number;
  shell: number;
}
