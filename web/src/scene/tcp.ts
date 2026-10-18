import { Matrix4, Quaternion, Vector3, type Object3D } from 'three';
import { mat4FromRows, matrixToPose7 } from './math';
import type { Mat4Rows, Pose7 } from './types';

export const FLANGE_LINK = 'link_6';

/**
 * Gerenderte TCP-Pose in W (mm): Weltmatrix des Flansch-Glieds im Szenengraphen (ohne die
 * 1000er-Skalierung der URDF-Gruppe) mal T_FT aus scene.json. Das ist die Groesse, die die
 * Debug-Schnittstelle als `tcpRendered` meldet und gegen `tcp[i]` des Artefakts prueft.
 */
export function tcpFromScene(flange: Object3D, T_FT: Mat4Rows): Pose7 {
  flange.updateWorldMatrix(true, false);
  const p = new Vector3();
  const q = new Quaternion();
  flange.matrixWorld.decompose(p, q, new Vector3());
  const T_WF = new Matrix4().compose(p, q, new Vector3(1, 1, 1));
  return matrixToPose7(T_WF.multiply(mat4FromRows(T_FT)));
}
