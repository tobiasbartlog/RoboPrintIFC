/**
 * Zustand-Store der App. Die Slices (step, project, wall, params, job, run, selection, t) sind
 * absichtlich in einem Objekt, damit A3.3 (Szene) und A3.4 (Player) sie erweitern können, ohne
 * die Shell umzubauen. `t` ist die einzige Zeitquelle (Sekunden).
 */
import { createStore, type StoreApi } from 'zustand/vanilla';
import type { Example, JobState, PartArtifact, ProjectInfo, Summary, TrajectorySummary } from '../contracts';
import type { ApiPort } from './apiPort';
import { createPlaybackSlice, type PlaybackSlice } from './playback';
import { DEFAULT_PARAMS, type ParamValue, type ParamValues } from './params';
import { makeBasis, stepBlockedReason, stepStatuses, type RunBasis, type StepId, type StepInputs, type StepStatus } from './stepper';

export interface RunData {
  runId: string;
  basis: RunBasis;
  summary: Summary;
  parts: Record<string, PartArtifact>;
  /** Kennzahlen je Teil aus trajectory.json (nur die Zusammenfassung wird gehalten). */
  trajectory: Record<string, TrajectorySummary>;
}

export interface JobSlice {
  jobId: string | null;
  state: JobState | null;
  error: string | null;
  errorDetail: string | null;
}

export interface AppState extends PlaybackSlice {
  // step
  step: StepId;
  setStep: (s: StepId) => void;
  // project
  examples: Example[];
  projectBusy: boolean;
  projectError: string | null;
  projectErrorDetail: string | null;
  project: ProjectInfo | null;
  loadExamples: () => Promise<void>;
  openExample: (path: string) => Promise<void>;
  openFile: (file: File) => Promise<void>;
  // wall
  wallId: string | null;
  selectWall: (id: string) => void;
  // params
  params: ParamValues;
  setParam: (key: string, value: ParamValue) => void;
  resetParam: (key: string) => void;
  resetParams: () => void;
  // job
  job: JobSlice;
  startJob: () => Promise<void>;
  cancelJob: () => Promise<void>;
  // run
  run: RunData | null;
  /** Lädt eine Datei des aktuellen Laufs als Text (DRL-Export). */
  loadRunFile: (path: string) => Promise<string>;
  /**
   * Direkteinstieg (`/?run=<run_id>&part=<part_id>`): vorhandenen Lauf ohne Projekt und Job öffnen
   * und in die Simulation springen. Ohne `partId` gilt das erste Teil.
   */
  openRun: (runId: string, partId?: string | null) => Promise<void>;
  runError: string | null;
  runErrorDetail: string | null;
  // selection
  partId: string | null;
  selectPart: (id: string | null) => void;
  // Uhr: einzige Zeitquelle (s)
  t: number;
  setT: (t: number) => void;
}

export interface StoreOptions {
  pollMs?: number;
}

const EMPTY_JOB: JobSlice = { jobId: null, state: null, error: null, errorDetail: null };

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export type AppStore = StoreApi<AppState>;

