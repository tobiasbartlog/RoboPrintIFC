import { Matrix4, Plane, Quaternion, Vector3 } from 'three';
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
 * Hoehe der Schnittebene im Frame P (mm) fuer k fertige Schichten: gedruckt ist z_P <= k * h
 * (spec/ARTEFAKTE.md). k ist der Druckfortschritt (`progress.ts`) oder, fuer das Hindernis, der
 * Kollisions-Druckstand `layer[i]`. Ohne Schicht (null): alles gedruckt.
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

/** Schnittebene in W: behalten wird z_P >= zLow (Unterkante eines Bands). */
export function clipPlaneAboveInW(zLow: number, T_WP: Matrix4): Plane {
  return new Plane(new Vector3(0, 0, 1), -zLow).applyMatrix4(T_WP);
}
