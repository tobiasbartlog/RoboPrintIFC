/* eslint-disable */
/**
 * GENERIERT aus schemas/Toolpath.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface Toolpath {
  bead_width_mm: number;
  layer_height_mm: number;
  part_id: string;
  rings: Ring[];
  schema_version: "2";
}
export interface Ring {
  closed: boolean;
  kind: "outer" | "inner" | "hole";
  layer: number;
  shell: number;
  waypoints: [number, number, number, number, number, number, number][];
}
