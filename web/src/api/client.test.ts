import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  cancelJob,
  createJob,
  createProjectFromExample,
  getHealth,
  loadDrl,
  loadTrajectory,
  partStlUrl,
  pollJob,
  robotUrdfUrl,
  runUrl,
  uploadProject,
} from './client';
import type { JobState } from '../contracts';

const fetchMock = vi.fn();
const call = (i: number): [string, RequestInit | undefined] =>
  fetchMock.mock.calls[i] as [string, RequestInit | undefined];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const job = (state: JobState['state'], progress = 0): JobState => ({
  state,
  progress,
  stage: null,
  message: null,
  run_id: state === 'done' ? 'jobs/j1/run' : null,
});

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe('api client', () => {
  it('liest health', async () => {
    fetchMock.mockResolvedValue(json({ status: 'ok', version: '1', versions: {} }));
    expect((await getHealth()).status).toBe('ok');
    expect(fetchMock).toHaveBeenCalledWith('/api/health', undefined);
  });

  it('legt Projekt aus Beispiel an (JSON-POST)', async () => {
    fetchMock.mockResolvedValue(json({ project_id: 'p1' }));
    const r = await createProjectFromExample('examples/a.ifc');
    expect(r.project_id).toBe('p1');
    const [url, init] = call(0);
    expect(url).toBe('/api/projects');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ example_path: 'examples/a.ifc' });
  });

  it('lädt IFC als multipart hoch', async () => {
    fetchMock.mockResolvedValue(json({ project_id: 'p2' }));
    await uploadProject(new Blob(['x']), 'm.ifc');
    const init = call(0)[1];
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get('file')).toBeInstanceOf(Blob);
  });

  it('legt Job an und bricht ab', async () => {
    fetchMock.mockResolvedValueOnce(json({ job_id: 'j1' }, 202));
    expect((await createJob('p1', { wall_id: 'W1', params: {}, planner_mode: 'collision_aware' })).job_id).toBe('j1');
    expect(call(0)[0]).toBe('/api/projects/p1/jobs');
    fetchMock.mockResolvedValueOnce(json(job('cancelled')));
    expect((await cancelJob('j1')).state).toBe('cancelled');
    expect(call(1)[1]?.method).toBe('DELETE');
  });

  it('wirft ApiError mit Detail', async () => {
    fetchMock.mockResolvedValue(json({ detail: 'IFC-Import ist noch nicht implementiert' }, 501));
    await expect(createProjectFromExample('x')).rejects.toMatchObject({
      name: 'ApiError',
      status: 501,
      message: 'IFC-Import ist noch nicht implementiert',
    });
    fetchMock.mockResolvedValue(new Response('boom', { status: 500, statusText: 'Server Error' }));
    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
  });

  it('pollt bis zum Endzustand und meldet Updates', async () => {
    fetchMock
      .mockResolvedValueOnce(json(job('queued')))
      .mockResolvedValueOnce(json(job('running', 0.5)))
      .mockResolvedValueOnce(json(job('done', 1)));
    const seen: number[] = [];
    const end = await pollJob('j1', { intervalMs: 1, onUpdate: (s) => seen.push(s.progress) });
    expect(end.state).toBe('done');
    expect(end.run_id).toBe('jobs/j1/run');
    expect(seen).toEqual([0, 0.5, 1]);
  });

  it('pollJob bricht per AbortSignal ab', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json(job('running', 0.1))));
    const ac = new AbortController();
    const p = pollJob('j1', { intervalMs: 1000, signal: ac.signal });
    setTimeout(() => ac.abort(), 5);
    await expect(p).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('baut URLs für Laufartefakte (run_id mit Schrägstrichen)', () => {
    expect(runUrl('verify/S1', 'parts/P01/part.stl')).toBe('/api/runs/verify/S1/parts/P01/part.stl');
    expect(partStlUrl('run_demo', 'P01')).toBe('/api/runs/run_demo/parts/P01/part.stl');
    expect(robotUrdfUrl()).toBe('/api/assets/robot.urdf');
  });

  it('lädt Trajektorie und DRL-Text', async () => {
    fetchMock.mockResolvedValueOnce(json({ t_s: [0, 1] }));
    const traj = await loadTrajectory('verify/S1', 'P01');
    expect(traj.t_s).toEqual([0, 1]);
    expect(call(0)[0]).toBe('/api/runs/verify/S1/parts/P01/trajectory.json');
    fetchMock.mockResolvedValueOnce(new Response('movej(...)'));
    expect(await loadDrl('run_demo', 'P01', 'v3')).toBe('movej(...)');
    expect(call(1)[0]).toBe('/api/runs/run_demo/parts/P01/program.v3.drl');
  });
});
