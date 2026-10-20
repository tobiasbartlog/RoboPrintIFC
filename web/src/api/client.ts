/**
 * Typisierter API-Client (SPEC §8). Basis `/api`; Typen kommen aus `../contracts`.
 * run_id ist der relative Pfad des Laufordners (z. B. `verify/S1`, `run_demo`).
 */
import type {
  Example,
  Health,
  JobCreate,
  JobCreated,
  JobState,
  PartArtifact,
  PartPatternLayer,
  PartPatternReport,
  ProjectCreated,
  ProjectInfo,
  Scene,
  Summary,
  Toolpath,
  Trajectory,
} from '../contracts';

export const API_BASE = '/api';

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function failure(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') detail = body.detail;
  } catch {
    /* Antwort ohne JSON */
  }
  return new ApiError(res.status, detail || `HTTP ${res.status}`);
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(path.startsWith(API_BASE) ? path : `${API_BASE}${path}`, init);
  if (!res.ok) throw await failure(res);
  return res;
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json() as Promise<T>;
}

function sendJson<T>(method: string, path: string, body: unknown): Promise<T> {
  return getJson<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/** Pfadsegmente einzeln kodieren, `/` bleibt Trenner. */
function encodePath(path: string): string {
  return path
    .split('/')
    .filter((s) => s.length > 0)
    .map(encodeURIComponent)
    .join('/');
}

export const getHealth = (): Promise<Health> => getJson('/health');
export const listExamples = (): Promise<Example[]> => getJson('/examples');
export const listRuns = (): Promise<string[]> => getJson('/runs');

export const createProjectFromExample = (examplePath: string): Promise<ProjectCreated> =>
  sendJson('POST', '/projects', { example_path: examplePath });

export function uploadProject(file: File | Blob, name?: string): Promise<ProjectCreated> {
  const form = new FormData();
  form.append('file', file, name ?? (file instanceof File ? file.name : 'upload.ifc'));
  return getJson('/projects', { method: 'POST', body: form });
}

export const getProject = (id: string): Promise<ProjectInfo> =>
  getJson(`/projects/${encodeURIComponent(id)}`);

export const createJob = (projectId: string, job: JobCreate): Promise<JobCreated> =>
  sendJson('POST', `/projects/${encodeURIComponent(projectId)}/jobs`, job);

export const getJob = (jobId: string): Promise<JobState> =>
  getJson(`/jobs/${encodeURIComponent(jobId)}`);

export const cancelJob = (jobId: string): Promise<JobState> =>
  getJson(`/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' });

const TERMINAL: ReadonlySet<JobState['state']> = new Set(['done', 'failed', 'cancelled']);
export const isTerminal = (s: JobState): boolean => TERMINAL.has(s.state);

export interface PollOptions {
  intervalMs?: number;
  signal?: AbortSignal;
  onUpdate?: (state: JobState) => void;
}

/** Fragt den Job ab, bis er `done`, `failed` oder `cancelled` ist; liefert den Endstand. */
export async function pollJob(jobId: string, opts: PollOptions = {}): Promise<JobState> {
  const interval = opts.intervalMs ?? 500;
  for (;;) {
    if (opts.signal?.aborted) throw new DOMException('Abgebrochen', 'AbortError');
    const state = await getJob(jobId);
    opts.onUpdate?.(state);
    if (isTerminal(state)) return state;
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, interval);
      opts.signal?.addEventListener(
        'abort',
        () => {
          clearTimeout(timer);
          reject(new DOMException('Abgebrochen', 'AbortError'));
        },
        { once: true },
      );
    });
  }
}

// ---------------------------------------------------------------------- Laufartefakte

export const runUrl = (runId: string, path: string): string =>
  `${API_BASE}/runs/${encodePath(runId)}/${encodePath(path)}`;
export const assetUrl = (path: string): string => `${API_BASE}/assets/${encodePath(path)}`;
/** URDF mit aufgelösten Mesh-Pfaden für urdf-loader. */
export const robotUrdfUrl = (): string => `${API_BASE}/assets/robot.urdf`;

export const partStlUrl = (runId: string, partId: string): string =>
  runUrl(runId, `parts/${partId}/part.stl`);

const partPath = (partId: string, file: string): string => `parts/${partId}/${file}`;

export const loadSummary = (runId: string): Promise<Summary> =>
  getJson(runUrl(runId, 'summary.json'));
export const loadScene = (runId: string): Promise<Scene> =>
  getJson(runUrl(runId, 'scene.json'));
export const loadPart = (runId: string, partId: string): Promise<PartArtifact> =>
  getJson(runUrl(runId, partPath(partId, 'part.json')));
export const loadToolpath = (runId: string, partId: string): Promise<Toolpath> =>
  getJson(runUrl(runId, partPath(partId, 'toolpath.json')));
export const loadTrajectory = (runId: string, partId: string): Promise<Trajectory> =>
  getJson(runUrl(runId, partPath(partId, 'trajectory.json')));

const reportQuery = (runId: string, partId: string): string =>
  `run_id=${encodeURIComponent(runId)}&part_id=${encodeURIComponent(partId)}`;
/** Kennzahlen des Druckmusters eines Teils (gerechnet im Kern aus `toolpath.json`). */
export const loadPatternReport = (runId: string, partId: string): Promise<PartPatternReport> =>
  getJson(`/pattern-report/metrics?${reportQuery(runId, partId)}`);
/** Eine Schicht des Teils im Teil-Frame P samt Nachbarschicht. */
export const loadPatternLayer = (runId: string, partId: string, layer: number): Promise<PartPatternLayer> =>
  getJson(`/pattern-report/layer?${reportQuery(runId, partId)}&layer=${layer}`);

export async function loadDrl(
  runId: string,
  partId: string,
  dialect: 'v2' | 'v3' = 'v2',
): Promise<string> {
  const res = await request(runUrl(runId, partPath(partId, `program.${dialect}.drl`)));
  return res.text();
}

/** Pfade aus `scene.json` (repo-relativ, z. B. `tools/30gut.stl`) als Asset-URL. */
export const sceneAssetUrl = (repoRelativePath: string): string => assetUrl(repoRelativePath);
