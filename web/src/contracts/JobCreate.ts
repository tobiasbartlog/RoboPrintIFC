/* eslint-disable */
/**
 * GENERIERT aus schemas/JobCreate.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface JobCreate {
  params: {
    [k: string]:
      | number
      | string
      | boolean
      | {
          [k: string]: number | string | boolean | number[];
        };
  };
  planner_mode: "collision_aware" | "ignore_collision";
  wall_id: string;
}