export function createAppStore(api: ApiPort, opts: StoreOptions = {}): AppStore {
  const pollMs = opts.pollMs ?? 400;
  let jobToken = 0;

  return createStore<AppState>()((set, get) => {
    const playback = createPlaybackSlice(set, get, api);
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

    async function openProject(load: () => Promise<ProjectInfo>) {
      set({ projectBusy: true, projectError: null, projectErrorDetail: null });
      try {
        const project = await load();
        jobToken++;
        set({
          project,
          projectBusy: false,
          wallId: null,
          run: null,
          partId: null,
          t: 0,
          job: EMPTY_JOB,
          playback: null,
          playing: false,
          highlightedLinks: [],
        });
      } catch (e) {
        set({
          projectBusy: false,
          projectError: 'Das Modell konnte nicht geöffnet werden. Anderes Beispiel oder eine andere IFC-Datei versuchen.',
          projectErrorDetail: errText(e),
        });
      }
    }

    async function loadRunData(runId: string, basis: RunBasis): Promise<RunData> {
      const summary = JSON.parse(await api.loadRun(runId, 'summary.json')) as Summary;
      const parts: Record<string, PartArtifact> = {};
      const trajectory: Record<string, TrajectorySummary> = {};
      for (const p of summary.parts) {
        parts[p.part_id] = JSON.parse(await api.loadRun(runId, `parts/${p.part_id}/part.json`)) as PartArtifact;
        const tr = JSON.parse(await api.loadRun(runId, `parts/${p.part_id}/trajectory.json`)) as { summary: TrajectorySummary };
        trajectory[p.part_id] = tr.summary;
      }
      return { runId, basis, summary, parts, trajectory };
    }

    return {
      step: 'model',
      setStep: (step) => set({ step }),

      examples: [],
      projectBusy: false,
      projectError: null,
      projectErrorDetail: null,
      project: null,
      loadExamples: async () => {
        try {
          set({ examples: await api.listExamples() });
        } catch (e) {
          set({
            projectError: 'Die Beispielliste konnte nicht geladen werden. Läuft der Server?',
            projectErrorDetail: errText(e),
          });
        }
      },
      openExample: (path) => openProject(async () => api.createProject({ examplePath: path })),
      openFile: (file) => openProject(async () => api.createProject({ file })),

      wallId: null,
      selectWall: (wallId) => set({ wallId }),

      params: { ...DEFAULT_PARAMS },
      setParam: (key, value) => set((s) => ({ params: { ...s.params, [key]: value } })),
      resetParam: (key) => set((s) => ({ params: { ...s.params, [key]: DEFAULT_PARAMS[key] as ParamValue } })),
      resetParams: () => set({ params: { ...DEFAULT_PARAMS } }),

      job: EMPTY_JOB,
      startJob: async () => {
        const { project, wallId, params, job } = get();
        if (!project || !wallId) return;
        if (job.state && (job.state.state === 'queued' || job.state.state === 'running')) return;
        const token = ++jobToken;
        const basis = makeBasis(project.project_id, wallId, params);
        set({ job: { ...EMPTY_JOB, state: { state: 'queued', progress: 0, stage: null, message: null, run_id: null } } });
        try {
          const jobId = await api.startJob(project.project_id, { wall_id: wallId, params, planner_mode: 'collision_aware' });
          if (token !== jobToken) return;
          set((s) => ({ job: { ...s.job, jobId } }));
          for (;;) {
            await sleep(pollMs);
            if (token !== jobToken) return;
            const st = await api.getJob(jobId);
            if (token !== jobToken) return;
            set((s) => ({ job: { ...s.job, state: st } }));
            if (st.state === 'done' && st.run_id) {
              const run = await loadRunData(st.run_id, basis);
              if (token !== jobToken) return;
              const first = run.summary.parts[0]?.part_id ?? null;
              set({ run, partId: first, t: 0, playback: null });
              if (first) void get().loadPlayback(run.runId, first);
              return;
            }
            if (st.state === 'failed') {
              set((s) => ({
                job: {
                  ...s.job,
                  error: 'Die Rechnung ist fehlgeschlagen. Wand oder Parameter ändern und erneut starten.',
                  errorDetail: st.message,
                },
              }));
              return;
            }
            if (st.state === 'cancelled') return;
          }
        } catch (e) {
          if (token !== jobToken) return;
          set((s) => ({
            job: {
              ...s.job,
              state: null,
              error: 'Die Rechnung konnte nicht gestartet oder verfolgt werden. Verbindung prüfen und erneut versuchen.',
              errorDetail: errText(e),
            },
          }));
        }
      },
      cancelJob: async () => {
        const { job } = get();
        if (!job.jobId) return;
        try {
          await api.cancelJob(job.jobId);
        } catch (e) {
          set((s) => ({ job: { ...s.job, error: 'Abbrechen hat nicht geklappt.', errorDetail: errText(e) } }));
        }
      },

      run: null,
      loadRunFile: async (path) => {
        const run = get().run;
        if (!run) throw new Error('Kein Lauf vorhanden');
        return api.loadRun(run.runId, path);
      },

      openRun: async (runId, partId) => {
        jobToken++;
        set({ runError: null, runErrorDetail: null });
        try {
          const run = await loadRunData(runId, { projectId: '', wallId: '', paramsKey: '', direct: true });
          const ids = run.summary.parts.map((p) => p.part_id);
          const chosen = partId && ids.includes(partId) ? partId : (ids[0] ?? null);
          set({ run, partId: chosen, t: 0, playback: null, step: 'simulation', job: EMPTY_JOB });
          if (chosen) await get().loadPlayback(runId, chosen);
        } catch (e) {
          set({
            runError: `Der Lauf „${runId}“ konnte nicht geöffnet werden. Adresse prüfen oder ein Modell öffnen und neu rechnen.`,
            runErrorDetail: errText(e),
          });
        }
      },
      runError: null,
      runErrorDetail: null,

      partId: null,
      selectPart: (partId) => {
        set({ partId, t: 0, playing: false });
        const run = get().run;
        if (run && partId) void get().loadPlayback(run.runId, partId);
      },

      t: 0,
      setT: (t) => set({ t }),

      ...playback,
    };
  });
}

/** Eingaben der reinen Stepper-Logik aus dem Store-Zustand. */
export function stepInputs(s: AppState): StepInputs {
  return {
    projectId: s.project?.project_id ?? null,
    wallId: s.wallId,
    params: s.params,
    runBasis: s.run?.basis ?? null,
  };
}

export function selectStatuses(s: AppState): Record<StepId, StepStatus> {
  return stepStatuses(stepInputs(s));
}

export function selectBlocked(s: AppState, step: StepId): string | null {
  return stepBlockedReason(step, stepInputs(s));
}

export function isJobRunning(s: AppState): boolean {
  const st = s.job.state?.state;
  return st === 'queued' || st === 'running';
}
