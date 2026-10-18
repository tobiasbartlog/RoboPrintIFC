import { useEffect } from 'react';
import { useStl } from './assets';

interface WorkstationProps {
  meshUrl: string;
  color: string;
  /** Hindernis hervorheben (Tisch ist das kritische Paar). */
  highlight: string | null;
  onLoaded?: () => void;
  onError?: (e: Error) => void;
}

/** Doosantisch: Mesh-Koordinaten sind bereits Frame W (mm), keine Transformation. */
export function Workstation({ meshUrl, color, highlight, onLoaded, onError }: WorkstationProps) {
  const geometry = useStl(meshUrl, onError);
  useEffect(() => {
    if (geometry) onLoaded?.();
  }, [geometry, onLoaded]);
  if (!geometry) return null;
  return (
    <mesh geometry={geometry} name="workstation">
      <meshStandardMaterial
        color={highlight ?? color}
        emissive={highlight ?? '#000000'}
        emissiveIntensity={highlight ? 0.45 : 0}
        roughness={0.85}
        metalness={0.05}
        flatShading
      />
    </mesh>
  );
}
