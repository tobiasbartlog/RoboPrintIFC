import { useEffect, useState } from 'react';
import type { BufferGeometry } from 'three';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';

export const DEFAULT_ASSET_BASE = '/api/assets';

/** Datei relativ zur Asset-Basis, z. B. `tools/30gut.stl`. */
export function assetUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
}

/** Die URDF liefert die API (Mesh-Pfade umgeschrieben) unter `<base>/robot.urdf`. */
export function urdfUrl(base: string): string {
  return assetUrl(base, 'robot.urdf');
}

/** Basis fuer `package://dsr_description2/...`, falls die URDF nicht umgeschrieben wurde. */
export function packageBase(base: string): string {
  return assetUrl(base, 'third_party/doosan_m1013');
}

const cache = new Map<string, Promise<BufferGeometry>>();

export function loadStl(url: string): Promise<BufferGeometry> {
  let p = cache.get(url);
  if (!p) {
    p = fetch(url).then(async (res) => {
      if (!res.ok) throw new Error(`STL nicht ladbar (${res.status}): ${url}`);
      return new STLLoader().parse(await res.arrayBuffer());
    });
    p.catch(() => cache.delete(url));
    cache.set(url, p);
  }
  return p;
}

/** Geometrie einer STL-Datei; null, solange sie laedt oder wenn url fehlt. */
export function useStl(url: string | null, onError?: (e: Error) => void): BufferGeometry | null {
  const [state, setState] = useState<{ url: string; geo: BufferGeometry } | null>(null);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    loadStl(url).then(
      (geo) => alive && setState({ url, geo }),
      (e: Error) => onError?.(e),
    );
    return () => {
      alive = false;
    };
  }, [url, onError]);
  return state && state.url === url ? state.geo : null;
}
