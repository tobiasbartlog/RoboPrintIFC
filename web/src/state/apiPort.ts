/**
 * Schmale Schnittstelle der Shell zum Backend. Der Orchestrator verdrahtet sie beim Merge mit
 * dem echten Client (`src/api/client.ts`); Tests und Fixture-Betrieb nutzen `fakeApi.ts`.
 */
import type { Example, JobCreate, JobState, PartPatternLayer, PartPatternReport, ProjectInfo } from '../contracts';

export type ProjectSource = { examplePath: string } | { file: File };
export type WallFrame = 'L' | 'building';

export interface ApiPort {
  listExamples(): Promise<Example[]>;
  /** Legt das Projekt an und liefert direkt die Wandliste (POST /projects + GET /projects/{id}). */
  createProject(source: ProjectSource): Promise<ProjectInfo>;
  getProject(projectId: string): Promise<ProjectInfo>;
  startJob(projectId: string, request: JobCreate): Promise<string>;
  getJob(jobId: string): Promise<JobState>;
  cancelJob(jobId: string): Promise<void>;
  /** Lädt ein Artefakt des Laufs als Text (JSON, DRL), z. B. `summary.json` oder `parts/P01/program.v2.drl`. */
  loadRun(runId: string, path: string): Promise<string>;
  /** URL einer Laufdatei für Lader, die selbst holen (z. B. `parts/P01/part.stl`). */
  runFileUrl(runId: string, path: string): string;
  /**
   * URL des Wandmeshes (STL, mm) einer Wand des Projekts: `L` im Wand-Frame, `building` in
   * Gebäudelage relativ zum Ursprung der Hausansicht (nur wenn `building_mm` gesetzt ist).
   */
  wallMeshUrl(projectId: string, wallId: string, frame?: WallFrame): string;
  /** URL der übrigen Bauteile (Decken, Dach, ...) für die Hausansicht (STL, mm). */
  contextMeshUrl(projectId: string): string;
  /** Kennzahlen des Druckmusters eines Teils (die API rechnet sie aus `toolpath.json`). */
  patternReport(runId: string, partId: string): Promise<PartPatternReport>;
  /** Eine Schicht des Teils im Frame P samt Nachbarschicht (2D-Vorschau). */
  patternLayer(runId: string, partId: string, layer: number): Promise<PartPatternLayer>;
  /** Basis-URL der Assets (URDF, Tisch- und Werkzeug-STL), z. B. `/api/assets`. */
  readonly assetBase: string;
}
