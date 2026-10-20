import { useEffect, useMemo } from 'react';
import { DoubleSide } from 'three';
import type { SceneTool } from '../contracts';
import { useStl } from './assets';
import { mat4FromRows } from './math';
import { TransformGroup } from './TransformGroup';

interface ToolProps {
  tool: SceneTool;
  meshUrl: string;
  color: string;
  /** Farbe, wenn das Werkzeug (`tool_body`) am kritischen Paar beteiligt ist. */
  highlight: string | null;
  onLoaded?: () => void;
  onError?: (e: Error) => void;
}

/**
 * Werkzeug im Flansch-Anker (mm, Frame F): Mesh ueber `mesh_transform`, TCP-Marke ueber `T_FT`.
 * Dieselbe `T_FT` benutzt `tcpFromScene`, die Marke macht sie sichtbar.
 */
export function Tool({ tool, meshUrl, color, highlight, onLoaded, onError }: ToolProps) {
  const geometry = useStl(meshUrl, onError);
  useEffect(() => {
    if (geometry) onLoaded?.();
  }, [geometry, onLoaded]);
  const meshM = useMemo(() => mat4FromRows(tool.mesh_transform), [tool.mesh_transform]);
  const tcpM = useMemo(() => mat4FromRows(tool.T_FT), [tool.T_FT]);
  return (
    <>
      {geometry && (
        <TransformGroup matrix={meshM} name="tool_body">
          <mesh geometry={geometry}>
            <meshStandardMaterial
              color={highlight ?? color}
              emissive={highlight ?? '#000000'}
              emissiveIntensity={highlight ? 0.5 : 0}
              roughness={0.6}
              side={DoubleSide}
              flatShading
            />
          </mesh>
        </TransformGroup>
      )}
      <TransformGroup matrix={tcpM} name="tcp_marker">
        <axesHelper args={[40]} />
      </TransformGroup>
    </>
  );
}
