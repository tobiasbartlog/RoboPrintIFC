import { Matrix4, Plane, Quaternion, Vector3 } from 'three';
import type { Toolpath } from '../contracts';
import type { Mat4Rows, Pose7 } from './types';

/** Zeilenweise 4x4 aus dem Artefakt nach three (intern spaltenweise). */
export function mat4FromRows(m: Mat4Rows): Matrix4 {
  const r = (i: number, j: number) => m[i]?.[j] ?? 0;
  return new Matrix4().set(
    r(0, 0), r(0, 1), r(0, 2), r(0, 3),
    r(1, 0), r(1, 1), r(1, 2), r(1, 3),
    r(2, 0), r(2, 1), r(2, 2), r(2, 3),
    r(3, 0), r(3, 1), r(3, 2), r(3, 3),
  );
}

/** [x, y, z, qw, qx, qy, qz] nach Matrix4 (mm). */
export function pose7ToMatrix(p: readonly number[]): Matrix4 {
  const [x = 0, y = 0, z = 0, w = 1, qx = 0, qy = 0, qz = 0] = p;
  const q = new Quaternion(qx, qy, qz, w).normalize();
  return new Matrix4().compose(new Vector3(x, y, z), q, new Vector3(1, 1, 1));
}

/** Matrix4 nach Pose7; eine Skalierung (z. B. 1000 unter der URDF-Gruppe) wird verworfen. */
export function matrixToPose7(m: Matrix4): Pose7 {
  const p = new Vector3();
  const q = new Quaternion();
  m.decompose(p, q, new Vector3());
  return [p.x, p.y, p.z, q.w, q.x, q.y, q.z];
}

/**
 * Hoehe der Schnittebene im Frame P (mm). `layer[i]` im Artefakt ist die Anzahl k der fertigen
 * Schichten (spec/ARTEFAKTE.md), gedruckt ist also z_P <= k * h. Ohne Schicht (null): alles gedruckt.
 */
export function clipHeightMm(layer: number | null | undefined, layerHeightMm: number, nLayers: number): number {
  if (layer === null || layer === undefined || !Number.isFinite(layer)) return Infinity;
  const k = Math.min(Math.max(Math.floor(layer), 0), Math.max(nLayers, 0));
  return k * layerHeightMm;
}

/** Schnittebene in W: behalten wird z_P <= zClip (die Normale zeigt in den behaltenen Bereich). */
export function clipPlaneInW(zClip: number, T_WP: Matrix4): Plane {
  return new Plane(new Vector3(0, 0, -1), zClip).applyMatrix4(T_WP);
}

/** Linienstuecke (Punktpaare, flach) der Ringe, deren Schicht `keep` besteht. */
export function ringSegments(tp: Toolpath, keep: (layer: number) => boolean): Float32Array {
  const out: number[] = [];
  for (const ring of tp.rings) {
    if (!keep(ring.layer)) continue;
    const w = ring.waypoints;
    const n = w.length;
    const last = ring.closed ? n : n - 1;
    for (let i = 0; i < last; i++) {
      const a = w[i];
      const b = w[(i + 1) % n];
      if (!a || !b) continue;
      out.push(a[0], a[1], a[2], b[0], b[1], b[2]);
    }
  }
  return new Float32Array(out);
}
