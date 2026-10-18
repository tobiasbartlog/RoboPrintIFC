/* eslint-disable */
/**
 * GENERIERT aus schemas/Scenario.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface Scenario {
  beschreibung: string;
  decompose: boolean;
  expect: {
    [k: string]: unknown;
  };
  id: string;
  limits: ScenarioLimits;
  mode: string;
  params: {
    [k: string]: number | string | boolean;
  };
  placement_override: PlacementOverride | null;
  planner_mode: "collision_aware" | "ignore_collision";
  robot: string;
  schema_version: "1";
  source: BoxSource | IfcSource;
  tool: string;
  urdf: string;
  workstation: string;
}
export interface ScenarioLimits {
  wall_time_s: number;
}
export interface PlacementOverride {
  x_mm: number;
  y_mm: number;
  yaw_deg: number;
}
export interface BoxSource {
  kind: "box";
  /**
   * @minItems 3
   * @maxItems 3
   */
  size_mm: [number, number, number];
}
export interface IfcSource {
  kind: "ifc";
  path: string;
  walls: "all" | string[];
}
