/**
 * Fake-Implementierung von `ApiPort` gegen `web/fixtures/run_demo`. Kein Netz, keine Zufallswerte.
 * Modus `fixture`: das Fixture unverändert (Teil P01 ist dort "nicht machbar").
 * Modus `ok`: dasselbe Fixture, aber alle Teile machbar (Glückspfad).
 */
import type { Example, JobState, ProjectInfo, Summary, WallEntry } from '../contracts';
import type { ApiPort, ProjectSource } from './apiPort';

const RAW = import.meta.glob('../../fixtures/run_demo/**/*.{json,drl}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

function fixtureFile(path: string): string | undefined {
  return RAW[`../../fixtures/run_demo/${path}`];
}

export type FakeMode = 'fixture' | 'ok';

export interface FakeOptions {
  mode?: FakeMode;
  /** Anzahl getJob-Aufrufe bis "done". */
  polls?: number;
  /** Künstliche Antwortverzögerung in ms. */
  latencyMs?: number;
}

const STAGES = ['Zerlegen', 'Platzieren', 'Planen', 'Prüfen'];

export function createFakeApi(opts: FakeOptions = {}): ApiPort {
  const mode = opts.mode ?? 'fixture';
  const polls = Math.max(1, opts.polls ?? 4);
  const latency = opts.latencyMs ?? 0;
  const jobs = new Map<string, { calls: number; cancelled: boolean }>();
  let nextJob = 1;

  const wait = async () => {
    if (latency > 0) await new Promise((r) => setTimeout(r, latency));
  };

  const summary = JSON.parse(fixtureFile('summary.json') ?? '{}') as Summary;
  const thinWall: WallEntry = {
    wall_id: 'duenn',
    name: 'Wand 2 (dünn)',
    eligible: false,
    reason: 'Wand ist 24 mm dick, braucht ≥ 60 mm. Andere Wand wählen.',
    length_mm: 1800,
    thickness_mm: 24,
    height_mm: 2400,
    volume_mm3: 1800 * 24 * 2400,
    part_ids: [],
  };
  const info = (name: string): ProjectInfo => ({
    project_id: 'fake-project',
    name,
    walls: [...summary.walls, thinWall],
  });

  function patched(path: string): string {
    const raw = fixtureFile(path);
    if (raw === undefined) throw new Error(`Fixture-Datei fehlt: ${path}`);
    if (mode !== 'ok') return raw;
    if (path === 'summary.json') {
      const s = JSON.parse(raw) as Summary;
      s.parts = s.parts.map((p) => ({ ...p, status: 'machbar', d_min_mm: 62.5, n_collision: 0, n_unreachable: 0 }));
      return JSON.stringify(s);
    }
    if (/^parts\/[^/]+\/part\.json$/.test(path)) {
      return JSON.stringify({ ...(JSON.parse(raw) as object), status: 'machbar', cause: null });
    }
    if (/^parts\/[^/]+\/trajectory\.json$/.test(path)) {
      const t = JSON.parse(raw) as { summary: { n: number; d_min_mm: number | null; n_collision: number; n_unreachable: number; n_warn: number; n_ok: number } };
      t.summary = { ...t.summary, n_ok: t.summary.n, n_warn: 0, n_collision: 0, n_unreachable: 0, d_min_mm: 62.5 };
      return JSON.stringify(t);
    }
    return raw;
  }

  return {
    async listExamples(): Promise<Example[]> {
      await wait();
      return [
        { id: 'demo', name: 'Demo-Box (Fixture)', kind: 'scenario', path: 'fixture/run_demo', description: 'Kleine Box, 600 × 200 × 40 mm' },
        { id: 'building', name: 'Gebäudemodell (IFC)', kind: 'ifc', path: 'examples/Building-Architecture.ifc', description: 'Mehrere Wände, darunter ungeeignete' },
      ];
    },
    async createProject(source: ProjectSource) {
      await wait();
      return info('file' in source ? source.file.name : source.examplePath);
    },
    async getProject() {
      await wait();
      return info('Demo');
    },
    async startJob() {
      await wait();
      const id = `job-${nextJob++}`;
      jobs.set(id, { calls: 0, cancelled: false });
      return id;
    },
    async getJob(jobId: string): Promise<JobState> {
      await wait();
      const j = jobs.get(jobId);
      if (!j) throw new Error(`Unbekannter Job ${jobId}`);
      if (j.cancelled) return { state: 'cancelled', progress: j.calls / polls, stage: null, message: 'Abgebrochen', run_id: null };
      j.calls++;
      if (j.calls >= polls) return { state: 'done', progress: 1, stage: 'Prüfen', message: null, run_id: 'run_demo' };
      const progress = j.calls / polls;
      const stage = STAGES[Math.min(STAGES.length - 1, Math.floor(progress * STAGES.length))] ?? null;
      return { state: 'running', progress, stage, message: 'Teil P01', run_id: null };
    },
    async cancelJob(jobId: string) {
      await wait();
      const j = jobs.get(jobId);
      if (j) j.cancelled = true;
    },
    async loadRun(_runId: string, path: string) {
      await wait();
      if (path.endsWith('program.v3.drl')) {
        return patched(path.replace('program.v3.drl', 'program.v2.drl')).replace('Dialekt v2', 'Dialekt v3');
      }
      return patched(path);
    },
    // Binärdateien (STL) und Assets liefert der Vite-Dev-Server (Ordner fixtures/, /dev-assets).
    runFileUrl: (_runId: string, path: string) => `/fixtures/run_demo/${path}`,
    assetBase: '/dev-assets',
  };
}
