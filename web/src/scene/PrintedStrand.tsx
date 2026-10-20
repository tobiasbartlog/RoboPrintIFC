import { useThree } from '@react-three/fiber';
import { useEffect, useLayoutEffect, useMemo } from 'react';
import { BufferAttribute, BufferGeometry, DoubleSide } from 'three';
import type { PrintedState } from './progress';
import { kindColorFn } from './kindColors';
import { BEAD_VERTS, beadBuffer, beadsDone, hasPatternKinds, layerRange, strandCut, writeTipBead, type StrandLayout } from './strand';

interface PrintedStrandProps {
  layout: StrandLayout;
  printed: PrintedState;
  /** Strangbreite und Schichthoehe aus dem Toolpath (mm). */
  widthMm: number;
  heightMm: number;
  color: string;
  /** Farbe, wenn der Druckstand das Hindernis des kritischen Paars ist. */
  highlight: string | null;
  /** Farben der Musterarten (infill, web, outfill); null = einfarbig wie ohne Muster. */
  kindColors?: Record<string, string> | null;
}

function Material({ color, highlight, vertexColors }: { color: string; highlight: string | null; vertexColors: boolean }) {
  // polygonOffset: Die Bahnlinie auf der Oberkante bleibt vor der Raupe sichtbar.
  // Mit Vertexfarben (Muster) multipliziert `white` nichts weg; bei einem Treffer gilt die Warnfarbe.
  const tinted = vertexColors && !highlight;
  return (
    <meshStandardMaterial
      key={tinted ? 'kind-colors' : 'plain'}
      color={highlight ?? (tinted ? 'white' : color)}
      vertexColors={tinted}
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
export function PrintedStrand({ layout, printed, widthMm, heightMm, color, highlight, kindColors = null }: PrintedStrandProps) {
  const invalidate = useThree((s) => s.invalidate);
  const { from, to } = layerRange(layout, printed.layers);
  const colorOf = useMemo(
    () => (kindColors && hasPatternKinds(layout) ? kindColorFn(kindColors, color) : undefined),
    [kindColors, layout, color],
  );
  const { body, buf } = useMemo(() => {
    const buf = beadBuffer(layout, from, to, widthMm, heightMm, colorOf);
    const body = new BufferGeometry();
    body.setAttribute('position', new BufferAttribute(buf.positions, 3));
    body.setAttribute('normal', new BufferAttribute(buf.normals, 3));
    if (buf.colors) body.setAttribute('color', new BufferAttribute(buf.colors, 3));
    return { body, buf };
  }, [layout, from, to, widthMm, heightMm, colorOf]);
  const tip = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(new Float32Array(BEAD_VERTS * 3), 3));
    g.setAttribute('normal', new BufferAttribute(new Float32Array(BEAD_VERTS * 3), 3));
    if (colorOf) g.setAttribute('color', new BufferAttribute(new Float32Array(BEAD_VERTS * 3), 3));
    return g;
  }, [colorOf]);
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
      const col = tip.getAttribute('color') as BufferAttribute | undefined;
      const c = colorOf?.(layout.paths[cut.piece]?.kind ?? '');
      if (col && c) {
        for (let j = 0; j < BEAD_VERTS; j++) col.setXYZ(j, c[0], c[1], c[2]);
        col.needsUpdate = true;
      }
      p.needsUpdate = true;
      n.needsUpdate = true;
      tip.computeBoundingSphere();
    }
    tip.setDrawRange(0, drawn ? BEAD_VERTS : 0);
    invalidate();
  }, [layout, pos, body, buf, tip, widthMm, heightMm, colorOf, invalidate]);

  return (
    <group name="printed_strand">
      <mesh geometry={body} name="strand_beads" frustumCulled={false}>
        <Material color={color} highlight={highlight} vertexColors={colorOf !== undefined} />
      </mesh>
      <mesh geometry={tip} name="strand_tip" frustumCulled={false}>
        <Material color={color} highlight={highlight} vertexColors={colorOf !== undefined} />
      </mesh>
    </group>
  );
}
