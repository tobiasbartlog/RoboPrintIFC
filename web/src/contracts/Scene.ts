/* eslint-disable */
/**
 * GENERIERT aus schemas/Scene.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface Scene {
  params: SceneParams;
  robot: SceneRobot;
  schema_version: "2";
  tool: SceneTool;
  workstation: SceneWorkstation;
}
export interface SceneParams {
  d_hard_mm: number;
  d_target_mm: number;
  d_target_printed_mm: number;
  layer_height_mm: number;
  r_free_mm: number;
}
export interface SceneRobot {
  urdf: string;
}
export interface SceneTool {
  /**
   * @minItems 4
   * @maxItems 4
   */
  T_FT: [
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number]
  ];
  mesh: string;
  /**
   * @minItems 4
   * @maxItems 4
   */
  mesh_transform: [
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number]
  ];
}
export interface SceneWorkstation {
  /**
   * @minItems 4
   * @maxItems 4
   */
  T_WB: [
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number]
  ];
  /**
   * @minItems 4
   * @maxItems 4
   */
  T_WS: [
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number],
    [number, number, number, number]
  ];
  mesh: string;
}
