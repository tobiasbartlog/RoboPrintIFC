/**
 * Schmale Schnittstelle der Shell zum Backend. Der Orchestrator verdrahtet sie beim Merge mit
 * dem echten Client (`src/api/client.ts`); Tests und Fixture-Betrieb nutzen `fakeApi.ts`.
 */
import type { Example, JobCreate, JobState, ProjectInfo } from '../contracts';

export type ProjectSource = { examplePath: string } | { file: File };

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
  /** URL des Wandmeshes (STL, Frame L, mm) einer Wand des Projekts. */
  wallMeshUrl(projectId: string, wallId: string): string;
  /** Basis-URL der Assets (URDF, Tisch- und Werkzeug-STL), z. B. `/api/assets`. */
  readonly assetBase: string;
}
