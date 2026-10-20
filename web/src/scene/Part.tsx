import { useMemo } from 'react';
import { DoubleSide, type BufferGeometry, type Matrix4, type Plane } from 'three';
import type { PartArtifact } from '../contracts';
import { useStl } from './assets';
import { clipHeightMm, clipPlaneAboveInW, clipPlaneInW, mat4FromRows } from './math';
import { TransformGroup } from './TransformGroup';

interface PartProps {
  part: PartArtifact;
  stlUrl: string;
  layerHeightMm: number;
  /** Fertig gedruckte Schichten laut Druckfortschritt (`progress.ts`); null = alles gedruckt. */
  layer: number | null;
  /**
   * Druckstand der Kollisionspruefung k (Artefakt `layer[i]`). Er zaehlt nur bei hervorgehobenem
   * Hindernis: Dann ist genau z_P <= k*h eingefaerbt, auch wenn k vom Gedruckten abweicht.
   */
  obstacleLayer?: number | null;
  color: string;
  ghostColor: string;
  /** Farbe, wenn der Druckstand das Hindernis des kritischen Paars ist. */
  highlight: string | null;
  onError?: (e: Error) => void;
}

/** Ebenen fuer die Scheibe z_P in [lo, hi] (Frame P); offene Seiten ohne Ebene. */
function slabPlanes(lo: number, hi: number, zTop: number, T_WP: Matrix4): Plane[] {
  const planes: Plane[] = [];
  if (Number.isFinite(hi) && hi < zTop) planes.push(clipPlaneInW(hi, T_WP));
  if (lo > 0) planes.push(clipPlaneAboveInW(lo, T_WP));
  return planes;
}

interface SlabProps {
  geometry: BufferGeometry;
  planes: Plane[];
  color: string;
  glow: boolean;
  /** Durchsichtig: Hindernis der Pruefung, das noch nicht gedruckt ist. */
  ghost?: boolean;
  name: string;
}

function Slab({ geometry, planes, color, glow, ghost = false, name }: SlabProps) {
  return (
    <mesh geometry={geometry} name={name} renderOrder={ghost ? 2 : 0}>
      <meshStandardMaterial
        color={color}
        emissive={glow ? color : '#000000'}
        emissiveIntensity={glow ? 0.45 : 0}
        roughness={0.9}
        side={DoubleSide}
        clippingPlanes={planes}
        transparent={ghost}
        opacity={ghost ? 0.45 : 1}
        depthWrite={!ghost}
        flatShading
      />
    </mesh>
  );
}

/**
 * Teil in Frame P (part.stl) mit T_WP nach W. Die fertigen Schichten z_P <= k*h sind deckend, das
 * ganze Teil darueber als Geist. Eine Schnittebene markiert die Druckhoehe. Ist der Druckstand das
 * Hindernis, ist genau sein Anteil eingefaerbt; Hindernis ueber dem Gedruckten (Travel zur
 * naechsten Schale) erscheint halb durchsichtig.
 */
export function Part({ part, stlUrl, layerHeightMm, layer, obstacleLayer = null, color, ghostColor, highlight, onError }: PartProps) {
  const geometry = useStl(stlUrl, onError);
  const T_WP = useMemo(() => mat4FromRows(part.T_WP), [part.T_WP]);
  const zTop = part.bbox_P.max[2];
  const zShown = clipHeightMm(layer, layerHeightMm, part.n_layers);
  const zObstacle = highlight && obstacleLayer !== null ? clipHeightMm(obstacleLayer, layerHeightMm, part.n_layers) : zShown;
  // Gedruckt und Hindernis bis zLow, darueber entweder nur gedruckt oder nur Hindernis.
  const zLow = Math.min(zShown, zObstacle);
  const clipping = Number.isFinite(zShown) && zShown < zTop;
  const slabs = useMemo(
    () => ({
      low: slabPlanes(0, zLow, zTop, T_WP),
      printedOnly: zShown > zLow ? slabPlanes(zLow, zShown, zTop, T_WP) : null,
      obstacleOnly: zObstacle > zLow ? slabPlanes(zLow, zObstacle, zTop, T_WP) : null,
    }),
    [zLow, zShown, zObstacle, zTop, T_WP],
  );

  const { min, max } = part.bbox_P;
  const cut = Number.isFinite(zShown) ? Math.min(zShown, zTop) : zTop;
  if (!geometry) return null;
  return (
    <TransformGroup matrix={T_WP} name="part">
      {/* Geist: das ganze Teil, durchsichtig. */}
      <mesh geometry={geometry} renderOrder={1} name="part_ghost">
        <meshStandardMaterial color={ghostColor} transparent opacity={0.16} depthWrite={false} side={DoubleSide} />
      </mesh>
      {/* Gedruckt: deckend, an der Schnittebene abgeschnitten. */}
      {zLow > 0 && <Slab geometry={geometry} planes={slabs.low} color={highlight ?? color} glow={!!highlight} name="part_printed" />}
      {slabs.printedOnly && <Slab geometry={geometry} planes={slabs.printedOnly} color={color} glow={false} name="part_printed_free" />}
      {slabs.obstacleOnly && highlight && (
        <Slab geometry={geometry} planes={slabs.obstacleOnly} color={highlight} glow ghost name="part_obstacle" />
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
