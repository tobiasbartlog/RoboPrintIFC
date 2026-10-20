/* eslint-disable */
/**
 * GENERIERT aus schemas/ProjectInfo.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface ProjectInfo {
  /**
   * Ausdehnung (x, y, z) der Hausansicht in mm; None ohne IFC-Gebäude (Quader-Beispiel)
   */
  building_mm: number[] | null;
  name: string;
  project_id: string;
  walls: WallEntry[];
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
