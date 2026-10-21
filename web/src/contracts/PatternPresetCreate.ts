/* eslint-disable */
/**
 * GENERIERT aus schemas/PatternPresetCreate.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

/**
 * Body von `POST /api/patterns/presets`. Ohne `id` wird sie aus dem Namen gebildet. Eine
 * eigene Vorlage mit derselben id wird überschrieben, eine mitgelieferte nie (409).
 */
export interface PatternPresetCreate {
  description: string;
  id: string | null;
  name: string;
  outline: PatternOutlineBox | PatternOutlinePolygon | null;
  params: {
    [k: string]: boolean | number | string | number[] | null;
  };
  pattern: string;
}
/**
 * Rechteckiger Querschnitt, Ursprung in der Mitte (x ∈ [−L/2, L/2], y ∈ [−d/2, d/2]).
 */
export interface PatternOutlineBox {
  length_mm: number;
  thickness_mm: number;
}
/**
 * Beliebiger Querschnitt als Polygon (Frame P, mm) mit optionalen Löchern.
 */
export interface PatternOutlinePolygon {
  holes: [number, number][][];
  /**
   * @minItems 3
   */
  polygon: [[number, number], [number, number], [number, number], ...[number, number][]];
}
