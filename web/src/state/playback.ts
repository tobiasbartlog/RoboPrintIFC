/**
 * Wiedergabe-Slice: geladenes Teil (Szene, Teil, Bahn, Trajektorie), Abspielzustand und
 * Hervorhebung. Die Zeit selbst ist `t` im Store (eine Uhr); hier wird sie nur gesetzt.
 */
import type { PartArtifact, Scene, Toolpath, Trajectory } from '../contracts';
import { duration, type CollisionRange } from '../player/clock';
import type { LoadedRun } from '../scene/types';
import type { ApiPort } from './apiPort';

export interface PlaybackData {
  runId: string;
  partId: string;
  trajectory: Trajectory;
  /** Eingabe für SceneView (scene.json plus genau dieses Teil). */
  loaded: LoadedRun;
}

export interface PlaybackSlice {
  playback: PlaybackData | null;
  playbackLoading: boolean;
  playbackError: string | null;
  playbackErrorDetail: string | null;
  playing: boolean;
  /** Abspielgeschwindigkeit (Faktor auf Echtzeit). */
  speed: number;
  /** Glieder, die nach Auswahl eines Kollisionseintrags hervorgehoben sind. */
  highlightedLinks: string[];
  /** Hindernis bei Warnung oder Kollision einblenden. */
  showObstacle: boolean;
  /** Kamera-Ziel (W, mm); `seq` zählt Anfragen, damit gleiche Punkte erneut greifen. */
  focus: { p: [number, number, number]; seq: number } | null;
  /** Basis der Asset-URLs (URDF, Tisch, Werkzeug). */
  assetBase: string;
  loadPlayback: (runId: string, partId: string) => Promise<void>;
  play: () => void;
  pause: () => void;
  setSpeed: (v: number) => void;
  /** Vom Nutzer gesetzte Zeit (Scrubber, Sprungknöpfe): pausiert nicht, löscht die Hervorhebung. */
  scrub: (t: number) => void;
  /** Klick auf einen Eintrag der Kollisionsliste: pausiert beim kritischsten Sample. */
  selectCollision: (c: CollisionRange) => void;
}

interface Base {
  t: number;
  run: { runId: string } | null;
  partId: string | null;
}

type State = PlaybackSlice & Base;
type Writable = Partial<PlaybackSlice & { t: number }>;
type SetFn = (partial: Writable | ((s: State) => Writable)) => void;

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function createPlaybackSlice(set: SetFn, get: () => State, api: ApiPort): PlaybackSlice {
  let token = 0;
  const sceneCache = new Map<string, Promise<Scene>>();
  const json = async <T>(runId: string, path: string): Promise<T> => JSON.parse(await api.loadRun(runId, path)) as T;

  return {
    playback: null,
    playbackLoading: false,
    playbackError: null,
    playbackErrorDetail: null,
    playing: false,
    speed: 1,
    highlightedLinks: [],
    showObstacle: true,
    focus: null,
    assetBase: api.assetBase,

    loadPlayback: async (runId, partId) => {
      const my = ++token;
      set({ playbackLoading: true, playbackError: null, playbackErrorDetail: null, playing: false, highlightedLinks: [] });
      try {
        let scene = sceneCache.get(runId);
        if (!scene) {
          scene = json<Scene>(runId, 'scene.json');
          sceneCache.set(runId, scene);
          scene.catch(() => sceneCache.delete(runId));
        }
        const base = `parts/${partId}`;
        const [sc, part, toolpath, trajectory] = await Promise.all([
          scene,
          json<PartArtifact>(runId, `${base}/part.json`),
          json<Toolpath>(runId, `${base}/toolpath.json`).catch(() => null),
          json<Trajectory>(runId, `${base}/trajectory.json`),
        ]);
        if (my !== token) return;
        const loaded: LoadedRun = {
          scene: sc,
          parts: { [partId]: { part, toolpath, stlUrl: api.runFileUrl(runId, `${base}/part.stl`) } },
        };
        set({ playback: { runId, partId, trajectory, loaded }, playbackLoading: false });
      } catch (e) {
        if (my !== token) return;
        set({
          playback: null,
          playbackLoading: false,
          playbackError: `Die Wiedergabe für ${partId} konnte nicht geladen werden. Teil erneut wählen oder neu rechnen.`,
          playbackErrorDetail: errText(e),
        });
      }
    },

    play: () => {
      const s = get();
      const end = duration(s.playback?.trajectory ?? null);
      if (end <= 0) return;
      // Am Ende startet Abspielen von vorn.
      set({ playing: true, highlightedLinks: [], ...(s.t >= end ? { t: 0 } : {}) });
    },
    pause: () => set({ playing: false }),
    setSpeed: (speed) => set({ speed }),
    scrub: (t) => {
      const end = duration(get().playback?.trajectory ?? null);
      set({ t: Math.min(Math.max(t, 0), end), highlightedLinks: [] });
    },
    selectCollision: (c) => {
      set((s) => ({
        playing: false,
        t: c.tMin,
        highlightedLinks: c.link === 'unbekannt' ? [] : [c.link],
        showObstacle: true,
        focus: c.focus ? { p: c.focus, seq: (s.focus?.seq ?? 0) + 1 } : s.focus,
      }));
    },
  };
}
