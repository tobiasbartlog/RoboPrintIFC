import { Html } from '@react-three/drei';
import { useThree } from '@react-three/fiber';
import { useEffect, useLayoutEffect, useMemo } from 'react';
import { Line2 } from 'three/examples/jsm/lines/Line2.js';
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import type { SceneSample } from './types';

interface ContactOverlayProps {
  sample: SceneSample | null;
  color: string;
}

/**
 * Kontaktlinie als Line2. Material und Geometrie leben so lange wie die Komponente; bei jedem
 * Sample werden nur die Punkte gesetzt. (drei `<Line>` verwirft bei neuen Punkten auch das
 * Material, was jedes Mal den Shader neu übersetzt, mit Software-WebGL ~1 s je Sample.)
 */
function ContactLine({ a, b, color }: { a: readonly number[]; b: readonly number[]; color: string }) {
  const size = useThree((s) => s.size);
  const invalidate = useThree((s) => s.invalidate);
  const { line, geometry, material } = useMemo(() => {
    const geometry = new LineGeometry();
    geometry.setPositions([0, 0, 0, 0, 0, 1]);
    const material = new LineMaterial({ linewidth: 3, depthTest: false });
    const line = new Line2(geometry, material);
    line.renderOrder = 10;
    return { line, geometry, material };
  }, []);
  useEffect(
    () => () => {
      geometry.dispose();
      material.dispose();
    },
    [geometry, material],
  );
  useLayoutEffect(() => {
    geometry.setPositions([a[0] ?? 0, a[1] ?? 0, a[2] ?? 0, b[0] ?? 0, b[1] ?? 0, b[2] ?? 0]);
    line.computeLineDistances();
    invalidate();
  }, [a, b, geometry, line, invalidate]);
  useLayoutEffect(() => {
    material.color.set(color);
    material.resolution.set(size.width, size.height);
    invalidate();
  }, [color, size.width, size.height, material, invalidate]);
  return <primitive object={line} />;
}

/** Zeugenpunkte und Kontaktlinie (Frame W, mm) bei Warnung oder Kollision. */
export function ContactOverlay({ sample, color }: ContactOverlayProps) {
  if (!sample || !sample.witness) return null;
  if (sample.status !== 'collision' && sample.status !== 'warn') return null;
  const [a, b] = sample.witness;
  const pa: [number, number, number] = [a[0] ?? 0, a[1] ?? 0, a[2] ?? 0];
  const pb: [number, number, number] = [b[0] ?? 0, b[1] ?? 0, b[2] ?? 0];
  const mid: [number, number, number] = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2];
  const d = sample.d_mm;
  return (
    <group name="contact_overlay">
      <ContactLine a={a} b={b} color={color} />
      {[pa, pb].map((p, i) => (
        <mesh key={i} position={p} renderOrder={10}>
          <sphereGeometry args={[7, 16, 12]} />
          <meshBasicMaterial color={color} depthTest={false} />
        </mesh>
      ))}
      {typeof d === 'number' && (
        <Html position={mid} center style={{ pointerEvents: 'none', whiteSpace: 'nowrap' }}>
          <span style={{ color, fontWeight: 600, fontSize: 13 }}>{`${d.toFixed(1)} mm`}</span>
        </Html>
      )}
    </group>
  );
}
