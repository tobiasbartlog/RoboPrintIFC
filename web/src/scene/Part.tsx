import { useMemo } from 'react';
import { DoubleSide } from 'three';
import type { PartArtifact } from '../contracts';
import { useStl } from './assets';
import { clipHeightMm, clipPlaneInW, mat4FromRows } from './math';
import { TransformGroup } from './TransformGroup';

interface PartProps {
  part: PartArtifact;
  stlUrl: string;
  layerHeightMm: number;
  /** Anzahl fertiger Schichten k (Artefakt `layer[i]`); null = alles gedruckt. */
  layer: number | null;
  color: string;
  ghostColor: string;
  /** Farbe, wenn der Druckstand das Hindernis des kritischen Paars ist. */
  highlight: string | null;
  onError?: (e: Error) => void;
}

/**
 * Teil in Frame P (part.stl) mit T_WP nach W. Der gedruckte Anteil z_P <= k*h ist deckend, das
 * ganze Teil darueber als Geist. Eine Schnittebene markiert die Druckhoehe.
 */
export function Part({ part, stlUrl, layerHeightMm, layer, color, ghostColor, highlight, onError }: PartProps) {
  const geometry = useStl(stlUrl, onError);
  const T_WP = useMemo(() => mat4FromRows(part.T_WP), [part.T_WP]);
  const zClip = clipHeightMm(layer, layerHeightMm, part.n_layers);
  const zTop = part.bbox_P.max[2];
  const clipping = Number.isFinite(zClip) && zClip < zTop;
  const planes = useMemo(() => (clipping ? [clipPlaneInW(zClip, T_WP)] : []), [clipping, zClip, T_WP]);

  const { min, max } = part.bbox_P;
  const cut = Number.isFinite(zClip) ? Math.min(zClip, zTop) : zTop;
  if (!geometry) return null;
  return (
    <TransformGroup matrix={T_WP} name="part">
      {/* Geist: das ganze Teil, durchsichtig. */}
      <mesh geometry={geometry} renderOrder={1} name="part_ghost">
        <meshStandardMaterial color={ghostColor} transparent opacity={0.16} depthWrite={false} side={DoubleSide} />
      </mesh>
      {/* Gedruckt: deckend, an der Schnittebene abgeschnitten. */}
      {zClip > 0 && (
        <mesh geometry={geometry} name="part_printed">
          <meshStandardMaterial
            color={highlight ?? color}
            emissive={highlight ?? '#000000'}
            emissiveIntensity={highlight ? 0.45 : 0}
            roughness={0.9}
            side={DoubleSide}
            clippingPlanes={planes}
            flatShading
          />
        </mesh>
      )}
      {clipping && (
        <mesh position={[(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, cut]} renderOrder={2} name="cut_plane">
          <planeGeometry args={[max[0] - min[0] + 80, max[1] - min[1] + 80]} />
          <meshBasicMaterial color={ghostColor} transparent opacity={0.18} side={DoubleSide} depthWrite={false} />
        </mesh>
      )}
    </TransformGroup>
  );
}
