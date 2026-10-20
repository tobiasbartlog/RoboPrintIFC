/* eslint-disable */
/**
 * GENERIERT aus schemas/Health.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface Health {
  status: "ok";
  version: string;
  versions: {
    [k: string]: string;
  };
}
