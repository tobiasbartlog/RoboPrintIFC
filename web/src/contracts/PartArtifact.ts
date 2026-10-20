/* eslint-disable */
/**
 * GENERIERT aus schemas/PartArtifact.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface PartArtifact {
  /**
   * @minItems 4
   * @maxItems 4
   */
  T_LP: [
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number]
  ];
  /**
   * @minItems 4
   * @maxItems 4
   */
  T_SP: [
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number]
  ];
  /**
   * @minItems 4
   * @maxItems 4
   */
  T_WP: [
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number]
  ];
  bbox_P: BBox;
  cause: Cause | null;
  n_layers: number;
  part_id: string;
  placement: Placement;
  schema_version: "2";
  status: "machbar" | "nicht machbar";
  volume_mm3: number;
  wall_id: string;
}
export interface BBox {
  /**
   * @minItems 3
   * @maxItems 3
   */
  max: [number, number, number];
  /**
   * @minItems 3
   * @maxItems 3
   */
  min: [number, number, number];
}
export interface Cause {
  link: string;
  message: string;
  obstacle: string;
  sample: number;
  t_s: number;
}
export interface Placement {
  x_mm: number;
  y_mm: number;
  yaw_deg: number;
}
