/* eslint-disable */
/**
 * GENERIERT aus schemas/PatternPreviewRequest.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

/**
 * Body von `POST /api/patterns/preview`.
 *
 * `pattern`: registrierter Mustername oder `schalen`/`none`; ist es keins von beiden, gilt es als
 * Preset-id. `preset`: Preset-id als Grundlage (Muster, Parameter, Querschnitt); `pattern`,
 * `params` und `outline` überschreiben es. `params` ist flach: Kern- und Musterparameter
 * nebeneinander. Ohne `outline` gilt das Preset-`outline`, sonst 600 × 200 mm.
 */
export interface PatternPreviewRequest {
  layer: number;
  outline: PatternOutlineBox | PatternOutlinePolygon | null;
  params: {
    [k: string]: boolean | number | string | number[] | null;
  };
  pattern: string | null;
  preset: string | null;
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
