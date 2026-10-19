/* eslint-disable */
/**
 * GENERIERT aus schemas/Summary.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface Summary {
  assumptions: string[];
  params: {
    [k: string]: number | string | boolean;
  };
  parts: PartEntry[];
  provenance: Provenance;
  scenario_id: string;
  scenario_path: string;
  schema_version: "2";
  timings_s: {
    [k: string]: number;
  };
  walls: WallEntry[];
}
export interface PartEntry {
  d_min_mm: number | null;
  n_collision: number;
  n_unreachable: number;
  part_id: string;
  same_as: string | null;
  status: "machbar" | "nicht machbar";
  wall_id: string;
}
export interface Provenance {
  command: string;
  created: string;
  git_commit: string | null;
}
export interface WallEntry {
  eligible: boolean;
  height_mm: number;
  length_mm: number;
  name: string;
  part_ids: string[];
  reason: string | null;
  thickness_mm: number;
  volume_mm3: number;
  wall_id: string;
}
