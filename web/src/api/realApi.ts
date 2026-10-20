/** Adapter: verbindet die Shell-Schnittstelle `ApiPort` mit dem typisierten Client. */
import type { ApiPort } from '../state/apiPort';
import * as client from './client';

export const realApi: ApiPort = {
  listExamples: () => client.listExamples(),
  async createProject(source) {
    const created =
      'file' in source
        ? await client.uploadProject(source.file)
        : await client.createProjectFromExample(source.examplePath);
    return client.getProject(created.project_id);
  },
  getProject: (projectId) => client.getProject(projectId),
  startJob: async (projectId, request) => (await client.createJob(projectId, request)).job_id,
  getJob: (jobId) => client.getJob(jobId),
  cancelJob: async (jobId) => {
    await client.cancelJob(jobId);
  },
  async loadRun(runId, path) {
    const res = await fetch(client.runUrl(runId, path));
    if (!res.ok) throw new client.ApiError(res.status, `Artefakt ${path} nicht ladbar (HTTP ${res.status})`);
    return res.text();
  },
  runFileUrl: (runId, path) => client.runUrl(runId, path),
  wallMeshUrl: (projectId, wallId, frame = 'L') =>
    `${client.API_BASE}/projects/${encodeURIComponent(projectId)}/walls/${encodeURIComponent(wallId)}.stl${frame === 'L' ? '' : `?frame=${frame}`}`,
  contextMeshUrl: (projectId) => `${client.API_BASE}/projects/${encodeURIComponent(projectId)}/context.stl`,
  assetBase: `${client.API_BASE}/assets`,
};
