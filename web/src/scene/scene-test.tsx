import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { PartArtifact, Scene, Toolpath, Trajectory } from '../contracts';
import { SceneView } from './SceneView';
import type { LoadedRun, SceneApi, SceneSample } from './types';

/**
 * Testseite ohne API (nur Entwicklung): /scene-test.html?fixture=run_demo&part=P01&i=collision
 * `i` ist ein Sample-Index oder `collision`/`warn`/`unreachable` (erstes Sample mit dem Status).
 * Assets kommen aus `/dev-assets` (siehe vite-dev-assets.ts).
 */
declare global {
  interface Window {
    __scene?: SceneApi & { sampleIndex: number; sample: SceneSample | null; artifactTcp: number[] | null };
  }
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return (await res.json()) as T;
}

function App() {
  const params = new URLSearchParams(window.location.search);
  const fixture = params.get('fixture') ?? 'run_demo';
  const partId = params.get('part') ?? 'P01';
  const base = `/fixtures/${fixture}`;
  const [run, setRun] = useState<LoadedRun | null>(null);
  const [traj, setTraj] = useState<Trajectory | null>(null);
  const [api, setApi] = useState<SceneApi | null>(null);

  useEffect(() => {
    (async () => {
      const [scene, part, toolpath, trajectory] = await Promise.all([
        getJson<Scene>(`${base}/scene.json`),
        getJson<PartArtifact>(`${base}/parts/${partId}/part.json`),
        getJson<Toolpath>(`${base}/parts/${partId}/toolpath.json`),
        getJson<Trajectory>(`${base}/parts/${partId}/trajectory.json`),
      ]);
      setTraj(trajectory);
      setRun({ scene, parts: { [partId]: { part, toolpath, stlUrl: `${base}/parts/${partId}/part.stl` } } });
    })().catch((e) => console.error(e));
  }, [base, partId]);

  const sel = params.get('i') ?? '0';
  let index = Number(sel);
  if (traj && Number.isNaN(index)) index = Math.max(0, traj.status.indexOf(sel as Trajectory['status'][number]));
  let sample: SceneSample | null = null;
  if (traj && traj.q[index]) {
    sample = {
      q: traj.q[index]!,
      tcp: traj.tcp[index]!,
      layer: traj.layer[index]!,
      status: traj.status[index]!,
      pair: traj.pair[index] ?? null,
      witness: traj.witness[index] ?? null,
      d_mm: traj.d_mm[index] ?? null,
    };
  }

  useEffect(() => {
    if (!api) return;
    window.__scene = Object.assign(api, { sampleIndex: index, sample, artifactTcp: sample ? [...sample.tcp] : null });
  });

  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      <SceneView
        run={run}
        partId={partId}
        sample={sample}
        highlightedLinks={[]}
        obstacleVisible
        assetBase={params.get('assets') ?? '/dev-assets'}
        showToolpath={params.get('toolpath') !== '0'}
        onApi={setApi}
      />
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
