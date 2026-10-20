import { useCallback, useEffect, useMemo, useRef } from 'react';
import { SceneView } from '../scene/SceneView';
import type { SceneApi } from '../scene/types';
import type { AppStore } from '../state/store';
import { useAppStore, useAppStoreApi } from '../state/storeContext';
import { debugSnapshot, duration, sampleAt, sceneSample, type DebugSnapshot } from './clock';

/** Test- und Diagnose-Schnittstelle (SPEC §9). */
export interface RoboprintDebug {
  /** Genau {t, sampleIndex, tcpRendered[3], tcpArtifact[3], status, highlightedLinks[], obstacleVisible}. */
  debug: () => DebugSnapshot;
  /** Setzt die Uhr (pausiert) und wartet, bis der Szenengraph die Pose des Samples traegt. */
  seek: (t: number) => Promise<DebugSnapshot>;
  /** Szene geladen, Teil geladen und der Roboter im Szenengraphen auf q des Samples zu `t`. */
  ready: () => boolean;
}

declare global {
  interface Window {
    __roboprint?: RoboprintDebug;
  }
}

/**
 * Naechste Makroaufgabe. `seek` wartet bewusst nicht auf Animationsframes: Der Szenengraph traegt
 * die Pose schon nach dem React-Commit, das Rastern folgt im naechsten Frame. Mit Software-WebGL
 * dauert ein Frame der vollen Szene ueber eine Sekunde, und requestAnimationFrame staut sich hinter
 * der GPU; das hat die Uhr-Invariante (50 Zeiten je Lauf) frueher ueber das Zeitlimit gebracht.
 */
const nextTask = () => new Promise<void>((r) => setTimeout(r, 0));
/** Obergrenze fuer `seek`, bis die Szene die Pose zeigt (ms). */
const SEEK_BUDGET_MS = 10_000;

/** Wiedergabe-Schleife: setzt `t` pro Animationsframe, solange `playing`. */
function usePlaybackLoop(store: AppStore) {
  const playing = useAppStore((s) => s.playing);
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const step = (now: number) => {
      const s = store.getState();
      const end = duration(s.playback?.trajectory ?? null);
      const t = Math.min(end, s.t + ((now - last) / 1000) * s.speed);
      last = now;
      if (t >= end) {
        store.setState({ t: end, playing: false });
        return;
      }
      store.setState({ t });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, store]);
}

/**
 * Die 3D-Szene am Store: das Sample zu `t` (binäre Suche in `t_s`) speist SceneView. Installiert
 * `window.__roboprint` und richtet die Kamera bei Auswahl eines Kollisionseintrags aus.
 */
export function PlayerScene() {
  const store = useAppStoreApi();
  const t = useAppStore((s) => s.t);
  const pb = useAppStore((s) => s.playback);
  const partId = useAppStore((s) => s.partId);
  const highlightedLinks = useAppStore((s) => s.highlightedLinks);
  const showObstacle = useAppStore((s) => s.showObstacle);
  const focus = useAppStore((s) => s.focus);
  const assetBase = useAppStore((s) => s.assetBase);
  const sceneApi = useRef<SceneApi | null>(null);

  usePlaybackLoop(store);

  const active = pb && pb.partId === partId ? pb : null;
  const index = active ? sampleAt(active.trajectory.t_s, t) : -1;
  const sample = useMemo(
    () => (active && index >= 0 ? sceneSample(active.trajectory, index, active.loaded.parts[active.partId]?.progress) : null),
    [active, index],
  );

  useEffect(() => {
    if (focus) sceneApi.current?.focusOn(focus.p);
  }, [focus]);

  const onApi = useCallback((api: SceneApi | null) => {
    sceneApi.current = api;
  }, []);

  useEffect(() => {
    const snapshot = (): DebugSnapshot => {
      const s = store.getState();
      const tr = s.playback && s.playback.partId === s.partId ? s.playback.trajectory : null;
      return debugSnapshot({
        t: s.t,
        trajectory: tr,
        tcpRendered: sceneApi.current?.tcpRendered() ?? null,
        highlightedLinks: s.highlightedLinks,
        showObstacle: s.showObstacle,
      });
    };
    // Bereit heißt: Szene geladen und der Roboter zeigt genau q des Samples zu t. Die Szene
    // rendert in einem eigenen React-Root; deshalb wird die gezeigte Pose verglichen.
    const ready = () => {
      const s = store.getState();
      const api = sceneApi.current;
      const tr = s.playback && s.playback.partId === s.partId ? s.playback.trajectory : null;
      if (!api?.ready() || !tr) return false;
      const q = tr.q[sampleAt(tr.t_s, s.t)];
      const shown = api.jointValues();
      return !!q && !!shown && q.every((v, k) => Math.abs(v - (shown[k] ?? Number.NaN)) < 1e-9);
    };
    window.__roboprint = {
      debug: snapshot,
      ready,
      seek: async (tq: number) => {
        store.setState({ t: tq, playing: false });
        const deadline = performance.now() + SEEK_BUDGET_MS;
        while (!ready() && performance.now() < deadline) await nextTask();
        return snapshot();
      },
    };
    return () => {
      delete window.__roboprint;
    };
  }, [store]);

  return (
    <SceneView
      run={active ? active.loaded : null}
      partId={active ? active.partId : null}
      sample={sample}
      highlightedLinks={highlightedLinks}
      obstacleVisible={showObstacle}
      assetBase={assetBase}
      showToolpath
      onApi={onApi}
    />
  );
}
