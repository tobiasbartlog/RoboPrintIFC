/* eslint-disable */
/**
 * GENERIERT aus schemas/Trajectory.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface Trajectory {
  branch: number[];
  d_mm: (number | null)[];
  kind: ("print" | "approach" | "retract" | "lift" | "transfer" | "lower")[];
  layer: number[];
  pair: ([string, string] | null)[];
  part_id: string;
  psi_rad: number[];
  q: [number, number, number, number, number, number][];
  ring: number[];
  schema_version: "2";
  status: ("ok" | "warn" | "collision" | "unreachable")[];
  summary: TrajectorySummary;
  t_s: number[];
  tcp: [number, number, number, number, number, number, number][];
  witness: ([[number, number, number], [number, number, number]] | null)[];
}
export interface TrajectorySummary {
  d_min_mm: number | null;
  dauer_s: number;
  n: number;
  n_collision: number;
  n_ok: number;
  n_unreachable: number;
  n_warn: number;
  zweig_wechsel_in_ringen: number;
}
