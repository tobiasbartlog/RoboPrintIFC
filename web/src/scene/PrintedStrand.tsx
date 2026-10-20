import { useThree } from '@react-three/fiber';
import { useEffect, useLayoutEffect, useMemo } from 'react';
import { BufferAttribute, BufferGeometry, DoubleSide } from 'three';
import type { PrintedState } from './progress';
import { BEAD_VERTS, beadBuffer, beadsDone, layerRange, strandCut, writeTipBead, type StrandLayout } from './strand';

interface PrintedStrandProps {
  layout: StrandLayout;
  printed: PrintedState;
  /** Strangbreite und Schichthoehe aus dem Toolpath (mm). */
  widthMm: number;
  heightMm: number;
  color: string;
  /** Farbe, wenn der Druckstand das Hindernis des kritischen Paars ist. */
  highlight: string | null;
}

function Material({ color, highlight }: { color: string; highlight: string | null }) {
  // polygonOffset: Die Bahnlinie auf der Oberkante bleibt vor der Raupe sichtbar.
  return (
    <meshStandardMaterial
      color={highlight ?? color}
      emissive={highlight ?? '#000000'}
      emissiveIntensity={highlight ? 0.45 : 0}
      roughness={0.9}
      side={DoubleSide}
      flatShading
      polygonOffset
      polygonOffsetFactor={1}
      polygonOffsetUnits={1}
    />
  );
}

/**
 * Gedruckter Strang der laufenden Schicht (Frame W) als Raupen auf dem fertigen Volumen: Ringe und
 * Verbinder bis genau zur Duese. Die Geometrie entsteht je Schicht einmal; ein Uhrschritt setzt nur
 * den drawRange und die Raupe der Spitze neu.
 */
export function PrintedStrand({ layout, printed, widthMm, heightMm, color, highlight }: PrintedStrandProps) {
  const invalidate = useThree((s) => s.invalidate);
  const { from, to } = layerRange(layout, printed.layers);
  const { body, buf } = useMemo(() => {
    const buf = beadBuffer(layout, from, to, widthMm, heightMm);
    const body = new BufferGeometry();
    body.setAttribute('position', new BufferAttribute(buf.positions, 3));
    body.setAttribute('normal', new BufferAttribute(buf.normals, 3));
    return { body, buf };
  }, [layout, from, to, widthMm, heightMm]);
  const tip = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(new Float32Array(BEAD_VERTS * 3), 3));
    g.setAttribute('normal', new BufferAttribute(new Float32Array(BEAD_VERTS * 3), 3));
    return g;
  }, []);
  useEffect(() => () => body.dispose(), [body]);
  useEffect(() => () => tip.dispose(), [tip]);

  const pos = printed.pos;
  useLayoutEffect(() => {
    const cut = strandCut(layout, pos);
    body.setDrawRange(0, beadsDone(buf, cut));
    const inLayer = cut.piece >= buf.from && cut.piece < buf.to;
    const p = tip.getAttribute('position') as BufferAttribute;
    const n = tip.getAttribute('normal') as BufferAttribute;
    const drawn = inLayer && writeTipBead(p.array as Float32Array, n.array as Float32Array, layout, cut, widthMm, heightMm);
    if (drawn) {
      p.needsUpdate = true;
      n.needsUpdate = true;
      tip.computeBoundingSphere();
    }
    tip.setDrawRange(0, drawn ? BEAD_VERTS : 0);
    invalidate();
  }, [layout, pos, body, buf, tip, widthMm, heightMm, invalidate]);

  return (
    <group name="printed_strand">
      <mesh geometry={body} name="strand_beads" frustumCulled={false}>
        <Material color={color} highlight={highlight} />
      </mesh>
      <mesh geometry={tip} name="strand_tip" frustumCulled={false}>
        <Material color={color} highlight={highlight} />
      </mesh>
    </group>
  );
}
