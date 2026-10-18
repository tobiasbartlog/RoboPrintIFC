import { Html, Line } from '@react-three/drei';
import type { SceneSample } from './types';

interface ContactOverlayProps {
  sample: SceneSample | null;
  color: string;
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
      <Line points={[pa, pb]} color={color} lineWidth={3} depthTest={false} renderOrder={10} />
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
