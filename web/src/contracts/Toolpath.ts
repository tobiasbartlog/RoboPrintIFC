/* eslint-disable */
/**
 * GENERIERT aus schemas/Toolpath.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface Toolpath {
  bead_width_mm: number;
  layer_height_mm: number;
  part_id: string;
  pattern?: ToolpathPattern | null;
  rings: Ring[];
  schema_version: "2";
}
/**
 * Druckmuster eines Teils (opt-in, docs/muster/ARTEFAKT-FORMAT.md); nur zur Beschriftung.
 */
export interface ToolpathPattern {
  infill: string;
  layer_order: "same" | "alternate";
  notes?: string[];
  outfill: string;
  params: {
    [k: string]: number | string | boolean | number[];
  };
}
export interface Ring {
  closed: boolean;
  kind: "outer" | "inner" | "hole" | "infill" | "web" | "outfill";
  layer: number;
  link_next: boolean;
  shell: number;
  waypoints: [number, number, number, number, number, number, number][];
}
