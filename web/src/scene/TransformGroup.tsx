import { useMemo, type ReactNode } from 'react';
import { Quaternion, Vector3, type Matrix4 } from 'three';

/** Gruppe mit fester Pose aus einer Matrix (Translation, Rotation, optionale Skalierung). */
export function TransformGroup({ matrix, children, name }: { matrix: Matrix4; children?: ReactNode; name?: string }) {
  const { p, q, s } = useMemo(() => {
    const p = new Vector3();
    const q = new Quaternion();
    const s = new Vector3();
    matrix.decompose(p, q, s);
    return { p, q, s };
  }, [matrix]);
  return (
    <group name={name} position={p} quaternion={q} scale={s}>
      {children}
    </group>
  );
}
