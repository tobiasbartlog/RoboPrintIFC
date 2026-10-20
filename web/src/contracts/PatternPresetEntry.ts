/* eslint-disable */
/**
 * GENERIERT aus schemas/PatternPresetEntry.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface PatternPresetEntry {
  id: string;
  preset: PatternPreset;
  source: "builtin" | "user";
}
/**
 * Benanntes Muster (Preset-Datei, Schema siehe `roboprint.patterns.preview`).
 */
export interface PatternPreset {
  description: string;
  name: string;
  outline: PatternOutlineBox | PatternOutlinePolygon | null;
  params: {
    [k: string]: boolean | number | string | number[] | null;
  };
  pattern: string;
  schema_version: number;
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
