/**
 * Auswahl der Backend-Anbindung.
 * Fake-Betrieb: Query `?fake=1` (Fixture unverändert, Teil nicht machbar), `?fake=ok` (alle Teile
 * machbar) oder Umgebungsvariable `VITE_API_MODE=fake`. Ohne das wird `realApi` genutzt, die der
 * Orchestrator beim Merge mit `src/api/client.ts` verdrahtet.
 */
import type { ApiPort } from './apiPort';
import { createFakeApi } from './fakeApi';

let realApi: ApiPort | null = null;

/** Wird beim Merge mit dem echten Client aufgerufen (z. B. in main.tsx). */
export function registerRealApi(api: ApiPort): void {
  realApi = api;
}

function unavailable(): ApiPort {
  const fail = async (): Promise<never> => {
    throw new Error('Der Server ist nicht angebunden (kein echter API-Client registriert).');
  };
  return {
    listExamples: fail,
    createProject: fail,
    getProject: fail,
    startJob: fail,
    getJob: fail,
    cancelJob: fail,
    loadRun: fail,
    runFileUrl: (runId, path) => `/api/runs/${runId}/${path}`,
    wallMeshUrl: (projectId, wallId, frame = 'L') =>
      `/api/projects/${projectId}/walls/${encodeURIComponent(wallId)}.stl${frame === 'L' ? '' : `?frame=${frame}`}`,
    contextMeshUrl: (projectId) => `/api/projects/${projectId}/context.stl`,
    assetBase: '/api/assets',
  };
}

export function selectApi(search: string = window.location.search, env: string | undefined = import.meta.env.VITE_API_MODE): ApiPort {
  const q = new URLSearchParams(search).get('fake');
  if (q === 'ok') return createFakeApi({ mode: 'ok', latencyMs: 50 });
  if (q !== null || env === 'fake') return createFakeApi({ mode: 'fixture', latencyMs: 50 });
  return realApi ?? unavailable();
}
